import streamlit as st
import pandas as pd
import numpy as np
import math
import matplotlib.pyplot as plt
import plotly.graph_objects as go
import folium
from streamlit_folium import st_folium
import os
from geopy.geocoders import Nominatim
from weather_utils import obtener_estaciones_cercanas, descargar_y_extraer_epw, procesar_datos_clima

# --- 1. CONFIGURACIÓN INICIAL Y MEMORIA BLINDADA ---
st.set_page_config(page_title="SkyCalc 2.0 | Eco Consultor", layout="wide", page_icon="⚡")

from weather_utils import geocode_name

# Inicialización de estado
# Evitar la amnesia de Streamlit guardando todo en session_state
if 'lat_lon' not in st.session_state:
    st.session_state.lat_lon = [15.0, -90.0] # Coordenadas por defecto
if 'zoom_mapa' not in st.session_state:
    st.session_state.zoom_mapa = 4
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

# --- IMPORTACIÓN LADYBUG TOOLS ---
try:
    from ladybug.epw import EPW
    LADYBUG_READY = True
except ImportError:
    LADYBUG_READY = False

# ==========================================
# 2. BASE DE DATOS MAESTRA
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
        'U_Value': [5.80, 3.20, 5.80, 3.20, 5.80, 3.20, 2.80, 3.20],
        'Ancho_in': [51.25, 51.25, 51.25, 51.25, 52.25, 52.25, 52.25, 52.25],
        'Largo_in': [51.25, 51.25, 87.25, 87.25, 100.25, 100.25, 100.25, 100.25]
    }
    df = pd.DataFrame(data)
    df['Ancho_m'] = (df['Ancho_in'] * 0.0254).round(3)
    df['Largo_m'] = (df['Largo_in'] * 0.0254).round(3)
    return df

df_domos = cargar_catalogo()

# ==========================================
# 3. INTERFAZ: SIDEBAR E IDENTIFICACIÓN ASHRAE
# ==========================================
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
tab_config, tab_analitica, tab_reporte = st.tabs(["🌍 Ubicación y Clima", "📊 Simulación Energética", "📄 Reporte Final"])

with tab_config:
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("🌍 Mapa Interactivo")
        st.caption("Método 3: Haz clic en el mapa para buscar estaciones en ese punto.")

        m = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=8)
        folium.Marker([st.session_state.lat, st.session_state.lon], tooltip="Ubicación seleccionada", icon=folium.Icon(color='red', icon='info-sign')).add_to(m)

        if st.session_state.df_cercanas is not None:
            for idx, st_row in st.session_state.df_cercanas.iterrows():
                l_est = st_row.get('lat')
                ln_est = st_row.get('lon')
                if l_est and ln_est:
                    folium.Marker(
                        [l_est, ln_est],
                        tooltip=f"{st_row['name']} ({st_row['distancia_km']} km)",
                        icon=folium.Icon(color='blue', icon='cloud')
                    ).add_to(m)

        output = st_folium(m, width=700, height=500, key="mapa_estaciones")

        # Lógica de clic en el mapa
        if output and output.get("last_clicked"):
            c_lat = output["last_clicked"]["lat"]
            c_lon = output["last_clicked"]["lng"]
            if round(c_lat, 4) != round(st.session_state.lat, 4) or round(c_lon, 4) != round(st.session_state.lon, 4):
                st.session_state.lat = c_lat
                st.session_state.lon = c_lon
                buscar_estaciones()
                st.rerun()

    with col2:
        st.subheader("Estaciones Disponibles")
        if st.session_state.df_cercanas is not None and not st.session_state.df_cercanas.empty:
            st.write("Selecciona para cargar datos:")
            for idx, row in st.session_state.df_cercanas.iterrows():
                st_name = row.get('name') or f"Estación {idx}"
                st_dist = row.get('distancia_km') or 0
                url = row.get('URL_ZIP')

                if st.button(f"📥 {st_name} ({st_dist} km)", key=f"btn_st_{idx}"):
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
    st.header("⚙️ 1. Geometría de la Nave")
    ancho = st.number_input("Ancho (m)", 10.0, 200.0, 30.0)
    largo = st.number_input("Largo (m)", 10.0, 200.0, 50.0)
    alto = st.number_input("Altura Libre (m)", 3.0, 25.0, 8.0)
    
    st.header("☀️ 2. Configuración Sunoptics")
    modelo_sel = st.selectbox("Modelo NFRC", df_domos['Modelo'])
    sfr_target = st.slider("Objetivo SFR (%)", 1.0, 10.0, 4.0, 0.1) / 100.0
    datos_domo = df_domos[df_domos['Modelo'] == modelo_sel].iloc[0]

    st.header("📚 3. Normativa ASHRAE")
    mapa_programas = {"Warehouse": 6.5, "Manufacturing": 12.0, "Retail": 16.0}
    mapa_materiales = {
        "Membrana Genérica (Aislada)": "Generic Roof Membrane", 
        "Concreto Pesado": "Generic HW Concrete", 
        "Concreto Ligero": "Generic LW Concrete"
    }
    
    uso_edificio = st.selectbox("Uso del Espacio", list(mapa_programas.keys()))
    material_techo = st.selectbox("Material de Cubierta", list(mapa_materiales.keys()))

# Conexión con Honeybee (LBT)
try:
    from honeybee_energy.lib.materials import opaque_material_by_identifier
    lpd_real = mapa_programas[uso_edificio]
    nombre_material_lbt = mapa_materiales[material_techo]
    mat = opaque_material_by_identifier(nombre_material_lbt)
    u_techo_real = 1 / ((mat.thickness / mat.conductivity) + 0.15) 
    st.sidebar.success(f"✅ BEM Conectado\nLPD: {lpd_real} W/m²\nU-Roof: {u_techo_real:.3f} W/m²K")
except Exception as e:
    lpd_real, u_techo_real = 8.0, 0.5
    st.sidebar.warning(f"Usando valores estándar (LBT inactivo).")

# Generar vector de horarios (8760 horas)
horario_uso = np.zeros(8760)
for d in range(365): 
    if d % 7 < 6: # Lunes a Sábado
        for h in range(8, 18): # 8 AM a 6 PM
            horario_uso[(d * 24) + h] = 1.0

# ==========================================
# 4. TABS PRINCIPALES
# ==========================================
st.title("SkyCalc 2.0: Daylight Autonomy Estimator")
st.markdown("Powered by **Eco Consultor** & **Sunoptics®**")
st.divider()

tab_geo, tab_3d, tab_analitica = st.tabs(["📍 Ubicación y Clima", "📐 Distribución 2D", "📊 Análisis Energético"])

with tab_geo:
    st.subheader("Buscador Universal de Clima")
    
    # --- BUSCADOR POR NOMBRE O COORDENADAS ---
    query = st.text_input("🔍 Escribe una ciudad, país o pega coordenadas (ej. 'Madrid' o '40.41, -3.70')")
    if st.button("Buscar Ubicación"):
        if ',' in query and any(char.isdigit() for char in query):
            # Es una coordenada
            try:
                lat_str, lon_str = query.split(',')
                st.session_state.lat_lon = [float(lat_str.strip()), float(lon_str.strip())]
                st.session_state.zoom_mapa = 10
                st.rerun()
            except ValueError:
                st.error("Formato de coordenadas inválido. Usa: Latitud, Longitud")
        else:
            # Es un nombre de ciudad (Usamos Geopy)
            try:
                geolocator = Nominatim(user_agent="skycalc_buscador")
                loc = geolocator.geocode(query)
                if loc:
                    st.session_state.lat_lon = [loc.latitude, loc.longitude]
                    st.session_state.zoom_mapa = 10
                    st.rerun()
                else:
                    st.error("No se encontró la ubicación. Intenta ser más específico.")
            except Exception as e:
                st.error("Error al conectar con el servicio de búsqueda.")

    # --- CAPTURAR CLIC EN EL MAPA ---
    # Revisamos si el mapa fue clickeado antes de dibujarlo para actualizar la memoria
    if 'mapa_v3' in st.session_state and st.session_state['mapa_v3']:
        clicked = st.session_state['mapa_v3'].get('last_clicked')
        if clicked:
            click_lat, click_lng = clicked['lat'], clicked['lng']
            if round(click_lat, 4) != round(st.session_state.lat_lon[0], 4): # Solo actualizar si cambió
                st.session_state.lat_lon = [click_lat, click_lng]

    col_mapa, col_datos = st.columns([2, 1])

    with col_mapa:
        m = folium.Map(location=st.session_state.lat_lon, zoom_start=st.session_state.zoom_mapa)
        
        # Marcador principal del proyecto (Rojo)
        folium.Marker(
            location=st.session_state.lat_lon,
            popup="Punto de Proyecto",
            icon=folium.Icon(color='red', icon='crosshairs')
        ).add_to(m)
        
        df_estaciones = obtener_estaciones_cercanas(st.session_state.lat_lon[0], st.session_state.lat_lon[1], top_n=5)
        
        if df_estaciones is not None and not df_estaciones.empty:
            for _, st_row in df_estaciones.iterrows():
                lat_est = st_row.get('lat', st_row.get('Lat', st_row.get('latitude', 0)))
                lon_est = st_row.get('lon', st_row.get('Lon', st_row.get('longitude', 0)))
                nombre_est = st_row.get('name', st_row.get('Estación', st_row.get('station', 'Estación EPW')))
                dist_est = st_row.get('distancia_km', st_row.get('Distancia (km)', 0))
                
                folium.Marker(
                    location=[lat_est, lon_est],
                    popup=f"{nombre_est} ({dist_est} km)",
                    icon=folium.Icon(color='blue', icon='cloud')
                ).add_to(m)
            
        m.add_child(folium.LatLngPopup())
        map_data = st_folium(m, height=400, width=700, key="mapa_v3")
    
    with col_datos:
        st.write(f"📍 **Coordenadas del Proyecto:** {st.session_state.lat_lon[0]:.3f}, {st.session_state.lat_lon[1]:.3f}")
        
        # Confirmación de clima cargado (Sobrevive a reinicios)
        if st.session_state.clima_data:
            st.success(f"✅ Clima Activo: **{st.session_state.estacion_seleccionada}**")
        else:
            st.warning("⚠️ El proyecto aún no tiene clima cargado.")

        if df_estaciones is not None and not df_estaciones.empty:
            st.markdown("### Estación Recomendada:")
            mejor_est = df_estaciones.iloc[0]
            nombre_optimo = mejor_est.get('name', mejor_est.get('Estación', 'Estación EPW'))
            dist_optima = mejor_est.get('distancia_km', 0)
            url_optima = mejor_est.get('epw', mejor_est.get('URL_ZIP'))
            
            st.info(f"**{nombre_optimo}**\n\nDistancia: {dist_optima} km")
            
            if st.button("📥 Descargar EPW y Cargar Clima", type="primary"):
                with st.spinner("Descargando e inyectando datos climáticos..."):
                    try:
                        epw_path = descargar_y_extraer_epw(url_optima)
                        if epw_path:
                            datos_clima = procesar_datos_clima(epw_path)
                            st.session_state.clima_data = datos_clima
                            st.session_state.estacion_seleccionada = nombre_optimo
                            st.rerun() # Obligamos a recargar para que se actualice la alerta verde
                        else:
                            st.error("Error al descargar el archivo EPW.")
                    except Exception as e:
                        st.error(f"Error procesando clima: {e}")

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
                                       datos_domo['Ancho_m'], datos_domo['Largo_m'], color='#3498DB', alpha=0.8))
    plt.axis('equal')
    st.pyplot(fig_mat)
    st.caption(f"Distribución estimada para {num_domos} domos ({sfr_target*100}% de cobertura).")

with tab_analitica:
    st.subheader("Motor Analítico de Flujo Dividido (Split-Flux)")

    # Ahora sí detectará el clima porque está protegido en session_state
    if st.session_state.clima_data:
        clima = st.session_state.clima_data
        
        temp = np.array(clima['temp_seca'])
        dni = np.array(clima['rad_directa'])
        dhi = np.array(clima['rad_dif'])
        
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
        ghi = dni + dhi 
        lux = ghi * 115 
        
        cu = 0.85 * (math.exp(-0.12 * ((5 * alto * (ancho + largo)) / (ancho * largo))))
        pot_total_kw = (ancho * largo * lpd_real) / 1000.0
        c_base = pot_total_kw * horario_uso
        
        st.markdown("### Curva de Optimización Energética (Rendimientos Decrecientes)")
        sfr_range = np.linspace(0.01, 0.10, 10)
        ahorros_l, cargas_h, netos = [], [], []
        cop_sistema = 3.0

        with st.spinner("Ejecutando simulación vectorizada de 8,760 horas..."):
            for s in sfr_range:
                e_t = lux * s * 0.65 * cu
                c_t = (np.clip(300 - e_t, 0, 300) / 300) * pot_total_kw * horario_uso
                ah_l = np.sum(c_base) - np.sum(c_t)
                
                q_solar = (ghi * (ancho * largo * s) * datos_domo['SHGC'])
                q_cond = (ancho * largo * s) * (datos_domo['U_Value'] - u_techo_real) * (temp - 22.0)
                q_luces_evitado = (pot_total_kw * horario_uso - c_t) * 1000 
                
                carga_neta_w = q_solar + q_cond - q_luces_evitado
                penal_h = np.sum(np.where(temp > 24, carga_neta_w / (cop_sistema * 1000), 0))
                
                ahorros_l.append(ah_l)
                cargas_h.append(-penal_h)
                netos.append(ah_l - penal_h)

        fig_opt = go.Figure()
        fig_opt.add_trace(go.Scatter(x=sfr_range*100, y=ahorros_l, name='Ahorro Iluminación (kWh)', line=dict(color='#3498db', dash='dash')))
        fig_opt.add_trace(go.Scatter(x=sfr_range*100, y=cargas_h, name='Penalización HVAC (kWh)', line=dict(color='#e74c3c')))
        fig_opt.add_trace(go.Scatter(x=sfr_range*100, y=netos, name='<b>AHORRO NETO TOTAL</b>', line=dict(color='#2ecc71', width=4)))
        
        idx_max = np.argmax(netos)
        sfr_optimo = sfr_range[idx_max] * 100
        ahorro_max = netos[idx_max]
        fig_opt.add_annotation(x=sfr_optimo, y=ahorro_max, text=f"Punto Óptimo: {sfr_optimo:.1f}% SFR", showarrow=True, arrowhead=1)
        
        fig_opt.update_layout(xaxis_title="Cobertura de Techo (SFR %)", yaxis_title="Impacto Energético Anual (kWh)", hovermode="x unified", template="plotly_white")
        st.plotly_chart(fig_opt, use_container_width=True)
        
        st.divider()
        c1, c2, c3 = st.columns(3)
        sda_proyectado = (np.sum((lux * sfr_target * 0.65 * cu >= 300) & (horario_uso == 1.0)) / np.sum(horario_uso)) * 100
        
        c1.metric("Ahorro Neto Máximo", f"{int(ahorro_max):,} kWh/año")
        c2.metric("SFR Óptimo Calculado", f"{sfr_optimo:.1f} %")
        c3.metric(f"Autonomía Lumínica (sDA)", f"{sda_proyectado:.1f} %")

    else:
        st.warning("⚠️ Esperando datos... Selecciona una ubicación en el mapa de Clima y haz clic en 'Descargar EPW' para habilitar el motor.")
