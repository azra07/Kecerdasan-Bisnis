import requests
import pandas as pd
import holidays
import os

print("[INGESTION] Memulai penarikan API Hari Libur Nasional (2019 - 2026)...")

daftar_libur = []

# Kamus terjemahan otomatis ke Bahasa Indonesia
terjemahan = {
    "New Year's Day": "Tahun Baru Masehi",
    "Lunar New Year": "Tahun Baru Imlek",
    "Prophet's Birthday": "Maulid Nabi Muhammad SAW",
    "Day of Silence": "Hari Suci Nyepi",
    "Good Friday": "Wafat Isa Al-Masih / Jumat Agung",
    "Vesak Day": "Hari Raya Waisak",
    "Ascension Day": "Kenaikan Isa Al-Masih",
    "Isra' and Mi'raj": "Isra Mi'raj Nabi Muhammad SAW",
    "Independence Day": "Hari Kemerdekaan RI",
    "Eid al-Fitr": "Hari Raya Idul Fitri",
    "Eid al-Adha": "Hari Raya Idul Adha",
    "Islamic New Year": "Tahun Baru Islam",
    "Christmas Day": "Hari Raya Natal",
    "Labour Day": "Hari Buruh Internasional",
    "Pancasila Day": "Hari Lahir Pancasila",
}

# 1. Tarik dari REST API publik per tahun (2019 - 2026)
for tahun in range(2019, 2027):
    url = f"https://api-hari-libur.vercel.app/api?year={tahun}"
    try:
        response = requests.get(url, timeout=7)
        if response.status_code == 200:
            payload = response.json()
            items = payload.get('data', []) if isinstance(payload, dict) else payload
            for item in items:
                nama = item.get('holiday_name', '')
                daftar_libur.append({
                    'holiday_date': str(item.get('holiday_date')),
                    'holiday_name': nama,
                    'is_national_holiday': True
                })
            print(f"  ✓ Tahun {tahun}: Berhasil ({len(items)} hari libur)")
        else:
            print(f"  ⚠ Tahun {tahun}: API non-200, fallback ke pustaka...")
    except Exception as e:
        print(f"  ⚠ Tahun {tahun}: Gagal koneksi API ({e}), fallback ke pustaka...")

# 2. Mekanisme Fallback / Pelengkap via pustaka holidays resmi Indonesia
id_holidays = holidays.Indonesia(years=range(2019, 2027))
for tgl_obj, nama_eng in id_holidays.items():
    tgl_str = str(tgl_obj)
    if not any(d['holiday_date'] == tgl_str for d in daftar_libur):
        nama_indo = terjemahan.get(nama_eng, nama_eng)
        daftar_libur.append({
            'holiday_date': tgl_str,
            'holiday_name': nama_indo,
            'is_national_holiday': True
        })

# 3. Bentuk DataFrame, hapus duplikat & urutkan
df_libur = pd.DataFrame(daftar_libur)
df_libur = df_libur.dropna(subset=['holiday_date']).drop_duplicates(subset=['holiday_date'])
df_libur['holiday_date'] = pd.to_datetime(df_libur['holiday_date'])
df_libur = df_libur.sort_values(by='holiday_date').reset_index(drop=True)

# 4. Simpan ke CSV sebagai Raw Data Lake
output_file = "master_libur_2019_2026.csv"
df_libur.to_csv(output_file, index=False)

print(f"\n✅ SUKSES! Total {len(df_libur)} hari libur tersimpan di: {output_file}")
print(df_libur.head())