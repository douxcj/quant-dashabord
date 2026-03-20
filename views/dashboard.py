import streamlit as st
import pandas as pd
from portfolio import calculate_portfolio_summary, build_portfolio_history
from market_data import get_ticker_info
from metrics import calculate_drawdown_series
from components.cards import render_summary_cards
from components.charts import (
    portfolio_value_chart,
    pnl_bar_chart,
    drawdown_chart,
    weight_donut_chart,
    stock_comparison_chart,
    sector_pie_chart,
)
from i18n import t


def render_overview(account_id: int, currency: str) -> tuple:
    """Render dashboard content. Returns (tickers,) so callers can drive the news panel."""
    summary = calculate_portfolio_summary(account_id)
    holdings = summary["holdings"]
    tickers = tuple(holdings["ticker"].tolist()) if not holdings.empty else ()

    render_summary_cards(summary, "$")
    st.divider()

    st.subheader(t("dash_holdings"))
    if holdings.empty:
        st.info(t("dash_no_holdings"))
    else:
        display = holdings[[
            "ticker", "shares", "avg_cost", "current_price",
            "current_value", "unrealized_pnl", "unrealized_pnl_pct", "weight_pct",
        ]].copy()
        display.columns = [
            t("dash_col_ticker"), t("dash_col_shares"), t("dash_col_avg_cost"), t("dash_col_price"),
            t("dash_col_value"), t("dash_col_pnl"), t("dash_col_pnl_pct"), t("dash_col_weight"),
        ]

        pnl_col = t("dash_col_pnl")
        pnl_pct_col = t("dash_col_pnl_pct")

        def _style_pnl(val):
            return "color:#00b386;font-weight:600" if val >= 0 else "color:#e53935;font-weight:600"

        st.dataframe(
            display.style
            .format({
                t("dash_col_shares"):   "{:.4f}",
                t("dash_col_avg_cost"): "${:.2f}",
                t("dash_col_price"):    "${:.2f}",
                t("dash_col_value"):    "${:,.2f}",
                pnl_col:               "${:,.2f}",
                pnl_pct_col:           "{:.2f}%",
                t("dash_col_weight"):   "{:.2f}%",
            })
            .applymap(_style_pnl, subset=[pnl_col, pnl_pct_col]),
            use_container_width=True,
            hide_index=True,
        )

    st.divider()

    cl, cr = st.columns([2, 1])
    hist_values, is_estimated = build_portfolio_history(account_id)
    with cl:
        st.plotly_chart(portfolio_value_chart(hist_values, currency, is_estimated),
                        use_container_width=True, key="ov_val_chart")
    with cr:
        st.plotly_chart(weight_donut_chart(holdings), use_container_width=True, key="ov_donut_chart")

    if not holdings.empty:
        st.plotly_chart(pnl_bar_chart(holdings), use_container_width=True, key="ov_pnl_chart")

    if not hist_values.empty:
        dd = calculate_drawdown_series(hist_values)
        st.plotly_chart(drawdown_chart(dd), use_container_width=True, key="ov_dd_chart")

    if not holdings.empty:
        st.subheader(t("dash_rel_perf"))
        period = st.selectbox(t("dash_period"), ["1mo", "3mo", "6mo", "1y"], index=3,
                              key="dash_period")
        from market_data import fetch_historical_data
        hist = fetch_historical_data(tickers, period=period)
        st.plotly_chart(stock_comparison_chart(hist), use_container_width=True, key="ov_cmp_chart")

        st.subheader(t("dash_sector_geo"))
        cs, cg = st.columns(2)
        sector_data: dict[str, float] = {}
        geo_data: dict[str, float] = {}
        for _, row in holdings.iterrows():
            info = get_ticker_info(row["ticker"])
            sector = info.get("sector") or "Unknown"
            country = info.get("country") or "Unknown"
            w = float(row["weight_pct"])
            sector_data[sector] = sector_data.get(sector, 0) + w
            geo = (
                "Canada" if country in ("Canada", "CA")
                else "United States" if country in ("United States", "US")
                else country or "Unknown"
            )
            geo_data[geo] = geo_data.get(geo, 0) + w
        with cs:
            st.plotly_chart(sector_pie_chart(sector_data), use_container_width=True)
        with cg:
            st.plotly_chart(sector_pie_chart(geo_data), use_container_width=True)
            st.caption(t("dash_geo_exposure"))

    return tickers


def show(account_id: int, account_name: str, currency: str):
    """Standalone entry point (kept for backwards-compat / direct routing)."""
    from components.news import render_news_panel
    col_main, col_news = st.columns([3, 1], gap="large")
    with col_main:
        st.title(account_name)
        tickers = render_overview(account_id, currency)
    with col_news:
        render_news_panel(tickers)
