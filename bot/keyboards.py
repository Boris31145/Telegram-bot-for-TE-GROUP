"""All keyboards and label mappings used by the bot."""

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

CARGO_TYPES = [
    ("📦 Генеральный", "general"),
    ("⚠️ Опасный", "dangerous"),
    ("📐 Негабаритный", "oversized"),
    ("🔄 Сборный", "consolidated"),
    ("📋 Другой", "other"),
]

URGENCY_OPTIONS = [
    ("🕐 Стандарт (15–25 дн)", "standard"),
    ("⚡ Экспресс (7–12 дн)", "express"),
    ("🚀 Срочная (3–5 дн)", "urgent"),
]

INCOTERMS_OPTIONS = [
    ("EXW", "exw"),
    ("FOB", "fob"),
    ("CIF", "cif"),
    ("DDP", "ddp"),
    ("❓ Не знаю", "unknown"),
]

# ── Quick label look-ups (callback_value → emoji label) ─────────────

COUNTRY_LABELS: dict[str, str] = {v: lbl for lbl, v in COUNTRIES}
CARGO_LABELS: dict[str, str] = {v: lbl for lbl, v in CARGO_TYPES}
URGENCY_LABELS: dict[str, str] = {v: lbl for lbl, v in URGENCY_OPTIONS}
INCOTERMS_LABELS: dict[str, str] = {v: lbl for lbl, v in INCOTERMS_OPTIONS}


# ── Keyboard builders ───────────────────────────────────────────────

def country_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for label, data in COUNTRIES:
        b.button(text=label, callback_data=f"country:{data}")
    b.adjust(2, 2, 1)
    return b.as_markup()


def cargo_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for label, data in CARGO_TYPES:
        b.button(text=label, callback_data=f"cargo:{data}")
    b.adjust(2, 2, 1)
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
    b.adjust(2, 2, 1)
    return b.as_markup()


def phone_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Отправить номер", request_contact=True)]],
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
