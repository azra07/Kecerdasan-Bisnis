"""
Tahap 2 - Ingestion ke Data Lake (raw zone) dan skema raw PostgreSQL.

Alur per sumber:
  sumber (Excel + CSV) -> salin apa adanya ke datalake/raw/<tanggal>/ -> muat ke tabel raw.* (semua kolom teks)

Fitur: retry 3x dengan backoff, log ke etl_pipeline.log, status sukses/gagal per sumber.
Jalankan dari root repo:  python etl/extract.py
"""
import os
import re
import sys
import time
import shutil
import logging
import functools
from datetime import datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "data" / "raw"                      # tempat file asli (tidak masuk GitHub)
BATCH = datetime.now().strftime("%Y%m%d_%H%M%S")      # id batch = lineage
LAKE_DIR = ROOT / "datalake" / "raw" / datetime.now().strftime("%Y-%m-%d")
RAW_SCHEMA = os.getenv("RAW_SCHEMA", "raw")
if RAW_SCHEMA.lower() == "none":
    RAW_SCHEMA = None  # hanya dipakai untuk uji lokal tanpa PostgreSQL

# semua file .xlsx di data/raw/ otomatis diproses (nama file bebas), kecuali file sementara Excel (~$...)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.FileHandler(ROOT / "etl_pipeline.log", encoding="utf-8"),
              logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("extract")


def get_engine():
    url = os.getenv("DATABASE_URL")
    if not url:
        url = "postgresql+psycopg2://{u}:{p}@{h}:{port}/{d}".format(
            u=os.environ["POSTGRES_USER"], p=os.environ["POSTGRES_PASSWORD"],
            h=os.getenv("DB_HOST_LOCAL", "localhost"),
            port=os.getenv("POSTGRES_PORT", "5432"), d=os.environ["POSTGRES_DB"])
    return create_engine(url)


def retry(times=3, base_delay=2):
    """Ulangi fungsi bila gagal, jeda bertambah (2s, 4s, 8s)."""
    def deco(fn):
        @functools.wraps(fn)
        def wrap(*a, **k):
            for i in range(1, times + 1):
                try:
                    return fn(*a, **k)
                except Exception as e:
                    log.warning("%s gagal percobaan %d/%d: %s", fn.__name__, i, times, e)
                    if i == times:
                        raise
                    time.sleep(base_delay * 2 ** (i - 1))
        return wrap
    return deco


def clean_name(text):
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def to_raw_table(df, table, engine, source):
    """Muat apa adanya (semua teks) + kolom lineage."""
    df = df.astype(str)
    df["_source_file"] = source
    df["_batch_id"] = BATCH
    df["_ingested_at"] = datetime.now().isoformat(timespec="seconds")
    df.to_sql(table, engine, schema=RAW_SCHEMA, if_exists="append", index=False)
    return len(df)


@retry()
def ingest_excel(name, engine):
    src = SRC_DIR / name
    if not src.exists():
        raise FileNotFoundError(f"{src} tidak ditemukan")
    shutil.copy2(src, LAKE_DIR / f"{src.stem}_{BATCH}{src.suffix}")   # salinan mentah di data lake
    total = 0
    for sheet, df in pd.read_excel(src, sheet_name=None, dtype=str).items():
        df.columns = [clean_name(str(c)) or f"kolom_{i}" for i, c in enumerate(df.columns)]
        table = f"{clean_name(src.stem)}__{clean_name(sheet)}"
        n = to_raw_table(df, table, engine, src.name)
        log.info("  %s | sheet '%s' -> %s.%s : %d baris", name, sheet, RAW_SCHEMA, table, n)
        total += n
    return total


@retry()
def ingest_csv(name, engine):
    """CSV eksternal (hasil pengambilan API/scraping: libur, cuaca, kalender, wilayah, dll)."""
    src = SRC_DIR / name
    if not src.exists():
        raise FileNotFoundError(f"{src} tidak ditemukan")
    shutil.copy2(src, LAKE_DIR / f"{src.stem}_{BATCH}{src.suffix}")
    df = pd.read_csv(src, dtype=str, encoding="utf-8-sig")
    df.columns = [clean_name(str(c)) or f"kolom_{i}" for i, c in enumerate(df.columns)]
    n = to_raw_table(df, clean_name(src.stem), engine, src.name)
    log.info("  %s -> %s.%s : %d baris", name, RAW_SCHEMA, clean_name(src.stem), n)
    return n


def main():
    LAKE_DIR.mkdir(parents=True, exist_ok=True)
    engine = get_engine()
    log.info("=== MULAI INGESTION batch %s ===", BATCH)
    excel_files = sorted(p.name for p in SRC_DIR.glob("*.xlsx") if not p.name.startswith("~$"))
    if not excel_files:
        log.error("Tidak ada file .xlsx di %s", SRC_DIR)
    jobs = [(n, lambda n=n: ingest_excel(n, engine)) for n in excel_files]
    csv_files = sorted(p.name for p in SRC_DIR.glob("*.csv"))
    jobs += [(n, lambda n=n: ingest_csv(n, engine)) for n in csv_files]

    status = {}
    for name, job in jobs:
        try:
            n = job()
            status[name] = ("SUKSES", n)
            log.info("[SUKSES] %s : %d baris", name, n)
        except Exception as e:                      # satu sumber gagal tidak menghentikan yang lain
            status[name] = ("GAGAL", str(e))
            log.error("[GAGAL] %s : %s", name, e)

    log.info("=== RINGKASAN batch %s ===", BATCH)
    for k, (s, d) in status.items():
        log.info("%-32s %-7s %s", k, s, d)
    failed = [k for k, (s, _) in status.items() if s == "GAGAL"]
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
