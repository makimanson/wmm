#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

"""
WMM - Wallpaper Multi-Monitor Manager

xfce-frontend.py - XFCE frontend
================================
Provides WMM presence in the XFCE Status Tray through StatusNotifier.

The frontend deliberately keeps two menu surfaces with different roles:
- left click: WMM's own Gtk.Menu with live wallpaper controls;
- right click: the DBusMenu exported to XFCE with application utilities.

The WMM engine remains the authority for settings, bookmarks and actions.
This process keeps no persistent copy of that state: it reads the engine via
D-Bus, reacts to its signals and sends normal actions through send_command.py.
"""

import gettext
import json
import os
import signal
import sys
import gi

gi.require_version("Gio", "2.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Wnck", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Wnck

# ==========================================================
# IDENTIDAD, RUTAS Y CONSTANTES
# ==========================================================

BUS_NAME = "org.maki.wmm.XfceFrontend"
OBJECT_PATH = "/StatusNotifierItem"
MENU_PATH = "/MenuBar"

WATCHER_BUS = "org.kde.StatusNotifierWatcher"
WATCHER_PATH = "/StatusNotifierWatcher"
WATCHER_INTERFACE = "org.kde.StatusNotifierWatcher"

SNI_INTERFACE = "org.kde.StatusNotifierItem"
ENGINE_BUS = "org.maki.wmm"

FRONTEND_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.abspath(os.path.join(FRONTEND_DIR, "..", ".."))

SEND_COMMAND_PATH = os.path.join(APP_DIR, "python", "send_command.py")
INSTALL_MANAGER_PATH = os.path.join(
    APP_DIR, "wmm_platform", "shell", "installer", "wmm-install_manager.py")
DEBUG_LOG_VIEWER_PATH = os.path.join(APP_DIR, "python", "debug_log_viewer.py")

CSS_PATH = os.path.join(FRONTEND_DIR, "xfce-frontend.css")

FAVORITES_VISIBLE_ROWS = 4

# ==========================================================
# TRADUCCIONES
# ==========================================================

APP_DOMAIN = "wmm@maki"
LOCALE_DIR = os.path.join(GLib.get_user_data_dir(), "locale")

gettext.bindtextdomain(APP_DOMAIN, LOCALE_DIR)

def _(text):
    """Traduce una cadena usando el dominio gettext propio de WMM."""
    return gettext.dgettext(APP_DOMAIN, text)

# ==========================================================
# ESTILOS GTK
# ==========================================================

wmm_css_provider = None

def _load_wmm_css():
    """Carga una sola vez los estilos propios del frontend XFCE."""
    global wmm_css_provider

    if wmm_css_provider is not None or not os.path.isfile(CSS_PATH):
        return

    try:
        provider = Gtk.CssProvider()
        provider.load_from_path(CSS_PATH)

        screen = Gdk.Screen.get_default()
        if screen is None:
            return

        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        wmm_css_provider = provider

    except GLib.Error as error:
        print(f"[WMM XFCE] No se pudo cargar xfce-frontend.css: {error}",
            flush=True,)

# ==========================================================
# STATUSNOTIFIERITEM: CONTRATO D-BUS
# ==========================================================

INTROSPECTION_XML = """
<node>
  <interface name="org.kde.StatusNotifierItem">
    <method name="ContextMenu">
      <arg name="x" type="i" direction="in"/>
      <arg name="y" type="i" direction="in"/>
    </method>

    <method name="Activate">
      <arg name="x" type="i" direction="in"/>
      <arg name="y" type="i" direction="in"/>
    </method>

    <method name="SecondaryActivate">
      <arg name="x" type="i" direction="in"/>
      <arg name="y" type="i" direction="in"/>
    </method>

    <method name="Scroll">
      <arg name="delta" type="i" direction="in"/>
      <arg name="orientation" type="s" direction="in"/>
    </method>

    <property name="Category" type="s" access="read"/>
    <property name="Id" type="s" access="read"/>
    <property name="Title" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="IconName" type="s" access="read"/>
    <property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
    <property name="ItemIsMenu" type="b" access="read"/>
    <property name="Menu" type="o" access="read"/>

    <signal name="NewTitle"/>
    <signal name="NewIcon"/>
    <signal name="NewToolTip"/>
    <signal name="NewStatus">
      <arg name="status" type="s"/>
    </signal>
  </interface>
</node>
"""

PROPERTIES = {
    "Category": GLib.Variant("s", "ApplicationStatus"),
    "Id": GLib.Variant("s", "wmm"),
    "Title": GLib.Variant("s", "WMM - Wallpaper Multi-Monitor Manager"),
    "Status": GLib.Variant("s", "Active"),
    "IconName": GLib.Variant("s", "video-display"),
    "ToolTip": GLib.Variant("(sa(iiay)ss)",
        ("video-display", [], "WMM - Wallpaper Multi-Monitor Manager", "")),
    "ItemIsMenu": GLib.Variant("b", False),
    "Menu": GLib.Variant("o", MENU_PATH),
}

# ==========================================================
# MENÚ CONTEXTUAL DBUSMENU
# ==========================================================

DBUSMENU_XML = """
<node>
  <interface name="com.canonical.dbusmenu">
    <property name="Version" type="u" access="read"/>
    <property name="TextDirection" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="IconThemePath" type="as" access="read"/>

    <method name="GetLayout">
      <arg name="parentId" type="i" direction="in"/>
      <arg name="recursionDepth" type="i" direction="in"/>
      <arg name="propertyNames" type="as" direction="in"/>
      <arg name="revision" type="u" direction="out"/>
      <arg name="layout" type="(ia{sv}av)" direction="out"/>
    </method>

    <method name="GetGroupProperties">
      <arg name="ids" type="ai" direction="in"/>
      <arg name="propertyNames" type="as" direction="in"/>
      <arg name="properties" type="a(ia{sv})" direction="out"/>
    </method>

    <method name="GetProperty">
      <arg name="id" type="i" direction="in"/>
      <arg name="name" type="s" direction="in"/>
      <arg name="value" type="v" direction="out"/>
    </method>

    <method name="Event">
      <arg name="id" type="i" direction="in"/>
      <arg name="eventId" type="s" direction="in"/>
      <arg name="data" type="v" direction="in"/>
      <arg name="timestamp" type="u" direction="in"/>
    </method>

    <method name="EventGroup">
      <arg name="events" type="a(isvu)" direction="in"/>
      <arg name="idErrors" type="ai" direction="out"/>
    </method>

    <method name="AboutToShow">
      <arg name="id" type="i" direction="in"/>
      <arg name="needUpdate" type="b" direction="out"/>
    </method>

    <method name="AboutToShowGroup">
      <arg name="ids" type="ai" direction="in"/>
      <arg name="updatesNeeded" type="ai" direction="out"/>
      <arg name="idErrors" type="ai" direction="out"/>
    </method>

    <signal name="ItemsPropertiesUpdated">
      <arg name="updatedProps" type="a(ia{sv})"/>
      <arg name="removedProps" type="a(ias)"/>
    </signal>

    <signal name="LayoutUpdated">
      <arg name="revision" type="u"/>
      <arg name="parent" type="i"/>
    </signal>

    <signal name="ItemActivationRequested">
      <arg name="id" type="i"/>
      <arg name="timestamp" type="u"/>
    </signal>
  </interface>
</node>
"""

DBUSMENU_PROPERTIES = {
    "Version": GLib.Variant("u", 3),
    "TextDirection": GLib.Variant("s", "ltr"),
    "Status": GLib.Variant("s", "normal"),
    "IconThemePath": GLib.Variant("as", []),
}

CONTEXT_MENU_ITEMS = {
    1: ("Settings", "preferences-system"),
    2: ("Sync Library", "emblem-synchronizing"),
    3: ("Install Manager", "system-software-install"),
    4: ("Debug Log Viewer", "edit-find"),
    5: ("Help", "help-faq"),
    6: None,
    7: ("About", "user-info"),
    8: ("Exit", "application-exit"),
}

CONTEXT_MENU_ORDER = tuple(CONTEXT_MENU_ITEMS)

def _context_menu_properties(item_id):
    """Construye las propiedades DBusMenu de una entrada contextual."""
    if item_id not in CONTEXT_MENU_ITEMS:
        return {}

    item = CONTEXT_MENU_ITEMS[item_id]

    if item is None:
        return {"type": GLib.Variant("s", "separator"),
            "visible": GLib.Variant("b", True),}

    label, icon_name = item

    if translations_ready:
        label = _(label)

    if item_id == 7:
        label += " WMM Manager"
    elif item_id == 8:
        label += " WMM"

    return {"label": GLib.Variant("s", label),
        "icon-name": GLib.Variant("s", icon_name),
        "enabled": GLib.Variant("b", True),
        "visible": GLib.Variant("b", True),}


def _context_menu_child(item_id):
    """Construye un hijo terminal del layout DBusMenu."""
    return GLib.Variant("(ia{sv}av)",
        (item_id, _context_menu_properties(item_id), []),)


def _context_menu_layout(item_id):
    """Devuelve el layout plano del menú contextual WMM."""
    if item_id == 0:
        return (0, {},
            [_context_menu_child(child_id) for child_id in CONTEXT_MENU_ORDER],)

    if item_id in CONTEXT_MENU_ITEMS:
        return item_id, _context_menu_properties(item_id), []

    return item_id, {}, []

# ==========================================================
# IDENTIDAD DEL PROCESO
# ==========================================================

def _set_frontend_identity():
    """Asigna nombre e icono propios al proceso frontend XFCE."""
    GLib.set_prgname("WMM Frontend")
    GLib.set_application_name("WMM Frontend")
    Gtk.Window.set_default_icon_name("video-display")

    try:
        with open("/proc/self/comm", "w", encoding="ascii") as process_name:
            process_name.write("WMM Frontend")
    except OSError:
        pass

# ==========================================================
# ENGINE: ACTIVACIÓN Y ENVÍO DE COMANDOS
# ==========================================================

def _spawn_send_command(command):
    """Envía un comando normal al engine mediante el canal común de WMM."""
    if not os.path.isfile(SEND_COMMAND_PATH):
        print(f"[WMM XFCE] send_command.py no encontrado: {SEND_COMMAND_PATH}",
            flush=True,)
        return

    payload = json.dumps(command, ensure_ascii=False, separators=(",", ":"))

    try:
        Gio.Subprocess.new([sys.executable, SEND_COMMAND_PATH, payload],
            Gio.SubprocessFlags.NONE,)
    except GLib.Error as error:
        print(f"[WMM XFCE] No se pudo enviar "
            f"{command.get('action', 'unknown')}: {error}", flush=True,)

def _on_busy_reply(connection, result, _user_data):
    """Aplica al icono SNI el estado busy actual del engine."""
    try:
        reply = connection.call_finish(result)
        busy = bool(reply.unpack()[0])
        _set_sni_icon(connection, "view-refresh" if busy else "video-display")
    except GLib.Error:
        pass


def _refresh_busy_state(connection):
    """Consulta una vez el estado busy actual del engine."""
    connection.call(
        ENGINE_BUS,
        "/org/maki/wmm",
        "org.maki.wmm",
        "GetBusy",
        None,
        GLib.VariantType.new("(b)"),
        Gio.DBusCallFlags.NO_AUTO_START,
        1500, None, _on_busy_reply, None,)

def _initialize_translated_ui(connection):
    """Materializa la UI sólo cuando el engine ya preparó las traducciones."""
    global wmm_menu
    global translations_ready
    global context_menu_revision

    if translations_ready:
        return

    translations_ready = True

    tooltip_text = (
        _("Click action") + ": " + _("Main Menu") + "\n" +
        _("Middle Click") + ": " + _("Next Background") + "\n" +
        _("Secondary Click") + ": " + _("Context Menu")
    )

    PROPERTIES["ToolTip"] = GLib.Variant(
        "(sa(iiay)ss)",
        ("video-display", [], "WMM - Wallpaper Multi-Monitor Manager",
         tooltip_text))

    wmm_menu = _build_menu(connection)
    context_menu_revision += 1

    connection.emit_signal(
        None, OBJECT_PATH, SNI_INTERFACE, "NewToolTip", None)

    connection.emit_signal(
        None, MENU_PATH, "com.canonical.dbusmenu", "LayoutUpdated",
        GLib.Variant("(ui)", (context_menu_revision, 0)))

def _on_engine_appeared(connection, _name, _name_owner):
    """Completa y publica el frontend cuando el engine está realmente disponible."""
    global status_notifier_watch_id

    _initialize_translated_ui(connection)

    # El icono sólo se publica cuando traducciones y menú principal ya existen.
    if status_notifier_watch_id is None:
        status_notifier_watch_id = Gio.bus_watch_name_on_connection(
            connection, WATCHER_BUS,
            Gio.BusNameWatcherFlags.NONE,
            _on_watcher_appeared,
            _on_watcher_vanished,)

    _refresh_menu_settings(connection)
    _refresh_menu_bookmarks(connection)
    _refresh_busy_state(connection)

def _on_engine_vanished(_connection, _name):
    """Mantiene vivo el frontend si el engine desaparece temporalmente."""
    print("[WMM XFCE] Engine no disponible; esperando", flush=True)

def _on_engine_started(connection, result, command):
    """Finaliza la solicitud de activación; la disponibilidad la marca D-Bus."""
    try:
        connection.call_finish(result)
    except GLib.Error as error:
        if command is None:
            print(f"[WMM XFCE] Activación inicial pendiente; "
                f"esperando {ENGINE_BUS}: {error}", flush=True,)
        else:
            print(f"[WMM XFCE] No se pudo activar {ENGINE_BUS}: {error}",
                flush=True,)
        return

    if command is not None:
        _spawn_send_command(command)

def _start_engine(connection, command=None):
    """Activa org.maki.wmm y continúa opcionalmente con un comando."""
    connection.call(
        "org.freedesktop.DBus",
        "/org/freedesktop/DBus",
        "org.freedesktop.DBus",
        "StartServiceByName",
        GLib.Variant("(su)", (ENGINE_BUS, 0)),
        GLib.VariantType.new("(u)"),
        Gio.DBusCallFlags.NONE,
        5000, None, _on_engine_started, command,)

def _send_action_to_engine(connection, command):
    """Activa el engine y envía un comando por el canal común de WMM."""
    # Las acciones normales pasan por send_command.py; Install Manager y
    # Debug Log Viewer son deliberadamente independientes del engine.
    _start_engine(connection, command)

# ==========================================================
# HERRAMIENTAS INDEPENDIENTES Y CIERRE GLOBAL
# ==========================================================

def _launch_independent_tool(path):
    """Lanza una herramienta que no depende del estado del engine."""
    if not os.path.isfile(path):
        print(f"[WMM XFCE] Herramienta no encontrada: {path}", flush=True)
        return

    try:
        Gio.Subprocess.new([sys.executable, path], Gio.SubprocessFlags.NONE,)
    except GLib.Error as error:
        print(f"[WMM XFCE] No se pudo lanzar {path}: {error}", flush=True,)

def _quit_frontend():
    """Finaliza el loop principal del frontend XFCE."""
    if frontend_loop is not None:
        frontend_loop.quit()

    return GLib.SOURCE_REMOVE

def _on_shutdown_finished(connection, result, user_data):
    """Finaliza el frontend aunque el engine ya no esté disponible."""
    try:
        connection.call_finish(result)
    except GLib.Error:
        pass

    _quit_frontend()


def _shutdown_wmm(connection):
    """Solicita el cierre del engine sin arrancarlo y termina el frontend."""
    connection.call(
        ENGINE_BUS,
        "/org/maki/wmm",
        "org.maki.wmm",
        "Shutdown",
        None, None, Gio.DBusCallFlags.NO_AUTO_START,
        1000, None, _on_shutdown_finished, None,)

# ==========================================================
# MENÚ CONTEXTUAL DBUSMENU: CALLBACKS
# ==========================================================

def _activate_context_menu_item(connection, item_id):
    """Ejecuta la acción seleccionada en el menú contextual WMM."""
    if item_id == 1:
        _send_action_to_engine(connection, {"action": "open_panel"})

    elif item_id == 2:
        _send_action_to_engine(connection, {"action": "sync_library"})

    elif item_id == 3:
        _launch_independent_tool(INSTALL_MANAGER_PATH)

    elif item_id == 4:
        _launch_independent_tool(DEBUG_LOG_VIEWER_PATH)

    elif item_id == 5:
        _send_action_to_engine(connection, {"action": "open_help"})

    elif item_id == 7:
        _send_action_to_engine(connection, {"action": "open_about"})

    elif item_id == 8:
        _shutdown_wmm(connection)


def _on_context_menu_get_property(connection, sender,
    object_path, interface_name, property_name):
    """Entrega las propiedades públicas de com.canonical.dbusmenu."""
    return DBUSMENU_PROPERTIES.get(property_name)


def _on_context_menu_method_call(connection, sender, object_path,
    interface_name, method_name, parameters, invocation):
    """Atiende las consultas y eventos del menú contextual XFCE."""
    values = parameters.unpack()

    if method_name == "GetLayout":
        parent_id, recursion_depth, property_names = values
        invocation.return_value(
            GLib.Variant("(u(ia{sv}av))",
                (context_menu_revision, _context_menu_layout(parent_id)),))
        return

    if method_name == "GetGroupProperties":
        ids, property_names = values

        if not ids:
            ids = CONTEXT_MENU_ORDER

        properties = [(item_id, _context_menu_properties(item_id))
            for item_id in ids
            if item_id in CONTEXT_MENU_ITEMS]

        invocation.return_value(GLib.Variant("(a(ia{sv}))", (properties,)))
        return

    if method_name == "GetProperty":
        item_id, property_name = values
        value = _context_menu_properties(item_id).get(
            property_name, GLib.Variant("s", ""),)

        invocation.return_value(GLib.Variant("(v)", (value,)))
        return

    if method_name == "Event":
        item_id, event_id, data, timestamp = values

        if event_id == "clicked":
            _activate_context_menu_item(connection, item_id)

        invocation.return_value(None)
        return

    if method_name == "EventGroup":
        events = values[0]

        for item_id, event_id, data, timestamp in events:
            if event_id == "clicked":
                _activate_context_menu_item(connection, item_id)

        invocation.return_value(GLib.Variant("(ai)", ([],)))
        return

    if method_name == "AboutToShow":
        invocation.return_value(GLib.Variant("(b)", (False,)))
        return

    if method_name == "AboutToShowGroup":
        invocation.return_value(GLib.Variant("(aiai)", ([], [])))
        return

# ==========================================================
# MENÚ PRINCIPAL GTK: ESTADO COMPARTIDO
# ==========================================================
#
# Estos valores son sólo estado efímero de presentación. Settings y
# bookmarks pertenecen al engine y nunca se persisten desde el frontend.

wmm_menu = None
frontend_loop = None
status_notifier_watch_id = None
translations_ready = False
context_menu_revision = 1
favorites_expanded = False
favorites_header_item = None
favorites_switch_item = None
favorites_only_switch = None
favorites_add_item = None
favorites_scroll_item = None
favorites_scrolled = None
favorites_inline_list = None
favorites_hover_widget = None
cached_bookmarks = {}
slideshow_expanded = False
slideshow_header_item = None
slideshow_switch_item = None
slideshow_switch = None
slideshow_switch_label = None
slideshow_interval_item = None
slideshow_interval_label = None
slideshow_scale = None
slideshow_scale_dragging = False
slideshow_interval = 15
slideshow_max_interval = 60
displays_item = None
spanned_item = None
next_background_item = None
menu_syncing_state = False
menu_anchor_edge = None
menu_anchor_coordinate = None


# ==========================================================
# MENÚ PRINCIPAL: SINCRONIZACIÓN CON EL ENGINE
# ==========================================================

def _update_displays_label():
    """Refleja SYNC/ASYNC en la etiqueta visible de Displays."""
    if displays_item is None:
        return

    mode = _("SYNC (All)") if displays_item.get_active() else _("ASYNC (One)")
    displays_item.set_label(_("Displays") + ": " + mode)


def _apply_menu_settings(data):
    """Sincroniza el estado visible del menú desde los settings del engine."""
    global menu_syncing_state
    global slideshow_interval
    global slideshow_max_interval

    if not isinstance(data, dict):
        return

    config = data.get("global", data)
    if not isinstance(config, dict):
        return

    if (displays_item is None or spanned_item is None
        or slideshow_switch is None or slideshow_scale is None
        or favorites_only_switch is None):
        return

    slideshow_max_interval = max(
        1, int(config.get("slideshow_max_interval", 60) or 60))
    slideshow_interval = int(config.get("slideshow_interval", 15) or 15)
    slideshow_interval = max(
        1, min(slideshow_interval, slideshow_max_interval))

    enabled = bool(config.get("slideshow_enabled", False))

    # set_active()/set_value() disparan señales GTK. Esta barrera evita que
    # un refresh procedente del engine rebote como un nuevo comando de usuario.
    menu_syncing_state = True

    try:
        displays_item.set_active(
            config.get("slideshow_mode", "async") == "sync")
        spanned_item.set_active(
            bool(config.get("spanned_enabled", False)))
        slideshow_switch.set_active(enabled)
        slideshow_scale.set_range(1, slideshow_max_interval)
        slideshow_scale.set_value(slideshow_interval)
        favorites_only_switch.set_active(
            bool(config.get("slideshow_bookmark", False)))
    finally:
        menu_syncing_state = False

    _update_displays_label()
    slideshow_switch_label.set_text(_("Enabled") if enabled else _("Disabled"))
    slideshow_scale.set_sensitive(enabled)
    slideshow_interval_label.set_text(
        str(slideshow_interval) + " " + _("minutes"))


def _on_menu_settings_reply(connection, result, user_data):
    """Decodifica GetSettings y actualiza el estado visible del menú."""
    try:
        reply = connection.call_finish(result)
        raw = reply.unpack()[0]
        _apply_menu_settings(json.loads(raw) if raw else {})
    except (GLib.Error, json.JSONDecodeError, TypeError, ValueError):
        pass


def _refresh_menu_settings(connection):
    """Consulta al engine el estado actual necesario para el menú principal."""
    connection.call(
        ENGINE_BUS,
        "/org/maki/wmm",
        "org.maki.wmm",
        "GetSettings",
        None, GLib.VariantType.new("(s)"),
        Gio.DBusCallFlags.NO_AUTO_START,
        1500, None, _on_menu_settings_reply, None,)

def _refresh_menu_bookmarks(connection):
    """Solicita al engine la colección actual de favoritos."""
    connection.call(
        ENGINE_BUS,
        "/org/maki/wmm",
        "org.maki.wmm",
        "GetBookmarks",
        None,
        GLib.VariantType.new("(s)"),
        Gio.DBusCallFlags.NO_AUTO_START,
        1500, None, _on_menu_bookmarks_reply, None,)


def _on_menu_bookmarks_reply(connection, result, user_data):
    """Decodifica GetBookmarks y reconstruye la lista inline."""
    global cached_bookmarks

    try:
        reply = connection.call_finish(result)
        raw = reply.unpack()[0]
        bookmarks = json.loads(raw) if raw else {}
        cached_bookmarks = bookmarks if isinstance(bookmarks, dict) else {}
        _paint_inline_bookmarks()
    except (GLib.Error, json.JSONDecodeError, TypeError, ValueError):
        pass


def _on_bookmarks_changed(connection, sender_name, object_path,
    interface_name, signal_name, parameters):
    """Aplica una actualización push de favoritos recibida del engine."""
    global cached_bookmarks

    try:
        raw = parameters.unpack()[0]
        bookmarks = json.loads(raw) if raw else {}
        cached_bookmarks = bookmarks if isinstance(bookmarks, dict) else {}
        _paint_inline_bookmarks()
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

def _on_busy_changed(connection, sender_name, object_path,
    interface_name, signal_name, parameters):
    """Refleja en el icono SNI el estado busy publicado por el engine."""
    busy = bool(parameters.unpack()[0])
    _set_sni_icon(connection, "view-refresh" if busy else "video-display")


def _on_settings_changed(connection, sender_name, object_path,
    interface_name, signal_name, parameters):
    """Aplica al menú los cambios de settings publicados por el engine."""
    try:
        raw = parameters.unpack()[0]
        _apply_menu_settings(json.loads(raw) if raw else {})
    except (json.JSONDecodeError, TypeError, ValueError):
        pass


# ==========================================================
# DISPLAYS / SPANNED
# ==========================================================

def _on_displays_toggled(item, connection):
    """Alterna ASYNC/SYNC sin modificar el resto de ajustes del slideshow."""
    if menu_syncing_state:
        return

    _update_displays_label()
    _send_action_to_engine(connection, {
        "action": "update_timer_settings",
        "mode": "sync" if item.get_active() else "async",
    })


def _on_spanned_toggled(item, connection):
    """Propaga únicamente el estado de Spanned al engine."""
    if menu_syncing_state:
        return

    _send_action_to_engine(connection, {
        "action": "update_timer_settings",
        "spanned_enabled": item.get_active(),
    })

# ==========================================================
# SLIDESHOW
# ==========================================================

def _sync_slideshow_ui(enabled):
    """Refleja el estado de Slideshow sin generar un comando recursivo."""
    global menu_syncing_state

    if slideshow_switch is None:
        return

    syncing = menu_syncing_state
    menu_syncing_state = True
    slideshow_switch.set_active(enabled)
    menu_syncing_state = syncing

    slideshow_switch_label.set_text(_("Enabled") if enabled else _("Disabled"))
    slideshow_scale.set_sensitive(enabled)


def _on_slideshow_switch_changed(switch, pspec, connection):
    """Propaga únicamente el estado ON/OFF de Slideshow al engine."""
    if menu_syncing_state:
        return

    _sync_slideshow_ui(switch.get_active())
    _send_action_to_engine(connection, {
        "action": "update_timer_settings",
        "enabled": switch.get_active(),
    })


def _on_slideshow_scale_changed(scale):
    """Actualiza en vivo el intervalo mostrado mientras se mueve el slider."""
    global slideshow_interval

    slideshow_interval = int(round(scale.get_value()))
    slideshow_interval_label.set_text(
        str(slideshow_interval) + " " + _("minutes"))


def _set_slideshow_scale_from_event(menu, event):
    """Convierte la posición del puntero en un valor del slider."""
    if slideshow_scale is None or not slideshow_scale.get_sensitive():
        return False

    menu_window = menu.get_window()
    if menu_window is None:
        return False

    _, origin_x, origin_y = menu_window.get_origin()
    menu_x = int(event.x_root - origin_x)
    menu_y = int(event.y_root - origin_y)

    translated = menu.translate_coordinates(slideshow_scale, menu_x, menu_y)
    if translated is None:
        return False

    x, y = translated
    width = slideshow_scale.get_allocated_width()
    height = slideshow_scale.get_allocated_height()

    if width <= 0 or height <= 0:
        return False

    if x < 0 or x > width or y < 0 or y > height:
        return False

    fraction = max(0.0, min(1.0, x / width))

    if slideshow_scale.get_direction() == Gtk.TextDirection.RTL:
        fraction = 1.0 - fraction

    adjustment = slideshow_scale.get_adjustment()
    value = adjustment.get_lower() + fraction * (
        adjustment.get_upper() - adjustment.get_lower())

    slideshow_scale.set_value(round(value))
    return True


# ==========================================================
# EVENTOS INLINE COMPARTIDOS
# ==========================================================
#
# Gtk.Menu conserva el grab del puntero mientras está abierto. El slider
# y la lista de Favorites no pueden depender de la interacción GTK normal:
# el menú recibe los eventos y los delega manualmente por coordenadas.

def _on_menu_button_press(menu, event):
    """Inicia el drag manual cuando el clic cae sobre el slider."""
    global slideshow_scale_dragging

    if event.button != 1:
        return False

    selected_item = menu.get_selected_item()

    if (selected_item is slideshow_interval_item
        and not slideshow_scale.get_sensitive()):
        return True

    if not _set_slideshow_scale_from_event(menu, event):
        return False

    slideshow_scale_dragging = True
    return True


def _on_menu_motion(menu, event):
    """Actualiza slider o hover manual de Favorites."""
    if slideshow_scale_dragging:
        _set_slideshow_scale_from_event(menu, event)
        return True

    _update_favorites_hover(menu, event)
    return False

def _on_menu_scroll(menu, event):
    """Desplaza Favorites con la rueda sin mostrar scrollbar."""
    if menu.get_selected_item() is not favorites_scroll_item:
        return False

    adjustment = favorites_scrolled.get_vadjustment()
    step = max(adjustment.get_step_increment(), 24.0)

    if event.direction == Gdk.ScrollDirection.UP:
        delta = -step
    elif event.direction == Gdk.ScrollDirection.DOWN:
        delta = step
    elif event.direction == Gdk.ScrollDirection.SMOOTH:
        success, delta_x, delta_y = event.get_scroll_deltas()
        if not success:
            return True
        delta = delta_y * step
    else:
        return True

    lower = adjustment.get_lower()
    upper = max(
        lower, adjustment.get_upper() - adjustment.get_page_size())

    adjustment.set_value(max(
        lower, min(upper, adjustment.get_value() + delta)))

    return True


def _event_inside_widget(menu, event, widget):
    """Comprueba si un evento del Gtk.Menu cae realmente en un widget."""
    if widget is None or not widget.get_visible():
        return False

    menu_window = menu.get_window()
    if menu_window is None:
        return False

    _, origin_x, origin_y = menu_window.get_origin()
    menu_x = int(event.x_root - origin_x)
    menu_y = int(event.y_root - origin_y)

    translated = menu.translate_coordinates(widget, menu_x, menu_y)
    if translated is None:
        return False

    x, y = translated
    width = widget.get_allocated_width()
    height = widget.get_allocated_height()

    return 0 <= x < width and 0 <= y < height


def _update_favorites_hover(menu, event):
    """Aplica PRELIGHT al nombre o papelera bajo el puntero."""
    global favorites_hover_widget

    hover_widget = None

    if favorites_expanded:
        for row in favorites_inline_list.get_children():
            if _event_inside_widget(
                menu, event, getattr(row, "wmm_delete_widget", None)):
                hover_widget = row.wmm_delete_widget
                break

            if _event_inside_widget(
                menu, event, getattr(row, "wmm_name_widget", None)):
                hover_widget = row.wmm_name_widget
                break

    if favorites_hover_widget is hover_widget:
        return

    if favorites_hover_widget is not None:
        favorites_hover_widget.unset_state_flags(Gtk.StateFlags.PRELIGHT)

    favorites_hover_widget = hover_widget

    if favorites_hover_widget is not None:
        favorites_hover_widget.set_state_flags(
            Gtk.StateFlags.PRELIGHT, False)

# ==========================================================
# FAVORITOS
# ==========================================================

def _on_favorites_only_switch_changed(switch, pspec, connection):
    """Actualiza Favorites Only y activa Slideshow si resulta necesario."""
    if menu_syncing_state:
        return

    enabled = switch.get_active()
    command = {"action": "update_timer_settings", "slideshow_bookmark": enabled}

    # Favorites Only sólo tiene sentido con el slideshow activo.
    if enabled and not slideshow_switch.get_active():
        _sync_slideshow_ui(True)
        command["enabled"] = True

    _send_action_to_engine(connection, command)

def _paint_inline_bookmarks():
    """Reconstruye la lista inline desde los favoritos publicados por el engine."""
    global favorites_hover_widget

    if favorites_inline_list is None:
        return

    # BookmarksChanged puede repintar con el menú abierto. No conservamos
    # PRELIGHT ni una referencia a un botón que va a ser destruido.
    if favorites_hover_widget is not None:
        favorites_hover_widget.unset_state_flags(Gtk.StateFlags.PRELIGHT)
        favorites_hover_widget = None

    for child in favorites_inline_list.get_children():
        child.destroy()

    names = list(cached_bookmarks.keys())

    if not names:
        row = Gtk.ListBoxRow()
        row.set_selectable(False)
        row.set_activatable(False)
        row.get_style_context().add_class("wmm-favorite-row")

        label = Gtk.Label(label=_("No saved favorites"), xalign=0)
        label.set_sensitive(False)
        label.get_style_context().add_class("wmm-favorite-empty")

        row.add(label)
        favorites_inline_list.add(row)

    else:
        for name in names:
            row = Gtk.ListBoxRow()
            row.set_selectable(False)
            row.set_activatable(False)
            row.wmm_name = name
            row.get_style_context().add_class("wmm-favorite-row")

            row_box = Gtk.Box(
                orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
            row_box.get_style_context().add_class(
                "wmm-favorite-row-box")

            name_button = Gtk.Button()
            name_button.set_relief(Gtk.ReliefStyle.NONE)
            name_button.set_can_focus(False)
            name_button.set_focus_on_click(False)
            name_button.set_hexpand(True)
            name_button.get_style_context().add_class(
                "wmm-favorite-button")

            name_label = Gtk.Label(label=name, xalign=0)
            name_label.set_ellipsize(3)
            name_button.add(name_label)

            delete_button = Gtk.Button()
            delete_button.set_relief(Gtk.ReliefStyle.NONE)
            delete_button.set_can_focus(False)
            delete_button.set_focus_on_click(False)
            delete_button.get_style_context().add_class(
                "wmm-favorite-button")

            delete_icon = Gtk.Image.new_from_icon_name(
                "user-trash-symbolic", Gtk.IconSize.MENU)
            delete_button.add(delete_icon)

            # Gtk.Menu posee los eventos: guardamos las zonas reales
            # que después usará el hit-testing manual.
            row.wmm_name_widget = name_button
            row.wmm_delete_widget = delete_button

            row_box.pack_start(name_button, True, True, 0)
            row_box.pack_end(delete_button, False, False, 0)
            row.add(row_box)
            favorites_inline_list.add(row)

    favorites_inline_list.show_all()
    _update_favorites_scroll_height()


def _update_favorites_scroll_height():
    """Limita Favorites a cuatro filas reales según las métricas del tema."""
    if favorites_scrolled is None:
        return

    rows = favorites_inline_list.get_children()
    if not rows:
        return

    target_height = 0

    for row in rows[:FAVORITES_VISIBLE_ROWS]:
        _, natural_height = row.get_preferred_height()
        target_height += natural_height

    style = favorites_inline_list.get_style_context()
    state = style.get_state()
    padding = style.get_padding(state)
    border = style.get_border(state)

    target_height += padding.top + padding.bottom
    target_height += border.top + border.bottom
    target_height = max(1, target_height)

    # Liberar primero el máximo evita min > max al cambiar
    # dinámicamente entre listas de distinta altura.
    favorites_scrolled.set_max_content_height(-1)
    favorites_scrolled.set_min_content_height(target_height)
    favorites_scrolled.set_max_content_height(target_height)
    favorites_scrolled.queue_resize()
    favorites_scroll_item.queue_resize()

def _load_favorite(name, connection):
    """Carga un favorito y refleja de inmediato el slideshow forzado a OFF."""
    _sync_slideshow_ui(False)

    _send_action_to_engine(connection, {
        "action": "load_bookmark",
        "name": name,
        "timer_force_off": True,
    })


def _confirm_delete_favorite(name, connection):
    """Solicita confirmación antes de borrar un favorito."""
    dialog = Gtk.MessageDialog(
        transient_for=None,
        modal=True,
        message_type=Gtk.MessageType.QUESTION,
        buttons=Gtk.ButtonsType.YES_NO,
        text=_("Delete") + ' "' + name + '"?',
    )
    dialog.set_title(_("Delete favorite"))

    response = dialog.run()
    dialog.destroy()

    if response == Gtk.ResponseType.YES:
        _send_action_to_engine(connection, {
            "action": "delete_bookmark",
            "name": name,
        })

# ==========================================================
# CONSTRUCCIÓN DEL MENÚ PRINCIPAL
# ==========================================================

def _build_menu(connection):
    """Construye la estructura base del menú principal WMM para XFCE."""
    global favorites_header_item
    global favorites_switch_item
    global favorites_add_item
    global favorites_only_switch
    global favorites_scroll_item
    global favorites_scrolled
    global favorites_inline_list
    global displays_item
    global spanned_item
    global next_background_item
    global slideshow_header_item
    global slideshow_switch_item
    global slideshow_switch
    global slideshow_switch_label
    global slideshow_interval_item
    global slideshow_interval_label
    global slideshow_scale

    menu = Gtk.Menu()

    # Favorites y Slideshow son secciones inline: sus hijos permanecen dentro
    # del mismo Gtk.Menu para que expandir, cargar o ajustar no cierre el popup.
    # CheckMenuItem conserva la columna izquierda nativa del menú; su indicador
    # se reutiliza como flecha de expansión mediante la clase CSS propia.
    favorites_header_item = Gtk.CheckMenuItem(label=_("Favorites"))
    favorites_header_item.get_style_context().add_class("wmm-menu-icon")
    favorites_header_item.get_style_context().add_class("wmm-inline-header")
    favorites_header_item.set_active(False)
    menu.append(favorites_header_item)

    # Favorites Only.
    favorites_switch_item = Gtk.MenuItem()

    switch_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
    switch_label = Gtk.Label(label=_("Favorites Only"), xalign=0)
    favorites_only_switch = Gtk.Switch()
    favorites_only_switch.connect(
        "notify::active", _on_favorites_only_switch_changed, connection)

    switch_box.pack_start(switch_label, True, True, 0)
    switch_box.pack_end(favorites_only_switch, False, False, 0)
    favorites_switch_item.add(switch_box)

    # Add Preset Favorite.
    # CheckMenuItem aporta únicamente la columna nativa reservada al icono;
    # la acción sigue siendo momentánea y no representa un estado booleano.
    favorites_add_item = Gtk.CheckMenuItem(label=_("Add Preset Favorite"))
    favorites_add_item.get_style_context().add_class("wmm-menu-icon")
    favorites_add_item.get_style_context().add_class("wmm-add-favorite")
    favorites_add_item.set_active(False)

    # Lista inline de favoritos. Mantiene GtkAdjustment aunque la
    # scrollbar permanezca oculta visualmente.
    favorites_scroll_item = Gtk.MenuItem()

    favorites_scrolled = Gtk.ScrolledWindow()
    favorites_scrolled.set_overlay_scrolling(True)
    favorites_scrolled.set_policy(
        Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    favorites_scrolled.set_propagate_natural_height(True)

    favorites_scrollbar = favorites_scrolled.get_vscrollbar()
    favorites_scrollbar.get_style_context().add_class(
        "wmm-hidden-scrollbar")

    favorites_inline_list = Gtk.ListBox()
    favorites_inline_list.set_selection_mode(Gtk.SelectionMode.NONE)

    favorites_scrolled.add(favorites_inline_list)
    favorites_scroll_item.add(favorites_scrolled)

    menu.append(favorites_switch_item)
    menu.append(favorites_add_item)
    menu.append(favorites_scroll_item)

    # Slideshow reutiliza la columna nativa de Gtk.CheckMenuItem como
    # indicador desplegable, igual que Favorites.
    slideshow_header_item = Gtk.CheckMenuItem(label=_("Slideshow"))
    slideshow_header_item.get_style_context().add_class("wmm-menu-icon")
    slideshow_header_item.get_style_context().add_class("wmm-inline-header")
    slideshow_header_item.set_active(False)
    menu.append(slideshow_header_item)

    # Switch maestro de Slideshow.
    slideshow_switch_item = Gtk.MenuItem()

    slideshow_switch_box = Gtk.Box(
        orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
    slideshow_switch_label = Gtk.Label(label=_("Disabled"), xalign=0)
    slideshow_switch = Gtk.Switch()
    slideshow_switch.connect(
        "notify::active", _on_slideshow_switch_changed, connection)

    slideshow_switch_box.pack_start(
        slideshow_switch_label, True, True, 0)
    slideshow_switch_box.pack_end(
        slideshow_switch, False, False, 0)
    slideshow_switch_item.add(slideshow_switch_box)
    menu.append(slideshow_switch_item)

    # Intervalo + slider.
    slideshow_interval_item = Gtk.MenuItem()

    slideshow_interval_box = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL, spacing=0)

    slideshow_interval_label = Gtk.Label(
        label=str(slideshow_interval) + " " + _("minutes"))
    slideshow_interval_label.set_halign(Gtk.Align.CENTER)

    slideshow_scale = Gtk.Scale.new_with_range(
        Gtk.Orientation.HORIZONTAL, 1, slideshow_max_interval, 1)
    slideshow_scale.set_draw_value(False)
    slideshow_scale.set_value(slideshow_interval)
    slideshow_scale.set_hexpand(True)
    slideshow_scale.set_sensitive(False)
    slideshow_scale.connect(
        "value-changed", _on_slideshow_scale_changed)

    slideshow_interval_box.pack_start(
        slideshow_interval_label, False, False, 0)
    slideshow_interval_box.pack_start(
        slideshow_scale, False, False, 0)
    slideshow_interval_item.add(slideshow_interval_box)
    menu.append(slideshow_interval_item)

    displays_item = Gtk.CheckMenuItem(
        label=_("Displays") + ": " + _("ASYNC (One)"))
    displays_item.connect("toggled", _on_displays_toggled, connection)
    menu.append(displays_item)

    spanned_item = Gtk.CheckMenuItem(label=_("Spanned Mode"))
    spanned_item.connect("toggled", _on_spanned_toggled, connection)
    menu.append(spanned_item)

    menu.append(Gtk.SeparatorMenuItem())

    # Next Background conserva la columna nativa reservada al icono sin usar
    # Gtk.ImageMenuItem; la acción sigue siendo momentánea y no un toggle.
    next_background_item = Gtk.CheckMenuItem(label=_("Next Background"))
    next_background_item.get_style_context().add_class("wmm-menu-icon")
    next_background_item.get_style_context().add_class("wmm-next-background")
    next_background_item.set_active(False)
    menu.append(next_background_item)

    # El grab propio de Gtk.Menu obliga a centralizar estos eventos. No sustituir
    # por callbacks directos de Gtk.Switch/Gtk.Scale/Gtk.Button sin revalidar.
    menu.add_events(
        Gdk.EventMask.BUTTON_PRESS_MASK |
        Gdk.EventMask.BUTTON_RELEASE_MASK |
        Gdk.EventMask.POINTER_MOTION_MASK |
        Gdk.EventMask.SCROLL_MASK)

    menu.connect("button-press-event", _on_menu_button_press)
    menu.connect("motion-notify-event", _on_menu_motion)
    menu.connect("button-release-event", _on_menu_button_release, connection)
    menu.connect("scroll-event", _on_menu_scroll)

    menu_toplevel = menu.get_toplevel()
    menu_toplevel.connect("unmap", _on_menu_toplevel_unmap)

    menu.show_all()

    # show_all() materializa todos los widgets; las secciones inline empiezan
    # cerradas de forma deliberada en cada nueva apertura del menú.
    favorites_switch_item.hide()
    favorites_add_item.hide()
    favorites_scroll_item.hide()

    slideshow_switch_item.hide()
    slideshow_interval_item.hide()

    _paint_inline_bookmarks()

    return menu

# ==========================================================
# POPUP: REDIMENSIONADO Y DESPACHO DE INTERACCIÓN
# ==========================================================

def _resize_menu_native_window():
    """Redimensiona el popup conservando tamaño nativo y anclaje al panel.

    Gtk.Menu no conserva por sí solo el borde de contacto al crecer después de
    abrirse. El move_resize mantiene fijo el borde del panel ya validado en las
    cuatro orientaciones (top/bottom/left/right).
    """
    if (wmm_menu is None
        or menu_anchor_edge is None
        or menu_anchor_coordinate is None):
        return GLib.SOURCE_REMOVE

    _, natural = wmm_menu.get_preferred_size()
    allocation = wmm_menu.get_allocation()
    native_window = wmm_menu.get_toplevel().get_window()

    if native_window is None:
        return GLib.SOURCE_REMOVE

    _, x, y = native_window.get_origin()
    geometry = native_window.get_geometry()

    extra_width = geometry.width - allocation.width
    extra_height = geometry.height - allocation.height

    width = natural.width + extra_width
    height = natural.height + extra_height

    if menu_anchor_edge == "bottom":
        y = menu_anchor_coordinate - height

    elif menu_anchor_edge == "top":
        y = menu_anchor_coordinate

    elif menu_anchor_edge == "right":
        x = menu_anchor_coordinate - width

    elif menu_anchor_edge == "left":
        x = menu_anchor_coordinate

    native_window.move_resize(x, y, width, height)

    return GLib.SOURCE_REMOVE

def _on_menu_button_release(menu, event, connection):
    """Gestiona las secciones inline sin cerrar el popup."""
    global favorites_expanded
    global slideshow_expanded
    global slideshow_scale_dragging

    if event.button != 1:
        return False

    if slideshow_scale_dragging:
        _set_slideshow_scale_from_event(menu, event)
        slideshow_scale_dragging = False

        _send_action_to_engine(connection, {
            "action": "update_timer_settings",
            "interval": slideshow_interval,
        })
        return True

    selected_item = menu.get_selected_item()

    if selected_item is favorites_header_item:
        favorites_expanded = not favorites_expanded

        if favorites_expanded:
            _update_favorites_scroll_height()

        favorites_switch_item.set_visible(favorites_expanded)
        favorites_add_item.set_visible(favorites_expanded)
        favorites_scroll_item.set_visible(favorites_expanded)

        favorites_header_item.set_active(favorites_expanded)

        _resize_menu_native_window()
        return True

    if selected_item is favorites_switch_item:
        favorites_only_switch.set_active(
            not favorites_only_switch.get_active())
        return True

    # El formulario de alta es externo: cerramos el popup.
    if selected_item is favorites_add_item:
        menu.popdown()
        _send_action_to_engine(connection, {"action": "add_bookmark"})
        return True

    # El nombre carga y mantiene abierto; la papelera abre confirmación.
    if selected_item is favorites_scroll_item:
        for row in favorites_inline_list.get_children():
            name = getattr(row, "wmm_name", None)
            if not name:
                continue

            if _event_inside_widget(
                menu, event, getattr(row, "wmm_delete_widget", None)):
                menu.popdown()
                _confirm_delete_favorite(name, connection)
                return True

            if _event_inside_widget(
                menu, event, getattr(row, "wmm_name_widget", None)):
                _load_favorite(name, connection)
                return True

        return True

    if selected_item is slideshow_header_item:
        slideshow_expanded = not slideshow_expanded

        slideshow_switch_item.set_visible(slideshow_expanded)
        slideshow_interval_item.set_visible(slideshow_expanded)

        slideshow_header_item.set_active(slideshow_expanded)

        _resize_menu_native_window()
        return True

    if selected_item is slideshow_switch_item:
        slideshow_switch.set_active(
            not slideshow_switch.get_active())
        return True

    if selected_item is slideshow_interval_item:
        return True

    if selected_item is next_background_item:
        # Se despacha aquí, no mediante "activate": devolver True mantiene el
        # popup abierto para permitir varias rotaciones consecutivas.
        _send_action_to_engine(connection, {"action": "force_rotation"})
        return True

    return False

def _on_menu_toplevel_unmap(widget):
    """Restablece el estado efímero de las secciones al cerrar el popup."""
    global favorites_expanded
    global slideshow_expanded
    global slideshow_scale_dragging
    global favorites_hover_widget

    favorites_expanded = False
    favorites_switch_item.hide()
    favorites_add_item.hide()
    favorites_scroll_item.hide()
    if favorites_hover_widget is not None:
        favorites_hover_widget.unset_state_flags(Gtk.StateFlags.PRELIGHT)
        favorites_hover_widget = None
    favorites_header_item.set_active(False)

    slideshow_expanded = False
    # Si el popup desaparece durante un drag, GTK puede no entregar release.
    # Evitamos que la siguiente apertura herede y confirme un drag antiguo.
    slideshow_scale_dragging = False
    slideshow_switch_item.hide()
    slideshow_interval_item.hide()

    slideshow_header_item.set_active(False)

# ==========================================================
# POPUP: ANCLAJE CONTRA EL PANEL XFCE
# ==========================================================

def _get_panel_geometry_at_point(x, y):
    """Devuelve geometría y borde del panel XFCE que contiene el punto."""
    display = Gdk.Display.get_default()
    if display is None:
        return None

    monitor = display.get_monitor_at_point(x, y)
    if monitor is None:
        return None

    monitor_geometry = monitor.get_geometry()

    screen = Wnck.Screen.get_default()
    screen.force_update()

    for window in screen.get_windows():
        if window.get_window_type() != Wnck.WindowType.DOCK:
            continue

        panel_x, panel_y, panel_width, panel_height = window.get_geometry()

        if not (panel_x <= x < panel_x + panel_width
            and panel_y <= y < panel_y + panel_height):
            continue

        if panel_width >= panel_height:
            top_distance = abs(panel_y - monitor_geometry.y)
            bottom_distance = abs(
                monitor_geometry.y + monitor_geometry.height
                - panel_y - panel_height)
            edge = "top" if top_distance <= bottom_distance else "bottom"

        else:
            left_distance = abs(panel_x - monitor_geometry.x)
            right_distance = abs(
                monitor_geometry.x + monitor_geometry.width
                - panel_x - panel_width)
            edge = "left" if left_distance <= right_distance else "right"

        return panel_x, panel_y, panel_width, panel_height, edge

    return None

def _show_wmm_menu(x, y):
    """Muestra el menú WMM contra el borde interior del panel XFCE."""
    global menu_anchor_edge
    global menu_anchor_coordinate

    if wmm_menu is None:
        return GLib.SOURCE_REMOVE

    root = Gdk.get_default_root_window()
    if root is None:
        return GLib.SOURCE_REMOVE

    panel_geometry = _get_panel_geometry_at_point(x, y)
    if panel_geometry is None:
        return GLib.SOURCE_REMOVE

    panel_x, panel_y, panel_width, panel_height, edge = panel_geometry

    rect = Gdk.Rectangle()
    rect.width = 1
    rect.height = 1

    if edge == "top":
        rect.x = x
        rect.y = panel_y + panel_height
        rect_anchor = Gdk.Gravity.SOUTH
        menu_anchor = Gdk.Gravity.NORTH
        menu_anchor_coordinate = rect.y

    elif edge == "left":
        rect.x = panel_x + panel_width
        rect.y = y
        rect_anchor = Gdk.Gravity.EAST
        menu_anchor = Gdk.Gravity.WEST
        menu_anchor_coordinate = rect.x

    elif edge == "right":
        rect.x = panel_x
        rect.y = y
        rect_anchor = Gdk.Gravity.WEST
        menu_anchor = Gdk.Gravity.EAST
        menu_anchor_coordinate = rect.x

    else:
        rect.x = x
        rect.y = panel_y
        rect_anchor = Gdk.Gravity.NORTH
        menu_anchor = Gdk.Gravity.SOUTH
        menu_anchor_coordinate = rect.y

    menu_anchor_edge = edge

    # StatusNotifierItem sólo entrega Activate(x, y) por D-Bus; el Gdk.Event
    # original ya no existe. Pasar None es deliberado: GTK3 intenta usar el
    # evento actual y avisa "no trigger event for menu popup" al no encontrarlo.
    # No sintetizar un evento: SNI no conserva botón, timestamp, dispositivo ni
    # modificadores, y falsearlos sólo ocultaría el warning sin normalizar el flujo.
    wmm_menu.popup_at_rect(root, rect, rect_anchor, menu_anchor, None,)

    print(f"[WMM XFCE] Gtk.Menu abierto desde panel {edge} "
        f"({panel_x},{panel_y},{panel_width}x{panel_height})",
        flush=True,)

    return GLib.SOURCE_REMOVE

# ==========================================================
# STATUSNOTIFIERITEM: CALLBACKS
# ==========================================================

def _on_method_call(connection, sender, object_path, interface_name,
                    method_name, parameters, invocation):
    """Recibe los eventos enviados por el StatusNotifier de XFCE."""
    values = parameters.unpack()

    if method_name == "Activate":
        x, y = values
        print(f"[WMM XFCE] Activate: ({x}, {y})", flush=True)
        GLib.idle_add(_show_wmm_menu, x, y)

    elif method_name == "ContextMenu":
        x, y = values
        print(f"[WMM XFCE] ContextMenu: ({x}, {y})", flush=True)

    elif method_name == "SecondaryActivate":
        x, y = values
        print(f"[WMM XFCE] SecondaryActivate: ({x}, {y})", flush=True)

        # La activación secundaria de StatusNotifier se aprovecha como acceso
        # directo a Next Background, reutilizando el canal y anti-spam del engine.
        _send_action_to_engine(connection, {"action": "force_rotation"})

    elif method_name == "Scroll":
        delta, orientation = values
        print(f"[WMM XFCE] Scroll: {delta} ({orientation})", flush=True)

    invocation.return_value(None)

def _on_get_property(connection, sender, object_path, interface_name, property_name):
    """Entrega al StatusNotifier las propiedades públicas del frontend."""
    return PROPERTIES.get(property_name)

def _set_sni_icon(connection, icon_name):
    """Actualiza el icono publicado por StatusNotifier y avisa al host."""
    if PROPERTIES["IconName"].get_string() == icon_name:
        return

    PROPERTIES["IconName"] = GLib.Variant("s", icon_name)

    # StatusNotifier mantiene las propiedades en el frontend; NewIcon indica
    # al host que debe volver a leer IconName después de un cambio de estado.
    connection.emit_signal(
        None, OBJECT_PATH, SNI_INTERFACE, "NewIcon", None,)

def _on_watcher_appeared(connection, _name, _name_owner):
    """Registra WMM cuando el StatusNotifierWatcher está disponible."""
    try:
        connection.call_sync(
            WATCHER_BUS,
            WATCHER_PATH,
            WATCHER_INTERFACE,
            "RegisterStatusNotifierItem",
            GLib.Variant("(s)", (BUS_NAME,)),
            None, Gio.DBusCallFlags.NONE, -1, None,)
    except GLib.Error as error:
        print(f"[WMM XFCE] No se pudo registrar StatusNotifier: {error}", flush=True,)
        return

    print("[WMM XFCE] StatusNotifier registrado", flush=True)


def _on_watcher_vanished(_connection, _name):
    """Mantiene vivo el frontend hasta que el StatusNotifierWatcher reaparezca."""
    print("[WMM XFCE] StatusNotifierWatcher no disponible; esperando", flush=True)

# ==========================================================
# CICLO DE VIDA DEL FRONTEND
# ==========================================================

def main():
    """Registra WMM como StatusNotifierItem y mantiene vivo el frontend."""
    global wmm_menu
    global frontend_loop
    global status_notifier_watch_id

    Gtk.init(None)
    _load_wmm_css()
    _set_frontend_identity()

    connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)

    name_reply = connection.call_sync(
        "org.freedesktop.DBus",
        "/org/freedesktop/DBus",
        "org.freedesktop.DBus",
        "RequestName",
        GLib.Variant("(su)", (BUS_NAME, 4)),
        GLib.VariantType.new("(u)"),
        Gio.DBusCallFlags.NONE, -1, None,)

    if name_reply.unpack()[0] != 1:
        print("[WMM XFCE] Frontend ya activo; segundo lanzamiento ignorado", flush=True)
        return

    # Suscribirse antes de StartServiceByName evita perder un cambio emitido
    # entre el arranque del engine y las lecturas iniciales GetSettings/GetBookmarks.
    settings_signal_id = connection.signal_subscribe(
        ENGINE_BUS,
        "org.maki.wmm",
        "SettingsChanged",
        "/org/maki/wmm",
        None,
        Gio.DBusSignalFlags.NONE,
        _on_settings_changed,)

    bookmarks_signal_id = connection.signal_subscribe(
        ENGINE_BUS,
        "org.maki.wmm",
        "BookmarksChanged",
        "/org/maki/wmm",
        None,
        Gio.DBusSignalFlags.NONE,
        _on_bookmarks_changed,)

    busy_signal_id = connection.signal_subscribe(
        ENGINE_BUS,
        "org.maki.wmm",
        "BusyChanged",
        "/org/maki/wmm",
        None,
        Gio.DBusSignalFlags.NONE,
        _on_busy_changed,)

    sni_node_info = Gio.DBusNodeInfo.new_for_xml(INTROSPECTION_XML)
    menu_node_info = Gio.DBusNodeInfo.new_for_xml(DBUSMENU_XML)

    sni_registration_id = connection.register_object(
        OBJECT_PATH,
        sni_node_info.interfaces[0],
        _on_method_call,
        _on_get_property, None,)

    menu_registration_id = connection.register_object(
        MENU_PATH,
        menu_node_info.interfaces[0],
        _on_context_menu_method_call,
        _on_context_menu_get_property, None,)

    # La activación sólo solicita el arranque. La aparición real del nombre
    # D-Bus determina cuándo el engine está listo para sincronizar el frontend.
    engine_watch_id = Gio.bus_watch_name_on_connection(
        connection, ENGINE_BUS,
        Gio.BusNameWatcherFlags.NONE,
        _on_engine_appeared,
        _on_engine_vanished,)

    _start_engine(connection)

    frontend_loop = GLib.MainLoop()

    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, _quit_frontend)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, _quit_frontend)

    try:
        frontend_loop.run()

    finally:
        Gio.bus_unwatch_name(engine_watch_id)

        if status_notifier_watch_id is not None:
            Gio.bus_unwatch_name(status_notifier_watch_id)
            status_notifier_watch_id = None

        connection.signal_unsubscribe(settings_signal_id)
        connection.signal_unsubscribe(bookmarks_signal_id)
        connection.signal_unsubscribe(busy_signal_id)

        if wmm_menu is not None:
            wmm_menu.popdown()
            wmm_menu = None

        connection.unregister_object(menu_registration_id)
        connection.unregister_object(sni_registration_id)

        connection.call_sync(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            "ReleaseName",
            GLib.Variant("(s)", (BUS_NAME,)),
            GLib.VariantType.new("(u)"),
            Gio.DBusCallFlags.NONE, -1, None,)

        print("[WMM XFCE] Frontend detenido", flush=True)
        frontend_loop = None

if __name__ == "__main__":
    main()
