# geometry_utils.py
import math
import pathlib
from ladybug_geometry.geometry3d.pointvector import Point3D
from ladybug_geometry.geometry3d.face import Face3D
from dragonfly.model import Model as DFModel, Building
from dragonfly.story import Story, Room2D
from honeybee.aperture import Aperture
from honeybee.boundarycondition import Outdoors # Clase con Mayúscula
from honeybee_vtk.model import Model as VTKModel

def generar_nave_3d_vtk(ancho, largo, altura, sfr_objetivo, domo_ancho_m, domo_largo_m, lat=None, lon=None):
    try:
        # 1. Crear piso y volumen
        puntos_piso = [Point3D(0, 0, 0), Point3D(ancho, 0, 0), Point3D(ancho, largo, 0), Point3D(0, largo, 0)]
        room_df = Room2D('Nave_Principal', Face3D(puntos_piso), floor_to_ceiling_height=altura)
        story = Story('Nivel_0', room_2ds=[room_df])
        building = Building('Planta_Industrial', unique_stories=[story])
        
        # 2. Pasar a Honeybee
        hb_model = DFModel('Modelo_Nave', buildings=[building]).to_honeybee(object_per_model='Building')[0]
        hb_room = hb_model.rooms[0]
        
        # 3. Fix de Boundary Condition (Indispensable para añadir Apertures)
        techo = [f for f in hb_room.faces if f.type.name == 'RoofCeiling'][0]
        techo.boundary_condition = Outdoors() 
        
        # 4. Algoritmo de Cuadrícula (Homologado a la versión 2D impecable)
        area_domo = domo_ancho_m * domo_largo_m
        area_nave = ancho * largo
        num_domos_teoricos = max(1, math.ceil((area_nave * sfr_objetivo) / area_domo))
        
        cols = max(1, round((num_domos_teoricos * (ancho / largo)) ** 0.5))
        filas = max(1, math.ceil(num_domos_teoricos / cols))
        
        dx, dy = ancho / cols, largo / filas
        contador = 1
        
        # LA MAGIA: Eliminamos el 'break' para forzar la simetría completa (cols * filas)
        for i in range(cols):
            for j in range(filas):
                cx = (i * dx) + (dx / 2)
                cy = (j * dy) + (dy / 2)
                
                pt1 = Point3D(cx - domo_ancho_m/2, cy - domo_largo_m/2, altura)
                pt2 = Point3D(cx + domo_ancho_m/2, cy - domo_largo_m/2, altura)
                pt3 = Point3D(cx + domo_ancho_m/2, cy + domo_largo_m/2, altura)
                pt4 = Point3D(cx - domo_ancho_m/2, cy + domo_largo_m/2, altura)
                
                cara_domo = Face3D([pt1, pt2, pt3, pt4])
                techo.add_aperture(Aperture(f"Domo_{contador}", cara_domo))
                contador += 1

        # ==========================================
        # 5. VALIDACIÓN OFICIAL PARA LBT (EnergyPlus / Radiance)
        # ==========================================
        reporte_validacion = hb_model.check_all()
        if reporte_validacion:
            print(f"⚠️ El modelo tiene problemas LBT: {reporte_validacion}")
        else:
            print("✅ GEOMETRÍA PERFECTA: Modelo LBT 100% válido para simulación.")

       # 6. EXPORTAR A VTK (BEM + SUNPATH)
        vtk_file = pathlib.Path('data', 'nave_industrial.vtkjs')
        vtk_file.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            # Si tenemos coordenadas, intentamos inyectar el Sunpath
            if lat is not None and lon is not None:
                from ladybug.sunpath import Sunpath
                from ladybug_display.visualization.sunpath import SunpathDisplay
                from honeybee_display.model import model_to_vis_set
                
                # A) Crear el motor solar con las coordenadas
                sp = Sunpath(latitude=lat, longitude=lon)
                
                # B) Centroide de la nave (la mitad del ancho y largo, altura 0)
                centro = Point3D(ancho / 2, largo / 2, 0)
                
                # C) Radio de la bóveda (70% de la diagonal geométrica para que "abrace" la nave)
                radio = math.sqrt(ancho**2 + largo**2) * 0.7 
                
                # D) Generar la geometría gráfica del Sol
                sp_display = SunpathDisplay(sp, center=centro, radius=radio)
                sp_vis_set = sp_display.to_vis_set()
                
                # E) Convertir la nave industrial a un set visual y fusionarlos
                vis_set = model_to_vis_set(hb_model)
                for geo in sp_vis_set.geometries:
                    vis_set.add_geometry(geo)
                    
                # F) Exportar el conjunto unificado
                vis_set.to_vtkjs(folder=str(vtk_file.parent), name=vtk_file.stem)
                
            else:
                # Exportación clásica (solo edificio) si no llegaron coordenadas
                vtk_model = VTKModel(hb_model)
                vtk_model.to_vtkjs(folder=str(vtk_file.parent), name=vtk_file.stem)
                
        except Exception as e:
            print(f"Aviso Sunpath: No se pudo renderizar la bóveda solar ({e}). Usando renderizado clásico.")
            # RED DE SEGURIDAD: Si la librería gráfica falla, exportamos el edificio normal.
            try:
                vtk_model = VTKModel(hb_model)
                vtk_model.to_vtkjs(folder=str(vtk_file.parent), name=vtk_file.stem)
            except Exception as e2:
                print(f"Error crítico al generar VTK: {e2}")
                return None, 0, 0
        
        # Cálculo final de métricas 
        area_domos_total = sum([ap.area for ap in techo.apertures])
        sfr_real = (area_domos_total / techo.area)
        
        return str(vtk_file), len(techo.apertures), sfr_real

    except Exception as e:
        print(f"Error en geometría: {e}")
        return None, 0, 0
