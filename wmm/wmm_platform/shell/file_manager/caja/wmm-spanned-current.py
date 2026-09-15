#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

"""
WMM - Wallpaper Multi-Monitor Manager

wmm-spanned-current.py - Caja Desktop Menu Provider
===================================================
Añade al menú contextual del escritorio de Caja la acción
"Span Current Image".

La extensión obtiene la posición absoluta del evento que activa
la acción y delega en el engine común de WMM la resolución del
monitor y la composición Spanned temporal.
"""

import gettext
import json
import os
import subprocess

import gi

gi.require_version("Caja", "2.0")
gi.require_version("Gtk", "3.0")

from gi.repository import Caja, GObject, Gtk


# ==========================================================
# RUTAS DE WMM
# ==========================================================
DATA_BASE = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
APP_DIR = "@APP_DIR@"
PYTHON3 = "@PYTHON3@"
SEND_COMMAND = os.path.join(APP_DIR, "python", "send_command.py")


# ==========================================================
# TRADUCCIONES
# ==========================================================
APP_DOMAIN = "wmm@maki"
LOCALE_DIR = os.path.join(DATA_BASE, "locale")

gettext.bindtextdomain(APP_DOMAIN, LOCALE_DIR)

def _(text):
    return gettext.dgettext(APP_DOMAIN, text)


# ==========================================================
# MENÚ CONTEXTUAL DEL ESCRITORIO
# ==========================================================
class WMMCajaExtension(Caja.MenuProvider, GObject.GObject):

    def __init__(self):
        pass

    def _on_span_activate(self, _menu_item):
        """Envía al engine la posición absoluta desde la que se activa la acción."""
        event = Gtk.get_current_event()

        if event is None:
            return

        has_coords, x_root, y_root = event.get_root_coords()

        if not has_coords:
            return

        if not os.path.isfile(SEND_COMMAND):
            print(f"WMM Caja: send_command.py not found: {SEND_COMMAND}")
            return

        command = json.dumps({
            "action": "shell_spanned_current",
            "x": x_root,
            "y": y_root,
        })

        try:
            subprocess.Popen([PYTHON3, SEND_COMMAND, command])
        except OSError as error:
            print(f"WMM Caja: unable to execute action: {error}")

    def get_background_items(self, window, _current_folder):
        """Muestra la acción únicamente en el escritorio gestionado por Caja."""
        if type(window).__name__ != "CajaDesktopWindow":
            return []

        item = Caja.MenuItem(
            name="WMMCaja::SpanCurrentImage",
            label="WMM: " + _("Span Current Image"),
            tip=_("Span the image currently shown on this monitor across all monitors"),
            icon="view-fullscreen-symbolic",
        )
        item.connect("activate", self._on_span_activate)

        return [item]
