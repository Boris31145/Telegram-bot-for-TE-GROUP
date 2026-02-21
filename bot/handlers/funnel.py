"""
Modern conversation funnel with edit-in-place UX.

/start → country → city → cargo type → weight → volume →
urgency (+ delivery estimate) → incoterms → phone → comment → save

• Progress card: one message is edited at each step (no chat clutter).
• Inline keyboards for most steps; text input only when needed.
• Delivery method / estimate shown after urgency selection.
"""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

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


# ── Helper: build a progress card ────────────────────────────────────

def _bar(step: int) -> str:
    """Premium-ish step indicator."""
    step = max(1, min(TOTAL_STEPS, step))
    filled = "▰" * step
    empty = "▱" * (TOTAL_STEPS - step)
    return f"Шаг {step}/{TOTAL_STEPS}  {filled}{empty}"


def _card(data: dict, step: int, question: str = "") -> str:
    """
    Build an accumulating summary card.
    Shows all previously collected data + the current question.
    """
    lines: list[str] = [
        "<b>TE GROUP • Расчёт доставки</b>\n"
        "<i>Сроки покажем сразу, цену уточнит менеджер</i>\n"
        f"{_bar(step)}\n"
    ]

    if data.get("country"):
        lbl = COUNTRY_LABELS.get(data["country"], data["country"])
        lines.append(f"  ✅ Страна: {lbl}")
    if data.get("city_from"):
        lines.append(f"  ✅ Город: {data['city_from']}")
    if data.get("cargo_type"):
        lbl = CARGO_LABELS.get(data["cargo_type"], data["cargo_type"])
        lines.append(f"  ✅ Груз: {lbl}")
    if data.get("weight_kg"):
        lbl = WEIGHT_LABELS.get(data["weight_kg"], f"{data['weight_kg']} кг")
        lines.append(f"  ✅ Вес: {lbl}")
    if data.get("volume_m3"):
        lbl = VOLUME_LABELS.get(data["volume_m3"], f"{data['volume_m3']} м³")
        lines.append(f"  ✅ Объём: {lbl}")
    if data.get("urgency"):
        lbl = URGENCY_LABELS.get(data["urgency"], data["urgency"])
        lines.append(f"  ✅ Срочность: {lbl}")
        # delivery estimate
        country = data.get("country", "")
        info = DELIVERY_INFO.get(country, DEFAULT_DELIVERY).get(data["urgency"], "")
        if info:
            lines.append(f"        💡 {info}")
    if data.get("incoterms"):
        lbl = INCOTERMS_LABELS.get(data["incoterms"], data["incoterms"])
        lines.append(f"  ✅ Условия: {lbl}")

    if question:
        lines.append(f"\n{question}")

    return "\n".join(lines)


async def _safe_edit(
    cb: CallbackQuery,
    text: str,
    reply_markup=None,  # noqa: ANN001
) -> None:
    """
    Render free tier can restart; users may click old buttons.
    If edit fails (old message / too old / already edited), send a new message.
    """
    try:
        await cb.message.edit_text(text, reply_markup=reply_markup)  # type: ignore[union-attr]
    except Exception:
        await cb.message.answer(text, reply_markup=reply_markup)  # type: ignore[union-attr]


# ── 1. /start ────────────────────────────────────────────────────────

async def _start_flow(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(_card({}, 1, "🌍 <b>Страна отправления:</b>"), reply_markup=country_kb())
    await state.set_state(OrderForm.country)


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await _start_flow(message, state)


@router.message(F.text.regexp(r"(?i)^(start|старт)$"))
async def text_start(message: Message, state: FSMContext) -> None:
    await _start_flow(message, state)


# ── 2. Country ───────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("country:"))
async def pick_country(cb: CallbackQuery, state: FSMContext) -> None:
    value = cb.data.split(":")[1]  # type: ignore[union-attr]

    if value == "other":
        await _safe_edit(cb, _card({}, 1, "🌍 <b>Введите название страны:</b>"))
        await cb.answer()
        return

    # Reset funnel from country selection (works even if state was lost)
    await state.clear()
    await state.update_data(country=value)
    data = await state.get_data()
    text = _card(data, 2, "📍 <b>Город отправления:</b>")
    await _safe_edit(cb, text, reply_markup=city_kb(value))
    await state.set_state(OrderForm.city)
    await cb.answer()


@router.message(OrderForm.country)
async def type_other_country(message: Message, state: FSMContext) -> None:
    """User typed a custom country name (chose 'Другая')."""
    await state.update_data(country=message.text.strip())  # type: ignore[union-attr]
    data = await state.get_data()
    text = _card(data, 1, "📍 <b>Введите город отправления:</b>")
    await message.answer(text)
    await state.set_state(OrderForm.city)


# ── 3. City ──────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("city:"))
async def pick_city(cb: CallbackQuery, state: FSMContext) -> None:
    # city:<country>:<city>
    parts = cb.data.split(":", 2)  # type: ignore[union-attr]
    if len(parts) < 3:
        await cb.answer()
        return
    country = parts[1]
    value = parts[2]

    if value == "__custom__":
        data = await state.get_data()
        # If state was lost, restore country from callback
        if not data.get("country"):
            await state.update_data(country=country)
            data = await state.get_data()
        await _safe_edit(cb, _card(data, 2, "📍 <b>Введите название города:</b>"))
        await cb.answer()
        return

    data = await state.get_data()
    if not data.get("country"):
        await state.update_data(country=country)
    await state.update_data(city_from=value)
    data = await state.get_data()
    text = _card(data, 3, "📦 <b>Тип груза:</b>")
    await _safe_edit(cb, text, reply_markup=cargo_kb())
    await state.set_state(OrderForm.cargo_type)
    await cb.answer()


@router.message(OrderForm.city)
async def type_city(message: Message, state: FSMContext) -> None:
    city = (message.text or "").strip()
    if len(city) < 2:
        await message.answer("⚠️ Введите корректное название города.")
        return
    await state.update_data(city_from=city)
    data = await state.get_data()
    text = _card(data, 2, "📦 <b>Выберите тип груза:</b>")
    await message.answer(text, reply_markup=cargo_kb())
    await state.set_state(OrderForm.cargo_type)


# ── 4. Cargo type ────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("cargo:"))
async def pick_cargo(cb: CallbackQuery, state: FSMContext) -> None:
    value = cb.data.split(":")[1]  # type: ignore[union-attr]
    await state.update_data(cargo_type=value)
    data = await state.get_data()
    text = _card(data, 4, "⚖️ <b>Вес груза:</b>")
    await _safe_edit(cb, text, reply_markup=weight_kb())
    await state.set_state(OrderForm.weight)
    await cb.answer()


# ── 5. Weight ────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("weight:"))
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
    text = _card(data, 5, "📐 <b>Объём груза:</b>")
    await _safe_edit(cb, text, reply_markup=volume_kb())
    await state.set_state(OrderForm.volume)
    await cb.answer()


@router.message(OrderForm.weight)
async def type_weight(message: Message, state: FSMContext) -> None:
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
    text = _card(data, 4, "📐 <b>Укажите объём груза:</b>")
    await message.answer(text, reply_markup=volume_kb())
    await state.set_state(OrderForm.volume)


# ── 6. Volume ────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("volume:"))
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
    text = _card(data, 6, "⏰ <b>Срочность доставки:</b>")
    await _safe_edit(cb, text, reply_markup=urgency_kb())
    await state.set_state(OrderForm.urgency)
    await cb.answer()


@router.message(OrderForm.volume)
async def type_volume(message: Message, state: FSMContext) -> None:
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
    text = _card(data, 5, "⏰ <b>Выберите срочность доставки:</b>")
    await message.answer(text, reply_markup=urgency_kb())
    await state.set_state(OrderForm.urgency)


# ── 7. Urgency ───────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("urgency:"))
async def pick_urgency(cb: CallbackQuery, state: FSMContext) -> None:
    value = cb.data.split(":")[1]  # type: ignore[union-attr]
    await state.update_data(urgency=value)
    data = await state.get_data()
    text = _card(data, 7, "📋 <b>Условия поставки (Инкотермс):</b>")
    await _safe_edit(cb, text, reply_markup=incoterms_kb())
    await state.set_state(OrderForm.incoterms)
    await cb.answer()


# ── 8. Incoterms ─────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("terms:"))
async def pick_incoterms(cb: CallbackQuery, state: FSMContext) -> None:
    value = cb.data.split(":")[1]  # type: ignore[union-attr]
    await state.update_data(incoterms=value)
    data = await state.get_data()

    # Edit the card to show complete progress
    text = _card(data, 8, "📱 <b>Контактный телефон:</b>")
    await _safe_edit(cb, text)

    # Send reply-keyboard for phone (needs a separate message)
    await cb.message.answer(  # type: ignore[union-attr]
        "Нажмите кнопку ниже или введите номер вручную:",
        reply_markup=phone_kb(),
    )
    await state.set_state(OrderForm.phone)
    await cb.answer()


# ── 9. Phone ─────────────────────────────────────────────────────────

@router.message(OrderForm.phone, F.contact)
async def share_phone_contact(message: Message, state: FSMContext) -> None:
    phone = message.contact.phone_number  # type: ignore[union-attr]
    await state.update_data(phone=phone)
    data = await state.get_data()
    text = _card(
        data,
        7,
        "💬 <b>Комментарий</b> (необязательно)\n"
        "Напишите сообщением или нажмите «⏭ Пропустить».",
    )
    # Reply keyboard is one_time_keyboard and should collapse after sharing contact.
    await message.answer(text, reply_markup=skip_comment_kb())
    await state.set_state(OrderForm.comment)


@router.message(OrderForm.phone)
async def type_phone(message: Message, state: FSMContext) -> None:
    phone = (message.text or "").strip()
    if len(phone) < 6:
        await message.answer(
            "⚠️ Нажмите кнопку «📱 Отправить номер» или введите номер вручную."
        )
        return
    await state.update_data(phone=phone)
    data = await state.get_data()
    text = _card(
        data,
        7,
        "💬 <b>Комментарий</b> (необязательно)\n"
        "Напишите сообщением или нажмите «⏭ Пропустить».",
    )
    await message.answer(text, reply_markup=skip_comment_kb())
    await state.set_state(OrderForm.comment)


# ── 10. Comment ──────────────────────────────────────────────────────

@router.callback_query(OrderForm.comment, F.data == "skip_comment")
async def skip_comment(cb: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.update_data(comment="")
    await cb.message.edit_text("⏭ Комментарий пропущен.")  # type: ignore[union-attr]
    await _finish_order(cb.message, state, bot, cb.from_user)  # type: ignore[arg-type]
    await cb.answer()


@router.message(OrderForm.comment)
async def type_comment(message: Message, state: FSMContext, bot: Bot) -> None:
    await state.update_data(comment=(message.text or "").strip())
    await _finish_order(message, state, bot, message.from_user)


# ── Finalise ─────────────────────────────────────────────────────────

def _resolve_weight(value: str) -> float:
    """Convert FSM weight value to float for DB."""
    if value in WEIGHT_TO_FLOAT:
        return WEIGHT_TO_FLOAT[value]
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0


def _resolve_volume(value: str) -> float:
    """Convert FSM volume value to float for DB."""
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

    # Persist
    lead_id = await save_lead(lead_data)

    # Labels for display
    c_lbl = COUNTRY_LABELS.get(lead_data["country"], lead_data["country"])
    cargo_lbl = CARGO_LABELS.get(lead_data["cargo_type"], lead_data["cargo_type"])
    w_lbl = WEIGHT_LABELS.get(weight_raw, f"{lead_data['weight_kg']} кг")
    v_lbl = VOLUME_LABELS.get(volume_raw, f"{lead_data['volume_m3']} м³")
    urg_lbl = URGENCY_LABELS.get(lead_data["urgency"], lead_data["urgency"])
    terms_lbl = INCOTERMS_LABELS.get(lead_data["incoterms"], lead_data["incoterms"])

    # Delivery estimate
    country = lead_data["country"]
    urgency = lead_data["urgency"]
    delivery = DELIVERY_INFO.get(country, DEFAULT_DELIVERY).get(urgency, "")

    comment_line = f"\n💬 {lead_data['comment']}" if lead_data["comment"] else ""

    # ── Confirmation to user ─────────────────────────────────────────
    await message.answer(
        f"<b>✅ Заявка #{lead_id} принята!</b>\n\n"
        f"  🌍 Страна: {c_lbl}\n"
        f"  📍 Город: {lead_data['city_from']}\n"
        f"  📦 Груз: {cargo_lbl}\n"
        f"  ⚖️ Вес: {w_lbl}\n"
        f"  📐 Объём: {v_lbl}\n"
        f"  ⏰ {urg_lbl}\n"
        f"  💡 {delivery}\n"
        f"  📋 Условия: {terms_lbl}"
        f"{comment_line}\n\n"
        "👨‍💼 Наш менеджер свяжется с вами\n"
        "в ближайшее время!",
        reply_markup=after_submit_kb(),
    )

    # ── Notification to every admin ──────────────────────────────────
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
            await bot.send_message(
                admin_id,
                admin_text,
                reply_markup=admin_lead_kb(lead_id),
            )
        except Exception as exc:
            logger.error("Failed to notify admin %s: %s", admin_id, exc)

    await state.clear()
    logger.info("Lead #%d saved [%s / %s]", lead_id, lead_data["country"], lead_data["city_from"])


# ── Post-submission quick actions ────────────────────────────────────

@router.callback_query(F.data == "action:docs")
async def action_docs(cb: CallbackQuery) -> None:
    await cb.message.answer(  # type: ignore[union-attr]
        "📎 Отправьте документы (фото, PDF, архивы) —\n"
        "мы прикрепим их к вашей заявке."
    )
    await cb.answer()


@router.callback_query(F.data == "action:details")
async def action_details(cb: CallbackQuery) -> None:
    await cb.message.answer(  # type: ignore[union-attr]
        "✏️ Напишите дополнительную информацию —\n"
        "мы передадим её менеджеру."
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
    text = (
        "<b>🔄 Новая заявка</b>\n\n"
        f"{_card({}, 0, '🌍 <b>Выберите страну отправления:</b>')}"
    )
    await cb.message.answer(text, reply_markup=country_kb())  # type: ignore[union-attr]
    await state.set_state(OrderForm.country)
    await cb.answer()


# ── Admin inline buttons on lead notifications ───────────────────────

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
