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

def generar_nave_3d_vtk(ancho, largo, altura, sfr_objetivo, domo_ancho_m, domo_largo_m):
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

        # 6. EXPORTAR A VTK PARA EL VISOR 3D DE STREAMLIT
        vtk_file = pathlib.Path('data', 'nave_industrial.vtkjs')
        vtk_file.parent.mkdir(parents=True, exist_ok=True)
        
        vtk_model = VTKModel(hb_model)
        vtk_model.to_vtkjs(folder=vtk_file.parent, name=vtk_file.stem)
        
        # Cálculo final de métricas 
        area_domos_total = sum([ap.area for ap in techo.apertures])
        sfr_real = (area_domos_total / techo.area)
        
        return str(vtk_file), len(techo.apertures), sfr_real

    except Exception as e:
        print(f"Error en geometría: {e}")
        return None, 0, 0
