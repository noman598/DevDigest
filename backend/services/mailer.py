"""
Email delivery via Resend (https://resend.com — free tier available).
Swap this module out for SendGrid/SES later without touching main.py,
as long as send_digest() keeps the same signature.
"""
from datetime import date
from typing import List
import resend

from backend.config import config
from backend.utils.logger import log

resend.api_key = config.RESEND_API_KEY


def _render_html(summaries: List[dict]) -> str:
    today = date.today().strftime("%B %d, %Y")

    rows = ""
    for s in summaries:
        rows += f"""
        <tr>
          <td style="padding: 16px 0; border-bottom: 1px solid #eee;">
            <a href="{s['url']}" style="font-size: 16px; font-weight: 600; color: #0969da; text-decoration: none;">
              {s['title']}
            </a>
            <p style="margin: 6px 0 0; color: #333; font-size: 14px;">{s['summary']}</p>
            <p style="margin: 4px 0 0; color: #666; font-size: 13px; font-style: italic;">
              {s.get('why_it_matters', '')}
            </p>
          </td>
        </tr>
        """

    return f"""
    <html>
      <body style="font-family: -apple-system, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #111;">🔥 GitHub Trending Digest — {today}</h2>
        <p style="color: #555; font-size: 14px;">Top trending repos from the last 24 hours.</p>
        <table style="width: 100%; border-collapse: collapse;">
          {rows}
        </table>
        <p style="color: #999; font-size: 12px; margin-top: 30px;">
          You're receiving this because you set up your own digest bot.
        </p>
      </body>
    </html>
    """


def send_digest(summaries: List[dict], to_email: str) -> bool:
    if not summaries:
        log.info("no_new_items_skipping_email")
        return False

    html = _render_html(summaries)

    try:
        resend.Emails.send({
            "from": config.EMAIL_FROM,
            "to": to_email,
            "subject": f"🔥 {len(summaries)} Trending Repos Today — GitHub Digest",
            "html": html,
        })
        log.info("email_sent", to=to_email, item_count=len(summaries))
        return True
    except Exception as e:
        log.error("email_send_failed", error=str(e))
        raise
