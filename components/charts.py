import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from i18n import t

# ── Theme constants (light) ────────────────────────────────────────────────────
BG      = "#ffffff"
CARD_BG = "#ffffff"
ACCENT  = "#00b386"
RED     = "#e53935"
TEXT    = "#374151"
GRID    = "#f0f0f0"
SUBTEXT = "#9ca3af"

LAYOUT_DEFAULTS = dict(
    paper_bgcolor=BG,
    plot_bgcolor=BG,
    font=dict(color=TEXT, family="Inter, Segoe UI, system-ui, sans-serif", size=12),
    xaxis=dict(gridcolor=GRID, zerolinecolor=GRID, linecolor="#e8eaed", tickfont=dict(color=SUBTEXT)),
    yaxis=dict(gridcolor=GRID, zerolinecolor=GRID, linecolor="#e8eaed", tickfont=dict(color=SUBTEXT)),
    margin=dict(l=40, r=20, t=45, b=40),
    legend=dict(bgcolor=BG, bordercolor=GRID, borderwidth=1, font=dict(color=TEXT)),
    title=dict(font=dict(color="#1a1a2e", size=14, family="Inter, Segoe UI, sans-serif")),
)


def apply_theme(fig: go.Figure) -> go.Figure:
    fig.update_layout(**LAYOUT_DEFAULTS)
    return fig


# ── Portfolio value over time ──────────────────────────────────────────────────

def portfolio_value_chart(values: pd.Series, currency: str = "CAD", is_estimated: bool = False) -> go.Figure:
    """Filled area chart of portfolio value over time."""
    fig = go.Figure()
    if values.empty:
        fig.add_annotation(text=t("chart_no_history"), showarrow=False,
                           font=dict(color=TEXT, size=14))
        return apply_theme(fig)

    fig.add_trace(
        go.Scatter(
            x=values.index,
            y=values.values,
            mode="lines",
            name=t("card_total_value"),
            line=dict(color=ACCENT, width=2),
            fill="tozeroy",
            fillcolor="rgba(0,212,170,0.1)",
            hovertemplate=f"%{{x|%Y-%m-%d}}<br>$%{{y:,.2f}} {currency}<extra></extra>",
        )
    )
    title = t("chart_port_value_est") if is_estimated else t("chart_port_value")
    fig.update_layout(
        title=title,
        xaxis_title=t("chart_date"),
        yaxis_title=f"{t('chart_value')} ({currency})",
    )
    return apply_theme(fig)


# ── P&L by position ────────────────────────────────────────────────────────────

def pnl_bar_chart(holdings: pd.DataFrame) -> go.Figure:
    """Horizontal bar chart of unrealized P&L per position."""
    fig = go.Figure()
    if holdings.empty or "unrealized_pnl" not in holdings.columns:
        fig.add_annotation(text=t("chart_no_holdings"), showarrow=False,
                           font=dict(color=TEXT, size=14))
        return apply_theme(fig)

    df = holdings.sort_values("unrealized_pnl")
    colors = [ACCENT if v >= 0 else RED for v in df["unrealized_pnl"]]

    fig.add_trace(
        go.Bar(
            x=df["unrealized_pnl"],
            y=df["ticker"],
            orientation="h",
            marker_color=colors,
            text=[f"${v:,.2f}" for v in df["unrealized_pnl"]],
            textposition="outside",
            hovertemplate="%{y}<br>P&L: $%{x:,.2f}<extra></extra>",
        )
    )
    fig.update_layout(title=t("chart_pnl"), xaxis_title=t("chart_pnl_axis"),
                      yaxis_title=t("chart_ticker"))
    return apply_theme(fig)


# ── Drawdown chart ─────────────────────────────────────────────────────────────

def drawdown_chart(drawdown_series: pd.Series) -> go.Figure:
    """Area chart of portfolio drawdown percentage over time."""
    fig = go.Figure()
    if drawdown_series.empty:
        fig.add_annotation(text=t("chart_no_drawdown"), showarrow=False,
                           font=dict(color=TEXT, size=14))
        return apply_theme(fig)

    fig.add_trace(
        go.Scatter(
            x=drawdown_series.index,
            y=drawdown_series.values,
            mode="lines",
            name=t("chart_drawdown_trace"),
            line=dict(color=RED, width=1.5),
            fill="tozeroy",
            fillcolor="rgba(255,71,87,0.15)",
            hovertemplate="%{x|%Y-%m-%d}<br>" + t("chart_drawdown_trace") + ": %{y:.2f}%<extra></extra>",
        )
    )
    fig.update_layout(title=t("chart_drawdown"), xaxis_title=t("chart_date"),
                      yaxis_title=t("chart_drawdown_axis"))
    return apply_theme(fig)


# ── Rolling Sharpe ─────────────────────────────────────────────────────────────

def rolling_sharpe_chart(rolling_sharpe: pd.Series) -> go.Figure:
    """Line chart of 30-day rolling Sharpe ratio."""
    fig = go.Figure()
    if rolling_sharpe.empty:
        fig.add_annotation(text=t("chart_no_sharpe"),
                           showarrow=False, font=dict(color=TEXT, size=14))
        return apply_theme(fig)

    fig.add_trace(
        go.Scatter(
            x=rolling_sharpe.index,
            y=rolling_sharpe.values,
            mode="lines",
            name=t("chart_30d_sharpe"),
            line=dict(color="#a78bfa", width=2),
            hovertemplate="%{x|%Y-%m-%d}<br>Sharpe: %{y:.2f}<extra></extra>",
        )
    )
    fig.add_hline(y=1.0, line_dash="dash", line_color=ACCENT, opacity=0.5,
                  annotation_text=t("chart_sharpe_ref"), annotation_font_color=TEXT)
    fig.add_hline(y=0.0, line_dash="dot", line_color=RED, opacity=0.4)
    fig.update_layout(title=t("chart_rolling_sharpe"), xaxis_title=t("chart_date"),
                      yaxis_title=t("chart_sharpe_axis"))
    return apply_theme(fig)


# ── Sector pie ─────────────────────────────────────────────────────────────────

def sector_pie_chart(sector_data: dict) -> go.Figure:
    """Pie chart of portfolio allocation by sector."""
    fig = go.Figure()
    if not sector_data:
        fig.add_annotation(text=t("chart_no_sector"), showarrow=False,
                           font=dict(color=TEXT, size=14))
        return apply_theme(fig)

    labels = list(sector_data.keys())
    values = list(sector_data.values())
    colors = px.colors.qualitative.Set2

    fig.add_trace(
        go.Pie(
            labels=labels,
            values=values,
            hole=0.4,
            marker=dict(colors=colors[:len(labels)], line=dict(color=BG, width=2)),
            textfont=dict(color=TEXT),
            hovertemplate="%{label}<br>%{value:.1f}%<extra></extra>",
        )
    )
    fig.update_layout(
        title=t("chart_sector"),
        paper_bgcolor=BG,
        font=dict(color=TEXT, family="Inter, Segoe UI, sans-serif"),
        legend=dict(bgcolor=BG, font=dict(color=TEXT)),
        margin=dict(l=20, r=20, t=40, b=20),
    )
    return fig


# ── Individual stock comparison ────────────────────────────────────────────────

def stock_comparison_chart(hist: pd.DataFrame) -> go.Figure:
    """Normalised (base-100) multi-line chart comparing tickers."""
    fig = go.Figure()
    if hist.empty:
        fig.add_annotation(text=t("chart_no_comparison"), showarrow=False,
                           font=dict(color=TEXT, size=14))
        return apply_theme(fig)

    palette = [ACCENT, "#a78bfa", "#f59e0b", "#38bdf8", RED, "#fb923c", "#4ade80"]
    for i, col in enumerate(hist.columns):
        series = hist[col].dropna()
        if series.empty:
            continue
        normalised = series / series.iloc[0] * 100
        fig.add_trace(
            go.Scatter(
                x=normalised.index,
                y=normalised.values,
                mode="lines",
                name=col,
                line=dict(color=palette[i % len(palette)], width=2),
                hovertemplate=f"{col}: %{{y:.1f}}<extra></extra>",
            )
        )

    fig.add_hline(y=100, line_dash="dot", line_color=GRID, opacity=0.6)
    fig.update_layout(title=t("chart_comparison"), xaxis_title=t("chart_date"),
                      yaxis_title=t("chart_indexed"))
    return apply_theme(fig)


# ── Weight doughnut ────────────────────────────────────────────────────────────

def weight_donut_chart(holdings: pd.DataFrame) -> go.Figure:
    """Portfolio weight distribution as a donut chart."""
    fig = go.Figure()
    if holdings.empty or "weight_pct" not in holdings.columns:
        fig.add_annotation(text=t("chart_no_weight"), showarrow=False,
                           font=dict(color=TEXT, size=14))
        return apply_theme(fig)

    colors = px.colors.qualitative.Set2
    fig.add_trace(
        go.Pie(
            labels=holdings["ticker"],
            values=holdings["weight_pct"],
            hole=0.5,
            marker=dict(colors=colors[:len(holdings)], line=dict(color=BG, width=2)),
            textfont=dict(color=TEXT),
            hovertemplate="%{label}: %{value:.1f}%<extra></extra>",
        )
    )
    fig.update_layout(
        title=t("chart_weight"),
        paper_bgcolor=BG,
        font=dict(color=TEXT, family="Inter, Segoe UI, sans-serif"),
        legend=dict(bgcolor=BG, font=dict(color=TEXT)),
        margin=dict(l=20, r=20, t=40, b=20),
    )
    return fig
