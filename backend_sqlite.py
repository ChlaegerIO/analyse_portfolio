from sqlalchemy import create_engine, text
import pandas as pd
from pathlib import Path

DB_PORTFOLIO_URL = "sqlite:///portfolio.db"
engine_portfolio = create_engine(DB_PORTFOLIO_URL)
DB_WATCHLIST_URL = "sqlite:///watchlist.db"
engine_watchlist = create_engine(DB_WATCHLIST_URL)

def insert_transactions(df: pd.DataFrame):
    df.to_sql("transactions", engine_portfolio, if_exists="append", index=False)

def get_transactions(engine=engine_portfolio) -> pd.DataFrame:
    try:
        return pd.read_sql("SELECT * FROM transactions", engine)
    except Exception as e:
        print(f"Fehler beim Laden der Transaktionen: {e}")
        # Return empty DataFrame with expected columns
        return pd.DataFrame(columns=[
            "date", "transaction_type", "transaction_info", "buy", "buy_currency",
            "sell", "sell_currency", "fees", "buy_sell", "quantity", "Ticker", "price_per_unit", "platform", "currency"
        ])

def update_positions(df: pd.DataFrame):
    """
    Update the current positions in the backend.
    """
    # Remove duplicate columns before writing to SQL
    df = df.loc[:, ~df.columns.duplicated()]
    df.to_sql("current_positions", engine_portfolio, if_exists="replace", index=False)

def get_current_positions(engine=engine_portfolio) -> pd.DataFrame:
    return pd.read_sql("SELECT * FROM current_positions", engine)

def get_watchlist(engine=engine_watchlist) -> pd.DataFrame:
    try:
        return pd.read_sql("SELECT * FROM watchlist", engine)
    except Exception as e:
        print(f"Fehler beim Laden der Watchlist: {e}")
        return pd.DataFrame(columns=["Name", "Ticker", "Currency", "Comment"])

def add_to_watchlist(Name, Ticker, Currency, Comment, engine=engine_watchlist):
    df = pd.DataFrame([{
        "Name": Name,
        "Ticker": Ticker,
        "Currency": Currency,
        "Comment": Comment
    }])
    df.to_sql("watchlist", engine, if_exists="append", index=False)

def remove_from_watchlist(Ticker):
    with engine_watchlist.begin() as conn:
        query = text("DELETE FROM watchlist WHERE Ticker = :ticker")
        conn.execute(query, {"ticker": Ticker})
    print(f"Removed {Ticker} from watchlist")

def read_yuh_csv(file) -> pd.DataFrame:
    """
    Read a yuh csv file and create a pandas dataframe
    """
    try:
        df = pd.read_csv(file, sep=';', engine='python', on_bad_lines='skip')
    except Exception as e:
        print(f"Fehler beim Einlesen der CSV: {e}")
        return pd.DataFrame({"Fehler": [str(e)]})

    required_cols = ["DATE", "ACTIVITY TYPE", "ACTIVITY NAME", "DEBIT", "DEBIT CURRENCY", "CREDIT", "CREDIT CURRENCY", "FEES/COMMISSION", "BUY/SELL", "QUANTITY", "ASSET", "PRICE PER UNIT"]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        error_msg = f"Fehlende Spalten in der CSV: {missing_cols}"
        print(error_msg)
        return pd.DataFrame({"Fehler": [error_msg], "Gefundene Spalten": [str(list(df.columns))]})

    # Read existing transactions from the database
    try:
        existing = get_transactions()
    except Exception:
        existing = pd.DataFrame()

    # only use specific types and columns
    df = df[df['ACTIVITY TYPE'].isin(['INVEST_ORDER_EXECUTED', 'CASH_TRANSACTION_RELATED_OTHER'])]
    
    df = df[["DATE", "ACTIVITY TYPE", "ACTIVITY NAME", "DEBIT", "DEBIT CURRENCY", "CREDIT", "CREDIT CURRENCY", "FEES/COMMISSION", "BUY/SELL", "QUANTITY", "ASSET", "PRICE PER UNIT"]]
    column_map = {
        "DATE": "date",
        "ACTIVITY TYPE": "transaction_type",
        "ACTIVITY NAME": "transaction_info",
        "DEBIT": "buy",     # buy stocks, -xxx from bank account view
        "DEBIT CURRENCY": "buy_currency",
        "CREDIT": "sell",
        "CREDIT CURRENCY": "sell_currency",
        "FEES/COMMISSION": "fees",
        "BUY/SELL": "buy_sell",
        "QUANTITY": "quantity",
        "ASSET": "Ticker",
        "PRICE PER UNIT": "price_per_unit"
    }
    df.rename(columns=column_map, inplace=True)
    df["platform"] = "Yuh"

    # merge buy_currency and sell_currency and take the one that is not NULL, then remove the original columns
    df["currency"] = df["buy_currency"].combine_first(df["sell_currency"])
    df.drop(columns=["buy_currency", "sell_currency"], inplace=True)

    # If the table is empty, insert all
    if existing.empty:
        insert_transactions(df)
        print(f"Inserted {len(df)} new transactions from Yuh CSV")
        print(f"df", df)
        return df

    # Find new transactions (rows not in existing)
    # Assumes all columns must match for a transaction to be considered duplicate
    merged = df.merge(existing.drop_duplicates(), how='left', indicator=True)
    new_rows = merged[merged['_merge'] == 'left_only'].drop('_merge', axis=1)

    if not new_rows.empty:
        insert_transactions(new_rows)
        print(f"Merged {len(new_rows)} new transactions from Yuh CSV")
        print(f"new_rows", new_rows)
    return new_rows

def update_current_price(ticker, price):
    """
    Update the current price for a given ticker in the current_positions table.
    """
    import sqlite3
    conn = sqlite3.connect("portfolio.db")
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE current_positions SET [Current Price]=? WHERE Ticker=?",
        (price, ticker)
    )
    conn.commit()
    conn.close()