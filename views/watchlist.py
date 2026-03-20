import streamlit as st
import pandas as pd
import numpy as np
from database import get_watchlist, add_to_watchlist, remove_from_watchlist
from market_data import fetch_current_prices, get_ticker_info
from i18n import t


def show(account_id: int, account_name: str, currency: str, embedded: bool = False):
    if not embedded:
        st.title(f"{t('watchlist_title')} — {account_name}")

    # ── Add ticker ─────────────────────────────────────────────────────────────
    st.subheader(t("watchlist_add"))
    with st.form("watchlist_add", clear_on_submit=True):
        col1, col2 = st.columns([3, 1])
        with col1:
            new_ticker = st.text_input(
                t("watchlist_ticker"),
                placeholder=t("watchlist_placeholder"),
                help=t("watchlist_ticker_help"),
            )
        with col2:
            st.markdown("<br>", unsafe_allow_html=True)
            add_btn = st.form_submit_button(t("watchlist_add_btn"), type="primary")

        if add_btn and new_ticker:
            clean = new_ticker.upper().strip()
            add_to_watchlist(account_id, clean)
            st.success(t("watchlist_added", ticker=clean))

    st.divider()

    # ── Watchlist table ────────────────────────────────────────────────────────
    watchlist = get_watchlist(account_id)

    if watchlist.empty:
        st.info(t("watchlist_empty"))
        return

    tickers = tuple(watchlist["ticker"].tolist())
    prices = fetch_current_prices(tickers)

    rows = []
    for _, wl_row in watchlist.iterrows():
        ticker = wl_row["ticker"]
        price = prices.get(ticker, float("nan"))
        info = get_ticker_info(ticker)
        rows.append({
            "id": wl_row["id"],
            "Ticker": ticker,
            t("watchlist_col_name"):    info.get("name", ticker),
            t("watchlist_col_price"):   price,
            t("watchlist_col_day"):     info.get("day_change"),
            t("watchlist_col_52h"):     info.get("week_52_high"),
            t("watchlist_col_52l"):     info.get("week_52_low"),
            t("watchlist_col_sector"):  info.get("sector", "Unknown"),
            t("watchlist_col_added"):   wl_row.get("added_at", ""),
        })

    df = pd.DataFrame(rows)
    display = df.drop(columns=["id"])

    day_col = t("watchlist_col_day")
    price_col = t("watchlist_col_price")
    high_col = t("watchlist_col_52h")
    low_col = t("watchlist_col_52l")

    def style_change(val):
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return ""
        return "color: #00d4aa; font-weight: 600" if val >= 0 else "color: #ff4757; font-weight: 600"

    formatted = (
        display.style
        .format({
            price_col: lambda v: f"${v:.2f}" if v and not np.isnan(v) else "N/A",
            day_col:   lambda v: f"{v:+.2f}%" if v and not np.isnan(v) else "N/A",
            high_col:  lambda v: f"${v:.2f}" if v and not np.isnan(v) else "N/A",
            low_col:   lambda v: f"${v:.2f}" if v and not np.isnan(v) else "N/A",
        })
        .applymap(style_change, subset=[day_col])
    )
    st.dataframe(formatted, use_container_width=True, hide_index=True)

    # ── Remove ticker ──────────────────────────────────────────────────────────
    st.subheader(t("watchlist_remove"))
    ticker_options = dict(zip(df["Ticker"], df["id"]))
    with st.form("watchlist_remove"):
        selected = st.selectbox(t("watchlist_remove_select"), options=list(ticker_options.keys()))
        if st.form_submit_button(t("watchlist_remove_btn"), type="secondary"):
            remove_from_watchlist(ticker_options[selected])
            st.warning(t("watchlist_removed", ticker=selected))
            st.rerun()
