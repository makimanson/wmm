#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

"""
WMM - Wallpaper Multi-Monitor Manager

monitor_events.py - Monitor Events Engine
============================
Centraliza la monitorización de cambios de hardware (conexión/desconexión de monitores).

Este módulo se encarga de:
    - Detectar el entorno (escritorio, SO) y elegir la estrategia de monitorización adecuada.
    - Iniciar la escucha de eventos (D-Bus, Gdk, etc.).
    - Notificar al motor cuando se produce un cambio.

No depende de GTK ni de la lógica de negocio. Solo usa los módulos de plataforma
para implementar la monitorización específica de cada escritorio.

Flujo típico:
    1. main.py llama a monitor_events.init_monitor_events(callback).
    2. El módulo decide qué estrategia usar (GNOME D-Bus, fallback Gdk).
    3. Inicia la escucha y llama al callback cuando se detecta un cambio.

"""

import ctypes

from debug_logger import log_event
from monitor_detection import (
    XEvent, XRRNotifyEvent,
    RRNotify,
    RRCrtcChangeNotifyMask, RROutputChangeNotifyMask, RRResourceChangeNotifyMask,
    RRNotify_CrtcChange, RRNotify_OutputChange, RRNotify_ResourceChange,
    get_x11_randr_api,
)

_x11_display = None
_x11_io_channel = None
_gnome_bus = None
_gnome_signal_match = None

# ==========================================================
# 1. Estrategia para X11 (XRandR)
# ==========================================================
def init_x11_events(callback):
    """
    Escucha cambios relevantes de configuración X11 mediante XRandR.

    Sólo se solicitan cambios de CRTC, output y recursos. Los eventos recibidos
    durante una misma activación del main loop se consumen como una sola ráfaga;
    el engine conserva después su estabilización final de hardware.
    """
    global _x11_display, _x11_io_channel

    try:
        import gi
        gi.require_version('GLib', '2.0')
        from gi.repository import GLib

        libX11, libXrandr = get_x11_randr_api()

        display = libX11.XOpenDisplay(None)
        if not display:
            log_event("No se pudo abrir la conexión X11 para XRandR",
                origin="MON_EVENT", level="WARN", reason="HARDWARE")
            return False

        screen = libX11.XDefaultScreen(display)
        root = libX11.XRootWindow(display, screen)

        event_base = ctypes.c_int()
        error_base = ctypes.c_int()
        if not libXrandr.XRRQueryExtension(display, ctypes.byref(event_base), ctypes.byref(error_base)):
            libX11.XCloseDisplay(display)
            log_event("XRandR no está disponible en el servidor X11",
                origin="MON_EVENT", level="WARN", reason="HARDWARE")
            return False

        event_mask = (
            RRCrtcChangeNotifyMask
            | RROutputChangeNotifyMask
            | RRResourceChangeNotifyMask
        )
        relevant_subtypes = {
            RRNotify_CrtcChange: "CrtcChange",
            RRNotify_OutputChange: "OutputChange",
            RRNotify_ResourceChange: "ResourceChange",
        }

        libXrandr.XRRSelectInput(display, root, event_mask)
        libX11.XFlush(display)

        rr_notify_type = event_base.value + RRNotify

        def _on_x11_io(channel, condition):
            if condition & (GLib.IO_HUP | GLib.IO_ERR):
                log_event("Conexión XRandR cerrada",
                    origin="MON_EVENT", level="WARN", reason="HARDWARE")
                return False

            received = set()

            while libX11.XPending(display):
                event = XEvent()
                libX11.XNextEvent(display, ctypes.byref(event))

                if event.type != rr_notify_type:
                    continue

                rr_event = ctypes.cast(
                    ctypes.byref(event),
                    ctypes.POINTER(XRRNotifyEvent)
                ).contents

                event_name = relevant_subtypes.get(rr_event.subtype)
                if event_name:
                    received.add(event_name)

            if received:
                log_event(f"Evento XRandR relevante: {', '.join(sorted(received))}",
                    origin="MON_EVENT", level="DEBUG", reason="HARDWARE")
                callback("hardware_changed")

            return True

        fd = libX11.XConnectionNumber(display)
        _x11_io_channel = GLib.IOChannel.unix_new(fd)
        _x11_display = display
        GLib.io_add_watch(
            _x11_io_channel,
            GLib.IO_IN | GLib.IO_HUP | GLib.IO_ERR,
            _on_x11_io
        )

        log_event("Monitorización XRandR iniciada",
            origin="MON_EVENT", level="INFO", reason="HARDWARE")
        return True

    except Exception as e:
        log_event(f"Error al iniciar monitorización XRandR: {e}",
            origin="MON_EVENT", level="ERROR", reason="HARDWARE")
        return False

# ==========================================================
# 2. Estrategia para GNOME (D-Bus)
# ==========================================================
def init_gnome_events(callback):
    """
    Inicia la monitorización de hardware en GNOME usando D-Bus
    (org.gnome.Mutter.DisplayConfig).

    La conexión D-Bus es privada y dispone de su propio DBusGMainLoop,
    evitando depender de un main loop global compartido con otros
    componentes de WMM.
    """
    global _gnome_bus, _gnome_signal_match

    try:
        import dbus
        from dbus.mainloop.glib import DBusGMainLoop

        _gnome_bus = dbus.SessionBus(
            private=True,
            mainloop=DBusGMainLoop()
        )

        display_config = _gnome_bus.get_object(
            "org.gnome.Mutter.DisplayConfig",
            "/org/gnome/Mutter/DisplayConfig"
        )

        def on_monitors_changed(*args):
            log_event("Señal MonitorsChanged recibida desde D-Bus", origin="MON_EVENT", level="DEBUG", reason="HARDWARE")
            callback("hardware_changed")

        _gnome_signal_match = display_config.connect_to_signal(
            "MonitorsChanged",
            on_monitors_changed
        )

        log_event("Monitor D-Bus de GNOME iniciado correctamente", origin="MON_EVENT", level="INFO", reason="D-BUS")
        return True

    except Exception as e:
        log_event(f"Error al iniciar monitor D-Bus de GNOME: {e}", origin="MON_EVENT", level="ERROR", reason="D-BUS")
        return False

# ==========================================================
# 3. Estrategia de fallback (Gdk signals)
# ==========================================================
def init_gdk_events(callback):
    """
    Inicia la monitorización de hardware usando señales de Gdk.
    Es el fallback genérico para escritorios sin método específico.
    """
    try:
        import gi
        gi.require_version('Gdk', '3.0')
        from gi.repository import Gdk

        display = Gdk.Display.get_default()
        if not display:
            log_event("No se pudo obtener Gdk.Display para monitorización", origin="MON_EVENT", level="WARN", reason="HARDWARE")
            return False

        def _on_monitor_event(display, monitor):
            callback("hardware_changed")

        display.connect("monitor-added", _on_monitor_event)
        display.connect("monitor-removed", _on_monitor_event)

        log_event("Monitorización Gdk iniciada (fallback)", origin="MON_EVENT", level="INFO", reason="HARDWARE")
        return True

    except Exception as e:
        log_event(f"Error al iniciar monitorización Gdk: {e}", origin="MON_EVENT", level="ERROR", reason="HARDWARE")
        return False

# ==========================================================
# 4. Orquestador principal
# ==========================================================
def init_monitor_events(callback):
    """
    Inicia la monitorización de cambios de hardware usando la mejor estrategia disponible.
    Estrategias (por orden de prioridad):
        1. X11 → init_x11_events() (XRandR)
        2. GNOME Wayland → init_gnome_events() (D-Bus)
        3. Otros → init_gdk_events() (fallback)
    """
    from wmm_platform.core import PlatformManager

    pm = PlatformManager()
    desktop = getattr(pm, 'desktop', None)
    graphics_engine = getattr(pm, 'graphics_engine', 'x11')

    # 1. X11: XRandR
    if graphics_engine == 'x11':
        log_event("Intentando monitorización X11 vía XRandR",
            origin="MON_EVENT", level="DEBUG", reason="HARDWARE")
        if init_x11_events(callback):
            return True

        log_event("XRandR falló, usando fallback Gdk",
            origin="MON_EVENT", level="WARN", reason="HARDWARE")

    # 2. GNOME Wayland: D-Bus
    elif desktop == "gnome":
        log_event("Intentando monitorización GNOME vía D-Bus",
            origin="MON_EVENT", level="DEBUG", reason="HARDWARE")
        if init_gnome_events(callback):
            return True

        log_event("D-Bus falló, usando fallback Gdk",
            origin="MON_EVENT", level="WARN", reason="HARDWARE")

    # 3. Fallback: Gdk signals
    log_event("Usando monitorización Gdk (fallback)",
        origin="MON_EVENT", level="DEBUG", reason="HARDWARE")
    return init_gdk_events(callback)
