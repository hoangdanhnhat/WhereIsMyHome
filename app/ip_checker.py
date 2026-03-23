"""Public IP checker with multiple fallback sources and change detection."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Callable, Awaitable

import httpx

from app.storage import IPStorage

logger = logging.getLogger(__name__)

IP_SOURCES: list[str] = [
    "https://api.ipify.org",
    "https://ifconfig.me/ip",
    "https://icanhazip.com",
    "https://checkip.amazonaws.com",
    "https://api4.my-ip.io/ip",
]

_IPV4_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")

# Type alias for notification callbacks
NotifyCallback = Callable[[str, str | None], Awaitable[None]]
"""async def callback(new_ip: str, old_ip: str | None) -> None"""


class IPChecker:
    """Fetches the public IP, detects changes, and fires notification callbacks."""

    def __init__(
        self,
        storage: IPStorage,
        interval: int = 300,
    ) -> None:
        self.storage = storage
        self.interval = interval
        self._callbacks: list[NotifyCallback] = []
        self._running = False
        self._last_check: datetime | None = None
        self._start_time: datetime = datetime.now(timezone.utc)

    # ---- public ----------------------------------------------------------

    def register_callback(self, cb: NotifyCallback) -> None:
        self._callbacks.append(cb)

    @property
    def last_check(self) -> datetime | None:
        return self._last_check

    @property
    def uptime_seconds(self) -> float:
        return (datetime.now(timezone.utc) - self._start_time).total_seconds()

    async def fetch_ip(self) -> str | None:
        """Try each source in order; return first valid IPv4 or None."""
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            for url in IP_SOURCES:
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    ip = resp.text.strip()
                    if _IPV4_RE.match(ip):
                        return ip
                    logger.warning("Non-IPv4 response from %s: %r", url, ip)
                except Exception as exc:
                    logger.warning("Failed to fetch IP from %s: %s", url, exc)
        logger.error("All IP sources failed!")
        return None

    async def check_once(self) -> str | None:
        """Fetch current IP, compare with stored, notify on change.

        Returns the current IP (or None on total failure).
        """
        ip = await self.fetch_ip()
        if ip is None:
            return None

        self._last_check = datetime.now(timezone.utc)
        stored = self.storage.get_current_ip()

        if stored is None:
            # First run — store without notifying
            logger.info("Initial IP detected: %s", ip)
            self.storage.store_ip(ip)
        elif ip != stored:
            logger.info("IP changed: %s → %s", stored, ip)
            self.storage.store_ip(ip)
            await self._fire_callbacks(ip, stored)
        else:
            logger.debug("IP unchanged: %s", ip)

        return ip

    async def run_loop(self) -> None:
        """Periodically check the IP until stopped."""
        self._running = True
        self._start_time = datetime.now(timezone.utc)
        logger.info("IP checker loop started (interval=%ds)", self.interval)

        # Immediate first check
        await self.check_once()

        while self._running:
            await asyncio.sleep(self.interval)
            if not self._running:
                break
            await self.check_once()

        logger.info("IP checker loop stopped.")

    def stop(self) -> None:
        self._running = False

    async def simulate_ip_change(self) -> str:
        """Fire all notification callbacks with a fake IP change.

        Useful for verifying that every enabled channel is working.
        Returns the current (real) IP used in the test.
        """
        real_ip = await self.fetch_ip() or self.storage.get_current_ip() or "0.0.0.0"
        fake_old = "192.0.2.1"  # RFC 5737 TEST-NET-1 — obviously fake
        fake_new = "198.51.100.1"  # RFC 5737 TEST-NET-2

        logger.info(
            "🧪 Simulating IP change: %s → %s  (real IP: %s)",
            fake_old, fake_new, real_ip,
        )
        await self._fire_callbacks(fake_new, fake_old)
        return real_ip

    # ---- internal --------------------------------------------------------

    async def _fire_callbacks(self, new_ip: str, old_ip: str | None) -> None:
        """Notify all registered callbacks concurrently."""
        tasks = [asyncio.create_task(cb(new_ip, old_ip)) for cb in self._callbacks]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error("Notification callback %d failed: %s", i, result)
