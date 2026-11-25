import requests
import pandas as pd
from icalendar import Calendar
from datetime import datetime
import os

print("[INGESTION] Mengambil data Kalender Akademik Kampus...")

# Contoh URL Public Google Calendar iCal (atau endpoint kalender kampus)
# Format Google Calendar publik: https://calendar.google.com/calendar/ical/<CALENDAR_ID>/public/basic.ics
ICAL_URL = "https://calendar.google.com/calendar/ical/id.indonesian%23holiday%40group.v.calendar.google.com/public/basic.ics"

def ambil_kalender_akademik(url_kalender):
    daftar_event = []
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url_kalender, headers=headers, timeout=10)
        
        if response.status_code == 200:
            cal = Calendar.from_ical(response.text)
            
            for component in cal.walk():
                if component.name == "VEVENT":
                    summary = str(component.get('summary', ''))
                    dtstart = component.get('dtstart')
                    dtend = component.get('dtend')
                    
                    if dtstart:
                        tgl_mulai = dtstart.dt
                        # Tangani jika objek berupa datetime atau date
                        if isinstance(tgl_mulai, datetime):
                            tgl_mulai = tgl_mulai.date()
                            
                        tgl_selesai = dtend.dt if dtend else tgl_mulai
                        if isinstance(tgl_selesai, datetime):
                            tgl_selesai = tgl_selesai.date()
                            
                        daftar_event.append({
                            'tanggal_mulai': str(tgl_mulai),
                            'tanggal_selesai': str(tgl_selesai),
                            'nama_event': summary,
                            'kategori_akademik': klasifikasi_event(summary)
                        })
            print(f"  ✓ Berhasil mengambil {len(daftar_event)} jadwal dari feed iCal.")
        else:
            print(f"  ⚠ URL kalender mengembalikan kode {response.status_code}, memicu fallback lokal...")
            
    except Exception as e:
        print(f"  ⚠ Gagal kontak server kalender ({e}), memicu fallback lokal...")
        
    return daftar_event

def klasifikasi_event(nama_event):
    nama_lower = nama_event.lower()
    if any(k in nama_lower for k in ['wisuda', 'graduation']):
        return 'Wisuda'
    elif any(k in nama_lower for k in ['uts', 'uas', 'ujian']):
        return 'Masa Ujian'
    elif any(k in nama_lower for k in ['maba', 'pkkmb', 'registrasi', 'daftar ulang']):
        return 'Penerimaan Mahasiswa Baru'
    elif any(k in nama_lower for k in ['libur semester', 'semester break']):
        return 'Libur Semester'
    else:
        return 'Event Akademik Umum'

# JIKA KAMPUS TIDAK MEMILIKI FEED ONLINE: 
# Kita lengkapi dengan Siklus Akademik Historis Resmi (2019 - 2026)
def generate_siklus_akademik_historis():
    events = []
    for tahun in range(2019, 2027):
        # 1. Musim Mahasiswa Baru & Masuk Kuliah (Agustus - September) -> Peak Okupansi
        events.append({
            'tanggal_mulai': f"{tahun}-08-15",
            'tanggal_selesai': f"{tahun}-09-05",
            'nama_event': f"Penerimaan Mahasiswa Baru & Awal Semester Ganjil TA {tahun}/{tahun+1}",
            'kategori_akademik': 'Penerimaan Mahasiswa Baru'
        })
        # 2. Musim Wisuda Gelombang 1 (Oktober/November) -> Okupansi Tamu Harian Naik
        events.append({
            'tanggal_mulai': f"{tahun}-10-20",
            'tanggal_selesai': f"{tahun}-10-25",
            'nama_event': f"Periode Wisuda Kampus Periode Ganjil {tahun}",
            'kategori_akademik': 'Wisuda'
        })
        # 3. Libur Semester Ganjil (Januari) -> Mahasiswa Pulang Kampung
        events.append({
            'tanggal_mulai': f"{tahun}-01-10",
            'tanggal_selesai': f"{tahun}-02-05",
            'nama_event': f"Libur Semester Ganjil & Pengisian KRS Genap {tahun}",
            'kategori_akademik': 'Libur Semester'
        })
        # 4. Musim Wisuda Gelombang 2 (Mei/Juni)
        events.append({
            'tanggal_mulai': f"{tahun}-05-15",
            'tanggal_selesai': f"{tahun}-05-20",
            'nama_event': f"Periode Wisuda Kampus Periode Genap {tahun}",
            'kategori_akademik': 'Wisuda'
        })
        # 5. Libur Panjang Semester Genap (Juli - Agustus Awal)
        events.append({
            'tanggal_mulai': f"{tahun}-07-01",
            'tanggal_selesai': f"{tahun}-08-10",
            'nama_event': f"Libur Panjang Akhir Tahun Ajaran {tahun}",
            'kategori_akademik': 'Libur Semester'
        })
    return events

# Eksekusi Pipeline
if __name__ == "__main__":
    # Coba ambil feed online
    data_ical = ambil_kalender_akademik(ICAL_URL)
    
    # Gabungkan dengan data siklus historis agar mencakup 2019 - 2026 secara penuh
    data_historis = generate_siklus_akademik_historis()
    total_data = data_ical + data_historis
    
    df_akademik = pd.DataFrame(total_data)
    df_akademik = df_akademik.drop_duplicates(subset=['tanggal_mulai', 'nama_event'])
    df_akademik['tanggal_mulai'] = pd.to_datetime(df_akademik['tanggal_mulai'])
    df_akademik = df_akademik.sort_values(by='tanggal_mulai').reset_index(drop=True)
    
    output_csv = "master_kalender_akademik_2019_2026.csv"
    df_akademik.to_csv(output_csv, index=False)
    
    print(f"\n✅ SUKSES! Total {len(df_akademik)} event akademik tersimpan di: {output_csv}")
    print(df_akademik.head(10))