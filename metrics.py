import pandas as pd
import numpy as np
from database import get_trades
from market_data import fetch_historical_data
from portfolio import build_portfolio_history, calculate_holdings


RISK_FREE_CAD = 0.045
RISK_FREE_USD = 0.050
BENCHMARK_CAD = "XIU.TO"
BENCHMARK_USD = "SPY"
TRADING_DAYS = 252


def _daily_returns(series: pd.Series) -> pd.Series:
    return series.pct_change().dropna()


def calculate_sharpe(returns: pd.Series, risk_free_rate: float = RISK_FREE_CAD) -> float:
    if returns.empty or returns.std() == 0:
        return float("nan")
    excess = returns.mean() - risk_free_rate / TRADING_DAYS
    return float((excess / returns.std()) * np.sqrt(TRADING_DAYS))


def calculate_sortino(returns: pd.Series, risk_free_rate: float = RISK_FREE_CAD) -> float:
    if returns.empty:
        return float("nan")
    target = risk_free_rate / TRADING_DAYS
    downside = returns[returns < target]
    if downside.empty or downside.std() == 0:
        return float("nan")
    downside_std = np.sqrt((downside ** 2).mean())
    excess = returns.mean() - target
    return float((excess / downside_std) * np.sqrt(TRADING_DAYS))


def calculate_max_drawdown(values: pd.Series) -> float:
    """Return max drawdown as a negative percentage (e.g. -15.3)."""
    if values.empty:
        return float("nan")
    roll_max = values.cummax()
    drawdown = (values - roll_max) / roll_max.replace(0, float("nan"))
    return float(drawdown.min() * 100)


def calculate_drawdown_series(values: pd.Series) -> pd.Series:
    if values.empty:
        return pd.Series(dtype=float)
    roll_max = values.cummax()
    return ((values - roll_max) / roll_max.replace(0, float("nan"))) * 100


def calculate_beta(portfolio_returns: pd.Series, currency: str = "CAD") -> float:
    benchmark = BENCHMARK_CAD if currency == "CAD" else BENCHMARK_USD
    hist = fetch_historical_data((benchmark,), period="1y")
    if hist.empty or benchmark not in hist.columns:
        return float("nan")
    bench_returns = hist[benchmark].pct_change().dropna()
    # Align
    aligned = pd.concat([portfolio_returns, bench_returns], axis=1).dropna()
    aligned.columns = ["port", "bench"]
    if len(aligned) < 10:
        return float("nan")
    cov = aligned.cov()
    return float(cov.loc["port", "bench"] / cov.loc["bench", "bench"])


def calculate_annualized_return(values: pd.Series) -> float:
    if len(values) < 2:
        return float("nan")
    total_days = (values.index[-1] - values.index[0]).days
    if total_days <= 0:
        return float("nan")
    total_return = values.iloc[-1] / values.iloc[0] - 1
    return float(((1 + total_return) ** (365.0 / total_days) - 1) * 100)


def calculate_win_rate(account_id: int) -> float:
    """% of closed positions that were profitable."""
    trades = get_trades(account_id)
    if trades.empty:
        return float("nan")
    sells = trades[trades["action"] == "SELL"]
    if sells.empty:
        return float("nan")
    holdings = calculate_holdings(account_id)
    avg_costs = (
        dict(zip(holdings["ticker"], holdings["avg_cost"])) if not holdings.empty else {}
    )
    profitable = 0
    total = 0
    for _, sell in sells.iterrows():
        ticker = sell["ticker"]
        sell_price = float(sell["price"])
        buys = trades[(trades["ticker"] == ticker) & (trades["action"] == "BUY")]
        if buys.empty:
            continue
        avg_buy = (buys["quantity"] * buys["price"]).sum() / buys["quantity"].sum()
        if sell_price > avg_buy:
            profitable += 1
        total += 1
    return (profitable / total * 100) if total > 0 else float("nan")


def calculate_rolling_sharpe(returns: pd.Series, window: int = 30) -> pd.Series:
    if returns.empty:
        return pd.Series(dtype=float)
    rf_daily = RISK_FREE_CAD / TRADING_DAYS
    excess = returns - rf_daily
    rolling_mean = excess.rolling(window).mean()
    rolling_std = returns.rolling(window).std()
    return (rolling_mean / rolling_std.replace(0, float("nan"))) * np.sqrt(TRADING_DAYS)


def get_all_metrics(account_id: int, currency: str = "CAD") -> dict:
    """Compute and return all key metrics for the analytics page."""
    hist_values, _ = build_portfolio_history(account_id)

    if hist_values.empty or len(hist_values) < 5:
        return {k: float("nan") for k in [
            "total_return_pct", "annualized_return", "volatility",
            "sharpe", "sortino", "max_drawdown", "beta", "win_rate",
            "best_day", "worst_day",
        ]}

    returns = _daily_returns(hist_values)
    rf = RISK_FREE_CAD if currency == "CAD" else RISK_FREE_USD

    total_return_pct = (hist_values.iloc[-1] / hist_values.iloc[0] - 1) * 100
    annualized_vol = float(returns.std() * np.sqrt(TRADING_DAYS) * 100)

    best_day = float(returns.max() * 100)
    worst_day = float(returns.min() * 100)

    return {
        "total_return_pct": float(total_return_pct),
        "annualized_return": calculate_annualized_return(hist_values),
        "volatility": annualized_vol,
        "sharpe": calculate_sharpe(returns, rf),
        "sortino": calculate_sortino(returns, rf),
        "max_drawdown": calculate_max_drawdown(hist_values),
        "beta": calculate_beta(returns, currency),
        "win_rate": calculate_win_rate(account_id),
        "best_day": best_day,
        "worst_day": worst_day,
    }
