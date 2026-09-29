import pandas as pd
import pulp
import requests
from collections import Counter


def get_all_possible_requirements(traits_dict, units_df=None, missions=None):
    """Собирает уникальный список всех возможных тегов из всех источников"""
    options = {
        "SpaceWolves",
        "Custodes",
        "Ultramarines",
        "BlackTemplars",
        "DeathGuard",
        "ThousandSons",
        "Зверебой",
        "Предсмертное возмездие",
        "Страшилище",
        "Сокрушающий удар",
        "Урон: Силовой",
        "Урон: Болтер",
        "Урон: Потрошение",
        "Только ближний бой",
        "Летающий",
        "Стремительный натиск",
        "Глубинный удар",
        "Прикрывающий огонь",
        "Дальний бой",
        "Ясновидец",
        "Синапс",
    }

    if traits_dict:
        for val in traits_dict.values():
            if isinstance(val, list):
                options.update(val)
            elif isinstance(val, str):
                options.add(val)

    if units_df is not None and "faction" in units_df.columns:
        options.update(units_df["faction"].dropna().unique())

    if missions:
        for m in missions:
            reqs = m.get("bonus_requirements", [])
            if isinstance(reqs, list):
                options.update(reqs)
            elif isinstance(reqs, str):
                options.update([x.strip() for x in reqs.split(",") if x.strip()])

    return sorted(list(options))


def fetch_player_data(api_key, traits_dict):
    BASE_URL = "https://api.tacticusgame.com"
    ENDPOINT = "/api/v1/player"
    headers = {"X-API-KEY": api_key, "Accept": "application/json"}

    try:
        response = requests.get(
            f"{BASE_URL}{ENDPOINT}", headers=headers, timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            units = pd.DataFrame(data=data["player"]["units"])[
                ["name", "grandAlliance", "faction", "rank", "progressionIndex"]
            ]
            units["id"] = range(len(units))
            units["traits"] = (
                units["name"]
                .map(traits_dict)
                .fillna("")
                .apply(lambda x: x if isinstance(x, list) else [])
            )
            units = units[
                ~units["name"].isin(
                    [
                        "Malleus Rocket Launcher",
                        "Forgefiend",
                        "Biovore",
                        "Z'Kar",
                        "Galatian",
                        "Plagueburst Crawler",
                        "Exorcist",
                        "Storm Speeder",
                        "Reanimator",
                        "Rukkatrukk",
                        "Tson'ji",
                    ]
                )
            ]
            return units, None
        else:
            return None, f"Ошибка API {response.status_code}: {response.text}"
    except Exception as e:
        return None, f"Ошибка при подключении: {str(e)}"


def optimize_missions(df_collection, raw_missions, weights):
    prob = pulp.LpProblem("Mission_Optimization", pulp.LpMaximize)
    char_ids = df_collection["id"].tolist()

    missions = []
    for m in raw_missions:
        m_copy = m.copy()
        if isinstance(m_copy.get("bonus_requirements"), str):
            m_copy["bonus_requirements"] = [
                x.strip()
                for x in m_copy["bonus_requirements"].split(",")
                if x.strip()
            ]
        missions.append(m_copy)

    mission_ids = [m["id"] for m in missions]

    x = pulp.LpVariable.dicts(
        "assign", ((c, m) for c in char_ids for m in mission_ids), cat="Binary"
    )
    y = pulp.LpVariable.dicts("base_completed", mission_ids, cat="Binary")
    z = pulp.LpVariable.dicts("bonus_completed", mission_ids, cat="Binary")

    # 1. Один персонаж — максимум 1 миссия
    for c in char_ids:
        prob += pulp.lpSum([x[(c, m)] for m in mission_ids]) <= 1

    for m in missions:
        m_id = m["id"]

        # 2. Ограничение слотов
        prob += (
            pulp.lpSum([x[(c, m_id)] for c in char_ids]) == m["slots"] * y[m_id]
        )

        # 3. Бонус только при базовом выполнении
        prob += z[m_id] <= y[m_id]

        req_counts = Counter(m.get("bonus_requirements", []))

        # Базовые ограничения
        for c in char_ids:
            char_row = df_collection[df_collection["id"] == c].iloc[0]
            eligible = True

            if char_row["rank"] < m.get("min_rank", 0):
                eligible = False
            if char_row["progressionIndex"] < m.get("min_progression_index", 0):
                eligible = False

            ga_req = m["grandAlliance"]
            if isinstance(ga_req, list):
                if char_row["grandAlliance"] not in ga_req:
                    eligible = False
            else:
                if char_row["grandAlliance"] != ga_req:
                    eligible = False

            if not eligible:
                prob += x[(c, m_id)] == 0

        # Бонусные требования
        for req, needed_amount in req_counts.items():
            prob += (
                pulp.lpSum(
                    [
                        x[(c, m_id)]
                        * (
                            1
                            if (
                                req
                                == df_collection.loc[
                                    df_collection["id"] == c, "faction"
                                ].values[0]
                                or req
                                in df_collection.loc[
                                    df_collection["id"] == c, "traits"
                                ].values[0]
                            )
                            else 0
                        )
                        for c in char_ids
                    ]
                )
                >= needed_amount * z[m_id]
            )

    # Целевая функция
    objective = 0
    for m in missions:
        m_id = m["id"]
        for key, value in m.items():
            if key.startswith("base_") and key in weights:
                objective += y[m_id] * value * weights[key]
            if (
                key.startswith("bonus_")
                and key != "bonus_requirements"
                and key in weights
            ):
                objective += z[m_id] * value * weights[key]

    prob += objective
    prob.solve(pulp.PULP_CBC_CMD(msg=False))

    results = {
        "status": pulp.LpStatus[prob.status],
        "total_score": pulp.value(prob.objective),
        "missions": [],
    }

    if prob.status == pulp.LpStatusOptimal:
        for m in missions:
            m_id = m["id"]
            assigned_chars = [
                c for c in char_ids if pulp.value(x[(c, m_id)]) == 1
            ]
            names = df_collection[df_collection["id"].isin(assigned_chars)][
                "name"
            ].tolist()

            results["missions"].append(
                {
                    "id": m_id,
                    "is_base": pulp.value(y[m_id]) == 1,
                    "is_bonus": pulp.value(z[m_id]) == 1,
                    "assigned_chars": names,
                    "slots": m["slots"],
                    "reqs": m.get("bonus_requirements", []),
                }
            )

    return results