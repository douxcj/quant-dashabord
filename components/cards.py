import streamlit as st
from i18n import t


def metric_card(col, label: str, value: str, delta: str = "", delta_color: str = "normal"):
    """Render a styled metric card inside a Streamlit column."""
    with col:
        st.metric(label=label, value=value, delta=delta if delta else None,
                  delta_color=delta_color)


def render_summary_cards(summary: dict, currency_symbol: str = "$"):
    """Render the top-level portfolio summary row of metric cards."""
    c1, c2, c3, c4, c5, c6 = st.columns(6)

    pnl = summary.get("unrealized_pnl", 0)
    pnl_pct = summary.get("unrealized_pnl_pct", 0)
    total_ret = summary.get("total_return", 0)
    total_ret_pct = summary.get("total_return_pct", 0)

    pnl_str = f"{'+' if pnl >= 0 else ''}{currency_symbol}{pnl:,.2f}"
    pnl_delta = f"{'+' if pnl_pct >= 0 else ''}{pnl_pct:.2f}%"
    ret_str = f"{'+' if total_ret >= 0 else ''}{currency_symbol}{total_ret:,.2f}"
    ret_delta = f"{'+' if total_ret_pct >= 0 else ''}{total_ret_pct:.2f}%"

    metric_card(c1, t("card_total_value"),
                f"{currency_symbol}{summary.get('portfolio_value', 0):,.2f}")
    metric_card(c2, t("card_stock_value"),
                f"{currency_symbol}{summary.get('market_value', 0):,.2f}")
    metric_card(c3, t("card_cash"),
                f"{currency_symbol}{summary.get('cash_remaining', 0):,.2f}")
    metric_card(c4, t("card_unrealized_pnl"), pnl_str, pnl_delta,
                delta_color="normal" if pnl >= 0 else "inverse")
    metric_card(c5, t("card_total_return"), ret_str, ret_delta,
                delta_color="normal" if total_ret >= 0 else "inverse")
    metric_card(c6, t("card_positions"),
                str(len(summary.get("holdings", []))))


def color_pnl(val: float) -> str:
    """Return a CSS color string based on sign."""
    return "#00d4aa" if val >= 0 else "#ff4757"


def signal_badge(signal: str) -> str:
    """Return HTML badge for a signal strength label."""
    colors = {
        "Strong Buy": "#00d4aa",
        "Buy": "#4caf50",
        "Weak Buy": "#8bc34a",
        "Hold": "#9e9e9e",
        "Weak Sell": "#ff9800",
        "Sell": "#ff5722",
        "Strong Sell": "#ff4757",
        "No Data": "#555",
    }
    color = colors.get(signal, "#555")
    return (
        f'<span style="background:{color};color:white;padding:2px 8px;'
        f'border-radius:4px;font-size:0.8em;font-weight:600;">{signal}</span>'
    )
