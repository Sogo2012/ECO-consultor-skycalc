import json
import requests
import os
import zipfile
import urllib.request
from geopy.distance import geodesic
import pandas as pd

# Hardcoded major stations for Costa Rica and some others for the demo
# In a real scenario, this would be a large JSON or fetched from a working URL
SAMPLE_STATIONS = [
    {
        "name": "San Jose Santamaria Intl AP",
        "location": [9.998, -84.211],
        "source": "OneBuilding",
        "epw": "https://climate.onebuilding.org/WMO_Region_4_North_and_Central_America/CRI_Costa_Rica/CRI_AL_San.Jose-Santamaria.Intl.AP.787620_TMYx.2009-2023.zip"
    },
    {
        "name": "Limon Intl AP",
        "location": [9.957, -83.022],
        "source": "OneBuilding",
        "epw": "https://climate.onebuilding.org/WMO_Region_4_North_and_Central_America/CRI_Costa_Rica/CRI_LI_Limon.Intl.AP.787670_TMYx.2009-2023.zip"
    },
    {
        "name": "Liberia Intl AP",
        "location": [10.593, -85.544],
        "source": "OneBuilding",
        "epw": "https://climate.onebuilding.org/WMO_Region_4_North_and_Central_America/CRI_Costa_Rica/CRI_GU_Quiros-Liberia.Intl.AP.787740_TMYx.2009-2023.zip"
    },
    {
        "name": "Mexico City Intl AP",
        "location": [19.436, -99.072],
        "source": "OneBuilding",
        "epw": "https://climate.onebuilding.org/WMO_Region_4_North_and_Central_America/MEX_Mexico/DF_Distrito_Federal/MEX_DF_Mexico.City-Juarez.Intl.AP.766790_TMYx.2009-2023.zip"
    },
    {
        "name": "Queretaro Intl AP",
        "location": [20.617, -100.186],
        "source": "OneBuilding",
        "epw": "https://climate.onebuilding.org/WMO_Region_4_North_and_Central_America/MEX_Mexico/QA_Queretaro/MEX_QA_Queretaro.Intl.AP.766250_TMYx.2009-2023.zip"
    },
    {
        "name": "Bogota Eldorado Intl AP",
        "location": [4.701, -74.146],
        "source": "OneBuilding",
        "epw": "https://climate.onebuilding.org/WMO_Region_3_South_America/COL_Colombia/DC_Bogota/COL_DC_Bogota-Eldorado.Intl.AP.802220_TMYx.2009-2023.zip"
    },
    {
        "name": "Madrid Barajas Intl AP",
        "location": [40.472, -3.560],
        "source": "OneBuilding",
        "epw": "https://climate.onebuilding.org/WMO_Region_6_Europe/ESP_Spain/MD_Madrid/ESP_MD_Madrid-Barajas.Intl.AP.082210_TMYx.2009-2023.zip"
    },
    {
        "name": "Miami Intl AP",
        "location": [25.793, -80.290],
        "source": "OneBuilding",
        "epw": "https://climate.onebuilding.org/WMO_Region_4_North_and_Central_America/USA_United_States_of_America/FL_Florida/USA_FL_Miami.Intl.AP.722020_TMYx.2009-2023.zip"
    },
    {
        "name": "London Heathrow Intl AP",
        "location": [51.470, -0.454],
        "source": "OneBuilding",
        "epw": "https://climate.onebuilding.org/WMO_Region_6_Europe/GBR_United_Kingdom/ENG_England/GBR_ENG_London.Heathrow.Intl.AP.037720_TMYx.2009-2023.zip"
    }
]

def obtener_estaciones_cercanas(lat, lon, top_n=5):
    """
    Busca las estaciones más cercanas a las coordenadas dadas.
    Actualmente usa una lista local de ejemplo.
    """
    estaciones_con_distancia = []
    for st in SAMPLE_STATIONS:
        dist = geodesic((lat, lon), st['location']).km
        st_copy = st.copy()
        st_copy['distancia_km'] = round(dist, 2)
        estaciones_con_distancia.append(st_copy)
    
    # Ordenar por distancia
    df = pd.DataFrame(estaciones_con_distancia).sort_values('distancia_km')
    return df.head(top_n)

import shutil
import tempfile

def descargar_y_extraer_epw(url_zip):
    """
    Descarga un archivo ZIP de clima y extrae el archivo EPW en un directorio temporal único.
    """
    temp_dir = tempfile.mkdtemp(prefix="epw_data_")
    zip_fn = os.path.join(temp_dir, "clima.zip")
    print(f"📦 Descargando desde {url_zip}...")
    
    try:
        # User agent to avoid blocks
        opener = urllib.request.build_opener()
        opener.addheaders = [('User-agent', 'Mozilla/5.0')]
        urllib.request.install_opener(opener)
        urllib.request.urlretrieve(url_zip, zip_fn)
        
        with zipfile.ZipFile(zip_fn, 'r') as z:
            z.extractall(temp_dir)
        
        # Buscar el archivo .epw de forma recursiva (algunos OneBuilding ZIP tienen subcarpetas)
        epw_files = []
        for root, _, files in os.walk(temp_dir):
            for f in files:
                if f.endswith('.epw'):
                    epw_files.append(os.path.join(root, f))
        
        if not epw_files:
            raise Exception("No se encontró ningún archivo .epw en el ZIP.")
        
        # Retornar el primer archivo EPW encontrado
        return epw_files[0]
    except Exception as e:
        # Limpiar en caso de error
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        raise Exception(f"Error al descargar o extraer EPW: {e}")

if __name__ == "__main__":
    # Test with Juan Santamaria Airport
    lat, lon = 9.998, -84.211
    print(f"Buscando estaciones cerca de {lat}, {lon}...")
    cercanas = obtener_estaciones_cercanas(lat, lon)
    print(cercanas[['name', 'distancia_km']])
    
    mejor = cercanas.iloc[0]
    epw_path = descargar_y_extraer_epw(mejor['epw'])
    print(f"EPW extraído en: {epw_path}")
