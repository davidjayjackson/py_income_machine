"""
grab_income_stock_data.py
Python port of grab_income_stock_data.R

Downloads daily prices and dividend history for income ETFs from Yahoo
Finance and writes them to the MariaDB `investpy` database.

Requires:
    pip install yfinance pandas sqlalchemy pymysql matplotlib seaborn
"""

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
import yfinance as yf
from sqlalchemy import create_engine, inspect, text

# -----------------------------
# 1) Database connection
# -----------------------------
DB_USER = "root"
DB_PASS = "Bjmj3265"
DB_HOST = "localhost"
DB_PORT = 3333
DB_NAME = "investpy"

engine = create_engine(
    f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

symbols = ["JEPI", "QYLD", "SCHD", "JEPQ"]
START = "2000-01-01"


# -----------------------------
# 2) Helpers (equivalents of tq_get)
# -----------------------------
def get_stock_prices(symbols, start):
    """Like tq_get(get = "stock.prices"): symbol, date, open, high, low,
    close, volume, adjusted."""
    frames = []
    for sym in symbols:
        df = yf.Ticker(sym).history(start=start, auto_adjust=False, actions=False)
        if df.empty:
            print(f"Warning: no price data for {sym}")
            continue
        df = df.reset_index().rename(
            columns={
                "Date": "date",
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
                "Adj Close": "adjusted",
            }
        )
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None).dt.date
        df.insert(0, "symbol", sym)
        frames.append(df[["symbol", "date", "open", "high", "low",
                          "close", "volume", "adjusted"]])
    return pd.concat(frames, ignore_index=True)


def get_dividends(symbols, start):
    """Like tq_get(get = "dividends"): symbol, date, value."""
    frames = []
    for sym in symbols:
        s = yf.Ticker(sym).dividends
        if s.empty:
            print(f"Warning: no dividend data for {sym}")
            continue
        df = s.reset_index()
        df.columns = ["date", "value"]
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None).dt.date
        df.insert(0, "symbol", sym)
        frames.append(df)
    div = pd.concat(frames, ignore_index=True)
    return div[div["date"] >= pd.to_datetime(start).date()]


# -----------------------------
# 3) Stock prices -> `stocks` table
# -----------------------------
stocks = get_stock_prices(symbols, START)
stocks.to_sql("stocks", engine, if_exists="replace", index=False)

insp = inspect(engine)
print(insp.get_table_names())
print([c["name"] for c in insp.get_columns("stocks")])

with engine.connect() as conn:
    print(conn.execute(text("SELECT min(date), max(date) FROM stocks")).fetchall())

# -----------------------------
# 4) Get dividend history
#    Use the last 12 months to estimate annual dividends/share
# -----------------------------
div_tbl = get_dividends(symbols, START)
div_tbl["date"] = pd.to_datetime(div_tbl["date"])
last_date = div_tbl["date"].max()

annual_div_tbl = (
    div_tbl.dropna(subset=["value"])
    .loc[lambda d: d["date"] > last_date - pd.DateOffset(months=12)]
    .groupby("symbol", as_index=False)["value"]
    .sum()
    .rename(columns={"value": "annual_dividend_per_share"})
)
print(annual_div_tbl)

div_tbl.to_sql("dividends", engine, if_exists="replace", index=False)

insp = inspect(engine)
print(insp.get_table_names())
print([c["name"] for c in insp.get_columns("dividends")])

with engine.connect() as conn:
    print(conn.execute(text("SELECT min(date), max(date) FROM dividends")).fetchall())

# -----------------------------
# 5) Plot dividends (facet by symbol)
# -----------------------------
g = sns.FacetGrid(div_tbl, col="symbol", col_wrap=2, sharex=False,
                  sharey=False, height=3, aspect=1.6)
g.map_dataframe(lambda data, **kw: plt.bar(data["date"], data["value"],
                                           width=20, **kw))
g.set_axis_labels("date", "value")
for ax in g.axes.flat:
    ax.tick_params(axis="x", rotation=45)
plt.tight_layout()
plt.show()
