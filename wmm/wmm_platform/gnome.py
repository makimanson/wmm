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

def get_positioned_gtk_child_env():
    """Prepara un formulario GTK para respetar posicionamiento absoluto en GNOME."""
    if os.environ.get("XDG_SESSION_TYPE", "").lower() != "wayland":
        return None

    env = os.environ.copy()

    # Bajo GNOME/Wayland, GTK3 no puede posicionar una toplevel mediante
    # coordenadas globales. XWayland conserva esa capacidad cuando está disponible.
    if not env.get("DISPLAY"):
        return None

    env["GDK_BACKEND"] = "x11"
    return env

def get_point_available_area(x, y):
    """
    Devuelve el área útil del monitor que contiene un punto global,
    según la geometría autoritativa de Mutter.
    """
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)

        result = bus.call_sync(
            "org.maki.wmm.Gnome",
            "/org/maki/wmm/Gnome",
            "org.maki.wmm.Gnome",
            "GetPointAvailableArea",
            GLib.Variant("(ii)", (int(x), int(y))),
            GLib.VariantType.new("(s)"),
            Gio.DBusCallFlags.NONE,
            1000, None)

        value = result.unpack()[0]

        if not value:
            return None

        area_x, area_y, width, height = (
            int(part) for part in value.split(","))

        if width <= 0 or height <= 0:
            return None

        return { "x": area_x, "y": area_y, "width": width, "height": height, }

    except Exception as e:
        log_event(
            f"No se pudo obtener el área útil del punto desde GNOME Shell: {e}",
            origin="GNOME", level="WARN", reason="D-BUS")
        return None

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
    """Gestiona la invalidación del fondo según las capacidades de GNOME Shell."""
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

        handled = bool(result.unpack()[0])

        if handled:
            log_event(f"Gestión de caché de fondo GNOME completada: {path}",
                origin="GNOME", level="DEBUG", reason="D-BUS")
        else:
            log_event(f"GNOME Shell no pudo gestionar la caché de fondo: {path}",
                origin="GNOME", level="WARN", reason="D-BUS")

        return handled

    except Exception as e:
        log_event(f"No se pudo gestionar la caché de fondo de GNOME Shell: {e}",
            origin="GNOME", level="WARN", reason="D-BUS")
        return False

def render_master_wallpaper(self, processed_images, monitors_map, config_handler):
    """
    Monta el lienzo a partir de imágenes ya procesadas y lo aplica en GNOME.
    """
    if not processed_images:
        log_event("No hay imágenes procesadas para GNOME",
            origin="GNOME", level="ERROR", reason="LIBRARY")
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
            origin="GNOME", level="INFO", reason="LIBRARY")

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

def _get_next_background_keybinding():
    """
    Devuelve la entrada GSettings que ejecuta Siguiente fondo.

    La identidad pertenece al comando de WMM, no al índice customN:
    GNOME puede asignar cualquier índice y ensure_keybindings() conserva
    el existente durante las migraciones.
    """
    import shlex

    app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    send_command_path = os.path.join(app_dir, "python", "send_command.py")

    schema_main = "org.gnome.settings-daemon.plugins.media-keys"
    schema_custom = "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding"

    settings = Gio.Settings.new(schema_main)

    for path in settings.get_strv("custom-keybindings"):
        try:
            custom = Gio.Settings.new_with_path(schema_custom, path)
            arguments = shlex.split(custom.get_string("command"))

            if len(arguments) != 4:
                continue
            if os.path.abspath(arguments[1]) != send_command_path:
                continue
            if arguments[3] != "HOTKEY":
                continue

            payload = json.loads(arguments[2])
            if payload != {"action": "force_rotation"}:
                continue

            binding_type = custom.get_value("binding").get_type_string()
            if binding_type not in ("s", "as"):
                raise ValueError(
                    f"Tipo de binding GNOME no soportado: {binding_type}")

            return custom, binding_type

        except (GLib.GError, ValueError, json.JSONDecodeError):
            continue

    raise RuntimeError("No se encontró el atajo GNOME de WMM")

def validate_keybinding(shortcut):
    """Valida la representación común según los aceleradores admitidos por GNOME."""
    if shortcut is None:
        return None
    if not isinstance(shortcut, dict):
        raise ValueError(_("This key combination is not supported."))

    key = shortcut.get("key")
    modifiers = shortcut.get("modifiers")

    if not isinstance(key, str) or not key or not isinstance(modifiers, list):
        raise ValueError(_("This key combination is not supported."))

    gi.require_version("Gdk", "3.0")
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gdk, Gtk

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

    # GTK representa las letras mediante el keyval base; Shift pertenece
    # al modificador y no debe quedar codificado también en la tecla.
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
    """Consulta o modifica el binding persistente que GNOME asigna a WMM."""
    if not isinstance(request, dict):
        return {"ok": False, "shortcut": None, "error": "invalid_request"}

    try:
        custom, binding_type = _get_next_background_keybinding()

        gi.require_version("Gdk", "3.0")
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gdk, Gtk

        def read_shortcut():
            if binding_type == "s":
                binding = custom.get_string("binding")
            else:
                bindings = list(custom.get_strv("binding"))
                binding = bindings[0] if bindings else ""

            if not binding:
                return None

            keyval, modifier_mask = Gtk.accelerator_parse(binding)
            if not keyval:
                raise ValueError(f"Binding GNOME no válido: {binding}")

            modifier_masks = (
                ("Control", Gdk.ModifierType.CONTROL_MASK),
                ("Alt", Gdk.ModifierType.MOD1_MASK),
                ("Shift", Gdk.ModifierType.SHIFT_MASK),
                ("Super", Gdk.ModifierType.SUPER_MASK | Gdk.ModifierType.MOD4_MASK),
                ("Meta", Gdk.ModifierType.META_MASK),
                ("Hyper", Gdk.ModifierType.HYPER_MASK),
            )

            key = Gdk.keyval_name(keyval)
            if not key:
                raise ValueError(f"Binding GNOME no válido: {binding}")
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
            shortcut = read_shortcut()
            return {"ok": True, "shortcut": shortcut, "error": 0}

        if action != "set" or "shortcut" not in request:
            return {"ok": False, "shortcut": read_shortcut(),
                    "error": "invalid_request"}

        canonical = validate_keybinding(request["shortcut"])

        if canonical is None:
            binding = ""
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

        if binding_type == "s":
            changed = custom.set_string("binding", binding)
        else:
            changed = custom.set_strv("binding", [binding] if binding else [])

        if not changed:
            return {"ok": False, "shortcut": read_shortcut(),
                    "error": "write_failed"}

        Gio.Settings.sync()

        observed = read_shortcut()
        if observed != canonical:
            return {"ok": False, "shortcut": observed,
                    "error": "verification_failed"}

        return {"ok": True, "shortcut": observed, "error": 0}

    except Exception as error:
        log_event(f"Error gestionando el atajo GNOME: {error}",
            origin="GNOME", level="ERROR", reason="SETTINGS")
        return {"ok": False, "shortcut": None, "error": "request_failed"}

def apply_keybinding(config_handler, shortcut):
    """Aplica y confirma Siguiente fondo mediante la autoridad GSettings de GNOME."""
    canonical = validate_keybinding(shortcut)

    previous = request_keybindings(
        config_handler.data_dir, {"action": "get"})
    if not previous["ok"]:
        raise RuntimeError(
            f"No se pudo consultar el atajo GNOME: {previous}")

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

        raise ValueError(_("Could not apply the keyboard shortcut."))

    log_event(f"Atajo GNOME guardado: {canonical}",
        origin="GNOME", level="INFO", reason="SETTINGS")
    return canonical

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
