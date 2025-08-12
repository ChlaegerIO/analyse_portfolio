import numpy as np
import streamlit as st
import pandas as pd
import backend_sqlite
import yfinance as yf
import re

# --- Currency Conversion ---
@st.cache_data(ttl=300)
def get_current_fx_rates(fx_type):
    if fx_type == 'usd_chf':
        fx_rate = yf.Ticker("USDCHF=X").history(period="1d")["Close"].iloc[-1]
    elif fx_type == 'eur_chf':
        fx_rate = yf.Ticker("EURCHF=X").history(period="1d")["Close"].iloc[-1]
    return fx_rate

@st.cache_data(ttl=300)
def get_fx_rate(fx_type, date):
    """
    Get exchange rates
    Args: 
    - fx_type: [usd_chf, eur_chf]
    - date: the date for which to retrieve the exchange rate, 'yyy-mm-dd'
    """
    if fx_type == 'usd_chf':
        rx_rate = yf.Ticker("USDCHF=X").history(start=date, end=date, interval="1d")["Close"].iloc[0]
    elif fx_type == 'eur_chf':
        rx_rate = yf.Ticker("EURCHF=X").history(start=date, end=date, interval="1d")["Close"].iloc[0]
    return rx_rate


def get_current_positions():
    df = backend_sqlite.get_transactions()
    df = df[df["buy_sell"].isin(["BUY", "SELL"])].copy()
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0)
    df["price_per_unit"] = pd.to_numeric(df["price_per_unit"], errors="coerce").fillna(0)
    df["buy"] = pd.to_numeric(df["buy"], errors="coerce").fillna(0)
    df["sell"] = pd.to_numeric(df["sell"], errors="coerce").fillna(0)

    # Calculate quantity and average buying price (buy - sell)
    df["signed_quantity"] = df.apply(lambda row: row["quantity"] if row["buy_sell"] == "BUY" else -row["quantity"], axis=1)
    buy_df = df[df["buy_sell"] == "BUY"]
    avg_buy_price = buy_df.groupby("Ticker")["price_per_unit"].mean().reset_index().rename(columns={"price_per_unit": "Buy Price"})
    # Summe der Stückzahl
    df = df.drop(columns=["quantity"])
    positions = df.groupby("Ticker").agg({
        "signed_quantity": "sum"
    }).reset_index().rename(columns={"signed_quantity": "Quantity"})
    positions = positions.merge(avg_buy_price, on="Ticker", how="left")

    # Hole weitere Infos aus letzter Transaktion je Ticker
    info_cols = ["Ticker", "transaction_info", "currency"]
    latest_info = df.sort_values("date").groupby("Ticker").tail(1)[info_cols]
    positions = positions.merge(latest_info, on="Ticker", how="left")
    positions["Name"] = positions["transaction_info"]
    positions["Name"] = positions["Name"].str.replace(r'^.*x ', '', regex=True).str.rstrip('"')
    positions["Currency"] = positions["currency"]

    # Nur Positionen mit Bestand > 0
    positions = positions[positions["Quantity"] > 0].copy()
    positions = positions[["Name", "Ticker", "Currency", "Quantity", "Buy Price"]]
    kpis = positions["Ticker"].apply(fetch_kpis)
    positions = pd.concat([positions, kpis], axis=1)

    backend_sqlite.update_positions(positions)

    return positions

def set_current_positions(positions):
    """
    Set current positions in the backend.
    """
    backend_sqlite.set_positions(positions)

def get_total_up2_chf(periode):
    """
    Get total quantity and value in CHF for each Ticker at a specific up_date.
    """
    # get transactions and filter them
    up_date = pd.to_datetime("today") - pd.DateOffset(**periode)
    df = backend_sqlite.get_transactions()
    df["date"] = pd.to_datetime(df["date"])  # Ensure date column is datetime
    df = df[df["date"] <= up_date]

    # calculate total quantity per Ticker (buy, sell)
    total_quantity = df.groupby(["Ticker", "buy_sell"])["quantity"].sum().unstack(fill_value=0)
    total_quantity["Net"] = total_quantity.get("BUY", 0) - total_quantity.get("SELL", 0)

    print(f"Total quantity up to {up_date.strftime('%Y-%m-%d')}: {total_quantity}")

    # Get price for each ticker at up_date and convert to CHF if needed
    prices_chf = {}
    for ticker in total_quantity.index:
        # Get last close price at up_date
        try:
            price = yf.Ticker(ticker).history(start=up_date, end=up_date + pd.DateOffset(days=1), interval="1d")["Close"]
            price = price.iloc[0] if not price.empty else 0
        except Exception:
            price = 0

        # Get currency for ticker
        currency = df[df["Ticker"] == ticker]["currency"].iloc[-1] if not df[df["Ticker"] == ticker].empty else "CHF"
        if currency == "USD":
            fx = get_fx_rate("usd_chf", up_date.strftime("%Y-%m-%d"))
            price_chf = price * fx
        elif currency == "EUR":
            fx = get_fx_rate("eur_chf", up_date.strftime("%Y-%m-%d"))
            price_chf = price * fx
        else:
            price_chf = price
        prices_chf[ticker] = price_chf

    # Calculate total value in CHF
    total_value = total_quantity["Net"].copy()
    for ticker in total_value.index:
        total_value[ticker] = total_value[ticker] * prices_chf.get(ticker, 0)

    return total_quantity, total_value

def get_total_graph_chf(periode, interval):
    """
    Get total value for the graph period with interval
    """
    # get transactions and filter them
    total_start_quantity, total_value = get_total_up2_chf(periode)

    # graph list or pandas dataframe

@st.cache_data(ttl=300)
def fetch_kpis(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        price = stock.history(period="1d")["Close"].iloc[-1]
        return pd.Series({
            "Current Price": price,
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