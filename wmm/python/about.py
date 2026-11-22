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
from gi.repository import Gtk, Gio, GLib, Gdk, GdkPixbuf

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
# HISTORIA DE WMM
# ==========================================================
def _read_about_history():
    """Lee únicamente la historia correspondiente al idioma de sesión."""
    path = os.path.join(_PROJECT_ROOT, "licenses", "WMM", "WMM-a-little-history")

    try:
        with open(path, "r", encoding="utf-8-sig") as document:
            lines = document.read().splitlines(keepends=True)
    except (OSError, UnicodeError) as error:
        print(f"[WMM ABOUT] Error reading history: {error}", file=sys.stderr)
        return None

    # Los marcadores delimitan el texto; no forman parte de la vista.
    markers = ("[English]", "[Català]", "[Castellano]")
    positions = {
        line.rstrip("\r\n"): index
        for index, line in enumerate(lines)
        if line.rstrip("\r\n") in markers
    }

    if (len(positions) != 3 or
            not positions[markers[0]] < positions[markers[1]] < positions[markers[2]]):
        print("[WMM ABOUT] Invalid history language markers", file=sys.stderr)
        return None

    # Mismo criterio de idioma utilizado por Online y Docs Viewer.
    raw = (os.environ.get("LANGUAGE") or os.environ.get("LC_ALL")
           or os.environ.get("LC_MESSAGES") or os.environ.get("LANG") or "en")
    language = raw.split(":", 1)[0].split(".", 1)[0].replace("-", "_").split("_", 1)[0].lower()
    marker = {"ca": markers[1], "es": markers[2]}.get(language, markers[0])

    start = positions[marker] + 1
    end = next((positions[m] for m in markers
                if positions[m] > positions[marker]), len(lines))

    return "".join(lines[start:end]).strip() or None

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

        # About e historia comparten ventana y geometría.
        # La transición pertenece a GTK, sin animaciones manuales.
        self._history_text = _read_about_history()

        self._view_stack = Gtk.Stack()
        self._view_stack.set_hhomogeneous(True)
        self._view_stack.set_vhomogeneous(True)
        self._view_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._view_stack.set_transition_duration(2400)
        self.add(self._view_stack)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        content.set_border_width(22)
        self._view_stack.add_named(content, "about")

        # ----------------------------------------------------------
        # IDENTIDAD DE LA APLICACIÓN
        # ----------------------------------------------------------
        # Identidad gráfica de WMM: PNG local con respaldo del tema GTK.
        icon_path = os.path.join(platform.app_dir, "icon.png")

        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(icon_path, 100, -1, True)
            self.set_icon(pixbuf)
            icon = Gtk.Image.new_from_pixbuf(pixbuf)
        except (GLib.Error, OSError):
            self.set_icon_name("video-display")
            icon = Gtk.Image.new_from_icon_name("video-display", Gtk.IconSize.DIALOG)

        icon.set_halign(Gtk.Align.CENTER)

        if self._history_text:
            icon_button = Gtk.Button()
            icon_button.set_relief(Gtk.ReliefStyle.NONE)
            icon_button.get_style_context().add_class("flat")
            icon_button.set_halign(Gtk.Align.CENTER)
            icon_button.add(icon)
            icon_button.connect("clicked", self._on_show_history)
            content.pack_start(icon_button, False, False, 0)
        else:
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
            (_("License"), 'wmm-doc:licenses'),
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

        # ----------------------------------------------------------
        # HISTORIA OCULTA DE WMM
        # ----------------------------------------------------------
        if self._history_text:
            story = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            story.set_border_width(10)

            back = Gtk.Button.new_from_icon_name(
                "go-previous-symbolic", Gtk.IconSize.BUTTON)
            back.set_relief(Gtk.ReliefStyle.NONE)
            back.set_halign(Gtk.Align.START)
            back.set_tooltip_text(_("About"))

            # El CSS común elimina las dimensiones mínimas del tema GTK.
            back.get_style_context().add_class("wmm-history-back")

            back.connect("clicked", self._on_show_about)
            story.pack_start(back, False, False, 0)

            # El relato no modifica la geometría de About.
            # Sólo el texto dispone de desplazamiento vertical.
            scrolled = Gtk.ScrolledWindow()
            scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scrolled.set_hexpand(True)
            scrolled.set_vexpand(True)

            text = Gtk.Label(label=self._history_text)
            text.set_line_wrap(True)
            text.set_max_width_chars(48)
            text.set_xalign(0.0)
            text.set_yalign(0.0)
            text.set_selectable(True)

            scrolled.add_with_viewport(text)
            story.pack_start(scrolled, True, True, 0)

            self._view_stack.add_named(story, "history")
            self.connect("key-press-event", self._on_history_key_press)

        self._view_stack.set_visible_child_name("about")
        self.show_all()

    def _on_show_history(self, _button):
        """Descubre el relato sin abrir otra ventana."""
        self._view_stack.set_visible_child_name("history")

    def _on_show_about(self, _button=None):
        """Recupera la presentación original de About."""
        self._view_stack.set_visible_child_name("about")

    def _on_history_key_press(self, _window, event):
        """Escape regresa a About sin cerrar la aplicación."""
        if (event.keyval == Gdk.KEY_Escape and
                self._view_stack.get_visible_child_name() == "history"):
            self._on_show_about()
            return True
        return False

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
        if hasattr(platform, "prepare_gtk_color_scheme"):
            platform.prepare_gtk_color_scheme()

        window = self.props.active_window

        if window is None:

            # ----------------------------------------------------------
            # CSS COMPARTIDO DE WMM
            # ----------------------------------------------------------
            # About es un proceso independiente del Panel.
            # Cargar el recurso común una sola vez, al crear la ventana.
            css_path = os.path.join(
                platform.app_dir, "wmm_platform", "shell", "common", "wmm.css")

            if os.path.isfile(css_path):
                css_provider = Gtk.CssProvider()
                css_provider.load_from_path(css_path)
                Gtk.StyleContext.add_provider_for_screen(
                    Gdk.Screen.get_default(), css_provider,
                    Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            else:
                print(f"[WMM ABOUT] CSS compartido no disponible: {css_path}",
                    file=sys.stderr)

            try:
                data = _load_about_data()
            except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
                print(f"[WMM ABOUT] Error loading {ABOUT_PATH}: {error}", file=sys.stderr)
                self.quit()
                return

            window = AboutWindow(self, data)
            window.connect("destroy", lambda *_: self.quit())
            self.add_window(window)

        if hasattr(platform, "present_window"):
            platform.present_window(window)
        else:
            window.present()

    def do_shutdown(self):
        if self._engine_watch_id:
            Gio.bus_unwatch_name(self._engine_watch_id)
            self._engine_watch_id = 0
        Gtk.Application.do_shutdown(self)


if __name__ == "__main__":
    app = AboutApplication()
    raise SystemExit(app.run(sys.argv))
