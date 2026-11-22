#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

"""
WMM - Wallpaper Multi-Monitor Manager

shell_send_to_monitor.py – Acción "Enviar a monitor" desde file_manager.
===============================
Recibe la ruta de una imagen, muestra un diálogo nativo con los monitores activos
y asigna la imagen al monitor seleccionado.

FLUJO DE CONTROL:
    1. Se invoca desde el menú contextual de file_manager.
    2. Verifica la ruta de la imagen y controla la instancia única.
    3. Lee los monitores activos desde geometry.json y monitor_vault.json.
    4. Muestra un diálogo GTK con los monitores disponibles.
    5. Al aceptar, actualiza el vault, notifica al motor y envía una
       notificación de confirmación.
"""

# ==========================================================
# IMPORTS DE LIBRERÍA ESTÁNDAR
# ==========================================================
import sys
import os
import subprocess

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
from gi.repository import Gtk

# ==========================================================
# IMPORTS DE MÓDULOS DEL PROYECTO
# ==========================================================
from config_handler import ConfigHandler
from wmm_platform.core import PlatformManager
from debug_logger import log_event, set_cache_dir
from i18n import _, initialize

# ----------------------------------------------------------------------
# DIÁLOGO DE SELECCIÓN DE MONITOR
# ----------------------------------------------------------------------

class MonitorSelectorDialog(Gtk.Dialog):
    """
    Diálogo GTK nativo para seleccionar un monitor de destino.
    Hereda de Gtk.Dialog para usar run() y response types estándar.
    """

    def __init__(self, monitors, label_to_hash, mfg_map):
        """
        Args:
            monitors (list): Lista de etiquetas descriptivas para el ComboBox.
            label_to_hash (dict): Diccionario que mapea etiqueta -> hash del monitor.
            mfg_map (dict): Mapa de códigos de fabricante (no se usa directamente,
                            pero se recibe por coherencia con el resto del módulo).
        """
        super().__init__(title=_("Send to Monitor"))
        self.set_icon_name("video-display")
        self.set_default_size(250, 150)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_modal(True)

        # Guardar referencia al mapa de hashes para usarlo en la respuesta
        self._label_to_hash = label_to_hash
        self.selected_hash = None
        self.selected_label = None

        # --- Área de contenido ---
        content = self.get_content_area()
        content.set_spacing(10)
        content.set_margin_start(10)
        content.set_margin_end(10)
        content.set_margin_top(10)

        label = Gtk.Label(label=_("Select a monitor:"))
        label.set_halign(Gtk.Align.START)
        content.pack_start(label, False, False, 0)

        # Combo con los monitores disponibles
        self.combo = Gtk.ComboBoxText()
        for label_text in monitors:
            self.combo.append_text(label_text)
        self.combo.set_active(0)  # Seleccionar el primero por defecto
        content.pack_start(self.combo, False, False, 0)

        # --- Botones de acción estándar ---
        self.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
        self.add_button(_("OK"), Gtk.ResponseType.OK)

        self.show_all()

    def do_response(self, response):
        """
        Maneja la respuesta del diálogo antes de cerrar.
        Si se pulsa OK, guarda la etiqueta y el hash del monitor seleccionado.
        """
        if response == Gtk.ResponseType.OK:
            selected_label = self.combo.get_active_text()
            if selected_label:
                self.selected_label = selected_label
                self.selected_hash = self._label_to_hash.get(selected_label)
        self.destroy()

# ----------------------------------------------------------------------
# PUNTO DE ENTRADA
# ----------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("Uso: shell_send_to_monitor.py <ruta_imagen>")
        sys.exit(1)

    # Reconstruir la ruta si file_manager la ha fragmentado por espacios
    if len(sys.argv) > 2:
        sys.argv = [sys.argv[0], ' '.join(sys.argv[1:])]

    image_path = os.path.abspath(sys.argv[1])
    if not os.path.isfile(image_path):
        sys.exit(1)

    # Inicializar la plataforma
    platform = PlatformManager()

    if hasattr(platform, "prepare_gtk_color_scheme"):
        platform.prepare_gtk_color_scheme()

    if hasattr(platform, "set_process_name"):
        platform.set_process_name("WMM SendToMon")

    # Inicializar traducciones
    initialize(platform)

    # Inicializar el sistema de registro
    set_cache_dir(platform.cache_dir)

    # Crear el gestor de configuración
    ch = ConfigHandler(cache_base_dir=platform.cache_dir, platform=platform)

    log_event(f"sys.argv = {sys.argv}",
        origin="SHELL_SEND", level="DEBUG", reason="BOOKMARK")
    log_event(f"CWD = {os.getcwd()}",
        origin="SHELL_SEND", level="DEBUG", reason="BOOKMARK")
    log_event(f"Iniciando envío a monitor: {os.path.basename(image_path)}",
              origin="SHELL_SEND", level="INFO", reason="BOOKMARK")

    # --- Control de instancia única ---
    # El lock demuestra qué instancia posee el diálogo; el PID conserva
    # únicamente su identidad y se elimina durante el cierre limpio.
    lock_path = os.path.join(ch.cache_dir, "send_to_monitor.lock")
    pid_path = os.path.join(ch.cache_dir, "pid_send_to_monitor.pid")
    os.makedirs(ch.cache_dir, exist_ok=True)

    lock_file = open(lock_path, "a+")

    try:
        acquired = platform.try_lock_file(lock_file)

        if not acquired:
            # Sólo un lock ocupado convierte el PID publicado por la instancia
            # anterior en una identidad válida para sustituirla.
            try:
                with open(pid_path, "r", encoding="utf-8") as pid_reader:
                    old_pid = int(pid_reader.read().strip())
            except (OSError, ValueError):
                log_event("Instancia anterior sin PID válido; no se fuerza su cierre",
                    origin="SHELL_SEND", level="WARN", reason="NOTIFY")
                return

            try:
                platform.terminate_process(old_pid)
            except OSError as error:
                # Puede haber terminado por sí sola entre la lectura y la
                # terminación. Continuar sólo si el lock ya ha quedado libre.
                if not platform.try_lock_file(lock_file):
                    log_event(f"No se pudo sustituir la instancia anterior: {error}",
                        origin="SHELL_SEND", level="WARN", reason="NOTIFY")
                    return
            else:
                # Esperar a la liberación real del proceso anterior.
                platform.lock_file(lock_file)

        # Desde este punto somos propietarios del diálogo.
        with open(pid_path, "w", encoding="utf-8") as pid_writer:
            pid_writer.write(str(os.getpid()))

        # --- Leer monitores activos ---
        vault = ch.load_json("vault")
        active = vault.get("active_session", {})
        geometry = ch.load_json("geometry")
        monitors = geometry.get("monitors", {})
        mfg_map = ch.get_mfg_map()

        # --- Construir lista de monitores y mapa de vuelta ---
        monitors_list = []
        label_to_hash = {}
        for m_hash, entry in active.items():
            if isinstance(entry, dict) and not entry.get("active", True):
                continue
            info = monitors.get(m_hash, {})
            label = ch.get_monitor_display_name(m_hash)

            if info.get("primary", False):
                label += " " + _("Primary")

            monitors_list.append(label)
            label_to_hash[label] = m_hash

        if not monitors_list:
            log_event("No hay monitores activos",
                origin="SHELL_SEND", level="ERROR", reason="NOTIFY")
            ch._send_notification("WMM: " + _("No monitors"),
                _("No active monitors found"), level="warn")
            sys.exit(1)

        # --- Mostrar diálogo GTK nativo ---
        dialog = MonitorSelectorDialog(monitors_list, label_to_hash, mfg_map)

        if hasattr(platform, "present_window"):
            platform.present_window(dialog)

        response = dialog.run()
        dialog.destroy()

        if response != Gtk.ResponseType.OK or not dialog.selected_hash:
            log_event("Envío cancelado por el usuario",
                origin="SHELL_SEND", level="INFO", reason="NOTIFY")
            sys.exit(0)

        m_hash = dialog.selected_hash
        log_event(f"Monitor seleccionado: {m_hash[:8]}...",
            origin="SHELL_SEND", level="INFO", reason="NOTIFY")

        # --- Actualizar el vault ---
        entry = active.get(m_hash, {})
        if isinstance(entry, str):
            entry = {"path": entry, "active": True}
        entry["path"] = image_path
        vault["active_session"][m_hash] = entry
        log_event(f"Vault actualizado: {m_hash[:8]} -> {os.path.basename(image_path)}",
                  origin="SHELL_SEND", level="DEBUG", reason="HARDWARE")
        ch.save_json("vault", vault)

        # --- Notificar al motor ---
        log_event("Notificando al motor (apply_manual_selection)",
            origin="SHELL_SEND", level="DEBUG", reason="COMMAND")
        import json
        cmd = json.dumps({"action": "apply_manual_selection"})
        script = os.path.join(os.path.dirname(__file__), "send_command.py")
        try:
            subprocess.run([sys.executable, script, cmd], check=True)
        except Exception as e:
            log_event(f"No se pudo notificar al motor: {e}",
                origin="SHELL_SEND", level="WARN", reason="COMMAND")

        # Notificación de confirmación
        name = os.path.basename(image_path)
        monitor_label = dialog.selected_label or m_hash[:8]
        ch._send_notification(
            reason="WMM: " + _("Image sent to monitor"),
            detail_msg=_("Image '{name}' assigned to monitor {monitor}.")
                .format(name=name, monitor=monitor_label),
            level="info")

    finally:
        log_event("Finalizando envío a monitor",
            origin="SHELL_SEND", level="DEBUG", reason="NOTIFY")

        # Mientras conservamos el lock ninguna nueva instancia puede publicar
        # su identidad, así que sólo podemos retirar nuestro propio PID.
        if os.path.exists(pid_path):
            try:
                with open(pid_path, "r", encoding="utf-8") as pid_reader:
                    content = pid_reader.read().strip()

                if content and int(content) == os.getpid():
                    os.remove(pid_path)

            except (OSError, ValueError):
                pass

        if not lock_file.closed:
            try:
                platform.unlock_file(lock_file)
            except OSError:
                pass

            try:
                lock_file.close()
            except OSError:
                pass

if __name__ == "__main__":
    main()
