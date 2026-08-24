#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

"""
WMM - Wallpaper Multi-Monitor Manager

generic.py - Módulo de plataforma genérico (fallback).
==========================================================
Se usa cuando no se detecta un SO específico (Linux, Windows, macOS).
Proporciona implementaciones vacías o seguras de todas las funciones
que el motor y el logger esperan de una plataforma.
"""

def normalize_platform(raw_platform):
    """Devuelve el nombre canónico del SO tal cual (sin normalizar)."""
    return raw_platform

def normalize_desktop(desktop):
    """Devuelve el nombre del escritorio tal cual (sin normalizar)."""
    return desktop

def detect_desktop():
    """Detecta el escritorio. En genérico, retorna 'unknown'."""
    return 'unknown'

def get_system_paths():
    """Retorna rutas vacías (la plataforma real las completará)."""
    return {
        'data_base': '',
        'cache_base': '',
        'locale_dir': '',
        'cache_dir': '',
    }

def lock_file(f):
    """Bloqueo de archivo no disponible en plataforma genérica."""
    pass

def unlock_file(f):
    """Desbloqueo de archivo no disponible en plataforma genérica."""
    pass

def open_file(path):
    """Apertura de archivo no disponible en plataforma genérica."""
    pass

def send_notification(title, message, level="info"):
    """Notificaciones no disponibles en plataforma genérica."""
    pass
