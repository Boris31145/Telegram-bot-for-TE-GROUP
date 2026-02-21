"""
Admin commands:
/leads [N]          — last N leads (default 10)
/lead <id>          — full lead card
/status <id> STATUS — change status (NEW | IN_PROGRESS | WON | LOST)
/export             — CSV dump of all leads
/test               — test that bot can send to admin group
"""

from __future__ import annotations

import csv
import io
import logging

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message

from bot.config import settings
from bot.db import export_all_leads, get_lead, get_leads, update_lead_status
from bot.keyboards import (
    CARGO_LABELS,
    COUNTRY_LABELS,
    DEFAULT_DELIVERY,
    DELIVERY_INFO,
    INCOTERMS_LABELS,
    URGENCY_LABELS,
    VOLUME_LABELS,
    WEIGHT_LABELS,
)

logger = logging.getLogger(__name__)
router = Router()

VALID_STATUSES = {"NEW", "IN_PROGRESS", "WON", "LOST"}
STATUS_EMOJI = {"NEW": "🆕", "IN_PROGRESS": "🔄", "WON": "✅", "LOST": "❌"}


def _is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids


def _weight_display(val) -> str:  # noqa: ANN001
    """Return a human label for weight. Checks preset labels first."""
    s = str(val)
    if s in WEIGHT_LABELS:
        return WEIGHT_LABELS[s]
    return f"{val} кг"


def _volume_display(val) -> str:  # noqa: ANN001
    s = str(val)
    if s in VOLUME_LABELS:
        return VOLUME_LABELS[s]
    return f"{val} м³"


# ── /leads ───────────────────────────────────────────────────────────

@router.message(Command("leads"))
async def cmd_leads(message: Message) -> None:
    if not _is_admin(message.from_user.id):  # type: ignore[union-attr]
        return

    args = (message.text or "").split()
    limit = int(args[1]) if len(args) > 1 and args[1].isdigit() else 10

    leads = await get_leads(limit)
    if not leads:
        await message.answer("📭 Лидов пока нет.")
        return

    lines: list[str] = [f"📋 <b>Последние {len(leads)} лидов:</b>\n"]
    for ld in leads:
        emoji = STATUS_EMOJI.get(ld["status"], "❓")
        country = COUNTRY_LABELS.get(ld["country"], ld["country"])
        date = ld["created_at"].strftime("%d.%m %H:%M")
        lines.append(
            f"{emoji} <b>#{ld['id']}</b> | {country} | "
            f"{_weight_display(ld['weight_kg'])} | {ld['status']} | {date}"
        )

    await message.answer("\n".join(lines))


# ── /lead <id> ───────────────────────────────────────────────────────

@router.message(Command("lead"))
async def cmd_lead(message: Message) -> None:
    if not _is_admin(message.from_user.id):  # type: ignore[union-attr]
        return

    args = (message.text or "").split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("⚠️ Использование: <code>/lead 123</code>")
        return

    lead = await get_lead(int(args[1]))
    if not lead:
        await message.answer("❌ Лид не найден.")
        return

    c = COUNTRY_LABELS.get(lead["country"], lead["country"])
    cargo = CARGO_LABELS.get(lead["cargo_type"], lead["cargo_type"])
    urg = URGENCY_LABELS.get(lead["urgency"], lead["urgency"])
    terms = INCOTERMS_LABELS.get(lead["incoterms"], lead["incoterms"])
    uname = f" (@{lead['username']})" if lead["username"] else ""
    comment = f"\n💬 {lead['comment']}" if lead["comment"] else ""

    delivery = DELIVERY_INFO.get(lead["country"], DEFAULT_DELIVERY).get(lead["urgency"], "")

    await message.answer(
        f"📋 <b>Лид #{lead['id']}</b>\n\n"
        f"👤 {lead['full_name']}{uname}\n"
        f"📱 {lead['phone']}\n\n"
        f"🌍 {c} → {lead['city_from']}\n"
        f"📦 {cargo}\n"
        f"⚖️ {_weight_display(lead['weight_kg'])} | 📐 {_volume_display(lead['volume_m3'])}\n"
        f"⏰ {urg}\n"
        f"💡 {delivery}\n"
        f"📋 {terms}\n\n"
        f"📊 Статус: <b>{lead['status']}</b>\n"
        f"📅 Создан: {lead['created_at'].strftime('%d.%m.%Y %H:%M')}"
        f"{comment}"
    )


# ── /status <id> NEW|IN_PROGRESS|WON|LOST ───────────────────────────

@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    if not _is_admin(message.from_user.id):  # type: ignore[union-attr]
        return

    args = (message.text or "").split()
    if len(args) < 3:
        await message.answer(
            "⚠️ Использование: <code>/status 123 IN_PROGRESS</code>\n"
            "Статусы: NEW, IN_PROGRESS, WON, LOST"
        )
        return

    if not args[1].isdigit():
        await message.answer("⚠️ ID должен быть числом.")
        return

    lead_id = int(args[1])
    status = args[2].upper()

    if status not in VALID_STATUSES:
        await message.answer(
            f"⚠️ Допустимые статусы: {', '.join(sorted(VALID_STATUSES))}"
        )
        return

    ok = await update_lead_status(lead_id, status)
    if ok:
        emoji = STATUS_EMOJI.get(status, "")
        await message.answer(f"{emoji} Лид #{lead_id} → <b>{status}</b>")
    else:
        await message.answer(f"❌ Лид #{lead_id} не найден.")


# ── /test — diagnostic: send test message to admin group ─────────────

@router.message(Command("test"))
async def cmd_test_notify(message: Message, bot: Bot) -> None:
    """
    Anyone can run /test — the bot will try to send a test message
    to every configured ADMIN_CHAT_ID and report success / error.
    Useful to verify the bot is added to the group.
    """
    results: list[str] = []
    for chat_id in settings.admin_ids:
        try:
            await bot.send_message(
                chat_id,
                f"🔔 <b>Тест уведомлений TE GROUP</b>\n"
                f"Запрошено: {message.from_user.full_name if message.from_user else 'unknown'}\n"  # type: ignore[union-attr]
                f"Если видишь это — всё работает ✅",
            )
            results.append(f"✅ <code>{chat_id}</code> — сообщение доставлено")
        except Exception as exc:
            results.append(f"❌ <code>{chat_id}</code> — ошибка: <code>{exc}</code>")

    await message.answer(
        "<b>Результат теста уведомлений:</b>\n\n"
        + "\n".join(results)
        + f"\n\n<i>ADMIN_CHAT_ID в настройках: <code>{settings.ADMIN_CHAT_ID}</code></i>\n"
        "<i>Если ошибка — убедитесь, что бот добавлен в группу как участник.</i>"
    )


# ── /export ──────────────────────────────────────────────────────────

@router.message(Command("export"))
async def cmd_export(message: Message) -> None:
    if not _is_admin(message.from_user.id):  # type: ignore[union-attr]
        return

    leads = await export_all_leads()
    if not leads:
        await message.answer("📭 Нет данных для экспорта.")
        return

    fieldnames = [
        "id", "telegram_id", "username", "full_name",
        "country", "city_from", "cargo_type",
        "weight_kg", "volume_m3", "urgency", "incoterms",
        "phone", "comment", "status", "created_at", "updated_at",
    ]

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for ld in leads:
        writer.writerow(ld)

    csv_bytes = buf.getvalue().encode("utf-8-sig")  # BOM for Excel
    doc = BufferedInputFile(csv_bytes, filename="leads_export.csv")
    await message.answer_document(doc, caption=f"📊 Экспорт: {len(leads)} лидов")
