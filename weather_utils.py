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
    """Robust reverse geocoding to identify country and city."""
    user_agents = [f"skycalc_explorer_{random.randint(100, 999)}", "Mozilla/5.0", "SkyCalc/2.0"]

    # Try Photon first
    try:
        geolocator = Photon(user_agent=random.choice(user_agents))
        location = geolocator.reverse(f"{lat}, {lon}", timeout=10)
        if location and 'properties' in location.raw:
            props = location.raw['properties']
            country = props.get('country')
            city = props.get('city') or props.get('name')
            if country:
                return country, city
    except:
        pass

    # Try Nominatim as fallback
    try:
        geolocator = Nominatim(user_agent=random.choice(user_agents))
        location = geolocator.reverse(f"{lat}, {lon}", language='en', timeout=10)
        if location and 'address' in location.raw:
            addr = location.raw['address']
            country = addr.get('country')
            city = addr.get('city') or addr.get('town') or addr.get('village')
            return country, city
    except:
        pass

    return None, None

def geocode_name(name):
    """Geocodes a city/country name into coordinates."""
    user_agents = [f"skycalc_search_{random.randint(100, 999)}"]
    try:
        geolocator = Photon(user_agent=random.choice(user_agents))
        location = geolocator.geocode(name, timeout=10)
        if location:
            return location.latitude, location.longitude
    except:
        pass

    try:
        geolocator = Nominatim(user_agent=random.choice(user_agents))
        location = geolocator.geocode(name, timeout=10)
        if location:
            return location.latitude, location.longitude
    except:
        pass

    return None, None

def normalize_text(text):
    if not text: return ""
    res = text.lower().replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u').replace('ñ', 'n')
    mappings = {
        "espana": "spain",
        "mexico": "mexico",
        "estados unidos": "usa",
        "united states": "usa",
        "brasil": "brazil",
        "costa rica": "costa_rica"
    }
    for k, v in mappings.items():
        if k in res:
            return v
    return res

def extract_city_from_filename(filename):
    name = filename.split('/')[-1].replace('.zip', '')
    name = re.sub(r'\.7\d{5}.*', '', name)
    name = re.sub(r'_TMYx.*', '', name)
    parts = name.split('_')
    if len(parts) >= 3:
        city = parts[2]
    elif len(parts) == 2:
        city = parts[1]
    else:
        city = parts[0]
    return city.replace('.', ' ').replace('-', ' ')
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
        # Fallback default
        country = "Mexico"

    norm_country = normalize_text(country)
    country_url = None
    for name, url in ONEBUILDING_MAPPING.items():
        if norm_country in normalize_text(name) or normalize_text(name) in norm_country:
            country_url = url
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
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        resp = requests.get(country_url, headers=headers, timeout=15)
        if resp.status_code != 200:
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

        estaciones = []
        seen_base_names = set()

        for link in links:
            href = link['href']
            if href.endswith('.zip') and 'TMYx' in href:
                base_name = re.sub(r'\.\d{4}-\d{4}', '', href)
                if base_name in seen_base_names: continue
                seen_base_names.add(base_name)

                full_url = urllib.parse.urljoin(country_url, href)
                city_name = extract_city_from_filename(href)
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

        df = pd.DataFrame(estaciones)

        # Heuristic: Search for city in names or just geocode first few
        candidatos = []
        if city_target:
            mask = df['City_Search'].str.contains(city_target, case=False, na=False)
            candidatos = df[mask].head(10).to_dict('records')

        if len(candidatos) < 3:
            existing_urls = [c['URL_ZIP'] for c in candidatos]
            for _, row in df.head(10).iterrows():
                if row['URL_ZIP'] not in existing_urls:
                    candidatos.append(row.to_dict())

        geolocator = Photon(user_agent=f"skycalc_v{random.randint(100,999)}")
        verified_estaciones = []

        for cand in candidatos[:8]:
            try:
                query = f"{cand['City_Search']}, {country}"
                loc = geolocator.geocode(query, timeout=5)
                if loc:
                    dist = geodesic((lat, lon), (loc.latitude, loc.longitude)).km
                    verified_estaciones.append({
                        'Estación': cand['Estación'],
                        'name': cand['Estación'],
                        'distancia_km': round(dist, 2),
                        'URL_ZIP': cand['URL_ZIP'],
                        'lat': loc.latitude,
                        'lon': loc.longitude
                    })
                time.sleep(0.5)
            except:
                continue

        if verified_estaciones:
            return pd.DataFrame(verified_estaciones).sort_values('distancia_km').head(top_n)

        return pd.DataFrame()
        # Ordenar por los más cercanos y devolver los mejores 5
        df_resultados = pd.DataFrame(resultados).sort_values('distancia_km').head(top_n)
        return df_resultados

    except Exception as e:
        print(f"Error en scraping: {e}")
        return pd.DataFrame()

def descargar_y_extraer_epw(url_zip):
    temp_dir = tempfile.mkdtemp(prefix="epw_")
    zip_fn = os.path.join(temp_dir, "clima.zip")
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        req = urllib.request.Request(url_zip, headers=headers)
        with urllib.request.urlopen(req) as response, open(zip_fn, 'wb') as out_file:
            shutil.copyfileobj(response, out_file)
        
        with zipfile.ZipFile(zip_fn, 'r') as z:
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
                    target_path = os.path.join(tempfile.gettempdir(), f"skycalc_{random.randint(1000,9999)}.epw")
                    shutil.copy(os.path.join(root, f), target_path)
                    return target_path
    except Exception as e:
        print(f"Error: {e}")
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
    """Returns exactly: temp_seca, rad_directa, rad_dif."""
    try:
        epw = EPW(epw_path)
        return {
            'temp_seca': epw.dry_bulb_temperature.values,
            'rad_directa': epw.direct_normal_radiation.values,
            'rad_dif': epw.diffuse_horizontal_radiation.values,
            # Including metadata as well just in case, though the requirement was specific.
            # I'll keep it simple but safe.
            'ciudad': epw.location.city,
            'pais': epw.location.country
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
