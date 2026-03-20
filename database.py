import sqlite3
from pathlib import Path
import pandas as pd

DB_PATH = Path(__file__).parent / "quantview.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            currency TEXT DEFAULT 'CAD',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            starting_capital REAL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER,
            amount REAL,
            deposit_date DATE,
            notes TEXT,
            FOREIGN KEY (account_id) REFERENCES accounts(id)
        );

        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER,
            ticker TEXT,
            action TEXT,
            quantity REAL,
            price REAL,
            trade_date DATE,
            notes TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (account_id) REFERENCES accounts(id)
        );

        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER,
            ticker TEXT,
            added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (account_id) REFERENCES accounts(id)
        );

        CREATE TABLE IF NOT EXISTS quant_portfolios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            currency TEXT DEFAULT 'USD',
            risk_mode TEXT DEFAULT 'Conservative',
            starting_cash REAL DEFAULT 0,
            current_cash REAL DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS quant_holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            portfolio_id INTEGER,
            ticker TEXT NOT NULL,
            shares REAL DEFAULT 0,
            avg_entry_price REAL DEFAULT 0,
            FOREIGN KEY (portfolio_id) REFERENCES quant_portfolios(id)
        );

        CREATE TABLE IF NOT EXISTS quant_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            portfolio_id INTEGER,
            ticker TEXT,
            action TEXT,
            shares REAL,
            price REAL,
            commission REAL DEFAULT 0,
            trade_type TEXT DEFAULT 'Manual',
            notes TEXT,
            executed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (portfolio_id) REFERENCES quant_portfolios(id)
        );

        CREATE TABLE IF NOT EXISTS quant_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            portfolio_id INTEGER,
            total_value REAL,
            cash REAL,
            holdings_json TEXT,
            regime TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (portfolio_id) REFERENCES quant_portfolios(id)
        );

        CREATE TABLE IF NOT EXISTS quant_rebalances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            portfolio_id INTEGER,
            regime TEXT,
            suggestion_json TEXT,
            actual_json TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (portfolio_id) REFERENCES quant_portfolios(id)
        );

        CREATE TABLE IF NOT EXISTS quant_streaks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            portfolio_id INTEGER,
            ticker TEXT,
            consecutive_count INTEGER DEFAULT 0,
            FOREIGN KEY (portfolio_id) REFERENCES quant_portfolios(id),
            UNIQUE(portfolio_id, ticker)
        );
    """)

    conn.close()


# ── Account CRUD ──────────────────────────────────────────────────────────────

def get_accounts() -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM accounts ORDER BY created_at", conn)
    conn.close()
    return df


def get_account(account_id: int) -> dict:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM accounts WHERE id=?", (account_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else {}


def create_account(name: str, currency: str, starting_capital: float):
    conn = get_connection()
    conn.execute(
        "INSERT INTO accounts (name, currency, starting_capital) VALUES (?, ?, ?)",
        (name, currency, starting_capital),
    )
    conn.commit()
    conn.close()


def update_account_capital(account_id: int, starting_capital: float):
    conn = get_connection()
    conn.execute(
        "UPDATE accounts SET starting_capital=? WHERE id=?",
        (starting_capital, account_id),
    )
    conn.commit()
    conn.close()


def delete_account(account_id: int):
    """Delete a portfolio and all its associated data."""
    conn = get_connection()
    conn.execute("DELETE FROM trades WHERE account_id=?", (account_id,))
    conn.execute("DELETE FROM watchlist WHERE account_id=?", (account_id,))
    conn.execute("DELETE FROM deposits WHERE account_id=?", (account_id,))
    conn.execute("DELETE FROM accounts WHERE id=?", (account_id,))
    conn.commit()
    conn.close()


# ── Deposit CRUD ──────────────────────────────────────────────────────────────

def get_deposits(account_id: int) -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql(
        "SELECT * FROM deposits WHERE account_id=? ORDER BY deposit_date",
        conn,
        params=(account_id,),
    )
    conn.close()
    return df


def add_deposit(account_id: int, amount: float, deposit_date, notes: str = ""):
    conn = get_connection()
    conn.execute(
        "INSERT INTO deposits (account_id, amount, deposit_date, notes) VALUES (?, ?, ?, ?)",
        (account_id, amount, str(deposit_date), notes),
    )
    conn.commit()
    conn.close()


def get_total_deposited(account_id: int) -> float:
    """Starting capital + all subsequent deposits."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT starting_capital FROM accounts WHERE id=?", (account_id,))
    row = cursor.fetchone()
    starting = float(row[0]) if row else 0.0
    cursor.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM deposits WHERE account_id=?",
        (account_id,),
    )
    dep_total = float(cursor.fetchone()[0])
    conn.close()
    return starting + dep_total


# ── Trade CRUD ────────────────────────────────────────────────────────────────

def get_trades(account_id: int) -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql(
        "SELECT * FROM trades WHERE account_id=? ORDER BY trade_date, created_at",
        conn,
        params=(account_id,),
    )
    conn.close()
    return df


def add_trade(
    account_id: int,
    ticker: str,
    action: str,
    quantity: float,
    price: float,
    trade_date,
    notes: str = "",
):
    conn = get_connection()
    conn.execute(
        """INSERT INTO trades (account_id, ticker, action, quantity, price, trade_date, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (account_id, ticker.upper().strip(), action, quantity, price, str(trade_date), notes),
    )
    conn.commit()
    conn.close()


def delete_trade(trade_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM trades WHERE id=?", (trade_id,))
    conn.commit()
    conn.close()


# ── Watchlist CRUD ────────────────────────────────────────────────────────────

def get_watchlist(account_id: int) -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql(
        "SELECT * FROM watchlist WHERE account_id=? ORDER BY added_at",
        conn,
        params=(account_id,),
    )
    conn.close()
    return df


def add_to_watchlist(account_id: int, ticker: str):
    conn = get_connection()
    existing = pd.read_sql(
        "SELECT id FROM watchlist WHERE account_id=? AND ticker=?",
        conn,
        params=(account_id, ticker.upper().strip()),
    )
    if existing.empty:
        conn.execute(
            "INSERT INTO watchlist (account_id, ticker) VALUES (?, ?)",
            (account_id, ticker.upper().strip()),
        )
        conn.commit()
    conn.close()


def remove_from_watchlist(watchlist_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM watchlist WHERE id=?", (watchlist_id,))
    conn.commit()
    conn.close()


# ── Quant Portfolio CRUD ───────────────────────────────────────────────────────

def get_quant_portfolios() -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM quant_portfolios ORDER BY created_at", conn)
    conn.close()
    return df


def get_quant_portfolio(portfolio_id: int) -> dict:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM quant_portfolios WHERE id=?", (portfolio_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else {}


def create_quant_portfolio(name: str, currency: str, risk_mode: str, starting_cash: float) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO quant_portfolios (name, currency, risk_mode, starting_cash, current_cash) "
        "VALUES (?, ?, ?, ?, ?)",
        (name, currency, risk_mode, starting_cash, starting_cash),
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return new_id


def delete_quant_portfolio(portfolio_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM quant_streaks WHERE portfolio_id=?", (portfolio_id,))
    conn.execute("DELETE FROM quant_rebalances WHERE portfolio_id=?", (portfolio_id,))
    conn.execute("DELETE FROM quant_snapshots WHERE portfolio_id=?", (portfolio_id,))
    conn.execute("DELETE FROM quant_trades WHERE portfolio_id=?", (portfolio_id,))
    conn.execute("DELETE FROM quant_holdings WHERE portfolio_id=?", (portfolio_id,))
    conn.execute("DELETE FROM quant_portfolios WHERE id=?", (portfolio_id,))
    conn.commit()
    conn.close()


def get_quant_holdings(portfolio_id: int) -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql(
        "SELECT * FROM quant_holdings WHERE portfolio_id=? ORDER BY ticker",
        conn,
        params=(portfolio_id,),
    )
    conn.close()
    return df


def upsert_quant_holding(portfolio_id: int, ticker: str, shares: float, avg_entry_price: float):
    """Insert or update a holding. If shares <= 0, delete the row."""
    conn = get_connection()
    if shares <= 0:
        conn.execute(
            "DELETE FROM quant_holdings WHERE portfolio_id=? AND ticker=?",
            (portfolio_id, ticker),
        )
    else:
        existing = pd.read_sql(
            "SELECT id FROM quant_holdings WHERE portfolio_id=? AND ticker=?",
            conn,
            params=(portfolio_id, ticker),
        )
        if existing.empty:
            conn.execute(
                "INSERT INTO quant_holdings (portfolio_id, ticker, shares, avg_entry_price) "
                "VALUES (?, ?, ?, ?)",
                (portfolio_id, ticker, shares, avg_entry_price),
            )
        else:
            conn.execute(
                "UPDATE quant_holdings SET shares=?, avg_entry_price=? "
                "WHERE portfolio_id=? AND ticker=?",
                (shares, avg_entry_price, portfolio_id, ticker),
            )
    conn.commit()
    conn.close()


def delete_quant_holding(portfolio_id: int, ticker: str):
    conn = get_connection()
    conn.execute(
        "DELETE FROM quant_holdings WHERE portfolio_id=? AND ticker=?",
        (portfolio_id, ticker),
    )
    conn.commit()
    conn.close()


def get_quant_trades(portfolio_id: int) -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql(
        "SELECT * FROM quant_trades WHERE portfolio_id=? ORDER BY executed_at DESC",
        conn,
        params=(portfolio_id,),
    )
    conn.close()
    return df


def log_quant_trade(
    portfolio_id: int,
    ticker: str,
    action: str,
    shares: float,
    price: float,
    commission: float = 0.0,
    trade_type: str = "Manual",
    notes: str = "",
):
    conn = get_connection()
    conn.execute(
        "INSERT INTO quant_trades "
        "(portfolio_id, ticker, action, shares, price, commission, trade_type, notes) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (portfolio_id, ticker, action, shares, price, commission, trade_type, notes),
    )
    conn.commit()
    conn.close()


def update_quant_cash(portfolio_id: int, new_cash: float):
    conn = get_connection()
    conn.execute(
        "UPDATE quant_portfolios SET current_cash=? WHERE id=?",
        (new_cash, portfolio_id),
    )
    conn.commit()
    conn.close()


def get_quant_snapshots(portfolio_id: int) -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql(
        "SELECT * FROM quant_snapshots WHERE portfolio_id=? ORDER BY created_at",
        conn,
        params=(portfolio_id,),
    )
    conn.close()
    return df


def save_quant_snapshot(
    portfolio_id: int,
    total_value: float,
    cash: float,
    holdings_json: str,
    regime: str,
):
    conn = get_connection()
    conn.execute(
        "INSERT INTO quant_snapshots (portfolio_id, total_value, cash, holdings_json, regime) "
        "VALUES (?, ?, ?, ?, ?)",
        (portfolio_id, total_value, cash, holdings_json, regime),
    )
    conn.commit()
    conn.close()


def save_quant_rebalance(
    portfolio_id: int,
    regime: str,
    suggestion_json: str,
    actual_json: str = "",
):
    conn = get_connection()
    conn.execute(
        "INSERT INTO quant_rebalances (portfolio_id, regime, suggestion_json, actual_json) "
        "VALUES (?, ?, ?, ?)",
        (portfolio_id, regime, suggestion_json, actual_json),
    )
    conn.commit()
    conn.close()


def get_quant_rebalances(portfolio_id: int) -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql(
        "SELECT * FROM quant_rebalances WHERE portfolio_id=? ORDER BY created_at DESC",
        conn,
        params=(portfolio_id,),
    )
    conn.close()
    return df


def get_quant_streaks(portfolio_id: int) -> dict:
    """Return {ticker: consecutive_count}"""
    conn = get_connection()
    df = pd.read_sql(
        "SELECT ticker, consecutive_count FROM quant_streaks WHERE portfolio_id=?",
        conn,
        params=(portfolio_id,),
    )
    conn.close()
    if df.empty:
        return {}
    return dict(zip(df["ticker"], df["consecutive_count"]))


def update_quant_streaks(portfolio_id: int, top5_tickers: list):
    """
    For each ticker in the full universe:
    - If in top5_tickers → increment streak (or insert with 1)
    - If not in top5_tickers → reset to 0 (and delete if already 0)
    Only store tickers with streak > 0.
    """
    conn = get_connection()
    # Increment streaks for tickers in top5
    for ticker in top5_tickers:
        existing = conn.execute(
            "SELECT consecutive_count FROM quant_streaks WHERE portfolio_id=? AND ticker=?",
            (portfolio_id, ticker),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE quant_streaks SET consecutive_count=consecutive_count+1 "
                "WHERE portfolio_id=? AND ticker=?",
                (portfolio_id, ticker),
            )
        else:
            conn.execute(
                "INSERT INTO quant_streaks (portfolio_id, ticker, consecutive_count) "
                "VALUES (?, ?, 1)",
                (portfolio_id, ticker),
            )
    # Reset streaks for tickers not in top5
    if top5_tickers:
        placeholders = ",".join(["?" for _ in top5_tickers])
        conn.execute(
            f"DELETE FROM quant_streaks WHERE portfolio_id=? AND ticker NOT IN ({placeholders})",
            [portfolio_id] + list(top5_tickers),
        )
    else:
        conn.execute(
            "DELETE FROM quant_streaks WHERE portfolio_id=?",
            (portfolio_id,),
        )
    conn.commit()
    conn.close()
