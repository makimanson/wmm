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
import shutil
import time

from debug_logger import log_event

# ---------------------------------------------------------------------
# Desktop Wallpaper COM API
# ---------------------------------------------------------------------

import ctypes
import uuid
from ctypes import wintypes

class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]

def _guid(value):
    """Convierte una representación textual de GUID al formato Win32."""
    return _GUID.from_buffer_copy(uuid.UUID(value).bytes_le)

_CLSID_DESKTOP_WALLPAPER = _guid("C2CF3110-460E-4FC1-B9D0-8A1C0C9CC4BD")
_IID_IDESKTOP_WALLPAPER = _guid("B92B56A9-8B55-4E14-9A89-0199BBB6F93B")
_IID_ISHELL_ITEM = _guid("43826D1E-E718-42EE-BC55-A1E261C37BFE")
_IID_ISHELL_ITEM_ARRAY = _guid("B63EA76D-1F85-456F-A19C-48159EFA858B")

def _check_hresult(hr, operation):
    """Convierte un HRESULT fallido en una excepción legible."""
    if hr < 0:
        raise OSError(f"{operation} falló (HRESULT 0x{hr & 0xFFFFFFFF:08X})")

def _com_method(interface, index, restype, *argtypes):
    """Obtiene un método de una interfaz COM por su posición en la vtable."""
    vtable = ctypes.cast(interface, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)), ).contents

    return ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(vtable[index])

def _release_com(interface):
    """Libera una referencia COM obtenida mediante ctypes."""
    if interface:
        release = _com_method(interface, 2, wintypes.ULONG)
        release(interface)

def _open_desktop_wallpaper():
    """Inicializa COM y obtiene IDesktopWallpaper para el hilo actual."""
    ole32 = ctypes.WinDLL("ole32")

    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    ole32.CoInitializeEx.restype = ctypes.c_long

    ole32.CoCreateInstance.argtypes = [
        ctypes.POINTER(_GUID),
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_GUID),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    ole32.CoCreateInstance.restype = ctypes.c_long

    ole32.CoUninitialize.argtypes = []
    ole32.CoUninitialize.restype = None

    # COINIT_APARTMENTTHREADED. Si el hilo ya estaba inicializado con otro
    # modelo, COM sigue disponible y no debemos equilibrar esa inicialización.
    hr = ole32.CoInitializeEx(None, 0x00000002)
    hr_code = hr & 0xFFFFFFFF
    com_initialized = hr >= 0

    if hr < 0 and hr_code != 0x80010106:  # RPC_E_CHANGED_MODE
        _check_hresult(hr, "CoInitializeEx")

    desktop = ctypes.c_void_p()

    try:
        hr = ole32.CoCreateInstance(ctypes.byref(_CLSID_DESKTOP_WALLPAPER),
            None, 0x00000004,  # CLSCTX_LOCAL_SERVER
            ctypes.byref(_IID_IDESKTOP_WALLPAPER), ctypes.byref(desktop))
        _check_hresult(hr, "CoCreateInstance(IDesktopWallpaper)")
        return desktop, ole32, com_initialized

    except Exception:
        if com_initialized:
            ole32.CoUninitialize()
        raise

def _close_desktop_wallpaper(desktop, ole32, com_initialized):
    """Libera IDesktopWallpaper y equilibra la inicialización COM propia."""
    _release_com(desktop)

    if com_initialized:
        ole32.CoUninitialize()

def get_install_path(data_base, app_domain):
    """Devuelve la ruta de instalación (esqueleto)."""
    if data_base:
        return os.path.join(data_base, app_domain)
    return app_domain

def get_window_available_area(pid):
    """
    Devuelve la workarea del monitor que contiene el Panel.

    Utiliza coordenadas GDK, igual que GTK al dimensionar la ventana,
    para respetar las reservas de la barra de tareas de Windows.
    """
    try:
        if int(pid) != os.getpid():
            return None

        from gi.repository import Gdk, Gio, Gtk

        app = Gio.Application.get_default()
        if not isinstance(app, Gtk.Application):
            return None

        window = next((w for w in app.get_windows()
            if isinstance(w, Gtk.ApplicationWindow) and w.get_window()), None)

        if window is None:
            return None

        display = Gdk.Display.get_default()
        if display is None:
            return None

        monitor = display.get_monitor_at_window(window.get_window())
        if monitor is None:
            return None

        workarea = monitor.get_workarea()

        if workarea.width <= 0 or workarea.height <= 0:
            return None

        return {
            "x": workarea.x,
            "y": workarea.y,
            "width": workarea.width,
            "height": workarea.height,
        }

    except Exception as error:
        log_event(f"No se pudo obtener el área útil del Panel: {error}",
            origin="WINDOWS", level="WARN", reason="LAYOUT")
        return None

def render_master_wallpaper(self, processed_images, monitors_map, config_handler):
    """Monta el lienzo maestro y lo aplica mediante el backend de Windows."""
    from PIL import Image

    if not processed_images:
        log_event("No hay imágenes procesadas para Windows",
            origin="WINDOWS", level="ERROR", reason="LIBRARY")
        return False

    canvas_w = max(mon["x"] + mon["width"] for mon in monitors_map.values())
    canvas_h = max(mon["y"] + mon["height"] for mon in monitors_map.values())

    master_canvas = Image.new("RGB", (canvas_w, canvas_h), (0, 0, 0))

    for m_hash, img in processed_images.items():
        if m_hash not in monitors_map:
            continue

        mon = monitors_map[m_hash]
        master_canvas.paste(img, (mon["x"], mon["y"]))

    master_path = os.path.join(config_handler.cache_dir, "wallpaper_master.jpg")

    return self.set_wallpaper(master_canvas, master_path, config_handler)

def _get_slideshow_source(desktop, ole32):
    """
    Devuelve la carpeta configurada como fuente del slideshow, si Windows
    expone una única carpeta contenedora.
    """
    items = ctypes.c_void_p()
    item = ctypes.c_void_p()
    display_name = ctypes.c_void_p()

    try:
        get_slideshow = _com_method(
            desktop, 13, ctypes.c_long, ctypes.POINTER(ctypes.c_void_p))

        hr = get_slideshow(desktop, ctypes.byref(items))
        if hr < 0 or not items:
            return None

        get_count = _com_method(items, 7, ctypes.c_long, ctypes.POINTER(wintypes.DWORD))
        count = wintypes.DWORD()
        _check_hresult(get_count(items, ctypes.byref(count)),
            "IShellItemArray.GetCount")

        if count.value != 1:
            return None

        get_item_at = _com_method(
            items, 8, ctypes.c_long, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p))
        _check_hresult(get_item_at(items, 0, ctypes.byref(item)),
            "IShellItemArray.GetItemAt")
        get_display_name = _com_method(
            item, 5, ctypes.c_long, ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p))

        # SIGDN_FILESYSPATH
        _check_hresult(get_display_name(item, 0x80058000, ctypes.byref(display_name)),
            "IShellItem.GetDisplayName")

        return ctypes.wstring_at(display_name)

    finally:
        if display_name:
            ole32.CoTaskMemFree(display_name)

        _release_com(item)
        _release_com(items)

def _get_slideshow_state(desktop, ole32, cache_dir):
    """
    Devuelve si Windows mantiene la cache de WMM como fuente y si el
    slideshow está realmente activo.
    """
    get_status = _com_method(
        desktop, 17, ctypes.c_long, ctypes.POINTER(wintypes.DWORD))

    state = wintypes.DWORD()
    _check_hresult(
        get_status(desktop, ctypes.byref(state)),
        "IDesktopWallpaper.GetStatus")

    current_source = _get_slideshow_source(desktop, ole32)
    source_matches = (
        current_source is not None
        and os.path.normcase(os.path.normpath(current_source))
        == os.path.normcase(os.path.normpath(cache_dir))
    )

    # DSS_ENABLED | DSS_SLIDESHOW
    slideshow_active = (state.value & 0x03) == 0x03

    return source_matches, slideshow_active

def _force_desktop_settings(config_handler, desktop, reset_slideshow=False):
    """
    Mantiene Windows en el estado requerido por el backend de WMM:
      - slideshow de la cache de WMM
      - shuffle desactivado
      - intervalo de 1 día
      - fondo negro
      - posición SPAN

    La fuente sólo se reconstruye cuando set_wallpaper determina que el
    slideshow ha perdido el estado requerido.
    """
    cache_dir = getattr(config_handler, "cache_dir", None)

    if not cache_dir or not os.path.isdir(cache_dir):
        log_event("No existe la carpeta cache necesaria para el slideshow",
            origin="WINDOWS", level="ERROR", reason="SETTINGS")
        return False

    folder = ctypes.c_void_p()
    items = ctypes.c_void_p()

    try:
        if reset_slideshow:
            shell32 = ctypes.WinDLL("shell32")

            shell32.SHCreateItemFromParsingName.argtypes = [
                wintypes.LPCWSTR,
                ctypes.c_void_p,
                ctypes.POINTER(_GUID),
                ctypes.POINTER(ctypes.c_void_p),
            ]
            shell32.SHCreateItemFromParsingName.restype = ctypes.c_long

            shell32.SHCreateShellItemArrayFromShellItem.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(_GUID),
                ctypes.POINTER(ctypes.c_void_p),
            ]
            shell32.SHCreateShellItemArrayFromShellItem.restype = ctypes.c_long

            _check_hresult(shell32.SHCreateItemFromParsingName(cache_dir, None,
                    ctypes.byref(_IID_ISHELL_ITEM), ctypes.byref(folder)),
                    "SHCreateItemFromParsingName")

            _check_hresult(shell32.SHCreateShellItemArrayFromShellItem(folder,
                ctypes.byref(_IID_ISHELL_ITEM_ARRAY), ctypes.byref(items)),
                "SHCreateShellItemArrayFromShellItem")

            set_slideshow = _com_method(
                desktop, 12, ctypes.c_long, ctypes.c_void_p)

            _check_hresult(set_slideshow(desktop, items),
                "IDesktopWallpaper.SetSlideshow")

            log_event("Slideshow Windows vinculado a la cache de WMM",
                origin="WINDOWS", level="DEBUG", reason="SETTINGS")

        get_slideshow_options = _com_method(desktop, 15, ctypes.c_long,
            ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.UINT))
        set_slideshow_options = _com_method(desktop, 14, ctypes.c_long,
            wintypes.DWORD, wintypes.UINT)
        get_background_color = _com_method(desktop, 9, ctypes.c_long,
            ctypes.POINTER(wintypes.DWORD))
        set_background_color = _com_method(desktop, 8, ctypes.c_long,
            wintypes.DWORD)
        get_position = _com_method(desktop, 11, ctypes.c_long,
            ctypes.POINTER(ctypes.c_int))
        set_position = _com_method(desktop, 10, ctypes.c_long, ctypes.c_int)

        options = wintypes.DWORD()
        interval = wintypes.UINT()
        background_color = wintypes.DWORD()
        position = ctypes.c_int()

        _check_hresult(get_slideshow_options(desktop, ctypes.byref(options), ctypes.byref(interval)),
            "IDesktopWallpaper.GetSlideshowOptions")
        _check_hresult(get_background_color(desktop, ctypes.byref(background_color)),
            "IDesktopWallpaper.GetBackgroundColor")
        _check_hresult(get_position(desktop, ctypes.byref(position)),
            "IDesktopWallpaper.GetPosition")

        # No reafirmar ajustes que Windows ya mantiene. Además de evitar trabajo
        # innecesario, SetBackgroundColor provoca un repaint incluso sin cambiar
        # el valor, interfiriendo con el cierre de la transición del slideshow.
        if options.value != 0 or interval.value != 86400000:
            _check_hresult(set_slideshow_options(desktop, 0, 86400000),
                "IDesktopWallpaper.SetSlideshowOptions")

        if background_color.value != 0:
            _check_hresult(set_background_color(desktop, 0),
                "IDesktopWallpaper.SetBackgroundColor")

        # SetSlideshow puede restaurar la posición previa del usuario; al leer
        # después de configurarlo sólo corregimos SPAN cuando realmente difiere.
        if position.value != 5:
            _check_hresult(set_position(desktop, 5),
                "IDesktopWallpaper.SetPosition")

        log_event("Ajustes Windows verificados: slideshow WMM, 1 día, SPAN y fondo negro",
            origin="WINDOWS", level="DEBUG", reason="SETTINGS")
        return True

    except Exception as e:
        log_event(f"No se pudieron forzar los ajustes Windows: {e}",
            origin="WINDOWS", level="ERROR", reason="SETTINGS")
        return False

    finally:
        _release_com(items)
        _release_com(folder)

def set_wallpaper(master_canvas, master_path, config_handler):
    """
    Guarda y aplica el wallpaper maestro mediante el slideshow nativo de Windows.

    Alterna entre dos archivos para que AdvanceSlideshow cambie siempre de
    recurso y Windows conserve su transición nativa.
    """
    desktop = None
    ole32 = None
    com_initialized = False
    monitor_ptr = ctypes.c_void_p()
    wallpaper_ptr = ctypes.c_void_p()

    try:
        root, ext = os.path.splitext(master_path)
        ext = ext or ".jpg"

        path_0 = f"{root}_0{ext}"
        path_1 = f"{root}_1{ext}"

        slots_ready = os.path.isfile(path_0) and os.path.isfile(path_1)

        desktop, ole32, com_initialized = _open_desktop_wallpaper()

        ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
        ole32.CoTaskMemFree.restype = None

        source_matches, slideshow_active = _get_slideshow_state(
            desktop, ole32, config_handler.cache_dir)

        needs_reset = (not slots_ready or not source_matches or not slideshow_active)

        if needs_reset:
            # El slideshow necesita dos imágenes válidas. Al iniciar o recuperar
            # su estado, ambos slots parten de la composición actual.
            master_canvas.save(path_0, "JPEG", quality=95)
            shutil.copyfile(path_0, path_1)

            if not _force_desktop_settings(
                    config_handler, desktop, reset_slideshow=True):
                return False

            # Solicitar a Windows el primer fondo del slideshow recién
            # reconstruido. Ambos slots son idénticos; no usar el ciclo
            # SYNC de fade-out/fade-in ni alterar la rama normal.
            advance_slideshow = _com_method(
                desktop, 16, ctypes.c_long, wintypes.LPCWSTR, ctypes.c_int)
            _check_hresult(advance_slideshow(desktop, None, 0),
                "IDesktopWallpaper.AdvanceSlideshow (initial reset)")

            log_event("Doble buffer Windows preparado y slideshow sincronizado",
                origin="WINDOWS", level="INFO", reason="SETTINGS")
            return True

        if not _force_desktop_settings(config_handler, desktop):
            return False

        get_monitor_count = _com_method(
            desktop, 6, ctypes.c_long, ctypes.POINTER(wintypes.UINT))
        get_monitor_at = _com_method(
            desktop, 5, ctypes.c_long,
            wintypes.UINT, ctypes.POINTER(ctypes.c_void_p))
        get_wallpaper = _com_method(
            desktop, 4, ctypes.c_long,
            wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p))
        advance_slideshow = _com_method(
            desktop, 16, ctypes.c_long, wintypes.LPCWSTR, ctypes.c_int)

        monitor_count = wintypes.UINT()
        _check_hresult(get_monitor_count(desktop, ctypes.byref(monitor_count)),
            "IDesktopWallpaper.GetMonitorDevicePathCount")

        if monitor_count.value == 0:
            log_event("Windows no devolvió ningún monitor para aplicar el wallpaper",
                origin="WINDOWS", level="ERROR", reason="HARDWARE")
            return False

        _check_hresult(get_monitor_at(desktop, 0, ctypes.byref(monitor_ptr)),
            "IDesktopWallpaper.GetMonitorDevicePathAt")

        monitor_id = ctypes.wstring_at(monitor_ptr)

        _check_hresult(get_wallpaper(desktop, monitor_id, ctypes.byref(wallpaper_ptr)),
            "IDesktopWallpaper.GetWallpaper")

        current_path = ctypes.wstring_at(wallpaper_ptr) if wallpaper_ptr else ""

        current_norm = os.path.normcase(os.path.normpath(current_path))
        path_0_norm = os.path.normcase(os.path.normpath(path_0))

        next_path = path_1 if current_norm == path_0_norm else path_0

        settings = config_handler.load_json("settings").get("global", {})
        sl_mode = settings.get("slideshow_mode", "sync")

        if sl_mode == "sync":
            from PIL import Image

            # Fade-out: preparar el slot inactivo en negro y avanzar.
            # Se reutiliza el mismo archivo del slideshow, sin crear otro.
            Image.new("RGB", (1, 1), (0, 0, 0)).save(next_path, "JPEG", quality=95)

            _check_hresult(advance_slideshow(desktop, None, 0),
                "IDesktopWallpaper.AdvanceSlideshow (fade-out)")

            # Pausa visual deliberada, siguiendo el criterio de GNOME y KDE.
            # Permite consumir la transición nativa antes del segundo avance.
            time.sleep(1.1)

            # Fade-in: el antiguo slot activo queda disponible para recibir
            # la nueva imagen y completar la segunda transición.
            next_path = path_0 if current_norm == path_0_norm else path_1

        # SYNC aplica la imagen tras el negro; ASYNC conserva el crossfade
        # original mediante un único avance al slot alternativo.
        master_canvas.save(next_path, "JPEG", quality=95)

        _check_hresult(advance_slideshow(desktop, None, 0),
            "IDesktopWallpaper.AdvanceSlideshow")

        log_event(f"Transición Windows {sl_mode.upper()} aplicada: {next_path}",
            origin="WINDOWS", level="INFO", reason="SETTINGS")
        return True

    except Exception as e:
        log_event(f"No se pudo generar/aplicar el wallpaper maestro en Windows: {e}",
            origin="WINDOWS", level="ERROR", reason="SETTINGS")
        return False

    finally:
        if ole32 is not None:
            if wallpaper_ptr:
                ole32.CoTaskMemFree(wallpaper_ptr)
            if monitor_ptr:
                ole32.CoTaskMemFree(monitor_ptr)

        if desktop is not None:
            _close_desktop_wallpaper(
                desktop, ole32, com_initialized)

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

class _NextBackgroundHotkey:
    """Mantiene un atajo global en un hilo nativo, sin sondeo ni widgets GTK."""

    _WM_CONFIGURE = 0x8000 + 20
    _WM_HOTKEY = 0x0312
    _IDS = (0x501, 0x502)

    def __init__(self, on_activate):
        import threading

        self._on_activate = on_activate
        self._thread = threading.Thread(
            target=self._listen, name="WMM-NextBackgroundHotkey", daemon=True)
        self._ready = threading.Event()
        self._request_lock = threading.Lock()
        self._request = None
        self._thread_id = None
        self._user32 = None
        self._error = None
        self._active_id = None
        self._shortcut = None

    def start(self):
        """Espera a que exista la cola nativa antes de admitir peticiones."""
        with self._request_lock:
            if self._thread.ident is None:
                self._thread.start()
            self._ready.wait()
            return self._error is None and self._thread.is_alive()

    def configure(self, shortcut):
        """Solicita un cambio y devuelve su resultado real de registro."""
        import threading

        canonical, modifiers, virtual_key = _next_background_hotkey_binding(shortcut)
        with self._request_lock:
            if self._thread_id is None or self._error is not None:
                raise RuntimeError("El receptor del atajo no está disponible")

            request = {
                "shortcut": canonical, "modifiers": modifiers, "key": virtual_key,
                "done": threading.Event(), "result": None,
            }
            self._request = request
            try:
                if not self._user32.PostThreadMessageW(
                        self._thread_id, self._WM_CONFIGURE, 0, 0):
                    raise ctypes.WinError(ctypes.get_last_error())
                request["done"].wait()
                if request["result"] is None:
                    raise RuntimeError("El receptor del atajo se ha detenido") from self._error
                return request["result"]
            finally:
                self._request = None

    def stop(self):
        """Despierta la escucha bloqueante y espera la retirada del registro."""
        with self._request_lock:
            if not self._thread.is_alive():
                return
            if self._thread_id is not None:
                if not self._user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0):
                    raise ctypes.WinError(ctypes.get_last_error())
            self._thread.join()

    def _configure_native(self, request):
        """Ejecuta el cambio exclusivamente en el hilo propietario del atajo."""
        shortcut = request["shortcut"]
        if shortcut == self._shortcut:
            return {"ok": True, "shortcut": self._shortcut, "error": 0}

        new_id = self._IDS[1] if self._active_id == self._IDS[0] else self._IDS[0]
        if shortcut is not None:
            # Reservar primero la nueva combinación conserva la anterior
            # cuando Windows rechaza el cambio porque ya está ocupada.
            if not self._user32.RegisterHotKey(
                    None, new_id, request["modifiers"] | 0x4000, request["key"]):
                return {"ok": False, "shortcut": self._shortcut,
                        "error": ctypes.get_last_error()}

        if self._active_id is not None:
            if not self._user32.UnregisterHotKey(None, self._active_id):
                error = ctypes.get_last_error()
                if shortcut is not None:
                    self._user32.UnregisterHotKey(None, new_id)
                return {"ok": False, "shortcut": self._shortcut, "error": error}

        self._active_id = new_id if shortcut is not None else None
        self._shortcut = shortcut
        return {"ok": True, "shortcut": self._shortcut, "error": 0}

    def _listen(self):
        """Recibe WM_HOTKEY y peticiones de configuración mediante GetMessageW."""
        try:
            class _Message(ctypes.Structure):
                _fields_ = [
                    ("hwnd", wintypes.HWND), ("message", wintypes.UINT),
                    ("wParam", wintypes.WPARAM), ("lParam", wintypes.LPARAM),
                    ("time", wintypes.DWORD), ("pt", wintypes.POINT),
                    ("lPrivate", wintypes.DWORD),
                ]

            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.RegisterHotKey.argtypes = [
                wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
            user32.RegisterHotKey.restype = wintypes.BOOL
            user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
            user32.UnregisterHotKey.restype = wintypes.BOOL
            user32.GetMessageW.argtypes = [
                ctypes.POINTER(_Message), wintypes.HWND, wintypes.UINT, wintypes.UINT]
            user32.GetMessageW.restype = wintypes.BOOL
            user32.PeekMessageW.argtypes = [ctypes.POINTER(_Message), wintypes.HWND,
                wintypes.UINT, wintypes.UINT, wintypes.UINT]
            user32.PeekMessageW.restype = wintypes.BOOL
            user32.PostThreadMessageW.argtypes = [
                wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            user32.PostThreadMessageW.restype = wintypes.BOOL

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.GetCurrentThreadId.argtypes = []
            kernel32.GetCurrentThreadId.restype = wintypes.DWORD

            message = _Message()
            # Una única llamada crea la cola. La espera posterior es
            # bloqueante: no se utiliza PeekMessage como sondeo periódico.
            user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 0)
            self._user32 = user32
            self._thread_id = kernel32.GetCurrentThreadId()
            self._ready.set()

            while True:
                result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result == -1:
                    raise ctypes.WinError(ctypes.get_last_error())
                if result == 0:
                    break

                if message.message == self._WM_CONFIGURE:
                    request = self._request
                    if request is not None:
                        request["result"] = self._configure_native(request)
                        request["done"].set()
                elif message.message == self._WM_HOTKEY and message.wParam == self._active_id:
                    try:
                        # El callback se ejecuta en este hilo: debe emitir
                        # la orden, sin acceder a widgets ni al estado de GTK.
                        self._on_activate()
                    except Exception as e:
                        log_event(f"Error al emitir la orden del atajo: {e}",
                            origin="WINDOWS", level="ERROR", reason="COMMAND")

        except Exception as e:
            self._error = e
            log_event(f"Error en el receptor del atajo: {e}",
                origin="WINDOWS", level="ERROR", reason="COMMAND")
        finally:
            if self._user32 is not None:
                for hotkey_id in self._IDS:
                    self._user32.UnregisterHotKey(None, hotkey_id)
            self._thread_id = None
            self._active_id = None
            self._shortcut = None
            self._ready.set()
            # Una salida nativa anómala también libera al solicitante;
            # no puede quedar esperando una confirmación que ya no llegará.
            request = self._request
            if request is not None:
                request["done"].set()



def _start_keybindings_requests(data_dir, receiver):
    """Atiende consultas y cambios del atajo; devuelve su función de cierre."""
    import json
    import threading
    from multiprocessing.connection import Client, Listener
    from wmm_platform.channels import NamedPipeChannel

    # Reutilizar la identidad por instalación de NamedPipeChannel mantiene
    # este intercambio separado de las órdenes normales, que no tienen respuesta.
    address = NamedPipeChannel(data_dir, endpoint="keybindings")._address
    listener = Listener(address, family="AF_PIPE")
    stopping = threading.Event()

    def receive_requests():
        try:
            while not stopping.is_set():
                connection = listener.accept()
                try:
                    if stopping.is_set():
                        break
                    try:
                        request = json.loads(connection.recv_bytes(4096).decode("utf-8"))
                        if not isinstance(request, dict):
                            raise ValueError("La petición del atajo no es un objeto")
                        action = request.get("action")
                        if action == "get":
                            result = {"ok": True, "shortcut": receiver._shortcut, "error": 0}
                        elif action == "set" and "shortcut" in request:
                            result = receiver.configure(request["shortcut"])
                        else:
                            raise ValueError("Petición del atajo no admitida")
                    except Exception as e:
                        log_event(f"Error en la petición del atajo: {e}",
                            origin="WINDOWS", level="ERROR", reason="SETTINGS")
                        result = {"ok": False, "shortcut": receiver._shortcut,
                                  "error": "request_failed"}

                    connection.send_bytes(json.dumps(result, ensure_ascii=False,
                        separators=(",", ":")).encode("utf-8"))
                except (EOFError, OSError) as e:
                    if not stopping.is_set():
                        log_event(f"No se pudo responder a la petición del atajo: {e}",
                            origin="WINDOWS", level="ERROR", reason="SETTINGS")
                finally:
                    connection.close()
        except (EOFError, OSError) as e:
            if not stopping.is_set():
                log_event(f"Error en el canal de configuración del atajo: {e}",
                    origin="WINDOWS", level="ERROR", reason="SETTINGS")
        finally:
            listener.close()

    thread = threading.Thread(target=receive_requests,
        name="WMM-KeybindingsRequests", daemon=True)
    try:
        thread.start()
    except Exception:
        listener.close()
        raise

    def stop_requests():
        if not thread.is_alive():
            return
        stopping.set()
        # Una conexión despierta accept() para cerrar el servidor antes
        # de retirar el receptor nativo. No hay sondeo ni temporizadores.
        try:
            connection = Client(address, family="AF_PIPE")
            connection.close()
        except (EOFError, OSError):
            pass
        thread.join()

    return stop_requests

def request_keybindings(data_dir, request):
    """Consulta o cambia el registro del motor y recibe su confirmación."""
    import json
    from multiprocessing.connection import Client
    from wmm_platform.channels import NamedPipeChannel

    payload = json.dumps(request, ensure_ascii=False,
        separators=(",", ":")).encode("utf-8")
    if len(payload) > 4096:
        raise ValueError("Petición del atajo demasiado grande")

    address = NamedPipeChannel(data_dir, endpoint="keybindings")._address
    connection = Client(address, family="AF_PIPE")
    try:
        connection.send_bytes(payload)
        result = json.loads(connection.recv_bytes(4096).decode("utf-8"))
        if not isinstance(result, dict) or not isinstance(result.get("ok"), bool):
            raise ValueError("Respuesta del atajo no válida")
        return result
    finally:
        connection.close()

_next_background_hotkey = None
_next_background_hotkey_pending = False

def validate_keybinding(shortcut):
    """Publica la validación canónica para el formulario común."""
    return _next_background_hotkey_binding(shortcut)[0]

def apply_keybinding(config_handler, shortcut):
    """Registra Siguiente fondo y confirma su persistencia en settings.json."""
    import copy
    from i18n import _

    canonical = _next_background_hotkey_binding(shortcut)[0]
    settings = config_handler.load_json("settings")
    if not isinstance(settings, dict) or not isinstance(settings.get("global"), dict):
        raise ValueError(_("Could not read WMM settings."))

    previous = request_keybindings(config_handler.data_dir, {"action": "get"})
    if not previous["ok"]:
        raise RuntimeError(f"No se pudo consultar el registro del atajo: {previous}")
    result = request_keybindings(config_handler.data_dir,
        {"action": "set", "shortcut": canonical})
    if not result["ok"]:
        log_event(f"Registro del atajo rechazado: error={result['error']}",
            origin="WINDOWS", level="WARN", reason="SETTINGS")
        if result.get("error") == 1409:
            raise ValueError(_("This key combination is already in use."))
        raise ValueError(_("Could not register the keyboard shortcut."))

    key = "next_background_hotkey"
    updated = copy.deepcopy(settings)
    updated["global"][key] = canonical
    try:
        config_handler.save_json("settings", updated)
        saved = config_handler.load_json("settings")
        # save_json registra sus errores sin propagarlos: releer el ajuste
        # evita confirmar como guardado un cambio que no llegó al archivo.
        if (not isinstance(saved, dict) or not isinstance(saved.get("global"), dict)
                or key not in saved["global"] or saved["global"][key] != canonical):
            raise RuntimeError("El atajo no coincide con el ajuste guardado")
    except Exception as error:
        log_event(f"No se pudo guardar el atajo: {error}",
            origin="WINDOWS", level="ERROR", reason="SETTINGS")
        rollback_failed = False
        try:
            observed = config_handler.load_json("settings")
            restored_settings = observed
            if (not isinstance(restored_settings, dict)
                    or not isinstance(restored_settings.get("global"), dict)):
                restored_settings = copy.deepcopy(settings)
            else:
                # Si otros ajustes cambiaron, conservarlos al retirar solamente
                # nuestro cambio. Un JSON dañado se recupera de la lectura inicial.
                restored_settings = copy.deepcopy(restored_settings)
                if key in settings["global"]:
                    restored_settings["global"][key] = settings["global"][key]
                else:
                    restored_settings["global"].pop(key, None)
            if observed != restored_settings:
                config_handler.save_json("settings", restored_settings)
            if config_handler.load_json("settings") != restored_settings:
                raise RuntimeError("No se pudo confirmar la restauración de settings")
        except Exception as restore_error:
            rollback_failed = True
            log_event(f"Error restaurando settings tras el fallo del atajo: {restore_error}",
                origin="WINDOWS", level="ERROR", reason="SETTINGS")

        try:
            restored = request_keybindings(config_handler.data_dir,
                {"action": "set", "shortcut": previous["shortcut"]})
            if not restored["ok"] or restored["shortcut"] != previous["shortcut"]:
                raise RuntimeError(f"Restauración del registro rechazada: {restored}")
        except Exception as restore_error:
            rollback_failed = True
            log_event(f"Error restaurando el registro del atajo: {restore_error}",
                origin="WINDOWS", level="ERROR", reason="SETTINGS")

        if rollback_failed:
            raise ValueError(_("Could not restore the previous shortcut settings.")) from error
        raise ValueError(_("Could not save the keyboard shortcut.")) from error

    log_event(f"Atajo guardado: {canonical}",
        origin="WINDOWS", level="INFO", reason="SETTINGS")
    return canonical

def ensure_keybindings(app_dir):
    """Prepara una única escucha y recupera el atajo guardado al arrancar."""
    global _next_background_hotkey_pending

    if _next_background_hotkey is not None or _next_background_hotkey_pending:
        return True

    import atexit
    import json
    from gi.repository import GLib

    sender_path = os.path.join(app_dir, "python", "send_command.py")

    def emit_rotation():
        import threading

        # Usar el mismo emisor que los frontends conserva la barrera de
        # admisión de force_rotation mientras el engine está ocupado.
        process = subprocess.Popen(
            [sys.executable, sender_path, '{"action":"force_rotation"}', "HOTKEY"],
            creationflags=subprocess.CREATE_NO_WINDOW)
        threading.Thread(target=process.wait,
            name=f"WMM-HotkeyCommand-{process.pid}", daemon=True).start()

    def start_receiver():
        global _next_background_hotkey, _next_background_hotkey_pending

        receiver = None
        try:
            # Las rutas explícitas del .ini siguen teniendo prioridad.
            # No derivar data_dir de app_dir ni recrear ConfigHandler.
            from wmm_platform.core import PlatformManager
            platform = PlatformManager()
            settings_path = os.path.join(platform.data_dir, "settings.json")
            with open(settings_path, "r", encoding="utf-8") as settings_file:
                settings = json.load(settings_file)
            shortcut = settings.get("global", {}).get("next_background_hotkey")

            if not os.path.isfile(sender_path):
                raise FileNotFoundError(sender_path)

            receiver = _NextBackgroundHotkey(emit_rotation)
            if not receiver.start():
                raise RuntimeError("No se pudo iniciar el receptor del atajo")

            result = receiver.configure(shortcut)
            stop_requests = _start_keybindings_requests(platform.data_dir, receiver)
            atexit.register(receiver.stop)
            atexit.register(stop_requests)
            _next_background_hotkey = receiver

            if not result["ok"]:
                log_event(f"No se pudo recuperar el atajo guardado: error={result['error']}",
                    origin="WINDOWS", level="WARN", reason="SETTINGS")
            elif result["shortcut"] is None:
                log_event("Receptor de atajos preparado; sin combinación asignada",
                    origin="WINDOWS", level="INFO", reason="SETTINGS")
            else:
                log_event(f"Atajo recuperado: {result['shortcut']}",
                    origin="WINDOWS", level="INFO", reason="SETTINGS")

        except Exception as e:
            _next_background_hotkey = None
            if receiver is not None:
                try:
                    receiver.stop()
                except Exception as stop_error:
                    log_event(f"Error al cerrar el receptor del atajo: {stop_error}",
                        origin="WINDOWS", level="ERROR", reason="SETTINGS")
            log_event(f"No se pudo preparar el atajo: {e}",
                origin="WINDOWS", level="ERROR", reason="SETTINGS")
        finally:
            _next_background_hotkey_pending = False

        return GLib.SOURCE_REMOVE

    # Post-instalación llama a este método antes del lock de instancia;
    # run() vuelve a llamarlo después. Una única fuente diferida evita
    # registrar desde el primer punto o iniciar dos receptores.
    _next_background_hotkey_pending = True
    try:
        GLib.idle_add(start_receiver)
    except Exception:
        _next_background_hotkey_pending = False
        raise
    return True