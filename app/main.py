"""WhereIsMyHome — entry point.

Starts IP checker + all enabled notification bots concurrently via asyncio.
Handles graceful shutdown on SIGTERM / SIGINT.

Usage:
    python -m app.main           # normal operation
    python -m app.main --test    # send a test notification on every enabled
                                 # channel, then exit
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys

from app.config import load_config, AppConfig
from app.storage import IPStorage
from app.ip_checker import IPChecker

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("whereismyhome")

# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


async def main() -> None:
    logger.info("=== WhereIsMyHome IP Tracker starting ===")

    # ---- config & storage ------------------------------------------------
    config: AppConfig = load_config()
    storage = IPStorage(config.db_path)

    # ---- IP checker ------------------------------------------------------
    checker = IPChecker(storage=storage, interval=config.check_interval)

    # Convenience lambdas handed to bots so they can query status
    get_uptime = lambda: checker.uptime_seconds
    get_last_check = lambda: checker.last_check

    # ---- notifiers -------------------------------------------------------
    discord_bot = None
    telegram_notifier = None
    email_notifier = None

    # Discord
    if config.discord.enabled:
        from app.notifiers.discord_bot import start_discord_bot

        discord_bot = await start_discord_bot(
            config.discord, storage, get_uptime, get_last_check
        )
        checker.register_callback(discord_bot.notify_ip_change)
        logger.info("Discord notifier enabled.")

    # Email
    if config.email.enabled:
        from app.notifiers.email_notifier import EmailNotifier

        email_notifier = EmailNotifier(config.email, storage)
        checker.register_callback(email_notifier.notify_ip_change)
        logger.info("Email notifier enabled.")

    # Telegram
    if config.telegram.enabled:
        from app.notifiers.telegram_bot import TelegramNotifier

        telegram_notifier = TelegramNotifier(
            config.telegram, storage, get_uptime, get_last_check
        )
        await telegram_notifier.start()
        checker.register_callback(telegram_notifier.notify_ip_change)
        logger.info("Telegram notifier enabled.")

    # ---- test mode -------------------------------------------------------
    parser = argparse.ArgumentParser(description="WhereIsMyHome IP Tracker")
    parser.add_argument(
        "--test",
        action="store_true",
        help="Send a test notification on every enabled channel, then exit.",
    )
    args = parser.parse_args()

    if args.test:
        logger.info("🧪 TEST MODE — sending test notifications…")
        real_ip = await checker.simulate_ip_change()
        logger.info("🧪 Test complete (real IP: %s). Shutting down.", real_ip)
        # Tear down
        if telegram_notifier:
            await telegram_notifier.stop()
        if discord_bot:
            await discord_bot.close()
        storage.close()
        return

    # ---- graceful shutdown -----------------------------------------------
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def _signal_handler() -> None:
        logger.info("Shutdown signal received.")
        checker.stop()
        shutdown_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _signal_handler)

    # ---- run -------------------------------------------------------------
    checker_task = asyncio.create_task(checker.run_loop())

    # Wait for shutdown
    await shutdown_event.wait()
    logger.info("Shutting down…")

    checker_task.cancel()
    try:
        await checker_task
    except asyncio.CancelledError:
        pass

    # Tear down notifiers
    if telegram_notifier:
        await telegram_notifier.stop()
    if discord_bot:
        await discord_bot.close()

    storage.close()
    logger.info("=== WhereIsMyHome stopped cleanly ===")


if __name__ == "__main__":
    asyncio.run(main())
