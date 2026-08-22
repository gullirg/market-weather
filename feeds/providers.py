"""Feed providers. `local` reads the frozen CSVs in data/ and is the
tested offline mode. `live` refreshes the FRED and EIA series into the
same CSVs via free-key APIs, then everything downstream is identical.
Live calls are fixture-tested; first real run happens on the host with
keys in .env (FRED_API_KEY, EIA_API_KEY)."""

import os
import pandas as pd

FRED_SERIES = {"cpi_fred.csv": ("CPIAUCSL", "cpi", "m"),
               "core_cpi_fred.csv": ("CPILFESL", "core", "m"),
               "gs10_fred.csv": ("GS10", "gs10", "m"),
               "baa_yield.csv": ("BAA", "baa", "m"),
               "usd_broad.csv": ("TWEXBGSMTH", "usd", "m"),
               "ovx.csv": ("OVXCLS", "ovx", "d"),
               "hy_oas.csv": ("BAMLH0A0HYM2", "hy_oas", "d"),
               "ig_oas.csv": ("BAMLC0A0CM", "ig_oas", "d"),
               "claims.csv": ("ICSA", "claims", "d"),
               "mortgage.csv": ("MORTGAGE30US", "mortgage", "d"),
               "fed_bs.csv": ("WALCL", "fed_bs", "d"),
               "btc.csv": ("CBBTCUSD", "btc", "d"),
               "eu_equities.csv": ("SPASTT01EZM661N", "eu_equities", "m"),
               "yen.csv": ("EXJPUS", "yen", "m"),
               "yuan.csv": ("EXCHUS", "yuan", "m"),
               "sterling.csv": ("EXUSUK", "sterling", "m"),
               "em_dollar.csv": ("TWEXEMEGSMTH", "em_usd", "m"),
               "wei.csv": ("WEI", "wei", "d"),
               "houst.csv": ("HOUST", "houst", "m"),
               "m2.csv": ("M2SL", "m2", "m")}
EIA_SERIES = {"us_total_stocks_exspr.csv": "PET.MTESTUS1.M"}
FRED_URL = ("https://api.stlouisfed.org/fred/series/observations"
            "?series_id={sid}&api_key={key}&file_type=json")


def fred_json_to_series(payload, col, freq="m"):
    obs = payload["observations"]
    vals = [float(o["value"]) if o["value"] != "." else float("nan")
            for o in obs]
    if freq == "d":
        idx = pd.to_datetime([o["date"] for o in obs])
        s = pd.Series(vals, index=idx, name=col).dropna()
        return s.groupby(s.index.to_period("M")).mean().rename(col)
    idx = pd.PeriodIndex([o["date"][:7] for o in obs], freq="M")
    return pd.Series(vals, index=idx, name=col)


def fred_csv_to_series(text, col, freq="m"):
    """Parse the fredgraph.csv download shape into a monthly series.

    Two columns, `observation_date` and the FRED series id, with "."
    for a missing observation. Daily and weekly series are collapsed
    to monthly means, matching fred_json_to_series."""
    import io
    df = pd.read_csv(io.StringIO(text))
    df.columns = [c.strip() for c in df.columns]
    datec, valc = df.columns[0], df.columns[1]
    vals = pd.to_numeric(df[valc].astype(str).str.strip()
                         .replace(".", "nan"), errors="coerce")
    idx = pd.to_datetime(df[datec])
    s = pd.Series(vals.to_numpy(float), index=idx, name=col)
    if freq in ("d", "w"):
        s = s.dropna()
        return s.groupby(s.index.to_period("M")).mean().rename(col)
    s.index = idx.dt.to_period("M")
    return s.rename(col)


def jodi_csv_to_series(text, country="TOTAL", product="CRUDEOIL",
                       flow="TOTPROD"):
    """Parse a JODI world primary CSV extract into a monthly series."""
    import io
    df = pd.read_csv(io.StringIO(text))
    df.columns = [c.strip().upper() for c in df.columns]
    m = df[(df["REF_AREA"].str.upper() == country)
           & (df["ENERGY_PRODUCT"].str.upper() == product)
           & (df["FLOW_BREAKDOWN"].str.upper() == flow)]
    idx = pd.PeriodIndex(m["TIME_PERIOD"], freq="M")
    return pd.Series(pd.to_numeric(m["OBS_VALUE"], errors="coerce")
                     .to_numpy(), index=idx).sort_index()


def cot_csv_to_series(text):
    """Managed-money net length from a CFTC disaggregated futures CSV."""
    import io
    df = pd.read_csv(io.StringIO(text))
    df.columns = [c.strip() for c in df.columns]
    long_c = [c for c in df.columns if "M_Money_Positions_Long" in c][0]
    short_c = [c for c in df.columns if "M_Money_Positions_Short" in c][0]
    date_c = [c for c in df.columns if "Report_Date" in c][0]
    net = pd.to_numeric(df[long_c], errors="coerce") - pd.to_numeric(
        df[short_c], errors="coerce")
    idx = pd.to_datetime(df[date_c])
    s = pd.Series(net.to_numpy(), index=idx).sort_index()
    return s.groupby(s.index.to_period("M")).last()


def refresh(data_dir, source="local", session=None):
    """Returns list of (file, status). In local mode this is a no-op
    inventory; in live mode it rewrites the FRED CSVs."""
    out = []
    if source == "local":
        for f in sorted(os.listdir(data_dir)):
            out.append((f, "local"))
        return out
    import requests
    session = session or requests.Session()
    key = os.environ["FRED_API_KEY"]
    for fname, (sid, col, freq) in FRED_SERIES.items():
        r = session.get(FRED_URL.format(sid=sid, key=key), timeout=30)
        r.raise_for_status()
        s = fred_json_to_series(r.json(), col, freq)
        s.to_csv(os.path.join(data_dir, fname), header=[col])
        out.append((fname, f"fred:{sid}"))
    # EIA v2 and the futures-curve branch land here on the host; the
    # decision tree is in the build prompt and runbook.
    return out
