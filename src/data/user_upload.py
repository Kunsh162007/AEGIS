"""Turn USER-UPLOADED transaction data into AEGIS cases.

This is the bring-your-own-data path: someone uploads a ledger export and AEGIS
investigates the most active accounts in it (or one account they name). Data is
parsed in memory only — nothing is written to disk.

Supported formats (detected from the filename):
  .csv          — comma/semicolon-separated text
  .xlsx / .xls  — Excel (first sheet, or the first sheet that has the columns)
  .json         — an array of transaction objects
  .pdf          — best effort: text-based tables (e.g. exported statements) are
                  extracted with pdfplumber; scanned/image PDFs can't be read.

Column names are detected flexibly so common exports work as-is:

  source account : src | from | from_account | origin | nameOrig | sender | source | debit_account | payer
  dest account   : dst | to | to_account | dest | nameDest | receiver | beneficiary | destination | credit_account | payee
  amount         : amount | amt | value | sum | transaction_amount
  timestamp (opt): timestamp | date | time | datetime | transaction_date
  channel  (opt) : channel | type | transaction_type   (cash/transfer/card/wire; PaySim names mapped)

Only src/dst/amount are required. There is no label column — this is real
inference, not the benchmark path.
"""
from __future__ import annotations

import io
from collections import defaultdict
from datetime import datetime, timedelta

from .public_loader import _MAX_TXNS_PER_CASE, _PAYSIM_CHANNEL, _derive_alert_type
from .schema import Case, Party, Transaction

_SRC_COLS = ("src", "from", "from_account", "origin", "nameorig", "sender", "source",
             "debit_account", "payer")
_DST_COLS = ("dst", "to", "to_account", "dest", "namedest", "receiver", "beneficiary",
             "destination", "credit_account", "payee")
_AMT_COLS = ("amount", "amt", "value", "sum", "transaction_amount")
_TS_COLS = ("timestamp", "date", "time", "datetime", "transaction_date")
_CHANNEL_COLS = ("channel", "type", "transaction_type")
_OUR_CHANNELS = {"cash", "transfer", "card", "wire"}

_MAX_ROWS = 200_000


def _pick(columns: dict[str, str], wanted: tuple[str, ...]) -> str | None:
    return next((columns[w] for w in wanted if w in columns), None)


def _channel(raw: str) -> str:
    raw = str(raw).strip()
    low = raw.lower()
    if low in _OUR_CHANNELS:
        return low
    return _PAYSIM_CHANNEL.get(raw.upper(), "transfer")


def _norm_cols(df) -> dict[str, str]:
    return {str(c).strip().lower().replace(" ", "_"): c for c in df.columns}


def _has_required(df) -> bool:
    cols = _norm_cols(df)
    return all(_pick(cols, group) for group in (_SRC_COLS, _DST_COLS, _AMT_COLS))


def _missing_columns_error(df) -> ValueError:
    cols = _norm_cols(df)
    missing = [name for name, group in
               (("source account", _SRC_COLS), ("destination account", _DST_COLS),
                ("amount", _AMT_COLS)) if _pick(cols, group) is None]
    return ValueError(
        f"Data is missing required column(s): {', '.join(missing)}. "
        f"Expected headers like src/from/nameOrig, dst/to/nameDest, amount. "
        f"Found: {', '.join(str(c) for c in df.columns)}")


# ── format readers: bytes -> DataFrame ──────────────────────────────────────

def _read_csv(data: bytes):
    import pandas as pd
    df = pd.read_csv(io.BytesIO(data), nrows=_MAX_ROWS, sep=None, engine="python")
    return df


def _read_excel(data: bytes):
    import pandas as pd
    # Try every sheet; use the first one that has the required columns.
    sheets = pd.read_excel(io.BytesIO(data), sheet_name=None, nrows=_MAX_ROWS)
    for df in sheets.values():
        if _has_required(df):
            return df
    # None matched — surface the columns of the first sheet in the error.
    return next(iter(sheets.values()))


def _read_json(data: bytes):
    import pandas as pd
    df = pd.read_json(io.BytesIO(data))
    return df.head(_MAX_ROWS)


def _read_pdf(data: bytes):
    """Best effort for TEXT-BASED statement PDFs: extract tables and use the
    first one whose header row matches. Scanned PDFs (images) can't be read."""
    import pandas as pd
    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover
        raise ValueError("PDF support not installed on this server "
                         "(pip install pdfplumber).") from exc

    frames = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages[:50]:
            for table in page.extract_tables():
                if not table or len(table) < 2:
                    continue
                header = [str(h or "").strip() for h in table[0]]
                df = pd.DataFrame(table[1:], columns=header)
                if _has_required(df):
                    frames.append(df)
    if not frames:
        raise ValueError(
            "Couldn't find a transaction table in this PDF. PDF support is "
            "best-effort and needs a text-based table with source/destination/"
            "amount columns — scanned statements can't be read. Please export "
            "CSV or Excel instead.")
    return pd.concat(frames, ignore_index=True).head(_MAX_ROWS)


_READERS = {"csv": _read_csv, "txt": _read_csv, "xlsx": _read_excel,
            "xls": _read_excel, "json": _read_json, "pdf": _read_pdf}


def _edges_from_df(df) -> list[dict]:
    """DataFrame -> normalised money-flow edges {src,dst,amount,ts,step,channel}."""
    import pandas as pd

    if not _has_required(df):
        raise _missing_columns_error(df)
    cols = _norm_cols(df)
    src_col, dst_col = _pick(cols, _SRC_COLS), _pick(cols, _DST_COLS)
    amt_col = _pick(cols, _AMT_COLS)

    ts_col = _pick(cols, _TS_COLS)
    ts = None
    if ts_col:
        ts = pd.to_datetime(df[ts_col], errors="coerce", utc=False)
        if ts.isna().all():
            ts = None
    channel_col = _pick(cols, _CHANNEL_COLS)
    step_col = cols.get("step")

    edges: list[dict] = []
    for i, r in enumerate(df.itertuples(index=False)):
        row = dict(zip(df.columns, r))
        try:
            # tolerate "1,234.56", "$1234", etc.
            amount = float(str(row[amt_col]).replace(",", "").replace("$", "").strip())
        except (TypeError, ValueError):
            continue  # skip malformed rows rather than failing the upload
        edges.append({
            "src": str(row[src_col]).strip(), "dst": str(row[dst_col]).strip(),
            "amount": amount,
            "ts": (ts.iloc[i].to_pydatetime() if ts is not None and pd.notna(ts.iloc[i])
                   else None),
            "step": int(row[step_col]) if step_col and pd.notna(row[step_col]) else i,
            "channel": _channel(row[channel_col]) if channel_col else "transfer",
        })
    if not edges:
        raise ValueError("No parsable transaction rows found in the file.")
    return edges


def parse_upload(data: bytes, filename: str = "upload.csv") -> list[dict]:
    """Uploaded bytes (any supported format) -> normalised money-flow edges."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "csv"
    reader = _READERS.get(ext)
    if reader is None:
        raise ValueError(f"Unsupported file type '.{ext}'. "
                         f"Supported: {', '.join(sorted(_READERS))}.")
    try:
        df = reader(data)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Couldn't read this .{ext} file: {exc}") from exc
    return _edges_from_df(df)


def parse_csv(data: bytes) -> list[dict]:
    """Back-compat shim for CSV bytes."""
    return parse_upload(data, "upload.csv")


def _build_case(account: str, ins: list[dict], outs: list[dict]) -> Case:
    rel = sorted(ins + outs, key=lambda e: e["step"])[:_MAX_TXNS_PER_CASE]
    t0 = datetime(2026, 1, 1)
    txns = [Transaction(
        txn_id=f"upload-{account}-{j}",
        timestamp=e["ts"] or (t0 + timedelta(hours=float(e["step"]) % 168)),
        src_account=e["src"], dst_account=e["dst"], amount=e["amount"],
        channel=e["channel"], note=e["channel"]) for j, e in enumerate(rel)]

    accounts = {account} | {e["src"] for e in rel} | {e["dst"] for e in rel}
    in_amt = sum(e["amount"] for e in ins)
    parties = [Party(account=a, name=f"acct-{a}",
                     expected_monthly_volume=round(max(in_amt, 1.0)) if a == account else 0.0)
               for a in sorted(accounts)]

    return Case(case_id=f"UPLOAD-{account}",
                alert_type=_derive_alert_type(account, ins, outs),
                focus_account=account, parties=parties, transactions=txns)


def cases_from_upload(data: bytes, filename: str = "upload.csv",
                      focus: str | None = None, limit: int = 5) -> list[Case]:
    """Build investigation cases from an uploaded file: one per focus account.
    `focus` names a single account to investigate; otherwise the `limit` most
    active accounts are investigated."""
    edges = parse_upload(data, filename)

    inbound: dict[str, list[dict]] = defaultdict(list)
    outbound: dict[str, list[dict]] = defaultdict(list)
    for e in edges:
        inbound[e["dst"]].append(e)
        outbound[e["src"]].append(e)
    accounts = set(inbound) | set(outbound)

    if focus:
        focus = focus.strip()
        if focus not in accounts:
            raise ValueError(f"Account '{focus}' does not appear in the uploaded data.")
        selected = [focus]
    else:
        selected = sorted(
            accounts,
            key=lambda a: len(inbound.get(a, [])) + len(outbound.get(a, [])),
            reverse=True)[:max(1, min(limit, 20))]

    return [_build_case(a, inbound.get(a, []), outbound.get(a, [])) for a in selected]


def cases_from_csv(data: bytes, focus: str | None = None, limit: int = 5) -> list[Case]:
    """Back-compat shim for CSV bytes."""
    return cases_from_upload(data, "upload.csv", focus, limit)
