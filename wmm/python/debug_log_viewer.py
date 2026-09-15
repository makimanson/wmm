#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

"""
WMM - Wallpaper Multi-Monitor Manager

debug_log_viewer.py – Visor independiente del log de depuración.
===============================

Muestra el contenido de debug.log en tiempo real, con actualización
automática cada segundo.
"""

# ==========================================================
# IMPORTS DE LIBRERÍA ESTÁNDAR
# ==========================================================
import os
import sys
import json
import re

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# ==========================================================
# IMPORTS DE TERCEROS (GTK)
# ==========================================================
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Gio

# ==========================================================
# IMPORTS DE MÓDULOS DEL PROYECTO
# ==========================================================
from debug_logger import read_log, get_log_path, clear_log, set_cache_dir, log_event
from i18n import _

# ----------------------------------------------------------------------
# LISTAS DE FILTROS PARA LOS COMBOS
# ----------------------------------------------------------------------

FILTER_ORIGINS = ["All", "ADD_BOOK", "BACKEND", "CHANNELS", "CINNAMON", "CONFIG", "CORE",
        "DESKTOP", "ENGINE", "GNOME", "IMG_ENG", "IMG_SEL", "KDE", "LINUX", "MATE", "MON_DETECT",
        "MON_EVENT", "PANEL", "SEND_COMM", "SHELL_SEND", "SHELL_ADD", "UNKNOW", "XFCE"]

FILTER_LEVELS = ["All", "DEBUG", "ERROR", "INFO", "WARN"]

FILTER_REASONS = ["All", "BOOKMARK", "COMMAND", "D-BUS", "FILE_MON", "GENERIC", "HARDWARE",
        "INIT", "LAYOUT", "LIBRARY", "MODULE", "NOTIFY", "SETTINGS", "TIMER", "VAULT"]

class DebugLogViewer(Gtk.Window):
    def __init__(self, parent=None):
        super().__init__(title="WMM - " + _("Debug Log Viewer"))
        self.set_icon_name("utilities-system-monitor")  # Icono de monitorización del sistema
        # Heredar los colores del tema del sistema (fondo de ventana)
        self.get_style_context().add_class("background")
        self.set_position(Gtk.WindowPosition.CENTER)
        if parent:
            self.set_transient_for(parent)

        # ----------------------------------------------------------
        # PREFERENCIAS DEL VISOR
        # ----------------------------------------------------------
        self._settings_path = os.path.join(_PROJECT_ROOT, "data", "settings.json")
        self._viewer_preferences = self._load_viewer_preferences()
        self.set_default_size(*self._viewer_preferences["window_size"])

        # ----------------------------------------------------------
        # CONTENEDOR PRINCIPAL
        # ----------------------------------------------------------
        main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        main_vbox.set_border_width(8)
        self.add(main_vbox)

        # ==========================================================
        # DEFINICIÓN DE WIDGETS (por bloques)
        # ==========================================================

        # --- BLOQUE IZQUIERDO: COMBOS DE FILTRO ---
        combos_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        # Combo de Origen
        origin_vbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        origin_label = Gtk.Label(label=_("Origin"))
        origin_label.set_halign(Gtk.Align.CENTER)
        self.origin_combo = Gtk.ComboBoxText()
        for item in FILTER_ORIGINS:
            self.origin_combo.append_text(item)
        self.origin_combo.set_active(0)  # "All"
        self.origin_combo.connect("changed", self._on_filter_changed)
        origin_vbox.pack_start(origin_label, False, False, 0)
        origin_vbox.pack_start(self.origin_combo, False, False, 0)
        combos_box.pack_start(origin_vbox, False, False, 0)

        # Combo de Nivel
        level_vbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        level_label = Gtk.Label(label=_("Level"))
        level_label.set_halign(Gtk.Align.CENTER)
        self.level_combo = Gtk.ComboBoxText()
        for item in FILTER_LEVELS:
            self.level_combo.append_text(item)
        self.level_combo.set_active(0)  # "All"
        self.level_combo.connect("changed", self._on_filter_changed)
        level_vbox.pack_start(level_label, False, False, 0)
        level_vbox.pack_start(self.level_combo, False, False, 0)
        combos_box.pack_start(level_vbox, False, False, 0)

        # Combo de Reason
        reason_vbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        reason_label = Gtk.Label(label=_("Reason"))
        reason_label.set_halign(Gtk.Align.CENTER)
        self.reason_combo = Gtk.ComboBoxText()
        for item in FILTER_REASONS:
            self.reason_combo.append_text(item)
        self.reason_combo.set_active(0)  # "All"
        self.reason_combo.connect("changed", self._on_filter_changed)
        reason_vbox.pack_start(reason_label, False, False, 0)
        reason_vbox.pack_start(self.reason_combo, False, False, 0)
        combos_box.pack_start(reason_vbox, False, False, 0)

        # --- BLOQUE DERECHO: BARRA DE BÚSQUEDA ---
        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        search_label = Gtk.Label(label=_("Search"))
        search_label.set_halign(Gtk.Align.CENTER)
        self.search_entry = Gtk.Entry()
        self.search_entry.set_placeholder_text(_("Filter by text") + "...")
        self.search_entry.connect("changed", self._on_filter_changed)
        search_box.pack_start(search_label, False, False, 0)
        search_box.pack_start(self.search_entry, True, True, 0)

        # --- SEPARADORES VISUALES ---
        top_separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        bottom_separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)

        # --- VISOR DE TEXTO ---
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_overlay_scrolling(False)  # Las barras ocupan espacio propio y no cubren el texto
        self.textview = Gtk.TextView()
        self.textview.set_editable(False)
        self.textview.set_monospace(True)

        # El área interna "text" de Gtk.TextView puede recibir un fondo distinto
        # al del nodo principal en algunos temas. Hacemos que herede explícitamente
        # los colores del propio TextView para respetar siempre el tema GTK activo.
        textview_context = self.textview.get_style_context()
        textview_context.add_class("view")
        textview_context.add_class("wmm-log-view")

        textview_css = Gtk.CssProvider()
        textview_css.load_from_data(b"""
            textview.wmm-log-view text {
                color: inherit;
                background-color: inherit;
            }
        """)
        textview_context.add_provider(textview_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.textbuffer = self.textview.get_buffer()
        scrolled.add(self.textview)

        # --- MARCAS PARA EL RESALTADO (no se invalidan al modificar el buffer) ---
        self._highlight_start_mark = self.textbuffer.create_mark(
            "highlight-start", self.textbuffer.get_start_iter(), True
        )
        self._highlight_end_mark = self.textbuffer.create_mark(
            "highlight-end", self.textbuffer.get_start_iter(), False
        )

        # --- RESALTADO DE LÍNEA ACTUAL ---
        # Creamos una etiqueta visual sin colores fijos: los tomaremos del tema
        self.highlight_tag = self.textbuffer.create_tag("highlight-line")

        # Aplicar los colores del tema actual al tag de resaltado
        self._update_highlight_colors()

        # Conectar señales: movimiento del cursor y cambios de tema
        self.textbuffer.connect("notify::cursor-position", self._on_cursor_moved)
        self.textview.connect("style-updated", lambda w: self._update_highlight_colors())

        # --- BOTONES DE ACCIÓN (LIMPIAR LOG) ---

        clear_btn = Gtk.Button.new_from_icon_name("edit-clear-symbolic", Gtk.IconSize.BUTTON)
        clear_btn.set_tooltip_text(_("Clear log"))
        clear_btn.connect("clicked", self._on_clear_log)

        # --- BLOQUE CENTRAL: SWITCHES DE VISUALIZACIÓN ---
        switches_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        # Switch Auto-scroll
        auto_scroll_vbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        auto_scroll_label = Gtk.Label(label=_("Auto-scroll"))
        auto_scroll_label.set_halign(Gtk.Align.CENTER)
        self.auto_scroll_switch = Gtk.Switch(active=self._viewer_preferences["auto_scroll"])
        self.auto_scroll_switch.set_halign(Gtk.Align.CENTER)
        self.auto_scroll_switch.set_valign(Gtk.Align.CENTER)
        self.auto_scroll_switch.connect("notify::active", self._on_auto_scroll_changed)
        auto_scroll_vbox.pack_start(auto_scroll_label, False, False, 0)
        auto_scroll_vbox.pack_start(self.auto_scroll_switch, False, False, 0)
        switches_box.pack_start(auto_scroll_vbox, False, False, 0)

        # Switch Orden inverso
        reverse_vbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        reverse_label = Gtk.Label(label=_("Reverse order"))
        reverse_label.set_halign(Gtk.Align.CENTER)

        self.reverse_order_switch = Gtk.Switch(active=self._viewer_preferences["reverse_order"])
        self.reverse_order_switch.set_halign(Gtk.Align.CENTER)
        self.reverse_order_switch.set_valign(Gtk.Align.CENTER)

        self.reverse_order_indicator = Gtk.Label()
        self.reverse_order_indicator.set_markup('<span size="18000">↑</span>'
            if self.reverse_order_switch.get_active()
            else '<span size="18000">↓</span>')
        self.reverse_order_indicator.set_halign(Gtk.Align.CENTER)
        self.reverse_order_indicator.set_valign(Gtk.Align.CENTER)

        self.reverse_order_switch.connect("notify::active", self._on_reverse_order_changed)

        reverse_vbox.pack_start(reverse_label, False, False, 0)
        reverse_vbox.pack_start(self.reverse_order_switch, False, False, 0)
        reverse_vbox.pack_start(self.reverse_order_indicator, False, False, 0)

        switches_box.pack_start(reverse_vbox, False, False, 0)

        # ==========================================================
        # ORDEN DE EMPAQUETADO EN LA VENTANA
        # ==========================================================

        # --- FILA SUPERIOR: COMBOS (IZQ) + ESPACIADOR + BÚSQUEDA (DER) ---
        top_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        top_box.pack_start(combos_box, False, False, 0)  # Combos alineados a la izquierda
        top_box.pack_start(Gtk.Box(), True, True, 0)      # Espaciador central (empuja la búsqueda)
        top_box.pack_start(search_box, False, False, 0)   # Búsqueda alineada a la derecha
        main_vbox.pack_start(top_box, False, False, 0)
        # --- SEPARADOR SUPERIOR (entre barra de filtros y visor) ---
        main_vbox.pack_start(top_separator, False, False, 4)

        # --- VISOR DE TEXTO (OCUPA EL ESPACIO RESTANTE) ---
        main_vbox.pack_start(scrolled, True, True, 0)

        # --- SEPARADOR INFERIOR (entre visor y barra de acciones) ---
        main_vbox.pack_start(bottom_separator, False, False, 4)
        # --- FILA INFERIOR: SWITCHES (IZQ) + LIMPIAR (DER) ---
        toolbar_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        toolbar_box.pack_start(switches_box, False, False, 0) # Switches alineados a la izquierda
        toolbar_box.pack_start(Gtk.Box(), True, True, 0)      # Espaciador (empuja el botón limpiar)
        toolbar_box.pack_end(clear_btn, False, False, 0)      # Limpiar a la derecha
        main_vbox.pack_start(toolbar_box, False, False, 0)

        # ----------------------------------------------------------
        # PRIMERA CARGA Y MONITORIZACIÓN
        # ----------------------------------------------------------
        self._last_content = ""
        self._scroll_timeout_id = 0  # Sólo puede existir un auto-scroll pendiente
        self._refresh()

        # Monitorizar cambios en el archivo de log para actualización reactiva
        log_file = Gio.File.new_for_path(get_log_path())
        self._log_monitor = log_file.monitor_file(Gio.FileMonitorFlags.NONE, None)
        self._log_monitor.connect("changed", self._on_log_changed)
        # Reaccionar a cambios de tema del sistema (claro/oscuro)
        self.connect("style-updated", lambda w: self._refresh(force=True))
        # Guardar el tamaño mientras la ventana conserva su geometría real
        self.connect("delete-event", self._on_delete_event)
        # Cancelar monitor al cerrar la ventana
        self.connect("destroy", self._on_destroy)

    # ==========================================================
    # PREFERENCIAS DEL VISOR
    # ==========================================================
    def _load_viewer_preferences(self):
        """Carga las preferencias visuales propias del Debug Log Viewer."""
        defaults = { "auto_scroll": True, "reverse_order": True, "window_size": [800, 550], }

        try:
            with open(self._settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)
        except (OSError, json.JSONDecodeError):
            return defaults

        if not isinstance(settings, dict):
            return defaults

        viewer_state = settings.get("debug_log_viewer", {})
        if not isinstance(viewer_state, dict):
            return defaults

        preferences = {}

        for key in ("auto_scroll", "reverse_order"):
            default = defaults[key]
            value = viewer_state.get(key, default)
            preferences[key] = value if isinstance(value, bool) else default

        window_size = viewer_state.get("window_size", defaults["window_size"])
        valid_size = (isinstance(window_size, list) and len(window_size) == 2
            and all(type(value) is int and value > 0 for value in window_size))
        preferences["window_size"] = window_size if valid_size else defaults["window_size"]

        return preferences

    def _save_viewer_preference(self, key, value):
        """Guarda una preferencia propia del Debug Log Viewer sin reformatear settings.json."""
        if key in ("auto_scroll", "reverse_order"):
            value = bool(value)

        try:
            with open(self._settings_path, "r", encoding="utf-8") as f:
                raw_settings = f.read()
            settings = json.loads(raw_settings)
        except (OSError, json.JSONDecodeError) as e:
            log_event(f"No se pudo cargar settings para guardar una preferencia: {e}",
                origin="DEBUG_VIEW", level="WARN", reason="SETTINGS")
            return

        if not isinstance(settings, dict):
            return

        viewer_state = settings.get("debug_log_viewer")
        if "debug_log_viewer" in settings and not isinstance(viewer_state, dict):
            return

        if isinstance(viewer_state, dict) and viewer_state.get(key) == value:
            return

        match = re.search(
            r'("debug_log_viewer"\s*:\s*\{)(.*?)(\n[ \t]*\})',
            raw_settings, re.DOTALL
        )

        serialized_value = json.dumps(value, ensure_ascii=False)

        if match:
            body = match.group(2)
            key_pattern = rf'(^[ \t]*"{re.escape(key)}"\s*:\s*)(?:true|false|\[[^\]]*\])'

            if re.search(key_pattern, body, re.MULTILINE):
                body = re.sub(
                    key_pattern,
                    lambda m: m.group(1) + serialized_value,
                    body,
                    count=1,
                    flags=re.MULTILINE
                )
            else:
                indent_match = re.search(r'\n([ \t]+)"', body)
                indent = indent_match.group(1) if indent_match else "        "
                separator = "," if body.strip() else ""
                body = body.rstrip() + separator + "\n" + indent + f'"{key}": {serialized_value}'

            updated = raw_settings[:match.start(2)] + body + raw_settings[match.end(2):]
        else:
            end = raw_settings.rfind("}")
            if end < 0:
                return

            prefix = raw_settings[:end].rstrip()
            separator = "," if prefix and not prefix.endswith("{") else ""
            updated = (
                prefix + separator +
                '\n    "debug_log_viewer": {\n'
                f'        "{key}": {serialized_value}\n'
                "    }\n" +
                raw_settings[end:]
            )

        try:
            with open(self._settings_path, "w", encoding="utf-8") as f:
                f.write(updated)
        except OSError as e:
            log_event(f"No se pudo guardar una preferencia del visor: {e}",
                origin="DEBUG_VIEW", level="WARN", reason="SETTINGS")

    def _on_filter_changed(self, widget):
        """Callback cuando cambia cualquier filtro (combo o búsqueda)."""
        self._refresh(force=False)  # Solo re-aplicar filtros, no releer archivo

    def _on_auto_scroll_changed(self, switch, param):
        """Guarda la preferencia de desplazamiento automático."""
        self._save_viewer_preference("auto_scroll", switch.get_active())

    def _on_reverse_order_changed(self, switch, param):
        """Guarda el orden, actualiza el indicador visual y refresca el visor."""
        active = switch.get_active()
        self._save_viewer_preference("reverse_order", active)

        self.reverse_order_indicator.set_markup('<span size="18000">↑</span>'
            if active
            else '<span size="18000">↓</span>')

        self._refresh()

    def _on_clear_log(self, widget):
        """Pide confirmación y vacía el archivo de log."""
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=_("Clear debug log?")
        )
        dialog.format_secondary_text(_("All log entries will be permanently deleted."))
        response = dialog.run()
        if response == Gtk.ResponseType.YES:
            clear_log()
            self._refresh()
        dialog.destroy()

    def _on_cursor_moved(self, buffer, param):
        """Resalta la línea del cursor usando marcas (no se invalidan)."""
        # 1. Eliminar resaltado antiguo (usando las marcas)
        start = buffer.get_iter_at_mark(self._highlight_start_mark)
        end = buffer.get_iter_at_mark(self._highlight_end_mark)
        if not start.equal(end):  # Solo si hay algo que limpiar
            buffer.remove_tag(self.highlight_tag, start, end)

        # 2. Obtener la línea actual del cursor
        cursor = buffer.get_iter_at_mark(buffer.get_insert())
        line_start = cursor.copy()
        line_start.set_line_offset(0)
        line_end = line_start.copy()
        if not line_end.ends_line():
            line_end.forward_to_line_end()

        # 3. Aplicar nuevo resaltado
        buffer.apply_tag(self.highlight_tag, line_start, line_end)

        # 4. Mover las marcas a la nueva posición
        buffer.move_mark(self._highlight_start_mark, line_start)
        buffer.move_mark(self._highlight_end_mark, line_end)

    def _update_highlight_colors(self):
        """
        Aplica al resaltado de línea una variación neutra del fondo normal
        del tema GTK.

        En temas oscuros aclara ligeramente el fondo.
        En temas claros lo oscurece ligeramente.

        La selección real de texto conserva íntegramente los colores
        SELECTED definidos por el tema.
        """
        style_ctx = self.textview.get_style_context()

        bg_color = style_ctx.get_property("background-color", Gtk.StateFlags.NORMAL)

        # Luminosidad perceptual aproximada del color de fondo.
        luminance = (
            0.2126 * bg_color.red +
            0.7152 * bg_color.green +
            0.0722 * bg_color.blue
        )

        variation = 0.30

        if luminance < 0.5:
            # Tema oscuro: acercar ligeramente el fondo al blanco.
            bg_color.red += (1.0 - bg_color.red) * variation
            bg_color.green += (1.0 - bg_color.green) * variation
            bg_color.blue += (1.0 - bg_color.blue) * variation
        else:
            # Tema claro: acercar ligeramente el fondo al negro.
            bg_color.red *= (1.0 - variation)
            bg_color.green *= (1.0 - variation)
            bg_color.blue *= (1.0 - variation)

        bg_color.alpha = 1.0

        self.highlight_tag.set_property("foreground-set", False)
        self.highlight_tag.set_property("background-rgba", bg_color)

    def _schedule_auto_scroll(self):
        """Mantiene como máximo un auto-scroll vertical pendiente."""
        if not self.auto_scroll_switch.get_active() or self._scroll_timeout_id:
            return

        def scroll_to_active_edge():
            self._scroll_timeout_id = 0

            # La preferencia puede haber cambiado mientras el callback esperaba.
            if not self.auto_scroll_switch.get_active():
                return False

            adjustment = self.textview.get_vadjustment()

            # Auto-scroll controla sólo el eje vertical; la posición horizontal
            # del usuario no debe perseguir el final de una línea larga.
            if self.reverse_order_switch.get_active():
                adjustment.set_value(adjustment.get_lower())
            else:
                adjustment.set_value(
                    max(adjustment.get_lower(),
                        adjustment.get_upper() - adjustment.get_page_size())
                )

            return False

        # Varias inserciones pueden compartir el mismo desplazamiento pendiente.
        self._scroll_timeout_id = GLib.timeout_add(50, scroll_to_active_edge)

    def _refresh(self, widget=None, force=False):
        """
        Lee el archivo de log, aplica filtros y actualiza el visor.
        Si force=True, relee el archivo aunque no haya cambiado.
        Si force=False y el contenido no ha cambiado, solo re-aplica filtros.
        """
        if force:
            content = read_log()
            self._last_content = content
        else:
            content = read_log()
            if content == self._last_content:
                # El archivo no ha cambiado: solo re-aplicar filtros a lo ya leído
                lines = self._last_content.splitlines()
                lines = self._apply_filters(lines)
                if self.reverse_order_switch.get_active():
                    lines.reverse()
                self.textbuffer.set_text("\n".join(lines))
                return
            self._last_content = content

        # El archivo ha cambiado o forzamos lectura: aplicar filtros a las nuevas líneas
        lines = content.splitlines()
        lines = self._apply_filters(lines)

        if self.reverse_order_switch.get_active():
            lines.reverse()

        self.textbuffer.set_text("\n".join(lines))

        self._schedule_auto_scroll()

    def _update_log_incremental(self):
        """Añade sólo las nuevas líneas cuando debug.log crece por append."""
        content = read_log()

        if content == self._last_content:
            return

        # Clear, truncado o reemplazo rompen la continuidad:
        # sólo esos casos necesitan reconstruir toda la vista.
        if not content.startswith(self._last_content):
            self._refresh(force=True)
            return

        delta = content[len(self._last_content):]
        self._last_content = content

        # Los filtros activos se aplican únicamente a las líneas nuevas.
        lines = self._apply_filters(delta.splitlines())
        if not lines:
            return

        if self.reverse_order_switch.get_active():
            # Más recientes arriba: invertir sólo el delta e insertarlo al inicio.
            lines.reverse()
            text = "\n".join(lines)
            if self.textbuffer.get_char_count():
                text += "\n"
            self.textbuffer.insert(self.textbuffer.get_start_iter(), text)
        else:
            # Orden cronológico: las líneas nuevas prolongan el buffer por abajo.
            text = "\n".join(lines)
            if self.textbuffer.get_char_count():
                text = "\n" + text
            self.textbuffer.insert(self.textbuffer.get_end_iter(), text)

        self._schedule_auto_scroll()

    def _apply_filters(self, lines):
        """
        Filtra las líneas del log según los criterios activos.
        La barra de búsqueda filtra por texto en toda la línea.
        Los combos filtran por el campo correspondiente (origen, nivel, reason).
        Si un combo está en "All", no filtra por ese campo.
        """
        # 1. Filtro de búsqueda (texto libre en toda la línea)
        search_text = self.search_entry.get_text().strip().lower()
        if search_text:
            lines = [line for line in lines if search_text in line.lower()]

        # 2. Filtro por origen
        origin_filter = self.origin_combo.get_active_text()
        if origin_filter and origin_filter != "All":
            lines = [line for line in lines if f"[{origin_filter}]" in line]

        # 3. Filtro por nivel
        level_filter = self.level_combo.get_active_text()
        if level_filter and level_filter != "All":
            lines = [line for line in lines if f"[{level_filter}]" in line]

        # 4. Filtro por reason
        reason_filter = self.reason_combo.get_active_text()
        if reason_filter and reason_filter != "All":
            lines = [line for line in lines if f"[{reason_filter}]" in line]

        return lines

    def _on_log_changed(self, monitor, file, other_file, event_type):
        """Actualiza incrementalmente el visor cuando cambia el archivo de log."""
        if event_type == Gio.FileMonitorEvent.CHANGED:
            self._update_log_incremental()

    def _on_delete_event(self, widget, event):
        """Guarda el tamaño actual una única vez al solicitar el cierre."""
        width, height = self.get_size()
        self._save_viewer_preference("window_size", [width, height])
        return False

    def _on_destroy(self, widget):
        """Cancela la monitorización y cualquier auto-scroll pendiente al cerrar."""
        if hasattr(self, '_log_monitor') and self._log_monitor:
            self._log_monitor.cancel()

        if self._scroll_timeout_id:
            GLib.source_remove(self._scroll_timeout_id)
            self._scroll_timeout_id = 0

# ==========================================================
# APLICACIÓN
# ==========================================================
class DebugLogViewerApplication(Gtk.Application):
    """Aplicación GTK de instancia única para WMM Debug Log Viewer."""

    def __init__(self):
        super().__init__(application_id="org.maki.wmm.DebugLogViewer")

    def do_activate(self):
        window = self.props.active_window

        if window is None:
            window = DebugLogViewer()
            window.connect("destroy", lambda *_: self.quit())
            self.add_window(window)
            window.show_all()

        window.present()

if __name__ == "__main__":
    from wmm_platform.core import PlatformManager
    from i18n import initialize

    platform = PlatformManager()

    if hasattr(platform, "set_process_name"):
        platform.set_process_name("WMM Debug Log")

    initialize(platform)

    # El visor autónomo no pasa por ConfigHandler, por lo que debe
    # configurar explícitamente la ruta del logger común de WMM.
    set_cache_dir(platform.cache_dir)

    app = DebugLogViewerApplication()
    raise SystemExit(app.run(sys.argv))
