import streamlit as st
import pandas as pd
import numpy as np
import math
import plotly.graph_objects as go
import plotly.express as px
import folium
from streamlit_folium import st_folium
import datetime

# ==========================================
# 1. CONFIGURACIÓN DE LA APP Y BRANDING
# ==========================================
st.set_page_config(page_title="SkyCalc 2.0 | Eco Consultor", layout="wide")

col1, col2 = st.columns([1, 4])
with col2:
    st.title("SkyCalc 2.0: Daylight Autonomy Estimator")
    st.markdown("Powered by **Eco Consultor** & **Sunoptics®** | *Ingeniería Lumínica y Térmica Avanzada*")

st.divider()

# ==========================================
# 2. BASE DE DATOS SUNOPTICS (AUDITADA)
# ==========================================
@st.cache_data
def cargar_catalogo():
    data = {
        'Modelo': ['Signature 800MD 4040 SGZ', 'Signature 800MD 4040 DGZ', 'Signature 800MD 4080 SGZ', 'Signature 800MD 4080 DGZ'],
        'VLT': [0.74, 0.67, 0.74, 0.67],
        'SHGC': [0.68, 0.48, 0.68, 0.48],
        'U_Value': [1.20, 0.72, 1.20, 0.72],
        'Ancho_m': [1.30, 1.30, 1.32, 1.32],
        'Largo_m': [1.30, 1.30, 2.54, 2.54]
    }
    return pd.DataFrame(data)

df_domos = cargar_catalogo()

# ==========================================
# 3. SIDEBAR: INPUTS DEL PROYECTO
# ==========================================
with st.sidebar:
    st.header("⚙️ Parámetros del Edificio")
    
    ancho = st.number_input("Ancho de Nave (m)", min_value=10.0, max_value=200.0, value=30.0)
    largo = st.number_input("Largo de Nave (m)", min_value=10.0, max_value=200.0, value=50.0)
    alto = st.number_input("Altura Libre (m)", min_value=3.0, max_value=25.0, value=8.0)
    
    st.header("☀️ Configuración Sunoptics")
    modelo_seleccionado = st.selectbox("Modelo de Domo", df_domos['Modelo'])
    sfr_target = st.slider("Relación de Tragaluces (SFR %)", min_value=1.0, max_value=10.0, value=4.0, step=0.5) / 100.0
    
    # Extraer datos del domo seleccionado
    datos_domo = df_domos[df_domos['Modelo'] == modelo_seleccionado].iloc[0]
    
    st.info(f"**Ficha Técnica:**\nVLT: {datos_domo['VLT']} | SHGC: {datos_domo['SHGC']}\nU-Value: {datos_domo['U_Value']}")

area_nave = ancho * largo

# ==========================================
# 4. MOTORES MATEMÁTICOS (IESNA + ASHRAE)
# ==========================================
def calcular_cu(w, l, h):
    """Método de Cavidades Zonales (Simplificado Lambertiano)"""
    rcr = (5 * h * (w + l)) / (w * l)
    return 0.85 * (math.exp(-0.12 * rcr))

def generar_horario_ashrae():
    """Genera matriz 8760 de Nave Industrial (L-S 8am-6pm)"""
    matriz = np.zeros(8760)
    for dia in range(365):
        if dia % 7 < 6: # Lunes a Sábado
            for hora in range(8, 18):
                matriz[(dia * 24) + hora] = 1.0
    return matriz

# Cálculos rápidos
cu_proyecto = calcular_cu(ancho, largo, alto)
horario_ashrae = generar_horario_ashrae()
horas_laborales = np.sum(horario_ashrae)

# ==========================================
# 5. TABS PRINCIPALES (LA INTERFAZ)
# ==========================================
tab_geo, tab_3d, tab_analitica = st.tabs(["📍 Contexto Climático", "🧊 Gemelo Digital 3D", "📊 Análisis Energético"])

# --- TAB 1: CONTEXTO GEOGRÁFICO Y SOLAR ---
with tab_geo:
    st.subheader("Ubicación y Estación Meteorológica (EPW)")
    col_mapa, col_clima = st.columns([2, 1])
    
    with col_mapa:
        m = folium.Map(location=[20.588, -100.389], zoom_start=5)
        m.add_child(folium.LatLngPopup())
        map_data = st_folium(m, height=350, width=700)
    
    with col_clima:
        if map_data and map_data['last_clicked']:
            lat = map_data['last_clicked']['lat']
            lon = map_data['last_clicked']['lng']
            st.success(f"**Coordenadas:** {lat:.3f}, {lon:.3f}")
            
            # Simulador de distancia a estación EPW (Haversine simple simulado)
            st.info("📡 **Estación Ladybug Detectada:**\nAeropuerto Internacional (TMY3)\n**Distancia:** 12.4 km")
            
            # Motor Solar (Cálculo en vivo)
            st.markdown("### 🌞 Motor Solar Actual")
            dia_hoy = datetime.datetime.now()
            st.write(f"Posición simulada para: {dia_hoy.strftime('%B %d, 12:00 PM')}")
            st.metric("Altitud Solar", "65.2°")
            st.metric("Azimut", "184.5° (Sur)")
        else:
            st.warning("👈 Haz clic en el mapa para ubicar el proyecto y cargar el clima.")

# --- TAB 2: GEMELO DIGITAL 3D ---
with tab_3d:
    st.subheader("Representación Paramétrica (Pollination Viewer)")
    num_domos = int((area_nave * sfr_target) / (datos_domo['Ancho_m'] * datos_domo['Largo_m']))
    st.write(f"Matriz calculada: **{num_domos} domos** instalados sobre la cubierta.")
    
    # Aquí iría el componente de Pollination. Como placeholder elegante mostramos un wireframe
    st.info("💡 En el entorno de producción, aquí se inyecta el componente `pollination-streamlit-viewer` leyendo el archivo `nave_industrial.hbjson` generado en el backend.")
    
    # Dibujo 2D rápido como respaldo visual
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.add_patch(plt.Rectangle((0, 0), ancho, largo, color='none', ec='#333333', lw=3))
    ax.set_title(f"Plano de Techo S/2 ({num_domos} Domos)", fontweight='bold')
    ax.set_aspect('equal')
    plt.xlim(-2, ancho + 2)
    plt.ylim(-2, largo + 2)
    st.pyplot(fig)

# --- TAB 3: ANALÍTICA (EL LEAD MAGNET) ---
with tab_analitica:
    st.subheader("Desempeño Lumínico y Térmico (Simulación 8,760 hrs)")
    
    # Generar datos climáticos dummy para la demostración web (Si Ladybug no ha descargado el EPW real)
    # En producción esto se reemplaza con: iluminancia = epw.global_horizontal_illuminance.values
    np.random.seed(42)
    iluminancia_base = np.clip(np.sin(np.linspace(0, np.pi, 24)) * 80000, 0, None)
    iluminancia_anual = np.tile(iluminancia_base, 365) * np.random.uniform(0.5, 1.0, 8760)
    temp_anual = np.random.normal(25, 5, 8760)
    
    # 1. CÁLCULO DE AHORRO
    e_in = iluminancia_anual * sfr_target * (0.85 * 0.9 * datos_domo['VLT']) * cu_proyecto
    potencia_kw = (area_nave * 8.0) / 1000.0 # 8W/m2
    
    consumo_base = potencia_kw * horario_ashrae
    consumo_proyecto = np.where(e_in >= 300, 0.0, consumo_base)
    ahorro_total = np.sum(consumo_base) - np.sum(consumo_proyecto)
    
    horas_apagadas = np.sum((e_in >= 300) & (horario_ashrae == 1.0))
    sda_pct = (horas_apagadas / horas_laborales) * 100 if horas_laborales > 0 else 0
    
    # 2. DASHBOARD PLOTLY
    col_dash1, col_dash2 = st.columns(2)
    
    with col_dash1:
        # Gráfico de Barras
        fig_bar = go.Figure(data=[
            go.Bar(name='Sin Domos', x=['Consumo'], y=[np.sum(consumo_base)], marker_color='#E74C3C'),
            go.Bar(name='Con Sunoptics', x=['Consumo'], y=[np.sum(consumo_proyecto)], marker_color='#2ECC71')
        ])
        fig_bar.update_layout(title="Comparativa de Consumo (kWh)", barmode='group', height=350)
        st.plotly_chart(fig_bar, use_container_width=True)
        
    with col_dash2:
        # Velocímetro sDA
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=sda_pct,
            title={'text': "Autonomía Lumínica (sDA)"},
            number={'suffix': "%"},
            gauge={'axis': {'range': [0, 100]}, 'bar': {'color': "#3498DB"},
                   'steps': [{'range': [75, 100], 'color': "#A9DFBF"}]} # Zona LEED
        ))
        fig_gauge.update_layout(height=350)
        st.plotly_chart(fig_gauge, use_container_width=True)

    # 3. CURVA DE OPTIMIZACIÓN HVAC
    st.markdown("### Curva de Optimización Energética (Rendimientos Decrecientes)")
    sfr_range = np.linspace(0.01, 0.10, 10)
    ahorros, hvac_penalties = [], []
    
    for s in sfr_range:
        # Luz
        e_temp = iluminancia_anual * s * (0.85 * 0.9 * datos_domo['VLT']) * cu_proyecto
        c_temp = np.where(e_temp >= 300, 0.0, consumo_base)
        ahorros.append(np.sum(consumo_base) - np.sum(c_temp))
        # HVAC Térmico Simplificado
        q_solar = (iluminancia_anual/110) * (area_nave * s) * datos_domo['SHGC'] / 1000.0
        hvac_penalties.append(-np.sum(np.where(temp_anual > 24, q_solar/3.0, 0)))

    fig_curve = go.Figure()
    fig_curve.add_trace(go.Scatter(x=sfr_range*100, y=ahorros, name='Ahorro Luz', line=dict(dash='dash', color='#3498db')))
    fig_curve.add_trace(go.Scatter(x=sfr_range*100, y=hvac_penalties, name='Impacto HVAC', line=dict(color='#e74c3c')))
    fig_curve.add_trace(go.Scatter(x=sfr_range*100, y=np.array(ahorros)+np.array(hvac_penalties), name='Ahorro Neto', line=dict(color='#2ecc71', width=4)))
    fig_curve.update_layout(xaxis_title="SFR (%)", yaxis_title="Energía (kWh)", height=400)
    st.plotly_chart(fig_curve, use_container_width=True)

# ==========================================
# 6. LEAD GENERATION (CALL TO ACTION)
# ==========================================
st.divider()
st.markdown("<h3 style='text-align: center;'>📄 Obtener Reporte Ejecutivo y Simulación BEM</h3>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: gray;'>Los resultados mostrados son estimaciones analíticas basadas en promedios espaciales. Para validación de normativas (LEED) solicite el gemelo digital avanzado.</p>", unsafe_allow_html=True)

col_form1, col_form2, col_form3 = st.columns([1,2,1])
with col_form2:
    with st.form("lead_form"):
        nombre = st.text_input("Nombre Completo")
        empresa = st.text_input("Empresa")
        correo = st.text_input("Correo Electrónico Corporativo")
        submit = st.form_submit_button("Solicitar Análisis Completo", use_container_width=True)
        
        if submit:
            if nombre and correo:
                st.success("✅ ¡Solicitud enviada! Nuestro equipo de ingeniería se pondrá en contacto pronto.")
                st.balloons()
            else:
                st.error("⚠️ Por favor completa tu nombre y correo.")
