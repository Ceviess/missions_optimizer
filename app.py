import streamlit as st
import requests
import pandas as pd
import pulp
from collections import Counter
from constants import TRAITS_DICT

st.set_page_config(
    page_title="Tacticus operations optimizer", layout="wide", page_icon="⚔️"
)

if "units_df" not in st.session_state:
    st.session_state.units_df = None

if "missions" not in st.session_state:
    st.session_state.missions = []

MISSION_LEVELS = {
    "Обычная": {
        "min_rank": 0,
        "min_progression_index": 0,
        "base_xp": 20,
        "base_crusade": 3,
        "bonus_crusade": 3,
    },
    "Необычная": {
        "min_rank": 3,
        "min_progression_index": 3,
        "base_xp": 60,
        "base_crusade": 4,
        "bonus_crusade": 8,
    },
    "Редкая": {
        "min_rank": 6,
        "min_progression_index": 6,
        "base_xp": 200,
        "base_crusade": 6,
        "bonus_crusade": 12,
    },
    "Эпическая": {
        "min_rank": 9,
        "min_progression_index": 9,
        "base_xp": 720,
        "base_crusade": 9,
        "bonus_crusade": 15,
    },
}


def apply_mission_level(mission_index):
    """Заполняет параметры миссии по выбранному уровню."""
    level = st.session_state[f"level_{mission_index}"]
    level_config = MISSION_LEVELS[level]

    mission = st.session_state.missions[mission_index]

    for field, value in level_config.items():
        mission[field] = value

        st.session_state[f"{field}_{mission_index}"] = value


def get_all_possible_requirements(traits_dict, units_df=None, missions=None):
    """Собирает уникальный список всех возможные тегов из всех источников"""
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
        "Синапс"
    }

    if TRAITS_DICT:
        for val in TRAITS_DICT.values():
            if isinstance(val, list):
                options.update(val)
            elif isinstance(val, str):
                options.add(val)

    if units_df is not None:
        if "faction" in units_df.columns:
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
        response = requests.get(f"{BASE_URL}{ENDPOINT}", headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            units = pd.DataFrame(data=data["player"]["units"])[
                ["name", "grandAlliance", "faction", "rank", "progressionIndex"]
            ]
            units["id"] = range(len(units))
            units["traits"] = (
                units["name"]
                .map(TRAITS_DICT)
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
                x.strip() for x in m_copy["bonus_requirements"].split(",") if x.strip()
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
        prob += pulp.lpSum([x[(c, m_id)] for c in char_ids]) == m["slots"] * y[m_id]

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

    # Формируем структуру с результатами
    results = {
        "status": pulp.LpStatus[prob.status],
        "total_score": pulp.value(prob.objective),
        "missions": [],
    }

    if prob.status == pulp.LpStatusOptimal:
        for m in missions:
            m_id = m["id"]
            assigned_chars = [c for c in char_ids if pulp.value(x[(c, m_id)]) == 1]
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


# --- ИНТЕРФЕЙС STREAMLIT ---

st.title("Оптимизатор операций")

# Боковая панель: API и веса
with st.sidebar:
    st.header("Подключение API")
    api_key = st.text_input("Вставьте X-API-KEY:", type="password")



    if st.button(
        "📥 Загрузить данные игрока", type="primary", use_container_width=True
    ):
        if not api_key:
            st.error("Укажите API Key!")
        elif not TRAITS_DICT:
            st.error("Загрузите словарь особеннностей JSON!")
        else:
            with st.spinner("Запрос к API Tacticus..."):
                df, err = fetch_player_data(api_key, TRAITS_DICT)
                if err:
                    st.error(err)
                else:
                    st.session_state.units_df = df
                    st.success(f"Загружено персонажей: {len(df)}")

    st.divider()
    st.header("Веса Наград")
    weights = {
        "base_xp": st.number_input("Вес: очки операций", value=5.0, step=0.1),
        "base_crusade": st.number_input("Вес: очки крестового похода", value=5.0, step=1.0),
        "bonus_crusade": st.number_input("Вес: бонусные очки крествого похода", value=2.0, step=1.0),
        "bonus_power": st.number_input("Вес: бонус силы", value=1.0, step=1.0),
        "bonus_intel": st.number_input("Вес: бонус разведданные", value=1.0, step=1.0),
        "bonus_bombs": st.number_input("Вес: бонус боеприпасы", value=1.0, step=1.0),
    }

all_possible_reqs = get_all_possible_requirements(
    TRAITS_DICT, st.session_state.units_df, st.session_state.missions
)

# Вкладки главного экрана
tab_missions, tab_units, tab_results = st.tabs(
    ["Настройка Миссий", "Персонажи", "Результат"]
)

# 1. ВКЛАДКА: НАСТРОЙКА МИССИЙ
with tab_missions:
    st.subheader("Редактирование миссий")

    # Кнопки добавления/сброса
    col_btn1, col_btn2 = st.columns([1, 4])
    with col_btn1:
        if st.button("➕ Добавить миссию"):
            new_id = max([m["id"] for m in st.session_state.missions], default=-1) + 1
            st.session_state.missions.append(
                {
                    "id": new_id,
                    "level": "Обычная",
                    "slots": 4,
                    "grandAlliance": ["Imperial"],
                    "min_rank": 0,
                    "min_progression_index": 0,
                    "bonus_requirements": "",
                    "base_crusade": 3,
                    "base_xp": 20,
                    "bonus_power": 0,
                    "bonus_crusade": 3,
                    "bonus_intel": 0,
                    "bonus_bombs": 0,
                }
            )
            st.rerun()

    # Отображаем миссии в форме карточек/аккордеонов
    missions_to_delete = []

    for i, m in enumerate(st.session_state.missions):
        with st.expander(f"Миссия ID #{m['id']}", expanded=True):
            level_options = list(MISSION_LEVELS.keys())

            current_level = m.get("level", "Обычная")

            if current_level not in level_options:
                current_level = "Обычная"
                m["level"] = current_level

            st.selectbox(
                "Уровень миссии",
                options=level_options,
                index=level_options.index(current_level),
                key=f"level_{i}",
                on_change=apply_mission_level,
                args=(i,),
            )
            col1, col2, col3 = st.columns([2, 2, 1])

            with col1:
                m["slots"] = st.number_input(
                    f"Слоты",
                    min_value=1,
                    max_value=5,
                    value=m["slots"],
                    key=f"slots_{i}",
                )
                m["grandAlliance"] = st.multiselect(
                    "Grand Alliance",
                    ["Imperial", "Chaos", "Xenos"],
                    default=(
                        m["grandAlliance"]
                        if isinstance(m["grandAlliance"], list)
                        else [m["grandAlliance"]]
                    ),
                    key=f"ga_{i}",
                )

            with col2:
                m["bonus_power"] = st.number_input(
                    "Бонус силы", value=m["bonus_power"], key=f"bnpow_{i}"
                )
                m["bonus_intel"] = st.number_input(
                    "Бонус разведданные", value=m.get("bonus_intel", 0), key=f"bnint_{i}"
                )
                m["bonus_bombs"] = st.number_input(
                    "Бонус бомбы", value=m.get("bonus_bombs", 0), key=f"bnbom_{i}"
                )

            with col3:
                st.write("")
                st.write("")
                if st.button("❌ Удалить", key=f"del_{i}"):
                    missions_to_delete.append(i)

            # --- Удобный выбор бонусных требований ---
            st.markdown("**Бонусные требования:**")

            # Подсчитываем текущее количество для каждого свойства
            req_list = (
                m["bonus_requirements"]
                if isinstance(m["bonus_requirements"], list)
                else [
                    x.strip() for x in m["bonus_requirements"].split(",") if x.strip()
                ]
            )
            current_counts = Counter(req_list)
            selected_options = list(current_counts.keys())

            # Выпадающий список мульти-выбора
            chosen = st.multiselect(
                "Выберите фракции / особенности:",
                options=sorted(list(set(all_possible_reqs + selected_options))),
                default=selected_options,
                key=f"req_ms_{i}",
            )

            # Если выбрано несколько одинаковых тегов (например, 2 x
            # SpaceWolves), выводим счетчики количества
            final_req_list = []
            if chosen:
                q_cols = st.columns(min(len(chosen), 4))
                for idx, req_item in enumerate(chosen):
                    default_qty = current_counts.get(req_item, 1)
                    qty = q_cols[idx % 4].number_input(
                        f"К-во '{req_item}':",
                        min_value=1,
                        max_value=5,
                        value=default_qty,
                        key=f"qty_{i}_{req_item}",
                    )
                    final_req_list.extend([req_item] * qty)

            m["bonus_requirements"] = final_req_list
    # Удаляем отмеченные миссии
    if missions_to_delete:
        for index in sorted(missions_to_delete, reverse=True):
            st.session_state.missions.pop(index)
        st.rerun()

# 2. ВКЛАДКА: ПЕРСОНАЖИ
with tab_units:
    if st.session_state.units_df is not None:
        st.dataframe(st.session_state.units_df, use_container_width=True)
    else:
        st.info("Загрузите данные игрока с помощью панели слева.")

# 3. ВКЛАДКА: РЕЗУЛЬТАТЫ
with tab_results:
    if st.button(
        "Запустить расчет оптимизации", type="primary", use_container_width=True
    ):
        if st.session_state.units_df is None:
            st.error("Сначала загрузите данные игрока!")
        else:
            with st.spinner("Ищем наилучшее распределение..."):
                res = optimize_missions(
                    st.session_state.units_df, st.session_state.missions, weights
                )

                if res["status"] == "Optimal":
                    st.success(f"Оптимизация успешна! Итоговая ценность наград: **{res['total_score']:.2f}**")
                    for m_res in res["missions"]:
                        if not m_res["assigned_chars"]:
                            st.warning(f"**Миссия #{m_res['id']}**: ПРОПУЩЕНА (недостаточно подпадающих персонажей)")
                            continue

                        status_str = (
                            "🟢 ВЫПОЛНЕНА С БОНУСАМИ"
                            if m_res["is_bonus"]
                            else "🟡 ВЫПОЛНЕНА (Только базовые)"
                        )

                        with st.container():
                            st.markdown(f"#### Миссия #{m_res['id']+1} — {status_str}")
                            st.write(f"**Назначено ({len(m_res['assigned_chars'])}/{m_res['slots']}):** {', '.join(m_res['assigned_chars'])}")

                            if m_res["reqs"] and not m_res["is_bonus"]:
                                st.caption(f"Бонусы не собраны. Требовалось: {', '.join(m_res['reqs'])}")
                            st.divider()
                else:
                    st.error(
                        "Не удалось найти оптимальное решение для заданных условий."
                    )
