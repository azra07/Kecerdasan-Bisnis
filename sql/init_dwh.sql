-- =============================================================================
-- INISIALISASI SKEMA DATA WAREHOUSE (SNOWFLAKE SCHEMA) - KOST BU RATNA
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS dwh;
CREATE SCHEMA IF NOT EXISTS mart;

-- -----------------------------------------------------------------------------
-- 1. TABEL DIMENSI HIERARKI WILAYAH (Snowflake Level 1 & 2)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dwh.dim_provinsi (
    provinsi_id INT PRIMARY KEY,
    nama_provinsi VARCHAR(100) NOT NULL
);

CREATE TABLE IF NOT EXISTS dwh.dim_kota (
    kota_id INT PRIMARY KEY,
    provinsi_id INT REFERENCES dwh.dim_provinsi(provinsi_id),
    nama_kota_kab VARCHAR(100) NOT NULL
);

-- Dimensi Penghuni (SCD Type 2 & Hashing NIK UU PDP)
CREATE TABLE IF NOT EXISTS dwh.dim_penghuni (
    penghuni_key SERIAL PRIMARY KEY,
    nama_penghuni VARCHAR(150),
    nik_hash VARCHAR(64),           -- SHA-256 Hashing
    kota_id INT REFERENCES dwh.dim_kota(kota_id),
    alamat_asli TEXT,
    is_current BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------------------------------------------------------------
-- 2. TABEL DIMENSI HIERARKI KAMAR (Snowflake Level 1 & 2)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dwh.dim_blok (
    blok_id SERIAL PRIMARY KEY,
    nama_blok VARCHAR(50) NOT NULL UNIQUE -- Lantai 2, Bawah, Rumah sebelah
);

CREATE TABLE IF NOT EXISTS dwh.dim_tipe_fasilitas (
    tipe_fasilitas_id SERIAL PRIMARY KEY,
    status_ac VARCHAR(10) NOT NULL,       -- Ya / Tidak
    luas_kamar_m2 INT,
    kapasitas INT,
    tarif_harian_dasar DECIMAL(12,2),
    tarif_bulanan_dasar DECIMAL(12,2),
    fasilitas_text TEXT
);

CREATE TABLE IF NOT EXISTS dwh.dim_kamar (
    kamar_key SERIAL PRIMARY KEY,
    kode_kamar VARCHAR(20) NOT NULL UNIQUE, -- L201, B01, RS01, dll
    nama_kamar VARCHAR(50),
    blok_id INT REFERENCES dwh.dim_blok(blok_id),
    tipe_fasilitas_id INT REFERENCES dwh.dim_tipe_fasilitas(tipe_fasilitas_id)
);

-- -----------------------------------------------------------------------------
-- 3. TABEL DIMENSI WAKTU (Conformed Dimension)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dwh.dim_waktu (
    waktu_key INT PRIMARY KEY,              -- Format YYYYMMDD (contoh: 20240101)
    tanggal DATE NOT NULL UNIQUE,
    hari INT,
    bulan INT,
    tahun INT,
    nama_hari VARCHAR(20),
    nama_bulan VARCHAR(20),
    is_weekend BOOLEAN,
    is_libur_nasional BOOLEAN DEFAULT FALSE,
    keterangan_libur VARCHAR(150),
    is_event_akademik BOOLEAN DEFAULT FALSE,
    kategori_akademik VARCHAR(100),
    suhu_rata2_celsius DECIMAL(5,2),
    curah_hujan_mm DECIMAL(6,2)
);

-- -----------------------------------------------------------------------------
-- 4. TABEL FAKTA (3 FACT TABLES)
-- -----------------------------------------------------------------------------

-- Fakta 1: Transaksi Sewa (Grain: 1 baris per transaksi sewa)
CREATE TABLE IF NOT EXISTS dwh.fact_transaksi_sewa (
    transaksi_id SERIAL PRIMARY KEY,
    penghuni_key INT REFERENCES dwh.dim_penghuni(penghuni_key),
    kamar_key INT REFERENCES dwh.dim_kamar(kamar_key),
    waktu_masuk_key INT REFERENCES dwh.dim_waktu(waktu_key),
    waktu_keluar_key INT REFERENCES dwh.dim_waktu(waktu_key),
    jumlah_penghuni INT,
    durasi_hari INT,
    tipe_sewa VARCHAR(20),                 -- Harian / Bulanan
    total_tagihan_rp DECIMAL(14,2)
);

-- Fakta 2: Okupansi Harian (Grain: 1 baris per unit kamar per tanggal)
CREATE TABLE IF NOT EXISTS dwh.fact_okupansi_harian (
    okupansi_id BIGSERIAL PRIMARY KEY,
    kamar_key INT REFERENCES dwh.dim_kamar(kamar_key),
    waktu_key INT REFERENCES dwh.dim_waktu(waktu_key),
    status_terisi INT DEFAULT 0,          -- 1 jika terisi, 0 jika kosong
    pendapatan_proporsional_rp DECIMAL(12,2) DEFAULT 0
);

-- Fakta 3: Biaya Operasional Bulanan (Grain: 1 baris per bulan kalender)
CREATE TABLE IF NOT EXISTS dwh.fact_biaya_operasional (
    biaya_id SERIAL PRIMARY KEY,
    id_biaya_sumber VARCHAR(30),
    bulan INT,
    tahun INT,
    waktu_key INT REFERENCES dwh.dim_waktu(waktu_key),
    listrik_pln DECIMAL(14,2),
    air_pdam DECIMAL(14,2),
    wifi DECIMAL(14,2),
    sampah DECIMAL(14,2),
    jaga_malam DECIMAL(14,2),
    gas DECIMAL(14,2),
    tv_kabel DECIMAL(14,2),
    servis_ac DECIMAL(14,2),
    total_beban_operasional DECIMAL(14,2)
);