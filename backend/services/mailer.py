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

# def build_digest_html(user_name: str, digest, ranked_items: list[dict]) -> str:
#     items_html = ""
#     for item, digest_item in zip(ranked_items, digest['items']):  # ← Use digest['items']
#         items_html += f"""
#         <div style="margin-bottom:16px;padding:12px;border-left:3px solid #185fa5;">
#             <a href="{item['url']}" style="font-weight:600;color:#185fa5;text-decoration:none;">{item['title']}</a>
#             <p style="margin:4px 0 0;color:#333;font-size:14px;">{digest_item['one_liner']}</p>  <!-- ← Use dict access -->
#         </div>
#         """

#     return f"""
#     <div style="font-family:sans-serif;max-width:600px;margin:0 auto;">
#         <h2>Hey {user_name or 'there'} 👋</h2>
#         <p>{digest['intro']}</p>  <!-- ← Use dict access -->
#         {items_html}
#         <p style="color:#999;font-size:12px;">You're receiving this because you subscribed to DevSnack.</p>
#     </div>
#     """

# services/mailer.py

def build_digest_html(user_name: str, digest: dict, ranked_items: list) -> str:
    items_html = ""
    for item, digest_item in zip(ranked_items, digest["items"]):
        # item may be a Row (dict-style) or dict — handle both safely
        title      = item["title"] if not hasattr(item, "title") else item.title
        url        = item["url"] if not hasattr(item, "url") else item.url
        summary    = item["summary"] if not hasattr(item, "summary") else item.summary
        tech_stack = item["tech_stack"] if not hasattr(item, "tech_stack") else item.tech_stack
        raw_data   = item["raw_data"] if isinstance(item, dict) and "raw_data" in item else getattr(item, "raw_data", {})
        meta       = (raw_data or {}).get("metadata", {})
        source     = (raw_data or {}).get("source", "")

        hn_badge = ""
        if source == "hacker_news" or meta.get("hn_url"):
            pts = meta.get("score", 0)
            comms = meta.get("comments_count", 0)
            hn_url = meta.get("hn_url") or f"https://news.ycombinator.com/item?id={meta.get('id', '')}"
            hn_badge = (
                f'<a href="{hn_url}" target="_blank" style="display:inline-block;background:#ff6600;color:#ffffff;'
                f'font-size:11px;font-weight:700;padding:3px 9px;border-radius:12px;'
                f'margin-right:6px;text-decoration:none;">🟠 HN {pts} pts · {comms} comms</a>'
            )

        tech_badges = "".join(
            f'<span style="display:inline-block;background:#eef4fc;color:#185fa5;'
            f'font-size:11px;font-weight:600;padding:3px 8px;border-radius:12px;'
            f'margin-right:6px;">{t}</span>'
            for t in (tech_stack or [])[:3]
        )
        all_badges = hn_badge + tech_badges

        items_html += f"""
        <div style="background:#ffffff;border:1px solid #e8e8e8;border-radius:10px;
                    padding:18px 20px;margin-bottom:14px;">
            <a href="{url}" style="font-size:16px;font-weight:700;color:#111;
               text-decoration:none;line-height:1.4;">{title}</a>

            <div style="margin:8px 0 10px;">{all_badges}</div>

            <p style="margin:0 0 10px;color:#444;font-size:14px;line-height:1.6;">
                {summary}
            </p>

            <div style="background:#f5f9ff;border-left:3px solid #185fa5;
                        padding:8px 12px;border-radius:0 6px 6px 0;">
                <p style="margin:0;color:#185fa5;font-size:12px;font-weight:700;
                          text-transform:uppercase;letter-spacing:0.4px;">
                    Why it matters
                </p>
                <p style="margin:4px 0 0;color:#333;font-size:13.5px;line-height:1.5;">
                    {digest_item["one_liner"]}
                </p>
            </div>
        </div>
        """

    return f"""
    <div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:600px;
                margin:0 auto;background:#f9fafb;padding:24px;">

        <div style="text-align:center;margin-bottom:24px;">
            <span style="background:#185fa5;color:#fff;font-size:12px;font-weight:700;
                         padding:5px 14px;border-radius:20px;letter-spacing:0.3px;">
                DEVSNACK
            </span>
        </div>

        <h2 style="color:#111;font-size:20px;margin:0 0 8px;">Hey {user_name or 'there'} 👋</h2>
        <p style="color:#555;font-size:14.5px;line-height:1.6;margin:0 0 24px;">
            {digest["intro"]}
        </p>

        {items_html}

        <p style="text-align:center;color:#aaa;font-size:11.5px;margin-top:28px;">
            You're receiving this because you subscribed to DevSnack.
        </p>
    </div>
    """
def send_digest_email(to_email: str, subject: str, html_content: str) -> bool:
    try:
        response = _client.transactional_emails.send_transac_email(
            html_content=html_content,
            sender=SENDER,
            subject=subject,
            to=[SendTransacEmailRequestToItem(email=to_email)],
        )
        log.info("mailer.email_sent", to=to_email)
        return True

    except ApiError as e:
        log.error("mailer.send_failed", to=to_email, status=e.status_code, body=e.body)
        return False

    except Exception as e:
        log.error("mailer.send_failed_unexpected", to=to_email, error=str(e))
        return False

