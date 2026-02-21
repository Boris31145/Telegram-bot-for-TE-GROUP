"""
Main conversation funnel:
/start → country → city → cargo type → weight → volume →
urgency → incoterms → phone → comment → save & notify
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
    INCOTERMS_LABELS,
    URGENCY_LABELS,
    admin_lead_kb,
    after_submit_kb,
    cargo_kb,
    country_kb,
    incoterms_kb,
    phone_kb,
    skip_comment_kb,
    urgency_kb,
)
from bot.states import OrderForm

logger = logging.getLogger(__name__)
router = Router()


# ── 1. /start ────────────────────────────────────────────────────────

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "👋 <b>Добро пожаловать в T.E. Group!</b>\n\n"
        "Мы организуем доставку грузов из-за рубежа\n"
        "в Россию и страны ЕАЭС.\n\n"
        "Чтобы получить расчёт стоимости,\n"
        "ответьте на несколько вопросов 👇",
        reply_markup=country_kb(),
    )
    await state.set_state(OrderForm.country)


# ── 2. Country ───────────────────────────────────────────────────────

@router.callback_query(OrderForm.country, F.data.startswith("country:"))
async def pick_country(cb: CallbackQuery, state: FSMContext) -> None:
    value = cb.data.split(":")[1]  # type: ignore[union-attr]

    if value == "other":
        await cb.message.edit_text("🌍 Введите название страны:")  # type: ignore[union-attr]
        # State stays at OrderForm.country — text handler catches it
        await cb.answer()
        return

    await state.update_data(country=value)
    label = COUNTRY_LABELS.get(value, value)
    await cb.message.edit_text(  # type: ignore[union-attr]
        f"{label}\n\n📍 Из какого города отправка?"
    )
    await state.set_state(OrderForm.city)
    await cb.answer()


@router.message(OrderForm.country)
async def type_other_country(message: Message, state: FSMContext) -> None:
    """User typed a custom country name (chose 'Другая')."""
    await state.update_data(country=message.text.strip())  # type: ignore[union-attr]
    await message.answer("📍 Из какого города отправка?")
    await state.set_state(OrderForm.city)


# ── 3. City ──────────────────────────────────────────────────────────

@router.message(OrderForm.city)
async def type_city(message: Message, state: FSMContext) -> None:
    city = (message.text or "").strip()
    if len(city) < 2:
        await message.answer("⚠️ Введите корректное название города.")
        return
    await state.update_data(city_from=city)
    await message.answer("📦 Выберите тип груза:", reply_markup=cargo_kb())
    await state.set_state(OrderForm.cargo_type)


# ── 4. Cargo type ────────────────────────────────────────────────────

@router.callback_query(OrderForm.cargo_type, F.data.startswith("cargo:"))
async def pick_cargo(cb: CallbackQuery, state: FSMContext) -> None:
    value = cb.data.split(":")[1]  # type: ignore[union-attr]
    await state.update_data(cargo_type=value)
    await cb.message.edit_text(  # type: ignore[union-attr]
        "⚖️ Укажите примерный <b>вес груза</b> (кг):"
    )
    await state.set_state(OrderForm.weight)
    await cb.answer()


# ── 5. Weight ────────────────────────────────────────────────────────

@router.message(OrderForm.weight)
async def type_weight(message: Message, state: FSMContext) -> None:
    try:
        weight = float((message.text or "").replace(",", ".").strip())
        if weight <= 0:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Введите число больше 0 (например: 500).")
        return
    await state.update_data(weight_kg=weight)
    await message.answer("📐 Укажите примерный <b>объём груза</b> (м³):")
    await state.set_state(OrderForm.volume)


# ── 6. Volume ────────────────────────────────────────────────────────

@router.message(OrderForm.volume)
async def type_volume(message: Message, state: FSMContext) -> None:
    try:
        volume = float((message.text or "").replace(",", ".").strip())
        if volume <= 0:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Введите число больше 0 (например: 2.5).")
        return
    await state.update_data(volume_m3=volume)
    await message.answer(
        "⏰ Выберите срочность доставки:", reply_markup=urgency_kb()
    )
    await state.set_state(OrderForm.urgency)


# ── 7. Urgency ───────────────────────────────────────────────────────

@router.callback_query(OrderForm.urgency, F.data.startswith("urgency:"))
async def pick_urgency(cb: CallbackQuery, state: FSMContext) -> None:
    value = cb.data.split(":")[1]  # type: ignore[union-attr]
    await state.update_data(urgency=value)
    await cb.message.edit_text(  # type: ignore[union-attr]
        "📋 Выберите условия поставки (Инкотермс):",
        reply_markup=incoterms_kb(),
    )
    await state.set_state(OrderForm.incoterms)
    await cb.answer()


# ── 8. Incoterms ─────────────────────────────────────────────────────

@router.callback_query(OrderForm.incoterms, F.data.startswith("terms:"))
async def pick_incoterms(cb: CallbackQuery, state: FSMContext) -> None:
    value = cb.data.split(":")[1]  # type: ignore[union-attr]
    await state.update_data(incoterms=value)
    await cb.message.edit_text(  # type: ignore[union-attr]
        "📱 Поделитесь номером телефона для связи 👇"
    )
    await cb.message.answer(  # type: ignore[union-attr]
        "Нажмите кнопку или введите номер вручную:",
        reply_markup=phone_kb(),
    )
    await state.set_state(OrderForm.phone)
    await cb.answer()


# ── 9. Phone ─────────────────────────────────────────────────────────

@router.message(OrderForm.phone, F.contact)
async def share_phone_contact(message: Message, state: FSMContext) -> None:
    """User pressed the «Share contact» button."""
    phone = message.contact.phone_number  # type: ignore[union-attr]
    await state.update_data(phone=phone)
    await message.answer(
        "💬 Добавьте комментарий или пожелание:",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer(
        "Или нажмите «Пропустить»:", reply_markup=skip_comment_kb()
    )
    await state.set_state(OrderForm.comment)


@router.message(OrderForm.phone)
async def type_phone(message: Message, state: FSMContext) -> None:
    """User typed the phone number manually."""
    phone = (message.text or "").strip()
    if len(phone) < 6:
        await message.answer(
            "⚠️ Нажмите кнопку «📱 Отправить номер» или введите номер вручную."
        )
        return
    await state.update_data(phone=phone)
    await message.answer(
        "💬 Добавьте комментарий или пожелание:",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer(
        "Или нажмите «Пропустить»:", reply_markup=skip_comment_kb()
    )
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

async def _finish_order(message: Message, state: FSMContext, bot: Bot, user) -> None:
    data = await state.get_data()

    lead_data = {
        "telegram_id": user.id,
        "username": user.username or "",
        "full_name": user.full_name or "",
        "country": data.get("country", ""),
        "city_from": data.get("city_from", ""),
        "cargo_type": data.get("cargo_type", ""),
        "weight_kg": data.get("weight_kg", 0),
        "volume_m3": data.get("volume_m3", 0),
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
    urg_lbl = URGENCY_LABELS.get(lead_data["urgency"], lead_data["urgency"])
    terms_lbl = INCOTERMS_LABELS.get(lead_data["incoterms"], lead_data["incoterms"])

    # ── Confirmation to user ─────────────────────────────────────────
    comment_line = f"— Комментарий: {lead_data['comment']}\n" if lead_data["comment"] else ""
    await message.answer(
        f"✅ <b>Заявка #{lead_id} принята!</b>\n\n"
        f"📋 <b>Ваши данные:</b>\n"
        f"— Страна: {c_lbl}\n"
        f"— Город: {lead_data['city_from']}\n"
        f"— Груз: {cargo_lbl}\n"
        f"— Вес: {lead_data['weight_kg']} кг\n"
        f"— Объём: {lead_data['volume_m3']} м³\n"
        f"— Срочность: {urg_lbl}\n"
        f"— Условия: {terms_lbl}\n"
        f"{comment_line}\n"
        "👨‍💼 Наш менеджер свяжется с вами в ближайшее время.",
        reply_markup=after_submit_kb(),
    )

    # ── Notification to every admin ──────────────────────────────────
    username_part = f" (@{lead_data['username']})" if lead_data["username"] else ""
    comment_part = f"💬 {lead_data['comment']}\n" if lead_data["comment"] else ""
    admin_text = (
        f"🆕 <b>Новый лид #{lead_id}</b>\n\n"
        f"👤 {lead_data['full_name']}{username_part}\n"
        f"📱 {lead_data['phone']}\n"
        f"🌍 {c_lbl} → {lead_data['city_from']}\n"
        f"📦 {cargo_lbl}, {lead_data['weight_kg']} кг, {lead_data['volume_m3']} м³\n"
        f"⏰ {urg_lbl} | {terms_lbl}\n"
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
    logger.info("Lead #%d saved  [%s / %s]", lead_id, lead_data["country"], lead_data["city_from"])


# ── Post-submission quick actions ────────────────────────────────────

@router.callback_query(F.data == "action:docs")
async def action_docs(cb: CallbackQuery) -> None:
    await cb.message.answer(  # type: ignore[union-attr]
        "📎 Отправьте документы (фото, PDF, архивы) — "
        "мы прикрепим их к вашей заявке."
    )
    await cb.answer()


@router.callback_query(F.data == "action:details")
async def action_details(cb: CallbackQuery) -> None:
    await cb.message.answer(  # type: ignore[union-attr]
        "✏️ Напишите дополнительную информацию — "
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
