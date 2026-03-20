import pandas as pd
import numpy as np
from database import get_trades, get_total_deposited
from market_data import fetch_current_prices, fetch_historical_data


def calculate_holdings(account_id: int) -> pd.DataFrame:
    """
    Aggregate all trades into current open positions.
    Returns DataFrame: ticker | shares | avg_cost | total_cost
    Uses FIFO-style cost averaging on sells.
    """
    trades = get_trades(account_id)
    if trades.empty:
        return pd.DataFrame(columns=["ticker", "shares", "avg_cost", "total_cost"])

    positions: dict[str, dict] = {}
    for _, row in trades.iterrows():
        ticker = row["ticker"]
        qty = float(row["quantity"])
        price = float(row["price"])

        if ticker not in positions:
            positions[ticker] = {"shares": 0.0, "total_cost": 0.0}

        if row["action"] == "BUY":
            positions[ticker]["shares"] += qty
            positions[ticker]["total_cost"] += qty * price
        elif row["action"] == "SELL":
            held = positions[ticker]["shares"]
            if held > 0:
                sold = min(qty, held)
                avg = positions[ticker]["total_cost"] / held
                positions[ticker]["shares"] -= sold
                positions[ticker]["total_cost"] -= sold * avg
                if positions[ticker]["shares"] < 1e-6:
                    positions[ticker] = {"shares": 0.0, "total_cost": 0.0}

    rows = []
    for ticker, pos in positions.items():
        if pos["shares"] > 1e-6:
            rows.append(
                {
                    "ticker": ticker,
                    "shares": pos["shares"],
                    "total_cost": pos["total_cost"],
                    "avg_cost": pos["total_cost"] / pos["shares"],
                }
            )

    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["ticker", "shares", "avg_cost", "total_cost"]
    )


def enrich_holdings(holdings: pd.DataFrame, prices: dict) -> pd.DataFrame:
    """Add live-price columns to holdings DataFrame."""
    if holdings.empty:
        return holdings
    df = holdings.copy()
    df["current_price"] = df["ticker"].map(prices).astype(float)
    df["current_value"] = df["shares"] * df["current_price"]
    df["unrealized_pnl"] = df["current_value"] - df["total_cost"]
    df["unrealized_pnl_pct"] = np.where(
        df["total_cost"] > 0,
        (df["unrealized_pnl"] / df["total_cost"]) * 100,
        0.0,
    )
    total_val = df["current_value"].sum()
    df["weight_pct"] = np.where(
        total_val > 0, (df["current_value"] / total_val) * 100, 0.0
    )
    return df


def calculate_portfolio_summary(account_id: int) -> dict:
    """
    Full portfolio calculation.
    Returns a summary dict plus an enriched holdings DataFrame.
    """
    holdings = calculate_holdings(account_id)
    total_deposited = get_total_deposited(account_id)

    if holdings.empty:
        return {
            "holdings": pd.DataFrame(),
            "total_deposited": total_deposited,
            "total_cost": 0.0,
            "market_value": 0.0,
            "portfolio_value": total_deposited,
            "unrealized_pnl": 0.0,
            "unrealized_pnl_pct": 0.0,
            "cash_remaining": total_deposited,
            "total_return": 0.0,
            "total_return_pct": 0.0,
        }

    tickers = tuple(holdings["ticker"].tolist())
    prices = fetch_current_prices(tickers)
    holdings = enrich_holdings(holdings, prices)

    total_cost = holdings["total_cost"].sum()
    market_value = holdings["current_value"].sum()
    cash_remaining = max(0.0, total_deposited - total_cost)
    portfolio_value = market_value + cash_remaining
    unrealized_pnl = holdings["unrealized_pnl"].sum()
    unrealized_pnl_pct = (unrealized_pnl / total_cost * 100) if total_cost > 0 else 0.0
    total_return_pct = (
        ((portfolio_value - total_deposited) / total_deposited) * 100
        if total_deposited > 0
        else 0.0
    )

    return {
        "holdings": holdings,
        "total_deposited": total_deposited,
        "total_cost": total_cost,
        "market_value": market_value,
        "portfolio_value": portfolio_value,
        "unrealized_pnl": unrealized_pnl,
        "unrealized_pnl_pct": unrealized_pnl_pct,
        "cash_remaining": cash_remaining,
        "total_return": portfolio_value - total_deposited,
        "total_return_pct": total_return_pct,
    }


def build_portfolio_history(account_id: int) -> tuple[pd.Series, bool]:
    """
    Reconstruct daily portfolio value.

    Two modes:
    - Real trade history (trades span multiple dates): replay trades day-by-day.
    - Imported / single-date portfolio: use current holdings × historical prices
      to produce a meaningful "what-if" curve (returns estimated=True).

    Returns (series_indexed_by_date, is_estimated).
    """
    trades = get_trades(account_id)
    starting_capital = get_total_deposited(account_id)

    if trades.empty:
        return pd.Series(dtype=float), False

    trades["trade_date"] = pd.to_datetime(trades["trade_date"])
    tickers = tuple(trades["ticker"].unique().tolist())

    # Detect imported portfolio: all trades on the same calendar day
    unique_trade_dates = trades["trade_date"].dt.date.nunique()
    is_imported = unique_trade_dates == 1

    hist = fetch_historical_data(tickers, period="1y")
    if hist.empty:
        return pd.Series(dtype=float), False

    if isinstance(hist, pd.Series):
        hist = hist.to_frame(name=tickers[0])

    holdings = calculate_holdings(account_id)
    total_cost = holdings["total_cost"].sum() if not holdings.empty else 0.0
    cash_balance = max(0.0, starting_capital - total_cost)

    daily_values: dict = {}

    if is_imported:
        # ── Hypothetical reconstruction using current position sizes ─────────
        # For each historical date, apply current share counts × that day's price.
        # Cash is treated as constant. This shows how the portfolio WOULD have
        # performed if held since the start of the period.
        for dt in hist.index:
            stock_val = 0.0
            for _, row in holdings.iterrows():
                ticker = row["ticker"]
                shares = float(row["shares"])
                if ticker in hist.columns:
                    p = hist.loc[dt, ticker]
                    if pd.notna(p):
                        stock_val += shares * p
            daily_values[dt] = stock_val + cash_balance

    else:
        # ── Actual trade-date reconstruction ─────────────────────────────────
        for dt in hist.index:
            past = trades[trades["trade_date"] <= dt]
            if past.empty:
                daily_values[dt] = cash_balance
                continue

            positions: dict[str, float] = {}
            cost_used = 0.0
            for _, row in past.iterrows():
                t = row["ticker"]
                qty = float(row["quantity"])
                pr = float(row["price"])
                positions.setdefault(t, 0.0)
                if row["action"] == "BUY":
                    positions[t] += qty
                    cost_used += qty * pr
                elif row["action"] == "SELL":
                    positions[t] -= qty
                    cost_used -= qty * pr

            stock_val = sum(
                shares * hist.loc[dt, ticker]
                for ticker, shares in positions.items()
                if shares > 0
                and ticker in hist.columns
                and pd.notna(hist.loc[dt, ticker])
            )
            cash = max(0.0, starting_capital - cost_used)
            daily_values[dt] = stock_val + cash

    series = pd.Series(daily_values)
    series.index = pd.to_datetime(series.index)
    return series.sort_index(), is_imported
