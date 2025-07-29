import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
import backend_sqlite  # Importiere das Backend-Modul

# Page config
st.set_page_config(page_title="Portfolio Dashboard", layout="wide")
st.title("📊 Live Portfolio Dashboard")

# --- Input Data ---
portfolio = pd.DataFrame({
    "Type": ["Stock", "ETF", "ETF", "Stock"],
    "Name": ["Palantir Technologies", "iShares Automation & Robotics", "iShares Core MSCI World", "Georg Fischer AG"],
    "Ticker": ["PLTR", "RBOT.SW", "IWRD.SW", "FI-N.SW"],
    "Currency": ["USD", "USD", "USD", "CHF"],
    "Units": [2, 10, 1, round(200 / 59.65, 3)],
    "Buy Price": [88.50, 12.26, 101.30, 59.65]
    })

cash = 162.07
total_deposit = 500.00
total_invested = total_deposit - cash

# --- Currency Conversion ---
@st.cache_data(ttl=300)
def get_fx_rates():
    usd_chf = yf.Ticker("USDCHF=X").history(period="1d")["Close"].iloc[-1]
    return usd_chf

usd_chf = get_fx_rates()

# --- KPI Fetch ---
@st.cache_data(ttl=300)
def fetch_kpis(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        price = stock.history(period="1d")["Close"].iloc[-1]
        return pd.Series({
            "Raw Price": price,
            "EPS": info.get("trailingEps"),
            "PE Ratio": info.get("trailingPE"),
            "Market Cap": info.get("marketCap"),
            "PEG Ratio": info.get("pegRatio"),
            "Beta": info.get("beta"),
            "Free Cash Flow": info.get("freeCashflow"),
            "Revenue Growth YoY (%)": info.get("revenueGrowth") * 100 if info.get("revenueGrowth") else None
        })
    except:
        return pd.Series({col: None for col in ["Raw Price", "EPS", "PE Ratio", "Market Cap", "PEG Ratio", "Beta", "Free Cash Flow", "Revenue Growth YoY (%)"]})

kpis = portfolio["Ticker"].apply(fetch_kpis)
portfolio = pd.concat([portfolio, kpis], axis=1)

# --- Preis & Kennzahlen ---
portfolio["Current Price"] = portfolio["Raw Price"]

def convert_to_chf(row):
    if row["Currency"] == "USD":
        return row["Current Price"] * usd_chf
    elif row["Currency"] == "CHF":
        return row["Current Price"]
    return None

portfolio["Value (CHF)"] = portfolio.apply(lambda row: convert_to_chf(row) * row["Units"], axis=1)
portfolio["Profit/Loss"] = (portfolio["Current Price"] - portfolio["Buy Price"]) * portfolio["Units"]
portfolio["Profit/Loss (%)"] = ((portfolio["Current Price"] - portfolio["Buy Price"]) / portfolio["Buy Price"]) * 100

# --- Rundung ---
round_cols = ["Buy Price", "Current Price", "Value (CHF)", "Profit/Loss", "Profit/Loss (%)", "EPS", "PE Ratio",
              "PEG Ratio", "Beta", "Free Cash Flow", "Revenue Growth YoY (%)"]
portfolio[round_cols] = portfolio[round_cols].round(3)

# --- Portfolio Summary ---
total_value_chf = portfolio["Value (CHF)"].sum() + cash
growth_pct = ((total_value_chf - total_deposit) / total_deposit) * 100

st.markdown("### 💰 Portfolio Summary")
col1, col2, col3, col4 = st.columns([1.2, 1, 0.5, 1])
with col1:
    st.metric("Total Deposit", f"{total_deposit:.3f} CHF")
    st.markdown(f"<div style='margin-top: -15px; font-size: 0.9em;'>• Invested: {total_invested:.2f} CHF<br>• Cash: {cash:.2f} CHF</div>", unsafe_allow_html=True)
with col2:
    st.metric("Total Value Portfolio", f"{total_value_chf:.3f} CHF")
with col4:
    st.metric("Value Development", f"{growth_pct:.2f} %")

# --- Positionen aufteilen ---
stocks_df = portfolio[portfolio["Type"] == "Stock"]
etfs_df = portfolio[portfolio["Type"] == "ETF"]

# Spaltenanordnung
cols_order = ["Type", "Name", "Ticker", "Currency", "Units", "Buy Price", "Current Price", "Value (CHF)",
              "Profit/Loss", "Profit/Loss (%)", "EPS", "PE Ratio", "Market Cap", "PEG Ratio", "Beta",
              "Free Cash Flow", "Revenue Growth YoY (%)"]

st.markdown("### 📌 Current Positions – Stocks")
st.dataframe(stocks_df[cols_order], use_container_width=True)

st.markdown("### 📌 Current Positions – ETFs")
st.dataframe(etfs_df[cols_order], use_container_width=True)


# --- Watchlist aus Datenbank laden ---
def show_watchlist():
    watchlist = backend_sqlite.get_watchlist()
    st.markdown("### 👀 Watchlist – Stocks")
    st.dataframe(watchlist[watchlist["Type"] == "Stock"], use_container_width=True)
    st.markdown("### 👀 Watchlist – ETFs")
    st.dataframe(watchlist[watchlist["Type"] == "ETF"], use_container_width=True)
    return watchlist

# --- Watchlist hinzufügen, entfernen und anzeigen ---
st.markdown("#### ➕ Unternehmen zur Watchlist hinzufügen")
with st.form("add_watchlist_form"):
    col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 1, 3])
    with col1:
        wl_name = st.text_input("Name", key="wl_name")
    with col2:
        wl_ticker = st.text_input("Ticker", key="wl_ticker")
    with col3:
        wl_currency = st.selectbox("Währung", ["USD", "EUR", "CHF"], key="wl_currency")
    with col4:
        wl_type = st.selectbox("Typ", ["Stock", "ETF"], key="wl_type")
    with col5:
        wl_comment = st.text_input("Kommentar", key="wl_comment")
    add_btn = st.form_submit_button("Zur Watchlist hinzufügen")
    if add_btn and wl_name and wl_ticker:
        new_row = {
            "Name": wl_name,
            "Ticker": wl_ticker,
            "Currency": wl_currency,
            "Comment": wl_comment,
            "Type": wl_type
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


watchlist = show_watchlist()  # Watchlist nach dem Hinzufügen neu laden und anzeigen

# --- Performance Graph
st.markdown("---")
st.markdown("### 📊 Performance Graph")

# --- Kursentwicklung
st.markdown("---")
st.markdown("### 📈 Kursentwicklung anzeigen")
all_tickers = pd.concat([portfolio[["Name", "Ticker"]], watchlist[["Name", "Ticker"]]])
selected_name = st.selectbox("Wähle eine Position aus dem Portfolio oder Watchlist:", all_tickers["Name"])
selected_ticker = all_tickers[all_tickers["Name"] == selected_name]["Ticker"].values[0]

@st.cache_data(ttl=3600)
def get_history(ticker):
    return yf.Ticker(ticker).history(period="5y", interval="1d")

hist = get_history(selected_ticker)
fig = go.Figure()
fig.add_trace(go.Scatter(x=hist.index, y=hist["Close"], mode="lines", name="Kurs", line=dict(color="royalblue")))
fig.update_layout(title=f"Kursentwicklung von {selected_ticker} (5 Jahre, täglich)",
                  xaxis_title="Datum", yaxis_title="Kurs", height=500)
st.plotly_chart(fig, use_container_width=True)

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
