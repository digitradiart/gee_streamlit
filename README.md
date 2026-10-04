# ERA5-Land Indonesia dengan Streamlit

Aplikasi ini memvisualisasikan data bulanan dari koleksi
`ECMWF/ERA5_LAND/MONTHLY_AGGR` melalui Earth Engine Python API. Raster tidak
diunduh ke komputer aplikasi: peta memakai tile Earth Engine, sedangkan grafik
mengambil statistik bulanan per wilayah.

## Fitur

- Peta bulanan untuk seluruh Indonesia atau provinsi terpilih.
- Deret waktu bulanan berupa rata-rata spasial di wilayah terpilih.
- Variabel awal: curah hujan, suhu udara 2 m, dan kelembapan tanah lapisan atas.
- Batas provinsi dari `FAO/GAUL/2015/level1`.
- Konversi curah hujan dari meter ke milimeter dan suhu dari Kelvin ke Celsius.
- Cache Streamlit untuk daftar provinsi dan hasil deret waktu.

> GAUL 2015 disertakan untuk prototipe dan mungkin belum mencerminkan pemekaran
> provinsi terbaru. Ganti sumber batas dengan data administratif yang lebih baru
> jika batas terkini diperlukan.

## Persiapan Earth Engine

1. Buat/pilih Google Cloud project, daftarkan untuk Earth Engine, dan aktifkan
   Earth Engine API.
2. Untuk penggunaan lokal, buat virtual environment agar dependensi tidak
   dipasang ke Python sistem (yang pada Debian/Ubuntu biasanya dilindungi oleh
   PEP 668), lalu pasang dependensi dan autentikasi akun yang memiliki akses ke
   Earth Engine:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   earthengine authenticate
   ```

   Jalankan langkah berikutnya dari terminal yang sama, selama `.venv` masih aktif.
   Jika pembuatan environment gagal karena modul `venv` belum tersedia, pasang
   paket sistem `python3-venv` (dan `python3-full` bila diminta), lalu ulangi.

3. Atur project:

   ```bash
   export EE_PROJECT="id-google-cloud-project"
   ```

   Pada Windows PowerShell gunakan:

   ```powershell
   $env:EE_PROJECT = "id-google-cloud-project"
   ```

4. Jalankan aplikasi:

   ```bash
   streamlit run app.py
   ```

Untuk sesi terminal baru, aktifkan environment sebelum menjalankan perintah:

```bash
source .venv/bin/activate
```

Library menggunakan kredensial lokal Earth Engine atau Application Default
Credentials ketika tidak ada kredensial service account pada Streamlit secrets.
Untuk penggunaan lokal, file `.streamlit/secrets.toml` tidak wajib dibuat jika
`EE_PROJECT` sudah diatur di environment dan autentikasi Earth Engine lokal
sudah dilakukan.

## Deployment dengan Streamlit secrets

Untuk platform hosting, konfigurasikan kredensial service account sebagai
Streamlit secrets di dashboard hosting (jangan commit secrets). Contoh:

```toml
[earth_engine]
project_id = "id-google-cloud-project"
service_account = "nama-akun@id-google-cloud-project.iam.gserviceaccount.com"
private_key = """-----BEGIN PRIVATE KEY-----
ISI_PRIVATE_KEY_DI_SECRET_MANAGER
-----END PRIVATE KEY-----"""
```

Project service account harus terdaftar untuk Earth Engine, Earth Engine API
harus aktif, dan akun harus memiliki izin akses yang sesuai. Bila platform
menyediakan Application Default Credentials, gunakan ADC alih-alih menyimpan
private key.

## Catatan analisis

- `total_precipitation_sum` adalah akumulasi bulanan dalam meter pada katalog;
  aplikasi mengonversinya menjadi mm/bulan dan memasker nilai negatif.
- `temperature_2m` merupakan suhu bulanan dalam Kelvin; aplikasi mengubahnya
  menjadi °C.
- `volumetric_soil_water_layer_1` menunjukkan kandungan air volumetrik tanah
  lapisan atas.
- Statistik wilayah dihitung dengan `ee.Reducer.mean()` pada skala 11.132 m.
  Ini merupakan rata-rata spasial grid, bukan total volume atau rata-rata
  berbobot luas geodesik.
- Katalog menyatakan ERA5-Land Monthly Aggregated tersedia sejak 1950 hingga
  kira-kira tiga bulan sebelum waktu terkini. Jika bulan terakhir belum ada,
  pilih bulan sebelumnya.

Referensi:

- [Katalog ERA5-Land Monthly Aggregated](https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_MONTHLY_AGGR)
- [Autentikasi Earth Engine](https://developers.google.com/earth-engine/guides/auth)
- [GAUL 2015 level 1](https://developers.google.com/earth-engine/datasets/catalog/FAO_GAUL_2015_level1)
