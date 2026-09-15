#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

"""
WMM - Wallpaper Multi-Monitor Manager

wmm-nautilus.py - Nautilus Menu Provider
========================================
Integración nativa de WMM con el menú contextual de Nautilus.
"""

import gettext
import json
import os
import shutil

import gi

for version in ("4.1", "4.0"):
    try:
        gi.require_version("Nautilus", version)
        break
    except ValueError:
        continue
else:
    raise RuntimeError("Nautilus GI namespace not available")

from gi.repository import Gio, GLib, GObject, Nautilus


# ==========================================================
# RUTAS DE WMM
# ==========================================================
DATA_BASE = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
APP_DIR = os.path.join(DATA_BASE, "gnome-shell", "extensions", "wmm@maki")
SEND_COMMAND = os.path.join(APP_DIR, "python", "send_command.py")
PYTHON3 = shutil.which("python3") or "/usr/bin/python3"


# ==========================================================
# TRADUCCIONES
# ==========================================================
APP_DOMAIN = "wmm@maki"
LOCALE_DIR = os.path.join(DATA_BASE, "locale")

gettext.bindtextdomain(APP_DOMAIN, LOCALE_DIR)

def _(text):
    return gettext.dgettext(APP_DOMAIN, text)


# ==========================================================
# MENÚ CONTEXTUAL
# ==========================================================
class WMMNautilusExtension(GObject.GObject, Nautilus.MenuProvider):

    def _run_action(self, _menu_item, action, image_path):
        """Envía a WMM la acción seleccionada para la imagen."""
        if not os.path.isfile(SEND_COMMAND):
            print(f"WMM Nautilus: send_command.py not found: {SEND_COMMAND}")
            return

        command = json.dumps({
            "action": action,
            "image_path": image_path,
        })

        try:
            Gio.Subprocess.new(
                [PYTHON3, SEND_COMMAND, command],
                Gio.SubprocessFlags.NONE,
            )
        except GLib.Error as error:
            print(f"WMM Nautilus: unable to execute action: {error}")

    def get_file_items(self, files):
        """Muestra las acciones de WMM únicamente para una imagen local."""
        if len(files) != 1:
            return []

        file_info = files[0]

        if file_info.is_directory():
            return []

        if file_info.get_uri_scheme() != "file":
            return []

        mime_type = file_info.get_mime_type() or ""
        if not mime_type.startswith("image/"):
            return []

        location = file_info.get_location()
        image_path = location.get_path() if location else None

        if not image_path:
            return []

        # ----------------------------------------------------------
        # SUBMENÚ WMM MANAGER
        # ----------------------------------------------------------
        submenu = Nautilus.Menu()

        favorite_item = Nautilus.MenuItem(
            name="WMMNautilus::AddToFavorites",
            label=_("Add to favorites"),
        )
        favorite_item.connect(
            "activate",
            self._run_action,
            "shell_add_favorite",
            image_path,
        )
        submenu.append_item(favorite_item)

        send_item = Nautilus.MenuItem(
            name="WMMNautilus::SendToMonitor",
            label=_("Send to Monitor"),
        )
        send_item.connect(
            "activate",
            self._run_action,
            "shell_send_to_monitor",
            image_path,
        )
        submenu.append_item(send_item)

        span_item = Nautilus.MenuItem(
            name="WMMNautilus::SpanImage",
            label=_("Span image across all active screens"),
        )
        span_item.connect(
            "activate",
            self._run_action,
            "shell_spanned_image",
            image_path,
        )
        submenu.append_item(span_item)

        wmm_item = Nautilus.MenuItem(
            name="WMMNautilus::Menu",
            label="WMM Manager",
        )
        wmm_item.set_submenu(submenu)

        return [wmm_item]
