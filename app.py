import streamlit as st
from database import init_db, get_accounts
from i18n import t

# ── Language state — read from URL so it survives page navigation ───────────────
_lang_from_url = st.query_params.get("lang", "en")
if _lang_from_url not in ("en", "zh"):
    _lang_from_url = "en"
st.session_state["lang"] = _lang_from_url

# ── Page config (must be first Streamlit call) ─────────────────────────────────
st.set_page_config(
    page_title="QuantView",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Light theme CSS (Wealthsimple-inspired) ────────────────────────────────────
st.markdown(
    """
    <style>
    /* ── Hide Streamlit chrome ── */
    [data-testid="stHeader"]  { display: none !important; }
    [data-testid="stToolbar"] { display: none !important; }
    #MainMenu { visibility: hidden; }
    footer    { visibility: hidden; }
    header    { visibility: hidden; }

    /* ── Global ── */
    html, body, [class*="css"] {
        font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif;
    }
    .stApp { background-color: #f7f8fa; color: #1a1a2e; }
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 3rem;
        max-width: 1400px;
    }

    /* ── Sidebar ── */
    [data-testid="stSidebar"] {
        background-color: #ffffff !important;
        border-right: 1px solid #e8eaed;
    }
    [data-testid="stSidebar"] > div:first-child { padding-top: 0.5rem; }

    /* ── Metric cards ── */
    [data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid #e8eaed;
        border-radius: 12px;
        padding: 1.1rem 1.3rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }
    [data-testid="stMetricValue"] {
        color: #1a1a2e !important;
        font-size: 1.4rem !important;
        font-weight: 700 !important;
    }
    [data-testid="stMetricLabel"] {
        color: #6b7280 !important;
        font-size: 0.72rem !important;
        text-transform: uppercase !important;
        letter-spacing: 0.09em !important;
        font-weight: 600 !important;
    }
    [data-testid="stMetricDelta"] svg { display: none; }
    [data-testid="stMetricDelta"] { font-size: 0.82rem !important; font-weight: 600 !important; }

    /* ── Headings ── */
    h1 { color: #1a1a2e !important; font-size: 1.55rem; font-weight: 700; margin-bottom: 0.25rem; }
    h2 { color: #374151 !important; font-size: 1.05rem; font-weight: 600; margin-bottom: 0.25rem; }
    h3 { color: #6b7280 !important; font-size: 0.95rem; font-weight: 600; }

    /* ── Divider ── */
    hr { border-color: #e8eaed !important; margin: 1.25rem 0; }

    /* ── Buttons (main content) ── */
    .stButton > button {
        border-radius: 8px;
        font-weight: 600;
        font-size: 0.875rem;
        transition: all 0.18s ease;
        cursor: pointer;
    }
    .stButton > button[kind="primary"] {
        background: #00c896;
        color: #ffffff;
        border: none;
        box-shadow: 0 1px 4px rgba(0,200,150,0.35);
    }
    .stButton > button[kind="primary"]:hover {
        background: #00b386;
        box-shadow: 0 3px 10px rgba(0,200,150,0.4);
        transform: translateY(-1px);
    }
    .stButton > button[kind="secondary"] {
        background: #ffffff;
        border: 1px solid #d1d5db;
        color: #374151;
    }
    .stButton > button[kind="secondary"]:hover {
        border-color: #00c896;
        color: #00c896;
        background: #f0fdf9;
    }

    /* ── Labels (all form widgets) ── */
    label,
    .stTextInput > label,
    .stNumberInput > label,
    .stTextArea > label,
    .stSelectbox > label,
    .stMultiSelect > label,
    .stDateInput > label,
    .stRadio > label,
    .stCheckbox > label {
        color: #374151 !important;
        font-size: 0.85rem !important;
        font-weight: 500 !important;
    }

    /* ── Text / number / date inputs ── */
    .stTextInput input,
    .stNumberInput input,
    .stTextArea textarea,
    [data-testid="stDateInput"] input {
        background: #ffffff !important;
        color: #1a1a2e !important;
        border: 1px solid #d1d5db !important;
        border-radius: 8px !important;
    }
    .stTextInput input:focus,
    .stNumberInput input:focus,
    .stTextArea textarea:focus {
        border-color: #00c896 !important;
        box-shadow: 0 0 0 3px rgba(0,200,150,0.12) !important;
    }

    /* ── Selectbox / multiselect ── */
    [data-baseweb="select"] > div {
        background: #ffffff !important;
        border: 1px solid #d1d5db !important;
        border-radius: 8px !important;
        color: #1a1a2e !important;
    }
    [data-baseweb="select"] > div:focus-within { border-color: #00c896 !important; box-shadow: 0 0 0 3px rgba(0,200,150,0.12) !important; }
    [data-baseweb="popover"] { background: #ffffff !important; border: 1px solid #e8eaed !important; box-shadow: 0 4px 16px rgba(0,0,0,0.1) !important; border-radius: 10px !important; }
    [data-baseweb="menu"]    { background: #ffffff !important; }
    [data-baseweb="option"]  { color: #1a1a2e !important; }
    [data-baseweb="option"]:hover { background: #f0fdf9 !important; }
    [data-baseweb="tag"]     { background: #e6f9f4 !important; color: #00b386 !important; border-radius: 6px !important; }

    /* ── Dataframe ── */
    [data-testid="stDataFrame"] {
        border: 1px solid #e8eaed;
        border-radius: 12px;
        overflow: hidden;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }

    /* ── Forms ── */
    [data-testid="stForm"] {
        background: #ffffff;
        border: 1px solid #e8eaed;
        border-radius: 14px;
        padding: 1.5rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }

    /* ── Alerts ── */
    [data-testid="stAlert"] { border-radius: 10px; font-size: 0.875rem; }
    [data-testid="stAlert"][kind="info"]    { background: #eff6ff !important; border-color: #93c5fd !important; color: #1d4ed8 !important; }
    [data-testid="stAlert"][kind="success"] { background: #f0fdf4 !important; border-color: #86efac !important; color: #15803d !important; }
    [data-testid="stAlert"][kind="warning"] { background: #fffbeb !important; border-color: #fcd34d !important; color: #92400e !important; }
    [data-testid="stAlert"][kind="error"]   { background: #fef2f2 !important; border-color: #fca5a5 !important; color: #dc2626 !important; }

    /* ── Spinner ── */
    .stSpinner > div { border-top-color: #00c896 !important; }

    /* ── Sidebar: account selector label ── */
    [data-testid="stSidebar"] .stSelectbox > label {
        color: #9ca3af !important;
        font-size: 0.68rem !important;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        font-weight: 700;
        margin-bottom: 4px !important;
    }
    [data-testid="stSidebar"] [data-baseweb="select"] > div {
        background: #f7f8fa !important;
        border-color: #e8eaed !important;
        color: #1a1a2e !important;
    }

    /* ── Nav links ── */
    .qv-nav { display: flex; flex-direction: column; gap: 2px; margin: 0; padding: 0; }
    .qv-nav a {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 0.58rem 0.85rem;
        border-radius: 9px;
        color: #6b7280;
        font-size: 0.875rem;
        font-weight: 500;
        text-decoration: none;
        transition: background 0.15s ease, color 0.15s ease;
        line-height: 1.4;
    }
    .qv-nav a:hover  { background: #f3f4f6; color: #374151; }
    .qv-nav a.active { background: #e6f9f4; color: #00b386; font-weight: 600; }
    .qv-nav a.active:hover { background: #d1f5eb; }
    .qv-nav-icon { font-size: 0.95rem; width: 1.1rem; text-align: center; flex-shrink: 0; opacity: 0.8; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Bootstrap DB ───────────────────────────────────────────────────────────────
init_db()

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        """
        <div style='padding:1rem 0.5rem 0.5rem 0.5rem;'>
            <div style='font-size:1.35rem;font-weight:800;color:#00b386;letter-spacing:-0.02em;'>
                📈 QuantView
            </div>
            <div style='font-size:0.68rem;color:#9ca3af;letter-spacing:0.08em;text-transform:uppercase;margin-top:3px;font-weight:600;'>
                Investment Dashboard
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("<hr style='border-color:#e8eaed;margin:0.75rem 0;'>", unsafe_allow_html=True)

    # ── Language toggle ───────────────────────────────────────────────────────
    lang_col, _ = st.columns([1, 2])
    with lang_col:
        if st.button(t("lang_toggle"), key="lang_btn", use_container_width=True):
            new_lang = "zh" if st.session_state["lang"] == "en" else "en"
            st.session_state["lang"] = new_lang
            st.query_params["lang"] = new_lang
            st.rerun()

    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

    # ── Account state (selector lives inside My Portfolio page) ───────────────
    accounts = get_accounts()
    if accounts.empty:
        st.error("No accounts found. Restart the app to re-initialise.")
        st.stop()

    account_names = accounts["name"].tolist()
    account_ids = accounts["id"].tolist()

    if "selected_account_idx" not in st.session_state:
        st.session_state.selected_account_idx = 0

    idx = min(st.session_state.selected_account_idx, len(account_ids) - 1)
    account_id = int(account_ids[idx])
    selected_name = account_names[idx]
    currency = str(accounts.iloc[idx]["currency"])

    # ── Query-param driven nav (pure HTML <a> links) ─────────────────────────
    NAV_MY_PORTFOLIO = [
        ("myportfolio", "nav_myportfolio", "📊"),
    ]
    NAV_QUANT = [
        ("quant", "nav_quant", "⚡"),
    ]
    PAGE_KEYS = {k for k, _, _ in NAV_MY_PORTFOLIO + NAV_QUANT}
    # Legacy page keys still routable directly
    _ALL_KEYS = PAGE_KEYS | {"dashboard", "trade", "analytics", "rebalancer", "watchlist", "portfolio"}

    current_key = st.query_params.get("page", "myportfolio")
    # Redirect legacy sub-pages to the unified portfolio page
    if current_key in {"dashboard", "trade", "analytics", "rebalancer", "watchlist", "portfolio", "account"}:
        current_key = "myportfolio"
    if current_key not in PAGE_KEYS:
        current_key = "myportfolio"

    current_lang = st.session_state.get("lang", "en")

    def _nav_section(label: str, items: list) -> str:
        html = (
            f"<div style='font-size:0.68rem;color:#9ca3af;letter-spacing:0.1em;"
            f"text-transform:uppercase;font-weight:700;padding:0 4px 6px 4px;'>{label}</div>"
        )
        for key, label_key, icon in items:
            active_cls = "active" if key == current_key else ""
            html += (
                f'<a href="?page={key}&lang={current_lang}" class="{active_cls}" target="_self">'
                f'<span class="qv-nav-icon">{icon}</span>{t(label_key)}</a>'
            )
        return html

    st.markdown(
        f'<nav class="qv-nav">'
        f'{_nav_section(t("nav_section_portfolio"), NAV_MY_PORTFOLIO)}'
        f'<div style="margin:10px 0 6px 0;border-top:1px solid #e8eaed;"></div>'
        f'{_nav_section(t("nav_section_quant"), NAV_QUANT)}'
        f'</nav>',
        unsafe_allow_html=True,
    )

    st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)
    st.markdown(
        f"<p style='color:#9ca3af;font-size:0.7rem;padding:0 4px;line-height:1.8;'>"
        f"{t('nav_refresh_hint')}</p>",
        unsafe_allow_html=True,
    )

# ── Route to page ──────────────────────────────────────────────────────────────
if current_key == "myportfolio":
    from views.my_portfolio import show
    show(account_id, selected_name, currency)

elif current_key == "quant":
    from views.quant_portfolio import show
    show()
