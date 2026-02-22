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

# --- IMPORTACIÓN LADYBUG ---
try:
    from ladybug.sunpath import Sunpath
    from ladybug.location import Location
    LADYBUG_READY = True
except ImportError:
    LADYBUG_READY = False

# ==========================================
# 1. CONFIGURACIÓN Y BRANDING
# ==========================================
st.set_page_config(page_title="SkyCalc 2.0 | Eco Consultor", layout="wide")

col_logo, col_tit = st.columns([1, 6])
with col_tit:
    st.title("SkyCalc 2.0: Daylight Autonomy Estimator")
    st.markdown("Powered by **Eco Consultor** & **Sunoptics®** | *Basado en Motor IESNA & SkyCalc 3.0*")
st.divider()

# ==========================================
# 2. BASE DE DATOS MAESTRA (COMPLETA)
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
# 3. MOTOR NASA (CORREGIDO)
# ==========================================
@st.cache_data
def obtener_clima_nasa(lat, lon):
    url = (f"https://power.larc.nasa.gov/api/temporal/hourly/point?"
           f"parameters=ALLSKY_SFC_SW_DWN,T2M&community=RE&longitude={lon}&latitude={lat}"
           f"&start=20230101&end=20231231&format=JSON")
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            data = r.json()['properties']['parameter']
            ghi = np.array(list(data['ALLSKY_SFC_SW_DWN'].values()))[:8760]
            temp = np.array(list(data['T2M'].values()))[:8760]
            return {"lux": ghi * 115, "temp": temp, "ghi": ghi}
    except: return None

# ==========================================
# 4. SIDEBAR INPUTS
# ==========================================
with st.sidebar:
    st.header("⚙️ 1. Geometría")
    ancho = st.number_input("Ancho (m)", 10.0, 200.0, 30.0)
    largo = st.number_input("Largo (m)", 10.0, 200.0, 50.0)
    alto = st.number_input("Altura Libre (m)", 3.0, 25.0, 8.0)
    
    st.header("☀️ 2. Sunoptics")
    modelo_sel = st.selectbox("Modelo NFRC", df_domos['Modelo'])
    sfr_target = st.slider("Objetivo SFR (%)", 1.0, 10.0, 4.0, 0.1) / 100.0
    datos_domo = df_domos[df_domos['Modelo'] == modelo_sel].iloc[0]
    st.info(f"VLT: {datos_domo['VLT']} | SHGC: {datos_domo['SHGC']}")

# Lógica de Horario Industrial (ASHRAE)
horario_uso = np.zeros(8760)
for d in range(365): 
    if d % 7 < 6: 
        for h in range(8, 18): horario_uso[(d * 24) + h] = 1.0

if 'clima_data' not in st.session_state: st.session_state['clima_data'] = None

# ==========================================
# 5. TABS INTERFAZ
# ==========================================
tab_geo, tab_3d, tab_analitica = st.tabs(["📍 Clima", "📐 Geometría", "📊 Análisis Energético"])

with tab_geo:
    st.subheader("Buscador Satelital de Datos")
    col_mapa, col_datos = st.columns([2, 1])
    with col_mapa:
        m = folium.Map(location=[15.0, -90.0], zoom_start=5)
        m.add_child(folium.LatLngPopup())
        map_data = st_folium(m, height=400, width=700, key="mapa_v2")
    
    with col_datos:
        if map_data and map_data['last_clicked']:
            lat, lon = map_data['last_clicked']['lat'], map_data['last_clicked']['lng']
            st.write(f"📍 **Lat:** {lat:.3f} | **Lon:** {lon:.3f}")
            if st.button("Descargar Datos NASA"):
                with st.spinner("Bajando registros 2023..."):
                    st.session_state['clima_data'] = obtener_clima_nasa(lat, lon)
                    st.rerun()
        else: st.info("👈 Haz clic en el mapa.")

with tab_3d:
    # Plano 2D (Distribución simétrica S/2)
    num_domos = max(1, math.ceil((ancho * largo * sfr_target) / (datos_domo['Ancho_m'] * datos_domo['Largo_m'])))
    cols = max(1, round((num_domos * (ancho/largo))**0.5))
    filas = max(1, math.ceil(num_domos / cols))
    
    fig_mat, ax = plt.subplots(figsize=(8, 5))
    ax.add_patch(plt.Rectangle((0, 0), ancho, largo, color='white', ec='black', lw=2))
    dx, dy = ancho / cols, largo / filas
    for i in range(cols):
        for j in range(filas):
            ax.add_patch(plt.Rectangle(((i*dx)+(dx/2)-datos_domo['Ancho_m']/2, (j*dy)+(dy/2)-datos_domo['Largo_m']/2), 
                                       datos_domo['Ancho_m'], datos_domo['Largo_m'], color='#3498DB', alpha=0.7))
    plt.axis('equal')
    st.pyplot(fig_mat)

with tab_analitica:
    if st.session_state['clima_data'] is not None:
        lux = st.session_state['clima_data']['lux']
        temp = st.session_state['clima_data']['temp']
        
        # --- CÁLCULOS SKYCALC ---
        cu = 0.85 * (math.exp(-0.12 * ((5 * alto * (ancho + largo)) / (ancho * largo))))
        e_in = lux * sfr_target * 0.85 * 0.9 * datos_domo['VLT'] * cu
        pot_kw = (ancho * largo * 8.0) / 1000.0
        c_base = pot_kw * horario_uso
        c_proy = (np.clip(300 - e_in, 0, 300) / 300) * pot_kw * horario_uso
        
        # --- VISUALES RESTAURADAS (DASHBOARD) ---
        st.subheader("Reporte Preliminar de Eficiencia Energética")
        c1, c2 = st.columns(2)
        with c1:
            fig_bar = go.Figure(data=[
                go.Bar(name='Sin Domos', x=['Consumo'], y=[np.sum(c_base)], marker_color='#E74C3C', text=[f"{np.sum(c_base):,.0f} kWh"], textposition='auto'),
                go.Bar(name='Con Sunoptics', x=['Consumo'], y=[np.sum(c_proy)], marker_color='#2ECC71', text=[f"{np.sum(c_proy):,.0f} kWh"], textposition='auto')
            ])
            fig_bar.update_layout(title="Comparativa de Consumo (kWh/año)", height=400, barmode='group', template="plotly_white")
            st.plotly_chart(fig_bar, use_container_width=True)
            
        with c2:
            sda = (np.sum((e_in >= 300) & (horario_uso == 1.0)) / np.sum(horario_uso)) * 100
            fig_sda = go.Figure(go.Indicator(
                mode="gauge+number", value=sda, title={'text': "Autonomía Lumínica (sDA)"},
                number={'suffix': "%"},
                gauge={'axis': {'range': [0, 100]}, 'bar': {'color': "#3498DB"},
                       'steps': [{'range': [75, 100], 'color': "#A9DFBF"}]}
            ))
            fig_sda.update_layout(height=400, template="plotly_white")
            st.plotly_chart(fig_sda, use_container_width=True)

        # --- CURVA DE OPTIMIZACIÓN CON TOOLTIPS AGRUPADOS ---
        st.markdown("### Análisis de Optimización Energética (Flujo Dividido)")
        sfr_range = np.linspace(0.01, 0.10, 10)
        ahorros, cargas_hvac, netos = [], [], []
        
        for s in sfr_range:
            e_t = lux * s * 0.7 * cu
            c_t = (np.clip(300 - e_t, 0, 300) / 300) * pot_kw * horario_uso
            ah_luz = np.sum(c_base) - np.sum(c_t)
            ahorros.append(ah_luz)
            # Impacto HVAC simplificado
            penal_h = np.sum(np.where(temp > 24, (st.session_state['clima_data']['ghi'] * (ancho*largo*s) * datos_domo['SHGC'])/3000, 0))
            cargas_hvac.append(-penal_h)
            netos.append(ah_luz - penal_h)

        fig_opt = go.Figure()
        fig_opt.add_trace(go.Scatter(x=sfr_range*100, y=ahorros, name='Ahorro Luz', line=dict(color='#3498db', dash='dash'), hovertemplate='%{y:,.0f} kWh<extra></extra>'))
        fig_opt.add_trace(go.Scatter(x=sfr_range*100, y=cargas_hvac, name='Impacto HVAC', line=dict(color='#e74c3c'), hovertemplate='%{y:,.0f} kWh<extra></extra>'))
        fig_opt.add_trace(go.Scatter(x=sfr_range*100, y=netos, name='<b>NETO TOTAL</b>', line=dict(color='#2ecc71', width=4), hovertemplate='<b>%{y:,.0f} kWh</b><extra></extra>'))
        
        fig_opt.update_layout(xaxis_title="SFR %", yaxis_title="Energía (kWh)", hovermode="x unified", template="plotly_white", height=500)
        st.plotly_chart(fig_opt, use_container_width=True)
    else:
        st.warning("⚠️ Selecciona una ubicación en la pestaña Clima primero.")
