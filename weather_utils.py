import json
import requests
import os
import zipfile
import pandas as pd
from geopy.distance import geodesic
from geopy.geocoders import Nominatim, Photon
from ladybug.epw import EPW
import shutil
import tempfile
import urllib.parse
import random

# 1. Cargar el Diccionario Global
try:
    with open("onebuilding_mapping.json", "r") as f:
        ONEBUILDING_MAPPING = json.load(f)
except FileNotFoundError:
    ONEBUILDING_MAPPING = {}

def get_country_from_coords(lat, lon):
    """Obtiene el nombre del país en inglés a partir de coordenadas para asegurar el match."""
    try:
        # Usamos Nominatim forzando el idioma inglés para que coincida con OneBuilding
        ua = f"skycalc_agent_{random.randint(1000, 9999)}"
        geolocator = Nominatim(user_agent=ua)
        location = geolocator.reverse(f"{lat}, {lon}", timeout=10, language='en')
        if location and 'address' in location.raw:
            return location.raw['address'].get('country', '')
    except:
        pass
    return ""

def obtener_estaciones_cercanas(lat, lon, top_n=5):
    """Raspa la web de OneBuilding y devuelve las estaciones más cercanas."""
    country_name = get_country_from_coords(lat, lon)
    if not country_name:
        return pd.DataFrame() # No se pudo identificar el país

    # 2. Búsqueda Inteligente del País en el JSON
    target_url = None
    country_clean = country_name.lower().replace(" ", "")
    
    for key, url in ONEBUILDING_MAPPING.items():
        key_clean = key.lower().replace("_", "").replace(".", "")
        if country_clean in key_clean or key_clean in country_clean:
            target_url = url
            break
            
    if not target_url:
        return pd.DataFrame() # El país no está en la base de datos

    # 3. Web Scraping de la tabla de estaciones
    try:
        base_url = target_url.rsplit('/', 1)[0] + '/'
        
        # Leemos todas las tablas HTML de la página
        dfs = pd.read_html(target_url)
        if not dfs: return pd.DataFrame()
        
        df_stations = dfs[0] # Generalmente la primera tabla tiene los datos
        
        # Limpiar la tabla (OneBuilding usa columnas como 'Station', 'Lat', 'Lon', 'Elev', 'ZIP')
        columnas_validas = [col for col in df_stations.columns if 'Lat' in col or 'Lon' in col or 'Station' in col or 'ZIP' in col]
        if not columnas_validas: return pd.DataFrame()
        
        df_stations = df_stations.dropna(subset=['Lat', 'Lon'])
        
        # 4. Calcular distancias
        def calc_distance(row):
            try:
                return geodesic((lat, lon), (float(row['Lat']), float(row['Lon']))).km
            except:
                return 9999
                
        df_stations['distancia_km'] = df_stations.apply(calc_distance, axis=1)
        df_stations = df_stations.sort_values('distancia_km').head(top_n)
        
        # 5. Formatear salida para evitar KeyErrors
        resultados = []
        for _, row in df_stations.iterrows():
            # Construir URL del ZIP
            zip_name = str(row.get('ZIP', '')).strip()
            if zip_name and zip_name.endswith('.zip'):
                full_zip_url = urllib.parse.urljoin(base_url, zip_name)
                
                resultados.append({
                    'name': str(row.get('Station', 'Estación EPW')),
                    'lat': float(row['Lat']),
                    'lon': float(row['Lon']),
                    'distancia_km': round(row['distancia_km'], 1),
                    'epw': full_zip_url
                })
                
        return pd.DataFrame(resultados)
        
    except Exception as e:
        print(f"Error en scraping: {e}")
        return pd.DataFrame()

def descargar_y_extraer_epw(url_zip):
    """Descarga el ZIP, lo extrae temporalmente y devuelve la ruta del EPW."""
    temp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(temp_dir, "clima.zip")
    
    try:
        response = requests.get(url_zip, stream=True, timeout=20)
        response.raise_for_status()
        with open(zip_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                
        with zipfile.ZipFile(zip_path, 'r') as z:
            z.extractall(temp_dir)

        # Buscar el archivo EPW extraído
        for root, _, files in os.walk(temp_dir):
            for f in files:
                if f.endswith('.epw'):
                    fd, target_path = tempfile.mkstemp(suffix=".epw", prefix="skycalc_")
                    os.close(fd)
                    shutil.copy(os.path.join(root, f), target_path)
                    return target_path
        return None
    except Exception as e:
        print(f"Error en descarga: {e}")
        return None
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

def procesar_datos_clima(epw_path):
    """Usa Ladybug para extraer los vectores de 8760 horas."""
    try:
        epw = EPW(epw_path)
        return {
            'ciudad': epw.location.city,
            'pais': epw.location.country,
            'temp_seca': epw.dry_bulb_temperature.values,
            'rad_directa': epw.direct_normal_radiation.values,
            'rad_difusa': epw.diffuse_horizontal_radiation.values
        }
    except Exception as e:
        print(f"Error con Ladybug EPW: {e}")
        return None
