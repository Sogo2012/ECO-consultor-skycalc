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
# 2. BASE DE DATOS SUNOPTICS (COMPLETA)
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
        'Ancho_in': [51.25, 51.25, 51.25, 51.25, 52.25, 52.25, 52.25, 52.25],
        'Largo_in': [51.25, 51.25, 87.25, 87.25, 100.25, 100.25, 100.25, 100.25],
        'VLT': [0.74, 0.67, 0.74, 0.67, 0.74, 0.67, 0.52, 0.64],
        'SHGC': [0.68, 0.48, 0.68, 0.48, 0.68, 0.48, 0.24, 0.31],
        'U_Value': [1.20, 0.72, 1.20, 0.72, 1.20, 0.72, 0.58, 0.72]
    }
    df = pd.DataFrame(data)
    df['Ancho_m'] = (df['Ancho_in'] * 0.0254).round(3)
    df['Largo_m'] = (df['Largo_in'] * 0.0254).round(3)
    return df

df_domos = cargar_catalogo()

# ==========================================
# 3. MOTOR CLIMÁTICO AVANZADO (NASA POWER)
# ==========================================
@st.cache_data
def obtener_clima_detallado_nasa(lat, lon):
    """Extrae componentes de luz y nubes de la NASA para cualquier coordenada."""
    parametros = "ALLSKY_SFC_SW_DWN,DIFF,ALLSKY_SFC_SW_DNI,CLD_OT,T2M"
    url = (
        f"https://power.larc.nasa.gov/api/temporal/hourly/point?"
        f"parameters={parametros}&community=RE&longitude={lon}&latitude={lat}"
        f"&start=20230101&end=20231231&format=JSON"
    )
    try:
        r = requests.get(url, timeout=15)
        data = r.json()['properties']['parameter']
        ghi = np.array(list(data['ALLSKY_SFC_SW_DWN'].values()))
        difusa = np.array(list(data['DIFF'].values()))
        nubes = np.array(list(data['CLD_OT'].values()))
        temp = np.array(list(data['T2M'].values()))
        # Conversión científica a LUX (Eficacia lumínica global ~115)
        return {
            "lux": ghi[:8760] * 115,
            "difusa": difusa[:8760] * 115,
            "nubes": nubes[:8760],
            "temp": temp[:8760]
        }
    except:
        return None

# ==========================================
# 4. SIDEBAR: INPUTS
# ==========================================
with st.sidebar:
    st.header("⚙️ 1. Geometría de la Nave")
    ancho = st.number_input("Ancho (m)", min_value=10.0, max_value=200.0, value=30.0)
    largo = st.number_input("Largo (m)", min_value=10.0, max_value=200.0, value=50.0)
    alto = st.number_input("Altura Libre (m)", min_value=3.0, max_value=25.0, value=8.0)
    
    st.header("☀️ 2. Configuración Sunoptics")
    modelo_seleccionado = st.selectbox("Modelo NFRC", df_domos['Modelo'])
    sfr_target = st.slider("Objetivo SFR (%)", 1.0, 10.0, 4.0, 0.1) / 100.0
    datos_domo = df_domos[df_domos['Modelo'] == modelo_seleccionado].iloc[0]
    
    st.info(f"**VLT:** {datos_domo['VLT']} | **SHGC:** {datos_domo['SHGC']}")

    st.header("📚 3. Normativa")
    uso_edificio = st.selectbox("Uso (ASHRAE 90.1)", ["Warehouse", "Manufacturing", "Retail"])
    material_techo = st.selectbox("Material de Cubierta", ["Membrane", "Metal Deck", "Concrete"])

area_nave = ancho * largo

# ==========================================
# 5. LÓGICA DE CÁLCULO (MOTORES FÍSICOS)
# ==========================================
def calcular_cu(w, l, h):
    rcr = (5 * h * (w + l)) / (w * l)
    return 0.85 * (math.exp(-0.12 * rcr))

cu_proyecto = calcular_cu(ancho, largo, alto)

def generar_horario_ashrae():
    matriz = np.zeros(8760)
    for dia in range(365):
        if dia % 7 < 6: # Lunes a Sábado
            for hora in range(8, 18): matriz[(dia * 24) + hora] = 1.0
    return matriz

horario_uso = generar_horario_ashrae()
horas_laborales = np.sum(horario_uso)

# Inicializar estado del clima para evitar errores al cargar
if 'clima_data' not in st.session_state:
    st.session_state['clima_data'] = None

# ==========================================
# 6. INTERFAZ PRINCIPAL (TABS)
# ==========================================
tab_geo, tab_3d, tab_analitica = st.tabs(["📍 Contexto Climático", "📐 Distribución Geométrica", "📊 Análisis Energético"])

with tab_geo:
    st.subheader("Buscador Satelital de Irradiancia y Nubosidad")
    col_mapa, col_datos = st.columns([2, 1])
    if st.session_state['clima_data']:
    st.success(f"✅ Conexión exitosa: {len(st.session_state['clima_data']['lux'])} registros recibidos.")
else:
    st.info("💡 Por favor, haz clic en un punto del mapa para obtener los datos de la NASA.")
    
    with col_mapa:
        m = folium.Map(location=[9.933, -84.083], zoom_start=7) # Centrado en Costa Rica
        m.add_child(folium.LatLngPopup())
        map_data = st_folium(m, height=400, width=700)
    
    with col_datos:
        if map_data and map_data['last_clicked']:
            lat, lon = map_data['last_clicked']['lat'], map_data['last_clicked']['lng']
            st.success(f"**Coordenadas:** {lat:.3f}, {lon:.3f}")
            
            with st.spinner("Descargando datos de la NASA..."):
                st.session_state['clima_data'] = obtener_clima_detallado_nasa(lat, lon)
            
            if st.session_state['clima_data']:
                st.info("✅ Datos satelitales vinculados al motor de cálculo.")
                if LADYBUG_READY:
                    loc = Location("Proyecto", latitude=lat, longitude=lon, time_zone=0)
                    sp = Sunpath.from_location(loc)
                    sol = sp.calculate_sun(month=6, day=21, hour=12)
                    st.metric("Altitud Solar (Zenit)", f"{round(sol.altitude, 2)}°")
        else:
            st.warning("👈 Haz clic en el mapa para cargar el clima real.")

    if st.session_state['clima_data']:
        # Gráfico de Nubosidad
        df_c = pd.DataFrame({
            'Mes': pd.date_range("2023-01-01", periods=8760, freq="h").month,
            'Nubes': st.session_state['clima_data']['nubes']
        }).groupby('Mes').mean()
        
        fig_n = px.bar(df_c, y='Nubes', title="Índice de Nubosidad Mensual (Satelital)", 
                       labels={'Nubes':'Grosor Óptico (OT)'}, color_discrete_sequence=['#95a5a6'])
        st.plotly_chart(fig_n, use_container_width=True)

with tab_3d:
    st.subheader("Distribución Matricial Sunoptics")
    col_plot, col_info = st.columns([2, 1])
    
    area_un_domo = datos_domo['Ancho_m'] * datos_domo['Largo_m']
    num_domos_teorico = (area_nave * sfr_target) / area_un_domo
    cols = max(1, round((num_domos_teorico * (ancho/largo))**0.5))
    filas = max(1, math.ceil(num_domos_teorico / cols))
    total_domos = cols * filas

    with col_plot:
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.add_patch(plt.Rectangle((0, 0), ancho, largo, color='none', ec='black', lw=2))
        sp_x, sp_y = ancho / cols, largo / filas
        for i in range(cols):
            for j in range(filas):
                cx, cy = (i * sp_x) + (sp_x/2), (j * sp_y) + (sp_y/2)
                ax.add_patch(plt.Rectangle((cx-datos_domo['Ancho_m']/2, cy-datos_domo['Largo_m']/2), 
                                           datos_domo['Ancho_m'], datos_domo['Largo_m'], color='#00aaff', alpha=0.6))
        plt.axis('equal')
        st.pyplot(fig)
    
    with col_info:
        st.metric("Total Domos", f"{total_domos} und")
        st.write(f"Distanciamiento: {sp_x:.2f}m x {sp_y:.2f}m")

with tab_analitica:
    if st.session_state['clima_data']:
        lux_anual = st.session_state['clima_data']['lux']
        temp_anual = st.session_state['clima_data']['temp']

        # Cálculo de Iluminancia Interna
        e_in = lux_anual * sfr_target * (0.85 * 0.9 * datos_domo['VLT']) * cu_proyecto
        potencia_w_m2 = 8.0 # Estándar ASHRAE
        potencia_total_kw = (area_nave * potencia_w_m2) / 1000.0
        
        consumo_base = potencia_total_kw * horario_uso
        luz_faltante = np.clip(300 - e_in, 0, 300)
        consumo_proyecto = (luz_faltante / 300) * potencia_total_kw * horario_uso
        
        sda_pct = (np.sum((e_in >= 300) & (horario_uso == 1.0)) / horas_laborales) * 100

        # Visualización
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(px.bar(x=['Base', 'Proyecto'], y=[np.sum(consumo_base), np.sum(consumo_proyecto)], 
                                   title="Consumo Eléctrico Anual (kWh)", color=['#e74c3c', '#2ecc71']), use_container_width=True)
        with c2:
            st.metric("Autonomía Lumínica (sDA)", f"{sda_pct:.1f}%")
            
        # Gráfico de Optimización SFR
        st.markdown("### Análisis de Sensibilidad Energética (Neto)")
        sfr_range = np.linspace(0.01, 0.10, 10)
        neto = []
        for s in sfr_range:
            ahorro_l = np.sum(consumo_base) - np.sum((np.clip(300 - (lux_anual * s * 0.5 * cu_proyecto), 0, 300)/300) * potencia_total_kw * horario_uso)
            carga_hvac = np.sum(np.where(temp_anual > 24, (lux_anual/110 * area_nave * s * datos_domo['SHGC'])/3000, 0))
            neto.append(ahorro_l - carga_hvac)
        
        fig_opt = px.line(x=sfr_range*100, y=neto, title="Punto Óptimo de Ahorro Neto", labels={'x':'SFR %', 'y':'kWh Ahorrados'})
        st.plotly_chart(fig_opt, use_container_width=True)
    else:
        st.warning("⚠️ Selecciona una ubicación en el mapa primero.")

# Formulario de contacto
st.divider()
with st.expander("📄 Solicitar Informe de Ingeniería"):
    with st.form("contact"):
        st.text_input("Nombre")
        st.text_input("Correo")
        if st.form_submit_button("Enviar"): st.success("Enviado")
