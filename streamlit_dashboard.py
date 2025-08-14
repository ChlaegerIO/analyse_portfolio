import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import backend_sqlite  # Importiere das Backend-Modul
import backend_analysis  # Importiere das Backend-Modul für Analysen

# TODO: Verknüpfung von Transaktionen und Portfolie
# TODO: Berechnung Performance und aktueller Portfoliostand
# TODO: Aktienkurs anschauen von allen Firmen mit Ticker
# TODO: Automated run script with an app icon: conda activate market, streamlit run streamlit_dashboard.py


# Page config
st.set_page_config(page_title="Portfolio Dashboard", layout="wide")

# --- Input Data ---
with st.spinner("Lade aktuelle Positionen..."):
    current_positions = backend_analysis.get_current_positions()

# Entferne doppelte Spaltennamen
current_positions = current_positions.loc[:, ~current_positions.columns.duplicated()]

# --- Preis & Kennzahlen ---
if "Current Price" not in current_positions.columns or current_positions["Current Price"].isnull().any():
    # Fallback: Hole die Preise direkt bzw. neu
    current_positions["Current Price"] = current_positions.apply(
        lambda row: backend_analysis.fetch_kpis(row["Ticker"], row["Currency"]).get("Current Price", None), axis=1
    )

current_positions["Value (CHF)"] = current_positions.apply(lambda row: backend_analysis.convert_to_chf(row) * row["Quantity"], axis=1)
current_positions["Profit/Loss"] = (current_positions["Current Price"] - current_positions["Buy Price"]) * current_positions["Quantity"]
current_positions["Profit/Loss (%)"] = ((current_positions["Current Price"] - current_positions["Buy Price"]) / current_positions["Buy Price"]) * 100

# --- Rundung ---
round_cols = ["Buy Price", "Current Price", "Value (CHF)", "Profit/Loss", "Profit/Loss (%)", "EPS", "PE Ratio",
              "PEG Ratio", "Beta", "Free Cash Flow", "Revenue Growth YoY (%)"]
existing_round_cols = [col for col in round_cols if col in current_positions.columns]
current_positions[existing_round_cols] = current_positions[existing_round_cols].round(3)

# --- Portfolio Summary ---
total_value_chf = current_positions["Value (CHF)"].sum()
growth_pct = 10  # TODO: dynamic calculation of growth percentage

# --- Seitenwahl ---
page = st.sidebar.radio("Seite wählen", ["Portfolio", "Watchlist & Kursentwicklung"])

if page == "Portfolio":
    st.title("📊 Live Portfolio Dashboard")
    # --- Portfolio Summary ---
    col1, col2 = st.columns([1, 1])
    with col1:
        st.metric("Total Value Portfolio", f"{total_value_chf:.3f} CHF")
    with col2:
        st.metric("Value Development", f"{growth_pct:.2f} %")

    # Spaltenanordnung
    cols_order = ["Name", "Ticker", "Currency", "Quantity", "Buy Price", "Current Price", "Value (CHF)",
                  "Profit/Loss", "Profit/Loss (%)", "Price/Book", "PE Ratio", "Market Cap", "PEG Ratio", "Beta",
                  "Free Cash Flow", "Revenue Growth YoY (%)"]


    # --- Portfolio Entwicklungsdiagramm ---
    change_duration = {
        "1 Tag": ("1d", "1m"),
        "1 Woche": ("1wk", "1d"),
        "1 Monat": ("1mo", "1d"),
        "6 Monate": ("6mo", "1d"),
        "1 Jahr": ("1y", "1d"),
        "5 Jahre": ("5y", "1wk"),
        "10 Jahre": ("10y", "1wk"),
        "20 Jahre": ("20y", "1mo"),
        "Max": ("max", "1mo")
    }

    st.markdown("### 📈 Portfolio Entwicklung")

    # circle diagram of share per stock - left side
    fig1 = go.Figure()
    fig1.add_trace(go.Pie(labels=current_positions["Name"], values=current_positions["Value (CHF)"], name="Portfolio Share"))
    fig1.update_layout(title="Portfolio Share by Stock")
    st.plotly_chart(fig1, use_container_width=True)

    portfolio_tickers = pd.concat([current_positions[["Name", "Ticker"]]])
    selected_name = st.selectbox("Wähle eine Position aus dem Portfolio:", portfolio_tickers["Name"])
    portfolio_ticker_values = portfolio_tickers[portfolio_tickers["Name"] == selected_name]["Ticker"].values
    selected_portfolio_ticker = portfolio_ticker_values[0] if len(portfolio_ticker_values) > 0 else None

    # Zeitraum-Auswahl für Kursentwicklung
    duration_map = {
        "1 Tag": ("1d", "1m"),
        "1 Woche": ("1wk", "15m"),
        "1 Monat": ("1mo", "1d"),
        "6 Monate": ("6mo", "1d"),
        "1 Jahr": ("1y", "1d"),
        "5 Jahre": ("5y", "1d"),
        "10 Jahre": ("10y", "1wk"),
        "20 Jahre": ("20y", "1wk"),
        "Max": ("max", "1wk")
    }
    selected_duration = st.selectbox("Zeitraum für Kursentwicklung:", list(duration_map.keys()), index=5)
    period, interval = duration_map[selected_duration]

    if selected_portfolio_ticker:
        @st.cache_data(ttl=3600)
        def get_history(ticker, period, interval):
            return yf.Ticker(ticker).history(period=period, interval=interval)

        hist = get_history(selected_portfolio_ticker, period, interval)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=hist.index, y=hist["Close"], mode="lines", name="Kurs", line=dict(color="royalblue")))
        fig.update_layout(title=f"Kursentwicklung von {selected_portfolio_ticker} ({selected_duration}, {interval})",
                          xaxis_title="Datum", yaxis_title="Kurs", height=500)
        
        # Get transactions for this ticker and add buy/sell points to graph
        transactions = backend_sqlite.get_transactions()
        transactions = transactions[transactions["Ticker"] == selected_portfolio_ticker].copy()
        transactions["date"] = pd.to_datetime(transactions["date"], dayfirst=True, errors="coerce")

        # Buy markers
        buys = transactions[transactions["buy_sell"] == "BUY"]
        buy_dates = buys["date"]
        buy_prices = buys["price_per_unit"]
        # buy_prices = [hist["Close"].loc[date] if date in hist.index else None for date in buy_dates]
        fig.add_trace(go.Scatter(
            x=buy_dates, y=buy_prices,
            mode="markers", name="Buy",
            marker=dict(color="green", size=12, symbol="triangle-up", line=dict(width=2, color="black")),
            showlegend=True
        ))

        # Sell markers
        sells = transactions[transactions["buy_sell"] == "SELL"]
        sell_dates = sells["date"]
        sell_prices = sells["price_per_unit"]
        # sell_prices = [hist["Close"].loc[date] if date in hist.index else None for date in sell_dates]
        fig.add_trace(go.Scatter(
            x=sell_dates, y=sell_prices,
            mode="markers", name="Sell",
            marker=dict(color="red", size=12, symbol="triangle-down", line=dict(width=2, color="black")),
            showlegend=True
        ))

        st.plotly_chart(fig, use_container_width=True)

    st.markdown("### 📌 Current Positions")
    # Display table with sorting enabled
    st.dataframe(
        current_positions,
        use_container_width=True,
        height=400
    )

    # Optionally, provide an "Edit" button to open st.data_editor for editing
    if st.button("Edit Current Prices"):
        editable_cols = ["Current Price"]
        edited_positions = st.data_editor(
            current_positions,
            use_container_width=True,
            column_order=["Name"] + [col for col in current_positions.columns if col != "Name"],
            column_config={
                "Name": st.column_config.TextColumn(disabled=True, pinned=True),
                **{col: st.column_config.NumberColumn() for col in editable_cols}
            },
            disabled=[col for col in current_positions.columns if col not in editable_cols],
            num_rows="dynamic"
        )

        # Check for edits and update database
        for idx, row in edited_positions.iterrows():
            orig_price = current_positions.loc[idx, "Current Price"]
            new_price = row["Current Price"]
            if pd.notnull(new_price) and new_price != orig_price:
                ticker = row["Ticker"]
                backend_sqlite.update_current_price(ticker, new_price)
                current_positions.loc[idx, "Current Price"] = new_price  # update in-memory


    # --- Alle Transaktionen anzeigen ---
    st.markdown("---")
    st.markdown("### 📑 Alle Transaktionen")
    try:
        transactions_df = backend_sqlite.get_transactions()
        st.dataframe(transactions_df, use_container_width=True, height=400)
    except Exception as e:
        st.warning(f"Transaktionen konnten nicht geladen werden: {e}")

    # --- Datenimport (Yuh csv, ...) ---
    st.markdown("---")
    st.markdown("### 📥 Yuh CSV Import")
    yuh_file = st.file_uploader("Wähle eine Yuh CSV-Datei zum Hinzufügen zur Datenbank aus", type=["csv"])
    if yuh_file is not None:
        yuh_df = backend_sqlite.read_yuh_csv(yuh_file)
        st.markdown("**Vorschau der importierten Yuh CSV-Datei:**")
        st.dataframe(yuh_df, use_container_width=True)

elif page == "Watchlist & Kursentwicklung":
    st.title("👀 Watchlist & Kursentwicklung")
    # --- Watchlist aus Datenbank laden ---
    def show_watchlist():
        watchlist = backend_sqlite.get_watchlist()
        st.markdown("### 👀 Watchlist")
        st.dataframe(watchlist, use_container_width=True)
        return watchlist

    # --- Watchlist hinzufügen, entfernen und anzeigen ---
    st.markdown("#### ➕ Unternehmen zur Watchlist hinzufügen")
    with st.form("add_watchlist_form"):
        col1, col2, col3, col4 = st.columns([2, 1, 1, 4])
        with col1:
            wl_name = st.text_input("Name", key="wl_name")
        with col2:
            wl_ticker = st.text_input("Ticker", key="wl_ticker")
        with col3:
            wl_currency = st.selectbox("Währung", ["USD", "EUR", "CHF"], key="wl_currency")
        with col4:
            wl_comment = st.text_input("Kommentar", key="wl_comment")
        add_btn = st.form_submit_button("Zur Watchlist hinzufügen")
        if add_btn and wl_name and wl_ticker:
            new_row = {
                "Name": wl_name,
                "Ticker": wl_ticker,
                "Currency": wl_currency,
                "Comment": wl_comment
            }
            if hasattr(backend_sqlite, "add_to_watchlist"):
                backend_sqlite.add_to_watchlist(**new_row)
                st.success(f"{wl_name} wurde persistent zur Watchlist hinzugefügt!")
            else:
                st.warning("Persistente Speicherung der Watchlist ist nicht aktiviert (Funktion fehlt im Backend).")

    st.markdown("#### ➖ Unternehmen aus der Watchlist entfernen")
    with st.form("remove_watchlist_form"):
        remove_ticker = st.selectbox("Wähle ein Unternehmen zum Entfernen:", backend_sqlite.get_watchlist()["Ticker"].tolist(), key="remove_ticker")
        remove_btn = st.form_submit_button("Aus Watchlist entfernen")
        if remove_btn and remove_ticker:
            backend_sqlite.remove_from_watchlist(remove_ticker)
            st.success(f"{remove_ticker} wurde aus der Watchlist entfernt!")

    watchlist = show_watchlist()  # Watchlist nach dem Hinzufügen/Entfernen neu laden und anzeigen

    # --- Kursentwicklung ---
    st.markdown("---")
    st.markdown("### 📈 Kursentwicklung anzeigen")
    all_tickers = pd.concat([current_positions[["Name", "Ticker"]], watchlist[["Name", "Ticker"]]])
    selected_name = st.selectbox("Wähle eine Position aus dem Portfolio oder Watchlist:", all_tickers["Name"])
    ticker_values = all_tickers[all_tickers["Name"] == selected_name]["Ticker"].values
    selected_ticker = ticker_values[0] if len(ticker_values) > 0 else None

    # Zeitraum-Auswahl für Kursentwicklung
    duration_map = {
        "1 Tag": ("1d", "1m"),
        "1 Woche": ("1wk", "15m"),
        "1 Monat": ("1mo", "1d"),
        "6 Monate": ("6mo", "1d"),
        "1 Jahr": ("1y", "1d"),
        "5 Jahre": ("5y", "1d"),
        "10 Jahre": ("10y", "1wk"),
        "20 Jahre": ("20y", "1wk"),
        "Max": ("max", "1wk")
    }
    selected_duration = st.selectbox("Zeitraum für Kursentwicklung:", list(duration_map.keys()), index=5)
    period, interval = duration_map[selected_duration]

    if selected_ticker:
        @st.cache_data(ttl=3600)
        def get_history(ticker, period, interval):
            return yf.Ticker(ticker).history(period=period, interval=interval)

        hist = get_history(selected_ticker, period, interval)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=hist.index, y=hist["Close"], mode="lines", name="Kurs", line=dict(color="royalblue")))
        fig.update_layout(title=f"Kursentwicklung von {selected_ticker} ({selected_duration}, {interval})",
                          xaxis_title="Datum", yaxis_title="Kurs", height=500)
        st.plotly_chart(fig, use_container_width=True)
