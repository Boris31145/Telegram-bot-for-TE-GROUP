"""
TE GROUP bot — single-message funnel, two tracks.

Track 1 · 🛃 Таможня  — cargo → country → invoice → urgency → phone → comment
Track 2 · 🚚 Доставка — country → city → cargo → weight → volume → urgency → incoterms → phone → comment

One card message is edited at every step.
Every step has a ← Назад button.
Phone step: card is edited + a separate message with ReplyKeyboard is sent.
"""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardRemove,
)

from bot.config import settings
from bot.db import get_lead, save_lead, update_lead_status
from bot.keyboards import (
    CARGO_LABELS,
    COUNTRY_LABELS,
    CUSTOMS_SAVINGS,
    CUSTOMS_URGENCY_INFO,
    CUSTOMS_URGENCY_LABELS,
    DEFAULT_DELIVERY,
    DELIVERY_INFO,
    INCOTERMS_LABELS,
    INVOICE_LABELS,
    INVOICE_TO_FLOAT,
    SERVICE_LABELS,
    URGENCY_LABELS,
    VOLUME_LABELS,
    VOLUME_TO_FLOAT,
    WEIGHT_LABELS,
    WEIGHT_TO_FLOAT,
    admin_lead_kb,
    after_submit_kb,
    cargo_kb,
    city_kb,
    country_kb,
    customs_urgency_kb,
    incoterms_kb,
    invoice_kb,
    phone_kb,
    service_kb,
    skip_comment_kb,
    urgency_kb,
    volume_kb,
    weight_kb,
)
from bot.states import OrderForm

logger = logging.getLogger(__name__)
router = Router()

TOTAL_CUSTOMS  = 5   # cargo, country, invoice, urgency, phone
TOTAL_DELIVERY = 8   # country, city, cargo, weight, volume, urgency, incoterms, phone

_DIV = "─" * 18

_WELCOME = (
    "<b>✦  TE GROUP  ✦</b>\n"
    "<i>Таможня · Логистика · ЕАЭС</i>\n\n"
    "Оформляем грузы в <b>Кыргызстане</b> —\n"
    "участнике Таможенного союза ЕАЭС.\n\n"
    "Ввозим товары из любой точки мира\n"
    "и доставляем в <b>Россию, Казахстан,\n"
    "Беларусь</b> и другие страны союза.\n\n"
    f"{_DIV}\n"
    "Выберите услугу:"
)

# First-screen text for customs (shown after picking service:customs)
_CUSTOMS_INTRO = (
    "<b>✦  TE GROUP  ✦</b>  <i>· Таможня ·</i>\n\n"
    "Растаможим ваш товар в <b>Кыргызстане</b>.\n\n"
    "КР — член ЕАЭС с <b>самыми низкими ставками</b>\n"
    "в союзе для ввоза товара в Россию.\n"
    "Легально, быстро, со всеми документами.\n\n"
    f"{_DIV}\n"
    "📦 <b>Что за товар хотите растаможить?</b>"
)


# ── Helpers ───────────────────────────────────────────────────────────

def _bar(step: int, total: int) -> str:
    """Progress bar: ●●●○○  3/5"""
    if step <= 0 or total <= 0:
        return ""
    filled = "●" * min(step, total)
    empty  = "○" * max(0, total - step)
    return f"<i>{filled}{empty}  {step}/{total}</i>"


def _card(data: dict, step: int, question: str = "") -> str:
    """
    Build the single card message edited in-place.
    Uses correct total steps and field set based on data['service'].
    """
    service = data.get("service", "delivery")
    total   = TOTAL_CUSTOMS if service == "customs" else TOTAL_DELIVERY

    if service == "customs":
        header = "<b>✦  TE GROUP  ✦</b>  <i>· Таможня ·</i>"
    else:
        header = "<b>✦  TE GROUP  ✦</b>  <i>· Доставка ·</i>"

    lines: list[str] = [header]
    bar = _bar(step, total)
    if bar:
        lines.append(bar)

    fields: list[str] = []

    if service == "customs":
        if data.get("cargo_type"):
            lbl = CARGO_LABELS.get(data["cargo_type"], data["cargo_type"])
            fields.append(f"  ✅  Товар — <b>{lbl}</b>")
        if data.get("country"):
            lbl = COUNTRY_LABELS.get(data["country"], data["country"])
            fields.append(f"  ✅  Страна — <b>{lbl}</b>")
        if data.get("invoice_value"):
            lbl = INVOICE_LABELS.get(data["invoice_value"], f"${data['invoice_value']}")
            fields.append(f"  ✅  Стоимость — <b>{lbl}</b>")
        if data.get("customs_urgency"):
            lbl = CUSTOMS_URGENCY_LABELS.get(data["customs_urgency"], data["customs_urgency"])
            fields.append(f"  ✅  Срочность — <b>{lbl}</b>")
            info = CUSTOMS_URGENCY_INFO.get(data["customs_urgency"], "")
            if info:
                fields.append(f"       💡 <i>{info}</i>")
    else:
        if data.get("country"):
            lbl = COUNTRY_LABELS.get(data["country"], data["country"])
            fields.append(f"  ✅  Страна — <b>{lbl}</b>")
        if data.get("city_from"):
            fields.append(f"  ✅  Город  — <b>{data['city_from']}</b>")
        if data.get("cargo_type"):
            lbl = CARGO_LABELS.get(data["cargo_type"], data["cargo_type"])
            fields.append(f"  ✅  Груз   — <b>{lbl}</b>")
        if data.get("weight_kg"):
            lbl = WEIGHT_LABELS.get(data["weight_kg"], f"{data['weight_kg']} кг")
            fields.append(f"  ✅  Вес    — <b>{lbl}</b>")
        if data.get("volume_m3"):
            lbl = VOLUME_LABELS.get(data["volume_m3"], f"{data['volume_m3']} м³")
            fields.append(f"  ✅  Объём  — <b>{lbl}</b>")
        if data.get("urgency"):
            lbl = URGENCY_LABELS.get(data["urgency"], data["urgency"])
            fields.append(f"  ✅  Срочность — <b>{lbl}</b>")
            info = DELIVERY_INFO.get(data.get("country", ""), DEFAULT_DELIVERY).get(data["urgency"], "")
            if info:
                fields.append(f"       💡 <i>{info}</i>")
        if data.get("incoterms"):
            lbl = INCOTERMS_LABELS.get(data["incoterms"], data["incoterms"])
            fields.append(f"  ✅  Условия — <b>{lbl}</b>")

    if fields:
        lines.append("")
        lines.extend(fields)

    if question:
        lines.append(f"\n{_DIV}")
        lines.append(question)

    return "\n".join(lines)


def _with_back(kb: InlineKeyboardMarkup, back_cb: str) -> InlineKeyboardMarkup:
    """Append a ← Назад row to any inline keyboard."""
    rows = list(kb.inline_keyboard)
    rows.append([InlineKeyboardButton(text="← Назад", callback_data=back_cb)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _edit_card(
    bot: Bot,
    chat_id: int,
    msg_id: int,
    text: str,
    markup: InlineKeyboardMarkup | None = None,
) -> int:
    """Edit the card in place. Fall back to a new message if editing fails."""
    try:
        await bot.edit_message_text(
            text,
            chat_id=chat_id,
            message_id=msg_id,
            reply_markup=markup,
        )
        return msg_id
    except Exception:
        new_msg = await bot.send_message(chat_id, text, reply_markup=markup)
        return new_msg.message_id


async def _show_phone_step(
    bot: Bot,
    chat_id: int,
    card_id: int,
    data: dict,
    step: int,
) -> int:
    """
    Edit card to the phone question (clearing any inline keyboard),
    then send a separate message with the ReplyKeyboard share button.
    Returns the updated card message_id.
    """
    # Explicitly pass reply_markup=None to clear old inline buttons
    new_id = await _edit_card(
        bot, chat_id, card_id,
        _card(data, step, "📱 <b>Поделитесь контактом или введите номер:</b>"),
        None,  # ← clear inline keyboard
    )
    await bot.send_message(
        chat_id,
        "👇 Нажмите кнопку ниже или введите номер вручную:",
        reply_markup=phone_kb(),
    )
    return new_id


# ═══════════════════════════════════════════════════════════════════
# 1. /start — welcome screen + service selection
# ═══════════════════════════════════════════════════════════════════

async def _start_flow(message: Message, state: FSMContext) -> None:
    await state.clear()
    msg = await message.answer(_WELCOME, reply_markup=service_kb())
    await state.update_data(card_message_id=msg.message_id)
    await state.set_state(OrderForm.service)


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await _start_flow(message, state)


@router.message(F.text.regexp(r"(?i)^(start|старт)$"))
async def text_start(message: Message, state: FSMContext) -> None:
    await _start_flow(message, state)


# ── Service selection ─────────────────────────────────────────────

@router.callback_query(OrderForm.service, F.data.startswith("service:"))
async def pick_service(cb: CallbackQuery, state: FSMContext) -> None:
    value = cb.data.split(":")[1]  # "customs" or "delivery"
    await state.update_data(service=value)

    if value == "customs":
        # Show customs intro + first question (what goods?)
        await cb.message.edit_text(  # type: ignore[union-attr]
            _CUSTOMS_INTRO,
            reply_markup=_with_back(cargo_kb(), "back:service"),
        )
        await state.set_state(OrderForm.customs_cargo)
    else:
        data = await state.get_data()
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 0, "🌍 <b>Выберите страну отправления:</b>"),
            reply_markup=_with_back(country_kb(), "back:service"),
        )
        await state.set_state(OrderForm.country)

    await cb.answer()


# ═══════════════════════════════════════════════════════════════════
# TRACK 1 — ТАМОЖНЯ
# ═══════════════════════════════════════════════════════════════════

# ── C1. Cargo type (customs) ──────────────────────────────────────

@router.callback_query(OrderForm.customs_cargo, F.data.startswith("cargo:"))
async def pick_customs_cargo(cb: CallbackQuery, state: FSMContext) -> None:
    value = cb.data.split(":")[1]
    await state.update_data(cargo_type=value)
    data = await state.get_data()
    await cb.message.edit_text(  # type: ignore[union-attr]
        _card(data, 1, "🌍 <b>Из какой страны везёте товар?</b>"),
        reply_markup=_with_back(country_kb(), "back:customs_cargo"),
    )
    await state.set_state(OrderForm.customs_country)
    await cb.answer()


# ── C2. Country of origin ─────────────────────────────────────────

@router.callback_query(OrderForm.customs_country, F.data.startswith("country:"))
async def pick_customs_country(cb: CallbackQuery, state: FSMContext) -> None:
    value = cb.data.split(":")[1]

    if value == "other":
        data = await state.get_data()
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 1, "🌍 <b>Введите название страны:</b>"),
            reply_markup=None,
        )
        await cb.answer()
        return

    await state.update_data(country=value)
    data = await state.get_data()
    await cb.message.edit_text(  # type: ignore[union-attr]
        _card(data, 2, "💰 <b>Укажите стоимость товара (USD):</b>\n"
              "<i>Нужно для расчёта таможенных платежей</i>"),
        reply_markup=_with_back(invoice_kb(), "back:customs_country"),
    )
    await state.set_state(OrderForm.invoice_value)
    await cb.answer()


@router.message(OrderForm.customs_country)
async def type_customs_country(message: Message, state: FSMContext, bot: Bot) -> None:
    country = (message.text or "").strip()
    if len(country) < 2:
        await message.answer("⚠️ Введите корректное название страны.")
        return
    await state.update_data(country=country)
    data = await state.get_data()
    card_id = data.get("card_message_id", 0)
    new_id = await _edit_card(
        bot, message.chat.id, card_id,
        _card(data, 2, "💰 <b>Укажите стоимость товара (USD):</b>\n"
              "<i>Нужно для расчёта таможенных платежей</i>"),
        _with_back(invoice_kb(), "back:customs_country"),
    )
    await state.update_data(card_message_id=new_id)
    await state.set_state(OrderForm.invoice_value)


# ── C3. Invoice value ─────────────────────────────────────────────

@router.callback_query(OrderForm.invoice_value, F.data.startswith("invoice:"))
async def pick_invoice(cb: CallbackQuery, state: FSMContext) -> None:
    value = cb.data.split(":")[1]

    if value == "__custom__":
        data = await state.get_data()
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 2, "💰 <b>Введите сумму в USD</b> (например: 15000):"),
            reply_markup=None,
        )
        await cb.answer()
        return

    num = INVOICE_TO_FLOAT.get(value, 0)
    await state.update_data(invoice_value=value, invoice_value_num=num)
    data = await state.get_data()
    await cb.message.edit_text(  # type: ignore[union-attr]
        _card(data, 3, "⏰ <b>Когда нужна доставка?</b>"),
        reply_markup=_with_back(customs_urgency_kb(), "back:invoice"),
    )
    await state.set_state(OrderForm.customs_urgency)
    await cb.answer()


@router.message(OrderForm.invoice_value)
async def type_invoice(message: Message, state: FSMContext, bot: Bot) -> None:
    raw = (message.text or "").replace(",", ".").replace("$", "").strip()
    try:
        num = float(raw)
        if num <= 0:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Введите сумму числом, например: 15000")
        return
    await state.update_data(invoice_value=raw, invoice_value_num=num)
    data = await state.get_data()
    card_id = data.get("card_message_id", 0)
    new_id = await _edit_card(
        bot, message.chat.id, card_id,
        _card(data, 3, "⏰ <b>Когда нужна доставка?</b>"),
        _with_back(customs_urgency_kb(), "back:invoice"),
    )
    await state.update_data(card_message_id=new_id)
    await state.set_state(OrderForm.customs_urgency)


# ── C4. Customs urgency ───────────────────────────────────────────

@router.callback_query(OrderForm.customs_urgency, F.data.startswith("curgency:"))
async def pick_customs_urgency(cb: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    value = cb.data.split(":")[1]
    await state.update_data(customs_urgency=value)
    data = await state.get_data()
    card_id = data.get("card_message_id", 0)
    new_id = await _show_phone_step(bot, cb.message.chat.id, card_id, data, 4)  # type: ignore[union-attr]
    await state.update_data(card_message_id=new_id)
    await state.set_state(OrderForm.phone)
    await cb.answer()


# ═══════════════════════════════════════════════════════════════════
# TRACK 2 — ДОСТАВКА
# ═══════════════════════════════════════════════════════════════════

# ── D1. Country ───────────────────────────────────────────────────

@router.callback_query(OrderForm.country, F.data.startswith("country:"))
async def pick_country(cb: CallbackQuery, state: FSMContext) -> None:
    value = cb.data.split(":")[1]

    if value == "other":
        data = await state.get_data()
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 0, "🌍 <b>Введите название страны:</b>"),
            reply_markup=None,
        )
        await cb.answer()
        return

    await state.update_data(country=value)
    data = await state.get_data()
    await cb.message.edit_text(  # type: ignore[union-attr]
        _card(data, 1, "📍 <b>Выберите город отправления:</b>"),
        reply_markup=_with_back(city_kb(value), "back:country"),
    )
    await state.set_state(OrderForm.city)
    await cb.answer()


@router.message(OrderForm.country)
async def type_other_country(message: Message, state: FSMContext, bot: Bot) -> None:
    country = (message.text or "").strip()
    if len(country) < 2:
        await message.answer("⚠️ Введите корректное название страны.")
        return
    await state.update_data(country=country)
    data = await state.get_data()
    card_id = data.get("card_message_id", 0)
    new_id = await _edit_card(
        bot, message.chat.id, card_id,
        _card(data, 1, "📍 <b>Выберите город отправления:</b>"),
        _with_back(city_kb(country), "back:country"),
    )
    await state.update_data(card_message_id=new_id)
    await state.set_state(OrderForm.city)


# ── D2. City ──────────────────────────────────────────────────────

@router.callback_query(OrderForm.city, F.data.startswith("city:"))
async def pick_city(cb: CallbackQuery, state: FSMContext) -> None:
    # Format: city:<country_key>:<city_name>
    parts = (cb.data or "").split(":", 2)
    if len(parts) < 3:
        await cb.answer("Ошибка формата кнопки.")
        return
    city_name = parts[2]

    data = await state.get_data()
    if city_name == "__custom__":
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 1, "📍 <b>Введите название города:</b>"),
            reply_markup=None,
        )
        await cb.answer()
        return

    await state.update_data(city_from=city_name)
    data = await state.get_data()
    await cb.message.edit_text(  # type: ignore[union-attr]
        _card(data, 2, "📦 <b>Выберите тип груза:</b>"),
        reply_markup=_with_back(cargo_kb(), "back:city"),
    )
    await state.set_state(OrderForm.cargo_type)
    await cb.answer()


@router.message(OrderForm.city)
async def type_city(message: Message, state: FSMContext, bot: Bot) -> None:
    city = (message.text or "").strip()
    if len(city) < 2:
        await message.answer("⚠️ Введите корректное название города.")
        return
    await state.update_data(city_from=city)
    data = await state.get_data()
    card_id = data.get("card_message_id", 0)
    new_id = await _edit_card(
        bot, message.chat.id, card_id,
        _card(data, 2, "📦 <b>Выберите тип груза:</b>"),
        _with_back(cargo_kb(), "back:city"),
    )
    await state.update_data(card_message_id=new_id)
    await state.set_state(OrderForm.cargo_type)


# ── D3. Cargo type (delivery) ─────────────────────────────────────

@router.callback_query(OrderForm.cargo_type, F.data.startswith("cargo:"))
async def pick_cargo(cb: CallbackQuery, state: FSMContext) -> None:
    value = cb.data.split(":")[1]
    await state.update_data(cargo_type=value)
    data = await state.get_data()
    await cb.message.edit_text(  # type: ignore[union-attr]
        _card(data, 3, "⚖️ <b>Укажите вес груза:</b>"),
        reply_markup=_with_back(weight_kb(), "back:cargo"),
    )
    await state.set_state(OrderForm.weight)
    await cb.answer()


# ── D4. Weight ────────────────────────────────────────────────────

@router.callback_query(OrderForm.weight, F.data.startswith("weight:"))
async def pick_weight(cb: CallbackQuery, state: FSMContext) -> None:
    value = cb.data.split(":")[1]

    if value == "__custom__":
        data = await state.get_data()
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 3, "⚖️ <b>Введите точный вес в кг</b> (например: 500):"),
            reply_markup=None,
        )
        await cb.answer()
        return

    await state.update_data(weight_kg=value)
    data = await state.get_data()
    await cb.message.edit_text(  # type: ignore[union-attr]
        _card(data, 4, "📐 <b>Укажите объём груза:</b>"),
        reply_markup=_with_back(volume_kb(), "back:weight"),
    )
    await state.set_state(OrderForm.volume)
    await cb.answer()


@router.message(OrderForm.weight)
async def type_weight(message: Message, state: FSMContext, bot: Bot) -> None:
    raw = (message.text or "").replace(",", ".").strip()
    try:
        w = float(raw)
        if w <= 0:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Введите число больше 0 (например: 500).")
        return
    await state.update_data(weight_kg=str(w))
    data = await state.get_data()
    card_id = data.get("card_message_id", 0)
    new_id = await _edit_card(
        bot, message.chat.id, card_id,
        _card(data, 4, "📐 <b>Укажите объём груза:</b>"),
        _with_back(volume_kb(), "back:weight"),
    )
    await state.update_data(card_message_id=new_id)
    await state.set_state(OrderForm.volume)


# ── D5. Volume ────────────────────────────────────────────────────

@router.callback_query(OrderForm.volume, F.data.startswith("volume:"))
async def pick_volume(cb: CallbackQuery, state: FSMContext) -> None:
    value = cb.data.split(":")[1]

    if value == "__custom__":
        data = await state.get_data()
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 4, "📐 <b>Введите точный объём в м³</b> (например: 2.5):"),
            reply_markup=None,
        )
        await cb.answer()
        return

    await state.update_data(volume_m3=value)
    data = await state.get_data()
    await cb.message.edit_text(  # type: ignore[union-attr]
        _card(data, 5, "⏰ <b>Выберите срочность доставки:</b>"),
        reply_markup=_with_back(urgency_kb(), "back:volume"),
    )
    await state.set_state(OrderForm.urgency)
    await cb.answer()


@router.message(OrderForm.volume)
async def type_volume(message: Message, state: FSMContext, bot: Bot) -> None:
    raw = (message.text or "").replace(",", ".").strip()
    try:
        v = float(raw)
        if v <= 0:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Введите число больше 0 (например: 2.5).")
        return
    await state.update_data(volume_m3=str(v))
    data = await state.get_data()
    card_id = data.get("card_message_id", 0)
    new_id = await _edit_card(
        bot, message.chat.id, card_id,
        _card(data, 5, "⏰ <b>Выберите срочность доставки:</b>"),
        _with_back(urgency_kb(), "back:volume"),
    )
    await state.update_data(card_message_id=new_id)
    await state.set_state(OrderForm.urgency)


# ── D6. Urgency ───────────────────────────────────────────────────

@router.callback_query(OrderForm.urgency, F.data.startswith("urgency:"))
async def pick_urgency(cb: CallbackQuery, state: FSMContext) -> None:
    value = cb.data.split(":")[1]
    await state.update_data(urgency=value)
    data = await state.get_data()
    await cb.message.edit_text(  # type: ignore[union-attr]
        _card(data, 6, "📋 <b>Условия поставки (Инкотермс):</b>"),
        reply_markup=_with_back(incoterms_kb(), "back:urgency"),
    )
    await state.set_state(OrderForm.incoterms)
    await cb.answer()


# ── D7. Incoterms ─────────────────────────────────────────────────

@router.callback_query(OrderForm.incoterms, F.data.startswith("terms:"))
async def pick_incoterms(cb: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    value = cb.data.split(":")[1]
    await state.update_data(incoterms=value)
    data = await state.get_data()
    card_id = data.get("card_message_id", 0)
    new_id = await _show_phone_step(bot, cb.message.chat.id, card_id, data, 7)  # type: ignore[union-attr]
    await state.update_data(card_message_id=new_id)
    await state.set_state(OrderForm.phone)
    await cb.answer()


# ═══════════════════════════════════════════════════════════════════
# SHARED — Phone + Comment + Finish
# ═══════════════════════════════════════════════════════════════════

@router.message(OrderForm.phone, F.contact)
async def share_phone_contact(message: Message, state: FSMContext, bot: Bot) -> None:
    phone = message.contact.phone_number  # type: ignore[union-attr]
    await state.update_data(phone=phone)
    data = await state.get_data()
    total = TOTAL_CUSTOMS if data.get("service") == "customs" else TOTAL_DELIVERY
    card_id = data.get("card_message_id", 0)
    new_id = await _edit_card(
        bot, message.chat.id, card_id,
        _card(data, total, "💬 <b>Добавьте комментарий</b> (необязательно):"),
        skip_comment_kb(),
    )
    await state.update_data(card_message_id=new_id)
    await message.answer("✅", reply_markup=ReplyKeyboardRemove())
    await state.set_state(OrderForm.comment)


@router.message(OrderForm.phone)
async def type_phone(message: Message, state: FSMContext, bot: Bot) -> None:
    phone = (message.text or "").strip()
    if len(phone) < 6:
        await message.answer(
            "⚠️ Введите номер телефона или нажмите кнопку «📱 Поделиться номером»."
        )
        return
    await state.update_data(phone=phone)
    data = await state.get_data()
    total = TOTAL_CUSTOMS if data.get("service") == "customs" else TOTAL_DELIVERY
    card_id = data.get("card_message_id", 0)
    new_id = await _edit_card(
        bot, message.chat.id, card_id,
        _card(data, total, "💬 <b>Добавьте комментарий</b> (необязательно):"),
        skip_comment_kb(),
    )
    await state.update_data(card_message_id=new_id)
    await message.answer("✅", reply_markup=ReplyKeyboardRemove())
    await state.set_state(OrderForm.comment)


@router.callback_query(OrderForm.comment, F.data == "skip_comment")
async def skip_comment(cb: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.update_data(comment="")
    await cb.message.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]
    await _finish_order(cb.message, state, bot, cb.from_user)  # type: ignore[arg-type]
    await cb.answer()


@router.message(OrderForm.comment)
async def type_comment(message: Message, state: FSMContext, bot: Bot) -> None:
    await state.update_data(comment=(message.text or "").strip())
    await _finish_order(message, state, bot, message.from_user)


# ── Resolve helpers ───────────────────────────────────────────────

def _resolve_weight(value: str) -> float:
    return WEIGHT_TO_FLOAT.get(value) or _safe_float(value)


def _resolve_volume(value: str) -> float:
    return VOLUME_TO_FLOAT.get(value) or _safe_float(value)


def _safe_float(v: str) -> float:
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0


# ── Finish ────────────────────────────────────────────────────────

async def _finish_order(message: Message, state: FSMContext, bot: Bot, user) -> None:  # noqa: ANN001
    data    = await state.get_data()
    service = data.get("service", "delivery")

    base = {
        "telegram_id":  user.id,
        "username":     user.username or "",
        "full_name":    user.full_name or "",
        "service_type": service,
        "country":      data.get("country", ""),
        "phone":        data.get("phone", ""),
        "comment":      data.get("comment", ""),
    }

    if service == "customs":
        lead_data = {
            **base,
            "cargo_type":        data.get("cargo_type", ""),
            "invoice_value":     data.get("invoice_value", ""),
            "invoice_value_num": float(data.get("invoice_value_num", 0) or 0),
            "customs_urgency":   data.get("customs_urgency", ""),
        }
    else:
        weight_raw = data.get("weight_kg", "0")
        volume_raw = data.get("volume_m3", "0")
        lead_data = {
            **base,
            "city_from":  data.get("city_from", ""),
            "cargo_type": data.get("cargo_type", ""),
            "weight_kg":  _resolve_weight(weight_raw),
            "volume_m3":  _resolve_volume(volume_raw),
            "urgency":    data.get("urgency", ""),
            "incoterms":  data.get("incoterms", ""),
        }

    lead_id = await save_lead(lead_data)

    # ── User confirmation ──────────────────────────────────────────
    if service == "customs":
        c_lbl      = COUNTRY_LABELS.get(lead_data["country"], lead_data["country"])
        cargo_lbl  = CARGO_LABELS.get(lead_data["cargo_type"], lead_data["cargo_type"])
        inv_key    = lead_data["invoice_value"]
        inv_lbl    = INVOICE_LABELS.get(inv_key, f"${inv_key}" if inv_key else "—")
        savings    = CUSTOMS_SAVINGS.get(inv_key, "")
        urg_lbl    = CUSTOMS_URGENCY_LABELS.get(lead_data["customs_urgency"], "—")
        urg_info   = CUSTOMS_URGENCY_INFO.get(lead_data["customs_urgency"], "")
        comment_ln = f"\n💬 {lead_data['comment']}" if lead_data["comment"] else ""
        savings_ln = f"\n<i>Примерная экономия на пошлинах vs РФ: <b>{savings}</b></i>" if savings else ""

        await message.answer(
            f"<b>✅ Заявка #{lead_id} принята!</b>\n\n"
            f"🛃 <b>Таможня в Кыргызстане → РФ / ЕАЭС</b>\n"
            f"📦 {cargo_lbl}\n"
            f"🌍 {c_lbl}\n"
            f"💰 {inv_lbl}\n"
            f"⏰ {urg_lbl}\n"
            f"<i>{urg_info}</i>"
            f"{savings_ln}"
            f"{comment_ln}\n\n"
            f"{_DIV}\n"
            "💡 <b>Почему выгодно через Кыргызстан?</b>\n"
            "Ставки таможни КР — самые низкие в ЕАЭС.\n"
            "Легальная оптимизация, все документы чистые.\n\n"
            "👨‍💼 Менеджер рассчитает точную стоимость\n"
            "и свяжется с вами <b>в течение 1 рабочего часа.</b>",
            reply_markup=after_submit_kb(),
        )

    else:
        weight_raw = data.get("weight_kg", "0")
        volume_raw = data.get("volume_m3", "0")
        c_lbl      = COUNTRY_LABELS.get(lead_data["country"], lead_data["country"])
        cargo_lbl  = CARGO_LABELS.get(lead_data["cargo_type"], lead_data["cargo_type"])
        w_lbl      = WEIGHT_LABELS.get(weight_raw, f"{lead_data.get('weight_kg', 0)} кг")
        v_lbl      = VOLUME_LABELS.get(volume_raw, f"{lead_data.get('volume_m3', 0)} м³")
        urg_lbl    = URGENCY_LABELS.get(lead_data["urgency"], "—")
        terms_lbl  = INCOTERMS_LABELS.get(lead_data["incoterms"], "—")
        delivery   = DELIVERY_INFO.get(lead_data["country"], DEFAULT_DELIVERY).get(lead_data.get("urgency", ""), "")
        comment_ln = f"\n💬 {lead_data['comment']}" if lead_data["comment"] else ""

        await message.answer(
            f"<b>✅ Заявка #{lead_id} принята!</b>\n\n"
            f"🚚 <b>Доставка</b>\n"
            f"🌍 {c_lbl} → {lead_data.get('city_from', '')}\n"
            f"📦 {cargo_lbl}\n"
            f"⚖️ {w_lbl}  |  📐 {v_lbl}\n"
            f"⏰ {urg_lbl}\n"
            f"💡 {delivery}\n"
            f"📋 {terms_lbl}"
            f"{comment_ln}\n\n"
            "👨‍💼 Менеджер свяжется с вами в ближайшее время.",
            reply_markup=after_submit_kb(),
        )

    # ── Admin notification ─────────────────────────────────────────
    username_part = f" (@{lead_data['username']})" if lead_data["username"] else ""
    comment_part  = f"\n💬 {lead_data['comment']}" if lead_data["comment"] else ""

    if service == "customs":
        c_lbl     = COUNTRY_LABELS.get(lead_data["country"], lead_data["country"])
        cargo_lbl = CARGO_LABELS.get(lead_data["cargo_type"], "—")
        inv_key   = lead_data["invoice_value"]
        inv_lbl   = INVOICE_LABELS.get(inv_key, f"${inv_key}" if inv_key else "—")
        urg_lbl   = CUSTOMS_URGENCY_LABELS.get(lead_data["customs_urgency"], "—")
        admin_text = (
            f"🆕 <b>Лид #{lead_id} · 🛃 Таможня</b>\n\n"
            f"👤 {lead_data['full_name']}{username_part}\n"
            f"📱 {lead_data['phone']}\n\n"
            f"📦 {cargo_lbl}\n"
            f"🌍 {c_lbl}\n"
            f"💰 {inv_lbl}\n"
            f"⏰ {urg_lbl}"
            f"{comment_part}"
        )
    else:
        weight_raw = data.get("weight_kg", "0")
        volume_raw = data.get("volume_m3", "0")
        c_lbl      = COUNTRY_LABELS.get(lead_data["country"], lead_data["country"])
        cargo_lbl  = CARGO_LABELS.get(lead_data["cargo_type"], "—")
        w_lbl      = WEIGHT_LABELS.get(weight_raw, f"{lead_data.get('weight_kg', 0)} кг")
        v_lbl      = VOLUME_LABELS.get(volume_raw, f"{lead_data.get('volume_m3', 0)} м³")
        urg_lbl    = URGENCY_LABELS.get(lead_data["urgency"], "—")
        terms_lbl  = INCOTERMS_LABELS.get(lead_data["incoterms"], "—")
        delivery   = DELIVERY_INFO.get(lead_data["country"], DEFAULT_DELIVERY).get(lead_data.get("urgency", ""), "")
        admin_text = (
            f"🆕 <b>Лид #{lead_id} · 🚚 Доставка</b>\n\n"
            f"👤 {lead_data['full_name']}{username_part}\n"
            f"📱 {lead_data['phone']}\n\n"
            f"🌍 {c_lbl} → {lead_data.get('city_from', '')}\n"
            f"📦 {cargo_lbl}\n"
            f"⚖️ {w_lbl} | 📐 {v_lbl}\n"
            f"⏰ {urg_lbl}\n"
            f"💡 {delivery}\n"
            f"📋 {terms_lbl}"
            f"{comment_part}"
        )

    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(admin_id, admin_text, reply_markup=admin_lead_kb(lead_id))
        except Exception as exc:
            logger.error("Failed to notify admin %s: %s", admin_id, exc)

    await state.clear()
    logger.info("Lead #%d saved [service=%s / %s]", lead_id, service, lead_data.get("country"))


# ═══════════════════════════════════════════════════════════════════
# Back navigation
# ═══════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("back:"))
async def handle_back(cb: CallbackQuery, state: FSMContext) -> None:
    target = (cb.data or "").split(":")[1]
    data   = await state.get_data()

    if target == "service":
        await cb.message.edit_text(_WELCOME, reply_markup=service_kb())  # type: ignore[union-attr]
        await state.set_state(OrderForm.service)

    # ── Customs back chain ─────────────────────────────────────────
    elif target == "customs_cargo":
        await cb.message.edit_text(  # type: ignore[union-attr]
            _CUSTOMS_INTRO,
            reply_markup=_with_back(cargo_kb(), "back:service"),
        )
        await state.set_state(OrderForm.customs_cargo)

    elif target == "customs_country":
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 1, "🌍 <b>Из какой страны везёте товар?</b>"),
            reply_markup=_with_back(country_kb(), "back:customs_cargo"),
        )
        await state.set_state(OrderForm.customs_country)

    elif target == "invoice":
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 2, "💰 <b>Укажите стоимость товара (USD):</b>\n"
                  "<i>Нужно для расчёта таможенных платежей</i>"),
            reply_markup=_with_back(invoice_kb(), "back:customs_country"),
        )
        await state.set_state(OrderForm.invoice_value)

    elif target == "customs_urgency":
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 3, "⏰ <b>Когда нужна доставка?</b>"),
            reply_markup=_with_back(customs_urgency_kb(), "back:invoice"),
        )
        await state.set_state(OrderForm.customs_urgency)

    # ── Delivery back chain ────────────────────────────────────────
    elif target == "country":
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 0, "🌍 <b>Выберите страну отправления:</b>"),
            reply_markup=_with_back(country_kb(), "back:service"),
        )
        await state.set_state(OrderForm.country)

    elif target == "city":
        country = data.get("country", "")
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 1, "📍 <b>Выберите город отправления:</b>"),
            reply_markup=_with_back(city_kb(country), "back:country"),
        )
        await state.set_state(OrderForm.city)

    elif target == "cargo":
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 2, "📦 <b>Выберите тип груза:</b>"),
            reply_markup=_with_back(cargo_kb(), "back:city"),
        )
        await state.set_state(OrderForm.cargo_type)

    elif target == "weight":
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 3, "⚖️ <b>Укажите вес груза:</b>"),
            reply_markup=_with_back(weight_kb(), "back:cargo"),
        )
        await state.set_state(OrderForm.weight)

    elif target == "volume":
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 4, "📐 <b>Укажите объём груза:</b>"),
            reply_markup=_with_back(volume_kb(), "back:weight"),
        )
        await state.set_state(OrderForm.volume)

    elif target == "urgency":
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 5, "⏰ <b>Выберите срочность доставки:</b>"),
            reply_markup=_with_back(urgency_kb(), "back:volume"),
        )
        await state.set_state(OrderForm.urgency)

    elif target == "incoterms":
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 6, "📋 <b>Условия поставки (Инкотермс):</b>"),
            reply_markup=_with_back(incoterms_kb(), "back:urgency"),
        )
        await state.set_state(OrderForm.incoterms)

    await cb.answer()


# ═══════════════════════════════════════════════════════════════════
# Post-submission quick actions
# ═══════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "action:docs")
async def action_docs(cb: CallbackQuery) -> None:
    await cb.message.answer(  # type: ignore[union-attr]
        "📎 Отправьте документы (фото, PDF, архивы) — мы прикрепим их к вашей заявке."
    )
    await cb.answer()


@router.callback_query(F.data == "action:details")
async def action_details(cb: CallbackQuery) -> None:
    await cb.message.answer(  # type: ignore[union-attr]
        "✏️ Напишите дополнительную информацию — мы передадим её менеджеру."
    )
    await cb.answer()


@router.callback_query(F.data == "action:call")
async def action_call(cb: CallbackQuery) -> None:
    await cb.message.answer(  # type: ignore[union-attr]
        "📞 Наш менеджер свяжется с вами в ближайшее время.\n"
        "Или напишите нам: <b>info@tegroup.cc</b>"
    )
    await cb.answer()


@router.callback_query(F.data == "action:restart")
async def action_restart(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    msg = await cb.message.answer(_WELCOME, reply_markup=service_kb())  # type: ignore[union-attr]
    await state.update_data(card_message_id=msg.message_id)
    await state.set_state(OrderForm.service)
    await cb.answer()


# ═══════════════════════════════════════════════════════════════════
# Admin inline buttons
# ═══════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("adm:progress:"))
async def adm_take_progress(cb: CallbackQuery) -> None:
    if cb.from_user.id not in settings.admin_ids:
        await cb.answer("⛔ Нет доступа.", show_alert=True)
        return
    lead_id = int(cb.data.split(":")[2])  # type: ignore[union-attr]
    ok = await update_lead_status(lead_id, "IN_PROGRESS")
    if ok:
        await cb.message.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]
        await cb.message.answer(f"✅ Лид #{lead_id} взят в работу.")  # type: ignore[union-attr]
    await cb.answer()


@router.callback_query(F.data.startswith("adm:call:"))
async def adm_show_phone(cb: CallbackQuery) -> None:
    if cb.from_user.id not in settings.admin_ids:
        await cb.answer("⛔ Нет доступа.", show_alert=True)
        return
    lead_id = int(cb.data.split(":")[2])  # type: ignore[union-attr]
    lead = await get_lead(lead_id)
    if lead:
        await cb.message.answer(  # type: ignore[union-attr]
            f"📞 Телефон клиента: <b>{lead['phone']}</b>"
        )
    await cb.answer()
