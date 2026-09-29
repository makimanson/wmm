#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

"""
WMM - Wallpaper Multi-Monitor Manager

mate-launcher.py - MATE Panel launcher helper
==============================================
Garantiza que WMM tenga una instancia registrada en MATE Panel.

El helper no inicia directamente mate-applet.py ni el engine:
    1. Localiza la barra de tareas a partir de un applet de sistema.
    2. Registra WMMAppletFactory::WMMApplet si todavía no existe.
    3. MATE Panel detecta el nuevo objeto y activa la factoría por D-Bus.
"""
import sys
import json
import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

panel_schema = "org.mate.panel"
object_schema = "org.mate.panel.object"
object_base_path = "/org/mate/panel/objects/"

wmm_iid = "WMMAppletFactory::WMMApplet"
wmm_object_base = "wmm-applet"
wmm_applet_bus_name = "org.maki.wmm.MateApplet"

# Preferencia para identificar la barra de tareas.
# El reloj es la referencia principal; los demás son fallback de sistema.
taskbar_applets = (
    "ClockAppletFactory::ClockApplet",
    "NotificationAreaAppletFactory::NotificationArea",
    "WnckletFactory::WindowListApplet", )

def _object_settings(object_id):
    return Gio.Settings.new_with_path(object_schema, f"{object_base_path}{object_id}/")

def _find_wmm_objects(object_ids):
    """Devuelve todos los object-id registrados como applet WMM."""
    wmm_ids = []

    for object_id in object_ids:
        settings = _object_settings(object_id)

        if settings.get_string("object-type") == "applet" and settings.get_string("applet-iid") == wmm_iid:
            wmm_ids.append(object_id)

    return wmm_ids

def _applet_is_alive():
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    reply = bus.call_sync(
        "org.freedesktop.DBus",
        "/org/freedesktop/DBus",
        "org.freedesktop.DBus",
        "NameHasOwner",
        GLib.Variant("(s)", (wmm_applet_bus_name,)),
        GLib.VariantType.new("(b)"),
        Gio.DBusCallFlags.NONE,
        1000, None)

    return bool(reply.unpack()[0])

def _get_active_object_id():
    """Consulta al frontend MATE qué object-id corresponde a la instancia activa."""
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    reply = bus.call_sync(
        wmm_applet_bus_name,
        "/org/maki/wmm/MateApplet",
        "org.maki.wmm.MateApplet",
        "GetObjectId", None,
        GLib.VariantType.new("(s)"),
        Gio.DBusCallFlags.NO_AUTO_START,
        1000, None)

    return reply.unpack()[0] or None

def _find_taskbar(object_ids):
    objects = {}

    for object_id in object_ids:
        settings = _object_settings(object_id)
        objects[object_id] = settings

    for preferred_iid in taskbar_applets:
        for object_id, settings in objects.items():
            if settings.get_string("object-type") != "applet":
                continue
            if settings.get_string("applet-iid") == preferred_iid:
                return settings.get_string("toplevel-id"), settings.get_boolean("panel-right-stick")

    return None, None

def _next_position(object_ids, toplevel_id, right_stick):
    positions = []
    for object_id in object_ids:
        settings = _object_settings(object_id)
        if settings.get_string("toplevel-id") != toplevel_id:
            continue
        if settings.get_boolean("panel-right-stick") != right_stick:
            continue
        positions.append(settings.get_int("position"))
    return max(positions, default=-1) + 1

def _object_id_is_used(object_id, object_ids):
    if object_id in object_ids:
        return True

    settings = _object_settings(object_id)
    return any(
        settings.get_user_value(key) is not None
        for key in ("object-type", "applet-iid", "toplevel-id"))

def _get_free_object_id(object_ids):
    if not _object_id_is_used(wmm_object_base, object_ids):
        return wmm_object_base

    index = 1
    while _object_id_is_used(f"{wmm_object_base}-{index}", object_ids):
        index += 1

    return f"{wmm_object_base}-{index}"

def _set_value(success, key):
    if not success:
        raise RuntimeError(f"No se pudo escribir la clave '{key}'")

def _reset_object(settings):
    for key in ("locked", "panel-right-stick", "position", "toplevel-id", "applet-iid", "object-type"):
        try:
            settings.reset(key)
        except Exception:
            pass

def install_applet():
    panel_settings = Gio.Settings.new(panel_schema)
    object_ids = list(panel_settings.get_strv("object-id-list"))

    wmm_ids = _find_wmm_objects(object_ids)
    existing_id = wmm_ids[0] if wmm_ids else None

    if existing_id:
        if _applet_is_alive():
            active_id = _get_active_object_id()

            if active_id not in wmm_ids:
                print(
                    f"[WMM MATE] La instancia activa '{active_id}' no coincide con los objetos registrados.",
                    file=sys.stderr)
                return 1

            duplicate_ids = set(wmm_ids) - {active_id}

            if duplicate_ids:
                remaining_ids = [object_id
                    for object_id in object_ids
                    if object_id not in duplicate_ids]
                _set_value(panel_settings.set_strv("object-id-list", remaining_ids), "object-id-list")
                Gio.Settings.sync()
            return 0

        stale_settings = _object_settings(existing_id)
        toplevel_id = stale_settings.get_string("toplevel-id")
        position = stale_settings.get_int("position")
        right_stick = stale_settings.get_boolean("panel-right-stick")

        remaining_ids = [object_id for object_id in object_ids if object_id != existing_id]
        object_id = _get_free_object_id(remaining_ids)
        settings = _object_settings(object_id)

        try:
            _set_value(settings.set_string("object-type", "applet"), "object-type")
            _set_value(settings.set_string("applet-iid", wmm_iid), "applet-iid")
            _set_value(settings.set_string("toplevel-id", toplevel_id), "toplevel-id")
            _set_value(settings.set_int("position", position), "position")
            _set_value(settings.set_boolean("panel-right-stick", right_stick), "panel-right-stick")
            _set_value(settings.set_boolean("locked", False), "locked")

            Gio.Settings.sync()

            replacement_ids = [object_id if current_id == existing_id else current_id for current_id in object_ids]
            _set_value(panel_settings.set_strv("object-id-list", replacement_ids), "object-id-list")
            Gio.Settings.sync()

            _reset_object(stale_settings)
            Gio.Settings.sync()

        except Exception as error:
            _reset_object(settings)
            Gio.Settings.sync()
            print(f"[WMM MATE] No se pudo recuperar el applet: {error}", file=sys.stderr)
            return 1

        return 0

    toplevel_id, right_stick = _find_taskbar(object_ids)
    if not toplevel_id:
        print("[WMM MATE] No se pudo localizar la barra de tareas de MATE.", file=sys.stderr)
        return 1

    object_id = _get_free_object_id(object_ids)
    position = _next_position(object_ids, toplevel_id, right_stick)
    settings = _object_settings(object_id)

    try:
        _set_value(settings.set_string("object-type", "applet"), "object-type")
        _set_value(settings.set_string("applet-iid", wmm_iid), "applet-iid")
        _set_value(settings.set_string("toplevel-id", toplevel_id), "toplevel-id")
        _set_value(settings.set_int("position", position), "position")
        _set_value(settings.set_boolean("panel-right-stick", right_stick), "panel-right-stick")
        _set_value(settings.set_boolean("locked", False), "locked")

        Gio.Settings.sync()

        _set_value(panel_settings.set_strv("object-id-list", object_ids + [object_id]), "object-id-list")
        Gio.Settings.sync()

    except Exception as error:
        _reset_object(settings)
        Gio.Settings.sync()
        print(f"[WMM MATE] No se pudo registrar el applet: {error}", file=sys.stderr)
        return 1

    return 0

def _wait_for_bus_name(bus_name, present, timeout_ms=10000):
    """Espera reactivamente a que un nombre D-Bus aparezca o desaparezca."""
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    loop = GLib.MainLoop()
    reached = False
    timeout_fired = False
    timeout_id = 0

    def on_owner_changed(_connection, _sender, _path, _interface, _signal, parameters, _user_data):
        nonlocal reached
        _name, _old_owner, new_owner = parameters.unpack()

        if bool(new_owner) == present:
            reached = True
            loop.quit()

    subscription_id = bus.signal_subscribe(
        "org.freedesktop.DBus",
        "org.freedesktop.DBus",
        "NameOwnerChanged",
        "/org/freedesktop/DBus",
        bus_name,
        Gio.DBusSignalFlags.NONE,
        on_owner_changed,
        None)

    try:
        reply = bus.call_sync(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            "NameHasOwner",
            GLib.Variant("(s)", (bus_name,)),
            GLib.VariantType.new("(b)"),
            Gio.DBusCallFlags.NONE,
            1000, None)

        if bool(reply.unpack()[0]) == present:
            return True

        def on_timeout():
            nonlocal timeout_fired
            timeout_fired = True
            loop.quit()
            return GLib.SOURCE_REMOVE

        timeout_id = GLib.timeout_add(timeout_ms, on_timeout)
        loop.run()
        return reached

    finally:
        bus.signal_unsubscribe(subscription_id)

        if timeout_id and not timeout_fired:
            GLib.source_remove(timeout_id)

def _restore_applet_state(state):
    """Restaura el mismo objeto MATE retirado previamente."""
    panel_settings = Gio.Settings.new(panel_schema)
    object_id = state["object_id"]
    settings = _object_settings(object_id)

    _set_value(settings.set_string("object-type", state["object_type"]), "object-type")
    _set_value(settings.set_string("applet-iid", state["applet_iid"]), "applet-iid")
    _set_value(settings.set_string("toplevel-id", state["toplevel_id"]), "toplevel-id")
    _set_value(settings.set_int("position", state["position"]), "position")
    _set_value(settings.set_boolean("panel-right-stick", state["right_stick"]), "panel-right-stick")
    _set_value(settings.set_boolean("locked", state["locked"]), "locked")
    Gio.Settings.sync()

    object_ids = list(panel_settings.get_strv("object-id-list"))

    if object_id not in object_ids:
        object_ids.insert(min(state["index"], len(object_ids)), object_id)
        _set_value(panel_settings.set_strv("object-id-list", object_ids), "object-id-list")
        Gio.Settings.sync()

    if not _wait_for_bus_name(wmm_applet_bus_name, True):
        raise RuntimeError("El frontend MATE no volvió a activarse.")

    if not _wait_for_bus_name("org.maki.wmm", True):
        raise RuntimeError("El engine no volvió a activarse.")

    return 0

def unload_applet():
    """
    Retira limpiamente el frontend MATE y devuelve el estado necesario
    para restaurar exactamente el mismo objeto después del reemplazo.
    """
    if not _applet_is_alive():
        return None

    if install_applet() != 0:
        raise RuntimeError("No se pudo sanear el registro MATE antes de retirarlo.")

    panel_settings = Gio.Settings.new(panel_schema)
    object_ids = list(panel_settings.get_strv("object-id-list"))
    wmm_ids = _find_wmm_objects(object_ids)
    active_id = _get_active_object_id()

    if active_id not in wmm_ids:
        raise RuntimeError(
            f"La instancia activa '{active_id}' no coincide con los objetos registrados.")

    settings = _object_settings(active_id)
    state = {
        "object_id": active_id,
        "index": object_ids.index(active_id),
        "object_type": settings.get_string("object-type"),
        "applet_iid": settings.get_string("applet-iid"),
        "toplevel_id": settings.get_string("toplevel-id"),
        "position": settings.get_int("position"),
        "right_stick": settings.get_boolean("panel-right-stick"),
        "locked": settings.get_boolean("locked"),
    }

    remaining_ids = [object_id for object_id in object_ids if object_id != active_id]
    _set_value(panel_settings.set_strv("object-id-list", remaining_ids), "object-id-list")
    Gio.Settings.sync()

    if not _wait_for_bus_name(wmm_applet_bus_name, False):
        _restore_applet_state(state)
        raise RuntimeError("Timeout esperando el cierre del frontend MATE.")

    if not _wait_for_bus_name("org.maki.wmm", False):
        _restore_applet_state(state)
        raise RuntimeError("Timeout esperando el cierre del engine.")

    return state

def reload_applet():
    """Retira y restaura el frontend MATE mediante su lifecycle nativo."""
    state = unload_applet()
    if state is None:
        return install_applet()
    return _restore_applet_state(state)

def main():
    try:
        if len(sys.argv) > 1:
            if sys.argv[1] == "--reload":
                return reload_applet()
            if sys.argv[1] == "--unload":
                state = unload_applet()
                if state is not None:
                    print(json.dumps(state, separators=(",", ":")))
                return 0
            if sys.argv[1] == "--restore":
                if len(sys.argv) != 3:
                    raise RuntimeError("--restore requiere el estado del applet.")
                return _restore_applet_state(json.loads(sys.argv[2]))
            raise RuntimeError(f"Opción desconocida: {sys.argv[1]}")
        return install_applet()
    except Exception as error:
        print(f"[WMM MATE] Error del launcher: {error}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
