import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px

# ==========================================
# CONFIGURACIÓN DE LA PÁGINA
# ==========================================
st.set_page_config(
    page_title="SkyCalc 2.0 | Eco Consultor",
    page_icon="☀️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# BLOQUE 1: BASE DE DATOS Y FUNCIONES CORE (Simuladas para UI)
# ==========================================
# (Aquí pegarás tus funciones reales: calcular_rho_efectiva, simular_ahorro_normativo, etc.)
# Para el esqueleto de la UI, usamos datos de catálogo:

@st.cache_data
def cargar_catalogo_sunoptics():
    return pd.DataFrame({
        'Modelo': ['Signature 4040 SGZ', 'Signature 4040 DGZ', 'Signature 4080 SGZ', 'Signature 4080 DGZ'],
        'VLT': [0.74, 0.67, 0.74, 0.67],
        'SHGC': [0.68, 0.48, 0.68, 0.48],
        'U_Value': [1.20, 0.72, 1.20, 0.72]
    })

df_sun = cargar_catalogo_sunoptics()

# ==========================================
# BLOQUE 2: FRONTEND - SIDEBAR (Inputs del Usuario)
# ==========================================
with st.sidebar:
    st.image("https://via.placeholder.com/300x100.png?text=Eco+Consultor+Logo", use_container_width=True)
    st.header("⚙️ Parámetros del Proyecto")
    
    with st.expander("📍 Ubicación y Clima", expanded=True):
        ciudad = st.selectbox("Ciudad:", ["Querétaro, MX", "Monterrey, MX", "Miami, FL", "San José, CR"])
        st.caption("Los datos climáticos EPW se cargarán automáticamente.")
        
    with st.expander("🏭 Geometría de la Nave", expanded=True):
        ancho = st.number_input("Ancho (m):", min_value=10.0, value=30.0, step=1.0)
        largo = st.number_input("Largo (m):", min_value=10.0, value=50.0, step=1.0)
        alto = st.number_input("Altura (m):", min_value=3.0, value=8.0, step=0.5)
        
    with st.expander("☀️ Configuración Sunoptics", expanded=True):
        modelo_sel = st.selectbox("Modelo de Domo:", df_sun['Modelo'])
        sfr_target = st.slider("Ratio Tragaluz/Suelo (SFR %):", min_value=1.0, max_value=10.0, value=4.0, step=0.1)
        
    st.markdown("---")
    st.markdown("Desarrollado con el motor **SkyCalc 2.0**")

# ==========================================
# BLOQUE 3: FRONTEND - PANEL PRINCIPAL
# ==========================================
st.title("📊 Análisis de Iluminación Natural y Ahorro Energético")
st.markdown("Evalúa el rendimiento de tu diseño integrando domos Sunoptics bajo normativas ASHRAE 90.1.")

# Extraer datos seleccionados
datos_domo = df_sun[df_sun['Modelo'] == modelo_sel].iloc[0]

# --- SECCIÓN DE KPIs ---
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric(label="Ahorro Eléctrico Estimado", value="18,450 kWh/año", delta="Iluminación")
with col2:
    st.metric(label="Autonomía Lumínica (sDA)", value="82.4%", delta="+75% Meta LEED")
with col3:
    st.metric(label="Impacto Térmico HVAC", value="-2,100 kWh/año", delta="Carga AC Añadida", delta_color="inverse")
with col4:
    st.metric(label="Ahorro Energético Neto", value="16,350 kWh/año", delta="Balance Total")

st.markdown("---")

# --- SECCIÓN DE PESTAÑAS (Gráficos y 3D) ---
tab1, tab2, tab3 = st.tabs(["💡 Desempeño Lumínico", "📉 Curva de Optimización Térmica", "🧊 Gemelo Digital 3D"])

with tab1:
    st.subheader("Mapa de Disponibilidad de Luz Natural (Heatmap)")
    # Aquí va tu función: generar_heatmap_ahorro()
    # Placeholder visual:
    st.info("Aquí se renderiza el Heatmap Plotly de 12x24 horas que ya validamos, mostrando las horas exactas donde las lámparas se apagan al 100%.")

with tab2:
    st.subheader("Punto de Equilibrio: Luz vs. HVAC")
    # Aquí va tu función: generar_curva_optimizacion_final()
    # Placeholder visual:
    st.info("Aquí se renderiza la curva iterativa de Plotly (1% al 10% SFR). Ayuda al cliente a ver que poner demasiados domos penaliza el aire acondicionado.")

with tab3:
    st.subheader("Visualización del Proyecto")
    st.info("El visor tridimensional de Pollination (honeybee-vtk) se incrustará aquí. Las sombras responderán al archivo climático seleccionado.")

st.markdown("---")

# ==========================================
# BLOQUE 4: CAPTURA DE LEADS (EL EMBUDO)
# ==========================================
st.header("📥 Descargar Reporte Ejecutivo (PDF)")
st.markdown("""
Este análisis web es preliminar. Para descargar el reporte completo con validaciones normativas, gráficas de retorno de inversión (ROI) y solicitar un modelo BEM detallado, ingresa tus datos:
""")

with st.form("lead_capture_form"):
    col_form1, col_form2 = st.columns(2)
    with col_form1:
        nombre = st.text_input("Nombre Completo *")
        empresa = st.text_input("Empresa *")
    with col_form2:
        email = st.text_input("Correo Electrónico *")
        telefono = st.text_input("Teléfono (Opcional)")
    
    st.caption("Al enviar este formulario, aceptas que un especialista de Eco Consultor te contacte para validar tu proyecto.")
    submit_button = st.form_submit_button("Generar y Enviar PDF 🚀")

    if submit_button:
        if nombre and empresa and email:
            st.success(f"¡Gracias {nombre}! El reporte detallado para {empresa} se está generando y será enviado a {email}.")
            st.balloons()
            # Aquí iría la lógica de FPDF y envío de correo (ej. SendGrid o st.core.mail)
        else:
            st.error("Por favor, completa los campos obligatorios (*).")
