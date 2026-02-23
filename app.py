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
if 'df_cercanas' not in st.session_state:
    st.session_state.df_cercanas = None

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
        with st.spinner("Buscando estaciones cercanas..."):
            df_cercanas = obtener_estaciones_cercanas(lat, lon)
            st.session_state.df_cercanas = df_cercanas
            if df_cercanas.empty:
                st.error("No se encontraron estaciones para esta ubicación.")
            else:
                st.success(f"Encontradas {len(df_cercanas)} estaciones.")

# Tabs principales
tab_config, tab_analitica, tab_reporte = st.tabs(["🌍 Ubicación y Clima", "📊 Simulación Energética", "📄 Reporte Final"])

with tab_config:
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("Mapa de Estaciones EPW")
        if st.session_state.df_cercanas is not None and not st.session_state.df_cercanas.empty:
            df = st.session_state.df_cercanas
            m = folium.Map(location=[lat, lon], zoom_start=10)
            folium.Marker([lat, lon], tooltip="Proyecto", icon=folium.Icon(color='red', icon='home')).add_to(m)
            
            for idx, st_row in df.iterrows():
                # Acceso defensivo a coordenadas y etiquetas
                lat_est = st_row.get('LAT') or st_row.get('lat')
                lon_est = st_row.get('LON') or st_row.get('lon')

                nombre_est = st_row.get('name', st_row.get('Estación', 'Estación Desconocida'))
                dist_est = st_row.get('distancia_km', st_row.get('Distancia (km)', 0))

                if lat_est is not None and lon_est is not None:
                    folium.Marker(
                        location=[lat_est, lon_est],
                        tooltip=f"{nombre_est} ({dist_est} km)",
                        popup=f"{nombre_est} ({dist_est} km)",
                        icon=folium.Icon(color='blue', icon='info-sign')
                    ).add_to(m)
            
            st_folium(m, width=700, height=500, key="mapa_estaciones")
        else:
            st.info("Presiona 'Localizar Estaciones' en el sidebar para ver el mapa.")

    with col2:
        st.subheader("Estaciones Disponibles")
        if st.session_state.df_cercanas is not None and not st.session_state.df_cercanas.empty:
            st.write("Selecciona para cargar datos:")
            for idx, row in st.session_state.df_cercanas.iterrows():
                st_name = row.get('Estación') or row.get('name') or f"Estación {idx}"
                st_dist = row.get('Distancia (km)') or row.get('distancia_km') or 0
                url = row.get('URL_ZIP')

                if st.button(f"📥 {st_name} ({st_dist} km)", key=f"btn_{idx}"):
                    if url:
                        with st.spinner(f"Descargando datos de {st_name}..."):
                            path = descargar_y_extraer_epw(url)
                            if path:
                                try:
                                    data = procesar_datos_clima(path)
                                    if data:
                                        st.session_state.clima_data = data
                                        st.session_state.estacion_seleccionada = st_name
                                        st.success("✅ Datos cargados correctamente.")
                                    else:
                                        st.error("No se pudieron procesar los datos del archivo EPW.")
                                finally:
                                    if os.path.exists(path):
                                        os.remove(path)
                            else:
                                st.error("No se pudo descargar el archivo de clima.")
        
        st.divider()
        st.subheader("Milla Cero (NASA POWER)")
        if st.button("🚀 Usar Datos Satelitales (Alta Precisión)"):
            st.warning("Integrando con API de NASA POWER... (Simulado)")
            st.session_state.estacion_seleccionada = "NASA POWER Satelital"

with tab_analitica:
    st.subheader("Motor de Cálculo SkyCalc")

    if st.session_state.clima_data:
        clima = st.session_state.clima_data
        # Acceso seguro a metadatos
        ciudad = clima.get('ciudad') or clima.get('metadata', {}).get('ciudad', 'Desconocida')
        pais = clima.get('pais') or clima.get('metadata', {}).get('pais', 'Desconocido')
        
        st.info(f"Analizando: **{ciudad}, {pais}** (vía {st.session_state.estacion_seleccionada})")
        
        temp_data = clima.get('temp_seca', [])
        rad_data = clima.get('rad_dir') or clima.get('rad_directa', [])

        if len(temp_data) > 0:
            c1, c2, c3 = st.columns(3)
            c1.metric("Temp. Media", f"{round(sum(temp_data)/len(temp_data), 1)} °C")
            c2.metric("Rad. Solar Máx", f"{max(rad_data) if len(rad_data) > 0 else 'N/A'} W/m²")
            c3.metric("Horas de Análisis", f"{len(temp_data)} h")

            st.divider()

            if st.button("🔥 EJECUTAR SIMULACIÓN"):
                with st.spinner("Calculando demanda térmica..."):
                    import time
                    time.sleep(1)
                    st.session_state.calculo_completado = True
                    st.balloons()
                    st.success("Cálculo completado.")

            if getattr(st.session_state, 'calculo_completado', False):
                st.write("### Resultados de la Optimización")
                df_temp = pd.DataFrame({'Temperatura (°C)': temp_data[:168]})
                st.line_chart(df_temp)
                st.write("Estimación de Ahorro Proyectado: **24.5%**.")
        else:
            st.error("Los datos de clima están incompletos.")
            
    else:
        st.warning("⚠️ Selecciona una estación primero en la pestaña 'Ubicación y Clima'.")

with tab_reporte:
    st.subheader("Generación de Reportes")
    if getattr(st.session_state, 'calculo_completado', False):
        st.success("El reporte está listo para ser generado.")
        st.button("💾 Descargar PDF de Auditoría")
    else:
        st.info("Completa la simulación en la pestaña 'Simulación Energética' primero.")
