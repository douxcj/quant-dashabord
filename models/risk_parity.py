"""
Model 3: Risk Parity
Allocate capital inversely proportional to each asset's 30-day volatility.
Lower-volatility assets receive higher weight.
"""
import pandas as pd
import numpy as np
from market_data import fetch_historical_data


NAME = "Risk Parity"
DESCRIPTION = (
    "Allocates capital inversely proportional to each asset's 30-day realised volatility. "
    "Lower-volatility assets receive a higher weight, reducing concentration risk. "
    "Best for risk-conscious investors."
)


def run(tickers: list[str], portfolio_value: float, current_weights: dict) -> pd.DataFrame:
    if not tickers:
        return pd.DataFrame()

    hist = fetch_historical_data(tuple(tickers), period="3mo")
    if hist.empty:
        return _empty_result(tickers, current_weights)

    vols = {}
    for ticker in tickers:
        if ticker not in hist.columns:
            vols[ticker] = float("nan")
            continue
        prices = hist[ticker].dropna()
        if len(prices) < 5:
            vols[ticker] = float("nan")
            continue
        ret = prices.pct_change().dropna()
        vols[ticker] = float(ret.tail(30).std() * np.sqrt(252) * 100)

    valid = {t: v for t, v in vols.items() if not pd.isna(v) and v > 0}
    if not valid:
        return _empty_result(tickers, current_weights)

    inv_vol = {t: 1.0 / v for t, v in valid.items()}
    total_inv_vol = sum(inv_vol.values())
    target_weights = {t: (iv / total_inv_vol) * 100 for t, iv in inv_vol.items()}

    rows = []
    for ticker in tickers:
        cur_w = current_weights.get(ticker, 0.0)
        vol = vols.get(ticker, float("nan"))
        target_w = target_weights.get(ticker, 0.0)
        drift = cur_w - target_w

        if abs(drift) > 3.0:
            action = "BUY" if drift < 0 else "SELL"
            signal = ("Strong Buy" if drift < -8 else "Buy") if drift < 0 else (
                "Strong Sell" if drift > 8 else "Sell"
            )
        else:
            action = "HOLD"
            signal = "Hold"

        vol_str = f"{vol:.1f}%" if not pd.isna(vol) else "N/A"
        explanation = (
            f"30-day annualised volatility: {vol_str}. "
            f"Risk-parity target: {target_w:.1f}% (current: {cur_w:.1f}%)."
        )

        rows.append(
            {
                "ticker": ticker,
                "volatility_30d": round(vol, 2) if not pd.isna(vol) else None,
                "current_weight": round(cur_w, 2),
                "target_weight": round(target_w, 2),
                "action": action,
                "signal_strength": signal,
                "explanation": explanation,
            }
        )

    return pd.DataFrame(rows)


def _empty_result(tickers, current_weights):
    return pd.DataFrame(
        [{"ticker": t, "current_weight": current_weights.get(t, 0),
          "target_weight": 0, "action": "HOLD",
          "signal_strength": "No Data", "explanation": "Insufficient price history"}
         for t in tickers]
    )
