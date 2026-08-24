#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

"""
WMM - Wallpaper Multi-Monitor Manager

file_utils.py - Utilidades de bloqueo de archivos para escritura atómica.
==========================================================
Independiente del resto de WMM. Puede usarse desde cualquier módulo.
"""
import fcntl


def lock_file(f):
    """Bloquea el archivo f (debe estar abierto en modo escritura)."""
    fcntl.flock(f, fcntl.LOCK_EX)


def unlock_file(f):
    """Desbloquea el archivo f."""
    fcntl.flock(f, fcntl.LOCK_UN)
