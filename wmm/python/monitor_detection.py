#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

"""
WMM - Wallpaper Multi-Monitor Manager

monitor_detection.py - Monitor Detection Engine
===============================
Centraliza todas las estrategias de detección de monitores para WMM.

Este módulo se encarga de:
    - Detectar el entorno (X11, Wayland, escritorio, etc.).
    - Seleccionar la mejor estrategia de detección disponible.
    - Devolver un diccionario de monitores con geometría e identificadores.

Centraliza directamente las estrategias de detección específicas de cada
entorno y devuelve sus resultados mediante el contrato común de WMM.

Flujo típico:
    1. main.py llama a monitor_detection.detect_monitors().
    2. El módulo selecciona la estrategia de detección adecuada al entorno.
    3. Devuelve el diccionario de monitores usando el contrato común de WMM.
"""

import os
import sys
import glob
import json
import subprocess
import hashlib
import ctypes
import ctypes.util
import gi

gi.require_version('Gdk', '3.0')

from gi.repository import Gdk
from monitor_manager import calculate_inches
from debug_logger import log_event

# ==========================================================
# ESTRUCTURAS NATIVAS XRandR
# ==========================================================
# Deben existir una sola vez a nivel de módulo.
# ctypes mantiene en caché los tipos creados con POINTER(); redefinir estas
# estructuras dentro de get_x11_monitors() hacía crecer esa caché en cada
# detección de monitores.
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

class XEvent(ctypes.Union):
    _fields_ = [
        ("type", ctypes.c_int),
        ("pad", ctypes.c_long * 24),
    ]


class XRRNotifyEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("serial", ctypes.c_ulong),
        ("send_event", ctypes.c_int),
        ("display", ctypes.c_void_p),
        ("window", ctypes.c_ulong),
        ("subtype", ctypes.c_int),
    ]


# Eventos XRandR relevantes para WMM.
RRNotify = 1
RRCrtcChangeNotifyMask = 1 << 1
RROutputChangeNotifyMask = 1 << 2
RRResourceChangeNotifyMask = 1 << 6

RRNotify_CrtcChange = 0
RRNotify_OutputChange = 1
RRNotify_ResourceChange = 5


_libX11 = None
_libXrandr = None


def get_x11_randr_api():
    """
    Devuelve la API nativa X11/XRandR común utilizada por detección y eventos.

    Las bibliotecas y sus firmas ctypes se inicializan una sola vez. Las
    conexiones Display siguen perteneciendo a cada consumidor: detección usa
    conexiones puntuales y monitor_events mantendrá la suya persistente.
    """
    global _libX11, _libXrandr

    if _libX11 is not None and _libXrandr is not None:
        return _libX11, _libXrandr

    libX11 = ctypes.cdll.LoadLibrary(ctypes.util.find_library("X11"))
    libXrandr = ctypes.cdll.LoadLibrary(ctypes.util.find_library("Xrandr"))

    # Xlib común
    libX11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    libX11.XOpenDisplay.restype = ctypes.c_void_p
    libX11.XDefaultScreen.argtypes = [ctypes.c_void_p]
    libX11.XDefaultScreen.restype = ctypes.c_int
    libX11.XRootWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
    libX11.XRootWindow.restype = ctypes.c_ulong
    libX11.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    libX11.XInternAtom.restype = ctypes.c_ulong
    libX11.XConnectionNumber.argtypes = [ctypes.c_void_p]
    libX11.XConnectionNumber.restype = ctypes.c_int
    libX11.XPending.argtypes = [ctypes.c_void_p]
    libX11.XPending.restype = ctypes.c_int
    libX11.XNextEvent.argtypes = [ctypes.c_void_p, ctypes.POINTER(XEvent)]
    libX11.XNextEvent.restype = ctypes.c_int
    libX11.XFlush.argtypes = [ctypes.c_void_p]
    libX11.XFlush.restype = ctypes.c_int
    libX11.XCloseDisplay.argtypes = [ctypes.c_void_p]
    libX11.XCloseDisplay.restype = ctypes.c_int
    libX11.XFree.argtypes = [ctypes.c_void_p]
    libX11.XFree.restype = ctypes.c_int

    # XRandR: detección
    libXrandr.XRRGetScreenResourcesCurrent.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    libXrandr.XRRGetScreenResourcesCurrent.restype = ctypes.POINTER(XRRScreenResources)
    libXrandr.XRRFreeScreenResources.argtypes = [ctypes.POINTER(XRRScreenResources)]
    libXrandr.XRRFreeScreenResources.restype = None
    libXrandr.XRRGetOutputInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(XRRScreenResources), ctypes.c_ulong]
    libXrandr.XRRGetOutputInfo.restype = ctypes.POINTER(XRROutputInfo)
    libXrandr.XRRFreeOutputInfo.argtypes = [ctypes.POINTER(XRROutputInfo)]
    libXrandr.XRRFreeOutputInfo.restype = None
    libXrandr.XRRGetCrtcInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(XRRScreenResources), ctypes.c_ulong]
    libXrandr.XRRGetCrtcInfo.restype = ctypes.POINTER(XRRCrtcInfo)
    libXrandr.XRRFreeCrtcInfo.argtypes = [ctypes.POINTER(XRRCrtcInfo)]
    libXrandr.XRRFreeCrtcInfo.restype = None
    libXrandr.XRRGetOutputPrimary.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    libXrandr.XRRGetOutputPrimary.restype = ctypes.c_ulong
    libXrandr.XRRGetOutputProperty.argtypes = [
        ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong,
        ctypes.c_long, ctypes.c_long, ctypes.c_int, ctypes.c_int, ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.POINTER(ctypes.c_ubyte)),
    ]
    libXrandr.XRRGetOutputProperty.restype = ctypes.c_int

    # XRandR: eventos
    libXrandr.XRRQueryExtension.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_int),
    ]
    libXrandr.XRRQueryExtension.restype = ctypes.c_int
    libXrandr.XRRSelectInput.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int]
    libXrandr.XRRSelectInput.restype = None

    _libX11 = libX11
    _libXrandr = libXrandr
    return _libX11, _libXrandr

# ==========================================================
# 1. Estrategia para X11
# ==========================================================
def get_x11_monitors():
    """
    Obtiene monitores usando libXrandr (X11).
    Retorna un diccionario {hash: {connector, manufacturer, x, y, width, height,
                                    width_mm, height_mm, inches, orientation, primary}}
    """
    libX11, libXrandr = get_x11_randr_api()

    # Abrir una conexión puntual para esta detección.
    display = libX11.XOpenDisplay(None)
    if not display:
        raise RuntimeError("No se pudo abrir la conexión a X11")

    screen = libX11.XDefaultScreen(display)
    root = libX11.XRootWindow(display, screen)

    resources = libXrandr.XRRGetScreenResourcesCurrent(display, root)
    if not resources:
        libX11.XCloseDisplay(display)
        return {}

    primary_output = libXrandr.XRRGetOutputPrimary(display, root)

    monitors_data = {}
    try:
        for i in range(resources.contents.noutput):
            output = resources.contents.outputs[i]
            info_ptr = libXrandr.XRRGetOutputInfo(display, resources, output)
            if not info_ptr:
                continue

            try:
                info = info_ptr.contents
                if info.connection != 0:  # 0 = RR_Connected
                    continue

                connector = ctypes.string_at(info.name, info.nameLen).decode()
                if info.crtc == 0:
                    continue

                crtc_ptr = libXrandr.XRRGetCrtcInfo(display, resources, info.crtc)
                if not crtc_ptr:
                    continue

                try:
                    crtc = crtc_ptr.contents

                    # Obtener EDID para hash estable
                    edid_atom_name = ctypes.c_char_p(b"EDID")
                    edid_atom = libX11.XInternAtom(display, edid_atom_name, 0)
                    actual_type = ctypes.c_ulong()
                    actual_format = ctypes.c_int()
                    nitems = ctypes.c_ulong()
                    bytes_after = ctypes.c_ulong()
                    prop = ctypes.POINTER(ctypes.c_ubyte)()

                    try:
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

                    finally:
                        if prop:
                            libX11.XFree(prop)

                finally:
                    libXrandr.XRRFreeCrtcInfo(crtc_ptr)

            finally:
                libXrandr.XRRFreeOutputInfo(info_ptr)

    finally:
        libXrandr.XRRFreeScreenResources(resources)
        libX11.XCloseDisplay(display)

    return monitors_data

def get_monitor_hash_from_position(x, y, monitors_map):
    """Devuelve el hash WMM del monitor que contiene una posición absoluta."""
    if x is None or y is None or not monitors_map:
        return None

    try:
        x = float(x)
        y = float(y)
    except (TypeError, ValueError):
        return None

    for m_hash, monitor in monitors_map.items():
        if monitor["x"] <= x < monitor["x"] + monitor["width"] and monitor["y"] <= y < monitor["y"] + monitor["height"]:
            return m_hash

    return None

def get_monitor_hash_from_xid(xid, monitors_map):
    """Devuelve el hash WMM del monitor que contiene la ventana X11 indicada."""
    if not xid or not monitors_map:
        return None

    try:
        gi.require_version('GdkX11', '3.0')
        from gi.repository import GdkX11

        display = Gdk.Display.get_default()
        window = GdkX11.X11Window.foreign_new_for_display(display, int(xid))
        success, x, y = window.get_origin()

        if not success:
            return None

        m_hash = get_monitor_hash_from_position(x, y, monitors_map)
        if m_hash:
            log_event(f"XID {xid} -> posición {x},{y} -> monitor {m_hash}",
                origin="MON_DETECT", level="DEBUG", reason="HARDWARE")
            return m_hash

    except Exception as e:
        log_event(f"No se pudo resolver el XID {xid}: {e}",
            origin="MON_DETECT", level="WARN", reason="HARDWARE")

    return None

# ==========================================================
# 2. Estrategia para GNOME Wayland
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
        display_config = bus.get_object("org.gnome.Mutter.DisplayConfig", "/org/gnome/Mutter/DisplayConfig")

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
            output_by_connector[name] = { 'id': output_id, 'current_crtc': current_crtc, 'props': props, }

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

        log_event(f"Monitores obtenidos desde D-Bus: {len(monitors)}",
            origin="MON_DETECT", level="DEBUG", reason="HARDWARE")
        return monitors

    except Exception as e:
        log_event(f"Error en GNOME D-Bus: {e}",
            origin="MON_DETECT", level="ERROR", reason="HARDWARE")
        return {}


# ==========================================================
# 3. Estrategia de fallback para Wayland
# ==========================================================
def get_gdk_wayland_monitors():
    """
    Obtiene monitores usando Gdk como fallback genérico para Wayland.
    Proporciona geometría, dimensiones físicas y orientación básica.
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

# ------------------------------------------------------------
# 4. KDE Plasma 6 detection (kscreen-doctor + EDID)
# ------------------------------------------------------------

def _parse_edid_base(edid_bytes):
    """Extrae identidad y dimensiones físicas del EDID base."""
    if len(edid_bytes) < 128:
        return None

    # Fabricante (bytes 8-9)
    b8 = edid_bytes[8]
    b9 = edid_bytes[9]
    char1 = chr(((b8 & 0x7C) >> 2) + 64)
    char2 = chr((((b8 & 0x03) << 3) | ((b9 & 0xE0) >> 5)) + 64)
    char3 = chr((b9 & 0x1F) + 64)
    manufacturer = f"{char1}{char2}{char3}"

    model_name = None
    serial_number = None
    width_mm = 0
    height_mm = 0

    # Los DTD proporcionan medidas físicas más precisas que los cm del bloque base.
    for offset in [54, 72, 90, 108]:
        desc = edid_bytes[offset:offset+18]

        if desc[0] != 0 or desc[1] != 0:
            if width_mm == 0 or height_mm == 0:
                dtd_width = desc[12] | ((desc[14] & 0xF0) << 4)
                dtd_height = desc[13] | ((desc[14] & 0x0F) << 8)
                if dtd_width > 0 and dtd_height > 0:
                    width_mm = dtd_width
                    height_mm = dtd_height
            continue

        tag = desc[3]
        raw_text = desc[5:].decode(
            'ascii', errors='ignore').replace(
            '\r', '').replace('\n', '').strip()

        if tag == 0xFF and raw_text:
            serial_number = raw_text
        elif tag == 0xFC and raw_text:
            model_name = raw_text
        elif tag == 0xFE and raw_text and not serial_number:
            if any(c.isdigit() for c in raw_text) and len(raw_text) >= 4:
                serial_number = raw_text

    # Algunos EDID sólo publican el tamaño físico en centímetros.
    if width_mm == 0 or height_mm == 0:
        width_mm = int(edid_bytes[21]) * 10
        height_mm = int(edid_bytes[22]) * 10

    # El descriptor ASCII prevalece; el serial binario es sólo fallback.
    if not serial_number:
        serial_raw = int.from_bytes(
            edid_bytes[12:16], byteorder='little')
        if serial_raw != 0:
            serial_number = str(serial_raw)
        else:
            serial_number = "Unknown"

    return {
        "manufacturer": manufacturer,
        "model": model_name,
        "serial_number": serial_number,
        "width_mm": width_mm,
        "height_mm": height_mm,
    }

def _get_edids_from_sysfs():
    """Lee EDID de /sys/class/drm/*/edid y devuelve dict {connector: info}."""
    edid_map = {}
    for path in glob.glob('/sys/class/drm/card*-*'):
        connector_name = "-".join(path.split('-')[1:])
        edid_file = os.path.join(path, 'edid')
        if os.path.exists(edid_file):
            try:
                with open(edid_file, 'rb') as f:
                    edid_bytes = f.read()
                if edid_bytes:
                    parsed = _parse_edid_base(edid_bytes)
                    if parsed:
                        edid_map[connector_name] = parsed
            except Exception:
                # Si no se puede leer, loguear WARN y continuar
                log_event(f"No se pudo leer EDID para {connector_name}",
                    origin="MON_DETECT", level="WARN", reason="HARDWARE")
                continue
    return edid_map

def _get_kscreen_info():
    """Ejecuta kscreen-doctor -j y extrae geometría, posición, mm y prioridad."""
    try:
        log_event("Ejecutando kscreen-doctor -j",
            origin="MON_DETECT", level="DEBUG", reason="HARDWARE")
        result = subprocess.run(['kscreen-doctor', '-j'], capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
    except Exception as e:
        log_event(f"Error al ejecutar kscreen-doctor: {e}",
            origin="MON_DETECT", level="ERROR", reason="HARDWARE")
        log_event(f"Excepción en kscreen-doctor: {e}",
            origin="MON_DETECT", level="ERROR", reason="HARDWARE")
        return {}

    outputs = data.get("outputs", [])
    kscreen_map = {}
    for out in outputs:
        connector = out.get("name")
        if not connector or not out.get("connected", False):
            continue

        # Geometría en píxeles
        size = out.get("size", {})
        width = size.get("width")
        height = size.get("height")
        if width is None or height is None:
            # Intentar obtener del modo activo
            current_mode = str(out.get("currentModeId", ""))
            for mode in out.get("modes", []):
                if str(mode.get("id")) == current_mode:
                    mode_size = mode.get("size", {})
                    width = mode_size.get("width")
                    height = mode_size.get("height")
                    break

        # Dimensiones físicas (mm)
        size_mm = out.get("sizeMM", {})
        width_mm = size_mm.get("width", 0)
        height_mm = size_mm.get("height", 0)

        pos = out.get("pos", {})

        kscreen_map[connector] = {
            "x": pos.get("x", 0),
            "y": pos.get("y", 0),
            "width": width,
            "height": height,
            "width_mm": width_mm,
            "height_mm": height_mm,
            "primary": (out.get("priority") == 1),
        }

    return kscreen_map

def get_kde_monitors():
    """Obtiene monitores en KDE Plasma 6 usando kscreen-doctor + EDID desde sysfs."""
    # 1. Obtener EDID
    edid_map = _get_edids_from_sysfs()

    # 2. Obtener información de KScreen
    kscreen_map = _get_kscreen_info()
    log_event(f"kscreen_map tiene {len(kscreen_map)} monitores",
        origin="MON_DETECT", level="DEBUG", reason="HARDWARE")
    if not kscreen_map:
        return {}

    monitors = {}
    for connector, display in kscreen_map.items():
        # Datos de EDID (o valores por defecto)
        edid_info = edid_map.get(connector, {
            "manufacturer": "Unknown",
            "model": "",
            "serial_number": "Unknown"
        })

        manufacturer = edid_info["manufacturer"]
        model = edid_info["model"]
        serial = edid_info["serial_number"]

        # Orientación
        orientation = "horizontal" if display["width"] >= display["height"] else "vertical"

        # Pulgadas
        w_mm = display["width_mm"]
        h_mm = display["height_mm"]
        if w_mm > 0 and h_mm > 0:
            inches = calculate_inches(w_mm, h_mm)
        else:
            inches = 0

        # Hash
        if serial != "Unknown":
            hash_base = f"{manufacturer}_{model}_{serial}"
        else:
            hash_base = f"{manufacturer}_{model}_{connector}"
        monitor_hash = hashlib.shake_128(hash_base.encode()).hexdigest(4)

        monitors[monitor_hash] = {
            "connector": connector,
            "manufacturer": manufacturer,
            "model": model,
            "x": display["x"],
            "y": display["y"],
            "width": display["width"],
            "height": display["height"],
            "width_mm": display["width_mm"],
            "height_mm": display["height_mm"],
            "inches": inches,
            "orientation": orientation,
            "primary": display["primary"],
        }

    log_event(f"Monitores obtenidos con kscreen-doctor + EDID: {len(monitors)}",
        origin="MON_DETECT", level="INFO", reason="HARDWARE")
    log_event(f"monitores finales: {len(monitors)}",
        origin="MON_DETECT", level="DEBUG", reason="HARDWARE")
    return monitors

# ==========================================================
# INFRAESTRUCTURA NATIVA WIN32
# ==========================================================
# Igual que en XRandR, los tipos ctypes deben existir una sola vez a nivel
# de módulo. Redefinir estructuras en cada detección generaría nuevos tipos
# y volvería a alimentar la caché interna de POINTER().
if sys.platform == 'win32':
    from ctypes import wintypes

    class _MONITORINFOEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
            ("szDevice", wintypes.WCHAR * 32),
        ]


    class _DISPLAY_DEVICEW(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("DeviceName", wintypes.WCHAR * 32),
            ("DeviceString", wintypes.WCHAR * 128),
            ("StateFlags", wintypes.DWORD),
            ("DeviceID", wintypes.WCHAR * 128),
            ("DeviceKey", wintypes.WCHAR * 128),
        ]


    class _GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", wintypes.DWORD),
            ("Data2", wintypes.WORD),
            ("Data3", wintypes.WORD),
            ("Data4", ctypes.c_ubyte * 8),
        ]


    class _SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("InterfaceClassGuid", _GUID),
            ("Flags", wintypes.DWORD),
            ("Reserved", ctypes.c_size_t),
        ]


    class _SP_DEVINFO_DATA(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("ClassGuid", _GUID),
            ("DevInst", wintypes.DWORD),
            ("Reserved", ctypes.c_size_t),
        ]


    _MONITORENUMPROC = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HANDLE,
        wintypes.HDC,
        ctypes.POINTER(wintypes.RECT),
        wintypes.LPARAM,
    )

    # Infraestructura de mensajes utilizada por monitor_events.
    _WNDPROC = ctypes.WINFUNCTYPE(
        ctypes.c_ssize_t,
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    )


    class _WNDCLASSW(ctypes.Structure):
        _fields_ = [
            ("style", wintypes.UINT),
            ("lpfnWndProc", _WNDPROC),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", wintypes.HINSTANCE),
            ("hIcon", wintypes.HICON),
            ("hCursor", wintypes.HCURSOR),
            ("hbrBackground", wintypes.HBRUSH),
            ("lpszMenuName", wintypes.LPCWSTR),
            ("lpszClassName", wintypes.LPCWSTR),
        ]


    class _MSG(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("message", wintypes.UINT),
            ("wParam", wintypes.WPARAM),
            ("lParam", wintypes.LPARAM),
            ("time", wintypes.DWORD),
            ("pt", wintypes.POINT),
            ("lPrivate", wintypes.DWORD),
        ]

_user32 = None
_setupapi = None
_advapi32 = None
_kernel32 = None


def get_windows_display_api():
    """
    Devuelve la API Win32 común utilizada por detección y eventos.

    Las DLL y sus firmas ctypes se inicializan una sola vez. Los recursos
    obtenidos mediante estas APIs pertenecen a cada consumidor y deben
    liberarse allí.
    """
    global _user32, _setupapi, _advapi32, _kernel32

    if sys.platform != 'win32':
        raise RuntimeError(
            "La API de display Win32 sólo está disponible en Windows")

    if (_user32 is not None
            and _setupapi is not None
            and _advapi32 is not None
            and _kernel32 is not None):
        return _user32, _setupapi, _advapi32, _kernel32

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    # User32: enumeración y geometría efectiva de los monitores.
    user32.EnumDisplayMonitors.argtypes = [
        wintypes.HDC,
        ctypes.POINTER(wintypes.RECT),
        _MONITORENUMPROC,
        wintypes.LPARAM,
    ]
    user32.EnumDisplayMonitors.restype = wintypes.BOOL

    user32.GetMonitorInfoW.argtypes = [ wintypes.HANDLE, ctypes.POINTER(_MONITORINFOEXW), ]
    user32.GetMonitorInfoW.restype = wintypes.BOOL

    user32.EnumDisplayDevicesW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(_DISPLAY_DEVICEW),
        wintypes.DWORD,
    ]
    user32.EnumDisplayDevicesW.restype = wintypes.BOOL

    # User32: ventana oculta y message loop utilizados por monitor_events.
    user32.RegisterClassW.argtypes = [
        ctypes.POINTER(_WNDCLASSW),
    ]
    user32.RegisterClassW.restype = wintypes.WORD

    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HWND,
        wintypes.HMENU,
        wintypes.HINSTANCE,
        ctypes.c_void_p,
    ]
    user32.CreateWindowExW.restype = wintypes.HWND

    user32.DefWindowProcW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    user32.DefWindowProcW.restype = ctypes.c_ssize_t

    # GetMessage puede devolver -1, 0 o un valor positivo; no se trata
    # como un simple booleano para no ocultar la condición de error.
    user32.GetMessageW.argtypes = [
        ctypes.POINTER(_MSG),
        wintypes.HWND,
        wintypes.UINT,
        wintypes.UINT,
    ]
    user32.GetMessageW.restype = ctypes.c_int

    user32.DispatchMessageW.argtypes = [ ctypes.POINTER(_MSG), ]
    user32.DispatchMessageW.restype = ctypes.c_ssize_t

    user32.DestroyWindow.argtypes = [ wintypes.HWND, ]
    user32.DestroyWindow.restype = wintypes.BOOL

    user32.PostQuitMessage.argtypes = [ ctypes.c_int, ]
    user32.PostQuitMessage.restype = None

    user32.UnregisterClassW.argtypes = [ wintypes.LPCWSTR, wintypes.HINSTANCE, ]
    user32.UnregisterClassW.restype = wintypes.BOOL

    # La clase de ventana pertenece al ejecutable que hospeda WMM.
    kernel32.GetModuleHandleW.argtypes = [ wintypes.LPCWSTR, ]
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE

    # SetupAPI: asociación con la interfaz física y acceso al dispositivo.
    setupapi.SetupDiGetClassDevsW.argtypes = [
        ctypes.POINTER(_GUID),
        wintypes.LPCWSTR,
        wintypes.HANDLE,
        wintypes.DWORD,
    ]
    setupapi.SetupDiGetClassDevsW.restype = wintypes.HANDLE

    setupapi.SetupDiOpenDeviceInterfaceW.argtypes = [
        wintypes.HANDLE,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(_SP_DEVICE_INTERFACE_DATA),
    ]
    setupapi.SetupDiOpenDeviceInterfaceW.restype = wintypes.BOOL

    setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_SP_DEVICE_INTERFACE_DATA),
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(_SP_DEVINFO_DATA),
    ]
    setupapi.SetupDiGetDeviceInterfaceDetailW.restype = wintypes.BOOL

    setupapi.SetupDiOpenDevRegKey.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_SP_DEVINFO_DATA),
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    setupapi.SetupDiOpenDevRegKey.restype = wintypes.HANDLE

    setupapi.SetupDiDestroyDeviceInfoList.argtypes = [ wintypes.HANDLE, ]
    setupapi.SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL

    # Advapi32: lectura y cierre de la clave de dispositivo que contiene EDID.
    advapi32.RegQueryValueExW.argtypes = [
        wintypes.HANDLE,
        wintypes.LPCWSTR,
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.RegQueryValueExW.restype = wintypes.LONG

    advapi32.RegCloseKey.argtypes = [ wintypes.HANDLE, ]
    advapi32.RegCloseKey.restype = wintypes.LONG

    _user32 = user32
    _setupapi = setupapi
    _advapi32 = advapi32
    _kernel32 = kernel32

    return _user32, _setupapi, _advapi32, _kernel32

# ==========================================================
# 5. Estrategia para Windows
# ==========================================================

def get_windows_monitors():
    """
    Obtiene los monitores activos mediante Win32 y devuelve el contrato WMM.

    GetMonitorInfo aporta la geometría efectiva del escritorio.
    EnumDisplayDevices enlaza cada DISPLAYx con su interfaz física y
    SetupAPI permite recuperar el EDID asociado a ese dispositivo.
    """
    user32, setupapi, advapi32, _kernel32 = get_windows_display_api()

    MONITORINFOF_PRIMARY = 0x00000001
    DISPLAY_DEVICE_ACTIVE = 0x00000001
    EDD_GET_DEVICE_INTERFACE_NAME = 0x00000001

    DIGCF_PRESENT = 0x00000002
    DIGCF_DEVICEINTERFACE = 0x00000010
    DICS_FLAG_GLOBAL = 0x00000001
    DIREG_DEV = 0x00000001
    KEY_READ = 0x00020019

    ERROR_SUCCESS = 0
    ERROR_INSUFFICIENT_BUFFER = 122
    REG_BINARY = 3
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    guid_monitor = _GUID(
        0xE6F07B5F,
        0xEE97,
        0x4A90,
        (ctypes.c_ubyte * 8)(
            0xB0, 0x76, 0x33, 0xF5,
            0x7B, 0xF4, 0xEA, 0xA7),
    )

    def get_interface_path(device):
        """
        Obtiene la interfaz SetupAPI asociada a un dispositivo DISPLAYx.
        """
        fallback = None
        index = 0

        while True:
            display_device = _DISPLAY_DEVICEW()
            display_device.cb = ctypes.sizeof(display_device)

            if not user32.EnumDisplayDevicesW(
                    device,
                    index,
                    ctypes.byref(display_device),
                    EDD_GET_DEVICE_INTERFACE_NAME):
                break

            if display_device.DeviceID:
                if fallback is None:
                    fallback = display_device.DeviceID

                if display_device.StateFlags & DISPLAY_DEVICE_ACTIVE:
                    return display_device.DeviceID

            index += 1

        return fallback

    def read_edid(device_info_set, interface_path):
        """
        Obtiene el EDID desde la clave de dispositivo de la interfaz física.
        """
        if device_info_set is None or not interface_path:
            return None

        interface_data = _SP_DEVICE_INTERFACE_DATA()
        interface_data.cbSize = ctypes.sizeof(interface_data)

        if not setupapi.SetupDiOpenDeviceInterfaceW(
                device_info_set,
                interface_path,
                0,
                ctypes.byref(interface_data)):
            return None

        device_info = _SP_DEVINFO_DATA()
        device_info.cbSize = ctypes.sizeof(device_info)
        required_size = wintypes.DWORD()

        # Sólo necesitamos SP_DEVINFO_DATA. Con el buffer de detalle a NULL,
        # SetupAPI lo rellena y señala ERROR_INSUFFICIENT_BUFFER por diseño.
        ctypes.set_last_error(0)
        result = setupapi.SetupDiGetDeviceInterfaceDetailW(
            device_info_set,
            ctypes.byref(interface_data),
            None,
            0,
            ctypes.byref(required_size),
            ctypes.byref(device_info),
        )

        if (not result
                and ctypes.get_last_error() != ERROR_INSUFFICIENT_BUFFER):
            return None

        registry_key = setupapi.SetupDiOpenDevRegKey(
            device_info_set,
            ctypes.byref(device_info),
            DICS_FLAG_GLOBAL,
            0,
            DIREG_DEV,
            KEY_READ,
        )

        if registry_key in (None, INVALID_HANDLE_VALUE):
            return None

        try:
            value_type = wintypes.DWORD()
            value_size = wintypes.DWORD()

            result = advapi32.RegQueryValueExW(
                registry_key,
                "EDID",
                None,
                ctypes.byref(value_type),
                None,
                ctypes.byref(value_size),
            )

            if (result != ERROR_SUCCESS
                    or value_type.value != REG_BINARY
                    or value_size.value < 128):
                return None

            buffer = (ctypes.c_ubyte * value_size.value)()

            result = advapi32.RegQueryValueExW(
                registry_key,
                "EDID",
                None,
                ctypes.byref(value_type),
                ctypes.cast(buffer, ctypes.c_void_p),
                ctypes.byref(value_size),
            )

            if result != ERROR_SUCCESS:
                return None

            return bytes(buffer[:value_size.value])

        finally:
            advapi32.RegCloseKey(registry_key)

    raw_monitors = []

    @_MONITORENUMPROC
    def monitor_callback(hmonitor, _hdc, _rect, _data):
        info = _MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(info)

        if user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
            rect = info.rcMonitor

            raw_monitors.append({
                "device": info.szDevice,
                "x": rect.left,
                "y": rect.top,
                "width": rect.right - rect.left,
                "height": rect.bottom - rect.top,
                "primary": bool(
                    info.dwFlags & MONITORINFOF_PRIMARY),
            })

        return True

    if not user32.EnumDisplayMonitors(
            None, None, monitor_callback, 0):
        log_event("Windows no pudo enumerar los monitores activos",
            origin="MON_DETECT", level="ERROR", reason="HARDWARE")
        return {}

    if not raw_monitors:
        log_event(
            "Enumeración Win32 completada sin monitores válidos",
            origin="MON_DETECT", level="ERROR", reason="HARDWARE")
        return {}

    device_info_set = setupapi.SetupDiGetClassDevsW(
        ctypes.byref(guid_monitor),
        None,
        None,
        DIGCF_PRESENT | DIGCF_DEVICEINTERFACE,
    )

    if device_info_set == INVALID_HANDLE_VALUE:
        device_info_set = None
        log_event(
            "SetupAPI no pudo acceder a las interfaces de monitor; "
            "se usará identidad por conector",
            origin="MON_DETECT", level="WARN", reason="HARDWARE")

    min_x = min(display["x"] for display in raw_monitors)
    min_y = min(display["y"] for display in raw_monitors)

    monitors = {}

    try:
        for display in raw_monitors:
            device = display["device"]
            connector = (
                device[4:]
                if device.startswith("\\\\.\\")
                else device)

            interface_path = get_interface_path(device)
            edid = read_edid(device_info_set, interface_path)

            edid_info = _parse_edid_base(edid) if edid else None
            if not edid_info:
                edid_info = {
                    "manufacturer": "Unknown",
                    "model": None,
                    "serial_number": "Unknown",
                    "width_mm": 0,
                    "height_mm": 0,
                }

            manufacturer = edid_info["manufacturer"]
            model = edid_info["model"]
            serial = edid_info["serial_number"]
            width_mm = edid_info["width_mm"]
            height_mm = edid_info["height_mm"]

            # Hash
            if serial != "Unknown":
                hash_base = f"{manufacturer}_{model}_{serial}"
            else:
                hash_base = f"{manufacturer}_{model}_{connector}"

            monitor_hash = hashlib.shake_128(
                hash_base.encode()).hexdigest(4)

            # Orientación
            width = display["width"]
            height = display["height"]
            orientation = ("horizontal" if width >= height else "vertical")

            # Pulgadas
            if width_mm > 0 and height_mm > 0:
                inches = calculate_inches(width_mm, height_mm)
            else:
                inches = 0

            monitors[monitor_hash] = {
                "connector": connector,
                "manufacturer": manufacturer,
                "model": model,
                "x": display["x"] - min_x,
                "y": display["y"] - min_y,
                "width": width,
                "height": height,
                "width_mm": width_mm,
                "height_mm": height_mm,
                "inches": inches,
                "orientation": orientation,
                "primary": display["primary"],
            }

    finally:
        if device_info_set is not None:
            setupapi.SetupDiDestroyDeviceInfoList(device_info_set)

    log_event(
        f"Monitores obtenidos mediante Win32 + EDID: {len(monitors)}",
        origin="MON_DETECT", level="INFO", reason="HARDWARE")
    return monitors

# ==========================================================
# 6. Orquestador principal
# ==========================================================
def detect_monitors():
    """
    Devuelve el diccionario de monitores según el entorno activo.
    Estrategias:
        - Windows → get_windows_monitors()
        - X11 → get_x11_monitors()
        - Wayland + GNOME → get_gnome_wayland_monitors()
        - Wayland + KDE → get_kde_monitors()
        - Wayland + otros → get_gdk_wayland_monitors()
    """
    from wmm_platform.core import PlatformManager
    pm = PlatformManager()
    desktop = getattr(pm, 'desktop', None)
    graphics_engine = getattr(pm, 'graphics_engine', 'x11')

    # Windows utiliza la estrategia nativa Win32, que ya devuelve
    # directamente el contrato común de monitores de WMM.
    if graphics_engine == 'win32' and desktop == 'windows':
        return get_windows_monitors()

    # 1. X11
    if graphics_engine == 'x11':
        log_event("Detección X11 usando libXrandr",
            origin="MON_DETECT", level="DEBUG", reason="HARDWARE")
        return get_x11_monitors()

    # 2. GNOME Wayland
    if graphics_engine == 'wayland' and desktop == 'gnome':
        log_event("Detección GNOME Wayland usando D-Bus",
            origin="MON_DETECT", level="DEBUG", reason="HARDWARE")
        monitors = get_gnome_wayland_monitors()
        if monitors:
            return monitors
        else:
            log_event("D-Bus falló, usando fallback GDK",
                origin="MON_DETECT", level="WARN", reason="HARDWARE")

    # 3. KDE Wayland
    if graphics_engine == 'wayland' and desktop == 'kde':
        log_event("Detección KDE Wayland usando kscreen-doctor + EDID",
            origin="MON_DETECT", level="DEBUG", reason="HARDWARE")
        monitors = get_kde_monitors()
        if monitors:
            return monitors
        else:
            log_event("kscreen-doctor falló, usando fallback GDK",
                origin="MON_DETECT", level="WARN", reason="HARDWARE")

    # 4. Fallback GDK para cualquier otro caso
    log_event("Detección genérica Wayland usando GDK",
        origin="MON_DETECT", level="DEBUG", reason="HARDWARE")
    return get_gdk_wayland_monitors()
