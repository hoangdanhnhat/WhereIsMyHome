"""Email (SMTP) notifier — sends email on IP change."""

from __future__ import annotations

import logging
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import EmailConfig
from app.storage import IPStorage

logger = logging.getLogger(__name__)


def _build_message(
    config: EmailConfig,
    new_ip: str,
    old_ip: str | None,
    history_snippet: str,
) -> MIMEMultipart:
    """Compose a MIME email for the IP-change notification."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "[IP Tracker] Your public IP has changed"
    msg["From"] = config.smtp_user
    msg["To"] = ", ".join(config.notify_emails)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    text_body = (
        f"Your public IP address has changed.\n\n"
        f"  Old IP:    {old_ip or 'N/A'}\n"
        f"  New IP:    {new_ip}\n"
        f"  Detected:  {timestamp}\n\n"
        f"--- Recent IP History ---\n{history_snippet}\n"
    )

    html_body = f"""\
<html>
<body style="font-family: Arial, sans-serif; color: #333;">
  <h2 style="color: #2c3e50;">🌐 IP Address Changed</h2>
  <table style="border-collapse: collapse; margin: 16px 0;">
    <tr>
      <td style="padding: 6px 14px; font-weight: bold;">Old IP</td>
      <td style="padding: 6px 14px;"><code>{old_ip or 'N/A'}</code></td>
    </tr>
    <tr style="background: #f8f9fa;">
      <td style="padding: 6px 14px; font-weight: bold;">New IP</td>
      <td style="padding: 6px 14px;"><code>{new_ip}</code></td>
    </tr>
    <tr>
      <td style="padding: 6px 14px; font-weight: bold;">Detected</td>
      <td style="padding: 6px 14px;">{timestamp}</td>
    </tr>
  </table>
  <h3 style="color: #2c3e50;">📋 Recent IP History</h3>
  <pre style="background: #f8f9fa; padding: 12px; border-radius: 6px;">{history_snippet}</pre>
  <hr style="border: none; border-top: 1px solid #eee; margin: 24px 0;">
  <p style="font-size: 12px; color: #999;">
    Sent by <strong>WhereIsMyHome</strong> IP Tracker
  </p>
</body>
</html>"""

    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))
    return msg


class EmailNotifier:
    """Sends IP-change notifications via SMTP."""

    def __init__(self, config: EmailConfig, storage: IPStorage) -> None:
        self.cfg = config
        self.storage = storage

    async def notify_ip_change(self, new_ip: str, old_ip: str | None) -> None:
        """Send an email notification (runs blocking SMTP in a thread)."""
        import asyncio

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._send_sync, new_ip, old_ip)

    def _send_sync(self, new_ip: str, old_ip: str | None) -> None:
        records = self.storage.get_history(limit=10)
        history_lines = [f"  {r.timestamp}  →  {r.ip}" for r in records]
        history_snippet = "\n".join(history_lines) if history_lines else "  (no history)"

        msg = _build_message(self.cfg, new_ip, old_ip, history_snippet)

        try:
            if self.cfg.smtp_port == 465:
                # SSL
                with smtplib.SMTP_SSL(self.cfg.smtp_host, self.cfg.smtp_port) as srv:
                    srv.login(self.cfg.smtp_user, self.cfg.smtp_pass)
                    srv.sendmail(
                        self.cfg.smtp_user,
                        self.cfg.notify_emails,
                        msg.as_string(),
                    )
            else:
                # STARTTLS
                with smtplib.SMTP(self.cfg.smtp_host, self.cfg.smtp_port) as srv:
                    srv.ehlo()
                    srv.starttls()
                    srv.ehlo()
                    srv.login(self.cfg.smtp_user, self.cfg.smtp_pass)
                    srv.sendmail(
                        self.cfg.smtp_user,
                        self.cfg.notify_emails,
                        msg.as_string(),
                    )

            logger.info("Email notification sent to %s", self.cfg.notify_emails)
        except Exception as exc:
            logger.error("Failed to send email: %s", exc)
