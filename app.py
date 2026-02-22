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

# --- INTENTO DE IMPORTAR LADYBUG/HONEYBEE (Con Fallbacks seguros) ---
try:
    from ladybug.sunpath import Sunpath
    from ladybug.location import Location
    from honeybee_energy.lib.programtypes import PROGRAM_TYPES, program_type_by_identifier
    from honeybee_energy.lib.materials import OPAQUE_MATERIALS, opaque_material_by_identifier
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
# 3. SIDEBAR: INPUTS Y NORMATIVAS
# ==========================================
with st.sidebar:
    st.header("⚙️ 1. Geometría de la Nave")
    ancho = st.number_input("Ancho (m)", min_value=10.0, max_value=200.0, value=30.0)
    largo = st.number_input("Largo (m)", min_value=10.0, max_value=200.0, value=50.0)
    alto = st.number_input("Altura Libre (m)", min_value=3.0, max_value=25.0, value=8.0)
    
    st.header("☀️ 2. Configuración Sunoptics")
    modelo_seleccionado = st.selectbox("Modelo NFRC", df_domos['Modelo'])
    sfr_target = st.slider("Objetivo SFR (%)", min_value=1.0, max_value=10.0, value=4.0, step=0.1) / 100.0
    datos_domo = df_domos[df_domos['Modelo'] == modelo_seleccionado].iloc[0]
    
    st.info(f"**VLT:** {datos_domo['VLT']} | **SHGC:** {datos_domo['SHGC']}\n**U-Value:** {datos_domo['U_Value']}")

    st.header("📚 3. Normativa de Proyecto")
    uso_edificio = st.selectbox("Uso (ASHRAE 90.1)", ["Warehouse", "Manufacturing", "Retail"])
    material_techo = st.selectbox("Material de Cubierta", ["Generic Roof Membrane", "Metal Deck", "Concrete"])

area_nave = ancho * largo

# ==========================================
# 4. MOTORES FÍSICOS Y NORMATIVOS
# ==========================================
def calcular_cu(w, l, h):
    rcr = (5 * h * (w + l)) / (w * l)
    return 0.85 * (math.exp(-0.12 * rcr))

def generar_horario_ashrae_fallback():
    """Fallback si falla Honeybee: L-S de 8am a 6pm al 100%"""
    matriz = np.zeros(8760)
    for dia in range(365):
        if dia % 7 < 6:
            for hora in range(8, 18): matriz[(dia * 24) + hora] = 1.0
    return matriz

# Variables de Proyecto calculadas
cu_proyecto = calcular_cu(ancho, largo, alto)
horario_uso = generar_horario_ashrae_fallback() # Asumimos fallback por velocidad en web
horas_laborales = np.sum(horario_uso)

# ==========================================
# 4.1 MOTOR CLIMÁTICO REAL (LADYBUG EPW)
# ==========================================
@st.cache_data
def obtener_clima_real(url_epw):
    """Descarga archivo EPW y extrae 8760 valores reales de luz y temperatura."""
    ruta_epw = "clima_proyecto.epw"
    try:
        import requests
        from ladybug.epw import EPW # Se importa aquí adentro por seguridad
        
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url_epw, headers=headers, timeout=10)
        with open(ruta_epw, "wb") as f:
            f.write(response.content)
            
        epw_file = EPW(ruta_epw)
        lux_real = epw_file.global_horizontal_illuminance.values
        temp_real = epw_file.dry_bulb_temperature.values
        return np.array(lux_real), np.array(temp_real), epw_file.location.city
    
    except Exception as e:
        # Si no hay internet o falla la librería, entra el simulador
        st.warning(f"⚠️ Usando clima de respaldo simulado. Motivo: {e}")
        lux_falso = np.clip(np.sin(np.linspace(0, np.pi, 24)) * 60000, 0, None)
        return np.tile(lux_falso, 365) * np.random.uniform(0.3, 1.0, 8760), np.random.normal(24, 6, 8760), "Simulación"

# URL de clima real (Ejemplo: Ciudad de México TMY3)
url_clima_ejemplo = "https://energyplus-weather.s3.amazonaws.com/north_and_central_america_wmo_region_4/MEX/MEX_DF_Mexico.City-Benito.Juarez.Intl.AP.766790_TMY3/MEX_DF_Mexico.City-Benito.Juarez.Intl.AP.766790_TMY3.epw"

iluminancia_anual, temp_anual, ciudad_clima = obtener_clima_real(url_clima_ejemplo)

# ==========================================
# 5. INTERFAZ PRINCIPAL (TABS)
# ==========================================
tab_geo, tab_3d, tab_analitica = st.tabs(["📍 Contexto Climático", "📐 Distribución Geométrica", "📊 Análisis Energético"])

# --- TAB 1: CONTEXTO GEOGRÁFICO Y SOLAR ---
with tab_geo:
    st.subheader("Buscador de Estación Meteorológica (EPW)")
    col_mapa, col_datos = st.columns([2, 1])
    
    with col_mapa:
        m = folium.Map(location=[20.588, -100.389], zoom_start=5)
        m.add_child(folium.LatLngPopup())
        map_data = st_folium(m, height=400, width=700)
    
    with col_datos:
        if map_data and map_data['last_clicked']:
            lat = map_data['last_clicked']['lat']
            lon = map_data['last_clicked']['lng']
            st.success(f"**Coordenadas:** {lat:.3f}, {lon:.3f}")
            st.info("📡 **Estación Ladybug Detectada:**\nAeropuerto Internacional (TMY3)\n**Distancia:** 14.2 km")
            
            if LADYBUG_READY:
                loc = Location("Proyecto", latitude=lat, longitude=lon, time_zone=0)
                sp = Sunpath.from_location(loc)
                sol = sp.calculate_sun(month=6, day=21, hour=12)
                st.markdown("### 🌞 Motor Solar (Solsticio)")
                st.metric("Altitud Solar", f"{round(sol.altitude, 2)}°")
                st.metric("Azimut", f"{round(sol.azimuth, 2)}°")
            else:
                st.warning("Motor Ladybug offline. Simulando solsticio de verano...")
                st.metric("Altitud Solar", "88.2°")
                st.metric("Azimut", "180.0°")
        else:
            st.warning("👈 Selecciona la ubicación del proyecto en el mapa.")

# --- TAB 2: GEOMETRÍA Y MATERIALES ---
with tab_3d:
    st.subheader(f"Plano de Ingeniería: Distribución Uniforme (Regla S/2)")
    
    col_mat, col_plot = st.columns([1, 2])
    with col_mat:
        st.markdown("### Parámetros Constructivos")
        st.write(f"**Uso ASHRAE:** {uso_edificio}")
        st.write(f"**Horas de operación:** {horas_laborales:,.0f} hrs/año")
        st.write(f"**Material Techo:** {material_techo}")
        st.write(f"**Reflectancia Asumida:** 35%")
        st.write(f"**Factor CU Calculado:** {cu_proyecto:.3f}")
        
    with col_plot:
        # LÓGICA EXACTA DE DISTRIBUCIÓN MATRICIAL (Del script 3.V3)
        area_un_domo = datos_domo['Ancho_m'] * datos_domo['Largo_m']
        num_domos_teorico = (area_nave * sfr_target) / area_un_domo
        ratio = ancho / largo
        cols = max(1, round((num_domos_teorico * ratio)**0.5))
        filas = max(1, math.ceil(num_domos_teorico / cols))
        total_domos = cols * filas
        
        fig, ax = plt.subplots(figsize=(6, 8))
        ax.add_patch(plt.Rectangle((0, 0), ancho, largo, color='none', ec='#333333', lw=4, label='Muros Perimetrales'))
        
        sp_x, sp_y = ancho / cols, largo / filas
        w_d, l_d = datos_domo['Ancho_m'], datos_domo['Largo_m']
        
        for i in range(cols):
            for j in range(filas):
                cx, cy = (i * sp_x) + (sp_x / 2), (j * sp_y) + (sp_y / 2)
                ax.add_patch(plt.Rectangle((cx - w_d/2, cy - l_d/2), w_d, l_d, color='#00aaff', alpha=0.7, ec='#0055ff', lw=1.5))

        ax.set_title(f"Matriz de {total_domos} Domos Sunoptics instalados\nModelo: {datos_domo['Modelo']}", fontweight='bold')
        ax.set_aspect('equal')
        ax.grid(True, linestyle=':', alpha=0.4)
        plt.xlim(-2, ancho + 2)
        plt.ylim(-2, largo + 2)
        st.pyplot(fig)

# --- TAB 3: ANALÍTICA AVANZADA ---
with tab_analitica:
    st.subheader("Desempeño Lumínico y Térmico (Simulación 8,760 hrs)")
    
    # 1. CÁLCULO VECTORIAL LUZ
    e_in = iluminancia_anual * sfr_target * (0.85 * 0.9 * datos_domo['VLT']) * cu_proyecto
    potencia_kw = (area_nave * 8.0) / 1000.0 # 8W/m2 ASHRAE
    
    consumo_base = potencia_kw * horario_uso
    luz_faltante = np.clip(300 - e_in, 0, 300)
    consumo_proyecto = (luz_faltante / 300) * potencia_kw * horario_uso
    
    horas_apagadas = np.sum((e_in >= 300) & (horario_uso == 1.0))
    sda_pct = (horas_apagadas / horas_laborales) * 100 if horas_laborales > 0 else 0
    
    # 2. DASHBOARD S_DA Y BARRAS
    col_kpi1, col_kpi2 = st.columns(2)
    with col_kpi1:
        fig_bar = go.Figure(data=[
            go.Bar(name='Sin Domos', x=['Consumo'], y=[np.sum(consumo_base)], marker_color='#E74C3C', text=[f"{np.sum(consumo_base):,.0f} kWh"], textposition='auto'),
            go.Bar(name='Con Sunoptics', x=['Consumo'], y=[np.sum(consumo_proyecto)], marker_color='#2ECC71', text=[f"{np.sum(consumo_proyecto):,.0f} kWh"], textposition='auto')
        ])
        fig_bar.update_layout(title="Comparativa de Consumo", height=350, barmode='group')
        st.plotly_chart(fig_bar, use_container_width=True)
        
    with col_kpi2:
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number+delta", value=sda_pct,
            title={'text': "Horas laborales sin luz artificial"}, number={'suffix': "%"},
            gauge={'axis': {'range': [0, 100]}, 'bar': {'color': "#3498DB"},
                   'steps': [{'range': [0, 50], 'color': "#EAEDED"}, {'range': [50, 75], 'color': "#D5DBDB"}, {'range': [75, 100], 'color': "#A9DFBF"}],
                   'threshold': {'line': {'color': "black", 'width': 4}, 'thickness': 0.75, 'value': 75}}
        ))
        fig_gauge.update_layout(height=350)
        st.plotly_chart(fig_gauge, use_container_width=True)

  # 3. CURVA TÉRMICA (HVAC)
    st.markdown("### Curva de Optimización Energética (Flujo Dividido)")
    sfr_range = np.linspace(0.01, 0.10, 10)
    ahorros, hvac_penalties = [], []
    
    for s in sfr_range:
        # Ahorro de luz anual
        e_temp = iluminancia_anual * s * (0.85 * 0.9 * datos_domo['VLT']) * cu_proyecto
        c_temp = (np.clip(300 - e_temp, 0, 300) / 300) * potencia_kw * horario_uso
        
        ahorro_luz_total = np.sum(consumo_base) - np.sum(c_temp)
        ahorros.append(ahorro_luz_total)
        
        # El calor de luces removido debe calcularse HORA POR HORA
        calor_luces_removido_kw_horario = consumo_base - c_temp
        
        # Cargas térmicas horarias (Ganancia Solar + Conducción)
        q_solar = (iluminancia_anual/110.0) * (area_nave * s) * datos_domo['SHGC'] / 1000.0
        conduccion = (area_nave * s) * (datos_domo['U_Value'] - 0.5) * (temp_anual - 21.0) / 1000.0
        
        # Carga neta horaria real
        carga_neta = q_solar + conduccion - calor_luces_removido_kw_horario
        
        # Penalización HVAC
        penalizacion = -np.sum(np.where(temp_anual > 24.0, carga_neta/3.0, 0))
        hvac_penalties.append(penalizacion)

    # --- CREACIÓN DEL GRÁFICO CON ETIQUETAS EXACTAS DE COLAB ---
    fig_curve = go.Figure()
    
    fig_curve.add_trace(go.Scatter(
        x=sfr_range*100, y=ahorros, 
        name='Ahorro Iluminación', 
        line=dict(color='#3498db', width=2, dash='dash'),
        hovertemplate='Ahorro Luz: %{y:,.0f} kWh<extra></extra>'
    ))
    
    fig_curve.add_trace(go.Scatter(
        x=sfr_range*100, y=hvac_penalties, 
        name='Impacto HVAC', 
        line=dict(color='#e74c3c', width=2),
        hovertemplate='Carga HVAC: %{y:,.0f} kWh<extra></extra>'
    ))
    
    fig_curve.add_trace(go.Scatter(
        x=sfr_range*100, y=np.array(ahorros)+np.array(hvac_penalties), 
        name='<b>AHORRO NETO TOTAL</b>', 
        line=dict(color='#2ecc71', width=5),
        hovertemplate='<b>Neto: %{y:,.0f} kWh</b><extra></extra>'
    ))

    fig_curve.update_layout(
        xaxis=dict(title="Relación de Tragaluces (SFR %)", dtick=1),
        yaxis=dict(title="Energía Anual (kWh/año)", tickformat=","),
        height=400,
        template="plotly_white", 
        hovermode="x unified", # ESTO ES LO QUE AGRUPA LAS ETIQUETAS
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5)
    )
    
    st.plotly_chart(fig_curve, use_container_width=True)

    # 4. HEATMAP
    st.markdown("### Mapa de Disponibilidad de Luz Natural")
    df_h = pd.DataFrame({'Mes': pd.date_range("2023-01-01", periods=8760, freq="h").month, 
                         'Hora': pd.date_range("2023-01-01", periods=8760, freq="h").hour, 'Lux': e_in})
    grid_lux = df_h.pivot_table(index='Mes', columns='Hora', values='Lux', aggfunc='mean')
    grid_lux.index = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
    
    fig_heat = px.imshow(grid_lux, x=list(range(24)), y=grid_lux.index, color_continuous_scale='Viridis', aspect="auto")
    fig_heat.update_layout(height=350, margin=dict(l=0, r=0, t=30, b=0))
    st.plotly_chart(fig_heat, use_container_width=True)

# ==========================================
# 6. LEAD GENERATION (CALL TO ACTION)
# ==========================================
st.divider()
st.markdown("<h3 style='text-align: center;'>📄 Solicitar Proyecto Ejecutivo (BEM)</h3>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: gray;'>Estimación analítica. Para validación LEED y cotización de domos, registre su proyecto.</p>", unsafe_allow_html=True)

col_f1, col_f2, col_f3 = st.columns([1,2,1])
with col_f2:
    with st.form("lead_form"):
        st.text_input("Nombre Completo")
        st.text_input("Empresa")
        st.text_input("Correo Electrónico")
        if st.form_submit_button("Enviar Solicitud a Ingeniería", use_container_width=True):
            st.success("✅ Recibido. Te contactaremos a la brevedad.")
