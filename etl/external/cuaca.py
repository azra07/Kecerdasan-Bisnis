import requests
import pandas as pd

print("[INGESTION] Menarik Data API Cuaca & Suhu Historis (Open-Meteo)...")

# Koordinat lokasi kost (contoh: Bandung -6.9175, 107.6191 atau sesuaikan dengan kota kost Anda)
url = (
    "https://archive-api.open-meteo.com/v1/archive?"
    "latitude=-6.9175&longitude=107.6191"
    "&start_date=2019-01-01&end_date=2026-03-31"
    "&daily=temperature_2m_max,temperature_2m_mean,precipitation_sum"
    "&timezone=Asia%2FJakarta"
)

response = requests.get(url)
if response.status_code == 200:
    data = response.json()
    df_cuaca = pd.DataFrame(data['daily'])
    df_cuaca.rename(columns={
        'time': 'tanggal',
        'temperature_2m_max': 'suhu_max_celsius',
        'temperature_2m_mean': 'suhu_rata2_celsius',
        'precipitation_sum': 'curah_hujan_mm'
    }, inplace=True)
    
    df_cuaca.to_csv("data_cuaca_historis_2019_2026.csv", index=False)
    print(f"✅ SUKSES! {len(df_cuaca)} baris data suhu dan cuaca harian berhasil ditarik.")
    print(df_cuaca.head())
else:
    print(f"❌ Gagal: {response.status_code}")