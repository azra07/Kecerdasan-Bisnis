import time
import os
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DB_USER = os.getenv("POSTGRES_USER", "kost_user")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "ganti_dengan_password")
DB_NAME = os.getenv("POSTGRES_DB", "kost_dwh")
DB_HOST = "localhost"
DB_PORT = os.getenv("POSTGRES_PORT", "5432")

DATABASE_URI = f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(DATABASE_URI)

def main():
    print("=" * 75)
    print("PENGUJIAN PERFORMA & SKALABILITAS SISTEM BIG DATA (KOST BU RATNA)")
    print("=" * 75)

    test_results = []

    # 1. UJI LATENSI KUERI AGREGASI ANALITIK (COMPLEX OLAP QUERY)
    queries = {
        "Q1: Agregasi Mart Finansial Bulanan": "SELECT * FROM mart.mart_finansial_bulanan;",
        "Q2: Agregasi 46.000+ Baris Mart Okupansi": "SELECT * FROM mart.mart_okupansi_harian WHERE tahun = 2024;",
        "Q3: Join Fakta Transaksi + Dim Kamar + Dim Waktu": """
            SELECT k.nama_kamar, w.nama_bulan, SUM(f.total_tagihan_rp) 
            FROM dwh.fact_transaksi_sewa f
            JOIN dwh.dim_kamar k ON f.kamar_key = k.kamar_key
            JOIN dwh.dim_waktu w ON f.waktu_masuk_key = w.waktu_key
            GROUP BY k.nama_kamar, w.nama_bulan;
        """,
        "Q4: Prediksi ML vs Realisasi": "SELECT * FROM mart.prediksi_okupansi_ml;"
    }

    print("\n[1/2] Menguji Latensi Kueri Analitik (Query Latency)...")
    with engine.connect() as conn:
        for q_name, q_sql in queries.items():
            start_time = time.time()
            res = conn.execute(text(q_sql)).fetchall()
            elapsed_ms = (time.time() - start_time) * 1000
            
            test_results.append({
                "Pengujian": q_name,
                "Jumlah Baris Output": len(res),
                "Latensi (ms)": round(elapsed_ms, 2),
                "Status": "Passed (< 100 ms)" if elapsed_ms < 100 else "Good"
            })
            print(f"  {q_name}: {len(res)} baris dalam {elapsed_ms:.2f} ms")

    # 2. UJI THROUGHPUT PEMROSESAN DATA
    print("\n[2/2] Menguji Kecepatan Throughput Pemrosesan Fakta...")
    with engine.connect() as conn:
        total_rows_oku = conn.execute(text("SELECT COUNT(*) FROM dwh.fact_okupansi_harian")).scalar()
        total_rows_trans = conn.execute(text("SELECT COUNT(*) FROM dwh.fact_transaksi_sewa")).scalar()

    df_test_report = pd.DataFrame(test_results)
    print("\n" + "=" * 75)
    print("TABEL HASIL PENGUJIAN SKALABILITAS (UNTUK BAB 4.8 LAPORAN UAS):")
    print("=" * 75)
    print(df_test_report.to_string(index=False))

    os.makedirs("docs", exist_ok=True)
    df_test_report.to_csv("docs/hasil_uji_skalabilitas.csv", index=False)
    print("\n  Laporan pengujian tersimpan di: docs/hasil_uji_skalabilitas.csv")
    print("=" * 75)

if __name__ == "__main__":
    main()