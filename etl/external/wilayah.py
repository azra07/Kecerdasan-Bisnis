import requests
import pandas as pd

print("[INGESTION] Menghubungi API Wilayah Indonesia (emsifa open API)...")

# 1. Tarik Data Semua Provinsi
url_provinsi = "https://www.emsifa.com/api-wilayah-indonesia/api/provinces.json"
try:
    res_prov = requests.get(url_provinsi, timeout=10)
    res_prov.raise_for_status()
    data_prov = res_prov.json()
    df_prov = pd.DataFrame(data_prov)
    df_prov.columns = ['provinsi_id', 'nama_provinsi']
    print(f"  ✓ Berhasil mengambil {len(df_prov)} Provinsi se-Indonesia.")
except Exception as e:
    print(f"❌ Gagal mengambil provinsi: {e}")
    exit()

# 2. Tarik Data Seluruh Kabupaten/Kota per Provinsi
semua_kota = []
print("  Sedang memproses seluruh Kabupaten/Kota...")

for _, row in df_prov.iterrows():
    prov_id = row['provinsi_id']
    url_kota = f"https://www.emsifa.com/api-wilayah-indonesia/api/regencies/{prov_id}.json"
    try:
        res_kota = requests.get(url_kota, timeout=10)
        if res_kota.status_code == 200:
            for k in res_kota.json():
                semua_kota.append({
                    'kota_id': k['id'],
                    'provinsi_id': k['province_id'],
                    'nama_kota_kab': k['name'],
                    'nama_provinsi': row['nama_provinsi']
                })
    except Exception:
        pass

df_kota = pd.DataFrame(semua_kota)
print(f"  ✓ Berhasil mengambil {len(df_kota)} Kota/Kabupaten.")

# 3. Simpan ke File CSV (Data Lake / Raw Zone)
df_prov.to_csv("master_provinsi.csv", index=False)
df_kota.to_csv("master_kota.csv", index=False)

print("\n✅ SUKSES! Data Master Wilayah tersimpan:")
print("  📁 master_provinsi.csv")
print("  📁 master_kota.csv")
print(df_kota.head())