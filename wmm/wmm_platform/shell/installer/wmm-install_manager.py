#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

"""
WMM - Wallpaper Multi-Monitor Manager

wmm-install_manager.py - WMM Install Manager
============================================
Frontend GTK3 para las operaciones de mantenimiento de WMM.

Responsabilidades:
- mostrar la versión instalada y el entorno de escritorio/sesión;
- consultar la última release estable publicada en GitHub;
- presentar progreso y resultados mediante un terminal VTE embebido;
- orquestar Upgrade, Reinstall y Uninstall;
- delegar siempre la instalación/desinstalación real en los scripts autoritativos.

El frontend no replica la lógica de instalación. Prepara el paquete adecuado,
lanza el script correspondiente y refleja su resultado en la interfaz.

Durante el desarrollo de Upgrade existe una pausa temporal de prueba que
permite sustituir el árbol descargado antes de ejecutar el instalador.
"""

import json
import os
import sys
import tempfile
import zipfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Vte", "2.91")
from gi.repository import Gtk, GLib, Vte, Pango

# ==========================================================
# CONFIGURACIÓN DEL PATH DEL PROYECTO
# ==========================================================
_PROJECT_ROOT = os.path.dirname( os.path.dirname( os.path.dirname( os.path.dirname(os.path.abspath(__file__)) ) ) )
_PYTHON_DIR = os.path.join(_PROJECT_ROOT, "python")

sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, _PYTHON_DIR)


# ==========================================================
# IMPORTS DE MÓDULOS DEL PROYECTO
# ==========================================================
from wmm_platform.core import PlatformManager
from i18n import _, initialize


platform = PlatformManager()

if hasattr(platform, "set_process_name"):
    platform.set_process_name("WMM Installer")

initialize(platform)


# ==========================================================
# RUTAS
# ==========================================================
APP_DIR = Path(__file__).resolve().parents[3]
ABOUT_PATH = APP_DIR / "data" / "about.json"
UNINSTALLER_PATH = Path(__file__).resolve().with_name("wmm-uninstall.sh")
REPAIR_ARCHIVE_PATH = Path(__file__).resolve().with_name("wmm-repair.zip")
GITHUB_LATEST_RELEASE = "https://api.github.com/repos/makimanson/wmm/releases/latest"
# ==========================================================
# ESTADO BÁSICO
# ==========================================================
def load_installed_version():
    """Obtiene la versión instalada desde data/about.json."""
    try:
        with ABOUT_PATH.open("r", encoding="utf-8") as file:
            data = json.load(file)

        version = str(data.get("version", "")).strip()
        return version or "Unknown"

    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return "Unknown"

def parse_version(version):
    """Convierte una versión X.Y.Z / vX.Y.Z en una tupla comparable."""
    parts = str(version).strip().lstrip("v").split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise ValueError(f"Invalid version: {version}")
    return tuple(int(part) for part in parts)


def load_latest_release():
    """Obtiene la última release estable publicada en GitHub."""
    request = urllib.request.Request(
        GITHUB_LATEST_RELEASE,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "WMM-Install-Manager",
        })

    with urllib.request.urlopen(request, timeout=10) as response:
        data = json.load(response)

    tag = str(data.get("tag_name", "")).strip()
    version = tag.lstrip("v")
    parse_version(version)

    return {
        "version": version,
        "tag": tag,
    }

def detect_desktop():
    """Devuelve un nombre legible para el escritorio actual."""
    raw = ( os.environ.get("XDG_CURRENT_DESKTOP") or os.environ.get("DESKTOP_SESSION") or "Unknown" )
    value = raw.lower()

    if "cinnamon" in value:
        return "Cinnamon"

    if "gnome" in value or "ubuntu" in value:
        return "GNOME"

    if "kde" in value or "plasma" in value:
        return "KDE Plasma"

    if "mate" in value:
        return "MATE"

    return raw


def detect_session():
    """Devuelve el motor gráfico de la sesión actual."""
    if os.environ.get("WAYLAND_DISPLAY"):
        return "Wayland"

    session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()

    if session_type == "wayland":
        return "Wayland"

    if session_type == "x11":
        return "X11"

    return "Unknown"


# ==========================================================
# VENTANA PRINCIPAL
# ==========================================================
class InstallManagerWindow(Gtk.ApplicationWindow):
    def __init__(self, application):
        super().__init__(application=application)
        self.set_position(Gtk.WindowPosition.CENTER)

        self.set_title("WMM Install Manager")
        self.set_icon_name("video-display")
        self.set_resizable(False)
        self.set_default_size(605, 493)

        self.set_border_width(24)
        self._operation_running = False
        self._current_operation = None

        self.connect("delete-event", self._on_delete_event)
        content = Gtk.Box( orientation=Gtk.Orientation.VERTICAL, spacing=16 )
        self.add(content)

        # --------------------------------------------------
        # CABECERA
        # --------------------------------------------------
        header = Gtk.Overlay()
        header.set_hexpand(True)

        header_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        header_text.set_halign(Gtk.Align.CENTER)
        header_text.set_valign(Gtk.Align.CENTER)

        title_text = _("Install Manager")

        title = Gtk.Label()
        title.set_markup("<span size='x-large'><b>WMM " + GLib.markup_escape_text(title_text) + "</b></span>")
        title.set_halign(Gtk.Align.CENTER)
        header_text.pack_start(title, False, False, 0)

        subtitle = Gtk.Label(label="Wallpaper Multi-Monitor Manager")
        subtitle.set_halign(Gtk.Align.CENTER)
        header_text.pack_start(subtitle, False, False, 0)

        header.add(header_text)

        icon = Gtk.Image.new_from_icon_name("video-display", Gtk.IconSize.DIALOG)
        icon.set_pixel_size(50)
        icon.set_halign(Gtk.Align.START)
        icon.set_valign(Gtk.Align.CENTER)
        icon.set_margin_start(48)

        header.add_overlay(icon)

        content.pack_start(header, False, False, 0)

        separator = Gtk.Separator( orientation=Gtk.Orientation.HORIZONTAL )
        content.pack_start(separator, False, False, 2)

        # --------------------------------------------------
        # ESTADO ACTUAL
        # --------------------------------------------------
        self.installed_version = load_installed_version()
        self.latest_release = None

        info_grid = Gtk.Grid()
        info_grid.set_row_spacing(8)
        info_grid.set_column_spacing(18)
        info_grid.set_halign(Gtk.Align.CENTER)

        self.version_value_label = self._add_info_row(info_grid, 0, _("Installed version") + ":", self.installed_version)
        self._add_info_row(info_grid, 1, _("Desktop") + ":", detect_desktop())
        self._add_info_row(info_grid, 2, _("Session") + ":", detect_session())

        content.pack_start(info_grid, False, False, 0)

        # --------------------------------------------------
        # ACCIONES
        # --------------------------------------------------
        actions = Gtk.Box( orientation=Gtk.Orientation.HORIZONTAL, spacing=8 )
        actions.set_homogeneous(True)

        self.upgrade_button = Gtk.Button(label=_("Upgrade"))
        self.upgrade_button.set_sensitive(False)
        self.upgrade_button.connect("clicked", self._on_upgrade_clicked)
        actions.pack_start(self.upgrade_button, True, True, 0)

        self.repair_button = Gtk.Button(label=_("Reinstall"))
        self.repair_button.set_sensitive(True)
        self.repair_button.connect("clicked", self._on_reinstall_clicked)
        actions.pack_start(self.repair_button, True, True, 0)

        self.uninstall_button = Gtk.Button(label=_("Uninstall"))
        self.uninstall_button.set_sensitive(True)
        self.uninstall_button.connect("clicked", self._on_uninstall_clicked)
        actions.pack_start(self.uninstall_button, True, True, 0)

        content.pack_start(actions, False, False, 0)

        # --------------------------------------------------
        # ÁREA DINÁMICA
        # Estado normal / terminal de operación
        # --------------------------------------------------
        self.dynamic_stack = Gtk.Stack()
        self.dynamic_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.dynamic_stack.set_transition_duration(150)
        self.dynamic_stack.set_homogeneous(True)
        self.dynamic_stack.set_hexpand(True)
        self.dynamic_stack.set_vexpand(True)

        # Página de estado / resultados
        status_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        status_box.set_border_width(24)
        status_box.set_valign(Gtk.Align.CENTER)

        self.status_icon = Gtk.Image()
        self.status_icon.set_no_show_all(True)
        status_box.pack_start(self.status_icon, False, False, 0)

        self.status_spinner = Gtk.Spinner()
        self.status_spinner.set_no_show_all(True)
        status_box.pack_start(self.status_spinner, False, False, 0)

        self.status_title = Gtk.Label()
        status_title_text = _("Maintenance status")

        self.status_title.set_markup("<span size='large'><b>" + GLib.markup_escape_text(status_title_text) + "</b></span>")
        self.status_title.set_justify(Gtk.Justification.CENTER)
        status_box.pack_start(self.status_title, False, False, 0)

        self.status_label = Gtk.Label()
        self.status_label.set_justify(Gtk.Justification.CENTER)
        self.status_label.set_line_wrap(True)
        self.status_label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.status_label.set_max_width_chars(58)
        self.status_label.set_selectable(True)
        status_box.pack_start(self.status_label, False, False, 0)

        self.dynamic_stack.add_named(status_box, "status")

        self._set_status("dialog-information-symbolic", _("Maintenance status"), _("WMM is ready for maintenance operations."))

        # Terminal embebido
        terminal_frame = Gtk.Frame()
        terminal_frame.set_shadow_type(Gtk.ShadowType.IN)

        self.terminal = Vte.Terminal()
        self.terminal.set_scrollback_lines(5000)
        self.terminal.set_size(50, 8)
        self.terminal.set_hexpand(True)
        self.terminal.set_vexpand(True)
        self.terminal.connect("child-exited", self._on_terminal_child_exited)
        self.terminal.connect("button-press-event", self._on_terminal_button_press)

        terminal_scrolled = Gtk.ScrolledWindow()
        terminal_scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.ALWAYS)
        terminal_scrolled.add(self.terminal)

        terminal_frame.add(terminal_scrolled)

        self.dynamic_stack.add_named(terminal_frame, "terminal")

        # Arranca mostrando información, no el terminal.
        self.dynamic_stack.set_visible_child_name("status")

        content.pack_start(self.dynamic_stack, True, True, 0)

        # --------------------------------------------------
        # BARRA INFERIOR
        # --------------------------------------------------
        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        self.details_button = Gtk.Button(label=_("Show details"))
        self.details_button.connect("clicked", self._on_toggle_details)

        footer.pack_start( self.details_button, False, False, 0 )

        self.close_button = Gtk.Button(label=_("Close"))
        self.close_button.connect( "clicked", lambda *_: application.quit() )
        footer.pack_end( self.close_button, False, False, 0 )

        content.pack_end( footer, False, False, 0 )
        self.show_all()
        threading.Thread(target=self._check_for_updates, daemon=True).start()

    # ==========================================================
    # ACCIÓN: UPGRADE
    # ==========================================================
    # Detección remota, preparación del paquete y ejecución del instalador de actualización.

    def _check_for_updates(self):
        """Consulta GitHub en segundo plano para no bloquear el bucle principal de GTK."""
        try:
            release = load_latest_release()
            GLib.idle_add(self._apply_update_status, release, None)
        except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError) as error:
            GLib.idle_add(self._apply_update_status, None, error)

    def _apply_update_status(self, release, error):
        """Aplica a la interfaz el resultado de la consulta y habilita Upgrade cuando corresponde."""
        if self._operation_running:
            if error is None:
                self.latest_release = release
            return False
        if error is not None:
            self.upgrade_button.set_sensitive(False)
            self._set_status("dialog-information-symbolic",
                _("Update check unavailable"),
                _("WMM could not check GitHub for updates."))
            return False

        self.latest_release = release
        installed = parse_version(self.installed_version)
        available = parse_version(release["version"])

        if installed < available:
            self.upgrade_button.set_sensitive(True)
            self._set_status("software-update-available-symbolic",
                _("Update available"),
                _("WMM {} is available.").format(release["version"]) + " " + _("Installed version") + ": " + str(self.installed_version) + ".")
        elif installed == available:
            self.upgrade_button.set_sensitive(False)
            self._set_status("emblem-ok-symbolic",
                _("WMM is up to date"),
                _("You are running the latest published version:") + " " + str(self.installed_version) + ".")
        else:
            self.upgrade_button.set_sensitive(False)
            self._set_status("dialog-information-symbolic",
                _("Development version"),
                _("Installed version") + ": " + str(self.installed_version) + "\n" +
                _("Latest published version") + ": " + str(release["version"]))

        return False

    def _on_upgrade_clicked(self, _button):
        """Confirma con el usuario el Upgrade detectado antes de iniciar su preparación."""
        if not self.latest_release:
            return

        available = self.latest_release["version"]

        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            destroy_with_parent=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.CANCEL,
            text=_("A new version of WMM is available."))

        dialog.set_title(_("Upgrade WMM"))
        installed_version_text = _("Installed version")
        available_version_text = _("Available version")
        continue_text = _("Do you want to continue?")

        dialog.format_secondary_text("{}: {}\n{}: {}\n\n{}".format(
                installed_version_text,
                self.installed_version,
                available_version_text,
                available,
                continue_text))

        dialog.add_button(_("Upgrade"), Gtk.ResponseType.ACCEPT)
        dialog.set_default_response(Gtk.ResponseType.CANCEL)

        response = dialog.run()
        dialog.destroy()

        if response == Gtk.ResponseType.ACCEPT:
            self._start_upgrade()

    def _start_upgrade(self):
        """Prepara la interfaz y arranca en segundo plano la preparación del Upgrade."""
        self._operation_running = True
        self._current_operation = "upgrade"

        self.upgrade_button.set_sensitive(False)
        self.repair_button.set_sensitive(False)
        self.uninstall_button.set_sensitive(False)
        self.close_button.set_sensitive(False)

        self._set_status(None,
            _("Preparing WMM upgrade"),
            _("The update package is being downloaded and prepared."), spinning=True)

        self.terminal.reset(True, True)
        self.dynamic_stack.set_visible_child_name("terminal")
        self.details_button.set_label(_("Hide details"))

        threading.Thread(target=self._prepare_upgrade, daemon=True).start()

    def _prepare_upgrade(self):
        """Descarga y valida el paquete remoto antes de iniciar la pausa temporal de prueba."""
        try:
            # El temporal debe sobrevivir hasta que termine por completo la operación.
            self._operation_tempdir = tempfile.TemporaryDirectory(prefix="wmm-upgrade-")
            temp_root = Path(self._operation_tempdir.name)

            # La release detectada previamente es la autoridad de versión remota.
            release = self.latest_release
            expected_version = release["version"]
            tag = release["tag"]
            download_url = f"https://github.com/makimanson/wmm/archive/refs/tags/{tag}.zip"

            archive_path = temp_root / f"{tag}.zip"

            GLib.idle_add(self._terminal_write, f"Downloading WMM {expected_version} from GitHub...\r\n")

            # Descarga el ZIP del tag estable anunciado por GitHub.
            request = urllib.request.Request(download_url, headers={
                    "Accept": "application/vnd.github+json", "User-Agent": "WMM-Install-Manager"})

            with urllib.request.urlopen(request, timeout=30) as response, archive_path.open("wb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)

            GLib.idle_add(self._terminal_write, "Download completed.\r\nExtracting package...\r\n")

            # Rechaza rutas inseguras y exige una única raíz con nombre esperado.
            with zipfile.ZipFile(archive_path, "r") as archive:
                members = archive.infolist()

                for member in members:
                    path = Path(member.filename)
                    if path.is_absolute() or ".." in path.parts:
                        raise ValueError("Unsafe path found in update package.")

                roots = {Path(member.filename).parts[0] for member in members if Path(member.filename).parts}
                expected_root = f"wmm-{expected_version}"

                if roots != {expected_root}:
                    raise ValueError(
                        f"Unexpected package root: expected {expected_root}, found {', '.join(sorted(roots))}")

                package_root = temp_root / expected_root
                archive.extractall(temp_root)

            # CHANGELOG.md confirma que el paquete corresponde a la release detectada.
            changelog = package_root / "CHANGELOG.md"
            if not changelog.is_file():
                raise ValueError("CHANGELOG.md was not found in the update package.")

            package_version = None
            with changelog.open("r", encoding="utf-8") as file:
                for line in file:
                    line = line.strip()
                    if line.startswith("## v"):
                        package_version = line[4:].split()[0].strip()
                        break

            if package_version != expected_version:
                raise ValueError(
                    f"Release version mismatch: GitHub={expected_version}, package={package_version}")

            GLib.idle_add(self._terminal_write,
                f"\r\nPackage WMM {expected_version} downloaded and validated.\r\n"
                f"Temporary package:\r\n{package_root}\r\n\r\n")
            GLib.idle_add(self._terminal_write,
                f"\r\nPackage WMM {expected_version} downloaded and validated.\r\n")

            GLib.idle_add(self._validate_and_launch_upgrade, package_root)
            return

        except (OSError, EOFError, ValueError, zipfile.BadZipFile,
                urllib.error.URLError, urllib.error.HTTPError) as error:
            GLib.idle_add(self._upgrade_prepare_failed, error)

    def _validate_and_launch_upgrade(self, package_root):
        """Valida el paquete descargado y lanza su instalador en modo Upgrade."""
        installer = package_root / "wmm-install.sh"

        required = [
            installer,
            package_root / "wmm-uninstall.sh",
            package_root / "README.md",
            package_root / "CHANGELOG.md",
            package_root / "LICENSE",
            package_root / "wmm",
            package_root / "wmm" / "data" / "about.json",
        ]

        if not all(path.exists() for path in required):
            self._upgrade_prepare_failed(ValueError("The prepared update package is incomplete."))
            return False

        try:
            installer_text = installer.read_text(encoding="utf-8")
        except OSError as error:
            self._upgrade_prepare_failed(error)
            return False

        if "--upgrade)" not in installer_text:
            self._upgrade_prepare_failed(ValueError("The prepared installer does not support --upgrade."))
            return False

        self._terminal_write(
            "Prepared package validated.\r\n"
            "Starting WMM upgrade...\r\n\r\n")

        self._launch_upgrade_installer(package_root, installer)
        return False

    def _launch_upgrade_installer(self, package_root, installer):
        """Ejecuta en VTE el wmm-install.sh del paquete preparado con --upgrade."""
        self.terminal.spawn_async(
            Vte.PtyFlags.DEFAULT,
            str(package_root),
            ["bash", str(installer), "--upgrade"],
            ["WMM_INSTALL_MANAGER=1"],
            GLib.SpawnFlags.SEARCH_PATH, None, None, -1, None, self._on_terminal_spawned)

        return False

    def _upgrade_prepare_failed(self, error):
        """Restaura la interfaz y muestra el error si falla la preparación del Upgrade."""
        if getattr(self, "_operation_tempdir", None):
            self._operation_tempdir.cleanup()
            self._operation_tempdir = None

        self._operation_running = False
        self._current_operation = None

        self.upgrade_button.set_sensitive(True)
        self.repair_button.set_sensitive(True)
        self.uninstall_button.set_sensitive(True)
        self.close_button.set_sensitive(True)

        self._set_status("dialog-error-symbolic",
            _("Upgrade preparation failed"),
            _("The WMM update package could not be prepared:") + "\n" + str(error))

        self._terminal_write(f"\r\nERROR: {error}\r\n")
        return False

    # ==========================================================
    # ACCIÓN: REINSTALL
    # ==========================================================
    # Reinstalación desde el payload local limpio de la misma versión.

    def _on_reinstall_clicked(self, _button):
        """Comprueba el payload local y solicita confirmación antes de Reinstall."""
        if not REPAIR_ARCHIVE_PATH.is_file():
            self._set_status("dialog-error-symbolic",
                _("Repair package unavailable"),
                _("The local WMM repair package could not be found."))
            self.dynamic_stack.set_visible_child_name("status")
            return

        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            destroy_with_parent=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.CANCEL,
            text=_("WMM will be reinstalled using a clean copy of the current version."))
        dialog.set_title(_("Reinstall") + " WMM")
        dialog.format_secondary_text(_("Your WMM settings and persistent data will be preserved."))
        dialog.add_button(_("Reinstall"), Gtk.ResponseType.ACCEPT)
        dialog.set_default_response(Gtk.ResponseType.CANCEL)

        response = dialog.run()
        dialog.destroy()

        if response == Gtk.ResponseType.ACCEPT:
            self._start_reinstall()

    def _start_reinstall(self):
        """Extrae el payload local de reparación y ejecuta su instalador con --repair."""
        # Reinstall siempre parte del payload limpio generado durante la instalación.
        try:
            self._operation_tempdir = tempfile.TemporaryDirectory(prefix="wmm-repair-")
            temp_root = Path(self._operation_tempdir.name)

            with zipfile.ZipFile(REPAIR_ARCHIVE_PATH, "r") as archive:
                roots = {Path(name).parts[0] for name in archive.namelist() if Path(name).parts}
                if len(roots) != 1:
                    raise ValueError("Invalid repair package structure.")

                package_root = temp_root / roots.pop()
                archive.extractall(temp_root)

            installer = package_root / "wmm-install.sh"

            required = [
                installer,
                package_root / "wmm-uninstall.sh",
                package_root / "README.md",
                package_root / "CHANGELOG.md",
                package_root / "LICENSE",
                package_root / "wmm",
            ]
            if not all(path.exists() for path in required):
                raise ValueError("Incomplete repair package.")

        except (OSError, ValueError, zipfile.BadZipFile) as error:
            if getattr(self, "_operation_tempdir", None):
                self._operation_tempdir.cleanup()
                self._operation_tempdir = None

            self._set_status("dialog-error-symbolic",
                _("Unable to prepare reinstall"),
                _("The WMM repair package could not be prepared:") + "\n" + str(error))
            self.dynamic_stack.set_visible_child_name("status")
            return

        self._operation_running = True
        self._current_operation = "reinstall"

        self.upgrade_button.set_sensitive(False)
        self.repair_button.set_sensitive(False)
        self.uninstall_button.set_sensitive(False)
        self.close_button.set_sensitive(False)

        self._set_status(None,
            _("Reinstalling WMM"),
            _("The reinstall process is running."),
            spinning=True)

        self.terminal.reset(True, True)
        self.dynamic_stack.set_visible_child_name("terminal")
        self.details_button.set_label(_("Hide details"))

        self.terminal.spawn_async(
            Vte.PtyFlags.DEFAULT,
            str(package_root),
            ["bash", str(installer), "--repair"],
            ["WMM_INSTALL_MANAGER=1"],
            GLib.SpawnFlags.SEARCH_PATH, None, None, -1, None, self._on_terminal_spawned)

    # ==========================================================
    # ACCIÓN: UNINSTALL
    # ==========================================================
    # Confirmación y ejecución del desinstalador autoritativo.

    def _on_uninstall_clicked(self, _button):
        """Solicita confirmación antes de iniciar la desinstalación."""
        if not UNINSTALLER_PATH.is_file():
            self.status_label.set_text( _("WMM uninstaller was not found.") )
            self.dynamic_stack.set_visible_child_name("status")
            return

        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            destroy_with_parent=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.CANCEL,
            text=_("WMM and its desktop integration will be " "removed from this system."),
        )
        dialog.set_title(_("Uninstall") + " WMM")
        dialog.format_secondary_text(_("Do you want to continue?"))

        dialog.add_button(_("Uninstall"), Gtk.ResponseType.ACCEPT)

        uninstall_button = dialog.get_widget_for_response(Gtk.ResponseType.ACCEPT)
        if uninstall_button is not None:
            uninstall_button.get_style_context().add_class("destructive-action")

        dialog.set_default_response(Gtk.ResponseType.CANCEL)

        response = dialog.run()
        dialog.destroy()

        if response != Gtk.ResponseType.ACCEPT:
            return

        self._start_uninstall()

    def _start_uninstall(self):
        """Ejecuta el desinstalador dentro del terminal VTE."""
        self._operation_running = True
        self._current_operation = "uninstall"

        self.upgrade_button.set_sensitive(False)
        self.repair_button.set_sensitive(False)
        self.uninstall_button.set_sensitive(False)
        self.close_button.set_sensitive(False)

        self._set_status(None, _("Uninstalling WMM"), _("The uninstall process is running."), spinning=True)

        self.terminal.reset(True, True)

        self.dynamic_stack.set_visible_child_name("terminal")
        self.details_button.set_label(_("Hide details"))

        self.terminal.spawn_async(
            Vte.PtyFlags.DEFAULT,
            str(UNINSTALLER_PATH.parent),
            ["bash", str(UNINSTALLER_PATH), "--managed"],
            ["WMM_INSTALL_MANAGER=1"],
            GLib.SpawnFlags.SEARCH_PATH, None, None, -1, None, self._on_terminal_spawned)

    # ==========================================================
    # CONTROL COMÚN DE OPERACIONES
    # ==========================================================
    # Lifecycle compartido de VTE y protección de la ventana durante procesos activos.

    def _on_delete_event(self, _window, _event):
        """Impide cerrar el manager mientras una operación está activa."""
        return self._operation_running

    def _on_terminal_spawned(self, _terminal, _pid, error):
        """Restaura la interfaz si VTE no consigue iniciar una operación."""
        if error is None:
            # El VTE debe recibir el teclado inmediatamente: prompts como sudo no muestran lo escrito.
            self.terminal.grab_focus()
            return

        operation = self._current_operation

        self._operation_running = False
        self._current_operation = None

        if getattr(self, "_operation_tempdir", None):
            self._operation_tempdir.cleanup()
            self._operation_tempdir = None

        upgrade_available = (
            self.latest_release is not None and
            parse_version(self.installed_version) < parse_version(self.latest_release["version"])
        )

        self.upgrade_button.set_sensitive(upgrade_available)
        self.repair_button.set_sensitive(True)
        self.uninstall_button.set_sensitive(True)
        self.close_button.set_sensitive(True)

        if operation == "upgrade":
            title = _("Unable to start upgrade")
            message = _("The WMM upgrade process could not be started:")
        elif operation == "reinstall":
            title = _("Unable to start reinstall")
            message = _("The WMM reinstall process could not be started:")
        else:
            title = _("Unable to start the uninstaller")
            message = _("The WMM uninstaller could not be started:")

        self._set_status("dialog-error-symbolic", title, message + "\n" + str(error))

        self.dynamic_stack.set_visible_child_name("status")
        self.details_button.set_label(_("Show details"))

    def _on_terminal_child_exited(self, _terminal, status):
        """Procesa el resultado final del script de mantenimiento ejecutado en VTE."""
        operation = self._current_operation
        if operation is None:
            return

        self._operation_running = False
        self._current_operation = None
        self.close_button.set_sensitive(True)

        if operation == "uninstall":
            if status == 0:
                # WMM ya no está instalado: no ofrecer operaciones de mantenimiento.
                self.upgrade_button.set_sensitive(False)
                self.repair_button.set_sensitive(False)
                self.uninstall_button.set_sensitive(False)

                self._set_status("emblem-ok-symbolic",
                    _("Uninstallation completed"),
                    _("WMM has been successfully uninstalled."))
            else:
                # Puede existir una instalación parcialmente eliminada.
                # Reinstall y Uninstall permanecen como vías de recuperación.
                self.upgrade_button.set_sensitive(False)
                self.repair_button.set_sensitive(True)
                self.uninstall_button.set_sensitive(True)

                self._set_status("dialog-error-symbolic",
                    _("Uninstallation incomplete"),
                    _("WMM could not be completely uninstalled.") + "\n" +
                    _("Review the terminal output for details."))

        elif operation == "reinstall":
            if status == 0:
                self.installed_version = load_installed_version()
                self.version_value_label.set_text(self.installed_version)

                upgrade_available = (
                    self.latest_release is not None and
                    parse_version(self.installed_version) < parse_version(self.latest_release["version"])
                )

                self.upgrade_button.set_sensitive(upgrade_available)
                self.repair_button.set_sensitive(True)
                self.uninstall_button.set_sensitive(True)

                self._set_status("emblem-ok-symbolic",
                    _("Reinstallation completed"),
                    _("WMM has been successfully reinstalled."))
            else:
                self.upgrade_button.set_sensitive(False)
                self.repair_button.set_sensitive(True)
                self.uninstall_button.set_sensitive(True)

                self._set_status("dialog-error-symbolic",
                    _("Reinstallation incomplete"),
                    _("WMM could not be completely reinstalled.") + "\n" +
                    _("Review the terminal output for details."))

        elif operation == "upgrade":
            self.installed_version = load_installed_version()
            self.version_value_label.set_text(self.installed_version)

            upgrade_available = (
                self.latest_release is not None and
                parse_version(self.installed_version) < parse_version(self.latest_release["version"])
            )

            self.upgrade_button.set_sensitive(upgrade_available)
            self.repair_button.set_sensitive(True)
            self.uninstall_button.set_sensitive(True)

            if status == 0:
                self._set_status("emblem-ok-symbolic",
                    _("Upgrade completed"),
                    _("WMM has been successfully upgraded to version:") + " " + str(self.installed_version))
            else:
                self._set_status("dialog-error-symbolic",
                    _("Upgrade incomplete"),
                    _("WMM could not be completely upgraded.") + "\n" +
                    _("Review the terminal output for details."))

        if getattr(self, "_operation_tempdir", None):
            self._operation_tempdir.cleanup()
            self._operation_tempdir = None

    # ==========================================================
    # UI Y HELPERS COMUNES
    # ==========================================================
    # Utilidades visuales compartidas por todas las acciones.

    def _terminal_write(self, text):
        """Escribe texto informativo directamente en el terminal VTE."""
        self.terminal.feed(text.encode("utf-8"))
        return False

    def _on_terminal_button_press(self, terminal, event):
        """Muestra el menú contextual del terminal con el botón derecho."""
        if event.button != 3:
            return False

        menu = Gtk.Menu()

        copy_item = Gtk.MenuItem(label=_("Copy"))
        copy_item.set_sensitive(terminal.get_has_selection())
        copy_item.connect("activate", lambda *_: terminal.copy_clipboard_format(Vte.Format.TEXT))
        menu.append(copy_item)

        paste_item = Gtk.MenuItem(label=_("Paste"))
        paste_item.connect("activate", lambda *_: terminal.paste_clipboard())
        menu.append(paste_item)

        menu.show_all()
        menu.popup_at_pointer(event)
        return True

    def _set_status(self, icon_name, title, message, spinning=False):
        """Actualiza el contenido de la página de estado."""
        self.status_title.set_markup(f"<span size='large'><b>{title}</b></span>")
        self.status_label.set_text(message)

        if spinning:
            self.status_icon.hide()
            self.status_spinner.show()
            self.status_spinner.start()
            return

        self.status_spinner.stop()
        self.status_spinner.hide()
        self.status_icon.set_from_icon_name(icon_name, Gtk.IconSize.DIALOG)
        self.status_icon.show()

    def _on_toggle_details(self, button):
        """Alterna entre la información de estado y el terminal."""
        if self.dynamic_stack.get_visible_child_name() == "terminal":
            self.dynamic_stack.set_visible_child_name("status")
            button.set_label(_("Show details"))
        else:
            self.dynamic_stack.set_visible_child_name("terminal")
            button.set_label(_("Hide details"))

    @staticmethod
    def _add_info_row(grid, row, name, value):
        """Añade una fila nombre/valor al bloque informativo."""
        name_label = Gtk.Label(label=name)
        name_label.set_halign(Gtk.Align.END)

        value_label = Gtk.Label(label=value)
        value_label.set_halign(Gtk.Align.START)

        grid.attach( name_label, 0, row, 1, 1 )
        grid.attach( value_label, 1, row, 1, 1 )

        return value_label

# ==========================================================
# APLICACIÓN
# ==========================================================
class InstallManagerApplication(Gtk.Application):
    """Aplicación GTK de instancia única para WMM Install Manager."""

    def __init__(self):
        super().__init__( application_id="org.maki.wmm.InstallManager" )

    def do_activate(self):
        window = self.props.active_window

        if window is None:
            window = InstallManagerWindow(self)
            window.connect(
                "destroy",
                lambda *_: self.quit()
            )
            self.add_window(window)

        window.present()


if __name__ == "__main__":
    app = InstallManagerApplication()
    raise SystemExit(app.run(sys.argv))
