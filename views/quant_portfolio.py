"""
Quant Portfolio Manager View
Implements a 4-layer systematic ETF rotation strategy with full portfolio tracking.
"""
import json
import math
from datetime import datetime, date, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from database import (
    create_quant_portfolio,
    delete_quant_portfolio,
    get_quant_holdings,
    get_quant_portfolio,
    get_quant_portfolios,
    get_quant_rebalances,
    get_quant_snapshots,
    get_quant_streaks,
    get_quant_trades,
    log_quant_trade,
    save_quant_rebalance,
    save_quant_snapshot,
    update_quant_cash,
    update_quant_streaks,
    upsert_quant_holding,
)
from models.quant_portfolio_model import (
    CAD_TICKER_META,
    PARAMS,
    compute_rebalance_trades,
    get_ticker_description,
    get_market_hours,
    run_model,
)
from i18n import t
from components.news import render_news_panel


# ── Helpers ────────────────────────────────────────────────────────────────────

def _add_trading_days(start: date, n: int) -> date:
    """Advance start by n Mon–Fri trading days."""
    d = start
    added = 0
    while added < n:
        d += timedelta(days=1)
        if d.weekday() < 5:
            added += 1
    return d


def _next_rebalance_banner(portfolio_id: int):
    """Show last-rebalanced date and next suggested date (3 trading days later)."""
    rebalances = get_quant_rebalances(portfolio_id)
    today = date.today()

    if rebalances.empty:
        st.info("No rebalances recorded yet. Click **Run Rebalance** to run the model for the first time.")
        return

    last_dt = pd.to_datetime(rebalances["created_at"].iloc[0]).date()
    next_dt = _add_trading_days(last_dt, 3)
    days_until = (next_dt - today).days

    if days_until > 0:
        color, icon, status = "#374151", "🗓", f"in {days_until} trading day{'s' if days_until != 1 else ''}"
    elif days_until == 0:
        color, icon, status = "#d97706", "⏰", "today"
    else:
        color, icon, status = "#00b386", "✅", f"{abs(days_until)} day{'s' if abs(days_until) != 1 else ''} ago (ready)"

    st.markdown(
        f"<div style='background:#f7f8fa;border:1px solid #e8eaed;border-radius:10px;"
        f"padding:10px 16px;margin-bottom:1rem;display:flex;gap:24px;align-items:center;'>"
        f"<span style='font-size:0.8rem;color:#6b7280;'>Last rebalance: "
        f"<b style='color:#374151;'>{last_dt.strftime('%b %d, %Y')}</b></span>"
        f"<span style='font-size:0.8rem;color:#6b7280;'>Next suggested: "
        f"<b style='color:{color};'>{icon} {next_dt.strftime('%b %d, %Y')} — {status}</b></span>"
        f"</div>",
        unsafe_allow_html=True,
    )


def _currency_symbol(currency: str) -> str:
    return "C$" if currency == "CAD" else "$"


def _regime_badge_html(regime: str) -> str:
    colors = {
        "RISK_ON": ("#00c896", "#e6f9f4", "RISK ON"),
        "CAUTION": ("#d97706", "#fffbeb", "CAUTION"),
        "RISK_OFF": ("#e53935", "#fef2f2", "RISK OFF"),
    }
    color, bg, label = colors.get(regime, ("#9ca3af", "#f3f4f6", regime))
    return (
        f'<span style="background:{bg};color:{color};border:1px solid {color};'
        f'padding:4px 14px;border-radius:20px;font-size:0.82rem;font-weight:700;'
        f'letter-spacing:0.05em;">{label}</span>'
    )


def _compute_portfolio_value(holdings_df: pd.DataFrame, prices: dict, cash: float) -> float:
    market_value = 0.0
    for _, row in holdings_df.iterrows():
        price = prices.get(row["ticker"], row.get("avg_entry_price", 0.0))
        market_value += float(row["shares"]) * float(price)
    return market_value + cash


def _holdings_with_prices(holdings_df: pd.DataFrame, prices: dict) -> pd.DataFrame:
    if holdings_df.empty:
        return holdings_df
    df = holdings_df.copy()
    df["current_price"] = df["ticker"].map(lambda t: prices.get(t, 0.0))
    df["market_value"] = df["shares"] * df["current_price"]
    df["pnl_dollar"] = df["market_value"] - df["shares"] * df["avg_entry_price"]
    df["pnl_pct"] = df.apply(
        lambda r: (r["pnl_dollar"] / (r["shares"] * r["avg_entry_price"]) * 100)
        if r["avg_entry_price"] > 0 else 0.0,
        axis=1,
    )
    total_mv = df["market_value"].sum()
    df["weight_pct"] = df["market_value"] / total_mv * 100 if total_mv > 0 else 0.0
    return df


def _color_pnl(val: float) -> str:
    return "color: #00d4aa; font-weight: 700" if val >= 0 else "color: #e53935; font-weight: 700"


def _apply_trades_to_portfolio(
    portfolio_id: int,
    trade_rows: list,
    regime: str,
    suggestion_json: str,
    prices: dict,
    top_tickers: list,
):
    """
    Apply confirmed trade rows to the portfolio:
    - Log each trade
    - Upsert holdings (weighted avg for BUY, reduce for SELL)
    - Update cash
    - Save snapshot
    - Save rebalance record
    - Update streaks
    """
    portfolio = get_quant_portfolio(portfolio_id)
    current_cash = float(portfolio.get("current_cash", 0.0))
    holdings_df = get_quant_holdings(portfolio_id)
    holdings_map = {}
    for _, row in holdings_df.iterrows():
        holdings_map[row["ticker"]] = {
            "shares": float(row["shares"]),
            "avg_entry_price": float(row["avg_entry_price"]),
        }

    # Apply each trade
    for trade in trade_rows:
        action = trade["action"]
        ticker = trade["ticker"]
        shares = float(trade["shares"])
        exec_price = float(trade["exec_price"])
        commission = float(trade.get("commission", 0.0))
        notes = str(trade.get("notes", ""))

        if shares <= 0:
            continue

        log_quant_trade(
            portfolio_id=portfolio_id,
            ticker=ticker,
            action=action,
            shares=shares,
            price=exec_price,
            commission=commission,
            trade_type="Rebalance",
            notes=notes,
        )

        trade_amount = shares * exec_price + commission

        if action == "BUY":
            old = holdings_map.get(ticker, {"shares": 0.0, "avg_entry_price": 0.0})
            old_shares = old["shares"]
            old_avg = old["avg_entry_price"]
            new_shares = old_shares + shares
            new_avg = (old_shares * old_avg + shares * exec_price) / new_shares if new_shares > 0 else exec_price
            holdings_map[ticker] = {"shares": new_shares, "avg_entry_price": new_avg}
            current_cash -= trade_amount

        elif action == "SELL":
            old = holdings_map.get(ticker, {"shares": 0.0, "avg_entry_price": 0.0})
            new_shares = old["shares"] - shares
            holdings_map[ticker] = {"shares": max(0.0, new_shares), "avg_entry_price": old["avg_entry_price"]}
            current_cash += shares * exec_price - commission

    # Persist holdings
    for ticker, data in holdings_map.items():
        upsert_quant_holding(portfolio_id, ticker, data["shares"], data["avg_entry_price"])

    # Update cash
    update_quant_cash(portfolio_id, current_cash)

    # Compute total value for snapshot
    updated_holdings_df = get_quant_holdings(portfolio_id)
    total_value = _compute_portfolio_value(updated_holdings_df, prices, current_cash)

    # Save snapshot
    snap_holdings = [
        {"ticker": r["ticker"], "shares": r["shares"], "price": prices.get(r["ticker"], 0.0)}
        for _, r in updated_holdings_df.iterrows()
    ]
    save_quant_snapshot(
        portfolio_id=portfolio_id,
        total_value=total_value,
        cash=current_cash,
        holdings_json=json.dumps(snap_holdings),
        regime=regime,
    )

    # Save rebalance record
    actual_json = json.dumps(trade_rows)
    save_quant_rebalance(portfolio_id, regime, suggestion_json, actual_json)

    # Update streaks
    update_quant_streaks(portfolio_id, top_tickers)


# ── Main Show Function ─────────────────────────────────────────────────────────

_TITLE_STYLE = "margin:0 0 6px 0;font-size:1.75rem;font-weight:800;color:#1a1a2e;"
_HR = "<hr style='border-color:#e8eaed;margin:0.75rem 0 1rem 0;'>"


def show():
    # Init session state keys
    for key, default in [
        ("qpm_selected_id", None),
        ("qpm_show_create", False),
        ("qpm_rebalance_step", 1),
        ("qpm_suggestion", None),
        ("qpm_trade_rows", []),
        ("qpm_last_model_run", None),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

    portfolios_df = get_quant_portfolios()

    # Pre-resolve selected portfolio and tickers for news
    port_names = portfolios_df["name"].tolist() if not portfolios_df.empty else []
    port_ids = portfolios_df["id"].tolist() if not portfolios_df.empty else []
    cur_id = st.session_state["qpm_selected_id"]
    if port_ids and cur_id not in port_ids:
        cur_id = port_ids[0]
        st.session_state["qpm_selected_id"] = cur_id
    news_tickers: tuple = ()
    if cur_id:
        _hdf = get_quant_holdings(cur_id)
        news_tickers = tuple(_hdf["ticker"].tolist()) if not _hdf.empty else ()

    # ── Top-level split — news starts from the very top ───────────────────────
    col_main, col_news = st.columns([3, 1], gap="large")

    with col_news:
        render_news_panel(news_tickers)

    with col_main:
        # ── Title ─────────────────────────────────────────────────────────────
        st.markdown(f"<p style='{_TITLE_STYLE}'>⚡ {t('qpm_title')}</p>", unsafe_allow_html=True)

        # ── Selector + action buttons row ─────────────────────────────────────
        if portfolios_df.empty:
            st.info("No Quant portfolios yet. Create one below.")
            st.session_state["qpm_show_create"] = True
            st.session_state["qpm_selected_id"] = None
        else:
            left_col, _ = st.columns([2, 3])
            with left_col:
                sel_col, btn_new, btn_del = st.columns([3, 1, 1])
                with sel_col:
                    default_idx = port_ids.index(cur_id) if cur_id in port_ids else 0
                    selected_name = st.selectbox(
                        "portfolio",
                        options=port_names,
                        index=default_idx,
                        key="qpm_port_selector",
                        label_visibility="collapsed",
                    )
                    selected_idx = port_names.index(selected_name)
                    st.session_state["qpm_selected_id"] = int(port_ids[selected_idx])
                with btn_new:
                    if st.button("+ New", key="qpm_new_btn", use_container_width=True):
                        st.session_state["qpm_show_create"] = True
                with btn_del:
                    if st.session_state["qpm_selected_id"] and st.button(
                        "Delete", key="qpm_del_btn", use_container_width=True
                    ):
                        st.session_state["qpm_confirm_delete"] = True

        # ── Confirm delete ────────────────────────────────────────────────────
        if st.session_state.get("qpm_confirm_delete") and st.session_state["qpm_selected_id"]:
            port_info = get_quant_portfolio(st.session_state["qpm_selected_id"])
            st.warning(
                f"Delete portfolio **{port_info.get('name', '')}**? "
                "This will permanently remove all holdings, trades, and history."
            )
            c1, c2, _ = st.columns([1, 1, 4])
            with c1:
                if st.button("Confirm Delete", type="primary", key="qpm_confirm_del_yes"):
                    delete_quant_portfolio(st.session_state["qpm_selected_id"])
                    st.session_state["qpm_selected_id"] = None
                    st.session_state["qpm_confirm_delete"] = False
                    st.session_state["qpm_suggestion"] = None
                    st.rerun()
            with c2:
                if st.button("Cancel", key="qpm_confirm_del_no"):
                    st.session_state["qpm_confirm_delete"] = False
                    st.rerun()
            return

        st.markdown(_HR, unsafe_allow_html=True)

        # ── Creation Form ─────────────────────────────────────────────────────
        if st.session_state["qpm_show_create"]:
            _render_create_form()
            if not portfolios_df.empty:
                if st.button("Cancel", key="qpm_cancel_create"):
                    st.session_state["qpm_show_create"] = False
                    st.rerun()
            return

        # ── Portfolio View ────────────────────────────────────────────────────
        portfolio_id = st.session_state["qpm_selected_id"]
        if not portfolio_id:
            st.info("Create a Quant Portfolio to get started.")
            return

        portfolio = get_quant_portfolio(portfolio_id)
        if not portfolio:
            st.error("Portfolio not found.")
            return

        currency = portfolio.get("currency", "USD")
        risk_mode = portfolio.get("risk_mode", "Conservative")
        ccy = _currency_symbol(currency)
        current_cash = float(portfolio.get("current_cash", 0.0))

        holdings_df = get_quant_holdings(portfolio_id)
        tickers = holdings_df["ticker"].tolist() if not holdings_df.empty else []

        if st.session_state["qpm_suggestion"] and "prices" in st.session_state["qpm_suggestion"]:
            prices = st.session_state["qpm_suggestion"]["prices"]
            missing = [t for t in tickers if t not in prices]
            if missing:
                from models.quant_portfolio_model import fetch_prices
                extra = fetch_prices(missing)
                prices = {**prices, **extra}
        else:
            from models.quant_portfolio_model import fetch_prices
            prices = fetch_prices(tickers) if tickers else {}

        holdings_rich = _holdings_with_prices(holdings_df, prices) if not holdings_df.empty else pd.DataFrame()
        market_value = holdings_rich["market_value"].sum() if not holdings_rich.empty else 0.0
        total_value = market_value + current_cash

        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            f"📊 {t('qpm_tab_overview')}",
            f"⚖️ {t('qpm_tab_rebalance')}",
            f"📋 {t('qpm_tab_history')}",
            f"🔬 {t('qpm_tab_model')}",
            f"📈 {t('qpm_tab_performance')}",
        ])

        with tab1:
            _render_overview(portfolio, holdings_rich, prices, current_cash, market_value, total_value, ccy, risk_mode, portfolio_id, currency)
        with tab2:
            _render_rebalance(portfolio, portfolio_id, currency, risk_mode, ccy, current_cash, total_value, holdings_df, prices)
        with tab3:
            _render_trade_history(portfolio_id, ccy)
        with tab4:
            _render_model_details(portfolio, currency, risk_mode, ccy)
        with tab5:
            _render_performance(portfolio_id, ccy, current_cash, holdings_rich, prices)


# ── Tab 1: Overview ────────────────────────────────────────────────────────────

def _render_overview(portfolio, holdings_rich, prices, current_cash, market_value, total_value, ccy, risk_mode, portfolio_id, currency="USD"):
    stop_loss_threshold = PARAMS[risk_mode]["stop_loss"]

    # Stop-loss alerts
    if not holdings_rich.empty:
        for _, row in holdings_rich.iterrows():
            entry = float(row["avg_entry_price"])
            current = float(row.get("current_price", 0.0))
            if entry > 0 and current > 0:
                loss_pct = (entry - current) / entry
                if loss_pct >= stop_loss_threshold:
                    pct_display = loss_pct * 100
                    st.markdown(
                        f'<div style="background:#fef2f2;border:1px solid #fca5a5;border-radius:10px;'
                        f'padding:0.75rem 1rem;margin-bottom:0.5rem;">'
                        f'<span style="color:#dc2626;font-weight:700;">⛔ STOP-LOSS TRIGGERED: '
                        f'{row["ticker"]} is down {pct_display:.1f}% from entry '
                        f'({ccy}{entry:.2f} → {ccy}{current:.2f})</span></div>',
                        unsafe_allow_html=True,
                    )
                    with st.expander(f"Log Stop-Loss Sale — {row['ticker']}"):
                        with st.form(key=f"sl_form_{row['ticker']}"):
                            sl_shares = st.number_input(
                                "Shares to sell",
                                min_value=0.0,
                                max_value=float(row["shares"]),
                                value=float(row["shares"]),
                                step=1.0,
                                key=f"sl_shares_{row['ticker']}",
                            )
                            sl_price = st.number_input(
                                "Execution price",
                                min_value=0.01,
                                value=float(current) if current > 0 else float(entry),
                                step=0.01,
                                key=f"sl_price_{row['ticker']}",
                            )
                            sl_commission = st.number_input(
                                "Commission",
                                min_value=0.0,
                                value=0.0,
                                step=0.01,
                                key=f"sl_comm_{row['ticker']}",
                            )
                            if st.form_submit_button("Log Stop-Loss Sale", type="primary"):
                                log_quant_trade(
                                    portfolio_id=portfolio_id,
                                    ticker=row["ticker"],
                                    action="SELL",
                                    shares=sl_shares,
                                    price=sl_price,
                                    commission=sl_commission,
                                    trade_type="Stop-Loss",
                                    notes=f"Stop-loss triggered at {loss_pct*100:.1f}% loss",
                                )
                                new_shares = float(row["shares"]) - sl_shares
                                upsert_quant_holding(
                                    portfolio_id, row["ticker"], new_shares, float(row["avg_entry_price"])
                                )
                                new_cash = current_cash + sl_shares * sl_price - sl_commission
                                update_quant_cash(portfolio_id, new_cash)
                                st.success(f"Stop-loss sale logged for {row['ticker']}.")
                                st.rerun()

    # Regime badge (from latest suggestion or fetch inline)
    regime_label = "—"
    if st.session_state.get("qpm_suggestion"):
        regime_info = st.session_state["qpm_suggestion"].get("regime_info", {})
        regime_label = regime_info.get("regime", "—")

    col_regime, _ = st.columns([2, 5])
    with col_regime:
        st.markdown(
            f"<div style='margin-bottom:1rem;'>"
            f"<span style='font-size:0.75rem;color:#6b7280;font-weight:600;text-transform:uppercase;"
            f"letter-spacing:0.06em;'>{t('qpm_market_regime')}&nbsp;&nbsp;</span>"
            f"{_regime_badge_html(regime_label)}</div>",
            unsafe_allow_html=True,
        )

    # Summary cards
    starting_cash = float(portfolio.get("starting_cash", 0.0))
    unrealized_pnl = holdings_rich["pnl_dollar"].sum() if not holdings_rich.empty else 0.0
    total_return_pct = (total_value / starting_cash - 1) * 100 if starting_cash > 0 else 0.0
    n_positions = len(holdings_rich) if not holdings_rich.empty else 0

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric(t("qpm_card_total_value"), f"{ccy}{total_value:,.2f}")
    c2.metric(t("qpm_card_market_value"), f"{ccy}{market_value:,.2f}")
    c3.metric(t("qpm_card_cash"), f"{ccy}{current_cash:,.2f}")

    pnl_delta = f"{'+' if unrealized_pnl >= 0 else ''}{ccy}{unrealized_pnl:,.2f}"
    c4.metric(
        t("qpm_card_pnl"),
        pnl_delta,
        delta=f"{'+' if unrealized_pnl >= 0 else ''}{unrealized_pnl / market_value * 100:.2f}%" if market_value > 0 else None,
        delta_color="normal",
    )
    ret_str = f"{'+' if total_return_pct >= 0 else ''}{total_return_pct:.2f}%"
    c5.metric(t("qpm_card_total_return"), ret_str, delta=ret_str, delta_color="normal")
    c6.metric(t("qpm_card_positions"), str(n_positions))

    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)

    # Holdings table
    if holdings_rich.empty:
        st.info(t("qpm_no_holdings"))
    else:
        st.subheader(t("qpm_holdings"))
        display_df = holdings_rich[[
            "ticker", "shares", "avg_entry_price", "current_price",
            "market_value", "pnl_dollar", "pnl_pct", "weight_pct"
        ]].copy()
        display_df.insert(
            1, t("qpm_col_description"),
            display_df["ticker"].apply(lambda tk: get_ticker_description(tk, currency))
        )
        display_df.insert(
            2, t("qpm_col_market_hours"),
            display_df["ticker"].apply(get_market_hours)
        )
        display_df.columns = [
            t("qpm_col_ticker"), t("qpm_col_description"), t("qpm_col_market_hours"),
            t("qpm_col_shares"), f"{t('qpm_col_avg_entry')} ({ccy})", f"{t('qpm_col_price')} ({ccy})",
            f"{t('qpm_col_mkt_value')} ({ccy})", f"{t('qpm_col_pnl')} ({ccy})", t("qpm_col_pnl_pct"), t("qpm_col_weight"),
        ]

        def style_pnl(df_s):
            styles = pd.DataFrame("", index=df_s.index, columns=df_s.columns)
            pnl_col = f"P&L ({ccy})"
            pnl_pct_col = "P&L %"
            if pnl_col in df_s.columns:
                styles[pnl_col] = df_s[pnl_col].apply(
                    lambda v: "color: #00d4aa; font-weight: 700"
                    if (isinstance(v, (int, float)) and v >= 0)
                    else "color: #e53935; font-weight: 700"
                )
            if pnl_pct_col in df_s.columns:
                styles[pnl_pct_col] = df_s[pnl_pct_col].apply(
                    lambda v: "color: #00d4aa; font-weight: 700"
                    if (isinstance(v, (int, float)) and v >= 0)
                    else "color: #e53935; font-weight: 700"
                )
            return styles

        fmt = {
            t("qpm_col_shares"): "{:.0f}",
            f"{t('qpm_col_avg_entry')} ({ccy})": f"{ccy}{{:.2f}}",
            f"{t('qpm_col_price')} ({ccy})": f"{ccy}{{:.2f}}",
            f"{t('qpm_col_mkt_value')} ({ccy})": f"{ccy}{{:,.2f}}",
            f"{t('qpm_col_pnl')} ({ccy})": f"{ccy}{{:+,.2f}}",
            t("qpm_col_pnl_pct"): "{:+.2f}%",
            t("qpm_col_weight"): "{:.1f}%",
        }
        styled = display_df.style.apply(style_pnl, axis=None).format(fmt)
        st.dataframe(styled, use_container_width=True, hide_index=True)

    # Equity curve chart
    snapshots_df = get_quant_snapshots(portfolio_id)
    if not snapshots_df.empty and len(snapshots_df) >= 2:
        st.subheader("Equity Curve")
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=snapshots_df["created_at"],
            y=snapshots_df["total_value"],
            mode="lines",
            line=dict(color="#00c896", width=2.5),
            fill="tozeroy",
            fillcolor="rgba(0,200,150,0.08)",
            name="Portfolio Value",
            hovertemplate=f"{ccy}%{{y:,.2f}}<extra></extra>",
        ))
        fig.update_layout(
            plot_bgcolor="#ffffff",
            paper_bgcolor="#ffffff",
            xaxis=dict(showgrid=False, tickfont=dict(color="#6b7280", size=11)),
            yaxis=dict(
                showgrid=True,
                gridcolor="#f3f4f6",
                tickfont=dict(color="#6b7280", size=11),
                tickprefix=ccy,
            ),
            margin=dict(l=10, r=10, t=10, b=10),
            height=280,
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)


# ── Tab 2: Rebalance ──────────────────────────────────────────────────────────

def _render_rebalance(portfolio, portfolio_id, currency, risk_mode, ccy, current_cash, total_value, holdings_df, prices):
    step = st.session_state.get("qpm_rebalance_step", 1)

    _next_rebalance_banner(portfolio_id)

    # Step indicator
    step_labels = ["1 — Run Model", "2 — Log Actual Trades", "3 — Review & Apply"]
    st.markdown(
        "<div style='display:flex;gap:8px;margin-bottom:1.25rem;'>"
        + "".join(
            f'<div style="padding:5px 16px;border-radius:20px;font-size:0.8rem;font-weight:600;'
            f'background:{"#00c896" if i+1==step else "#e8eaed"};'
            f'color:{"#fff" if i+1==step else "#6b7280"};">{label}</div>'
            for i, label in enumerate(step_labels)
        )
        + "</div>",
        unsafe_allow_html=True,
    )

    if step == 1:
        _rebalance_step1(portfolio, portfolio_id, currency, risk_mode, ccy, current_cash, total_value, holdings_df, prices)
    elif step == 2:
        _rebalance_step2(portfolio_id, ccy, current_cash)
    elif step == 3:
        _rebalance_step3(portfolio, portfolio_id, ccy, current_cash, prices)

    st.divider()

    # Ad-hoc trade expander
    with st.expander("Ad-hoc Manual Trade", expanded=False):
        _render_adhoc_trade(portfolio_id, ccy, current_cash)

    # Cash management expander
    with st.expander("Cash Deposit / Withdrawal", expanded=False):
        _render_cash_management(portfolio_id, current_cash, ccy)


def _rebalance_step1(portfolio, portfolio_id, currency, risk_mode, ccy, current_cash, total_value, holdings_df, prices):
    col_run, col_info = st.columns([1, 3])
    with col_run:
        run_clicked = st.button(t("qpm_btn_run"), type="primary", key="qpm_run_model_btn", use_container_width=True)

    if run_clicked:
        streaks = get_quant_streaks(portfolio_id)
        with st.spinner("Running 4-layer model..."):
            import time
            t0 = time.time()
            result = run_model(
                currency=currency,
                risk_mode=risk_mode,
                total_value=total_value,
                streaks=streaks,
            )
            elapsed = time.time() - t0

        st.session_state["qpm_suggestion"] = result
        st.session_state["qpm_last_model_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.success(f"Model run complete in {elapsed:.1f}s.")

    suggestion = st.session_state.get("qpm_suggestion")
    if not suggestion:
        st.info(t("qpm_run_hint"))
        return

    regime_info = suggestion["regime_info"]
    regime = regime_info.get("regime", "RISK_ON")
    portfolio_df = suggestion.get("portfolio_df", pd.DataFrame())
    momentum_df = suggestion.get("momentum_df", pd.DataFrame())
    model_prices = suggestion.get("prices", {})

    # Regime badge
    st.markdown(
        f"<div style='margin:0.75rem 0;'><b>Regime:</b>&nbsp;&nbsp;"
        f"{_regime_badge_html(regime)}</div>",
        unsafe_allow_html=True,
    )
    if st.session_state.get("qpm_last_model_run"):
        st.caption(f"Last model run: {st.session_state['qpm_last_model_run']}")

    # Side-by-side comparison
    col_cur, col_new = st.columns(2)

    with col_cur:
        st.subheader("Current Holdings")
        if holdings_df.empty:
            st.info("No current holdings.")
        else:
            rich = _holdings_with_prices(holdings_df, model_prices)
            if not rich.empty:
                cur_display = rich[["ticker", "shares", "avg_entry_price", "current_price"]].copy()
                cur_display.columns = ["Ticker", "Shares", f"Avg ({ccy})", f"Price ({ccy})"]
                st.dataframe(cur_display, use_container_width=True, hide_index=True)

    with col_new:
        st.subheader("Suggested Portfolio")
        if portfolio_df.empty:
            st.warning("Model returned no positions. Market data may be unavailable.")
        else:
            new_display = portfolio_df[["ticker", "shares", "weight_pct", "price"]].copy()
            new_display.columns = ["Ticker", "Shares", "Weight %", f"Price ({ccy})"]
            new_display["Weight %"] = new_display["Weight %"].apply(lambda x: f"{x:.1f}%")
            st.dataframe(new_display, use_container_width=True, hide_index=True)

    # Trade list
    st.subheader("Suggested Trades")
    current_holdings_list = []
    if not holdings_df.empty:
        for _, row in holdings_df.iterrows():
            current_holdings_list.append({
                "ticker": row["ticker"],
                "shares": float(row["shares"]),
                "avg_entry_price": float(row["avg_entry_price"]),
            })

    trades = compute_rebalance_trades(current_holdings_list, portfolio_df, model_prices)

    if not trades:
        st.success("Portfolio is already optimal — no trades needed.")
        return

    trade_df = pd.DataFrame(trades)
    display_cols = ["action", "ticker", "current_shares", "suggested_shares", "price", "dollar_amount", "reason"]
    display_df = trade_df[display_cols].copy()
    display_df.columns = ["Action", "Ticker", "Current Shares", "Suggested Shares", f"Est. Price ({ccy})", f"Est. Amount ({ccy})", "Reason"]

    def style_action(val):
        if val == "BUY":
            return "color: #00d4aa; font-weight: 700"
        elif val == "SELL":
            return "color: #e53935; font-weight: 700"
        return ""

    styled = display_df.style.applymap(style_action, subset=["Action"])
    st.dataframe(styled, use_container_width=True, hide_index=True)

    # Proceed button
    col_proceed, _ = st.columns([1, 4])
    with col_proceed:
        if st.button(t("qpm_btn_proceed"), type="primary", key="qpm_proceed_step2"):
            # Pre-populate trade rows for step 2
            trade_rows = []
            for trade in trades:
                trade_rows.append({
                    "action": trade["action"],
                    "ticker": trade["ticker"],
                    "shares": float(trade["suggested_shares"]) if trade["action"] == "BUY" else float(trade["current_shares"]) - float(trade["suggested_shares"]),
                    "exec_price": float(trade["price"]) if trade["price"] else 0.0,
                    "commission": 0.0,
                    "notes": trade["reason"],
                    "skip": False,
                })
            st.session_state["qpm_trade_rows"] = trade_rows
            st.session_state["qpm_rebalance_step"] = 2
            st.rerun()


def _rebalance_step2(portfolio_id, ccy, current_cash):
    st.subheader("Log Actual Trades")
    st.caption("Edit the pre-populated trade rows. Uncheck 'Skip' to include a trade. Add manual trades below.")

    trade_rows = st.session_state.get("qpm_trade_rows", [])
    if not trade_rows:
        st.warning("No trade rows found. Please go back to Step 1.")
        if st.button("← Back to Step 1", key="qpm_back_1_from2_empty"):
            st.session_state["qpm_rebalance_step"] = 1
            st.rerun()
        return

    updated_rows = []
    total_buys = 0.0
    total_sells = 0.0

    for i, row in enumerate(trade_rows):
        with st.container():
            st.markdown(
                f"<div style='background:#f7f8fa;border:1px solid #e8eaed;border-radius:10px;"
                f"padding:0.75rem 1rem;margin-bottom:0.5rem;'>",
                unsafe_allow_html=True,
            )
            c0, c1, c2, c3, c4, c5, c6, c7 = st.columns([0.5, 1, 1, 1, 1, 1, 2, 0.7])

            with c0:
                skip = st.checkbox("Skip", value=row.get("skip", False), key=f"skip_{i}")
            with c1:
                action = st.selectbox(
                    "Action",
                    options=["BUY", "SELL"],
                    index=0 if row["action"] == "BUY" else 1,
                    key=f"action_{i}",
                    label_visibility="collapsed",
                )
            with c2:
                ticker = st.text_input(
                    "Ticker",
                    value=row["ticker"],
                    key=f"ticker_{i}",
                    label_visibility="collapsed",
                )
            with c3:
                shares = st.number_input(
                    "Shares",
                    min_value=0.0,
                    value=float(row["shares"]),
                    step=1.0,
                    key=f"shares_{i}",
                    label_visibility="collapsed",
                )
            with c4:
                exec_price = st.number_input(
                    f"Price ({ccy})",
                    min_value=0.0,
                    value=float(row["exec_price"]),
                    step=0.01,
                    key=f"price_{i}",
                    label_visibility="collapsed",
                )
            with c5:
                commission = st.number_input(
                    "Comm.",
                    min_value=0.0,
                    value=float(row.get("commission", 0.0)),
                    step=0.01,
                    key=f"comm_{i}",
                    label_visibility="collapsed",
                )
            with c6:
                notes = st.text_input(
                    "Notes",
                    value=str(row.get("notes", "")),
                    key=f"notes_{i}",
                    label_visibility="collapsed",
                )
            with c7:
                total_trade = shares * exec_price
                color = "#00d4aa" if action == "BUY" else "#e53935"
                st.markdown(
                    f"<div style='padding-top:0.4rem;font-weight:700;color:{color};font-size:0.85rem;'>"
                    f"{ccy}{total_trade:,.0f}</div>",
                    unsafe_allow_html=True,
                )

            st.markdown("</div>", unsafe_allow_html=True)

            updated_rows.append({
                "action": action,
                "ticker": ticker.upper().strip(),
                "shares": shares,
                "exec_price": exec_price,
                "commission": commission,
                "notes": notes,
                "skip": skip,
            })
            if not skip:
                if action == "BUY":
                    total_buys += shares * exec_price + commission
                else:
                    total_sells += shares * exec_price - commission

    # Add manual trade button
    if st.button("+ Add Manual Trade", key="qpm_add_manual_row"):
        updated_rows.append({
            "action": "BUY",
            "ticker": "",
            "shares": 0.0,
            "exec_price": 0.0,
            "commission": 0.0,
            "notes": "Manual trade",
            "skip": False,
        })
    st.session_state["qpm_trade_rows"] = updated_rows

    # Summary
    net_cash_change = total_sells - total_buys
    resulting_cash = current_cash + net_cash_change
    st.markdown("<hr style='border-color:#e8eaed;margin:1rem 0;'>", unsafe_allow_html=True)
    sc1, sc2, sc3, sc4 = st.columns(4)
    sc1.metric("Total Buys", f"{ccy}{total_buys:,.2f}")
    sc2.metric("Total Sells", f"{ccy}{total_sells:,.2f}")
    net_sign = "+" if net_cash_change >= 0 else ""
    sc3.metric("Net Cash Change", f"{net_sign}{ccy}{net_cash_change:,.2f}")
    sc4.metric("Resulting Cash", f"{ccy}{resulting_cash:,.2f}")

    if resulting_cash < 0:
        st.warning(f"Warning: resulting cash would be negative ({ccy}{resulting_cash:,.2f}). Check your trade amounts.")

    col_back, col_proceed, _ = st.columns([1, 1, 4])
    with col_back:
        if st.button("← Back", key="qpm_back_step1"):
            st.session_state["qpm_rebalance_step"] = 1
            st.rerun()
    with col_proceed:
        if st.button("Confirm & Update Portfolio →", type="primary", key="qpm_proceed_step3"):
            st.session_state["qpm_rebalance_step"] = 3
            st.rerun()


def _rebalance_step3(portfolio, portfolio_id, ccy, current_cash, prices):
    st.subheader("Review & Apply")

    trade_rows = [r for r in st.session_state.get("qpm_trade_rows", []) if not r.get("skip")]
    if not trade_rows:
        st.warning("No trades to apply (all are skipped).")
        if st.button("← Back", key="qpm_back_step2_empty"):
            st.session_state["qpm_rebalance_step"] = 2
            st.rerun()
        return

    # Get suggestion for comparison
    suggestion = st.session_state.get("qpm_suggestion", {})
    suggested_trades = []
    if suggestion:
        holdings_df = get_quant_holdings(portfolio_id)
        current_holdings_list = [
            {"ticker": r["ticker"], "shares": float(r["shares"]), "avg_entry_price": float(r["avg_entry_price"])}
            for _, r in holdings_df.iterrows()
        ] if not holdings_df.empty else []
        portfolio_df = suggestion.get("portfolio_df", pd.DataFrame())
        model_prices = suggestion.get("prices", {})
        suggested_trades = compute_rebalance_trades(current_holdings_list, portfolio_df, model_prices)

    suggested_map = {t["ticker"]: t for t in suggested_trades}

    st.markdown("**Trades to be applied:**")
    deviations = []
    for row in trade_rows:
        sugg = suggested_map.get(row["ticker"])
        flags = []
        if sugg:
            sugg_shares = float(sugg.get("suggested_shares", 0)) if row["action"] == "BUY" else float(sugg.get("current_shares", 0)) - float(sugg.get("suggested_shares", 0))
            if sugg_shares > 0 and abs(row["shares"] - sugg_shares) / sugg_shares > 0.10:
                flags.append(f"Shares deviate >10% from suggestion ({sugg_shares:.0f} suggested)")
            sugg_price = float(sugg.get("price", 0))
            if sugg_price > 0 and abs(row["exec_price"] - sugg_price) / sugg_price > 0.01:
                flags.append(f"Price deviates >1% from suggestion ({ccy}{sugg_price:.2f} suggested)")

        color = "#00d4aa" if row["action"] == "BUY" else "#e53935"
        flag_html = ""
        if flags:
            deviations.append((row["ticker"], flags))
            flag_html = (
                f'<span style="color:#d97706;font-size:0.75rem;margin-left:8px;">'
                f'⚠ {"; ".join(flags)}</span>'
            )

        st.markdown(
            f'<div style="background:#f7f8fa;border:1px solid #e8eaed;border-radius:8px;'
            f'padding:0.6rem 1rem;margin-bottom:0.4rem;">'
            f'<span style="font-weight:700;color:{color};">{row["action"]}</span> '
            f'<span style="font-weight:600;">{row["ticker"]}</span> '
            f'&nbsp;{row["shares"]:.0f} shares @ {ccy}{row["exec_price"]:.2f} '
            f'= <b>{ccy}{row["shares"]*row["exec_price"]:,.2f}</b>'
            f'{flag_html}</div>',
            unsafe_allow_html=True,
        )

    if deviations:
        st.warning(f"{len(deviations)} trade(s) deviate from model suggestion. Review before applying.")

    col_back, col_apply, _ = st.columns([1, 1, 4])
    with col_back:
        if st.button("← Back", key="qpm_back_step2"):
            st.session_state["qpm_rebalance_step"] = 2
            st.rerun()
    with col_apply:
        if st.button(t("qpm_btn_apply"), type="primary", key="qpm_apply_btn"):
            regime_info = suggestion.get("regime_info", {}) if suggestion else {}
            regime = regime_info.get("regime", "RISK_ON")
            suggestion_json = json.dumps(suggested_trades)

            # Top tickers from momentum for streak tracking
            top_tickers = []
            if suggestion and "portfolio_df" in suggestion and not suggestion["portfolio_df"].empty:
                top_tickers = suggestion["portfolio_df"]["ticker"].tolist()[:5]

            _apply_trades_to_portfolio(
                portfolio_id=portfolio_id,
                trade_rows=trade_rows,
                regime=regime,
                suggestion_json=suggestion_json,
                prices={**prices, **suggestion.get("prices", {})},
                top_tickers=top_tickers,
            )
            st.success("Portfolio updated successfully!")
            st.session_state["qpm_rebalance_step"] = 1
            st.session_state["qpm_suggestion"] = None
            st.session_state["qpm_trade_rows"] = []
            st.rerun()


def _render_adhoc_trade(portfolio_id, ccy, current_cash):
    with st.form("adhoc_trade_form"):
        st.markdown("**Log an ad-hoc trade outside of rebalance cycle**")
        c1, c2, c3, c4, c5 = st.columns([1.5, 1, 1.5, 1.5, 2])
        with c1:
            ticker = st.text_input("Ticker", placeholder="e.g. XLE", key="adhoc_ticker")
        with c2:
            action = st.selectbox("Action", ["BUY", "SELL"], key="adhoc_action")
        with c3:
            shares = st.number_input("Shares", min_value=0.0, step=1.0, key="adhoc_shares")
        with c4:
            price = st.number_input(f"Price ({ccy})", min_value=0.0, step=0.01, key="adhoc_price")
        with c5:
            notes = st.text_input("Notes", placeholder="Reason for trade", key="adhoc_notes")
        commission = st.number_input("Commission", min_value=0.0, value=0.0, step=0.01, key="adhoc_comm")

        if st.form_submit_button("Log Ad-hoc Trade"):
            if not ticker.strip():
                st.error("Ticker is required.")
            elif shares <= 0 or price <= 0:
                st.error("Shares and price must be > 0.")
            else:
                ticker_upper = ticker.upper().strip()
                log_quant_trade(
                    portfolio_id=portfolio_id,
                    ticker=ticker_upper,
                    action=action,
                    shares=shares,
                    price=price,
                    commission=commission,
                    trade_type="Manual",
                    notes=notes,
                )
                # Update holding
                holdings_df = get_quant_holdings(portfolio_id)
                holding = holdings_df[holdings_df["ticker"] == ticker_upper] if not holdings_df.empty else pd.DataFrame()
                if action == "BUY":
                    if holding.empty:
                        upsert_quant_holding(portfolio_id, ticker_upper, shares, price)
                    else:
                        old_shares = float(holding.iloc[0]["shares"])
                        old_avg = float(holding.iloc[0]["avg_entry_price"])
                        new_shares = old_shares + shares
                        new_avg = (old_shares * old_avg + shares * price) / new_shares
                        upsert_quant_holding(portfolio_id, ticker_upper, new_shares, new_avg)
                    new_cash = current_cash - shares * price - commission
                else:
                    if not holding.empty:
                        old_shares = float(holding.iloc[0]["shares"])
                        new_shares = max(0.0, old_shares - shares)
                        upsert_quant_holding(portfolio_id, ticker_upper, new_shares, float(holding.iloc[0]["avg_entry_price"]))
                    new_cash = current_cash + shares * price - commission
                update_quant_cash(portfolio_id, new_cash)
                st.success(f"Trade logged: {action} {shares:.0f} {ticker_upper} @ {ccy}{price:.2f}")
                st.rerun()


def _render_cash_management(portfolio_id, current_cash, ccy):
    with st.form("cash_form"):
        col1, col2 = st.columns(2)
        with col1:
            cash_type = st.radio("Type", ["Deposit", "Withdrawal"], horizontal=True, key="cash_type")
        with col2:
            amount = st.number_input(f"Amount ({ccy})", min_value=0.0, step=100.0, key="cash_amount")
        notes = st.text_input("Notes", placeholder="e.g. Monthly contribution", key="cash_notes")

        if st.form_submit_button("Apply Cash Change"):
            if amount <= 0:
                st.error("Amount must be > 0.")
            else:
                if cash_type == "Deposit":
                    new_cash = current_cash + amount
                    action_label = "DEPOSIT"
                else:
                    if amount > current_cash:
                        st.error(f"Insufficient cash. Available: {ccy}{current_cash:,.2f}")
                        return
                    new_cash = current_cash - amount
                    action_label = "WITHDRAWAL"
                update_quant_cash(portfolio_id, new_cash)
                log_quant_trade(
                    portfolio_id=portfolio_id,
                    ticker="CASH",
                    action=action_label,
                    shares=0,
                    price=0,
                    commission=0,
                    trade_type="Cash",
                    notes=notes or f"{cash_type} of {ccy}{amount:,.2f}",
                )
                st.success(f"{cash_type} of {ccy}{amount:,.2f} applied. New cash: {ccy}{new_cash:,.2f}")
                st.rerun()


# ── Tab 3: Trade History ───────────────────────────────────────────────────────

def _render_trade_history(portfolio_id, ccy):
    trades_df = get_quant_trades(portfolio_id)

    if trades_df.empty:
        st.info("No trades recorded yet.")
        return

    # Filters
    f1, f2, f3 = st.columns([2, 2, 2])
    with f1:
        min_date = pd.to_datetime(trades_df["executed_at"].min()).date() if "executed_at" in trades_df.columns else date.today()
        max_date = date.today()
        date_range = st.date_input(
            "Date Range",
            value=(min_date, max_date),
            key="trade_hist_date_range",
        )
    with f2:
        trade_types = trades_df["trade_type"].unique().tolist() if "trade_type" in trades_df.columns else []
        selected_types = st.multiselect(
            "Trade Type",
            options=trade_types,
            default=trade_types,
            key="trade_hist_type_filter",
        )
    with f3:
        ticker_filter = st.text_input("Ticker", placeholder="Filter by ticker...", key="trade_hist_ticker")

    filtered = trades_df.copy()
    if "executed_at" in filtered.columns:
        filtered["executed_at"] = pd.to_datetime(filtered["executed_at"])
        if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
            start_dt, end_dt = date_range
            filtered = filtered[
                (filtered["executed_at"].dt.date >= start_dt)
                & (filtered["executed_at"].dt.date <= end_dt)
            ]
    if selected_types:
        filtered = filtered[filtered["trade_type"].isin(selected_types)]
    if ticker_filter.strip():
        filtered = filtered[filtered["ticker"].str.upper().str.contains(ticker_filter.upper().strip())]

    # Display
    display = filtered[["executed_at", "trade_type", "ticker", "action", "shares", "price", "commission", "notes"]].copy()
    display["total"] = display["shares"] * display["price"]
    display.columns = ["Date", "Type", "Ticker", "Action", "Shares", f"Price ({ccy})", f"Comm. ({ccy})", "Notes", f"Total ({ccy})"]

    def style_action(val):
        if val == "BUY":
            return "color: #00d4aa; font-weight: 700"
        elif val == "SELL":
            return "color: #e53935; font-weight: 700"
        return ""

    styled = display.style.applymap(style_action, subset=["Action"])
    st.dataframe(styled, use_container_width=True, hide_index=True)

    # Download CSV
    csv = filtered.to_csv(index=False)
    st.download_button(
        "Download CSV",
        data=csv,
        file_name=f"quant_trades_{portfolio_id}_{date.today()}.csv",
        mime="text/csv",
        key="trade_hist_download",
    )


# ── Tab 4: Model Details ───────────────────────────────────────────────────────

def _render_model_details(portfolio, currency, risk_mode, ccy):
    st.subheader("How This Model Works")

    st.markdown("""
This portfolio manager runs a **4-layer systematic ETF rotation model** every 3 trading days.
It combines a macro regime filter, momentum ranking, a short-term mean-reversion overlay,
and risk-based position sizing to decide which ETFs to hold and how much to allocate to each.

---

### Layer 1 — Regime Filter
The model first checks whether the overall market is in a healthy trend or under stress.
It does this by fetching the last 250 trading days of the benchmark index
(S&P 500 via **SPY** for USD portfolios, or **XSP.TO** for CAD portfolios) and computing
its 200-day and 50-day simple moving averages.

- **RISK ON** — benchmark price is above both the 200-day and 50-day MA. Full universe active.
- **CAUTION** — above the 200-day MA but below the 50-day. Fewer positions taken.
- **RISK OFF** — below the 200-day MA. Universe narrows to defensive assets only (bonds, gold, utilities).

The regime directly controls how many positions are held and which ETFs are eligible.
In Risk Off, the goal shifts from growth to capital preservation.

---

### Layer 2 — Momentum Ranking
Every eligible ETF in the universe is scored on recent price momentum.
The model computes three metrics for each ETF from the last 60 trading days:

- **40-day total return** — the main trend signal
- **20-day total return** — a shorter confirmation signal
- **Risk-adjusted momentum** — the 40-day return divided by annualized volatility
  (rewards strong returns that weren't achieved through excessive risk)

Each metric is converted to a z-score across the universe (so every ETF is ranked relative
to its peers, not on absolute numbers). The final **composite score** is a weighted average
of these z-scores.

**Conservative mode** weights risk-adjusted momentum most heavily (60%), rewarding
ETFs that trend steadily rather than violently.

**Aggressive mode** shifts more weight toward raw 40-day return (30%) and adds a
**trend persistence bonus** — ETFs that have ranked in the top 5 for multiple consecutive
rebalance cycles receive a bonus score (up to +1.0 after 5 cycles). This rewards
sustained leadership and is what allows the model to concentrate heavily in a
sector like tech during a multi-year bull run.

---

### Layer 3 — Mean Reversion Overlay
Before finalizing the ranking, the model checks whether top-ranked ETFs have recently
pulled back to a better entry point. For each ETF it computes a **pullback score** from
the last 5 trading days using:

- 5-day RSI (lower = more oversold = better entry)
- Bollinger Band position (price near the lower band = better entry)
- 5-day return (a recent dip improves the score)

A small pullback bonus is added to the composite score from Layer 2.
In **Conservative mode** the overlay carries more weight (0.3×), since it makes sense
to wait for dips before buying steady assets. In **Aggressive mode** the overlay is
reduced (0.15×) — strong trends rarely pull back deeply, and waiting for a dip means
missing the move.

---

### Layer 4 — Portfolio Construction
The top-ranked ETFs (N depends on regime and risk mode) are selected.
Their capital allocations are then sized:

**Conservative** uses **inverse-volatility weighting** — each ETF is weighted in
inverse proportion to its recent volatility, so lower-volatility positions get more
capital. This ensures no single volatile ETF dominates the portfolio's risk.

**Aggressive** uses **momentum-weighted sizing** — each ETF is weighted in proportion
to its composite momentum score. The ETF with the highest score gets the largest
allocation. This can result in 50%+ going into a single ETF when one sector is
clearly dominant.

In both modes, position weights are clamped to a minimum and maximum (to avoid
over-concentration or meaningless tiny positions), and a small cash buffer is always
held (5% Conservative, 3% Aggressive). Share counts are rounded down to whole shares;
any remainder stays as cash.

---

### Rebalance Cadence
The model is designed to run every **3 trading days** (roughly once a week).
Rebalancing more frequently generates excessive turnover and transaction costs.
Rebalancing less frequently allows positions to drift significantly from target weights
and misses regime changes.

The suggested next rebalance date is shown at the top of the Rebalance tab.

---

### Conservative vs Aggressive — Summary
""")

    params_c = PARAMS["Conservative"]
    params_a = PARAMS["Aggressive"]

    comparison = pd.DataFrame({
        "Parameter": [
            "Universe (RISK ON)", "Universe (RISK OFF)", "Max positions (RISK ON)",
            "Max positions (CAUTION)", "Max single weight", "Min single weight",
            "Cash buffer", "Position sizing", "Stop-loss threshold",
            "Mean reversion overlay weight",
        ],
        "Conservative": [
            "All ETFs (25 USD / 15 CAD)", "Bonds, gold, utilities only",
            str(params_c["max_positions"]["RISK_ON"]),
            str(params_c["max_positions"]["CAUTION"]),
            f"{params_c['max_weight']*100:.0f}%", f"{params_c['min_weight']*100:.0f}%",
            f"{params_c['cash_buffer']*100:.0f}%", "Inverse volatility",
            f"{params_c['stop_loss']*100:.0f}%", "0.30×",
        ],
        "Aggressive": [
            "Equity ETFs only (15 USD / 12 CAD)", "Bonds, gold, utilities added back",
            str(params_a["max_positions"]["RISK_ON"]),
            str(params_a["max_positions"]["CAUTION"]),
            f"{params_a['max_weight']*100:.0f}%", f"{params_a['min_weight']*100:.0f}%",
            f"{params_a['cash_buffer']*100:.0f}%", "Momentum-weighted",
            f"{params_a['stop_loss']*100:.0f}%", "0.15×",
        ],
    })

    st.dataframe(
        comparison.style.apply(
            lambda col: ["font-weight:700" if col.name == "Parameter" else "" for _ in col], axis=0
        ),
        use_container_width=True,
        hide_index=True,
    )

    if currency == "CAD":
        st.info(
            "**CAD note:** The CAD universe uses TSX-listed ETFs that hold similar underlying assets "
            "to their USD counterparts, but some behave differently — XEG.TO tracks Canadian oil sands "
            "companies (not US majors), XIT.TO is heavily concentrated in Shopify (~40–50%), and the "
            "bond ETF (XBB.TO) tracks Canadian aggregate bonds rather than US Treasuries. "
            "The model logic is identical; only the tickers and regime benchmark (XSP.TO) change."
        )


# ── Tab 5: Performance ────────────────────────────────────────────────────────

def _render_performance(portfolio_id, ccy, current_cash, holdings_rich, prices):
    snapshots_df = get_quant_snapshots(portfolio_id)
    rebalances_df = get_quant_rebalances(portfolio_id)
    portfolio = get_quant_portfolio(portfolio_id)
    starting_cash = float(portfolio.get("starting_cash", 0.0))
    total_value = holdings_rich["market_value"].sum() if not holdings_rich.empty else 0.0
    total_value += current_cash

    # ── Performance metrics ────────────────────────────────────────────────────
    total_return_pct = (total_value / starting_cash - 1) * 100 if starting_cash > 0 else 0.0

    ann_return = None
    max_drawdown = None
    sharpe = None
    n_rebalances = len(rebalances_df) if not rebalances_df.empty else 0

    if not snapshots_df.empty and len(snapshots_df) >= 2:
        snapshots_df["created_at"] = pd.to_datetime(snapshots_df["created_at"])
        values = snapshots_df["total_value"].values.astype(float)
        dates = snapshots_df["created_at"]

        # Annualized return
        days_elapsed = (dates.iloc[-1] - dates.iloc[0]).days
        if days_elapsed > 0:
            ann_return = (total_value / float(values[0]) - 1) * (365 / days_elapsed) * 100

        # Max drawdown
        rolling_max = np.maximum.accumulate(values)
        drawdown = (values - rolling_max) / rolling_max
        max_drawdown = float(drawdown.min()) * 100

        # Simple Sharpe (daily returns from snapshots)
        daily_ret = pd.Series(values).pct_change().dropna()
        if len(daily_ret) > 1:
            sharpe = (daily_ret.mean() / daily_ret.std() * np.sqrt(252)) if daily_ret.std() > 0 else None

    # Win rate from trades
    trades_df = get_quant_trades(portfolio_id)
    win_rate = None
    if not trades_df.empty:
        sells = trades_df[trades_df["action"] == "SELL"]
        if not sells.empty:
            wins = len(sells[sells["price"] > 0])  # placeholder — real win rate needs avg cost comparison
            win_rate = wins / len(sells) * 100

    # Summary metrics
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Total Return", f"{'+' if total_return_pct >= 0 else ''}{total_return_pct:.2f}%")
    m2.metric("Ann. Return", f"{ann_return:+.2f}%" if ann_return is not None else "—")
    m3.metric("Max Drawdown", f"{max_drawdown:.2f}%" if max_drawdown is not None else "—")
    m4.metric("Sharpe Ratio", f"{sharpe:.2f}" if sharpe is not None else "—")
    m5.metric("# Rebalances", str(n_rebalances))
    m6.metric("Win Rate", f"{win_rate:.1f}%" if win_rate is not None else "—")

    # ── Cumulative P&L chart ───────────────────────────────────────────────────
    if not snapshots_df.empty and len(snapshots_df) >= 2:
        st.subheader("Portfolio Value Over Time")
        snapshots_df["cum_pnl"] = snapshots_df["total_value"] - starting_cash

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=snapshots_df["created_at"],
            y=snapshots_df["cum_pnl"],
            mode="lines",
            line=dict(color="#00c896", width=2.5),
            fill="tozeroy",
            fillcolor="rgba(0,200,150,0.08)",
            name="Cumulative P&L",
            hovertemplate=f"P&L: {ccy}%{{y:,.2f}}<extra></extra>",
        ))
        fig.add_hline(y=0, line_dash="dash", line_color="#e8eaed")
        fig.update_layout(
            plot_bgcolor="#ffffff",
            paper_bgcolor="#ffffff",
            xaxis=dict(showgrid=False, tickfont=dict(color="#6b7280", size=11)),
            yaxis=dict(
                showgrid=True,
                gridcolor="#f3f4f6",
                tickfont=dict(color="#6b7280", size=11),
                tickprefix=ccy,
            ),
            margin=dict(l=10, r=10, t=10, b=10),
            height=300,
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Not enough snapshots to display equity chart. Run the model and apply trades to generate history.")

    # ── Rebalance history table ────────────────────────────────────────────────
    if not rebalances_df.empty:
        st.subheader("Rebalance History")
        rebalances_df["created_at"] = pd.to_datetime(rebalances_df["created_at"])

        reb_display = []
        prev_value = starting_cash
        for _, row in rebalances_df.iterrows():
            # Find closest snapshot
            snap_val = None
            if not snapshots_df.empty:
                snapshots_df["created_at"] = pd.to_datetime(snapshots_df["created_at"])
                nearby = snapshots_df[
                    snapshots_df["created_at"] >= row["created_at"]
                ]
                if not nearby.empty:
                    snap_val = float(nearby.iloc[0]["total_value"])

            suggestion = {}
            if row.get("suggestion_json"):
                try:
                    suggestion = json.loads(row["suggestion_json"])
                except Exception:
                    suggestion = {}

            n_positions = len(suggestion) if isinstance(suggestion, list) else 0

            pnl_since = (snap_val - prev_value) if snap_val else None
            if snap_val:
                prev_value = snap_val

            reb_display.append({
                "Date": row["created_at"].strftime("%Y-%m-%d %H:%M"),
                "Regime": row.get("regime", "—"),
                "# Positions": n_positions,
                "Portfolio Value": f"{ccy}{snap_val:,.2f}" if snap_val else "—",
                "P&L Since Last": f"{ccy}{pnl_since:+,.2f}" if pnl_since is not None else "—",
            })

        st.dataframe(pd.DataFrame(reb_display), use_container_width=True, hide_index=True)

    # ── Model Accuracy ─────────────────────────────────────────────────────────
    if not rebalances_df.empty:
        st.subheader("Model Accuracy")
        st.caption("Compares what the model suggested vs what was actually executed.")

        total_sugg = 0
        total_actual = 0
        matching = 0

        for _, row in rebalances_df.iterrows():
            try:
                sugg = json.loads(row.get("suggestion_json", "[]"))
                actual = json.loads(row.get("actual_json", "[]"))
                if not isinstance(sugg, list):
                    sugg = []
                if not isinstance(actual, list):
                    actual = []
                total_sugg += len(sugg)
                total_actual += len(actual)
                sugg_tickers = {t.get("ticker") for t in sugg if isinstance(t, dict)}
                actual_tickers = {t.get("ticker") for t in actual if isinstance(t, dict) if not t.get("skip")}
                matching += len(sugg_tickers & actual_tickers)
            except Exception:
                continue

        if total_sugg > 0:
            accuracy = matching / total_sugg * 100
            ac1, ac2, ac3 = st.columns(3)
            ac1.metric("Total Suggested Trades", str(total_sugg))
            ac2.metric("Total Actual Trades", str(total_actual))
            ac3.metric("Ticker Match Rate", f"{accuracy:.1f}%")


# ── Portfolio Creation Form ────────────────────────────────────────────────────

def _render_create_form():
    st.subheader("Create New Quant Portfolio")
    st.markdown(
        "Set up a systematic ETF rotation portfolio. The model will automatically "
        "select ETFs based on momentum, regime, and mean reversion signals.",
    )

    with st.form("qpm_create_form"):
        name = st.text_input(
            "Portfolio Name",
            placeholder="e.g. TFSA Quant, Aggressive Growth",
            key="qpm_create_name",
        )
        col1, col2 = st.columns(2)
        with col1:
            currency = st.radio(
                "Currency",
                options=["USD", "CAD"],
                horizontal=True,
                key="qpm_create_currency",
            )
        with col2:
            risk_mode = st.radio(
                "Risk Mode",
                options=["Conservative", "Aggressive"],
                horizontal=True,
                key="qpm_create_risk",
            )

        # Risk mode descriptions
        risk_desc = {
            "Conservative": (
                "Max 4 positions, inverse-volatility sizing, 35% max weight, 5% cash buffer, "
                "5% stop-loss. Prefers diversification and lower drawdown."
            ),
            "Aggressive": (
                "Max 3 positions, momentum-weighted sizing, 55% max weight, 3% cash buffer, "
                "8% stop-loss. Concentrates in highest-conviction ideas."
            ),
        }
        sel_risk = st.session_state.get("qpm_create_risk", "Conservative")
        st.info(f"**{sel_risk}:** {risk_desc.get(sel_risk, '')}")

        starting_cash = st.number_input(
            "Starting Cash",
            min_value=0.0,
            value=10000.0,
            step=1000.0,
            help="Total investable capital for this portfolio",
            key="qpm_create_cash",
        )

        submitted = st.form_submit_button("Create Portfolio", type="primary")

    if submitted:
        if not name.strip():
            st.error("Portfolio name is required.")
            return

        portfolio_id = create_quant_portfolio(
            name=name.strip(),
            currency=currency,
            risk_mode=risk_mode,
            starting_cash=starting_cash,
        )
        st.session_state["qpm_selected_id"] = portfolio_id
        st.session_state["qpm_show_create"] = False
        st.session_state["qpm_suggestion"] = None
        st.session_state["qpm_rebalance_step"] = 1

        st.success(
            f"Portfolio **{name}** created! "
            "Go to the **Rebalance** tab to run the model and build your initial holdings."
        )
        st.rerun()
