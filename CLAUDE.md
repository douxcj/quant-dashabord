# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
streamlit run app.py
```

Two active pages, navigated via URL query params: `?page=myportfolio` (default), `?page=quant`. Legacy params (`dashboard`, `trade`, `analytics`, `rebalancer`, `watchlist`, `portfolio`) all redirect to `myportfolio`. Language is toggled via `?lang=en` or `?lang=zh`.

## Installing Dependencies

```bash
pip install -r requirements.txt
```

Key packages: `streamlit`, `yfinance`, `pandas`, `numpy`, `plotly`, `sqlalchemy`, `scipy`.

## Architecture Overview

**Entry point:** `app.py` — sets global CSS (Wealthsimple-inspired light theme), initializes the SQLite DB, renders the sidebar (account selector + nav), and routes to one of two view modules via `?page=` query param.

**Data layer (`database.py`):** Raw SQLite via `sqlite3`. DB file is `quantview.db` in the project root. Schema has two groups of tables:
- *Manual portfolio*: `accounts`, `trades`, `deposits`, `watchlist`
- *Quant portfolio*: `quant_portfolios`, `quant_holdings`, `quant_trades`, `quant_snapshots`, `quant_rebalances`, `quant_streaks`

**Market data (`market_data.py`):** Wraps `yfinance`. All fetch functions are decorated with `@st.cache_data` (TTL 300s for prices/FX/news, 3600s for ticker metadata). The `fetch_current_prices` and `fetch_historical_data` functions accept `tuple` arguments (not lists) because Streamlit's cache hashes by value — always pass tuples.

**Portfolio logic (`portfolio.py`):** Computes holdings from raw trades using weighted-average cost basis (FIFO-style for sells). `build_portfolio_history` has two modes: real trade-date replay (multiple trade dates) vs. hypothetical reconstruction using current share counts × historical prices (single-date "imported" portfolios).

**Metrics (`metrics.py`):** Calculates Sharpe, Sortino, max drawdown, beta, win rate, etc. Benchmarks: `XIU.TO` for CAD accounts, `SPY` for USD. Risk-free rates: 4.5% CAD, 5.0% USD.

**Internationalization (`i18n.py`):** All UI strings go through `t(key)` which reads `st.session_state["lang"]` (set from URL `?lang=` param). Both `"en"` and `"zh"` translations are in a single `TRANSLATIONS` dict. Add new strings to both language blocks.

**Views (`views/`):**
- `my_portfolio.py` — unified manual portfolio page; calls `show(account_id, account_name, currency)`. Embeds `accounts.py` for account management.
- `quant_portfolio.py` — quant portfolio manager; calls `show()` with no args (uses its own DB tables, independent of the manual account system).
- Other files (`dashboard.py`, `trade_entry.py`, `analytics.py`, `rebalancer.py`, `watchlist.py`) are legacy modules no longer routed to directly — they may still be imported by `my_portfolio.py`.

**Components (`components/`):**
- `cards.py` — reusable metric card renderers
- `charts.py` — Plotly chart builders (portfolio value, P&L, drawdown, rolling Sharpe, sector, etc.)
- `news.py` — `render_news_panel(tickers: tuple)` shared news feed, used across views

**Quant models (`models/`):** Two distinct model systems:
- *Rebalancer models* (`momentum.py`, `equal_weight.py`, `risk_parity.py`, `mean_reversion.py`, `trend_following.py`): each exposes `NAME`, `DESCRIPTION`, and `run(tickers, portfolio_value, current_weights) -> pd.DataFrame`.
- *4-layer systematic model* (`quant_portfolio_model.py`): implements regime detection → momentum scoring → mean reversion overlay → portfolio construction for ETF rotation. Used exclusively by `views/quant_portfolio.py`.

**Ticker data (`ticker_data.py`):** Static dict of popular US/Canadian tickers with company names. Canadian TSX tickers use the `.TO` suffix convention (also used by yfinance).

## Key Conventions

- **Multi-account:** Every manual-portfolio DB query is scoped by `account_id`. The active account is stored in `st.session_state.selected_account_idx` and passed down through `show()`. The quant portfolio system is account-independent and uses its own `quant_*` tables.
- **Currency:** CAD accounts use `.TO`-suffixed tickers; USD otherwise. FX conversion (CAD/USD) is fetched via `fetch_fx_rate("CADUSD=X")`.
- **Cache invalidation:** Market data caches are per-`tickers` tuple. Force refresh by calling `st.cache_data.clear()`.
- **No ORM:** All DB access uses raw `sqlite3` connections opened and closed per function call.
