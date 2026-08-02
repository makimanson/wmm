#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
WMM - Monitor Detection Engine
===============================
Centraliza todas las estrategias de detección de monitores para WMM.

Este módulo se encarga de:
    - Detectar el entorno (X11, Wayland, escritorio, etc.).
    - Seleccionar la mejor estrategia de detección disponible.
    - Devolver un diccionario de monitores con geometría e identificadores.

No depende de GTK, ni de la plataforma directamente. Solo usa los módulos
de plataforma (linux, gnome, etc.) para obtener la información.

Flujo típico:
    1. main.py llama a monitor_detection.detect_monitors().
    2. El módulo decide qué estrategia usar (X11, GNOME D-Bus, GDK fallback).
    3. Devuelve el diccionario de monitores (mismo formato que get_x11_monitors).

Autor: WMM Project
Fecha: 2026-08-02 (Refactorización desde linux.py y gnome.py)
"""

import os
import sys
import hashlib
import ctypes
import ctypes.util
import fcntl
import gi
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk

from monitor_manager import calculate_inches
from debug_logger import log_event


# ==========================================================
# 1. Estrategia para X11 (copiada de linux.get_x11_monitors)
# ==========================================================
def get_x11_monitors():
    """
    Obtiene monitores usando libXrandr (X11).
    Retorna un diccionario {hash: {connector, manufacturer, x, y, width, height,
                                    width_mm, height_mm, inches, orientation, primary}}
    """
    # Cargar las bibliotecas nativas de X11
    libX11 = ctypes.cdll.LoadLibrary(ctypes.util.find_library("X11"))
    libXrandr = ctypes.cdll.LoadLibrary(ctypes.util.find_library("Xrandr"))

    # Abrir la conexión al servidor X
    display = libX11.XOpenDisplay(None)
    if not display:
        raise RuntimeError("No se pudo abrir la conexión a X11")

    screen = libX11.XDefaultScreen(display)
    root = libX11.XRootWindow(display, screen)

    # Estructuras para XRRScreenResources
    class XRRScreenResources(ctypes.Structure):
        _fields_ = [
            ("timestamp", ctypes.c_ulong),
            ("configTimestamp", ctypes.c_ulong),
            ("ncrtc", ctypes.c_int),
            ("crtcs", ctypes.POINTER(ctypes.c_ulong)),
            ("noutput", ctypes.c_int),
            ("outputs", ctypes.POINTER(ctypes.c_ulong)),
            ("nmode", ctypes.c_int),
            ("modes", ctypes.c_void_p),
        ]

    libXrandr.XRRGetScreenResourcesCurrent.restype = ctypes.POINTER(XRRScreenResources)
    resources = libXrandr.XRRGetScreenResourcesCurrent(display, root)

    class XRROutputInfo(ctypes.Structure):
        _fields_ = [
            ("timestamp", ctypes.c_ulong),
            ("crtc", ctypes.c_ulong),
            ("name", ctypes.c_char_p),
            ("nameLen", ctypes.c_int),
            ("mm_width", ctypes.c_ulong),
            ("mm_height", ctypes.c_ulong),
            ("connection", ctypes.c_short),
            ("subpixel_order", ctypes.c_short),
            ("ncrtc", ctypes.c_int),
            ("crtcs", ctypes.POINTER(ctypes.c_ulong)),
            ("nclone", ctypes.c_int),
            ("clones", ctypes.POINTER(ctypes.c_ulong)),
            ("nmode", ctypes.c_int),
            ("npreferred", ctypes.c_int),
            ("modes", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class XRRCrtcInfo(ctypes.Structure):
        _fields_ = [
            ("timestamp", ctypes.c_ulong),
            ("x", ctypes.c_int),
            ("y", ctypes.c_int),
            ("width", ctypes.c_uint),
            ("height", ctypes.c_uint),
            ("mode", ctypes.c_ulong),
            ("rotation", ctypes.c_ushort),
            ("noutput", ctypes.c_int),
            ("outputs", ctypes.POINTER(ctypes.c_ulong)),
            ("rotations", ctypes.c_ushort),
            ("npossible", ctypes.c_int),
            ("possible", ctypes.POINTER(ctypes.c_ulong)),
        ]

    libXrandr.XRRGetOutputInfo.restype = ctypes.POINTER(XRROutputInfo)
    libXrandr.XRRGetCrtcInfo.restype = ctypes.POINTER(XRRCrtcInfo)
    libXrandr.XRRGetOutputPrimary.restype = ctypes.c_ulong
    primary_output = libXrandr.XRRGetOutputPrimary(display, root)

    monitors_data = {}
    for i in range(resources.contents.noutput):
        output = resources.contents.outputs[i]
        info = libXrandr.XRRGetOutputInfo(display, resources, output)
        if not info:
            continue
        info = info.contents
        if info.connection != 0:  # 0 = RR_Connected
            continue
        connector = ctypes.string_at(info.name, info.nameLen).decode()
        if info.crtc == 0:
            continue
        crtc = libXrandr.XRRGetCrtcInfo(display, resources, info.crtc)
        if not crtc:
            continue
        crtc = crtc.contents

        # Obtener EDID para hash estable
        edid_atom_name = ctypes.c_char_p(b"EDID")
        edid_atom = libX11.XInternAtom(display, edid_atom_name, 0)
        actual_type = ctypes.c_ulong()
        actual_format = ctypes.c_int()
        nitems = ctypes.c_ulong()
        bytes_after = ctypes.c_ulong()
        prop = ctypes.POINTER(ctypes.c_ubyte)()
        status = libXrandr.XRRGetOutputProperty(
            display, output, edid_atom, 0, 256, 0, 0, 0,
            ctypes.byref(actual_type), ctypes.byref(actual_format),
            ctypes.byref(nitems), ctypes.byref(bytes_after), ctypes.byref(prop)
        )

        unique_id = None
        if status == 0 and prop and nitems.value >= 128:
            edid_data = bytes(prop[i] for i in range(nitems.value))
            for offset in range(54, 126, 18):
                block = edid_data[offset:offset+18]
                if len(block) < 18:
                    break
                if block[0] == 0 and block[1] == 0 and block[2] == 0:
                    tag = block[3]
                    text = block[5:18].replace(b'\n', b'').decode("ascii", errors="ignore").strip()
                    if tag == 255 and text:
                        unique_id = text
                        break
        if not unique_id:
            unique_id = connector

        m_hash = hashlib.shake_128(unique_id.encode()).hexdigest(4)

        # Extraer fabricante y modelo
        manufacturer = None
        model = None
        if prop and nitems.value >= 128:
            edid_data = bytes(prop[i] for i in range(min(128, nitems.value)))
            mfg_bytes = int.from_bytes(edid_data[8:10], 'big')
            manufacturer = ''.join([
                chr(((mfg_bytes >> 10) & 0x1F) + ord('A') - 1),
                chr(((mfg_bytes >> 5) & 0x1F) + ord('A') - 1),
                chr((mfg_bytes & 0x1F) + ord('A') - 1)
            ])
            for offset in range(54, 126, 18):
                block = edid_data[offset:offset+18]
                if len(block) < 18:
                    break
                if block[0] == 0 and block[1] == 0 and block[3] == 0xFC:
                    name_bytes = block[5:18]
                    model = name_bytes.split(b'\x0A')[0].decode('ascii', errors='ignore').strip()
                    break

        if not manufacturer:
            manufacturer = "Unknown"

        orientation = "horizontal" if crtc.width >= crtc.height else "vertical"
        inches = calculate_inches(info.mm_width, info.mm_height)

        monitors_data[m_hash] = {
            "connector": connector,
            "manufacturer": manufacturer,
            "model": model,
            "x": crtc.x,
            "y": crtc.y,
            "width": crtc.width,
            "height": crtc.height,
            "width_mm": info.mm_width,
            "height_mm": info.mm_height,
            "inches": inches,
            "orientation": orientation,
            "primary": (output == primary_output),
        }

    libX11.XCloseDisplay(display)
    return monitors_data


# ==========================================================
# 2. Estrategia para GNOME Wayland (copiada de gnome.get_monitors_from_dbus)
# ==========================================================
def get_gnome_wayland_monitors():
    """
    Obtiene monitores usando D-Bus de Mutter (GNOME Wayland).
    Combina GetCurrentState (geometría) y GetResources (current_crtc, dimensiones físicas).
    """
    try:
        import dbus
        from monitor_manager import calculate_inches

        bus = dbus.SessionBus()
        display_config = bus.get_object(
            "org.gnome.Mutter.DisplayConfig",
            "/org/gnome/Mutter/DisplayConfig"
        )

        # GetCurrentState para posición y modos activos
        state = display_config.GetCurrentState(dbus_interface="org.gnome.Mutter.DisplayConfig")
        outputs_curr = state[1]
        logical_monitors = state[2]

        # GetResources para CRTCs y outputs con dimensiones físicas
        resources = display_config.GetResources(dbus_interface="org.gnome.Mutter.DisplayConfig")
        crtcs = resources[1]
        outputs_res = resources[2] if len(resources) > 2 else []

        # Construir mapa de CRTC por ID
        crtc_by_id = {}
        for crtc in crtcs:
            crtc_id = crtc[0]
            crtc_by_id[crtc_id] = {
                'x': int(crtc[2]),
                'y': int(crtc[3]),
                'width': int(crtc[4]),
                'height': int(crtc[5]),
                'current_mode': crtc[6],
                'current_transform': crtc[7],
            }

        # Construir mapa de output por conector (desde GetResources)
        output_by_connector = {}
        for output in outputs_res:
            # output = (id, winsys_id, current_crtc, possible_crtcs, name, modes, encoders, props)
            output_id = output[0]
            current_crtc = output[2]
            name = output[4] if len(output) > 4 else "Unknown"
            props = output[7] if len(output) > 7 else {}
            output_by_connector[name] = {
                'id': output_id,
                'current_crtc': current_crtc,
                'props': props,
            }

        # Construir mapa de posición -> conector desde logical_monitors
        pos_to_connector = {}
        for logical in logical_monitors:
            x = int(logical[0])
            y = int(logical[1])
            connector_list = logical[5]
            if connector_list:
                connector_name = connector_list[0][0]
                pos_to_connector[(x, y)] = connector_name

        monitors = {}
        for (x, y), connector_name in pos_to_connector.items():
            output_info = output_by_connector.get(connector_name)
            if not output_info:
                continue
            crtc_id = output_info['current_crtc']
            crtc_data = crtc_by_id.get(crtc_id)
            if not crtc_data:
                continue

            width = crtc_data['width']
            height = crtc_data['height']
            if width == 0 or height == 0:
                # fallback al modo activo de GetCurrentState
                for output in outputs_curr:
                    if output[0][0] == connector_name:
                        for mode in output[1]:
                            if len(mode) > 6 and mode[6].get('is-current', False):
                                width = int(mode[1])
                                height = int(mode[2])
                                break
                        break

            props = output_info['props']
            manufacturer = props.get('vendor', '')
            model = props.get('product', '')
            serial = props.get('serial', '')
            width_mm = int(props.get('width-mm', 0))
            height_mm = int(props.get('height-mm', 0))
            is_primary = bool(props.get('primary', False))

            orientation = "horizontal" if width >= height else "vertical"
            inches = calculate_inches(width_mm, height_mm)

            if serial and serial not in ("0x00000000", "00000000"):
                hash_base = f"{manufacturer}_{model}_{serial}"
            else:
                hash_base = f"{manufacturer}_{model}_{connector_name}"
            unique_hash = f"{hash_base}_{connector_name}"
            monitor_hash = hashlib.shake_128(unique_hash.encode()).hexdigest(4)

            monitors[monitor_hash] = {
                "connector": connector_name,
                "manufacturer": manufacturer,
                "model": model,
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "width_mm": width_mm,
                "height_mm": height_mm,
                "inches": inches,
                "orientation": orientation,
                "primary": is_primary,
            }

        log_event(f"Monitores obtenidos desde D-Bus: {len(monitors)}", origin="MON_DETECT", level="DEBUG", reason="HARDWARE")
        return monitors

    except Exception as e:
        log_event(f"Error en GNOME D-Bus: {e}", origin="MON_DETECT", level="ERROR", reason="HARDWARE")
        return {}


# ==========================================================
# 3. Estrategia de fallback para Wayland (copiada del bloque GDK en linux.get_monitors)
# ==========================================================
def get_gdk_wayland_monitors():
    """
    Obtiene monitores usando Gdk (fallback genérico para Wayland).
    Proporciona geometría básica pero sin orientación ni dimensiones físicas.
    """
    display = Gdk.Display.get_default()
    if not display:
        return {}
    display.sync()

    monitors_data = {}
    n_monitors = display.get_n_monitors()
    for i in range(n_monitors):
        monitor = display.get_monitor(i)
        geometry = monitor.get_geometry()
        connector = monitor.get_model() or "Unknown"
        manufacturer = monitor.get_manufacturer() or "Unknown"
        w_mm = monitor.get_width_mm()
        h_mm = monitor.get_height_mm()
        is_primary = monitor.is_primary()

        m_hash = hashlib.shake_128(f"{connector}-{manufacturer}-{geometry.x}-{geometry.y}".encode()).hexdigest(4)
        orientation = "horizontal" if geometry.width >= geometry.height else "vertical"
        inches = calculate_inches(w_mm, h_mm)

        monitors_data[m_hash] = {
            "connector": connector,
            "manufacturer": manufacturer,
            "model": None,  # GDK no proporciona modelo en Wayland
            "x": geometry.x,
            "y": geometry.y,
            "width": geometry.width,
            "height": geometry.height,
            "width_mm": w_mm,
            "height_mm": h_mm,
            "inches": inches,
            "orientation": orientation,
            "primary": is_primary,
        }
    return monitors_data


# ==========================================================
# 4. Orquestador principal
# ==========================================================
def detect_monitors():
    """
    Devuelve el diccionario de monitores usando la mejor estrategia disponible.
    Estrategias (por orden de prioridad):
        1. X11 → get_x11_monitors()
        2. Wayland + GNOME → get_gnome_wayland_monitors()
        3. Wayland + otros → get_gdk_wayland_monitors()
        4. Fallback → {}
    """
    from wmm_platform.core import PlatformManager
    pm = PlatformManager()
    desktop = getattr(pm, 'desktop', None)
    graphics_engine = getattr(pm, 'graphics_engine', 'x11')

    # 1. X11
    if graphics_engine == 'x11':
        log_event("Detección X11 usando libXrandr", origin="MON_DETECT", level="DEBUG", reason="HARDWARE")
        return get_x11_monitors()

    # 2. GNOME Wayland
    if graphics_engine == 'wayland' and desktop == 'gnome':
        log_event("Detección GNOME Wayland usando D-Bus", origin="MON_DETECT", level="DEBUG", reason="HARDWARE")
        monitors = get_gnome_wayland_monitors()
        if monitors:
            return monitors
        else:
            log_event("D-Bus falló, usando fallback GDK", origin="MON_DETECT", level="WARN", reason="HARDWARE")

    # 3. Fallback GDK para cualquier otro caso
    log_event("Detección genérica Wayland usando GDK", origin="MON_DETECT", level="DEBUG", reason="HARDWARE")
    return get_gdk_wayland_monitors()
