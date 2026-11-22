#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later
"""
WMM - Wallpaper Multi-Monitor Manager

config_handler.py – Gestor de configuración y persistencia.
"""
# ==========================================================
# IMPORTS DE LIBRERÍA ESTÁNDAR
# ==========================================================
import os
import stat
import sys
import json
import hashlib
import random
import re
import time
import subprocess
import threading

# ==========================================================
# CONFIGURACIÓN DEL PATH DEL PROYECTO
# ==========================================================
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

# ==========================================================
# IMPORTS DE TERCEROS (GTK)
# ==========================================================
import gi
gi.require_version('GLib', '2.0')
from gi.repository import GLib

# ==========================================================
# IMPORTS DE MÓDULOS DEL PROYECTO
# ==========================================================
from image_engine import ImageEngine
from wmm_platform.core import PlatformManager
from debug_logger import log_event, set_cache_dir
from i18n import _, N_, initialize

class ConfigHandler:
    ...
    """
    Gestor de configuración y persistencia para WMM (Wallpaper Master Manager).
    Maneja la lectura/escritura de JSONs, el escaneo de bibliotecas y la
    normalización de rutas con soporte para caracteres especiales.
    """
    # Dimensiones máximas de las miniaturas de la biblioteca
    thumbnail_max_width = 190
    thumbnail_max_height = 120

    # Modos de ajuste disponibles para la interfaz
    ASPECT_MODES = {
        "fit": N_("Scaled"),
        "zoom": N_("Zoom"),
        "stretched": N_("Stretched")
    }
    COLOR_MODES = {
        "solid_color": N_("Solid color"),
        "gradient_h": N_("Gradient H"),
        "gradient_v": N_("Gradient V")
    }
    IMAGE_EFFECT = {
        "none": N_("None"),
        "sepia": N_("Sepia"),
        "bw": N_("Black and White")
    }
    BACK_EFFECT = {"blur": N_("Blur effect"), "color": N_("Color")}

    # Posiciones disponibles para los metadatos EXIF.
    METADATA_POSITIONS = {
        "top_left": N_("Top-left corner"),
        "bottom_left": N_("Bottom-left corner"),
        "top_right": N_("Top-right corner"),
        "bottom_right": N_("Bottom-right corner")
    }
    # Catálogo común para selección y representación de metadatos EXIF.
    # Las claves son estables y las etiquetas se traducen en el consumidor.
    METADATA_FIELD_GROUPS = (
        (N_("Image"), (
            ("filename", N_("Filename without extension")),
            ("directory", N_("Folder")),
            ("IFD0.XPTitle", N_("Title")),
            ("IFD0.ImageDescription", N_("Description")),
            ("IFD0.XPComment", N_("Comment")),
            ("IFD0.XPSubject", N_("Subject")))),

        (N_("Author"), (
            ("IFD0.XPAuthor", N_("Author")),
            ("IFD0.Copyright", N_("Copyright")),
            ("IFD0.Artist", N_("Artist")))),

        (N_("Source"), (
            ("IFD0.Make", N_("Manufacturer")),
            ("IFD0.Model", N_("Camera")),
            ("Exif.LensModel", N_("Lens")),
            ("IFD0.Software", N_("Software")))),

        (N_("Dates"), (
            ("Exif.DateTimeOriginal", N_("Date taken")),
            ("Exif.DateTimeDigitized", N_("Date digitized")),
            ("IFD0.DateTime", N_("EXIF modification date")),
            ("GPSInfo.GPSDateStamp", N_("GPS date")))),

        (N_("Geolocation"), (
            ("Geolocation.country", N_("Country")),
            ("Geolocation.region", N_("Region")),
            ("Geolocation.city", N_("Locality")),
            ("Geolocation.distance_km", N_("Distance")),
            ("GPSInfo.AltitudeMeters", N_("Altitude"))))
    )
    # ------------------------------------------------------------
    # Claves internas para motivos de ejecución (estables, no traducibles)
    # ------------------------------------------------------------
    REASON_HARDWARE  = "hardware_plug_unplug"
    REASON_SERVICE   = "service_startup"
    REASON_TIMER     = "timer_rotation"
    REASON_MANUAL    = "manual_next"
    REASON_SELECTION = "manual_selection"
    REASON_BOOKMARK  = "bookmark_load"

    EXECUTION_REASONS = {
        REASON_HARDWARE:  "Hardware Plug/Unplug",
        REASON_SERVICE:   "WMM Service",
        REASON_TIMER:     "Timer",
        REASON_MANUAL:    "Manual next Wallapaper",
        REASON_SELECTION: "Manual Selection",
        REASON_BOOKMARK: "Bookmark Load"
    }

    RECONFIGURATION_REASONS = (REASON_HARDWARE)
    ROTATION_REASONS = (REASON_TIMER, REASON_MANUAL, REASON_SELECTION)
    ASYNC_ROTATION_REASONS = (REASON_TIMER, REASON_MANUAL)

    # Órdenes externas (lo que envía el applet/panel en commands.json)
    CMD_UPDATE_TIMER    = "update_timer_settings"
    CMD_SET_SELECTIVE_ROTATION = "set_selective_rotation"
    CMD_LOAD_BOOKMARK   = "load_bookmark"
    CMD_DELETE_BOOKMARK = "delete_bookmark"
    CMD_BOOKMARK_ADDED  = "bookmark_added"
    CMD_SINGLE_FAVORITE_ADDED = "single_favorite_added"
    CMD_FORCE_ROTATION  = "force_rotation"
    CMD_SYNC_LIBRARY    = "sync_library"
    CMD_OPEN_PANEL      = "open_panel"
    CMD_ADD_BOOKMARK    = "add_bookmark"
    CMD_OPEN_HELP       = "open_help"
    CMD_OPEN_KEYBINDING = "open_keybinding"
    CMD_OPEN_ABOUT      = "open_about"
    CMD_SHELL_SEND_TO = "shell_send_to_monitor"
    CMD_SHELL_ADD_FAV = "shell_add_favorite"
    CMD_SHELL_ADD_FAV_CURRENT = "shell_add_favorite_current"
    CMD_SHELL_SPANNED_CURRENT = "shell_spanned_current"
    CMD_SHELL_SPANNED_IMAGE = "shell_spanned_image"
    CMD_APPLY_SELECTION = "apply_manual_selection"
    CMD_APPLY_EDIT_PREVIEW = "apply_edit_preview"
    CMD_SET_METADATA_ENABLED = "set_metadata_enabled"

    def __init__(self, cache_base_dir=None, platform=None):
        """
        Inicializa el gestor de configuración.
        Define todas las rutas del proyecto, la caché y los archivos JSON.

        Args:
            cache_base_dir (str, optional): Ruta base para la caché, proporcionada
                                           por la plataforma (PlatformManager).
                                           Si es None, se usa un fallback local.
        """
        # Configurar la plataforma antes de resolver las rutas.
        # Si se proporciona una instancia de PlatformManager, se reutiliza;
        # si no, se crea una nueva (modo standalone, ej. scripts auxiliares).
        if platform is not None:
            self._platform = platform
        else:
            self._platform = PlatformManager()

        # ==========================================================
        # BLOQUE 1: RUTAS DEL PROYECTO Y DATOS
        # ==========================================================
        # base_dir y app_root describen el árbol del core instalado.
        # data_dir pertenece al espacio común de datos persistentes de WMM.
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.app_root = os.path.dirname(self.base_dir)
        self.data_dir = self._platform.data_dir

        # ==========================================================
        # BLOQUE 2: RUTAS DE CACHÉ (DEPENDIENTES DEL SO)
        # ==========================================================
        # La ruta base de caché la proporciona la plataforma.
        # En Linux: ~/.cache/wmm
        # En Windows: %LOCALAPPDATA%/wmm (cuando se implemente)
        # En macOS: ~/Library/Caches/wmm (cuando se implemente)
        # Si no se proporciona, se usa un fallback local dentro del proyecto.
        if cache_base_dir:
            self.cache_dir = cache_base_dir
        else:
            self.cache_dir = os.path.join(self.app_root, "cache")

        # Rutas derivadas de la caché
        self.master_canvas = os.path.join(self.cache_dir, "wallpaper_master.jpg")
        self.thumbnails_dir = os.path.join(self.cache_dir, "thumbnails")

        # ==========================================================
        # BLOQUE 3: CONFIGURACIÓN DEL LOGGER CENTRALIZADO
        # ==========================================================
        # El debug_logger usa la misma ruta de caché que ConfigHandler.
        # Así, los logs se guardan siempre en el directorio correcto
        # independientemente del SO.
        set_cache_dir(self.cache_dir)

        # ==========================================================
        # BLOQUE 4: CONSTANTES DEL MOTOR
        # ==========================================================
        # Extensiones de imagen soportadas por WMM.
        self.img_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.webp', '.gif')

        # ==========================================================
        # BLOQUE 5: MAPA DE ARCHIVOS JSON
        # ==========================================================
        # Centraliza las rutas de todos los archivos de persistencia.
        # Así, si en el futuro se cambia la ubicación de data/, solo
        # hay que modificar este diccionario.
        self.files = {
            "settings":          os.path.join(self.data_dir, "settings.json"),
            "mfg_codes":         os.path.join(self.data_dir, "monitor_mfg.json"),
            "cache":             os.path.join(self.data_dir, "image_cache.json"),
            "online_origins":    os.path.join(self.data_dir, "image_online.json"),
            "index":             os.path.join(self.data_dir, "scan_index.json"),
            "sources":           os.path.join(self.data_dir, "sources.json"),
            "vault":             os.path.join(self.data_dir, "monitor_vault.json"),
            "geometry":          os.path.join(self.data_dir, "geometry.json"),
            "rotation_h":        os.path.join(self.data_dir, "rotation_h.json"),
            "rotation_v":        os.path.join(self.data_dir, "rotation_v.json"),
            "sel_rotation_h":    os.path.join(self.data_dir, "sel_rotation_h.json"),
            "sel_rotation_v":    os.path.join(self.data_dir, "sel_rotation_v.json"),
            "bm_rotation_h":     os.path.join(self.data_dir, "bookmark_rotation_h.json"),
            "bm_rotation_v":     os.path.join(self.data_dir, "bookmark_rotation_v.json"),
            "history_vault":     os.path.join(self.data_dir, "history_vault.json"),
            "history_presets":   os.path.join(self.data_dir, "history_presets.json"),
            "commands":          os.path.join(self.data_dir, "commands.json"),
            "bookmarks":         os.path.join(self.data_dir, "bookmarks.json"),
            "bookmarks_single":  os.path.join(self.data_dir, "bookmarks_single_list.json")
        }

        # ==========================================================
        # BLOQUE 6: INICIALIZACIÓN DE LA ESTRUCTURA
        # ==========================================================
        # Garantiza que todos los directorios y archivos JSON existan.
        # Si es la primera ejecución, los crea con valores por defecto.
        self.ensure_structure()
        self._retire_legacy_rotation_history()
        self._retire_legacy_bookmark_history()

        # Configurar el sistema de traducciones.
        initialize(self._platform)

    def ensure_structure(self):
        """
        Garantiza la infraestructura de archivos del sistema.
        Migra las fuentes a su propio archivo y asegura el Vault Virtual como raíz.
        """
        os.makedirs(self.thumbnails_dir, exist_ok=True)
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.cache_dir, exist_ok=True)

        # --- MAPA DE INICIALIZACIÓN POR DEFECTO ---
        default_map = {
            "settings": {
                "global": {
                    "slideshow_enabled": True,
                    "slideshow_mode": "sync",
                    "slideshow_bookmark": False,
                    "selective_rotation_enabled": False,
                    "slideshow_interval": 15,
                    "slideshow_max_interval": 60,
                    "wallpaper_mode": "fit",
                    "wallpaper_effect": "none",
                    "wallpaper_effect_scope": "blur",
                    "spanned_enabled": False,
                    "min_area_coverage": 0.60,
                    "transition_effect": "fade",
                    "persist_on_reboot": True,
                    "generate_on_login": True,
                    "color_mode": "solid_color",
                    "solid_color": "#000000",
                    "gradient_h": ["#000000", "#8D9797"],
                    "gradient_v": ["#000000", "#8D9797"],
                    "monitor_group_align": "CENTER",

                    # Aceptación informada del uso de recursos externos.
                    # La omisión del aviso requiere confirmación expresa.
                    "online_responsible_use_accepted": False,
                    "online_responsible_use_dont_show_again": False,

                    # Campos EXIF iniciales para mostrar la funcionalidad.
                    # Solo se aplican al crear settings.json; las selecciones
                    # posteriores del usuario permanecen bajo su control.
                    "exif_metadata_enabled": True,
                    "exif_metadata_position": "bottom_left",
                    "exif_metadata_font": "Sans Oblique 12",
                    "exif_metadata_fields": [
                        # Image
                        "IFD0.XPTitle",
                        "IFD0.ImageDescription",
                        "IFD0.XPComment",
                        "IFD0.XPSubject",

                        # Author
                        "IFD0.Copyright",

                        # Source
                        "IFD0.Make",
                        "IFD0.Model",
                        "Exif.LensModel",
                        "IFD0.Software",

                        # Dates
                        "Exif.DateTimeOriginal",
                        "IFD0.DateTime",

                        # Geolocation
                        "Geolocation.country",
                        "Geolocation.region",
                        "Geolocation.city",
                        "Geolocation.distance_km",
                        "GPSInfo.AltitudeMeters"
                    ],
                }
            },
            "sources": {"sources": []},
            "vault": {
                "active_session": {},
                "active_composition": {},
                "history": {}
            },
            "history_presets": {"last_update": 0, "log": []},
            "cache": {"folders": {}},
            "online_origins": {},
            "index": {},
            "sel_rotation_h": [],
            "sel_rotation_v": [],
            "commands": {},
            "bookmarks": {},
            "bookmarks_single": []
        }

        # --- BUCLE DE INICIALIZACIÓN ÚNICO ---
        for key, default_content in default_map.items():
            if not os.path.exists(self.files[key]):
                self.save_json(key, default_content)

        # --- COMPATIBILIDAD Y MIGRACIÓN DE scan_index ---
        # Se conservan los booleanos actuales y el nuevo par
        # [active, selective]. Sólo se migra el formato histórico
        # [folder_mtime, active], cuya primera posición no es booleana.
        index_data = self.load_json("index")
        index_migrated = False

        for path, entry in index_data.items():
            if isinstance(entry, bool):
                continue

            if (isinstance(entry, list) and len(entry) == 2
                    and isinstance(entry[0], bool)
                    and isinstance(entry[1], bool)):
                continue

            if isinstance(entry, list) and len(entry) > 1:
                # Formato legacy: [folder_mtime, active].
                index_data[path] = bool(entry[1])
            else:
                # Formato legacy sin estado explícito: Active.
                index_data[path] = True

            index_migrated = True

        if index_migrated:
            self.save_json("index", index_data)
            log_event(f"scan_index migrado desde formato legacy: {len(index_data)} entradas",
                origin="CONFIG", level="INFO", reason="LIBRARY")

        # --- BLOQUE DE MIGRACIÓN Y GESTIÓN DE FUENTES ---
        sources_data = self.load_json("sources")
        settings_data = self.load_json("settings")
        global_conf = settings_data.get("global", {})

        # Incorporar las preferencias Online a instalaciones existentes
        # sin sobrescribir decisiones ya guardadas.
        online_defaults = (
            "online_responsible_use_accepted",
            "online_responsible_use_dont_show_again"
        )
        if any(key not in global_conf for key in online_defaults):
            for key in online_defaults:
                global_conf.setdefault(key, False)
            self.save_json("settings", settings_data)

        # 1. Migración: De settings.json -> sources.json
        # Extraemos la lista según tu JSON real
        legacy_sources = global_conf.get("sources", [])

        if legacy_sources and not sources_data.get("sources"):
            log_event("Migrando fuentes a sources.json",
                origin="CONFIG", level="INFO", reason="SETTINGS")
            for item in legacy_sources:

                # Extraemos la ruta: en tu JSON es un dict con clave "path"
                folder_path = item.get("path") if isinstance(item, dict) else item

                # Extraemos la recursividad (si existe en el dict, si no, True por defecto)
                is_recursive = item.get("recursive", True) if isinstance(item, dict) else True

                if not folder_path or not isinstance(folder_path, str):
                    continue

                # Evitar duplicados y añadir
                if not any(s.get("path") == folder_path for s in sources_data["sources"]):
                    sources_data["sources"].append({
                        "id": hashlib.md5(folder_path.encode()).hexdigest()[:8],
                        "name": os.path.basename(folder_path.rstrip(os.sep)) or folder_path,
                        "path": folder_path,
                        "type": "physical",
                        "locked": False,
                        "recursive": is_recursive
                    })

            # Limpieza del settings.json para no volver a migrar
            if "sources" in global_conf:
                del global_conf["sources"]
                self.save_json("settings", settings_data)

        # 2. Garantía del VAULT VIRTUAL (Siempre el primero por defecto)
        # Buscamos si ya existe por ID
        vault_exists = any(s.get("id") == "vault" for s in sources_data["sources"])

        if not vault_exists:
            vault_source = {
                "id": "vault",
                "name": "Favoritos",
                "path": "__vault__",
                "type": "virtual",
                "locked": True,
                "recursive": False
            }
            # Insertar en la posición 0 (Cabecera)
            sources_data["sources"].insert(0, vault_source)
            log_event("Fuente del sistema 'Vault' inicializada",
                origin="CONFIG", level="INFO", reason="VAULT")
        else:
            # Si existe pero no está el primero, podríamos reordenar aquí si fuera crítico
            pass

        # Online es una fuente física del sistema. Su identidad es fija,
        # pero su ubicación la elegirá posteriormente el usuario.
        # Sin path todavía no participa en la sincronización.
        if not any(s.get("id") == "online" for s in sources_data["sources"]):
            online_source = {
                "id": "online",
                "name": "Online",
                "path": "",
                "type": "physical",
                "locked": True,
                "recursive": False
            }

            # Vault no aparece en Sources. Online será la primera fuente visible.
            position = 1 if sources_data["sources"][0].get("id") == "vault" else 0
            sources_data["sources"].insert(position, online_source)

            log_event("Fuente del sistema 'Online' inicializada",
                origin="CONFIG", level="INFO", reason="LIBRARY")

        self.save_json("sources", sources_data)

        # Sincronización final de metadatos al iniciar
        self.refresh_history_metadata()

        # --- VALIDACIÓN DE SINCRONIZACIÓN CRÍTICA ---
        #self.sync_bookmarks_flat_list()  <---- por el momento dejamos que la sincronización de favoritos sea un proceso "bajo demanda

    def get_mfg_map(self):
        """Carga el diccionario de códigos de fabricante."""
        return self.load_json("mfg_codes")

    def sync_vault(self, current_active_hashes):
        """
        Sincroniza el Vault y retorna True si ha habido cambios en la
        composición de monitores (altas o bajas).
        """
        vault = self.load_json("vault")
        active = vault.get("active_session", {})
        history = vault.get("history", {})

        has_changed = False
        new_active = {}

        # 1. Detectar si algún monitor activo ha desaparecido (Mover a History)
        for m_hash, data in active.items():
            # Migrar formato antiguo (string) a nuevo diccionario
            if isinstance(data, str):
                data = {"path": data if data else None, "active": True}
            if m_hash not in current_active_hashes:
                history[m_hash] = data       # guardar siempre, con o sin imagen
                has_changed = True
                log_event(f"Monitor {m_hash} movido a histórico",
                    origin="CONFIG", level="DEBUG", reason="VAULT")

        # 2. Reconstruir la sesión activa con los hashes actuales
        for m_hash in current_active_hashes:
            if m_hash in active:
                entry = active[m_hash]
                # Migrar formato antiguo si es string
                if isinstance(entry, str):
                    entry = {"path": entry if entry else None, "active": True}
                new_active[m_hash] = entry
            elif m_hash in history:
                entry = history.pop(m_hash)
                if isinstance(entry, str):
                    entry = {"path": entry if entry else None, "active": True}
                new_active[m_hash] = entry
                has_changed = True
                log_event(f"Monitor {m_hash} recuperado del histórico",
                    origin="CONFIG", level="DEBUG", reason="VAULT")
            else:
                # Nuevo monitor: sin imagen y activo por defecto
                new_active[m_hash] = {"path": None, "active": True}
                has_changed = True
                log_event(f"Nuevo monitor {m_hash} detectado",
                    origin="CONFIG", level="INFO", reason="VAULT")

        if has_changed:
            vault["active_session"] = new_active
            log_event("Vault sincronizado con cambios",
                origin="CONFIG", level="DEBUG", reason="VAULT")
            vault["history"] = history
            self.save_json("vault", vault)

        return has_changed, vault

    def get_monitors_layout_data(self, area_w, area_h):
        """
        Devuelve una lista de diccionarios con los datos necesarios para pintar
        cada monitor virtual: hash, x, y, w, h, img_path.
        """
        geometry = self.load_json("geometry")
        if not geometry:
            return []

        monitors_map = geometry.get("monitors", {})
        if not monitors_map:
            return []

        vault = self.load_json("vault")
        active_session = vault.get("active_session", {})

        # Obtener coordenadas escaladas desde MonitorManager
        scaled = self._platform.scale_monitors_to_area(monitors_map, area_w, area_h)

        layout_data = []
        for m_hash, coords in scaled.items():
            entry = active_session.get(m_hash, "")
            if isinstance(entry, dict):
                img_path = entry.get("path") or ""
            else:
                img_path = entry if entry else ""
            layout_data.append({
                'hash': m_hash,
                'x': coords['x'],
                'y': coords['y'],
                'w': coords['w'],
                'h': coords['h'],
                'img_path': img_path
            })
        return layout_data

    def get_monitor_info(self, m_hash):
        """Devuelve la info completa de un monitor desde geometry.json."""
        geo = self.load_json("geometry")
        monitors = geo.get("monitors", {})
        return monitors.get(m_hash, {})

    def get_monitor_display_name(self, m_hash):
        """
        Devuelve una etiqueta legible para el monitor con el hash dado.

        Reglas:
        1. Si hay modelo: se usa modelo (y fabricante si no está incluido en el modelo).
           El conector NO se muestra.
        2. Si no hay modelo pero hay fabricante: se muestra fabricante + conector + pulgadas.
        3. Si no hay modelo ni fabricante: se muestra "Generic Monitor" + conector + pulgadas.
        4. Si no hay conector: "Generic Monitor" (sin pulgadas si no hay).
        """
        geo = self.load_json("geometry")
        monitors = geo.get("monitors", {})
        info = monitors.get(m_hash, {})
        if not info:
            return _("Generic Monitor")

        connector = info.get("connector", "")
        mfg_code = info.get("manufacturer", "")
        inches = info.get("inches", 0)
        model = info.get("model", "")

        # Obtener nombre legible del fabricante
        mfg_map = self.get_mfg_map()
        mfg_name = mfg_map.get(mfg_code, mfg_code) if mfg_code else ""

        # --- Construir label según reglas ---
        if model:
            # Caso 1: hay modelo
            if mfg_name and mfg_name.lower() in model.lower():
                label = model
            elif mfg_name:
                label = f"{mfg_name} {model}"
            else:
                label = model
        elif mfg_name:
            # Caso 2: sin modelo, con fabricante
            if connector:
                label = f"{mfg_name} {connector}"
            else:
                label = mfg_name
        elif connector:
            # Caso 3: sin modelo ni fabricante, con conector
            label = _("Generic Monitor") + " " + connector
        else:
            # Caso 4: sin nada
            label = _("Generic Monitor")

        # Añadir pulgadas si están disponibles
        if inches > 0:
            label += f' ({inches}")'

        return label

    def refresh_history_metadata(self):
        """
        Sincroniza los contadores de los padres en los metadatos de los hijos.
        Evita lecturas pesadas durante el ciclo de ejecución principal.
        """
        try:
            # 1. Presets (Sincronía con bookmarks.json)
            hist_p = self.load_json("history_presets")
            hist_p["parent_total"] = len(self.load_json("bookmarks"))
            self.save_json("history_presets", hist_p)

        except Exception as e:
            log_event(f"Error en refresh_metadata: {e}",
                origin="CONFIG", level="ERROR", reason="LIBRARY")

    def remember_absent_preset_images(self, preset_data, current_active_hashes):
        """Conserva en history las imágenes de un preset para monitores ausentes.

        No modifica active_session: sync_vault() recuperará esas asignaciones
        cuando sus monitores reaparezcan.
        """
        vault = self.load_json("vault")
        history = vault.setdefault("history", {})
        present = set(current_active_hashes)
        changed = False

        for m_hash, entry in preset_data.items():
            if m_hash.startswith("__") or m_hash in present:
                continue
            path = entry.get("path") if isinstance(entry, dict) else entry
            if not path:
                continue

            active = entry.get("active", True) if isinstance(entry, dict) else True
            assignment = {"path": path, "active": active}
            if history.get(m_hash) != assignment:
                history[m_hash] = assignment
                changed = True

        if changed:
            self.save_json("vault", vault)

    def update_monitor_image(self, m_hash, image_path):
        """Actualiza la asociación de imagen para un monitor específico en la sesión activa."""
        vault = self.load_json("vault")
        if m_hash in vault["active_session"]:

            # Asegurar el nuevo formato (diccionario con path y active)
            if isinstance(vault["active_session"][m_hash], str):
                vault["active_session"][m_hash] = {"path": vault["active_session"][m_hash], "active": True}
            vault["active_session"][m_hash]["path"] = image_path
            self.save_json("vault", vault)

    def set_active_composition(self, overrides):
        """Guarda los overrides impuestos por la composición actualmente aplicada."""
        vault = self.load_json("vault")
        vault["active_composition"] = overrides if isinstance(overrides, dict) else {}
        self.save_json("vault", vault)

    def load_json(self, key):
        """Lee un JSON con soporte para UTF-8."""
        if not os.path.exists(self.files[key]):
            return {}
        try:
            with open(self.files[key], 'r', encoding='utf-8') as f:
                data = json.load(f)

            if key == "online_origins" and isinstance(data, dict):
                # En disco usamos [provider, id, url]; los consumidores
                # continúan trabajando con campos nombrados.
                fields = ("provider", "id", "url")
                return {path: dict(zip(fields, record))
                    if isinstance(record, list) and len(record) == 3
                    else record
                    for path, record in data.items()}

            return data
        except (json.JSONDecodeError, Exception) as e:
            log_event(f"Error cargando {key}: {e}",
                origin="CONFIG", level="ERROR", reason="SETTINGS")
            return {}

    def save_json(self, key, data):
        """Guarda datos en formato JSON con soporte para múltiples formatos compactos."""
        path = self.files.get(key)
        if not path: return

        try:
            with open(path, 'w', encoding='utf-8') as f:
                # Generamos el JSON estándar con indentación para procesar
                raw_json = json.dumps(data, indent=4, ensure_ascii=False)

                if key in ("cache", "rotation_h", "rotation_v",
                        "sel_rotation_h", "sel_rotation_v",
                        "bm_rotation_h", "bm_rotation_v"):

                    # Formato compacto actual: ["ruta", w, h, mtime_ns]
                    compact_json = re.sub(
                        r'\[\s+"([^"]+)",\s+(\d+),\s+(\d+),\s+(\d+)\s+\]',
                        r'["\1", \2, \3, \4]',
                        raw_json
                    )
                    # Compatibilidad visual durante la migración desde el formato legacy.
                    compact_json = re.sub(
                        r'\[\s+"([^"]+)",\s+(\d+),\s+(\d+)\s+\]',
                        r'["\1", \2, \3]',
                        compact_json
                    )
                    f.write(compact_json)

                elif key == "bookmarks_single":
                    # bookmarks_single mantiene path + metadatos derivados;
                    # mtime_ns pertenece exclusivamente a image_cache.
                    # Formato compacto para 4 elementos: ["ruta", w, h, "orient"]
                    # Sherlock: Cazamos el trío V5 + el string de orientación
                    compact_json = re.sub(
                        r'\[\s+"([^"]+)",\s+(\d+),\s+(\d+),\s+"([^"]+)"\s+\]',
                        r'["\1", \2, \3, "\4"]',
                        raw_json
                    )
                    f.write(compact_json)

                elif key == "settings":
                    # Compactar los arrays de degradados para que ocupen una sola línea
                    compact_json = re.sub(
                        r'"gradient_h": \[\s+("[^"]*"),\s+("[^"]*")\s+\]',
                        r'"gradient_h": [\1, \2]',
                        raw_json
                    )
                    compact_json = re.sub(
                        r'"gradient_v": \[\s+("[^"]*"),\s+("[^"]*")\s+\]',
                        r'"gradient_v": [\1, \2]',
                        compact_json
                    )
                    # Mantener compactas las estructuras breves de atajos y ventanas.
                    # Las selecciones EXIF y los demás bloques siguen verticales.
                    compact_json = re.sub(
                        r'("modifiers": )(\[\s*(?:"(?:\\.|[^"\\])*"\s*,?\s*)*\])',
                        lambda match: match.group(1) + json.dumps(
                            json.loads(match.group(2)), ensure_ascii=False),
                        compact_json
                    )
                    compact_json = re.sub(
                        r'("window_size": )\{\s*("width": \d+),\s*("height": \d+)\s*\}',
                        r'\1{\2, \3}',
                        compact_json
                    )
                    compact_json = re.sub(
                        r'("window_size": )\[\s*(\d+),\s*(\d+)\s*\]',
                        r'\1[\2, \3]',
                        compact_json
                    )
                    f.write(compact_json)

                elif key == "index":
                    # Compactar los dos estados de cada carpeta en una línea.
                    compact_json = re.sub(
                        r'\[\s*(true|false),\s*(true|false)\s*\]',
                        r'[\1, \2]',
                        raw_json
                    )
                    f.write(compact_json)

                elif key == "online_origins":
                    # Contrato persistente: [provider, id, url].
                    # Los consumidores conservan los campos nombrados.
                    entries = []

                    for path, origin in data.items():
                        if (isinstance(origin, dict)
                                and set(origin) == {"provider", "id", "url"}):
                            origin = [
                                origin["provider"], origin["id"], origin["url"]
                            ]

                        # Conservar registros desconocidos sin descartarlos
                        # durante una escritura posterior.
                        entries.append(
                            f'    {json.dumps(path, ensure_ascii=False)}: '
                            f'{json.dumps(origin, ensure_ascii=False)}'
                        )

                    f.write("{\n" + ",\n".join(entries) + "\n}" if entries else "{}")

                else:
                    # Index, vault, geometry, etc. (Formato expandido estándar)
                    f.write(raw_json)

            # EXIF es un derivado de image_cache, nunca su autoridad.
            # Lanzar sólo después de cerrar el archivo y sin bloquear
            # al llamante (Panel, Sync o motor).
            if key == "cache":
                exif_script = os.path.join(self.base_dir, "exif_cache.py")
                if os.path.isfile(exif_script):
                    try:
                        # El dispatcher compilado espera el script como primer
                        # argumento; -B sólo corresponde al intérprete Python.
                        command = [sys.executable, exif_script, self.data_dir]
                        if not getattr(sys, "frozen", False):
                            command.insert(1, "-B")

                        subprocess.Popen(command,
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

                    except OSError as error:
                        log_event(f"No se pudo iniciar EXIF: {error}",
                            origin="CONFIG", level="WARN", reason="LIBRARY")

        except Exception as e:
            log_event(f"Error al guardar {key}: {e}",
                origin="CONFIG", level="ERROR", reason="SETTINGS")

        # --- PERSISTENCIA DE ESTADOS ---

    def get_index_active(self, path, index=None, default=True):
        """Retorna Active desde el índice booleano o de dos estados."""
        if index is None:
            index = self.load_json("index")

        state = index.get(path, default)

        # El primer valor conserva la autoridad Active/Inactive.
        # El segundo pertenece exclusivamente a rotación selectiva.
        return state[0] if isinstance(state, list) else state

    def update_source_recursive(self, path, state):
        """Actualiza el modo recursivo de una raíz en sources.json."""
        data = self.load_json("sources")
        for s in data.get("sources", []):
            if s.get("path") == path:
                s["recursive"] = state
                self.save_json("sources", data)
                return True
        return False

    def discover_recursive_folders(self, root_path):
        """Añade al scan_index las subcarpetas aún no conocidas, sin materializar imágenes."""
        if not os.path.isdir(root_path):
            return 0

        index = self.load_json("index")
        root = os.path.abspath(root_path)
        added = 0

        for folder, _, _ in os.walk(root):
            folder = os.path.abspath(folder)
            if folder == root or folder in index:
                continue
            index[folder] = True

            # Descubrir estructura no materializa imágenes:
            # la carpeta nace conocida y activa; Sync resolverá su cache.
            added += 1

        if added:
            self.save_json("index", index)
            log_event(f"Subcarpetas descubiertas: {root_path} ({added})",
                origin="CONFIG", level="INFO", reason="LIBRARY")

        return added

    def update_index_active_state(self, path, state):
        """Cambia Active sin alterar la selección de rotación."""
        index = self.load_json("index")
        if path not in index:
            return False

        # Capturar la elegibilidad anterior antes de modificar Active.
        # La marca Selective permanece independiente de este cambio.
        cache = self.load_json("cache")
        previous_selective = self._filter_selective_cache(cache, index)

        entry = index[path]

        if isinstance(entry, list):
            entry[0] = bool(state)
        else:
            index[path] = bool(state)

        self.save_json("index", index)

        # Active cambia la elegibilidad, no la marca Selective.
        # La reconciliación mantiene los historiales aunque el switch esté OFF.
        current_selective = self._filter_selective_cache(cache, index)

        if not self._reconcile_rotation_pools(
                previous_selective, current_selective,
                pool_keys=("sel_rotation_h", "sel_rotation_v")):
            log_event("No se pudieron reconciliar los pools selectivos",
                origin="CONFIG", level="ERROR", reason="LIBRARY")

        return True

    def set_index_selective_state(self, folder_path, state):
        """Marca o desmarca una carpeta y toda su rama para rotación selectiva."""
        index = self.load_json("index")
        previous_index = index.copy()
        root = os.path.normcase(os.path.normpath(folder_path))
        prefix = root + os.sep
        changed = False

        for path, entry in index.items():
            current = os.path.normcase(os.path.normpath(path))

            if current != root and not current.startswith(prefix):
                continue

            active = entry[0] if isinstance(entry, list) else entry
            selective = entry[1] if isinstance(entry, list) else False

            if selective != state:
                index[path] = [active, bool(state)]
                changed = True

        if changed:
            cache = self.load_json("cache")

            # La biblioteca no cambia al marcar carpetas.
            # Cambia únicamente el conjunto elegible para rotación selectiva.
            previous_selective = self._filter_selective_cache(cache, previous_index)
            current_selective = self._filter_selective_cache(cache, index)

            self.save_json("index", index)

            # Reutilizar la reconciliación H/V con autoridad independiente.
            if not self._reconcile_rotation_pools(
                    previous_selective, current_selective,
                    pool_keys=("sel_rotation_h", "sel_rotation_v")):
                log_event("No se pudieron reconciliar los pools selectivos",
                    origin="CONFIG", level="ERROR", reason="LIBRARY")

        return changed

    def toggle_all_children(self, parent_path, new_state):
        """Actualiza todos los hijos de una raíz en el scan_index."""
        index = self.load_json("index")

        # La operación modifica varias entradas del índice en memoria.
        # Capturar primero la elegibilidad selectiva de toda la rama.
        cache = self.load_json("cache")
        previous_selective = self._filter_selective_cache(cache, index)
        changed = False

        # El separador delimita la rama y evita incluir carpetas hermanas.
        root = os.path.normcase(os.path.abspath(parent_path))
        prefix = root if root.endswith(os.sep) else root + os.sep

        for path in index.keys():
            current_path = os.path.normcase(os.path.abspath(path))

            # Sólo descendientes reales; excluye la raíz y carpetas hermanas.
            if current_path.startswith(prefix):

                # Solo marcamos como cambiado si el estado es realmente distinto
                if self.get_index_active(path, index) != new_state:

                # El cambio masivo afecta sólo a Active/Inactive;
                # conserva la selección de rotación y no fuerza materialización.
                    entry = index[path]
                    if isinstance(entry, list):
                        entry[0] = bool(new_state)
                    else:
                        index[path] = bool(new_state)
                    changed = True

        if changed:
            self.save_json("index", index)

            # Una única reconciliación después de modificar toda la rama.
            # Las marcas Selective permanecen intactas.
            current_selective = self._filter_selective_cache(cache, index)

            if not self._reconcile_rotation_pools(
                    previous_selective, current_selective,
                    pool_keys=("sel_rotation_h", "sel_rotation_v")):
                log_event("No se pudieron reconciliar los pools selectivos",
                    origin="CONFIG", level="ERROR", reason="LIBRARY")

            log_event(f"Cambio masivo completado: {len(index)} entradas procesadas",
                origin="CONFIG", level="INFO", reason="SETTINGS")
            return True

        # Si llegamos aquí sin cambios, es que no había hijos o ya estaban en ese estado
        return False

    def _refresh_bookmarks_single_metadata(self, cache):
        """
        Actualiza width, height y orientación de favoritos individuales
        utilizando image_cache como autoridad de metadatos derivados.

        Las rutas fuera de la biblioteca materializada se conservan intactas.
        Retorna el número de favoritos actualizados.
        """
        current_list = self.load_json("bookmarks_single")
        if not current_list:
            return 0

        lookup = {}

        # La ruta sigue siendo la identidad del favorito.
        # width / height / orientación son derivados del image_cache final.
        for folder_data in cache.get("folders", {}).values():
            for img in folder_data.get("h", []): lookup[img[0]] = [img[1], img[2], "h"]
            for img in folder_data.get("v", []): lookup[img[0]] = [img[1], img[2], "v"]

        updated = 0
        for entry in current_list:
            if not isinstance(entry, list) or len(entry) < 4:
                continue

            info = lookup.get(entry[0])

            # Si la ruta no pertenece a la biblioteca materializada,
            # no tenemos autoridad para modificar sus metadatos.
            if info and entry[1:4] != info:
                entry[1:4] = info
                updated += 1

        if updated:
            # La ruta conserva la identidad: cambiar dimensiones u
            # orientación no debe reintroducir favoritos ya consumidos.
            if not self.save_bookmarks_single(current_list):
                log_event("No se pudo reconciliar la actualización de metadatos",
                    origin="CONFIG", level="ERROR", reason="BOOKMARK")
                return 0

            log_event(f"Metadatos de favoritos actualizados: {updated}",
                origin="CONFIG", level="DEBUG", reason="BOOKMARK")

        return updated

    def sync_bookmarks_flat_list(self):
        """
        Actualiza la lista plana con las imágenes de los presets.
        No elimina las entradas existentes; solo añade las nuevas.
        """
        from PIL import Image

        bookmarks = self.load_json("bookmarks")
        cache = self.load_json("cache")

        # 1. Mapa de linaje (rápido)
        lookup = {}
        for folder_data in cache.get("folders", {}).values():
            for img in folder_data.get("h", []): lookup[img[0]] = [img[1], img[2], "h"]
            for img in folder_data.get("v", []): lookup[img[0]] = [img[1], img[2], "v"]

        # 2. Cargar la lista actual para preservar entradas manuales
        current_list = self.load_json("bookmarks_single")
        existing_paths = {item[0] for item in current_list if item}

        # 3. Recorrer presets y añadir nuevas imágenes
        for bookmark_name, monitor_data in bookmarks.items():
            for monitor_id, path_entry in monitor_data.items():
                # Los metadatos del preset no representan imágenes de monitor.
                if monitor_id.startswith("__"):
                    continue

                # Extraer el path real si es un diccionario (nuevo formato)
                if isinstance(path_entry, dict):
                    actual_path = path_entry.get("path", "") or ""
                else:
                    actual_path = path_entry if path_entry else ""

                if not actual_path or not os.path.exists(actual_path):
                    continue
                if actual_path in existing_paths:
                    continue

                info = lookup.get(actual_path)
                if info:
                    entry = [actual_path, info[0], info[1], info[2]]
                else:
                    try:
                        with Image.open(actual_path) as img:
                            w, h = img.size
                            orient = "h" if w >= h else "v"
                        entry = [actual_path, w, h, orient]
                    except Exception as error:
                        log_event(f"No se pudo incorporar a favoritos '{actual_path}' "
                            f"desde el preset '{bookmark_name}': "
                            f"{type(error).__name__}: {error}",
                            origin="CONFIG", level="ERROR", reason="BOOKMARK")
                        continue

                current_list.append(entry)
                existing_paths.add(actual_path)

        if not self.save_bookmarks_single(current_list):
            log_event("No se pudo sincronizar la lista plana de favoritos",
                origin="CONFIG", level="ERROR", reason="BOOKMARK")
            return

        # Este método sólo incorpora rutas nuevas.
        # Los metadatos de favoritos existentes se refrescan desde image_cache
        # mediante _refresh_bookmarks_single_metadata() durante Sync.

    def maintenance_flat_list(self):
        """
        Inspecciona 'bookmarks_single_list.json' y elimina entradas inexistentes.
        No depende de los presets, solo de la realidad del disco duro.
        """
        # Cargamos la lista plana usando su clave oficial
        flat_list = self.load_json("bookmarks_single")

        if not flat_list:
            return

        # Filtramos: Solo mantenemos lo que os.path.exists confirme
        new_list = [item for item in flat_list if item[0] and os.path.exists(item[0])]

        # La limpieza también debe retirar las imágenes de los
        # pendientes H/V, sin reiniciar las rondas existentes.
        if len(new_list) != len(flat_list):
            num_removed = len(flat_list) - len(new_list)

            if not self.save_bookmarks_single(new_list):
                log_event("No se pudo completar el mantenimiento de favoritos",
                    origin="CONFIG", level="ERROR", reason="BOOKMARK")
                return

            log_event(f"Limpieza: {num_removed} favoritos eliminados (no existen en disco)",
                origin="CONFIG", level="INFO", reason="BOOKMARK")

    def save_current_state_as_bookmark(self, bookmark_name, current_state):
        """
        Guarda la sesión actual y dispara automáticamente la sincronización plana.
        current_state: dict {m_hash: {"path": str, "active": bool}}.
        """
        try:
            bookmarks = self.load_json("bookmarks")
            bookmarks[bookmark_name] = current_state

            # Asegurar orden canónico: preferencias primero, luego monitores
            ordered = {}
            for pref in ("__mode__", "__spanned__", "__effect__", "__effect_scope__"):
                if pref in bookmarks[bookmark_name]:
                    ordered[pref] = bookmarks[bookmark_name][pref]
            for key in bookmarks[bookmark_name]:
                if not key.startswith("__"):
                    ordered[key] = bookmarks[bookmark_name][key]
            bookmarks[bookmark_name] = ordered

            self._cleanup_preset_data(bookmarks[bookmark_name])
            self.save_json("bookmarks", bookmarks)

            self.sync_bookmarks_flat_list()
            self.refresh_history_metadata()
            return True
        except Exception as e:
            log_event(f"Error al guardar favorito '{bookmark_name}': {e}",
                origin="CONFIG", level="ERROR", reason="BOOKMARK")
            return False

    def get_next_bookmark_id(self):
        """
        Busca el primer hueco disponible siguiendo el patrón 'Bookmark XX'.
        """
        try:
            data = self.load_json("bookmarks")
            if not data: return 1

            next_id = 1
            while True:
                candidate = f"Bookmark {next_id:02d}"
                if candidate not in data:
                    return next_id
                next_id += 1
        except:
            return 1

    def save_new_bookmark(self, name, session_data):
        """
        Validates the bookmark name and saves the current monitor session.
        session_data: dict {m_hash: {"path": str, "active": bool}}.
        Returns: (success: bool, error_code: str)
        """
        bookmarks = self.load_json("bookmarks")
        clean_name = name.strip()
        if not clean_name:
            return False, "EMPTY_NAME"
        if clean_name in bookmarks:
            return False, "DUPLICATE_NAME"
        try:
            bookmarks[clean_name] = session_data
            # Asegurar orden canónico: preferencias primero, luego monitores
            ordered = {}
            for pref in ("__mode__", "__spanned__", "__effect__", "__effect_scope__"):
                if pref in bookmarks[clean_name]:
                    ordered[pref] = bookmarks[clean_name][pref]
            for key in bookmarks[clean_name]:
                if not key.startswith("__"):
                    ordered[key] = bookmarks[clean_name][key]
            bookmarks[clean_name] = ordered

            self._cleanup_preset_data(bookmarks[clean_name])
            self.save_json("bookmarks", bookmarks)

            self.sync_bookmarks_flat_list()
            self.refresh_history_metadata()
            return True, "SUCCESS"
        except Exception as e:
            return False, f"ERROR: {str(e)}"
            log_event(f"Error al guardar bookmark: {e}",
                origin="CONFIG", level="ERROR", reason="BOOKMARK")

    def _cleanup_preset_data(self, preset_data):
        """
        Si el preset tiene __spanned__ = True, elimina todos los monitores
        excepto el principal (o el que tenga imagen) para no guardar duplicados.
        """
        if preset_data.get("__spanned__", False):
            # Buscar el monitor principal desde geometry.json
            geo = self.load_json("geometry")
            monitors = geo.get("monitors", {})
            primary_hash = None
            for h, info in monitors.items():
                if info.get("primary", False):
                    entry = preset_data.get(h)
                    path = entry.get("path", "") if isinstance(entry, dict) else entry
                    if path:
                        primary_hash = h
                    break

            # Sin imagen en el principal, preservar el origen existente,
            # aunque pertenezca a un monitor temporalmente desconectado.
            if primary_hash is None:
                for h, entry in preset_data.items():
                    if h.startswith("__"):
                        continue
                    if isinstance(entry, dict) and entry.get("path", ""):
                        primary_hash = h
                        break
            # Si aun así no hay, dejar el primer monitor como principal
            if primary_hash is None:
                for h in preset_data:
                    if not h.startswith("__"):
                        primary_hash = h
                        break

            # Eliminar todos los monitores excepto el principal
            keys_to_remove = [h for h in preset_data if not h.startswith("__") and h != primary_hash]
            for h in keys_to_remove:
                del preset_data[h]

    def delete_bookmark(self, name):
        """
        Elimina un preset de bookmarks.json y actualiza la lista plana y metadatos.

        Args:
            name (str): Nombre del favorito a eliminar.

        Returns:
            bool: True si se eliminó correctamente, False si no existía.
        """
        bookmarks = self.load_json("bookmarks")
        if name in bookmarks:
            del bookmarks[name]
            self.save_json("bookmarks", bookmarks)
            # Sincronizar lista plana y metadatos
            self.sync_bookmarks_flat_list()
            self.refresh_history_metadata()
            return True
        return False

    def save_bookmarks_single(self, bookmarks):
        """Guarda favoritos y reconcilia sus pendientes H/V."""
        previous = self.load_json("bookmarks_single")

        if previous == bookmarks:
            return True

        # Migrar primero desde el estado anterior, si procede.
        if not self._initialize_bookmark_rotation_pools():
            return False

        self.save_json("bookmarks_single", bookmarks)

        if self.load_json("bookmarks_single") != bookmarks:
            log_event("No se pudo verificar la escritura de bookmarks",
                origin="CONFIG", level="ERROR", reason="BOOKMARK")
            return False

        if not self._reconcile_bookmark_rotation_pools(previous, bookmarks):
            log_event("No se pudieron reconciliar los pools de bookmarks",
                origin="CONFIG", level="ERROR", reason="BOOKMARK")
            return False

        return True

    def add_to_favorites(self, img_path):
        """Añade una imagen a la lista plana de favoritos (bookmarks_single_list.json)."""
        flat_list = self.load_json("bookmarks_single")
        if any(entry[0] == img_path for entry in flat_list):
            return False  # ya existe

        orient, w, h = ImageEngine.process_image(img_path)
        if orient is None:
            return False  # no se pudo procesar la imagen

        flat_list.append([img_path, w, h, orient])

        if not self.save_bookmarks_single(flat_list):
            return False

        self.refresh_history_metadata()
        return True

    def remove_from_favorites(self, img_path):
        """Elimina una imagen de la lista plana de favoritos (bookmarks_single_list.json)."""
        flat_list = self.load_json("bookmarks_single")
        new_list = [entry for entry in flat_list if entry[0] != img_path]

        if len(new_list) != len(flat_list):
            if not self.save_bookmarks_single(new_list):
                return False
            self.refresh_history_metadata()
            return True

        return False

        # --- ENTRADA DE MOTOR ---

    def _is_covered_by_any_recursive_source(self, path, sources_data):
        """
        Retorna True si el path está dentro de al menos una fuente
        física, recursiva y que no esté desactivada.
        """
        for source in sources_data:
            if source.get("type") != "physical":
                continue
            if not source.get("recursive", False):
                continue
            root = source.get("path", "")
            if not root:
                continue
            # Verificar si el path cuelga de esta raíz
            if path == root or path.startswith(root.rstrip(os.sep) + os.sep):
                return True
        return False

    def _is_covered_by_any_source(self, path, sources_data):
        """Retorna True si path pertenece al ámbito actual de alguna fuente física."""
        current = os.path.abspath(path)

        for source in sources_data:
            if source.get("type") != "physical":
                continue
            root = source.get("path", "")
            if not root:
                continue
            root = os.path.abspath(root)
            if current == root:
                return True
            if source.get("recursive", False) and current.startswith(root + os.sep):
                return True

        return False

    def _is_path_active(self, img_path, sources_data=None, index=None):
        """
        Retorna True si la imagen pertenece al ámbito actual de una fuente
        y su carpeta está activa.

        sources_data e index pueden proporcionarse ya cargados para evitar
        releer los JSON durante recorridos masivos.
        """
        if sources_data is None:
            sources_data = self.load_json("sources").get("sources", [])
        if index is None:
            index = self.load_json("index")
        container = os.path.dirname(img_path)

        if not self._is_covered_by_any_source(container, sources_data):
            return False
        check_path = container

        while check_path:
            if check_path in index:
                return self.get_index_active(check_path, index)
            parent = os.path.dirname(check_path)
            if parent == check_path:
                break
            check_path = parent

        return True

    def sync_library(self, on_progress=None, on_folder=None, on_complete=None, on_error=None):
        """
        Sincroniza la biblioteca física basándose en sources.json.
        Implementa discriminación por carpeta y poda de árbol recursiva.
        """
        # --- 1. CARGA DE INFRAESTRUCTURA ---
        sources_data = self.load_json("sources").get("sources", [])
        scan_index = self.load_json("index")
        extensions = self.img_extensions

        # Conjunto ordenado de carpetas físicamente activas.
        # La frescura ya no se decide mediante mtime de directorio.
        active_folders = {}

        # --- 2. MAPEO DE REALIDAD FÍSICA Y PODA LÓGICA ---
        for source in sources_data:
            if source.get("type") != "physical" or not os.path.exists(source.get("path", "")):
                continue

            root_path = source.get("path")
            if not root_path or not os.path.exists(root_path):
                continue

            is_recursive = source.get("recursive", False)

            if is_recursive:
                for root, dirs, _ in os.walk(root_path):
                    # Si es totalmente nueva, nace activa en el índice.
                    if root not in scan_index:
                        scan_index[root] = True

                    folder_active = self.get_index_active(root, scan_index)

                    if not folder_active:
                        # Si ninguna fuente recursiva activa cubre esta carpeta,
                        # podar también su descendencia.
                        if not self._is_covered_by_any_recursive_source(root, sources_data):
                            dirs[:] = []
                        continue

                    active_folders[root] = True
            else:
                # Una fuente no recursiva también pertenece al índice lógico.
                # Sin esta entrada, su caché no coincide con el ámbito de Sources.
                scan_index.setdefault(root_path, True)

                if self.get_index_active(root_path, scan_index):
                    active_folders[root_path] = True

        # --- 3. PREPARACIÓN DE RECONCILIACIÓN FÍSICA ---
        full_cache = self.load_json("cache")
        if "folders" not in full_cache:
            full_cache["folders"] = {}

        # Toda carpeta activa se inspecciona.
        # _reconcile_folder_cache() determina qué imágenes están
        # intactas, nuevas, modificadas, eliminadas o son legacy.
        folders_to_reconcile = list(active_folders)

        # No existe ya un gate de frescura por directorio:
        # todas las activas se inspeccionan y mtime_ns decide por imagen.

        # --- Carpetas a eliminar de la caché ---
        # Separamos las que han sido eliminadas (fuente ya no existe) de las
        # que simplemente están desactivadas (hijos inactivos).
        deleted_folders = []
        inactive_folders = []

        # Inactive conserva identidad en scan_index y sólo pierde materialización.
        # Deleted pierde además su entrada lógica porque ya no pertenece al ámbito.
        for f in scan_index:

        # Una carpeta fuera del conjunto activo no significa necesariamente Deleted:
        # si sigue cubierta y está Inactive, conserva su identidad lógica.
            if f not in active_folders:
                is_inactive = not self.get_index_active(f, scan_index)
                if is_inactive:
                    # Inactive conserva identidad mientras exista una Source
                    # que cubra la ruta, también si no es recursiva.
                    if not self._is_covered_by_any_source(f, sources_data):
                        deleted_folders.append(f)
                    else:
                        inactive_folders.append(f)
                else:
                    deleted_folders.append(f)
            elif not self.get_index_active(f, scan_index):
                inactive_folders.append(f)

        # Una Source no recursiva antigua podía materializar caché sin
        # registrarse en scan_index. Limpiar esas entradas cuando ya no
        # pertenecen al ámbito físico activo.
        for f in full_cache["folders"]:
            if f not in active_folders and f not in scan_index:
                deleted_folders.append(f)

        # Mantenimiento de Favoritos y Metadatos
        self.maintenance_flat_list()
        self.refresh_history_metadata()

        # Resumen de carpetas activas, desactivadas y eliminadas
        active_count = len(active_folders)
        inactive_count = len(inactive_folders)
        deleted_count = len(deleted_folders)
        if inactive_count or deleted_count:
            log_event(f"Carpetas: {active_count} activas, {inactive_count} desactivadas, {deleted_count} eliminadas",
                      origin="CONFIG", level="DEBUG", reason="LIBRARY")

        # SALIDA RÁPIDA: Si no hay ninguna carpeta que reconciliar ni limpiar.
        # El modo UI conserva el lifecycle completo: Sync termina y entrega
        # el control a Thumbnails; progress ya no gobierna la operación.
        if not folders_to_reconcile and not deleted_folders and not inactive_folders:
            log_event("Biblioteca sincronizada. Sin cambios", origin="CONFIG", level="INFO", reason="LIBRARY")
            if on_complete:
                on_complete()
            h, v = self._get_cache_totals(full_cache)
            return h, v, False, None

        # --- MODO ASÍNCRONO (si se solicita desde la UI) ---
        if on_progress and on_folder:
            self._async_state = {
                'on_complete': on_complete,
                'on_error': on_error,
                'folders_to_reconcile': folders_to_reconcile,
                'deleted_folders': deleted_folders,
                'inactive_folders': inactive_folders,
                'full_cache': full_cache,
                'previous_cache': {"folders": full_cache["folders"].copy()},
                'extensions': extensions,
                'scan_index': scan_index,
                'stats': {"added_h": 0, "added_v": 0, "removed_h": 0, "removed_v": 0, "modified": 0},
                'on_progress': on_progress,
                'on_folder': on_folder
            }
            # RUNTIME-04: la reconciliación pesada abandona el main thread.
            # Un único worker secuencial conserva el orden sin paralelizar carpetas.
            threading.Thread(
                target=self._process_sync_worker,
                name="WMM-SyncLibrary",
                daemon=True
            ).start()
            return None  # Salida temporal, el resultado se comunicará por callback
        # --- FIN MODO ASÍNCRONO ---

        # --- 4. PROCESAMIENTO QUIRÚRGICO DE CAMBIOS ---
        full_cache = self.load_json("cache")
        if "folders" not in full_cache: full_cache = {"folders": {}}

        # Preservar las carpetas anteriores antes de migrar o reconciliar.
        # Sus rutas permiten distinguir altas de imágenes ya consumidas.
        previous_cache = {"folders": full_cache["folders"].copy()}

        stats = {"added_h": 0, "added_v": 0, "removed_h": 0, "removed_v": 0, "modified": 0}

        # Migrar sobre la caché definitiva, antes de reconciliar por mtime_ns.
        migrated, invalidated, migration_ok = self._migrate_exif_orientation_cache(full_cache)

        # A. Limpieza de carpetas eliminadas o desactivadas
        for f in deleted_folders:

        # Deleted elimina materialización y estado lógico:
        # la carpeta ya no pertenece al ámbito actual de Sources.
            # 1. Poda del Caché: Se elimina siempre para no mostrar fotos "apagadas"
            if f in full_cache["folders"]:
                stats["removed_h"] += len(full_cache["folders"][f]['h'])
                stats["removed_v"] += len(full_cache["folders"][f]['v'])

                # Limpiar miniaturas asociadas antes de eliminar la carpeta de la caché
                log_event(f"Eliminando caché de carpeta inactiva: {f}",
                    origin="CONFIG", level="DEBUG", reason="LIBRARY")
                self._delete_thumbnails_for_folder(full_cache["folders"][f])
                del full_cache["folders"][f]

            # 2. BISTURÍ EN EL ÍNDICE: Eliminar la entrada siempre que la carpeta
            #    no esté activa, independientemente de si existe en disco.
            # Una caché huérfana puede carecer de entrada en el índice.
            if f in scan_index:
                del scan_index[f]
                log_event(f"Entrada de índice eliminada: {f}",
                    origin="CONFIG", level="DEBUG", reason="LIBRARY")

        # A.2 Limpieza diferida de carpetas hijas desactivadas.
        # Se eliminan su caché de imágenes y sus thumbnails, pero se conserva
        # scan_index con active=False para mantener la carpeta visible y permitir
        # que una futura reactivación fuerce su reconstrucción.
        for f in inactive_folders:

        # Inactive elimina sólo cache y thumbnails:
        # scan_index conserva la ruta y su estado False para una futura reactivación.
            if f in full_cache["folders"]:
                stats["removed_h"] += len(full_cache["folders"][f]['h'])
                stats["removed_v"] += len(full_cache["folders"][f]['v'])
                log_event(f"Eliminando caché de carpeta desactivada: {f}",
                          origin="CONFIG", level="DEBUG", reason="LIBRARY")
                self._delete_thumbnails_for_folder(full_cache["folders"][f])
                del full_cache["folders"][f]

        # B. Reconciliación de carpetas activas
        if folders_to_reconcile:
            log_event(f"Sincronizando {len(folders_to_reconcile)} directorios",
                origin="CONFIG", level="INFO", reason="LIBRARY")

        for folder in folders_to_reconcile:
            old_folder_data = full_cache["folders"].get(folder, {"h": [], "v": []})
            new_folder_data, delta = self._reconcile_folder_cache(
                folder, old_folder_data, extensions)
            full_cache["folders"][folder] = new_folder_data
            for key in stats:
                stats[key] += delta[key]

        # --- 5. PERSISTENCIA Y REPORTE ---
        # Persistir primero el estado materializado final; scan_index sólo conserva
        # después la estructura lógica Active/Inactive.
        self.save_json("cache", full_cache)
        self.save_json("index", scan_index)
        self._reconcile_online_origins(full_cache)

        # La caché final ya es autoritativa: actualizar ahora parent_total evita
        # conservar el total previo a la reconciliación recién completada.
        self.refresh_history_metadata()

        # Los pools existentes se reconcilian diferencialmente.
        # La primera generación conserva la migración legacy.
        if (os.path.isfile(self.files["rotation_h"]) and
                os.path.isfile(self.files["rotation_v"])):
            if not self._reconcile_rotation_pools(previous_cache, full_cache):
                log_event("No se pudieron reconciliar los pools H/V",
                    origin="CONFIG", level="ERROR", reason="LIBRARY")
        elif not self._initialize_rotation_pools(full_cache):
            log_event("No se pudieron inicializar los pools H/V",
                origin="CONFIG", level="ERROR", reason="LIBRARY")

        # --- Reconciliación selectiva ---
        # El mismo maestro alimenta ambas autoridades; scan_index
        # delimita las carpetas Active + Selective.
        # No se reponen imágenes consumidas durante esta ronda.
        previous_selective = self._filter_selective_cache(previous_cache, scan_index)
        current_selective = self._filter_selective_cache(full_cache, scan_index)

        if not self._reconcile_rotation_pools(
                previous_selective, current_selective,
                pool_keys=("sel_rotation_h", "sel_rotation_v")):
            log_event("No se pudieron reconciliar los pools selectivos",
                origin="CONFIG", level="ERROR", reason="LIBRARY")

        if stats["modified"] > 0 or migrated:
            self._refresh_bookmarks_single_metadata(full_cache)

        detail_msg = self._notify_detailed_changes(stats, full_cache)  # Ahora devuelve el detalle o None
        h, v = self._get_cache_totals(full_cache)
        has_changes = any((
            stats["added_h"] > 0,
            stats["added_v"] > 0,
            stats["removed_h"] > 0,
            stats["removed_v"] > 0,
            stats["modified"] > 0,
            migrated > 0,
            invalidated > 0
        ))
        return h, v, has_changes, detail_msg

    def _process_sync_worker(self):
        """
        Reconcilia secuencialmente las carpetas fuera del main thread.

        El worker sólo realiza trabajo de filesystem/imágenes y actualiza
        el estado privado del Sync. GTK, progreso y commit permanecen
        delegados al main thread mediante GLib.idle_add().
        """
        try:
            state = self._async_state
            folders = state['folders_to_reconcile']
            full_cache = state['full_cache']
            stats = state['stats']

            # La migración EXIF también pertenece al worker, nunca a GTK.
            migrated, invalidated, migration_ok = self._migrate_exif_orientation_cache(full_cache)
            state["exif_migration"] = (migrated, invalidated, migration_ok)
            total = len(folders)

            for i, folder in enumerate(folders):

                # La UI sigue perteneciendo al main thread.
                GLib.idle_add(state['on_folder'], folder)

                old_folder_data = full_cache["folders"].get(folder, {"h": [], "v": []})
                new_folder_data, delta = self._reconcile_folder_cache(
                    folder, old_folder_data, state["extensions"])

                full_cache["folders"][folder] = new_folder_data
                for key in stats:
                    stats[key] += delta[key]

                # El progreso conserva su granularidad histórica: una carpeta.
                GLib.idle_add(self._report_sync_worker_progress, i + 1, total)

            # Sin carpetas que reconciliar sólo puede quedar cleanup pendiente.
            if not folders:
                GLib.idle_add(self._commit_sync_async)

        except Exception as e:
            GLib.idle_add(self._report_sync_worker_error, str(e))

    def _commit_sync_async(self):
        """
        Finaliza en el main thread el Sync realizado por _process_sync_worker().

        Mantiene deliberadamente el orden histórico de cleanup, persistencia,
        progress y on_complete; RUNTIME-10 audita ese lifecycle por separado.
        """
        try:
            state = self._async_state
            folders = state['folders_to_reconcile']
            full_cache = state['full_cache']
            stats = state['stats']
            scan_index = state['scan_index']

            # El worker sólo reconcilia carpetas activas. La autoridad para
            # eliminar estado persistente permanece en el COMMIT del main thread.
            for f in state['deleted_folders']:
                if f in full_cache["folders"]:
                    stats["removed_h"] += len(full_cache["folders"][f]['h'])
                    stats["removed_v"] += len(full_cache["folders"][f]['v'])
                    self._delete_thumbnails_for_folder(full_cache["folders"][f])
                    del full_cache["folders"][f]
                if f in scan_index:
                    del scan_index[f]

            # Una hija Inactive pierde materialización, pero conserva su identidad
            # lógica en scan_index para permitir una futura reactivación.
            for f in state['inactive_folders']:
                if f in full_cache["folders"]:
                    stats["removed_h"] += len(full_cache["folders"][f]['h'])
                    stats["removed_v"] += len(full_cache["folders"][f]['v'])
                    self._delete_thumbnails_for_folder(full_cache["folders"][f])
                    del full_cache["folders"][f]

            # El cierre async conserva el contrato autoritativo:
            # cache físico primero, índice lógico después.
            self.save_json("cache", full_cache)
            self.save_json("index", scan_index)
            self._reconcile_online_origins(full_cache)

            # La caché final ya es autoritativa: actualizar ahora parent_total evita
            # conservar el total previo a la reconciliación recién completada.
            self.refresh_history_metadata()

            # Reconciliar los pendientes existentes o inicializarlos
            # desde el maestro definitivo durante la primera ejecución.
            if (os.path.isfile(self.files["rotation_h"]) and
                    os.path.isfile(self.files["rotation_v"])):
                if not self._reconcile_rotation_pools(state["previous_cache"], full_cache):
                    log_event("No se pudieron reconciliar los pools H/V",
                        origin="CONFIG", level="ERROR", reason="LIBRARY")
            elif not self._initialize_rotation_pools(full_cache):
                log_event("No se pudieron inicializar los pools H/V",
                    origin="CONFIG", level="ERROR", reason="LIBRARY")

            # --- Reconciliación selectiva ---
            # Actualizar los pendientes desde el maestro consolidado,
            # conservando las imágenes ya consumidas.
            previous_selective = self._filter_selective_cache(state["previous_cache"], scan_index)
            current_selective = self._filter_selective_cache(full_cache, scan_index)

            if not self._reconcile_rotation_pools(
                    previous_selective, current_selective,
                    pool_keys=("sel_rotation_h", "sel_rotation_v")):
                log_event("No se pudieron reconciliar los pools selectivos",
                    origin="CONFIG", level="ERROR", reason="LIBRARY")

            migrated, invalidated, migration_ok = state["exif_migration"]

            if stats["modified"] > 0 or migrated:
                self._refresh_bookmarks_single_metadata(full_cache)

            self._notify_detailed_changes(stats, full_cache)

            del self._async_state

            if state.get('on_complete'):
                state['on_complete']()

            log_event(f"Escaneo asíncrono completado: {len(folders)} carpetas procesadas",
                origin="CONFIG", level="INFO", reason="LIBRARY")

        except Exception as e:
            log_event(f"Fallo en escaneo asíncrono: {e}",
                origin="CONFIG", level="ERROR", reason="LIBRARY")

            if hasattr(self, '_async_state'):
                state = self._async_state
                del self._async_state

                if state.get('on_error'):
                    state['on_error'](str(e))

        return False  # GLib.idle_add debe ejecutar el COMMIT una sola vez

    def _report_sync_worker_progress(self, current, total):
        """Entrega el progreso del worker y encadena el commit desde el main thread."""
        state = self._async_state
        state['on_progress'](current, total)

        # La última actualización reproduce la frontera actual de RUNTIME-10:
        # primero N/N y después se encola el commit, sin mover su lógica.
        if current >= total:
            GLib.idle_add(self._commit_sync_async)

        return False

    def _report_sync_worker_error(self, message):
        """Cierra en main thread un Sync cuyo WORK ha fallado."""
        log_event(f"Fallo en escaneo asíncrono: {message}",
            origin="CONFIG", level="ERROR", reason="LIBRARY")

        if hasattr(self, '_async_state'):
            state = self._async_state
            del self._async_state

            if state.get('on_error'):
                state['on_error'](message)

        return False

    # --- [SECCIÓN: GESTIÓN DE FUENTES] ---

    def add_source(self, name, path, recursive=False):
        """Añade una nueva fuente y sincroniza la biblioteca."""
        data = self.load_json("sources")
        # Accedemos a la lista interna para evitar el TypeError
        sources_list = data.get("sources", [])

        # Generar ID basado en la ruta (igual que en la migración)
        source_id = hashlib.md5(path.encode()).hexdigest()[:8]

        # Evitar duplicados por ruta o por ID
        if any(s.get('path') == path or s.get('id') == source_id for s in sources_list if isinstance(s, dict)):
            return False

        new_entry = {
            "id": source_id,
            "name": name,
            "path": path,
            "type": "physical",
            "locked": False,
            "recursive": recursive
        }

        sources_list.append(new_entry)
        data["sources"] = sources_list # Actualizamos el diccionario original
        self.save_json("sources", data) # Guardamos el objeto completo

        log_event(f"Fuente añadida: {name}",
            origin="CONFIG", level="INFO", reason="LIBRARY")
        # self.sync_library() # La sincronización ahora se hace asíncronamente desde el panel
        return True

    def get_online_source_path(self):
        """Consulta la ruta de Online sin modificar ni validar su configuración."""
        sources = self.load_json("sources").get("sources", [])
        return next((source.get("path") for source in sources
                     if source.get("id") == "online"), None)

    def record_online_origins(self, entries):
        """Registra varias procedencias Online con una sola persistencia.

        El lote contiene (ruta, item, url). Sólo admite originales
        incorporados en Sources/Online; nunca previews temporales.
        """
        source = self.get_online_source_path()
        if not source:
            return set()

        root = os.path.normcase(os.path.abspath(source))
        origins = self.load_json("online_origins")
        if not isinstance(origins, dict):
            return set()

        expected = {}
        changed = False

        for img_path, item, page_url in entries:
            if (not isinstance(img_path, str)
                    or not isinstance(item, dict)
                    or not isinstance(page_url, str)
                    or not page_url
                    or not os.path.isfile(img_path)):
                continue

            path = os.path.normcase(os.path.abspath(img_path))
            if os.path.dirname(path) != root:
                continue

            record = {
                "provider": item.get("provider"),
                "id": item.get("id"),
                "url": page_url,
            }
            if not all(isinstance(value, str) and value
                       for value in record.values()):
                continue

            expected[path] = record

            if origins.get(path) != record:
                origins[path] = record
                changed = True

        # El JSON se reescribe una sola vez, independientemente
        # del número de originales incorporados en la operación.
        if changed:
            self.save_json("online_origins", origins)

        # save_json registra sus propios errores sin propagarlos.
        # Confirmar qué entradas quedaron realmente persistidas.
        saved = self.load_json("online_origins")

        return {path for path, record in expected.items()
            if saved.get(path) == record}


    def _reconcile_online_origins(self, cache):
        """Retira procedencias de imágenes fuera de image_cache.

        Inactive, Deleted y las bajas físicas comparten una frontera:
        si la imagen deja de estar materializada, WMM deja de custodiar
        su procedencia. No se consulta el disco ni se reconstruye después.
        """
        origins = self.load_json("online_origins")
        if not isinstance(origins, dict) or not origins:
            return

        active_paths = {
            os.path.normcase(os.path.abspath(entry[0]))
            for folder in cache.get("folders", {}).values()
            for orientation in ("h", "v")
            for entry in folder.get(orientation, [])
            if isinstance(entry, list) and entry
            and isinstance(entry[0], str)
        }

        retained = {
            path: record for path, record in origins.items()
            if path in active_paths
        }

        if len(retained) != len(origins):
            self.save_json("online_origins", retained)

    def set_online_source_path(self, path):
        """Configura la ubicación física de Online sin cambiar su identidad."""
        if not path or not os.path.isdir(path):
            return False

        path = os.path.abspath(path)
        data = self.load_json("sources")
        sources = data.get("sources", [])
        online = next((s for s in sources if s.get("id") == "online"), None)

        if online is None:
            return False

        # No registrar dos fuentes físicas sobre el mismo directorio.
        for source in sources:
            other = source.get("path")
            if (source.get("id") != "online"
                    and source.get("type") == "physical"
                    and other
                    and os.path.normcase(os.path.abspath(other))
                    == os.path.normcase(path)):
                log_event(f"Directorio Online ya registrado como fuente: {path}",
                    origin="CONFIG", level="WARN", reason="LIBRARY")
                return False

        if online.get("path") == path:
            return True

        online["path"] = path
        self.save_json("sources", data)
        log_event(f"Directorio Online configurado: {path}",
            origin="CONFIG", level="INFO", reason="LIBRARY")
        return True

    def clear_online_source_path(self):
        """Desvincula Online sin eliminar su identidad ni los archivos físicos."""
        data = self.load_json("sources")
        online = next((s for s in data.get("sources", [])
            if s.get("id") == "online"), None)

        if not online or not online.get("path"):
            return False

        old_path = online["path"]
        online["path"] = ""
        self.save_json("sources", data)

        log_event(f"Directorio Online desvinculado: {old_path}",
            origin="CONFIG", level="INFO", reason="LIBRARY")
        return True

    def remove_source(self, path):
        """Elimina una fuente, limpia su índice y sincroniza la biblioteca."""
        data = self.load_json("sources")
        sources_list = data.get("sources", [])

        original_count = len(sources_list)
        sources_list = [s for s in sources_list
            if not (s.get('path') == path and not s.get('locked', False))]

        if len(sources_list) < original_count:
            data["sources"] = sources_list
            self.save_json("sources", data)
            log_event(f"Fuente eliminada: {path}",
                origin="CONFIG", level="INFO", reason="LIBRARY")
            self.sync_library()
            return True

        log_event(f"No se pudo eliminar la fuente: {path}",
            origin="CONFIG", level="WARN", reason="LIBRARY")
        return False

    def purge_folder_cache(self, folder_path):
        """
        Elimina de image_cache.json la entrada correspondiente a folder_path
        y borra todas las miniaturas asociadas. Retorna True si se eliminó algo.
        """
        cache = self.load_json("cache")

        if "folders" not in cache:
            return False

        if folder_path in cache["folders"]:
            # Conservar el maestro anterior para retirar los pendientes
            # de esta carpeta sin recuperar imágenes ya consumidas.
            previous_cache = {"folders": cache["folders"].copy()}

            # Borrar miniaturas antes de quitar la entrada.
            deleted = self._delete_thumbnails_for_folder(cache["folders"][folder_path])
            del cache["folders"][folder_path]
            self.save_json("cache", cache)
            self._reconcile_online_origins(cache)

            # La reconciliación retira únicamente las entradas afectadas.
            # Mantener ambas autoridades coherentes también ante una purga directa.
            # Desde Sources, la carpeta ya está Inactive y sus pendientes
            # selectivos deberían haberse retirado al desactivarla.
            index = self.load_json("index")
            previous_selective = self._filter_selective_cache(previous_cache, index)
            current_selective = self._filter_selective_cache(cache, index)

            if not self._reconcile_rotation_pools(
                    previous_selective, current_selective,
                    pool_keys=("sel_rotation_h", "sel_rotation_v")):
                log_event("No se pudieron reconciliar los pools selectivos",
                    origin="CONFIG", level="ERROR", reason="LIBRARY")

            log_event(f"Carpeta purgada: {folder_path}",
                origin="CONFIG", level="INFO", reason="LIBRARY")
            return deleted
        return 0

    def has_folder_cache(self, folder_path):
        """Retorna True si la carpeta sigue presente en image_cache."""
        cache = self.load_json("cache")
        return folder_path in cache.get("folders", {})

    def has_child_cache(self, parent_path):
        """Retorna True si alguna carpeta hija conserva entrada en image_cache."""
        cache = self.load_json("cache")

        # Delimitar descendientes por separador, no por prefijo de nombre.
        # La propia carpeta y sus hermanas quedan excluidas.
        root = os.path.normcase(os.path.abspath(parent_path))
        prefix = root if root.endswith(os.sep) else root + os.sep

        return any(os.path.normcase(os.path.abspath(path)).startswith(prefix)
            for path in cache.get("folders", {}))

    def needs_sources_resync(self):
        """Retorna True si el estado materializado no coincide con el ámbito actual de Sources."""
        index = self.load_json("index")
        cache = self.load_json("cache")
        sources = self.load_json("sources").get("sources", [])

        # Compara el ámbito lógico que debería estar materializado
        # con las carpetas que existen realmente en image_cache.
        expected_paths = {path for path in index
            if self._is_covered_by_any_source(path, sources)
            and self.get_index_active(path, index)}

        cached_paths = set(cache.get("folders", {}))
        return expected_paths != cached_paths

    def materialize_folder_cache(self, folder_path):
        """Reconstruye image_cache para una única carpeta activa."""
        index = self.load_json("index")
        if not self.get_index_active(folder_path, index, default=False):
            return False, 0

        if not os.path.isdir(folder_path):
            log_event(f"No se puede materializar la carpeta: {folder_path}",
                origin="CONFIG", level="WARN", reason="LIBRARY")
            return False, 0

        cache = self.load_json("cache")
        # Operación local y explícita: reconstruye sólo esta carpeta.
        # No sustituye a Sync ni resuelve otras Sources pendientes.
        if "folders" not in cache:
            cache = {"folders": {}}

        # Conservar las entradas anteriores para distinguir altas reales
        # de imágenes ya consumidas durante la ronda actual.
        previous_cache = {"folders": cache["folders"].copy()}

        new_h = []
        new_v = []

        try:
            for filename in os.listdir(folder_path):
                if not filename.lower().endswith(self.img_extensions):
                    continue

                image_path = os.path.join(folder_path, filename)
                if not os.path.isfile(image_path):
                    continue

                try:
                    mtime_ns = os.stat(image_path).st_mtime_ns
                except OSError:
                    continue

                orient, width, height = self._process_image(image_path)
                if orient == "h":
                    new_h.append([image_path, width, height, mtime_ns])
                elif orient == "v":
                    new_v.append([image_path, width, height, mtime_ns])

            cache["folders"][folder_path] = {"h": new_h, "v": new_v}
            self.save_json("cache", cache)

            # Actualizar los pendientes H/V con la carpeta materializada.
            # Las imágenes ya consumidas conservan ese estado.
            if not self._reconcile_rotation_pools(previous_cache, cache):
                log_event("No se pudieron reconciliar los pools H/V",
                    origin="CONFIG", level="ERROR", reason="LIBRARY")

            # Reconciliar la misma materialización con la autoridad selectiva.
            # El índice determina elegibilidad; no reinicia los consumidos.
            previous_selective = self._filter_selective_cache(previous_cache, index)
            current_selective = self._filter_selective_cache(cache, index)

            if not self._reconcile_rotation_pools(
                    previous_selective, current_selective,
                    pool_keys=("sel_rotation_h", "sel_rotation_v")):
                log_event("No se pudieron reconciliar los pools selectivos",
                    origin="CONFIG", level="ERROR", reason="LIBRARY")

            total = len(new_h) + len(new_v)
            log_event(f"Carpeta materializada: {folder_path} ({total} imágenes)",
                origin="CONFIG", level="INFO", reason="LIBRARY")
            return True, total

        except (PermissionError, FileNotFoundError, OSError) as e:
            log_event(f"Error materializando carpeta {folder_path}: {e}",
                origin="CONFIG", level="ERROR", reason="LIBRARY")
            return False, 0

    def get_children_state(self, parent_path):
        """
        Retorna el estado global de los hijos de parent_path:
        'all_active', 'all_inactive', o 'mixed'.
        """
        index = self.load_json("index")
        prefix = parent_path if parent_path.endswith(os.sep) else parent_path + os.sep
        has_active = False
        has_inactive = False
        for path, entry in index.items():
            if path.startswith(prefix) and path != parent_path:
                active = self.get_index_active(path, index)
                if active:
                    has_active = True
                else:
                    has_inactive = True
                if has_active and has_inactive:
                    return "mixed"
        if has_active and not has_inactive:
            return "all_active"
        elif has_inactive and not has_active:
            return "all_inactive"
        else:
            # Sin hijos, consideramos all_active para que "Desactivar" esté habilitada
            return "all_active"

    def _delete_thumbnail_for_image(self, img_path):
        """Elimina únicamente la miniatura derivada de una imagen."""
        m = hashlib.md5(img_path.encode()).hexdigest()
        # El nombre del thumbnail depende únicamente de la ruta origen:
        # invalidar una imagen no requiere recorrer ni reconstruir la carpeta.
        thumb_path = os.path.join(self.thumbnails_dir, f"{m}.jpg")

        if not os.path.exists(thumb_path):
            return False

        try:
            os.remove(thumb_path)
            return True

        except OSError as e:
            log_event(f"No se pudo eliminar miniatura {thumb_path}: {e}",
                origin="CONFIG", level="WARN", reason="LIBRARY")
            return False

    def _migrate_exif_orientation_cache(self, cache):
        """
        Actualiza la orientación visual de entradas existentes.
        Invalida sólo miniaturas afectadas por EXIF 2-8.
        La marca de versión se confirma únicamente si no quedan fallos pendientes.
        """
        if cache.get("exif_orientation_version") == 1:
            return 0, 0, True

        from PIL import Image

        reclassified = 0
        invalidated = 0
        pending = False

        for folder_data in cache.get("folders", {}).values():
            migrated = {"h": [], "v": []}

            for old_orientation in ("h", "v"):
                for entry in folder_data.get(old_orientation, []):
                    # El formato legacy seguirá siendo responsabilidad
                    # de la reconciliación existente.
                    if not isinstance(entry, list) or len(entry) < 4:
                        migrated[old_orientation].append(entry)
                        continue

                    path, saved_mtime = entry[0], entry[3]

                    try:
                        current_mtime = os.stat(path).st_mtime_ns
                    except FileNotFoundError:
                        # Sync eliminará la entrada desaparecida.
                        migrated[old_orientation].append(entry)
                        continue
                    except OSError:
                        pending = True
                        migrated[old_orientation].append(entry)
                        continue

                    if current_mtime != saved_mtime:
                        # Sync reprocesará esta versión modificada.
                        migrated[old_orientation].append(entry)
                        continue

                    try:
                        with Image.open(path) as img:
                            exif_orientation = img.getexif().get(274, 1)
                            width, height = img.size
                    except (OSError, ValueError, TypeError, SyntaxError):
                        pending = True
                        migrated[old_orientation].append(entry)
                        continue

                    new_orientation = old_orientation

                    if exif_orientation in (5, 6, 7, 8):
                        width, height = height, width
                        new_orientation = "h" if width >= height else "v"

                    if exif_orientation in (2, 3, 4, 5, 6, 7, 8):
                        thumb_path = os.path.join(self.thumbnails_dir,
                            f"{hashlib.md5(path.encode()).hexdigest()}.jpg")

                        if os.path.exists(thumb_path):
                            if self._delete_thumbnail_for_image(path):
                                invalidated += 1
                            else:
                                pending = True

                        if new_orientation != old_orientation:
                            reclassified += 1

                        entry = [path, width, height, *entry[3:]]

                    migrated[new_orientation].append(entry)

            folder_data["h"] = migrated["h"]
            folder_data["v"] = migrated["v"]

        if not pending:
            cache["exif_orientation_version"] = 1

        log_event(f"Migración EXIF: {reclassified} reclasificadas, "
            f"{invalidated} miniaturas invalidadas"
            + (", con incidencias pendientes" if pending else ""),
            origin="CONFIG", level="INFO", reason="LIBRARY")

        return reclassified, invalidated, not pending

    def _reconcile_folder_cache(self, folder, folder_data, extensions):
        """
        Reconcilia una carpeta física contra su image_cache.

        Reutiliza las imágenes cuya ruta y mtime_ns no han cambiado.
        Reprocesa únicamente imágenes nuevas o modificadas.
        Elimina del cache las que ya no existen.

        Si detecta cache legacy sin mtime_ns, mantiene la migración
        acordada: reconstrucción completa de la carpeta una sola vez.

        Retorna:
            (nuevo_folder_data, stats_delta)
        """
        delta = {
            "added_h": 0,
            "added_v": 0,
            "removed_h": 0,
            "removed_v": 0,
            "unchanged": 0,
            "new": 0,
            "modified": 0,
            "deleted": 0,
        }

        folder_data = folder_data or {"h": [], "v": []}

        old_by_path = {}
        legacy = False

        for orientation in ("h", "v"):
            for entry in folder_data.get(orientation, []):
                if not isinstance(entry, list) or len(entry) < 4:
                    legacy = True

                if isinstance(entry, list) and entry:
                    old_by_path[entry[0]] = (entry, orientation)

        try:
            filenames = os.listdir(folder)
        except (PermissionError, FileNotFoundError, OSError) as e:
            log_event(f"No se pudo inspeccionar carpeta {folder}: {e}",
                origin="CONFIG", level="WARN", reason="LIBRARY")
            return folder_data, delta

        # ------------------------------------------------------
        # MIGRACIÓN LEGACY: reconstrucción completa de carpeta
        # ------------------------------------------------------
        # Una sola entrada sin mtime_ns convierte la carpeta en legacy:
        # se migra completa para no dejar un cache parcialmente actualizado.
        if legacy:
            new_h = []
            new_v = []

            for filename in filenames:
                if not filename.lower().endswith(extensions):
                    continue

                image_path = os.path.join(folder, filename)

                try:
                    file_stat = os.stat(image_path)
                except OSError:
                    # No convertir un fallo temporal de stat en una
                    # migración parcial de la carpeta legacy.
                    return folder_data, delta

                if not stat.S_ISREG(file_stat.st_mode):
                    continue

                orient, width, height = self._process_image(image_path)
                # El thumbnail es derivado de esa versión física:
                # invalidar únicamente el de esta imagen.
                if orient == "h":
                    new_h.append([image_path, width, height, file_stat.st_mtime_ns])
                elif orient == "v":
                    new_v.append([image_path, width, height, file_stat.st_mtime_ns])

            self._delete_thumbnails_for_folder(folder_data)

            # La migración legacy es la única excepción al borrado selectivo:
            # toda la carpeta cambia de contrato y sus derivados se regeneran.
            delta["removed_h"] = len(folder_data.get("h", []))
            delta["removed_v"] = len(folder_data.get("v", []))
            delta["added_h"] = len(new_h)
            delta["added_v"] = len(new_v)

            return {"h": new_h, "v": new_v}, delta

        # ------------------------------------------------------
        # RECONCILIACIÓN DIFERENCIAL
        # ------------------------------------------------------
        new_h = []
        new_v = []
        seen_paths = set()

        for filename in filenames:
            if not filename.lower().endswith(extensions):
                continue

            image_path = os.path.join(folder, filename)

            try:
                file_stat = os.stat(image_path)
            except OSError:
                # Un fallo temporal de stat no demuestra que una imagen conocida
                # haya desaparecido: conservar su entrada evita un borrado falso.
                # Si ya conocíamos la imagen, conservar su cache.
                old_info = old_by_path.get(image_path)

                if old_info:
                    old_entry, old_orientation = old_info
                    seen_paths.add(image_path)

                    if old_orientation == "h":
                        new_h.append(old_entry)
                    else:
                        new_v.append(old_entry)

                continue

            if not stat.S_ISREG(file_stat.st_mode):
                continue

            seen_paths.add(image_path)
            current_mtime_ns = file_stat.st_mtime_ns
            old_info = old_by_path.get(image_path)

            # Misma ruta + mismo mtime_ns: reutilizar cache sin abrir la imagen.
            if old_info:
                old_entry, old_orientation = old_info
                if old_entry[3] == current_mtime_ns:
                    delta["unchanged"] += 1
                    if old_orientation == "h":
                        new_h.append(old_entry)
                    else:
                        new_v.append(old_entry)
                    continue

                # Misma ruta + distinto mtime_ns: misma identidad, nueva versión física.
                delta["modified"] += 1
                orient, width, height = self._process_image(image_path)
                self._delete_thumbnail_for_image(image_path)
                if orient == "h":
                    new_h.append([image_path, width, height, current_mtime_ns])
                elif orient == "v":
                    new_v.append([image_path, width, height, current_mtime_ns])

                continue

            # Imagen nueva.
            delta["new"] += 1
            orient, width, height = self._process_image(image_path)
            if orient == "h":
                new_h.append([image_path, width, height, current_mtime_ns])
                delta["added_h"] += 1
            elif orient == "v":
                new_v.append([image_path, width, height, current_mtime_ns])
                delta["added_v"] += 1

        # Imágenes que estaban cacheadas y ya no existen.
        for old_path, (_, old_orientation) in old_by_path.items():
            if old_path in seen_paths:
                continue

            delta["deleted"] += 1
            delta[f"removed_{old_orientation}"] += 1
            self._delete_thumbnail_for_image(old_path)

        parts = []

        if delta["unchanged"]:
            parts.append(f"{delta['unchanged']} reutilizadas")
        if delta["new"]:
            parts.append(f"{delta['new']} nuevas")
        if delta["modified"]:
            parts.append(f"{delta['modified']} modificadas")
        if delta["deleted"]:
            parts.append(f"{delta['deleted']} eliminadas")
        if delta["new"] or delta["modified"] or delta["deleted"]:
            log_event(f"Reconciliación de carpeta: {folder} — " + ", ".join(parts),
                origin="CONFIG", level="DEBUG", reason="LIBRARY")

        return {"h": new_h, "v": new_v}, delta

    def _delete_thumbnails_for_folder(self, folder_data):
        """
        Elimina los archivos de miniatura de todas las imágenes de una carpeta.
        folder_data es el valor asociado a una clave en cache['folders'].
        Cada imagen usa [path, width, height, mtime_ns].
        """
        thumb_dir = self.thumbnails_dir
        deleted_count = 0
        for orientation in ('h', 'v'):
            for img_entry in folder_data.get(orientation, []):
                img_path = img_entry[0]
                m = hashlib.md5(img_path.encode()).hexdigest()
                thumb_path = os.path.join(thumb_dir, f"{m}.jpg")
                if os.path.exists(thumb_path):
                    try:
                        os.remove(thumb_path)
                        deleted_count += 1
                    except OSError as e:
                        log_event(f"No se pudo eliminar miniatura {thumb_path}: {e}",
                            origin="CONFIG", level="WARN", reason="LIBRARY")

        log_event(f"{deleted_count} miniaturas eliminadas",
            origin="CONFIG", level="INFO", reason="LIBRARY")

        return deleted_count

    def _cleanup_blur_thumbnails(self):
        """
        Elimina todas las miniaturas compuestas (blur_*.jpg) del directorio thumbnails.
        Se ejecuta solo al inicio de sesión para evitar acumulación.
        """
        thumb_dir = self.thumbnails_dir
        if not os.path.isdir(thumb_dir):
            return
        deleted = 0
        for fname in os.listdir(thumb_dir):
            if (fname.startswith("blur_") or fname.startswith("spanned_")) and fname.endswith(".jpg"):
                fpath = os.path.join(thumb_dir, fname)
                try:
                    os.remove(fpath)
                    deleted += 1
                except OSError as e:
                    log_event(f"No se pudo eliminar miniatura blur {fpath}: {e}",
                        origin="CONFIG", level="WARN", reason="LIBRARY")
        if deleted > 0:
            log_event(f"{deleted} miniaturas blur eliminadas al inicio",
                origin="CONFIG", level="INFO", reason="LIBRARY")

    # --- [SIGUIENTE SECCIÓN: HISTORIAL Y LOGS] ---

    def log_error(self, message, reason=None):
        """
        Registra un error en el archivo de log.
        Mantiene solo las últimas 10 entradas.
        """
        log_path = os.path.join(self.data_dir, "error_log.txt")
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}]"
        if reason:
            entry += f" [{reason}]"
        entry += f" {message}\n"

        # Leer entradas existentes
        lines = []
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

        # Añadir nueva entrada al principio
        lines.insert(0, entry)

        # Mantener solo las últimas 10
        lines = lines[:10]

        # Guardar
        with open(log_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

    def _get_cache_totals(self, cache):
        """Helper para sumar totales del caché V5"""
        total_h = sum(len(d['h']) for d in cache.get("folders", {}).values())
        total_v = sum(len(d['v']) for d in cache.get("folders", {}).values())
        return total_h, total_v

    def get_flat_lists(self, cache=None):
        """
        Extrae todas las imágenes del caché y las devuelve en dos listas planas (H y V).
        Cada elemento de la lista es: [ruta, ancho, alto].
        """
        full_cache = self.load_json("cache") if cache is None else cache
        h_list = []
        v_list = []

        for folder_data in full_cache.get("folders", {}).values():
            h_list.extend(folder_data.get("h", []))
            v_list.extend(folder_data.get("v", []))

        return h_list, v_list

    def _filter_selective_cache(self, cache, index):
        """
        Obtiene la vista selectiva de la biblioteca materializada.

        Sólo participan carpetas Active y marcadas en scan_index.
        La vista no modifica image_cache ni los historiales.
        """
        selected = {}

        for folder_path, folder_data in cache.get("folders", {}).items():
            state = index.get(folder_path)

            if (isinstance(state, list) and len(state) == 2
                    and state[0] and state[1]):
                selected[folder_path] = folder_data

        return {"folders": selected}

    def _get_bookmark_rotation_lists(self, bookmarks=None):
        """
        Extrae los favoritos individuales por orientación.
        bookmarks_single_list.json es el maestro; estos datos no
        dependen de Sources ni de sus marcas selectivas.
        """
        h_list = []
        v_list = []

        # Permite comparar dos estados del maestro sin releerlo.
        if bookmarks is None:
            bookmarks = self.load_json("bookmarks_single")

        for entry in bookmarks:
            if not isinstance(entry, list) or len(entry) < 4:
                continue

            if entry[3] == "h":
                h_list.append(entry[:3])
            elif entry[3] == "v":
                v_list.append(entry[:3])

        return h_list, v_list

    def _reconcile_bookmark_rotation_pools(self, previous_bookmarks, current_bookmarks):
        """
        Reconcilia los pendientes de favoritos mediante el mismo
        mecanismo H/V que utilizan las otras autoridades.
        """
        def as_cache(bookmarks):
            h_list, v_list = self._get_bookmark_rotation_lists(bookmarks)
            return {"folders": {"bookmarks": {"h": h_list, "v": v_list}}}

        return self._reconcile_rotation_pools(
            as_cache(previous_bookmarks),
            as_cache(current_bookmarks),
            pool_keys=("bm_rotation_h", "bm_rotation_v"))

    def _initialize_rotation_pools(self, cache):
        """
        Inicializa los pools desde la biblioteca materializada.

        En actualizaciones, descuenta las imágenes del historial legacy.
        No modifica image_cache.json ni elimina history.json hasta que
        el trasvase pueda validarse y se cierre la migración.
        """
        h_path = self.files["rotation_h"]
        v_path = self.files["rotation_v"]

        h_exists = os.path.isfile(h_path)
        v_exists = os.path.isfile(v_path)

        # Los pools existentes conservan sus pendientes.
        if h_exists and v_exists:
            return True

        if h_exists or v_exists:
            log_event("Inicialización H/V incompleta: falta uno de los pools",
                origin="CONFIG", level="ERROR", reason="LIBRARY")
            return False

        # El historial antiguo sólo interviene en la primera generación.
        legacy_path = os.path.join(self.data_dir, "history.json")
        consumed = set()

        if os.path.isfile(legacy_path):
            try:
                with open(legacy_path, "r", encoding="utf-8") as file:
                    legacy = json.load(file)
                consumed = set(legacy.get("history_log", []))
            except (OSError, ValueError, TypeError) as error:
                log_event(f"No se pudo migrar history.json: {error}",
                    origin="CONFIG", level="ERROR", reason="LIBRARY")
                return False

        # Las entradas proceden del maestro vigente, nunca del historial.
        pending_h = []
        pending_v = []

        for folder in cache.get("folders", {}).values():
            pending_h.extend(entry for entry in folder.get("h", [])
                if entry[0] not in consumed)
            pending_v.extend(entry for entry in folder.get("v", [])
                if entry[0] not in consumed)

        self.save_json("rotation_h", pending_h)
        self.save_json("rotation_v", pending_v)

        # Verificar el trasvase antes de autorizar el cierre legacy.
        if (self.load_json("rotation_h") != pending_h or
                self.load_json("rotation_v") != pending_v):
            log_event("Falló la verificación de los pools H/V",
                origin="CONFIG", level="ERROR", reason="LIBRARY")
            return False

        log_event(f"Pools H/V inicializados: {len(pending_h)}H / {len(pending_v)}V; "
            f"historial legacy: {len(consumed)} rutas",
            origin="CONFIG", level="INFO", reason="LIBRARY")

        # El trasvase ya se ha verificado: cerrar el legado.
        self._retire_legacy_rotation_history()
        return True

    def _retire_legacy_rotation_history(self):
        """
        Retira history.json cuando ambos pools H/V están disponibles
        y contienen listas válidas. Nunca reconstruye sus pendientes.
        """
        legacy_path = os.path.join(self.data_dir, "history.json")
        if not os.path.isfile(legacy_path):
            return

        keys = ("rotation_h", "rotation_v")
        if not all(os.path.isfile(self.files[key]) for key in keys):
            return

        if not all(isinstance(self.load_json(key), list) for key in keys):
            log_event("No se retira history.json: pools H/V inválidos",
                origin="CONFIG", level="ERROR", reason="LIBRARY")
            return

        try:
            os.remove(legacy_path)
            log_event("Migración H/V cerrada: history.json eliminado",
                origin="CONFIG", level="INFO", reason="LIBRARY")
        except OSError as error:
            log_event(f"No se pudo eliminar history.json: {error}",
                origin="CONFIG", level="WARN", reason="LIBRARY")

    def _initialize_bookmark_rotation_pools(self):
        """
        Inicializa los pendientes H/V desde los favoritos individuales.

        Sólo durante la primera generación se descuenta el consumo
        registrado en history_vault.json. Los pools existentes no se
        reconstruyen: pueden representar rondas ya consumidas.
        """
        h_key, v_key = "bm_rotation_h", "bm_rotation_v"
        h_exists = os.path.isfile(self.files[h_key])
        v_exists = os.path.isfile(self.files[v_key])

        if h_exists and v_exists:
            return True

        if h_exists or v_exists:
            log_event("Inicialización H/V de bookmarks incompleta",
                origin="CONFIG", level="ERROR", reason="BOOKMARK")
            return False

        # Migrar únicamente el consumo conocido del historial anterior.
        # El historial anterior sólo interviene en la primera generación.
        # Su ausencia no impide crear los pools desde el maestro.
        history_path = self.files["history_vault"]
        consumed = set()

        if os.path.isfile(history_path):
            try:
                with open(history_path, "r", encoding="utf-8") as file:
                    legacy = json.load(file)
                consumed = set(legacy.get("log", []))
            except (OSError, ValueError, TypeError) as error:
                log_event(f"No se pudo migrar history_vault.json: {error}",
                    origin="CONFIG", level="ERROR", reason="BOOKMARK")
                return False

        h_list, v_list = self._get_bookmark_rotation_lists()
        pending_h = [entry for entry in h_list if entry[0] not in consumed]
        pending_v = [entry for entry in v_list if entry[0] not in consumed]

        self.save_json(h_key, pending_h)
        self.save_json(v_key, pending_v)

        if (self.load_json(h_key) != pending_h or
                self.load_json(v_key) != pending_v):
            log_event("Falló la verificación de los pools de bookmarks",
                origin="CONFIG", level="ERROR", reason="BOOKMARK")
            return False

        log_event(f"Pools de bookmarks inicializados: "
            f"{len(pending_h)}H / {len(pending_v)}V; "
            f"historial anterior: {len(consumed)} rutas",
            origin="CONFIG", level="INFO", reason="BOOKMARK")

        # El trasvase ya se ha verificado: cerrar el legado.
        self._retire_legacy_bookmark_history()
        return True

    def _retire_legacy_bookmark_history(self):
        """
        Retira history_vault.json cuando ambos pools H/V de favoritos
        están disponibles y contienen listas válidas.
        Nunca reconstruye ni modifica sus pendientes.
        """
        legacy_path = self.files["history_vault"]
        if not os.path.isfile(legacy_path):
            return

        keys = ("bm_rotation_h", "bm_rotation_v")
        if not all(os.path.isfile(self.files[key]) for key in keys):
            return

        if not all(isinstance(self.load_json(key), list) for key in keys):
            log_event("No se retira history_vault.json: pools H/V inválidos",
                origin="CONFIG", level="ERROR", reason="BOOKMARK")
            return

        try:
            os.remove(legacy_path)
            log_event("Migración H/V de favoritos cerrada: history_vault.json eliminado",
                origin="CONFIG", level="INFO", reason="BOOKMARK")
        except OSError as error:
            log_event(f"No se pudo eliminar history_vault.json: {error}",
                origin="CONFIG", level="WARN", reason="BOOKMARK")

    def _get_builtin_fallback_images(self):
        """
        Obtiene las imágenes internas de WMM usadas únicamente cuando la
        biblioteca materializada del usuario no contiene ninguna imagen.

        Este fallback no forma parte de Sources: no modifica sources.json,
        scan_index.json, image_cache.json ni genera miniaturas.
        """
        fallback_dir = os.path.join(self.app_root, "screenshots")
        h_list = []
        v_list = []

        if not os.path.isdir(fallback_dir):
            return h_list, v_list

        for filename in sorted(os.listdir(fallback_dir)):
            if not filename.lower().endswith(self.img_extensions):
                continue

            image_path = os.path.join(fallback_dir, filename)
            if not os.path.isfile(image_path):
                continue

            orientation, width, height = ImageEngine.process_image(image_path)
            if orientation == "h":
                h_list.append([image_path, width, height])
            elif orientation == "v":
                v_list.append([image_path, width, height])

        return h_list, v_list

    def _reconcile_rotation_pools(self, previous_cache, current_cache,
            pool_keys=("rotation_h", "rotation_v")):
        """
        Actualiza los pendientes H/V según los cambios del maestro.

        Conserva las imágenes todavía pendientes, incorpora altas reales
        y descarta las eliminadas. Una imagen previamente consumida no
        reaparece por sincronizar o modificar sus metadatos.
        """
        pending_h = self.load_json(pool_keys[0])
        pending_v = self.load_json(pool_keys[1])

        if not isinstance(pending_h, list) or not isinstance(pending_v, list):
            log_event("Pools H/V no válidos para reconciliación",
                origin="CONFIG", level="ERROR", reason="LIBRARY")
            return False

        # El maestro anterior distingue una imagen nueva de otra
        # que ya existía pero fue consumida durante esta ronda.
        previous_paths = {entry[0]
            for folder in previous_cache.get("folders", {}).values()
            for orientation in ("h", "v")
            for entry in folder.get(orientation, [])}

        pending_paths = {entry[0] for entry in pending_h + pending_v}

        # La orientación y los datos vigentes proceden siempre del maestro.
        # Las altas entran en su pool; los consumidos siguen excluidos.
        updated = {}
        for orientation, key in zip(("h", "v"), pool_keys):
            updated[key] = [entry
                for folder in current_cache.get("folders", {}).values()
                for entry in folder.get(orientation, [])
                if entry[0] in pending_paths or entry[0] not in previous_paths]

        # No reescribir los archivos cuando el resultado es idéntico.
        for key, previous in zip(pool_keys, (pending_h, pending_v)):
            if updated[key] != previous:
                self.save_json(key, updated[key])

        return True

    def _update_history(self, entry_id, mode):
        """
        Registra una entrada en el historial aplicando 'Aleatoriedad Redonda':
        Si el ciclo está a punto de completarse, se vacía preventivamente para
        garantizar que el último elemento no se repita en el nuevo inicio.
        """
        # Sólo permanecen los historiales de favoritos y presets.
        file_key = f"history_{mode}"
        log_key = "log"

        # 2. Carga y metadatos
        hist = self.load_json(file_key)
        log = hist.get(log_key, [])
        parent_total = hist.get("parent_total", 100)

        # 3. Lógica de la Escoba (Ciclo cerrado para colecciones pequeñas)
        # Si el log llegará al total con esta inserción, reseteamos el pool.
        if parent_total <= 100 and len(log) >= (parent_total - 1):
            log = []

        # 4. Gestión quirúrgica del log: evitar duplicados y mover al top
        if entry_id in log:
            log.remove(entry_id)

        log.insert(0, entry_id)

        # 5. Persistencia y actualización de timestamp
        limit = min(parent_total, 100)
        hist.update({log_key: log[:limit], "last_update": time.time()})
        self.save_json(file_key, hist)

    def _filter_by_smart_ratio(self, candidates, m_w, m_h, orientation):
        """
        Filtra candidatos basándose en el ratio del monitor y la orientación.
        """
        final_candidates = []
        m_ratio = m_w / m_h

        for item in candidates:
            # Soportar tanto [path, w, h] como [path, w, h, orient]
            path, w, h = item[0], item[1], item[2]

            # 1. Filtro de Orientación Físico
            img_orient = "h" if w >= h else "v"
            if img_orient != orientation:
                continue

            # 2. Filtro de "Cuadratura" para monitores verticales (Ratio 1.0 Estricto)
            # No permitimos imágenes horizontales en monitores verticales.
            if orientation == "v":
                ratio = w / h
                if ratio > 1.0: # Si es horizontal (ancho > alto), descartar.
                    continue

            # 3. Filtro de Smart Ratio (evitar deformación excesiva)
            img_ratio = w / h
            diff = abs(img_ratio - m_ratio)

            if diff < 0.5:
                final_candidates.append(path)

        return final_candidates

    def get_smart_selection(self, target_w=None, target_h=None, orientation="h",
        match_orientation=True, rotation_authority=None, exclude_paths=None):
        """
        Selecciona y consume una imagen pendiente de los pools H/V.

        Con orientación vinculada, cada monitor consume su propio pool.
        Sin vinculación, ambas orientaciones comparten una ronda y cada
        imagen tiene idéntica probabilidad de selección.
        """
        # Conservar la firma dimensional para los consumidores actuales.
        # Los tamaños y ratios ya no condicionan la selección.
        # El switch selecciona la autoridad; cada una conserva sus pendientes.
        # Bookmarks solicita su propia autoridad sin alterar
        # la selección general/selectiva gobernada por el switch.
        if rotation_authority == "bookmarks":
            if not self._initialize_bookmark_rotation_pools():
                return None
            prefix = "bm_rotation"
        else:
            selective = self.load_json("settings").get("global", {}).get(
                "selective_rotation_enabled", False)
            prefix = "sel_rotation" if selective else "rotation"


        pool_keys = (f"{prefix}_v",) if orientation == "v" else (f"{prefix}_h",)
        if not match_orientation:
            pool_keys = (f"{prefix}_h", f"{prefix}_v")

        pending = {key: self.load_json(key) for key in pool_keys}

        # Reponer sólo cuando se agotan los pendientes elegibles.
        # En modo combinado, ambos pools forman una única ronda.
        if not any(pending.values()):
            if rotation_authority == "bookmarks":
                h_list, v_list = self._get_bookmark_rotation_lists()
                if not h_list and not v_list:
                    return None
            elif selective:
                cache = self.load_json("cache")
                index = self.load_json("index")
                selected_cache = self._filter_selective_cache(cache, index)
                h_list, v_list = self.get_flat_lists(selected_cache)

                # Sin carpetas elegibles, no recurrir a la autoridad general.
                if not h_list and not v_list:
                    return None
            else:
                h_list, v_list = self.get_flat_lists()

                # Mantener el fallback original de biblioteca vacía.
                if not h_list and not v_list:
                    h_list, v_list = self._get_builtin_fallback_images()
                    fallback = (v_list if orientation == "v" else h_list) \
                        if match_orientation else h_list + v_list
                    return random.choice(fallback)[0] if fallback else None

            master = {f"{prefix}_h": h_list, f"{prefix}_v": v_list}
            for key in pool_keys:
                pending[key] = master[key]
                if pending[key]:
                    self.save_json(key, pending[key])

            log_event(f"Reposición {prefix}: "
                f"{len(pending.get(f'{prefix}_h', []))}H / "
                f"{len(pending.get(f'{prefix}_v', []))}V",
                origin="CONFIG", level="DEBUG", reason="LIBRARY")

        total = sum(len(records) for records in pending.values())
        if not total:
            return None

        # Al completar una composición, priorizar imágenes no asignadas
        # a otros monitores. Si todas están excluidas, conservar el
        # comportamiento de reserva: seleccionar entre los pendientes.
        if exclude_paths:
            excluded = set(exclude_paths)
            eligible = [(key, pos)
                for key in pool_keys
                for pos, entry in enumerate(pending[key])
                if entry[0] not in excluded]

            if eligible:
                key, pos = random.choice(eligible)
                selected = pending[key].pop(pos)[0]
                self.save_json(key, pending[key])
                return selected

        # Un índice uniforme sobre todos los registros pendientes
        # proporciona proporcionalidad natural entre H y V.
        index = random.randrange(total)

        for key in pool_keys:
            records = pending[key]
            if index < len(records):
                selected = records.pop(index)[0]
                self.save_json(key, records)
                return selected
            index -= len(records)

        return None

    def _process_image(self, path):
        """Delega en ImageEngine el procesado de la imagen."""
        return ImageEngine.process_image(path)

    def get_thumbnail(self, img_path):
        """Delega en ImageEngine la generación de miniaturas."""
        return ImageEngine.generate_thumbnail(img_path, self.thumbnail_max_height,
            self.thumbnail_max_width, thumb_dir=self.thumbnails_dir)

    def get_composite_thumbnail(self, img_path, target_w, target_h):
        """Delega en ImageEngine la generación de miniaturas compuestas con blur."""
        return ImageEngine.generate_composite_thumbnail(
            img_path, target_w, target_h, thumb_dir=self.thumbnails_dir)

    def open_file(self, path, capability=None, **params):
        """
        Abre la ruta con la aplicación predeterminada del sistema.
        Puede solicitar capacidades adicionales soportadas por la plataforma.
        """
        try:
            if os.path.exists(path):
                self._platform.open_file(path, capability=capability, **params)
                return True
            return False

        except Exception as e:
            log_event(f"No se pudo abrir archivo: {e}",
                origin="CONFIG", level="ERROR", reason="LIBRARY")

            return False

    def _notify_detailed_changes(self, stats, cache):
        """Construye un informe basado en entradas, salidas y modificaciones reales."""
        # Calculamos el movimiento total (Añadidas + Eliminadas + Modificadas)
        total_changes = sum(stats.values())

        # Si el movimiento es 0, salimos sin devolver nada
        if total_changes == 0:
            return None

        msg_lines = []

        # Bloque de Altas
        if stats["added_h"] > 0 or stats["added_v"] > 0:
            added = []
            if stats["added_h"] > 0: added.append(f"<b>+{stats['added_h']}</b> H")
            if stats["added_v"] > 0: added.append(f"<b>+{stats['added_v']}</b> V")
            msg_lines.append(_("New") + ": " + ' • '.join(added))

        # Bloque de Bajas
        if stats["removed_h"] > 0 or stats["removed_v"] > 0:
            removed = []
            if stats["removed_h"] > 0: removed.append(f"<b>-{stats['removed_h']}</b> H")
            if stats["removed_v"] > 0: removed.append(f"<b>-{stats['removed_v']}</b> V")
            msg_lines.append(_("Removed") + ": " + ' • '.join(removed))

        # Bloque de Modificaciones
        # Modified conserva identidad por ruta: no se representa como alta + baja.
        if stats["modified"] > 0:
            msg_lines.append(_("Modified") + f": <b>{stats['modified']}</b>")

        # Totales actuales para contexto
        total_h, total_v = self._get_cache_totals(cache)

        body = "\n".join(msg_lines)
        summary = "\n" + _("Total library") + ": {}H | {}V".format(total_h, total_v)

        # Devolvemos el texto completo para que otro método (main.py) lo use en la notificación
        return f"{body}\n{summary}"

    def _send_notification(self, reason, detail_msg, action=None, level="info"):
        """
        Motor de notificaciones con jerarquía visual automática.
        La lógica de construcción del mensaje se mantiene aquí.
        La ejecución se delega en PlatformManager para usar la implementación adecuada según el SO.
        Niveles:
          - 'info' (default): icon dialog-information
          - 'warn': icon dialog-warning
          - 'error': icon dialog-error
        """
        # 1. Mapa de jerarquía de iconos
        icon_map = {
            "info": "dialog-information-symbolic",
            "warn": "dialog-warning-symbolic",
            "error": "dialog-error-symbolic"
        }
        selected_icon = icon_map.get(level, "dialog-information")

        # 2. Construcción dinámica del cuerpo
        fixed_title = "WMM Wallpapers"
        lines = [f"<b>{reason}</b>"]
        if action:
            lines.append(_("Action") + ": " + action)
        lines.append(f"\n<i>{detail_msg}</i>")

        full_message = "\n".join(lines)

        # 3. Delegar la ejecución en PlatformManager
        try:
            self._platform.send_notification(fixed_title, full_message, selected_icon)
        except Exception as e:
            log_event(f"Error en notificación: {e}",
                origin="CONFIG", level="ERROR", reason="NOTIFY")

# --- DEBUGGER & DIAGNOSTIC MODE ---
if __name__ == "__main__":
    print("\n" + "═"*50)
    print("  WMM CONFIG HANDLER - SYSTEM CHECKUP")
    print("═"*50)

    handler = ConfigHandler()

    # 1. Rutas Críticas
    print(f"\n[PATH CHECK]")
    print(f"  Root:  {handler.app_root}")
    print(f"  Data:  {handler.data_dir}")
    print(f"  Cache: {handler.cache_dir}")

    # 2. Integridad de Archivos JSON
    print(f"\n[JSON FILES]")
    for key, path in handler.files.items():
        status = "✔ OK" if os.path.exists(path) else "✘ MISSING"
        size = f"({os.path.getsize(path)} bytes)" if os.path.exists(path) else ""
        print(f"  {key.ljust(10)} {status.ljust(10)} {size}")

    # 3. Test de Lógica de Marcadores
    print(f"\n[BOOKMARKS LOGIC]")
    next_id = handler.get_next_bookmark_id()
    print(f"  Next suggested: Bookmark {next_id:02d}")

    # 4. Estado de la Biblioteca Global
    print(f"\n[LIBRARY OVERALL]")
    h_list, v_list = handler.get_flat_lists()
    print(f"  Total Horizontal: {len(h_list)}")
    print(f"  Total Vertical:   {len(v_list)}")

    # 5. SOURCES STAT (Desglose por carpetas)
    print(f"\n[SOURCES STAT]")
    settings = handler.load_json("settings")
    cache = handler.load_json("cache")

    # Accedemos a la lista de diccionarios
    sources_list = settings.get("global", {}).get("sources", [])

    if not sources_list:
        print("  (!) No sources defined in settings.json")
    else:
        for source_item in sources_list:
            # EXTRAEMOS LA RUTA (aquí estaba el fallo)
            path = source_item.get("path")

            if not path:
                continue

            # Ahora path es un string, os.path.exists funcionará
            exists = "✔" if os.path.exists(path) else "✘ NOT FOUND"

            # Buscamos en el caché
            #folder_data = cache.get("folders", {}).get(path, {"h": [], "v": []})
            #num_h = len(folder_data["h"])
            #num_v = len(folder_data["v"])

            # Formateamos la salida
            folder_name = os.path.basename(path) or path
            print(f"  [{exists}] {folder_name[:20].ljust(20)}") # | H: {str(num_h).ljust(4)} | V: {str(num_v).ljust(4)}")
            if exists == "✘ NOT FOUND":
                print(f"      └─ Path: {path}")

    print("\n" + "═"*50)
    print("  Diagnostic complete.")
    print("═"*50 + "\n")
