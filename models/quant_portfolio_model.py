"""
Quant Portfolio Manager — 4-Layer Model
Layer 1: Regime Detection
Layer 2: Momentum Scoring
Layer 3: Mean Reversion Overlay
Layer 4: Portfolio Construction
"""
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime

# ── Universe Definitions ───────────────────────────────────────────────────────

USD_UNIVERSE_FULL = [
    "XLE", "XLK", "XLF", "XLV", "XLI", "XLU", "XLP", "XLY", "XLB", "XLC",
    "XLRE", "GLD", "SLV", "TLT", "HYG", "LQD", "EFA", "EEM", "EWJ", "FXI",
    "IWM", "QQQ", "DIA", "VNQ", "XME",
]
USD_UNIVERSE_AGGRESSIVE = [
    "XLE", "XLK", "XLF", "XLV", "XLI", "XLU", "XLP", "XLY", "XLB", "XLC",
    "XLRE", "IWM", "QQQ", "EFA", "EEM",
]
USD_RISK_OFF_CONSERVATIVE = ["TLT", "GLD", "SLV", "XLU", "XLP", "LQD", "HYG"]
USD_RISK_OFF_AGGRESSIVE = ["TLT", "GLD", "SLV", "XLU", "XLP"]
USD_REGIME_BENCHMARK = "SPY"

CAD_UNIVERSE_FULL = [
    "QQC.TO", "VFV.TO", "ZUB.TO", "ZUH.TO", "XEF.TO", "XEC.TO", "XEG.TO",
    "XFN.TO", "XIT.TO", "XMA.TO", "XUT.TO", "XRE.TO", "CGL.TO", "XBB.TO",
    "XGOV.TO",
]
CAD_UNIVERSE_AGGRESSIVE = [
    "QQC.TO", "VFV.TO", "ZUB.TO", "ZUH.TO", "XEG.TO", "XFN.TO", "XIT.TO",
    "XMA.TO", "XUT.TO", "XRE.TO", "XEF.TO", "XEC.TO",
]
CAD_RISK_OFF_CONSERVATIVE = ["CGL.TO", "XBB.TO", "XGOV.TO", "XUT.TO", "XRE.TO"]
CAD_RISK_OFF_AGGRESSIVE = ["CGL.TO", "XBB.TO", "XUT.TO", "XRE.TO"]
CAD_REGIME_BENCHMARK = "XSP.TO"

# ── Parameter Sets ─────────────────────────────────────────────────────────────

PARAMS = {
    "Conservative": {
        "max_positions": {"RISK_ON": 4, "CAUTION": 3, "RISK_OFF": 3},
        "max_weight": 0.35,
        "min_weight": 0.10,
        "cash_buffer": 0.05,
        "sizing": "inverse_vol",
        "mom_weights": {
            "risk_adj": 0.60,
            "raw_40d": 0.25,
            "raw_20d": 0.15,
            "trend": 0.0,
        },
        "mr_overlay": 0.3,
        "stop_loss": 0.05,
    },
    "Aggressive": {
        "max_positions": {"RISK_ON": 3, "CAUTION": 2, "RISK_OFF": 2},
        "max_weight": 0.55,
        "min_weight": 0.15,
        "cash_buffer": 0.03,
        "sizing": "momentum_weighted",
        "mom_weights": {
            "risk_adj": 0.40,
            "raw_40d": 0.30,
            "raw_20d": 0.20,
            "trend": 0.10,
        },
        "mr_overlay": 0.15,
        "stop_loss": 0.08,
    },
}

# ── CAD Ticker Metadata ────────────────────────────────────────────────────────

CAD_TICKER_META = {
    "QQC.TO": {
        "name": "Invesco NASDAQ 100 Index ETF",
        "hedged": True,
        "usd_equiv": "QQQ",
        "mapping": "Exact",
        "warning": False,
    },
    "VFV.TO": {
        "name": "Vanguard S&P 500 Index ETF",
        "hedged": False,
        "usd_equiv": "VOO",
        "mapping": "Exact",
        "warning": False,
    },
    "ZUB.TO": {
        "name": "BMO Equal Weight US Banks Hedged ETF",
        "hedged": True,
        "usd_equiv": "XLF",
        "mapping": "Partial",
        "warning": False,
    },
    "ZUH.TO": {
        "name": "BMO Equal Weight US Health Care Hedged ETF",
        "hedged": True,
        "usd_equiv": "XLV",
        "mapping": "Exact",
        "warning": False,
    },
    "XEF.TO": {
        "name": "iShares Core MSCI EAFE IMI Index ETF",
        "hedged": False,
        "usd_equiv": "EFA",
        "mapping": "Similar",
        "warning": False,
    },
    "XEC.TO": {
        "name": "iShares Core MSCI Emerging Markets IMI ETF",
        "hedged": False,
        "usd_equiv": "EEM",
        "mapping": "Similar",
        "warning": False,
    },
    "XEG.TO": {
        "name": "iShares S&P/TSX Capped Energy Index ETF",
        "hedged": False,
        "usd_equiv": "XLE",
        "mapping": "Similar",
        "warning": False,
    },
    "XFN.TO": {
        "name": "iShares S&P/TSX Capped Financials Index ETF",
        "hedged": False,
        "usd_equiv": "XLF",
        "mapping": "Similar",
        "warning": False,
    },
    "XIT.TO": {
        "name": "iShares S&P/TSX Capped Info Tech Index ETF",
        "hedged": False,
        "usd_equiv": "XLK",
        "mapping": "Different",
        "warning": True,
    },
    "XMA.TO": {
        "name": "iShares S&P/TSX Capped Materials Index ETF",
        "hedged": False,
        "usd_equiv": "XLB",
        "mapping": "Similar",
        "warning": False,
    },
    "XUT.TO": {
        "name": "iShares S&P/TSX Capped Utilities Index ETF",
        "hedged": False,
        "usd_equiv": "XLU",
        "mapping": "Exact",
        "warning": False,
    },
    "XRE.TO": {
        "name": "iShares S&P/TSX Capped REIT Index ETF",
        "hedged": False,
        "usd_equiv": "VNQ",
        "mapping": "Similar",
        "warning": False,
    },
    "CGL.TO": {
        "name": "iShares Gold Bullion ETF (CAD-Hedged)",
        "hedged": True,
        "usd_equiv": "GLD",
        "mapping": "Exact",
        "warning": False,
    },
    "XBB.TO": {
        "name": "iShares Core Canadian Universe Bond Index ETF",
        "hedged": False,
        "usd_equiv": "AGG",
        "mapping": "Similar",
        "warning": False,
    },
    "XGOV.TO": {
        "name": "iShares Core Canadian Government Bond Index ETF",
        "hedged": False,
        "usd_equiv": "TLT",
        "mapping": "Partial",
        "warning": False,
    },
}

USD_TICKER_META = {
    "XLE":  "Energy Select Sector SPDR — US oil, gas & energy companies",
    "XLK":  "Technology Select Sector SPDR — US tech (Apple, NVIDIA, Microsoft)",
    "XLF":  "Financial Select Sector SPDR — US banks, insurers, asset managers",
    "XLV":  "Health Care Select Sector SPDR — US pharma, biotech, hospitals",
    "XLI":  "Industrial Select Sector SPDR — US aerospace, defence, machinery",
    "XLU":  "Utilities Select Sector SPDR — US electric, gas & water utilities",
    "XLP":  "Consumer Staples Select Sector SPDR — food, beverages, household goods",
    "XLY":  "Consumer Discretionary Select Sector SPDR — retail, autos, leisure",
    "XLB":  "Materials Select Sector SPDR — chemicals, metals, packaging",
    "XLC":  "Communication Services Select Sector SPDR — Alphabet, Meta, telecoms",
    "XLRE": "Real Estate Select Sector SPDR — US REITs and real estate companies",
    "GLD":  "SPDR Gold Shares — physical gold bullion",
    "SLV":  "iShares Silver Trust — physical silver bullion",
    "TLT":  "iShares 20+ Year Treasury Bond ETF — long-duration US government bonds",
    "HYG":  "iShares High Yield Corporate Bond ETF — junk-rated US corporate debt",
    "LQD":  "iShares Investment Grade Corporate Bond ETF — investment-grade US debt",
    "EFA":  "iShares MSCI EAFE ETF — developed markets ex-US (Europe, Aus, Japan)",
    "EEM":  "iShares MSCI Emerging Markets ETF — China, India, Brazil, etc.",
    "EWJ":  "iShares MSCI Japan ETF — large & mid-cap Japanese equities",
    "FXI":  "iShares China Large-Cap ETF — top 50 Chinese companies (H-shares)",
    "IWM":  "iShares Russell 2000 ETF — US small-cap equities",
    "QQQ":  "Invesco Nasdaq-100 ETF — top 100 non-financial Nasdaq companies",
    "DIA":  "SPDR Dow Jones Industrial Average ETF — 30 blue-chip US stocks",
    "VNQ":  "Vanguard Real Estate ETF — US REITs basket",
    "XME":  "SPDR S&P Metals & Mining ETF — steel, aluminium, gold miners",
    "SPY":  "SPDR S&P 500 ETF Trust — 500 largest US companies (regime benchmark)",
}


def get_ticker_description(ticker: str, currency: str) -> str:
    """Return a short description for a ticker based on currency context."""
    if currency == "CAD":
        meta = CAD_TICKER_META.get(ticker, {})
        return meta.get("name", ticker)
    return USD_TICKER_META.get(ticker, ticker)


def get_market_hours(ticker: str) -> str:
    """Return trading hours in Eastern Time for a ticker.

    TSX (.TO) ETFs trade regular hours only.
    US-listed ETFs support pre-market and after-hours on most platforms.
    """
    if ticker.endswith(".TO"):
        return "9:30 AM – 4:00 PM ET (TSX)"
    return "9:30 AM – 4:00 PM ET (+ pre/after)"


# ── Layer 1: Universe Selection ────────────────────────────────────────────────

def get_universe(currency: str, risk_mode: str, regime: str) -> list:
    """Return the correct ETF universe based on currency, risk_mode, and regime."""
    if currency == "USD":
        if regime == "RISK_OFF":
            if risk_mode == "Conservative":
                return USD_RISK_OFF_CONSERVATIVE
            else:
                return USD_RISK_OFF_AGGRESSIVE
        else:
            if risk_mode == "Conservative":
                return USD_UNIVERSE_FULL
            else:
                return USD_UNIVERSE_AGGRESSIVE
    else:  # CAD
        if regime == "RISK_OFF":
            if risk_mode == "Conservative":
                return CAD_RISK_OFF_CONSERVATIVE
            else:
                return CAD_RISK_OFF_AGGRESSIVE
        else:
            if risk_mode == "Conservative":
                return CAD_UNIVERSE_FULL
            else:
                return CAD_UNIVERSE_AGGRESSIVE


# ── Layer 1: Regime Detection ──────────────────────────────────────────────────

def fetch_regime(currency: str) -> dict:
    """
    Download benchmark and detect market regime.
    Returns dict with regime info: RISK_ON, CAUTION, or RISK_OFF.
    """
    benchmark = USD_REGIME_BENCHMARK if currency == "USD" else CAD_REGIME_BENCHMARK
    default = {
        "benchmark": benchmark,
        "current_price": None,
        "sma_200": None,
        "sma_50": None,
        "pct_above_200": None,
        "pct_above_50": None,
        "rsi_14": None,
        "regime": "RISK_ON",
    }
    try:
        data = yf.download(benchmark, period="14mo", auto_adjust=True, progress=False)
        if data.empty or len(data) < 50:
            return default

        close = data["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.squeeze()
        close = close.dropna()

        if len(close) < 50:
            return default

        sma_200 = close.rolling(200, min_periods=50).mean().iloc[-1]
        sma_50 = close.rolling(50, min_periods=20).mean().iloc[-1]
        current_price = float(close.iloc[-1])

        # RSI using EWM method (com=13, min_periods=14)
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = gain.ewm(com=13, min_periods=14).mean()
        avg_loss = loss.ewm(com=13, min_periods=14).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        rsi_14 = float(rsi.iloc[-1]) if not rsi.empty else None

        sma_200_val = float(sma_200) if not pd.isna(sma_200) else None
        sma_50_val = float(sma_50) if not pd.isna(sma_50) else None

        pct_above_200 = None
        pct_above_50 = None
        if sma_200_val and sma_200_val != 0:
            pct_above_200 = (current_price / sma_200_val - 1) * 100
        if sma_50_val and sma_50_val != 0:
            pct_above_50 = (current_price / sma_50_val - 1) * 100

        # Determine regime
        above_200 = sma_200_val is not None and current_price > sma_200_val
        above_50 = sma_50_val is not None and current_price > sma_50_val

        if above_200 and above_50:
            regime = "RISK_ON"
        elif above_200 and not above_50:
            regime = "CAUTION"
        else:
            regime = "RISK_OFF"

        return {
            "benchmark": benchmark,
            "current_price": current_price,
            "sma_200": sma_200_val,
            "sma_50": sma_50_val,
            "pct_above_200": pct_above_200,
            "pct_above_50": pct_above_50,
            "rsi_14": rsi_14,
            "regime": regime,
        }
    except Exception:
        return default


# ── Layer 2: Momentum Scoring ──────────────────────────────────────────────────

def _z_score(series: pd.Series) -> pd.Series:
    """Standard z-score, handle std=0 case."""
    std = series.std()
    if std == 0 or pd.isna(std):
        return pd.Series(0.0, index=series.index)
    return (series - series.mean()) / std


def compute_momentum_scores(tickers: list, risk_mode: str, streaks: dict = None) -> pd.DataFrame:
    """
    Compute multi-factor momentum scores for each ticker.
    Returns DataFrame sorted by composite_score descending.
    """
    if streaks is None:
        streaks = {}

    if not tickers:
        return pd.DataFrame()

    try:
        data = yf.download(tickers, period="6mo", auto_adjust=True, progress=False)
        if data.empty:
            return pd.DataFrame()

        if isinstance(data.columns, pd.MultiIndex):
            close = data["Close"]
        else:
            close = data[["Close"]] if "Close" in data.columns else data

        if isinstance(close, pd.Series):
            close = close.to_frame(name=tickers[0])

    except Exception:
        return pd.DataFrame()

    mw = PARAMS[risk_mode]["mom_weights"]
    rows = []

    for ticker in tickers:
        if ticker not in close.columns:
            continue
        prices = close[ticker].dropna()
        if len(prices) < 42:
            continue

        ret_40d = float((prices.iloc[-1] / prices.iloc[-41] - 1) * 100) if len(prices) >= 41 else 0.0
        ret_20d = float((prices.iloc[-1] / prices.iloc[-21] - 1) * 100) if len(prices) >= 21 else 0.0

        daily_returns = prices.pct_change().dropna()
        vol_20d = daily_returns.tail(20).std()
        vol_annualized = float(vol_20d * np.sqrt(252) * 100) if not pd.isna(vol_20d) else 0.0

        risk_adj_mom = ret_40d / (vol_annualized / 100) if vol_annualized > 0 else 0.0

        streak = streaks.get(ticker, 0)
        trend_bonus = min(streak * 0.2, 1.0)

        # Check if price is above its 50-day SMA for trend signal
        sma_50 = prices.rolling(50, min_periods=20).mean().iloc[-1]
        trend_signal = 1.0 if (not pd.isna(sma_50) and prices.iloc[-1] > sma_50) else 0.0

        rows.append({
            "ticker": ticker,
            "ret_40d": ret_40d,
            "ret_20d": ret_20d,
            "vol_annualized": vol_annualized,
            "risk_adj_mom": risk_adj_mom,
            "trend_signal": trend_signal,
            "streak": streak,
            "trend_bonus": trend_bonus,
        })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    # Z-score each metric
    df["z_risk_adj"] = _z_score(df["risk_adj_mom"])
    df["z_raw_40d"] = _z_score(df["ret_40d"])
    df["z_raw_20d"] = _z_score(df["ret_20d"])
    df["z_trend"] = _z_score(df["trend_signal"])

    # Composite score = weighted sum of z-scores + streak bonus
    df["composite_score"] = (
        mw["risk_adj"] * df["z_risk_adj"]
        + mw["raw_40d"] * df["z_raw_40d"]
        + mw["raw_20d"] * df["z_raw_20d"]
        + mw["trend"] * df["z_trend"]
        + df["trend_bonus"]
    )

    df = df.sort_values("composite_score", ascending=False).reset_index(drop=True)
    return df[[
        "ticker", "ret_40d", "ret_20d", "vol_annualized", "risk_adj_mom",
        "composite_score", "streak", "trend_bonus"
    ]]


# ── Layer 3: Mean Reversion Overlay ───────────────────────────────────────────

def compute_mean_reversion(tickers: list) -> pd.DataFrame:
    """
    Compute mean reversion pullback scores for each ticker.
    Returns DataFrame with rsi_5d, bb_pos, ret_5d, pullback_score.
    """
    if not tickers:
        return pd.DataFrame()

    try:
        data = yf.download(tickers, period="1mo", auto_adjust=True, progress=False)
        if data.empty:
            return pd.DataFrame()

        if isinstance(data.columns, pd.MultiIndex):
            close = data["Close"]
        else:
            close = data[["Close"]] if "Close" in data.columns else data

        if isinstance(close, pd.Series):
            close = close.to_frame(name=tickers[0])

    except Exception:
        return pd.DataFrame()

    rows = []
    for ticker in tickers:
        if ticker not in close.columns:
            continue
        prices = close[ticker].dropna()
        if len(prices) < 7:
            continue

        # 5-day RSI using simple rolling mean method
        delta = prices.diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = gain.rolling(5, min_periods=1).mean()
        avg_loss = loss.rolling(5, min_periods=1).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi_series = 100 - (100 / (1 + rs))
        rsi_5d = float(rsi_series.iloc[-1]) if not rsi_series.empty else 50.0

        # Bollinger Band position: SMA5 ± 1.5×STD5
        sma_5 = prices.rolling(5, min_periods=3).mean()
        std_5 = prices.rolling(5, min_periods=3).std()
        upper_band = sma_5 + 1.5 * std_5
        lower_band = sma_5 - 1.5 * std_5
        last_price = float(prices.iloc[-1])
        upper_val = float(upper_band.iloc[-1]) if not pd.isna(upper_band.iloc[-1]) else last_price
        lower_val = float(lower_band.iloc[-1]) if not pd.isna(lower_band.iloc[-1]) else last_price

        band_range = upper_val - lower_val
        if band_range > 0:
            bb_pos = (last_price - lower_val) / band_range
        else:
            bb_pos = 0.5

        # 5-day return
        ret_5d = float((prices.iloc[-1] / prices.iloc[-6] - 1) * 100) if len(prices) >= 6 else 0.0

        # Pullback score: higher = better pullback entry
        bb_clamped = max(0.0, min(1.0, bb_pos))
        pullback_score = (
            0.40 * (1 - rsi_5d / 100)
            + 0.30 * (1 - bb_clamped)
            + 0.30 * max(0.0, -ret_5d / 10)
        )

        rows.append({
            "ticker": ticker,
            "rsi_5d": rsi_5d,
            "bb_pos": bb_pos,
            "ret_5d": ret_5d,
            "pullback_score": pullback_score,
        })

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows)


# ── Layer 4: Portfolio Construction ───────────────────────────────────────────

def construct_portfolio(
    momentum_df: pd.DataFrame,
    mr_df: pd.DataFrame,
    risk_mode: str,
    regime: str,
    total_value: float,
    prices: dict,
) -> pd.DataFrame:
    """
    Construct final portfolio by combining momentum and mean reversion scores,
    applying position sizing, weight constraints, and cash buffer.
    """
    if momentum_df.empty:
        return pd.DataFrame()

    params = PARAMS[risk_mode]
    mr_overlay = params["mr_overlay"]
    max_n = params["max_positions"].get(regime, params["max_positions"]["RISK_ON"])
    max_weight = params["max_weight"]
    min_weight = params["min_weight"]
    cash_buffer = params["cash_buffer"]
    sizing = params["sizing"]

    # Merge momentum with mean reversion
    if not mr_df.empty:
        merged = momentum_df.merge(mr_df[["ticker", "rsi_5d", "bb_pos", "ret_5d", "pullback_score"]],
                                   on="ticker", how="left")
    else:
        merged = momentum_df.copy()
        merged["rsi_5d"] = 50.0
        merged["bb_pos"] = 0.5
        merged["ret_5d"] = 0.0
        merged["pullback_score"] = 0.0

    merged["pullback_score"] = merged["pullback_score"].fillna(0.0)

    # Final score
    merged["final_score"] = merged["composite_score"] + merged["pullback_score"] * mr_overlay

    # Select top N
    merged = merged.sort_values("final_score", ascending=False).reset_index(drop=True)
    selected = merged.head(max_n).copy()

    # Filter to tickers that have valid prices
    selected = selected[selected["ticker"].apply(lambda t: t in prices and prices[t] > 0)]

    if selected.empty:
        return pd.DataFrame()

    # Sizing
    if sizing == "inverse_vol":
        vols = selected["vol_annualized"].replace(0, np.nan).fillna(1.0)
        inv_vol = 1.0 / vols
        raw_weights = inv_vol / inv_vol.sum()
    else:  # momentum_weighted
        scores = selected["composite_score"].clip(lower=0)
        total_score = scores.sum()
        if total_score > 0:
            raw_weights = scores / total_score
        else:
            raw_weights = pd.Series(1.0 / len(selected), index=selected.index)

    # Clamp weights
    weights = raw_weights.clip(lower=min_weight, upper=max_weight)

    # Renormalize
    weights = weights / weights.sum()

    # Apply cash buffer
    weights = weights * (1 - cash_buffer)

    selected = selected.copy()
    selected["weight"] = weights.values
    selected["weight_pct"] = selected["weight"] * 100

    # Dollar amounts and shares
    investable = total_value * (1 - cash_buffer)
    selected["dollar_amount"] = selected["weight"] * total_value
    selected["price"] = selected["ticker"].map(prices)
    selected["shares"] = (selected["dollar_amount"] / selected["price"]).apply(
        lambda x: int(np.floor(x)) if not pd.isna(x) else 0
    )
    selected["actual_cost"] = selected["shares"] * selected["price"]

    return selected[[
        "ticker", "weight_pct", "dollar_amount", "shares", "price", "actual_cost",
        "composite_score", "final_score", "ret_40d", "ret_20d", "vol_annualized",
        "rsi_5d", "pullback_score", "streak",
    ]].reset_index(drop=True)


# ── Price Fetching ─────────────────────────────────────────────────────────────

def fetch_prices(tickers: list) -> dict:
    """Download latest close prices for a list of tickers. Returns {ticker: price}."""
    if not tickers:
        return {}
    try:
        data = yf.download(tickers, period="2d", auto_adjust=True, progress=False)
        if data.empty:
            return {}

        if isinstance(data.columns, pd.MultiIndex):
            close = data["Close"]
        else:
            close = data[["Close"]] if "Close" in data.columns else data

        if isinstance(close, pd.Series):
            close = close.to_frame(name=tickers[0])

        result = {}
        for ticker in tickers:
            if ticker in close.columns:
                price_series = close[ticker].dropna()
                if not price_series.empty:
                    result[ticker] = float(price_series.iloc[-1])
        return result
    except Exception:
        return {}


# ── Main Entry Point ───────────────────────────────────────────────────────────

def run_model(
    currency: str,
    risk_mode: str,
    total_value: float,
    streaks: dict = None,
) -> dict:
    """
    Run all 4 layers of the quant portfolio model.
    Returns dict with regime_info, universe, momentum_df, mr_df, portfolio_df, prices.
    """
    if streaks is None:
        streaks = {}

    # Layer 1a: Regime detection
    regime_info = fetch_regime(currency)
    regime = regime_info["regime"]

    # Layer 1b: Universe selection
    universe = get_universe(currency, risk_mode, regime)

    # Layer 2: Momentum scoring
    momentum_df = compute_momentum_scores(universe, risk_mode, streaks)

    # Layer 3: Mean reversion overlay
    mr_df = compute_mean_reversion(universe)

    # Fetch current prices
    prices = fetch_prices(universe)

    # Layer 4: Portfolio construction
    portfolio_df = construct_portfolio(
        momentum_df=momentum_df,
        mr_df=mr_df,
        risk_mode=risk_mode,
        regime=regime,
        total_value=total_value,
        prices=prices,
    )

    return {
        "regime_info": regime_info,
        "universe": universe,
        "momentum_df": momentum_df,
        "mr_df": mr_df,
        "portfolio_df": portfolio_df,
        "prices": prices,
    }


# ── Rebalance Trade Computation ────────────────────────────────────────────────

def compute_rebalance_trades(
    current_holdings: list,
    new_portfolio_df: pd.DataFrame,
    prices: dict,
) -> list:
    """
    Compare current holdings to new optimal portfolio and generate trade list.

    current_holdings: list of dicts with keys {ticker, shares, avg_entry_price}
    new_portfolio_df: DataFrame from construct_portfolio()
    prices: dict {ticker: current_price}

    Returns list of dicts: action, ticker, current_shares, suggested_shares,
                           price, dollar_amount, reason
    """
    trades = []

    current_map = {h["ticker"]: h for h in current_holdings}
    new_map = {}
    if not new_portfolio_df.empty:
        for _, row in new_portfolio_df.iterrows():
            new_map[row["ticker"]] = row

    all_tickers = set(list(current_map.keys()) + list(new_map.keys()))

    for ticker in sorted(all_tickers):
        price = prices.get(ticker, 0.0)
        in_current = ticker in current_map
        in_new = ticker in new_map

        current_shares = float(current_map[ticker]["shares"]) if in_current else 0.0
        suggested_shares = float(new_map[ticker]["shares"]) if in_new else 0.0

        if in_current and not in_new:
            # SELL all
            dollar_amount = current_shares * price
            trades.append({
                "action": "SELL",
                "ticker": ticker,
                "current_shares": current_shares,
                "suggested_shares": 0,
                "price": price,
                "dollar_amount": dollar_amount,
                "reason": "Dropped from optimal portfolio",
            })

        elif in_new and not in_current:
            # BUY new position
            score = float(new_map[ticker].get("final_score", 0.0))
            dollar_amount = suggested_shares * price
            trades.append({
                "action": "BUY",
                "ticker": ticker,
                "current_shares": 0,
                "suggested_shares": suggested_shares,
                "price": price,
                "dollar_amount": dollar_amount,
                "reason": f"New entry — score {score:.3f}",
            })

        else:
            # Both: check delta
            delta_shares = suggested_shares - current_shares
            if abs(delta_shares) >= 1:
                action = "BUY" if delta_shares > 0 else "SELL"
                dollar_amount = abs(delta_shares) * price
                trades.append({
                    "action": action,
                    "ticker": ticker,
                    "current_shares": current_shares,
                    "suggested_shares": suggested_shares,
                    "price": price,
                    "dollar_amount": dollar_amount,
                    "reason": f"Weight adjustment: {int(current_shares)}→{int(suggested_shares)} shares",
                })

    return trades
