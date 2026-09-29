#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

"""
WMM - Wallpaper Multi-Monitor Manager

about.py - About WMM Viewer
===========================
Ventana común "Acerca de WMM" para los frontends que no disponen
de una presentación About adecuada proporcionada por el escritorio.

Los datos se obtienen exclusivamente de data/about.json.
"""

# ==========================================================
# IMPORTS DE LIBRERÍA ESTÁNDAR
# ==========================================================
import html
import json
import os
import sys

# ==========================================================
# CONFIGURACIÓN DEL PATH DEL PROYECTO
# ==========================================================
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

# ==========================================================
# IMPORTS DE TERCEROS (GTK)
# ==========================================================
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gio', '2.0')
from gi.repository import Gtk, Gio, GLib

# ==========================================================
# IMPORTS DE MÓDULOS DEL PROYECTO
# ==========================================================
from wmm_platform.core import PlatformManager
from i18n import _, initialize

platform = PlatformManager()
if hasattr(platform, "set_process_name"):
    platform.set_process_name("WMM About")
initialize(platform)

ABOUT_PATH = os.path.join(platform.data_dir, "about.json")

# ==========================================================
# DATOS DE ABOUT
# ==========================================================
def _load_about_data():
    """Carga los datos comunes de WMM desde data/about.json."""
    with open(ABOUT_PATH, "r", encoding="utf-8") as file:
        data = json.load(file)

    required = (
        "name",
        "short_name",
        "version",
        "author",
        "copyright_start_year",
        "copyright_release_year",
        "license",
        "links",
    )

    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"Missing required About fields: {', '.join(missing)}")

    return data

def _format_copyright(data):
    """Construye el copyright sin inventar un año para versiones aún no publicadas."""
    start_year = int(data["copyright_start_year"])
    release_year = data["copyright_release_year"]
    author = str(data["author"])

    if release_year is None:
        years = str(start_year)
    else:
        release_year = int(release_year)
        years = f"{start_year}\u2013{release_year}" if release_year > start_year else str(start_year)

    return f"Copyright \u00a9 {years} {author}"

# ==========================================================
# VENTANA ABOUT
# ==========================================================
class AboutWindow(Gtk.ApplicationWindow):
    """Ventana GTK3 no modal con la información común de WMM."""

    def __init__(self, app, data):
        super().__init__(application=app, title=_("About") + " " + str(data["short_name"]))
        self.set_resizable(False)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_keep_above(True)
        self.set_icon_name("video-display")

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        content.set_border_width(22)
        self.add(content)

        # ----------------------------------------------------------
        # IDENTIDAD DE LA APLICACIÓN
        # ----------------------------------------------------------
        icon = Gtk.Image.new_from_icon_name("video-display", Gtk.IconSize.DIALOG)
        icon.set_halign(Gtk.Align.CENTER)
        content.pack_start(icon, False, False, 0)

        short_name = Gtk.Label()
        short_name.set_markup(
            f'<span size="x-large" weight="bold">{GLib.markup_escape_text(str(data["short_name"]))}</span>')
        short_name.set_halign(Gtk.Align.CENTER)
        content.pack_start(short_name, False, False, 0)

        full_name = Gtk.Label(label=str(data["name"]))
        full_name.set_halign(Gtk.Align.CENTER)
        content.pack_start(full_name, False, False, 0)

        version = Gtk.Label(label=_("Version") + ": " + str(data["version"]))
        version.set_halign(Gtk.Align.CENTER)
        content.pack_start(version, False, False, 0)

        # ----------------------------------------------------------
        # INFORMACIÓN LEGAL
        # ----------------------------------------------------------
        legal_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        legal_box.set_margin_top(8)
        legal_box.set_halign(Gtk.Align.CENTER)

        copyright_label = Gtk.Label(label=_format_copyright(data))
        copyright_label.set_halign(Gtk.Align.CENTER)
        legal_box.pack_start(copyright_label, False, False, 0)

        license_name = str(data["license"]["name"])
        license_label = Gtk.Label(label=_("License") + ": " + license_name)
        license_label.set_halign(Gtk.Align.CENTER)
        legal_box.pack_start(license_label, False, False, 0)

        content.pack_start(legal_box, False, False, 0)

        # ----------------------------------------------------------
        # ENLACES OFICIALES
        # ----------------------------------------------------------
        links = data["links"]
        link_items = (
            ("GitHub", links["github"]),
            (_("Changelog"), f'wmm-doc:{links["changelog"]}'),
            (_("Help"), f'wmm-doc:{links["help"]}'),
            (_("License"), f'wmm-doc:{data["license"]["document"]}'),
        )

        links_markup = "   ".join(
            f'<a href="{html.escape(str(url), quote=True)}">{GLib.markup_escape_text(str(label))}</a>'
            for label, url in link_items)

        links_label = Gtk.Label()
        links_label.set_markup(links_markup)
        links_label.set_halign(Gtk.Align.CENTER)
        links_label.set_margin_top(10)
        links_label.set_track_visited_links(False)
        links_label.connect("activate-link", self._on_activate_link)
        content.pack_start(links_label, False, False, 0)

        self.show_all()

    def _on_activate_link(self, label, uri):
        """Abre documentos WMM en el visor interno y deja las URLs al sistema."""
        if not uri.startswith("wmm-doc:"):
            return False

        document = uri[len("wmm-doc:"):]
        viewer = os.path.join(os.path.dirname(__file__), "docs_viewer.py")
        GLib.spawn_async([sys.executable, viewer, document])
        return True

# ==========================================================
# APLICACIÓN
# ==========================================================
class AboutApplication(Gtk.Application):
    """Aplicación GTK de instancia única para la ventana About de WMM."""

    def __init__(self):
        super().__init__(application_id="org.maki.wmm.About")
        self._engine_seen = False
        self._engine_watch_id = Gio.bus_watch_name(
            Gio.BusType.SESSION,
            "org.maki.wmm",
            Gio.BusNameWatcherFlags.NONE,
            self._on_engine_appeared,
            self._on_engine_vanished,
        )

    def _on_engine_appeared(self, connection, name, owner):
        """Marca que el engine WMM está presente en la sesión."""
        self._engine_seen = True

    def _on_engine_vanished(self, connection, name):
        """Cierra About cuando desaparece el engine al reiniciar o salir de WMM."""
        if not self._engine_seen:
            return

        window = self.props.active_window
        if window is not None:
            window.destroy()
        else:
            self.quit()

    def do_activate(self):
        window = self.props.active_window

        if window is None:
            try:
                data = _load_about_data()
            except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
                print(f"[WMM ABOUT] Error loading {ABOUT_PATH}: {error}", file=sys.stderr)
                self.quit()
                return

            window = AboutWindow(self, data)
            window.connect("destroy", lambda *_: self.quit())
            self.add_window(window)

        window.present()

    def do_shutdown(self):
        if self._engine_watch_id:
            Gio.bus_unwatch_name(self._engine_watch_id)
            self._engine_watch_id = 0
        Gtk.Application.do_shutdown(self)


if __name__ == "__main__":
    app = AboutApplication()
    raise SystemExit(app.run(sys.argv))
