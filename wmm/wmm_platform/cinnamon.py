#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

"""
WMM - Wallpaper Multi-Monitor Manager

cinnamon.py - Módulo de plataforma para Cinnamon (Linux).
==========================================================
Contiene solo las implementaciones específicas de este entorno.
"""
import os
import glob
import hashlib
import subprocess
import time
import json
import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib
from PIL import Image
from debug_logger import log_event
from i18n import _

# Variable global para mantener vivo el monitor de archivos
_monitor = None

def get_install_path(data_base, app_domain):
    """Devuelve la ruta de instalación para Cinnamon."""
    return os.path.join(data_base, 'cinnamon', 'applets', app_domain)

def get_window_available_area(pid):
    """
    Devuelve el área útil del monitor que contiene la ventana identificada
    por PID, según la workarea calculada por Muffin.

    Returns:
        dict: {"x": int, "y": int, "width": int, "height": int}
        None: si Cinnamon no puede resolver la ventana o la consulta falla.
    """
    try:
        pid = int(pid)

        script = f"""
        (() => {{
            let window = global.get_window_actors()
                .map(actor => actor.get_meta_window())
                .find(window => window.get_pid() === {pid});

            if (!window)
                return null;

            let area = window.get_work_area_current_monitor();

            return {{
                x: area.x,
                y: area.y,
                width: area.width,
                height: area.height
            }};
        }})()
        """

        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)

        result = bus.call_sync(
            "org.Cinnamon",
            "/org/Cinnamon",
            "org.Cinnamon",
            "Eval",
            GLib.Variant("(s)", (script,)),
            GLib.VariantType.new("(bs)"),
            Gio.DBusCallFlags.NONE,
            1000,
            None
        )

        success, value = result.unpack()

        if not success or not value:
            log_event(f"Muffin no pudo resolver el área útil para PID {pid}", origin="CINNAMON", level="DEBUG", reason="D-BUS")
            return None

        area = json.loads(value)

        if not isinstance(area, dict):
            return None

        x = int(area["x"])
        y = int(area["y"])
        width = int(area["width"])
        height = int(area["height"])

        if width <= 0 or height <= 0:
            return None

        result_area = {
            "x": x,
            "y": y,
            "width": width,
            "height": height,
        }

        log_event(f"Área útil Cinnamon obtenida para PID {pid}: {result_area}", origin="CINNAMON", level="DEBUG", reason="D-BUS")

        return result_area

    except Exception as e:
        log_event(f"No se pudo obtener el área útil desde Cinnamon: {e}", origin="CINNAMON", level="WARN", reason="D-BUS")
        return None

def preserve_window_position_on_expand(pid):
    """
    Conserva la posición de la ventana durante una expansión del panel.

    Muffin puede recolocar hacia arriba una ventana cuando su nuevo tamaño
    excede el área útil del monitor. Se guarda la posición previa y, una vez
    procesado el resize, se restaura únicamente si Muffin la ha modificado.
    """
    try:
        pid = int(pid)
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)

        capture_script = f"""
        (() => {{
            let window = global.get_window_actors()
                .map(actor => actor.get_meta_window())
                .find(window => window.get_pid() === {pid});

            if (!window)
                return null;

            let frame = window.get_frame_rect();

            return {{
                x: frame.x,
                y: frame.y
            }};
        }})()
        """

        result = bus.call_sync(
            "org.Cinnamon",
            "/org/Cinnamon",
            "org.Cinnamon",
            "Eval",
            GLib.Variant("(s)", (capture_script,)),
            GLib.VariantType.new("(bs)"),
            Gio.DBusCallFlags.NONE,
            1000,
            None
        )

        success, value = result.unpack()

        if not success or not value:
            return

        position = json.loads(value)

        if not isinstance(position, dict):
            return

        x = int(position["x"])
        y = int(position["y"])

        def restore_position():
            try:
                restore_script = f"""
                (() => {{
                    let window = global.get_window_actors()
                        .map(actor => actor.get_meta_window())
                        .find(window => window.get_pid() === {pid});

                    if (!window)
                        return false;

                    let frame = window.get_frame_rect();
                    let moved = frame.x !== {x} || frame.y !== {y};

                    if (moved)
                        window.move_frame(true, {x}, {y});

                    return moved;
                }})()
                """

                result = bus.call_sync(
                    "org.Cinnamon",
                    "/org/Cinnamon",
                    "org.Cinnamon",
                    "Eval",
                    GLib.Variant("(s)", (restore_script,)),
                    GLib.VariantType.new("(bs)"),
                    Gio.DBusCallFlags.NONE,
                    1000,
                    None
                )

                success, value = result.unpack()

                if success and value and json.loads(value):
                    log_event(f"Posición restaurada tras expansión para PID {pid}: x={x}, y={y}", origin="CINNAMON", level="DEBUG", reason="LAYOUT")

            except Exception as e:
                log_event(f"No se pudo restaurar la posición tras expansión: {e}", origin="CINNAMON", level="WARN", reason="LAYOUT")

            return False

        # Esperar a que GTK y Muffin hayan procesado el nuevo tamaño.
        GLib.timeout_add(50, restore_position)

    except Exception as e:
        log_event(f"No se pudo preservar la posición antes de expandir: {e}", origin="CINNAMON", level="WARN", reason="LAYOUT")

def correct_initial_window_position(pid):
    """
    Corrige la posición inicial del panel si Muffin lo desplaza por encima
    del área útil al mapear una ventana más alta que la workarea.
    """
    try:
        pid = int(pid)
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)

        script = f"""
        (() => {{
            let window = global.get_window_actors()
                .map(actor => actor.get_meta_window())
                .find(window => window.get_pid() === {pid});

            if (!window)
                return false;

            let frame = window.get_frame_rect();
            let area = window.get_work_area_current_monitor();

            if (frame.y >= area.y)
                return false;

            window.move_frame(true, frame.x, area.y);
            return true;
        }})()
        """

        result = bus.call_sync(
            "org.Cinnamon",
            "/org/Cinnamon",
            "org.Cinnamon",
            "Eval",
            GLib.Variant("(s)", (script,)),
            GLib.VariantType.new("(bs)"),
            Gio.DBusCallFlags.NONE,
            1000,
            None
        )

        success, value = result.unpack()

        if success and value and json.loads(value):
            log_event(f"Posición inicial corregida para PID {pid}", origin="CINNAMON", level="DEBUG", reason="LAYOUT")

    except Exception as e:
        log_event(f"No se pudo corregir la posición inicial: {e}", origin="CINNAMON", level="WARN", reason="LAYOUT")

def render_master_wallpaper(self, processed_images, monitors_map, config_handler):
    """
    Monta el lienzo a partir de imágenes ya procesadas y lo aplica en Cinnamon.
    """
    if not processed_images:
        log_event("No hay imágenes procesadas para Cinnamon", origin="CINNAMON", level="ERROR", reason="LIBRARY")
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

def _force_desktop_settings(config_handler):
    """
    Fuerza los ajustes del sistema necesarios para que WMM funcione
    correctamente en Cinnamon:
      - picture-options     = 'spanned'  (no deformar el lienzo)
      - slideshow           = false      (evitar interferencias)
      - color-shading-type  = 'solid'    (evitar mezclas de color)
    Verifica cada ajuste y notifica al usuario si alguno no se aplicó.
    """
    try:
        subprocess.run(
            ["gsettings", "set", "org.cinnamon.desktop.background", "picture-options", "spanned"],
            check=False
        )
        log_event("Forzando picture-options a 'spanned'", origin="CINNAMON", level="DEBUG", reason="HARDWARE")

        subprocess.run(
            ["gsettings", "set", "org.cinnamon.desktop.background.slideshow", "slideshow-enabled", "false"],
            check=False
        )
        log_event("Forzando slideshow a 'false'", origin="CINNAMON", level="DEBUG", reason="HARDWARE")

        subprocess.run(
            ["gsettings", "set", "org.cinnamon.desktop.background", "color-shading-type", "solid"],
            check=False
        )
        log_event("Forzando color-shading-type a 'solid'", origin="CINNAMON", level="DEBUG", reason="HARDWARE")

        issues = []

        result = subprocess.run(
            ["gsettings", "get", "org.cinnamon.desktop.background", "picture-options"],
            capture_output=True, text=True
        )
        if result.stdout.strip().lower().replace("'", "") != "spanned":
            issues.append("Picture aspect")

        result = subprocess.run(
            ["gsettings", "get", "org.cinnamon.desktop.background.slideshow", "slideshow-enabled"],
            capture_output=True, text=True
        )
        if result.stdout.strip().lower() != "false":
            issues.append("Slideshow")

        result = subprocess.run(
            ["gsettings", "get", "org.cinnamon.desktop.background", "color-shading-type"],
            capture_output=True, text=True
        )
        if result.stdout.strip().lower().replace("'", "") != "solid":
            issues.append("Background color type")

        if issues:
            log_event(
                f"No se pudieron forzar algunos ajustes: {', '.join(issues)}. Notificando al usuario.",
                origin="CINNAMON", level="WARN", reason="HARDWARE"
            )
            config_handler._send_notification(
                reason="WMM: " + _("Configuration issue"),
                detail_msg=_("For WMM to function correctly, please check the following settings in 'System Settings > Backgrounds':")
                + "\n" + "\n".join(f"• {issue}" for issue in issues),
                level="warn"
            )
        else:
            log_event("Todos los ajustes del sistema forzados correctamente", origin="CINNAMON", level="DEBUG", reason="HARDWARE")

    except Exception as e:
        log_event(f"Error al forzar ajustes de Cinnamon: {e}", origin="CINNAMON", level="ERROR", reason="NOTIFY")

def set_wallpaper(master_canvas, final_path, config_handler):
    """
    Aplica el fondo de pantalla usando gsettings (Cinnamon).
    Fuerza los ajustes del sistema y aplica una transición suave.
    """
    _force_desktop_settings(config_handler)

    try:
        settings = config_handler.load_json("settings").get("global", {})
        sl_mode = settings.get("slideshow_mode", "sync")

        if sl_mode == "sync":
            from gi.repository import Gdk
            result_color = subprocess.run(
                ["gsettings", "get", "org.cinnamon.desktop.background", "primary-color"],
                capture_output=True, text=True
            )
            color_str = result_color.stdout.strip().lower().replace("'", "")
            rgba = Gdk.RGBA()

            if rgba.parse(color_str):
                r = int(rgba.red * 255)
                g = int(rgba.green * 255)
                b = int(rgba.blue * 255)
            else:
                r, g, b = 0, 0, 0

            fade_color_path = os.path.join(config_handler.cache_dir, "fade_color.png")
            Image.new('RGB', (1, 1), (r, g, b)).save(fade_color_path)

            os.system(f"gsettings set org.cinnamon.desktop.background picture-uri 'file://{fade_color_path}'")
            time.sleep(2.0)
            os.system(f"gsettings set org.cinnamon.desktop.background picture-uri 'file://{fade_color_path}'")
        master_canvas.save(final_path, "JPEG", quality=95)
        log_event(f"Lienzo maestro generado en Cinnamon: {final_path}", origin="DESKTOP", level="INFO", reason="LIBRARY")

        os.system(f"gsettings set org.cinnamon.desktop.background picture-uri 'file://{final_path}'")

        if sl_mode == "sync":
            log_event("Transición Cine aplicada (sync)", origin="CINNAMON", level="INFO", reason="LIBRARY")
        else:
            log_event("Transicion Crossfade aplicada (async)", origin="CINNAMON", level="INFO", reason="LIBRARY")

    except Exception as e:
        log_event(f"Cinnamon no respondió: {e}", origin="CINNAMON", level="ERROR", reason="NOTIFY")

def ensure_keybindings(app_dir):
    """
    Instala el atajo de teclado de WMM si todavía no existe.

    No modifica atajos existentes del usuario.
    Si el atajo de WMM ya está registrado, simplemente termina.
    """
    import re
    import shlex
    import sys

    # ----------------------------------------------------------
    # 1. Comando directo
    # ----------------------------------------------------------
    send_command_path = os.path.join(app_dir, "python", "send_command.py")

    if not os.path.exists(send_command_path):
        log_event(f"Script no encontrado: {send_command_path}", origin="CINNAMON", level="WARN", reason="SETTINGS")
        return

    command = " ".join([
        shlex.quote(sys.executable),
        shlex.quote(send_command_path),
        shlex.quote(json.dumps({"action": "force_rotation"})),
        shlex.quote("HOTKEY"),
    ])

    # Ruta utilizada por versiones anteriores, únicamente para migrar
    # instalaciones existentes sin perder el atajo asignado por el usuario.
    legacy_script_path = os.path.join(app_dir, "wmm_platform", "shell", "cinnamon", "wmm-next.sh")

    # ----------------------------------------------------------
    # 3. Nombre traducido
    # ----------------------------------------------------------
    full_name = f"WMM - { _('Next Background') }"

    schema_main = "org.cinnamon.desktop.keybindings"
    schema_custom = "org.cinnamon.desktop.keybindings.custom-keybinding"
    base_path = "/org/cinnamon/desktop/keybindings/custom-keybindings/"

    settings = Gio.Settings.new(schema_main)

    # Cinnamon utiliza "custom-list"
    custom_list = settings.get_strv("custom-list")

    # ----------------------------------------------------------
    # 4. ¿Ya existe un atajo de WMM?
    # ----------------------------------------------------------
    for item in custom_list:

        if item == "__dummy__":
            continue

        path = f"{base_path}{item}/"

        try:
            ks = Gio.Settings.new_with_path(schema_custom, path)

            existing_command = ks.get_string("command")

            if existing_command == command:
                log_event("Atajo de WMM ya instalado", origin="CINNAMON", level="INFO", reason="SETTINGS")
                return

            if existing_command == legacy_script_path:
                ks.set_string("command", command)
                ks.sync()

                log_event("Atajo de WMM migrado a send_command.py", origin="CINNAMON", level="INFO", reason="SETTINGS")
                return

        except Exception:
            pass

    # ----------------------------------------------------------
    # 5. Buscar primer índice libre
    # ----------------------------------------------------------
    used = []

    pattern = re.compile(r"custom(\d+)")

    for item in custom_list:
        m = pattern.fullmatch(item)
        if m:
            used.append(int(m.group(1)))

    index = 0
    while index in used:
        index += 1

    name = f"custom{index}"
    path = f"{base_path}{name}/"

    # ----------------------------------------------------------
    # 6. Crear el nuevo atajo
    # ----------------------------------------------------------
    ks = Gio.Settings.new_with_path(schema_custom, path)

    ks.set_string("name", full_name)
    ks.set_string("command", command)
    ks.set_strv("binding", [])

    ks.sync()

    # ----------------------------------------------------------
    # 7. Añadirlo a la lista principal
    # ----------------------------------------------------------
    custom_list.append(name)

    settings.set_strv("custom-list", custom_list)
    settings.sync()

    log_event(f"Atajo instalado correctamente ({name})", origin="CINNAMON", level="INFO", reason="SETTINGS")
