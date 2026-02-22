import streamlit as st
import pandas as pd
import numpy as np
import math
import matplotlib.pyplot as plt
import plotly.graph_objects as go
import plotly.express as px
import folium
from streamlit_folium import st_folium
import datetime
import requests

# --- IMPORTACIÓN SEPARADA PARA EVITAR CAÍDAS ---
try:
    from ladybug.sunpath import Sunpath
    from ladybug.location import Location
    LADYBUG_READY = True
except ImportError:
    LADYBUG_READY = False

# ==========================================
# 1. CONFIGURACIÓN DE LA APP Y BRANDING
# ==========================================
st.set_page_config(page_title="SkyCalc 2.0 | Eco Consultor", layout="wide", initial_sidebar_state="expanded")

col1, col2 = st.columns([1, 6])
with col2:
    st.title("SkyCalc 2.0: Daylight Autonomy Estimator")
    st.markdown("Powered by **Eco Consultor** & **Sunoptics®** | *Ingeniería Lumínica, Térmica y BEM*")
st.divider()

# ==========================================
# 2. BASE DE DATOS SUNOPTICS
# ==========================================
@st.cache_data
def cargar_catalogo():
    data = {
        'Modelo': [
            'Signature 800MD 4040 SGZ', 'Signature 800MD 4040 DGZ',
            'Signature 800MD 4070 SGZ', 'Signature 800MD 4070 DGZ',
            'Signature 800MD 4080 SGZ', 'Signature 800MD 4080 DGZ',
            'Signature 900SC 4080 (Storm)', 'Smoke Vent SVT2 4080 DGZ'
        ],
        'VLT': [0.74, 0.67, 0.74, 0.67, 0.74, 0.67, 0.52, 0.64],
        'SHGC': [0.68, 0.48, 0.68, 0.48, 0.68, 0.48, 0.24, 0.31],
        'U_Value': [1.20, 0.72, 1.20, 0.72, 1.20, 0.72, 0.58, 0.72],
        'Ancho_in': [51.25, 51.25, 51.25, 51.25, 52.25, 52.25, 52.25, 52.25],
        'Largo_in': [51.25, 51.25, 87.25, 87.25, 100.25, 100.25, 100.25, 100.25]
    }
    df = pd.DataFrame(data)
    df['Ancho_m'] = (df['Ancho_in'] * 0.0254).round(3)
    df['Largo_m'] = (df['Largo_in'] * 0.0254).round(3)
    return df

df_domos = cargar_catalogo()

# ==========================================
# 3. MOTOR CLIMÁTICO NASA
# ==========================================
@st.cache_data
def obtener_clima_detallado_nasa(lat, lon):
    parametros = "ALLSKY_SFC_SW_DWN,DIFF,ALLSKY_SFC_SW_DNI,CLD_OT,T2M"
    url = (f"https://power.larc.nasa.gov/api/temporal/hourly/point?"
           f"parameters={parametros}&community=RE&longitude={lon}&latitude={lat}"
           f"&start=20230101&end=20231231&format=JSON")
    try:
        r = requests.get(url, timeout=15)
        data = r.json()['properties']['parameter']
        return {
            "lux": np.array(list(data['ALLSKY_SFC_SW_DWN'].values()))[:8760] * 115,
            "nubes": np.array(list(data['CLD_OT'].values()))[:8760],
            "temp": np.array(list(data['T2M'].values()))[:8760]
        }
    except: return None

# ==========================================
# 4. SIDEBAR Y LÓGICA BASE
# ==========================================
with st.sidebar:
    st.header("⚙️ 1. Geometría")
    ancho = st.number_input("Ancho (m)", 10.0, 200.0, 30.0)
    largo = st.number_input("Largo (m)", 10.0, 200.0, 50.0)
    alto = st.number_input("Altura (m)", 3.0, 25.0, 8.0)
    
    st.header("☀️ 2. Sunoptics")
    modelo_sel = st.selectbox("Modelo NFRC", df_domos['Modelo'])
    sfr_target = st.slider("Objetivo SFR (%)", 1.0, 10.0, 4.0, 0.1) / 100.0
    datos_domo = df_domos[df_domos['Modelo'] == modelo_sel].iloc[0]

area_nave = ancho * largo
cu_proyecto = 0.85 * (math.exp(-0.12 * ((5 * alto * (ancho + largo)) / (ancho * largo))))
horario_uso = np.zeros(8760)
for d in range(365): 
    if d % 7 < 6: 
        for h in range(8, 18): horario_uso[(d * 24) + h] = 1.0

if 'clima_data' not in st.session_state:
    st.session_state['clima_data'] = None

# ==========================================
# 5. TABS INTERFAZ
# ==========================================
tab_geo, tab_3d, tab_analitica = st.tabs(["📍 Contexto Climático", "📐 Distribución Geométrica", "📊 Análisis Energético"])

with tab_geo:
    st.subheader("Buscador Satelital NASA POWER")
    
    # --- VALIDACIÓN DE REGISTROS ---
    if st.session_state['clima_data']:
        st.success(f"✅ Conexión exitosa: {len(st.session_state['clima_data']['lux'])} registros horarios recibidos.")
    else:
        st.info("💡 Haz clic en el mapa para cargar datos climáticos reales de la NASA.")

    col_mapa, col_datos = st.columns([2, 1])
    with col_mapa:
        m = folium.Map(location=[15.0, -90.0], zoom_start=5) # Zona Centroamérica/México
        m.add_child(folium.LatLngPopup())
        map_data = st_folium(m, height=400, width=700, key="mapa_clima")
    
    with col_datos:
        if map_data and map_data['last_clicked']:
            lat, lon = map_data['last_clicked']['lat'], map_data['last_clicked']['lng']
            st.write(f"📍 **Lat:** {lat:.3f} | **Lon:** {lon:.3f}")
            if st.button("Actualizar Datos NASA"):
                with st.spinner("Conectando con satélite..."):
                    st.session_state['clima_data'] = obtener_clima_detallado_nasa(lat, lon)
                    st.rerun()
            
            if st.session_state['clima_data'] and LADYBUG_READY:
                loc = Location("Proyecto", lat, lon, 0)
                sp = Sunpath.from_location(loc)
                sol = sp.calculate_sun(6, 21, 12)
                st.metric("Altitud Solar Máx.", f"{round(sol.altitude, 1)}°")

    if st.session_state['clima_data']:
        df_n = pd.DataFrame({'Mes': pd.date_range("2023-01-01", periods=8760, freq="h").month,
                             'Nubes': st.session_state['clima_data']['nubes']}).groupby('Mes').mean()
        st.plotly_chart(px.bar(df_n, title="Nubosidad Media Mensual (Satelital)", color_discrete_sequence=['#95a5a6']), use_container_width=True)

with tab_3d:
    st.subheader("Plano de Techos (Distribución Matricial)")
    num_domos = max(1, math.ceil((area_nave * sfr_target) / (datos_domo['Ancho_m'] * datos_domo['Largo_m'])))
    cols = max(1, round((num_domos * (ancho/largo))**0.5))
    filas = max(1, math.ceil(num_domos / cols))
    
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.set_facecolor('#f0f0f0')
    ax.add_patch(plt.Rectangle((0, 0), ancho, largo, color='white', ec='black', lw=2))
    dx, dy = ancho / cols, largo / filas
    for i in range(cols):
        for j in range(filas):
            ax.add_patch(plt.Rectangle(((i*dx)+(dx/2)-datos_domo['Ancho_m']/2, (j*dy)+(dy/2)-datos_domo['Largo_m']/2), 
                                       datos_domo['Ancho_m'], datos_domo['Largo_m'], color='#00aaff', alpha=0.7))
    plt.axis('equal')
    st.pyplot(fig)
    st.write(f"**Total de domos instalados:** {cols*filas} | **SFR Real:** {((cols*filas*datos_domo['Ancho_m']*datos_domo['Largo_m'])/area_nave)*100:.2f}%")

with tab_analitica:
    if st.session_state['clima_data']:
        lux = st.session_state['clima_data']['lux']
        temp = st.session_state['clima_data']['temp']
        e_in = lux * sfr_target * (0.85 * 0.9 * datos_domo['VLT']) * cu_proyecto
        
        # Dashboard de KPIs
        k1, k2, k3 = st.columns(3)
        pot_kw = (area_nave * 8.0) / 1000.0
        c_base = np.sum(pot_kw * horario_uso)
        c_proy = np.sum((np.clip(300 - e_in, 0, 300) / 300) * pot_kw * horario_uso)
        
        k1.metric("Ahorro Energético", f"{((c_base-c_proy)/c_base)*100:.1f}%", f"-{c_base-c_proy:,.0f} kWh/año")
        k2.metric("Autonomía (sDA)", f"{(np.sum((e_in >= 300) & (horario_uso == 1.0)) / np.sum(horario_uso))*100:.1f}%")
        k3.metric("Iluminancia Promedio", f"{np.mean(e_in[e_in>0]):,.0f} lux")

        st.plotly_chart(px.line(e_in[8:18+24*10], title="Desempeño Lumínico (Primeros 10 días laborables)"), use_container_width=True)
    else:
        st.warning("⚠️ Sin datos climáticos. Por favor, selecciona un punto en la primera pestaña.")

st.divider()
st.info("Desarrollado para Eco Consultor por la unidad de BEM & Ingeniería Lumínica.")
