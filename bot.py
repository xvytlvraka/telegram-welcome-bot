import os
import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timezone

from aiohttp import web
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher
from aiogram.enums import ChatMemberStatus, ParseMode
from aiogram.filters import Command
from aiogram.types import (
    Message, ChatJoinRequest, ChatMemberUpdated,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.client.default import DefaultBotProperties

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID_RAW = os.getenv("ADMIN_ID", "").strip()
LINKS_CHANNEL = os.getenv("LINKS_CHANNEL", "https://t.me/your_links_channel").strip()
SUPPORT_URL = os.getenv("SUPPORT_URL", "https://t.me/your_support_username").strip()
PORT = int(os.getenv("PORT", "10000"))
DATA_FILE = Path(os.getenv("DATA_FILE", "data.json"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing in .env / Render Environment")
if not ADMIN_ID_RAW:
    raise RuntimeError("ADMIN_ID is missing in .env / Render Environment")
try:
    ADMIN_ID = int(ADMIN_ID_RAW)
except ValueError as exc:
    raise RuntimeError("ADMIN_ID must be a numeric Telegram user ID") from exc

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
data_lock = asyncio.Lock()


def fresh_data():
    return {
        "stats": {"approved_total": 0, "leave_events": 0, "rejoin_events": 0},
        "members": {},
        "updated_at": None,
    }


def load_data():
    if not DATA_FILE.exists():
        return fresh_data()
    try:
        raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        base = fresh_data()
        base.update(raw if isinstance(raw, dict) else {})
        base.setdefault("stats", fresh_data()["stats"])
        base.setdefault("members", {})
        for key in fresh_data()["stats"]:
            base["stats"].setdefault(key, 0)
        return base
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read %s: %s; starting with empty stats", DATA_FILE, exc)
        return fresh_data()


DATA = load_data()


async def save_data():
    DATA["updated_at"] = datetime.now(timezone.utc).isoformat()
    tmp = DATA_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(DATA, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(DATA_FILE)


def get_user_name(user) -> str:
    return user.first_name or (f"@{user.username}" if user.username else "there")


def safe_html(value: str) -> str:
    return (value or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def welcome_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 View All Channels", url=LINKS_CHANNEL)],
        [InlineKeyboardButton(text="💬 Support / Contact", url=SUPPORT_URL)],
    ])


def rejoin_keyboard(invite_link: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Rejoin Community", url=invite_link)],
        [InlineKeyboardButton(text="🔗 View All Channels", url=LINKS_CHANNEL)],
    ])


def member_key(chat_id: int, user_id: int) -> str:
    return f"{chat_id}:{user_id}"


async def is_admin(message: Message) -> bool:
    if not message.from_user or message.from_user.id != ADMIN_ID:
        await message.answer("⛔ <b>Admin-only command.</b>\nThis command is available only to the bot administrator.")
        return False
    return True


@dp.message(Command("start"))
async def start_handler(message: Message):
    name = safe_html(get_user_name(message.from_user))
    text = (
        f"✨ <b>Hey {name}!</b>\n\n"
        "Welcome! We're glad to have you here. 🖤\n\n"
        "Use the buttons below to explore our channel network or contact support. "
        "You can find updates, announcements, and more in our official links channel.\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "⚡ <i>Stay connected. Stay informed. Be part of the community.</i>"
    )
    await message.answer(text, reply_markup=welcome_keyboard())


@dp.message(Command("id"))
async def id_handler(message: Message):
    await message.answer(
        "🆔 <b>Your Telegram ID</b>\n"
        f"<code>{message.from_user.id}</code>\n\n"
        "💬 <b>Current Chat ID</b>\n"
        f"<code>{message.chat.id}</code>"
    )


@dp.chat_join_request()
async def join_request_handler(request: ChatJoinRequest):
    chat, user = request.chat, request.from_user
    key = member_key(chat.id, user.id)
    logger.info("Join request | user=%s | chat=%s (%s)", user.id, chat.title, chat.id)

    try:
        async with data_lock:
            record = DATA["members"].get(key, {})
            was_previously_member = bool(record.get("left", False))
            await bot.approve_chat_join_request(chat_id=chat.id, user_id=user.id)
            DATA["stats"]["approved_total"] += 1
            if was_previously_member:
                DATA["stats"]["rejoin_events"] += 1
            DATA["members"][key] = {
                "user_id": user.id,
                "chat_id": chat.id,
                "chat_title": chat.title or "Community",
                "left": False,
                "last_approved_at": datetime.now(timezone.utc).isoformat(),
                "last_left_at": record.get("last_left_at"),
            }
            await save_data()
    except Exception:
        logger.exception("Failed to approve join request | chat=%s | user=%s", chat.id, user.id)
        return

    name = safe_html(get_user_name(user))
    chat_name = safe_html(chat.title or "our community")
    welcome_text = (
        f"🎉 <b>Welcome aboard, {name}!</b>\n\n"
        f"Your join request for <b>{chat_name}</b> has been approved successfully. "
        "We're happy to have you as part of the community. 🖤\n\n"
        "Please keep an eye on the channel for new posts, announcements, and useful updates. "
        "If you ever need help, you can use the support button below. To discover our other communities, "
        "open the channel directory.\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "✨ <i>Thanks for joining us — stay connected and enjoy the community!</i>"
    )
    try:
        await bot.send_message(user.id, welcome_text, reply_markup=welcome_keyboard())
        logger.info("Welcome DM sent | user=%s", user.id)
    except Exception as exc:
        logger.warning("Welcome DM failed | user=%s | %s", user.id, exc)


@dp.chat_member()
async def member_update_handler(update: ChatMemberUpdated):
    chat = update.chat
    old_status = update.old_chat_member.status
    new_status = update.new_chat_member.status
    user = update.new_chat_member.user

    previous_member_statuses = {
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.CREATOR,
        ChatMemberStatus.RESTRICTED,
    }
    left_statuses = {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}
    was_member = old_status in previous_member_statuses
    has_left = new_status in left_statuses
    if not (was_member and has_left):
        return

    key = member_key(chat.id, user.id)
    chat_name = safe_html(chat.title or "this community")
    name = safe_html(get_user_name(user))

    async with data_lock:
        record = DATA["members"].get(key, {
            "user_id": user.id, "chat_id": chat.id,
            "chat_title": chat.title or "Community",
            "left": False,
        })
        # Avoid counting duplicate leave updates while the user is already marked as left.
        if not record.get("left", False):
            DATA["stats"]["leave_events"] += 1
        record["left"] = True
        record["last_left_at"] = datetime.now(timezone.utc).isoformat()
        record["chat_title"] = chat.title or "Community"
        DATA["members"][key] = record
        await save_data()

    invite_link = None
    try:
        # Bot must have permission to invite users/manage invite links in this chat.
        invite_link = await bot.export_chat_invite_link(chat.id)
    except Exception as exc:
        logger.warning("Could not create invite link | chat=%s | %s", chat.id, exc)

    if not invite_link and chat.username:
        invite_link = f"https://t.me/{chat.username}"

    leave_text = (
        f"👋 <b>Hey {name},</b>\n\n"
        f"We noticed that you have left <b>{chat_name}</b>. We understand that everyone has their own "
        "preferences and reasons, and there's absolutely no pressure.\n\n"
        "However, if you left by mistake or would like to stay connected with the community, "
        "you are always welcome to return. You'll continue to find updates, announcements, and community "
        "content whenever you rejoin.\n\n"
        "If you have feedback or faced any issue, feel free to contact support. We'd appreciate the chance "
        "to help and make your experience better.\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🖤 <i>The door is always open. We hope to see you again!</i>"
    )
    try:
        if invite_link:
            await bot.send_message(user.id, leave_text, reply_markup=rejoin_keyboard(invite_link))
        else:
            await bot.send_message(user.id, leave_text, reply_markup=welcome_keyboard())
        logger.info("Leave DM sent | user=%s | chat=%s", user.id, chat.id)
    except Exception as exc:
        logger.warning("Leave DM failed | user=%s | %s", user.id, exc)


@dp.message(Command("stats"))
async def stats_handler(message: Message):
    if not await is_admin(message):
        return
    async with data_lock:
        stats = dict(DATA["stats"])
        tracked = len(DATA["members"])
        currently_in = sum(1 for r in DATA["members"].values() if not r.get("left", False))
        last_updated = DATA.get("updated_at") or "Not available"
    await message.answer(
        "📊 <b>BOT STATISTICS</b>\n\n"
        f"✅ Join requests approved: <b>{stats['approved_total']}</b>\n"
        f"↩️ Rejoin events: <b>{stats['rejoin_events']}</b>\n"
        f"👋 Leave events: <b>{stats['leave_events']}</b>\n"
        f"👥 Tracked chat/user records: <b>{tracked}</b>\n"
        f"🟢 Records currently marked joined: <b>{currently_in}</b>\n\n"
        f"🕒 Last stats update: <code>{safe_html(str(last_updated))}</code>\n\n"
        "<i>Note: counts begin when this version of the bot starts tracking events. "
        "A rejoin is counted when a previously tracked leaver submits a new join request and gets approved.</i>"
    )


@dp.message(Command("status"))
async def status_handler(message: Message):
    if not await is_admin(message):
        return
    me = await bot.get_me()
    await message.answer(
        "🤖 <b>BOT STATUS</b>\n\n"
        f"Username: @{safe_html(me.username or 'unknown')}\n"
        f"Bot ID: <code>{me.id}</code>\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "✅ Join Request Auto-Approval: ON\n"
        "✅ Personal Welcome Message: ON\n"
        "✅ Leave Detection & DM: ON\n"
        "✅ Rejoin Link Generation: ON (where permissions allow)\n"
        "✅ Admin Statistics: ON\n"
        "✅ Health Endpoints: / and /health\n"
    )


@dp.message(Command("test"))
async def test_handler(message: Message):
    if not await is_admin(message):
        return
    name = safe_html(get_user_name(message.from_user))
    await message.answer(
        f"🧪 <b>Test successful, {name}!</b>\n\n"
        "The bot is online and responding correctly. Both welcome buttons are configured below.",
        reply_markup=welcome_keyboard()
    )


async def health_handler(request):
    return web.Response(text="OK", status=200)


async def start_health_server():
    app = web.Application()
    app.router.add_get("/", health_handler)
    app.router.add_get("/health", health_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info("Health server running on port %s", PORT)
    return runner


async def main():
    logger.info("Starting bot...")
    me = await bot.get_me()
    logger.info("Bot connected as @%s | ID=%s", me.username, me.id)
    health_runner = await start_health_server()
    await bot.delete_webhook(drop_pending_updates=False)
    try:
        await dp.start_polling(
            bot,
            allowed_updates=["message", "chat_join_request", "chat_member"],
        )
    finally:
        await health_runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped.")
