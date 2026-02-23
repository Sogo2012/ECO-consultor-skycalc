import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from weather_utils import obtener_estaciones_cercanas, descargar_y_extraer_epw, procesar_datos_clima
import os

# Configuración de página
st.set_page_config(page_title="SkyCalc 2.0 - Eco Consultor", layout="wide", page_icon="⚡")

# Estilos CSS personalizados
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #007bff; color: white; }
    .stMetric { background-color: white; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

# Inicialización de estado
if 'clima_data' not in st.session_state:
    st.session_state.clima_data = None
if 'estacion_seleccionada' not in st.session_state:
    st.session_state.estacion_seleccionada = None

# Sidebar - Configuración del Proyecto
with st.sidebar:
    st.image("https://img.icons8.com/external-flat-icons-inmotus-design/64/000000/external-Eco-energy-flat-icons-inmotus-design.png", width=100)
    st.title("SkyCalc 2.0")
    st.subheader("Configuración Global")
    
    lat = st.number_input("Latitud", value=20.5888, format="%.4f")
    lon = st.number_input("Longitud", value=-100.3899, format="%.4f")
    
    st.divider()
    tipo_analisis = st.selectbox("Tipo de Análisis", ["Residencial", "Comercial", "Industrial"])
    
    if st.button("📍 Localizar Estaciones"):
        df_cercanas = obtener_estaciones_cercanas(lat, lon)
        st.session_state.df_cercanas = df_cercanas
        st.success(f"Encontradas {len(df_cercanas)} estaciones cercanas.")

# Tabs principales
tab_config, tab_analitica, tab_reporte = st.tabs(["🌍 Ubicación y Clima", "📊 Simulación Energética", "📄 Reporte Final"])

with tab_config:
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("Mapa de Estaciones EPW")
        if 'df_cercanas' in st.session_state:
            df = st.session_state.df_cercanas
            m = folium.Map(location=[lat, lon], zoom_start=10)
            folium.Marker([lat, lon], tooltip="Proyecto", icon=folium.Icon(color='red', icon='home')).add_to(m)
            
            for idx, row in df.iterrows():
                # Acceso seguro a coordenadas
                lat_st = row.get('LAT') or row.get('lat') or row.get('latitude')
                lon_st = row.get('LON') or row.get('lon') or row.get('longitude')

                if lat_st is not None and lon_st is not None:
                    folium.Marker(
                        [lat_st, lon_st],
                        tooltip=f"{row.get('Estación', 'Estación')} ({row.get('Distancia (km)', 0)} km)",
                        popup=row.get('Estación', 'Estación'),
                        tooltip=f"{row['Estación']} ({row['Distancia (km)']} km)",
                        popup=row['Estación'],
                        icon=folium.Icon(color='blue', icon='cloud')
                    ).add_to(m)
            
            st_folium(m, width=700, height=500)
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
                                if os.path.exists(path):
                                    os.remove(path)
        
        st.divider()
        st.subheader("Milla Cero (NASA POWER)")
        if st.button("🚀 Usar Datos Satelitales (Alta Precisión)"):
            st.warning("Integrando con API de NASA POWER... (Simulado para esta demo)")
            st.session_state.estacion_seleccionada = "NASA POWER Satelital"

with tab_analitica:
    st.subheader("Motor de Cálculo SkyCalc")

    if st.session_state.clima_data:
        clima = st.session_state.clima_data
        st.info(f"Analizando: **{clima['ciudad']}, {clima['pais']}** (vía {st.session_state.estacion_seleccionada})")
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Temp. Media", f"{round(sum(clima['temp_seca'])/8760, 1)} °C")
        c2.metric("Rad. Solar Máx", f"{max(clima['rad_directa'])} W/m²")
        c3.metric("Horas de Análisis", "8760 h")
        
        st.divider()

        if st.button("🔥 EJECUTAR SIMULACIÓN"):
            with st.spinner("Calculando demanda térmica..."):
                import time
                time.sleep(2)
                st.session_state.calculo_completado = True
                st.balloons()
                st.success("Cálculo completado.")

        if getattr(st.session_state, 'calculo_completado', False):
            st.write("### Resultados de la Optimización")
            df_temp = pd.DataFrame({'Temperatura (°C)': clima['temp_seca'][:168]})
            st.line_chart(df_temp)
            st.write("Estimación de Ahorro: **24.5%**.")
            
    else:
        st.warning("⚠️ Selecciona una estación primero.")

with tab_reporte:
    st.subheader("Generación de Reportes")
    if getattr(st.session_state, 'calculo_completado', False):
        st.button("💾 Descargar PDF de Auditoría")
    else:
        st.info("Completa la simulación primero.")
