import os
import asyncio
import logging

from aiohttp import web
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher
from aiogram.enums import ChatMemberStatus, ParseMode
from aiogram.filters import Command
from aiogram.types import (
    Message,
    ChatJoinRequest,
    ChatMemberUpdated,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.client.default import DefaultBotProperties


# ============================================================
# LOAD ENV
# ============================================================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID_RAW = os.getenv("ADMIN_ID", "").strip()
LINKS_CHANNEL = os.getenv(
    "LINKS_CHANNEL",
    "https://t.me/your_links_channel"
).strip()


if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing in .env / Render Environment")

if not ADMIN_ID_RAW:
    raise RuntimeError("ADMIN_ID is missing in .env / Render Environment")

try:
    ADMIN_ID = int(ADMIN_ID_RAW)
except ValueError:
    raise RuntimeError("ADMIN_ID must be a numeric Telegram user ID")


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)


# ============================================================
# BOT
# ============================================================

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(
        parse_mode=ParseMode.HTML
    )
)

dp = Dispatcher()


# ============================================================
# HELPERS
# ============================================================

def get_user_name(user) -> str:
    if user.first_name:
        return user.first_name

    if user.username:
        return f"@{user.username}"

    return "there"


def welcome_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔗 ᴠɪᴇᴡ ᴀʟʟ ᴄʜᴀɴɴᴇʟs",
                    url=LINKS_CHANNEL
                )
            ]
        ]
    )


def rejoin_keyboard(invite_link: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="↩️ ʀᴇᴊᴏɪɴ",
                    url=invite_link
                )
            ]
        ]
    )


# ============================================================
# /START
# ============================================================

@dp.message(Command("start"))
async def start_handler(message: Message):

    name = get_user_name(message.from_user)

    text = (
        f"✨ <b>Hey {name}!</b>\n\n"
        "Welcome! You're all set. 🖤\n\n"
        "Thanks for connecting with us.\n"
        "Explore our complete network below and stay updated.\n\n"
        "━━━━━━━━━━━━━━\n"
        "⚡ <i>Stay connected. Stay updated.</i>"
    )

    await message.answer(
        text,
        reply_markup=welcome_keyboard()
    )


# ============================================================
# /ID
# ============================================================

@dp.message(Command("id"))
async def id_handler(message: Message):

    await message.answer(
        "🆔 <b>Your Telegram ID</b>\n"
        f"<code>{message.from_user.id}</code>\n\n"
        "💬 <b>Current Chat ID</b>\n"
        f"<code>{message.chat.id}</code>"
    )


# ============================================================
# JOIN REQUEST AUTO APPROVAL
# ============================================================

@dp.chat_join_request()
async def join_request_handler(request: ChatJoinRequest):

    chat = request.chat
    user = request.from_user

    logger.info(
        "Join request received | user=%s | chat=%s | chat_id=%s",
        user.id,
        chat.title,
        chat.id
    )

    # --------------------------------------------------------
    # AUTO APPROVE
    # --------------------------------------------------------

    try:

        await bot.approve_chat_join_request(
            chat_id=chat.id,
            user_id=user.id
        )

        logger.info(
            "Join request approved | user=%s | chat=%s",
            user.id,
            chat.title
        )

    except Exception as e:

        logger.exception(
            "Failed to approve join request | chat=%s | user=%s | %s",
            chat.id,
            user.id,
            e
        )

        return

    # --------------------------------------------------------
    # PERSONAL WELCOME
    # --------------------------------------------------------

    name = get_user_name(user)

    chat_name = chat.title or "our community"

    welcome_text = (
        f"✨ <b>Welcome, {name}!</b>\n\n"
        f"Thanks for joining <b>{chat_name}</b>. 🖤\n\n"
        "You're officially connected now.\n"
        "Stay tuned for fresh updates, useful content "
        "and more from our network.\n\n"
        "━━━━━━━━━━━━━━\n"
        "🔗 <i>Explore our complete channel network below.</i>"
    )

    try:

        await bot.send_message(
            chat_id=user.id,
            text=welcome_text,
            reply_markup=welcome_keyboard()
        )

        logger.info(
            "Welcome DM sent | user=%s",
            user.id
        )

    except Exception as e:

        logger.warning(
            "Welcome DM failed | user=%s | %s",
            user.id,
            e
        )


# ============================================================
# LEAVE DETECTION
# ============================================================

@dp.chat_member()
async def member_update_handler(update: ChatMemberUpdated):

    chat = update.chat

    old_member = update.old_chat_member
    new_member = update.new_chat_member

    user = new_member.user

    old_status = old_member.status
    new_status = new_member.status

    logger.info(
        "Member update | user=%s | chat=%s | %s -> %s",
        user.id,
        chat.title,
        old_status,
        new_status
    )

    # --------------------------------------------------------
    # DETECT REAL MEMBER -> LEFT
    # --------------------------------------------------------

    previous_member_statuses = {
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.CREATOR,
        ChatMemberStatus.RESTRICTED,
    }

    left_statuses = {
        ChatMemberStatus.LEFT,
        ChatMemberStatus.KICKED,
    }

    was_member = old_status in previous_member_statuses
    has_left = new_status in left_statuses

    if not (was_member and has_left):
        return

    name = get_user_name(user)
    chat_name = chat.title or "this chat"

    logger.info(
        "User left | user=%s | chat=%s | chat_id=%s",
        user.id,
        chat_name,
        chat.id
    )

    # --------------------------------------------------------
    # AUTOMATIC REJOIN LINK
    # --------------------------------------------------------

    invite_link = None

    try:

        invite_link = await bot.export_chat_invite_link(
            chat_id=chat.id
        )

        logger.info(
            "Invite link created | chat=%s",
            chat.id
        )

    except Exception as e:

        logger.warning(
            "Could not create invite link | chat=%s | %s",
            chat.id,
            e
        )

    # --------------------------------------------------------
    # PUBLIC CHAT FALLBACK
    # --------------------------------------------------------

    if not invite_link and chat.username:

        invite_link = f"https://t.me/{chat.username}"

    # --------------------------------------------------------
    # LEAVE MESSAGE
    # --------------------------------------------------------

    leave_text = (
        f"👋 <b>Hey {name}</b>\n\n"
        f"We noticed that you left <b>{chat_name}</b>.\n\n"
        "No worries — you're always welcome back. ✨\n\n"
        "If you left by mistake or want to reconnect, "
        "tap the button below.\n\n"
        "━━━━━━━━━━━━━━\n"
        "🖤 <i>We'd love to have you back.</i>"
    )

    # --------------------------------------------------------
    # SEND PRIVATE MESSAGE
    # --------------------------------------------------------

    try:

        if invite_link:

            await bot.send_message(
                chat_id=user.id,
                text=leave_text,
                reply_markup=rejoin_keyboard(invite_link)
            )

        else:

            await bot.send_message(
                chat_id=user.id,
                text=leave_text
            )

        logger.info(
            "Leave DM sent | user=%s | chat=%s",
            user.id,
            chat.id
        )

    except Exception as e:

        logger.warning(
            "Leave DM failed | user=%s | %s",
            user.id,
            e
        )


# ============================================================
# ADMIN /STATUS
# ============================================================

@dp.message(Command("status"))
async def status_handler(message: Message):

    if message.from_user.id != ADMIN_ID:

        await message.answer(
            "⛔ <b>Only admin can access this command.</b>"
        )

        return

    me = await bot.get_me()

    text = (
        "🤖 <b>BOT STATUS</b>\n\n"
        f"Username: @{me.username}\n"
        f"Bot ID: <code>{me.id}</code>\n\n"
        "━━━━━━━━━━━━━━\n"
        "✅ Auto Join Approval: ON\n"
        "✅ Welcome DM: ON\n"
        "✅ Leave Detection: ON\n"
        "✅ Automatic Rejoin Link: ON\n"
        "✅ All Admin Chats: ON\n"
    )

    await message.answer(text)


# ============================================================
# ADMIN /TEST
# ============================================================

@dp.message(Command("test"))
async def test_handler(message: Message):

    if message.from_user.id != ADMIN_ID:

        await message.answer(
            "⛔ <b>Only admin can access this command.</b>"
        )

        return

    name = get_user_name(message.from_user)

    text = (
        f"🧪 <b>Test successful, {name}!</b>\n\n"
        "The bot is online and responding correctly.\n\n"
        "🔗 Welcome button is working."
    )

    await message.answer(
        text,
        reply_markup=welcome_keyboard()
    )


# ============================================================
# RENDER HEALTH SERVER
# ============================================================

async def health_handler(request):
    return web.Response(
        text="OK",
        status=200
    )


async def start_health_server():

    app = web.Application()

    app.router.add_get(
        "/",
        health_handler
    )

    app.router.add_get(
        "/health",
        health_handler
    )

    port = int(
        os.getenv(
            "PORT",
            "10000"
        )
    )

    runner = web.AppRunner(app)

    await runner.setup()

    site = web.TCPSite(
        runner,
        "0.0.0.0",
        port
    )

    await site.start()

    logger.info(
        "Render health server running on port %s",
        port
    )


# ============================================================
# MAIN
# ============================================================

async def main():

    logger.info("Starting bot...")

    me = await bot.get_me()

    logger.info(
        "Bot connected as @%s | ID=%s",
        me.username,
        me.id
    )

    await start_health_server()

    # Remove webhook so polling works correctly
    await bot.delete_webhook(
        drop_pending_updates=False
    )

    logger.info(
        "Starting polling..."
    )

    await dp.start_polling(
        bot,
        allowed_updates=[
            "message",
            "chat_join_request",
            "chat_member",
        ]
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    try:
        asyncio.run(main())

    except KeyboardInterrupt:

        logger.info(
            "Bot stopped."
        )
