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
    - Iniciar la escucha de eventos mediante la estrategia adecuada al entorno.
    - Notificar al motor cuando se produce un cambio.

Centraliza directamente las estrategias de monitorización específicas de cada
entorno y notifica al motor mediante un callback común.

Flujo típico:
    1. main.py llama a monitor_events.init_monitor_events(callback).
    2. El módulo selecciona la estrategia nativa del entorno.
    3. Inicia la escucha y llama al callback cuando se detecta un cambio.

"""

import ctypes
import threading

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
_windows_event_thread = None

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
# 2. Estrategia para Windows (Win32)
# ==========================================================
def init_windows_events(callback):
    """
    Escucha cambios de configuración de pantalla mediante WM_DISPLAYCHANGE.

    Win32 necesita un message loop propio; se ejecuta en un hilo dedicado y
    devuelve el evento al main loop de WMM antes de invocar el callback.
    """
    global _windows_event_thread

    if (_windows_event_thread is not None and _windows_event_thread.is_alive()):
        return True

    try:
        import gi
        gi.require_version('GLib', '2.0')
        from gi.repository import GLib

        # Estos tipos sólo existen en monitor_detection bajo Windows.
        from monitor_detection import (_MSG, _WNDCLASSW, _WNDPROC, get_windows_display_api)

        user32, _setupapi, _advapi32, kernel32 = get_windows_display_api()

        WM_DESTROY = 0x0002
        WM_DISPLAYCHANGE = 0x007E
        class_name = "WMMMonitorEventsWindow"

        ready = threading.Event()
        started = {"ok": False}

        def _run_windows_events():
            hwnd = None
            class_registered = False

            try:
                hinstance = kernel32.GetModuleHandleW(None)
                if not hinstance:
                    raise ctypes.WinError(ctypes.get_last_error())

                @_WNDPROC
                def wnd_proc(hwnd, message, wparam, lparam):
                    if message == WM_DISPLAYCHANGE:
                        log_event("Evento WM_DISPLAYCHANGE recibido",
                            origin="MON_EVENT", level="DEBUG", reason="HARDWARE")
                        GLib.idle_add(callback, "hardware_changed")
                        return 0

                    if message == WM_DESTROY:
                        user32.PostQuitMessage(0)
                        return 0

                    return user32.DefWindowProcW(hwnd, message, wparam, lparam)

                window_class = _WNDCLASSW()
                window_class.lpfnWndProc = wnd_proc
                window_class.hInstance = hinstance
                window_class.lpszClassName = class_name

                if not user32.RegisterClassW(ctypes.byref(window_class)):
                    raise ctypes.WinError(ctypes.get_last_error())

                class_registered = True

                # Sin WS_VISIBLE y sin parent sigue siendo una ventana top-level,
                # necesaria para recibir WM_DISPLAYCHANGE broadcast.
                hwnd = user32.CreateWindowExW( 0, class_name, "WMM Monitor Events",
                    0, 0, 0, 0, 0, None, None, hinstance, None, )

                if not hwnd:
                    raise ctypes.WinError(ctypes.get_last_error())

                started["ok"] = True
                ready.set()

                log_event("Monitorización Win32 iniciada (WM_DISPLAYCHANGE)",
                    origin="MON_EVENT", level="INFO", reason="HARDWARE")

                message = _MSG()

                while True:
                    result = user32.GetMessageW(
                        ctypes.byref(message), None, 0, 0)

                    if result == -1:
                        raise ctypes.WinError(ctypes.get_last_error())

                    if result == 0:
                        break

                    user32.DispatchMessageW(ctypes.byref(message))

            except Exception as e:
                log_event(f"Error en monitorización Win32: {e}",
                    origin="MON_EVENT", level="ERROR", reason="HARDWARE")

            finally:
                ready.set()

                if hwnd:
                    user32.DestroyWindow(hwnd)

                if class_registered:
                    user32.UnregisterClassW(class_name, hinstance)

        thread = threading.Thread( target=_run_windows_events, name="WMMMonitorEvents", daemon=True, )
        thread.start()

        # No devolvemos éxito hasta que RegisterClass/CreateWindow hayan
        # terminado; Event sincroniza sin polling ni retardos arbitrarios.
        ready.wait()

        if not started["ok"]:
            return False

        _windows_event_thread = thread
        return True

    except Exception as e:
        log_event(f"No se pudo iniciar monitorización Win32: {e}",
            origin="MON_EVENT", level="ERROR", reason="HARDWARE")
        return False

# ==========================================================
# 3. Estrategia para GNOME (D-Bus)
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

        _gnome_bus = dbus.SessionBus(private=True, mainloop=DBusGMainLoop())

        display_config = _gnome_bus.get_object(
            "org.gnome.Mutter.DisplayConfig",
            "/org/gnome/Mutter/DisplayConfig")

        def on_monitors_changed(*args):
            log_event("Señal MonitorsChanged recibida desde D-Bus",
                origin="MON_EVENT", level="DEBUG", reason="HARDWARE")
            callback("hardware_changed")

        _gnome_signal_match = display_config.connect_to_signal("MonitorsChanged", on_monitors_changed)

        log_event("Monitor D-Bus de GNOME iniciado correctamente",
            origin="MON_EVENT", level="INFO", reason="D-BUS")
        return True

    except Exception as e:
        log_event(f"Error al iniciar monitor D-Bus de GNOME: {e}",
            origin="MON_EVENT", level="ERROR", reason="D-BUS")
        return False

# ==========================================================
# 4. Estrategia de fallback (Gdk signals)
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
            log_event("No se pudo obtener Gdk.Display para monitorización",
                origin="MON_EVENT", level="WARN", reason="HARDWARE")
            return False

        def _on_monitor_event(display, monitor):
            callback("hardware_changed")

        display.connect("monitor-added", _on_monitor_event)
        display.connect("monitor-removed", _on_monitor_event)

        log_event("Monitorización Gdk iniciada (fallback)",
            origin="MON_EVENT", level="INFO", reason="HARDWARE")
        return True

    except Exception as e:
        log_event(f"Error al iniciar monitorización Gdk: {e}",
            origin="MON_EVENT", level="ERROR", reason="HARDWARE")
        return False

# ==========================================================
# 5. Orquestador principal
# ==========================================================
def init_monitor_events(callback):
    """
    Inicia la monitorización de cambios de hardware según el entorno activo.

    Estrategias:
        - X11 → init_x11_events() (XRandR)
        - GNOME Wayland → init_gnome_events() (D-Bus)
        - Windows → init_windows_events() (WM_DISPLAYCHANGE)
        - Otros → init_gdk_events() (fallback)
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

    # 3. Windows: WM_DISPLAYCHANGE
    elif graphics_engine == 'win32' and desktop == 'windows':
        if init_windows_events(callback):
            return True
        log_event("Win32 falló, usando fallback Gdk",
            origin="MON_EVENT", level="WARN", reason="HARDWARE")

    # 4. Fallback: Gdk signals
    log_event("Usando monitorización Gdk (fallback)",
        origin="MON_EVENT", level="DEBUG", reason="HARDWARE")
    return init_gdk_events(callback)
