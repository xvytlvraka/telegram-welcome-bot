import os
import asyncio
import logging

from aiohttp import web

from aiogram import Bot, Dispatcher, F
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
# CONFIG
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# Channel where all your channel/group links are available
LINKS_CHANNEL = os.getenv(
    "LINKS_CHANNEL",
    "https://t.me/your_links_channel"
).strip()

# Optional monitored chat IDs.
#
# Example:
# -1001234567890,-1009876543210
#
# Leave empty = monitor every chat where bot is admin.
MONITORED_CHATS_RAW = os.getenv("MONITORED_CHATS", "").strip()


if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")


if MONITORED_CHATS_RAW:
    MONITORED_CHATS = set()

    for item in MONITORED_CHATS_RAW.split(","):
        item = item.strip()

        if item:
            try:
                MONITORED_CHATS.add(int(item))
            except ValueError:
                pass
else:
    MONITORED_CHATS = set()


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)


# ============================================================
# BOT / DISPATCHER
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

def chat_is_monitored(chat_id: int) -> bool:
    """
    If MONITORED_CHATS is empty:
        monitor every chat where the bot receives updates.

    If MONITORED_CHATS contains IDs:
        monitor only those chats.
    """

    if not MONITORED_CHATS:
        return True

    return chat_id in MONITORED_CHATS


def user_name(user) -> str:
    """
    Safely get user's display name.
    """

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


def rejoin_keyboard(link: str) -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="↩️ ʀᴇᴊᴏɪɴ",
                    url=link
                )
            ]
        ]
    )


# ============================================================
# START
# ============================================================

@dp.message(Command("start"))
async def start_handler(message: Message):

    name = user_name(message.from_user)

    text = (
        f"✨ <b>Hey {name}!</b>\n\n"
        "Welcome! You're all set. 🖤\n\n"
        "Stay connected and explore our network below.\n"
        "Everything you need is just one tap away.\n\n"
        "━━━━━━━━━━━━━━\n"
        "⚡ <i>Stay connected. Stay updated.</i>"
    )

    await message.answer(
        text,
        reply_markup=welcome_keyboard()
    )


# ============================================================
# USER ID
# ============================================================

@dp.message(Command("id"))
async def id_handler(message: Message):

    await message.answer(
        f"<b>Your Telegram ID:</b>\n<code>{message.from_user.id}</code>\n\n"
        f"<b>Chat ID:</b>\n<code>{message.chat.id}</code>"
    )


# ============================================================
# JOIN REQUEST
# ============================================================

@dp.chat_join_request()
async def join_request_handler(request: ChatJoinRequest):

    chat = request.chat
    user = request.from_user

    chat_id = chat.id

    if not chat_is_monitored(chat_id):
        return

    logger.info(
        "Join request | user=%s | chat=%s (%s)",
        user.id,
        chat.title,
        chat_id
    )

    # --------------------------------------------------------
    # AUTO APPROVE
    # --------------------------------------------------------

    try:

        await bot.approve_chat_join_request(
            chat_id=chat_id,
            user_id=user.id
        )

        logger.info(
            "Approved | user=%s | chat=%s",
            user.id,
            chat.title
        )

    except Exception as e:

        logger.exception(
            "Failed to approve join request: %s",
            e
        )

        return


    # --------------------------------------------------------
    # PERSONAL WELCOME DM
    # --------------------------------------------------------

    name = user_name(user)

    welcome_text = (
        f"✨ <b>Welcome, {name}!</b>\n\n"
        "Thanks for joining us. 🖤\n\n"
        "You're officially connected now.\n"
        "Stay tuned for fresh updates, useful content "
        "and more from our network.\n\n"
        "━━━━━━━━━━━━━━\n"
        "🔗 <i>Explore the complete channel network below.</i>"
    )

    try:

        await bot.send_message(
            chat_id=user.id,
            text=welcome_text,
            reply_markup=welcome_keyboard()
        )

        logger.info(
            "Welcome sent | user=%s",
            user.id
        )

    except Exception as e:

        # User may have blocked the bot
        logger.warning(
            "Could not send welcome DM to %s: %s",
            user.id,
            e
        )


# ============================================================
# MEMBER STATUS CHANGE
# ============================================================

@dp.chat_member()
async def member_update_handler(update: ChatMemberUpdated):

    chat = update.chat

    if not chat_is_monitored(chat.id):
        return

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

    # ========================================================
    # USER LEFT
    # ========================================================

    was_member = old_status in {
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.CREATOR,
        ChatMemberStatus.RESTRICTED,
    }

    is_left = new_status in {
        ChatMemberStatus.LEFT,
        ChatMemberStatus.KICKED,
    }

    if was_member and is_left:

        name = user_name(user)

        chat_title = chat.title or "this chat"

        # ----------------------------------------------------
        # GET REJOIN LINK
        # ----------------------------------------------------

        rejoin_link = None

        try:

            # For public chats this may return a t.me link.
            # For private chats it uses the bot's invite link.
            rejoin_link = await bot.export_chat_invite_link(
                chat_id=chat.id
            )

        except Exception as e:

            logger.warning(
                "Could not create invite link for %s: %s",
                chat.id,
                e
            )

        # ----------------------------------------------------
        # FALLBACK FOR PUBLIC CHAT
        # ----------------------------------------------------

        if not rejoin_link:

            if chat.username:

                rejoin_link = f"https://t.me/{chat.username}"

        # ----------------------------------------------------
        # MESSAGE
        # ----------------------------------------------------

        leave_text = (
            f"👋 <b>Hey {name}</b>\n\n"
            f"We noticed that you left <b>{chat_title}</b>.\n\n"
            "No worries — you're always welcome back. ✨\n\n"
            "If you left by mistake or want to reconnect, "
            "use the button below.\n\n"
            "━━━━━━━━━━━━━━\n"
            "🖤 <i>We'd love to have you back.</i>"
        )

        # ----------------------------------------------------
        # SEND DM
        # ----------------------------------------------------

        try:

            if rejoin_link:

                await bot.send_message(
                    chat_id=user.id,
                    text=leave_text,
                    reply_markup=rejoin_keyboard(
                        rejoin_link
                    )
                )

            else:

                await bot.send_message(
                    chat_id=user.id,
                    text=leave_text
                )

            logger.info(
                "Leave message sent | user=%s | chat=%s",
                user.id,
                chat.id
            )

        except Exception as e:

            logger.warning(
                "Could not send leave DM to %s: %s",
                user.id,
                e
            )


# ============================================================
# ADMIN STATUS
# ============================================================

@dp.message(Command("status"))
async def status_handler(message: Message):

    if message.from_user.id != ADMIN_ID:

        await message.answer(
            "⛔ <b>Only admin can access this command.</b>"
        )

        return

    me = await bot.get_me()

    monitored_text = (
        "ALL CHATS"
        if not MONITORED_CHATS
        else "\n".join(
            str(x)
            for x in MONITORED_CHATS
        )
    )

    text = (
        "🤖 <b>BOT STATUS</b>\n\n"
        f"Username: @{me.username}\n"
        f"Bot ID: <code>{me.id}</code>\n\n"
        f"<b>Monitored:</b>\n"
        f"<code>{monitored_text}</code>\n\n"
        "✅ Join approval: ON\n"
        "✅ Welcome DM: ON\n"
        "✅ Leave detection: ON\n"
        "✅ Rejoin button: ON\n"
    )

    await message.answer(text)


# ============================================================
# ADMIN TEST
# ============================================================

@dp.message(Command("test"))
async def test_handler(message: Message):

    if message.from_user.id != ADMIN_ID:

        await message.answer(
            "⛔ <b>Only admin can access this command.</b>"
        )

        return

    name = user_name(message.from_user)

    text = (
        f"🧪 <b>Test successful, {name}!</b>\n\n"
        "Welcome system is working.\n"
        "Inline button is also enabled."
    )

    await message.answer(
        text,
        reply_markup=welcome_keyboard()
    )


# ============================================================
# HEALTH SERVER FOR RENDER
# ============================================================

async def health_handler(request):

    return web.Response(
        text="OK",
        status=200
    )


async def start_web_server():

    app = web.Application()

    app.router.add_get(
        "/",
        health_handler
    )

    app.router.add_get(
        "/health",
        health_handler
    )

    runner = web.AppRunner(app)

    await runner.setup()

    port = int(
        os.getenv(
            "PORT",
            "10000"
        )
    )

    site = web.TCPSite(
        runner,
        "0.0.0.0",
        port
    )

    await site.start()

    logger.info(
        "Health server running on port %s",
        port
    )


# ============================================================
# MAIN
# ============================================================

async def main():

    logger.info(
        "Starting Telegram bot..."
    )

    me = await bot.get_me()

    logger.info(
        "Logged in as @%s",
        me.username
    )

    # --------------------------------------------------------
    # Start Render health server
    # --------------------------------------------------------

    await start_web_server()

    # --------------------------------------------------------
    # Delete old webhook
    # --------------------------------------------------------

    await bot.delete_webhook(
        drop_pending_updates=False
    )

    # --------------------------------------------------------
    # Start polling
    #
    # chat_member is required for leave detection.
    # chat_join_request is required for auto approval.
    # --------------------------------------------------------

    await dp.start_polling(
        bot,
        allowed_updates=[
            "message",
            "chat_join_request",
            "chat_member",
        ]
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    try:

        asyncio.run(main())

    except KeyboardInterrupt:

        logger.info(
            "Bot stopped."
)
