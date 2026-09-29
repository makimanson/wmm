#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

"""
WMM - Wallpaper Multi-Monitor Manager

windows.py - Módulo de plataforma para Windows.
==========================================================
Contiene funciones comunes a Windows (independientes del escritorio).
"""
import os
import sys
import subprocess

def normalize_platform(raw_platform):
    """Normaliza el valor de sys.platform al nombre canónico del SO."""
    return raw_platform

def detect_desktop():
    """Detecta el escritorio actual (esqueleto)."""
    return 'generic'

def get_system_paths():
    """
    Devuelve las rutas base del sistema para Windows.
    TODO: Implementar usando %LOCALAPPDATA%, %APPDATA%, etc.
    Por ahora, devuelve None para usar fallbacks genéricos.
    """
    return {
        'data_base': None,
        'cache_base': None,
        'locale_dir': None,
        'cache_dir': None,
    }

def get_install_path(data_base, app_domain):
    """Devuelve la ruta de instalación (esqueleto)."""
    if data_base:
        return os.path.join(data_base, app_domain)
    return app_domain

def lock_file(f):
    """
    Bloquea el archivo para escritura exclusiva usando msvcrt.locking.
    """
    import msvcrt
    msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)

def unlock_file(f):
    """
    Desbloquea el archivo previamente bloqueado con lock_file.
    """
    import msvcrt
    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)

def open_file(path, capability=None, **params):
    """
    Abre un archivo o directorio con la aplicación predeterminada en Windows.
    """
    os.startfile(path)

def send_notification(title, message, level="info"):
    """
    Envía una notificación en Windows.
    """
    # TODO: Implementar usando win32api o toasts
    print(f"[NOTIFICACIÓN] {title}: {message}")

def _force_desktop_settings(config_handler):
    """
    Fuerza los ajustes del sistema necesarios para que WMM funcione
    correctamente en Windows.
    TODO: Implementar usando ctypes o pywin32.
    """
    pass

def ensure_shell_actions(applet_root, data_base):
    """
    Instala las acciones de shell necesarias para Windows
    (p. ej., menús contextuales del Explorador).
    TODO: Implementar cuando se añada soporte para Windows.
    """
    pass

def get_monitors():
    """
    Devuelve un diccionario con la geometría e identidad de todos los monitores en Windows.
    TODO: Implementar usando EnumDisplayMonitors + GetMonitorInfo (ctypes).
    Actualmente es un esqueleto que devuelve un diccionario vacío.

    Returns:
        dict: {hash: {connector, manufacturer, x, y, width, height, width_mm, height_mm, inches, orientation, primary}}

    Nota sobre Windows:
        - Los monitores se identifican mediante el nombre del dispositivo (DISPLAY1, DISPLAY2, etc.).
        - El monitor primario tiene flags = MONITORINFOF_PRIMARY.
        - Las dimensiones físicas (mm) se obtienen mediante EDID o, si no, se pueden estimar.
        - El hash debe basarse en el nombre del dispositivo + modelo (si está disponible).
    """
    # TODO: Usar ctypes para llamar a EnumDisplayMonitors y GetMonitorInfo.
    # Ejemplo de referencia (pseudocódigo):
    #   from ctypes import windll, byref, Structure, c_int, c_ulong
    #   user32 = windll.user32
    #   monitors = []
    #   callback = lambda hMonitor, hdc, rect, data: ...
    #   user32.EnumDisplayMonitors(None, None, callback, 0)
    # Para obtener el modelo/EDID, se puede usar SetupAPI o EDID desde el registro.
    return {}


def set_wallpaper(path, config_handler=None):
    """
    Aplica el fondo de pantalla en Windows.
    TODO: Implementar usando SystemParametersInfo(SPI_SETDESKWALLPAPER) con ctypes.

    Args:
        path: Ruta absoluta de la imagen a aplicar.
        config_handler: Opcional, instancia de ConfigHandler (no usado en la implementación actual).

    Nota sobre Windows:
        - SystemParametersInfo requiere que la imagen esté en formato BMP o JPG.
        - En Windows 10/11, se puede usar también la API IDesktopWallpaper para mayor control.
        - La función puede requerir que el archivo esté en formato BMP para ciertas versiones.
    """
    # TODO: Usar ctypes para llamar a SystemParametersInfoW(SPI_SETDESKWALLPAPER, 0, path, SPIF_UPDATEINIFILE | SPIF_SENDCHANGE)
    # from ctypes import windll
    # windll.user32.SystemParametersInfoW(0x0014, 0, path, 0x0001 | 0x0002)
    pass


def compile_translations(app_root, locale_dir, app_domain):
    """
    Compila los archivos .po a .mo en Windows.
    TODO: Verificar si msgfmt está disponible (posiblemente mediante gettext-tools).
    Si no, se podría usar una implementación Python pura (polib) para compilar.

    Args:
        app_root: Ruta raíz de la aplicación.
        locale_dir: Directorio donde se instalarán los archivos .mo.
        app_domain: Dominio de la aplicación (ej. 'wmm@maki').

    Nota sobre Windows:
        - gettext-tools puede instalarse via MSYS2, Cygwin o manualmente.
        - Alternativa: usar la librería polib de Python para compilar sin dependencias externas.
    """
    # TODO: Intentar subprocess.run(['msgfmt', po_path, '-o', mo_file]).
    # Si msgfmt no está disponible, usar polib (pip install polib) para generar el .mo.
    pass


def ensure_keybindings(app_dir):
    """
    Crea un atajo de teclado para "Next Background" en Windows.
    TODO: Implementar creando un acceso directo en el menú de inicio o usando el registro.

    Args:
        app_dir: Ruta de instalación de WMM.

    Nota sobre Windows:
        - Se puede crear un acceso directo en %APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs
          con el comando: python send_command.py '{"action":"force_rotation"}' "HOTKEY"
        - También se puede registrar un atajo global usando RegisterHotKey de user32.
    """
    # TODO: Crear acceso directo (.lnk) usando ctypes o comando nativo.
    # Opción 1: Crear un .lnk en el menú de inicio.
    # Opción 2: Registrar un atajo global con RegisterHotKey.
    pass


def init_channels(data_dir):
    """
    Registra los canales de comunicación soportados por Windows.
    TODO: Implementar canales (archivo, y posiblemente named pipes o mailslots).

    Nota sobre Windows:
        - El canal de archivo (commands.json) funciona igual que en Linux.
        - Para comunicación entre procesos, se pueden usar named pipes o mailslots.
        - No existe D-Bus en Windows, pero se puede usar D-Bus emulado via DBus.NET.
    """
    # TODO: Registrar FileChannel (similar a linux.py).
    # TODO: Registrar canal adicional (named pipes, mailslots, o socket local).
    pass


def init_monitor_events(callback):
    """
    Inicia la monitorización de cambios de hardware en Windows.
    TODO: Implementar usando WM_DEVICECHANGE o RegisterDeviceNotification.

    Args:
        callback: Función que se llamará al detectar cambios.

    Returns:
        bool: False (no implementado actualmente).

    Nota sobre Windows:
        - Se puede usar RegisterDeviceNotification para recibir notificaciones de cambios de monitores.
        - También se puede usar el evento WM_DISPLAYCHANGE.
        - Alternativa: polling con EnumDisplayMonitors cada X segundos.
    """
    # TODO: Implementar usando RegisterDeviceNotification con ctypes.
    # O bien, usar un timer con EnumDisplayMonitors para detectar cambios.
    return False


def normalize_desktop(desktop):
    """
    Normaliza el nombre del escritorio para Windows.
    En Windows, no hay múltiples escritorios como en Linux, así que siempre devuelve 'windows'.
    """
    return 'windows'
