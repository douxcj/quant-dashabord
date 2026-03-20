"""
Model 5: Trend Following (Moving Average Crossover)
Buy when 10-day MA crosses above 30-day MA.
Sell when 10-day MA crosses below 30-day MA.
"""
import pandas as pd
from market_data import fetch_historical_data


NAME = "Trend Following (MA Crossover)"
DESCRIPTION = (
    "Trend-following model based on moving average crossovers. "
    "BUY signal when the 10-day MA crosses above the 30-day MA (golden cross). "
    "SELL signal when the 10-day MA crosses below the 30-day MA (death cross). "
    "Best suited to trending markets."
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
        if len(prices) < 32:
            rows.append(_no_data_row(ticker, cur_w))
            continue

        ma10 = prices.rolling(10).mean()
        ma30 = prices.rolling(30).mean()

        # Last two valid values to detect crossover
        valid_idx = ma30.dropna().index
        if len(valid_idx) < 2:
            rows.append(_no_data_row(ticker, cur_w))
            continue

        curr_ma10 = float(ma10.loc[valid_idx[-1]])
        curr_ma30 = float(ma30.loc[valid_idx[-1]])
        prev_ma10 = float(ma10.loc[valid_idx[-2]])
        prev_ma30 = float(ma30.loc[valid_idx[-2]])

        golden_cross = prev_ma10 <= prev_ma30 and curr_ma10 > curr_ma30
        death_cross = prev_ma10 >= prev_ma30 and curr_ma10 < curr_ma30
        above = curr_ma10 > curr_ma30
        gap_pct = abs(curr_ma10 - curr_ma30) / curr_ma30 * 100

        if golden_cross:
            action = "BUY"
            signal = "Strong Buy"
            target_w = min(cur_w * 1.5, 35.0)
            explanation = (
                f"Golden cross: 10-MA ({curr_ma10:.2f}) just crossed above 30-MA ({curr_ma30:.2f}). "
                "Trend reversal to upside confirmed."
            )
        elif death_cross:
            action = "SELL"
            signal = "Strong Sell"
            target_w = max(cur_w * 0.3, 0.0)
            explanation = (
                f"Death cross: 10-MA ({curr_ma10:.2f}) just crossed below 30-MA ({curr_ma30:.2f}). "
                "Downtrend confirmed — reducing exposure."
            )
        elif above:
            action = "BUY"
            signal = "Buy" if gap_pct > 2 else "Weak Buy"
            target_w = cur_w * 1.1
            explanation = (
                f"10-MA ({curr_ma10:.2f}) above 30-MA ({curr_ma30:.2f}) by {gap_pct:.1f}%. "
                "Uptrend intact — holding / modest accumulation."
            )
        else:
            action = "SELL"
            signal = "Sell" if gap_pct > 2 else "Weak Sell"
            target_w = max(cur_w * 0.7, 0.0)
            explanation = (
                f"10-MA ({curr_ma10:.2f}) below 30-MA ({curr_ma30:.2f}) by {gap_pct:.1f}%. "
                "Downtrend active — reducing position."
            )

        rows.append(
            {
                "ticker": ticker,
                "ma_10": round(curr_ma10, 2),
                "ma_30": round(curr_ma30, 2),
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
        "ma_10": None,
        "ma_30": None,
        "current_weight": round(cur_w, 2),
        "target_weight": round(cur_w, 2),
        "action": "HOLD",
        "signal_strength": "No Data",
        "explanation": "Insufficient price history (need ≥ 32 days).",
    }


def _empty_result(tickers, current_weights):
    return pd.DataFrame([_no_data_row(t, current_weights.get(t, 0)) for t in tickers])
