"""
Конфигурация классов для YOLO Node Detection.

36 классов оборудования P&ID после очистки данных.

Маппинг классов:
- При обучении классы 34 (annotation), 36 (truba), 37 (unknown) были удалены
- Классы 35 (output) и 38 (strelka) переиндексированы в 34 и 35
- REVERSE_REINDEX возвращает их к исходным значениям для совместимости с разметкой
"""

NUM_CLASSES = 36

CLASS_NAMES = {
    0: "armatura_ruchn",           # Арматура ручная
    1: "klapan_obratn",            # Клапан обратный
    2: "regulator_ruchn",          # Регулятор ручной
    3: "armatura_electro",         # Арматура электропривод
    4: "regulator_electro",        # Регулятор электропривод
    5: "drossel",                  # Дроссель
    6: "perehod",                  # Переход
    7: "klapan_obratn_seroprivod", # Клапан обратный серопривод
    8: "armatura_seroprivod",      # Арматура серопривод
    9: "regulator_seroprivod",     # Регулятор серопривод
    10: "armatura_membr_electro",  # Арматура мембранная электро
    11: "nasos",                   # Насос
    12: "ventilaytor",             # Вентилятор
    13: "predohran",               # Предохранительный клапан
    14: "condensatootvod",         # Конденсатоотводчик
    15: "rashodomernaya_shaiba",   # Расходомерная шайба
    16: "vodostruiniy_nasos",      # Водоструйный насос
    17: "teploobmen",              # Теплообменник
    18: "zaglushka",               # Заглушка
    19: "gidrozatvor",             # Гидрозатвор
    20: "bak",                     # Бак
    21: "voronka",                 # Воронка
    22: "filtr_meh",               # Фильтр механический
    23: "separator",               # Сепаратор
    24: "kapleulov",               # Каплеуловитель
    25: "celindr_turb",            # Цилиндр турбины
    26: "redukcion_ustr",          # Редукционное устройство
    27: "bistro_redukc_ustr",      # Быстродействующее редукционное устройство
    28: "separator_paro",          # Сепаратор паро
    29: "dearator",                # Деаэратор
    30: "silfonnii_kompensator",   # Сильфонный компенсатор
    31: "electronagrevat",         # Электронагреватель
    32: "smotrowoe_steclo",        # Смотровое стекло
    33: "datchik",                 # Датчик
    34: "output",                  # Выход
    35: "strelka",                 # Стрелка направления
}

# Обратный маппинг: имя -> id
CLASS_IDS = {v: k for k, v in CLASS_NAMES.items()}

# Обратная переиндексация для совместимости с исходной разметкой
# Модель выдаёт 34, 35 → возвращаем к исходным 35, 38
REVERSE_REINDEX = {
    34: 35,  # output
    35: 38,  # strelka
}