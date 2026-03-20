"""
Model 1: Momentum + RSI Hybrid
Score assets by 20-day momentum; buy top performers where RSI < 65,
reduce where RSI > 75.
"""
import pandas as pd
import numpy as np
from market_data import fetch_historical_data, calculate_rsi, calculate_momentum


NAME = "Momentum + RSI Hybrid"
DESCRIPTION = (
    "Scores each asset by 20-day price momentum. "
    "Signals BUY for top performers where RSI < 65 (not overbought), "
    "and SELL/REDUCE where RSI > 75 (overbought). "
    "Best for growth-oriented portfolios with 3–7 day rebalancing."
)


def run(tickers: list[str], portfolio_value: float, current_weights: dict) -> pd.DataFrame:
    """
    Returns a DataFrame with rebalancing recommendations.
    Columns: ticker | momentum | rsi | action | signal_strength | target_weight | explanation
    """
    if not tickers:
        return pd.DataFrame()

    hist = fetch_historical_data(tuple(tickers), period="3mo")
    if hist.empty:
        return _empty_result(tickers)

    scores = []
    for ticker in tickers:
        if ticker not in hist.columns:
            continue
        prices = hist[ticker].dropna()
        if len(prices) < 22:
            continue
        mom = calculate_momentum(prices, 20)
        rsi = calculate_rsi(prices, 14).iloc[-1] if len(prices) >= 14 else float("nan")
        scores.append({"ticker": ticker, "momentum": mom, "rsi": rsi})

    if not scores:
        return _empty_result(tickers)

    df = pd.DataFrame(scores).dropna(subset=["momentum"])
    df = df.sort_values("momentum", ascending=False).reset_index(drop=True)

    n = len(df)
    top_third = max(1, n // 3)

    rows = []
    for i, row in df.iterrows():
        ticker = row["ticker"]
        mom = row["momentum"]
        rsi = row["rsi"]
        cur_w = current_weights.get(ticker, 0.0)

        if i < top_third and (pd.isna(rsi) or rsi < 65):
            action = "BUY"
            signal = "Strong Buy" if mom > 5 and (pd.isna(rsi) or rsi < 55) else "Buy"
            target_w = (1.0 / top_third) * 100
            explanation = (
                f"Top momentum ({mom:.1f}%) with RSI={rsi:.0f} (not overbought). "
                "Increasing allocation."
            )
        elif not pd.isna(rsi) and rsi > 75:
            action = "SELL"
            signal = "Strong Sell" if rsi > 80 else "Sell"
            target_w = max(0.0, cur_w * 0.5)
            explanation = (
                f"RSI={rsi:.0f} signals overbought conditions. "
                "Reducing position to manage risk."
            )
        elif not pd.isna(rsi) and rsi > 65:
            action = "HOLD"
            signal = "Hold"
            target_w = cur_w
            explanation = f"Momentum {mom:.1f}%, RSI={rsi:.0f}. Watching for confirmation."
        else:
            action = "HOLD"
            signal = "Weak Hold"
            target_w = cur_w
            explanation = f"Momentum {mom:.1f}% — below top tier. Holding current weight."

        rows.append(
            {
                "ticker": ticker,
                "momentum_20d": round(mom, 2),
                "rsi": round(rsi, 1) if not pd.isna(rsi) else None,
                "current_weight": round(cur_w, 2),
                "target_weight": round(target_w, 2),
                "action": action,
                "signal_strength": signal,
                "explanation": explanation,
            }
        )

    return pd.DataFrame(rows)


def _empty_result(tickers):
    return pd.DataFrame(
        [{"ticker": t, "action": "HOLD", "signal_strength": "No Data",
          "current_weight": 0, "target_weight": 0, "explanation": "Insufficient data"}
         for t in tickers]
    )
