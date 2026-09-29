#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

"""
WMM - Wallpaper Multi-Monitor Manager

xfce.py - Módulo de plataforma para XFCE (Linux).
=================================================
Contiene solo las implementaciones específicas de este entorno.
"""

import os
import subprocess
import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Wnck", "3.0")
from gi.repository import Gdk, Wnck

from PIL import Image
from debug_logger import log_event

def get_install_path(data_base, app_domain):
    """Devuelve la ruta de instalación para XFCE."""
    return os.path.join(data_base, app_domain)

def _force_desktop_settings(primary_connector):
    """
    Fuerza en XFCE los ajustes necesarios para que WMM controle el fondo:
      - image-style = 6 (Spanning screens)
      - backdrop-cycle-enable = false
    """
    if not primary_connector:
        log_event("No se pudo determinar el monitor primario para XFCE",
                  origin="XFCE", level="ERROR", reason="HARDWARE")
        return False

    base_path = f"/backdrop/screen0/monitor{primary_connector}/workspace0"
    required = (
        (f"{base_path}/image-style", "int", "6"),
        (f"{base_path}/backdrop-cycle-enable", "bool", "false"),
    )

    for path, value_type, value in required:
        result = subprocess.run(
            ["xfconf-query", "-c", "xfce4-desktop", "-p", path, "-s", value],
            capture_output=True, text=True, check=False)

        if result.returncode != 0:
            result = subprocess.run(
                ["xfconf-query", "-c", "xfce4-desktop", "-p", path,
                 "-n", "-t", value_type, "-s", value],
                capture_output=True, text=True, check=False)

        if result.returncode != 0:
            log_event(f"No se pudo forzar el ajuste XFCE {path}: {result.stderr.strip()}",
                      origin="XFCE", level="ERROR", reason="SETTINGS")
            return False

    log_event(f"Ajustes XFCE forzados en el primario {primary_connector}: Spanning screens, slideshow desactivado",
              origin="XFCE", level="INFO", reason="SETTINGS")
    return True

def render_master_wallpaper(self, processed_images, monitors_map, config_handler):
    """
    Monta el lienzo maestro a partir de las imágenes ya procesadas.
    """
    if not processed_images:
        log_event("No hay imágenes procesadas para XFCE",
                  origin="XFCE", level="ERROR", reason="LIBRARY")
        return False

    # Calcular las dimensiones del escritorio virtual
    canvas_w = max(mon["x"] + mon["width"] for mon in monitors_map.values())
    canvas_h = max(mon["y"] + mon["height"] for mon in monitors_map.values())

    # Crear el lienzo maestro
    master_canvas = Image.new("RGB", (canvas_w, canvas_h), (0, 0, 0))

    # Colocar cada imagen procesada en su posición física
    for m_hash, img in processed_images.items():
        if m_hash not in monitors_map:
            continue

        mon = monitors_map[m_hash]
        master_canvas.paste(img, (mon["x"], mon["y"]))

    primary_connector = next(
        (mon.get("connector") for mon in monitors_map.values() if mon.get("primary")),
        None)

    # Durante una reconfiguración XRandR puede retirar temporalmente el primary
    # antes de estabilizar la nueva topología. Si sólo queda un monitor activo,
    # ese monitor es necesariamente el destino válido para XFCE.
    if not primary_connector and len(monitors_map) == 1:
        primary_connector = next(iter(monitors_map.values())).get("connector")

    if not primary_connector:
        log_event("No se pudo determinar el monitor primario de XFCE",
                  origin="XFCE", level="ERROR", reason="HARDWARE")
        return False

    master_path = os.path.join(config_handler.cache_dir, "wallpaper_master.jpg")

    self.set_wallpaper(master_canvas, master_path, config_handler, primary_connector)

    return True

def set_wallpaper(master_canvas, master_path, config_handler, primary_connector):
    """
    Guarda y aplica el wallpaper maestro en XFCE usando doble buffer.

    XFCE 4.20.1 no detecta de forma fiable que el contenido del mismo archivo
    haya cambiado. Alternar entre _0 y _1 garantiza que last-image cambia
    realmente en cada rotación.
    """
    try:

        if not _force_desktop_settings(primary_connector):
            return False

        root, ext = os.path.splitext(master_path)
        ext = ext or ".jpg"

        path_0 = f"{root}_0{ext}"
        path_1 = f"{root}_1{ext}"

        last_image_path = f"/backdrop/screen0/monitor{primary_connector}/workspace0/last-image"

        current = subprocess.run(
            ["xfconf-query", "-c", "xfce4-desktop", "-p", last_image_path],
            capture_output=True, text=True, check=False
        )

        current_path = current.stdout.strip() if current.returncode == 0 else ""
        next_path = path_1 if current_path == path_0 else path_0

        master_canvas.save(next_path, "JPEG", quality=95)
        log_event(f"Lienzo maestro generado en XFCE: {next_path}",
                  origin="XFCE", level="INFO", reason="LIBRARY")

        result = subprocess.run(
            ["xfconf-query", "-c", "xfce4-desktop", "-p", last_image_path, "-s", next_path],
            capture_output=True, text=True, check=False
        )

        if result.returncode != 0:
            result = subprocess.run(
                ["xfconf-query", "-c", "xfce4-desktop", "-p", last_image_path,
                 "-n", "-t", "string", "-s", next_path],
                capture_output=True, text=True, check=False
            )

        if result.returncode != 0:
            log_event(f"No se pudo aplicar el wallpaper en XFCE: {result.stderr.strip()}",
                      origin="XFCE", level="ERROR", reason="SETTINGS")
            return False

        log_event(
            f"Wallpaper XFCE aplicado en el primario {primary_connector}: {next_path}",
            origin="XFCE", level="INFO", reason="SETTINGS"
        )
        return True

    except Exception as e:
        log_event(f"No se pudo generar/aplicar el wallpaper maestro en XFCE: {e}",
                  origin="XFCE", level="ERROR", reason="LIBRARY")
        return False

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
                  origin="XFCE", level="WARN", reason="WINDOW")
        return None


def ensure_keybindings(app_dir):
    """
    Registra el atajo de rotación de WMM en XFCE si todavía no existe.

    Se crea con "___" como placeholder para que sea el usuario quien
    asigne posteriormente la combinación de teclas desde XFCE.
    """
    channel = "xfce4-keyboard-shortcuts"
    base_path = "/commands/custom"
    shortcut_path = f"{base_path}/___"
    command = "wmm-next.sh"

    try:
        result = subprocess.run(
            ["xfconf-query", "-c", channel, "-p", base_path, "-lv"],
            capture_output=True, text=True, check=False)

        # Si el usuario ya asignó una combinación a WMM, la propiedad habrá
        # cambiado de nombre. Buscar por comando evita recrear "___" y duplicarla.
        for line in result.stdout.splitlines():
            parts = line.split(None, 1)
            if len(parts) == 2 and parts[1].strip() == command:
                log_event("Atajo de WMM ya instalado", origin="XFCE", level="INFO", reason="SETTINGS")
                return

        result = subprocess.run(
            ["xfconf-query", "-c", channel, "-p", shortcut_path,
             "-n", "-t", "string", "-s", command],
            capture_output=True, text=True, check=False)

        if result.returncode != 0:
            log_event(f"No se pudo registrar el atajo de WMM: {result.stderr.strip()}",
                      origin="XFCE", level="ERROR", reason="SETTINGS")
            return

        log_event("Atajo de WMM instalado correctamente (___)",
                  origin="XFCE", level="INFO", reason="SETTINGS")

    except OSError as error:
        log_event(f"No se pudo ejecutar xfconf-query: {error}",
                  origin="XFCE", level="ERROR", reason="SETTINGS")
