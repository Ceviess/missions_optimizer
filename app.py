from collections import Counter
import streamlit as st

from constants import TRAITS_DICT, RARITY_REQUIREMENTS, MISSION_REWARDS, BONUS_TYPES
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

if "global_duration" not in st.session_state:
    st.session_state.global_duration = "8 ч"


def apply_mission_level(mission_index):
    """Заполняет параметры миссии с учетом 1 активного типа бонусной награды."""
    mission = st.session_state.missions[mission_index]

    duration = st.session_state.global_duration
    level = st.session_state.get(
        f"level_{mission_index}", mission.get("level", "Обычная")
    )
    bonus_type = st.session_state.get(
        f"bonus_type_{mission_index}", mission.get("bonus_type", "Без бонуса")
    )

    mission["level"] = level
    mission["bonus_type"] = bonus_type

    # Применяем требования по рангу
    rarity_config = RARITY_REQUIREMENTS.get(level, {})
    for field, value in rarity_config.items():
        mission[field] = value

    # Базовые награды
    rewards_table = MISSION_REWARDS.get(duration, {}).get(level, {})
    mission["base_xp"] = rewards_table.get("base_xp", 0)
    mission["base_crusade"] = rewards_table.get("base_crusade", 0)
    mission["bonus_crusade"] = rewards_table.get("bonus_crusade", 0)

    # По умолчанию все 3 бонусных ресурса равны 0
    mission["bonus_power"] = 0
    mission["bonus_intel"] = 0
    mission["bonus_bombs"] = 0

    # Активируем только один выбранный бонус из таблицы
    active_field = BONUS_TYPES.get(bonus_type)
    if active_field and active_field in rewards_table:
        mission[active_field] = rewards_table[active_field]


def update_all_missions_duration():
    """Пересчитывает параметры всех миссий при изменении глобальной продолжительности."""
    duration = st.session_state.global_duration
    available_levels = list(MISSION_REWARDS[duration].keys())

    for i, m in enumerate(st.session_state.missions):
        # Если выбранная ранее редкость недоступна для новой длительности, сбрасываем на первую доступную
        if m["level"] not in available_levels:
            m["level"] = available_levels[0]
            st.session_state[f"level_{i}"] = available_levels[0]

        apply_mission_level(i)

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
        "📌 **Что нужно сделать:** Выберите продолжительность операций, "
        "добавьте нужные операции и укажите их уровень сложности (редкость) и требования к составу."
    )
    all_possible_reqs = get_all_possible_requirements(
        TRAITS_DICT, st.session_state.units_df, st.session_state.missions
    )

    # --- ГЛОБАЛЬНЫЙ ВЫБОР ДЛИТЕЛЬНОСТИ ---
    st.selectbox(
        "⏱️ **Продолжительность всех миссий:**",
        options=list(MISSION_REWARDS.keys()),
        index=list(MISSION_REWARDS.keys()).index(
            st.session_state.global_duration
        ),
        key="global_duration",
        on_change=update_all_missions_duration,
    )

    st.divider()

    # --- ДОБАВЛЕНИЕ НОВОЙ МИССИИ ---
    if st.button("➕ Добавить операцию"):
        new_id = (
                max([m["id"] for m in st.session_state.missions], default=-1) + 1
        )

        available_levels = list(
            MISSION_REWARDS[st.session_state.global_duration].keys()
        )
        default_level = available_levels[0]

        default_rewards = MISSION_REWARDS[
            st.session_state.global_duration
        ][default_level]
        default_reqs = RARITY_REQUIREMENTS[default_level]

        st.session_state.missions.append(
            {
                "id": new_id,
                "level": default_level,
                "bonus_type": "Без бонуса",
                "slots": 4,
                "grandAlliance": ["Imperial"],
                "min_rank": default_reqs["min_rank"],
                "min_progression_index": default_reqs["min_progression_index"],
                "bonus_requirements": "",
                "base_crusade": default_rewards["base_crusade"],
                "base_xp": default_rewards["base_xp"],
                "bonus_crusade": default_rewards["bonus_crusade"],
                "bonus_power": 0,
                "bonus_intel": 0,
                "bonus_bombs": 0,
            }
        )
        st.rerun()

    missions_to_delete = []

    # --- СПИСОК МИССИЙ ---
    for i, m in enumerate(st.session_state.missions):
        with st.expander(f"Миссия ID #{m['id']+1}", expanded=True):
            # Доступные варианты редкости зависят от выбранной глобальной длительности
            available_levels = list(
                MISSION_REWARDS[st.session_state.global_duration].keys()
            )

            current_level = m.get("level", available_levels[0])
            if current_level not in available_levels:
                current_level = available_levels[0]
                m["level"] = current_level

            # Выбор редкости конкретной миссии
            st.selectbox(
                "Уровень операции (редкость)",
                options=available_levels,
                index=available_levels.index(current_level),
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
                bonus_options = list(BONUS_TYPES.keys())
                current_bonus_type = m.get("bonus_type", "Без бонуса")

                if current_bonus_type not in bonus_options:
                    current_bonus_type = "Без бонуса"

                # Селектбокс выбора 1 возможного бонуса
                st.selectbox(
                    "Тип бонусной награды",
                    options=bonus_options,
                    index=bonus_options.index(current_bonus_type),
                    key=f"bonus_type_{i}",
                    on_change=apply_mission_level,
                    args=(i,),
                )

                # Вывод активного значения
                active_field = BONUS_TYPES.get(
                    st.session_state.get(f"bonus_type_{i}", current_bonus_type)
                )
                if active_field:
                    val = m.get(active_field, 0)
                    st.caption(f"Значение бонуса из таблицы: **+{val}**")
                else:
                    st.caption("Дополнительный бонус отключен (0)")

            with col3:
                st.write("")
                st.write("")
                if st.button("❌ Удалить", key=f"del_{i}"):
                    missions_to_delete.append(i)

            # Выбор тегов бонусных требований
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