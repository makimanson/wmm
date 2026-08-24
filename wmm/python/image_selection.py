#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

"""
WMM - Wallpaper Multi-Monitor Manager

image_selection.py - Image Selection Engine
=============================
Centraliza toda la lógica de selección de imágenes para los distintos
escenarios de WMM (rotaciones, cambios manuales, modos sync/async, spanned, etc.)

Este módulo se encarga de:
    - Determinar qué imágenes asignar a cada monitor según el modo (sync/async).
    - Gestionar la selección de imagen maestra para el modo spanned.
    - Aplicar filtros de orientación, ratio e historial para evitar repeticiones.
    - Manejar la selección manual sin rotar (REASON_SELECTION).

No depende de GTK, ni de la plataforma directamente. Solo usa ConfigHandler
para acceder a los datos persistentes (vault, bookmarks, history, etc.)
y, eventualmente, ImageEngine para obtener dimensiones de imágenes (aunque
la selección debería basarse solo en metadatos).

Flujo típico:
    1. main.py obtiene la geometría, el vault y la configuración.
    2. Llama a ImageSelectionEngine.build_selection() con el motivo y los datos.
    3. El motor recibe el diccionario selection {hash: path} y metadatos.
    4. main.py renderiza y aplica el fondo.

"""

import os
import random
import time

from typing import Dict, List, Optional, Tuple, Any
from config_handler import ConfigHandler
from image_engine import ImageEngine  # Solo para dimensiones, si es necesario
from debug_logger import log_event
from monitor_manager import get_spanned_reference_hash

class ImageSelectionEngine:
    """
    Motor de selección de imágenes para WMM.
    Encapsula toda la lógica de decisión sobre qué imagen asignar a cada monitor.
    """

    def __init__(self, config_handler: ConfigHandler, platform):
        """
        Args:
            config_handler: Instancia de ConfigHandler para acceso a datos.
            platform: Instancia de PlatformManager (solo para obtener geometría del canvas).
        """
        self.ch = config_handler
        self.platform = platform
        self.last_rotated_hash = None  # Para async rotation
        self.rotation_queue = []       # Para async rotation

        # Referencia a la función de historial (se usa internamente)
        self._update_history = self.ch._update_history

    # ==========================================================
    # MÉTODOS PÚBLICOS PRINCIPALES
    # ==========================================================

    def build_selection(
        self,
        reason: str,
        active_hashes: List[str],
        monitors_map: Dict,
        active_session: Dict,
        settings: Dict,
        target_hashes: Optional[List[str]] = None,
        target_bookmark: Optional[str] = None,
        temp_settings: Optional[Dict] = None
    ) -> Tuple[Dict[str, Any], bool, Dict]:
        """
        Construye el diccionario de selección {monitor_hash: path_or_color}
        y devuelve metadatos necesarios para el renderizado.

        Esta función es una copia exacta del método _build_selection de main.py,
        con la única diferencia de que ahora es un método de esta clase.

        Args:
            reason: Motivo de la ejecución (REASON_TIMER, REASON_MANUAL, etc.)
            active_hashes: Lista de hashes de monitores activos.
            monitors_map: Diccionario con geometría de monitores (de geometry.json).
            active_session: Diccionario active_session del vault.
            settings: Diccionario global de settings.json.
            target_hashes: Lista de hashes a rotar (para modo async). Si es None, se calcula.
            target_bookmark: Nombre de un preset específico a cargar (opcional).
            temp_settings: Ajustes temporales (desde el panel) que sobrescriben settings.

        Returns:
            (selection, valid_assets_found, metadata)
            - selection: dict {hash: path} o {hash: ("color", ...)} para monitores inactivos.
            - valid_assets_found: bool indicando si hay al menos una imagen válida.
            - metadata: dict con spanned_enabled, wp_mode, wallpaper_effect, etc.
        """
        log_event(f"Construyendo selección para motivo: {reason}", origin="IMG_SEL", level="DEBUG", reason="NOTIFY")

        # Unificar settings con temp_settings
        if temp_settings:
            settings = {**settings, **temp_settings}

        # Extraer parámetros de configuración
        color_mode = settings.get("color_mode", "solid_color")
        solid_color = settings.get("solid_color", "#000000")
        gradient_h = settings.get("gradient_h", ["#000000", "#8D9797"])
        gradient_v = settings.get("gradient_v", ["#000000", "#8D9797"])
        sl_mode = settings.get("slideshow_mode", "sync")
        wp_mode = settings.get("wallpaper_mode", "fit")
        fav_mode = settings.get("slideshow_bookmark", False)
        spanned_enabled = settings.get("spanned_enabled", False)
        wallpaper_effect_scope = settings.get("wallpaper_effect_scope", "blur")
        wallpaper_effect = settings.get("wallpaper_effect", "none")

        selection = {}
        valid_assets_found = False
        metadata = {
            "spanned_enabled": spanned_enabled,
            "wp_mode": wp_mode,
            "wallpaper_effect": wallpaper_effect,
            "wallpaper_effect_scope": wallpaper_effect_scope,
            "color_mode": color_mode,
            "solid_color": solid_color,
            "gradient_h": gradient_h,
            "gradient_v": gradient_v,
        }

        # ============================================================
        # CASO ESPECIAL: SELECCIÓN MANUAL (REASON_SELECTION)
        # ============================================================
        if reason == ConfigHandler.REASON_SELECTION:
            # Delegamos en _handle_selection_mode (que está copiado abajo)
            return self._handle_selection_mode(
                temp_settings=temp_settings,
                monitors_map_real=monitors_map,  # En main.py se llamaba monitors_map_real
                active_hashes=active_hashes,
                # Los demás parámetros se extraen dentro de _handle_selection_mode
            )

        # ============================================================
        # RECONFIGURACIÓN (cambio de hardware, inicio)
        # ============================================================
        if reason in ConfigHandler.RECONFIGURATION_REASONS:

            log_event("Reconfiguración: manteniendo imágenes del vault", origin="IMG_SEL", level="DEBUG", reason="VAULT")

            if spanned_enabled:
                selection, valid_assets_found = self._build_spanned_selection(
                    reason, active_hashes, monitors_map, active_session, settings,
                    target_preset=None, preset_assigned_paths=None, fav_mode=fav_mode
                )
                return selection, valid_assets_found, metadata

            for m_hash in active_hashes:
                if m_hash not in monitors_map:
                    continue
                entry = active_session.get(m_hash, {})
                if isinstance(entry, dict):
                    path = entry.get("path")
                    is_active = entry.get("active", True)
                else:
                    path = entry if entry else None
                    is_active = True

                if not is_active:
                    selection[m_hash] = ("color", color_mode, solid_color, gradient_h, gradient_v)
                elif path and os.path.exists(path):
                    selection[m_hash] = path
                    self._update_history(path)
                else:
                    # No tiene imagen válida: seleccionar una inteligentemente
                    m = monitors_map[m_hash]
                    orient = m.get('orientation', 'horizontal')[0].lower()
                    new_path = self.ch.get_smart_selection(m.get('width', 1920), m.get('height', 1080), orientation=orient)
                    if new_path:
                        selection[m_hash] = new_path
                        self.ch.update_monitor_image(m_hash, new_path)
                        self._update_history(new_path)
                    else:
                        selection[m_hash] = ("color", color_mode, solid_color, gradient_h, gradient_v)
            valid_assets_found = bool(selection)
            return selection, valid_assets_found, metadata

        # ============================================================
        # ROTACIÓN NORMAL (TIMER, MANUAL, BOOKMARK)
        # ============================================================
        # Resolver target_hashes para async
        if target_hashes is None:
            target_hashes = self._resolve_async_targets(
                reason, active_hashes, active_session, settings
            )

        # Determinar si se usa preset
        preset_data = None
        preset_wp_mode = None
        preset_spanned = None
        preset_effect_scope = None
        preset_effect = None
        target_preset = None
        preset_assigned_paths = []
        target_preset_data = None
        active_composition = {}

        if target_bookmark or (sl_mode == "sync" and fav_mode):
            bookmarks = self.ch.load_json("bookmarks")
            if target_bookmark:
                target_preset = target_bookmark
                log_event(f"Aplicando composición manual: '{target_preset}'", origin="IMG_SEL", level="INFO", reason="BOOKMARK")
            else:
                if bookmarks:
                    presets_history = self.ch.load_json("history_presets").get("log", [])
                    available = [k for k in bookmarks if k not in presets_history]
                    if not available:
                        self.ch.save_json("history_presets", {
                            "last_update": time.time(),
                            "log": [],
                            "parent_total": len(bookmarks)
                        })
                        available = list(bookmarks.keys())
                    target_preset = random.choice(available)
                    log_event(f"Preset global elegido: {target_preset}", origin="IMG_SEL", level="DEBUG", reason="BOOKMARK")

            if target_preset and target_preset in bookmarks:
                bm_data = bookmarks[target_preset].copy()
                active_composition = {
                    key: bm_data[key]
                    for key in ("__mode__", "__spanned__", "__effect__", "__effect_scope__")
                    if key in bm_data
                }
                if "__mode__" in bm_data:
                    preset_wp_mode = bm_data.pop("__mode__")
                if "__spanned__" in bm_data:
                    preset_spanned = bm_data.pop("__spanned__")
                if "__effect_scope__" in bm_data:
                    preset_effect_scope = bm_data.pop("__effect_scope__")
                if "__effect__" in bm_data:
                    preset_effect = bm_data.pop("__effect__")
                for m_hash, val in list(bm_data.items()):
                    if m_hash.startswith("__"):
                        continue
                    if isinstance(val, str):
                        bm_data[m_hash] = {"path": val if val else "", "active": True}
                self._update_history(target_preset, mode="presets")
                preset_assigned_paths = [v.get("path", "") for v in bm_data.values() if isinstance(v, dict) and v.get("path")]
                target_preset_data = bm_data
                preset_data = bm_data

        # Aplicar preferencias del preset
        if preset_wp_mode:
            wp_mode = preset_wp_mode
            metadata["wp_mode"] = wp_mode
        if preset_spanned is not None:
            spanned_enabled = preset_spanned
            metadata["spanned_enabled"] = spanned_enabled
        if preset_effect_scope:
            wallpaper_effect_scope = preset_effect_scope
            metadata["wallpaper_effect_scope"] = wallpaper_effect_scope
        if preset_effect is not None:
            wallpaper_effect = preset_effect
            metadata["wallpaper_effect"] = wallpaper_effect

        # La composición activa corresponde exclusivamente a los
        # overrides impuestos por este ciclo.
        self.ch.set_active_composition(active_composition)

        # ============================================================
        # CONSTRUCCIÓN DE LA SELECCIÓN
        # ============================================================
        if spanned_enabled:
            selection, valid_assets_found = self._build_spanned_selection(
                reason, active_hashes, monitors_map, active_session, settings,
                target_preset=target_preset, preset_assigned_paths=preset_assigned_paths,
                fav_mode=fav_mode
            )
            return selection, valid_assets_found, metadata

        else:
            # --- MODO NORMAL (cada monitor con su imagen) ---
            current_f_mode = sl_mode.lower()
            for m_hash in active_hashes:
                if m_hash not in monitors_map:
                    continue
                vault_entry = active_session.get(m_hash, {})
                if isinstance(vault_entry, dict):
                    is_active = vault_entry.get("active", True)
                else:
                    is_active = True

                if not is_active:
                    selection[m_hash] = ("color", color_mode, solid_color, gradient_h, gradient_v)
                    continue

                m = monitors_map[m_hash]
                m_orient = m['orientation'][0].lower()
                entry = active_session.get(m_hash)
                if isinstance(entry, dict):
                    current_vault_path = entry.get("path")
                else:
                    current_vault_path = entry

                is_target = (m_hash in target_hashes) if reason in ConfigHandler.ASYNC_ROTATION_REASONS else True
                img_path = None

                if is_target and (target_preset or fav_mode):
                    if target_preset and m_hash in target_preset_data:
                        p_entry = target_preset_data[m_hash]
                        if not p_entry.get("active", True):
                            selection[m_hash] = ("color", color_mode, solid_color, gradient_h, gradient_v)
                            continue
                        elif p_entry.get("path") and os.path.exists(p_entry["path"]):
                            img_path = p_entry["path"]
                    else:
                        img_path = self._get_smart_favorite(
                            m_hash, current_f_mode, m_orient,
                            forced_bookmark=target_preset,
                            exclude_paths=preset_assigned_paths
                        )
                elif is_target:
                    img_path = self.ch.get_smart_selection(m['width'], m['height'], orientation=m_orient)

                if img_path and os.path.exists(img_path):
                    selection[m_hash] = img_path
                    self.ch.update_monitor_image(m_hash, img_path)
                    self._update_history(img_path)
                    valid_assets_found = True
                elif current_vault_path and os.path.exists(str(current_vault_path)):
                    selection[m_hash] = current_vault_path
                    valid_assets_found = True
                else:
                    img_path = self.ch.get_smart_selection(m['width'], m['height'], orientation=m_orient)
                    if img_path:
                        selection[m_hash] = img_path
                        self.ch.update_monitor_image(m_hash, img_path)
                        self._update_history(img_path)
                        valid_assets_found = True
                    else:
                        selection[m_hash] = ("color", color_mode, solid_color, gradient_h, gradient_v)

        return selection, valid_assets_found, metadata

    # ==========================================================
    # MÉTODOS AUXILIARES PRIVADOS (copiados de main.py)
    # ==========================================================

    def _resolve_async_targets(
        self,
        reason: str,
        active_hashes: List[str],
        active_session: Dict,
        settings: Dict
    ) -> List[str]:
        """
        Aplica la lógica de rotación asíncrona (async).
        Devuelve la lista de hashes objetivo (target_hashes) para este ciclo.
        """
        target_hashes = active_hashes[:]
        sl_mode = settings.get("slideshow_mode", "sync")

        if sl_mode == "async" and reason in ConfigHandler.ASYNC_ROTATION_REASONS:
            active_image_hashes = []
            for h in active_hashes:
                entry = active_session.get(h, {})
                if isinstance(entry, dict):
                    if entry.get("active", True):
                        active_image_hashes.append(h)
                else:
                    active_image_hashes.append(h)

            self.rotation_queue = [h for h in self.rotation_queue if h in active_image_hashes]

            if not self.rotation_queue or not set(self.rotation_queue).issubset(set(active_image_hashes)):
                if not active_image_hashes:
                    target_hashes = []
                    self.rotation_queue = []
                    log_event("Async: sin monitores activos con imagen", origin="IMG_SEL", level="DEBUG", reason="HARDWARE")
                else:
                    new_queue = list(active_image_hashes)
                    if len(new_queue) > 1:
                        while True:
                            random.shuffle(new_queue)
                            if new_queue[0] != self.last_rotated_hash:
                                break
                    else:
                        random.shuffle(new_queue)
                    self.rotation_queue = new_queue
                    target_hashes = [self.rotation_queue.pop(0)]
                    self.last_rotated_hash = target_hashes[0]
                    log_event(f"Async: cola reconstruida, turno del monitor {target_hashes[0]}", origin="IMG_SEL", level="DEBUG", reason="HARDWARE")
            else:
                target_hashes = [self.rotation_queue.pop(0)]
                self.last_rotated_hash = target_hashes[0]
                log_event(f"Async: turno del monitor {target_hashes[0]}", origin="IMG_SEL", level="DEBUG", reason="HARDWARE")

        return target_hashes

    def _get_smart_favorite(
        self,
        m_hash: str,
        mode: str,
        target_orient: str,
        forced_bookmark: Optional[str] = None,
        fname: Optional[str] = None,
        exclude_paths: Optional[List[str]] = None
    ) -> Optional[str]:
        """
        Versión Definitiva V5: Respeta el Relleno Dinámico y gestiona imágenes desaparecidas.
        """
        exclude_paths = exclude_paths or []
        actual_settings = self.ch.load_json("settings")
        real_mode = actual_settings.get("global", {}).get("slideshow_mode", "async").lower()
        t_orient = target_orient[0].lower()

        if real_mode == "sync" or forced_bookmark:
            bookmarks = self.ch.load_json("bookmarks")
            if not forced_bookmark and bookmarks:
                forced_bookmark = random.choice(list(bookmarks.keys()))

            preset_data = bookmarks.get(forced_bookmark, {}) if forced_bookmark else {}
            path = preset_data.get(m_hash)

            if not path or not os.path.exists(path):
                if path and not os.path.exists(path):
                    fname = os.path.basename(path)
                    msg = _("Image: '{image}' from preset: '{preset}' not found.").format(image=fname, preset=forced_bookmark)
                    print(f" [!] {msg}")
                    self.ch._send_notification(
                        reason=_("PRESET image not found"),
                        action=_("Assigning a random one"),
                        detail_msg=msg,
                        level="warn"
                    )
                path = self.ch.get_vault_selection(orientation=t_orient, exclude=exclude_paths)

            return path
        else:
            return self.ch.get_vault_selection(orientation=t_orient, exclude=exclude_paths)

    def _build_spanned_selection(self, reason, active_hashes, monitors_map, active_session,
                                 settings, target_preset=None, preset_assigned_paths=None,
                                 fav_mode=False):
        """
        Construye la selección para el modo spanned.
        Retorna (selection, valid_assets_found).
        """
        selection = {}
        valid_assets_found = False

        # Obtener geometría, orientación y monitor de referencia para Spanned.
        canvas_w, canvas_h = self.platform.get_total_canvas_geometry(monitors_map)
        canvas_orientation = "horizontal" if canvas_w >= canvas_h else "vertical"
        canvas_orient = canvas_orientation[0]
        spanned_hash = get_spanned_reference_hash(monitors_map)

        if spanned_hash is None:
            return selection, valid_assets_found

        log_event(f"Spanned: canvas {canvas_w}x{canvas_h} ({canvas_orientation}), monitor de referencia {spanned_hash}", origin="IMG_SEL", level="DEBUG", reason="VAULT")

        # Obtener imagen actual del vault del monitor que representa al canvas
        entry = active_session.get(spanned_hash, {})
        if isinstance(entry, dict):
            current_path = entry.get("path")
        else:
            current_path = entry

        # Parámetros de color
        color_mode = settings.get("color_mode", "solid_color")
        solid_color = settings.get("solid_color", "#000000")
        gradient_h = settings.get("gradient_h", ["#000000", "#8D9797"])
        gradient_v = settings.get("gradient_v", ["#000000", "#8D9797"])

        # Decidir la ruta
        path = None

        # Casos especiales: mantener imagen actual en hardware o selección manual
        if reason in (ConfigHandler.REASON_HARDWARE, ConfigHandler.REASON_SELECTION):
            if current_path and os.path.exists(current_path):
                path = current_path

        if not path and target_preset:
            # Usar preset
            if preset_assigned_paths and preset_assigned_paths[0]:
                path = preset_assigned_paths[0]
            else:
                path = self._get_smart_favorite(
                    spanned_hash, "sync", canvas_orient,
                    forced_bookmark=target_preset,
                    exclude_paths=preset_assigned_paths
                )
        elif not path and fav_mode:
            path = self.ch.get_vault_selection(orientation=canvas_orient)
        elif not path:
            path = self.ch.get_smart_selection(canvas_w, canvas_h, orientation=canvas_orient)

        # Asignar y persistir siempre sobre el monitor alineado con el canvas
        if path and os.path.exists(path):
            selection[spanned_hash] = path
            valid_assets_found = True
            self.ch.update_monitor_image(spanned_hash, path)
            self._update_history(path)
        else:
            selection[spanned_hash] = ("color", color_mode, solid_color, gradient_h, gradient_v)
            valid_assets_found = False

        return selection, valid_assets_found

    def _handle_selection_mode(
        self,
        temp_settings: Dict,
        monitors_map_real: Dict,
        active_hashes: List[str]
    ) -> Tuple[Dict[str, Any], bool, Dict]:
        """
        Aplica la selección manual sin rotar (REASON_SELECTION).
        Carga las imágenes actuales del vault y las renderiza directamente.
        """
        log_event("Aplicando selección manual", origin="IMG_SEL", level="DEBUG", reason="LIBRARY")

        vault = self.ch.load_json("vault")
        active_session = vault.get("active_session", {})
        selection = {}

        settings = self.ch.load_json("settings").get("global", {})
        solid_color = settings.get("solid_color", "#000000")
        color_mode = settings.get("color_mode", "solid_color")
        gradient_h = settings.get("gradient_h", ["#000000", "#8D9797"])
        gradient_v = settings.get("gradient_v", ["#000000", "#8D9797"])
        wallpaper_effect_scope = settings.get("wallpaper_effect_scope", "blur")
        wallpaper_effect = temp_settings.get("wallpaper_effect", settings.get("wallpaper_effect", "none")) if temp_settings else settings.get("wallpaper_effect", "none")
        spanned_enabled = temp_settings.get("spanned_enabled", settings.get("spanned_enabled", False)) if temp_settings else settings.get("spanned_enabled", False)
        wp_mode = temp_settings.get("wallpaper_mode", settings.get("wallpaper_mode", "fit")) if temp_settings else settings.get("wallpaper_mode", "fit")

        metadata = {
            "spanned_enabled": spanned_enabled,
            "wp_mode": wp_mode,
            "wallpaper_effect": wallpaper_effect,
            "wallpaper_effect_scope": wallpaper_effect_scope,
            "color_mode": color_mode,
            "solid_color": solid_color,
            "gradient_h": gradient_h,
            "gradient_v": gradient_v,
        }

        if spanned_enabled:
            canvas_w, canvas_h = self.platform.get_total_canvas_geometry(monitors_map_real)
            canvas_orientation = "horizontal" if canvas_w >= canvas_h else "vertical"
            canvas_orient = "h" if canvas_orientation == "horizontal" else "v"

            log_event(f"Spanned reactivo: canvas {canvas_w}x{canvas_h} ({canvas_orientation})", origin="IMG_SEL", level="DEBUG", reason="VAULT")

            active_monitors_map = {m_hash: monitors_map_real[m_hash] for m_hash in active_hashes if m_hash in monitors_map_real}
            spanned_hash = get_spanned_reference_hash(active_monitors_map)

            if spanned_hash is None:
                return {}, False, metadata

            log_event(f"Spanned reactivo: monitor de referencia {spanned_hash}", origin="IMG_SEL", level="DEBUG", reason="VAULT")

            path = None
            source_hash = None

            # 1. Intentar primero el monitor de referencia Spanned
            entry = active_session.get(spanned_hash, {})
            if isinstance(entry, dict):
                candidate_path = entry.get("path")
                is_active = entry.get("active", True)
            else:
                candidate_path = entry if entry else None
                is_active = True

            if is_active and candidate_path and os.path.exists(candidate_path):
                path = candidate_path
                source_hash = spanned_hash

            # 2. Si no tiene imagen válida, probar otros monitores activos
            #    con la misma orientación que el canvas, de forma determinista
            if not path:
                compatible_hashes = []

                for candidate_hash in active_hashes:
                    if candidate_hash == spanned_hash:
                        continue

                    monitor = monitors_map_real.get(candidate_hash, {})
                    monitor_orientation = monitor.get("orientation")

                    if monitor_orientation not in ("horizontal", "vertical"):
                        monitor_w = monitor.get("width", 0)
                        monitor_h = monitor.get("height", 0)
                        monitor_orientation = "horizontal" if monitor_w >= monitor_h else "vertical"

                    if monitor_orientation == canvas_orientation:
                        compatible_hashes.append(candidate_hash)

                for candidate_hash in sorted(compatible_hashes):
                    entry = active_session.get(candidate_hash, {})
                    if isinstance(entry, dict):
                        candidate_path = entry.get("path")
                        is_active = entry.get("active", True)
                    else:
                        candidate_path = entry if entry else None
                        is_active = True

                    if not is_active:
                        continue

                    if candidate_path and os.path.exists(candidate_path):
                        path = candidate_path
                        source_hash = candidate_hash
                        break

            if path:
                log_event(f"Spanned reactivo: reutilizando imagen del monitor {source_hash}", origin="IMG_SEL", level="DEBUG", reason="VAULT")

            # 3. Si ninguna imagen actual sirve, seleccionar una nueva
            if not path:
                log_event(f"Spanned reactivo: ninguna imagen actual coincide con canvas {canvas_orientation}; seleccionando nueva", origin="IMG_SEL", level="DEBUG", reason="VAULT")
                path = self.ch.get_smart_selection(canvas_w, canvas_h, orientation=canvas_orient)

                if path:
                    self.ch.update_monitor_image(spanned_hash, path)
                    self._update_history(path)
                else:
                    log_event("No se pudo obtener imagen para spanned. Usando color de fondo.", origin="IMG_SEL", level="WARN", reason="LIBRARY")

            if path and os.path.exists(path):
                selection = {spanned_hash: path}
            else:
                selection = {spanned_hash: ("color", color_mode, solid_color, gradient_h, gradient_v)}

            return selection, bool(selection), metadata

        for m_hash in active_hashes:
            entry = active_session.get(m_hash, {})
            if isinstance(entry, dict):
                path = entry.get("path")
                is_active = entry.get("active", True)
            else:
                path = entry if entry else None
                is_active = True

            if is_active:
                if path and os.path.exists(path):
                    selection[m_hash] = path
                    self._update_history(path)
                else:
                    m = monitors_map_real.get(m_hash, {})
                    if m:
                        orient = m.get('orientation', 'horizontal')[0].lower()
                        new_path = self.ch.get_smart_selection(m.get('width', 1920), m.get('height', 1080), orientation=orient)
                        if new_path:
                            selection[m_hash] = new_path
                            self.ch.update_monitor_image(m_hash, new_path)
                            self._update_history(new_path)
                        else:
                            selection[m_hash] = ("color", color_mode, solid_color, gradient_h, gradient_v)
                    else:
                        selection[m_hash] = ("color", color_mode, solid_color, gradient_h, gradient_v)
            else:
                selection[m_hash] = ("color", color_mode, solid_color, gradient_h, gradient_v)

        return selection, bool(selection), metadata
