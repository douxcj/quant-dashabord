import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


@st.cache_data(ttl=300)
def fetch_current_prices(tickers: tuple) -> dict:
    """Fetch latest prices for a list of tickers. Returns {ticker: price}."""
    prices = {}
    if not tickers:
        return prices
    try:
        data = yf.download(list(tickers), period="2d", auto_adjust=True, progress=False)
        if data.empty:
            return prices
        # Handle both single and multi-ticker response
        if isinstance(data.columns, pd.MultiIndex):
            close = data["Close"]
        else:
            close = data[["Close"]].rename(columns={"Close": tickers[0]})
        for ticker in tickers:
            if ticker in close.columns:
                series = close[ticker].dropna()
                if not series.empty:
                    prices[ticker] = float(series.iloc[-1])
    except Exception:
        pass
    # Fallback: fetch individually for any missing
    for ticker in tickers:
        if ticker not in prices:
            try:
                t = yf.Ticker(ticker)
                hist = t.history(period="2d")
                if not hist.empty:
                    prices[ticker] = float(hist["Close"].iloc[-1])
            except Exception:
                prices[ticker] = float("nan")
    return prices


@st.cache_data(ttl=300)
def fetch_historical_data(tickers: tuple, period: str = "1y") -> pd.DataFrame:
    """Fetch OHLCV history for a list of tickers. Returns a Close-prices DataFrame."""
    if not tickers:
        return pd.DataFrame()
    try:
        data = yf.download(list(tickers), period=period, auto_adjust=True, progress=False)
        if data.empty:
            return pd.DataFrame()
        if isinstance(data.columns, pd.MultiIndex):
            close = data["Close"]
        else:
            close = data.rename(columns={"Close": tickers[0]})[["Close"]].rename(
                columns={"Close": tickers[0]}
            )
        return close.dropna(how="all")
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3600)
def get_ticker_info(ticker: str) -> dict:
    """Return a dict of ticker metadata (sector, industry, longName, etc.)."""
    try:
        t = yf.Ticker(ticker)
        info = t.info
        return {
            "name": info.get("longName", ticker),
            "sector": info.get("sector", "Unknown"),
            "industry": info.get("industry", "Unknown"),
            "country": info.get("country", "Unknown"),
            "quote_type": info.get("quoteType", "EQUITY"),
            "currency": info.get("currency", "USD"),
            "week_52_high": info.get("fiftyTwoWeekHigh"),
            "week_52_low": info.get("fiftyTwoWeekLow"),
            "day_change": info.get("regularMarketChangePercent"),
        }
    except Exception:
        return {
            "name": ticker,
            "sector": "Unknown",
            "industry": "Unknown",
            "country": "Unknown",
            "quote_type": "EQUITY",
            "currency": "USD",
            "week_52_high": None,
            "week_52_low": None,
            "day_change": None,
        }


@st.cache_data(ttl=300)
def fetch_fx_rate(pair: str = "CADUSD=X") -> float:
    """Fetch FX rate. Default: CAD per 1 USD (CADUSD=X)."""
    try:
        t = yf.Ticker(pair)
        hist = t.history(period="2d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception:
        pass
    return 0.74  # fallback


@st.cache_data(ttl=300)
def fetch_portfolio_news(tickers: tuple, max_total: int = 12) -> list[dict]:
    """
    Fetch recent news headlines for a set of tickers.
    Returns a list of dicts sorted newest-first.
    """
    from datetime import datetime, timezone
    all_news: list[dict] = []
    seen: set[str] = set()

    for ticker in tickers[:8]:  # cap API calls
        try:
            t = yf.Ticker(ticker)
            items = t.news or []
            for item in items[:4]:
                # yfinance ≥0.2.50 nests fields under item["content"]
                content = item.get("content", item)
                title = (content.get("title") or item.get("title") or "").strip()
                if not title or title in seen:
                    continue
                seen.add(title)

                # URL: nested canonical or flat link
                url = (
                    (content.get("canonicalUrl") or {}).get("url")
                    or content.get("url")
                    or item.get("link")
                    or "#"
                )

                # Publisher name
                source = (
                    (content.get("provider") or {}).get("displayName")
                    or content.get("provider")
                    or item.get("publisher")
                    or ""
                )
                if isinstance(source, dict):
                    source = source.get("displayName", "")

                # Publish timestamp: ISO string or unix int
                raw_ts = content.get("pubDate") or item.get("providerPublishTime", 0)
                try:
                    if isinstance(raw_ts, str):
                        pub_dt = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
                        ts = int(pub_dt.timestamp())
                    else:
                        ts = int(raw_ts)
                        pub_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                    age_mins = int((datetime.now(timezone.utc) - pub_dt).total_seconds() / 60)
                    if age_mins < 60:
                        age_str = f"{age_mins}m ago"
                    elif age_mins < 1440:
                        age_str = f"{age_mins // 60}h ago"
                    else:
                        age_str = f"{age_mins // 1440}d ago"
                except Exception:
                    ts = 0
                    age_str = ""

                all_news.append({
                    "title": title,
                    "source": source,
                    "url": url,
                    "ts": ts,
                    "age": age_str,
                    "ticker": ticker,
                })
        except Exception:
            continue

    all_news.sort(key=lambda x: x["ts"], reverse=True)
    return all_news[:max_total]


def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """Compute RSI for a price series."""
    delta = prices.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))


def calculate_momentum(prices: pd.Series, days: int = 20) -> float:
    """Percentage momentum over `days` trading days."""
    if len(prices) < days + 1:
        return float("nan")
    return (prices.iloc[-1] / prices.iloc[-days - 1] - 1) * 100
