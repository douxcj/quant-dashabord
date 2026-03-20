"""
Model 2: Equal Weight Rebalance
Maintain equal weight across all holdings.
Rebalance when any position drifts > 5% from target weight.
"""
import pandas as pd
import numpy as np


NAME = "Equal Weight Rebalance"
DESCRIPTION = (
    "Maintains equal weight across all holdings. "
    "Flags any position that has drifted more than 5% from its target allocation "
    "as a rebalancing candidate. Ideal for passive, ETF-heavy portfolios."
)


def run(tickers: list[str], portfolio_value: float, current_weights: dict) -> pd.DataFrame:
    if not tickers:
        return pd.DataFrame()

    n = len(tickers)
    target_w = 100.0 / n
    drift_threshold = 5.0  # percent

    rows = []
    for ticker in tickers:
        cur_w = current_weights.get(ticker, 0.0)
        drift = cur_w - target_w

        if abs(drift) > drift_threshold:
            if drift > 0:
                action = "SELL"
                signal = "Strong Sell" if abs(drift) > 10 else "Sell"
                explanation = (
                    f"Overweight by {drift:.1f}%. "
                    f"Trimming from {cur_w:.1f}% to target {target_w:.1f}%."
                )
            else:
                action = "BUY"
                signal = "Strong Buy" if abs(drift) > 10 else "Buy"
                explanation = (
                    f"Underweight by {abs(drift):.1f}%. "
                    f"Adding from {cur_w:.1f}% to target {target_w:.1f}%."
                )
        else:
            action = "HOLD"
            signal = "Hold"
            explanation = (
                f"Within ±5% of target {target_w:.1f}%. No rebalancing needed."
            )

        rows.append(
            {
                "ticker": ticker,
                "current_weight": round(cur_w, 2),
                "target_weight": round(target_w, 2),
                "drift": round(drift, 2),
                "action": action,
                "signal_strength": signal,
                "explanation": explanation,
            }
        )

    return pd.DataFrame(rows)
