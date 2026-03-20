import streamlit as st
from datetime import date
from database import add_trade, get_trades, delete_trade
from ticker_data import TICKER_OPTIONS, parse_ticker_option, ticker_currency, POPULAR_TICKERS
from i18n import t

_PLACEHOLDER = "— Type to search (NVDA, SHOP.TO, XIU.TO…) —"
_ALL_OPTIONS = [_PLACEHOLDER] + TICKER_OPTIONS


def show(account_id: int, account_name: str, currency: str, embedded: bool = False):
    if not embedded:
        st.title(f"{t('trade_title')} — {account_name}")

    # ── Narrow the entry area to ~60% page width ──────────────────────────────
    col_entry, _ = st.columns([3, 2])

    with col_entry:
        st.subheader(t("trade_log_new"))

        # Ticker selection lives OUTSIDE the form → currency badge updates live
        col_ticker, col_cb = st.columns([4, 1])
        with col_ticker:
            selected_option = st.selectbox(
                t("trade_ticker_label"),
                options=_ALL_OPTIONS,
                key="trade_ticker_select",
                help=t("trade_ticker_help"),
            )
        with col_cb:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            use_manual = st.checkbox(t("trade_custom"), key="trade_ticker_manual_cb",
                                     help=t("trade_custom_help"))

        if use_manual:
            raw = st.text_input(
                t("trade_ticker_label"),
                placeholder=t("trade_manual_placeholder"),
                key="trade_ticker_manual_input",
            ).upper().strip()
            ticker = raw
            detected_ccy = ticker_currency(ticker) if ticker else currency
        elif selected_option != _PLACEHOLDER:
            ticker = parse_ticker_option(selected_option)
            detected_ccy = ticker_currency(ticker)
        else:
            ticker = ""
            detected_ccy = currency

        # Live badge
        if ticker:
            company = POPULAR_TICKERS.get(ticker, "")
            ccy_color = "#00b386" if detected_ccy == "CAD" else "#3b82f6"
            st.markdown(
                f"<span style='background:#f0fdf9;color:#00b386;border:1px solid #86efac;"
                f"border-radius:6px;padding:2px 10px;font-size:0.82rem;font-weight:600;"
                f"margin-right:6px;'>{ticker}</span>"
                f"<span style='background:#f3f4f6;color:#374151;border:1px solid #e5e7eb;"
                f"border-radius:6px;padding:2px 10px;font-size:0.82rem;'>{company}</span>"
                f"<span style='color:{ccy_color};font-size:0.82rem;font-weight:600;"
                f"margin-left:10px;'>💱 {detected_ccy}</span>",
                unsafe_allow_html=True,
            )
            if detected_ccy != currency:
                st.caption(
                    f"{t('trade_converted_auto')} · "
                    f"{detected_ccy} → {currency}"
                )
        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

        # ── Trade details form ─────────────────────────────────────────────────
        with st.form("trade_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                trade_date = st.date_input(t("trade_date"), value=date.today())
                action = st.selectbox(t("trade_action"), ["BUY", "SELL"])
            with c2:
                quantity = st.number_input(
                    t("trade_qty"),
                    min_value=0.0001, step=1.0, format="%.4f", value=1.0,
                )
                price = st.number_input(
                    f"{t('trade_price')} ({detected_ccy})",
                    min_value=0.0001, step=0.01, format="%.4f", value=1.0,
                )
            notes = st.text_input(t("trade_notes"), placeholder=t("trade_notes_placeholder"))

            if ticker:
                st.markdown(
                    f"**{action}** {quantity:.4f} × **{ticker}** "
                    f"@ {detected_ccy} ${price:.4f} = **{detected_ccy} ${quantity*price:,.2f}**"
                )

            if st.form_submit_button(t("trade_submit"), type="primary"):
                if not ticker:
                    st.error(t("trade_err_no_ticker"))
                elif quantity <= 0 or price <= 0:
                    st.error(t("trade_err_qty_price"))
                else:
                    add_trade(account_id, ticker, action, quantity, price, trade_date, notes)
                    st.success(
                        f"{t('trade_submit')}: **{action} {quantity:.4f} {ticker}** "
                        f"@ {detected_ccy} ${price:.4f}"
                    )

    st.divider()

    # ── Trade history ─────────────────────────────────────────────────────────
    st.subheader(t("trade_history"))
    trades = get_trades(account_id)

    if trades.empty:
        st.info(t("trade_no_trades"))
        return

    display = trades[["id", "trade_date", "ticker", "action",
                       "quantity", "price", "notes"]].copy()
    display["value"] = display["quantity"] * display["price"]
    display["ccy"] = display["ticker"].apply(ticker_currency)
    display.columns = [
        t("trade_col_id"), t("trade_col_date"), t("trade_col_ticker"),
        t("trade_col_action"), t("trade_col_qty"), t("trade_col_price"),
        t("trade_col_notes"), t("trade_col_value"), t("trade_col_ccy"),
    ]

    action_col = t("trade_col_action")

    def _color_action(val):
        return "color:#00b386;font-weight:700" if val == "BUY" else "color:#e53935;font-weight:700"

    st.dataframe(
        display.style
        .format({
            t("trade_col_qty"):   "{:.4f}",
            t("trade_col_price"): "${:.4f}",
            t("trade_col_value"): "${:,.2f}",
        })
        .applymap(_color_action, subset=[action_col]),
        use_container_width=True,
        hide_index=True,
    )

    with st.expander(t("trade_delete_expander")):
        with st.form("delete_form"):
            selected_id = st.selectbox(
                t("trade_delete_select"),
                options=trades["id"].tolist(),
                format_func=lambda i: (
                    f"#{i}  "
                    + trades.loc[trades["id"] == i, "action"].values[0]
                    + "  "
                    + trades.loc[trades["id"] == i, "ticker"].values[0]
                    + "  "
                    + str(trades.loc[trades["id"] == i, "trade_date"].values[0])
                ),
            )
            if st.form_submit_button(t("trade_delete_btn"), type="secondary"):
                delete_trade(selected_id)
                st.warning(f"#{selected_id} deleted.")
                st.rerun()
