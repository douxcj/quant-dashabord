import streamlit as st
import pandas as pd
import numpy as np
from portfolio import build_portfolio_history
from metrics import (
    get_all_metrics,
    calculate_drawdown_series,
    calculate_rolling_sharpe,
)
from components.charts import (
    portfolio_value_chart,
    drawdown_chart,
    rolling_sharpe_chart,
    stock_comparison_chart,
)
from market_data import fetch_historical_data
from i18n import t


def _fmt(val, suffix="", prefix="", decimals=2, na="N/A"):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return na
    return f"{prefix}{val:.{decimals}f}{suffix}"


def show(account_id: int, account_name: str, currency: str, embedded: bool = False):
    if not embedded:
        st.title(f"{t('analytics_title')} — {account_name}")

    metrics = get_all_metrics(account_id, currency)
    hist_values, is_estimated = build_portfolio_history(account_id)

    # ── Return metrics row ─────────────────────────────────────────────────────
    st.subheader(t("analytics_return"))
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric(t("analytics_total_return"), _fmt(metrics["total_return_pct"], "%"))
    with c2:
        st.metric(t("analytics_ann_return"), _fmt(metrics["annualized_return"], "%"))
    with c3:
        st.metric(t("analytics_best_day"), _fmt(metrics["best_day"], "%", "+"))
    with c4:
        st.metric(t("analytics_worst_day"), _fmt(metrics["worst_day"], "%"))

    st.divider()

    # ── Risk metrics row ───────────────────────────────────────────────────────
    st.subheader(t("analytics_risk"))
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric(t("analytics_volatility"), _fmt(metrics["volatility"], "%"))
    with c2:
        st.metric(t("analytics_sharpe"), _fmt(metrics["sharpe"]))
    with c3:
        st.metric(t("analytics_sortino"), _fmt(metrics["sortino"]))
    with c4:
        st.metric(t("analytics_drawdown"), _fmt(metrics["max_drawdown"], "%"))
    with c5:
        benchmark = "XIU.TO" if currency == "CAD" else "SPY"
        st.metric(t("analytics_beta", bm=benchmark), _fmt(metrics["beta"]))

    st.divider()

    # ── Win rate ───────────────────────────────────────────────────────────────
    st.subheader(t("analytics_trade"))
    c1, c2 = st.columns(2)
    with c1:
        wr = metrics["win_rate"]
        wr_str = _fmt(wr, "%") if not np.isnan(wr or float("nan")) else t("analytics_win_rate_na")
        st.metric(t("analytics_win_rate"), wr_str,
                  help=t("analytics_win_rate_help"))
    with c2:
        rf = "4.5% CAD" if currency == "CAD" else "5.0% USD"
        st.caption(t("analytics_rf_rate", rf=rf))
        st.caption(t("analytics_benchmark", bm="XIU.TO" if currency == "CAD" else "SPY"))

    st.divider()

    # ── Charts ─────────────────────────────────────────────────────────────────
    st.subheader(t("analytics_history"))

    if hist_values.empty or len(hist_values) < 5:
        st.info(t("analytics_no_history"))
        return

    st.plotly_chart(portfolio_value_chart(hist_values, currency, is_estimated), use_container_width=True, key="an_val_chart")

    dd = calculate_drawdown_series(hist_values)
    st.plotly_chart(drawdown_chart(dd), use_container_width=True, key="an_dd_chart")

    returns = hist_values.pct_change().dropna()
    rs = calculate_rolling_sharpe(returns, window=30)
    st.plotly_chart(rolling_sharpe_chart(rs), use_container_width=True, key="an_sharpe_chart")

    # ── Individual stock comparison ────────────────────────────────────────────
    st.subheader(t("analytics_rel_perf"))
    from portfolio import calculate_holdings
    holdings = calculate_holdings(account_id)
    if not holdings.empty:
        tickers = tuple(holdings["ticker"].tolist())
        period = st.selectbox(t("dash_period"), ["3mo", "6mo", "1y", "2y"], index=2, key="analytics_period")
        hist = fetch_historical_data(tickers, period=period)
        st.plotly_chart(stock_comparison_chart(hist), use_container_width=True, key="an_cmp_chart")
    else:
        st.info(t("analytics_no_holdings"))
