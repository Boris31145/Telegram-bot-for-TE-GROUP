"""
Admin commands:
/leads [N]          — last N leads
/lead <id>          — lead details
/status <id> STATUS — change status
/export             — CSV dump
/test               — test admin notification
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

logger = logging.getLogger(__name__)
router = Router()

VALID_STATUSES = {"NEW", "IN_PROGRESS", "WON", "LOST"}
STATUS_EMOJI = {"NEW": "🆕", "IN_PROGRESS": "🔄", "WON": "✅", "LOST": "❌"}


def _is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids


@router.message(Command("leads"))
async def cmd_leads(message: Message) -> None:
    if not _is_admin(message.from_user.id):  # type: ignore[union-attr]
        return
    args = (message.text or "").split()
    limit = int(args[1]) if len(args) > 1 and args[1].isdigit() else 10
    try:
        leads = await get_leads(limit)
    except Exception:
        await message.answer("⚠️ База данных недоступна.")
        return
    if not leads:
        await message.answer("📭 Лидов пока нет.")
        return
    lines = [f"📋 <b>Последние {len(leads)} лидов:</b>\n"]
    for ld in leads:
        emoji = STATUS_EMOJI.get(ld["status"], "❓")
        date = ld["created_at"].strftime("%d.%m %H:%M")
        lines.append(
            f"{emoji} <b>#{ld['id']}</b> | {ld.get('country', '')} | "
            f"{ld['status']} | {date}",
        )
    await message.answer("\n".join(lines))


@router.message(Command("lead"))
async def cmd_lead(message: Message) -> None:
    if not _is_admin(message.from_user.id):  # type: ignore[union-attr]
        return
    args = (message.text or "").split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("Использование: <code>/lead 123</code>")
        return
    try:
        lead = await get_lead(int(args[1]))
    except Exception:
        await message.answer("⚠️ База данных недоступна.")
        return
    if not lead:
        await message.answer("❌ Лид не найден.")
        return
    uname = f" (@{lead['username']})" if lead.get("username") else ""
    comment = f"\n💬 {lead['comment']}" if lead.get("comment") else ""
    await message.answer(
        f"📋 <b>Лид #{lead['id']}</b>\n\n"
        f"👤 {lead['full_name']}{uname}\n"
        f"📱 {lead['phone']}\n"
        f"🏷 {lead.get('service_type', 'delivery')}\n"
        f"🌍 {lead.get('country', '')} → {lead.get('city_from', '')}\n"
        f"📦 {lead.get('cargo_type', '')}\n"
        f"⚖️ {lead.get('weight_kg', 0)} кг | 📐 {lead.get('volume_m3', 0)} м³\n"
        f"📊 <b>{lead['status']}</b>\n"
        f"📅 {lead['created_at'].strftime('%d.%m.%Y %H:%M')}"
        f"{comment}",
    )


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    if not _is_admin(message.from_user.id):  # type: ignore[union-attr]
        return
    args = (message.text or "").split()
    if len(args) < 3:
        await message.answer(
            "<code>/status 123 IN_PROGRESS</code>\n"
            "Статусы: NEW, IN_PROGRESS, WON, LOST",
        )
        return
    if not args[1].isdigit():
        await message.answer("ID должен быть числом.")
        return
    lead_id = int(args[1])
    status = args[2].upper()
    if status not in VALID_STATUSES:
        await message.answer(f"Допустимые: {', '.join(sorted(VALID_STATUSES))}")
        return
    try:
        ok = await update_lead_status(lead_id, status)
    except Exception:
        await message.answer("⚠️ База данных недоступна.")
        return
    if ok:
        await message.answer(f"{STATUS_EMOJI.get(status, '')} #{lead_id} → <b>{status}</b>")
    else:
        await message.answer(f"❌ #{lead_id} не найден.")


@router.message(Command("test"))
async def cmd_test(message: Message, bot: Bot) -> None:
    results: list[str] = []
    for chat_id in settings.admin_ids:
        try:
            await bot.send_message(
                chat_id,
                f"🔔 Тест TE GROUP бота\n"
                f"От: {message.from_user.full_name if message.from_user else '?'}\n"
                f"Статус: работает ✅",
                parse_mode=None,
            )
            results.append(f"✅ {chat_id}")
        except Exception as exc:
            results.append(f"❌ {chat_id} — {exc}")

    await message.answer(
        "<b>Тест уведомлений:</b>\n\n"
        + "\n".join(results)
        + f"\n\n<i>ADMIN_CHAT_ID: <code>{settings.ADMIN_CHAT_ID}</code></i>",
    )


@router.message(Command("export"))
async def cmd_export(message: Message) -> None:
    if not _is_admin(message.from_user.id):  # type: ignore[union-attr]
        return
    try:
        leads = await export_all_leads()
    except Exception:
        await message.answer("⚠️ База данных недоступна.")
        return
    if not leads:
        await message.answer("📭 Нет данных.")
        return
    fieldnames = [
        "id", "telegram_id", "username", "full_name",
        "service_type", "country", "city_from", "cargo_type",
        "weight_kg", "volume_m3", "urgency", "incoterms",
        "phone", "comment", "status", "created_at",
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for ld in leads:
        writer.writerow(ld)
    doc = BufferedInputFile(buf.getvalue().encode("utf-8-sig"), filename="leads.csv")
    await message.answer_document(doc, caption=f"📊 {len(leads)} лидов")
