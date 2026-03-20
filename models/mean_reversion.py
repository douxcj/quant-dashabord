"""
Model 4: Mean Reversion (RSI-based)
Buy oversold assets (RSI < 35), sell overbought assets (RSI > 70).
"""
import pandas as pd
from market_data import fetch_historical_data, calculate_rsi


NAME = "Mean Reversion (RSI)"
DESCRIPTION = (
    "Contrarian model: buys assets that are statistically oversold (RSI < 35) "
    "and sells assets that have rallied strongly (RSI > 70). "
    "Best for sideways or range-bound markets."
)


def run(tickers: list[str], portfolio_value: float, current_weights: dict) -> pd.DataFrame:
    if not tickers:
        return pd.DataFrame()

    hist = fetch_historical_data(tuple(tickers), period="3mo")
    if hist.empty:
        return _empty_result(tickers, current_weights)

    rows = []
    for ticker in tickers:
        cur_w = current_weights.get(ticker, 0.0)

        if ticker not in hist.columns:
            rows.append(_no_data_row(ticker, cur_w))
            continue

        prices = hist[ticker].dropna()
        if len(prices) < 15:
            rows.append(_no_data_row(ticker, cur_w))
            continue

        rsi_series = calculate_rsi(prices, 14)
        rsi = float(rsi_series.iloc[-1]) if not rsi_series.dropna().empty else float("nan")

        if pd.isna(rsi):
            rows.append(_no_data_row(ticker, cur_w))
            continue

        if rsi < 35:
            action = "BUY"
            signal = "Strong Buy" if rsi < 25 else "Buy"
            target_w = min(cur_w * 1.5, 30.0)
            explanation = (
                f"RSI={rsi:.1f} — deeply oversold. "
                "Mean-reversion entry opportunity; increasing allocation."
            )
        elif rsi > 70:
            action = "SELL"
            signal = "Strong Sell" if rsi > 80 else "Sell"
            target_w = max(cur_w * 0.5, 0.0)
            explanation = (
                f"RSI={rsi:.1f} — overbought. "
                "Expect mean reversion downward; reducing position."
            )
        elif 35 <= rsi <= 45:
            action = "BUY"
            signal = "Weak Buy"
            target_w = cur_w * 1.1
            explanation = f"RSI={rsi:.1f} — approaching oversold zone. Modest accumulation."
        elif 60 <= rsi <= 70:
            action = "HOLD"
            signal = "Hold"
            target_w = cur_w
            explanation = f"RSI={rsi:.1f} — neutral to slightly elevated. Monitoring."
        else:
            action = "HOLD"
            signal = "Hold"
            target_w = cur_w
            explanation = f"RSI={rsi:.1f} — neutral range (35–60). No action required."

        rows.append(
            {
                "ticker": ticker,
                "rsi": round(rsi, 1),
                "current_weight": round(cur_w, 2),
                "target_weight": round(target_w, 2),
                "action": action,
                "signal_strength": signal,
                "explanation": explanation,
            }
        )

    return pd.DataFrame(rows)


def _no_data_row(ticker, cur_w):
    return {
        "ticker": ticker,
        "rsi": None,
        "current_weight": round(cur_w, 2),
        "target_weight": round(cur_w, 2),
        "action": "HOLD",
        "signal_strength": "No Data",
        "explanation": "Insufficient price history to calculate RSI.",
    }


def _empty_result(tickers, current_weights):
    return pd.DataFrame([_no_data_row(t, current_weights.get(t, 0)) for t in tickers])
