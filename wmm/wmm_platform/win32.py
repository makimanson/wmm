#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

"""
WMM - Wallpaper Multi-Monitor Manager

win32.py - Módulo de plataforma para Win32.
===========================================
Contiene las implementaciones específicas del sistema operativo Win32,
independientes de la capa de escritorio Windows.
"""

import ctypes
import json
import msvcrt
import os
import subprocess
import sys
import threading

from debug_logger import log_event
from ctypes import wintypes
from wmm_platform.core import _build_launch_command

# ----------------------------------------------------------------------
# ESTRUCTURAS Y API DE BLOQUEO WIN32
# ----------------------------------------------------------------------
# LockFileEx usa una región centinela fija fuera de los datos reales.
# Así todos los procesos WMM compiten por el mismo lock sin interferir
# con las lecturas o escrituras normales del contenido del archivo.
_LOCKFILE_FAIL_IMMEDIATELY = 0x00000001
_LOCKFILE_EXCLUSIVE_LOCK = 0x00000002
_ERROR_LOCK_VIOLATION = 33

_LOCK_OFFSET = 0x7FFFFFFF
_LOCK_LENGTH = 1


class _OVERLAPPED(ctypes.Structure):
    """Estructura Win32 OVERLAPPED usada para definir la región bloqueada."""
    _fields_ = [
        ("Internal", ctypes.c_size_t),
        ("InternalHigh", ctypes.c_size_t),
        ("Offset", wintypes.DWORD),
        ("OffsetHigh", wintypes.DWORD),
        ("hEvent", wintypes.HANDLE),
    ]

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_LockFileEx = _kernel32.LockFileEx
_LockFileEx.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.POINTER(_OVERLAPPED),
]
_LockFileEx.restype = wintypes.BOOL

_UnlockFileEx = _kernel32.UnlockFileEx
_UnlockFileEx.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.POINTER(_OVERLAPPED),
]
_UnlockFileEx.restype = wintypes.BOOL

def _new_lock_overlapped():
    """
    Crea el OVERLAPPED que identifica la región centinela común de WMM.

    El offset es independiente del cursor del archivo y permanece fuera de
    los datos reales; lock y unlock deben usar siempre exactamente esta región.
    """
    overlapped = _OVERLAPPED()
    overlapped.Offset = _LOCK_OFFSET & 0xFFFFFFFF
    overlapped.OffsetHigh = (_LOCK_OFFSET >> 32) & 0xFFFFFFFF
    return overlapped

# ----------------------------------------------------------------------
# IDENTIFICACIÓN DE PLATAFORMA Y ESCRITORIO
# ----------------------------------------------------------------------
def normalize_platform(raw_platform):
    """Normaliza el identificador nativo de CPython al nombre canónico de WMM."""
    return raw_platform

def detect_desktop():
    """Devuelve el identificador del escritorio de Windows usado por WMM."""
    return 'windows'

def normalize_desktop(desktop):
    """
    Normaliza el nombre del escritorio para Windows.
    En Windows, no hay múltiples escritorios como en Linux, así que siempre devuelve 'windows'.
    """
    return 'windows'

# ----------------------------------------------------------------------
# INICIO AUTOMÁTICO EN WINDOWS
# ----------------------------------------------------------------------
# HKCU es la única autoridad para la cuenta actual.
# DEV utiliza el frontend físico; PyInstaller ejecuta su dispatcher.
# La desactivación elimina el valor de WMM sin depender de su ruta.

_AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_AUTOSTART_NAME = "WMM Manager"

def _autostart_command(app_dir):
    """Construye el comando real para iniciar WMM en la sesión Windows."""
    if getattr(sys, "frozen", False):
        arguments = [sys.executable]
    else:
        frontend = os.path.join(app_dir, "frontends", "windows", "windows-frontend.py")
        arguments = [sys.executable, frontend]

    return subprocess.list2cmdline(arguments)

def get_autostart_enabled():
    """Consulta la existencia de la entrada de WMM en HKCU."""
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _AUTOSTART_KEY) as key:
            winreg.QueryValueEx(key, _AUTOSTART_NAME)
        return True
    except FileNotFoundError:
        return False
    except OSError as error:
        log_event(f"No se pudo consultar el inicio automático: {error}",
            origin="WIN32", level="ERROR", reason="SETTINGS")
        return False

def set_autostart_enabled(app_dir, enabled):
    """Registra o retira el inicio automático del usuario actual."""
    import winreg

    try:
        if enabled:
            # Sólo DEV necesita un script físico. En el compilado,
            # el punto de entrada está integrado en el ejecutable.
            target = (sys.executable if getattr(sys, "frozen", False)
                else os.path.join(app_dir, "frontends", "windows", "windows-frontend.py"))

            if not os.path.isfile(target):
                log_event(f"Inicio automático: ejecutable no encontrado: {target}",
                    origin="WIN32", level="ERROR", reason="SETTINGS")
                return False

            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,
                    _AUTOSTART_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, _AUTOSTART_NAME, 0, winreg.REG_SZ,
                    _autostart_command(app_dir))

        else:
            # No comparar rutas: una instalación anterior puede haber
            # cambiado de ubicación sin actualizar su entrada Run.
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                        _AUTOSTART_KEY, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.DeleteValue(key, _AUTOSTART_NAME)
            except FileNotFoundError:
                return True

        log_event(f"Inicio automático {'activado' if enabled else 'desactivado'}",
            origin="WIN32", level="INFO", reason="SETTINGS")
        return True

    except OSError as error:
        log_event(f"No se pudo modificar el inicio automático: {error}",
            origin="WIN32", level="ERROR", reason="SETTINGS")
        return False

# ----------------------------------------------------------------------
# IDENTIDAD E ICONOGRAFÍA NATIVA DE FORMULARIOS WINDOWS
# ----------------------------------------------------------------------
# El icono GTK pertenece a cada formulario. Este catálogo identifica
# sus iconos nativos para la barra de tareas de Windows.
#
# Los índices corresponden a SHELL32.dll; no son identificadores de
# recurso y deberán resolverse según la API nativa que los consuma.
# WMM.Manager conserva por separado la identidad de notificaciones.

_FORM_ICON_LIBRARY = r"%SystemRoot%\System32\SHELL32.dll"

_FORM_TASKBAR_ICONS = {
    "panel":           ("WMM.Panel", 314),
    "about":           ("WMM.About", 160),
    "debug_log":       ("WMM.DebugLogViewer", 171),
    "help":            ("WMM.Help", 23),
    "changelog":       ("WMM.Changelog", 269),
    "install_manager": ("WMM.InstallManager", 78),
    "keybinding":      ("WMM.Keybinding", 173),
}

def prepare_form_taskbar_identity(form_name):
    """Establece la identidad Windows del proceso autónomo de un formulario.

    No modifica el icono GTK. La asociación del recurso nativo con
    la ventana se realiza por separado.
    """
    identity = _FORM_TASKBAR_ICONS.get(form_name)
    if identity is None:
        log_event(f"Formulario Windows sin identidad: {form_name}",
            origin="WIN32", level="ERROR", reason="WINDOW")
        return False

    app_id, _icon_index = identity

    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    set_app_id = shell32.SetCurrentProcessExplicitAppUserModelID
    set_app_id.argtypes = [wintypes.LPCWSTR]
    set_app_id.restype = wintypes.LONG

    result = set_app_id(app_id)
    if result != 0:
        log_event(f"No se pudo establecer AppUserModelID {app_id}: "
            f"HRESULT=0x{result & 0xFFFFFFFF:08X}",
            origin="WIN32", level="ERROR", reason="WINDOW")
        return False

    return True

def _apply_form_taskbar_icon(window, hwnd, form_name):
    """Aplica el icono grande Windows sin sustituir el icono pequeño de GTK.

    ICON_BIG permite diferenciar el icono nativo del formulario del que
    GTK proporciona para su barra de título. El HICON extraído permanece
    vivo hasta que se destruye la ventana.
    """
    identity = _FORM_TASKBAR_ICONS.get(form_name)
    if identity is None:
        log_event(f"Icono Windows no definido: {form_name}",
            origin="WIN32", level="ERROR", reason="WINDOW")
        return False

    _, icon_index = identity
    icon_path = os.path.expandvars(_FORM_ICON_LIBRARY)

    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    extract_icon = shell32.ExtractIconExW
    extract_icon.argtypes = [
        wintypes.LPCWSTR, ctypes.c_int,
        ctypes.POINTER(wintypes.HICON), ctypes.c_void_p, wintypes.UINT]
    extract_icon.restype = wintypes.UINT

    icon = wintypes.HICON()
    if extract_icon(icon_path, icon_index, ctypes.byref(icon), None, 1) != 1:
        log_event(f"No se pudo extraer {icon_path}, índice {icon_index}",
            origin="WIN32", level="ERROR", reason="WINDOW")
        return False

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    send_message = user32.SendMessageW
    send_message.argtypes = [
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    send_message.restype = wintypes.LPARAM

    destroy_icon = user32.DestroyIcon
    destroy_icon.argtypes = [wintypes.HICON]
    destroy_icon.restype = wintypes.BOOL

    is_window = user32.IsWindow
    is_window.argtypes = [wintypes.HWND]
    is_window.restype = wintypes.BOOL

    # ICON_BIG=1. ICON_SMALL=0 permanece bajo control de GTK.
    send_message(hwnd, 0x0080, 1, icon.value)

    def release_icon(*_):
        # Retirar la referencia antes de liberar el HICON propio.
        if is_window(hwnd):
            send_message(hwnd, 0x0080, 1, 0)
        destroy_icon(icon)

    window.connect("destroy", release_icon)

    log_event(f"Icono Windows aplicado: {form_name}, índice {icon_index}",
        origin="WIN32", level="INFO", reason="WINDOW")
    return True

# ----------------------------------------------------------------------
# ESQUEMA DE COLOR DEL SISTEMA
# ----------------------------------------------------------------------

_SYSTEM_COLOR_SCHEME_KEY = (
    r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
_SYSTEM_ACCENT_KEY = r"Software\Microsoft\Windows\DWM"
_REG_NOTIFY_CHANGE_LAST_SET = 0x00000004

_system_color_scheme_thread = None
_system_color_accent_thread = None

_win32_palette_provider = None
_win32_palette_css = None

def _read_win32_palette():
    """Lee UISettings.GetColorValue por WinRT, sin paquetes externos."""
    import uuid

    class Color(ctypes.Structure):
        _fields_ = [(channel, ctypes.c_ubyte) for channel in "ARGB"]

    # --- Interfaz IUISettings3 ---
    # GetColorValue ocupa el slot 6 de IInspectable.
    iid = (ctypes.c_ubyte * 16).from_buffer_copy(
        uuid.UUID("03021be4-5254-4781-8194-5168f7d06d7b").bytes_le)

    combase = ctypes.WinDLL("combase")
    initialize = combase.RoInitialize
    initialize.argtypes = [ctypes.c_uint32]
    initialize.restype = ctypes.c_long

    uninitialize = combase.RoUninitialize
    uninitialize.argtypes = []
    uninitialize.restype = None

    create_string = combase.WindowsCreateString
    create_string.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)]
    create_string.restype = ctypes.c_long

    delete_string = combase.WindowsDeleteString
    delete_string.argtypes = [ctypes.c_void_p]
    delete_string.restype = ctypes.c_long

    activate = combase.RoActivateInstance
    activate.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    activate.restype = ctypes.c_long

    def check(hr):
        if hr < 0:
            raise OSError(f"WinRT HRESULT 0x{hr & 0xffffffff:08X}")

    def method(pointer, slot, *args):
        vtable = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *args)(vtable[slot])

    initialized = initialize(0)  # RO_INIT_SINGLETHREADED

    # RPC_E_CHANGED_MODE significa que otro componente inicializó COM.
    if initialized < 0 and initialized != -2147417850:
        check(initialized)

    hstring = ctypes.c_void_p()
    instance = ctypes.c_void_p()
    ui3 = ctypes.c_void_p()

    try:
        # --- Activación del objeto WinRT ---
        name = "Windows.UI.ViewManagement.UISettings"
        check(create_string(name, len(name), ctypes.byref(hstring)))
        check(activate(hstring, ctypes.byref(instance)))

        query = method(instance, 0, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
        check(query(instance, ctypes.cast(iid, ctypes.c_void_p), ctypes.byref(ui3)))

        # --- Lectura de la paleta ---
        get_color = method(ui3, 6, ctypes.c_int32, ctypes.POINTER(Color))
        names = {
            "background": 0,
            "foreground": 1,
            "accent_dark1": 4,
            "accent": 5,
            "accent_light1": 6,
        }

        result = {}
        for name, value in names.items():
            color = Color()
            check(get_color(ui3, value, ctypes.byref(color)))
            result[name] = f"#{color.R:02X}{color.G:02X}{color.B:02X}"

        return result

    finally:
        # Las interfaces COM y el HSTRING deben liberarse siempre.
        if ui3:
            method(ui3, 2)(ui3)
        if instance:
            method(instance, 2)(instance)
        if hstring:
            delete_string(hstring)
        if initialized >= 0:
            uninitialize()


def _get_win32_css_path():
    """Resuelve el CSS propio en fuente y runtime compilado."""
    css_root = (os.path.join(os.path.dirname(sys.executable), "wmm_platform")
        if getattr(sys, "frozen", False) else os.path.dirname(__file__))

    return os.path.join(css_root, "shell", "windows", "wmm-win32.css")

def _apply_win32_palette_to_gtk(scheme):
    """Adapta la apariencia GTK a Windows sin modificar el CSS común."""
    global _win32_palette_provider, _win32_palette_css

    from gi.repository import Gdk, Gtk

    try:
        palette = _read_win32_palette()
    except Exception as error:
        log_event(f"Paleta WinRT no disponible: {error}",
            origin="WIN32", level="WARN", reason="SETTINGS")
        return

    # --- Derivación de superficies ---
    # Windows proporciona colores base y acentos, pero no una paleta
    # completa equivalente a los controles modernos de WinUI.
    def blend(first, second, fraction):
        first_rgb = [int(first[i:i + 2], 16) for i in (1, 3, 5)]
        second_rgb = [int(second[i:i + 2], 16) for i in (1, 3, 5)]
        channels = [round(a * (1 - fraction) + b * fraction)
                    for a, b in zip(first_rgb, second_rgb)]
        return "#" + "".join(f"{n:02X}" for n in channels)

    background = palette["background"]
    foreground = palette["foreground"]
    dark = scheme == "dark" or (scheme is None and background == "#000000")

    # En DARK, incorporar suavemente el acento elegido por Windows.
    # Todas las superficies derivadas comparten así la misma tonalidad,
    # conservando sus diferencias de luminosidad y contraste.
    if dark:
        background = blend(background, palette["accent"], 0.12)

    # En DARK, formularios y galerías comparten el mismo fondo.
    # LIGHT conserva sus tonalidades originales.
    field = blend(background, foreground, 0.16 if dark else 0.0)
    surface = field if dark else blend(background, foreground, 0.04)

    control = blend(background, foreground, 0.20 if dark else 0.02)
    selected = blend(background, foreground, 0.23 if dark else 0.12)
    border = blend(background, foreground, 0.35 if dark else 0.22)
    accent = palette["accent_light1" if dark else "accent_dark1"]
    thumb = blend(foreground, background, 0.10 if dark else 1.0)

    # --- Apariencia Windows 11 desde recurso propio ---
    # PyInstaller sitúa los módulos en runtime, pero los recursos
    # propios de WMM permanecen en la raíz de instalación.
    css_path = _get_win32_css_path()

    try:
        with open(css_path, "r", encoding="utf-8") as source:
            stylesheet = source.read()
    except OSError as error:
        log_event(f"CSS Windows no disponible: {css_path}: {error}",
            origin="WIN32", level="WARN", reason="SETTINGS")
        return

    # --- Reglas exclusivas del modo oscuro ---
    # Las marcas son literales completos: su mención en la cabecera
    # del archivo no debe confundirse con el delimitador del bloque.
    start_marker = "/* WMM-DARK-BEGIN */"
    end_marker = "/* WMM-DARK-END */"

    if stylesheet.count(start_marker) != 1 or stylesheet.count(end_marker) != 1:
        log_event("Delimitadores del CSS Windows ausentes o duplicados",
            origin="WIN32", level="ERROR", reason="SETTINGS")
        return

    before, _, remainder = stylesheet.partition(start_marker)
    dark_css, separator, after = remainder.partition(end_marker)
    if not separator:
        log_event("Orden inválido de bloques en el CSS Windows",
            origin="WIN32", level="ERROR", reason="SETTINGS")
        return

    stylesheet = before + (dark_css if dark else "") + after

    # --- Colores dinámicos desde WinRT ---
    # Conservar las mismas mezclas que utilizaba el CSS incrustado.
    colors = {
        "foreground": foreground,
        "surface": surface,
        "field": field,
        "control": control,
        "selected": selected,
        "border": border,
        "accent": accent,
        "thumb": thumb,
        "button_hover": blend(control, foreground, 0.12),
        "button_pressed": blend(control, foreground, 0.23),
        "button_checked": blend(control, foreground, 0.18),
        "text_disabled": blend(foreground, background, 0.55),
        "hover_dark": blend(control, foreground, 0.24),
        "pressed_dark": blend(control, foreground, 0.10),
        "border_hover_dark": blend(border, foreground, 0.20),
        "nav_checked_hover_dark": blend(control, foreground, 0.28),
    }

    definitions = "\n".join(f"@define-color wmm_win32_{name} {value};"
        for name, value in colors.items())

    css = definitions + "\n" + stylesheet

    # --- Proveedor CSS exclusivo de Windows ---
    # Se reutiliza en los cambios de esquema, sin acumular proveedores.
    try:
        if _win32_palette_provider is None:
            screen = Gdk.Screen.get_default()
            if screen is None:
                return

            provider = Gtk.CssProvider()
            provider.load_from_data(css.encode("utf-8"))

            Gtk.StyleContext.add_provider_for_screen(
                screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)

            _win32_palette_provider = provider
            _win32_palette_css = css
        elif css != _win32_palette_css:
            # DWM puede notificar varias veces un mismo cambio.
            # Recargar únicamente si varía el CSS resultante.
            _win32_palette_provider.load_from_data(css.encode("utf-8"))
            _win32_palette_css = css

    except Exception as error:
        log_event(f"No se pudo aplicar la paleta Windows a GTK: {error}",
            origin="WIN32", level="WARN", reason="SETTINGS")

def get_system_color_scheme():
    """
    Traduce la preferencia visual nativa de Windows al contrato común de WMM.

    AppsUseLightTheme pertenece a la preferencia de las aplicaciones, que es la
    que corresponde a los formularios GTK. Un valor ausente o desconocido deja
    la decisión al toolkit en lugar de imponer arbitrariamente claro u oscuro.
    """
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _SYSTEM_COLOR_SCHEME_KEY) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
    except OSError:
        return None

    if value == 0:
        return "dark"
    if value == 1:
        return "light"

    return None

def _apply_system_color_scheme_to_gtk(settings, scheme, css_available):
    """
    Comunica la preferencia claro/oscuro de Windows a GTK.

    El tema win32 no dispone de una variante oscura equivalente
    a Windows 11. La paleta WinRT complementa esa limitación.
    """
    # --- Preferencia del sistema ---
    if scheme in ("light", "dark"):
        prefer_dark = scheme == "dark"

        if settings.get_property("gtk-application-prefer-dark-theme") != prefer_dark:
            settings.set_property("gtk-application-prefer-dark-theme", prefer_dark)

    # --- Paleta nativa Windows 11 ---
    # Sin CSS propio mantenemos la preferencia LIGHT/DARK de GTK,
    # pero no intentamos aplicar la paleta específica de WMM.
    if css_available:
        _apply_win32_palette_to_gtk(scheme)

    return False

def prepare_gtk_color_scheme(apply_win32_style=True):
    """
    Completa en Windows el puente de preferencia visual que GTK3 no proporciona.

    Aplica primero el estado actual y vigila LIGHT/DARK y acento mediante
    esperas nativas independientes, sin polling ni temporizadores.
    """
    global _system_color_scheme_thread, _system_color_accent_thread

    import gi
    import winreg

    gi.require_version("Gtk", "3.0")
    from gi.repository import GLib, Gtk

    settings = Gtk.Settings.get_default()
    if settings is None:
        log_event("Gtk.Settings no disponible para sincronizar el esquema de color",
            origin="WIN32", level="ERROR", reason="SETTINGS")
        return False

    # --- Disponibilidad del recurso visual ---
    # La ausencia del CSS desactiva la adaptación visual Win32,
    # pero conserva la sincronización LIGHT/DARK del sistema.
    css_path = _get_win32_css_path()

    # La vigilancia LIGHT/DARK es independiente de la apariencia GTK.
    # Cada proceso decide si utiliza la personalización visual WMM/Win32.
    css_available = apply_win32_style and os.path.isfile(_get_win32_css_path())

    if not css_available:
        log_event(f"CSS Windows ausente; sincronización LIGHT/DARK conservada: {css_path}",
            origin="WIN32", level="INFO", reason="SETTINGS")

    initial_scheme = get_system_color_scheme()

    # --- Integración visual nativa de Windows ---
    # El tema Win32 requiere la paleta propia para representar
    # correctamente los controles en LIGHT y DARK.
    if css_available:
        settings.set_property("gtk-theme-name", "win32")

    _apply_system_color_scheme_to_gtk(settings, initial_scheme, css_available)
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    reg_notify = advapi32.RegNotifyChangeKeyValue
    reg_notify.argtypes = [
        wintypes.HANDLE,
        wintypes.BOOL,
        wintypes.DWORD,
        wintypes.HANDLE,
        wintypes.BOOL,
    ]
    reg_notify.restype = wintypes.LONG

    # --- Acento dinámico: vigilar DWM sin interferir con LIGHT/DARK ---
    # La notificación indica un cambio potencial; los colores reales
    # continúan obteniéndose de UISettings en el hilo GTK.
    if css_available and (_system_color_accent_thread is None
            or not _system_color_accent_thread.is_alive()):
        try:
            accent_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                _SYSTEM_ACCENT_KEY, 0, winreg.KEY_READ)
        except OSError as error:
            log_event(f"No se pudo vigilar el acento de Windows: {error}",
                origin="WIN32", level="WARN", reason="SETTINGS")
        else:
            def watch_system_accent():
                with accent_key:
                    while True:
                        result = reg_notify(int(accent_key), False,
                            _REG_NOTIFY_CHANGE_LAST_SET, None, False)
                        if result != 0:
                            log_event(f"Falló la vigilancia del acento de Windows "
                                f"(código {result})",
                                origin="WIN32", level="ERROR", reason="SETTINGS")
                            return

                        # Nunca acceder a Gtk.CssProvider desde este hilo.
                        GLib.idle_add(_apply_win32_palette_to_gtk,
                            get_system_color_scheme())

            _system_color_accent_thread = threading.Thread(
                target=watch_system_accent,
                name="wmm-system-color-accent", daemon=True)
            _system_color_accent_thread.start()

    if (_system_color_scheme_thread is not None
            and _system_color_scheme_thread.is_alive()):
        return True

    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
            _SYSTEM_COLOR_SCHEME_KEY, 0, winreg.KEY_READ)
    except OSError as error:
        log_event(f"No se pudo monitorizar el esquema de color de Windows: {error}",
            origin="WIN32", level="ERROR", reason="SETTINGS")
        return False

    def watch_system_color_scheme():
        current_scheme = initial_scheme

        with key:
            while True:
                result = reg_notify(
                    int(key), False, _REG_NOTIFY_CHANGE_LAST_SET, None, False)

                if result != 0:
                    log_event(
                        f"Falló RegNotifyChangeKeyValue para el esquema de color "
                        f"(código {result})",
                        origin="WIN32", level="ERROR", reason="SETTINGS")
                    return

                scheme = get_system_color_scheme()

                # Personalize contiene más valores; despertar no implica que
                # AppsUseLightTheme haya cambiado realmente.
                if scheme not in ("light", "dark") or scheme == current_scheme:
                    continue

                current_scheme = scheme
                GLib.idle_add(_apply_system_color_scheme_to_gtk,
                              settings, scheme, css_available)

                log_event(f"Esquema de color de Windows cambiado a '{scheme}'",
                    origin="WIN32", level="INFO", reason="SETTINGS")

    _system_color_scheme_thread = threading.Thread(
        target=watch_system_color_scheme,
        name="wmm-system-color-scheme",
        daemon=True)
    _system_color_scheme_thread.start()

    return True

# ----------------------------------------------------------------------
# PRESENTACIÓN DE MENÚS CONTEXTUALES GTK EN WINDOWS
# ----------------------------------------------------------------------

def prepare_gtk_context_menu(menu):
    """Evita el marco azul del tema GTK win32 en los menús contextuales.

    La ventana interna de Gtk.Menu solicita decoraciones CSD.
    Desactivarlas elimina el marco sin renunciar al tema win32,
    necesario para mantener la geometría de los controles.
    """
    from gi.repository import Gtk

    popup = menu.get_toplevel()
    if isinstance(popup, Gtk.Window):
        popup.set_decorated(False)

# ----------------------------------------------------------------------
# RECUPERACIÓN D&D TRAS CAMBIO DE TOPOLOGÍA (GTK/WIN32)
# ----------------------------------------------------------------------
def recover_dnd_after_topology_change(window):
    """
    Workaround GTK3/Win32 para recuperar el D&D tras cambios de topología.

    Reconstruir los widgets y revalidar la posición mediante SetWindowPos
    no recuperaba el D&D. Un desplazamiento real de la ventana mediante
    GTK sí lo consigue (validado el 14-10-2026).

    Se desplaza 1 píxel sin restauración. El efecto puede acumularse,
    pero evita introducir una segunda transición y su sincronización.
    """
    if not window.get_mapped():
        return False

    try:
        x, y = window.get_position()
        window.move(x + 1, y)

        log_event("Recuperación D&D: desplazamiento GTK de 1 píxel solicitado",
            origin="WIN32", level="DEBUG", reason="HARDWARE")

    except Exception as error:
        log_event(f"No se pudo recuperar D&D mediante desplazamiento GTK: {error}",
            origin="WIN32", level="WARN", reason="HARDWARE")

    # GLib.idle_add: ejecución única, sin repetición.
    return False

# ----------------------------------------------------------------------
# PRESENTACIÓN Y AUTORIZACIÓN DEL PRIMER PLANO
# ----------------------------------------------------------------------

def present_window(window, form_name=None):
    """Presenta GTK y aplica, si procede, la iconografía nativa Windows."""
    from gi.repository import GLib

    def activate_native():
        if not window.get_mapped():
            return False

        try:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            signatures = {
                "EnumWindows": (wintypes.BOOL, [enum_proc, wintypes.LPARAM]),
                "GetWindowThreadProcessId": (wintypes.DWORD,
                    [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]),
                "GetWindowTextLengthW": (ctypes.c_int, [wintypes.HWND]),
                "GetWindowTextW": (ctypes.c_int,
                    [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]),
                "IsWindowVisible": (wintypes.BOOL, [wintypes.HWND]),
                "SetForegroundWindow": (wintypes.BOOL, [wintypes.HWND]),
                "GetForegroundWindow": (wintypes.HWND, []),
            }
            for name, (result_type, argument_types) in signatures.items():
                function = getattr(user32, name)
                function.restype = result_type
                function.argtypes = argument_types

            process_id = os.getpid()
            title = window.get_title() or ""
            matches = []

            @enum_proc
            def find_window(hwnd, data):
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value != process_id or not user32.IsWindowVisible(hwnd):
                    return True
                text = ctypes.create_unicode_buffer(user32.GetWindowTextLengthW(hwnd) + 1)
                user32.GetWindowTextW(hwnd, text, len(text))
                if text.value == title:
                    matches.append(hwnd)
                return True

            # Una enumeración por presentación, nunca una búsqueda periódica.
            # PID y título evitan activar una ventana de otro proceso WMM.
            if not user32.EnumWindows(find_window, 0):
                raise ctypes.WinError(ctypes.get_last_error())
            if len(matches) != 1:
                log_event(f"[FOCO] pid={process_id} titulo={title!r} coincidencias={len(matches)}",
                    origin="WIN32", level="WARN", reason="WINDOW")
                return False

            hwnd = matches[0]

            # Aprovechar el HWND ya identificado; ningún sondeo adicional.
            if form_name is not None:
                _apply_form_taskbar_icon(window, hwnd, form_name)

            before = user32.GetForegroundWindow()
            activated = bool(user32.SetForegroundWindow(hwnd))
            after = user32.GetForegroundWindow()

            if not activated or after != hwnd:
                log_event(
                    f"[FOCO] Activación no confirmada: pid={process_id} "
                    f"hwnd={hwnd:#x} titulo={title!r} resultado={activated} "
                    f"anterior={before or 0:#x} actual={after or 0:#x}",
                    origin="WIN32", level="WARN", reason="WINDOW")

        except Exception as error:
            log_event(f"[FOCO] Error al presentar la ventana: {error}",
                origin="WIN32", level="ERROR", reason="WINDOW")
        return False

    if window.get_mapped():
        window.present()
        GLib.idle_add(activate_native)
    else:
        def on_map(widget, event):
            widget.disconnect(handler_id)
            GLib.idle_add(activate_native)
            return False

        handler_id = window.connect("map-event", on_map)
        window.present()

def allow_foreground_window(process_id):
    """Autoriza a un PID concreto a activar una ventana, si Windows lo permite."""
    try:
        if not isinstance(process_id, int) or not 0 < process_id < 0xFFFFFFFF:
            raise ValueError("PID de destino inválido")

        allow = ctypes.WinDLL("user32", use_last_error=True).AllowSetForegroundWindow
        allow.argtypes = [wintypes.DWORD]
        allow.restype = wintypes.BOOL
        ctypes.set_last_error(0)
        granted = bool(allow(process_id))
        error = ctypes.get_last_error() if not granted else 0

        if not granted:
            log_event(
                f"[FOCO] Autorización denegada: emisor={os.getpid()} "
                f"destino={process_id} error={error}",
                origin="WIN32", level="WARN", reason="WINDOW")
        return granted

    except Exception as error:
        log_event(f"[FOCO] Error al autorizar el primer plano: {error}",
            origin="WIN32", level="ERROR", reason="WINDOW")
        return False

# ----------------------------------------------------------------------
# IDIOMA DE INTERFAZ PARA GETTEXT
# ----------------------------------------------------------------------
def prepare_gettext_environment():
    """
    Expone a GNU gettext los idiomas de interfaz preferidos por el usuario.

    Windows conoce el idioma de la sesión mediante sus APIs nativas, pero no
    exporta normalmente LANGUAGE/LC_* como los escritorios Unix.
    WMM traduce aquí esa preferencia al mecanismo estándar que ya consume gettext.

    Una configuración gettext explícita del proceso siempre tiene prioridad.
    """
    gettext_vars = ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG")
    if any(os.environ.get(name) for name in gettext_vars):
        return False

    MUI_LANGUAGE_NAME = 0x00000008

    get_languages = _kernel32.GetUserPreferredUILanguages
    get_languages.argtypes = [
        wintypes.DWORD, ctypes.POINTER(wintypes.ULONG),
        wintypes.LPWSTR, ctypes.POINTER(wintypes.ULONG),
    ]
    get_languages.restype = wintypes.BOOL

    language_count = wintypes.ULONG()
    buffer_length = wintypes.ULONG()

    if not get_languages(MUI_LANGUAGE_NAME,
        ctypes.byref(language_count), None, ctypes.byref(buffer_length)):
        return False

    if buffer_length.value == 0:
        return False

    buffer = ctypes.create_unicode_buffer(buffer_length.value)

    if not get_languages(MUI_LANGUAGE_NAME,
        ctypes.byref(language_count), buffer, ctypes.byref(buffer_length)):
        return False

    languages = []
    raw_languages = ctypes.wstring_at(buffer, buffer_length.value)

    for language in raw_languages.split("\0"):
        if not language:
            continue

        normalized = language.replace("-", "_")
        candidates = [normalized]

        base_language = normalized.split("_", 1)[0]
        if base_language != normalized:
            candidates.append(base_language)

        for candidate in candidates:
            if candidate not in languages:
                languages.append(candidate)

    if not languages:
        return False

    os.environ["LANGUAGE"] = ":".join(languages)
    return True

# ----------------------------------------------------------------------
# RUTAS DEL SISTEMA Y DATOS DE USUARIO
# ----------------------------------------------------------------------
def get_system_paths():
    """
    Resuelve las rutas de usuario propias de WMM sobre Win32.

    La identidad técnica wmm@maki no se utiliza como nombre físico en Windows:
    los datos escribibles se agrupan bajo el nombre visible WMM Manager.
    """
    user_home = os.path.expanduser("~")

    roaming_base = (
        os.environ.get("APPDATA")
        or os.path.join(user_home, "AppData", "Roaming"))
    local_base = (os.environ.get("LOCALAPPDATA")
        or os.path.join(user_home, "AppData", "Local"))

    app_config = os.path.join(roaming_base, "WMM Manager")

    return {
        'data_base': roaming_base,
        'config_base': roaming_base,
        'cache_base': local_base,
        'app_config': app_config,
        'data_dir': os.path.join(app_config, "data"),
        'locale_dir': os.path.join(app_config, "locale"),
        'cache_dir': os.path.join(local_base, "WMM Manager", "cache"),
    }

# ----------------------------------------------------------------------
# GESTIÓN DE PROCESOS
# ----------------------------------------------------------------------
def terminate_process(pid):
    """
    Finaliza forzosamente un proceso Win32 ya identificado por su PID.

    La identidad del proceso debe validarse antes de llegar aquí; esta función
    sólo materializa la terminación específica del sistema operativo.
    """
    PROCESS_TERMINATE = 0x0001

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    kernel32.OpenProcess.argtypes = [ wintypes.DWORD, wintypes.BOOL, wintypes.DWORD, ]
    kernel32.OpenProcess.restype = wintypes.HANDLE

    kernel32.TerminateProcess.argtypes = [ wintypes.HANDLE, wintypes.UINT, ]
    kernel32.TerminateProcess.restype = wintypes.BOOL

    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)

    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())

    try:
        if not kernel32.TerminateProcess(handle, 1):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel32.CloseHandle(handle)

# ----------------------------------------------------------------------
# OPERACIONES DE BLOQUEO DE ARCHIVOS
# ----------------------------------------------------------------------
def lock_file(f):
    """
    Adquiere de forma bloqueante el lock exclusivo multiproceso de WMM.

    La región centinela queda fuera del contenido real del archivo, por lo que
    la sincronización no interfiere con las lecturas ni depende de su cursor.
    """
    handle = msvcrt.get_osfhandle(f.fileno())
    overlapped = _new_lock_overlapped()

    if not _LockFileEx(handle, _LOCKFILE_EXCLUSIVE_LOCK,
        0, _LOCK_LENGTH, 0, ctypes.byref(overlapped)):
        raise ctypes.WinError(ctypes.get_last_error())

def try_lock_file(f):
    """
    Intenta adquirir sin espera el mismo lock exclusivo de lock_file().

    Sólo una colisión con otro proceso se traduce a False. Cualquier otro
    error Win32 se propaga para no confundir un fallo real con un lock ocupado.
    """
    handle = msvcrt.get_osfhandle(f.fileno())
    overlapped = _new_lock_overlapped()
    flags = _LOCKFILE_EXCLUSIVE_LOCK | _LOCKFILE_FAIL_IMMEDIATELY

    if _LockFileEx(handle, flags, 0, _LOCK_LENGTH, 0, ctypes.byref(overlapped)):
        return True

    error_code = ctypes.get_last_error()
    if error_code == _ERROR_LOCK_VIOLATION:
        return False

    raise ctypes.WinError(error_code)

def unlock_file(f):
    """
    Libera exactamente la misma región centinela adquirida por WMM.
    """
    handle = msvcrt.get_osfhandle(f.fileno())
    overlapped = _new_lock_overlapped()

    if not _UnlockFileEx(handle, 0, _LOCK_LENGTH, 0, ctypes.byref(overlapped)):
        raise ctypes.WinError(ctypes.get_last_error())

# ----------------------------------------------------------------------
# APERTURA DE ARCHIVOS
# ----------------------------------------------------------------------

def open_file(path, capability=None, data_dir=None, **params):
    """
    Abre archivos y directorios mediante las asociaciones nativas de Windows.

    Para capacidades adicionales, identifica el ejecutable asociado y
    delega la construcción del comando al núcleo de WMM.
    Sin perfil compatible conserva la apertura habitual con os.startfile().
    """
    if capability and data_dir:
        extension = os.path.splitext(path)[1]

        if extension:
            try:
                # Consultar el ejecutable registrado para la extensión.
                # Windows mantiene la autoridad sobre las asociaciones.
                query = ctypes.WinDLL("shlwapi").AssocQueryStringW
                query.argtypes = [
                    wintypes.DWORD, wintypes.DWORD,
                    wintypes.LPCWSTR, wintypes.LPCWSTR,
                    wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
                query.restype = ctypes.c_long

                # ASSOCSTR_EXECUTABLE = 2. La primera consulta obtiene
                # el tamaño requerido; S_FALSE = 1 indica ese resultado.
                size = wintypes.DWORD()

                if query(0, 2, extension, None, None, ctypes.byref(size)) == 1 and size.value:
                    buffer = ctypes.create_unicode_buffer(size.value)

                    if query(0, 2, extension, None, buffer, ctypes.byref(size)) == 0:
                        command = _build_launch_command(
                            buffer.value, path, capability, params, data_dir)

                        if command:
                            subprocess.Popen(command)
                            return

            except (OSError, ValueError, AttributeError) as error:
                log_event(f"No se pudo ejecutar lanzamiento enriquecido: {error}",
                    origin="WIN32", level="WARN", reason="GENERIC")

    # Sin capacidad compatible, mantener el comportamiento original.
    os.startfile(path)

# ----------------------------------------------------------------------
# NOTIFICACIONES
# ----------------------------------------------------------------------

def send_notification(title, message, level="info"):
    """Entrega un informe al HWND del frontend que posee el icono residente."""
    class COPYDATASTRUCT(ctypes.Structure):
        _fields_ = [("dwData", ctypes.c_size_t), ("cbData", wintypes.DWORD),
                    ("lpData", ctypes.c_void_p)]

    payload_text = ""
    try:
        payload_text = json.dumps(
            {"title": str(title), "message": str(message), "level": str(level)},
            ensure_ascii=False, separators=(",", ":"))
        payload = payload_text.encode("utf-8")
        if len(payload) > 65536:
            raise ValueError("El informe supera los 65536 bytes del transporte")

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        user32.FindWindowW.restype = wintypes.HWND
        user32.SendMessageTimeoutW.argtypes = [
            wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
            wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]
        user32.SendMessageTimeoutW.restype = ctypes.c_ssize_t

        # Identidad del HWND publicado por windows-frontend.py. Se resuelve
        # por envio: no conservamos handles obsoletos tras reiniciar el frontend.
        hwnd = user32.FindWindowW("WMMWindowsFrontendWindow", None)
        if not hwnd:
            raise RuntimeError("El frontend Windows no esta disponible")

        buffer = ctypes.create_string_buffer(payload)
        data = COPYDATASTRUCT(0x574D4D4E, len(payload), ctypes.addressof(buffer))
        reply = ctypes.c_size_t()
        ctypes.set_last_error(0)

        # WM_COPYDATA copia los bytes entre procesos; buffer y data permanecen
        # vivos durante el envio. El limite evita bloquear ante un HWND colgado.
        delivered = user32.SendMessageTimeoutW(
            hwnd, 0x004A, 0, ctypes.addressof(data),
            0x0001 | 0x0002 | 0x0020, 2000, ctypes.byref(reply))
        if not delivered:
            raise RuntimeError(
                f"No se pudo entregar la notificacion: error={ctypes.get_last_error()}")
        if not reply.value:
            raise RuntimeError("El frontend rechazo la notificacion")

        # La respuesta confirma aceptacion nativa, no visibilidad en pantalla.
        return True

    except Exception as error:
        # Conservar el informe completo tambien si no cabe o falta el frontend.
        log_event(f"No se pudo mostrar la notificacion: {error}; informe={payload_text}",
            origin="WIN32", level="WARN", reason="NOTIFY")
        return False

# ----------------------------------------------------------------------
# HERRAMIENTAS Y COMPILACIÓN DE GETTEXT
# ----------------------------------------------------------------------
def resolve_gettext_tool(tool_name):
    """
    Resuelve una herramienta GNU gettext incluida en el runtime privado Win32.

    Las utilidades distribuidas por WMM viven junto al intérprete embebido y no
    deben depender de MSYS2 instalado ni del PATH global del sistema.
    """
    executable_name = (tool_name if tool_name.lower().endswith(".exe") else f"{tool_name}.exe")
    # En PyInstaller onedir, las dependencias están en runtime/,
    # identificado por _MEIPASS. Sin empaquetar, permanecen
    # junto al intérprete Python.
    tool_dir = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    tool_path = os.path.join(tool_dir, executable_name)

    return tool_path if os.path.isfile(tool_path) else None

def compile_translations(app_root, locale_dir, app_domain):
    """
    Compila traducciones pendientes con el msgfmt incluido en el runtime Win32.

    Los catálogos se escriben en locale_dir usando el dominio propio de la
    plataforma activa; en Windows éste es deliberadamente "WMM Manager".
    """
    po_dir = os.path.join(app_root, "wmm_platform", "shell", "po")
    if not os.path.isdir(po_dir):
        return False

    # El resolver común localiza msgfmt en el runtime privado, sin depender
    # de MSYS2 instalado ni del PATH del sistema.
    msgfmt_path = resolve_gettext_tool("msgfmt")
    if msgfmt_path is None:
        expected_path = os.path.join(os.path.dirname(sys.executable), "msgfmt.exe")
        log_event(f"No se encontró msgfmt.exe en el runtime: {expected_path}",
            origin="WIN32", level="ERROR", reason="SETTINGS")
        return False

    translations_changed = False

    for po_file in os.listdir(po_dir):
        if not po_file.endswith(".po"):
            continue

        lang = os.path.splitext(po_file)[0]
        mo_dir = os.path.join(locale_dir, lang, "LC_MESSAGES")
        mo_file = os.path.join(mo_dir, f"{app_domain}.mo")
        po_path = os.path.join(po_dir, po_file)

        if not os.path.exists(mo_file) or os.path.getmtime(po_path) > os.path.getmtime(mo_file):
            try:
                os.makedirs(mo_dir, exist_ok=True)
                # msgfmt.exe es una aplicación de consola; evitar que abra
                # una ventana fugaz durante el arranque gráfico de WMM.
                result = subprocess.run(
                    [msgfmt_path, po_path, "-o", mo_file],
                    check=False, capture_output=True, text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW)

                if result.returncode == 0 and os.path.isfile(mo_file):
                    translations_changed = True
                else:
                    log_event(f"Error compilando traducción '{po_file}': {result.stderr.strip()}",
                        origin="WIN32", level="ERROR", reason="SETTINGS")

            except Exception as error:
                log_event(f"Excepción compilando traducción '{po_file}': {error}",
                    origin="WIN32", level="ERROR", reason="SETTINGS")

    return translations_changed

# ----------------------------------------------------------------------
# ATAJO GLOBAL DE SIGUIENTE FONDO
# ----------------------------------------------------------------------

def _next_background_hotkey_binding(shortcut):
    """Valida los datos genéricos y devuelve (combinación, modificadores, VK)."""
    if shortcut is None:
        return None, 0, 0
    if not isinstance(shortcut, dict):
        raise ValueError("La combinación del atajo debe ser un objeto o null")

    key = shortcut.get("key")
    modifiers = shortcut.get("modifiers")
    if not isinstance(key, str) or not isinstance(modifiers, list):
        raise ValueError("El atajo requiere una tecla y una lista de modificadores")

    # El JSON conserva nombres estables. Los textos traducidos pertenecen
    # exclusivamente al formulario y a la etiqueta del menú.
    modifier_values = {"Control": 0x0002, "Alt": 0x0001, "Shift": 0x0004}
    if any(not isinstance(name, str) or name not in modifier_values for name in modifiers):
        raise ValueError("El atajo contiene un modificador no admitido")
    modifiers = [name for name in modifier_values if name in modifiers]
    key = key.upper()

    if len(key) == 1 and key in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789":
        if not ({"Control", "Alt"} & set(modifiers)):
            raise ValueError("Los atajos de letras y números requieren Control o Alt")
        virtual_key = ord(key)
    elif key.startswith("F") and key[1:].isdigit() and 1 <= int(key[1:]) <= 11:
        # Se conserva el alcance probado: F1–F11. F12 está reservada
        # por Windows para el depurador y no se ofrece en el formulario.
        key = f"F{int(key[1:])}"
        virtual_key = 0x70 + int(key[1:]) - 1
    else:
        raise ValueError("Tecla de atajo no admitida")

    # MOD_NOREPEAT se añadirá al registrar; no forma parte de la combinación
    # del usuario ni de su representación persistente.
    flags = sum(modifier_values[name] for name in modifiers)
    return {"key": key, "modifiers": modifiers}, flags, virtual_key

# ----------------------------------------------------------------------
# CONTEXTO DEL ESCRITORIO PARA EL EXPLORADOR
# ----------------------------------------------------------------------
class _ExplorerDesktopContext:
    """Conserva el clic original; su propietario es el receptor del engine."""

    def __init__(self):
        self._lock = threading.Lock()
        self._click = None
        self._ready = threading.Event()
        self._thread = None
        self._thread_id = None
        self._user32 = None
        self._error = None

    def start(self):
        """Espera sólo la instalación del hook, sin polling ni demora prefijada."""

        self._thread = threading.Thread(
            target=self._listen, name="WMM-DesktopContext", daemon=True)
        self._thread.start()
        self._ready.wait()
        if self._error is not None:
            log_event(f"No se pudo observar el contexto del escritorio: {self._error}",
                origin="WIN32", level="ERROR", reason="COMMAND")
            return False
        return True

    def stop(self):
        """Despierta GetMessage para retirar el hook antes de salir del proceso."""
        if self._thread is not None and self._thread.is_alive() and self._thread_id:
            if self._user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0):
                self._thread.join()

    def take_position(self):
        """Consume el contexto una vez y comprueba su ventana de origen."""
        if self._thread is None or not self._thread.is_alive() or self._error is not None:
            return None
        with self._lock:
            click, self._click = self._click, None
        if click is None:
            return None

        x, y, hwnd = click
        if not hwnd:
            return None

        def window_class(window):
            name = ctypes.create_unicode_buffer(256)
            self._user32.GetClassNameW(window, name, len(name))
            return name.value

        root = self._user32.GetAncestor(hwnd, 2)  # GA_ROOT, sin saltar a owners.
        # El Explorador también contiene SHELLDLL_DefView. La raíz distingue
        # sus carpetas del escritorio; no basta con comprobar la clase hija.
        if (not root or window_class(root) not in {"Progman", "WorkerW"}
                or window_class(hwnd) not in {
                    "SysListView32", "SHELLDLL_DefView", "Progman", "WorkerW"}):
            return None
        return x, y

    def _listen(self):
        """El hilo nativo sólo captura; ni ejecuta acciones ni escribe en disco."""
        hook = None
        previous_dpi = None
        user32 = None
        try:
            class MouseEvent(ctypes.Structure):
                _fields_ = [("pt", wintypes.POINT), ("mouseData", wintypes.DWORD),
                    ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("extra", ctypes.c_size_t)]

            class Message(ctypes.Structure):
                _fields_ = [("hwnd", wintypes.HWND), ("message", wintypes.UINT),
                    ("wParam", wintypes.WPARAM), ("lParam", wintypes.LPARAM),
                    ("time", wintypes.DWORD), ("pt", wintypes.POINT),
                    ("lPrivate", wintypes.DWORD)]

            hook_proc = ctypes.WINFUNCTYPE(
                ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            signatures = {
                "SetWindowsHookExW": (wintypes.HANDLE,
                    [ctypes.c_int, hook_proc, wintypes.HINSTANCE, wintypes.DWORD]),
                "CallNextHookEx": (ctypes.c_ssize_t,
                    [wintypes.HANDLE, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]),
                "UnhookWindowsHookEx": (wintypes.BOOL, [wintypes.HANDLE]),
                "WindowFromPoint": (wintypes.HWND, [wintypes.POINT]),
                "GetAncestor": (wintypes.HWND, [wintypes.HWND, wintypes.UINT]),
                "GetClassNameW": (ctypes.c_int, [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]),
                "SetThreadDpiAwarenessContext": (wintypes.HANDLE, [wintypes.HANDLE]),
                "GetMessageW": (wintypes.BOOL,
                    [ctypes.POINTER(Message), wintypes.HWND, wintypes.UINT, wintypes.UINT]),
                "PeekMessageW": (wintypes.BOOL, [ctypes.POINTER(Message),
                    wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]),
                "PostThreadMessageW": (wintypes.BOOL,
                    [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]),
            }
            for name, (result_type, argument_types) in signatures.items():
                function = getattr(user32, name)
                function.restype = result_type
                function.argtypes = argument_types

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
            kernel32.GetModuleHandleW.restype = wintypes.HMODULE
            kernel32.GetCurrentThreadId.argtypes = []
            kernel32.GetCurrentThreadId.restype = wintypes.DWORD

            # Sólo este hilo adopta PMv2. No cambia la política DPI de GTK.
            previous_dpi = user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
            if not previous_dpi:
                raise ctypes.WinError(ctypes.get_last_error())
            self._user32 = user32
            message = Message()
            user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 0)
            self._thread_id = kernel32.GetCurrentThreadId()

            @hook_proc
            def on_mouse(code, event_type, data):
                if code >= 0 and event_type == 0x0204:  # WM_RBUTTONDOWN.
                    try:
                        event = ctypes.cast(data, ctypes.POINTER(MouseEvent)).contents
                        x, y = event.pt.x, event.pt.y
                        hwnd = user32.WindowFromPoint(wintypes.POINT(x, y))
                        with self._lock:
                            # Todo nuevo clic derecho sustituye al anterior,
                            # también si procede de una ventana ajena al escritorio.
                            self._click = (x, y, hwnd)
                    except Exception:
                        with self._lock:
                            self._click = None
                return user32.CallNextHookEx(hook, code, event_type, data)

            instance = kernel32.GetModuleHandleW(None)
            if not instance:
                raise ctypes.WinError(ctypes.get_last_error())
            hook = user32.SetWindowsHookExW(14, on_mouse, instance, 0)  # WH_MOUSE_LL.
            if not hook:
                raise ctypes.WinError(ctypes.get_last_error())
            self._ready.set()

            while True:
                result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result == -1:
                    raise ctypes.WinError(ctypes.get_last_error())
                if result == 0:
                    break
        except Exception as error:
            self._error = error
        finally:
            if hook:
                user32.UnhookWindowsHookEx(hook)
            if previous_dpi:
                user32.SetThreadDpiAwarenessContext(previous_dpi)
            with self._lock:
                self._click = None
            self._ready.set()

# ----------------------------------------------------------------------
# CANAL DE COMANDOS IPC
# ----------------------------------------------------------------------
def init_channels(data_dir):
    """
    Registra los canales de comunicación disponibles en Win32.

    Windows utiliza Named Pipes como transporte IPC nativo. FileChannel se
    mantiene como implementación propia de los entornos que disponen de una
    semántica de FileMonitor adecuada para ese mecanismo.
    """
    from wmm_platform.channels import register_channel, NamedPipeChannel

    class ExplorerCommandChannel(NamedPipeChannel):
        """Integra el contexto del escritorio y la autorización del primer plano."""

        def send(self, command):
            """Autoriza al engine para presentar formularios Win32 solicitados por el usuario."""
            # Los formularios solicitados por el usuario necesitan conservar
            # la autorización de primer plano al atravesar el canal hacia el engine.
            if command.get("action") not in {
                    "shell_send_to_monitor", "open_help", "open_panel"}:
                return super().send(command)

            from multiprocessing.connection import Client

            payload = json.dumps(command, ensure_ascii=False,
                separators=(",", ":")).encode("utf-8")
            if len(payload) > self._MAX_MESSAGE_SIZE:
                raise ValueError(
                    f"Comando Named Pipe demasiado grande: {len(payload)} bytes")

            connection = Client(self._address, family="AF_PIPE")

            try:
                try:
                    # El propio pipe identifica al engine que recibirá la orden.
                    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                    get_pid = kernel32.GetNamedPipeServerProcessId
                    get_pid.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.ULONG)]
                    get_pid.restype = wintypes.BOOL
                    engine_pid = wintypes.ULONG()

                    if not get_pid(connection.fileno(), ctypes.byref(engine_pid)):
                        raise ctypes.WinError(ctypes.get_last_error())

                    allow_foreground_window(engine_pid.value)

                except Exception as error:
                    log_event(f"[FOCO] Error al identificar el engine del pipe: {error}",
                        origin="WIN32", level="ERROR", reason="WINDOW")

                # Un permiso denegado no cancela la acción solicitada.
                connection.send_bytes(payload)

            finally:
                connection.close()

        def start_receiving_commands(self, callback):
            if self._thread is not None and self._thread.is_alive():
                return

            import atexit

            context = _ExplorerDesktopContext()
            context.start()

            def dispatch(order, payload):
                if payload.get("explorer_desktop") is True:
                    if order not in {"shell_add_favorite_current", "shell_spanned_current"}:
                        return False
                    position = context.take_position()
                    if position is None:
                        log_event("Acción del escritorio descartada: no hay un clic de origen válido",
                            origin="WIN32", level="WARN", reason="COMMAND")
                        return False
                    # El hook recibe coordenadas absolutas de Windows;
                    # WMM utiliza el origen normalizado del escritorio virtual.
                    user32 = ctypes.windll.user32
                    origin_x = user32.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
                    origin_y = user32.GetSystemMetrics(77)  # SM_YVIRTUALSCREEN
                    normalized = (position[0] - origin_x, position[1] - origin_y)

                    # El engine conserva la autoridad sobre el monitor y la imagen.
                    payload = {"action": order, "x": normalized[0], "y": normalized[1]}

                return callback(order, payload)

            try:
                super().start_receiving_commands(dispatch)
            except Exception:
                context.stop()
                raise
            atexit.register(context.stop)

    try:
        # Los clientes sólo registran el transporte. El observador no arranca
        # hasta que el engine activa start_receiving_commands().
        register_channel("pipe", ExplorerCommandChannel(data_dir))

    except Exception as e:
        log_event(f"No se pudo registrar NamedPipeChannel: {e}",
            origin="WIN32", level="ERROR", reason="COMMAND")

# ----------------------------------------------------------------------
# EVENTOS DEL ENGINE AL PANEL
# ----------------------------------------------------------------------
# El canal de eventos del panel no pertenece al registro general de comandos:
# tiene dirección inversa (engine -> panel) y un listener con lifecycle propio.
_panel_event_channel = None

def send_panel_event(data_dir, event_dict):
    """
    Envía un evento del engine al panel mediante su Named Pipe dedicado.

    Si el panel no está abierto no existe listener; esa ausencia es normal y
    conserva la semántica histórica de las notificaciones best-effort.
    """
    from wmm_platform.channels import NamedPipeChannel

    try:
        NamedPipeChannel(data_dir, endpoint="panel").send(event_dict)
        return True
    except OSError:
        return False

def start_receiving_panel_events(data_dir, callback):
    """
    Inicia el listener Win32 dedicado a eventos engine -> panel.

    NamedPipeChannel entrega (action, payload); el panel consume únicamente
    el payload completo, igual que hacía al leer command_panel.json.
    """
    global _panel_event_channel

    if _panel_event_channel is not None:
        return True

    from wmm_platform.channels import NamedPipeChannel

    channel = NamedPipeChannel(data_dir, endpoint="panel")
    channel.start_receiving_commands(
        lambda action, event_dict: callback(event_dict))

    _panel_event_channel = channel
    return True

# ----------------------------------------------------------------------
# REGISTRO DE ACCIONES DEL EXPLORADOR
# ----------------------------------------------------------------------
_SHELL_IMAGE_MENU_KEY = r"Software\Classes\SystemFileAssociations\image\shell\WMM.Manager"
_SHELL_IMAGE_COMMANDS_KEY = r"Software\Classes\WMM.Manager.ImageCommands"
_SHELL_DESKTOP_MENU_KEY = r"Software\Classes\DesktopBackground\shell\WMM.Manager"
_SHELL_DESKTOP_COMMANDS_KEY = r"Software\Classes\WMM.Manager.DesktopCommands"

def _notify_shell_actions_changed():
    """Invalida la caché de asociaciones del Explorador tras cambiar los verbos."""
    notify = ctypes.WinDLL("shell32", use_last_error=True).SHChangeNotify
    notify.argtypes = [wintypes.LONG, wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p]
    notify.restype = None
    # SHCNE_ASSOCCHANGED con SHCNF_IDLIST: las rutas deben ser NULL.
    notify(0x08000000, 0x0000, None, None)


def ensure_shell_actions(applet_root, data_base):
    """
    Instala las acciones de shell necesarias para Windows.

    Registra menús clásicos por usuario para imágenes y fondo del escritorio.
    Actualiza rutas y traducciones sólo cuando cambian; data_base conserva
    la firma común, pero el destino de Windows es el registro del usuario.
    """
    import winreg
    from i18n import _

    app_root = os.path.abspath(applet_root)

    # Open Code utiliza pythonw; PyInstaller utiliza el ejecutable
    # con su dispatcher para ejecutar los módulos integrados en PYZ.
    runner = (sys.executable if getattr(sys, "frozen", False)
        else os.path.join(os.path.dirname(sys.executable), "pythonw.exe"))

    adapter = os.path.join(app_root, "wmm_platform", "shell", "file_manager",
        "explorer", "wmm-explorer.py")
    sender = os.path.join(app_root, "python", "send_command.py")

    # En compilado, el dispatcher reconoce las rutas lógicas de los .py.
    for path in (runner, adapter, sender):
        if not os.path.isfile(path):
            log_event(f"No se pueden registrar las acciones del Explorador; falta: {path}",
                origin="WIN32", level="ERROR", reason="SETTINGS")
            return False

    # Recursos elegidos visualmente en el selector de iconos de Windows.
    native_icons = os.path.expandvars(r"%SystemRoot%\System32\SHELL32.dll")
    image_actions = (
        ("01-favorite", _("Add to favorites"), "shell_add_favorite", 296),
        ("02-monitor", _("Send to Monitor"), "shell_send_to_monitor", 264),
        ("03-span", _("Span image across all active screens"), "shell_spanned_image", 140), )
    desktop_actions = (
        ("01-favorite", _("Add to favorites"), "shell_add_favorite_current", 296),
        ("02-span", _("Span image across all active screens"), "shell_spanned_current", 140), )
    changed = False

    def set_value(path, name, value):
        """Evita reescrituras y avisos al shell en arranques sin cambios."""
        nonlocal changed
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0,
                winreg.KEY_READ | winreg.KEY_WRITE) as key:
            try:
                current, value_type = winreg.QueryValueEx(key, name)
            except FileNotFoundError:
                current, value_type = None, None
            if current != value or value_type != winreg.REG_SZ:
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
                changed = True

    try:
        # Los subcomandos pertenecen a WMM. No usar CommandStore global,
        # que exige permisos de administrador para registrar verbos propios.
        scopes = (
            (_SHELL_IMAGE_MENU_KEY, _SHELL_IMAGE_COMMANDS_KEY,
                "WMM.Manager.ImageCommands", image_actions, True),
            (_SHELL_DESKTOP_MENU_KEY, _SHELL_DESKTOP_COMMANDS_KEY,
                "WMM.Manager.DesktopCommands", desktop_actions, False),
        )
        icon = os.path.join(app_root, "WMM-icon.ico")
        for menu_key, commands_key, commands_class, actions, selected_image in scopes:
            for key_name, label, action, icon_index in actions:
                verb_key = commands_key + "\\shell\\" + key_name
                set_value(verb_key, "MUIVerb", label)
                set_value(verb_key, "Icon", f'"{native_icons}",{icon_index}')
                command = subprocess.list2cmdline([runner, adapter, action])
                if selected_image:
                    set_value(verb_key, "MultiSelectModel", "Single")
                    command += ' "%1"'
                set_value(verb_key + "\\command", "", command)

            # Publicar cada menú después de preparar sus comandos. image es
            # el tipo percibido; DesktopBackground limita el segundo menú al
            # fondo del escritorio, sin añadirlo a carpetas ni a sus fondos.
            set_value(menu_key, "", "")
            set_value(menu_key, "MUIVerb", "WMM Manager")
            set_value(menu_key, "ExtendedSubCommandsKey", commands_class)
            if selected_image:
                set_value(menu_key, "MultiSelectModel", "Single")
            if os.path.isfile(icon):
                set_value(menu_key, "Icon", f'"{icon}"')

        if changed:
            _notify_shell_actions_changed()
            log_event("Menús WMM Manager del Explorador registrados/actualizados",
                origin="WIN32", level="INFO", reason="SETTINGS")
        return True
    except OSError as error:
        log_event(f"No se pudieron registrar las acciones del Explorador: {error}",
            origin="WIN32", level="ERROR", reason="SETTINGS")
        return False

def remove_shell_actions():
    """Retira únicamente los menús y subcomandos propios de WMM del usuario."""
    import winreg

    def delete_tree(path):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0,
                    winreg.KEY_READ | winreg.KEY_WRITE) as key:
                children = [winreg.EnumKey(key, index)
                    for index in range(winreg.QueryInfoKey(key)[0])]
                for child in children:
                    delete_tree(path + "\\" + child)
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
            return True
        except FileNotFoundError:
            return False

    changed = False
    success = True
    for path in (_SHELL_IMAGE_MENU_KEY, _SHELL_IMAGE_COMMANDS_KEY,
            _SHELL_DESKTOP_MENU_KEY, _SHELL_DESKTOP_COMMANDS_KEY):
        try:
            changed = delete_tree(path) or changed
        except OSError as error:
            success = False
            log_event(f"No se pudo retirar la clave WMM {path}: {error}",
                origin="WIN32", level="ERROR", reason="SETTINGS")
    if changed:
        _notify_shell_actions_changed()
    return success
