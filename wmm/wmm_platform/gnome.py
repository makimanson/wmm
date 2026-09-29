#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

"""
WMM - Wallpaper Multi-Monitor Manager

gnome.py - Módulo de plataforma para GNOME (Linux).
==========================================================
Contiene solo las implementaciones específicas de este entorno.
"""
import os
import subprocess
import time
import json
import gi

gi.require_version('Gio', '2.0')

from gi.repository import Gio, GLib
from PIL import Image
from debug_logger import log_event
from i18n import _

def get_install_path(data_base, app_domain):
    """Devuelve la ruta del frontend GNOME."""
    return os.path.join(data_base, 'gnome-shell', 'extensions', app_domain)

def get_window_available_area(pid):
    """
    Devuelve el área útil del monitor que contiene la ventana identificada
    por PID, según la workarea calculada por Mutter.

    GNOME Shell expone esta información a WMM mediante la interfaz D-Bus
    mínima implementada por extension.js, ya que Meta.Window solo está
    disponible dentro del contexto vivo del compositor.

    Returns:
        dict: {"x": int, "y": int, "width": int, "height": int}
        None: si Mutter no puede resolver la ventana o la consulta falla.
    """
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)

        result = bus.call_sync(
            "org.maki.wmm.Gnome",
            "/org/maki/wmm/Gnome",
            "org.maki.wmm.Gnome",
            "GetWindowAvailableArea",
            GLib.Variant("(u)", (int(pid),)),
            GLib.VariantType.new("(s)"),
            Gio.DBusCallFlags.NONE,
            1000, None)

        value = result.unpack()[0]

        if not value:
            log_event(f"Mutter no encontró una ventana para PID {pid}",
                origin="GNOME", level="DEBUG", reason="D-BUS")
            return None

        x, y, width, height = (int(part) for part in value.split(","))

        if width <= 0 or height <= 0:
            return None

        area = { "x": x, "y": y, "width": width, "height": height,  }

        log_event(f"Área útil GNOME obtenida para PID {pid}: {area}",
            origin="GNOME", level="DEBUG", reason="D-BUS")
        return area

    except Exception as e:
        log_event(f"No se pudo obtener el área útil desde GNOME Shell: {e}",
            origin="GNOME", level="WARN", reason="D-BUS")
        return None

def _purge_background_cache(path):
    """Purga de GNOME Shell la imagen de fondo asociada a la ruta indicada."""
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)

        result = bus.call_sync(
            "org.maki.wmm.Gnome",
            "/org/maki/wmm/Gnome",
            "org.maki.wmm.Gnome",
            "PurgeBackgroundCache",
            GLib.Variant("(s)", (path,)),
            GLib.VariantType.new("(b)"),
            Gio.DBusCallFlags.NONE,
            1000, None)

        purged = bool(result.unpack()[0])

        if purged:
            log_event(f"Caché de fondo GNOME purgada: {path}",
                origin="GNOME", level="DEBUG", reason="D-BUS")
        else:
            log_event(f"GNOME Shell no pudo purgar la caché de fondo: {path}",
                origin="GNOME", level="WARN", reason="D-BUS")

        return purged

    except Exception as e:
        log_event(f"No se pudo purgar la caché de fondo de GNOME Shell: {e}",
            origin="GNOME", level="WARN", reason="D-BUS")
        return False

def render_master_wallpaper(self, processed_images, monitors_map, config_handler):
    """
    Monta el lienzo a partir de imágenes ya procesadas y lo aplica en GNOME.
    """
    if not processed_images:
        log_event("No hay imágenes procesadas para GNOME",
            origin="DESKTOP", level="ERROR", reason="LIBRARY")
        return False

    # Mutter normaliza el layout lógico para que su bounding box comience
    # en (0, 0). Por ello no deben restarse min_x/min_y aquí: x + width
    # e y + height expresan directamente los límites reales del canvas.
    # WMM asume actualmente geometría 1:1; el escalado del escritorio
    # no forma parte del modelo soportado.
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
    correctamente en GNOME:
      - picture-options     = 'spanned'  (no deformar el lienzo)
      - color-shading-type  = 'solid'    (evitar mezclas de color)
    """
    try:
        subprocess.run(
            ["gsettings", "set", "org.gnome.desktop.background",
                "picture-options", "spanned"], check=False)
        log_event("Forzando picture-options a 'spanned'",
            origin="GNOME", level="DEBUG", reason="HARDWARE")

        subprocess.run(
            ["gsettings", "set", "org.gnome.desktop.background",
                "color-shading-type", "solid"], check=False)
        log_event("Forzando color-shading-type a 'solid'",
            origin="GNOME", level="DEBUG", reason="HARDWARE")

        issues = []

        result = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.background", "picture-options"],
            capture_output=True, text=True)
        if result.stdout.strip().lower().replace("'", "") != "spanned":
            issues.append("Picture aspect")

        result = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.background", "color-shading-type"],
            capture_output=True, text=True)
        if result.stdout.strip().lower().replace("'", "") != "solid":
            issues.append("Background color type")

        if issues:
            log_event(f"No se pudieron forzar algunos ajustes: {', '.join(issues)}. Notificando al usuario.",
                origin="GNOME", level="WARN", reason="HARDWARE")
            config_handler._send_notification(
                reason="WMM: " + _("Configuration issue"),
                detail_msg=_("For WMM to function correctly, please check the following settings in 'Settings > Background':")
                + "\n" + "\n".join(f"• {issue}" for issue in issues),
                level="warn")
        else:
            log_event("Todos los ajustes del sistema forzados correctamente",
                origin="GNOME", level="DEBUG", reason="HARDWARE")

    except Exception as e:
        log_event(f"Error al forzar ajustes de GNOME: {e}",
            origin="GNOME", level="ERROR", reason="NOTIFY")

def set_wallpaper(master_canvas, path, config_handler):
    """Aplica el fondo de pantalla y gestiona la transición en GNOME."""
    _force_desktop_settings(config_handler)

    try:
        settings = config_handler.load_json("settings").get("global", {})
        sl_mode = settings.get("slideshow_mode", "sync")

        result = subprocess.run(["gsettings", "list-keys", "org.gnome.desktop.background"],
            capture_output=True, text=True, check=False)
        has_dark_uri = "picture-uri-dark" in result.stdout

        if sl_mode == "sync":
            fade_path = os.path.join(config_handler.cache_dir, "fade_black.png")
            if not os.path.exists(fade_path):
                Image.new("RGB", (1, 1), (0, 0, 0)).save(fade_path)

            subprocess.run(["gsettings", "set", "org.gnome.desktop.background",
                "picture-uri", f"file://{fade_path}"], check=False)

            if has_dark_uri:
                subprocess.run(["gsettings", "set", "org.gnome.desktop.background",
                    "picture-uri-dark", f"file://{fade_path}"], check=False)

            # Mantener el negro el mismo intervalo de transición para equilibrar
            # visualmente el fade-out de la imagen saliente y el fade-in de la entrante.
            time.sleep(1.2)

        master_canvas.save(path, "JPEG", quality=95)
        log_event(f"Lienzo maestro generado en GNOME: {path}",
            origin="DESKTOP", level="INFO", reason="LIBRARY")

        _purge_background_cache(path)

        subprocess.run(["gsettings", "set", "org.gnome.desktop.background",
            "picture-uri", f"file://{path}"], check=False)

        if has_dark_uri:
            subprocess.run(["gsettings", "set", "org.gnome.desktop.background",
                "picture-uri-dark", f"file://{path}"], check=False)

        if sl_mode == "sync":
            log_event("Transición Fade out/in aplicada (sync)",
                origin="GNOME", level="INFO", reason="LIBRARY")
        else:
            log_event("Transición Crossfade aplicada (async)",
                origin="GNOME", level="INFO", reason="LIBRARY")

    except Exception as e:
        log_event(f"GNOME no respondió: {e}",
            origin="GNOME", level="ERROR", reason="NOTIFY")

def ensure_keybindings(app_dir):
    """
    Crea el atajo "WMM - Next Background" si aún no existe.
    app_dir: ruta del core común de WMM.
    """
    import shlex
    import sys
    # ----------------------------------------------------------
    # 1. Construir ruta del script
    # ----------------------------------------------------------
    send_command_path = os.path.join(app_dir, "python", "send_command.py")

    if not os.path.exists(send_command_path):
        log_event(f"Script no encontrado: {send_command_path}",
            origin="GNOME", level="WARN", reason="SETTINGS")
        return

    command = " ".join([
        shlex.quote(sys.executable),
        shlex.quote(send_command_path),
        shlex.quote(json.dumps({"action": "force_rotation"})),
        shlex.quote("HOTKEY"), ])

    # GNOME <= 1.4.x alojaba todo WMM dentro del directorio de la extensión.
    # Reconocer tanto el wrapper histórico como el send_command.py directo:
    # este último cambia de ruta al migrar el core común en v1.5.0.
    data_base = (os.environ.get("XDG_DATA_HOME")
        or os.path.expanduser("~/.local/share"))
    legacy_app_dir = get_install_path(data_base, "wmm@maki")
    legacy_script_path = os.path.join(
        legacy_app_dir, "wmm_platform", "shell", "gnome", "wmm-next.sh")
    legacy_send_command_path = os.path.join(
        legacy_app_dir, "python", "send_command.py")
    legacy_command = " ".join([
        shlex.quote(sys.executable),
        shlex.quote(legacy_send_command_path),
        shlex.quote(json.dumps({"action": "force_rotation"})),
        shlex.quote("HOTKEY"), ])

    # ----------------------------------------------------------
    # 3. Nombre traducido
    # ----------------------------------------------------------
    name = _("Next Background")
    full_name = f"WMM - {name}"

    # ----------------------------------------------------------
    # 4. Esquemas GSettings
    # ----------------------------------------------------------
    schema_main = "org.gnome.settings-daemon.plugins.media-keys"
    schema_custom = "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding"
    base_path = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/"
    try:
        settings = Gio.Settings.new(schema_main)
    except GLib.GError as e:
        log_event(f"Error al acceder al esquema '{schema_main}': {e}",
            origin="GNOME", level="ERROR", reason="SETTINGS")
        return

    # ----------------------------------------------------------
    # 5. Obtener lista actual
    # ----------------------------------------------------------
    current_list = settings.get_strv("custom-keybindings")

    # ----------------------------------------------------------
    # 6. Buscar atajo actual y variantes legacy
    # ----------------------------------------------------------
    current_entries = []
    legacy_entry = None

    for path in current_list:
        try:
            existing = Gio.Settings.new_with_path(schema_custom, path)
            existing_command = existing.get_string("command")

            if existing_command == command:
                current_entries.append((path, existing))

            elif existing_command in (legacy_script_path, legacy_command):
                legacy_entry = legacy_entry or (path, existing)

        except GLib.GError:
            continue

    if legacy_entry is not None:
        legacy_path, legacy_settings = legacy_entry

        # El atajo legacy conserva la combinación elegida por el usuario.
        # Si un arranque previo de v1.5.0 creó además una entrada nueva,
        # retirar sólo esa copia generada y mantener como autoridad la legacy.
        legacy_settings.set_string("command", command)
        legacy_settings.set_string("name", full_name)

        if current_entries:
            duplicate_paths = {path for path, _settings in current_entries}
            current_list = [
                path for path in current_list
                if path not in duplicate_paths
            ]
            settings.set_strv("custom-keybindings", current_list)

            for _path, duplicate in current_entries:
                duplicate.reset("name")
                duplicate.reset("command")
                duplicate.reset("binding")

        Gio.Settings.sync()
        log_event("Atajo de WMM migrado a la topología común",
            origin="GNOME", level="INFO", reason="SETTINGS")
        return

    if current_entries:
        _path, existing = current_entries[0]

        # El nombre no identifica el atajo, pero sí debe reflejar la etiqueta
        # publicada actualmente sin crear una entrada nueva por ese cambio.
        if existing.get_string("name") != full_name:
            existing.set_string("name", full_name)
            Gio.Settings.sync()

        log_event("Atajo de WMM ya instalado",
            origin="GNOME", level="INFO", reason="SETTINGS")
        return

    # ----------------------------------------------------------
    # 7. Calcular siguiente índice libre
    # ----------------------------------------------------------
    import re

    pattern = re.compile(rf"{re.escape(base_path)}custom(\d+)/")

    indices = [int(match.group(1))
        for path in current_list
        for match in [pattern.search(path)]
        if match]
    next_index = max(indices) + 1 if indices else 0
    new_path = f"{base_path}custom{next_index}/"

    # ----------------------------------------------------------
    # 8. Crear nuevo atajo
    # ----------------------------------------------------------
    try:
        custom = Gio.Settings.new_with_path(schema_custom, new_path)

        # El tipo de "binding" varía entre versiones de GNOME:
        # GNOME 46 usa string ("s"), mientras que versiones posteriores
        # pueden usar una lista de strings ("as").
        schema_source = Gio.SettingsSchemaSource.get_default()
        custom_schema = (schema_source.lookup(schema_custom, True)
            if schema_source else None)

        if not custom_schema:
            log_event(f"No se pudo consultar el esquema '{schema_custom}'",
                origin="GNOME", level="ERROR", reason="SETTINGS")
            return
        binding_type = custom_schema.get_key("binding").get_value_type().dup_string()
        if binding_type == "s":
            custom.set_string("binding", "")
        elif binding_type == "as":
            custom.set_strv("binding", [])
        else:
            log_event(f"Tipo de binding GNOME no soportado: {binding_type}",
                origin="GNOME", level="ERROR", reason="SETTINGS")
            return

        custom.set_string("command", command)
        custom.set_string("name", full_name)

        # Esta clave no existe en todas las versiones de GNOME.
        if custom_schema.has_key("enable-in-lockscreen"):
            custom.set_boolean("enable-in-lockscreen", False)

        custom.sync()

    except GLib.GError as e:
        log_event(f"Error al escribir el atajo en {new_path}: {e}",
            origin="GNOME", level="ERROR", reason="SETTINGS")
        return

    # ----------------------------------------------------------
    # 9. Añadir a la lista principal
    # ----------------------------------------------------------
    current_list.append(new_path)
    settings.set_strv("custom-keybindings", current_list)
    settings.sync()
    log_event(f"Atajo GNOME creado: {full_name}",
        origin="GNOME", level="INFO", reason="SETTINGS")
