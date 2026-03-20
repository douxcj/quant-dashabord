import streamlit as st
import pandas as pd
import numpy as np
from datetime import date
from database import create_account, update_account_capital, delete_account, get_accounts, get_account, add_trade
from market_data import fetch_current_prices
from ticker_data import TICKER_OPTIONS, parse_ticker_option, ticker_currency, POPULAR_TICKERS
from i18n import t

_PLACEHOLDER = "— Search ticker (NVDA, SHOP.TO, XIU.TO…) —"
_ALL_OPTIONS = [_PLACEHOLDER] + TICKER_OPTIONS


def show(account_id: int, account_name: str, currency: str, embedded: bool = False):
    if not embedded:
        st.title(t("accounts_title"))

    tab_create, tab_all = st.tabs([t("accounts_tab_new"), t("accounts_tab_all")])

    # ══════════════════════════════════════════════════════════════════════════
    with tab_create:
        st.subheader(t("accounts_create_title"))
        st.markdown(t("accounts_create_desc"))
        st.markdown("---")

        col1, col2, col3 = st.columns(3)
        with col1:
            new_name = st.text_input(
                t("accounts_name"),
                placeholder=t("accounts_name_placeholder"),
                key="create_port_name",
            )
        with col2:
            new_currency = st.selectbox(
                t("accounts_currency"),
                ["CAD", "USD"],
                key="create_port_currency",
                help=t("accounts_currency_help"),
            )
        with col3:
            new_cash = st.number_input(
                t("accounts_cash"),
                min_value=0.0,
                step=500.0,
                value=0.0,
                key="create_port_cash",
                help=t("accounts_cash_help"),
            )

        st.markdown("---")
        st.markdown(t("accounts_holdings_title"))
        st.caption(t("accounts_holdings_desc"))

        n = int(
            st.number_input(
                t("accounts_n_holdings"),
                min_value=0,
                max_value=20,
                value=0,
                step=1,
                key="create_port_n_holdings",
            )
        )

        holdings_to_import: list[tuple[str, float, float]] = []
        for i in range(n):
            c1, c2, c3 = st.columns([3, 1.2, 1.2])
            with c1:
                sel = st.selectbox(
                    f"Holding {i + 1}",
                    options=_ALL_OPTIONS,
                    key=f"create_port_ticker_{i}",
                    label_visibility="collapsed" if i > 0 else "visible",
                )
                ticker_i = parse_ticker_option(sel) if sel != _PLACEHOLDER else ""
                if ticker_i:
                    ccy_i = ticker_currency(ticker_i)
                    company_i = POPULAR_TICKERS.get(ticker_i, "")
                    label = f"`{ticker_i}` · {ccy_i}" + (f" — {company_i}" if company_i else "")
                    st.caption(label)
            with c2:
                shares_i = st.number_input(
                    t("accounts_shares") if i == 0 else f"{t('accounts_shares')} {i+1}",
                    min_value=0.0,
                    step=1.0,
                    format="%.4f",
                    key=f"create_port_shares_{i}",
                    label_visibility="collapsed" if i > 0 else "visible",
                )
            with c3:
                cost_i = st.number_input(
                    t("accounts_avg_cost") if i == 0 else f"Cost {i+1}",
                    min_value=0.0,
                    step=0.01,
                    format="%.4f",
                    key=f"create_port_cost_{i}",
                    label_visibility="collapsed" if i > 0 else "visible",
                    help=t("accounts_avg_cost_help"),
                )
            if ticker_i and shares_i > 0:
                holdings_to_import.append((ticker_i, float(shares_i), float(cost_i)))

        st.markdown("---")
        if st.button(t("accounts_create_btn"), type="primary", key="create_port_btn"):
            _create_portfolio(new_name, new_currency, new_cash, holdings_to_import)

    # ══════════════════════════════════════════════════════════════════════════
    with tab_all:
        st.subheader(t("accounts_all_title"))
        all_accounts = get_accounts()
        if all_accounts.empty:
            st.info("No portfolios yet.")
        else:
            display = all_accounts[["name", "currency", "starting_capital", "created_at"]].copy()
            display.columns = [
                t("accounts_col_name"), t("accounts_col_currency"),
                t("accounts_col_cash"), t("accounts_col_created"),
            ]
            st.dataframe(
                display.style.format({t("accounts_col_cash"): "${:,.2f}"}),
                use_container_width=True,
                hide_index=True,
            )

            st.markdown("---")
            st.subheader(t("accounts_delete_title"))
            st.caption(t("accounts_delete_warn"))
            with st.form("delete_portfolio_form"):
                names = all_accounts["name"].tolist()
                ids = all_accounts["id"].tolist()
                del_name = st.selectbox(t("accounts_delete_select"), names)
                del_id = ids[names.index(del_name)]
                confirm = st.checkbox(t("accounts_delete_confirm", name=del_name))
                if st.form_submit_button(t("accounts_delete_btn"), type="secondary"):
                    if confirm:
                        delete_account(del_id)
                        st.warning(f'"{del_name}" deleted.')
                        st.rerun()
                    else:
                        st.error(t("accounts_confirm_err"))


def _create_portfolio(name: str, currency: str, cash: float,
                       holdings: list[tuple[str, float, float]]):
    if not name.strip():
        st.error(t("accounts_err_no_name"))
        return

    create_account(name.strip(), currency, cash)

    accounts = get_accounts()
    new_id = int(accounts.iloc[-1]["id"])

    if not holdings:
        st.success(t("accounts_success_cash", name=name, cash=cash, ccy=currency))
        return

    zero_tickers = tuple(tk for tk, s, c in holdings if c == 0.0)
    live_prices: dict[str, float] = {}
    if zero_tickers:
        live_prices = fetch_current_prices(zero_tickers)

    imported, skipped = 0, []
    total_import_cost = 0.0
    for ticker, shares, avg_cost in holdings:
        price = avg_cost if avg_cost > 0 else live_prices.get(ticker, float("nan"))
        if np.isnan(price):
            skipped.append(ticker)
            continue
        add_trade(
            account_id=new_id,
            ticker=ticker,
            action="BUY",
            quantity=shares,
            price=price,
            trade_date=date.today(),
            notes="Imported holding",
        )
        total_import_cost += shares * price
        imported += 1

    if imported > 0:
        update_account_capital(new_id, cash + total_import_cost)

    lines = [
        t("accounts_created", name=name),
        t("accounts_cash_line", cash=cash, ccy=currency),
        t("accounts_imported_line", n=imported),
    ]
    if skipped:
        lines.append(t("accounts_skipped_line", tickers=", ".join(skipped)))
    st.success("\n".join(lines))
    st.info(t("accounts_select_info"))
