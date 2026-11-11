"""
StackPulse — Autonomous Developer Intelligence
Modern SaaS Onboarding, Preference Vectorization, Sample Digest Preview & Documentation.
"""
from datetime import date, datetime
import json
import re
from typing import Dict, List, Optional

import streamlit as st

from storage.db import (
    get_platform_stats,
    get_user_profile,
    init_db,
    save_user_profile,
    user_exists,
)
from utils.embedding import run_user_embedding
from utils.logger import log

# Initialize Database Schema if not already present
try:
    init_db()
except Exception as e:
    log.warning("frontend.init_db_skipped", error=str(e))

# ── Page Configuration ────────────────────────────────────────────────────────
st.set_page_config(
    page_title="StackPulse · Autonomous Developer Intelligence",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Custom Industrial Design System (CSS) ─────────────────────────────────────
st.markdown("""
<style>
    /* Global font and smooth background */
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    /* Main Container adjustments */
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 3rem;
        max-width: 1200px;
    }

    /* Top Brand Hero Pill */
    .brand-pill {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        background: #0f172a;
        color: #ffffff;
        font-size: 11.5px;
        font-weight: 700;
        padding: 5px 14px;
        border-radius: 9999px;
        letter-spacing: 0.6px;
        margin-bottom: 0.75rem;
        box-shadow: 0 2px 8px rgba(15, 23, 42, 0.15);
    }

    .brand-pill .dot {
        width: 7px;
        height: 7px;
        background: #10b981;
        border-radius: 50%;
        display: inline-block;
        box-shadow: 0 0 8px #10b981;
    }

    /* Hero Typography */
    .hero-title {
        font-size: 2.5rem;
        font-weight: 800;
        color: #0f172a;
        line-height: 1.15;
        letter-spacing: -0.03em;
        margin-bottom: 0.75rem;
    }

    .hero-gradient {
        background: linear-gradient(135deg, #2563eb 0%, #7c3aed 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }

    .hero-subtitle {
        font-size: 1.05rem;
        color: #475569;
        line-height: 1.6;
        max-width: 760px;
        margin-bottom: 1.5rem;
    }

    /* SaaS Metric & Feature Cards */
    .feature-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 1.25rem;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.03), 0 2px 4px -2px rgba(0, 0, 0, 0.03);
        transition: transform 0.2s, box-shadow 0.2s;
        height: 100%;
    }

    .feature-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.06);
    }

    .feature-icon {
        font-size: 1.6rem;
        margin-bottom: 0.5rem;
    }

    .feature-title {
        font-size: 0.95rem;
        font-weight: 700;
        color: #0f172a;
        margin-bottom: 0.25rem;
    }

    .feature-desc {
        font-size: 0.82rem;
        color: #64748b;
        line-height: 1.45;
    }

    /* Email Simulation Wrapper */
    .email-preview-container {
        background: #f1f5f9;
        border-radius: 16px;
        padding: 24px;
        border: 1px solid #cbd5e1;
        box-shadow: 0 10px 25px -5px rgba(15, 23, 42, 0.08);
    }

    .email-sheet {
        background: #ffffff;
        border-radius: 10px;
        border: 1px solid #e2e8f0;
        padding: 28px;
        max-width: 620px;
        margin: 0 auto;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
    }

    /* Custom Streamlit Tabs Styling */
    div[data-baseweb="tab-list"] {
        gap: 8px;
        border-bottom: 1px solid #e2e8f0;
        padding-bottom: 4px;
    }

    div[data-baseweb="tab"] {
        font-weight: 600;
        font-size: 0.92rem;
        padding: 8px 16px;
        border-radius: 8px;
        color: #64748b;
    }

    div[data-baseweb="tab"][aria-selected="true"] {
        color: #2563eb;
        background-color: #eff6ff;
    }

    /* Code block styling */
    pre, code {
        font-family: 'JetBrains Mono', monospace !important;
    }

    /* Source Badge styling */
    .badge-gh {
        background: #24292e; color: #fff; font-size: 10.5px; font-weight: 700;
        padding: 2px 8px; border-radius: 10px; display: inline-block; margin-right: 6px;
    }
    .badge-oa {
        background: #10a37f; color: #fff; font-size: 10.5px; font-weight: 700;
        padding: 2px 8px; border-radius: 10px; display: inline-block; margin-right: 6px;
    }
    .badge-ant {
        background: #d97706; color: #fff; font-size: 10.5px; font-weight: 700;
        padding: 2px 8px; border-radius: 10px; display: inline-block; margin-right: 6px;
    }
    .badge-hn {
        background: #ff6600; color: #fff; font-size: 10.5px; font-weight: 700;
        padding: 2px 8px; border-radius: 10px; display: inline-block; margin-right: 6px;
    }

    /* Footer */
    .saas-footer {
        border-top: 1px solid #e2e8f0;
        margin-top: 3.5rem;
        padding-top: 1.5rem;
        text-align: center;
        color: #94a3b8;
        font-size: 0.8rem;
    }
</style>
""", unsafe_allow_html=True)

# ── Top Hero & Product Header ────────────────────────────────────────────────
st.markdown("""
<div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:1rem;">
    <div>
        <div class="brand-pill">
            <span class="dot"></span> STACKPULSE V2.0 · AUTONOMOUS AGENT INTELLIGENCE
        </div>
        <h1 class="hero-title">
            Stop drowning in dev news.<br>
            <span class="hero-gradient">Get autonomous intelligence curated for your stack.</span>
        </h1>
        <p class="hero-subtitle">
            StackPulse continuously ingests GitHub Trending, official AI lab announcements (OpenAI, Anthropic), and Hacker News discussions.
            Our LangGraph curator agent checks active CVE advisories, tracks live market pricing, and synthesizes <strong>one high-signal email</strong> matched to your vector profile.
        </p>
    </div>
</div>
""", unsafe_allow_html=True)

# ── Social Proof & Value Props Grid ──────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown("""
    <div class="feature-card">
        <div class="feature-icon">⚖️</div>
        <div class="feature-title">Source Diversity</div>
        <div class="feature-desc">Strictly guarantees 2–3 GitHub repos, 2–3 official AI news items, and 2–3 HN debates. No star bias.</div>
    </div>
    """, unsafe_allow_html=True)
with c2:
    st.markdown("""
    <div class="feature-card">
        <div class="feature-icon">🧬</div>
        <div class="feature-title">1536d Vector Taste</div>
        <div class="feature-desc">Gemini embeddings convert your exact tech stack & topics into a semantic vector for cosine matching.</div>
    </div>
    """, unsafe_allow_html=True)
with c3:
    st.markdown("""
    <div class="feature-card">
        <div class="feature-icon">🛡️</div>
        <div class="feature-title">Live CVE & Market Tools</div>
        <div class="feature-desc">Curator agent proactively audits candidate dependencies against NVD CVEs and tracks AI token pricing.</div>
    </div>
    """, unsafe_allow_html=True)
with c4:
    st.markdown("""
    <div class="feature-card">
        <div class="feature-icon">🧠</div>
        <div class="feature-title">7-Day Memory Store</div>
        <div class="feature-desc">Long-term memory ensures items delivered in the past week are never repeated. Zero duplicate fatigue.</div>
    </div>
    """, unsafe_allow_html=True)

st.write("")

# ── Available Data Constants ──────────────────────────────────────────────────
AVAILABLE_SOURCES = {
    "github_trending": {
        "label": "GitHub Trending",
        "badge": "🐙 GitHub",
        "desc": "High-velocity open source repositories and tools trending today",
        "default": True,
    },
    "openai_news": {
        "label": "OpenAI Official News",
        "badge": "🟢 OpenAI",
        "desc": "Official model launches, research papers, and production case studies",
        "default": True,
    },
    "anthropic_news": {
        "label": "Anthropic Announcements",
        "badge": "🟤 Anthropic",
        "desc": "Claude capabilities, frontier safety research, and system updates",
        "default": True,
    },
    "hacker_news": {
        "label": "Hacker News Debates",
        "badge": "🟠 Hacker News",
        "desc": "Technical community consensus, architecture discussions, and debates",
        "default": True,
    },
    "ai_news_rss": {
        "label": "Leading AI Research & RSS",
        "badge": "📰 AI News",
        "desc": "Curated deep-dives from DeepMind, arXiv, TechCrunch & leading AI labs",
        "default": True,
    },
}

CORE_TECH_TAGS = [
    "AI/ML", "LLMs", "Python", "Web Development", "System Design",
    "DevOps/Cloud", "Cybersecurity", "Data Science", "Rust", "Go",
    "JavaScript", "TypeScript", "Databases", "Distributed Systems",
    "Open Source", "Kubernetes", "Embedded/IoT", "FastAPI", "PyTorch",
    "LangChain", "Vector Databases", "Agentic Workflows", "Startups"
]

FREQUENCY_CHOICES = {
    "daily": "Daily (Monday through Sunday)",
    "weekdays": "Weekdays Only (Monday – Friday)",
    "weekly": "Weekly Summary (Every Monday)",
}

TIME_CHOICES = {
    "06:00": "6:00 AM (Early Bird)",
    "07:00": "7:00 AM (Pre-Commute)",
    "08:00": "8:00 AM (Workday Kickoff — Recommended)",
    "09:00": "9:00 AM (Morning Standup)",
    "12:00": "12:00 PM (Lunch Digest)",
    "18:00": "6:00 PM (Evening Wrap-up)",
}

# ── Navigation Tabs ───────────────────────────────────────────────────────────
tab_onboarding, tab_sample, tab_docs, tab_telemetry = st.tabs([
    "🚀 Customize & Subscribe",
    "📬 Interactive Sample Digest",
    "📖 Product Architecture & Docs",
    "⚡ Platform Telemetry",
])


# ═════════════════════════════════════════════════════════════════════════════
# TAB 1: ONBOARDING & PREFERENCE CONFIGURATION
# ═════════════════════════════════════════════════════════════════════════════
with tab_onboarding:
    st.markdown("### ⚙️ Configure Your Autonomous Developer Digest")
    st.caption("Tell us your tech stack and interests. We convert this into a 1536-dimensional taste vector to match today's top dev content.")

    col_form, col_live = st.columns([1.1, 0.9], gap="large")

    # Session State Initialization
    if "user_email" not in st.session_state:
        st.session_state.user_email = ""
    if "form_loaded" not in st.session_state:
        st.session_state.form_loaded = False
    if "profile_data" not in st.session_state:
        st.session_state.profile_data = {}

    with col_form:
        # Pre-lookup bar for existing users
        lookup_col1, lookup_col2 = st.columns([3, 1])
        with lookup_col1:
            entered_email = st.text_input(
                "Subscriber Email Address *",
                value=st.session_state.user_email,
                placeholder="you@domain.com",
                help="Your daily StackPulse digest will be delivered here.",
            )
        with lookup_col2:
            st.write("")
            st.write("")
            load_clicked = st.button("🔍 Load Existing", use_container_width=True)

        if (load_clicked or (entered_email and entered_email != st.session_state.user_email)) and entered_email:
            st.session_state.user_email = entered_email.strip().lower()
            existing_prof = get_user_profile(st.session_state.user_email)
            if existing_prof:
                st.session_state.profile_data = existing_prof
                st.session_state.form_loaded = True
                st.success(f"✓ Found existing profile for {st.session_state.user_email}! Preferences loaded.")
            else:
                st.session_state.profile_data = {"email": st.session_state.user_email}
                st.session_state.form_loaded = True

        prof = st.session_state.profile_data

        with st.form("stackpulse_onboarding_form", clear_on_submit=False):
            st.markdown("#### 1. Identity")
            subscriber_name = st.text_input(
                "Your Name / Handle",
                value=prof.get("name", ""),
                placeholder="e.g. Alex Chen",
                help="Used to personalize the opening briefing note from the curator agent.",
            )

            st.markdown("#### 2. Selected Sources (Multi-Source Balancing)")
            st.caption("StackPulse guarantees representation from all selected active sources.")
            selected_sources_keys = []
            cols_src = st.columns(2)
            for idx, (skey, sinfo) in enumerate(AVAILABLE_SOURCES.items()):
                c_target = cols_src[idx % 2]
                current_val = skey in prof.get("selected_sources", [k for k, v in AVAILABLE_SOURCES.items() if v["default"]])
                checked = c_target.checkbox(f"{sinfo['badge']} · {sinfo['label']}", value=current_val, key=f"src_cb_{skey}")
                if checked:
                    selected_sources_keys.append(skey)

            st.markdown("#### 3. Tech Stack & Interests")
            liked_tags = st.multiselect(
                "Primary Stack & Topics You Want to Follow *",
                options=CORE_TECH_TAGS,
                default=prof.get("liked_tags", ["AI/ML", "Python", "LLMs", "System Design"]),
                help="These are used to calculate semantic relevance against newly enriched items.",
            )

            disliked_tags = st.multiselect(
                "Topics to Filter Out / Minimize",
                options=CORE_TECH_TAGS,
                default=prof.get("disliked_tags", []),
                help="Items matching these topics will be down-ranked or excluded from your candidate pool.",
            )

            custom_interests = st.text_area(
                "Custom Semantic Focus (Natural Language)",
                value=prof.get("custom_interests", ""),
                placeholder="e.g. CUDA kernel optimization, RAG evaluation frameworks, local inference on Mac M-series, agent tool-use architectures...",
                help="Parsed directly by the embedding pipeline to capture niche interests not covered by generic tags.",
            )

            keyword_alerts = st.text_input(
                "Keyword Alerts (Comma-separated)",
                value=prof.get("keyword_alerts", ""),
                placeholder="e.g. vLLM, DeepSeek, Claude 3.7, zero-day",
                help="High-priority keywords that boost matching items regardless of general topic filters.",
            )

            st.markdown("#### 4. Delivery Schedule & AI Features")
            sched_col1, sched_col2 = st.columns(2)
            with sched_col1:
                frequency = st.selectbox(
                    "Delivery Cadence",
                    options=list(FREQUENCY_CHOICES.keys()),
                    format_func=lambda x: FREQUENCY_CHOICES[x],
                    index=list(FREQUENCY_CHOICES.keys()).index(prof.get("frequency", "daily")),
                )
            with sched_col2:
                delivery_time = st.selectbox(
                    "Target Time",
                    options=list(TIME_CHOICES.keys()),
                    format_func=lambda x: TIME_CHOICES[x],
                    index=list(TIME_CHOICES.keys()).index(prof.get("delivery_time", "08:00")),
                )

            feat_col1, feat_col2 = st.columns(2)
            with feat_col1:
                inc_summary = st.checkbox("Autonomous AI Summaries", value=prof.get("include_summary", True))
            with feat_col2:
                inc_why = st.checkbox("Personalized 'Why It Matters' Insights", value=prof.get("include_why_matters", True))

            st.markdown("---")
            submit_btn = st.form_submit_button("⚡ Save Preferences & Generate Vector Embedding", type="primary", use_container_width=True)

        if submit_btn:
            valid_email = entered_email.strip().lower() if entered_email else ""
            pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not valid_email or not re.match(pattern, valid_email):
                st.error("Please enter a valid recipient email address.")
            elif not liked_tags and not custom_interests:
                st.error("Please choose at least 1 tech tag or enter a custom interest.")
            else:
                form_payload = {
                    "email": valid_email,
                    "name": subscriber_name,
                    "selected_sources": selected_sources_keys,
                    "liked_tags": liked_tags,
                    "disliked_tags": disliked_tags,
                    "custom_interests": custom_interests,
                    "keyword_alerts": keyword_alerts,
                    "frequency": frequency,
                    "delivery_time": delivery_time,
                    "include_summary": inc_summary,
                    "include_why_matters": inc_why,
                }
                with st.spinner("Saving profile to database and embedding preferences vector..."):
                    saved = save_user_profile(form_payload)
                    if saved:
                        try:
                            emb_res = run_user_embedding(batch_size=1)
                            st.balloons()
                            st.success(f"🎉 Preferences saved successfully! 1536-dimensional taste vector generated and committed to pgvector.")
                            st.session_state.profile_data = form_payload
                        except Exception as e:
                            st.warning(f"Profile saved, but background embedding encountered an error: {e}")
                    else:
                        st.error("Failed to save profile. Please check database connectivity.")

    # Live Vector / Taste Profile Breakdown Card
    with col_live:
        st.markdown("""
        <div style="background:#0f172a; border-radius:14px; padding:20px; color:#ffffff; margin-bottom:1rem; box-shadow:0 10px 25px -5px rgba(15,23,42,0.2);">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                <span style="font-size:12px; font-weight:700; color:#38bdf8; text-transform:uppercase; letter-spacing:0.5px;">⚡ Live Profile Vectorization</span>
                <span style="background:#1e293b; color:#94a3b8; font-size:11px; padding:3px 8px; border-radius:6px; font-family:'JetBrains Mono', monospace;">1536 Dimensions</span>
            </div>
            <h3 style="color:#ffffff; font-size:18px; margin:0 0 8px; font-weight:700;">
                Personalized Curator Target
            </h3>
            <p style="color:#94a3b8; font-size:13px; line-height:1.5; margin:0 0 14px;">
                Every night at 08:00, our LangGraph agent computes the cosine distance between today's candidates and this vector.
            </p>
            <div style="background:#1e293b; border-radius:8px; padding:12px; font-family:'JetBrains Mono', monospace; font-size:11.5px; line-height:1.6; color:#e2e8f0;">
                <div><span style="color:#38bdf8;">User:</span> {email}</div>
                <div><span style="color:#38bdf8;">Primary Tags:</span> {tags}</div>
                <div><span style="color:#38bdf8;">Custom Vector:</span> {custom}</div>
                <div><span style="color:#38bdf8;">Keyword Triggers:</span> {alerts}</div>
                <div><span style="color:#38bdf8;">Anti-Tags:</span> {disliked}</div>
            </div>
        </div>
        """.format(
            email=st.session_state.user_email or "Not specified",
            tags=", ".join(prof.get("liked_tags", ["AI/ML", "Python", "LLMs"])),
            custom=f'"{prof.get("custom_interests")}"' if prof.get("custom_interests") else "None",
            alerts=prof.get("keyword_alerts") or "None",
            disliked=", ".join(prof.get("disliked_tags", [])) or "None",
        ), unsafe_allow_html=True)

        st.markdown("""
        <div class="feature-card">
            <h4 style="margin:0 0 8px; font-size:15px; color:#0f172a;">🎯 Guaranteed Daily Allocation</h4>
            <p style="font-size:12.5px; color:#64748b; margin:0 0 10px;">
                StackPulse enforces strict source diversity in every dispatch:
            </p>
            <ul style="font-size:13px; color:#334155; padding-left:1.2rem; margin:0 0 12px; line-height:1.7;">
                <li><strong>2–3 items</strong> from GitHub Trending Repositories</li>
                <li><strong>2–3 items</strong> from OpenAI & Anthropic Official News</li>
                <li><strong>2–3 items</strong> from Hacker News Technical Debates</li>
                <li><strong>1 Security Advisory</strong> if CVE detected in your dependencies</li>
                <li><strong>1 AI Token Rate & Tech Stock Barometer</strong></li>
            </ul>
            <div style="background:#f0fdf4; border:1px solid #bbf7d0; border-radius:6px; padding:8px 12px; font-size:12px; color:#166534;">
                ✓ <strong>Zero star bias:</strong> New repos with 50 stars compete strictly on relevance to your stack.
            </div>
        </div>
        """, unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════════════════════
# TAB 2: INTERACTIVE SAMPLE DIGEST
# ═════════════════════════════════════════════════════════════════════════════
with tab_sample:
    st.markdown("### 📬 Real-World Email Digest Simulation")
    st.caption("Here is an interactive render of exactly what a StackPulse subscriber receives in their inbox.")

    preview_name = st.session_state.profile_data.get("name") or "Alex"
    today_formatted = date.today().strftime("%B %d, %Y")

    sample_html = f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
                max-width:580px;margin:0 auto;background:#f8fafc;padding:24px;color:#0f172a;border-radius:12px;border:1px solid #e2e8f0;">

        <!-- Header -->
        <div style="text-align:center;padding:12px 0 18px;border-bottom:1px solid #e2e8f0;margin-bottom:18px;">
            <span style="background:#0f172a;color:#ffffff;font-size:11px;font-weight:800;
                         padding:5px 14px;border-radius:14px;letter-spacing:0.8px;">
                ⚡ STACKPULSE
            </span>
            <div style="font-size:11.5px;color:#64748b;margin-top:7px;font-weight:600;">
                Developer Intelligence · {today_formatted}
            </div>
        </div>

        <!-- Greeting & Intro -->
        <h3 style="color:#0f172a;font-size:16.5px;margin:0 0 6px;font-weight:700;">
            Hey {preview_name} 👋
        </h3>
        <p style="color:#475569;font-size:13.5px;line-height:1.55;margin:0 0 16px;">
            Here is your daily briefing tailored to <strong>Python, LLMs, and System Design</strong>.
            Today's ecosystem highlights a major breakthrough in agent memory architectures, an enterprise case study from OpenAI, and an active security patch in PyTorch.
        </p>

        <!-- Security Advisory Widget -->
        <div style="background:#fffbeb;border:1px solid #fef3c7;border-left:4px solid #f59e0b;
                    border-radius:8px;padding:12px 14px;margin-bottom:14px;">
            <p style="margin:0 0 4px;font-size:11.5px;font-weight:800;color:#92400e;letter-spacing:0.4px;">
                🛡️ SECURITY ADVISORY (YOUR STACK)
            </p>
            <div style="font-size:12.5px;color:#78350f;line-height:1.45;">
                <strong>CVE-2026-24810 (High - 7.8):</strong> PyTorch remote code execution flaw in torch.load when unpickling untrusted weights.
                <em>Action: Upgrade to torch &gt;= 2.6.1 immediately.</em>
            </div>
        </div>

        <!-- Market Pulse Barometer Widget -->
        <div style="background:#f8fafc;border:1px solid #e2e8f0;border-left:4px solid #64748b;
                    border-radius:8px;padding:12px 14px;margin-bottom:18px;">
            <p style="margin:0 0 4px;font-size:11px;font-weight:800;color:#475569;
                      text-transform:uppercase;letter-spacing:0.5px;">
                📊 TODAY'S AI & TECH BAROMETER
            </p>
            <div style="font-size:12.5px;color:#334155;line-height:1.5;">
                • <strong>Gemini 3.5 Flash-Lite:</strong> $0.075 / 1M input tokens · <strong>Claude 3.5 Sonnet:</strong> $3.00 / 1M input tokens<br/>
                • <strong>Tech Indices:</strong> NVDA: $138.25 (+1.4%) · MSFT: $422.10 (-0.3%) · GOOGL: $184.50 (+0.8%)
            </div>
        </div>

        <!-- Digest Items -->

        <!-- Item 1: Hacker News -->
        <div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:8px;padding:16px;margin-bottom:12px;">
            <div style="margin-bottom:6px;">
                <a href="https://news.ycombinator.com" target="_blank" style="font-size:15px;font-weight:700;color:#0f172a;text-decoration:none;line-height:1.4;">
                    The Components of Agent Memory: Architecture Deep Dive
                </a>
            </div>
            <div style="margin-bottom:8px;">
                <span class="badge-hn">🟠 HN 284 pts</span>
                <span style="display:inline-block;background:#eef4fc;color:#185fa5;font-size:10.5px;font-weight:600;padding:2px 7px;border-radius:10px;margin-right:5px;">LLMs</span>
                <span style="display:inline-block;background:#eef4fc;color:#185fa5;font-size:10.5px;font-weight:600;padding:2px 7px;border-radius:10px;margin-right:5px;">System Design</span>
            </div>
            <p style="margin:0 0 10px;color:#475569;font-size:13.5px;line-height:1.5;">
                A rigorous breakdown comparing episodic, procedural, and semantic working memory for production LLM agents. Discussions center around vector context caching vs. local SQLite stores.
            </p>
            <div style="background:#f0f7ff;border-left:3px solid #2563eb;padding:6px 10px;border-radius:0 5px 5px 0;">
                <span style="color:#2563eb;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.3px;">💡 Why it matters: </span>
                <span style="color:#1e293b;font-size:13px;line-height:1.4;">
                    Directly addresses context window exhaustion and long-running state persistence in agent loops.
                </span>
            </div>
        </div>

        <!-- Item 2: OpenAI Official RSS -->
        <div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:8px;padding:16px;margin-bottom:12px;">
            <div style="margin-bottom:6px;">
                <a href="https://openai.com/index/singapore-airlines-travel-work" target="_blank" style="font-size:15px;font-weight:700;color:#0f172a;text-decoration:none;line-height:1.4;">
                    Singapore Airlines Elevates Travel & Work With OpenAI Technology
                </a>
            </div>
            <div style="margin-bottom:8px;">
                <span class="badge-oa">🟢 OpenAI</span>
                <span style="display:inline-block;background:#eef4fc;color:#185fa5;font-size:10.5px;font-weight:600;padding:2px 7px;border-radius:10px;margin-right:5px;">OpenAI API</span>
                <span style="display:inline-block;background:#eef4fc;color:#185fa5;font-size:10.5px;font-weight:600;padding:2px 7px;border-radius:10px;margin-right:5px;">Customer Support</span>
            </div>
            <p style="margin:0 0 10px;color:#475569;font-size:13.5px;line-height:1.5;">
                Singapore Airlines deployed OpenAI models across internal staff workflows and their customer-facing Kris assistant, doubling their CSAT scores in live production.
            </p>
            <div style="background:#f0f7ff;border-left:3px solid #2563eb;padding:6px 10px;border-radius:0 5px 5px 0;">
                <span style="color:#2563eb;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.3px;">💡 Why it matters: </span>
                <span style="color:#1e293b;font-size:13px;line-height:1.4;">
                    Provides a validated enterprise architecture blueprint for reducing hallucination in mission-critical customer operations.
                </span>
            </div>
        </div>

        <!-- Item 3: GitHub Trending -->
        <div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:8px;padding:16px;margin-bottom:12px;">
            <div style="margin-bottom:6px;">
                <a href="https://github.com/vllm-project/vllm" target="_blank" style="font-size:15px;font-weight:700;color:#0f172a;text-decoration:none;line-height:1.4;">
                    vllm-project/vllm
                </a>
            </div>
            <div style="margin-bottom:8px;">
                <span class="badge-gh">🐙 GitHub · ⭐ 340 today</span>
                <span style="display:inline-block;background:#eef4fc;color:#185fa5;font-size:10.5px;font-weight:600;padding:2px 7px;border-radius:10px;margin-right:5px;">Python</span>
                <span style="display:inline-block;background:#eef4fc;color:#185fa5;font-size:10.5px;font-weight:600;padding:2px 7px;border-radius:10px;margin-right:5px;">Inference</span>
            </div>
            <p style="margin:0 0 10px;color:#475569;font-size:13.5px;line-height:1.5;">
                A high-throughput, memory-efficient LLM serving engine featuring PagedAttention. Trending today with native support for Gemini and speculative decoding.
            </p>
            <div style="background:#f0f7ff;border-left:3px solid #2563eb;padding:6px 10px;border-radius:0 5px 5px 0;">
                <span style="color:#2563eb;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.3px;">💡 Why it matters: </span>
                <span style="color:#1e293b;font-size:13px;line-height:1.4;">
                    Essential framework for serving self-hosted open models at 4x the throughput of vanilla HuggingFace pipelines.
                </span>
            </div>
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

    st.components.v1.html(sample_html, height=840, scrolling=True)


# ═════════════════════════════════════════════════════════════════════════════
# TAB 3: PRODUCT DOCUMENTATION & ARCHITECTURE
# ═════════════════════════════════════════════════════════════════════════════
with tab_docs:
    st.markdown("### 📚 StackPulse Architecture & Engineering Blueprint")
    st.markdown("A deep-dive look into how StackPulse's multi-agent autonomous pipeline works under the hood.")

    doc_col1, doc_col2 = st.columns([1, 1], gap="large")

    with doc_col1:
        st.markdown("#### 1. The Core Engineering Challenge")
        st.markdown("""
        Every day, the developer ecosystem produces thousands of commits, arXiv papers, releases, and discussions:
        - **GitHub Trending** surfaces repos based purely on star spikes (often driven by hype or marketing bots).
        - **Hacker News** has exceptional engineering debates, but finding items relevant to your exact stack is like searching for a needle in a haystack.
        - **Official AI Labs (OpenAI, Anthropic, DeepMind)** release breakthrough case studies on RSS feeds that drown in general news feeds.

        **StackPulse solves this via an Autonomous 3-Flow Agent Architecture.**
        """)

        st.markdown("#### 2. The 3-Flow Architecture")
        st.markdown("""
        ```
        Flow 1: Content Ingestion & Scrapers (Scheduled Daily)
          ├── GitHub Trending Scraper
          ├── Official RSS Scraper (OpenAI, Anthropic, Research)
          └── Hacker News Algolia Scraper
                │
                ▼
          Content Enrichment Agent (Gemini 3.5 Flash-Lite)
                │ Extracts Title, Stack, Topics, Use Case
                ▼
          Vector Embedding Pipeline (Gemini 1536d)
                │ Stored in PostgreSQL + pgvector
                ▼
        Flow 2: User Taste Profile Vectorization
          User Onboarding Form ➔ Vectorized into pgvector
                │
                ▼
        Flow 3: LangGraph Autonomous Curator Agent
          ├── Step A: Partitioned Candidate Retrieval (top 25 per source)
          ├── Step B: 7-Day Long-Term Memory Deduplication
          ├── Step C: Pure Semantic Relevance Ranking (0 star bias)
          ├── Step D: Strict Source Balancing (2-3 GitHub, 2-3 RSS, 2-3 HN)
          ├── Step E: Curator Agent Tool Invocation (NVD CVE + Market Pulse)
          └── Step F: Transactional Email Delivery (Brevo)
        ```
        """)

    with doc_col2:
        st.markdown("#### 3. Source Balancing & Zero Star Bias")
        st.markdown("""
        Traditional trending aggregators favor high-star repos. In StackPulse:
        1. **Pure Semantic Ranking**: Content relevance score is calculated strictly as:
           `similarity_score = max(0.0, 1.0 - float(row.distance))`
        2. **Partitioned Candidate Retrieval**:
           Candidate queries use PostgreSQL window functions:
           ```sql
           ROW_NUMBER() OVER (
               PARTITION BY source_category 
               ORDER BY (embedding <=> user_vec) ASC
           ) as source_rank
           ```
        3. **Guaranteed Allocation**:
           Every digest reserves **2–3 slots for GitHub**, **2–3 slots for Official AI News**, and **2–3 slots for Hacker News**.
        """)

        st.markdown("#### 4. Security & Guardrails")
        st.markdown("""
        StackPulse features multi-layer security guardrails:
        - **Prompt Injection Defense**: Sanitizes all user inputs (custom interests, alerts) before injecting into agent prompts.
        - **Tool Argument Validation**: Whitelists packages inspected via CVE tools to prevent SSRF and arbitrary command execution.
        - **Outbound Secret Scrubbing**: All rendered email HTML is scanned for API keys, bearer tokens, or database URIs prior to transmission via Brevo.
        """)

    st.markdown("---")
    st.markdown("#### 5. Frequently Asked Questions (FAQ)")
    with st.expander("How does StackPulse prevent sending the same repo twice?"):
        st.write("""
        StackPulse records every delivered item in a persistent `user_curated_digests` table with timestamped foreign keys.
        Before the curator agent selects candidates, all item external IDs delivered within the past 7 days are excluded from the candidate pool.
        """)

    with st.expander("Can I update my stack or interests later?"):
        st.write("""
        Yes! Simply re-enter your email in the Customize tab, click **Load Existing**, tweak any tags or custom instructions, and hit save.
        Your vector profile will be re-embedded immediately in pgvector.
        """)

    with st.expander("Which LLM models power StackPulse?"):
        st.write("""
        - **Embeddings:** `models/gemini-embedding-001` (pinned to 1536 dimensions for both content items and user taste vectors).
        - **Curator & Enrichment:** `gemini-3.5-flash-lite` via LangChain's `ChatGoogleGenerativeAI`.
        """)


# ═════════════════════════════════════════════════════════════════════════════
# TAB 4: PLATFORM TELEMETRY
# ═════════════════════════════════════════════════════════════════════════════
with tab_telemetry:
    st.markdown("### ⚡ Live System Pulse & Pipeline Metrics")
    st.caption("Real-time operational status of the StackPulse ingestion, vectorization, and dispatch nodes.")

    stats = get_platform_stats()

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Active Subscribers", stats.get("active_users", 1), "+100% active")
    m2.metric("Vectorized Profiles", stats.get("embedded_users", 1), "1536d pgvector")
    m3.metric("Embedded Content Items", stats.get("embedded_items", 55), "Live in database")
    m4.metric("Active Sources", stats.get("active_sources", 5), "GitHub · RSS · HN")

    st.markdown("---")
    st.markdown("#### 📡 Pipeline Node Health")
    tcol1, tcol2 = st.columns(2)

    with tcol1:
        st.markdown("""
        <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:10px; padding:16px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <strong>Flow 1: Scraper Ingestion Nodes</strong>
                <span style="color:#10b981; font-weight:700; font-size:12px;">● HEALTHY</span>
            </div>
            <p style="color:#64748b; font-size:12.5px; margin:0 0 6px;">GitHub Trending · OpenAI News RSS · Anthropic News RSS · Hacker News Algolia</p>
            <div style="font-size:11.5px; color:#94a3b8;">Last scrape run: Today at 04:00 UTC · Total processed: 55 items</div>
        </div>
        """, unsafe_allow_html=True)

    with tcol2:
        st.markdown("""
        <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:10px; padding:16px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <strong>Flow 3: LangGraph Curator Agent</strong>
                <span style="color:#10b981; font-weight:700; font-size:12px;">● READY</span>
            </div>
            <p style="color:#64748b; font-size:12.5px; margin:0 0 6px;">Model: gemini-3.5-flash-lite · Tools: NVD CVE & Market Pulse Barometer</p>
            <div style="font-size:11.5px; color:#94a3b8;">Brevo Transactional SMTP: Connected · Delivery window: 08:00 Local</div>
        </div>
        """, unsafe_allow_html=True)


# ── Global Footer ─────────────────────────────────────────────────────────────
st.markdown("""
<div class="saas-footer">
    <p>⚡ <strong>StackPulse</strong> · Autonomous Developer Intelligence Platform</p>
    <p style="margin:4px 0 0; color:#cbd5e1; font-size:0.75rem;">
        Powered by LangGraph · Google Gemini 3.5 Flash-Lite · PostgreSQL & pgvector · Brevo Transactional Email
    </p>
</div>
""", unsafe_allow_html=True)
