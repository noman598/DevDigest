"""
app.py — DevDigest Frontend
User onboarding and preference collection for developer news digest.
"""
# import sys
# import os

# # Add the root directory to Python path so we can import storage
# sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import re
from datetime import datetime
from typing import List, Dict, Optional
import streamlit as st
import json

from storage.db import save_user_email  # Add this import at top

# ── Database Functions (Placeholder) ──────────────────────────────────────────
# These will be implemented later with your actual database
def save_user_profile(email: str, name: str, preferences: dict) -> bool:
    """
    Save user profile and preferences to database.
    Returns True if successful.
    """
    # TODO: Implement database storage
    # Example: 
    # db.users.insert_one({
    #     "email": email,
    #     "name": name,
    #     "preferences": preferences,
    #     "created_at": datetime.utcnow(),
    #     "updated_at": datetime.utcnow(),
    #     "active": True
    # })
    return True

def user_exists(email: str) -> bool:
    """Check if user already exists in database."""
    # TODO: Implement database check
    return False

# ── Page Configuration ────────────────────────────────────────────────────────
st.set_page_config(
    page_title="DevSnack - Daily AI-Curated Developer News",
    page_icon="🤖",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ── Custom CSS ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Main container */
    .main > div {
        padding-top: 0rem;
    }
    
    /* Card-like containers */
    .pref-card {
        background: white;
        padding: 1.5rem;
        border-radius: 10px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        margin-bottom: 1.5rem;
        border: 1px solid #f0f2f6;
    }
    
    /* Source badges */
    .source-badge {
        display: inline-block;
        background: #f0f2f6;
        border-radius: 6px;
        padding: 4px 12px;
        font-size: 0.8rem;
        margin-right: 6px;
        margin-bottom: 6px;
        color: #333;
        border: 1px solid #e0e0e0;
    }
    
    .source-badge.selected {
        background: #FF4B4B;
        color: white;
        border-color: #FF4B4B;
    }
    
    .topic-tag {
        display: inline-block;
        background: #e8f0fe;
        border-radius: 15px;
        padding: 4px 12px;
        font-size: 0.8rem;
        margin: 3px;
        color: #1a73e8;
    }
    
    /* Progress indicator */
    .step-indicator {
        display: flex;
        justify-content: space-between;
        margin-bottom: 2rem;
        padding: 0 1rem;
    }
    
    .step {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        color: #999;
        font-size: 0.85rem;
    }
    
    .step.active {
        color: #FF4B4B;
        font-weight: 600;
    }
    
    .step.completed {
        color: #00a65a;
    }
    
    .step-number {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 28px;
        height: 28px;
        border-radius: 50%;
        background: #e0e0e0;
        color: white;
        font-size: 0.8rem;
        font-weight: 600;
    }
    
    .step.active .step-number {
        background: #FF4B4B;
    }
    
    .step.completed .step-number {
        background: #00a65a;
    }
    
    /* Form sections */
    .form-section {
        background: #fafafa;
        padding: 1.5rem;
        border-radius: 8px;
        margin: 1rem 0;
    }
    
    /* Success animation */
    .success-check {
        font-size: 4rem;
        text-align: center;
        animation: bounce 1s ease;
    }
    
    @keyframes bounce {
        0%, 100% { transform: scale(1); }
        50% { transform: scale(1.2); }
    }
    
    /* Footer */
    .footer {
        text-align: center;
        color: #999;
        font-size: 0.8rem;
        margin-top: 3rem;
        padding: 1rem;
        border-top: 1px solid #f0f2f6;
    }
    
    /* Mobile responsive */
    @media (max-width: 640px) {
        .step-indicator {
            flex-direction: column;
            gap: 0.5rem;
        }
        .pref-card {
            padding: 1rem;
        }
    }
</style>
""", unsafe_allow_html=True)

# ── Initialize Session State ─────────────────────────────────────────────────
if 'current_step' not in st.session_state:
    st.session_state.current_step = 1

if 'form_data' not in st.session_state:
    st.session_state.form_data = {}

if 'submitted' not in st.session_state:
    st.session_state.submitted = False

# ── Constants ─────────────────────────────────────────────────────────────────
SOURCES = {
    "github_trending": {
        "label": "GitHub Trending",
        "icon": "🐙",
        "description": "Top repositories trending in the last 24 hours"
    },
    "hacker_news": {
        "label": "Hacker News",
        "icon": "🔶",
        "description": "Top stories from Hacker News"
    },
    "youtube": {
        "label": "YouTube",
        "icon": "▶️",
        "description": "Trending developer & tech videos"
    },
    "reddit": {
        "label": "Reddit",
        "icon": "🤖",
        "description": "Best posts from tech subreddits"
    },
    "product_hunt": {
        "label": "Product Hunt",
        "icon": "🚀",
        "description": "Top product launches of the day"
    },
    "dev_to": {
        "label": "Dev.to",
        "icon": "💻",
        "description": "Popular developer articles and tutorials"
    },
    "medium": {
        "label": "Medium",
        "icon": "📝",
        "description": "Top tech stories from Medium"
    },
    "devops": {
        "label": "DevOps Digest",
        "icon": "⚡",
        "description": "DevOps and cloud native updates"
    }
}

INTEREST_TAGS = [
    "AI/ML", "Web Development", "DevOps/Cloud", "Cybersecurity", 
    "Open Source", "Python", "JavaScript", "TypeScript", "Rust", "Go",
    "System Design", "Databases", "Mobile Development", "Startups", 
    "Career Growth", "LLMs", "Web3", "Embedded/IoT", "Data Science",
    "Frontend", "Backend", "Full Stack", "Testing", "Performance",
    "Architecture", "Leadership", "Remote Work"
]

FREQUENCY_OPTIONS = {
    "daily": "Daily",
    "weekly": "Weekly",
    "weekdays": "Weekdays only"
}

TIME_OPTIONS = {
    "06:00": "6:00 AM",
    "07:00": "7:00 AM", 
    "08:00": "8:00 AM",
    "09:00": "9:00 AM",
    "10:00": "10:00 AM",
    "12:00": "12:00 PM",
    "18:00": "6:00 PM",
    "20:00": "8:00 PM"
}

# ── Helper Functions ──────────────────────────────────────────────────────────
def validate_email(email: str) -> bool:
    """Validate email format."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def go_to_step(step: int):
    """Navigate to a specific step."""
    st.session_state.current_step = step
    st.rerun()

def render_step_indicator(current_step: int):
    """Render the step progress indicator."""
    steps = [
        {"num": 1, "label": "Profile"},
        {"num": 2, "label": "Sources"},
        {"num": 3, "label": "Interests"},
        {"num": 4, "label": "Schedule"}
    ]
    
    cols = st.columns(len(steps))
    for idx, step in enumerate(steps):
        with cols[idx]:
            status = "active" if step["num"] == current_step else "completed" if step["num"] < current_step else ""
            st.markdown(f"""
            <div class="step {status}">
                <span class="step-number">{step['num']}</span>
                <span>{step['label']}</span>
            </div>
            """, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# MAIN APP
# ─────────────────────────────────────────────────────────────────────────────

# ── Header ───────────────────────────────────────────────────────────────────
st.markdown("""
<div style="text-align: center; margin-bottom: 2rem;">
    <h1 style="font-size: 3rem; margin-bottom: 0.5rem;">🤖 DevSnack</h1>
    <p style="font-size: 1.1rem; color: #666; max-width: 600px; margin: 0 auto;">
        Your daily bite-sized developer news, curated by AI and delivered to your inbox.
    </p>
    <p style="font-size: 0.9rem; color: #999; margin-top: 0.5rem;">
        ⚡ No more surfing multiple sites — get everything in one personalized email, every day.
    </p>
</div>
""", unsafe_allow_html=True)

# ── Success State ────────────────────────────────────────────────────────────
if st.session_state.submitted:
    st.balloons()
    st.markdown("""
    <div class="success-check">✅</div>
    <div style="text-align: center; padding: 2rem;">
        <h2 style="color: #00a65a;">You're all set! 🎉</h2>
        <p style="font-size: 1.1rem; color: #555; max-width: 500px; margin: 1rem auto;">
            We'll start sending your personalized digest to 
            <strong>{}</strong> on your preferred schedule.
        </p>
        <div style="background: #f0f8ff; padding: 1rem; border-radius: 8px; margin: 1.5rem auto; max-width: 400px;">
            <p style="margin: 0; color: #0066cc;">
                💡 Tip: Add <strong>devdigest@yourdomain.com</strong> to your contacts
                to ensure our emails don't go to spam.
            </p>
        </div>
        <p style="color: #999; font-size: 0.9rem;">
            You can update your preferences anytime by visiting this page again.
        </p>
    </div>
    """.format(st.session_state.form_data.get('email', 'your email')), unsafe_allow_html=True)
    
    if st.button("📝 Update Preferences", type="primary"):
        st.session_state.submitted = False
        st.session_state.current_step = 1
        st.rerun()
    
    st.stop()

# ── Step Indicator ───────────────────────────────────────────────────────────
render_step_indicator(st.session_state.current_step)
st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: PROFILE
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.current_step == 1:
    st.markdown("### 👤 Your Profile")
    st.markdown("Tell us who you are and how to reach you.")
    
    with st.container():
        col1, col2 = st.columns(2)
        
        with col1:
            email = st.text_input(
                "Email Address *",
                placeholder="you@example.com",
                value=st.session_state.form_data.get('email', ''),
                help="We'll send your digest to this address"
            )
            
            if email and not validate_email(email):
                st.warning("Please enter a valid email address.")
        
        with col2:
            name = st.text_input(
                "Your Name",
                placeholder="Alex Johnson",
                value=st.session_state.form_data.get('name', ''),
                help="How should we address you in the emails?"
            )
        
        # Store in session
        if email and validate_email(email):
            st.session_state.form_data['email'] = email
        if name:
            st.session_state.form_data['name'] = name
        
        # Check if user exists
        if email and validate_email(email) and user_exists(email):
            st.info("ℹ️ We found an existing profile for this email. You can update your preferences.")
    
    st.markdown("---")
    
    col_btn1, col_btn2 = st.columns([1, 1])
    with col_btn2:
        if st.button("Next →", type="primary", use_container_width=True):
            if not email or not validate_email(email):
                st.error("Please enter a valid email address.")
            else:
                go_to_step(2)

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: SOURCES
# ─────────────────────────────────────────────────────────────────────────────
elif st.session_state.current_step == 2:
    st.markdown("### 📡 News Sources")
    st.markdown("Select the sources you want to include in your digest.")
    
    with st.container():
        st.markdown("#### Choose your sources")
        
        st.info("ℹ️ **Note:** Currently we support **GitHub Trending** only. More sources coming soon! 🚀")
        # Initialize selected sources
        if 'selected_sources' not in st.session_state.form_data:
            st.session_state.form_data['selected_sources'] = ['github_trending', 'hacker_news']
        
        # Display sources in a grid
        cols = st.columns(3)
        source_keys = list(SOURCES.keys())
        
        for idx, key in enumerate(source_keys):
            source = SOURCES[key]
            col = cols[idx % 3]
            
            with col:
                is_selected = key in st.session_state.form_data.get('selected_sources', [])
                
                # Custom checkbox with card style
                if st.checkbox(
                    f"{source['icon']} {source['label']}",
                    value=is_selected,
                    help=source['description'],
                    key=f"source_{key}"
                ):
                    if key not in st.session_state.form_data['selected_sources']:
                        st.session_state.form_data['selected_sources'].append(key)
                else:
                    if key in st.session_state.form_data.get('selected_sources', []):
                        st.session_state.form_data['selected_sources'].remove(key)
                
                st.caption(source['description'])
    
    st.markdown("---")
    
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("← Back", use_container_width=True):
            go_to_step(1)
    with col_btn2:
        if st.button("Next →", type="primary", use_container_width=True):
            if not st.session_state.form_data.get('selected_sources'):
                st.error("Please select at least one source.")
            else:
                go_to_step(3)

# ─────────────────────────────────────────────────────────────────────────────
# STEP 3: INTERESTS
# ─────────────────────────────────────────────────────────────────────────────
elif st.session_state.current_step == 3:
    st.markdown("### 🎯 Your Interests")
    st.markdown("Help us personalize your digest. Tell us what topics you care about.")
    
    with st.container():
        # Liked topics
        st.markdown("#### 👍 Topics you're interested in")
        liked_tags = st.multiselect(
            "Select topics you want more of",
            INTEREST_TAGS,
            default=st.session_state.form_data.get('liked_tags', []),
            placeholder="Choose topics that interest you",
            key="liked_multiselect"
        )
        st.session_state.form_data['liked_tags'] = liked_tags
        
        # Disliked topics
        st.markdown("#### 👎 Topics to filter out")
        disliked_tags = st.multiselect(
            "Select topics you want less of",
            INTEREST_TAGS,
            default=st.session_state.form_data.get('disliked_tags', []),
            placeholder="Choose topics to minimize",
            key="disliked_multiselect"
        )
        st.session_state.form_data['disliked_tags'] = disliked_tags
        
        # Custom interests
        st.markdown("#### ✏️ Custom Interests")
        custom_interests = st.text_area(
            "Anything else you'd like us to focus on?",
            placeholder="e.g., WebAssembly, RAG pipelines, Kubernetes operators, ...",
            value=st.session_state.form_data.get('custom_interests', ''),
            help="List specific technologies or topics you're particularly interested in."
        )
        st.session_state.form_data['custom_interests'] = custom_interests
        
        # Keyword alerts
        st.markdown("#### 🔔 Keyword Alerts")
        keyword_alerts = st.text_input(
            "Always include items mentioning these keywords",
            placeholder="e.g., Rust, LLM, open source AI",
            value=st.session_state.form_data.get('keyword_alerts', ''),
            help="Comma-separated keywords. Items matching these will always appear in your digest."
        )
        st.session_state.form_data['keyword_alerts'] = keyword_alerts
    
    st.markdown("---")
    
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("← Back", use_container_width=True):
            go_to_step(2)
    with col_btn2:
        if st.button("Next →", type="primary", use_container_width=True):
            go_to_step(4)

# ─────────────────────────────────────────────────────────────────────────────
# STEP 4: SCHEDULE & REVIEW
# ─────────────────────────────────────────────────────────────────────────────
elif st.session_state.current_step == 4:
    st.markdown("### ⏰ Schedule & Review")
    st.markdown("Configure when you want to receive your digest.")
    
    with st.container():
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### Schedule")
            frequency = st.selectbox(
                "Frequency",
                options=list(FREQUENCY_OPTIONS.keys()),
                format_func=lambda x: FREQUENCY_OPTIONS[x],
                index=list(FREQUENCY_OPTIONS.keys()).index(
                    st.session_state.form_data.get('frequency', 'daily')
                ),
                key="frequency_select"
            )
            st.session_state.form_data['frequency'] = frequency
            
            delivery_time = st.selectbox(
                "Preferred delivery time",
                options=list(TIME_OPTIONS.keys()),
                format_func=lambda x: TIME_OPTIONS[x],
                index=list(TIME_OPTIONS.keys()).index(
                    st.session_state.form_data.get('delivery_time', '08:00')
                ),
                key="time_select"
            )
            st.session_state.form_data['delivery_time'] = delivery_time
        
        with col2:
            st.markdown("#### Additional Preferences")
            
            include_summary = st.checkbox(
                "Include AI-generated summaries",
                value=st.session_state.form_data.get('include_summary', True),
                help="Get AI-powered summaries of each article"
            )
            st.session_state.form_data['include_summary'] = include_summary
            
            include_why_matters = st.checkbox(
                "Include 'Why it matters' insights",
                value=st.session_state.form_data.get('include_why_matters', True),
                help="Get context on why each item is important"
            )
            st.session_state.form_data['include_why_matters'] = include_why_matters
    
    # ── Review Summary ──────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 📋 Review Your Settings")
    
    with st.expander("View all preferences", expanded=True):
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Profile**")
            st.write(f"📧 {st.session_state.form_data.get('email', 'Not set')}")
            st.write(f"👤 {st.session_state.form_data.get('name', 'Not provided')}")
            
            st.markdown("**Schedule**")
            st.write(f"📅 {FREQUENCY_OPTIONS.get(st.session_state.form_data.get('frequency', 'daily'), 'Daily')}")
            st.write(f"🕐 {TIME_OPTIONS.get(st.session_state.form_data.get('delivery_time', '08:00'), '8:00 AM')}")
        
        with col2:
            st.markdown("**Sources**")
            selected = st.session_state.form_data.get('selected_sources', [])
            if selected:
                for key in selected:
                    if key in SOURCES:
                        st.write(f"• {SOURCES[key]['icon']} {SOURCES[key]['label']}")
            else:
                st.write("No sources selected")
            
            st.markdown("**Interests**")
            liked = st.session_state.form_data.get('liked_tags', [])
            if liked:
                st.write(f"👍 {', '.join(liked[:3])}{'...' if len(liked) > 3 else ''}")
            else:
                st.write("All topics (no specific preferences)")
            
            if st.session_state.form_data.get('keyword_alerts'):
                st.write(f"🔔 Alerts: {st.session_state.form_data.get('keyword_alerts')}")
    
    st.markdown("---")
    
    # ── Submit ──────────────────────────────────────────────────────────────
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("← Back", use_container_width=True):
            go_to_step(3)
    
    # with col_btn2:
    #     if st.button("✅ Subscribe to DevDigest", type="primary", use_container_width=True):
    #         # Validate
    #         if not st.session_state.form_data.get('email'):
    #             st.error("Email is required.")
    #         elif not st.session_state.form_data.get('selected_sources'):
    #             st.error("Please select at least one source.")
    #         else:
    #             # Save to database
    #             with st.spinner("Saving your preferences..."):
    #                 success = save_user_profile(
    #                     email=st.session_state.form_data['email'],
    #                     name=st.session_state.form_data.get('name', ''),
    #                     preferences=st.session_state.form_data
    #                 )
                    
    #                 if success:
    #                     st.session_state.submitted = True
    #                     st.rerun()
    #                 else:
    #                     st.error("Failed to save preferences. Please try again.")
    with col_btn2:
        if st.button("🍿 Get My DevSnack", type="primary", use_container_width=True):
            # Validate
            if not st.session_state.form_data.get('email'):
                st.error("Email is required.")
            else:
                # Save email to database
                with st.spinner("Saving your email..."):
                    
                    success = save_user_email(st.session_state.form_data['email'])
                    
                    if success:
                        st.session_state.submitted = True
                        st.rerun()
                    else:
                        st.error("Failed to save. Please try again.")

# ── Footer ──────────────────────────────────────────────────────────────────
st.markdown("""
<div class="footer">
    <p>🤖 DevSnack · Your Daily AI-Curated Developer News</p>
    <p style="font-size: 0.75rem;">
        ⚡ Scrapes → Summarizes → Delivers · All in one email, every day
    </p>
    <p style="font-size: 0.75rem; color: #aaa;">
        We respect your privacy. No spam, unsubscribe anytime.
    </p>
</div>
""", unsafe_allow_html=True)