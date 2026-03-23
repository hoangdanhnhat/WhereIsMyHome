"""Telegram bot notifier — commands + message on IP change."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from telegram import Update, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    filters,
)

from app.config import TelegramConfig
from app.storage import IPStorage

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Telegram bot: responds to /ip, /history, /status and pushes IP changes."""

    def __init__(
        self,
        config: TelegramConfig,
        storage: IPStorage,
        get_uptime: callable,
        get_last_check: callable,
    ) -> None:
        self.cfg = config
        self.storage = storage
        self._get_uptime = get_uptime
        self._get_last_check = get_last_check
        self._app: Application | None = None
        self._bot: Bot | None = None

    # ---- chat filter -----------------------------------------------------

    def _authorised(self, update: Update) -> bool:
        """Only respond to the configured chat ID."""
        return update.effective_chat and update.effective_chat.id == self.cfg.chat_id

    # ---- command handlers ------------------------------------------------

    async def _cmd_ip(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorised(update):
            return
        ip = self.storage.get_current_ip() or "Unknown (no check yet)"
        await update.message.reply_text(f"🌐 Current Public IP: {ip}")

    async def _cmd_history(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorised(update):
            return
        records = self.storage.get_history(limit=20)
        if not records:
            await update.message.reply_text("📭 No IP history yet.")
            return
        lines = [f"`{r.timestamp}`  →  `{r.ip}`" for r in records]
        msg = "📋 *IP Change History* (newest first):\n" + "\n".join(lines)
        if len(msg) > 4096:
            msg = msg[:4093] + "…"
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def _cmd_status(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorised(update):
            return
        ip = self.storage.get_current_ip() or "Unknown"
        uptime = self._get_uptime()
        last_check = self._get_last_check()

        hours, rem = divmod(int(uptime), 3600)
        minutes, seconds = divmod(rem, 60)
        uptime_str = f"{hours}h {minutes}m {seconds}s"
        last_str = last_check.isoformat() if last_check else "Never"
        total = self.storage.get_record_count()

        msg = (
            f"📊 *IP Tracker Status*\n\n"
            f"*Current IP:* `{ip}`\n"
            f"*Uptime:* {uptime_str}\n"
            f"*Last Check:* {last_str}\n"
            f"*Total Records:* {total}"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def _cmd_test(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorised(update):
            return
        try:
            await self.notify_ip_change("198.51.100.1", "192.0.2.1")
            await update.message.reply_text("✅ Test notification sent! Check above.")
        except Exception as exc:
            await update.message.reply_text(f"❌ Test failed: {exc}")

    # ---- lifecycle -------------------------------------------------------

    async def start(self) -> None:
        """Build and start the Telegram bot (non-blocking)."""
        self._app = (
            Application.builder()
            .token(self.cfg.bot_token)
            .build()
        )

        self._app.add_handler(CommandHandler("ip", self._cmd_ip))
        self._app.add_handler(CommandHandler("history", self._cmd_history))
        self._app.add_handler(CommandHandler("status", self._cmd_status))
        self._app.add_handler(CommandHandler("test", self._cmd_test))

        # Initialize and start polling in background
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)

        self._bot = self._app.bot
        logger.info("Telegram bot started (chat_id=%s)", self.cfg.chat_id)

    async def stop(self) -> None:
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            logger.info("Telegram bot stopped.")

    # ---- notification ----------------------------------------------------

    async def notify_ip_change(self, new_ip: str, old_ip: str | None) -> None:
        """Send a Telegram message to the configured chat on IP change."""
        if not self._bot:
            logger.warning("Telegram bot not ready; skipping notification.")
            return

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        msg = (
            f"🔔 *IP Address Changed!*\n\n"
            f"*Old:* `{old_ip or 'N/A'}`\n"
            f"*New:* `{new_ip}`\n"
            f"*Time:* {timestamp}"
        )
        try:
            await self._bot.send_message(
                chat_id=self.cfg.chat_id,
                text=msg,
                parse_mode="Markdown",
            )
            logger.info("Telegram notification sent to chat %s", self.cfg.chat_id)
        except Exception as exc:
            logger.error("Failed to send Telegram message: %s", exc)
