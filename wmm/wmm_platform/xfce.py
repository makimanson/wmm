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
            capture_output=True, text=True, check=False)

        current_path = current.stdout.strip() if current.returncode == 0 else ""
        next_path = path_1 if current_path == path_0 else path_0

        master_canvas.save(next_path, "JPEG", quality=95)
        log_event(f"Lienzo maestro generado en XFCE: {next_path}",
                  origin="XFCE", level="INFO", reason="LIBRARY")

        result = subprocess.run(
            ["xfconf-query", "-c", "xfce4-desktop", "-p", last_image_path, "-s", next_path],
            capture_output=True, text=True, check=False)

        if result.returncode != 0:
            result = subprocess.run(
                ["xfconf-query", "-c", "xfce4-desktop", "-p", last_image_path,
                 "-n", "-t", "string", "-s", next_path],
                capture_output=True, text=True, check=False)

        if result.returncode != 0:
            log_event(f"No se pudo aplicar el wallpaper en XFCE: {result.stderr.strip()}",
                      origin="XFCE", level="ERROR", reason="SETTINGS")
            return False

        log_event(f"Wallpaper XFCE aplicado en el primario {primary_connector}: {next_path}",
            origin="XFCE", level="INFO", reason="SETTINGS")
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

def get_point_available_area(x, y):
    """Delimita el área útil mediante GDK y los paneles reales de XFCE."""
    display = Gdk.Display.get_default()
    if display is None:
        return None

    monitor = display.get_monitor_at_point(int(x), int(y))
    if monitor is None:
        return None

    geometry = monitor.get_geometry()
    area = monitor.get_workarea()

    left, top = area.x, area.y
    right = area.x + area.width
    bottom = area.y + area.height

    screen = Wnck.Screen.get_default()

    if screen is not None:
        screen.force_update()

        for panel in screen.get_windows():
            if panel.get_window_type() != Wnck.WindowType.DOCK:
                continue

            px, py, pw, ph = panel.get_geometry()

            # Ignorar paneles de otros monitores.
            if (px + pw <= geometry.x or px >= geometry.x + geometry.width
                    or py + ph <= geometry.y or py >= geometry.y + geometry.height):
                continue

            if pw >= ph and px <= x < px + pw:
                # Panel horizontal: reservar el borde superior o inferior.
                top_distance = abs(py - geometry.y)
                bottom_distance = abs(geometry.y + geometry.height - py - ph)

                if top_distance <= bottom_distance:
                    top = max(top, py + ph)
                else:
                    bottom = min(bottom, py)

            elif ph > pw and py <= y < py + ph:
                # Panel vertical: reservar el borde izquierdo o derecho.
                left_distance = abs(px - geometry.x)
                right_distance = abs(geometry.x + geometry.width - px - pw)

                if left_distance <= right_distance:
                    left = max(left, px + pw)
                else:
                    right = min(right, px)

    if right <= left or bottom <= top:
        return None

    return { "x": left, "y": top, "width": right - left, "height": bottom - top, }

def _get_next_background_keybinding():
    """Devuelve la propiedad Xfconf que ejecuta Next Background en XFCE."""
    channel = "xfce4-keyboard-shortcuts"
    base_path = "/commands/custom"
    command = "wmm-next.sh"

    result = subprocess.run(
        ["xfconf-query", "-c", channel, "-p", base_path, "-lv"],
        capture_output=True, text=True, check=False)

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip() or "No se pudo consultar Xfconf")

    prefix = base_path + "/"

    for line in result.stdout.splitlines():
        parts = line.split(None, 1)

        if len(parts) != 2 or parts[1].strip() != command:
            continue

        property_path = parts[0].strip()

        if not property_path.startswith(prefix):
            continue

        return property_path, property_path[len(prefix):]

    raise RuntimeError("No se encontró el atajo XFCE de WMM")


def validate_keybinding(shortcut):
    """Valida la representación común según los aceleradores admitidos por XFCE."""
    from i18n import _

    if shortcut is None:
        return None

    if not isinstance(shortcut, dict):
        raise ValueError(_("This key combination is not supported."))

    key = shortcut.get("key")
    modifiers = shortcut.get("modifiers")

    if not isinstance(key, str) or not key or not isinstance(modifiers, list):
        raise ValueError(_("This key combination is not supported."))

    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk

    modifier_masks = {
        "Control": Gdk.ModifierType.CONTROL_MASK,
        "Alt": Gdk.ModifierType.MOD1_MASK,
        "Shift": Gdk.ModifierType.SHIFT_MASK,
        "Super": Gdk.ModifierType.SUPER_MASK,
        "Meta": Gdk.ModifierType.META_MASK,
        "Hyper": Gdk.ModifierType.HYPER_MASK,
    }
    modifier_order = tuple(modifier_masks)

    if any(
            not isinstance(name, str) or name not in modifier_masks
            for name in modifiers):
        raise ValueError(_("This key combination is not supported."))

    canonical_modifiers = [
        name for name in modifier_order if name in modifiers
    ]

    keyval = Gdk.keyval_from_name(key)

    if not keyval:
        raise ValueError(_("This key combination is not supported."))

    if len(key) == 1 and key.isalpha():
        keyval = Gdk.keyval_to_lower(keyval)

    modifier_mask = Gdk.ModifierType(0)

    for name in canonical_modifiers:
        modifier_mask |= modifier_masks[name]

    if not Gtk.accelerator_valid(keyval, modifier_mask):
        raise ValueError(_("This key combination is not supported."))

    canonical_key = Gdk.keyval_name(keyval)

    if not canonical_key:
        raise ValueError(_("This key combination is not supported."))

    if len(canonical_key) == 1 and canonical_key.isascii():
        canonical_key = canonical_key.upper()

    return {
        "key": canonical_key,
        "modifiers": canonical_modifiers,
    }


def request_keybindings(data_dir, request):
    """Consulta o modifica el atajo persistente que XFCE asigna a WMM."""
    if not isinstance(request, dict):
        return {"ok": False, "shortcut": None, "error": "invalid_request"}

    channel = "xfce4-keyboard-shortcuts"
    base_path = "/commands/custom"
    command = "wmm-next.sh"

    try:
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk

        def read_shortcut():
            _property_path, binding = _get_next_background_keybinding()

            if binding == "___":
                return None

            keyval, modifier_mask = Gtk.accelerator_parse(binding)

            if not keyval:
                raise ValueError(f"Binding XFCE no válido: {binding}")

            modifier_masks = (
                ("Control", Gdk.ModifierType.CONTROL_MASK),
                ("Alt", Gdk.ModifierType.MOD1_MASK),
                ("Shift", Gdk.ModifierType.SHIFT_MASK),
                ("Super", Gdk.ModifierType.SUPER_MASK |
                    Gdk.ModifierType.MOD4_MASK),
                ("Meta", Gdk.ModifierType.META_MASK),
                ("Hyper", Gdk.ModifierType.HYPER_MASK),
            )

            key = Gdk.keyval_name(keyval)

            if not key:
                raise ValueError(f"Binding XFCE no válido: {binding}")

            if len(key) == 1 and key.isascii():
                key = key.upper()

            return validate_keybinding({
                "key": key,
                "modifiers": [
                    name for name, mask in modifier_masks
                    if modifier_mask & mask
                ],
            })

        action = request.get("action")

        if action == "get":
            return {
                "ok": True,
                "shortcut": read_shortcut(),
                "error": 0,
            }

        if action != "set" or "shortcut" not in request:
            return {
                "ok": False,
                "shortcut": read_shortcut(),
                "error": "invalid_request",
            }

        canonical = validate_keybinding(request["shortcut"])

        if canonical is None:
            binding = "___"
        else:
            modifier_masks = {
                "Control": Gdk.ModifierType.CONTROL_MASK,
                "Alt": Gdk.ModifierType.MOD1_MASK,
                "Shift": Gdk.ModifierType.SHIFT_MASK,
                "Super": Gdk.ModifierType.SUPER_MASK,
                "Meta": Gdk.ModifierType.META_MASK,
                "Hyper": Gdk.ModifierType.HYPER_MASK,
            }

            keyval = Gdk.keyval_from_name(canonical["key"])

            if len(canonical["key"]) == 1 and canonical["key"].isalpha():
                keyval = Gdk.keyval_to_lower(keyval)

            modifier_mask = Gdk.ModifierType(0)

            for name in canonical["modifiers"]:
                modifier_mask |= modifier_masks[name]

            binding = Gtk.accelerator_name(keyval, modifier_mask)

        current_path, current_binding = _get_next_background_keybinding()
        target_path = f"{base_path}/{binding}"

        if target_path == current_path:
            return {
                "ok": True,
                "shortcut": read_shortcut(),
                "error": 0,
            }

        # Una propiedad custom ya existente representa un atajo ocupado.
        occupied = subprocess.run(
            ["xfconf-query", "-c", channel, "-p", target_path],
            capture_output=True, text=True, check=False)

        if occupied.returncode == 0:
            return {
                "ok": False,
                "shortcut": read_shortcut(),
                "error": "in_use",
            }

        # Crear primero el nuevo registro conserva el anterior como autoridad
        # hasta que XFCE haya aceptado realmente la nueva propiedad.
        created = subprocess.run(
            ["xfconf-query", "-c", channel, "-p", target_path,
             "-n", "-t", "string", "-s", command],
            capture_output=True, text=True, check=False)

        if created.returncode != 0:
            return {
                "ok": False,
                "shortcut": read_shortcut(),
                "error": "write_failed",
            }

        removed = subprocess.run(
            ["xfconf-query", "-c", channel, "-p", current_path, "-r"],
            capture_output=True, text=True, check=False)

        if removed.returncode != 0:
            subprocess.run(
                ["xfconf-query", "-c", channel, "-p", target_path, "-r"],
                capture_output=True, text=True, check=False)

            return {
                "ok": False,
                "shortcut": read_shortcut(),
                "error": "write_failed",
            }

        observed = read_shortcut()

        if observed != canonical:
            # La verificación pertenece a Xfconf, no a nuestra intención.
            # Restaurar el registro anterior antes de anunciar el fallo.
            subprocess.run(
                ["xfconf-query", "-c", channel, "-p", target_path, "-r"],
                capture_output=True, text=True, check=False)

            subprocess.run(
                ["xfconf-query", "-c", channel,
                 "-p", f"{base_path}/{current_binding}",
                 "-n", "-t", "string", "-s", command],
                capture_output=True, text=True, check=False)

            return {
                "ok": False,
                "shortcut": observed,
                "error": "verification_failed",
            }

        return {
            "ok": True,
            "shortcut": observed,
            "error": 0,
        }

    except Exception as error:
        log_event(f"Error gestionando el atajo XFCE: {error}",
            origin="XFCE", level="ERROR", reason="SETTINGS")

        return {
            "ok": False,
            "shortcut": None,
            "error": "request_failed",
        }


def apply_keybinding(config_handler, shortcut):
    """Aplica y confirma Next Background mediante Xfconf."""
    from i18n import _

    canonical = validate_keybinding(shortcut)

    previous = request_keybindings(
        config_handler.data_dir, {"action": "get"})

    if not previous["ok"]:
        raise RuntimeError(
            f"No se pudo consultar el atajo XFCE: {previous}")

    result = request_keybindings(
        config_handler.data_dir,
        {"action": "set", "shortcut": canonical})

    if not result["ok"] or result["shortcut"] != canonical:
        restored = request_keybindings(
            config_handler.data_dir,
            {"action": "set", "shortcut": previous["shortcut"]})

        if not restored["ok"] or restored["shortcut"] != previous["shortcut"]:
            raise ValueError(
                _("Could not restore the previous shortcut settings."))

        if result.get("error") == "in_use":
            raise ValueError(
                _("This key combination is already in use."))

        raise ValueError(_("Could not apply the keyboard shortcut."))

    log_event(f"Atajo XFCE guardado: {canonical}",
        origin="XFCE", level="INFO", reason="SETTINGS")

    return canonical

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