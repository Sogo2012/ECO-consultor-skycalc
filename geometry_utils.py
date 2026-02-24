import math
from ladybug_geometry.geometry3d.pointvector import Point3D
from ladybug_geometry.geometry3d.face import Face3D
from dragonfly.model import Model, Building
from dragonfly.story import Story, Room2D
from honeybee.room import Room
from honeybee.aperture import Aperture

def generar_nave_industrial(ancho, largo, altura, sfr_objetivo=0.04):
    """
    Genera un modelo 3D de Honeybee de una nave industrial con domos en el techo.
    
    Args:
        ancho (float): Ancho de la nave en metros (X).
        largo (float): Largo de la nave en metros (Y).
        altura (float): Altura de piso a techo en metros (Z).
        sfr_objetivo (float): Sky Fraction Ratio (0.0 a 1.0). Ejemplo: 4% = 0.04.
        
    Returns:
        hb_model (Model): Modelo de Honeybee listo para simulación.
        hb_room (Room): La zona térmica principal.
    """
    try:
        print(f"Generando Nave Industrial: {ancho}m x {largo}m x {altura}m | SFR: {sfr_objetivo*100}%")
        
        # 1. Ladybug Geometry: El piso 2D de la nave
        puntos_piso = [
            Point3D(0, 0, 0),
            Point3D(ancho, 0, 0),
            Point3D(ancho, largo, 0),
            Point3D(0, largo, 0)
        ]
        piso_cara = Face3D(puntos_piso)

        # 2. Dragonfly: Extruir el cuarto 3D
        room_df = Room2D('Nave_Principal', piso_cara, floor_to_ceiling_height=altura)
        
        # Crear estructura base
        story = Story('Nivel_0', room_2ds=[room_df])
        building = Building('Planta_Industrial', unique_stories=[story])
        model_df = Model('Modelo_DF', buildings=[building])

        # 3. Traducción a Honeybee (El Motor Físico)
        hb_model = model_df.to_honeybee(object_per_model='Building')[0]
        
        # Extraer la zona térmica (Room)
        hb_room = hb_model.rooms[0]
        
        # 4. Magia SkyCalc: Perforar el Techo (Generar Domos)
        # Identificar la cara del techo
        techo = None
        for face in hb_room.faces:
            if face.type.name == 'RoofCeiling':
                techo = face
                break
                
        if techo:
            # Aquí aplicaremos la lógica de la cuadrícula de domos.
            # Por ahora, usamos una función nativa de Honeybee para perforar 
            # el techo basándonos en el ratio (SFR = Roof Window-to-Wall Ratio)
            # En la siguiente iteración, haremos la cuadrícula exacta de 1.2m x 2.4m
            techo.apertures_by_ratio(sfr_objetivo)
            print(f"Éxito: Se generaron {len(techo.apertures)} domos en el techo.")
        else:
            print("Error: No se encontró un techo válido en la geometría.")

        return hb_model, hb_room
        
    except Exception as e:
        print(f"Error fatal en motor geométrico: {e}")
        return None, None
