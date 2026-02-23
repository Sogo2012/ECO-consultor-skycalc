import json
import requests
import os
import zipfile
import urllib.request
from geopy.distance import geodesic
from geopy.geocoders import Nominatim, Photon
import pandas as pd
from ladybug.epw import EPW
import shutil
import tempfile
from bs4 import BeautifulSoup
import urllib.parse
import random

# 1. Cargar el Diccionario Global
try:
    with open("onebuilding_mapping.json", "r") as f:
        ONEBUILDING_MAPPING = json.load(f)
except FileNotFoundError:
    ONEBUILDING_MAPPING = {}

def get_location_info(lat, lon):
    """Retorna el país en inglés para asegurar el match con OneBuilding."""
    try:
        # Photon es rápido y menos restrictivo
        geolocator = Photon(user_agent="skycalc_explorer_v5")
        location = geolocator.reverse(f"{lat}, {lon}", timeout=10)
        if location and 'properties' in location.raw:
            return location.raw['properties'].get('country')
    except:
        pass

    try:
        # Nominatim como respaldo forzando idioma inglés
        ua = f"skycalc_agent_{random.randint(1000, 9999)}"
        geolocator = Nominatim(user_agent=ua)
        location = geolocator.reverse(f"{lat}, {lon}", language='en', timeout=10)
        if location and 'address' in location.raw:
            return location.raw['address'].get('country')
    except:
        pass
    return None

def obtener_estaciones_cercanas(lat, lon, top_n=5):
    """Raspa OneBuilding leyendo las coordenadas reales y extrayendo los Zips."""
    country = get_location_info(lat, lon)
    if not country:
        return pd.DataFrame()

    # Búsqueda de país en la base de datos
    country_norm = "".join(e for e in country.lower() if e.isalnum())
    target_url = None
    
    for key, url in ONEBUILDING_MAPPING.items():
        key_norm = "".join(e for e in key.lower() if e.isalnum())
        if country_norm in key_norm or key_norm in country_norm:
            target_url = url
            break
            
    if not target_url:
        return pd.DataFrame()

    # Scraping Quirúrgico con BeautifulSoup
    try:
        base_url = target_url.rsplit('/', 1)[0] + '/'
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(target_url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        table = soup.find('table')
        if not table:
            return pd.DataFrame()

        # Encontrar en qué columna está cada dato
        headers = [th.text.strip().lower() for th in table.find_all('th')]
        try:
            lat_idx = headers.index('lat')
            lon_idx = headers.index('lon')
            station_idx = headers.index('station')
        except ValueError:
            return pd.DataFrame() # La tabla no tiene el formato esperado

        resultados = []
        
        # Leer fila por fila
        for tr in table.find_all('tr'):
            tds = tr.find_all('td')
            if len(tds) <= max(lat_idx, lon_idx, station_idx): 
                continue
            
            # Buscar el archivo .zip en esa fila
            zip_url = None
            for a in tr.find_all('a', href=True):
                if a['href'].endswith('.zip'):
                    zip_url = urllib.parse.urljoin(base_url, a['href'])
                    break
                    
            if not zip_url:
                continue # Si no hay archivo zip, saltamos a la siguiente

            try:
                st_lat = float(tds[lat_idx].text.strip())
                st_lon = float(tds[lon_idx].text.strip())
                st_name = tds[station_idx].text.strip()
                
                # Calcular la distancia real a nuestro proyecto
                dist = geodesic((lat, lon), (st_lat, st_lon)).km
                
                resultados.append({
                    'name': st_name,
                    'lat': st_lat,
                    'lon': st_lon,
                    'distancia_km': round(dist, 1),
                    'epw': zip_url
                })
            except ValueError:
                continue # Fila con datos corruptos o texto donde van números

        if not resultados:
            return pd.DataFrame()

        # Ordenar por los más cercanos y devolver los mejores 5
        df_resultados = pd.DataFrame(resultados).sort_values('distancia_km').head(top_n)
        return df_resultados

    except Exception as e:
        print(f"Error en scraping: {e}")
        return pd.DataFrame()

def descargar_y_extraer_epw(url_zip):
    """Descarga el ZIP, lo extrae y devuelve la ruta del EPW."""
    temp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(temp_dir, "clima.zip")
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url_zip, stream=True, timeout=20, headers=headers)
        response.raise_for_status()
        with open(zip_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                
        with zipfile.ZipFile(zip_path, 'r') as z:
            z.extractall(temp_dir)

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
    """Usa Ladybug para extraer los vectores de 8760 horas, garantizando las llaves."""
    try:
        epw = EPW(epw_path)
        return {
            'ciudad': epw.location.city,
            'pais': epw.location.country,
            'temp_seca': epw.dry_bulb_temperature.values,
            'rad_directa': epw.direct_normal_radiation.values,
            'rad_dif': epw.diffuse_horizontal_radiation.values  # <--- SE MANTIENE EL NOMBRE EXACTO QUE USA APP.PY
        }
    except Exception as e:
        print(f"Error con Ladybug EPW: {e}")
        return None
