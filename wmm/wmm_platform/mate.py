#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

"""
WMM - Wallpaper Multi-Monitor Manager

mate.py - Módulo de plataforma para MATE (Linux).
=================================================
Contiene solo las implementaciones específicas de este entorno.
"""

import os
import sys
import time
import shutil
import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Wnck", "3.0")

from gi.repository import Gio, Gdk, GLib, Wnck
from PIL import Image
from debug_logger import log_event
from i18n import _

def get_install_path(data_base, app_domain):
    """Devuelve la ruta de instalación para MATE."""
    return os.path.join(data_base, app_domain)

def _force_desktop_settings(config_handler, log_success=True):
    """
    Fuerza los ajustes de MATE necesarios para que WMM controle
    correctamente la composición y transición del fondo de escritorio:
      - picture-options     = 'spanned'
      - draw-background     = true
      - background-fade     = true
    Verifica cada ajuste y notifica al usuario si alguno no se aplicó.
    Las reafirmaciones internas del Fade pueden silenciar sólo el log de éxito.
    """
    try:
        settings = Gio.Settings.new("org.mate.background")

        # 1. Restablecer los ajustes requeridos por WMM
        if settings.get_string("picture-options") != "spanned":
            settings.set_string("picture-options", "spanned")

        if not settings.get_boolean("draw-background"):
            settings.set_boolean("draw-background", True)

        if not settings.get_boolean("background-fade"):
            settings.set_boolean("background-fade", True)

        if settings.get_string("color-shading-type") != "solid":
            settings.set_string("color-shading-type", "solid")

        if settings.get_string("primary-color") != "rgb(0,0,0)":
            settings.set_string("primary-color", "rgb(0,0,0)")

        if settings.get_string("secondary-color") != "rgb(0,0,0)":
            settings.set_string("secondary-color", "rgb(0,0,0)")

        # 2. Verificar que MATE ha aceptado todos los ajustes
        issues = []

        if settings.get_string("picture-options") != "spanned":
            issues.append("Picture aspect")

        if not settings.get_boolean("draw-background"):
            issues.append("Background drawing")

        if not settings.get_boolean("background-fade"):
            issues.append("Background fade")

        if settings.get_string("color-shading-type") != "solid":
            issues.append("Background color type")

        if settings.get_string("primary-color") != "rgb(0,0,0)":
            issues.append("Primary background color")

        if settings.get_string("secondary-color") != "rgb(0,0,0)":
            issues.append("Secondary background color")

        # 3. Informar solo si MATE no ha podido mantener el estado requerido
        if issues:
            log_event(f"No se pudieron forzar algunos ajustes: {', '.join(issues)}. Notificando al usuario.",
                origin="MATE", level="WARN", reason="HARDWARE")
            config_handler._send_notification(
                reason="WMM: " + _("Configuration issue"),
                detail_msg=_("For WMM to function correctly, please check the following settings in 'Control Center > Appearance > Background':")
                + "\n" + "\n".join(f"• {issue}" for issue in issues),
                level="warn"
            )
        elif log_success:
            log_event("Todos los ajustes del sistema forzados correctamente",
                origin="MATE", level="DEBUG", reason="HARDWARE")

    except Exception as e:
        log_event(f"Error al forzar ajustes de MATE: {e}",
            origin="MATE", level="ERROR", reason="NOTIFY")

def render_master_wallpaper(self, processed_images, monitors_map, config_handler):
    """
    Monta el lienzo a partir de imágenes ya procesadas y lo aplica en MATE.
    """
    if not processed_images:
        log_event("No hay imágenes procesadas para MATE",
            origin="MATE", level="ERROR", reason="LIBRARY")
        return False

    # Calcular dimensiones del canvas
    canvas_w = max(mon['x'] + mon['width'] for mon in monitors_map.values())
    canvas_h = max(mon['y'] + mon['height'] for mon in monitors_map.values())

    # Crear lienzo en blanco
    master_canvas = Image.new('RGB', (canvas_w, canvas_h), (0, 0, 0))

    # Pegar cada imagen procesada en su posición
    for m_hash, img in processed_images.items():
        if m_hash not in monitors_map:
            continue

        mon = monitors_map[m_hash]
        x, y = mon['x'], mon['y']
        master_canvas.paste(img, (x, y))

    # Preparar la ruta del lienzo maestro
    master_path = os.path.join(config_handler.cache_dir, "wallpaper_master.jpg")

    # Aplicar el wallpaper
    self.set_wallpaper(master_canvas, master_path, config_handler)

    return True

def set_wallpaper(master_canvas, master_path, config_handler):
    """Guarda y aplica el wallpaper maestro mediante el backend de MATE."""
    _force_desktop_settings(config_handler)

    try:
        settings_data = config_handler.load_json("settings").get("global", {})
        sl_mode = settings_data.get("slideshow_mode", "sync")
        settings = Gio.Settings.new("org.mate.background")

        # Transición SYNC: sacar primero el escritorio a negro
        if sl_mode == "sync":
            fade_color_path = os.path.join(config_handler.cache_dir, "fade_color.png")
            hold_path = os.path.join(config_handler.cache_dir, "wallpaper_hold.jpg")

            if not os.path.exists(fade_color_path):
                Image.new("RGB", (1, 1), (0, 0, 0)).save(fade_color_path)

            # Consumir la primera transición de MATE con una copia visualmente idéntica
            if os.path.exists(master_path):
                shutil.copyfile(master_path, hold_path)
                settings.set_string("picture-filename", hold_path)
                _force_desktop_settings(config_handler, log_success=False)

                # Pausa visual deliberada: deja a MATE consumir la primera
                # transición. No sincroniza estado ni realiza polling.
                time.sleep(1.0)

            # Fade-out hacia negro
            settings.set_string("picture-filename", fade_color_path)
            _force_desktop_settings(config_handler, log_success=False)

            # Pausa visual deliberada: mantiene el negro durante el fade-out.
            # No sincroniza estado ni realiza polling.
            time.sleep(1.0)

        # Guardar y aplicar el nuevo lienzo maestro
        master_canvas.save(master_path, "JPEG", quality=95)
        log_event(f"Lienzo maestro generado en MATE: {master_path}",
            origin="MATE", level="INFO", reason="LIBRARY")

        settings.set_string("picture-filename", master_path)

        if sl_mode == "sync":
            log_event("Transición Fade aplicada (sync)",
                origin="MATE", level="INFO", reason="LIBRARY")
        else:
            log_event("Wallpaper aplicado en MATE (async)",
                origin="MATE", level="INFO", reason="LIBRARY")

    except Exception as e:
        log_event(f"MATE no respondió: {e}", origin="MATE", level="ERROR", reason="NOTIFY")

def get_window_available_area(pid):
    """Devuelve el área útil del monitor donde se encuentra la ventana indicada."""
    try:
        screen = Wnck.Screen.get_default()
        screen.force_update()

        window = next((w for w in screen.get_windows() if w.get_pid() == pid), None)
        if not window:
            return None

        x, y, width, height = window.get_geometry()

        display = Gdk.Display.get_default()
        if not display:
            return None

        monitor = display.get_monitor_at_point(x + width // 2, y + height // 2)
        if not monitor:
            return None

        workarea = monitor.get_workarea()

        return {
            "x": workarea.x,
            "y": workarea.y,
            "width": workarea.width,
            "height": workarea.height,
        }

    except Exception as e:
        log_event(f"No se pudo obtener el área útil de la ventana: {e}",
            origin="MATE", level="WARN", reason="WINDOW")
        return None

def set_window_size_limit(window, max_width, max_height):
    """Publica el tamaño máximo permitido para la ventana del panel."""
    try:
        geometry = Gdk.Geometry()
        geometry.max_width = int(max_width)
        geometry.max_height = int(max_height)

        window.set_geometry_hints(None, geometry, Gdk.WindowHints.MAX_SIZE)

        log_event(f"Límite máximo del panel aplicado: {max_width}x{max_height}",
            origin="MATE", level="DEBUG", reason="LAYOUT")
        return True

    except Exception as e:
        log_event(f"No se pudo aplicar el límite máximo del panel: {e}",
            origin="MATE", level="WARN", reason="LAYOUT")
        return False

def preserve_window_position_on_expand(pid):
    """
    Conserva la posición de la ventana durante una expansión del panel.

    Marco puede recolocar hacia arriba una ventana cuando su nuevo tamaño
    excede el área útil. Se observa el cambio real de geometría y se restaura
    la posición previa si el gestor de ventanas la modifica.
    """
    try:
        pid = int(pid)

        screen = Wnck.Screen.get_default()
        screen.force_update()

        window = next((w for w in screen.get_windows() if w.get_pid() == pid), None)
        if not window:
            return

        x, y, _, _ = window.get_geometry()
        state = {"handler_id": None}

        def stop_watching():
            handler_id = state["handler_id"]
            if handler_id is not None:
                try:
                    window.disconnect(handler_id)
                except Exception:
                    pass
                state["handler_id"] = None
            return False

        def on_geometry_changed(changed_window):
            try:
                current_x, current_y, width, height = changed_window.get_geometry()
                log_event(f"Geometría modificada durante expansión: x={current_x}, y={current_y}, w={width}, h={height}",
                    origin="MATE", level="DEBUG", reason="LAYOUT")

                if current_x == x and current_y == y:
                    return

                stop_watching()

                changed_window.set_geometry(
                    Wnck.WindowGravity.CURRENT,
                    Wnck.WindowMoveResizeMask.X | Wnck.WindowMoveResizeMask.Y,
                    x, y, width, height
                )
                log_event(f"Posición restaurada tras expansión para PID {pid}: x={x}, y={y}",
                    origin="MATE", level="DEBUG", reason="LAYOUT")

            except Exception as e:
                stop_watching()
                log_event(f"No se pudo restaurar la posición tras expansión: {e}",
                    origin="MATE", level="WARN", reason="LAYOUT")

        state["handler_id"] = window.connect("geometry-changed", on_geometry_changed)

        # Evitar dejar el watcher conectado si Marco no modifica la posición.
        GLib.timeout_add(1000, stop_watching)

    except Exception as e:
        log_event(f"No se pudo preservar la posición antes de expandir: {e}",
            origin="MATE", level="WARN", reason="LAYOUT")

def correct_initial_window_position(pid):
    """Corrige la posición inicial del panel si Marco lo desplaza fuera del área útil."""
    try:
        pid = int(pid)

        def correct_position():
            try:
                screen = Wnck.Screen.get_default()
                screen.force_update()

                window = next((w for w in screen.get_windows() if w.get_pid() == pid), None)
                if not window:
                    return False

                x, y, width, height = window.get_geometry()

                display = Gdk.Display.get_default()
                if not display:
                    return False

                monitor = display.get_monitor_at_point(x + width // 2, y + height // 2)
                if not monitor:
                    return False

                workarea = monitor.get_workarea()

                if y < workarea.y:
                    window.set_geometry(
                        Wnck.WindowGravity.CURRENT,
                        Wnck.WindowMoveResizeMask.X | Wnck.WindowMoveResizeMask.Y,
                        x, workarea.y, width, height)
                    log_event(f"Posición inicial corregida para PID {pid}: y={workarea.y}",
                        origin="MATE", level="DEBUG", reason="LAYOUT")

            except Exception as e:
                log_event(f"No se pudo corregir la posición inicial: {e}",
                    origin="MATE", level="WARN", reason="LAYOUT")

            return False

        GLib.timeout_add(100, correct_position)

    except Exception as e:
        log_event(f"No se pudo programar la corrección inicial: {e}",
            origin="MATE", level="WARN", reason="LAYOUT")

def ensure_keybindings(app_dir):
    """
    Instala el atajo de teclado de WMM si todavía no existe.

    No asigna ninguna combinación de teclas por defecto.
    La configuración del atajo pertenece siempre al usuario.
    """
    import json
    import shlex

    # ----------------------------------------------------------
    # 1. Comando directo
    # ----------------------------------------------------------
    send_command_path = os.path.join(app_dir, "python", "send_command.py")

    if not os.path.exists(send_command_path):
        log_event(f"Script no encontrado: {send_command_path}",
            origin="MATE", level="WARN", reason="SETTINGS")
        return

    command = " ".join([
        shlex.quote(sys.executable),
        shlex.quote(send_command_path),
        shlex.quote(json.dumps({"action": "force_rotation"}, separators=(",", ":"))),
        shlex.quote("HOTKEY"),
    ])

    # ----------------------------------------------------------
    # 2. Nombre traducido
    # ----------------------------------------------------------
    full_name = f"WMM - { _('Next Background') }"

    schema = "org.mate.control-center.keybinding"
    base_path = "/org/mate/desktop/keybindings/"

    # ----------------------------------------------------------
    # 3. Buscar WMM existente y primer índice libre
    # ----------------------------------------------------------
    free_index = None

    for index in range(100):
        path = f"{base_path}custom{index}/"

        try:
            ks = Gio.Settings.new_with_path(schema, path)

            existing_name = ks.get_string("name")
            existing_action = ks.get_string("action")
            existing_binding = ks.get_string("binding")

            if existing_action == command:
                log_event(f"Atajo de WMM ya instalado (custom{index})",
                    origin="MATE", level="INFO", reason="SETTINGS")
                return

            if free_index is None and not existing_name and not existing_action and not existing_binding:
                free_index = index

        except Exception:
            continue

    if free_index is None:
        log_event("No hay un índice libre para registrar el atajo de WMM",
            origin="MATE", level="WARN", reason="SETTINGS")
        return

    # ----------------------------------------------------------
    # 4. Crear el nuevo atajo
    # ----------------------------------------------------------
    path = f"{base_path}custom{free_index}/"
    ks = Gio.Settings.new_with_path(schema, path)

    ks.set_string("name", full_name)
    ks.set_string("action", command)

    log_event(f"Atajo instalado correctamente (custom{free_index})",
        origin="MATE", level="INFO", reason="SETTINGS")
