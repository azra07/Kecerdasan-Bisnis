-- =============================================================================
-- DATA MART LAYER (MATERIALIZED VIEWS UNTUK METABASE & ML)
-- =============================================================================

-- 1. Mart Finansial Bulanan (Revenue vs Expense vs Net Profit)
CREATE OR REPLACE VIEW mart.mart_finansial_bulanan AS
WITH omzet AS (
    SELECT 
        w.tahun,
        w.bulan,
        SUM(f.total_tagihan_rp) AS total_omzet_sewa,
        COUNT(f.transaksi_id) AS total_transaksi
    FROM dwh.fact_transaksi_sewa f
    JOIN dwh.dim_waktu w ON f.waktu_masuk_key = w.waktu_key
    GROUP BY w.tahun, w.bulan
),
beban AS (
    SELECT 
        tahun,
        bulan,
        listrik_pln,
        air_pdam,
        wifi,
        sampah,
        jaga_malam,
        gas,
        tv_kabel,
        servis_ac,
        total_beban_operasional
    FROM dwh.fact_biaya_operasional
)
SELECT 
    b.tahun,
    b.bulan,
    TO_DATE(b.tahun || '-' || LPAD(b.bulan::text, 2, '0') || '-01', 'YYYY-MM-DD') AS periode_bulan,
    COALESCE(o.total_omzet_sewa, 0) AS total_pendapatan,
    COALESCE(o.total_transaksi, 0) AS total_transaksi,
    b.listrik_pln,
    b.air_pdam,
    b.total_beban_operasional,
    (COALESCE(o.total_omzet_sewa, 0) - b.total_beban_operasional) AS laba_bersih_operasional,
    ROUND(((COALESCE(o.total_omzet_sewa, 0) - b.total_beban_operasional) / NULLIF(COALESCE(o.total_omzet_sewa, 0), 0)) * 100, 2) AS net_profit_margin_pct
FROM beban b
LEFT JOIN omzet o ON b.tahun = o.tahun AND b.bulan = o.bulan
ORDER BY b.tahun, b.bulan;


-- 2. Mart Okupansi Harian (Room-Night & RevPAR)
CREATE OR REPLACE VIEW mart.mart_okupansi_harian AS
SELECT 
    w.tanggal,
    w.waktu_key,
    w.tahun,
    w.bulan,
    w.nama_hari,
    w.is_weekend,
    w.is_libur_nasional,
    w.is_event_akademik,
    w.suhu_rata2_celsius,
    COUNT(f.kamar_key) AS total_kamar_tersedia, -- 26 Kamar
    SUM(f.status_terisi) AS total_kamar_terisi,
    ROUND((SUM(f.status_terisi)::decimal / COUNT(f.kamar_key)::decimal) * 100, 2) AS okupansi_rate_pct,
    SUM(f.pendapatan_proporsional_rp) AS pendapatan_harian_rp,
    ROUND(SUM(f.pendapatan_proporsional_rp) / COUNT(f.kamar_key), 2) AS revpar_rp -- Revenue per Available Room
FROM dwh.fact_okupansi_harian f
JOIN dwh.dim_waktu w ON f.waktu_key = w.waktu_key
GROUP BY w.tanggal, w.waktu_key, w.tahun, w.bulan, w.nama_hari, w.is_weekend, w.is_libur_nasional, w.is_event_akademik, w.suhu_rata2_celsius
ORDER BY w.tanggal;


-- 3. Mart Korelasi Utilitas Beban Listrik vs Okupansi Kamar AC
CREATE OR REPLACE VIEW mart.mart_utilitas_beban AS
WITH ac_occupancy AS (
    SELECT 
        w.tahun,
        w.bulan,
        COUNT(DISTINCT f.kamar_key) FILTER (WHERE f.status_terisi = 1) AS kamar_ac_aktif_rata2
    FROM dwh.fact_okupansi_harian f
    JOIN dwh.dim_kamar k ON f.kamar_key = k.kamar_key
    JOIN dwh.dim_tipe_fasilitas tf ON k.tipe_fasilitas_id = tf.tipe_fasilitas_id
    JOIN dwh.dim_waktu w ON f.waktu_key = w.waktu_key
    WHERE tf.status_ac = 'Ya'
    GROUP BY w.tahun, w.bulan
)
SELECT 
    b.tahun,
    b.bulan,
    b.listrik_pln,
    b.servis_ac,
    COALESCE(ao.kamar_ac_aktif_rata2, 0) AS kamar_ac_terisi,
    ROUND(b.listrik_pln / NULLIF(COALESCE(ao.kamar_ac_aktif_rata2, 0), 0), 2) AS beban_listrik_per_kamar_ac
FROM dwh.fact_biaya_operasional b
LEFT JOIN ac_occupancy ao ON b.tahun = ao.tahun AND b.bulan = ao.bulan
ORDER BY b.tahun, b.bulan;


-- 4. Mart Demografi Asal Tamu
CREATE OR REPLACE VIEW mart.mart_demografi_penyewa AS
SELECT 
    COALESCE(pr.nama_provinsi, 'Luar Daerah') AS nama_provinsi,
    COALESCE(kt.nama_kota_kab, 'Lainnya') AS nama_kota,
    f.tipe_sewa,
    COUNT(f.transaksi_id) AS frekuensi_sewa,
    SUM(f.total_tagihan_rp) AS total_kontribusi_omzet
FROM dwh.fact_transaksi_sewa f
JOIN dwh.dim_penghuni p ON f.penghuni_key = p.penghuni_key
LEFT JOIN dwh.dim_kota kt ON p.kota_id = kt.kota_id
LEFT JOIN dwh.dim_provinsi pr ON kt.provinsi_id = pr.provinsi_id
GROUP BY pr.nama_provinsi, kt.nama_kota_kab, f.tipe_sewa
ORDER BY total_kontribusi_omzet DESC;