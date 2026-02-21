"""
TE GROUP bot — single-message funnel with back navigation.

All steps edit ONE card message (no chat clutter).
Every step has a ← Назад button.
Flow: /start → country → city → cargo → weight → volume → urgency → incoterms → phone → comment
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
    DEFAULT_DELIVERY,
    DELIVERY_INFO,
    INCOTERMS_LABELS,
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
    incoterms_kb,
    phone_kb,
    skip_comment_kb,
    urgency_kb,
    volume_kb,
    weight_kb,
)
from bot.states import OrderForm

logger = logging.getLogger(__name__)
router = Router()

TOTAL_STEPS = 8

_WELCOME = (
    "<b>TE GROUP</b>\n\n"
    "Таможенное оформление в Кыргызстане\n"
    "и доставка грузов из-за рубежа.\n\n"
    "🌍 <b>Выберите страну отправления:</b>"
)


# ── Helpers ───────────────────────────────────────────────────────────

def _bar(step: int) -> str:
    """Clean step counter, e.g. 'Шаг 3 из 8'."""
    if step <= 0:
        return ""
    return f"<i>Шаг {step} из {TOTAL_STEPS}</i>"


def _card(data: dict, step: int, question: str = "") -> str:
    """Accumulating summary card, edited in-place at every step."""
    lines: list[str] = ["<b>TE GROUP</b>"]
    bar = _bar(step)
    if bar:
        lines.append(bar)
    lines.append("")

    if data.get("country"):
        lbl = COUNTRY_LABELS.get(data["country"], data["country"])
        lines.append(f"✅ Страна: <b>{lbl}</b>")
    if data.get("city_from"):
        lines.append(f"✅ Город: <b>{data['city_from']}</b>")
    if data.get("cargo_type"):
        lbl = CARGO_LABELS.get(data["cargo_type"], data["cargo_type"])
        lines.append(f"✅ Груз: <b>{lbl}</b>")
    if data.get("weight_kg"):
        lbl = WEIGHT_LABELS.get(data["weight_kg"], f"{data['weight_kg']} кг")
        lines.append(f"✅ Вес: <b>{lbl}</b>")
    if data.get("volume_m3"):
        lbl = VOLUME_LABELS.get(data["volume_m3"], f"{data['volume_m3']} м³")
        lines.append(f"✅ Объём: <b>{lbl}</b>")
    if data.get("urgency"):
        lbl = URGENCY_LABELS.get(data["urgency"], data["urgency"])
        lines.append(f"✅ Срочность: <b>{lbl}</b>")
        info = DELIVERY_INFO.get(data.get("country", ""), DEFAULT_DELIVERY).get(data["urgency"], "")
        if info:
            lines.append(f"   💡 {info}")
    if data.get("incoterms"):
        lbl = INCOTERMS_LABELS.get(data["incoterms"], data["incoterms"])
        lines.append(f"✅ Условия: <b>{lbl}</b>")

    if question:
        lines.append("")
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
    """Edit the card message. If it fails, send a new one. Returns the active message_id."""
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


# ── 1. /start ─────────────────────────────────────────────────────────

async def _start_flow(message: Message, state: FSMContext) -> None:
    await state.clear()
    msg = await message.answer(_WELCOME, reply_markup=country_kb())
    await state.update_data(card_message_id=msg.message_id)
    await state.set_state(OrderForm.country)


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await _start_flow(message, state)


@router.message(F.text.regexp(r"(?i)^(start|старт)$"))
async def text_start(message: Message, state: FSMContext) -> None:
    await _start_flow(message, state)


# ── 2. Country ────────────────────────────────────────────────────────

@router.callback_query(OrderForm.country, F.data.startswith("country:"))
async def pick_country(cb: CallbackQuery, state: FSMContext) -> None:
    value = cb.data.split(":")[1]  # type: ignore[union-attr]

    if value == "other":
        await cb.message.edit_text(  # type: ignore[union-attr]
            "<b>TE GROUP</b>\n\n🌍 <b>Введите название страны:</b>",
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


# ── 3. City ───────────────────────────────────────────────────────────

@router.callback_query(OrderForm.city, F.data.startswith("city:"))
async def pick_city(cb: CallbackQuery, state: FSMContext) -> None:
    # Format: city:<country>:<city_name>
    parts = cb.data.split(":", 2)  # type: ignore[union-attr]
    if len(parts) < 3:
        await cb.answer()
        return
    city_name = parts[2]

    if city_name == "__custom__":
        data = await state.get_data()
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 1, "📍 <b>Введите название города:</b>"),
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


# ── 4. Cargo type ─────────────────────────────────────────────────────

@router.callback_query(OrderForm.cargo_type, F.data.startswith("cargo:"))
async def pick_cargo(cb: CallbackQuery, state: FSMContext) -> None:
    value = cb.data.split(":")[1]  # type: ignore[union-attr]
    await state.update_data(cargo_type=value)
    data = await state.get_data()
    await cb.message.edit_text(  # type: ignore[union-attr]
        _card(data, 3, "⚖️ <b>Укажите вес груза:</b>"),
        reply_markup=_with_back(weight_kb(), "back:cargo"),
    )
    await state.set_state(OrderForm.weight)
    await cb.answer()


# ── 5. Weight ─────────────────────────────────────────────────────────

@router.callback_query(OrderForm.weight, F.data.startswith("weight:"))
async def pick_weight(cb: CallbackQuery, state: FSMContext) -> None:
    value = cb.data.split(":")[1]  # type: ignore[union-attr]

    if value == "__custom__":
        data = await state.get_data()
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 3, "⚖️ <b>Введите точный вес в кг</b> (например: 500):"),
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


# ── 6. Volume ─────────────────────────────────────────────────────────

@router.callback_query(OrderForm.volume, F.data.startswith("volume:"))
async def pick_volume(cb: CallbackQuery, state: FSMContext) -> None:
    value = cb.data.split(":")[1]  # type: ignore[union-attr]

    if value == "__custom__":
        data = await state.get_data()
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 4, "📐 <b>Введите точный объём в м³</b> (например: 2.5):"),
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


# ── 7. Urgency ────────────────────────────────────────────────────────

@router.callback_query(OrderForm.urgency, F.data.startswith("urgency:"))
async def pick_urgency(cb: CallbackQuery, state: FSMContext) -> None:
    value = cb.data.split(":")[1]  # type: ignore[union-attr]
    await state.update_data(urgency=value)
    data = await state.get_data()
    await cb.message.edit_text(  # type: ignore[union-attr]
        _card(data, 6, "📋 <b>Выберите условия поставки (Инкотермс):</b>"),
        reply_markup=_with_back(incoterms_kb(), "back:urgency"),
    )
    await state.set_state(OrderForm.incoterms)
    await cb.answer()


# ── 8. Incoterms ──────────────────────────────────────────────────────

@router.callback_query(OrderForm.incoterms, F.data.startswith("terms:"))
async def pick_incoterms(cb: CallbackQuery, state: FSMContext) -> None:
    value = cb.data.split(":")[1]  # type: ignore[union-attr]
    await state.update_data(incoterms=value)
    data = await state.get_data()
    # Edit card to show phone question; phone keyboard is a separate message (ReplyKeyboard)
    await cb.message.edit_text(  # type: ignore[union-attr]
        _card(data, 7, "📱 <b>Поделитесь номером телефона для связи:</b>"),
    )
    await cb.message.answer(  # type: ignore[union-attr]
        "Нажмите кнопку или введите номер вручную:",
        reply_markup=phone_kb(),
    )
    await state.set_state(OrderForm.phone)
    await cb.answer()


# ── 9. Phone ──────────────────────────────────────────────────────────

@router.message(OrderForm.phone, F.contact)
async def share_phone_contact(message: Message, state: FSMContext, bot: Bot) -> None:
    phone = message.contact.phone_number  # type: ignore[union-attr]
    await state.update_data(phone=phone)
    data = await state.get_data()
    card_id = data.get("card_message_id", 0)
    new_id = await _edit_card(
        bot, message.chat.id, card_id,
        _card(data, 8, "💬 <b>Добавьте комментарий</b> (необязательно):"),
        skip_comment_kb(),
    )
    await state.update_data(card_message_id=new_id)
    # Remove the phone reply-keyboard without visual noise
    await message.answer("✅", reply_markup=ReplyKeyboardRemove())
    await state.set_state(OrderForm.comment)


@router.message(OrderForm.phone)
async def type_phone(message: Message, state: FSMContext, bot: Bot) -> None:
    phone = (message.text or "").strip()
    if len(phone) < 6:
        await message.answer("⚠️ Введите номер телефона или нажмите кнопку «📱 Отправить номер».")
        return
    await state.update_data(phone=phone)
    data = await state.get_data()
    card_id = data.get("card_message_id", 0)
    new_id = await _edit_card(
        bot, message.chat.id, card_id,
        _card(data, 8, "💬 <b>Добавьте комментарий</b> (необязательно):"),
        skip_comment_kb(),
    )
    await state.update_data(card_message_id=new_id)
    await message.answer("✅", reply_markup=ReplyKeyboardRemove())
    await state.set_state(OrderForm.comment)


# ── 10. Comment ───────────────────────────────────────────────────────

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


# ── Back navigation ───────────────────────────────────────────────────

@router.callback_query(F.data.startswith("back:"))
async def handle_back(cb: CallbackQuery, state: FSMContext) -> None:
    target = cb.data.split(":")[1]  # type: ignore[union-attr]
    data = await state.get_data()

    if target == "country":
        await cb.message.edit_text(_WELCOME, reply_markup=country_kb())  # type: ignore[union-attr]
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
            _card(data, 6, "📋 <b>Выберите условия поставки (Инкотермс):</b>"),
            reply_markup=_with_back(incoterms_kb(), "back:urgency"),
        )
        await state.set_state(OrderForm.incoterms)

    await cb.answer()


# ── Finalise ──────────────────────────────────────────────────────────

def _resolve_weight(value: str) -> float:
    if value in WEIGHT_TO_FLOAT:
        return WEIGHT_TO_FLOAT[value]
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0


def _resolve_volume(value: str) -> float:
    if value in VOLUME_TO_FLOAT:
        return VOLUME_TO_FLOAT[value]
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0


async def _finish_order(message: Message, state: FSMContext, bot: Bot, user) -> None:  # noqa: ANN001
    data = await state.get_data()
    weight_raw = data.get("weight_kg", "0")
    volume_raw = data.get("volume_m3", "0")

    lead_data = {
        "telegram_id": user.id,
        "username": user.username or "",
        "full_name": user.full_name or "",
        "country": data.get("country", ""),
        "city_from": data.get("city_from", ""),
        "cargo_type": data.get("cargo_type", ""),
        "weight_kg": _resolve_weight(weight_raw),
        "volume_m3": _resolve_volume(volume_raw),
        "urgency": data.get("urgency", ""),
        "incoterms": data.get("incoterms", ""),
        "phone": data.get("phone", ""),
        "comment": data.get("comment", ""),
    }

    lead_id = await save_lead(lead_data)

    c_lbl = COUNTRY_LABELS.get(lead_data["country"], lead_data["country"])
    cargo_lbl = CARGO_LABELS.get(lead_data["cargo_type"], lead_data["cargo_type"])
    w_lbl = WEIGHT_LABELS.get(weight_raw, f"{lead_data['weight_kg']} кг")
    v_lbl = VOLUME_LABELS.get(volume_raw, f"{lead_data['volume_m3']} м³")
    urg_lbl = URGENCY_LABELS.get(lead_data["urgency"], lead_data["urgency"])
    terms_lbl = INCOTERMS_LABELS.get(lead_data["incoterms"], lead_data["incoterms"])
    delivery = DELIVERY_INFO.get(lead_data["country"], DEFAULT_DELIVERY).get(lead_data["urgency"], "")
    comment_line = f"\n💬 {lead_data['comment']}" if lead_data["comment"] else ""

    # Confirmation to user
    await message.answer(
        f"<b>✅ Заявка #{lead_id} принята!</b>\n\n"
        f"🌍 {c_lbl} → {lead_data['city_from']}\n"
        f"📦 {cargo_lbl}\n"
        f"⚖️ {w_lbl}  |  📐 {v_lbl}\n"
        f"⏰ {urg_lbl}\n"
        f"💡 {delivery}\n"
        f"📋 {terms_lbl}"
        f"{comment_line}\n\n"
        "👨‍💼 Менеджер свяжется с вами в ближайшее время.",
        reply_markup=after_submit_kb(),
    )

    # Notification to admins
    username_part = f" (@{lead_data['username']})" if lead_data["username"] else ""
    comment_part = f"\n💬 {lead_data['comment']}" if lead_data["comment"] else ""
    admin_text = (
        f"🆕 <b>Новый лид #{lead_id}</b>\n\n"
        f"👤 {lead_data['full_name']}{username_part}\n"
        f"📱 {lead_data['phone']}\n\n"
        f"🌍 {c_lbl} → {lead_data['city_from']}\n"
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
    logger.info("Lead #%d saved [%s / %s]", lead_id, lead_data["country"], lead_data["city_from"])


# ── Post-submission quick actions ─────────────────────────────────────

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
    msg = await cb.message.answer(_WELCOME, reply_markup=country_kb())  # type: ignore[union-attr]
    await state.update_data(card_message_id=msg.message_id)
    await state.set_state(OrderForm.country)
    await cb.answer()


# ── Admin inline buttons ──────────────────────────────────────────────

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
