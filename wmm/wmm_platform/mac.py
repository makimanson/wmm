#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

"""
WMM - Wallpaper Multi-Monitor Manager

mac.py - Módulo de plataforma para macOS.
==========================================================
Contiene funciones comunes a macOS (independientes del escritorio).
"""
import os
import subprocess
import fcntl

def normalize_platform(raw_platform):
    """Normaliza el valor de sys.platform al nombre canónico del SO."""
    return raw_platform

def detect_desktop():
    """Detecta el escritorio actual (esqueleto)."""
    return 'generic'

def get_system_paths():
    """
    Devuelve las rutas base del sistema para macOS.
    TODO: Implementar usando ~/Library/Application Support, ~/Library/Caches, etc.
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
    Bloquea el archivo para escritura exclusiva usando fcntl.flock.
    Disponible en macOS por ser un sistema Unix.
    """
    fcntl.flock(f, fcntl.LOCK_EX)

def unlock_file(f):
    """
    Desbloquea el archivo previamente bloqueado con lock_file.
    """
    fcntl.flock(f, fcntl.LOCK_UN)

def open_file(path, capability=None, **params):
    """
    Abre un archivo o directorio con la aplicación predeterminada en macOS.
    """
    subprocess.run(["open", path], check=False)

def send_notification(title, message, level="info"):
    """
    Envía una notificación en macOS.
    """
    # TODO: Implementar usando osascript o PyObjC
    print(f"[NOTIFICACIÓN] {title}: {message}")

def _force_desktop_settings(config_handler):
    """
    Fuerza los ajustes del sistema necesarios para que WMM funcione
    correctamente en macOS.
    TODO: Implementar usando subprocess.run con defaults o PyObjC.
    """
    pass

def ensure_shell_actions(applet_root, data_base):
    """
    Instala las acciones de shell necesarias para macOS
    (p. ej., servicios del Finder).
    TODO: Implementar cuando se añada soporte para macOS.
    """
    pass

def set_wallpaper(path, config_handler=None):
    """
    Aplica el fondo de pantalla en macOS.
    TODO: Implementar usando NSWorkspace o CoreGraphics.
    """
    # TODO: Usar NSWorkspace.sharedWorkspace().setDesktopImageURL_forScreen_options_error()
    # o la API de CoreGraphics CGSSetDesktopImage.
    pass

def compile_translations(app_root, locale_dir, app_domain):
    """
    Compila los archivos .po a .mo en macOS.
    TODO: Verificar que msgfmt está disponible (posiblemente via Homebrew).
    """
    # TODO: Similar a linux.py, pero asegurarse de que msgfmt existe en el PATH.
    # En macOS, se puede instalar via Homebrew: brew install gettext
    pass

def ensure_keybindings(app_dir):
    """
    Crea un atajo de teclado para "Next Background" en macOS.
    TODO: Implementar usando defaults o creando un servicio global.
    """
    # TODO: Crear entrada en defaults para un atajo global, o usar
    # la API de servicios de macOS (NSServices).
    pass

def init_channels(data_dir):
    """
    Registra los canales de comunicación soportados por macOS.
    TODO: Implementar canales (archivo, y posiblemente Apple Events).
    """
    # TODO: Registrar FileChannel (similar a linux) y quizás un canal
    # basado en Apple Events / Distributed Objects para comunicación entre procesos.
    pass

def normalize_desktop(desktop):
    """
    Normaliza el nombre del escritorio para macOS.
    En macOS, no hay múltiples escritorios como en Linux, así que siempre devuelve 'macos'.
    """
    return 'macos'
