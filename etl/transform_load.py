import os
import hashlib
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from dotenv import load_dotenv

load_dotenv()

# Konfigurasi Database dari .env
DB_USER = os.getenv("POSTGRES_USER", "kost_user")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "ganti_dengan_password")
DB_NAME = os.getenv("POSTGRES_DB", "kost_dwh")
DB_HOST = "localhost"
DB_PORT = os.getenv("POSTGRES_PORT", "5432")

DATABASE_URI = f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(DATABASE_URI)

def hash_nik(nik):
    if pd.isna(nik) or str(nik).strip() in ['', '-']:
        return None
    return hashlib.sha256(str(nik).encode('utf-8')).hexdigest()

def run_etl():
    print("=" * 70)
    print("MEMULAI TRANSFORM & LOAD DWH (SNOWFLAKE SCHEMA)")
    print("=" * 70)

    with engine.connect() as conn:
        # ----------------------------------------------------------------------
        # 1. LOAD DIM_PROVINSI & DIM_KOTA
        # ----------------------------------------------------------------------
        print("\n[1/7] Memuat dim_provinsi & dim_kota...")
        df_prov = pd.read_sql("SELECT provinsi_id, nama_provinsi FROM raw.master_provinsi", conn)
        df_kota = pd.read_sql("SELECT kota_id, provinsi_id, nama_kota_kab FROM raw.master_kota", conn)

        df_prov.to_sql("dim_provinsi", engine, schema="dwh", if_exists="append", index=False)
        df_kota.to_sql("dim_kota", engine, schema="dwh", if_exists="append", index=False)
        print(f"  {len(df_prov)} Provinsi & {len(df_kota)} Kota/Kabupaten termuat.")

        # ----------------------------------------------------------------------
        # 2. LOAD DIM_BLOK, DIM_TIPE_FASILITAS & DIM_KAMAR
        # ----------------------------------------------------------------------
        print("\n[2/7] Memuat Hierarki Kamar (dim_blok, dim_tipe_fasilitas, dim_kamar)...")
        df_fas = pd.read_sql("SELECT * FROM raw.fasilitas_kost__sheet1", conn)

        blok_unik = df_fas['blok'].dropna().unique()
        df_blok = pd.DataFrame({'nama_blok': blok_unik})
        df_blok.to_sql("dim_blok", engine, schema="dwh", if_exists="append", index=False)
        
        blok_map = pd.read_sql("SELECT blok_id, nama_blok FROM dwh.dim_blok", conn).set_index('nama_blok')['blok_id'].to_dict()

        fas_records = []
        for _, row in df_fas.iterrows():
            fas_records.append({
                'status_ac': row['status_ac'],
                'luas_kamar_m2': int(row['luas_kamar_m2']),
                'kapasitas': int(row['kapasitas']),
                'tarif_harian_dasar': float(row['tarif_harian']),
                'tarif_bulanan_dasar': float(row['tarif_bulanan']),
                'fasilitas_text': row['fasilitas']
            })

        pd.DataFrame(fas_records).to_sql("dim_tipe_fasilitas", engine, schema="dwh", if_exists="append", index=False)
        
        df_fas_db = pd.read_sql("SELECT tipe_fasilitas_id FROM dwh.dim_tipe_fasilitas ORDER BY tipe_fasilitas_id", conn)
        
        kamar_records = []
        for i, row in df_fas.iterrows():
            kamar_records.append({
                'kode_kamar': row['kode_kamar'],
                'nama_kamar': str(row['nama_kamar']),
                'blok_id': blok_map[row['blok']],
                'tipe_fasilitas_id': int(df_fas_db.iloc[i]['tipe_fasilitas_id'])
            })

        pd.DataFrame(kamar_records).to_sql("dim_kamar", engine, schema="dwh", if_exists="append", index=False)
        print(f"  26 Unit Kamar berhasil dinormalisasi ke skema Snowflake.")

        # ----------------------------------------------------------------------
        # 3. LOAD DIM_WAKTU (Conformed Dimension 2019 - 2026)
        # ----------------------------------------------------------------------
        print("\n[3/7] Membangun dim_waktu (Kalender + Cuaca + Libur + Akademik)...")
        tgl_range = pd.date_range(start="2019-01-01", end="2026-12-31")
        df_waktu = pd.DataFrame({'tanggal': tgl_range})
        df_waktu['waktu_key'] = df_waktu['tanggal'].dt.strftime('%Y%m%d').astype(int)
        df_waktu['hari'] = df_waktu['tanggal'].dt.day
        df_waktu['bulan'] = df_waktu['tanggal'].dt.month
        df_waktu['tahun'] = df_waktu['tanggal'].dt.year
        df_waktu['nama_hari'] = df_waktu['tanggal'].dt.day_name()
        df_waktu['nama_bulan'] = df_waktu['tanggal'].dt.month_name()
        df_waktu['is_weekend'] = df_waktu['tanggal'].dt.dayofweek.isin([5, 6])

        # Join Cuaca
        df_cuaca = pd.read_sql("SELECT tanggal, suhu_rata2_celsius, curah_hujan_mm FROM raw.data_cuaca_historis_2019_2026", conn)
        df_cuaca['tanggal'] = pd.to_datetime(df_cuaca['tanggal'])
        df_waktu = df_waktu.merge(df_cuaca, on='tanggal', how='left')

        # Join Libur
        df_libur = pd.read_sql("SELECT holiday_date as tanggal, holiday_name as keterangan_libur FROM raw.master_libur_2019_2026", conn)
        df_libur['tanggal'] = pd.to_datetime(df_libur['tanggal'])
        df_libur['is_libur_nasional'] = True
        df_waktu = df_waktu.merge(df_libur, on='tanggal', how='left')
        df_waktu['is_libur_nasional'] = df_waktu['is_libur_nasional'].fillna(False)

        # Join Akademik
        df_akad = pd.read_sql("SELECT tanggal_mulai, tanggal_selesai, kategori_akademik FROM raw.master_kalender_akademik_2019_2026", conn)
        df_waktu['is_event_akademik'] = False
        df_waktu['kategori_akademik'] = None

        for _, ak in df_akad.iterrows():
            mask = (df_waktu['tanggal'] >= pd.to_datetime(ak['tanggal_mulai'])) & (df_waktu['tanggal'] <= pd.to_datetime(ak['tanggal_selesai']))
            df_waktu.loc[mask, 'is_event_akademik'] = True
            df_waktu.loc[mask, 'kategori_akademik'] = ak['kategori_akademik']

        df_waktu['suhu_rata2_celsius'] = df_waktu['suhu_rata2_celsius'].fillna(27.0)
        df_waktu['curah_hujan_mm'] = df_waktu['curah_hujan_mm'].fillna(0.0)

        df_waktu.to_sql("dim_waktu", engine, schema="dwh", if_exists="append", index=False)
        print(f"  ✓ {len(df_waktu)} hari kalender (2019-2026) termuat lengkap.")

        # ----------------------------------------------------------------------
        # 4. LOAD DIM_PENGHUNI (UU PDP SHA-256 Hashing)
        # ----------------------------------------------------------------------
        print("\n[4/7] Memuat dim_penghuni (dengan SHA-256 Masking)...")
        df_kost = pd.read_sql("SELECT * FROM raw.dataset_kost__sheet1", conn)
        
        penghuni_unik = df_kost[['nama', 'alamat', 'nomor_nip_sim']].drop_duplicates().copy()
        penghuni_unik['nik_hash'] = penghuni_unik['nomor_nip_sim'].apply(hash_nik)
        penghuni_unik['kota_id'] = 3273 # Default fallback Bandung
        penghuni_unik['is_current'] = True
        penghuni_unik.rename(columns={'nama': 'nama_penghuni', 'alamat': 'alamat_asli'}, inplace=True)

        penghuni_unik[['nama_penghuni', 'nik_hash', 'kota_id', 'alamat_asli', 'is_current']].to_sql(
            "dim_penghuni", engine, schema="dwh", if_exists="append", index=False
        )
        print(f"  ✓ {len(penghuni_unik)} Master Tamu terdaftar dengan NIK terenkripsi.")

        # ----------------------------------------------------------------------
        # 5. LOAD FACT_TRANSAKSI_SEWA
        # ----------------------------------------------------------------------
        print("\n[5/7] Memuat fact_transaksi_sewa...")
        kamar_db = pd.read_sql("SELECT kamar_key, kode_kamar FROM dwh.dim_kamar", conn).set_index('kode_kamar')['kamar_key'].to_dict()
        penghuni_db = pd.read_sql("SELECT penghuni_key, nama_penghuni, alamat_asli FROM dwh.dim_penghuni", conn)
        
        df_kost = df_kost.merge(penghuni_db, left_on=['nama', 'alamat'], right_on=['nama_penghuni', 'alamat_asli'], how='left')
        df_kost['kamar_key'] = df_kost['nomor_kamar'].map(kamar_db)
        df_kost['waktu_masuk_key'] = pd.to_datetime(df_kost['tanggal_masuk']).dt.strftime('%Y%m%d').astype(int)
        df_kost['waktu_keluar_key'] = pd.to_datetime(df_kost['tanggal_keluar']).dt.strftime('%Y%m%d').astype(int)
        df_kost['durasi_hari'] = (pd.to_datetime(df_kost['tanggal_keluar']) - pd.to_datetime(df_kost['tanggal_masuk'])).dt.days
        df_kost['tipe_sewa'] = np.where(df_kost['durasi_hari'] >= 28, 'Bulanan', 'Harian')

        fact_sewa = df_kost[[
            'penghuni_key', 'kamar_key', 'waktu_masuk_key', 'waktu_keluar_key',
            'jumlah_penghuni', 'durasi_hari', 'tipe_sewa', 'tagihan'
        ]].rename(columns={'tagihan': 'total_tagihan_rp'})

        fact_sewa.to_sql("fact_transaksi_sewa", engine, schema="dwh", if_exists="append", index=False)
        print(f"  ✓ {len(fact_sewa)} Transaksi Sewa berhasil dimuat.")

        # ----------------------------------------------------------------------
        # 6. LOAD FACT_OKUPANSI_HARIAN
        # ----------------------------------------------------------------------
        print("\n[6/7] Membangun Snapshot fact_okupansi_harian...")
        okupansi_rows = []
        for _, row in df_kost.iterrows():
            k_key = row['kamar_key']
            t_masuk = pd.to_datetime(row['tanggal_masuk'])
            t_keluar = pd.to_datetime(row['tanggal_keluar'])
            durasi = max(1, (t_keluar - t_masuk).days)
            tarif_per_hari = float(row['tagihan']) / durasi
            
            curr = t_masuk
            while curr < t_keluar:
                okupansi_rows.append({
                    'kamar_key': k_key,
                    'waktu_key': int(curr.strftime('%Y%m%d')),
                    'status_terisi': 1,
                    'pendapatan_proporsional_rp': round(tarif_per_hari, 2)
                })
                curr += timedelta(days=1)

        df_oku = pd.DataFrame(okupansi_rows)
        df_oku = df_oku.groupby(['kamar_key', 'waktu_key']).agg({
            'status_terisi': 'max',
            'pendapatan_proporsional_rp': 'sum'
        }).reset_index()

        df_oku.to_sql("fact_okupansi_harian", engine, schema="dwh", if_exists="append", index=False, chunksize=5000)
        print(f"  ✓ {len(df_oku)} snapshot room-night okupansi harian terbentuk.")

        # ----------------------------------------------------------------------
        # 7. LOAD FACT_BIAYA_OPERASIONAL
        # ----------------------------------------------------------------------
        print("\n[7/7] Memuat fact_biaya_operasional...")
        df_biaya = pd.read_sql("SELECT * FROM raw.biaya_operasional_kost__sheet1", conn)
        df_biaya['waktu_key'] = (df_biaya['tahun'].astype(str) + df_biaya['bulan'].astype(str).str.zfill(2) + "01").astype(int)
        
        kolom_beban = ['listrik_pln', 'air_pdam', 'wifi', 'sampah', 'jaga_malam', 'gas', 'tv_kabel', 'servis_ac']
        
        # Konversi ke float dulu agar dijumlahkan sebagai angka, bukan teks!
        for col in kolom_beban:
            df_biaya[col] = pd.to_numeric(df_biaya[col], errors='coerce').fillna(0)
            
        df_biaya['total_beban_operasional'] = df_biaya[kolom_beban].sum(axis=1)

        fact_biaya = df_biaya[[
            'id_biaya', 'bulan', 'tahun', 'waktu_key', 'listrik_pln', 'air_pdam',
            'wifi', 'sampah', 'jaga_malam', 'gas', 'tv_kabel', 'servis_ac', 'total_beban_operasional'
        ]].rename(columns={'id_biaya': 'id_biaya_sumber'})

        fact_biaya.to_sql("fact_biaya_operasional", engine, schema="dwh", if_exists="append", index=False)
        print(f"  ✓ {len(fact_biaya)} baris data Beban Operasional termuat.")

    print("\n" + "=" * 70)
    print("SELURUH DATA WAREHOUSE BERHASIL TERISI DENGAN LENGKAP!")
    print("=" * 70)

if __name__ == "__main__":
    run_etl()