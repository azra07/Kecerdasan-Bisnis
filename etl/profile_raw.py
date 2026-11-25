"""
Profil data di skema raw: jumlah baris, kolom kosong, duplikat, nilai unik, contoh nilai.
Kolom sensitif (nama, alamat, NIK/SIM) TIDAK ditampilkan nilainya.
Jalankan dari root repo:  python etl/profile_raw.py > profil_raw.txt
"""
import os
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect

load_dotenv()
url = "postgresql+psycopg2://{u}:{p}@{h}:{port}/{d}".format(
    u=os.environ["POSTGRES_USER"], p=os.environ["POSTGRES_PASSWORD"],
    h=os.getenv("DB_HOST_LOCAL", "localhost"),
    port=os.getenv("POSTGRES_PORT", "5432"), d=os.environ["POSTGRES_DB"])
eng = create_engine(url)

SENSITIF = ("nama", "alamat", "nip", "sim", "nik")
META = ("_source_file", "_batch_id", "_ingested_at")
KOSONG = {"nan", "-", "", "none", "null", "nat"}

for t in sorted(inspect(eng).get_table_names(schema="raw")):
    df = pd.read_sql(f'SELECT * FROM raw."{t}"', eng).drop(columns=list(META), errors="ignore")
    print("=" * 78)
    print(f"TABEL raw.{t} | {len(df)} baris | {df.shape[1]} kolom | baris duplikat penuh: {int(df.duplicated().sum())}")
    for c in df.columns:
        s = df[c].astype(str).str.strip()
        kosong = int(s.str.lower().isin(KOSONG).sum())
        valid = s[~s.str.lower().isin(KOSONG)]
        info = f"  - {c:<28} kosong/'-': {kosong:<5} unik: {valid.nunique():<5}"
        if any(k in c.lower() for k in SENSITIF):
            info += " [sensitif: nilai disembunyikan]"
        else:
            vc = valid.value_counts().head(5)
            info += " contoh: " + "; ".join(f"{i}({n})" for i, n in vc.items())
            if "tanggal" in c.lower() or c.lower() in ("date", "tgl"):
                d = pd.to_datetime(valid, errors="coerce")
                if d.notna().any():
                    info += f" | rentang: {d.min().date()} s/d {d.max().date()}"
        print(info[:300])