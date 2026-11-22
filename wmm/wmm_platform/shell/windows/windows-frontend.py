#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

"""
WMM - Wallpaper Multi-Monitor Manager

windows-frontend.py - Windows frontend
======================================
Provides WMM presence in the Windows notification area.

The frontend deliberately separates responsibilities:
- Win32 owns the notification icon and native mouse events.
- GTK owns WMM's popup windows and their controls.
- GLib.idle_add() is the boundary between both threads.
- The WMM engine remains the authority for settings and actions.
"""

import ctypes
import json
import os
import subprocess
import sys
import tempfile
import threading

from ctypes import wintypes

import gi

gi.require_version("Gio", "2.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk

# ==========================================================
# IDENTIDAD Y RUTAS
# ==========================================================

def _find_app_dir():
    """
    Resuelve la raíz WMM tanto desde el árbol fuente como desde el runtime.

    Fuente:
        wmm_platform/shell/windows/windows-frontend.py

    Runtime futuro:
        frontends/windows/windows-frontend.py
    """
    frontend_dir = os.path.dirname(os.path.abspath(__file__))

    candidates = (
        os.path.abspath(os.path.join(frontend_dir, "..", "..", "..")),
        os.path.abspath(os.path.join(frontend_dir, "..", "..")),
    )

    for candidate in candidates:
        send_command = os.path.join(candidate, "python", "send_command.py")
        if os.path.isfile(send_command) and os.path.isdir(os.path.join(candidate, "wmm_platform")):
            return candidate

    raise RuntimeError("No se pudo localizar la raíz de WMM")

APP_DIR = _find_app_dir()

sys.path.insert(0, APP_DIR)
sys.path.insert(0, os.path.join(APP_DIR, "python"))

from wmm_platform.core import PlatformManager
from wmm_platform import win32 as win32_platform
import i18n

platform = PlatformManager()
i18n.initialize(platform)
_ = i18n._

SEND_COMMAND_PATH = os.path.join(platform.app_dir, "python", "send_command.py")
INSTALL_MANAGER_PATH = os.path.join(
    platform.app_dir, "wmm_platform", "shell", "installer", "wmm-install.ps1")
DEBUG_LOG_VIEWER_PATH = os.path.join(platform.app_dir, "python", "debug_log_viewer.py")
ICON_PATH = platform.icon_path
CSS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "windows-frontend.css")
SETTINGS_PATH = os.path.join(platform.data_dir, "settings.json")
BOOKMARKS_PATH = os.path.join(platform.data_dir, "bookmarks.json")
ENGINE_STATUS_PATH = os.path.join(platform.cache_dir, "engine_status.json")

FAVORITES_VISIBLE_ROWS = 4

# El popup principal contiene controles más densos que el contextual. Estos
# márgenes sustituyen el aire que antes aportaba Gtk.Menu sin alterar su lógica.
MAIN_POPUP_MIN_WIDTH = 240
MAIN_POPUP_BORDER = 8
MAIN_POPUP_ROW_MARGIN_X = 4
MAIN_POPUP_ROW_MARGIN_Y = 3

# ==========================================================
# WIN32: TIPOS
# ==========================================================

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)

LRESULT = ctypes.c_ssize_t

WNDPROC = ctypes.WINFUNCTYPE(
    LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]

class _TimeoutVersion(ctypes.Union):
    _fields_ = [("uTimeout", wintypes.UINT), ("uVersion", wintypes.UINT)]

class NOTIFYICONDATAW(ctypes.Structure):
    _anonymous_ = ("version",)

    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HANDLE),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("version", _TimeoutVersion),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", GUID),
        ("hBalloonIcon", wintypes.HANDLE),
    ]

class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HANDLE),
        ("hIcon", wintypes.HANDLE),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HANDLE),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]

# ==========================================================
# WIN32: CONSTANTES
# ==========================================================

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_CONTEXTMENU = 0x007B

WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_MBUTTONUP = 0x0208

WM_APP = 0x8000
WM_TRAYICON = WM_APP + 1
WM_TRAY_BUSY = WM_APP + 2
WM_TRAY_QUIT = WM_APP + 3

NIM_ADD = 0
NIM_MODIFY = 1
NIM_DELETE = 2
NIM_SETVERSION = 4

NIF_MESSAGE = 0x01
NIF_ICON = 0x02
NIF_TIP = 0x04
NIF_SHOWTIP = 0x80

NOTIFYICON_VERSION_4 = 4

IMAGE_ICON = 1

LR_LOADFROMFILE = 0x0010
LR_DEFAULTSIZE = 0x0040

TRAY_ID = 1

# Identidad Windows del proceso que publica los avisos de WMM.
NOTIFICATION_APP_ID = "WMM.Manager"

# Recurso nativo elegido para representar una operación en curso.
BUSY_ICON_PATH = os.path.expandvars(r"%SystemRoot%\System32\SHELL32.dll")
BUSY_ICON_INDEX = 238

# Recurso nativo alternativo si el icono propio de WMM no puede cargarse.
FALLBACK_ICON_PATH = os.path.expandvars(r"%SystemRoot%\System32\SHELL32.dll")
FALLBACK_ICON_INDEX = 174

# engine_status.json se observa mediante la primitiva nativa de Windows.
# ReadDirectoryChangesW duerme hasta recibir cambios y permite filtrar después
# por nombre, evitando reaccionar al resto de actividad del directorio cache.
FILE_LIST_DIRECTORY = 0x0001

FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
FILE_SHARE_DELETE = 0x00000004

OPEN_EXISTING = 3
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000

FILE_NOTIFY_CHANGE_FILE_NAME = 0x00000001
FILE_NOTIFY_CHANGE_LAST_WRITE = 0x00000010

INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

ERROR_ALREADY_EXISTS = 183
FRONTEND_MUTEX_NAME = r"Local\WMM.WindowsFrontend"

WINDOW_CLASS = "WMMWindowsFrontendWindow"

# ==========================================================
# WIN32: FIRMAS
# ==========================================================

kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HANDLE

kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE

kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL

kernel32.CreateFileW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.HANDLE,
]
kernel32.CreateFileW.restype = wintypes.HANDLE

kernel32.ReadDirectoryChangesW.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    wintypes.DWORD,
    wintypes.BOOL,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.c_void_p,
    ctypes.c_void_p,
]
kernel32.ReadDirectoryChangesW.restype = wintypes.BOOL

user32.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
user32.RegisterWindowMessageW.restype = wintypes.UINT

user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
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
    wintypes.HANDLE,
    wintypes.HANDLE,
    ctypes.c_void_p,
]
user32.CreateWindowExW.restype = wintypes.HWND

user32.DefWindowProcW.argtypes = [
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
user32.DefWindowProcW.restype = LRESULT

user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.DestroyWindow.restype = wintypes.BOOL

user32.PostMessageW.argtypes = [
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
user32.PostMessageW.restype = wintypes.BOOL

user32.GetMessageW.argtypes = [
    ctypes.POINTER(wintypes.MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
]
user32.GetMessageW.restype = wintypes.BOOL

user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]

user32.LoadImageW.argtypes = [
    wintypes.HANDLE,
    wintypes.LPCWSTR,
    wintypes.UINT,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
]
user32.LoadImageW.restype = wintypes.HANDLE

user32.DestroyIcon.argtypes = [wintypes.HANDLE]
user32.DestroyIcon.restype = wintypes.BOOL

shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
shell32.Shell_NotifyIconW.restype = wintypes.BOOL

shell32.SetCurrentProcessExplicitAppUserModelID.argtypes = [wintypes.LPCWSTR]
shell32.SetCurrentProcessExplicitAppUserModelID.restype = ctypes.c_int32

shell32.ExtractIconExW.argtypes = [
    wintypes.LPCWSTR,
    ctypes.c_int,
    ctypes.POINTER(wintypes.HANDLE),
    ctypes.POINTER(wintypes.HANDLE),
    wintypes.UINT,
]
shell32.ExtractIconExW.restype = wintypes.UINT

# ==========================================================
# ESTADO DEL FRONTEND
# ==========================================================

taskbar_created = user32.RegisterWindowMessageW("TaskbarCreated")

tray_data = NOTIFYICONDATAW()
tray_icon = None
busy_icon = None

window_handle = None
frontend_mutex = None
frontend_loop = None
shutdown_requested = False

main_menu = None
context_menu = None
context_autostart_item = None
context_autostart_handler = None

wmm_css_provider = None

favorites_expanded = False
favorites_header_item = None
favorites_switch_item = None
favorites_only_switch = None
favorites_add_item = None
favorites_scroll_item = None
favorites_scrolled = None
favorites_inline_list = None
cached_bookmarks = {}

slideshow_expanded = False
slideshow_header_item = None
slideshow_switch_item = None
slideshow_switch = None
slideshow_switch_label = None
slideshow_interval_item = None
slideshow_interval_label = None
slideshow_scale = None
slideshow_interval = 15
slideshow_max_interval = 60

# Una sola confirmación por interacción; el arrastre se confirma al soltar.
slideshow_scale_dragging = False
slideshow_scale_dirty = False
slideshow_scale_commit_id = None

displays_item = None
displays_label = None
spanned_item = None
metadata_switch = None
next_background_item = None
next_background_hotkey_label = None
motor_busy = False

menu_syncing_state = False

# ==========================================================
# ENGINE
# ==========================================================

def _send_action(command):
    """Envía una acción normal mediante el canal común de WMM."""
    if not os.path.isfile(SEND_COMMAND_PATH):
        print(f"[WMM WINDOWS] send_command.py no encontrado: {SEND_COMMAND_PATH}", flush=True)
        return False

    payload = json.dumps(command, ensure_ascii=False, separators=(",", ":"))
    try:
        Gio.Subprocess.new(
            [sys.executable, SEND_COMMAND_PATH, payload], Gio.SubprocessFlags.NONE)
        return True
    except GLib.Error as error:
        action = command.get("action", "unknown")
        print(f"[WMM WINDOWS] No se pudo enviar {action}: {error}", flush=True)
        return False

def _set_motor_busy(busy):
    """
    Refleja localmente el estado autoritativo del engine.

    La marca local sólo evita spam inmediato en este frontend; send_command.py
    y el propio engine conservan sus barreras independientes.
    """
    global motor_busy

    busy = bool(busy)
    if motor_busy == busy:
        return

    motor_busy = busy

    if next_background_item is not None:
        next_background_item.set_sensitive(not busy)

    # El tray pertenece al hilo Win32; GTK sólo publica el nuevo estado.
    if window_handle:
        user32.PostMessageW(window_handle, WM_TRAY_BUSY, 1 if busy else 0, 0)

def _refresh_busy_state():
    """Relee engine_status.json únicamente después de una notificación Win32."""
    try:
        with open(ENGINE_STATUS_PATH, "r", encoding="utf-8") as status_file:
            status = json.load(status_file)

        if isinstance(status, dict):
            _set_motor_busy(bool(status.get("busy", False)))

    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        # Una lectura transitoria no altera el último estado válido conocido.
        pass

    # La primera consulta Gettext debe esperar a que el engine haya
    # preparado los catálogos. El método de inicialización verifica
    # esa disponibilidad antes de construir los menús.
    if main_menu is None and context_menu is None:
        GLib.idle_add(_initialize_translated_ui)

    return GLib.SOURCE_REMOVE

def _busy_monitor_loop():
    """
    Espera cambios de engine_status.json mediante la primitiva nativa Win32.

    ReadDirectoryChangesW observa técnicamente el directorio, pero cada evento
    incluye el nombre afectado: sólo engine_status.json alcanza al frontend.
    No existe polling ni temporizador.
    """
    watch_dir = os.path.abspath(os.path.dirname(ENGINE_STATUS_PATH))
    os.makedirs(watch_dir, exist_ok=True)

    directory_handle = kernel32.CreateFileW( watch_dir, FILE_LIST_DIRECTORY,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
        None, OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS, None, )

    if not directory_handle or directory_handle == INVALID_HANDLE_VALUE:
        print("[WMM WINDOWS] No se pudo observar engine_status.json", flush=True)
        return

    buffer = ctypes.create_string_buffer(4096)
    bytes_returned = wintypes.DWORD()

    try:
        while True:
            if not kernel32.ReadDirectoryChangesW(directory_handle, buffer,
                    ctypes.sizeof(buffer), False,
                    FILE_NOTIFY_CHANGE_FILE_NAME | FILE_NOTIFY_CHANGE_LAST_WRITE,
                    ctypes.byref(bytes_returned), None, None):
                return

            raw = buffer.raw[:bytes_returned.value]
            offset = 0

            while offset < len(raw):
                next_offset = int.from_bytes(raw[offset:offset + 4], "little")
                name_length = int.from_bytes(raw[offset + 8:offset + 12], "little")

                name_start = offset + 12
                name_end = name_start + name_length

                if name_end > len(raw):
                    break

                filename = raw[name_start:name_end].decode("utf-16-le", errors="ignore")

                if filename.casefold() == "engine_status.json":
                    GLib.idle_add(_refresh_busy_state)
                    break

                if next_offset == 0:
                    break

                offset += next_offset
    finally:
        kernel32.CloseHandle(directory_handle)

def _start_busy_monitor():
    """Sincroniza el estado inicial y observa cambios posteriores del engine."""
    _refresh_busy_state()

    threading.Thread(
        target=_busy_monitor_loop,
        name="wmm-busy-state",
        daemon=True,
    ).start()

def _next_background(_item=None):
    """Solicita una rotación sólo si este frontend todavía la considera admisible."""
    if motor_busy:
        return GLib.SOURCE_REMOVE

    # Cerramos localmente la pequeña carrera entre el gesto y busy=true del engine.
    _set_motor_busy(True)

    if not _send_action({"action": "force_rotation"}):
        _set_motor_busy(False)

    return GLib.SOURCE_REMOVE

def _launch_independent_tool(path):
    """Lanza una herramienta que no depende del estado del engine."""
    if not os.path.isfile(path):
        print(f"[WMM WINDOWS] Herramienta no encontrada: {path}", flush=True)
        return

    try:
        Gio.Subprocess.new([sys.executable, path], Gio.SubprocessFlags.NONE)
    except GLib.Error as error:
        print(f"[WMM WINDOWS] No se pudo lanzar {path}: {error}", flush=True)

def _launch_install_manager():
    """Lanza el gestor Windows sin depender del runtime de WMM."""
    if not os.path.isfile(INSTALL_MANAGER_PATH):
        print(f"[WMM WINDOWS] Gestor no encontrado: {INSTALL_MANAGER_PATH}",
            flush=True)
        return

    # PowerShell debe arrancar fuera del árbol instalado, que
    # podría sustituirse durante Upgrade, Reinstall o Downgrade.
    command = [
        "powershell.exe",
        "-NoProfile",
        "-STA",
        "-ExecutionPolicy", "Bypass",
        "-WindowStyle", "Hidden",
        "-File", INSTALL_MANAGER_PATH,
    ]

    try:
        subprocess.Popen(
            command,
            cwd=tempfile.gettempdir(),
            stdin=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except OSError as error:
        print(f"[WMM WINDOWS] No se pudo abrir Install Manager: {error}",
            flush=True)

# ==========================================================
# FRONTEND: INSTANCIA ÚNICA
# ==========================================================

def _acquire_frontend_instance():
    """
    Reserva la identidad única del frontend dentro de la sesión Windows.

    El mutex pertenece exclusivamente al frontend; no sustituye ni comparte
    responsabilidad con el lock autoritativo que protege la instancia del engine.
    """
    global frontend_mutex

    # CreateMutexW sólo garantiza ERROR_ALREADY_EXISTS cuando el objeto previo
    # existe. Limpiamos explícitamente last-error para no interpretar un valor
    # residual como una segunda instancia.
    ctypes.set_last_error(0)

    handle = kernel32.CreateMutexW(None, False, FRONTEND_MUTEX_NAME)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())

    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        print("[WMM WINDOWS] Frontend ya activo; segundo lanzamiento ignorado", flush=True)
        return False

    frontend_mutex = handle
    return True

# ==========================================================
# ENGINE: LIFECYCLE
# ==========================================================

def _engine_is_running():
    """
    Comprueba la instancia real mediante el lock autoritativo del engine.

    pid_main.pid puede sobrevivir a un cierre anómalo; su mera existencia no
    demuestra que WMM esté activo. El propietario real es quien mantiene el lock.
    """
    pid_path = os.path.join(platform.cache_dir, "pid_main.pid")

    if not os.path.isfile(pid_path):
        return False

    try:
        with open(pid_path, "r+") as pid_file:
            acquired = platform.try_lock_file(pid_file)

            if acquired:
                platform.unlock_file(pid_file)
                return False

            return True

    except OSError as error:
        # Ante un fallo al inspeccionar el lock no lanzamos a ciegas una segunda
        # instancia. main.py sigue siendo la última autoridad de todas formas.
        print(f"[WMM WINDOWS] No se pudo comprobar el estado del engine: {error}",
              flush=True)
        return True

def _engine_translations_ready():
    """
    El engine compila los .mo antes de adquirir el lock de pid_main.pid.
    Sólo un lock mantenido por otro proceso habilita el primer dgettext().

    Un error al consultar el lock no equivale a traducciones preparadas,
    aunque _engine_is_running() lo trate como instancia existente para
    evitar un segundo arranque accidental.
    """
    pid_path = os.path.join(platform.cache_dir, "pid_main.pid")
    if not os.path.isfile(pid_path):
        return False

    try:
        with open(pid_path, "r+") as pid_file:
            if platform.try_lock_file(pid_file):
                platform.unlock_file(pid_file)
                return False
        return True
    except OSError as error:
        print(f"[WMM WINDOWS] No se pudo verificar la preparación del engine: {error}",
              flush=True)
        return False

def _ensure_engine_running():
    """
    Arranca directamente main.py sólo cuando no existe una instancia activa.

    No se espera artificialmente a que termine el bootstrap. Si existe una
    carrera entre dos lanzamientos, el lock interno de main.py sigue decidiendo.
    """
    if _engine_is_running():
        return True

    engine_path = os.path.join(platform.app_dir, "python", "main.py")

    if not os.path.isfile(engine_path):
        print(f"[WMM WINDOWS] Engine no encontrado: {engine_path}", flush=True)
        return False

    try:
        subprocess.Popen(
            [sys.executable, engine_path],
            env=os.environ.copy(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW, )

    except OSError as error:
        print(f"[WMM WINDOWS] No se pudo arrancar el engine: {error}", flush=True)
        return False

    return True

def _initialize_translated_ui():
    """
    Construye y publica el frontend únicamente después de que el engine
    haya preparado los catálogos de traducción.

    La primera llamada a _() ocurre dentro de _build_main_menu().
    Esta frontera evita cargar y cachear un catálogo antiguo o ausente.

    Se ejecuta exclusivamente en el hilo GTK mediante GLib.
    """
    global main_menu, context_menu

    # La interfaz se materializa una sola vez, aunque lleguen
    # varias notificaciones de disponibilidad del engine.
    if main_menu is not None or context_menu is not None:
        return GLib.SOURCE_REMOVE

    # La existencia del proceso o del archivo PID no es suficiente.
    # Sólo el bloqueo activo garantiza que _ensure_translations()
    # ya ha terminado en el engine.
    if not _engine_translations_ready():
        return GLib.SOURCE_REMOVE

    # FRONTERA GETTEXT: ninguna consulta a _() antes de este punto.
    main_menu = _build_main_menu()
    context_menu = _build_context_menu()

    # El icono sólo aparece después de construir ambos menús.
    # Win32 conserva su hilo; GTK permanece en el principal.
    threading.Thread(
        target=_win32_loop,
        name="wmm-win32-tray",
        daemon=True,
    ).start()

    return GLib.SOURCE_REMOVE

# ==========================================================
# GTK: ESTILOS
# ==========================================================

def _load_wmm_css():
    """Carga una sola vez los estilos propios del frontend Windows."""
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
        print(f"[WMM WINDOWS] No se pudo cargar windows-frontend.css: {error}", flush=True)

# ==========================================================
# MENÚ PRINCIPAL: ESTADO
# ==========================================================

def _update_displays_label():
    """Refleja SYNC/ASYNC sin modificar el estado del switch."""
    if displays_label is None or displays_item is None:
        return

    mode = _("SYNC (All)") if displays_item.get_active() else _("ASYNC (One)")
    displays_label.set_text(_("Displays") + ": " + mode)

def _format_next_background_hotkey(shortcut):
    """Presenta la combinación sin traducir los datos guardados."""
    from wmm_platform.windows import _next_background_hotkey_binding

    shortcut = _next_background_hotkey_binding(shortcut)[0]
    if shortcut is None:
        return ""

    modifier_labels = { "Control": "Ctrl", "Alt": "Alt", "Shift": _("Shift"), }
    parts = [modifier_labels[name] for name in shortcut["modifiers"]]
    return " + ".join(parts + [shortcut["key"]])

def _update_next_background_hotkey_label(shortcut):
    """Actualiza únicamente el atajo; el nombre de la acción conserva su sitio."""
    if next_background_hotkey_label is None:
        return

    try:
        text = _format_next_background_hotkey(shortcut)
    except (TypeError, ValueError):
        text = ""

    next_background_hotkey_label.set_markup(
        "<i>" + GLib.markup_escape_text(text) + "</i>")
    next_background_hotkey_label.set_visible(bool(text))

def _apply_menu_settings(data):
    """Sincroniza el estado visible desde settings.json."""
    global menu_syncing_state, slideshow_interval, slideshow_max_interval

    if not isinstance(data, dict):
        return

    config = data.get("global", data)
    if not isinstance(config, dict):
        return

    if any(widget is None for widget in (
            displays_item, spanned_item, metadata_switch,
            slideshow_switch, slideshow_scale, favorites_only_switch)):
        return

    slideshow_max_interval = max(1, int(config.get("slideshow_max_interval", 60) or 60))
    slideshow_interval = int(config.get("slideshow_interval", 15) or 15)
    slideshow_interval = max(1, min(slideshow_interval, slideshow_max_interval))
    enabled = bool(config.get("slideshow_enabled", False))

    # Los set_active()/set_value() disparan señales GTK. Esta barrera evita
    # que una sincronización de estado rebote como una acción del usuario.
    menu_syncing_state = True
    try:
        displays_item.set_active(config.get("slideshow_mode", "async") == "sync")
        spanned_item.set_active(bool(config.get("spanned_enabled", False)))
        metadata_switch.set_active(bool(config.get("exif_metadata_enabled", False)))
        slideshow_switch.set_active(enabled)
        slideshow_scale.set_range(1, slideshow_max_interval)
        slideshow_scale.set_value(slideshow_interval)
        favorites_only_switch.set_active(bool(config.get("slideshow_bookmark", False)))
    finally:
        menu_syncing_state = False

    _update_displays_label()
    slideshow_switch_label.set_text(_("Enabled") if enabled else _("Disabled"))
    slideshow_scale.set_sensitive(enabled)
    slideshow_interval_label.set_text(str(slideshow_interval) + " " + _("minutes"))
    _update_next_background_hotkey_label(config.get("next_background_hotkey"))

def _refresh_menu_state():
    """
    Relee el estado persistente justo antes de abrir el popup.

    Windows no replica aquí las señales D-Bus de los frontends Linux. Tampoco
    recuperamos FileMonitor, descartado previamente para IPC reactivo Win32:
    la apertura del propio popup es la frontera natural de actualización.
    """
    global cached_bookmarks

    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as settings_file:
            _apply_menu_settings(json.load(settings_file))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        pass

    try:
        with open(BOOKMARKS_PATH, "r", encoding="utf-8") as bookmarks_file:
            bookmarks = json.load(bookmarks_file)

        if isinstance(bookmarks, dict):
            cached_bookmarks = bookmarks
            _paint_inline_bookmarks()
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        pass

# ==========================================================
# POPUPS GTK: LIFECYCLE Y GEOMETRÍA
# ==========================================================

def _new_popup_window(css_class):
    """
    Crea una ventana popup normal, no un Gtk.Menu.

    Shell_NotifyIcon origina el gesto fuera de GDK; por eso Windows no usa
    GtkMenuShell. La ventana posee explícitamente foco, cierre y geometría.
    """
    window = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
    window.set_decorated(False)
    window.set_resizable(False)
    window.set_skip_taskbar_hint(True)
    window.set_skip_pager_hint(True)
    window.set_keep_above(True)
    window.set_accept_focus(True)
    window.set_focus_on_map(True)
    window.set_gravity(Gdk.Gravity.NORTH_WEST)
    window.get_style_context().add_class("wmm-popup")
    window.get_style_context().add_class(css_class)
    window.connect("focus-out-event", _on_popup_focus_out)
    window.connect("key-press-event", _on_popup_key_press)
    window.connect("delete-event", _on_popup_delete)

    # Seguir el tamaño asignado por GTK antes de ajustar la posición.
    window.connect("size-allocate", _on_popup_size_allocate)
    return window

def _on_popup_focus_out(window, _event):
    """Un clic fuera transfiere el foco y cierra el popup de forma explícita."""
    window.hide()
    return False

def _on_popup_key_press(window, event):
    """Escape cierra el popup sin ejecutar ninguna acción."""
    if event.keyval == Gdk.KEY_Escape:
        window.hide()
        return True
    return False

def _on_popup_delete(window, _event):
    """Una petición de cierre oculta el popup residente en vez de destruirlo."""
    window.hide()
    return True

def _monitor_rectangles(x, y):
    """Devuelve geometría y workarea del monitor que contiene el icono del tray."""
    display = Gdk.Display.get_default()
    if display is not None and hasattr(display, "get_monitor_at_point"):
        monitor = display.get_monitor_at_point(x, y)
        if monitor is not None:
            return monitor.get_geometry(), monitor.get_workarea()

    # Compatibilidad GTK3: algunos builds exponen aún la API equivalente vía Screen.
    screen = Gdk.Screen.get_default()
    if screen is None:
        return None, None

    monitor_index = screen.get_monitor_at_point(x, y)
    return (screen.get_monitor_geometry(monitor_index),
            screen.get_monitor_workarea(monitor_index))

def _taskbar_edge(geometry, _workarea, x, y):
    """
    Determina el borde de la taskbar desde el gesto real recibido por el tray.

    La workarea permanece reservada para limitar el popup, pero no decide el
    borde: en Windows puede no reflejar inmediatamente la posición de la barra.
    """
    distances = {
        "left": abs(x - geometry.x),
        "top": abs(y - geometry.y),
        "right": abs((geometry.x + geometry.width) - x),
        "bottom": abs((geometry.y + geometry.height) - y),
    }
    return min(distances, key=distances.get)

def _popup_natural_size(window):
    """Obtiene el tamaño natural actual, incluyendo sólo las secciones visibles."""
    window.queue_resize()
    _minimum, natural = window.get_preferred_size()
    return max(1, natural.width), max(1, natural.height)

def _clamp(value, lower, upper):
    return max(lower, min(value, upper))

def _popup_position(edge, anchor_x, anchor_y, width, height, workarea):
    """Sitúa el popup dentro de la workarea y siempre al lado interior de la taskbar."""
    left = workarea.x
    top = workarea.y
    right = workarea.x + workarea.width
    bottom = workarea.y + workarea.height

    if edge in ("top", "bottom"):
        x = _clamp(anchor_x - width // 2, left, max(left, right - width))
        y = top if edge == "top" else max(top, bottom - height)
    else:
        x = left if edge == "left" else max(left, right - width)
        y = _clamp(anchor_y - height // 2, top, max(top, bottom - height))

    return x, y

def _main_popup_full_height():
    """
    Mide la altura potencial del menú principal con ambas secciones desplegadas.

    El popup todavía está oculto, por lo que podemos materializar temporalmente
    sus filas inline sin producir ningún cambio visible.
    """
    widgets = (
        favorites_switch_item,
        favorites_add_item,
        favorites_scroll_item,
        slideshow_switch_item,
        slideshow_interval_item,
    )
    states = [(widget, widget.get_visible())
              for widget in widgets if widget is not None]

    try:
        for widget, _visible in states:
            widget.show()

        main_menu.queue_resize()
        _minimum, natural = main_menu.get_preferred_size()
        return max(1, natural.height)

    finally:
        for widget, visible in states:
            widget.set_visible(visible)

def _place_popup_window(window, x, y):
    """
    Coloca el popup y memoriza su ancla para los redimensionados inline.

    A diferencia del antiguo Gtk.Menu, Windows conoce la workarea del monitor;
    conservar su borde interior hace que el popup crezca siempre alejándose de
    la taskbar, sea horizontal o vertical.
    """
    geometry, workarea = _monitor_rectangles(x, y)
    if geometry is None or workarea is None:
        window.move(x, y)
        return

    width, height = _popup_natural_size(window)
    edge = _taskbar_edge(geometry, workarea, x, y)
    popup_x, popup_y = _popup_position(edge, x, y, width, height, workarea)

    # En barras laterales la dirección vertical se decide contra la altura
    # totalmente desplegada y se mantiene durante toda esta apertura.
    window.wmm_grow_up = False

    if window is main_menu and edge in ("left", "right"):
        full_height = _main_popup_full_height()

        top = workarea.y
        bottom = workarea.y + workarea.height

        available_down = bottom - popup_y
        available_up = (popup_y + height) - top

        window.wmm_grow_up = (full_height > available_down
            and available_up > available_down)

    window.wmm_anchor_x = x
    window.wmm_anchor_y = y
    window.wmm_anchor_edge = edge

    # Cada apertura parte de una nueva geometría real, sin heredar el ancla inline.
    window.wmm_resize_anchor = None
    window.wmm_resize_size = None

    window.resize(width, height)
    window.move(popup_x, popup_y)

    # La ventana es residente: confirmar también su posición nativa mientras
    # sigue oculta evita heredar el desplazamiento de la apertura anterior.
    native_window = window.get_window()
    if native_window is not None:
        native_window.move(popup_x, popup_y)

def _resize_popup_window(window):
    """
    Solicita a GTK el tamaño natural del contenido visible.

    El borde real se memoriza una vez por apertura; size-allocate ajustará
    la posición después de que GTK haya asignado el nuevo tamaño.
    """
    if (window is None or not window.get_mapped()
            or not hasattr(window, "wmm_anchor_edge")):
        return

    native_window = window.get_window()
    if native_window is None:
        return

    # Conservar una referencia estable incluso si llegan varios clics antes
    # de que GTK complete el redimensionado pendiente.
    if getattr(window, "wmm_resize_anchor", None) is None:
        _, x, y = native_window.get_origin()
        geometry = native_window.get_geometry()
        window.wmm_resize_anchor = (
            x, y, x + geometry.width, y + geometry.height)
        window.wmm_resize_size = None

    _, natural = window.get_preferred_size()
    window.resize(max(1, natural.width), max(1, natural.height))

def _on_popup_size_allocate(window, allocation):
    """Conserva los bordes de anclaje siguiendo el tamaño asignado por GTK."""
    anchor = getattr(window, "wmm_resize_anchor", None)
    if anchor is None or not window.get_mapped():
        return

    size = (allocation.width, allocation.height)
    if size == getattr(window, "wmm_resize_size", None):
        return
    window.wmm_resize_size = size

    x, y, right, bottom = anchor
    edge = window.wmm_anchor_edge
    grow_up = getattr(window, "wmm_grow_up", False)
    if edge == "bottom" or (edge in ("left", "right") and grow_up):
        y = bottom - allocation.height
    if edge == "right":
        x = right - allocation.width
    window.move(x, y)

    # Diagnóstico temporal: una línea por tamaño asignado, sin trazar dibujos.
    native_window = window.get_window()
    _, actual_x, actual_y = native_window.get_origin()
    actual = native_window.get_geometry()
    print(f"[WMM RESIZE] edge={edge} up={grow_up} gtk={size} "
          f"actual={(actual_x, actual_y, actual.width, actual.height)}", flush=True)

def _show_popup_window(window, x, y):
    """
    Muestra el popup usando como ancla la posición root conocida por GDK.

    El gesto llega desde Win32, pero Gtk.Window se posiciona en el espacio de
    coordenadas de GDK; por eso GDK es la autoridad final sobre el punto.
    """
    display = Gdk.Display.get_default()
    if display is not None:
        seat = display.get_default_seat()
        pointer = seat.get_pointer() if seat is not None else None

        if pointer is not None:
            _screen, x, y = pointer.get_position()

    _place_popup_window(window, x, y)
    window.show()
    window.present()

def _popup_button(label, icon_name=None, css_classes=()):
    """Crea una fila plana reutilizable dentro de los popups Windows."""
    button = Gtk.Button()
    button.set_relief(Gtk.ReliefStyle.NONE)
    button.set_can_focus(False)
    button.set_focus_on_click(False)
    button.set_hexpand(True)

    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    if icon_name:
        box.pack_start(Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.MENU), False, False, 0)

    label_widget = Gtk.Label(label=label, xalign=0)
    box.pack_start(label_widget, True, True, 0)
    button.add(box)

    style = button.get_style_context()
    style.add_class("wmm-popup-row")
    for css_class in css_classes:
        style.add_class(css_class)
    return button

def _set_main_row_margins(widget, horizontal=MAIN_POPUP_ROW_MARGIN_X,
                          vertical=MAIN_POPUP_ROW_MARGIN_Y):
    """Da aire uniforme a las filas del popup principal sin depender del tema."""
    widget.set_margin_start(horizontal)
    widget.set_margin_end(horizontal)
    widget.set_margin_top(vertical)
    widget.set_margin_bottom(vertical)

def _popup_check_button(label, css_classes=()):
    """Crea una fila checkable que conserva la semántica de los antiguos CheckMenuItem."""
    button = Gtk.CheckButton(label=label)
    button.set_can_focus(False)
    button.set_focus_on_click(False)
    button.set_hexpand(True)
    _set_main_row_margins(button)

    child = button.get_child()
    if isinstance(child, Gtk.Label):
        child.set_xalign(0)

    style = button.get_style_context()
    style.add_class("wmm-popup-row")
    for css_class in css_classes:
        style.add_class(css_class)
    return button

def _popup_switch_row(label, switch):
    """Crea una fila label + Gtk.Switch sin interponer un GtkMenuShell."""
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    row.set_hexpand(True)
    _set_main_row_margins(row)
    row.get_style_context().add_class("wmm-popup-row")
    label_widget = label if isinstance(label, Gtk.Label) else Gtk.Label(label=label, xalign=0)
    row.pack_start(label_widget, True, True, 0)
    row.pack_end(switch, False, False, 0)
    return row

# ==========================================================
# DISPLAYS / SPANNED
# ==========================================================

def _on_displays_toggled(item, _pspec):
    """Alterna ASYNC/SYNC sin modificar los demás ajustes."""
    if menu_syncing_state:
        return

    _update_displays_label()
    _send_action({
        "action": "update_timer_settings",
        "mode": "sync" if item.get_active() else "async",
    })

def _on_spanned_toggled(item, _pspec):
    """Propaga únicamente el estado de Spanned al engine."""
    if menu_syncing_state:
        return

    _send_action({
        "action": "update_timer_settings",
        "spanned_enabled": item.get_active(),
    })

def _on_metadata_toggled(switch, _pspec):
    """Actualiza metadatos y solicita su aplicación sin cerrar el popup."""
    if menu_syncing_state:
        return

    _send_action({
        "action": "set_metadata_enabled",
        "enabled": switch.get_active(),
    })

# ==========================================================
# SLIDESHOW
# ==========================================================

def _sync_slideshow_ui(enabled):
    """Refleja Slideshow sin generar un comando recursivo."""
    global menu_syncing_state

    if slideshow_switch is None:
        return

    syncing = menu_syncing_state
    menu_syncing_state = True
    slideshow_switch.set_active(enabled)
    menu_syncing_state = syncing

    slideshow_switch_label.set_text(_("Enabled") if enabled else _("Disabled"))
    slideshow_scale.set_sensitive(enabled)

def _on_slideshow_switch_changed(switch, _pspec):
    """Propaga únicamente el estado ON/OFF de Slideshow."""
    if menu_syncing_state:
        return

    _sync_slideshow_ui(switch.get_active())
    _send_action({
        "action": "update_timer_settings",
        "enabled": switch.get_active(),
    })

def _on_slideshow_scale_changed(scale):
    """Actualiza en vivo el intervalo mostrado."""
    global slideshow_interval

    slideshow_interval = int(round(scale.get_value()))
    slideshow_interval_label.set_text(str(slideshow_interval) + " " + _("minutes"))

def _on_slideshow_scale_released(_scale, event):
    """Confirma el intervalo al terminar la interacción real con el slider."""
    if event.button == 1 and not menu_syncing_state:
        _send_action({
            "action": "update_timer_settings",
            "interval": slideshow_interval,
        })
    return False

def _cancel_slideshow_scale_commit():
    """Cancela una confirmación diferida pendiente."""
    global slideshow_scale_commit_id

    if slideshow_scale_commit_id is not None:
        GLib.source_remove(slideshow_scale_commit_id)
        slideshow_scale_commit_id = None

def _commit_slideshow_scale():
    """Comunica una sola vez el intervalo definitivo al engine."""
    global slideshow_scale_commit_id, slideshow_scale_dirty

    slideshow_scale_commit_id = None
    if slideshow_scale_dirty and not menu_syncing_state:
        slideshow_scale_dirty = False
        _send_action({
            "action": "update_timer_settings",
            "interval": slideshow_interval,
        })
    return False

def _on_slideshow_scale_pressed(_scale, event):
    """El arrastre conserva la confirmación inmediata al soltar."""
    global slideshow_scale_dragging

    if event.button == 1 and not menu_syncing_state:
        slideshow_scale_dragging = True
        _cancel_slideshow_scale_commit()
    return False

def _on_slideshow_scale_changed(scale):
    """Actualiza el valor y agrupa los cambios de teclado y rueda."""
    global slideshow_interval, slideshow_scale_dirty, slideshow_scale_commit_id

    slideshow_interval = int(round(scale.get_value()))
    slideshow_interval_label.set_text(str(slideshow_interval) + " " + _("minutes"))

    if menu_syncing_state:
        return

    slideshow_scale_dirty = True
    if slideshow_scale_dragging:
        return

    _cancel_slideshow_scale_commit()
    slideshow_scale_commit_id = GLib.timeout_add(800, _commit_slideshow_scale)

def _on_slideshow_scale_released(_scale, event):
    """Confirma inmediatamente el valor definitivo al soltar el ratón."""
    global slideshow_scale_dragging

    if event.button == 1:
        slideshow_scale_dragging = False
        _cancel_slideshow_scale_commit()
        _commit_slideshow_scale()
    return False

# ==========================================================
# FAVORITOS
# ==========================================================

def _on_favorites_only_switch_changed(switch, _pspec):
    """Actualiza Favorites Only y activa Slideshow si resulta necesario."""
    if menu_syncing_state:
        return

    enabled = switch.get_active()
    command = {
        "action": "update_timer_settings",
        "slideshow_bookmark": enabled,
    }

    # Favorites Only sólo tiene sentido con Slideshow activo.
    if enabled and not slideshow_switch.get_active():
        _sync_slideshow_ui(True)
        command["enabled"] = True

    _send_action(command)

def _on_favorite_name_clicked(_button, name):
    """Carga un favorito sin cerrar el popup para permitir cambios consecutivos."""
    _load_favorite(name)

def _on_favorite_delete_clicked(_button, name):
    """Cierra el popup y abre la confirmación en su misma zona de pantalla."""
    anchor = None
    native_window = main_menu.get_window() if main_menu is not None else None

    if native_window is not None:
        _, x, y = native_window.get_origin()
        geometry = native_window.get_geometry()
        anchor = (x + geometry.width // 2, y + geometry.height // 2)

    if main_menu is not None:
        main_menu.hide()

    _confirm_delete_favorite(name, anchor)

def _paint_inline_bookmarks():
    """Reconstruye la lista inline desde cached_bookmarks."""
    if favorites_inline_list is None:
        return

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
            row.get_style_context().add_class("wmm-favorite-row")

            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
            row_box.get_style_context().add_class("wmm-favorite-row-box")

            name_button = Gtk.Button()
            name_button.set_relief(Gtk.ReliefStyle.NONE)
            name_button.set_can_focus(False)
            name_button.set_focus_on_click(False)
            name_button.set_hexpand(True)
            name_button.get_style_context().add_class("wmm-favorite-button")
            name_button.connect("clicked", _on_favorite_name_clicked, name)

            name_label = Gtk.Label(label=name, xalign=0)
            name_label.set_ellipsize(3)
            name_button.add(name_label)

            delete_button = Gtk.Button()
            delete_button.set_relief(Gtk.ReliefStyle.NONE)
            delete_button.set_can_focus(False)
            delete_button.set_focus_on_click(False)
            delete_button.get_style_context().add_class("wmm-favorite-button")
            delete_button.connect("clicked", _on_favorite_delete_clicked, name)
            delete_button.add(Gtk.Image.new_from_icon_name(
                "user-trash-symbolic", Gtk.IconSize.MENU))

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

    target_height = sum(row.get_preferred_height()[1]
                        for row in rows[:FAVORITES_VISIBLE_ROWS])
    style = favorites_inline_list.get_style_context()
    state = style.get_state()
    padding = style.get_padding(state)
    border = style.get_border(state)
    target_height += padding.top + padding.bottom + border.top + border.bottom
    target_height = max(1, target_height)

    # Liberar primero el máximo evita min > max al cambiar entre listas.
    favorites_scrolled.set_max_content_height(-1)
    favorites_scrolled.set_min_content_height(target_height)
    favorites_scrolled.set_max_content_height(target_height)
    favorites_scrolled.queue_resize()
    favorites_scroll_item.queue_resize()

def _load_favorite(name):
    """Carga un favorito y refleja Slideshow forzado a OFF."""
    _sync_slideshow_ui(False)
    _send_action({
        "action": "load_bookmark",
        "name": name,
        "timer_force_off": True,
    })

def _confirm_delete_favorite(name, anchor=None):
    """Solicita confirmación donde estaba el popup que originó la acción."""
    dialog = Gtk.MessageDialog(
        transient_for=None,
        modal=True,
        message_type=Gtk.MessageType.QUESTION,
        buttons=Gtk.ButtonsType.YES_NO,
        text=_("Delete") + ' "' + name + '"?', )

    dialog.set_title(_("Delete favorite"))
    dialog.set_keep_above(True)

    if anchor is not None:
        dialog.realize()
        minimum, natural = dialog.get_preferred_size()
        monitor, workarea = _monitor_rectangles(*anchor)

        if workarea is not None:
            width = max(1, natural.width)
            height = max(1, natural.height)

            x = _clamp( anchor[0] - width // 2, workarea.x,
                max(workarea.x, workarea.x + workarea.width - width), )
            y = _clamp( anchor[1] - height // 2, workarea.y,
                max(workarea.y, workarea.y + workarea.height - height), )

            dialog.move(x, y)

    dialog.show_all()
    dialog.present()
    response = dialog.run()
    dialog.destroy()

    if response == Gtk.ResponseType.YES:
        _send_action({ "action": "delete_bookmark", "name": name, })

# ==========================================================
# CONSTRUCCIÓN DEL POPUP PRINCIPAL
# ==========================================================

def _on_favorites_header_clicked(button):
    """Actualiza Favorites y deja a GTK gestionar su tamaño y repintado."""
    global favorites_expanded

    favorites_expanded = button.get_active()
    if favorites_expanded:
        _update_favorites_scroll_height()

    favorites_switch_item.set_visible(favorites_expanded)
    favorites_add_item.set_visible(favorites_expanded)
    favorites_scroll_item.set_visible(favorites_expanded)
    _resize_popup_window(main_menu)

def _on_slideshow_header_clicked(button):
    """Actualiza Slideshow y deja a GTK gestionar su tamaño y repintado."""
    global slideshow_expanded

    slideshow_expanded = button.get_active()
    slideshow_switch_item.set_visible(slideshow_expanded)
    slideshow_interval_item.set_visible(slideshow_expanded)
    _resize_popup_window(main_menu)

def _on_add_favorite_clicked(button):
    button.set_active(False)

    # Conservar el centro real del menú antes de ocultarlo.
    command = {"action": "add_bookmark"}
    native_window = main_menu.get_window() if main_menu is not None else None

    if native_window is not None:
        _, x, y = native_window.get_origin()
        geometry = native_window.get_geometry()
        command["x"] = x + geometry.width // 2
        command["y"] = y + geometry.height // 2

    if main_menu is not None:
        main_menu.hide()

    _send_action(command)

def _on_next_background_clicked(button):
    """Mantiene el popup abierto y reutiliza la barrera local de rotación."""
    button.set_active(False)
    _next_background()

def _on_next_background_button_press(button, event):
    """El clic secundario configura el atajo sin solicitar una rotación."""
    if event.button != 3:
        return False

    # Conservar el centro real del menú antes de ocultarlo.
    path = os.path.join(platform.app_dir, "python", "keybinding_manager.py")
    command = [sys.executable, path]
    native_window = main_menu.get_window() if main_menu is not None else None

    if native_window is not None:
        _, x, y = native_window.get_origin()
        geometry = native_window.get_geometry()
        command.extend([
            str(x + geometry.width // 2),
            str(y + geometry.height // 2)])

    if main_menu is not None:
        main_menu.hide()

    from wmm_platform.win32 import allow_foreground_window

    try:
        process = subprocess.Popen(command,
            creationflags=subprocess.CREATE_NO_WINDOW)
        # El gesto del usuario autoriza al nuevo formulario a pedir primer plano.
        allow_foreground_window(process.pid)
        threading.Thread(target=process.wait,
            name="WMM-KeybindingForm", daemon=True).start()
    except OSError as error:
        print(f"[WMM WINDOWS] No se pudo abrir el formulario de atajo: {error}", flush=True)
    return True

def _reset_main_popup_state(_widget=None):
    """Restablece las secciones inline sin redimensionar el popup al ocultarlo."""
    global favorites_expanded, slideshow_expanded, slideshow_scale_dragging

    # El cierre finaliza cualquier ajuste pendiente antes de releer settings.
    _cancel_slideshow_scale_commit()
    slideshow_scale_dragging = False
    _commit_slideshow_scale()

    favorites_expanded = False
    slideshow_expanded = False

    for widget in (
            favorites_switch_item,
            favorites_add_item,
            favorites_scroll_item,
            slideshow_switch_item,
            slideshow_interval_item):
        if widget is not None:
            widget.hide()

    # set_active() también emite clicked: el reset no debe entrar en los
    # manejadores que redimensionan la ventana al desplegar o plegar secciones.
    for header, callback in (
            (favorites_header_item, _on_favorites_header_clicked),
            (slideshow_header_item, _on_slideshow_header_clicked)):
        if header is not None:
            header.handler_block_by_func(callback)
            try:
                header.set_active(False)
            finally:
                header.handler_unblock_by_func(callback)

    # La siguiente apertura calcula tamaño y posición en _place_popup_window().
    # Aquí sólo se restablece el contenido; no se modifica la geometría nativa.

def _build_main_menu():
    """
    Construye el popup principal como Gtk.Window controlada por WMM.

    Los widgets hijos recuperan sus eventos nativos; desaparecen el hit-testing,
    PRELIGHT y drag manual que sólo eran necesarios bajo GtkMenuShell.
    """
    global favorites_header_item, favorites_switch_item, favorites_add_item
    global favorites_only_switch, favorites_scroll_item, favorites_scrolled
    global favorites_inline_list, displays_item, displays_label, spanned_item, next_background_item
    global next_background_hotkey_label
    global metadata_switch
    global slideshow_header_item, slideshow_switch_item, slideshow_switch
    global slideshow_switch_label, slideshow_interval_item
    global slideshow_interval_label, slideshow_scale

    window = _new_popup_window("wmm-main-popup")
    window.set_size_request(MAIN_POPUP_MIN_WIDTH, -1)
    window.connect("hide", _reset_main_popup_state)

    content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
    content.set_border_width(MAIN_POPUP_BORDER)
    window.add(content)

    # Favorites.
    favorites_header_item = _popup_check_button(
        _("Favorites"), ("wmm-menu-icon", "wmm-inline-header"))
    favorites_header_item.connect("clicked", _on_favorites_header_clicked)
    content.pack_start(favorites_header_item, False, False, 0)

    favorites_only_switch = Gtk.Switch()
    favorites_only_switch.connect(
        "notify::active", _on_favorites_only_switch_changed)
    favorites_switch_item = _popup_switch_row(_("Favorites Only"), favorites_only_switch)

    favorites_add_item = _popup_check_button(
        _("Add Preset Favorite"), ("wmm-menu-icon", "wmm-add-favorite"))
    favorites_add_item.connect("clicked", _on_add_favorite_clicked)

    favorites_scrolled = Gtk.ScrolledWindow()
    _set_main_row_margins(favorites_scrolled, horizontal=MAIN_POPUP_ROW_MARGIN_X, vertical=2)
    favorites_scrolled.set_overlay_scrolling(True)
    favorites_scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    favorites_scrolled.set_propagate_natural_height(True)
    favorites_scrolled.get_vscrollbar().get_style_context().add_class("wmm-hidden-scrollbar")

    favorites_inline_list = Gtk.ListBox()
    favorites_inline_list.set_selection_mode(Gtk.SelectionMode.NONE)
    favorites_scrolled.add(favorites_inline_list)
    favorites_scroll_item = favorites_scrolled

    for widget in (favorites_switch_item, favorites_add_item, favorites_scroll_item):
        content.pack_start(widget, False, False, 0)
        widget.show_all()
        widget.set_no_show_all(True)
        widget.hide()

    # Slideshow.
    slideshow_header_item = _popup_check_button(
        _("Slideshow"), ("wmm-menu-icon", "wmm-inline-header"))
    slideshow_header_item.connect("clicked", _on_slideshow_header_clicked)
    content.pack_start(slideshow_header_item, False, False, 0)

    slideshow_switch = Gtk.Switch()
    slideshow_switch.connect("notify::active", _on_slideshow_switch_changed)
    slideshow_switch_label = Gtk.Label(label=_("Disabled"), xalign=0)
    slideshow_switch_item = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    _set_main_row_margins(slideshow_switch_item)
    slideshow_switch_item.get_style_context().add_class("wmm-popup-row")
    slideshow_switch_item.pack_start(slideshow_switch_label, True, True, 0)
    slideshow_switch_item.pack_end(slideshow_switch, False, False, 0)
    content.pack_start(slideshow_switch_item, False, False, 0)
    slideshow_switch_item.show_all()
    slideshow_switch_item.set_no_show_all(True)
    slideshow_switch_item.hide()

    slideshow_interval_label = Gtk.Label(
        label=str(slideshow_interval) + " " + _("minutes"))
    slideshow_interval_label.set_halign(Gtk.Align.CENTER)

    slideshow_scale = Gtk.Scale.new_with_range(
        Gtk.Orientation.HORIZONTAL, 1, slideshow_max_interval, 1)
    slideshow_scale.set_draw_value(False)
    slideshow_scale.set_value(slideshow_interval)
    slideshow_scale.set_hexpand(True)
    slideshow_scale.set_sensitive(False)
    slideshow_scale.connect("value-changed", _on_slideshow_scale_changed)
    slideshow_scale.connect("button-press-event", _on_slideshow_scale_pressed)
    slideshow_scale.connect("button-release-event", _on_slideshow_scale_released)

    slideshow_interval_item = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    _set_main_row_margins(slideshow_interval_item, vertical=4)
    slideshow_interval_item.get_style_context().add_class("wmm-popup-row")
    slideshow_interval_item.pack_start(slideshow_interval_label, False, False, 0)
    slideshow_interval_item.pack_start(slideshow_scale, False, False, 0)

    content.pack_start(slideshow_interval_item, False, False, 0)

    slideshow_interval_item.show_all()
    slideshow_interval_item.set_no_show_all(True)
    slideshow_interval_item.hide()

    mode_separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
    mode_separator.set_margin_top(4)
    mode_separator.set_margin_bottom(4)

    content.pack_start(mode_separator, False, False, 0)

    # Displays conserva su etiqueta dinámica; el switch representa el estado.
    displays_label = Gtk.Label(xalign=0)
    displays_item = Gtk.Switch()
    displays_item.connect("notify::active", _on_displays_toggled)
    content.pack_start(_popup_switch_row(displays_label, displays_item), False, False, 0)

    spanned_item = Gtk.Switch()
    spanned_item.connect("notify::active", _on_spanned_toggled)
    content.pack_start(_popup_switch_row(_("Spanned Mode"), spanned_item), False, False, 0)

    metadata_switch = Gtk.Switch()
    metadata_switch.connect("notify::active", _on_metadata_toggled)
    content.pack_start(_popup_switch_row(_("Image Metadata"), metadata_switch), False, False, 0)

    main_separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
    main_separator.set_margin_top(4)
    main_separator.set_margin_bottom(4)

    content.pack_start( main_separator, False, False, 0, )

    next_background_item = _popup_check_button(
        _("Next Background"), ("wmm-menu-icon", "wmm-next-background"))

    # Dos etiquetas evitan que la longitud de la traducción desplace el atajo.
    action_label = next_background_item.get_child()
    next_background_item.remove(action_label)

    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    row.pack_start(action_label, True, True, 0)

    next_background_hotkey_label = Gtk.Label(xalign=1)
    next_background_hotkey_label.set_no_show_all(True)
    row.pack_end(next_background_hotkey_label, False, False, 0)
    next_background_item.add(row)
    next_background_item.connect("clicked", _on_next_background_clicked)
    next_background_item.set_tooltip_text(_("Secondary click: assign a keyboard shortcut"))
    next_background_item.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
    next_background_item.connect("button-press-event", _on_next_background_button_press)

    content.pack_start(next_background_item, False, False, 0)

    content.show_all()
    _reset_main_popup_state()
    _paint_inline_bookmarks()
    return window

# ==========================================================
# INICIO AUTOMÁTICO - MENÚ CONTEXTUAL
# ==========================================================

def _refresh_context_autostart():
    """Refleja HKCU al abrir el menú, sin mantener estado duplicado."""
    if context_autostart_item is None:
        return

    # Actualizar programáticamente la casilla no debe modificar el Registro.
    context_autostart_item.handler_block_by_func(_on_autostart_toggled)
    try:
        context_autostart_item.set_active(
            win32_platform.get_autostart_enabled(platform.app_dir))
    finally:
        context_autostart_item.handler_unblock_by_func(_on_autostart_toggled)

def _on_autostart_toggled(button):
    """Aplica la preferencia al HKCU del usuario que ejecuta WMM."""
    if not win32_platform.set_autostart_enabled(platform.app_dir, button.get_active()):
        # Si falla la escritura, recuperar el estado real del Registro.
        _refresh_context_autostart()
        return

    if context_menu is not None:
        context_menu.hide()

# ==========================================================
# MENÚ CONTEXTUAL
# ==========================================================

def _activate_context_action(_button, callback):
    """Cierra el popup contextual antes de ejecutar su acción."""
    if context_menu is not None:
        context_menu.hide()
    callback()

def _context_menu_item(label, icon_name, callback):
    """Crea una entrada contextual GTK con icono y etiqueta."""
    item = _popup_button(label, icon_name)
    item.connect("clicked", _activate_context_action, callback)
    return item

def _refresh_context_autostart():
    """Refleja el estado real de HKCU sin provocar escrituras."""
    if context_autostart_item is None:
        return

    enabled = win32_platform.get_autostart_enabled()

    # set_active emite toggled: bloquear el callback durante
    # una actualización programática evita modificar HKCU.
    context_autostart_item.handler_block(context_autostart_handler)
    try:
        context_autostart_item.set_active(enabled)
    finally:
        context_autostart_item.handler_unblock(context_autostart_handler)

def _on_context_autostart_toggled(button):
    """Modifica el inicio automático para la cuenta Windows actual."""
    enabled = button.get_active()

    if not win32_platform.set_autostart_enabled(platform.app_dir, enabled):
        _refresh_context_autostart()
        return

    if context_menu is not None:
        context_menu.hide()

def _build_context_menu():
    """Construye el popup contextual como ventana GTK controlada por WMM."""
    global context_autostart_item, context_autostart_handler

    window = _new_popup_window("wmm-context-popup")
    content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    window.add(content)

    content.pack_start(_context_menu_item(_("Settings"), "preferences-system",
        lambda: _send_action({"action": "open_panel"})), False, False, 0)
    content.pack_start(_context_menu_item(_("Sync Library"), "emblem-synchronizing",
        lambda: _send_action({"action": "sync_library"})), False, False, 0)

    # El gestor PowerShell pertenece exclusivamente a Open Code.
    # La distribución compilada delega su mantenimiento en Inno Setup.
    if not getattr(sys, "frozen", False):
        content.pack_start(_context_menu_item(_("Install Manager"), "system-software-install",
            _launch_install_manager), False, False, 0)

    content.pack_start(_context_menu_item( _("Debug Log Viewer"), "edit-find",
        lambda: _launch_independent_tool(DEBUG_LOG_VIEWER_PATH)), False, False, 0)
    content.pack_start(_context_menu_item(_("Help"), "help-faq",
        lambda: _send_action({"action": "open_help"})), False, False, 0)

    # Inicio automático: preferencia exclusiva del usuario Windows.
    content.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0)

    context_autostart_item = _popup_check_button(_("Start WMM with Windows"))
    context_autostart_handler = context_autostart_item.connect(
        "toggled", _on_context_autostart_toggled)
    content.pack_start(context_autostart_item, False, False, 0)

    content.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0)

    content.pack_start(_context_menu_item(_("About") + " WMM Manager", "user-info",
        lambda: _send_action({"action": "open_about"})), False, False, 0)
    content.pack_start(_context_menu_item(_("Exit") + " WMM", "application-exit",
        _shutdown_and_quit), False, False, 0)

    content.show_all()
    return window

# ==========================================================
# POPUP DESDE EL TRAY
# ==========================================================

def _show_main_menu(x, y):
    """Sincroniza estado y muestra el popup principal junto a la taskbar."""
    if context_menu is not None and context_menu.get_visible():
        context_menu.hide()
    if main_menu.get_visible():
        main_menu.hide()

    _reset_main_popup_state()
    _refresh_menu_state()
    _show_popup_window(main_menu, x, y)
    return GLib.SOURCE_REMOVE

def _show_context_menu(x, y):
    """Muestra el popup secundario junto a la taskbar."""
    if main_menu is not None and main_menu.get_visible():
        main_menu.hide()
    if context_menu.get_visible():
        context_menu.hide()

    _refresh_context_autostart()
    _show_popup_window(context_menu, x, y)
    return GLib.SOURCE_REMOVE

def _shutdown_and_quit(*_args):
    """Unifica las solicitudes de cierre del frontend y del engine."""
    global shutdown_requested

    # El menú y WM_CLOSE pueden solicitar el cierre simultáneamente.
    # Sólo la primera solicitud debe enviar shutdown al engine.
    if shutdown_requested:
        return GLib.SOURCE_REMOVE

    shutdown_requested = True

    if _engine_is_running():
        _send_action({"action": "shutdown"})

    _request_quit()
    return GLib.SOURCE_REMOVE

# ==========================================================
# WIN32: ICONO
# ==========================================================

def _add_tray_icon():
    """
    Publica el icono y restablece NOTIFYICON_VERSION_4.

    Explorer pierde la versión asociada al icono cuando reconstruye la barra;
    por eso NIM_SETVERSION acompaña deliberadamente a cada NIM_ADD.
    """
    if not shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(tray_data)):
        print("[WMM WINDOWS] No se pudo publicar el icono", flush=True)
        return False

    tray_data.uVersion = NOTIFYICON_VERSION_4
    if not shell32.Shell_NotifyIconW(NIM_SETVERSION, ctypes.byref(tray_data)):
        print("[WMM WINDOWS] No se pudo establecer NOTIFYICON_VERSION_4", flush=True)
        return False

    return True

def _prepare_notification_identity():
    """Identifica el proceso que publica todos los avisos nativos de WMM."""
    import winreg
    from debug_logger import log_event

    # AppUserModelID pertenece al proceso: establecerlo antes de crear UI.
    result = shell32.SetCurrentProcessExplicitAppUserModelID(NOTIFICATION_APP_ID)
    if result != 0:
        log_event(f"No se pudo establecer la identidad de notificaciones: HRESULT=0x{result & 0xFFFFFFFF:08X}",
            origin="WINDOWS", level="WARN", reason="NOTIFY")
        return False

    try:
        # Comprobar el ICO con el mismo cargador del tray; existencia no basta.
        icon = user32.LoadImageW(
            None, ICON_PATH, IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE)
        if icon:
            user32.DestroyIcon(icon)
        else:
            log_event("Icono WMM no disponible para la cabecera; usando el predeterminado de Windows",
                origin="WINDOWS", level="WARN", reason="NOTIFY")

        path = rf"Software\Classes\AppUserModelId\{NOTIFICATION_APP_ID}"
        values = {"DisplayName": "WMM Manager", "IconUri": ICON_PATH if icon else None}
        changed = False
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0,
                winreg.KEY_READ | winreg.KEY_WRITE) as key:
            for name, value in values.items():
                try:
                    current, value_type = winreg.QueryValueEx(key, name)
                except FileNotFoundError:
                    current, value_type = None, None
                if value is None:
                    # Retirar una ruta obsoleta permite el fallback del shell.
                    if value_type is not None:
                        winreg.DeleteValue(key, name)
                        changed = True
                elif current != value or value_type != winreg.REG_EXPAND_SZ:
                    winreg.SetValueEx(key, name, 0, winreg.REG_EXPAND_SZ, value)
                    changed = True

        # Los metadatos sobreviven al cierre; se retiran al desinstalar WMM.
        log_event(f"Identidad de notificaciones preparada: {NOTIFICATION_APP_ID}; actualizada={changed}",
            origin="WINDOWS", level="INFO" if changed else "DEBUG", reason="NOTIFY")
        return True
    except OSError as error:
        # Un fallo de registro no debe impedir arrancar el frontend.
        log_event(f"No se pudieron registrar los metadatos de notificaciones: {error}",
            origin="WINDOWS", level="WARN", reason="NOTIFY")
        return False

def _receive_tray_notification(lparam):
    """Consume WM_COPYDATA en el hilo Win32 y solicita el aviso del tray."""
    import html
    import re
    from debug_logger import log_event

    class COPYDATASTRUCT(ctypes.Structure):
        _fields_ = [("dwData", ctypes.c_size_t), ("cbData", wintypes.DWORD),
                    ("lpData", ctypes.c_void_p)]

    try:
        if not lparam:
            return 0
        incoming = ctypes.cast(lparam, ctypes.POINTER(COPYDATASTRUCT)).contents
        # WMMN identifica este protocolo; otros WM_COPYDATA no son informes.
        if incoming.dwData != 0x574D4D4E:
            return 0
        if not incoming.lpData or not 0 < incoming.cbData <= 65536:
            raise ValueError("Tamano de informe invalido")

        # No retenemos el puntero: Windows solo garantiza su vida en el callback.
        raw = ctypes.string_at(incoming.lpData, incoming.cbData)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("El informe debe ser un objeto JSON")
        title, message = payload.get("title"), payload.get("message")
        level = payload.get("level", "info")
        if not all(isinstance(value, str) for value in (title, message, level)):
            raise ValueError("Campos del informe invalidos")

        # ConfigHandler entrega b/i de Pango. La adaptacion queda en Windows;
        # el resto de plataformas conserva los mensajes y su formato actuales.
        title = html.unescape(re.sub(r"</?(?:b|i)>", "", title))
        message = html.unescape(re.sub(r"</?(?:b|i)>", "", message))
        if not title or not message or "\0" in title or "\0" in message:
            raise ValueError("El informe esta vacio o contiene un terminador nulo")
        title_units = len(title.encode("utf-16-le")) // 2
        message_units = len(message.encode("utf-16-le")) // 2
        if title_units > 63 or message_units > 255:
            raise ValueError(
                f"Limite de Shell_NotifyIconW: titulo={title_units}/63, "
                f"cuerpo={message_units}/255; informe no recortado")

        icon_flags = {
            "info": 1, "dialog-information": 1, "dialog-information-symbolic": 1,
            "warn": 2, "warning": 2, "dialog-warning": 2, "dialog-warning-symbolic": 2,
            "error": 3, "dialog-error": 3, "dialog-error-symbolic": 3,
        }
        # Estructura efimera: NIF_INFO nunca queda en tray_data, que tambien se
        # usa al cambiar busy y al reconstruir el icono tras reiniciar Explorer.
        data = NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(data)
        data.hWnd = window_handle
        data.uID = TRAY_ID
        data.uFlags = 0x10  # NIF_INFO.
        data.szInfoTitle, data.szInfo = title, message
        data.dwInfoFlags = icon_flags.get(level, 1)
        accepted = bool(shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(data)))
        log_event(
            f"Aviso nativo: aceptado={accepted}, titulo={title_units}, cuerpo={message_units}",
            origin="WINDOWS", level="DEBUG" if accepted else "WARN", reason="NOTIFY")
        return int(accepted)

    except Exception as error:
        # Una entrada rechazada no debe escapar del callback ctypes ni cerrar WMM.
        log_event(f"Notificacion rechazada: {error}",
            origin="WINDOWS", level="WARN", reason="NOTIFY")
        return 0

def _apply_tray_busy(busy):
    """Alterna el tray entre la identidad WMM y el icono busy de Windows."""
    target_icon = busy_icon if busy and busy_icon else tray_icon
    if not target_icon:
        return

    tray_data.hIcon = target_icon
    shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(tray_data))

def _delete_tray_icon():
    """Retira el notification icon y libera los HICON residentes."""
    global tray_icon, busy_icon

    shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(tray_data))

    if tray_icon:
        user32.DestroyIcon(tray_icon)
        tray_icon = None

    if busy_icon:
        user32.DestroyIcon(busy_icon)
        busy_icon = None

def _mouse_coordinates(wparam):
    """Extrae las coordenadas firmadas entregadas por el tray."""
    x = ctypes.c_short(wparam & 0xFFFF).value
    y = ctypes.c_short((wparam >> 16) & 0xFFFF).value
    return x, y

# ==========================================================
# WIN32: CALLBACK
# ==========================================================

def _window_proc(hwnd, message, wparam, lparam):
    global window_handle

    if message == 0x004A:  # WM_COPYDATA: informes de procesos WMM.
        return _receive_tray_notification(lparam)

    if message == taskbar_created:
        # Explorer destruye los notification icons al reconstruir su taskbar.
        # El HWND permanece vivo, por lo que basta con publicar WMM de nuevo.
        _add_tray_icon()
        return 0

    if message == WM_TRAY_BUSY:
        _apply_tray_busy(bool(wparam))
        return 0

    if message == WM_TRAYICON:
        event = lparam & 0xFFFF
        icon_id = (lparam >> 16) & 0xFFFF
        if icon_id != TRAY_ID:
            return 0

        if event == WM_LBUTTONUP:
            x, y = _mouse_coordinates(wparam)
            GLib.idle_add(_show_main_menu, x, y)
            return 0

        if event == WM_MBUTTONUP:
            GLib.idle_add(_next_background)
            return 0

        if event == WM_RBUTTONUP:
            x, y = _mouse_coordinates(wparam)
            GLib.idle_add(_show_context_menu, x, y)
            return 0

        if event == WM_CONTEXTMENU:
            # Windows 11 emite WM_CONTEXTMENU inmediatamente después de
            # WM_RBUTTONUP; procesar ambos eventos duplicaría el popup.
            return 0

    if message == WM_CLOSE:
        # Todo cierre externo sigue el mismo recorrido que "Salir de WMM".
        # El shutdown pertenece al hilo GTK, no al callback nativo Win32.
        GLib.idle_add(_shutdown_and_quit)
        return 0

    if message == WM_TRAY_QUIT:
        # Confirmación interna del cierre: no reenviar a WM_CLOSE.
        user32.DestroyWindow(hwnd)
        return 0

    if message == WM_DESTROY:
        _delete_tray_icon()
        window_handle = None
        user32.PostQuitMessage(0)

        # GTK/GLib pertenece al hilo principal; el WndProc sólo solicita allí
        # la finalización una vez limpiado el recurso nativo.
        GLib.idle_add(_finish_quit)
        return 0

    return user32.DefWindowProcW(hwnd, message, wparam, lparam)

window_proc = WNDPROC(_window_proc)

# ==========================================================
# WIN32: LOOP NATIVO
# ==========================================================

def _win32_loop():
    """
    Mantiene el HWND y GetMessageW en un hilo dedicado.

    GetMessageW permanece bloqueado hasta recibir trabajo de Windows; no existe
    polling y ningún callback de este hilo manipula directamente widgets GTK.
    """
    global window_handle, tray_icon, busy_icon

    try:
        instance = kernel32.GetModuleHandleW(None)

        window_class = WNDCLASSW()
        window_class.lpfnWndProc = window_proc
        window_class.hInstance = instance
        window_class.lpszClassName = WINDOW_CLASS

        if not user32.RegisterClassW(ctypes.byref(window_class)):
            raise ctypes.WinError(ctypes.get_last_error())

        # Windows entrega directamente el recurso elegido como HICON pequeño.
        extracted_icon = wintypes.HANDLE()
        if shell32.ExtractIconExW(BUSY_ICON_PATH, BUSY_ICON_INDEX,
                None, ctypes.byref(extracted_icon), 1):
            busy_icon = extracted_icon.value
        else:
            print( "[WMM WINDOWS] Icono busy de SHELL32.dll no disponible", flush=True, )

        window_handle = user32.CreateWindowExW(
            0, WINDOW_CLASS, "WMM Windows Frontend", 0,
            0, 0, 0, 0, None, None, instance, None)
        if not window_handle:
            raise ctypes.WinError(ctypes.get_last_error())

        # El tray usa la identidad gráfica propia de WMM. LoadImageW permite
        # cargar directamente el .ico distribuido en la raíz de la aplicación.
        tray_icon = user32.LoadImageW(
            None, ICON_PATH, IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE)
        if not tray_icon:
            # Un ICO ausente, ilegible o corrupto no debe impedir usar WMM.
            # El HICON extraído se libera en _delete_tray_icon(), como el busy.
            fallback_icon = wintypes.HANDLE()
            extracted = shell32.ExtractIconExW(
                FALLBACK_ICON_PATH, FALLBACK_ICON_INDEX,
                None, ctypes.byref(fallback_icon), 1)
            if extracted != 1 or not fallback_icon.value:
                raise RuntimeError("No se pudo cargar el icono WMM ni su fallback")

            tray_icon = fallback_icon.value
            print("[WMM WINDOWS] Icono WMM no disponible; usando SHELL32.dll,174",
                flush=True)

        tray_data.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        tray_data.hWnd = window_handle
        tray_data.uID = TRAY_ID

        # VERSION_4 necesita SHOWTIP para mostrar el tooltip estándar.
        tray_data.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP | NIF_SHOWTIP

        tray_data.uCallbackMessage = WM_TRAYICON
        tray_data.hIcon = (busy_icon if motor_busy and busy_icon else tray_icon)
        tooltip_actions = (
            _("Click action") + ": " + _("Main Menu") + "\n" +
            _("Middle Click") + ": " + _("Next Background") + "\n" +
            _("Secondary Click") + ": " + _("Context Menu"))
        tooltip = "Wallpaper Multi-Monitor Manager\n" + tooltip_actions

        # szTip admite 127 unidades UTF-16 más el terminador. Primero acortamos
        # la cabecera para conservar las descripciones traducidas de las acciones.
        if len(tooltip.encode("utf-16-le")) > 254:
            tooltip = "WMM Manager\n" + tooltip_actions
        tray_data.szTip = tooltip.encode("utf-16-le")[:254].decode("utf-16-le", "ignore")

        # El icono sólo aparece cuando GTK y ambos popups ya existen.
        if not _add_tray_icon():
            user32.DestroyWindow(window_handle)
            return

        message = wintypes.MSG()
        while True:
            result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
            if result == 0:
                break
            if result == -1:
                raise ctypes.WinError(ctypes.get_last_error())

            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))

    except Exception as error:
        print(f"[WMM WINDOWS] Error en el frontend Win32: {error}", flush=True)
        GLib.idle_add(_finish_quit)

# ==========================================================
# CICLO DE VIDA
# ==========================================================

def _request_quit(_item=None):
    """
    Finaliza la ventana nativa después de solicitar el shutdown.

    WM_TRAY_QUIT evita regresar a WM_CLOSE y mantiene la limpieza
    del tray dentro de WM_DESTROY, en su propio hilo Win32.
    """
    if window_handle:
        user32.PostMessageW(window_handle, WM_TRAY_QUIT, 0, 0)
    return GLib.SOURCE_REMOVE

def _finish_quit():
    """Finaliza GLib después de que Win32 haya limpiado el tray."""
    if frontend_loop is not None:
        frontend_loop.quit()
    return GLib.SOURCE_REMOVE

def main():
    """Inicializa GTK y mantiene vivo el frontend residente de Windows."""
    global frontend_loop, frontend_mutex, main_menu, context_menu

    if not _acquire_frontend_instance():
        return

    _prepare_notification_identity()

    Gtk.init(None)

    if hasattr(platform, "prepare_gtk_color_scheme"):
        platform.prepare_gtk_color_scheme(apply_win32_style=False)

    _load_wmm_css()

    GLib.set_prgname("WMM Frontend")
    GLib.set_application_name("WMM Frontend")

    # La primera consulta Gettext pertenece a _initialize_translated_ui().
    # Preparar la observación antes de solicitar el arranque del engine.
    _start_busy_monitor()
    _ensure_engine_running()

    frontend_loop = GLib.MainLoop()

    try:
        frontend_loop.run()
    finally:

        # Limpieza de respaldo: no reactivar el shutdown cuando GLib
        # ya ha finalizado o se está abandonando por una excepción.
        if window_handle:
            user32.PostMessageW(window_handle, WM_TRAY_QUIT, 0, 0)

        if main_menu is not None:
            main_menu.destroy()

        if context_menu is not None:
            context_menu.destroy()

        if frontend_mutex:
            kernel32.CloseHandle(frontend_mutex)
            frontend_mutex = None

        print("[WMM WINDOWS] Frontend detenido", flush=True)
        frontend_loop = None

if __name__ == "__main__":
    main()
