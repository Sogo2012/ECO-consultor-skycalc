import streamlit as st
import pandas as pd
import numpy as np
import folium
import os
import plotly.graph_objects as go
import plotly.express as px
from streamlit_folium import st_folium
from streamlit_vtkjs import st_vtkjs

# Importaciones locales
from geometry_utils import generar_nave_3d_vtk
from weather_utils import obtener_estaciones_cercanas, descargar_y_extraer_epw, procesar_datos_clima

# 1. CONFIGURACIÓN DE PÁGINA
st.set_page_config(page_title="SkyCalc 2.0 - Eco Consultor", layout="wide", page_icon="⚡")

st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #007bff; color: white; }
    .stMetric { background-color: white; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

# 2. CARGA DE CATÁLOGO SUNOPTICS
@st.cache_data
def cargar_catalogo():
    data = {
        'Modelo': [
            'Signature 800MD 4040 SGZ', 'Signature 800MD 4040 DGZ',
            'Signature 800MD 4070 SGZ', 'Signature 800MD 4070 DGZ',
            'Signature 800MD 4080 SGZ', 'Signature 800MD 4080 DGZ',
            'Signature 900SC 4080 (Storm)', 'Smoke Vent SVT2 4080 DGZ'
        ],
        'Acristalamiento': ['Sencillo (SGZ)', 'Doble (DGZ)', 'Sencillo (SGZ)', 'Doble (DGZ)', 
                            'Sencillo (SGZ)', 'Doble (DGZ)', 'Storm Class', 'Doble (DGZ)'],
        'VLT': [0.74, 0.67, 0.74, 0.67, 0.74, 0.67, 0.52, 0.64],
        'SHGC': [0.68, 0.48, 0.68, 0.48, 0.68, 0.48, 0.24, 0.31],
        'U_Value': [5.80, 3.20, 5.80, 3.20, 5.80, 3.20, 2.80, 3.20],
        'Ancho_in': [51.25, 51.25, 51.25, 51.25, 52.25, 52.25, 52.25, 52.25],
        'Largo_in': [51.25, 51.25, 87.25, 87.25, 100.25, 100.25, 100.25, 100.25]
    }
    df = pd.DataFrame(data)
    df['Ancho_m'] = (df['Ancho_in'] * 0.0254).round(3)
    df['Largo_m'] = (df['Largo_in'] * 0.0254).round(3)
    return df

df_domos = cargar_catalogo()

# 3. INICIALIZACIÓN DE ESTADO
for key in ['clima_data', 'estacion_seleccionada', 'df_cercanas', 'vtk_path']:
    if key not in st.session_state: st.session_state[key] = None

if 'lat' not in st.session_state: st.session_state.lat = 20.5888
if 'lon' not in st.session_state: st.session_state.lon = -100.3899

def buscar_estaciones():
    with st.spinner("Buscando estaciones cercanas..."):
        df = obtener_estaciones_cercanas(st.session_state.lat, st.session_state.lon)
        st.session_state.df_cercanas = df

# 4. SIDEBAR - CONFIGURACIÓN
with st.sidebar:
    st.markdown("## 🍃 Eco Consultor")
    st.title("SkyCalc 2.0")
    
    with st.expander("📍 1. Ubicación y Clima", expanded=True):
        search_name = st.text_input("Ciudad o país", placeholder="Ej: Madrid, España")
        if st.button("🔍 Buscar"):
            from geopy.geocoders import Nominatim
            try:
                geolocator = Nominatim(user_agent="skycalc_explorer")
                loc = geolocator.geocode(search_name)
                if loc:
                    st.session_state.lat, st.session_state.lon = loc.latitude, loc.longitude
                    buscar_estaciones()
            except: st.error("Error en búsqueda")
        
        st.session_state.lat = st.number_input("Latitud", value=st.session_state.lat, format="%.4f")
        st.session_state.lon = st.number_input("Longitud", value=st.session_state.lon, format="%.4f")
        if st.button("🚀 Buscar en Coordenadas"): buscar_estaciones()

    st.subheader("📐 2. Geometría")
    ancho_nave = st.number_input("Ancho (m)", 10.0, 500.0, 50.0)
    largo_nave = st.number_input("Largo (m)", 10.0, 500.0, 100.0)
    alto_nave = st.number_input("Altura (m)", 3.0, 30.0, 8.0)
    
    st.subheader("☀️ 3. Sunoptics")
    modelo_sel = st.selectbox("Modelo NFRC", df_domos['Modelo'])
    sfr_target = st.slider("Objetivo SFR (%)", 1.0, 10.0, 4.0, 0.1) / 100.0

# 5. TABS PRINCIPALES
tab_config, tab_clima, tab_3d, tab_analitica = st.tabs([
    "🌍 Selección de Clima", "🌤️ Contexto Climático", "📐 Geometría 3D", "📊 Simulación Energética"
])

# --- PESTAÑA 1: CLIMA ---
with tab_config:
    col1, col2 = st.columns([2, 1])
    with col1:
        st.subheader("🌍 Mapa de Estaciones")
        m = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=8)
        folium.Marker([st.session_state.lat, st.session_state.lon], icon=folium.Icon(color='red')).add_to(m)
        
        if st.session_state.df_cercanas is not None:
            for _, row in st.session_state.df_cercanas.iterrows():
                folium.Marker([row['lat'], row['lon']], tooltip=row['name'], icon=folium.Icon(color='blue')).add_to(m)
        
        out = st_folium(m, width=700, height=450, use_container_width=True)
        if out and out.get("last_clicked"):
            st.session_state.lat, st.session_state.lon = out["last_clicked"]["lat"], out["last_clicked"]["lng"]
            buscar_estaciones()
            st.rerun()

    with col2:
        st.subheader("Estaciones")
        if st.session_state.df_cercanas is not None:
            for idx, row in st.session_state.df_cercanas.iterrows():
                if st.button(f"📥 {row['name']} ({row['distancia_km']} km)", key=f"btn_{idx}"):
                    path = descargar_y_extraer_epw(row['URL_ZIP'])
                    if path:
                        st.session_state.clima_data = procesar_datos_clima(path)
                        st.session_state.estacion_seleccionada = row['name']
                        os.remove(path)
                        st.rerun()

# --- PESTAÑA 3: GEOMETRÍA 3D ---
with tab_3d:
    st.subheader("Modelo Paramétrico Sunoptics®")
    
    if st.button("🏗️ Generar Modelo 3D", use_container_width=True):
        with st.spinner("Construyendo geometría Honeybee..."):
            datos_domo = df_domos[df_domos['Modelo'] == modelo_sel].iloc[0]
            vtk_path, num_domos, sfr_real = generar_nave_3d_vtk(
                ancho_nave, largo_nave, alto_nave, sfr_target, 
                datos_domo['Ancho_m'], datos_domo['Largo_m']
            )
            if vtk_path:
                st.session_state.vtk_path = vtk_path
                st.session_state.num_domos_real = num_domos
                st.session_state.sfr_final = sfr_real
                st.session_state.datos_domo_actual = datos_domo

    if st.session_state.vtk_path and os.path.exists(st.session_state.vtk_path):
        c3d, cmet = st.columns([3, 1])
        with c3d:
            with open(st.session_state.vtk_path, "rb") as f:
                # 1. Leemos el archivo y lo guardamos en una variable
                vtk_data = f.read()
            # 2. Pasamos esa variable indicando que es el 'content'
            st_vtkjs(content=vtk_data, key="visor_nave")
        with cmet:
            st.metric("Domos", f"{st.session_state.num_domos_real} uds")
            st.metric("SFR Real", f"{st.session_state.sfr_final*100:.2f} %")
            st.download_button("💾 Descargar .vtkjs", data=open(st.session_state.vtk_path, "rb"), file_name="nave.vtkjs")
    else:
        st.info("Configura la nave y presiona 'Generar Modelo 3D'.")
