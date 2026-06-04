"""
WMM - Platform Core
Lee settings_core.json, carga el módulo de plataforma adecuado
y expone sus funciones como propias.
"""
import os
import json
import importlib

class PlatformManager:
    def __init__(self):
        # Leer settings_core.json
        import os, json
        config_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'settings_core.json')
        with open(config_path, 'r') as f:
            config = json.load(f)

        platform_name = config['platform']   # 'linux', 'windows', 'darwin'
        desktop = config.get('desktop', '')   # 'cinnamon', 'kde', 'gnome', etc.

        # 1. Cargar el módulo del SO
        try:
            so_module = importlib.import_module(f'.{platform_name}', package='wmm_platform')
        except ImportError:
            so_module = importlib.import_module('.generic', package='wmm_platform')

        # Exponer funciones del SO (comunes a todos los escritorios de ese SO)
        self.get_terminal = so_module.get_terminal
        self.open_file = so_module.open_file
        self.setup_translations = so_module.setup_translations
        self.send_notification = so_module.send_notification
        self.open_in_terminal = so_module.open_in_terminal
        # La función _() para traducciones también puede venir del SO
        if hasattr(so_module, '_'):
            self._ = so_module._

        # 2. Si hay un entorno de escritorio específico, cargarlo y sobrescribir funciones
        if desktop:
            try:
                desktop_module = importlib.import_module(f'.{desktop}', package='wmm_platform')
                # Sobrescribir solo las funciones que el escritorio implementa
                if hasattr(desktop_module, 'get_monitors'):
                    self.get_monitors = desktop_module.get_monitors
                if hasattr(desktop_module, 'set_wallpaper'):
                    self.set_wallpaper = desktop_module.set_wallpaper
                # etc.
            except ImportError:
                pass  # Usaremos las del SO o las que ya tengamos

        # 3. Importar funciones de cálculo comunes (núcleo agnóstico)
        from monitor_manager import scale_monitors_to_area, get_total_canvas_geometry
        self.scale_monitors_to_area = scale_monitors_to_area
        self.get_total_canvas_geometry = get_total_canvas_geometry
