"""Fetch one FRED series through the public fredgraph.csv endpoint and
write it in the data/ house format: a YYYY-MM period index with an empty
index name, and one named value column.

  python3 scripts/fetch_fred_csv.py SERIES_ID column out.csv [m|w|d]

Weekly and daily series are collapsed to monthly means by
feeds.providers.fred_csv_to_series, which is fixture-tested.
"""

import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from feeds.providers import fred_csv_to_series

URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"


def main(sid, col, out, freq="m"):
    r = requests.get(URL.format(sid=sid), timeout=60,
                     headers={"User-Agent": "market-weather/1.0"})
    r.raise_for_status()
    s = fred_csv_to_series(r.text, col, freq)
    s = s.sort_index()
    s.to_csv(out, header=[col], index_label="")
    print(f"{sid} -> {out}: {len(s)} rows, "
          f"{s.index[0]}..{s.index[-1]}, "
          f"last={s.dropna().iloc[-1] if s.notna().any() else 'nan'}")


if __name__ == "__main__":
    main(*sys.argv[1:])
