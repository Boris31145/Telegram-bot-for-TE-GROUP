"""
TE GROUP bot — two-track funnel + free question.

Track 1  🛃 Таможня:   cargo → country → invoice → urgency → phone → comment
Track 2  🚚 Доставка:  country → city → cargo → weight → volume → urgency → phone → comment
Track 3  💬 Вопрос:    text → forward to admins → done

A single card message is edited at every step.  ← Назад on every step.
"""

from __future__ import annotations

import html as html_mod
import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardRemove,
)

from bot.config import settings
from bot.db import save_lead
from bot.keyboards import (
    CARGO_LABELS,
    COUNTRY_LABELS,
    CUSTOMS_URGENCY_INFO,
    CUSTOMS_URGENCY_LABELS,
    DEFAULT_DELIVERY,
    DELIVERY_INFO,
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
    invoice_kb,
    phone_kb,
    service_kb,
    skip_comment_kb,
    urgency_kb,
    volume_kb,
    weight_kb,
    with_back,
)
from bot.handlers.common import WELCOME_TEXT
from bot.states import OrderForm

logger = logging.getLogger(__name__)
router = Router()

# ── Layout constants ─────────────────────────────────────────
_SEP = "· · ·"
TOTAL_CUSTOMS = 5
TOTAL_DELIVERY = 7


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def _e(val: object) -> str:
    return html_mod.escape(str(val or ""))


def _bar(step: int, total: int) -> str:
    if step <= 0:
        return ""
    filled = "▰" * min(step, total)
    empty = "▱" * max(total - step, 0)
    return f"<i>{filled}{empty}  {step}/{total}</i>"


def _card(data: dict, step: int, question: str = "") -> str:
    """Build the single-card message for the current funnel state."""
    service = data.get("service", "delivery")
    total = TOTAL_CUSTOMS if service == "customs" else TOTAL_DELIVERY

    if service == "customs":
        header = "◈  <b>TE GROUP</b>  ·  🛃 Таможня"
    else:
        header = "◈  <b>TE GROUP</b>  ·  🚚 Доставка"

    lines: list[str] = [header]
    bar = _bar(step, total)
    if bar:
        lines.append(bar)
    lines.append("")

    fields: list[str] = []

    if service == "customs":
        if data.get("cargo_type"):
            fields.append(f"  📦  {_e(CARGO_LABELS.get(data['cargo_type'], data['cargo_type']))}")
        if data.get("country"):
            fields.append(f"  🌍  {_e(COUNTRY_LABELS.get(data['country'], data['country']))}")
        if data.get("invoice_value"):
            fields.append(f"  💰  {_e(INVOICE_LABELS.get(data['invoice_value'], data['invoice_value']))}")
        if data.get("customs_urgency"):
            lbl = CUSTOMS_URGENCY_LABELS.get(data["customs_urgency"], data["customs_urgency"])
            fields.append(f"  ⏰  {_e(lbl)}")
    else:
        if data.get("country"):
            fields.append(f"  🌍  {_e(COUNTRY_LABELS.get(data['country'], data['country']))}")
        if data.get("city_from"):
            fields.append(f"  📍  {_e(data['city_from'])}")
        if data.get("cargo_type"):
            fields.append(f"  📦  {_e(CARGO_LABELS.get(data['cargo_type'], data['cargo_type']))}")
        if data.get("weight_kg"):
            fields.append(f"  ⚖️  {_e(WEIGHT_LABELS.get(data['weight_kg'], data['weight_kg']))}")
        if data.get("volume_m3"):
            fields.append(f"  📐  {_e(VOLUME_LABELS.get(data['volume_m3'], data['volume_m3']))}")
        if data.get("urgency"):
            lbl = URGENCY_LABELS.get(data["urgency"], data["urgency"])
            fields.append(f"  ⏰  {_e(lbl)}")
            info = DELIVERY_INFO.get(data.get("country", ""), DEFAULT_DELIVERY).get(data["urgency"], "")
            if info:
                fields.append(f"        <i>{_e(info)}</i>")

    if fields:
        lines.extend(fields)

    if question:
        lines.append("")
        lines.append(f"  {_SEP}")
        lines.append("")
        lines.append(question)

    return "\n".join(lines)


async def _edit(
    bot: Bot, chat_id: int, msg_id: int,
    text: str, markup: InlineKeyboardMarkup | None = None,
) -> int:
    """Edit a message; if it fails (deleted/too old), send a new one."""
    try:
        await bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id, reply_markup=markup)
        return msg_id
    except Exception:
        new = await bot.send_message(chat_id, text, reply_markup=markup)
        return new.message_id


def _card_id(data: dict, cb: CallbackQuery | None = None) -> int:
    mid = data.get("card_id", 0)
    if not mid and cb and cb.message:
        mid = cb.message.message_id
    return mid


# ═══════════════════════════════════════════════════════════════
# ADMIN NOTIFICATION
# ═══════════════════════════════════════════════════════════════

async def _notify_admins(bot: Bot, lead_id: int, data: dict, service: str) -> bool:
    """Send a premium-styled lead notification to all admins."""
    svc_map = {
        "customs": "🛃 Таможня",
        "delivery": "🚚 Доставка",
        "question": "💬 Вопрос",
    }
    svc = svc_map.get(service, service)

    # ── Header ──────────────────────────────────────────────
    if lead_id:
        header = f"🆕  <b>Заявка #{lead_id}</b>  ·  {svc}"
    else:
        header = f"🆕  <b>Новая заявка</b>  ·  {svc}"

    # ── Common user info ────────────────────────────────────
    name = _e(data.get("full_name", ""))
    uname = data.get("username", "")
    phone = _e(data.get("phone", ""))
    comment = data.get("comment", "")

    user_line = f"👤  {name}" if name else "👤  —"
    if uname:
        user_line += f"  ·  @{_e(uname)}"

    lines: list[str] = [header, ""]
    lines.append(user_line)

    if phone:
        lines.append(f"📞  {phone}")

    # ── Service-specific fields ────────────────────────────
    if service == "customs":
        cargo = _e(CARGO_LABELS.get(data.get("cargo_type", ""), data.get("cargo_type", "")))
        country = _e(COUNTRY_LABELS.get(data.get("country", ""), data.get("country", "")))
        inv = _e(INVOICE_LABELS.get(data.get("invoice_value", ""), data.get("invoice_value", "")))
        urg = _e(CUSTOMS_URGENCY_LABELS.get(data.get("customs_urgency", ""), ""))

        lines.append("")
        if country:
            lines.append(f"🌍  {country}")
        if cargo:
            lines.append(f"📦  {cargo}")
        if inv:
            lines.append(f"💰  {inv}")
        if urg:
            lines.append(f"⏰  {urg}")

    elif service == "question":
        tg_id = data.get("telegram_id", "")
        if tg_id:
            lines.append(f"🆔  <code>{tg_id}</code>")

    else:  # delivery
        country = _e(COUNTRY_LABELS.get(data.get("country", ""), data.get("country", "")))
        city = _e(data.get("city_from", ""))
        cargo = _e(CARGO_LABELS.get(data.get("cargo_type", ""), data.get("cargo_type", "")))
        weight = data.get("weight_kg", 0)
        volume = data.get("volume_m3", 0)
        urg = _e(URGENCY_LABELS.get(data.get("urgency", ""), ""))

        lines.append("")
        if country and city:
            lines.append(f"🌍  {country}  →  {city}")
        elif country:
            lines.append(f"🌍  {country}")
        if cargo:
            lines.append(f"📦  {cargo}")

        dims: list[str] = []
        if weight:
            dims.append(f"⚖️ {weight} кг")
        if volume:
            dims.append(f"📐 {volume} м³")
        if dims:
            lines.append(f"{'  ·  '.join(dims)}")

        if urg:
            lines.append(f"⏰  {urg}")

    # ── Comment ─────────────────────────────────────────────
    if comment:
        lines.append("")
        lines.append(f"💬  <i>{_e(comment)}</i>")

    text = "\n".join(lines)

    # ── Send to admins (with action buttons if we have a lead) ──
    markup = admin_lead_kb(lead_id) if lead_id else None

    ok = False
    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(admin_id, text, reply_markup=markup)
            ok = True
        except Exception as exc:
            logger.error("Notify admin %s failed: %s", admin_id, exc)
    return ok


# ═══════════════════════════════════════════════════════════════
# FINISH ORDER
# ═══════════════════════════════════════════════════════════════

async def _finish(msg: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    user = msg.from_user
    service = data.get("service", "delivery")

    lead_data = {
        "telegram_id": user.id if user else 0,
        "username": getattr(user, "username", "") or "",
        "full_name": getattr(user, "full_name", "") or "",
        "service_type": service,
        "country": data.get("country", ""),
        "city_from": data.get("city_from", ""),
        "cargo_type": data.get("cargo_type", ""),
        "weight_kg": _resolve_weight(data.get("weight_kg", "0")),
        "volume_m3": _resolve_volume(data.get("volume_m3", "0")),
        "urgency": data.get("urgency", "") or data.get("customs_urgency", ""),
        "incoterms": "",
        "phone": data.get("phone", ""),
        "comment": data.get("comment", ""),
        "invoice_value": data.get("invoice_value", ""),
        "invoice_value_num": float(data.get("invoice_value_num", 0) or 0),
        "customs_direction": "",
    }

    # Save to DB (non-fatal — we still notify admins if this fails)
    lead_id = 0
    try:
        lead_id = await save_lead(lead_data)
    except Exception:
        logger.exception("save_lead failed — will still notify admins")

    # Notify admins FIRST (most important action)
    notified = await _notify_admins(bot, lead_id, lead_data, service)
    if not notified:
        logger.error("ALL admin notifications failed for lead #%d", lead_id)

    # Confirmation to user
    if lead_id:
        try:
            svc_line = "🛃 Таможня · ЕАЭС" if service == "customs" else "🚚 Доставка груза"
            await msg.answer(
                f"◈  <b>TE GROUP</b>\n\n"
                f"  {_SEP}\n\n"
                f"✅  <b>Заявка #{lead_id} принята</b>\n\n"
                f"  {svc_line}\n\n"
                f"  Менеджер рассчитает стоимость\n"
                f"  и свяжется <b>в течение 1 часа</b>.\n\n"
                f"  {_SEP}\n\n"
                f"  Спасибо за обращение!",
                reply_markup=after_submit_kb(),
            )
        except Exception:
            try:
                await msg.answer(f"✅ Заявка #{lead_id} принята. Менеджер свяжется.", parse_mode=None)
            except Exception:
                pass
    else:
        # DB save failed but admins were notified
        try:
            await msg.answer(
                f"◈  <b>TE GROUP</b>\n\n"
                f"  {_SEP}\n\n"
                f"✅  <b>Заявка отправлена менеджеру</b>\n\n"
                f"  Свяжемся <b>в течение 1 часа</b>.\n\n"
                f"  {_SEP}\n\n"
                f"  Спасибо за обращение!",
                reply_markup=after_submit_kb(),
            )
        except Exception:
            try:
                await msg.answer("✅ Заявка отправлена. Менеджер свяжется.", parse_mode=None)
            except Exception:
                pass

    await state.clear()
    logger.info("Lead #%d done [%s] (admin_notified=%s)", lead_id, service, notified)


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


# ═══════════════════════════════════════════════════════════════
# SERVICE SELECTION
# ═══════════════════════════════════════════════════════════════

_CUSTOMS_INTRO = (
    "◈  <b>TE GROUP</b>  ·  🛃 Таможня\n\n"
    f"  {_SEP}\n\n"
    "<b>Растаможим ваш груз\n"
    "в Кыргызстане</b>\n\n"
    "  КР — участник ЕАЭС с самыми\n"
    "  низкими ставками в союзе.\n"
    "  Товар <b>свободно продаётся</b>\n"
    "  в РФ, Казахстане, Беларуси.\n\n"
    f"  {_SEP}\n\n"
    "📦 <b>Какой товар растаможить?</b>"
)


@router.callback_query(OrderForm.service, F.data.startswith("service:"))
async def pick_service(cb: CallbackQuery, state: FSMContext) -> None:
    value = (cb.data or "").split(":")[1]
    await state.update_data(service=value)

    if value == "customs":
        await cb.message.edit_text(  # type: ignore[union-attr]
            _CUSTOMS_INTRO,
            reply_markup=with_back(cargo_kb(), "back:service"),
        )
        await state.set_state(OrderForm.customs_cargo)

    elif value == "delivery":
        data = await state.get_data()
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 0, "🌍 <b>Страна отправления?</b>"),
            reply_markup=with_back(country_kb(), "back:service"),
        )
        await state.set_state(OrderForm.country)

    elif value == "question":
        await cb.message.edit_text(  # type: ignore[union-attr]
            "◈  <b>TE GROUP</b>  ·  💬 Вопрос\n\n"
            f"  {_SEP}\n\n"
            "Опишите задачу или задайте вопрос —\n"
            "менеджер ответит <b>в этом чате</b>.",
        )
        await state.set_state(OrderForm.free_question)

    await cb.answer()


# ═══════════════════════════════════════════════════════════════
# FREE QUESTION
# ═══════════════════════════════════════════════════════════════

@router.message(OrderForm.free_question)
async def got_question(message: Message, state: FSMContext, bot: Bot) -> None:
    text = (message.text or "").strip()
    if len(text) < 3:
        await message.answer("Напишите чуть подробнее.")
        return

    user = message.from_user
    lead_data = {
        "telegram_id": user.id if user else 0,
        "username": getattr(user, "username", "") or "",
        "full_name": getattr(user, "full_name", "") or "",
        "service_type": "question",
        "country": "", "city_from": "", "cargo_type": "",
        "weight_kg": 0, "volume_m3": 0,
        "urgency": "", "incoterms": "",
        "phone": "", "comment": text,
        "invoice_value_num": 0, "customs_direction": "",
    }

    lead_id = 0
    try:
        lead_id = await save_lead(lead_data)
    except Exception:
        logger.warning("Could not save question to DB")

    # Forward to admins — this is the most important step
    notified = await _notify_admins(bot, lead_id, lead_data, "question")
    if not notified:
        logger.error("Question from user %s NOT delivered to any admin!",
                      user.id if user else "?")

    await message.answer(
        "◈  <b>TE GROUP</b>\n\n"
        f"  {_SEP}\n\n"
        "✅  <b>Вопрос получен</b>\n\n"
        "  Менеджер ответит в этом чате\n"
        "  в ближайшее время.\n\n"
        f"  {_SEP}\n\n"
        "  Для оформления заявки — /start",
    )
    await state.clear()


# ═══════════════════════════════════════════════════════════════
# CUSTOMS FLOW
# ═══════════════════════════════════════════════════════════════

# ── C1. Cargo ────────────────────────────────────────────────

@router.callback_query(OrderForm.customs_cargo, F.data.startswith("cargo:"))
async def c_cargo(cb: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(cargo_type=(cb.data or "").split(":")[1])
    data = await state.get_data()
    await cb.message.edit_text(  # type: ignore[union-attr]
        _card(data, 1, "🌍 <b>Откуда отправляется товар?</b>"),
        reply_markup=with_back(country_kb(), "back:c_cargo_reset"),
    )
    await state.set_state(OrderForm.customs_country)
    await cb.answer()


# ── C2. Country ──────────────────────────────────────────────

@router.callback_query(OrderForm.customs_country, F.data.startswith("country:"))
async def c_country(cb: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    value = (cb.data or "").split(":")[1]
    if value == "other":
        data = await state.get_data()
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 1, "🌍 <b>Введите название страны:</b>"),
        )
        await cb.answer()
        return
    await state.update_data(country=value)
    data = await state.get_data()
    await cb.message.edit_text(  # type: ignore[union-attr]
        _card(data, 2, "💰 <b>Примерная стоимость партии?</b>"),
        reply_markup=with_back(invoice_kb(), "back:c_country_reset"),
    )
    await state.set_state(OrderForm.invoice_value)
    await cb.answer()


@router.message(OrderForm.customs_country)
async def c_country_text(message: Message, state: FSMContext, bot: Bot) -> None:
    country = (message.text or "").strip()
    if len(country) < 2:
        await message.answer("Введите название страны.")
        return
    await state.update_data(country=country)
    data = await state.get_data()
    mid = _card_id(data)
    new_id = await _edit(
        bot, message.chat.id, mid,
        _card(data, 2, "💰 <b>Примерная стоимость партии?</b>"),
        with_back(invoice_kb(), "back:c_country_reset"),
    )
    await state.update_data(card_id=new_id)
    await state.set_state(OrderForm.invoice_value)


# ── C3. Invoice ──────────────────────────────────────────────

@router.callback_query(OrderForm.invoice_value, F.data.startswith("invoice:"))
async def c_invoice(cb: CallbackQuery, state: FSMContext) -> None:
    value = (cb.data or "").split(":")[1]
    if value == "__custom__":
        data = await state.get_data()
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 2, "💰 <b>Введите сумму в USD:</b>"),
        )
        await cb.answer()
        return
    num = INVOICE_TO_FLOAT.get(value, 0)
    await state.update_data(invoice_value=value, invoice_value_num=num)
    data = await state.get_data()
    await cb.message.edit_text(  # type: ignore[union-attr]
        _card(data, 3, "⏰ <b>Насколько срочно?</b>"),
        reply_markup=with_back(customs_urgency_kb(), "back:c_invoice_reset"),
    )
    await state.set_state(OrderForm.customs_urgency)
    await cb.answer()


@router.message(OrderForm.invoice_value)
async def c_invoice_text(message: Message, state: FSMContext, bot: Bot) -> None:
    raw = (message.text or "").strip().replace("$", "").replace(",", "").replace(" ", "")
    try:
        num = float(raw)
    except ValueError:
        await message.answer("Введите число (например: 5000).")
        return
    await state.update_data(invoice_value=f"custom_{raw}", invoice_value_num=num)
    data = await state.get_data()
    mid = _card_id(data)
    new_id = await _edit(
        bot, message.chat.id, mid,
        _card(data, 3, "⏰ <b>Насколько срочно?</b>"),
        with_back(customs_urgency_kb(), "back:c_invoice_reset"),
    )
    await state.update_data(card_id=new_id)
    await state.set_state(OrderForm.customs_urgency)


# ── C4. Customs urgency ─────────────────────────────────────

@router.callback_query(OrderForm.customs_urgency, F.data.startswith("curgency:"))
async def c_urgency(cb: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    value = (cb.data or "").split(":")[1]
    await state.update_data(customs_urgency=value)
    data = await state.get_data()
    mid = _card_id(data, cb)
    # Edit card → show phone prompt
    new_id = await _edit(
        bot, cb.message.chat.id, mid,  # type: ignore[union-attr]
        _card(data, 4, "📱 <b>Номер телефона для связи:</b>"),
    )
    # Send reply keyboard for phone sharing
    await bot.send_message(
        cb.message.chat.id,  # type: ignore[union-attr]
        "Нажмите кнопку или введите номер вручную 👇",
        reply_markup=phone_kb(),
    )
    await state.update_data(card_id=new_id)
    await state.set_state(OrderForm.phone)
    await cb.answer()


# ═══════════════════════════════════════════════════════════════
# DELIVERY FLOW
# ═══════════════════════════════════════════════════════════════

# ── D1. Country ──────────────────────────────────────────────

@router.callback_query(OrderForm.country, F.data.startswith("country:"))
async def d_country(cb: CallbackQuery, state: FSMContext) -> None:
    value = (cb.data or "").split(":")[1]
    if value == "other":
        data = await state.get_data()
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 0, "🌍 <b>Введите название страны:</b>"),
        )
        await cb.answer()
        return
    await state.update_data(country=value)
    data = await state.get_data()
    await cb.message.edit_text(  # type: ignore[union-attr]
        _card(data, 1, "📍 <b>Город отправления?</b>"),
        reply_markup=with_back(city_kb(value), "back:d_country_reset"),
    )
    await state.set_state(OrderForm.city)
    await cb.answer()


@router.message(OrderForm.country)
async def d_country_text(message: Message, state: FSMContext, bot: Bot) -> None:
    country = (message.text or "").strip()
    if len(country) < 2:
        await message.answer("Введите название страны.")
        return
    await state.update_data(country=country)
    data = await state.get_data()
    mid = _card_id(data)
    new_id = await _edit(
        bot, message.chat.id, mid,
        _card(data, 1, "📍 <b>Введите город отправления:</b>"),
    )
    await state.update_data(card_id=new_id)
    await state.set_state(OrderForm.city)


# ── D2. City ─────────────────────────────────────────────────

@router.callback_query(OrderForm.city, F.data.startswith("city:"))
async def d_city(cb: CallbackQuery, state: FSMContext) -> None:
    parts = (cb.data or "").split(":", 2)
    if len(parts) < 3:
        await cb.answer("Ошибка")
        return
    city_name = parts[2]
    data = await state.get_data()

    if city_name == "__custom__":
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 1, "📍 <b>Введите название города:</b>"),
        )
        await cb.answer()
        return

    await state.update_data(city_from=city_name)
    data = await state.get_data()
    await cb.message.edit_text(  # type: ignore[union-attr]
        _card(data, 2, "📦 <b>Тип груза?</b>"),
        reply_markup=with_back(cargo_kb(), "back:d_city_reset"),
    )
    await state.set_state(OrderForm.cargo_type)
    await cb.answer()


@router.message(OrderForm.city)
async def d_city_text(message: Message, state: FSMContext, bot: Bot) -> None:
    city = (message.text or "").strip()
    if len(city) < 2:
        await message.answer("Введите город.")
        return
    await state.update_data(city_from=city)
    data = await state.get_data()
    mid = _card_id(data)
    new_id = await _edit(
        bot, message.chat.id, mid,
        _card(data, 2, "📦 <b>Тип груза?</b>"),
        with_back(cargo_kb(), "back:d_city_reset"),
    )
    await state.update_data(card_id=new_id)
    await state.set_state(OrderForm.cargo_type)


# ── D3. Cargo ────────────────────────────────────────────────

@router.callback_query(OrderForm.cargo_type, F.data.startswith("cargo:"))
async def d_cargo(cb: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(cargo_type=(cb.data or "").split(":")[1])
    data = await state.get_data()
    await cb.message.edit_text(  # type: ignore[union-attr]
        _card(data, 3, "⚖️ <b>Примерный вес?</b>"),
        reply_markup=with_back(weight_kb(), "back:d_cargo_reset"),
    )
    await state.set_state(OrderForm.weight)
    await cb.answer()


# ── D4. Weight ───────────────────────────────────────────────

@router.callback_query(OrderForm.weight, F.data.startswith("weight:"))
async def d_weight(cb: CallbackQuery, state: FSMContext) -> None:
    value = (cb.data or "").split(":")[1]
    if value == "__custom__":
        data = await state.get_data()
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 3, "⚖️ <b>Введите вес в кг:</b>"),
        )
        await cb.answer()
        return
    await state.update_data(weight_kg=value)
    data = await state.get_data()
    await cb.message.edit_text(  # type: ignore[union-attr]
        _card(data, 4, "📐 <b>Примерный объём?</b>"),
        reply_markup=with_back(volume_kb(), "back:d_weight_reset"),
    )
    await state.set_state(OrderForm.volume)
    await cb.answer()


@router.message(OrderForm.weight)
async def d_weight_text(message: Message, state: FSMContext, bot: Bot) -> None:
    raw = (message.text or "").strip()
    try:
        float(raw)
    except ValueError:
        await message.answer("Введите число (например: 500).")
        return
    await state.update_data(weight_kg=raw)
    data = await state.get_data()
    mid = _card_id(data)
    new_id = await _edit(
        bot, message.chat.id, mid,
        _card(data, 4, "📐 <b>Примерный объём?</b>"),
        with_back(volume_kb(), "back:d_weight_reset"),
    )
    await state.update_data(card_id=new_id)
    await state.set_state(OrderForm.volume)


# ── D5. Volume ───────────────────────────────────────────────

@router.callback_query(OrderForm.volume, F.data.startswith("volume:"))
async def d_volume(cb: CallbackQuery, state: FSMContext) -> None:
    value = (cb.data or "").split(":")[1]
    if value == "__custom__":
        data = await state.get_data()
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 4, "📐 <b>Введите объём в м³:</b>"),
        )
        await cb.answer()
        return
    await state.update_data(volume_m3=value)
    data = await state.get_data()
    await cb.message.edit_text(  # type: ignore[union-attr]
        _card(data, 5, "⏰ <b>Насколько срочно?</b>"),
        reply_markup=with_back(urgency_kb(), "back:d_volume_reset"),
    )
    await state.set_state(OrderForm.urgency)
    await cb.answer()


@router.message(OrderForm.volume)
async def d_volume_text(message: Message, state: FSMContext, bot: Bot) -> None:
    raw = (message.text or "").strip()
    try:
        float(raw)
    except ValueError:
        await message.answer("Введите число (например: 5).")
        return
    await state.update_data(volume_m3=raw)
    data = await state.get_data()
    mid = _card_id(data)
    new_id = await _edit(
        bot, message.chat.id, mid,
        _card(data, 5, "⏰ <b>Насколько срочно?</b>"),
        with_back(urgency_kb(), "back:d_volume_reset"),
    )
    await state.update_data(card_id=new_id)
    await state.set_state(OrderForm.urgency)


# ── D6. Urgency ──────────────────────────────────────────────

@router.callback_query(OrderForm.urgency, F.data.startswith("urgency:"))
async def d_urgency(cb: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    value = (cb.data or "").split(":")[1]
    await state.update_data(urgency=value)
    data = await state.get_data()
    mid = _card_id(data, cb)
    new_id = await _edit(
        bot, cb.message.chat.id, mid,  # type: ignore[union-attr]
        _card(data, 6, "📱 <b>Номер телефона для связи:</b>"),
    )
    await bot.send_message(
        cb.message.chat.id,  # type: ignore[union-attr]
        "Нажмите кнопку или введите номер вручную 👇",
        reply_markup=phone_kb(),
    )
    await state.update_data(card_id=new_id)
    await state.set_state(OrderForm.phone)
    await cb.answer()


# ═══════════════════════════════════════════════════════════════
# SHARED: Phone → Comment → Finish
# ═══════════════════════════════════════════════════════════════

@router.message(OrderForm.phone, F.contact)
async def got_phone_contact(message: Message, state: FSMContext) -> None:
    phone = message.contact.phone_number  # type: ignore[union-attr]
    await state.update_data(phone=phone)
    try:
        # Remove reply keyboard
        await message.answer("✅ Принято!", reply_markup=ReplyKeyboardRemove())
        # Comment prompt
        await message.answer(
            "💬 <b>Комментарий к заявке?</b>\n\n"
            "<i>Напишите текст или нажмите «Пропустить»</i>",
            reply_markup=skip_comment_kb(),
        )
        await state.set_state(OrderForm.comment)
    except Exception as exc:
        logger.error("got_phone_contact error: %s", exc)
        await message.answer("⚠️ Ошибка. Попробуйте /start")
        await state.clear()


@router.message(OrderForm.phone)
async def got_phone_text(message: Message, state: FSMContext) -> None:
    phone = (message.text or "").strip()
    # Accept anything that looks like a phone number (digits, +, spaces, dashes, parens)
    clean = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if len(clean) < 6 or not any(c.isdigit() for c in clean):
        await message.answer(
            "📱 Введите корректный номер телефона.\n"
            "Например: +7 999 123 45 67",
        )
        return
    await state.update_data(phone=phone)
    try:
        await message.answer("✅ Принято!", reply_markup=ReplyKeyboardRemove())
        await message.answer(
            "💬 <b>Комментарий к заявке?</b>\n\n"
            "<i>Напишите текст или нажмите «Пропустить»</i>",
            reply_markup=skip_comment_kb(),
        )
        await state.set_state(OrderForm.comment)
    except Exception as exc:
        logger.error("got_phone_text error: %s", exc)
        await message.answer("⚠️ Ошибка. Попробуйте /start")
        await state.clear()


@router.callback_query(OrderForm.comment, F.data == "skip_comment")
async def skip_comment(cb: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.update_data(comment="")
    await cb.message.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]
    await _finish(cb.message, state, bot)  # type: ignore[arg-type]
    await cb.answer()


@router.message(OrderForm.comment)
async def got_comment(message: Message, state: FSMContext, bot: Bot) -> None:
    await state.update_data(comment=(message.text or "").strip())
    await _finish(message, state, bot)


# ═══════════════════════════════════════════════════════════════
# BACK NAVIGATION
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("back:"))
async def handle_back(cb: CallbackQuery, state: FSMContext) -> None:
    target = (cb.data or "").split(":", 1)[1]
    data = await state.get_data()

    # ── Back to welcome ──────────────────────────────────────
    if target == "service":
        await cb.message.edit_text(  # type: ignore[union-attr]
            WELCOME_TEXT, reply_markup=service_kb(),
        )
        await state.set_state(OrderForm.service)

    # ── CUSTOMS back ─────────────────────────────────────────
    elif target == "c_cargo_reset":
        await state.update_data(cargo_type="")
        await cb.message.edit_text(  # type: ignore[union-attr]
            _CUSTOMS_INTRO,
            reply_markup=with_back(cargo_kb(), "back:service"),
        )
        await state.set_state(OrderForm.customs_cargo)

    elif target == "c_country_reset":
        await state.update_data(country="")
        data = await state.get_data()
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 1, "🌍 <b>Откуда отправляется товар?</b>"),
            reply_markup=with_back(country_kb(), "back:c_cargo_reset"),
        )
        await state.set_state(OrderForm.customs_country)

    elif target == "c_invoice_reset":
        await state.update_data(invoice_value="", invoice_value_num=0)
        data = await state.get_data()
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 2, "💰 <b>Примерная стоимость партии?</b>"),
            reply_markup=with_back(invoice_kb(), "back:c_country_reset"),
        )
        await state.set_state(OrderForm.invoice_value)

    # ── DELIVERY back ────────────────────────────────────────
    elif target == "d_country_reset":
        await state.update_data(country="")
        data = await state.get_data()
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 0, "🌍 <b>Страна отправления?</b>"),
            reply_markup=with_back(country_kb(), "back:service"),
        )
        await state.set_state(OrderForm.country)

    elif target == "d_city_reset":
        await state.update_data(city_from="")
        data = await state.get_data()
        country = data.get("country", "")
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 1, "📍 <b>Город отправления?</b>"),
            reply_markup=with_back(city_kb(country), "back:d_country_reset"),
        )
        await state.set_state(OrderForm.city)

    elif target == "d_cargo_reset":
        await state.update_data(cargo_type="")
        data = await state.get_data()
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 2, "📦 <b>Тип груза?</b>"),
            reply_markup=with_back(cargo_kb(), "back:d_city_reset"),
        )
        await state.set_state(OrderForm.cargo_type)

    elif target == "d_weight_reset":
        await state.update_data(weight_kg="")
        data = await state.get_data()
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 3, "⚖️ <b>Примерный вес?</b>"),
            reply_markup=with_back(weight_kb(), "back:d_cargo_reset"),
        )
        await state.set_state(OrderForm.weight)

    elif target == "d_volume_reset":
        await state.update_data(volume_m3="")
        data = await state.get_data()
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 4, "📐 <b>Примерный объём?</b>"),
            reply_markup=with_back(volume_kb(), "back:d_weight_reset"),
        )
        await state.set_state(OrderForm.volume)

    elif target == "d_urgency_reset":
        await state.update_data(urgency="")
        data = await state.get_data()
        await cb.message.edit_text(  # type: ignore[union-attr]
            _card(data, 5, "⏰ <b>Насколько срочно?</b>"),
            reply_markup=with_back(urgency_kb(), "back:d_volume_reset"),
        )
        await state.set_state(OrderForm.urgency)

    await cb.answer()


# ═══════════════════════════════════════════════════════════════
# POST-SUBMIT ACTIONS
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "action:restart")
async def action_restart(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.message.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]
    msg = await cb.message.answer(WELCOME_TEXT, reply_markup=service_kb())  # type: ignore[union-attr]
    await state.clear()
    await state.update_data(card_id=msg.message_id)
    await state.set_state(OrderForm.service)
    await cb.answer()


@router.callback_query(F.data.startswith("action:"))
async def action_misc(cb: CallbackQuery) -> None:
    action = (cb.data or "").split(":")[1]
    texts = {
        "call": "📞 Менеджер перезвонит вам в ближайшее время.",
    }
    await cb.answer(texts.get(action, "Менеджер свяжется с вами."), show_alert=True)


# ── Admin inline buttons ─────────────────────────────────────

@router.callback_query(F.data.startswith("adm:"))
async def admin_action(cb: CallbackQuery) -> None:
    parts = (cb.data or "").split(":")
    if len(parts) < 3:
        await cb.answer()
        return
    action, lead_id_str = parts[1], parts[2]
    if action == "progress":
        from bot.db import update_lead_status
        await update_lead_status(int(lead_id_str), "IN_PROGRESS")
        await cb.answer(f"✅ Лид #{lead_id_str} → В РАБОТЕ")
    elif action == "call":
        from bot.db import get_lead
        lead = await get_lead(int(lead_id_str))
        phone = lead.get("phone", "—") if lead else "—"
        await cb.answer(f"📞 {phone}", show_alert=True)
    else:
        await cb.answer()
