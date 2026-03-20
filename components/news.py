import streamlit as st
from market_data import fetch_portfolio_news
from i18n import t


def render_news_panel(tickers: tuple):
    """Shared news feed panel for any view."""
    st.markdown(
        f"<div style='font-size:0.75rem;font-weight:700;color:#9ca3af;"
        f"text-transform:uppercase;letter-spacing:0.1em;margin-bottom:8px;'>"
        f"{t('dash_news_title')}</div>",
        unsafe_allow_html=True,
    )

    if not tickers:
        st.caption(t("dash_news_empty"))
        return

    news = fetch_portfolio_news(tickers)

    if not news:
        st.caption(t("dash_news_none"))
        return

    for item in news:
        _news_card(item)

    st.markdown(
        f"<div style='font-size:0.68rem;color:#9ca3af;margin-top:8px;'>"
        f"{t('dash_news_footer')}</div>",
        unsafe_allow_html=True,
    )


def _news_card(item: dict):
    ticker = item.get("ticker", "")
    title = item.get("title", "")
    source = item.get("source", "")
    url = item.get("url", "#")
    age = item.get("age", "")

    badge_bg = "#e6f9f4" if ticker.endswith(".TO") else "#eff6ff"
    badge_fg = "#00b386" if ticker.endswith(".TO") else "#3b82f6"

    st.markdown(
        f"""
        <a href="{url}" target="_blank" style="text-decoration:none;">
          <div style="
            background:#ffffff;
            border:1px solid #e8eaed;
            border-radius:10px;
            padding:10px 12px;
            margin-bottom:8px;
            transition:box-shadow 0.15s;
          ">
            <div style="display:flex;align-items:center;gap:6px;margin-bottom:5px;">
              <span style="background:{badge_bg};color:{badge_fg};
                font-size:0.68rem;font-weight:700;padding:1px 7px;
                border-radius:5px;">{ticker}</span>
              <span style="color:#9ca3af;font-size:0.68rem;">{age}</span>
            </div>
            <div style="font-size:0.8rem;font-weight:500;color:#1a1a2e;
              line-height:1.4;">{title}</div>
            <div style="font-size:0.68rem;color:#9ca3af;margin-top:4px;">{source}</div>
          </div>
        </a>
        """,
        unsafe_allow_html=True,
    )
