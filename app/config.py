"""Configuration loader — reads and validates environment variables."""

from __future__ import annotations

import os
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bool_env(key: str, default: bool = False) -> bool:
    """Parse a boolean env var (true/1/yes → True)."""
    val = os.getenv(key, str(default)).strip().lower()
    return val in ("true", "1", "yes")


def _int_env(key: str, default: int = 0) -> int:
    val = os.getenv(key, str(default)).strip()
    try:
        return int(val)
    except ValueError:
        logger.warning("Invalid integer for %s=%r, using default %d", key, val, default)
        return default

# ---------------------------------------------------------------------------
# Config dataclasses
# ---------------------------------------------------------------------------

@dataclass
class DiscordConfig:
    enabled: bool = False
    bot_token: str = ""
    user_id: int = 0
    channel_id: int = 0  # optional

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.enabled:
            return errors
        if not self.bot_token:
            errors.append("DISCORD_BOT_TOKEN is required when Discord is enabled")
        if not self.user_id:
            errors.append("DISCORD_USER_ID is required when Discord is enabled")
        return errors


@dataclass
class EmailConfig:
    enabled: bool = False
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    notify_emails: list[str] = field(default_factory=list)

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.enabled:
            return errors
        for name, val in [
            ("SMTP_HOST", self.smtp_host),
            ("SMTP_USER", self.smtp_user),
            ("SMTP_PASS", self.smtp_pass),
        ]:
            if not val:
                errors.append(f"{name} is required when Email is enabled")
        if not self.notify_emails:
            errors.append("NOTIFY_EMAIL is required when Email is enabled (comma-separated for multiple)")
        return errors


@dataclass
class TelegramConfig:
    enabled: bool = False
    bot_token: str = ""
    chat_id: int = 0

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.enabled:
            return errors
        if not self.bot_token:
            errors.append("TELEGRAM_BOT_TOKEN is required when Telegram is enabled")
        if not self.chat_id:
            errors.append("TELEGRAM_CHAT_ID is required when Telegram is enabled")
        return errors


@dataclass
class AppConfig:
    check_interval: int = 300  # seconds
    history_limit: int = 20
    data_dir: Path = field(default_factory=lambda: Path("/app/data"))

    discord: DiscordConfig = field(default_factory=DiscordConfig)
    email: EmailConfig = field(default_factory=EmailConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "ip_history.db"

    def validate(self) -> None:
        """Raise on fatal mis-configuration."""
        errors: list[str] = []
        errors.extend(self.discord.validate())
        errors.extend(self.email.validate())
        errors.extend(self.telegram.validate())

        if not any([self.discord.enabled, self.email.enabled, self.telegram.enabled]):
            logger.warning(
                "No notification channels are enabled. "
                "The tracker will still run but won't notify anyone."
            )

        if errors:
            for e in errors:
                logger.error("Config error: %s", e)
            raise SystemExit("Configuration errors — see log above.")

# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def load_config() -> AppConfig:
    """Build an AppConfig from environment variables."""
    data_dir = Path(os.getenv("DATA_DIR", "/app/data"))
    data_dir.mkdir(parents=True, exist_ok=True)

    cfg = AppConfig(
        check_interval=_int_env("CHECK_INTERVAL_SECONDS", 300),
        history_limit=_int_env("HISTORY_LIMIT", 20),
        data_dir=data_dir,
        discord=DiscordConfig(
            enabled=_bool_env("DISCORD_ENABLED"),
            bot_token=os.getenv("DISCORD_BOT_TOKEN", "").strip(),
            user_id=_int_env("DISCORD_USER_ID"),
            channel_id=_int_env("DISCORD_CHANNEL_ID"),
        ),
        email=EmailConfig(
            enabled=_bool_env("EMAIL_ENABLED"),
            smtp_host=os.getenv("SMTP_HOST", "smtp.gmail.com").strip(),
            smtp_port=_int_env("SMTP_PORT", 587),
            smtp_user=os.getenv("SMTP_USER", "").strip(),
            smtp_pass=os.getenv("SMTP_PASS", "").strip(),
            notify_emails=[
                e.strip() for e in os.getenv("NOTIFY_EMAIL", "").split(",")
                if e.strip()
            ],
        ),
        telegram=TelegramConfig(
            enabled=_bool_env("TELEGRAM_ENABLED"),
            bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
            chat_id=_int_env("TELEGRAM_CHAT_ID"),
        ),
    )
    cfg.validate()
    logger.info(
        "Config loaded — interval=%ds  discord=%s  email=%s  telegram=%s",
        cfg.check_interval,
        cfg.discord.enabled,
        cfg.email.enabled,
        cfg.telegram.enabled,
    )
    return cfg
