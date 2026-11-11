"""
Email delivery via Brevo with rich developer badges, Security Advisories, and Market Pulse.
Branded for StackPulse.
"""
from datetime import date
from typing import List, Optional
from brevo import Brevo
from brevo.transactional_emails import SendTransacEmailRequestSender, SendTransacEmailRequestToItem
from brevo.core.api_error import ApiError

from config import config
from security.guardrails import scan_output_for_leaks
from utils.logger import log

_client = Brevo(api_key=config.BREVO_API_KEY)

SENDER = SendTransacEmailRequestSender(
    email="nomankhan.work19@gmail.com",
    name="StackPulse",
)


def build_digest_html(
    user_name: str,
    digest: dict,
    ranked_items: list,
    market_pulse: Optional[str] = None,
    security_alert: Optional[str] = None,
) -> str:
    today_str = date.today().strftime("%B %d, %Y")

    # Map curated one-liners by external_id to avoid positional mismatches or item drops
    digest_items_map = {}
    for di in digest.get("items", []):
        if isinstance(di, dict) and di.get("external_id"):
            digest_items_map[str(di["external_id"]).strip().lower()] = di

    items_html = ""
    for idx, item in enumerate(ranked_items):
        item_dict = item if isinstance(item, dict) else dict(getattr(item, "_mapping", {}))
        title      = item_dict.get("title") or getattr(item, "title", "Untitled")
        url        = item_dict.get("url") or getattr(item, "url", "#")
        summary    = item_dict.get("summary") or getattr(item, "summary", "")
        tech_stack = item_dict.get("tech_stack") or getattr(item, "tech_stack", []) or []
        raw_data   = item_dict.get("raw_data") if "raw_data" in item_dict else getattr(item, "raw_data", {})
        meta       = (raw_data or {}).get("metadata", {})
        source_name = str(item_dict.get("source_name") or (raw_data or {}).get("source") or "").strip().lower()
        ext_id     = str(item_dict.get("external_id") or getattr(item, "external_id", "")).strip()
        url_lower  = str(url).lower()

        # Match curator one-liner, with positional fallback if within bounds
        matched_di = digest_items_map.get(ext_id.lower())
        if not matched_di and idx < len(digest.get("items", [])):
            candidate_fallback = digest.get("items", [])[idx]
            if isinstance(candidate_fallback, dict):
                matched_di = candidate_fallback

        why_it_matters = (matched_di.get("one_liner") if matched_di else "").strip()
        if not why_it_matters:
            top_tech = tech_stack[0] if tech_stack else "developer tools"
            why_it_matters = f"Trending in {top_tech} — highly relevant update for your core stack."

        # Compute source badge
        source_badge = ""
        if "hacker" in source_name or "hn" in source_name or "news.ycombinator.com" in url_lower or ext_id.startswith("hn:"):
            pts = meta.get("score") or meta.get("points", 0)
            hn_url = meta.get("hn_url") or (f"https://news.ycombinator.com/item?id={meta.get('id', '')}" if meta.get("id") else url)
            pts_str = f" {pts} pts" if pts else ""
            source_badge = (
                f'<a href="{hn_url}" target="_blank" style="display:inline-block;background:#ff6600;color:#ffffff;'
                f'font-size:10.5px;font-weight:700;padding:2px 8px;border-radius:10px;'
                f'margin-right:6px;text-decoration:none;">🟠 HN{pts_str}</a>'
            )
        elif "openai" in source_name or "openai.com" in url_lower:
            source_badge = (
                f'<span style="display:inline-block;background:#10a37f;color:#ffffff;'
                f'font-size:10.5px;font-weight:700;padding:2px 8px;border-radius:10px;'
                f'margin-right:6px;">🟢 OpenAI</span>'
            )
        elif "anthropic" in source_name or "anthropic.com" in url_lower:
            source_badge = (
                f'<span style="display:inline-block;background:#d97706;color:#ffffff;'
                f'font-size:10.5px;font-weight:700;padding:2px 8px;border-radius:10px;'
                f'margin-right:6px;">🟤 Anthropic</span>'
            )
        elif "rss" in source_name or any(k in url_lower for k in ["deepmind", "techcrunch", "arxiv", "feed"]):
            source_badge = (
                f'<span style="display:inline-block;background:#0284c7;color:#ffffff;'
                f'font-size:10.5px;font-weight:700;padding:2px 8px;border-radius:10px;'
                f'margin-right:6px;">📰 AI News</span>'
            )
        elif "github" in source_name or "github.com" in url_lower or ("/" in ext_id and not ext_id.startswith("http")):
            stars = meta.get("stars_today") or meta.get("total_stars")
            stars_label = f" · ⭐ {stars}" if stars and str(stars) != "0" else ""
            source_badge = (
                f'<span style="display:inline-block;background:#24292e;color:#ffffff;'
                f'font-size:10.5px;font-weight:700;padding:2px 8px;border-radius:10px;'
                f'margin-right:6px;">🐙 GitHub{stars_label}</span>'
            )
        else:
            source_badge = (
                f'<span style="display:inline-block;background:#475569;color:#ffffff;'
                f'font-size:10.5px;font-weight:700;padding:2px 8px;border-radius:10px;'
                f'margin-right:6px;">📰 Source</span>'
            )

        tech_badges = "".join(
            f'<span style="display:inline-block;background:#eef4fc;color:#185fa5;'
            f'font-size:10.5px;font-weight:600;padding:2px 7px;border-radius:10px;'
            f'margin-right:5px;">{t}</span>'
            for t in (tech_stack or [])[:3]
        )
        all_badges = source_badge + tech_badges

        items_html += f"""
        <div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:8px;
                    padding:16px;margin-bottom:12px;">
            <div style="margin-bottom:6px;">
                <a href="{url}" style="font-size:15px;font-weight:700;color:#0f172a;
                   text-decoration:none;line-height:1.4;">{title}</a>
            </div>

            <div style="margin-bottom:8px;">{all_badges}</div>

            <p style="margin:0 0 10px;color:#475569;font-size:13.5px;line-height:1.5;">
                {summary}
            </p>

            <div style="background:#f0f7ff;border-left:3px solid #2563eb;
                        padding:6px 10px;border-radius:0 5px 5px 0;">
                <span style="color:#2563eb;font-size:11px;font-weight:700;
                             text-transform:uppercase;letter-spacing:0.3px;">💡 Why it matters: </span>
                <span style="color:#1e293b;font-size:13px;line-height:1.4;">
                    {why_it_matters}
                </span>
            </div>
        </div>
        """

    # Optional Security Alert Banner
    sec_banner = ""
    if security_alert:
        clean_sec = security_alert.replace("\n", "<br/>")
        sec_banner = f"""
        <div style="background:#fffbeb;border:1px solid #fef3c7;border-left:4px solid #f59e0b;
                    border-radius:8px;padding:12px 14px;margin-bottom:14px;">
            <p style="margin:0 0 4px;font-size:11.5px;font-weight:800;color:#92400e;letter-spacing:0.4px;">
                🛡️ SECURITY ADVISORY (YOUR STACK)
            </p>
            <div style="font-size:12.5px;color:#78350f;line-height:1.45;">
                {clean_sec}
            </div>
        </div>
        """

    # Optional Market & AI Pulse Barometer Widget
    pulse_widget = ""
    pulse_content = market_pulse or digest.get("market_pulse")
    if pulse_content:
        clean_pulse = pulse_content.replace("📊 Today's AI & Tech Pulse:\n", "").replace("\n", "<br/>")
        pulse_widget = f"""
        <div style="background:#f8fafc;border:1px solid #e2e8f0;border-left:4px solid #64748b;
                    border-radius:8px;padding:12px 14px;margin-bottom:16px;">
            <p style="margin:0 0 4px;font-size:11px;font-weight:800;color:#475569;
                      text-transform:uppercase;letter-spacing:0.5px;">
                📊 TODAY'S AI & TECH BAROMETER
            </p>
            <div style="font-size:12.5px;color:#334155;line-height:1.5;">
                {clean_pulse}
            </div>
        </div>
        """

    return f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
                max-width:580px;margin:0 auto;background:#f8fafc;padding:20px;color:#0f172a;">

        <!-- Header -->
        <div style="text-align:center;padding:12px 0 16px;border-bottom:1px solid #e2e8f0;margin-bottom:16px;">
            <span style="background:#0f172a;color:#ffffff;font-size:11px;font-weight:800;
                         padding:4px 12px;border-radius:14px;letter-spacing:0.8px;">
                ⚡ STACKPULSE
            </span>
            <div style="font-size:11.5px;color:#64748b;margin-top:6px;font-weight:500;">
                Developer Intelligence · {today_str}
            </div>
        </div>

        <!-- Greeting & Intro -->
        <h3 style="color:#0f172a;font-size:16px;margin:0 0 6px;font-weight:700;">
            Hey {user_name or 'Developer'} 👋
        </h3>
        <p style="color:#475569;font-size:13.5px;line-height:1.55;margin:0 0 16px;">
            {digest.get("intro", "Here is your curated developer intelligence for today:")}
        </p>

        <!-- Widgets -->
        {sec_banner}
        {pulse_widget}

        <!-- Digest Items -->
        <div style="margin-top:8px;">
            {items_html}
        </div>

        <!-- Footer -->
        <div style="text-align:center;padding:20px 0 10px;border-top:1px solid #e2e8f0;margin-top:20px;">
            <p style="margin:0;font-size:11px;font-weight:600;color:#64748b;">
                StackPulse · Autonomous Developer Intelligence
            </p>
            <p style="margin:4px 0 0;font-size:10.5px;color:#94a3b8;">
                Curated specifically for your tech stack & interests.
            </p>
        </div>
    </div>
    """


def send_digest_email(to_email: str, subject: str, html_content: str) -> bool:
    try:
        # Guardrail 4: Scrub sensitive secrets and credentials before delivery
        safe_html, was_sanitized = scan_output_for_leaks(html_content)
        if was_sanitized:
            log.warning("security.email_secret_leak_scrubbed", recipient=to_email)

        response = _client.transactional_emails.send_transac_email(
            html_content=safe_html,
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
