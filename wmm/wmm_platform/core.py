
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

"""
WMM - Wallpaper Multi-Monitor Manager

core.py - Platform Core
==========================================================
Lee settings_core.json, carga el módulo de plataforma adecuado
y expone sus funciones como propias.
"""

import os
import json
import importlib
import types

from debug_logger import log_event, set_file_locking

# Identidad común del core WMM. No confundir con app_domain,
# que pertenece a la integración/frontend activo.
WMM_ID = 'wmm@maki'

# Nombre único del icono de aplicación; los consumidores reciben su ruta resuelta.
WMM_ICON_FILENAME = 'WMM-icon.ico'

def _read_ini(filepath):
    """Lee un archivo .ini y devuelve un diccionario con las claves y valores."""
    config = {}
    if not os.path.exists(filepath):
        return config
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            # Ignorar comentarios y líneas vacías
            if not line or line.startswith('#') or line.startswith(';'):
                continue
            if '=' in line:
                key, value = line.split('=', 1)
                config[key.strip()] = value.strip()
    return config

def _write_ini(filepath, config):
    """Escribe un diccionario en un archivo .ini."""
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write("# WMM Platform Configuration\n")
        for key, value in config.items():
            f.write(f"{key}={value}\n")

# ==========================================================
# PERFILES DE LANZAMIENTO — RESOLUCIÓN COMÚN
# ==========================================================
# ORIGEN:
#   open_file() de linux.py, win32.py o mac.py proporciona el ejecutable
#   predeterminado, la ruta del archivo y la capacidad solicitada.
#
# FUNCIÓN:
#   Lee launch_profiles.json desde el data_dir resuelto por PlatformManager,
#   identifica el editor y construye sus argumentos parametrizados.
#
# DESTINO:
#   Devuelve el comando preparado al open_file() de origen para su ejecución.
#   Si no existe un perfil compatible, devuelve None y la plataforma
#   conserva su mecanismo habitual de apertura.
#
# LÍMITE:
#   El núcleo no identifica aplicaciones ni ejecuta procesos.
#   Ambas responsabilidades pertenecen al sistema operativo.
# ==========================================================

def _build_launch_command(executable, path, capability, params, data_dir):
    """
    Construye el comando mediante los perfiles de lanzamiento comunes.

    El SO identifica el ejecutable; el núcleo únicamente interpreta sus
    capacidades y argumentos, sin intervenir en el lanzamiento.
    """
    if not executable or not data_dir:
        return None

    # Los perfiles son comunes a todos los SO y se cargan desde el DATA_DIR
    # que ya ha resuelto PlatformManager.
    try:
        with open(os.path.join(data_dir, "launch_profiles.json"), "r", encoding="utf-8") as f:
            profiles = json.load(f)

    except (OSError, json.JSONDecodeError) as error:
        log_event(f"No se pudieron cargar perfiles de lanzamiento: {error}",
            origin="CORE", level="WARN", reason="GENERIC")
        return None

    if not isinstance(profiles, dict):
        return None

    executable_name = os.path.basename(executable)
    values = {"file": path, **params}

    for profile in profiles.values():
        if executable_name not in profile.get("executables", []):
            continue

        arguments = profile.get(capability)
        if not isinstance(arguments, list):
            return None

        try:
            return [executable] + [argument.format(**values) for argument in arguments]

        except KeyError as error:
            log_event(f"Parámetro de lanzamiento no disponible: {error}",
                origin="CORE", level="WARN", reason="GENERIC")
            return None

    return None

class PlatformManager:
    def __init__(self):
        """
        Constructor del núcleo de plataforma.
        Detecta el SO y el escritorio, carga los módulos adecuados y expone
        todas las funciones necesarias para que el motor funcione de forma
        agnóstica al sistema operativo.
        """
        # ----------------------------------------------------------
        # 0. CONFIGURACIÓN DE PLATAFORMA (settings_core.json)
        # ----------------------------------------------------------
        # _ensure_platform_config() garantiza que el archivo existe.
        # Si no existe (primera instalación desde Spices), lo crea
        # detectando el SO y el escritorio automáticamente.
        config = self._ensure_platform_config()
        config = self._resolve_common_paths(config)

        self.platform = config['platform']
        self.desktop = config['desktop']

        # Win32 no participa en la selección X11/Wayland de Linux. Mantener
        # una identidad propia evita que la ausencia de XDG lo convierta
        # artificialmente en X11.
        if self.platform == 'win32':
            self.graphics_engine = 'win32'
        else:
            session_type = os.environ.get('XDG_SESSION_TYPE', '').lower()
            self.graphics_engine = session_type if session_type in ('x11', 'wayland') else 'x11'

        self.wmm_id = config.get('wmm_id', '')
        self.app_domain = config.get('app_domain', 'wmm@maki')

        self.data_base = config.get('data_base', '')
        self.config_base = config.get('config_base', '')
        self.cache_base = config.get('cache_base', '')

        self.app_dir = config.get('app_dir', '')
        self.icon_path = os.path.join(self.app_dir, WMM_ICON_FILENAME)
        self.app_config = config.get('app_config', '')
        self.data_dir = config.get('data_dir', '')
        self.frontend_dir = config.get('frontend_dir', '')
        self.cache_dir = config.get('cache_dir', '')
        self.locale_dir = config.get('locale_dir', '')

        platform_name = config['platform']
        desktop = config.get('desktop', '')

        # ----------------------------------------------------------
        # 1. CARGA DEL MÓDULO DEL SISTEMA OPERATIVO
        # ----------------------------------------------------------
        # Importa el módulo correspondiente al SO (linux.py, windows.py, mac.py).
        # Si no existe, usa 'generic' como fallback.
        # Este módulo contiene funciones COMUNES a todos los escritorios de ese SO.
        try:
            so_module = importlib.import_module(f'.{platform_name}', package='wmm_platform')

        except ImportError:
            so_module = importlib.import_module('.generic', package='wmm_platform')
            log_event(f"Módulo SO '{platform_name}' no encontrado, usando 'generic'",
                      origin="CORE", level="WARN", reason="MODULE")

        # ----------------------------------------------------------
        # 2. EXPOSICIÓN DE FUNCIONES COMUNES DEL SO
        # ----------------------------------------------------------
        # Estas funciones están disponibles en TODOS los escritorios
        # que se ejecuten sobre este SO. Se exponen como atributos
        # para que el motor pueda llamarlas sin saber en qué SO está.

        # Abrir archivos/carpetas con la aplicación predeterminada del SO.
        # DATA_DIR pertenece al núcleo; la capa de SO sólo lo consume cuando
        # necesita recursos de datos propios de WMM.
        self.open_file = lambda path, capability=None, **params: so_module.open_file(
            path, capability=capability, data_dir=self.data_dir, **params)

        # Enviar notificaciones de escritorio nativas del SO
        self.send_notification = so_module.send_notification

        # Nombre visible del proceso en el sistema
        if hasattr(so_module, 'set_process_name'):
            self.set_process_name = so_module.set_process_name

        # Terminación forzada de procesos mediante la primitiva nativa del SO.
        # La identidad del PID debe haber sido validada previamente por el consumidor.
        if hasattr(so_module, 'terminate_process'):
            self.terminate_process = so_module.terminate_process

        # Preparar el entorno gettext cuando el SO necesita traducir su
        # configuración nativa de idioma al convenio esperado por GNU gettext.
        if hasattr(so_module, 'prepare_gettext_environment'):
            self.prepare_gettext_environment = so_module.prepare_gettext_environment

        # Resolver herramientas GNU gettext cuando la plataforma necesita una
        # ubicación propia en lugar de depender del PATH global del sistema.
        if hasattr(so_module, 'resolve_gettext_tool'):
            self.resolve_gettext_tool = so_module.resolve_gettext_tool

        # Preferencia visual de las aplicaciones según el sistema operativo.
        # None significa que WMM no debe interferir y deja la decisión al toolkit.
        self.get_system_color_scheme = getattr(
            so_module, 'get_system_color_scheme', lambda: None)

        # Algunas plataformas necesitan completar explícitamente el puente entre
        # la preferencia visual del sistema y GTK.
        if hasattr(so_module, 'prepare_gtk_color_scheme'):
            self.prepare_gtk_color_scheme = so_module.prepare_gtk_color_scheme

        # Presentación de menús contextuales GTK específica del SO.
        # Windows elimina la decoración de Gtk.Menu; los demás sistemas
        # conservan su presentación nativa sin intervención del núcleo.
        if hasattr(so_module, 'prepare_gtk_context_menu'):
            self.prepare_gtk_context_menu = so_module.prepare_gtk_context_menu

        # Presentación nativa opcional: Linux conserva la presentación de GTK.
        if hasattr(so_module, 'present_window'):
            self.present_window = so_module.present_window

        # Recuperación del D&D tras cambios de topología, cuando
        # la plataforma proporciona una implementación específica.
        if hasattr(so_module, 'recover_dnd_after_topology_change'):
            self.recover_dnd_after_topology_change = so_module.recover_dnd_after_topology_change

        # Identidad de formularios autónomos en la barra de tareas Windows.
        # Sólo se expone cuando el sistema operativo proporciona la capacidad.
        if hasattr(so_module, 'prepare_form_taskbar_identity'):
            self.prepare_form_taskbar_identity = so_module.prepare_form_taskbar_identity

        # Compilar archivos .po a .mo (solo si el SO lo soporta)
        # En Linux se usa msgfmt; en otros SO puede no estar disponible
        if hasattr(so_module, 'compile_translations'):
            self.compile_translations = so_module.compile_translations

        # Bloqueo de archivos para escritura atómica (logs, JSONs, etc.)
        # En Linux/macOS se usa fcntl.flock; en Windows, msvcrt.locking
        if hasattr(so_module, 'lock_file'):
            self.lock_file = so_module.lock_file

        # Intento de lock exclusivo sin espera, usado cuando el consumidor
        # necesita distinguir inmediatamente entre "libre" y "ya ocupado".
        if hasattr(so_module, 'try_lock_file'):
            self.try_lock_file = so_module.try_lock_file

        if hasattr(so_module, 'unlock_file'):
            self.unlock_file = so_module.unlock_file

        # El logger se carga durante el bootstrap del propio PlatformManager,
        # por lo que recibe los locks sólo después de resolver la capa de SO.
        if hasattr(self, 'lock_file') and hasattr(self, 'unlock_file'):
            set_file_locking(self.lock_file, self.unlock_file)

        # Instalar acciones de shell (Nemo, Nautilus, Dolphin) a nivel de SO
        if hasattr(so_module, 'ensure_shell_actions'):
            self.ensure_shell_actions = so_module.ensure_shell_actions

        # ----------------------------------------------------------
        # BLOQUE DE COMUNICACIÓN
        # ----------------------------------------------------------
        #
        # Expone la API común de comunicación de WMM.
        #
        # channels.py proporciona una interfaz completamente agnóstica
        # al protocolo de transporte. La responsabilidad del núcleo se
        # limita a enviar y recibir comandos.
        #
        # La disponibilidad y registro de los canales de comunicación
        # corresponde exclusivamente a la capa del sistema operativo
        # (linux.py, windows.py, mac.py...).
        # ----------------------------------------------------------

        from wmm_platform.channels import (
            send_command, start_receiving_commands, emit_busy_changed,)

        # API pública de comunicación del motor.
        self.send_command = send_command
        self.start_receiving_commands = start_receiving_commands
        self.emit_busy_changed = emit_busy_changed

        # Inicialización de los canales de comandos soportados por el SO.
        if hasattr(so_module, "init_channels"):
            self.init_channels = lambda: so_module.init_channels(self.data_dir)

        # Los eventos engine -> panel forman un flujo distinto al de comandos.
        # Las plataformas que dispongan de transporte nativo pueden exponerlo
        # sin incorporar ese endpoint al registro general de channels.py.
        if hasattr(so_module, "send_panel_event"):
            self.send_panel_event = (
                lambda event_dict:
                so_module.send_panel_event(self.data_dir, event_dict))

        if hasattr(so_module, "start_receiving_panel_events"):
            self.start_receiving_panel_events = (
                lambda callback:
                so_module.start_receiving_panel_events(self.data_dir, callback))

        # Monitorización de cambios de hardware mediante el orquestador común.
        from python.monitor_events import init_monitor_events
        self.init_monitor_events = init_monitor_events

        # ----------------------------------------------------------
        # 3. FUNCIONES CON VALOR POR DEFECTO
        # ----------------------------------------------------------
        # Algunas funciones solo tienen sentido en ciertos escritorios/SO.
        # Se define un valor por defecto (normalmente no hacer nada)
        # que será sobrescrito si el SO o el escritorio lo implementan.

        # Instalar acciones de shell (menús contextuales de Nemo, Nautilus, Dolphin, etc.)
        # Por defecto, no hace nada. Solo Linux lo implementa por ahora.
        if not hasattr(so_module, 'ensure_shell_actions'):
            self.ensure_shell_actions = lambda app_root, data_base: None

        # Inicialización de canales de comunicación.
        # Por defecto no hace nada. Cada SO registra únicamente los
        # canales que soporta.
        if not hasattr(so_module, "init_channels"):
            self.init_channels = lambda: None

        # Transporte opcional engine -> panel. Las plataformas que no lo
        # implementan conservan sus mecanismos históricos de notificación.
        if not hasattr(so_module, "send_panel_event"):
            self.send_panel_event = lambda event_dict: False

        if not hasattr(so_module, "start_receiving_panel_events"):
            self.start_receiving_panel_events = lambda callback: False

        # Área útil disponible para una ventana.
        # Cada escritorio puede implementar su cálculo según su compositor.
        self.get_window_available_area = lambda pid: None

        # Área útil correspondiente a un punto global. Permite que el
        # compositor conserve la autoridad sobre geometrías multimonitor.
        self.get_point_available_area = lambda x, y: None

        # Entorno opcional para formularios GTK que necesitan respetar
        # una posición absoluta. Por defecto se hereda el entorno actual.
        self.get_positioned_gtk_child_env = lambda: None

        # Conservación opcional de la posición al expandir secciones del panel.
        # Por defecto no hace nada; solo los escritorios que necesiten corregir
        # el comportamiento de su gestor de ventanas la implementan.
        self.preserve_window_position_on_expand = lambda pid: None
        self.correct_initial_window_position = lambda pid: None

        # ----------------------------------------------------------
        # 4. CARGA DEL MÓDULO DEL ESCRITORIO (si existe)
        # ----------------------------------------------------------
        # Si se detectó un escritorio específico (cinnamon, gnome, kde...),
        # se carga su módulo y se SOBRESCRIBEN las funciones que el
        # escritorio implemente de forma diferente a la del SO base.
        if desktop:
            try:
                desktop_module = importlib.import_module(f'.{desktop}', package='wmm_platform')

                # Obtener la geometría de los monitores (Gdk, D-Bus, Win32...)
                # Si el SO (linux.py) ya proporciona get_monitors, úsalo.
                # Si no, usa el del escritorio.
                if hasattr(so_module, 'get_monitors'):
                    self.get_monitors = so_module.get_monitors
                elif hasattr(desktop_module, 'get_monitors'):
                    self.get_monitors = desktop_module.get_monitors

                # Envio y montaje de imagenes renderizadas
                if hasattr(desktop_module, 'render_master_wallpaper'):
                    self.render_master_wallpaper = types.MethodType(
                        desktop_module.render_master_wallpaper, desktop_module)

                # El escritorio puede definir su propio dominio de traducciones
                # (ej: 'cinnamon' vs 'gnome-shell'). Sobrescribe el del SO.
                if hasattr(desktop_module, 'system_domain'):
                    self.system_domain = desktop_module.system_domain

                # --- CREAR ATAJO EN PRIMERA INSTALACIÓN ---
                if hasattr(desktop_module, 'ensure_keybindings'):
                    self.ensure_keybindings = desktop_module.ensure_keybindings

                # El formulario común delega en el escritorio el formato
                # admitido, la comunicación y la aplicación del atajo.
                for name in ("validate_keybinding", "request_keybindings", "apply_keybinding"):
                    if hasattr(desktop_module, name):
                        setattr(self, name, getattr(desktop_module, name))

                # Área útil de la ventana según el compositor del escritorio
                if hasattr(desktop_module, 'get_window_available_area'):
                    self.get_window_available_area = desktop_module.get_window_available_area

                # Algunos escritorios necesitan preparar específicamente el
                # backend GTK para que un formulario respete un ancla global.
                if hasattr(desktop_module, 'get_positioned_gtk_child_env'):
                    self.get_positioned_gtk_child_env = (desktop_module.get_positioned_gtk_child_env)

                # Área útil correspondiente a un punto global.
                if hasattr(desktop_module, 'get_point_available_area'):
                    self.get_point_available_area = (
                        desktop_module.get_point_available_area)

                # Publica el tamaño máximo permitido para la ventana del panel
                if hasattr(desktop_module, 'set_window_size_limit'):
                    self.set_window_size_limit = desktop_module.set_window_size_limit

                # Correcciones específicas del gestor de ventanas durante
                # expansiones del panel.
                if hasattr(desktop_module, 'preserve_window_position_on_expand'):
                    self.preserve_window_position_on_expand = desktop_module.preserve_window_position_on_expand
                if hasattr(desktop_module, 'correct_initial_window_position'):
                    self.correct_initial_window_position = desktop_module.correct_initial_window_position

                # ----------------------------------------------------------
                # ACTUALIZACIÓN DEL SHELL TRAS CAMBIOS DE TRADUCCIÓN
                # ----------------------------------------------------------
                # Algunos escritorios pueden necesitar recargar su shell para que los
                # componentes ya cargados recojan los nuevos catálogos de traducción.
                if hasattr(desktop_module, 'refresh_shell_after_translation_update'):
                    self.refresh_shell_after_translation_update = desktop_module.refresh_shell_after_translation_update

            except ImportError:
                log_event(f"Módulo escritorio '{desktop}' no encontrado",
                          origin="CORE", level="WARN", reason="MODULE")

        # ----------------------------------------------------------
        # 5. FUNCIONES DE CÁLCULO AGNÓSTICAS
        # ----------------------------------------------------------
        # Estas funciones no dependen del SO ni del escritorio.
        # Son cálculos matemáticos puros (geometría, escalado).
        # ----------------------------------------------------------
        from monitor_manager import scale_monitors_to_area, get_total_canvas_geometry

        self.scale_monitors_to_area = scale_monitors_to_area
        self.get_total_canvas_geometry = get_total_canvas_geometry

    def _resolve_common_paths(self, config):
        """
        Resuelve en memoria las rutas comunes derivables de WMM.

        No persiste settings_core.ini: los entrypoints standalone necesitan
        estas rutas sin apropiarse del lifecycle de finalización del engine.
        """
        resolved = dict(config)

        # El SO puede publicar rutas concretas cuando su topología no coincide
        # con las derivaciones comunes de WMM. Las rutas explícitas tienen
        # prioridad; el núcleo sólo completa aquello que la plataforma omite.
        platform_paths = {}
        platform_name = resolved.get('platform')

        if platform_name:
            try:
                so_module = importlib.import_module(
                    f'.{platform_name}', package='wmm_platform')
            except ImportError:
                pass
            else:
                if hasattr(so_module, 'get_system_paths'):
                    platform_paths = so_module.get_system_paths()

        wmm_id = resolved.get('wmm_id') or WMM_ID
        data_base = resolved.get('data_base') or ''
        config_base = resolved.get('config_base') or ''
        cache_base = resolved.get('cache_base') or ''

        resolved['wmm_id'] = wmm_id

        # APP_DIR representa el árbol real del core instalado. Una plataforma
        # puede publicarlo expresamente; en su ausencia manda el código vivo.
        if not resolved.get('app_dir'):
            resolved['app_dir'] = (
                platform_paths.get('app_dir')
                or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            )

        if not resolved.get('app_config'):
            if platform_paths.get('app_config'):
                resolved['app_config'] = platform_paths['app_config']
            elif config_base:
                resolved['app_config'] = os.path.join(config_base, wmm_id)

        if not resolved.get('data_dir'):
            if platform_paths.get('data_dir'):
                resolved['data_dir'] = platform_paths['data_dir']
            elif resolved.get('app_config'):
                resolved['data_dir'] = os.path.join(
                    resolved['app_config'], 'data')

        if not resolved.get('cache_dir'):
            if platform_paths.get('cache_dir'):
                resolved['cache_dir'] = platform_paths['cache_dir']
            elif cache_base:
                resolved['cache_dir'] = os.path.join(cache_base, 'wmm')

        if not resolved.get('locale_dir'):
            if platform_paths.get('locale_dir'):
                resolved['locale_dir'] = platform_paths['locale_dir']
            elif data_base:
                resolved['locale_dir'] = os.path.join(data_base, 'locale')

        return resolved

    def _ensure_platform_config(self, app_root=None):
        """
        Lee o genera el archivo settings_core.ini y devuelve un
        diccionario con la configuración de plataforma.
        Delega toda la detección del entorno en los módulos de SO y escritorio.
        """
        import sys

        # ----------------------------------------------------------
        # 0. RESOLVER RAÍZ Y ESCRITORIO ACTIVOS
        # ----------------------------------------------------------
        # La ubicación de settings_core.ini pertenece al frontend activo.
        # MATE y XFCE lo alojan dentro del core común; los demás escritorios,
        # en sus respectivos directorios externos de integración.
        if app_root is None:
            app_root = os.path.dirname(os.path.dirname(__file__))

        raw_platform = sys.platform

        try:
            so_module = importlib.import_module(f'.{raw_platform}', package='wmm_platform')
            desktop = so_module.detect_desktop()
            if hasattr(so_module, 'normalize_desktop'):
                desktop = so_module.normalize_desktop(desktop)
        except ImportError:
            so_module = None
            desktop = 'generic'

        if desktop == 'mate':
            config_path = os.path.join(
                app_root, 'frontends', 'mate', 'settings_core.ini')

        elif desktop == 'xfce':
            config_path = os.path.join(
                app_root, 'frontends', 'xfce', 'settings_core.ini')

        elif desktop == 'cinnamon':
            paths = so_module.get_system_paths()
            desktop_module = importlib.import_module('.cinnamon', package='wmm_platform')
            frontend_dir = desktop_module.get_install_path(paths.get('data_base'), WMM_ID)
            config_path = os.path.join(frontend_dir, 'settings_core.ini')

        elif desktop == 'gnome':
            paths = so_module.get_system_paths()
            desktop_module = importlib.import_module('.gnome', package='wmm_platform')
            frontend_dir = desktop_module.get_install_path(paths.get('data_base'), WMM_ID)
            config_path = os.path.join(frontend_dir, 'settings_core.ini')

        elif desktop == 'kde':
            paths = so_module.get_system_paths()
            desktop_module = importlib.import_module('.kde', package='wmm_platform')
            frontend_dir = desktop_module.get_install_path(paths.get('data_base'), WMM_ID)
            config_path = os.path.join(frontend_dir, 'settings_core.ini')

        elif desktop == 'windows':
            paths = so_module.get_system_paths()
            config_path = os.path.join(
                paths['app_config'], 'settings_core.ini')

        else:
            config_path = os.path.join(app_root, 'data', 'settings_core.ini')

        self._config_path = config_path

        # ----------------------------------------------------------
        # 1. Intentar leer el .ini existente
        # ----------------------------------------------------------
        config = _read_ini(config_path)
        if config:
            self._ini_was_generated = False  # El .ini ya existía, no es el primer arranque

            return config

        # ----------------------------------------------------------
        # 2. Si no existe, completar la detección del entorno
        # ----------------------------------------------------------
        log_event("Generando settings_core.ini por primera vez",
                  origin="CORE", level="INFO", reason="SETTINGS")

        if so_module is not None:
            platform = so_module.normalize_platform(raw_platform)
            paths = so_module.get_system_paths()
            data_base = paths.get('data_base')
            config_base = paths.get('config_base')
            cache_base = paths.get('cache_base')

            # Estas rutas derivadas se calcularán posteriormente en
            # _complete_ini_if_needed(), igual que ocurre tras install.sh.
            # locale_dir = paths.get('locale_dir')

        else:
            platform = raw_platform
            log_event(
                f"No se pudo importar módulo para plataforma '{raw_platform}', usando fallback genérico",
                origin="CORE", level="WARN", reason="MODULE"
            )
            data_base = None
            cache_base = None
            config_base = None
            desktop = 'generic'

        # ----------------------------------------------------------
        # 3. Identidad de la aplicación
        # ----------------------------------------------------------
        app_domain = os.path.basename(app_root)

        # ----------------------------------------------------------
        # Las rutas derivadas NO se generan aquí.
        # Se dejan para _complete_ini_if_needed() con el fin de
        # reproducir exactamente el flujo de una instalación normal
        # mediante install.sh.
        # ----------------------------------------------------------

        # try:
        #     desktop_module = importlib.import_module(f'.{desktop}', package='wmm_platform')
        #     app_dir = desktop_module.get_install_path(data_base, app_domain)
        # except ImportError:
        #     app_dir = os.path.join(data_base or '', app_domain)
        #     log_event(
        #         f"No se pudo importar módulo de escritorio '{desktop}' para obtener ruta de instalación, usando fallback",
        #         origin="CORE", level="WARN", reason="MODULE"
        #     )

        # cache_dir = os.path.join(cache_base or '', 'wmm')

        # ----------------------------------------------------------
        # 4. Construir el INI mínimo de bootstrap
        # ----------------------------------------------------------
        config = {
            'platform': platform,
            'desktop': desktop,
            'wmm_id': WMM_ID,
            'app_domain': app_domain,
            'data_base': data_base or '',
            'config_base': config_base or '',
            'cache_base': cache_base or '',

            # Claves derivadas (se completan posteriormente)
            # 'app_dir': app_dir,
            # 'app_config': app_config,
            # 'data_dir': data_dir,
            # 'frontend_dir': frontend_dir,
            # 'locale_dir': locale_dir or '',
            # 'cache_dir': cache_dir,
        }

        os.makedirs(os.path.dirname(config_path), exist_ok=True)

        try:
            _write_ini(config_path, config)
            self._ini_was_generated = True
            log_event("Archivo settings_core.ini generado correctamente",
                      origin="CORE", level="INFO", reason="SETTINGS")
        except Exception as e:
            log_event(f"Error al guardar settings_core.ini: {e}",
                      origin="CORE", level="ERROR", reason="SETTINGS")

        # Verificación de integridad del INI mínimo.
        missing = [k for k in ('platform', 'desktop') if not config.get(k)]
        if missing:
            log_event(f"Configuración incompleta: faltan {', '.join(missing)}",
                      origin="CORE", level="WARN", reason="SETTINGS")

        return config

    def save_ini(self, config):
        """Persiste el diccionario de configuración en el archivo .ini."""
        _write_ini(self._config_path, config)
