
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
import re
import random
import time

# Load mapping of countries to OneBuilding URLs
try:
    with open("onebuilding_mapping.json", "r") as f:
        ONEBUILDING_MAPPING = json.load(f)
except FileNotFoundError:
    ONEBUILDING_MAPPING = {}

def get_location_info(lat, lon):
    """Retorna información de ubicación (país, ciudad) usando geocoding inverso."""
    # Intentar con Photon primero (suele ser más permisivo con 429)
    try:
        geolocator = Photon(user_agent="skycalc_explorer_v5")
        location = geolocator.reverse(f"{lat}, {lon}", timeout=10)
        if location and 'properties' in location.raw:
            props = location.raw['properties']
            country = props.get('country')
            city = props.get('city') or props.get('name')
            return country, city
    except:
        pass

    # Fallback a Nominatim con un user agent único
    try:
        ua = f"skycalc_agent_{random.randint(1000, 9999)}"
        geolocator = Nominatim(user_agent=ua)
        location = geolocator.reverse(f"{lat}, {lon}", language='en', timeout=10)
        if location and 'address' in location.raw:
            addr = location.raw['address']
            country = addr.get('country')
            city = addr.get('city') or addr.get('town') or addr.get('village') or addr.get('suburb')
            return country, city
    except Exception as e:
        print(f"Error en geocoding: {e}")
    return None, None

def extract_city_from_filename(filename):
    """
    Intenta extraer el nombre de la ciudad del formato de OneBuilding.
    Ejemplo: MEX_CMX_Cuidad.Mexico-Mexico.City.Intl.AP-Juarez.Intl.AP.766793_TMYx.zip
    """
    # Quitar extensiones
    name = filename.split('/')[-1].replace('.zip', '')
    # Quitar sufijos comunes
    name = re.sub(r'\.7\d{5}.*', '', name) # Quitar ID de WMO y años
    name = re.sub(r'_TMYx.*', '', name)
    
    # Split por _
    parts = name.split('_')
    if len(parts) >= 3:
        # Suele ser PAIS_ESTADO_CIUDAD
        city = parts[2]
    elif len(parts) == 2:
        city = parts[1]
    else:
        city = parts[0]

    return city.replace('.', ' ').replace('-', ' ')

def obtener_estaciones_cercanas(lat, lon, top_n=5):
    country, city_target = get_location_info(lat, lon)
    if not country:
        country = "Mexico"

    country_url = None
    for name, url in ONEBUILDING_MAPPING.items():
        if country.lower() in name.lower() or name.lower() in country.lower():
            country_url = url
            break

    if not country_url:
        return pd.DataFrame()

    try:
        resp = requests.get(country_url, timeout=15)
        if resp.status_code != 200:
            return pd.DataFrame()

        soup = BeautifulSoup(resp.text, 'html.parser')
        links = soup.find_all('a', href=True)

        estaciones = []
        seen_base_names = set()

        for link in links:
            href = link['href']
            if href.endswith('.zip') and 'TMYx' in href:
                # Filtrar versiones (usar la más reciente o base)
                base_name = re.sub(r'\.\d{4}-\d{4}', '', href)
                if base_name in seen_base_names:
                    continue
                seen_base_names.add(base_name)

                full_url = urllib.parse.urljoin(country_url, href)
                city_name = extract_city_from_filename(href)

                estaciones.append({
                    'Estación': base_name.replace('.zip', '').split('/')[-1],
                    'URL_ZIP': full_url,
                    'City_Search': city_name
                })

        if not estaciones:
            return pd.DataFrame()

        df = pd.DataFrame(estaciones)

        # Estrategia de búsqueda inteligente:
        # 1. Priorizar estaciones que contengan el nombre de la ciudad objetivo
        # 2. Si hay pocas, tomar una muestra representativa
        # 3. Geocodificar solo los candidatos más probables

        candidatos = []
        if city_target:
            mask = df['City_Search'].str.contains(city_target, case=False, na=False)
            candidatos = df[mask].head(10).to_dict('records')

        # Si no hay candidatos por nombre, tomar los primeros 5 como fallback
        if len(candidatos) < 3:
            # Evitar duplicados si ya agregamos algunos
            existing_urls = [c['URL_ZIP'] for c in candidatos]
            for _, row in df.head(5).iterrows():
                if row['URL_ZIP'] not in existing_urls:
                    candidatos.append(row.to_dict())

        # Usar Photon para geocodificar candidatos (más rápido y menos bloqueos)
        geolocator = Photon(user_agent="skycalc_explorer_v6")
        verified_estaciones = []

        for cand in candidatos[:10]:
            try:
                query = f"{cand['City_Search']}, {country}"
                loc = geolocator.geocode(query, timeout=5)
                if loc:
                    dist = geodesic((lat, lon), (loc.latitude, loc.longitude)).km
                    verified_estaciones.append({
                        'Estación': cand['Estación'],
                        'Distancia (km)': round(dist, 2),
                        'URL_ZIP': cand['URL_ZIP'],
                        'LAT': loc.latitude,
                        'LON': loc.longitude
                    })
                time.sleep(1) # Respetar rate-limit
            except:
                continue

        if verified_estaciones:
            return pd.DataFrame(verified_estaciones).sort_values('Distancia (km)').head(top_n)

        # Fallback absoluto
        df['Distancia (km)'] = 0
        df['LAT'] = lat
        df['LON'] = lon
        return df.head(top_n)

    except Exception as e:
        print(f"Error: {e}")
        return pd.DataFrame()

def descargar_y_extraer_epw(url_zip):
    """Descarga ZIP, extrae EPW y lo guarda en un archivo temporal único."""
    temp_dir = tempfile.mkdtemp(prefix="epw_process_")
    zip_fn = os.path.join(temp_dir, "clima.zip")
    try:
        opener = urllib.request.build_opener()
        opener.addheaders = [('User-agent', 'Mozilla/5.0')]
        urllib.request.install_opener(opener)
        urllib.request.urlretrieve(url_zip, zip_fn)
        
        with zipfile.ZipFile(zip_fn, 'r') as z:
            z.extractall(temp_dir)

        epw_files = []
        for root, _, files in os.walk(temp_dir):
            for f in files:
                if f.endswith('.epw'):
                    epw_files.append(os.path.join(root, f))

        if not epw_files:
            return None

        # Crear archivo temporal único para el EPW
        fd, target_path = tempfile.mkstemp(suffix=".epw", prefix="skycalc_")
        os.close(fd)
        shutil.copy(epw_files[0], target_path)
        return target_path
        
    except Exception as e:
        print(f"Error en descarga/extracción: {e}")
        return None
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

def procesar_datos_clima(epw_path):
    try:
        epw = EPW(epw_path)
        return {
            'metadata': {
                'ciudad': epw.location.city,
                'pais': epw.location.country,
                'lat': epw.location.latitude,
                'lon': epw.location.longitude,
            },
            'ciudad': epw.location.city,
            'pais': epw.location.country,
            'temp_seca': epw.dry_bulb_temperature.values,
            'hum': epw.relative_humidity.values,
            'rad_directa': epw.direct_normal_radiation.values,
            'rad_dir': epw.direct_normal_radiation.values,
            'rad_dif': epw.diffuse_horizontal_radiation.values
        }
    except Exception as e:
        print(f"Error: {e}")
        return None
