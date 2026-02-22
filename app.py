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
import os
from weather_utils import obtener_estaciones_cercanas, descargar_y_extraer_epw

# --- 1. CONFIGURACIÓN INICIAL (VITAL PARA EVITAR ERRORES) ---
st.set_page_config(page_title="SkyCalc 2.0 | Eco Consultor", layout="wide")

# Inicializamos el estado de la memoria al principio de todo
if 'clima_data' not in st.session_state:
    st.session_state['clima_data'] = None

# --- IMPORTACIÓN LADYBUG TOOLS ---
try:
    from ladybug.sunpath import Sunpath
    from ladybug.location import Location
    from ladybug.epw import EPW
    LADYBUG_READY = True
except ImportError:
    LADYBUG_READY = False

# ==========================================
# 2. BASE DE DATOS MAESTRA (SENSIBILIZADA)
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
        'Acristalamiento': ['Sencillo (SGZ)', 'Doble (DGZ)', 'Sencillo (SGZ)', 'Doble (DGZ)', 
                            'Sencillo (SGZ)', 'Doble (DGZ)', 'Storm Class', 'Doble (DGZ)'],
        'VLT': [0.74, 0.67, 0.74, 0.67, 0.74, 0.67, 0.52, 0.64],
        'SHGC': [0.68, 0.48, 0.68, 0.48, 0.68, 0.48, 0.24, 0.31],
        # SENSIBILIZACIÓN: SGZ = 5.8 (Como policarbonato delgado) | DGZ = 3.2 (Doble lente)
        'U_Value': [5.80, 3.20, 5.80, 3.20, 5.80, 3.20, 2.80, 3.20],
        'Ancho_in': [51.25, 51.25, 51.25, 51.25, 52.25, 52.25, 52.25, 52.25],
        'Largo_in': [51.25, 51.25, 87.25, 87.25, 100.25, 100.25, 100.25, 100.25]
    }
    df = pd.DataFrame(data)
    df['Ancho_m'] = (df['Ancho_in'] * 0.0254).round(3)
    df['Largo_m'] = (df['Largo_in'] * 0.0254).round(3)
    return df

# Ejecución global inmediata para evitar el NameError
df_domos = cargar_catalogo()

# ==========================================
# 3. MOTOR NASA POWER API (Backup)
# ==========================================
@st.cache_data
def obtener_clima_nasa(lat, lon):
    parametros = "ALLSKY_SFC_SW_DWN,T2M"
    url = (f"https://power.larc.nasa.gov/api/temporal/hourly/point?"
           f"parameters={parametros}&community=RE&longitude={lon}&latitude={lat}"
           f"&start=20230101&end=20231231&format=JSON")
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            data = r.json()['properties']['parameter']
            ghi = np.array(list(data['ALLSKY_SFC_SW_DWN'].values()))[:8760]
            temp = np.array(list(data['T2M'].values()))[:8760]
            return {"lux": ghi * 115, "temp": temp, "ghi": ghi, "dni": ghi * 0.7, "dhi": ghi * 0.3} # Fallback simple
    except:
        return None

# ==========================================
# 4. INTERFAZ: SIDEBAR E IDENTIFICACIÓN ASHRAE
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

    st.header("📚 3. Nave ASHRAE")
    mapa_programas = {"Warehouse": 6.5, "Manufacturing": 12.0, "Retail": 16.0}
    mapa_materiales = {
        "Membrana Genérica (Aislada)": "Generic Roof Membrane", 
        "Concreto Pesado": "Generic HW Concrete", 
        "Concreto Ligero": "Generic LW Concrete"
    }
    
    uso_edificio = st.selectbox("Uso", list(mapa_programas.keys()))
    material_techo = st.selectbox("Cubierta", list(mapa_materiales.keys()))

# --- LOGICA DE EXTRACCIÓN LBT ---
try:
    from honeybee_energy.lib.materials import opaque_material_by_identifier
    lpd_real = mapa_programas[uso_edificio]
    nombre_material_lbt = mapa_materiales[material_techo]
    mat = opaque_material_by_identifier(nombre_material_lbt)
    u_techo_real = 1 / ((mat.thickness / mat.conductivity) + 0.15) 
    st.sidebar.success(f"✅ Conectado a LBT\nLPD: {lpd_real} W/m²\nU-Roof: {u_techo_real:.3f} W/m²K")
except Exception as e:
    lpd_real, u_techo_real = 8.0, 0.5
    st.sidebar.error(f"Error LBT: {e}")

# --- HORARIO (VITAL) ---
horario_uso = np.zeros(8760)
for d in range(365): 
    if d % 7 < 6: 
        for h in range(8, 18): horario_uso[(d * 24) + h] = 1.0

# ==========================================
# 5. TABS INTERFAZ
# ==========================================
st.title("SkyCalc 2.0: Daylight Autonomy Estimator")
st.markdown("Powered by **Eco Consultor** & **Sunoptics®**")
st.divider()

tab_geo, tab_3d, tab_analitica = st.tabs(["📍 Clima", "📐 Geometría", "📊 Análisis Energético"])

with tab_geo:
    st.subheader("Buscador de Estaciones Climáticas (EPW)")
    col_mapa, col_datos = st.columns([2, 1])
    
    # Obtener ubicación actual del mapa o por defecto
    centro_lat, centro_lon = 15.0, -90.0
    if map_data := st.session_state.get('map_data_v3'):
        if map_data.get('last_clicked'):
            centro_lat, centro_lon = map_data['last_clicked']['lat'], map_data['last_clicked']['lng']

    with col_mapa:
        m = folium.Map(location=[centro_lat, centro_lon], zoom_start=5)
        
        # Mostrar estaciones en el mapa
        df_estaciones = obtener_estaciones_cercanas(centro_lat, centro_lon, top_n=10)
        for _, st_row in df_estaciones.iterrows():
            folium.Marker(
                location=st_row['location'],
                popup=f"{st_row['name']} ({st_row['distancia_km']} km)",
                icon=folium.Icon(color='blue', icon='info-sign')
            ).add_to(m)
            
        m.add_child(folium.LatLngPopup())
        map_data = st_folium(m, height=400, width=700, key="mapa_v3")
        st.session_state['map_data_v3'] = map_data
    
    with col_datos:
        if map_data and map_data['last_clicked']:
            lat, lon = map_data['last_clicked']['lat'], map_data['last_clicked']['lng']
            st.write(f"📍 **Proyecto:** {lat:.3f}, {lon:.3f}")
            
            st.markdown("---")
            st.write("🛰️ **Estaciones más cercanas:**")
            df_cercanas = obtener_estaciones_cercanas(lat, lon)
            st.dataframe(df_cercanas[['name', 'distancia_km']], hide_index=True)
            
            mejor_estacion = df_cercanas.iloc[0]
            if st.button(f"Usar estación: {mejor_estacion['name']}"):
                with st.spinner(f"Descargando datos de {mejor_estacion['name']}..."):
                    try:
                        epw_path = descargar_y_extraer_epw(mejor_estacion['epw'])
                        epw = EPW(epw_path)
                        
                        # Extraer vectores de 8760
                        temp = np.array(epw.dry_bulb_temperature.values)
                        ghi = np.array(epw.global_horizontal_radiation.values)
                        dni = np.array(epw.direct_normal_radiation.values)
                        dhi = np.array(epw.diffuse_horizontal_radiation.values)
                        
                        # Conversión aproximada de GHI a LUX (Eficacia luminosa promedio)
                        # Ladybug tools suele usar modelos más complejos pero aquí simplificamos
                        lux = ghi * 115 
                        
                        st.session_state['clima_data'] = {
                            "lux": lux, 
                            "temp": temp, 
                            "ghi": ghi, 
                            "dni": dni, 
                            "dhi": dhi,
                            "estacion": mejor_estacion['name'],
                            "distancia": mejor_estacion['distancia_km']
                        }
                        st.success(f"✅ Datos cargados de {mejor_estacion['name']}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al procesar EPW: {e}")
            
            if st.button("Fallback: NASA POWER"):
                with st.spinner("Conectando con satélites NASA..."):
                    st.session_state['clima_data'] = obtener_clima_nasa(lat, lon)
                    st.rerun()
        else:
            st.info("Presiona 'Localizar Estaciones' en el sidebar para ver el mapa.")

    with col2:
        st.subheader("Estaciones Disponibles")
        if 'df_cercanas' in st.session_state:
            st.write("Selecciona la estación para descargar datos:")
            for idx, row in st.session_state.df_cercanas.iterrows():
                if st.button(f"📥 {row['Estación']} ({row['Distancia (km)']} km)", key=f"btn_{idx}"):
                    with st.spinner(f"Descargando datos de {row['Estación']}..."):
                        path = descargar_y_extraer_epw(row['URL_ZIP'])
                        if path:
                            try:
                                data = procesar_datos_clima(path)
                                st.session_state.clima_data = data
                                st.session_state.estacion_seleccionada = row['Estación']
                                st.success("✅ Datos cargados correctamente.")
                            finally:
                                # Limpiar archivo temporal
                                if os.path.exists(path):
                                    os.remove(path)
        
        st.divider()
        st.subheader("Milla Cero (NASA POWER)")
        if st.button("🚀 Usar Datos Satelitales (Alta Precisión)"):
            st.warning("Integrando con API de NASA POWER... (Simulado para esta demo)")
            st.session_state.estacion_seleccionada = "NASA POWER Satelital"
            st.info("👈 Haz clic en el mapa para localizar tu proyecto.")
            
        if st.session_state['clima_data']:
            st.success(f"Clima activo: {st.session_state['clima_data'].get('estacion', 'NASA Satellite')}")

with tab_3d:
    area_nave = ancho * largo
    num_domos = max(1, math.ceil((area_nave * sfr_target) / (datos_domo['Ancho_m'] * datos_domo['Largo_m'])))
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
        ghi = st.session_state['clima_data']['ghi']
        
        cu = 0.85 * (math.exp(-0.12 * ((5 * alto * (ancho + largo)) / (ancho * largo))))
        e_in = lux * sfr_target * 0.75 * 0.9 * datos_domo['VLT'] * cu
        pot_total_kw = (ancho * largo * lpd_real) / 1000.0
        c_base = pot_total_kw * horario_uso
        c_proy = (np.clip(300 - e_in, 0, 300) / 300) * pot_total_kw * horario_uso
        
        st.subheader("Reporte de Eficiencia Energética")
        c1, c2 = st.columns(2)
        with c1:
            fig_bar = go.Figure(data=[
                go.Bar(name='Sin Domos', x=['Consumo'], y=[np.sum(c_base)], marker_color='#E74C3C', text=[f"{np.sum(c_base):,.0f} kWh"], textposition='auto'),
                go.Bar(name='Con Sunoptics', x=['Consumo'], y=[np.sum(c_proy)], marker_color='#2ECC71', text=[f"{np.sum(c_proy):,.0f} kWh"], textposition='auto')
            ])
            fig_bar.update_layout(title="kWh / año", height=400, barmode='group', template="plotly_white")
            st.plotly_chart(fig_bar, use_container_width=True)
            
        with c2:
            sda = (np.sum((e_in >= 300) & (horario_uso == 1.0)) / np.sum(horario_uso)) * 100
            fig_sda = go.Figure(go.Indicator(
                mode="gauge+number", value=sda, title={'text': "Autonomía Lumínica (sDA)"},
                number={'suffix': "%"}, gauge={'axis': {'range': [0, 100]}, 'bar': {'color': "#3498DB"}}))
            st.plotly_chart(fig_sda, use_container_width=True)

        st.markdown("### Curva de Optimización (Balance de Flujo Dividido)")
        sfr_range = np.linspace(0.01, 0.10, 10)
        ahorros_l, cargas_h, netos = [], [], []
        cop_sistema = 3.0

        for s in sfr_range:
            # LUZ
            e_t = lux * s * 0.65 * cu
            c_t = (np.clip(300 - e_t, 0, 300) / 300) * pot_total_kw * horario_uso
            ah_l = np.sum(c_base) - np.sum(c_t)
            
            # CALOR
            q_solar = (ghi * (ancho * largo * s) * datos_domo['SHGC'])
            q_cond = (ancho * largo * s) * (datos_domo['U_Value'] - u_techo_real) * (temp - 22.0)
            q_luces_evitado = (pot_total_kw * horario_uso - c_t) * 1000 
            
            carga_neta_w = q_solar + q_cond - q_luces_evitado
            penal_h = np.sum(np.where(temp > 24, carga_neta_w / (cop_sistema * 1000), 0))
            
            ahorros_l.append(ah_l)
            cargas_h.append(-penal_h)
            netos.append(ah_l - penal_h)

        fig_opt = go.Figure()
        fig_opt.add_trace(go.Scatter(x=sfr_range*100, y=ahorros_l, name='Ahorro Luz', line=dict(color='#3498db', dash='dash')))
        fig_opt.add_trace(go.Scatter(x=sfr_range*100, y=cargas_h, name='Carga HVAC', line=dict(color='#e74c3c')))
        fig_opt.add_trace(go.Scatter(x=sfr_range*100, y=netos, name='<b>AHORRO NETO TOTAL</b>', line=dict(color='#2ecc71', width=4)))
        fig_opt.update_layout(xaxis_title="SFR %", yaxis_title="Energía (kWh)", hovermode="x unified", template="plotly_white")
        st.plotly_chart(fig_opt, use_container_width=True)
    else:
        st.info("Completa la simulación primero.")
        st.warning("⚠️ Selecciona una ubicación en el mapa primero.")

st.info("Ingeniería Lumínica, Térmica y BEM | Eco Consultor.")
