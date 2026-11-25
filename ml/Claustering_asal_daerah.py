import os
import re
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sqlalchemy import create_engine
from dotenv import load_dotenv

from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score

load_dotenv()

DB_USER = os.getenv("POSTGRES_USER", "kost_user")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "ganti_dengan_password")
DB_NAME = os.getenv("POSTGRES_DB", "kost_dwh")
DB_HOST = "localhost"
DB_PORT = os.getenv("POSTGRES_PORT", "5432")

DATABASE_URI = f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(DATABASE_URI)

def ekstrak_kota_dari_alamat(alamat, daftar_kota):
    if pd.isna(alamat) or not str(alamat).strip():
        return "Kota Lainnya"
    alamat_clean = str(alamat).upper()
    for kota in daftar_kota:
        # Cek kecocokan nama kota di dalam string alamat
        pola = r'\b' + re.escape(kota.upper()) + r'\b'
        if re.search(pola, alamat_clean):
            return kota
    # Ekstraksi kata terakhir setelah tanda koma jika ada
    if ',' in str(alamat):
        bagian_akhir = str(alamat).split(',')[-1].strip()
        if len(bagian_akhir) > 3:
            return bagian_akhir.title()
    return "Kota Lainnya"

def main():
    print("=" * 80)
    print("SEGMENTASI PROFIL DAERAH ASAL TERHADAP KEBIASAAN SEWA (K-MEANS CLUSTERING)")
    print("=" * 80)

    # 1. AMBIL MASTER KOTA & TRANSAKSI
    print("\n[1/5] Membaca data transaksi dan alamat penyewa dari DWH...")
    df_kota_ref = pd.read_sql("SELECT DISTINCT nama_kota_kab FROM dwh.dim_kota", engine)
    daftar_kota = df_kota_ref['nama_kota_kab'].dropna().tolist()

    query_raw = """
        SELECT 
            p.alamat_asli,
            f.durasi_hari,
            f.total_tagihan_rp,
            f.tipe_sewa,
            tf.status_ac
        FROM dwh.fact_transaksi_sewa f
        JOIN dwh.dim_penghuni p ON f.penghuni_key = p.penghuni_key
        JOIN dwh.dim_kamar k ON f.kamar_key = k.kamar_key
        JOIN dwh.dim_tipe_fasilitas tf ON k.tipe_fasilitas_id = tf.tipe_fasilitas_id;
    """
    df_trans = pd.read_sql(query_raw, engine)
    
    # Parsing kota asal nyata dari alamat
    df_trans['kota_asal'] = df_trans['alamat_asli'].apply(lambda x: ekstrak_kota_dari_alamat(x, daftar_kota))
    print(f"  Berhasil memetakan transaksi ke {df_trans['kota_asal'].nunique()} kota asal yang berbeda.")

    # 2. AGREGASI KEBIASAAN SEWA PER KOTA
    print("\n[2/5] Mengagregasi metrik kebiasaan sewa per kota...")
    df = df_trans.groupby('kota_asal').agg(
        total_transaksi=('durasi_hari', 'count'),
        rata_durasi_hari=('durasi_hari', 'mean'),
        rata_belanja_rp=('total_tagihan_rp', 'mean'),
        pct_sewa_harian=('tipe_sewa', lambda x: (x == 'Harian').mean() * 100),
        pct_pilihan_ac=('status_ac', lambda x: (x == 'Ya').mean() * 100)
    ).reset_index()

    # Filter kota dengan minimal 3 transaksi agar cluster valid
    df = df[df['total_transaksi'] >= 3].reset_index(drop=True)
    print(f"  {len(df)} Kota Asal memenuhi kriteria untuk dikelompokkan.")

    # 3. STANDARDISASI FITUR PERILAKU
    features = ['rata_durasi_hari', 'rata_belanja_rp', 'pct_sewa_harian', 'pct_pilihan_ac']
    X = df[features]
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # 4. SILHOUETTE ANALYSIS UNTUK K OPTIMAL
    print("\n[3/5] Evaluasi Jumlah Klaster (Silhouette Score):")
    best_k = 3
    best_score = -1
    for k in [2, 3, 4]:
        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = km.fit_predict(X_scaled)
        score = silhouette_score(X_scaled, labels)
        print(f"  K = {k} | Silhouette Score = {score:.4f}")
        if score > best_score:
            best_score = score
            best_k = k

    # Latih model K-Means terpilih
    kmeans = KMeans(n_clusters=best_k, random_state=42, n_init=10)
    df['cluster'] = kmeans.fit_predict(X_scaled)

    # 5. INTERPRETASI SEGMEN BISNIS
    print("\n[4/5] Karakteristik Rata-rata per Klaster:")
    profil_klaster = df.groupby('cluster')[features].mean().round(1)
    print(profil_klaster)

    # Labeling Klaster
    nama_klaster_map = {}
    for c in sorted(df['cluster'].unique()):
        sub = df[df['cluster'] == c]
        if sub['pct_sewa_harian'].mean() >= 30:
            nama_klaster_map[c] = f"Klaster {c+1}: Daerah Wisata / Transit Singkat (Dominan Harian)"
        elif sub['pct_pilihan_ac'].mean() >= 40:
            nama_klaster_map[c] = f"Klaster {c+1}: Daerah Jangka Panjang VIP (Dominan Kamar AC)"
        else:
            nama_klaster_map[c] = f"Klaster {c+1}: Daerah Mahasiswa / Reguler (Dominan Non-AC Bulanan)"

    df['kategori_segmen'] = df['cluster'].map(nama_klaster_map)

    # Simpan hasil segmentasi ke Data Mart
    df.to_sql("segmentasi_daerah_asal_ml", engine, schema="mart", if_exists="replace", index=False)
    print("\n[5/5] Hasil segmentasi berhasil disimpan ke mart.segmentasi_daerah_asal_ml!")

    # Buat Plot Grafik Scatter Plot
    os.makedirs("docs", exist_ok=True)
    plt.figure(figsize=(12, 7))
    sns.scatterplot(
        data=df,
        x='pct_pilihan_ac',
        y='pct_sewa_harian',
        size='total_transaksi',
        hue='kategori_segmen',
        palette='Set1',
        sizes=(60, 450),
        alpha=0.85
    )
    plt.title('Segmentasi Daerah Asal Tamu terhadap Preferensi Sewa Kost Bu Ratna (K-Means)', fontsize=13, fontweight='bold')
    plt.xlabel('Preferensi Kamar AC (%)', fontsize=11)
    plt.ylabel('Preferensi Sewa Harian (%)', fontsize=11)
    plt.grid(True, linestyle=':', alpha=0.6)
    plt.legend(bbox_to_anchor=(1.02, 1), loc='upper left')
    plt.tight_layout()
    plt.savefig("docs/grafik_segmentasi_daerah.png", dpi=300)
    print("  Gambar grafik tersimpan di: docs/grafik_segmentasi_daerah.png")

    print("\n" + "=" * 80)
    print("DAFTAR 10 KOTA ASAL & KATEGORI SEGMENNYA:")
    print(df[['kota_asal', 'total_transaksi', 'rata_durasi_hari', 'kategori_segmen']].head(10).to_string(index=False))
    print("=" * 80)

if __name__ == "__main__":
    main()