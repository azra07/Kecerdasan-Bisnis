import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sqlalchemy import create_engine
from dotenv import load_dotenv

from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from xgboost import XGBRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

load_dotenv()

# Koneksi Database
DB_USER = os.getenv("POSTGRES_USER", "kost_user")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "ganti_dengan_password")
DB_NAME = os.getenv("POSTGRES_DB", "kost_dwh")
DB_HOST = "localhost"
DB_PORT = os.getenv("POSTGRES_PORT", "5432")

DATABASE_URI = f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(DATABASE_URI)

def mape(y_true, y_pred):
    return np.mean(np.abs((y_true - y_pred) / np.maximum(y_true, 1))) * 100

def main():
    print("=" * 75)
    print("MEMULAI PIPELINE MACHINE LEARNING (FORECASTING OKUPANSI & REVENUE)")
    print("=" * 75)

    # 1. TARIK DATA DARI DATA MART
    print("\n[1/6] Mengambil data analitik dari mart.mart_okupansi_harian...")
    query = """
        SELECT 
            tanggal,
            tahun,
            bulan,
            nama_hari,
            is_weekend,
            is_libur_nasional,
            is_event_akademik,
            suhu_rata2_celsius,
            total_kamar_terisi,
            pendapatan_harian_rp
        FROM mart.mart_okupansi_harian
        ORDER BY tanggal ASC;
    """
    df = pd.read_sql(query, engine)
    df['tanggal'] = pd.to_datetime(df['tanggal'])
    print(f"  Berhasil mengambil {len(df)} baris data time-series (2019 - 2026).")

    # 2. FEATURE ENGINEERING
    print("\n[2/6] Melakukan Feature Engineering & Temporal Lag Features...")
    df['is_weekend'] = df['is_weekend'].astype(int)
    df['is_libur_nasional'] = df['is_libur_nasional'].astype(int)
    df['is_event_akademik'] = df['is_event_akademik'].astype(int)
    df['day_of_week'] = df['tanggal'].dt.dayofweek
    df['day_of_month'] = df['tanggal'].dt.day

    # Fitur Siklus Kalender (Sin & Cos Encoding untuk menangkap musiman bulan)
    df['sin_bulan'] = np.sin(2 * np.pi * df['bulan'] / 12)
    df['cos_bulan'] = np.cos(2 * np.pi * df['bulan'] / 12)

    # Lag Features (Okupansi 1 hari, 7 hari, dan 14 hari sebelumnya)
    df['lag_okupansi_1d'] = df['total_kamar_terisi'].shift(1)
    df['lag_okupansi_7d'] = df['total_kamar_terisi'].shift(7)
    df['lag_okupansi_14d'] = df['total_kamar_terisi'].shift(14)
    df['rolling_mean_7d'] = df['total_kamar_terisi'].shift(1).rolling(window=7).mean()

    # Drop baris awal yang NaN akibat lag
    df = df.dropna().reset_index(drop=True)

    features = [
        'bulan', 'day_of_week', 'day_of_month', 'is_weekend', 'is_libur_nasional',
        'is_event_akademik', 'suhu_rata2_celsius', 'sin_bulan', 'cos_bulan',
        'lag_okupansi_1d', 'lag_okupansi_7d', 'lag_okupansi_14d', 'rolling_mean_7d'
    ]
    target = 'total_kamar_terisi'

    X = df[features]
    y = df[target]

    # 3. TIME-BASED DATA SPLITTING (Wajib untuk data deret waktu!)
    print("\n[3/6] Membagi data train-test berbasis urutan waktu (Time-Series Split)...")
    # Training: 2019 s.d. 2024 (80%), Testing: 2025 s.d. 2026 (20%)
    split_date = pd.to_datetime("2025-01-01")
    train_mask = df['tanggal'] < split_date
    test_mask = df['tanggal'] >= split_date

    X_train, y_train = X[train_mask], y[train_mask]
    X_test, y_test = X[test_mask], y[test_mask]
    df_test = df[test_mask].copy()

    print(f"  Data Train : {len(X_train)} hari (Periode: {df.loc[train_mask, 'tanggal'].min().strftime('%Y-%m-%d')} s.d. {df.loc[train_mask, 'tanggal'].max().strftime('%Y-%m-%d')})")
    print(f"  Data Test  : {len(X_test)} hari (Periode: {df.loc[test_mask, 'tanggal'].min().strftime('%Y-%m-%d')} s.d. {df.loc[test_mask, 'tanggal'].max().strftime('%Y-%m-%d')})")

    # 4. TRAINING & BENCHMARKING (BASELINE VS CHALLENGERS)
    print("\n[4/6] Melatih Model: Baseline vs Random Forest vs XGBoost...")
    models = {
        "1. Linear Regression (Baseline)": LinearRegression(),
        "2. Random Forest Regressor": RandomForestRegressor(n_estimators=100, max_depth=10, random_state=42),
        "3. XGBoost Regressor (Challenger)": XGBRegressor(n_estimators=120, learning_rate=0.08, max_depth=6, random_state=42)
    }

    eval_results = []
    predictions_dict = {}

    for name, model in models.items():
        model.fit(X_train, y_train)
        preds = model.predict(X_test)
        preds = np.clip(preds, 0, 26) # Okupansi kamar fisik Kost Bu Ratna maksimal 26 kamar!
        predictions_dict[name] = preds

        mae_val = mean_absolute_error(y_test, preds)
        rmse_val = np.sqrt(mean_squared_error(y_test, preds))
        r2_val = r2_score(y_test, preds)
        mape_val = mape(y_test, preds)

        eval_results.append({
            "Model": name,
            "MAE (Kamar)": round(mae_val, 2),
            "RMSE (Kamar)": round(rmse_val, 2),
            "R2 Score": round(r2_val, 4),
            "MAPE (%)": round(mape_val, 2)
        })

    # 5. TABEL EVALUASI RESMI (UNTUK LAPORAN & PPT SLIDE 8)
    df_eval = pd.DataFrame(eval_results)
    print("\n" + "=" * 75)
    print("HASIL EVALUASI KOMPARASI MODEL MACHINE LEARNING:")
    print("=" * 75)
    print(df_eval.to_string(index=False))

    # Tentukan model terbaik (R2 tertinggi)
    best_model_name = df_eval.sort_values(by="R2 Score", ascending=False).iloc[0]["Model"]
    print(f"\nMODEL TERPILIH: {best_model_name}")

    # Simpan tabel evaluasi ke CSV untuk lampiran laporan
    os.makedirs("docs", exist_ok=True)
    df_eval.to_csv("docs/evaluasi_model_ml.csv", index=False)
    print("  Tabel perbandingan tersimpan di: docs/evaluasi_model_ml.csv")

    # 6. SIMPAN HASIL PREDIKSI KE DATABASE (UNTUK METABASE DASHBOARD)
    print("\n[6/6] Menyimpan hasil prediksi (Actual vs Prediction) ke database mart...")
    best_preds = predictions_dict[best_model_name]
    df_test['prediksi_kamar_terisi'] = np.round(best_preds, 1)
    
    # Estimasi pendapatan harian yang diprediksi (berdasarkan rata-rata tarif proporsional)
    avg_tarif = df['pendapatan_harian_rp'].sum() / df['total_kamar_terisi'].sum()
    df_test['prediksi_pendapatan_rp'] = np.round(df_test['prediksi_kamar_terisi'] * avg_tarif, 2)

    output_db = df_test[['tanggal', 'total_kamar_terisi', 'prediksi_kamar_terisi', 'pendapatan_harian_rp', 'prediksi_pendapatan_rp']].copy()
    output_db.to_sql("prediksi_okupansi_ml", engine, schema="mart", if_exists="replace", index=False)
    print("  Tabel mart.prediksi_okupansi_ml berhasil dibuat di database PostgreSQL.")

    # Simpan Gambar Grafik Actual vs Prediction (Untuk Slide PPT & Laporan Bab IV)
    plt.figure(figsize=(14, 6))
    sample_plot = df_test.tail(120) # 120 hari terakhir
    plt.plot(sample_plot['tanggal'], sample_plot['total_kamar_terisi'], label='Aktual Okupansi', color='#1f77b4', linewidth=2)
    plt.plot(sample_plot['tanggal'], sample_plot['prediksi_kamar_terisi'], label=f'Prediksi ({best_model_name})', color='#ff7f0e', linestyle='--', linewidth=2)
    plt.title('Grafik Evaluasi Actual vs Predicted Okupansi Kamar Kost Bu Ratna', fontsize=14, fontweight='bold')
    plt.xlabel('Tanggal', fontsize=11)
    plt.ylabel('Jumlah Kamar Terisi (Unit)', fontsize=11)
    plt.grid(True, linestyle=':', alpha=0.6)
    plt.legend(fontsize=11)
    plt.tight_layout()
    plt.savefig("docs/grafik_evaluasi_ml.png", dpi=300)
    print("  Grafik Actual vs Predicted tersimpan di: docs/grafik_evaluasi_ml.png")

    print("\n" + "=" * 75)
    print("SELURUH PIPELINE MACHINE LEARNING SELESAI DENGAN SUKSES!")
    print("=" * 75)

if __name__ == "__main__":
    main()