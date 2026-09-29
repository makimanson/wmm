#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

"""
WMM - Wallpaper Multi-Monitor Manager

wmm-xfce-desktop.py - XFCE Desktop Menu Provider
===================================================
Añade al menú contextual del escritorio de XFCE la acción
"Span Current Image" mediante Thunarx.

La extensión obtiene el XID efímero de la XfceDesktop desde la
que se activa la acción y delega en el engine común de WMM la
resolución del monitor y la composición Spanned temporal.
"""

import gettext
import json
import os
import subprocess
import gi

gi.require_version("Thunarx", "3.0")

from gi.repository import GObject, Thunarx

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
class WMMThunarExtension(GObject.GObject, Thunarx.MenuProvider):

    def __init__(self):
        pass

    def get_folder_menu_items(self, window, _folder):
        """Muestra WMM Manager únicamente en el escritorio gestionado por xfdesktop."""
        # xfdesktop entrega una XfceDesktop; Thunar entrega otro tipo de ventana.
        if window.__gtype__.name != "XfceDesktop":
            return []

        manager_item = Thunarx.MenuItem(
            name="WMMThunar::Manager",
            label="WMM Manager",
            tooltip="Wallpaper Multi-Monitor Manager",
            icon="video-display",)

        submenu = Thunarx.Menu()
        manager_item.set_menu(submenu)

        span_item = Thunarx.MenuItem(
            name="WMMThunar::SpanCurrentImage",
            label=_("Span Current Image"),
            tooltip=_("Span the image currently shown on this monitor across all monitors"),
            icon="view-fullscreen",)
        span_item.connect("activate", self._on_activate, window)
        submenu.append_item(span_item)

        favorite_item = Thunarx.MenuItem(
            name="WMMThunar::AddCurrentToFavorites",
            label=_("Add to favorites"),
            tooltip=_("Add the image currently shown on this monitor to favorites"),
            icon="list-add",)
        favorite_item.connect(
            "activate", self._on_favorite_activate, window)
        submenu.append_item(favorite_item)

        return [manager_item]

    def _on_favorite_activate(self, _item, window):
        """Solicita añadir a favoritos la imagen activa del monitor seleccionado."""
        xid = window.get_window().get_xid()

        if not os.path.isfile(SEND_COMMAND):
            print(f"WMM XFCE Desktop: send_command.py not found: {SEND_COMMAND}")
            return

        command = json.dumps({ "action": "shell_add_favorite_current", "xid": xid, })

        try:
            subprocess.Popen([PYTHON3, SEND_COMMAND, command])
        except OSError as error:
            print(f"WMM XFCE Desktop: unable to execute action: {error}")

    def _on_activate(self, _item, window):
        """Extiende la imagen activa del monitor desde el que se abrió el menú."""
        # Cada monitor de xfdesktop dispone de su propia XfceDesktop/X11Window.
        # El XID sólo es válido durante esa sesión y por ello se obtiene aquí,
        # en el momento del clic, sin almacenarlo ni intentar resolver el monitor
        # dentro de la extensión. Esa responsabilidad permanece en el engine.
        xid = window.get_window().get_xid()

        if not os.path.isfile(SEND_COMMAND):
            print(f"WMM XFCE Desktop: send_command.py not found: {SEND_COMMAND}")
            return

        command = json.dumps({ "action": "shell_spanned_current", "xid": xid, })

        # Se lanza fuera de xfdesktop para no bloquear su loop GTK. El comando
        # entra por el mismo canal externo que las demás integraciones de WMM.
        try:
            subprocess.Popen([PYTHON3, SEND_COMMAND, command])
        except OSError as error:
            print(f"WMM XFCE Desktop: unable to execute action: {error}")
