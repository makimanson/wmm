import os
import hashlib
import gi
import glob
import time
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk

class MonitorManager:
    def __init__(self):
        self.display = Gdk.Display.get_default()

    def get_physical_edid_hashes(self):
        """
        Escanea el sistema en busca de todos los monitores con estado 'connected'
        y genera sus hashes reales de hardware.
        """
        hashes = []
        # Buscamos en todas las tarjetas y conectores
        for status_path in glob.glob("/sys/class/drm/card*-*/status"):
            try:
                with open(status_path, 'r') as f:
                    if "connected" in f.read():
                        edid_path = status_path.replace("status", "edid")
                        if os.path.exists(edid_path):
                            with open(edid_path, "rb") as e:
                                data = e.read(128)
                                if len(data) >= 128:
                                    h = hashlib.shake_128(data).hexdigest(4)
                                    hashes.append(h)
            except:
                continue
        return hashes

    def get_active_monitors_map(self):
        self.display = Gdk.Display.get_default()
        if self.display:
            self.display.sync() # Asegurar que GDK está al día con el SO
            
        monitors_data = {}
        n_monitors = self.display.get_n_monitors()
        physical_hashes = self.get_physical_edid_hashes()

        for i in range(n_monitors):
            monitor = self.display.get_monitor(i)
            geometry = monitor.get_geometry()
            connector = monitor.get_model()
            manufacturer = monitor.get_manufacturer()  # Código PNP o nombre del fabricante
            w_mm = monitor.get_width_mm()
            h_mm = monitor.get_height_mm()
            is_primary = monitor.is_primary()

            if i < len(physical_hashes):
                m_hash = physical_hashes[i]
            else:
                m_hash = hashlib.shake_128(connector.encode()).hexdigest(4)
            
            orientation = "horizontal" if geometry.width >= geometry.height else "vertical"

            monitors_data[m_hash] = {
                "connector": connector,
                "manufacturer": manufacturer,
                "x": geometry.x,
                "y": geometry.y,
                "width": geometry.width,
                "height": geometry.height,
                "width_mm": w_mm,
                "height_mm": h_mm,
                "orientation": orientation,
                "primary": is_primary,
            }
            
        return monitors_data

    def get_total_canvas_geometry(self, monitors_map):
        """
        Calcula el tamaño del lienzo basándose en el punto más lejano 
        al que llega cualquier monitor (Borde derecho y Borde inferior).
        """
        if not monitors_map:
            return 0, 0

        max_x_edge = 0
        max_y_edge = 0

        for m in monitors_map.values():
            # El monitor ocupa desde su 'x' hasta 'x + width'
            current_right = m['x'] + m['width']
            current_bottom = m['y'] + m['height']

            if current_right > max_x_edge:
                max_x_edge = current_right
            if current_bottom > max_y_edge:
                max_y_edge = current_bottom

        return max_x_edge, max_y_edge

    @staticmethod
    def scale_monitors_to_area(monitors_map, area_w, area_h, margin=10):
        """
        Escala los monitores para caber en el área dada, manteniendo la proporción.
        Retorna un diccionario {hash: {x, y, w, h}} con las coordenadas escaladas.
        """
        if not monitors_map:
            return {}

        # Calcular bounding box
        min_x = min_y = float('inf')
        max_x = max_y = 0
        for m_data in monitors_map.values():
            x, y, w, h = m_data['x'], m_data['y'], m_data['width'], m_data['height']
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x + w)
            max_y = max(max_y, y + h)

        bb_width = max_x - min_x
        bb_height = max_y - min_y
        if bb_width <= 0 or bb_height <= 0:
            return {}

        available_w = area_w - margin * 2
        # Si area_h es un target fijo (ej. 150), lo usamos directamente
        if area_h > 0:
            available_h = area_h - margin * 2
        else:
            # Si no, usar el bounding box natural (caso de redimensionado)
            available_h = bb_height
        scale = min(available_w / bb_width, available_h / bb_height)

        scaled_bb_w = bb_width * scale
        scaled_bb_h = bb_height * scale
        offset_x = margin
        offset_y = margin

        scaled_monitors = {}
        for m_hash, m_data in monitors_map.items():
            rel_x = m_data['x'] - min_x
            rel_y = m_data['y'] - min_y
            scaled_monitors[m_hash] = {
                'x': int(rel_x * scale) + offset_x,
                'y': int(rel_y * scale) + offset_y,
                'w': int(m_data['width'] * scale),
                'h': int(m_data['height'] * scale)
            }
        return scaled_monitors

# --- MANTENEMOS TU BLOQUE DE AUTODIAGNÓSTICO ---
if __name__ == "__main__":
    manager = MonitorManager()
    active = manager.get_active_monitors_map()
    canvas_w, canvas_h = manager.get_total_canvas_geometry(active)
    
    print(f"--- Diagnóstico de Monitores ---")
    for m_hash, data in active.items():
        # Verás que los IDs ahora coincidirán con los de HARDWARE de tu test
        print(f"ID: {m_hash} | {data['width']}x{data['height']} en ({data['x']},{data['y']}) | {data['orientation']}")
    
    print(f"---")
    print(f"Lienzo Maestro Requerido: {canvas_w}x{canvas_h}")
