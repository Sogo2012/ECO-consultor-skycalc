from weather_utils import obtener_estaciones_cercanas
import pandas as pd

lat, lon = 20.5888, -100.3899
print(f"Testing with {lat}, {lon}")
df = obtener_estaciones_cercanas(lat, lon)
print("Result:")
print(df)
