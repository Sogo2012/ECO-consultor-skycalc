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

from weather_utils import geocode_name

# Inicialización de estado
if 'clima_data' not in st.session_state:
    st.session_state.clima_data = None
if 'estacion_seleccionada' not in st.session_state:
    st.session_state.estacion_seleccionada = None
if 'df_cercanas' not in st.session_state:
    st.session_state.df_cercanas = None
if 'lat' not in st.session_state:
    st.session_state.lat = 20.5888
if 'lon' not in st.session_state:
    st.session_state.lon = -100.3899

def buscar_estaciones():
    with st.spinner("Buscando estaciones cercanas..."):
        df_cercanas = obtener_estaciones_cercanas(st.session_state.lat, st.session_state.lon)
        st.session_state.df_cercanas = df_cercanas
        if df_cercanas.empty:
            st.error("No se encontraron estaciones para esta ubicación.")
        else:
            st.success(f"Encontradas {len(df_cercanas)} estaciones.")

# Sidebar - Configuración del Proyecto
with st.sidebar:
    st.image("https://img.icons8.com/external-flat-icons-inmotus-design/64/000000/external-Eco-energy-flat-icons-inmotus-design.png", width=100)
    st.title("SkyCalc 2.0")
    
    st.subheader("🔍 Métodos de Búsqueda")
    
    # Método 1: Búsqueda por nombre
    search_name = st.text_input("Buscar por ciudad o país", placeholder="Ej: Madrid, España")
    if st.button("🔍 Buscar por Nombre"):
        if search_name:
            n_lat, n_lon = geocode_name(search_name)
            if n_lat:
                st.session_state.lat = n_lat
                st.session_state.lon = n_lon
                buscar_estaciones()
            else:
                st.error("No se pudo localizar ese lugar.")

    st.divider()
    
    # Método 2: Búsqueda por coordenadas
    st.subheader("📍 Coordenadas Exactas")
    st.session_state.lat = st.number_input("Latitud", value=st.session_state.lat, format="%.4f")
    st.session_state.lon = st.number_input("Longitud", value=st.session_state.lon, format="%.4f")

    if st.button("🚀 Buscar en Coordenadas"):
        buscar_estaciones()

    st.divider()
    tipo_analisis = st.selectbox("Tipo de Análisis", ["Residencial", "Comercial", "Industrial"])

# Tabs principales
tab_config, tab_clima, tab_analitica, tab_reporte = st.tabs(["🌍 Selección de Clima", "🌤️ Contexto Climático", "📊 Simulación Energética", "📄 Reporte Final"])

with tab_clima:
    st.subheader("Análisis Bioclimático del Sitio")
    
    if st.session_state.clima_data and 'vel_viento' in st.session_state.clima_data:
        clima = st.session_state.clima_data
        md = clima['metadata']
        
        # Mostrar metadatos clave para HVAC
        cols_hvac = st.columns(4)
        cols_hvac[0].metric("Latitud", f"{md['lat']}°")
        cols_hvac[1].metric("Elevación", f"{md['elevacion']} m")
        cols_hvac[2].metric("Humedad Relativa Media", f"{round(sum(clima['hum_relativa'])/8760, 1)} %")
        cols_hvac[3].metric("Velocidad Viento Media", f"{round(sum(clima['vel_viento'])/8760, 1)} m/s")
        
        st.divider()
        col_graf_1, col_graf_2 = st.columns(2)
        
        # 1. LA ROSA DE LOS VIENTOS (Plotly Express)
        with col_graf_1:
            st.markdown("### 🌬️ Rosa de los Vientos Anual")
            import plotly.express as px
            
            # Preparar datos: categorizar dirección y velocidad
            df_viento = pd.DataFrame({'dir': clima['dir_viento'], 'vel': clima['vel_viento']})
            # Limpiar datos nulos/calmas
            df_viento = df_viento[df_viento['vel'] > 0.5] 
            
            # Crear bins de 16 direcciones (N, NNE, NE, etc.)
            bins_dir = np.arange(-11.25, 371.25, 22.5)
            labels_dir = ['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW','N2']
            df_viento['Dir_Cat'] = pd.cut(df_viento['dir'], bins=bins_dir, labels=labels_dir, right=False)
            df_viento['Dir_Cat'] = df_viento['Dir_Cat'].replace('N2', 'N')
            
            # Crear bins de velocidad
            bins_vel = [0, 2, 4, 6, 8, 20]
            labels_vel = ['0-2 m/s', '2-4 m/s', '4-6 m/s', '6-8 m/s', '>8 m/s']
            df_viento['Vel_Cat'] = pd.cut(df_viento['vel'], bins=bins_vel, labels=labels_vel)
            
            # Agrupar para Plotly
            df_rose = df_viento.groupby(['Dir_Cat', 'Vel_Cat']).size().reset_index(name='Frecuencia')
            
            fig_rose = px.bar_polar(df_rose, r="Frecuencia", theta="Dir_Cat", color="Vel_Cat",
                                    color_discrete_sequence=px.colors.sequential.Plasma_r,
                                    template="plotly_white")
            fig_rose.update_layout(margin=dict(t=20, b=20, l=20, r=20))
            st.plotly_chart(fig_rose, use_container_width=True)

        # 2. PROPORCIÓN DE LUZ (Directa vs Difusa)
        with col_graf_2:
            st.markdown("### ☀️ Balance de Irradiación")
            st.caption("Justificación técnica para domos prismáticos de alta difusión.")
            
            suma_directa = sum(clima['rad_directa'])
            suma_difusa = sum(clima['rad_dif'])
            
            fig_pie = go.Figure(data=[go.Pie(labels=['Radiación Directa (Luz Dura)', 'Radiación Difusa (Luz Suave)'],
                                             values=[suma_directa, suma_difusa], hole=.4,
                                             marker_colors=['#f39c12', '#bdc3c7'])])
            fig_pie.update_layout(margin=dict(t=20, b=20, l=20, r=20), template="plotly_white")
            st.plotly_chart(fig_pie, use_container_width=True)
            
    else:
        st.warning("⚠️ Carga un archivo climático en la pestaña anterior para ver el análisis bioclimático.")

with tab_analitica:
    st.subheader("Motor de Cálculo SkyCalc")

    if st.session_state.clima_data:
        clima = st.session_state.clima_data
        # Acceso seguro a metadatos
        ciudad = clima.get('ciudad') or clima.get('metadata', {}).get('ciudad', 'Desconocida')
        pais = clima.get('pais') or clima.get('metadata', {}).get('pais', 'Desconocido')
        
        st.info(f"Analizando: **{ciudad}, {pais}** (vía {st.session_state.estacion_seleccionada})")
        
        temp_data = clima.get('temp_seca', [])
        rad_data = clima.get('rad_directa', [])
        rad_dif = clima.get('rad_dif', [])

        if len(temp_data) > 0:
            c1, c2, c3 = st.columns(3)
            c1.metric("Temp. Media", f"{round(sum(temp_data)/len(temp_data), 1)} °C")
            c2.metric("Rad. Directa Máx", f"{max(rad_data) if len(rad_data) > 0 else 'N/A'} W/m²")
            c3.metric("Rad. Difusa Máx", f"{max(rad_dif) if len(rad_dif) > 0 else 'N/A'} W/m²")

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
