"""
Email delivery via Resend (https://resend.com — free tier available).
Swap this module out for SendGrid/SES later without touching main.py,
as long as send_digest() keeps the same signature.
"""
from datetime import date
from typing import List
# import resend
from brevo import Brevo
from brevo.transactional_emails import SendTransacEmailRequestSender, SendTransacEmailRequestToItem
from brevo.core.api_error import ApiError

from config import config
from utils.logger import log

# resend.api_key = config.RESEND_API_KEY

_client = Brevo(api_key=config.BREVO_API_KEY)

SENDER = SendTransacEmailRequestSender(
    email="nomankhan.work19@gmail.com",   # must be verified in Brevo dashboard
    name="DevSnack",
)

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


# def send_digest(summaries: List[dict], to_email: str) -> bool:
#     if not summaries:
#         log.info("no_new_items_skipping_email")
#         return False

#     html = _render_html(summaries)

#     try:
#         resend.Emails.send({
#             "from": config.EMAIL_FROM,
#             "to": to_email,
#             "subject": f"🔥 {len(summaries)} Trending Repos Today — GitHub Digest",
#             "html": html,
#         })
#         log.info("email_sent", to=to_email, item_count=len(summaries))
#         return True
#     except Exception as e:
#         log.error("email_send_failed", error=str(e))
#         raise


# services/mailer.py — add this function (keep whatever SMTP/provider setup you already have)
def build_digest_html(user_name: str, digest, ranked_items: list[dict]) -> str:
    items_html = ""
    for item, digest_item in zip(ranked_items, digest.items):
        items_html += f"""
        <div style="margin-bottom:16px;padding:12px;border-left:3px solid #185fa5;">
            <a href="{item['url']}" style="font-weight:600;color:#185fa5;text-decoration:none;">{item['title']}</a>
            <p style="margin:4px 0 0;color:#333;font-size:14px;">{digest_item.one_liner}</p>
        </div>
        """

    return f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto;">
        <h2>Hey {user_name or 'there'} 👋</h2>
        <p>{digest.intro}</p>
        {items_html}
        <p style="color:#999;font-size:12px;">You're receiving this because you subscribed to DevSnack.</p>
    </div>
    """


def send_digest_email(to_email: str, subject: str, html_content: str) -> bool:
    try:
        response = _client.transactional_emails.send_transac_email(
            html_content=html_content,
            sender=SENDER,
            subject=subject,
            to=[SendTransacEmailRequestToItem(email='isoisoiso598@gmail.com')],
        )
        log.info("mailer.email_sent", to=to_email)
        return True

    except ApiError as e:
        log.error("mailer.send_failed", to=to_email, status=e.status_code, body=e.body)
        return False

    except Exception as e:
        log.error("mailer.send_failed_unexpected", to=to_email, error=str(e))
        return False

