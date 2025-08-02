import numpy as np
import pandas as pd
import backend_sqlite

def get_current_positions():
    df = backend_sqlite.get_transactions()
    df = df[df["buy_sell"].isin(["BUY", "SELL"])].copy()
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0)
    df["price_per_unit"] = pd.to_numeric(df["price_per_unit"], errors="coerce").fillna(0)
    df["buy"] = pd.to_numeric(df["buy"], errors="coerce").fillna(0)
    df["sell"] = pd.to_numeric(df["sell"], errors="coerce").fillna(0)

    # Stückzahl berechnen
    df["signed_quantity"] = df.apply(lambda row: row["quantity"] if row["buy_sell"] == "BUY" else -row["quantity"], axis=1)
    # Durchschnittlicher Kaufpreis (nur BUY)
    buy_df = df[df["buy_sell"] == "BUY"]
    avg_buy_price = buy_df.groupby("Ticker")["price_per_unit"].mean().reset_index().rename(columns={"price_per_unit": "Buy Price"})
    # Summe der Stückzahl
    positions = df.groupby("Ticker").agg({
        "signed_quantity": "sum"
    }).reset_index().rename(columns={"signed_quantity": "Units"})
    positions = positions.merge(avg_buy_price, on="Ticker", how="left")

    # Hole weitere Infos aus letzter Transaktion je Ticker
    info_cols = ["Ticker", "transaction_info", "buy_currency", "Type"]
    latest_info = df.sort_values("date").groupby("Ticker").tail(1)[info_cols]
    positions = positions.merge(latest_info, on="Ticker", how="left")
    positions["Name"] = positions["transaction_info"]
    positions["Currency"] = positions["buy_currency"]
    positions["Type"] = positions["Type"].fillna("Stock")

    # Nur Positionen mit Bestand > 0
    positions = positions[positions["Units"] > 0].copy()
    positions = positions[["Type", "Name", "Ticker", "Currency", "Units", "Buy Price"]]
    return positions

