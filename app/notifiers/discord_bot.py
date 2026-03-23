"""Discord bot notifier — slash commands + DM on IP change."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import discord
from discord import app_commands

from app.config import DiscordConfig
from app.storage import IPStorage

logger = logging.getLogger(__name__)


class IPTrackerBot(discord.Client):
    """A minimal Discord bot with slash commands for IP tracking."""

    def __init__(
        self,
        config: DiscordConfig,
        storage: IPStorage,
        get_uptime: callable,
        get_last_check: callable,
    ) -> None:
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.cfg = config
        self.storage = storage
        self._get_uptime = get_uptime
        self._get_last_check = get_last_check
        self.tree = app_commands.CommandTree(self)
        self._setup_commands()

    # ---- commands --------------------------------------------------------

    def _setup_commands(self) -> None:
        @self.tree.command(name="ip", description="Show your current public IP")
        async def cmd_ip(interaction: discord.Interaction) -> None:
            ip = self.storage.get_current_ip() or "Unknown (no check yet)"
            await interaction.response.send_message(
                f"🌐 **Current Public IP:** `{ip}`",
                ephemeral=True,
            )

        @self.tree.command(name="history", description="Show recent IP changes")
        async def cmd_history(interaction: discord.Interaction) -> None:
            records = self.storage.get_history(limit=20)
            if not records:
                await interaction.response.send_message(
                    "📭 No IP history yet.", ephemeral=True
                )
                return
            lines = [f"`{r.timestamp}`  →  `{r.ip}`" for r in records]
            msg = "📋 **IP Change History** (newest first):\n" + "\n".join(lines)
            # Discord limit is 2000 chars
            if len(msg) > 2000:
                msg = msg[:1997] + "…"
            await interaction.response.send_message(msg, ephemeral=True)

        @self.tree.command(name="status", description="Show tracker status")
        async def cmd_status(interaction: discord.Interaction) -> None:
            ip = self.storage.get_current_ip() or "Unknown"
            uptime = self._get_uptime()
            last_check = self._get_last_check()

            hours, rem = divmod(int(uptime), 3600)
            minutes, seconds = divmod(rem, 60)
            uptime_str = f"{hours}h {minutes}m {seconds}s"

            last_str = last_check.isoformat() if last_check else "Never"
            total = self.storage.get_record_count()

            embed = discord.Embed(
                title="📊 IP Tracker Status",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc),
            )
            embed.add_field(name="Current IP", value=f"`{ip}`", inline=False)
            embed.add_field(name="Uptime", value=uptime_str, inline=True)
            embed.add_field(name="Last Check", value=last_str, inline=True)
            embed.add_field(name="Total Records", value=str(total), inline=True)
            await interaction.response.send_message(embed=embed, ephemeral=True)

        @self.tree.command(name="test", description="Send a test notification to verify alerts work")
        async def cmd_test(interaction: discord.Interaction) -> None:
            await interaction.response.defer(ephemeral=True)
            try:
                await self.notify_ip_change("198.51.100.1", "192.0.2.1")
                await interaction.followup.send(
                    "✅ Test notification sent! Check your DMs.",
                    ephemeral=True,
                )
            except Exception as exc:
                await interaction.followup.send(
                    f"❌ Test failed: {exc}",
                    ephemeral=True,
                )

    # ---- lifecycle -------------------------------------------------------

    async def on_ready(self) -> None:
        logger.info("Discord bot logged in as %s (ID: %s)", self.user, self.user.id)
        await self.tree.sync()
        logger.info("Slash commands synced.")

    # ---- notification ----------------------------------------------------

    async def notify_ip_change(self, new_ip: str, old_ip: str | None) -> None:
        """DM the configured user. Optionally post to a private channel."""
        msg = (
            f"🔔 **IP Address Changed!**\n"
            f"Old: `{old_ip or 'N/A'}`\n"
            f"New: `{new_ip}`\n"
            f"Time: `{datetime.now(timezone.utc).isoformat()}`"
        )

        # DM the user
        try:
            user = await self.fetch_user(self.cfg.user_id)
            await user.send(msg)
            logger.info("Discord DM sent to user %s", self.cfg.user_id)
        except Exception as exc:
            logger.error("Failed to DM Discord user %s: %s", self.cfg.user_id, exc)

        # Optional channel post
        if self.cfg.channel_id:
            try:
                channel = self.get_channel(self.cfg.channel_id)
                if channel is None:
                    channel = await self.fetch_channel(self.cfg.channel_id)
                await channel.send(msg)
                logger.info("Discord channel message sent to %s", self.cfg.channel_id)
            except Exception as exc:
                logger.error(
                    "Failed to post to Discord channel %s: %s",
                    self.cfg.channel_id,
                    exc,
                )


async def start_discord_bot(
    config: DiscordConfig,
    storage: IPStorage,
    get_uptime: callable,
    get_last_check: callable,
) -> IPTrackerBot:
    """Create, start, and return the Discord bot instance.

    The bot runs in the background via its internal event loop integration.
    """
    bot = IPTrackerBot(config, storage, get_uptime, get_last_check)
    asyncio.create_task(bot.start(config.bot_token))
    # Give the bot a moment to connect
    await asyncio.sleep(3)
    return bot
