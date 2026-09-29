
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

from debug_logger import log_event

# Identidad común del core WMM. No confundir con app_domain,
# que pertenece a la integración/frontend activo.
WMM_ID = 'wmm@maki'

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

class PlatformManager:
    def __init__(self):
        """
        Constructor del núcleo de plataforma.
        Detecta el SO y el escritorio, carga los módulos adecuados y expone
        todas las funciones necesarias para que el motor funcione de forma
        agnóstica al sistema operativo.
        """
        log_event("PlatformManager inicializando",
                  origin="CORE", level="DEBUG", reason="INIT")
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
        session_type = os.environ.get('XDG_SESSION_TYPE', '').lower()
        self.graphics_engine = session_type if session_type in ('x11', 'wayland') else 'x11'

        self.wmm_id = config.get('wmm_id', '')
        self.app_domain = config.get('app_domain', 'wmm@maki')

        self.data_base = config.get('data_base', '')
        self.config_base = config.get('config_base', '')
        self.cache_base = config.get('cache_base', '')

        self.app_dir = config.get('app_dir', '')
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
            log_event(f"Módulo SO '{platform_name}' cargado",
                      origin="CORE", level="DEBUG", reason="MODULE")
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

        # Compilar archivos .po a .mo (solo si el SO lo soporta)
        # En Linux se usa msgfmt; en otros SO puede no estar disponible
        if hasattr(so_module, 'compile_translations'):
            self.compile_translations = so_module.compile_translations

        # Bloqueo de archivos para escritura atómica (logs, JSONs, etc.)
        # En Linux/macOS se usa fcntl.flock; en Windows, msvcrt.locking
        if hasattr(so_module, 'lock_file'):
            self.lock_file = so_module.lock_file
        if hasattr(so_module, 'unlock_file'):
            self.unlock_file = so_module.unlock_file

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

        # Inicialización de los canales soportados por el SO.
        if hasattr(so_module, "init_channels"):
            self.init_channels = lambda: so_module.init_channels(self.data_dir)

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

        # Área útil disponible para una ventana.
        # Cada escritorio puede implementar su cálculo según su compositor.
        self.get_window_available_area = lambda pid: None

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
                log_event(f"Módulo escritorio '{desktop}' cargado",
                          origin="CORE", level="DEBUG", reason="MODULE")

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

                # El escritorio puede instalar sus propias acciones de shell
                # (Cinnamon instala las de Nemo, GNOME las de Nautilus, etc.)
                if hasattr(desktop_module, 'ensure_shell_actions'):
                    self.ensure_shell_actions = desktop_module.ensure_shell_actions

                # --- CREAR ATAJO EN PRIMERA INSTALACIÓN ---
                if hasattr(desktop_module, 'ensure_keybindings'):
                    self.ensure_keybindings = desktop_module.ensure_keybindings

                # Área útil de la ventana según el compositor del escritorio
                if hasattr(desktop_module, 'get_window_available_area'):
                    self.get_window_available_area = desktop_module.get_window_available_area

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

        log_event(f"[DIAG] PlatformManager: _ini_was_generated={getattr(self, '_ini_was_generated', 'NO EXISTE')}",
                  origin="CORE", level="DEBUG", reason="SETTINGS")

    def _resolve_common_paths(self, config):
        """
        Resuelve en memoria las rutas comunes derivables de WMM.

        No persiste settings_core.ini: los entrypoints standalone necesitan
        estas rutas sin apropiarse del lifecycle de finalización del engine.
        """
        resolved = dict(config)

        wmm_id = resolved.get('wmm_id') or WMM_ID
        data_base = resolved.get('data_base') or ''
        config_base = resolved.get('config_base') or ''
        cache_base = resolved.get('cache_base') or ''

        resolved['wmm_id'] = wmm_id

        if not resolved.get('app_dir'):
            resolved['app_dir'] = (os.path.join(data_base, wmm_id) if data_base
                else os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        if not resolved.get('app_config') and config_base:
            resolved['app_config'] = os.path.join(config_base, wmm_id)

        if not resolved.get('data_dir') and resolved.get('app_config'):
            resolved['data_dir'] = os.path.join(resolved['app_config'], 'data')

        if not resolved.get('cache_dir') and cache_base:
            resolved['cache_dir'] = os.path.join(cache_base, 'wmm')

        if not resolved.get('locale_dir') and data_base:
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

        else:
            config_path = os.path.join(app_root, 'data', 'settings_core.ini')

        self._config_path = config_path

        # ----------------------------------------------------------
        # 1. Intentar leer el .ini existente
        # ----------------------------------------------------------
        config = _read_ini(config_path)
        if config:
            self._ini_was_generated = False  # El .ini ya existía, no es el primer arranque
            import inspect

            caller = inspect.stack()[1].function

            log_event(f"[DIAG] _ensure_platform_config llamado desde {caller}",
                      origin="CORE", level="DEBUG", reason="SETTINGS")
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
