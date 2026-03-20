import streamlit as st
from database import get_accounts
from portfolio import calculate_portfolio_summary
from components.news import render_news_panel
from i18n import t

_TITLE_STYLE = "margin:0 0 6px 0;font-size:1.75rem;font-weight:800;color:#1a1a2e;"
_HR = "<hr style='border-color:#e8eaed;margin:0.75rem 0 1rem 0;'>"


def show(account_id: int, account_name: str, currency: str):
    accounts = get_accounts()
    account_names = accounts["name"].tolist()
    account_ids = accounts["id"].tolist()
    cur_idx = st.session_state.get("selected_account_idx", 0)
    cur_idx = min(cur_idx, len(account_names) - 1)

    # Pre-fetch tickers so news panel can start immediately
    summary = calculate_portfolio_summary(int(account_ids[cur_idx]))
    tickers = tuple(summary["holdings"]["ticker"].tolist()) if not summary["holdings"].empty else ()

    # ── Top-level split — news starts from the very top ───────────────────────
    col_main, col_news = st.columns([3, 1], gap="large")

    with col_news:
        render_news_panel(tickers)

    with col_main:
        # Title
        st.markdown(f"<p style='{_TITLE_STYLE}'>📊 My Portfolio</p>", unsafe_allow_html=True)

        # Selector row
        sel_col, _ = st.columns([2, 3])
        with sel_col:
            selected = st.selectbox(
                "account",
                options=account_names,
                index=cur_idx,
                key="account_selector",
                label_visibility="collapsed",
            )
        new_idx = account_names.index(selected)
        if new_idx != cur_idx:
            st.session_state.selected_account_idx = new_idx
            st.rerun()

        account_id = int(account_ids[new_idx])
        account_name = account_names[new_idx]
        currency = str(accounts.iloc[new_idx]["currency"])

        st.markdown(_HR, unsafe_allow_html=True)

        # Tabs
        tab_overview, tab_trade, tab_analytics, tab_rebalancer, tab_watchlist, tab_settings = st.tabs([
            f"📊 {t('nav_dashboard')}",
            f"📝 {t('nav_trade')}",
            f"📈 {t('nav_analytics')}",
            f"⚖️ {t('nav_rebalancer')}",
            f"👁 {t('nav_watchlist')}",
            f"⚙️ {t('nav_portfolio')}",
        ])

        with tab_overview:
            from views.dashboard import render_overview
            render_overview(account_id, currency)

        with tab_trade:
            from views.trade_entry import show as trade_show
            trade_show(account_id, account_name, currency, embedded=True)

        with tab_analytics:
            from views.analytics import show as analytics_show
            analytics_show(account_id, account_name, currency, embedded=True)

        with tab_rebalancer:
            from views.rebalancer import show as rebalancer_show
            rebalancer_show(account_id, account_name, currency, embedded=True)

        with tab_watchlist:
            from views.watchlist import show as watchlist_show
            watchlist_show(account_id, account_name, currency, embedded=True)

        with tab_settings:
            from views.accounts import show as accounts_show
            accounts_show(account_id, account_name, currency, embedded=True)
