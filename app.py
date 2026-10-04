from __future__ import annotations

import os
from datetime import date
from typing import Any

import ee
import folium
import pandas as pd
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError
from streamlit_folium import st_folium


st.set_page_config(
    page_title="ERA5-Land Indonesia",
    page_icon="🌦️",
    layout="wide",
)

COLLECTION_ID = "ECMWF/ERA5_LAND/MONTHLY_AGGR"
PROVINCES_ID = "FAO/GAUL/2015/level1"
SCALE_METERS = 11_132

VARIABLES: dict[str, dict[str, Any]] = {
    "Curah hujan": {
        "band": "total_precipitation_sum",
        "unit": "mm/bulan",
        "min": 0.0,
        "max": 500.0,
        "palette": ["#fff7bc", "#fec44f", "#fe9929", "#ec7014", "#cc4c02", "#662506"],
        "multiplier": 1000.0,
        "offset": 0.0,
        "mask_negative": True,
        "description": (
            "Akumulasi bulanan; nilai katalog dalam meter dikonversi ke milimeter. "
            "Nilai negatif dari artefak data dimasker."
        ),
    },
    "Suhu udara 2 m": {
        "band": "temperature_2m",
        "unit": "°C",
        "min": 18.0,
        "max": 34.0,
        "palette": ["#313695", "#74add1", "#ffffbf", "#fdae61", "#a50026"],
        "multiplier": 1.0,
        "offset": -273.15,
        "mask_negative": False,
        "description": "Suhu rata-rata bulanan; dikonversi dari Kelvin ke Celsius.",
    },
    "Kelembapan tanah lapisan atas": {
        "band": "volumetric_soil_water_layer_1",
        "unit": "m³/m³",
        "min": 0.0,
        "max": 0.5,
        "palette": ["#fff7fb", "#c51b8a", "#7a0177", "#023858"],
        "multiplier": 1.0,
        "offset": 0.0,
        "mask_negative": False,
        "description": "Kandungan air volumetrik pada lapisan tanah paling atas.",
    },
}


def _first_day_of_month(value: date) -> date:
    return date(value.year, value.month, 1)


def _next_month(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


def _latest_expected_month() -> date:
    today = date.today()
    month_number = today.month - 3
    year = today.year
    if month_number <= 0:
        month_number += 12
        year -= 1
    return date(year, month_number, 1)


def _initialize_earth_engine() -> str:
    try:
        config = st.secrets.get("earth_engine", {})
    except StreamlitSecretNotFoundError:
        config = {}

    project_id = config.get("project_id") or os.getenv("EE_PROJECT")
    if not isinstance(project_id, str) or not project_id:
        st.error(
            "Project Google Cloud Earth Engine belum dikonfigurasi. "
            "Lihat README.md untuk pengaturan lokal atau deployment."
        )
        st.stop()
        raise RuntimeError("Project Earth Engine wajib dikonfigurasi.")

    try:
        service_account = config.get("service_account")
        private_key = config.get("private_key")
        if service_account and private_key:
            credentials = ee.ServiceAccountCredentials(
                service_account,
                key_data=private_key,
            )
            ee.Initialize(credentials=credentials, project=project_id)
        else:
            ee.Initialize(project=project_id)
    except Exception as error:
        st.error(
            "Autentikasi atau inisialisasi Earth Engine gagal. Pastikan project "
            "terdaftar untuk Earth Engine, API aktif, dan kredensial memiliki akses. "
            f"Detail: {error}"
        )
        st.stop()
        raise RuntimeError("Inisialisasi Earth Engine gagal.") from error

    return project_id


def _indonesia_provinces() -> ee.FeatureCollection:
    provinces = ee.FeatureCollection(PROVINCES_ID).filter(
        ee.Filter.eq("ADM0_NAME", "Indonesia")
    )
    if provinces.size().getInfo() == 0:
        raise RuntimeError(
            f"Tidak ditemukan batas Indonesia pada koleksi {PROVINCES_ID}."
        )
    return provinces


@st.cache_data(ttl=86_400, show_spinner=False)
def _province_names(project_id: str) -> list[str]:
    del project_id
    provinces = _indonesia_provinces().filter(
        ee.Filter.notNull(["ADM1_NAME"])
    )
    names = provinces.aggregate_array("ADM1_NAME").distinct().sort().getInfo()
    if not names:
        raise RuntimeError("Daftar nama provinsi kosong pada dataset batas.")
    return names


def _display_image(image: ee.Image, variable: dict[str, Any]) -> ee.Image:
    source = image.select(variable["band"])
    displayed = source.multiply(variable["multiplier"]).add(variable["offset"])
    if variable["mask_negative"]:
        displayed = displayed.updateMask(source.gte(0))
    return displayed.rename("value")


def _tile_url(image: ee.Image) -> str:
    map_id = image.getMapId()
    tile_url = map_id["tile_fetcher"].url_format
    if not isinstance(tile_url, str):
        raise RuntimeError("Earth Engine tidak mengembalikan URL tile peta.")
    return tile_url


def _monthly_map(
    project_id: str,
    region_name: str,
    selected_month: date,
    variable: dict[str, Any],
) -> tuple[folium.Map, str]:
    del project_id
    provinces = _indonesia_provinces()
    region_features = (
        provinces
        if region_name == "Seluruh Indonesia"
        else provinces.filter(ee.Filter.eq("ADM1_NAME", region_name))
    )
    region = region_features.geometry()

    start = _first_day_of_month(selected_month)
    end = _next_month(start)
    images = (
        ee.ImageCollection(COLLECTION_ID)
        .filterDate(start.isoformat(), end.isoformat())
        .select(variable["band"])
    )
    if images.size().getInfo() == 0:
        raise LookupError(
            f"Tidak ada citra untuk {start:%B %Y}. Dataset biasanya tertinggal "
            "sekitar tiga bulan dari waktu terkini; coba pilih bulan yang lebih lama."
        )

    image = _display_image(ee.Image(images.first()), variable).clip(region)
    visualized = image.visualize(
        min=variable["min"],
        max=variable["max"],
        palette=variable["palette"],
    )
    boundary = (
        ee.Image.constant(0)
        .byte()
        .paint(region_features, 1, 2)
        .selfMask()
        .visualize(min=0, max=1, palette=["#202020"])
    )

    center = region.centroid(maxError=1_000).coordinates().getInfo()
    map_view = folium.Map(
        location=[center[1], center[0]],
        zoom_start=4 if region_name == "Seluruh Indonesia" else 6,
        tiles="CartoDB positron",
        control_scale=True,
    )
    folium.TileLayer(
        tiles=_tile_url(visualized),
        attr="Google Earth Engine",
        name=f"{variable['band']} — {start:%Y-%m}",
        overlay=True,
    ).add_to(map_view)
    folium.TileLayer(
        tiles=_tile_url(boundary),
        attr="Batas administratif GAUL 2015",
        name="Batas provinsi",
        overlay=True,
    ).add_to(map_view)
    folium.LayerControl(collapsed=False).add_to(map_view)
    return map_view, f"{start:%B %Y}"


@st.cache_data(ttl=3_600, show_spinner="Menghitung statistik bulanan di Earth Engine…")
def _monthly_series(
    project_id: str,
    region_name: str,
    band: str,
    multiplier: float,
    offset: float,
    mask_negative: bool,
    start_date: str,
    end_date_exclusive: str,
) -> list[dict[str, Any]]:
    del project_id
    provinces = _indonesia_provinces()
    region_features = (
        provinces
        if region_name == "Seluruh Indonesia"
        else provinces.filter(ee.Filter.eq("ADM1_NAME", region_name))
    )
    region = region_features.geometry()
    collection = (
        ee.ImageCollection(COLLECTION_ID)
        .filterDate(start_date, end_date_exclusive)
        .select(band)
        .sort("system:time_start")
    )
    image_list = collection.toList(collection.size())

    def image_to_feature(image_object: Any) -> ee.Feature:
        image = ee.Image(image_object)
        source = image.select(band)
        displayed = source.multiply(multiplier).add(offset)
        if mask_negative:
            displayed = displayed.updateMask(source.gte(0))
        displayed = displayed.rename("value")
        statistics = displayed.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=region,
            scale=SCALE_METERS,
            maxPixels=100_000_000,
        )
        return ee.Feature(
            None,
            {
                "month": image.date().format("YYYY-MM"),
                "value": statistics.get("value"),
            },
        )

    table = ee.FeatureCollection(image_list.map(image_to_feature)).getInfo()
    return [
        feature["properties"]
        for feature in table["features"]
        if feature.get("properties", {}).get("value") is not None
    ]


st.title("ERA5-Land bulanan — Indonesia")
st.write(
    "Jelajahi pola spasial dan temporal variabel iklim ERA5-Land. "
    "Pemrosesan raster dan perhitungan statistik dilakukan di Google Earth Engine."
)

project_id = _initialize_earth_engine()
province_names: list[str] = []
try:
    province_names = _province_names(project_id)
except Exception as error:
    st.error(f"Gagal memuat daftar provinsi dari Earth Engine. Detail: {error}")
    st.stop()

latest_month = _latest_expected_month()
default_start = date(latest_month.year - 5, latest_month.month, 1)

with st.sidebar:
    st.header("Pengaturan")
    variable_name = st.selectbox("Variabel", list(VARIABLES))
    region_name = st.selectbox(
        "Wilayah",
        ["Seluruh Indonesia", *province_names],
        help="Batas provinsi menggunakan dataset GAUL 2015.",
    )
    selected_month = st.date_input(
        "Bulan pada peta",
        value=latest_month,
        min_value=date(1950, 1, 1),
        max_value=latest_month,
        help="Pilih tanggal di bulan yang ingin dipetakan.",
    )
    temporal_range = st.date_input(
        "Rentang grafik temporal",
        value=(default_start, latest_month),
        min_value=date(1950, 1, 1),
        max_value=latest_month,
        help="Statistik dihitung untuk seluruh bulan yang tercakup dalam rentang ini.",
    )

variable = VARIABLES[variable_name]
if isinstance(temporal_range, tuple) and len(temporal_range) == 2:
    range_start, range_end = temporal_range
else:
    st.warning("Pilih tanggal awal dan akhir untuk rentang grafik.")
    st.stop()
    raise RuntimeError("Rentang tanggal temporal tidak lengkap.")

series_start = _first_day_of_month(range_start)
series_end = _next_month(_first_day_of_month(range_end))

st.caption(
    f"Band: `{variable['band']}` · Satuan: {variable['unit']} · "
    f"Resolusi analisis statistik: sekitar {SCALE_METERS / 1_000:.1f} km"
)
st.info(variable["description"])
st.warning(
    "Batas wilayah pada prototipe ini memakai GAUL 2015; beberapa pemekaran "
    "provinsi Indonesia terbaru mungkin belum tercakup. Curah hujan ERA5-Land "
    "juga dapat memiliki nilai akumulasi negatif atau ekstrem akibat artefak "
    "data; nilai negatif dimasker pada visualisasi ini."
)

map_column, chart_column = st.columns([1.35, 1])
with map_column:
    st.subheader("Peta spasial")
    try:
        with st.spinner("Meminta tile peta dari Earth Engine…"):
            map_view, displayed_month = _monthly_map(
                project_id,
                region_name,
                selected_month,
                variable,
            )
        st_folium(map_view, height=620)
        st.caption(
            f"{variable_name} untuk {displayed_month}; rentang warna "
            f"{variable['min']:g}–{variable['max']:g} {variable['unit']}."
        )
    except LookupError as error:
        st.warning(str(error))
    except Exception as error:
        st.error(f"Gagal membuat peta Earth Engine. Detail: {error}")

with chart_column:
    st.subheader("Deret waktu bulanan")
    try:
        rows = _monthly_series(
            project_id,
            region_name,
            variable["band"],
            variable["multiplier"],
            variable["offset"],
            variable["mask_negative"],
            series_start.isoformat(),
            series_end.isoformat(),
        )
        if rows:
            chart_data = pd.DataFrame(rows).rename(
                columns={"month": "Bulan", "value": f"Rata-rata ({variable['unit']})"}
            )
            chart_data = chart_data.set_index("Bulan")
            st.line_chart(chart_data)
            st.caption(
                f"Rata-rata nilai grid di wilayah {region_name}, "
                f"{series_start:%Y-%m} hingga sebelum {series_end:%Y-%m}. "
                "Bulan tanpa data tidak ditampilkan."
            )
            st.dataframe(chart_data, use_container_width=True)
        else:
            st.info("Tidak ada statistik untuk wilayah dan rentang tanggal ini.")
    except Exception as error:
        st.error(f"Gagal menghitung deret waktu di Earth Engine. Detail: {error}")
