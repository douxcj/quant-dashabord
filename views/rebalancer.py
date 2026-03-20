import streamlit as st
import pandas as pd
import numpy as np
from database import get_watchlist, add_trade
from portfolio import calculate_portfolio_summary
from components.cards import signal_badge
from i18n import t
import importlib
from datetime import date

MODEL_MAP = {
    "Momentum + RSI Hybrid":      "models.momentum",
    "Equal Weight Rebalance":     "models.equal_weight",
    "Risk Parity":                "models.risk_parity",
    "Mean Reversion (RSI)":       "models.mean_reversion",
    "Trend Following (MA Crossover)": "models.trend_following",
}


def show(account_id: int, account_name: str, currency: str, embedded: bool = False):
    if not embedded:
        st.title(f"{t('reb_title')} — {account_name}")

    # ── Model selector ─────────────────────────────────────────────────────────
    st.subheader(t("reb_model"))
    model_name = st.selectbox(t("reb_model_label"), list(MODEL_MAP.keys()))
    mod = importlib.import_module(MODEL_MAP[model_name])
    st.info(f"**{mod.NAME}** — {mod.DESCRIPTION}")

    # ── Universe selector ──────────────────────────────────────────────────────
    st.subheader(t("reb_universe"))
    watchlist_df = get_watchlist(account_id)
    summary = calculate_portfolio_summary(account_id)
    holdings = summary["holdings"]

    watchlist_tickers = watchlist_df["ticker"].tolist() if not watchlist_df.empty else []
    holding_tickers = holdings["ticker"].tolist() if not holdings.empty else []
    all_tickers = sorted(set(watchlist_tickers + holding_tickers))

    if not all_tickers:
        st.warning(t("reb_no_tickers"))
        return

    selected_tickers = st.multiselect(
        t("reb_tickers"),
        options=all_tickers,
        default=all_tickers,
    )

    if not selected_tickers:
        st.warning(t("reb_select_one"))
        return

    current_weights: dict[str, float] = {}
    if not holdings.empty:
        current_weights = dict(zip(holdings["ticker"], holdings["weight_pct"]))

    portfolio_value = summary["portfolio_value"]

    # ── Run analysis ───────────────────────────────────────────────────────────
    if st.button(t("reb_run"), type="primary"):
        try:
            results = mod.run(selected_tickers, portfolio_value, current_weights)
        except Exception as e:
            st.error(f"{t('reb_run')} error: {e}")
            return

        if results.empty:
            st.warning(t("reb_no_results"))
            return

        st.success(t("reb_complete", n=len(results)))
        st.subheader(t("reb_recommendations"))

        results = _add_trade_suggestions(results, portfolio_value, holdings)
        _render_recommendations(results, portfolio_value, currency)

        st.divider()
        _apply_trades_section(account_id, results, currency)


def _add_trade_suggestions(results: pd.DataFrame, portfolio_value: float,
                            holdings: pd.DataFrame) -> pd.DataFrame:
    df = results.copy()

    if "target_weight" not in df.columns:
        df["target_weight"] = df.get("current_weight", 0)

    price_map: dict[str, float] = {}
    if not holdings.empty and "current_price" in holdings.columns:
        price_map = dict(zip(holdings["ticker"], holdings["current_price"]))

    def calc_shares(row):
        ticker = row["ticker"]
        cur_w = row.get("current_weight", 0) or 0
        tgt_w = row.get("target_weight", 0) or 0
        price = price_map.get(ticker)
        if not price or np.isnan(price):
            return None, None
        cur_val = (cur_w / 100) * portfolio_value
        tgt_val = (tgt_w / 100) * portfolio_value
        delta_val = tgt_val - cur_val
        shares = abs(delta_val) / price
        return round(shares, 4), round(abs(delta_val), 2)

    suggested_shares = []
    estimated_cost = []
    for _, row in df.iterrows():
        s, c = calc_shares(row)
        suggested_shares.append(s)
        estimated_cost.append(c)

    df["suggested_shares"] = suggested_shares
    df["estimated_cost"] = estimated_cost
    return df


def _render_recommendations(df: pd.DataFrame, portfolio_value: float, currency: str):
    display_rows = []
    for _, row in df.iterrows():
        sig = row.get("signal_strength", "Hold")
        display_rows.append({
            "Ticker":                  row["ticker"],
            t("reb_col_cur_weight"):   f"{row.get('current_weight', 0):.1f}%",
            t("reb_col_tgt_weight"):   f"{row.get('target_weight', 0):.1f}%",
            t("reb_col_action"):       row.get("action", "HOLD"),
            t("reb_col_signal"):       sig,
            t("reb_col_shares"):       (
                f"{row['suggested_shares']:.4f}" if row.get("suggested_shares") else "—"
            ),
            t("reb_col_cost"):         (
                f"${row['estimated_cost']:,.2f}" if row.get("estimated_cost") else "—"
            ),
            t("reb_col_why"):          row.get("explanation", ""),
        })

    table_df = pd.DataFrame(display_rows)
    action_col = t("reb_col_action")

    def style_action(val):
        if val == "BUY":
            return "color: #00d4aa; font-weight: 700"
        elif val == "SELL":
            return "color: #ff4757; font-weight: 700"
        return "color: #9e9e9e"

    styled = table_df.style.applymap(style_action, subset=[action_col])
    st.dataframe(styled, use_container_width=True, hide_index=True)

    st.markdown(t("reb_signal_legend"), unsafe_allow_html=True)
    badge_html = " &nbsp; ".join([
        signal_badge(s) for s in
        ["Strong Buy", "Buy", "Weak Buy", "Hold", "Weak Sell", "Sell", "Strong Sell"]
    ])
    st.markdown(badge_html, unsafe_allow_html=True)


def _apply_trades_section(account_id: int, results: pd.DataFrame, currency: str):
    st.subheader(t("reb_apply"))
    buys = results[results["action"] == "BUY"]
    sells = results[results["action"] == "SELL"]

    trade_date = st.date_input(t("reb_trade_date"), value=date.today())

    if buys.empty and sells.empty:
        st.info(t("reb_no_actions"))
        return

    st.write(t("reb_orders_ready", buys=len(buys), sells=len(sells)))

    col_apply, col_cancel = st.columns([1, 5])
    with col_apply:
        if st.button(t("reb_apply_btn"), type="primary"):
            applied = 0
            errors = []
            for _, row in results[results["action"].isin(["BUY", "SELL"])].iterrows():
                shares = row.get("suggested_shares")
                price = None
                from portfolio import calculate_holdings
                from market_data import fetch_current_prices
                h = calculate_holdings(account_id)
                if not h.empty and row["ticker"] in h["ticker"].values:
                    prices = fetch_current_prices(tuple(h["ticker"].tolist()))
                    price = prices.get(row["ticker"])

                if not shares or not price or np.isnan(price):
                    errors.append(row["ticker"])
                    continue

                add_trade(
                    account_id=account_id,
                    ticker=row["ticker"],
                    action=row["action"],
                    quantity=float(shares),
                    price=float(price),
                    trade_date=trade_date,
                    notes=f"Auto: {row.get('signal_strength', '')}",
                )
                applied += 1

            if applied:
                st.success(t("reb_applied", n=applied))
            if errors:
                st.warning(t("reb_errors", tickers=", ".join(errors)))
            if applied:
                st.rerun()
