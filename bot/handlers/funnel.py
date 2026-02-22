"""
TE GROUP bot — two-track funnel.

Track 1  🛃 Таможня:  cargo → country → invoice → urgency → phone → comment
Track 2  🚚 Доставка: country → city → cargo → weight → volume → urgency → incoterms → phone → comment

Single card message is edited at every step. ← Назад on every step.
"""

import html
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
from bot.db import save_lead
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

TOTAL_CUSTOMS = 5
TOTAL_DELIVERY = 8
_DIV = "─" * 18

# ── Texts ─────────────────────────────────────────────────────────

_WELCOME = (
    "✦  <b>TE GROUP</b>  ✦\n"
    "<i>Таможня · Логистика · ЕАЭС</i>\n"
    f"{_DIV}\n\n"
    "Работаем в <b>Кыргызстане</b> — участнике\n"
    "Таможенного союза ЕАЭС.\n\n"
    "✅  Самые низкие ставки таможни в ЕАЭС\n"
    "✅  Доставка в РФ, Казахстан, Беларусь\n"
    "✅  Любая страна отправления\n"
    "✅  100 % легально, все документы чистые\n\n"
    f"{_DIV}\n"
    "<b>Какая услуга вас интересует?</b>"
)

_CUSTOMS_INTRO = (
    "✦  <b>TE GROUP</b>  ✦  ·  <i>🛃 Таможня</i>\n"
    f"{_DIV}\n\n"
    "<b>Растаможим ваш груз в Кыргызстане.</b>\n\n"
    "КР — участник ЕАЭС с самыми низкими\n"
    "таможенными ставками в союзе.\n\n"
    "Растаможенный товар <b>свободно продаётся</b>\n"
    "в России, Казахстане, Беларуси —\n"
    "без повторного оформления.\n\n"
    f"{_DIV}\n"
    "📦 <b>Какой товар нужно растаможить?</b>"
)


# ══════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════

def _e(val: object) -> str:
    """HTML-escape any value (safe for Telegram HTML parse mode)."""
    return html.escape(str(val or ""))


def _bar(step: int, total: int) -> str:
    if step <= 0 or total <= 0:
        return ""
    filled = "▰" * min(step, total)
    empty = "▱" * max(total - step, 0)
    return f"<i>{filled}{empty}  шаг {step} / {total}</i>"


def _card(data: dict, step: int, question: str = "") -> str:
    service = data.get("service", "delivery")
    total = TOTAL_CUSTOMS if service == "customs" else TOTAL_DELIVERY

    if service == "customs":
        header = "✦  <b>TE GROUP</b>  ✦\n<i>🛃 Таможня · Кыргызстан → ЕАЭС</i>"
    else:
        header = "✦  <b>TE GROUP</b>  ✦\n<i>🚚 Доставка груза</i>"

    lines: list[str] = [header]
    bar = _bar(step, total)
    if bar:
        lines.append(bar)

    fields: list[str] = []

    if service == "customs":
        if data.get("cargo_type"):
            fields.append(f"▸ Товар · <b>{_e(CARGO_LABELS.get(data['cargo_type'], data['cargo_type']))}</b>")
        if data.get("country"):
            fields.append(f"▸ Откуда · <b>{_e(COUNTRY_LABELS.get(data['country'], data['country']))}</b>")
        if data.get("invoice_value"):
            fields.append(f"▸ Стоимость · <b>{_e(INVOICE_LABELS.get(data['invoice_value'], data['invoice_value']))}</b>")
        if data.get("customs_urgency"):
            lbl = CUSTOMS_URGENCY_LABELS.get(data["customs_urgency"], data["customs_urgency"])
            fields.append(f"▸ Срочность · <b>{_e(lbl)}</b>")
            info = CUSTOMS_URGENCY_INFO.get(data["customs_urgency"], "")
            if info:
                fields.append(f"   <i>╰ {_e(info)}</i>")
    else:
        if data.get("country"):
            fields.append(f"▸ Страна · <b>{_e(COUNTRY_LABELS.get(data['country'], data['country']))}</b>")
        if data.get("city_from"):
            fields.append(f"▸ Город · <b>{_e(data['city_from'])}</b>")
        if data.get("cargo_type"):
            fields.append(f"▸ Груз · <b>{_e(CARGO_LABELS.get(data['cargo_type'], data['cargo_type']))}</b>")
        if data.get("weight_kg"):
            fields.append(f"▸ Вес · <b>{_e(WEIGHT_LABELS.get(data['weight_kg'], data['weight_kg']))}</b>")
        if data.get("volume_m3"):
            fields.append(f"▸ Объём · <b>{_e(VOLUME_LABELS.get(data['volume_m3'], data['volume_m3']))}</b>")
        if data.get("urgency"):
            fields.append(f"▸ Срочность · <b>{_e(URGENCY_LABELS.get(data['urgency'], data['urgency']))}</b>")
            info = DELIVERY_INFO.get(data.get("country", ""), DEFAULT_DELIVERY).get(data["urgency"], "")
            if info:
                fields.append(f"   <i>╰ {_e(info)}</i>")
        if data.get("incoterms"):
            fields.append(f"▸ Условия · <b>{_e(INCOTERMS_LABELS.get(data['incoterms'], data['incoterms']))}</b>")

    if fields:
        lines.append(_DIV)
        lines.extend(fields)

    if question:
        lines.append(_DIV)
        lines.append(question)

    return "\n".join(lines)


def _with_back(kb: InlineKeyboardMarkup, back_cb: str) -> InlineKeyboardMarkup:
    rows = list(kb.inline_keyboard)
    rows.append([InlineKeyboardButton(text="← Назад", callback_data=back_cb)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _edit_card(
    bot: Bot, chat_id: int, msg_id: int,
    text: str, markup: InlineKeyboardMarkup | None = None,
) -> int:
    try:
        await bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id, reply_markup=markup)
        return msg_id
    except Exception:
        new = await bot.send_message(chat_id, text, reply_markup=markup)
        return new.message_id


async def _show_phone_step(
    bot: Bot, chat_id: int, card_id: int, data: dict, step: int,
) -> int:
    new_id = await _edit_card(
        bot, chat_id, card_id,
        _card(data, step, "📱 <b>Поделитесь контактом или введите номер:</b>"),
        None,
    )
    await bot.send_message(
        chat_id,
        "👇 Нажмите кнопку или введите номер вручную:",
        reply_markup=phone_kb(),
    )
    return new_id


def _resolve_weight(raw: str) -> float:
    if raw in WEIGHT_TO_FLOAT:
        return WEIGHT_TO_FLOAT[raw]
    try:
        return float(raw)
    except (ValueError, TypeError):
        return 0.0


def _resolve_volume(raw: str) -> float:
    if raw in VOLUME_TO_FLOAT:
        return VOLUME_TO_FLOAT[raw]
    try:
        return float(raw)
    except (ValueError, TypeError):
        return 0.0


# ══════════════════════════════════════════════════════════════════
# ADMIN NOTIFICATION — bulletproof, plain-text first
# ══════════════════════════════════════════════════════════════════

async def _notify_admins(bot: Bot, lead_id: int, lead_data: dict, service: str) -> bool:
    """
    Send lead notification to ALL admin chats.
    Uses parse_mode=None (plain text) — guaranteed safe.
    Returns True if at least one notification succeeded.
    """
    svc = "Таможня" if service == "customs" else "Доставка"

    name = lead_data.get("full_name", "")
    uname = lead_data.get("username", "")
    phone = lead_data.get("phone", "")
    country = COUNTRY_LABELS.get(lead_data.get("country", ""), lead_data.get("country", ""))
    comment = lead_data.get("comment", "")

    uname_part = f" (@{uname})" if uname else ""
    comment_part = f"\nКомментарий: {comment}" if comment else ""

    if service == "customs":
        cargo = CARGO_LABELS.get(lead_data.get("cargo_type", ""), lead_data.get("cargo_type", ""))
        inv = INVOICE_LABELS.get(lead_data.get("invoice_value", ""), lead_data.get("invoice_value", ""))
        urg = CUSTOMS_URGENCY_LABELS.get(lead_data.get("customs_urgency", ""), "")
        text = (
            f"🆕 НОВАЯ ЗАЯВКА #{lead_id} | {svc}\n"
            f"{'=' * 30}\n"
            f"Имя: {name}{uname_part}\n"
            f"Тел: {phone}\n"
            f"Товар: {cargo}\n"
            f"Страна: {country}\n"
            f"Стоимость: {inv}\n"
            f"Срочность: {urg}"
            f"{comment_part}"
        )
    else:
        city = lead_data.get("city_from", "")
        cargo = CARGO_LABELS.get(lead_data.get("cargo_type", ""), lead_data.get("cargo_type", ""))
        weight = lead_data.get("weight_kg", 0)
        volume = lead_data.get("volume_m3", 0)
        urg = URGENCY_LABELS.get(lead_data.get("urgency", ""), "")
        terms = INCOTERMS_LABELS.get(lead_data.get("incoterms", ""), "")
        text = (
            f"🆕 НОВАЯ ЗАЯВКА #{lead_id} | {svc}\n"
            f"{'=' * 30}\n"
            f"Имя: {name}{uname_part}\n"
            f"Тел: {phone}\n"
            f"Страна: {country} → {city}\n"
            f"Груз: {cargo}\n"
            f"Вес: {weight} кг | Объём: {volume} м³\n"
            f"Срочность: {urg}\n"
            f"Условия: {terms}"
            f"{comment_part}"
        )

    ok = False
    for admin_id in settings.admin_ids:
        try:
            # Plain text — no HTML, no parse errors possible
            await bot.send_message(admin_id, text, parse_mode=None)
            logger.info("Admin %s notified: lead #%d", admin_id, lead_id)
            ok = True
        except Exception as exc:
            logger.error("FAILED notify admin %s: %s", admin_id, exc)

    return ok


# ══════════════════════════════════════════════════════════════════
# FINISH ORDER
# ══════════════════════════════════════════════════════════════════

async def _finish_order(
    message: Message, state: FSMContext, bot: Bot, user: object,
) -> None:
    data = await state.get_data()
    service = data.get("service", "delivery")

    base = {
        "telegram_id": user.id,  # type: ignore[union-attr]
        "username": getattr(user, "username", "") or "",
        "full_name": getattr(user, "full_name", "") or "",
        "service_type": service,
        "country": data.get("country", ""),
        "phone": data.get("phone", ""),
        "comment": data.get("comment", ""),
    }

    if service == "customs":
        lead_data = {
            **base,
            "cargo_type": data.get("cargo_type", ""),
            "invoice_value": data.get("invoice_value", ""),
            "invoice_value_num": float(data.get("invoice_value_num", 0) or 0),
            "customs_urgency": data.get("customs_urgency", ""),
        }
    else:
        lead_data = {
            **base,
            "city_from": data.get("city_from", ""),
            "cargo_type": data.get("cargo_type", ""),
            "weight_kg": _resolve_weight(data.get("weight_kg", "0")),
            "volume_m3": _resolve_volume(data.get("volume_m3", "0")),
            "urgency": data.get("urgency", ""),
            "incoterms": data.get("incoterms", ""),
        }

    # ── Save to DB ─────────────────────────────────────────────
    try:
        lead_id = await save_lead(lead_data)
    except Exception:
        logger.exception("save_lead failed")
        try:
            await message.answer(
                "⚠️ Ошибка сохранения. Попробуйте ещё раз\n"
                "или напишите <b>info@tegroup.cc</b>",
            )
        except Exception:
            pass
        await state.clear()
        return

    # ── User confirmation (non-critical) ───────────────────────
    try:
        if service == "customs":
            await message.answer(
                f"✦  <b>TE GROUP</b>  ✦\n"
                f"<b>✅ Заявка #{lead_id} принята!</b>\n"
                f"{_DIV}\n"
                f"🛃  Таможня · Кыргызстан → ЕАЭС\n\n"
                f"Менеджер рассчитает стоимость\n"
                f"и свяжется с вами <b>в течение 1 часа.</b>\n\n"
                f"💡 Ставки КР — самые низкие в ЕАЭС.\n"
                f"Товар свободно продаётся в РФ.",
                reply_markup=after_submit_kb(),
            )
        else:
            await message.answer(
                f"✦  <b>TE GROUP</b>  ✦\n"
                f"<b>✅ Заявка #{lead_id} принята!</b>\n"
                f"{_DIV}\n"
                f"🚚  Доставка груза\n\n"
                f"Менеджер свяжется с вами в ближайшее время.",
                reply_markup=after_submit_kb(),
            )
    except Exception as exc:
        logger.error("User confirmation failed: %s", exc)
        try:
            await message.answer(f"✅ Заявка #{lead_id} принята! Менеджер свяжется с вами.")
        except Exception:
            pass

    # ── Admin notification (critical) ──────────────────────────
    notified = await _notify_admins(bot, lead_id, lead_data, service)
    if not notified:
        logger.error("ALL admin notifications failed for lead #%d", lead_id)
        try:
            await message.answer(
                "⚠️ Заявка сохранена, но уведомление менеджеру не дошло.\n"
                "Напишите нам: <b>info@tegroup.cc</b>"
            )
        except Exception:
            pass

    await state.clear()
    logger.info("Lead #%d done [%s]", lead_id, service)


# ══════════════════════════════════════════════════════════════════
# 1. /start
# ══════════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════════
# 2. Service selection
# ══════════════════════════════════════════════════════════════════

@router.callback_query(OrderForm.service, F.data.startswith("service:"))
async def pick_service(cb: CallbackQuery, state: FSMContext) -> None:
    value = cb.data.split(":")[1]
    await state.update_data(service=value)

    if value == "customs":
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


# ══════════════════════════════════════════════════════════════════
# CUSTOMS FLOW
# ══════════════════════════════════════════════════════════════════

# ── C1. Cargo type ───────────────────────────────────────────────

@router.callback_query(OrderForm.customs_cargo, F.data.startswith("cargo:"))
async def pick_customs_cargo(cb: CallbackQuery, state: FSMContext) -> None:
    value = cb.data.split(":")[1]
    await state.update_data(cargo_type=value)
    data = await state.get_data()
    await cb.message.edit_text(  # type: ignore[union-attr]
        _card(data, 1, "🌍 <b>Откуда отправляется товар?</b>"),
        reply_markup=_with_back(country_kb(), "back:customs_cargo_reset"),
    )
    await state.set_state(OrderForm.customs_country)
    await cb.answer()


# ── C2. Country ──────────────────────────────────────────────────

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
        _card(data, 2, "💰 <b>Примерная стоимость партии?</b>"),
        reply_markup=_with_back(invoice_kb(), "back:customs_country_reset"),
    )
    await state.set_state(OrderForm.invoice_value)
    await cb.answer()


@router.message(OrderForm.customs_country)
async def type_customs_country(message: Message, state: FSMContext, bot: Bot) -> None:
    country = (message.text or "").strip()
    if len(country) < 2:
        await message.answer("⚠️ Введите название страны.")
        return
    await state.update_data(country=country)
    data = await state.get_data()
    card_id = data.get("card_message_id", 0)
    new_id = await _edit_card(
        bot, message.chat.id, card_id,
        _card(data, 2, "💰 <b>Примерная стоимость партии?</b>"),
        _with_back(invoice_kb(), "back:customs_country_reset"),
    )
    await state.update_data(card_message_id=new_id)
    await state.set_state(OrderForm.invoice_value)


# ── C3. Invoice value ────────────────────────────────────────────

@router.callback_query(OrderForm.invoice_value, F.data.startswith("invoice:"))
async def pick_invoice(cb: CallbackQuery, state: FSMContext) -> None:
    value = cb.data.split(":")[1]
    if value == "__custom__":
        data = await state.get_data()
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 2, "💰 <b>Введите сумму в USD:</b>"),
            reply_markup=None,
        )
        await cb.answer()
        return
    num = INVOICE_TO_FLOAT.get(value, 0)
    await state.update_data(invoice_value=value, invoice_value_num=num)
    data = await state.get_data()
    await cb.message.edit_text(  # type: ignore[union-attr]
        _card(data, 3, "⏰ <b>Насколько срочно?</b>"),
        reply_markup=_with_back(customs_urgency_kb(), "back:invoice_reset"),
    )
    await state.set_state(OrderForm.customs_urgency)
    await cb.answer()


@router.message(OrderForm.invoice_value)
async def type_invoice(message: Message, state: FSMContext, bot: Bot) -> None:
    raw = (message.text or "").strip().replace("$", "").replace(",", "").replace(" ", "")
    try:
        num = float(raw)
    except ValueError:
        await message.answer("⚠️ Введите число (например: 5000).")
        return
    await state.update_data(invoice_value=f"custom_{raw}", invoice_value_num=num)
    data = await state.get_data()
    card_id = data.get("card_message_id", 0)
    new_id = await _edit_card(
        bot, message.chat.id, card_id,
        _card(data, 3, "⏰ <b>Насколько срочно?</b>"),
        _with_back(customs_urgency_kb(), "back:invoice_reset"),
    )
    await state.update_data(card_message_id=new_id)
    await state.set_state(OrderForm.customs_urgency)


# ── C4. Customs urgency ──────────────────────────────────────────

@router.callback_query(OrderForm.customs_urgency, F.data.startswith("curgency:"))
async def pick_customs_urgency(cb: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    value = cb.data.split(":")[1]
    await state.update_data(customs_urgency=value)
    data = await state.get_data()
    card_id = data.get("card_message_id", cb.message.message_id)  # type: ignore[union-attr]
    new_id = await _show_phone_step(bot, cb.message.chat.id, card_id, data, 4)  # type: ignore[union-attr]
    await state.update_data(card_message_id=new_id)
    await state.set_state(OrderForm.phone)
    await cb.answer()


# ══════════════════════════════════════════════════════════════════
# DELIVERY FLOW
# ══════════════════════════════════════════════════════════════════

# ── D1. Country ──────────────────────────────────────────────────

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
        reply_markup=_with_back(city_kb(value), "back:country_reset"),
    )
    await state.set_state(OrderForm.city)
    await cb.answer()


@router.message(OrderForm.country)
async def type_other_country(message: Message, state: FSMContext, bot: Bot) -> None:
    country = (message.text or "").strip()
    if len(country) < 2:
        await message.answer("⚠️ Введите название страны.")
        return
    await state.update_data(country=country)
    data = await state.get_data()
    card_id = data.get("card_message_id", 0)
    new_id = await _edit_card(
        bot, message.chat.id, card_id,
        _card(data, 1, "📍 <b>Введите город отправления:</b>"),
        None,
    )
    await state.update_data(card_message_id=new_id)
    await state.set_state(OrderForm.city)


# ── D2. City ─────────────────────────────────────────────────────

@router.callback_query(OrderForm.city, F.data.startswith("city:"))
async def pick_city(cb: CallbackQuery, state: FSMContext) -> None:
    parts = (cb.data or "").split(":", 2)
    if len(parts) < 3:
        await cb.answer("Ошибка формата")
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
        reply_markup=_with_back(cargo_kb(), "back:city_reset"),
    )
    await state.set_state(OrderForm.cargo_type)
    await cb.answer()


@router.message(OrderForm.city)
async def type_city(message: Message, state: FSMContext, bot: Bot) -> None:
    city = (message.text or "").strip()
    if len(city) < 2:
        await message.answer("⚠️ Введите город.")
        return
    await state.update_data(city_from=city)
    data = await state.get_data()
    card_id = data.get("card_message_id", 0)
    new_id = await _edit_card(
        bot, message.chat.id, card_id,
        _card(data, 2, "📦 <b>Выберите тип груза:</b>"),
        _with_back(cargo_kb(), "back:city_reset"),
    )
    await state.update_data(card_message_id=new_id)
    await state.set_state(OrderForm.cargo_type)


# ── D3. Cargo type ───────────────────────────────────────────────

@router.callback_query(OrderForm.cargo_type, F.data.startswith("cargo:"))
async def pick_cargo(cb: CallbackQuery, state: FSMContext) -> None:
    value = cb.data.split(":")[1]
    await state.update_data(cargo_type=value)
    data = await state.get_data()
    await cb.message.edit_text(  # type: ignore[union-attr]
        _card(data, 3, "⚖️ <b>Примерный вес груза:</b>"),
        reply_markup=_with_back(weight_kb(), "back:cargo_reset"),
    )
    await state.set_state(OrderForm.weight)
    await cb.answer()


# ── D4. Weight ───────────────────────────────────────────────────

@router.callback_query(OrderForm.weight, F.data.startswith("weight:"))
async def pick_weight(cb: CallbackQuery, state: FSMContext) -> None:
    value = cb.data.split(":")[1]
    if value == "__custom__":
        data = await state.get_data()
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 3, "⚖️ <b>Введите вес в кг:</b>"),
            reply_markup=None,
        )
        await cb.answer()
        return
    await state.update_data(weight_kg=value)
    data = await state.get_data()
    await cb.message.edit_text(  # type: ignore[union-attr]
        _card(data, 4, "📐 <b>Примерный объём груза:</b>"),
        reply_markup=_with_back(volume_kb(), "back:weight_reset"),
    )
    await state.set_state(OrderForm.volume)
    await cb.answer()


@router.message(OrderForm.weight)
async def type_weight(message: Message, state: FSMContext, bot: Bot) -> None:
    raw = (message.text or "").strip()
    try:
        float(raw)
    except ValueError:
        await message.answer("⚠️ Введите число (например: 500).")
        return
    await state.update_data(weight_kg=raw)
    data = await state.get_data()
    card_id = data.get("card_message_id", 0)
    new_id = await _edit_card(
        bot, message.chat.id, card_id,
        _card(data, 4, "📐 <b>Примерный объём груза:</b>"),
        _with_back(volume_kb(), "back:weight_reset"),
    )
    await state.update_data(card_message_id=new_id)
    await state.set_state(OrderForm.volume)


# ── D5. Volume ───────────────────────────────────────────────────

@router.callback_query(OrderForm.volume, F.data.startswith("volume:"))
async def pick_volume(cb: CallbackQuery, state: FSMContext) -> None:
    value = cb.data.split(":")[1]
    if value == "__custom__":
        data = await state.get_data()
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 4, "📐 <b>Введите объём в м³:</b>"),
            reply_markup=None,
        )
        await cb.answer()
        return
    await state.update_data(volume_m3=value)
    data = await state.get_data()
    await cb.message.edit_text(  # type: ignore[union-attr]
        _card(data, 5, "⏰ <b>Насколько срочно?</b>"),
        reply_markup=_with_back(urgency_kb(), "back:volume_reset"),
    )
    await state.set_state(OrderForm.urgency)
    await cb.answer()


@router.message(OrderForm.volume)
async def type_volume(message: Message, state: FSMContext, bot: Bot) -> None:
    raw = (message.text or "").strip()
    try:
        float(raw)
    except ValueError:
        await message.answer("⚠️ Введите число (например: 5).")
        return
    await state.update_data(volume_m3=raw)
    data = await state.get_data()
    card_id = data.get("card_message_id", 0)
    new_id = await _edit_card(
        bot, message.chat.id, card_id,
        _card(data, 5, "⏰ <b>Насколько срочно?</b>"),
        _with_back(urgency_kb(), "back:volume_reset"),
    )
    await state.update_data(card_message_id=new_id)
    await state.set_state(OrderForm.urgency)


# ── D6. Urgency ──────────────────────────────────────────────────

@router.callback_query(OrderForm.urgency, F.data.startswith("urgency:"))
async def pick_urgency(cb: CallbackQuery, state: FSMContext) -> None:
    value = cb.data.split(":")[1]
    await state.update_data(urgency=value)
    data = await state.get_data()
    await cb.message.edit_text(  # type: ignore[union-attr]
        _card(data, 6, "📋 <b>Условия поставки (Incoterms):</b>"),
        reply_markup=_with_back(incoterms_kb(), "back:urgency_reset"),
    )
    await state.set_state(OrderForm.incoterms)
    await cb.answer()


# ── D7. Incoterms ────────────────────────────────────────────────

@router.callback_query(OrderForm.incoterms, F.data.startswith("terms:"))
async def pick_incoterms(cb: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    value = cb.data.split(":")[1]
    await state.update_data(incoterms=value)
    data = await state.get_data()
    card_id = data.get("card_message_id", cb.message.message_id)  # type: ignore[union-attr]
    new_id = await _show_phone_step(bot, cb.message.chat.id, card_id, data, 7)  # type: ignore[union-attr]
    await state.update_data(card_message_id=new_id)
    await state.set_state(OrderForm.phone)
    await cb.answer()


# ══════════════════════════════════════════════════════════════════
# SHARED: Phone + Comment
# ══════════════════════════════════════════════════════════════════

@router.message(OrderForm.phone, F.contact)
async def got_phone_contact(message: Message, state: FSMContext) -> None:
    phone = message.contact.phone_number  # type: ignore[union-attr]
    await state.update_data(phone=phone)
    await message.answer(
        "💬 <b>Комментарий к заявке?</b>\n"
        "(или нажмите Пропустить)",
        reply_markup=ReplyKeyboardRemove(),
    )
    # Small delay then send skip button
    await message.answer("👇", reply_markup=skip_comment_kb())
    await state.set_state(OrderForm.comment)


@router.message(OrderForm.phone)
async def got_phone_text(message: Message, state: FSMContext) -> None:
    phone = (message.text or "").strip()
    if len(phone) < 6:
        await message.answer("⚠️ Введите корректный номер телефона.")
        return
    await state.update_data(phone=phone)
    await message.answer(
        "💬 <b>Комментарий к заявке?</b>\n"
        "(или нажмите Пропустить)",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer("👇", reply_markup=skip_comment_kb())
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


# ══════════════════════════════════════════════════════════════════
# BACK NAVIGATION
# ══════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("back:"))
async def handle_back(cb: CallbackQuery, state: FSMContext) -> None:
    target = (cb.data or "").split(":")[1]
    data = await state.get_data()
    service = data.get("service", "delivery")

    # ── Back to service selection ─────────────────────────────
    if target == "service":
        await cb.message.edit_text(  # type: ignore[union-attr]
            _WELCOME, reply_markup=service_kb(),
        )
        await state.set_state(OrderForm.service)

    # ── CUSTOMS back steps ────────────────────────────────────
    elif target == "customs_cargo_reset":
        await state.update_data(cargo_type="")
        await cb.message.edit_text(  # type: ignore[union-attr]
            _CUSTOMS_INTRO,
            reply_markup=_with_back(cargo_kb(), "back:service"),
        )
        await state.set_state(OrderForm.customs_cargo)

    elif target == "customs_country_reset":
        await state.update_data(country="")
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 1, "🌍 <b>Откуда отправляется товар?</b>"),
            reply_markup=_with_back(country_kb(), "back:customs_cargo_reset"),
        )
        await state.set_state(OrderForm.customs_country)

    elif target == "invoice_reset":
        await state.update_data(invoice_value="", invoice_value_num=0)
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 2, "💰 <b>Примерная стоимость партии?</b>"),
            reply_markup=_with_back(invoice_kb(), "back:customs_country_reset"),
        )
        await state.set_state(OrderForm.invoice_value)

    # ── DELIVERY back steps ───────────────────────────────────
    elif target == "country_reset":
        await state.update_data(country="")
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 0, "🌍 <b>Выберите страну отправления:</b>"),
            reply_markup=_with_back(country_kb(), "back:service"),
        )
        await state.set_state(OrderForm.country)

    elif target == "city_reset":
        await state.update_data(city_from="")
        country = data.get("country", "")
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 1, "📍 <b>Выберите город отправления:</b>"),
            reply_markup=_with_back(city_kb(country), "back:country_reset"),
        )
        await state.set_state(OrderForm.city)

    elif target == "cargo_reset":
        await state.update_data(cargo_type="")
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 2, "📦 <b>Выберите тип груза:</b>"),
            reply_markup=_with_back(cargo_kb(), "back:city_reset"),
        )
        await state.set_state(OrderForm.cargo_type)

    elif target == "weight_reset":
        await state.update_data(weight_kg="")
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 3, "⚖️ <b>Примерный вес груза:</b>"),
            reply_markup=_with_back(weight_kb(), "back:cargo_reset"),
        )
        await state.set_state(OrderForm.weight)

    elif target == "volume_reset":
        await state.update_data(volume_m3="")
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 4, "📐 <b>Примерный объём груза:</b>"),
            reply_markup=_with_back(volume_kb(), "back:weight_reset"),
        )
        await state.set_state(OrderForm.volume)

    elif target == "urgency_reset":
        await state.update_data(urgency="")
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 5, "⏰ <b>Насколько срочно?</b>"),
            reply_markup=_with_back(urgency_kb(), "back:volume_reset"),
        )
        await state.set_state(OrderForm.urgency)

    await cb.answer()


# ══════════════════════════════════════════════════════════════════
# POST-SUBMIT ACTIONS
# ══════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "action:restart")
async def action_restart(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.message.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]
    msg = await cb.message.answer(_WELCOME, reply_markup=service_kb())  # type: ignore[union-attr]
    await state.clear()
    await state.update_data(card_message_id=msg.message_id)
    await state.set_state(OrderForm.service)
    await cb.answer()


@router.callback_query(F.data.startswith("action:"))
async def action_placeholder(cb: CallbackQuery) -> None:
    action = (cb.data or "").split(":")[1]
    texts = {
        "docs": "📎 Для прикрепления документов свяжитесь с менеджером.\nОн ответит вам в ближайшее время.",
        "details": "✏️ Менеджер уточнит все детали при звонке.",
        "call": "📞 Менеджер перезвонит вам в ближайшее время.\nИли напишите нам: info@tegroup.cc",
    }
    await cb.answer(texts.get(action, "Менеджер свяжется с вами."), show_alert=True)


# ── Admin inline buttons (from group notifications) ──────────────

@router.callback_query(F.data.startswith("adm:"))
async def admin_action(cb: CallbackQuery, state: FSMContext) -> None:
    parts = (cb.data or "").split(":")
    if len(parts) < 3:
        await cb.answer()
        return
    action = parts[1]
    lead_id = parts[2]
    if action == "progress":
        from bot.db import update_lead_status
        await update_lead_status(int(lead_id), "IN_PROGRESS")
        await cb.answer(f"✅ Лид #{lead_id} → В РАБОТЕ")
    elif action == "call":
        from bot.db import get_lead
        lead = await get_lead(int(lead_id))
        phone = lead.get("phone", "—") if lead else "—"
        await cb.answer(f"📞 Тел: {phone}", show_alert=True)
    else:
        await cb.answer()
