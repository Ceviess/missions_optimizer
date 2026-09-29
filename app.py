from collections import Counter
import streamlit as st

from constants import TRAITS_DICT
from utils import get_all_possible_requirements, fetch_player_data, optimize_missions

st.set_page_config(
    page_title="Tacticus operations optimizer", layout="wide", page_icon="⚔️"
)

if "units_df" not in st.session_state:
    st.session_state.units_df = None

if "missions" not in st.session_state:
    st.session_state.missions = []

if "weights" not in st.session_state:
    st.session_state.weights = {
        "base_xp": 2,
        "base_crusade": 2,
        "bonus_crusade": 2,
        "bonus_power": 1,
        "bonus_intel": 1,
        "bonus_bombs": 1,
    }

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

# --- ОСНОВНОЙ ИНТЕРФЕЙС ---

st.title("⚔️ Tacticus Operations Optimizer")

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    [
        "1️⃣ Веса наград",
        "2️⃣ API и Загрузка",
        "3️⃣ Настройка миссий",
        "4️⃣ Расчет и Результат",
        "5️⃣ Персонажи",
    ]
)

# ---------------------------------------------------------
# ШАГ 1: Ввод весов наград
# ---------------------------------------------------------
with tab1:
    st.header("Шаг 1: Настройка ценности наград")
    st.info(
        "📌 **Что нужно сделать:** Укажите приоритеты для каждого типа ресурсов. "
        "Оптимизатор будет отдавать преимущество тем миссиям и бонусам, которые дают ресурсы с наибольшим весом."
    )

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Базовые награды")
        st.session_state.weights["base_xp"] = st.number_input(
            "Вес: Очки операций (XP)",
            value=int(st.session_state.weights["base_xp"]),
            step=int(1),
            key="w_base_xp",
        )
        st.session_state.weights["base_crusade"] = st.number_input(
            "Вес: Очки крестового похода",
            value=int(st.session_state.weights["base_crusade"]),
            step=int(1),
            key="w_base_crusade",
        )

    with col2:
        st.subheader("Бонусные награды")
        st.session_state.weights["bonus_crusade"] = st.number_input(
            "Вес: Бонусные очки крестового похода",
            value=int(st.session_state.weights["bonus_crusade"]),
            step=1,
            key="w_bonus_crusade",
        )
        st.session_state.weights["bonus_power"] = st.number_input(
            "Вес: Бонус силы",
            value=int(st.session_state.weights["bonus_power"]),
            step=1,
            key="w_bonus_power",
        )
        st.session_state.weights["bonus_intel"] = st.number_input(
            "Вес: Бонус разведданных",
            value=int(st.session_state.weights["bonus_intel"]),
            step=1,
            key="w_bonus_intel",
        )
        st.session_state.weights["bonus_bombs"] = st.number_input(
            "Вес: Бонус боеприпасы",
            value=int(st.session_state.weights["bonus_bombs"]),
            step=1,
            key="w_bonus_bombs",
        )


# ---------------------------------------------------------
# ШАГ 2: Ввод API и загрузка персонажей
# ---------------------------------------------------------
with tab2:
    st.header("Шаг 2: Подключение к API и импорт данных")
    st.info(
        "📌 **Что нужно сделать:** Вставьте ваш персональный `X-API-KEY` из игры Tacticus "
        "и нажмите кнопку **«Загрузить данные игрока»**, чтобы получить актуальный ростер персонажей."
    )

    api_key_input = st.text_input(
        "Вставьте X-API-KEY:", type="password", key="api_key_field"
    )

    if st.button("📥 Загрузить данные игрока", type="primary"):
        if not api_key_input:
            st.error("Укажите API Key!")
        elif not TRAITS_DICT:
            st.error("Отсутствует словарь особенностей TRAITS_DICT!")
        else:
            with st.spinner("Запрос к API Tacticus..."):
                df, err = fetch_player_data(api_key_input, TRAITS_DICT)
                if err:
                    st.error(err)
                else:
                    st.session_state.units_df = df
                    st.success(f"✅ Персонажи загружены ({len(st.session_state.units_df)} шт.). Можете переходить к следующему шагу.")

# ---------------------------------------------------------
# ШАГ 3: Настройка миссий
# ---------------------------------------------------------
with tab3:
    st.header("Шаг 3: Конфигурация активных миссий")
    st.info(
        "📌 **Что нужно сделать:** Добавьте операции"
        "Для каждой операции выберите её уровень редкости, количество слотов, альянс и бонусы."
    )

    all_possible_reqs = get_all_possible_requirements(
        TRAITS_DICT, st.session_state.units_df, st.session_state.missions
    )

    if st.button("➕ Добавить миссию"):
        new_id = (
            max([m["id"] for m in st.session_state.missions], default=-1) + 1
        )
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

    missions_to_delete = []

    for i, m in enumerate(st.session_state.missions):
        with st.expander(f"Миссия ID #{m['id']}", expanded=True):
            level_options = list(MISSION_LEVELS.keys())
            current_level = m.get("level", "Обычная")

            if current_level not in level_options:
                current_level = "Обычная"
                m["level"] = current_level

            st.selectbox(
                "Редкость миссии",
                options=level_options,
                index=level_options.index(current_level),
                key=f"level_{i}",
                on_change=apply_mission_level,
                args=(i,),
            )
            col1, col2, col3 = st.columns([2, 2, 1])

            with col1:
                m["slots"] = st.number_input(
                    "Слоты",
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
                    "Бонус разведданные",
                    value=m.get("bonus_intel", 0),
                    key=f"bnint_{i}",
                )
                m["bonus_bombs"] = st.number_input(
                    "Бонус бомбы",
                    value=m.get("bonus_bombs", 0),
                    key=f"bnbom_{i}",
                )

            with col3:
                st.write("")
                st.write("")
                if st.button("❌ Удалить", key=f"del_{i}"):
                    missions_to_delete.append(i)

            st.markdown("**Бонусные требования:**")
            req_list = (
                m["bonus_requirements"]
                if isinstance(m["bonus_requirements"], list)
                else [
                    x.strip()
                    for x in m["bonus_requirements"].split(",")
                    if x.strip()
                ]
            )
            current_counts = Counter(req_list)
            selected_options = list(current_counts.keys())

            chosen = st.multiselect(
                "Выберите фракции / особенности:",
                options=sorted(
                    list(set(all_possible_reqs + selected_options))
                ),
                default=selected_options,
                key=f"req_ms_{i}",
            )

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

    if missions_to_delete:
        for index in sorted(missions_to_delete, reverse=True):
            st.session_state.missions.pop(index)
        st.rerun()


# ---------------------------------------------------------
# ШАГ 4: Запуск расчета и результат
# ---------------------------------------------------------
with tab4:
    st.header("Шаг 4: Расчет и оптимальное распределение")
    st.info(
        "📌 **Что нужно сделать:** Убедитесь, что все данные загружены и миссии настроены, "
        "после чего нажмите кнопку ниже для запуска математической оптимизации."
    )

    if st.button(
        "🚀 Запустить расчет оптимизации",
        type="primary",
        use_container_width=True,
    ):
        if st.session_state.units_df is None:
            st.error("❌ Сначала загрузите данные игрока на Вкладке 2!")
        elif not st.session_state.missions:
            st.warning("⚠️ Добавьте хотя бы одну миссию на Вкладке 3!")
        else:
            with st.spinner("Ищем наилучшее распределение ростера..."):
                res = optimize_missions(
                    st.session_state.units_df,
                    st.session_state.missions,
                    st.session_state.weights,
                )

                if res["status"] == "Optimal":
                    st.success(
                        f"🏆 Оптимизация завершена успешно! Итоговая ценность наград: **{res['total_score']:.2f}**"
                    )
                    for m_res in res["missions"]:
                        if not m_res["assigned_chars"]:
                            st.warning(
                                f"**Миссия #{m_res['id']+1}**: ПРОПУЩЕНА (недостаточно подходящих персонажей)"
                            )
                            continue

                        status_str = (
                            "🟢 ВЫПОЛНЕНА С БОНУСАМИ"
                            if m_res["is_bonus"]
                            else "🟡 ВЫПОЛНЕНА (Только базовые)"
                        )

                        with st.container():
                            st.markdown(
                                f"#### Миссия #{m_res['id']+1} — {status_str}"
                            )
                            st.write(
                                f"**Назначено ({len(m_res['assigned_chars'])}/{m_res['slots']}):** {', '.join(m_res['assigned_chars'])}"
                            )

                            if m_res["reqs"] and not m_res["is_bonus"]:
                                st.caption(
                                    f"Бонусы не собраны. Требовалось: {', '.join(m_res['reqs'])}"
                                )
                            st.divider()
                else:
                    st.error(
                        "Не удалось найти оптимальное решение для заданных условий."
                    )


# ---------------------------------------------------------
# ШАГ 5: Загруженные персонажи
# ---------------------------------------------------------
with tab5:
    st.header("Просмотр ростера персонажей для дебага")
    st.info(
        "📌 **Описание:** Здесь отображается полная таблица загруженных персонажей игрока, "
        "их ранги, фракции и особенности."
    )

    if st.session_state.units_df is not None:
        st.dataframe(st.session_state.units_df, use_container_width=True)
    else:
        st.warning(
            "Персонажи ещё не загружены. Перейдите на Вкладку 2 («API и Загрузка») для импорта данных."
        )