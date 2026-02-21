"""All keyboards, label mappings and delivery estimates."""

from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ── Data lists (label, callback_value) ──────────────────────────────

COUNTRIES = [
    ("🇨🇳 Китай", "china"),
    ("🇹🇷 Турция", "turkey"),
    ("🇦🇪 ОАЭ", "uae"),
    ("🇮🇱 Израиль", "israel"),
    ("🌍 Другая", "other"),
]

CITIES_BY_COUNTRY: dict[str, list[str]] = {
    "china": ["Гуанчжоу", "Шанхай", "Пекин", "Иу", "Шэньчжэнь", "Нинбо"],
    "turkey": ["Стамбул", "Анкара", "Измир", "Мерсин", "Анталья"],
    "uae": ["Дубай", "Абу-Даби", "Шарджа", "Аджман"],
    "israel": ["Тель-Авив", "Хайфа", "Ашдод", "Иерусалим"],
}

CARGO_TYPES = [
    ("📦 Генеральный", "general"),
    ("⚠️ Опасный", "dangerous"),
    ("📐 Негабаритный", "oversized"),
    ("🔄 Сборный", "consolidated"),
    ("📋 Другой", "other"),
]

WEIGHT_PRESETS = [
    ("До 100 кг", "w_100"),
    ("100–500 кг", "w_500"),
    ("500 кг – 1 т", "w_1000"),
    ("1–5 тонн", "w_5000"),
    ("5–20 тонн", "w_20000"),
    ("20+ тонн", "w_20000p"),
]

VOLUME_PRESETS = [
    ("До 1 м³", "v_1"),
    ("1–5 м³", "v_5"),
    ("5–10 м³", "v_10"),
    ("10–33 м³ (20')", "v_33"),
    ("33–67 м³ (40')", "v_67"),
    ("67+ м³", "v_67p"),
]

URGENCY_OPTIONS = [
    ("🕐 Стандарт (15–25 дн)", "standard"),
    ("⚡ Экспресс (7–12 дн)", "express"),
    ("🚀 Срочная (3–6 дн)", "urgent"),
]

INCOTERMS_OPTIONS = [
    ("EXW — самовывоз", "exw"),
    ("FOB — до порта", "fob"),
    ("CIF — с страховкой", "cif"),
    ("DDP — до двери", "ddp"),
    ("❓ Не знаю / помочь", "unknown"),
]

# ── Quick label look-ups (callback_value → emoji label) ─────────────

COUNTRY_LABELS: dict[str, str] = {v: lbl for lbl, v in COUNTRIES}
CARGO_LABELS: dict[str, str] = {v: lbl for lbl, v in CARGO_TYPES}
WEIGHT_LABELS: dict[str, str] = {v: lbl for lbl, v in WEIGHT_PRESETS}
VOLUME_LABELS: dict[str, str] = {v: lbl for lbl, v in VOLUME_PRESETS}
URGENCY_LABELS: dict[str, str] = {v: lbl for lbl, v in URGENCY_OPTIONS}
INCOTERMS_LABELS: dict[str, str] = {v: lbl for lbl, v in INCOTERMS_OPTIONS}

# ── Weight/Volume → approximate float for DB ────────────────────────

WEIGHT_TO_FLOAT: dict[str, float] = {
    "w_100": 50, "w_500": 300, "w_1000": 750,
    "w_5000": 3000, "w_20000": 12500, "w_20000p": 25000,
}

VOLUME_TO_FLOAT: dict[str, float] = {
    "v_1": 0.5, "v_5": 3, "v_10": 7.5,
    "v_33": 21.5, "v_67": 50, "v_67p": 80,
}

# ── Delivery estimation by country + urgency ─────────────────────────

DELIVERY_INFO: dict[str, dict[str, str]] = {
    "china": {
        "standard": "🚢 Морская доставка — 18–25 дней",
        "express": "🚂 Ж/Д доставка — 10–14 дней",
        "urgent": "✈️ Авиадоставка — 3–6 дней",
    },
    "turkey": {
        "standard": "🚛 Автодоставка — 10–15 дней",
        "express": "🚛 Экспресс-авто — 5–8 дней",
        "urgent": "✈️ Авиадоставка — 2–4 дня",
    },
    "uae": {
        "standard": "🚢 Морская доставка — 15–20 дней",
        "express": "🚢+🚛 Мульти — 8–12 дней",
        "urgent": "✈️ Авиадоставка — 2–4 дня",
    },
    "israel": {
        "standard": "🚢 Морская доставка — 10–15 дней",
        "express": "🚢+🚛 Мульти — 5–8 дней",
        "urgent": "✈️ Авиадоставка — 2–3 дня",
    },
}

DEFAULT_DELIVERY: dict[str, str] = {
    "standard": "🚢 Стандартная — 15–25 дней",
    "express": "⚡ Экспресс — 7–12 дней",
    "urgent": "✈️ Авиа / срочная — 3–6 дней",
}


# ── Keyboard builders ───────────────────────────────────────────────

def country_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for label, data in COUNTRIES:
        b.button(text=label, callback_data=f"country:{data}")
    b.adjust(2, 2, 1)
    return b.as_markup()


def city_kb(country: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    cities = CITIES_BY_COUNTRY.get(country, [])
    for city in cities:
        b.button(text=city, callback_data=f"city:{city}")
    b.button(text="✏️ Другой город", callback_data="city:__custom__")
    cols = 3 if len(cities) >= 6 else 2
    b.adjust(cols)
    return b.as_markup()


def cargo_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for label, data in CARGO_TYPES:
        b.button(text=label, callback_data=f"cargo:{data}")
    b.adjust(2, 2, 1)
    return b.as_markup()


def weight_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for label, data in WEIGHT_PRESETS:
        b.button(text=label, callback_data=f"weight:{data}")
    b.button(text="✏️ Ввести точно", callback_data="weight:__custom__")
    b.adjust(2, 2, 2, 1)
    return b.as_markup()


def volume_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for label, data in VOLUME_PRESETS:
        b.button(text=label, callback_data=f"volume:{data}")
    b.button(text="✏️ Ввести точно", callback_data="volume:__custom__")
    b.adjust(2, 2, 2, 1)
    return b.as_markup()


def urgency_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for label, data in URGENCY_OPTIONS:
        b.button(text=label, callback_data=f"urgency:{data}")
    b.adjust(1)
    return b.as_markup()


def incoterms_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for label, data in INCOTERMS_OPTIONS:
        b.button(text=label, callback_data=f"terms:{data}")
    b.adjust(1)
    return b.as_markup()


def phone_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Отправить номер", request_contact=True)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def skip_comment_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏭ Пропустить", callback_data="skip_comment")]
        ]
    )


def after_submit_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📎 Добавить документы", callback_data="action:docs")],
            [InlineKeyboardButton(text="✏️ Уточнить детали", callback_data="action:details")],
            [InlineKeyboardButton(text="📞 Связаться с менеджером", callback_data="action:call")],
            [InlineKeyboardButton(text="🔄 Новая заявка", callback_data="action:restart")],
        ]
    )


def admin_lead_kb(lead_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ В работу",
                    callback_data=f"adm:progress:{lead_id}",
                ),
                InlineKeyboardButton(
                    text="📞 Позвонить",
                    callback_data=f"adm:call:{lead_id}",
                ),
            ]
        ]
    )
