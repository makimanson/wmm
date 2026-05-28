#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
WMM Applet - Cinnamon Edition
----------------------------
panel.py – Panel de control de WMM (Ajustes).
* FLUJO DE CONTROL:
  1. Se invoca directamente desde el applet.
  2. Muestra la ventana principal con todas las opciones de configuración.
  3. Si ya existe una instancia abierta, se trae al frente en lugar de crear una nueva.
  4. Al cerrar la ventana, el proceso termina (no queda en segundo plano).
"""
import traceback
import os
import sys
import gi
import base64
import signal
import atexit
import json
import gettext
import subprocess
import time
# import locale

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, Pango, GLib, Gio, GdkPixbuf
from config_handler import ConfigHandler
from backend import WMMBackend
from image_engine import ImageEngine

# ==========================================================
# Traducciones
# ==========================================================

# Captura de traducibles
_ = gettext.gettext
# Usa el idioma configurado en el sistema
# locale.setlocale(locale.LC_ALL, '')
# Ruta estándar de traducciones para extensiones de Cinnamon
# locale_dir = os.path.expanduser('~/.local/share/locale')
# Usar el dominio 'wmm-applet@maki'
# gettext.bindtextdomain('wmm-applet@maki', locale_dir)
# También vincular el dominio 'cinnamon' para heredar traducciones del sistema
# gettext.bindtextdomain('cinnamon', None)
# Establecer el dominio principal
# gettext.textdomain('wmm-applet@maki')

# Función de traducción personalizada: busca primero en el sistema, luego en nuestro dominio
def _(text):
    translated = gettext.dgettext('cinnamon', text)
    if translated != text:
        return translated
    return gettext.dgettext('wmm-applet@maki', text)

# ==========================================================
# VENTANA PRINCIPAL: PANEL DE CONTROL
# ==========================================================
class WMMControlPanel(Gtk.ApplicationWindow):
    """
    Ventana principal de configuración de WMM.
    Permite gestionar fuentes de imágenes, favoritos, opciones de presentación, etc.
    """

    def __init__(self, app):
        super().__init__(application=app, title="WMM - " + _("Control Panel"))
        self.set_size_request(1205, 925)  # Tamaño mínimo: 3 cols × 2 filas de thumbnails
        self.set_position(Gtk.WindowPosition.CENTER)

        # ==========================================================
        # PROVEEDOR CSS
        # ==========================================================
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b"""
            .favorite-thumbnail {
                border: 2px solid green;
                border-radius: 4px;
                padding: 2px;
            }
            .favorites-panel {
                border: 2px solid green;
                border-radius: 4px;
            }
            .dnd-source {
                border: 2px solid red;
            }
            .monitor-frame {
                border: 2px solid black;
                background: rgba(0, 0, 0, 0.05);
            }
            .dnd-target {
                border-color: green;
                border-width: 2px;
            }
            .align-active {
                background-color: rgba(128, 128, 128, 0.3);
                border-radius: 3px;
                padding: 0px 2px;
            }
            .edit-aspects-box {
                border: 1px solid rgba(128, 128, 128, 0.4);
                border-radius: 4px;
                padding: 4px 4px;
            }
            .dnd-source .favorite-thumbnail {
                border-color: transparent;
            }
        """)

        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        # ==========================================================
        # INICIALIZACIÓN DE VARIABLES DE ESTADO
        # ==========================================================
        self.handler = ConfigHandler()
        self.backend = WMMBackend(self.handler)
        self.ie = ImageEngine(self.handler, None)  # None porque panel no usa MonitorManager
        self._loading = False
        self._first_h_item = None
        self._first_v_item = None
        self._busy_counter = 0
        self._monitor_switches = {}       # hash -> (Gtk.Switch, Gtk.Box)
        self._last_container_size = (0, 0)  # (width, height) del último resize que activó repintado
        self._monitor_display_names = {}  # nombres descriptivos para tooltips
        self._edit_monitor_widgets = {}  # EventBox del modo edición
        self._updating_switches = False  # Flag para evitar bucles al actualizar switches
        self._repaint_scheduled = False  # Evita múltiples repintados idle
        self._opened_in_debug = False
        self._thumbnails_loading = False # NUEVO: Evita cargas duplicadas de thumbnails
        self._sources_need_refresh = False
        self.restart_btn = None  # Se creará en _build_options_section

        # ==========================================================
        # ALTA DEL PANEL (PID + SEÑAL)
        # ==========================================================
        pid_path = os.path.join(self.handler.cache_dir, "pid_panel.pid")
        os.makedirs(os.path.dirname(pid_path), exist_ok=True)

        # Si ya existe un PID anterior, comprobar si sigue vivo
        if os.path.exists(pid_path):
            try:
                with open(pid_path, "r") as f:
                    content = f.read().strip()
                    if content:
                        old_pid = int(content)
                        os.kill(old_pid, 0)  # ¿sigue vivo?
                        print(f" [AVISO] Otro panel ya está corriendo (PID {old_pid}).")
                        # No abortamos: puede ser una instancia zombi. Sobrescribimos.
            except (OSError, ValueError):
                pass  # El proceso no existe, seguimos

        # Guardar el PID actual
        with open(pid_path, "w") as f:
            f.write(str(os.getpid()))
        print(f" [PANEL] PID {os.getpid()} registrado en {pid_path}")

        # Instalar manejador de señales
        signal.signal(signal.SIGUSR1, self._handle_panel_signal)
        print(" [PANEL] Manejador SIGUSR1 instalado.")

        # ==========================================================
        # CONTENEDOR RAÍZ
        # ==========================================================
        self.main_layout = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.main_layout.set_border_width(10)
        self.add(self.main_layout)

        # ==========================================================
        # COLUMNA IZQUIERDA: Opciones, Favoritos, Fuentes
        # ==========================================================
        self.left_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        self.left_col.set_size_request(350, -1)
        self.main_layout.pack_start(self.left_col, False, False, 0)

        self._build_options_section()
        self._build_favorites_section()
        self._build_sources_section()

        # Separador vertical entre la columna de opciones y la sección de monitores
        vsep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        self.main_layout.pack_start(vsep, False, False, 0)

        # ==========================================================
        # COLUMNA DERECHA: Monitores, Thumbnails
        # ==========================================================
        self.right_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        self.main_layout.pack_start(self.right_col, True, True, 0)

        self._build_monitors_section()

        # Separador entre la sección de Monitores y la de Thumbnails
        sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        #sep.set_margin_top(1)
        #sep.set_margin_bottom(1)
        self.right_col.pack_start(sep, False, False, 0)

        self._build_thumbnails_section()

        # ==========================================================
        # CARGA INICIAL DE DATOS Y SEÑALES
        # ==========================================================
        self.load_sources_into_treeview()
        self._load_settings()
        print(f">>> [DIAG] restart_btn visible={self.restart_btn.get_visible()}, _opened_in_debug={self._opened_in_debug}, debug_mode={self.backend.load_settings().get('debug_mode', 'no existe')}")
        self._load_presets()
        self._load_bookmarks_single()
        self._load_thumbnails()
        GLib.idle_add(self._load_monitors)

        self.connect("delete-event", self._on_delete_event)
        self.show_all()

    # ==========================================================
    # MÉTODOS AUXILIARES
    # ==========================================================
    def _create_section_label(self, text):
        label = Gtk.Label()
        label.set_markup(f"<span weight='bold' size='large'>{text}</span>")
        label.set_halign(Gtk.Align.START)
        return label

    @staticmethod
    def _set_btn_color(btn, hex_color):
        """Aplica un color hexadecimal a un Gtk.ColorButton."""
        rgba = Gdk.RGBA()
        rgba.parse(hex_color)
        btn.set_rgba(rgba)

    def _set_monitor_switches_sensitive(self, sensitive):
        """Activa o desactiva todos los switches de monitor."""
        for m_hash, (switch, hbox) in self._monitor_switches.items():
            switch.set_sensitive(sensitive)

    # ==========================================================
    # SECCIÓN: OPCIONES
    # ==========================================================
    def _build_options_section(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        # Cabecera: label Options (izquierda) + bloque Debug (derecha)
        hbox_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        hbox_header.pack_start(self._create_section_label(_("Options")), True, True, 0)

        # Bloque derecho: botón Reiniciar + label dinámico + switch Debug
        debug_block = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        self.restart_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        self.restart_btn.set_tooltip_text(_("Restart engine and panel"))
        self.restart_btn.connect("clicked", self._on_restart_clicked)
        self.restart_btn.set_visible(False)
        self.restart_btn.set_no_show_all(True)
        debug_block.pack_start(self.restart_btn, False, False, 0)

        self.view_log_btn = Gtk.Button.new_from_icon_name("text-x-generic", Gtk.IconSize.BUTTON)
        self.view_log_btn.set_tooltip_text(_("View error log"))
        self.view_log_btn.connect("clicked", self._on_view_log_clicked)
        self.view_log_btn.set_no_show_all(True)
        self.view_log_btn.set_visible(False)
        debug_block.pack_start(self.view_log_btn, False, False, 0)

        self.debug_mode_label = Gtk.Label(label=_("Debug mode OFF"))
        self.debug_mode_switch = Gtk.Switch(active=False)
        self.debug_mode_switch.connect("notify::active", self._on_debug_mode_changed)
        debug_block.pack_end(self.debug_mode_switch, False, False, 0)
        debug_block.pack_end(self.debug_mode_label, False, False, 0)
        # Forzar altura uniforme en el bloque Debug para evitar saltos al mostrar/ocultar botones
        debug_size_group = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.VERTICAL)
        debug_size_group.add_widget(self.restart_btn)
        debug_size_group.add_widget(self.view_log_btn)
        debug_size_group.add_widget(self.debug_mode_label)
        debug_size_group.add_widget(self.debug_mode_switch)

        hbox_header.pack_end(debug_block, False, False, 0)

        vbox.pack_start(hbox_header, False, False, 0)

        # --- Cambiar fondo al inicio ---
        self.persist_switch = Gtk.Switch(active=True, halign=Gtk.Align.END)
        self.persist_switch.set_tooltip_text(_("If enabled, the wallpaper is changed at startup; if disabled, the last wallpaper is kept."))
        self.persist_switch.connect("notify::active", self._on_persist_changed)
        hbox_persist = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        hbox_persist.pack_start(Gtk.Label(label=_("Change wallpaper on startup"), halign=Gtk.Align.START), True, True, 0)
        hbox_persist.pack_start(self.persist_switch, False, False, 0)

        # --- Modo Distribuido ---
        self.spanned_switch = Gtk.Switch(active=False, halign=Gtk.Align.END)
        self.spanned_switch.set_tooltip_text(_("Span image across all active screens (Only if more than one)"))
        self.spanned_switch.connect("notify::active", self._on_spanned_changed)
        hbox_spanned = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        hbox_spanned.pack_start(Gtk.Label(label=_("Spanned") + ":", halign=Gtk.Align.START), True, True, 0)
        hbox_spanned.pack_start(self.spanned_switch, False, False, 0)

        # --- Relación Aspecto ---
        hbox_aspect = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        hbox_aspect.pack_start(Gtk.Label(label=_("Picture aspect") + ":", halign=Gtk.Align.START), True, True, 0)
        self.aspect_combo = Gtk.ComboBoxText()
        for key, label in ConfigHandler.ASPECT_MODES.items():
            self.aspect_combo.append_text(_(label))
        self.aspect_combo.set_active(0)  # "fit" por defecto
        self.aspect_combo.connect("changed", self._on_aspect_changed)
        hbox_aspect.pack_start(self.aspect_combo, False, False, 0)

        # --- Efecto de Imagen ---
        self.image_effect_combo = Gtk.ComboBoxText()
        for key, label in ConfigHandler.IMAGE_EFFECT.items():
            self.image_effect_combo.append_text(_(label))
        self.image_effect_combo.set_active(0)  # "blur" por defecto
        self.image_effect_combo.connect("changed", self._on_image_effect_changed)
        hbox_img_effect = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        hbox_img_effect.pack_start(Gtk.Label(label=_("Image Effect:"), halign=Gtk.Align.START), True, True, 0)
        hbox_img_effect.pack_start(self.image_effect_combo, False, False, 0)

        # --- Efecto de Fondo ---
        self.back_effect_combo = Gtk.ComboBoxText()
        for key, label in ConfigHandler.BACK_EFFECT.items():
            self.back_effect_combo.append_text(_(label))
        self.back_effect_combo.set_active(0)  # "blur" por defecto
        self.back_effect_combo.connect("changed", self._on_back_effect_changed)
        hbox_back_effect = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        hbox_back_effect.pack_start(Gtk.Label(label=_("Background Effect:"), halign=Gtk.Align.START), True, True, 0)
        hbox_back_effect.pack_start(self.back_effect_combo, False, False, 0)

        # --- Color de fondo ---
        # Contenedor horizontal con label a la izquierda y controles a la derecha
        hbox_color = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        hbox_color.pack_start(Gtk.Label(label=_("Background color") + ":", halign=Gtk.Align.START), True, True, 0)

        self.bg_mode_combo = Gtk.ComboBoxText()
        for key, label in ConfigHandler.COLOR_MODES.items():
            self.bg_mode_combo.append_text(_(label))
        self.bg_mode_combo.set_active(0)
        self.bg_mode_combo.set_halign(Gtk.Align.END)
        self.bg_mode_combo.connect("changed", self._on_bg_mode_changed)

        self.bg_color_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.solid_color_btn = Gtk.ColorButton()
        self.solid_color_btn.set_tooltip_text(_("Background color"))
        self.solid_color_btn.connect("color-set", self._on_solid_color_changed)
        self.bg_color_box.pack_start(self.solid_color_btn, False, False, 0)

        self.grad_h_start_btn = Gtk.ColorButton()
        self.grad_h_start_btn.set_tooltip_text(_("Horizontal gradient start color"))
        self.grad_h_start_btn.connect("color-set", self._on_gradient_h_changed)
        self.grad_h_end_btn = Gtk.ColorButton()
        self.grad_h_end_btn.set_tooltip_text(_("Horizontal gradient end color"))
        self.grad_h_end_btn.connect("color-set", self._on_gradient_h_changed)

        self.grad_v_start_btn = Gtk.ColorButton()
        self.grad_v_start_btn.set_tooltip_text(_("Vertical gradient start color"))
        self.grad_v_start_btn.connect("color-set", self._on_gradient_v_changed)
        self.grad_v_end_btn = Gtk.ColorButton()
        self.grad_v_end_btn.set_tooltip_text(_("Vertical gradient end color"))
        self.grad_v_end_btn.connect("color-set", self._on_gradient_v_changed)

        # Empaquetar combo y botones en un box a la derecha
        color_controls_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        color_controls_box.pack_end(self.bg_mode_combo, False, False, 0)
        color_controls_box.pack_end(self.bg_color_box, False, False, 0)

        hbox_color.pack_end(color_controls_box, False, False, 0)

        # --- Presentación Diapositivas ---
        self.slideshow_switch = Gtk.Switch(active=True, halign=Gtk.Align.END)
        self.slideshow_switch.set_tooltip_text(_("Enable/Disable Timer"))
        self.slideshow_switch.connect("notify::active", self._on_slideshow_changed)
        hbox_slideshow = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        hbox_slideshow.pack_start(Gtk.Label(label=_("Slideshow"), halign=Gtk.Align.START), True, True, 0)
        hbox_slideshow.pack_start(self.slideshow_switch, False, False, 0)

        # --- Max. Intervalo (minutos) ---
        hbox_max = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        hbox_max.pack_start(Gtk.Label(label=_("Max. Frequency") + ": " + "(" + _("minutes") + ")", halign=Gtk.Align.START), True, True, 0)
        self.max_interval_spin = Gtk.SpinButton.new_with_range(1, 999, 1)
        self.max_interval_spin.set_value(60)
        self.max_interval_spin.connect("value-changed", self._on_max_interval_changed)
        self.max_interval_spin.connect("activate", lambda w: self.set_focus(None))
        hbox_max.pack_start(self.max_interval_spin, False, False, 0)

        # --- Rotación (minutos) ---
        hbox_rot = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        hbox_rot.pack_start(Gtk.Label(label=_("Slideshow every") + ": " + "(" + _("minutes") + ")", halign=Gtk.Align.START), True, True, 0)
        self.rotation_spin = Gtk.SpinButton.new_with_range(1, 99, 1)
        self.rotation_spin.set_value(15)
        self.rotation_spin.connect("value-changed", self._on_rotation_changed)
        self.rotation_spin.connect("activate", lambda w: self.set_focus(None))
        hbox_rot.pack_start(self.rotation_spin, False, False, 0)

        # --- Modo de rotación (Sync/Async) ---
        self.mode_switch = Gtk.Switch(active=True, halign=Gtk.Align.END)
        self.mode_switch.set_tooltip_text(_("Sync: All Screens change at once") + "\n" + _("Async: Change by turns"))
        self.mode_switch.connect("notify::active", self._on_mode_changed)
        self.mode_info_label = Gtk.Label(label="", halign=Gtk.Align.CENTER, margin_left=8)
        hbox_mode = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        hbox_mode.pack_start(Gtk.Label(label=_("Slideshow mode:"), halign=Gtk.Align.START), False, False, 0)
        hbox_mode.pack_start(self.mode_info_label, True, True, 0)
        hbox_mode.pack_start(self.mode_switch, False, False, 0)

        # ==========================================================
        # ORDEN DE EMPAQUETADO EN LA SECCIÓN OPCIONES
        # ==========================================================
        vbox.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0)
        vbox.pack_start(hbox_persist, False, False, 0)          # Cambiar fondo al inicio
        vbox.pack_start(hbox_spanned, False, False, 0)          # Modo Distribuido
        vbox.pack_start(hbox_aspect, False, False, 5)           # Relación Aspecto
        vbox.pack_start(hbox_img_effect, False, False, 0)       # Efecto de Imagen
        vbox.pack_start(hbox_back_effect, False, False, 0)      # Efecto de Fondo
        vbox.pack_start(hbox_color, False, False, 5)            # Color de fondo
        vbox.pack_start(hbox_slideshow, False, False, 0)        # Presentación Diapositivas
        vbox.pack_start(hbox_max, False, False, 0)              # Max. Intervalo
        vbox.pack_start(hbox_rot, False, False, 0)              # Rotación
        vbox.pack_start(hbox_mode, False, False, 0)             # Modo rotación

        self.left_col.pack_start(vbox, False, False, 0)
        self.left_col.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0)

    def _on_aspect_changed(self, combo):
        if self._loading:
            return
        index = combo.get_active()
        keys = list(ConfigHandler.ASPECT_MODES.keys())
        if 0 <= index < len(keys):
            mode = keys[index]
            self.backend.save_setting("wallpaper_mode", mode)
            self._notify_engine({"action": "apply_manual_selection"})
            if not self.backend.edit_mode_active:
                self._load_monitors()

    def _on_bg_mode_changed(self, combo):
        """Activa o desactiva los selectores de color según el modo elegido."""
        if self._loading:
            return
        index = combo.get_active()
        keys = list(ConfigHandler.COLOR_MODES.keys())
        if 0 <= index < len(keys):
            mode = keys[index]
            self.backend.save_setting("color_mode", mode)
            self._notify_engine({"action": "apply_manual_selection"})
            self._update_bg_color_buttons(mode)
            if not self.backend.edit_mode_active:
                self._load_monitors()

    def _update_bg_color_buttons(self, mode):
        """Muestra los selectores de color adecuados según el modo."""
        for widget in self.bg_color_box.get_children():
            self.bg_color_box.remove(widget)

        if mode == "solid_color":
            self.bg_color_box.pack_start(self.solid_color_btn, False, False, 0)
        elif mode == "gradient_h":
            self.bg_color_box.pack_start(self.grad_h_start_btn, False, False, 0)
            self.bg_color_box.pack_start(self.grad_h_end_btn, False, False, 4)
        elif mode == "gradient_v":
            self.bg_color_box.pack_start(self.grad_v_start_btn, False, False, 0)
            self.bg_color_box.pack_start(self.grad_v_end_btn, False, False, 4)
        self.bg_color_box.show_all()

    def _on_solid_color_changed(self, button):
        """Guarda el color sólido seleccionado en settings.json."""
        if self._loading:
            return
        color = button.get_rgba()
        hex_color = "#{:02X}{:02X}{:02X}".format(
            int(color.red * 255), int(color.green * 255), int(color.blue * 255)
        )
        self.backend.save_setting("solid_color", hex_color)
        self._notify_engine({"action": "apply_manual_selection"})
        if not self.backend.edit_mode_active:
            self._load_monitors()

    def _on_gradient_h_changed(self, button):
        """Guarda los colores del degradado horizontal en settings.json."""
        if self._loading:
            return
        start = self.grad_h_start_btn.get_rgba()
        end = self.grad_h_end_btn.get_rgba()
        hex_start = "#{:02X}{:02X}{:02X}".format(int(start.red*255), int(start.green*255), int(start.blue*255))
        hex_end = "#{:02X}{:02X}{:02X}".format(int(end.red*255), int(end.green*255), int(end.blue*255))
        self.backend.save_setting("gradient_h", [hex_start, hex_end])
        self._notify_engine({"action": "apply_manual_selection"})
        if not self.backend.edit_mode_active:
            self._load_monitors()

    def _on_gradient_v_changed(self, button):
        """Guarda los colores del degradado vertical en settings.json."""
        if self._loading:
            return
        start = self.grad_v_start_btn.get_rgba()
        end = self.grad_v_end_btn.get_rgba()
        hex_start = "#{:02X}{:02X}{:02X}".format(int(start.red*255), int(start.green*255), int(start.blue*255))
        hex_end = "#{:02X}{:02X}{:02X}".format(int(end.red*255), int(end.green*255), int(end.blue*255))
        self.backend.save_setting("gradient_v", [hex_start, hex_end])
        self._notify_engine({"action": "apply_manual_selection"})
        if not self.backend.edit_mode_active:
            self._load_monitors()

    def _on_slideshow_changed(self, switch, param):
        if self._loading:
            return
        self.backend.save_setting("slideshow_enabled", switch.get_active())

    def _on_mode_changed(self, switch, param):
        if self._loading:
            return
        mode = "sync" if switch.get_active() else "async"
        self.backend.save_setting("slideshow_mode", mode)
        self._update_mode_info_label()

    def _on_debug_mode_changed(self, switch, param):
        """Actualiza el label, guarda el estado y refleja el modo Debug en la UI."""
        if self._loading:
            return
        debug_mode = switch.get_active()
        self.debug_mode_label.set_text(_("Debug mode ON") if debug_mode else _("Debug mode OFF"))
        self.backend.save_setting("debug_mode", debug_mode)
        # Actualizar título de la ventana
        title = _("Control Panel")
        if debug_mode:
            title += " (DEBUG)"
        self.set_title(title)
        # Mostrar u ocultar el botón Reiniciar
        if hasattr(self, 'restart_btn'):
            if self._opened_in_debug:
                self.restart_btn.set_visible(True)  # Siempre visible si se abrió en debug
            else:
                self.restart_btn.set_visible(debug_mode)
        # Mostrar u ocultar el botón de log
        if hasattr(self, 'view_log_btn'):
            if self._opened_in_debug:
                self.view_log_btn.set_visible(True)
            else:
                self.view_log_btn.set_visible(debug_mode)

    def _on_restart_clicked(self, widget):
        """Reinicia el motor y el panel en el modo correspondiente al switch Debug."""
        debug_mode = self.debug_mode_switch.get_active()
        # Rutas de los scripts
        engine_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
        panel_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "panel.py")
        # Matar el motor actual usando su PID (más agresivo)
        pid_path = os.path.join(self.handler.cache_dir, "pid_main.pid")
        if os.path.exists(pid_path):
            try:
                with open(pid_path, "r") as f:
                    old_pid = int(f.read().strip())
                os.kill(old_pid, signal.SIGKILL)  # SIGKILL para asegurar
                time.sleep(0.5)  # Esperar un poco más
                os.remove(pid_path)
            except (OSError, ValueError, FileNotFoundError):
                pass
        # Lanzar el nuevo motor antes de cerrar el panel
        if debug_mode:
            subprocess.Popen(
                ["gnome-terminal", "--", "bash", "-c",
                 f"WMM_DEBUG=1 python3 {engine_path}"],
                start_new_session=True,
                env=os.environ.copy()
            )
        else:
            subprocess.Popen(
                ["python3", engine_path],
                start_new_session=True,
                env=os.environ.copy(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        # Pequeña pausa para que el motor arranque
        time.sleep(0.5)
        # Limpiar PID del panel y cerrar
        panel_pid_path = os.path.join(self.handler.cache_dir, "pid_panel.pid")
        if os.path.exists(panel_pid_path):
            try:
                os.remove(panel_pid_path)
            except OSError:
                pass
        app = self.get_application()
        if app:
            app.quit()  # Cerrar sin timeout, con un pequeño retraso ya dado por el sleep

    def _on_view_log_clicked(self, widget):
        """Muestra el archivo de log de errores en un diálogo."""
        log_path = os.path.join(self.handler.data_dir, "error_log.txt")
        if not os.path.exists(log_path):
            self._show_warning_dialog(_("No errors logged yet."))
            return
        with open(log_path, "r", encoding="utf-8") as f:
            content = f.read()
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=_("Error Log")
        )
        dialog.format_secondary_text(content if content else _("No errors logged yet."))
        dialog.run()
        dialog.destroy()

    def _update_mode_info_label(self):
        """Actualiza el label informativo del modo según el estado de los switches."""
        sync_active = self.mode_switch.get_active()
        fav_only = self.fav_rotation_switch.get_active()
        if sync_active:
            mode_text = _("Synchronized")
            scope = _("Presets") if fav_only else _("All")
        else:
            mode_text = _("Asynchronous")
            scope = _("Favorites") if fav_only else _("Single")
        self.mode_info_label.set_text(f"{mode_text} ({scope})")

    def _on_max_interval_changed(self, spin):
        if self._loading:
            return
        max_val = spin.get_value_as_int()
        self.backend.save_setting("slideshow_max_interval", max_val)
        settings = self.backend.load_settings()
        if settings["slideshow_interval"] > max_val:
            self.backend.save_setting("slideshow_interval", max_val)
            self.rotation_spin.set_value(max_val)

    def _on_rotation_changed(self, spin):
        if self._loading:
            return
        settings = self.backend.load_settings()
        rot_val = spin.get_value_as_int()
        max_val = settings.get("slideshow_max_interval", 60)
        if rot_val > max_val:
            max_val = rot_val
            self.backend.save_setting("slideshow_max_interval", max_val)
            self._loading = True
            self.max_interval_spin.set_value(max_val)
            self._loading = False
        self.backend.save_setting("slideshow_interval", rot_val)

    # ==========================================================
    # SECCIÓN: FAVORITOS
    # ==========================================================
    def _build_favorites_section(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        header_box.pack_start(self._create_section_label(_("Favorites")), True, True, 0)
        self.fav_rotation_switch = Gtk.Switch(active=False)
        self.fav_rotation_switch.set_tooltip_text(_("Slideshow only among favorite images"))
        self.fav_rotation_switch.connect("notify::active", self._on_fav_rotation_changed)
        header_box.pack_end(self.fav_rotation_switch, False, False, 0)
        vbox.pack_start(header_box, False, False, 0)

        self.favorites_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.favorites_container.get_style_context().add_class("favorites-panel")

        self.paned = Gtk.HPaned()

        # --- Panel izquierdo: PRESETS ---
        left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        presets_header = Gtk.Button(label=_("Presets"), relief=Gtk.ReliefStyle.NONE)
        presets_header.connect("clicked", self._expand_left_panel)
        left_box.pack_start(presets_header, False, False, 0)

        self.presets_model = Gtk.TreeStore(str, str, bool)
        self.presets_tree = Gtk.TreeView(model=self.presets_model)
        self.presets_tree.set_headers_visible(False)
        self.presets_tree.connect("row-activated", self._on_preset_row_activated)

        col_name = Gtk.TreeViewColumn(_("Name"))
        renderer_text = Gtk.CellRendererText()
        col_name.pack_start(renderer_text, True)
        col_name.set_cell_data_func(renderer_text, self._render_preset_name)
        self.presets_tree.append_column(col_name)

        renderer_text.connect("edited", self._on_preset_renamed)
        self.presets_tree.connect("button-press-event", self._on_preset_tree_click)

        self.scrolled_left = Gtk.ScrolledWindow()
        self.scrolled_left.set_min_content_height(150)
        self.scrolled_left.add(self.presets_tree)
        left_box.pack_start(self.scrolled_left, True, True, 0)

        ctrl_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        del_btn = Gtk.Button.new_from_icon_name("user-trash", Gtk.IconSize.BUTTON)
        del_btn.set_tooltip_text(_("Delete selected preset/image"))
        del_btn.connect("clicked", self._on_delete_preset_clicked)
        ctrl_box.pack_end(del_btn, False, False, 0)
        left_box.pack_start(ctrl_box, False, False, 0)

        self.paned.pack1(left_box, True, False)

        # --- Panel derecho: Favoritos ---
        right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        single_header = Gtk.Button(label=_("Favorites"), relief=Gtk.ReliefStyle.NONE)
        single_header.connect("clicked", self._expand_right_panel)
        right_box.pack_start(single_header, False, False, 0)

        self.bookmarks_single_model = Gtk.ListStore(str, str)
        self.bookmarks_single_tree = Gtk.TreeView(model=self.bookmarks_single_model)
        self.bookmarks_single_tree.set_headers_visible(False)
        self.bookmarks_single_tree.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)
        self.bookmarks_single_tree.connect("row-activated", self._on_bookmark_single_row_activated)

        col_single = Gtk.TreeViewColumn(_("Name"))
        renderer_single = Gtk.CellRendererText()
        col_single.pack_start(renderer_single, True)
        col_single.set_cell_data_func(renderer_single, self._render_bookmark_single)
        self.bookmarks_single_tree.append_column(col_single)

        self.bookmarks_single_tree.connect("button-press-event", self._on_single_tree_click)

        self.scrolled_right = Gtk.ScrolledWindow()
        self.scrolled_right.set_min_content_height(150)
        self.scrolled_right.add(self.bookmarks_single_tree)
        right_box.pack_start(self.scrolled_right, True, True, 0)

        btn_box_right = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        del_btn_right = Gtk.Button.new_from_icon_name("user-trash", Gtk.IconSize.BUTTON)
        del_btn_right.set_tooltip_text(_("Delete selected image from favorites"))
        del_btn_right.connect("clicked", self._on_delete_single_clicked)
        btn_box_right.pack_end(del_btn_right, False, False, 0)
        right_box.pack_start(btn_box_right, False, False, 0)

        self.paned.pack2(right_box, True, False)

        self.favorites_container.pack_start(self.paned, True, True, 0)
        vbox.pack_start(self.favorites_container, True, True, 0)
        self.left_col.pack_start(vbox, True, True, 0)

    # --- Métodos de alternancia de paneles ---
    def _expand_left_panel(self, widget):
        """Alterna el panel izquierdo entre el 80 % y el 50 % del ancho."""
        if self.paned.get_allocated_width() > 0:
            half = self.paned.get_allocated_width() // 2
            current = self.paned.get_position()
            if current > half * 1.4:
                self.paned.set_position(half)
            else:
                self.paned.set_position(int(self.paned.get_allocated_width() * 0.8))

    def _expand_right_panel(self, widget):
        """Alterna el panel derecho entre el 20 % y el 50 % del ancho."""
        if self.paned.get_allocated_width() > 0:
            half = self.paned.get_allocated_width() // 2
            current = self.paned.get_position()
            if current < half * 0.6:
                self.paned.set_position(half)
            else:
                self.paned.set_position(int(self.paned.get_allocated_width() * 0.2))

    # Panel izquierdo
    def _load_presets(self):
        self.presets_model.clear()
        bookmarks = self.backend.load_json("bookmarks")
        for preset_name, monitors in bookmarks.items():
            parent_iter = self.presets_model.append(None, [preset_name, "", True])
            for m_hash, entry in monitors.items():
                # Saltar claves de configuración del preset (prefijos __)
                if m_hash.startswith("__"):
                    continue
                # Soportar formato nuevo (dict con path/active) y antiguo (string)
                if isinstance(entry, dict):
                    img_path = entry.get("path", "") or ""
                    active = entry.get("active", True)
                else:
                    img_path = entry or ""
                    active = True

                display_name = os.path.basename(img_path) if img_path else "(" + _("Empty") + ")"
                self.presets_model.append(parent_iter, [display_name, img_path, False])

    def _render_preset_name(self, column, cell, model, iter, data):
        name = model.get_value(iter, 0)
        is_preset = model.get_value(iter, 2)
        cell.set_property("text", name)
        cell.set_property("weight", 700 if is_preset else 400)
        cell.set_property("editable", is_preset)
        if not is_preset and model.get_value(iter, 1) == "":
            cell.set_property("style", Pango.Style.ITALIC)
        else:
            cell.set_property("style", Pango.Style.NORMAL)

    def _on_preset_renamed(self, renderer, path, new_name):
        iter = self.presets_model.get_iter(path)
        if not iter:
            return
        old_name = self.presets_model.get_value(iter, 0)
        is_preset = self.presets_model.get_value(iter, 2)
        if not is_preset or old_name == new_name:
            return
        bookmarks = self.backend.load_json("bookmarks")
        if new_name in bookmarks:
            self._show_warning_dialog(_("A Preset with that name already exists!"))
            return
        bookmarks[new_name] = bookmarks.pop(old_name)
        self.backend.save_json("bookmarks", bookmarks)
        self._load_presets()
        self.handler.sync_bookmarks_flat_list()
        self.handler.refresh_history_metadata()

    def _on_preset_tree_click(self, treeview, event):
        if event.button != 3:
            return
        path = treeview.get_path_at_pos(int(event.x), int(event.y))
        if not path:
            return
        model = treeview.get_model()
        iter = model.get_iter(path[0])
        if not iter:
            return
        name = model.get_value(iter, 0)
        is_preset = model.get_value(iter, 2)

        menu = Gtk.Menu()
        if is_preset:
            item = Gtk.MenuItem(label=_("Delete preset"))
            item.connect("activate", self._delete_preset, name)
            item_load = Gtk.MenuItem(label=_("Load on screens"))
            item_load.connect("activate", self._load_preset_to_monitors, name)
            menu.append(item_load)
        else:
            img_path = model.get_value(iter, 1)
            # Si el preset está en nuevo formato, img_path será un dict; extraer la ruta real
            if isinstance(img_path, dict):
                img_path = img_path.get("path", "")
            item = Gtk.MenuItem(label=_("Delete image"))
            item.connect("activate", self._delete_image_from_preset, iter)
        menu.append(item)
        menu.show_all()
        menu.popup(None, None, None, None, event.button, event.time)

    def _delete_preset(self, widget, preset_name):
        if self.handler.delete_bookmark(preset_name):
            self._load_presets()

    def _delete_image_from_preset(self, widget, iter):
        """Elimina la imagen (ruta) de una entrada de preset, manteniendo el hash y el estado active."""
        model = self.presets_model
        img_path = model.get_value(iter, 1)
        # Extraer la ruta real según el formato
        if isinstance(img_path, dict):
            img_path_real = img_path.get("path", "")
        else:
            img_path_real = img_path if img_path else ""

        parent_iter = model.iter_parent(iter)
        if not parent_iter:
            return
        preset_name = model.get_value(parent_iter, 0)
        bookmarks = self.backend.load_json("bookmarks")
        if preset_name in bookmarks:
            bm = bookmarks[preset_name]
            for hash, entry in list(bm.items()):
                # Obtener la ruta de la entrada para comparar
                if isinstance(entry, dict):
                    entry_path = entry.get("path", "")
                else:
                    entry_path = entry if entry else ""
                if entry_path == img_path_real:
                    # Mantener el hash y el estado active, solo vaciar la ruta
                    if isinstance(entry, dict):
                        entry["path"] = ""
                    else:
                        # Si por algún motivo es string antiguo, lo convertimos
                        bm[hash] = {"path": "", "active": True}
                    break
            # No eliminamos el preset aunque todos los paths queden vacíos
            bookmarks[preset_name] = bm
            self.backend.save_json("bookmarks", bookmarks)
            # También sincronizar la lista plana y metadatos
            self.handler.sync_bookmarks_flat_list()
            self.handler.refresh_history_metadata()
            # Actualizar directamente la fila en el modelo en lugar de recargar todo
            model.set_value(iter, 0, _("(empty)"))
            model.set_value(iter, 1, "")  # path vacío

    def _on_preset_row_activated(self, treeview, path, column):
        """Doble clic en un preset o imagen: si es imagen, abrir con visor."""
        model = treeview.get_model()
        tree_iter = model.get_iter(path)
        is_preset = model.get_value(tree_iter, 2)
        if not is_preset:
            img_path = model.get_value(tree_iter, 1)
            if isinstance(img_path, dict):
                img_path = img_path.get("path", "")
            if img_path:
                if os.path.exists(img_path):
                    self.handler.open_in_file_manager(img_path)
                else:
                    print(f" [AVISO] La imagen no existe en disco: {img_path}")

    def _load_preset_to_monitors(self, widget, preset_name):
        """Carga las imágenes de un preset en los monitores virtuales para edición."""
        # 1. Activar modo edición si no lo está (esto limpia la sesión y prepara la UI)
        if not self.backend.edit_mode_active:
            self.edit_mode_btn.set_active(True)

        # 2. Delegar en el backend la carga de datos del preset
        preset_monitors = self.backend.load_preset_for_edit(preset_name)
        if preset_monitors is None:
            return

        # 3. Actualizar la UI con el nombre del preset
        self._current_preset_name = preset_name
        self.fav_checkbox.set_active(True)

        # 4. Sincronizar la UI de edición con los valores temporales del backend
        if self.backend.edit_temp_spanned_enabled is not None and hasattr(self, 'spanned_switch_edit'):
            self.spanned_switch_edit.set_active(self.backend.edit_temp_spanned_enabled)
        if self.backend.edit_temp_image_effect is not None and hasattr(self, 'image_effect_combo_edit'):
            keys = list(ConfigHandler.IMAGE_EFFECT.keys())
            index = keys.index(self.backend.edit_temp_image_effect) if self.backend.edit_temp_image_effect in keys else 0
            self.image_effect_combo_edit.set_active(index)
        if self.backend.edit_temp_wp_scope is not None and hasattr(self, 'back_effect_combo_edit'):
            keys = list(ConfigHandler.BACK_EFFECT.keys())
            index = keys.index(self.backend.edit_temp_wp_scope) if self.backend.edit_temp_wp_scope in keys else 0
            self.back_effect_combo_edit.set_active(index)

        # 5. Pintar los monitores virtuales con los datos del preset
        self._load_monitors_edit()
        self._load_preset_to_edit_monitors(preset_monitors)

        # 6. Sincronizar los switches de activación
        self._build_monitor_switches()

        # 7. Actualizar la etiqueta de edición con el nombre del preset
        self.edit_preset_label.set_markup("<b>" + _("Editing") + ":" + "\n" + preset_name + "</b>")
        self.edit_preset_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.edit_preset_label.set_max_width_chars(24)
        self.edit_label_stack.set_visible_child_name("edit_preset")

        print(f" [Edición] Preset cargado en edición: {preset_name}")

    def _on_delete_preset_clicked(self, button):
        selection = self.presets_tree.get_selection()
        model, iter = selection.get_selected()
        if not iter:
            return
        is_preset = model.get_value(iter, 2)
        if is_preset:
            self._delete_preset(None, model.get_value(iter, 0))
        else:
            self._delete_image_from_preset(None, iter)

    def _show_warning_dialog(self, message):
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.OK,
            text=message
        )
        dialog.run()
        dialog.destroy()

    # Panel derecho
    def _load_bookmarks_single(self):
        self.bookmarks_single_model.clear()
        flat_list = self.backend.load_json("bookmarks_single")
        for entry in flat_list:
            if len(entry) >= 4 and entry[0]:
                name = os.path.basename(entry[0])
                self.bookmarks_single_model.append([name, entry[0]])

    def _render_bookmark_single(self, column, cell, model, iter, data):
        cell.set_property("text", model.get_value(iter, 0))

    def _on_bookmark_single_row_activated(self, treeview, path, column):
        """Doble clic en un favorito individual: abrir con visor."""
        model = treeview.get_model()
        tree_iter = model.get_iter(path)
        img_path = model.get_value(tree_iter, 1)
        if img_path and os.path.exists(img_path):
            self.handler.open_in_file_manager(img_path)
        else:
            print(f" [AVISO] Imagen no encontrada: {img_path}")

    def _on_single_tree_click(self, treeview, event):
        if event.button != 3:
            return

        # Obtener la selección actual ANTES de que GTK la modifique
        selection = treeview.get_selection()
        model, selected_paths = selection.get_selected_rows()

        # Si ya hay múltiples filas seleccionadas, evitar que el clic derecho
        # anule la selección. Para ello, detenemos la propagación del evento.
        if len(selected_paths) > 1:
            treeview.stop_emission_by_name('button-press-event')
        # Si solo hay una o ninguna, dejamos que GTK seleccione la fila bajo el cursor

        # Volver a obtener la selección (ahora ya definitiva)
        selection = treeview.get_selection()
        model, selected_paths = selection.get_selected_rows()
        if not selected_paths:
            return

        # Recopilar las rutas de todas las imágenes seleccionadas
        img_paths = []
        for path in selected_paths:
            tree_iter = model.get_iter(path)
            img_path = model.get_value(tree_iter, 1)  # columna 1 = ruta completa
            img_paths.append(img_path)

        # Construir el menú contextual
        menu = Gtk.Menu()
        if len(img_paths) == 1:
            label = _("Delete")
        else:
            label = _("Delete") + " " + str(len(img_paths)) + " " + _("images")
        item = Gtk.MenuItem(label=label)
        # Conectar la acción para eliminar todas las rutas seleccionadas
        item.connect('activate', lambda w: (
            [self._delete_bookmark_single(p) for p in img_paths],
            self._load_bookmarks_single()
        ))
        menu.append(item)
        menu.show_all()
        menu.popup(None, None, None, None, event.button, event.time)

    def _delete_bookmark_single(self, img_path):
        """Elimina una entrada de la lista plana de favoritos dada su ruta completa."""
        flat_list = self.backend.load_json("bookmarks_single")
        new_list = [entry for entry in flat_list if entry[0] != img_path]
        if len(new_list) != len(flat_list):
            self.backend.save_json("bookmarks_single", new_list)
            self.handler.refresh_history_metadata()

    def _on_delete_single_clicked(self, button):
        """Borra todas las imágenes seleccionadas en la lista plana de favoritos."""
        selection = self.bookmarks_single_tree.get_selection()
        model, paths = selection.get_selected_rows()
        # Recorrer de atrás hacia delante para no invalidar los paths al borrar
        for path in reversed(paths):
            tree_iter = model.get_iter(path)
            img_path = model.get_value(tree_iter, 1)  # la ruta completa está en la columna 1
            self._delete_bookmark_single(img_path)
        # Recargar la lista para reflejar los cambios
        self._load_bookmarks_single()

    def _on_fav_rotation_changed(self, switch, param):
        if self._loading:
            return
        self.backend.save_setting("slideshow_bookmark", switch.get_active())
        self._update_mode_info_label()

    def _on_persist_changed(self, switch, param):
        if self._loading:
            return
        # Guardar directamente el estado del switch: True = cambiar al inicio, False = mantener
        self.backend.save_setting("persist_on_reboot", not switch.get_active())

    def _on_spanned_changed(self, switch, param):
        """Activa o desactiva el modo Distribuido (spanned)."""
        if self._loading:
            return
        self.backend.save_setting("spanned_enabled", switch.get_active())
        self._notify_engine({"action": "apply_manual_selection"})
        self._set_monitor_switches_sensitive(not switch.get_active())
        if not self.backend.edit_mode_active:
            self._load_monitors()

    def _on_image_effect_changed(self, combo):
        """Guarda el efecto de imagen seleccionado y actualiza en tiempo real."""
        if self._loading:
            return
        keys = list(ConfigHandler.IMAGE_EFFECT.keys())
        index = combo.get_active()
        if 0 <= index < len(keys):
            self.backend.save_setting("wallpaper_effect", keys[index])
            self._notify_engine({"action": "apply_manual_selection"})
            if not self.backend.edit_mode_active:
                self._load_monitors()

    def _on_back_effect_changed(self, combo):
        """Guarda el efecto de fondo seleccionado."""
        if self._loading:
            return
        keys = list(ConfigHandler.BACK_EFFECT.keys())
        index = combo.get_active()
        if 0 <= index < len(keys):
            self.backend.save_setting("wallpaper_effect_scope", keys[index])
            self._notify_engine({"action": "apply_manual_selection"})
            if not self.backend.edit_mode_active:
                self._load_monitors()

    def _on_spanned_edit_changed(self, switch, param):
        """Guarda el estado temporal de Distribuido en modo edición."""
        if self._loading:
            return
        self.backend.edit_temp_spanned_enabled = switch.get_active()
        if self.backend.edit_mode_active and self.backend.edit_active_session:
            self._updating_switches = True
            self._load_preset_to_edit_monitors(self.backend.edit_active_session)
            self._updating_switches = False

    def _on_image_effect_edit_changed(self, combo):
        if self._loading:
            return
        keys = list(ConfigHandler.IMAGE_EFFECT.keys())
        index = combo.get_active()
        if 0 <= index < len(keys):
            self.backend.edit_temp_image_effect = keys[index]
            if self.backend.edit_mode_active and self.backend.edit_active_session:
                self._updating_switches = True
                self._load_preset_to_edit_monitors(self.backend.edit_active_session)
                self._updating_switches = False

    # ==========================================================
    # SECCIÓN: FUENTES DE IMÁGENES
    # ==========================================================
    def _build_sources_section(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        vbox.pack_start(self._create_section_label(_("Image Sources")), False, False, 0)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_min_content_height(150)

        self.sources_model = Gtk.TreeStore(str, str, str, bool, bool, bool)
        self.sources_tree = Gtk.TreeView(model=self.sources_model)
        self.sources_tree.connect("row-activated", self._on_source_row_activated)

        col_name = Gtk.TreeViewColumn(_("Source"))
        ri, rt = Gtk.CellRendererPixbuf(), Gtk.CellRendererText()
        col_name.pack_start(ri, False)
        col_name.pack_start(rt, True)
        col_name.set_cell_data_func(ri, self._render_source_icon)
        col_name.set_cell_data_func(rt, self._render_source_text)
        col_name.set_expand(True)
        self.sources_tree.append_column(col_name)

        renderer_rec = Gtk.CellRendererToggle()
        renderer_rec.connect("toggled", self.on_recursive_toggled)
        col_rec = Gtk.TreeViewColumn(_("Recursive"), renderer_rec, active=4)
        col_rec.set_cell_data_func(renderer_rec, self._hide_checkbox_in_children)
        self.sources_tree.append_column(col_rec)
        # self.sources_tree.set_tooltip_text("Activer/Desarctivar recursividad en Carpetas")

        self.sources_tree.connect("button-press-event", self.on_tree_button_press)
        scrolled.add(self.sources_tree)
        vbox.pack_start(scrolled, True, True, 0)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)

        self.refresh_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        self.refresh_btn.set_tooltip_text(_("Resync Image Sources"))
        self.refresh_btn.connect("clicked", self.on_refresh_sources_clicked)
        btn_box.pack_start(self.refresh_btn, False, False, 0)

        self.center_stack = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.scan_progress = Gtk.ProgressBar()
        self.scan_progress.set_no_show_all(True)
        self.scan_progress.hide()
        self.scan_progress.set_margin_start(15)
        self.scan_progress.set_margin_end(15)
        self.scan_progress.set_valign(Gtk.Align.CENTER)
        self.btn_spacer = Gtk.Box()
        self.center_stack.pack_start(self.scan_progress, True, True, 0)
        self.center_stack.pack_start(self.btn_spacer, True, True, 0)
        btn_box.pack_start(self.center_stack, True, True, 0)

        self.add_btn = Gtk.Button.new_from_icon_name("folder-new", Gtk.IconSize.BUTTON)
        self.add_btn.set_tooltip_text(_("Add Image Source"))
        self.add_btn.connect("clicked", self.on_add_source_clicked)
        self.del_btn = Gtk.Button.new_from_icon_name("user-trash", Gtk.IconSize.BUTTON)
        self.del_btn.set_tooltip_text(_("Delete Image Source"))
        self.del_btn.connect("clicked", self.on_remove_source_clicked)

        btn_box.pack_end(self.del_btn, False, False, 0)
        btn_box.pack_end(self.add_btn, False, False, 5)

        vbox.pack_start(btn_box, False, False, 0)
        self.left_col.pack_start(vbox, True, True, 0)

    def load_sources_into_treeview(self):
        self.sources_model.clear()
        sources_data = self.backend.load_json("sources").get("sources", [])
        index_data = self.backend.load_json("index")

        for s in sources_data:
            root_path = s.get('path')
            if not root_path or s.get('type') == 'virtual':
                continue

            root_name = s.get('name', os.path.basename(root_path))
            is_recursive = s.get('recursive', False)

            index_info = index_data.get(root_path)
            root_active = True
            if isinstance(index_info, list) and len(index_info) > 1:
                root_active = index_info[1]
            else:
                root_active = s.get('active', True)

            parent_iter = self.sources_model.append(None, [
                "", root_name, root_path, root_active, is_recursive, True
            ])

            prefix = root_path if root_path.endswith(os.sep) else root_path + os.sep
            sub_paths = sorted([p for p in index_data if p.startswith(prefix)])
            path_to_iter = {root_path: parent_iter}

            for sub in sub_paths:
                parent_path = os.path.dirname(sub)
                if parent_path in path_to_iter:
                    sub_info = index_data.get(sub, [0, True])
                    sub_active = sub_info[1] if isinstance(sub_info, list) and len(sub_info) > 1 else True
                    current_iter = self.sources_model.append(path_to_iter[parent_path], [
                        "", os.path.basename(sub), sub, sub_active, False, False
                    ])
                    path_to_iter[sub] = current_iter

        print(" >>> [SISTEMA] Vista de fuentes reconstruida.")
        self._auto_expand_sources()

    def _auto_expand_sources(self):
        model = self.sources_model
        parent_iter = model.get_iter_first()
        while parent_iter:
            path_str = model.get_value(parent_iter, 2)
            if model.get_value(parent_iter, 5):
                state = self.handler.get_children_state(path_str)
                if state in ("all_active", "mixed"):
                    tree_path = model.get_path(parent_iter)
                    if tree_path:
                        self.sources_tree.expand_row(tree_path, open_all=False)
            parent_iter = model.iter_next(parent_iter)

    def _hide_checkbox_in_children(self, column, cell, model, iter, data):
        is_raiz = model.get_value(iter, 5)
        cell.set_property("visible", is_raiz)
        cell.set_property("activatable", is_raiz)

    def on_recursive_toggled(self, widget, path):
        tree_iter = self.sources_model.get_iter(path)
        current_val = self.sources_model.get_value(tree_iter, 4)
        new_val = not current_val
        self.sources_model.set_value(tree_iter, 4, new_val)
        path_disk = self.sources_model.get_value(tree_iter, 2)
        if hasattr(self.handler, 'update_source_recursive'):
            self.handler.update_source_recursive(path_disk, new_val)
        self.sources_tree.queue_draw()

    def _render_source_icon(self, column, cell, model, iter, data):
        is_active = model.get_value(iter, 3)
        is_recursive = model.get_value(iter, 4)
        is_raiz = model.get_value(iter, 5)
        icon = "folder-remote" if (is_raiz and is_recursive) else "folder"
        cell.set_property("icon-name", icon)
        cell.set_property("sensitive", is_active)

    def _render_source_text(self, column, cell, model, iter, data):
        text = model.get_value(iter, 1)
        is_active = model.get_value(iter, 3)
        cell.set_property("text", text)
        cell.set_property("sensitive", is_active)

    def on_tree_button_press(self, treeview, event):
        if event.button == 3:
            selection = treeview.get_selection()
            model, iter = selection.get_selected()
            if iter:
                path = model.get_value(iter, 2)
                self.show_context_menu(path, iter, event)
        return False

    def _get_parent_source(self, path):
        sources = self.backend.load_json("sources").get("sources", [])
        for s in sources:
            root = s.get("path")
            if root and path.startswith(root):
                return s
        return None

    def _auto_update_recursive(self, parent_path):
        children_state = self.handler.get_children_state(parent_path)
        new_recursive = children_state != "all_inactive"
        sources = self.backend.load_json("sources").get("sources", [])
        for s in sources:
            if s.get("path") == parent_path and s.get("type") == "physical":
                if s.get("recursive") != new_recursive:
                    s["recursive"] = new_recursive
                    self.backend.save_json("sources", {"sources": sources})
                    self.load_sources_into_treeview()
                    print(f" >>> [UI] Recursividad auto-ajustada: '{parent_path}' -> recursive={new_recursive}")
                break

    def _on_source_row_activated(self, treeview, path, column):
        model = treeview.get_model()
        iter = model.get_iter(path)
        folder_path = model.get_value(iter, 2)
        if folder_path:
            self.handler.open_in_file_manager(folder_path)

    def _increment_busy(self):
        self._busy_counter += 1
        if self._busy_counter == 1:
            self._set_sources_sensitive(False)

    def _decrement_busy(self):
        if self._busy_counter == 0:
            return
        self._busy_counter -= 1
        if self._busy_counter <= 0:
            self._busy_counter = 0
            self._set_sources_sensitive(True)

    def _set_sources_sensitive(self, sensitive):
        self.sources_tree.set_sensitive(sensitive)
        if hasattr(self, 'refresh_btn'):
            self.refresh_btn.set_sensitive(sensitive)
        if hasattr(self, 'add_btn'):
            self.add_btn.set_sensitive(sensitive)
        if hasattr(self, 'del_btn'):
            self.del_btn.set_sensitive(sensitive)

    def _notify_engine(self, action=None):
        if action is None:
            action = {"action": "force_rotation"}
        self.backend.notify_engine(action)

    def _on_sync_folder_start(self, folder_path):
        pass

    def _on_sync_progress(self, current, total):
        if total > 0:
            fraction = current / total
            self.scan_progress.set_fraction(fraction)
            self.scan_progress.set_text(_("Scanning") + " " + str(current) + "/" + str(total) + " " + _("folders") + "...")
        if current >= total:
            self._decrement_busy()
            self._set_progress_active(False)
            if self._sources_need_refresh:
                self.load_sources_into_treeview()
                self._sources_need_refresh = False
            GLib.idle_add(self._load_thumbnails)

    def show_context_menu(self, path, iter, event):
        is_active = self.sources_model.get_value(iter, 3)
        menu = Gtk.Menu()
        parent_source = self._get_parent_source(path)
        is_recursive = parent_source.get("recursive", False) if parent_source else True
        is_root = (path == parent_source.get("path")) if parent_source else True

        if is_root:
            menu.append(Gtk.SeparatorMenuItem())
            children_state = self.handler.get_children_state(path)
            item_activate = Gtk.MenuItem(label=_("Activate subfolders"))
            item_activate.set_sensitive(children_state != "all_active")
            item_activate.connect("activate", self.on_bulk_toggle, path, True)
            menu.append(item_activate)
            item_deactivate = Gtk.MenuItem(label=_("Deactivate subfolders"))
            item_deactivate.set_sensitive(children_state != "all_inactive")
            item_deactivate.connect("activate", self.on_bulk_toggle, path, False)
            menu.append(item_deactivate)
            menu.append(Gtk.SeparatorMenuItem())

        label = _("Deactivate folder") if is_active else _("Activate folder")
        item = Gtk.MenuItem(label=label)
        item.connect("activate", self.toggle_child_active, self.sources_model, iter)
        menu.append(item)

        if not is_active:
            item_purge = Gtk.MenuItem(label=_("Delete cache"))
            item_purge.connect("activate", self.on_purge_cache_clicked, path)
            menu.append(item_purge)

        menu.show_all()
        menu.popup(None, None, None, None, event.button, event.time)

    def toggle_child_active(self, widget, model, iter):
        path = model.get_value(iter, 2)
        new_state = not model.get_value(iter, 3)
        model.set_value(iter, 3, new_state)
        if self.handler.update_index_active_state(path, new_state):
            print(f" >>> [UI] Estado cambiado: {path} -> {new_state}")
        parent_source = self._get_parent_source(path)
        if parent_source:
            self._auto_update_recursive(parent_source.get("path"))
            self._load_thumbnails()

    def on_purge_cache_clicked(self, widget, folder_path):
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=_("Delete cache of this folder?")
        )
        dialog.format_secondary_text(
            _("Will be removed from your library") + ":" + "\n" +
            folder_path + "\n" +
            _("Images will no longer be available")
        )
        response = dialog.run()
        if response == Gtk.ResponseType.YES:
            deleted_count = self.handler.purge_folder_cache(folder_path)
            self._load_thumbnails()
            # Notificar al usuario
            if deleted_count > 0:
                self.handler._send_notification(
                    reason=_("Cache deleted"),
                    detail_msg= deleted_count + " " + _("thumbnails have been removed from cache"),
                    level="info"
                )
            else:
                self.handler._send_notification(
                    reason=_("No cache"),
                    detail_msg=_("No thumbnails found in cache for this folder."),
                    level="info"
                )
        dialog.destroy()

    def on_bulk_toggle(self, widget, parent_path, new_state):
        if self.handler.toggle_all_children(parent_path, new_state):
            self.load_sources_into_treeview()
            self._load_thumbnails()
            self._auto_update_recursive(parent_path)

    def _set_progress_active(self, active, text=None):
        if active:
            self.btn_spacer.hide()
            self.scan_progress.show()
            self.scan_progress.set_fraction(0.0)
            if text:
                self.scan_progress.set_show_text(True)
                self.scan_progress.set_text(text)
        else:
            self.scan_progress.hide()
            self.btn_spacer.show()
            self.scan_progress.set_fraction(0.0)
            self.scan_progress.set_show_text(False)

    def on_refresh_sources_clicked(self, widget):
        window = self.get_toplevel().get_window()
        if window:
            window.set_cursor(Gdk.Cursor.new_for_display(Gdk.Display.get_default(), Gdk.CursorType.WATCH))
        self._set_progress_active(True, _("Resynchronizing library..."))
        while Gtk.events_pending():
            Gtk.main_iteration()
        self._set_progress_active(True, _("Scanning sources..."))
        self._sources_need_refresh = True
        self._increment_busy()
        self.handler.sync_library(
            on_progress=self._on_sync_progress,
            on_folder=self._on_sync_folder_start
        )
        if window:
            window.set_cursor(None)

    def on_add_source_clicked(self, widget):
        dialog = Gtk.FileChooserDialog(
            title=_("Select Image Folder"),
            parent=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER
        )
        dialog.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
        dialog.add_button(_("Add Source"), Gtk.ResponseType.OK)

        pictures_dir = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES)
        if pictures_dir:
            dialog.set_current_folder(pictures_dir)

        content_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        spacer = Gtk.Label()
        spacer.set_hexpand(True)
        content_box.pack_start(spacer, True, True, 0)
        check_rec = Gtk.CheckButton(label=_("Include subfolders (Recursive)"))
        check_rec.set_active(True)
        check_rec.set_margin_end(10)
        check_rec.set_margin_bottom(10)
        content_box.pack_start(check_rec, False, False, 0)
        content_box.show_all()
        dialog.set_extra_widget(content_box)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            path = dialog.get_filename()
            if path:
                name = os.path.basename(path)
                recursive = check_rec.get_active()
                dialog.destroy()
                self._set_progress_active(True, _("Scanning") + ": " + name + "...")
                while Gtk.events_pending():
                    Gtk.main_iteration()
                success = self.handler.add_source(name, path, recursive)
                if success:
                    self._sources_need_refresh = True
                    self._set_progress_active(True, _("Scanning") + ": " + name + "...")
                    self._increment_busy()
                    self.handler.sync_library(
                        on_progress=self._on_sync_progress,
                        on_folder=self._on_sync_folder_start
                    )
                else:
                    self._set_progress_active(False)
        else:
            dialog.destroy()

    def on_remove_source_clicked(self, widget):
        selection = self.sources_tree.get_selection()
        model, treeiter = selection.get_selected()
        if treeiter:
            source_name = model[treeiter][1]
            source_path = model[treeiter][2]
            dialog = Gtk.MessageDialog(
                transient_for=self,
                flags=0,
                message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.YES_NO,
                text=_("Delete image source?")
            )
            dialog.format_secondary_text(
                source_name + " " + _("will be removed from your library") + "\n" +
                _("Images will no longer be available")
            )
            response = dialog.run()
            if response == Gtk.ResponseType.YES:
                if self.handler.remove_source(source_path):
                    self.load_sources_into_treeview()
            dialog.destroy()

    # ==========================================================
    # SECCIÓN: MONITORES
    # ==========================================================
    def _build_monitors_section(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        # ------------------------------------------------------
        # Cabecera: título "Monitores" + Alineación
        # ------------------------------------------------------
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        header_box.pack_start(self._create_section_label(_("Displays")), False, False, 4)

        # Controles de alineación de 3 estados (pegados a la derecha)
        align_labels_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.align_label_start = Gtk.Label()
        self.align_label_start.set_markup("<b>  [  </b>")
        self.align_label_start.set_tooltip_text(_("Side Left"))
        align_labels_box.pack_start(self.align_label_start, False, False, 0)
        self.align_label_center = Gtk.Label()
        self.align_label_center.set_markup("<b>  •  </b>")
        self.align_label_center.set_tooltip_text(_("Center"))
        align_labels_box.pack_start(self.align_label_center, False, False, 0)
        self.align_label_end = Gtk.Label()
        self.align_label_end.set_markup("<b>  ]  </b>")
        self.align_label_end.set_tooltip_text(_("Side Right"))
        align_labels_box.pack_start(self.align_label_end, False, False, 0)
        self.align_label_start.get_style_context().add_class("align-active")

        align_event_box = Gtk.EventBox()
        align_event_box.get_style_context().add_class("edit-aspects-box")
        align_event_box.set_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        align_event_box.add(align_labels_box)
        align_event_box.connect("button-press-event", self._on_align_label_clicked)

        header_box.pack_end(align_event_box, False, False, 0)

        vbox.pack_start(header_box, False, False, 0)

        # ------------------------------------------------------
        # Contenedor interno: alberga todo el bloque unificado
        # ------------------------------------------------------
        inner_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        inner_box.connect("size-allocate", self._on_container_resized)
        vbox.pack_start(inner_box, True, True, 0)

        # ------------------------------------------------------
        # GRUPO UNIFICADO: switches + monitores + botones
        # Control de alineación horizontal centralizado
        # ------------------------------------------------------
        self.monitor_group_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        monitor_group_box = self.monitor_group_box
        monitor_group_box.set_halign(Gtk.Align.CENTER)  # ← Cambia aquí para mover todo el bloque (START, CENTER, END)

        # --- Sub-bloque 1: Switches de activación por monitor (centrados) ---
        switch_align_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        switch_align_box.set_halign(Gtk.Align.CENTER)
        self.monitor_switches_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        switch_align_box.pack_start(self.monitor_switches_box, False, False, 0)
        monitor_group_box.pack_start(switch_align_box, False, False, 0)

        # --- Sub-bloque 2: Stack con páginas normal y edición ---
        self.monitors_stack = Gtk.Stack()
        self.monitors_stack.set_homogeneous(True)
        monitor_group_box.pack_start(self.monitors_stack, False, False, 0)

        # Página normal (envuelta en Box vertical como en edición, con ancla para tamaño mínimo)
        normal_page_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        normal_page_box.set_halign(Gtk.Align.START)  # Alineación individual (opcional)

        # Widget ancla: ancho máximo conocido, altura 0 para no interferir con la botonera
        anchor = Gtk.Box()
        anchor.set_size_request(825, 0)
        normal_page_box.pack_start(anchor, False, False, 0)

        self.monitors_fixed = Gtk.Fixed()
        self.monitors_fixed.set_valign(Gtk.Align.START)
        normal_page_box.pack_start(self.monitors_fixed, False, False, 0)
        self.monitors_stack.add_named(normal_page_box, "normal")

        # Página edición
        edit_page_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        edit_page_box.set_halign(Gtk.Align.START)  # Alineación individual (opcional)
        self.monitors_fixed_edit = Gtk.Fixed()
        edit_page_box.pack_start(self.monitors_fixed_edit, False, False, 0)
        self.monitors_stack.add_named(edit_page_box, "edit")

        # --- Sub-bloque 3: Barra de botones inferior ---
        # Contenedor principal de la barra inferior
        button_align_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)

        # --- 1. BOTÓN DE EDICIÓN (izquierda) ---
        edit_controls_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        edit_controls_box.set_halign(Gtk.Align.START)

        self.edit_mode_btn = Gtk.ToggleButton()
        icon = Gtk.Image.new_from_icon_name("document-edit-symbolic", Gtk.IconSize.SMALL_TOOLBAR)
        self.edit_mode_btn.add(icon)
        self.edit_mode_btn.set_relief(Gtk.ReliefStyle.NORMAL)
        self.edit_mode_btn.set_tooltip_text(_("Enable/disable screen editing mode"))
        self.edit_mode_btn.connect("toggled", self._on_toggle_edit_mode)
        edit_controls_box.pack_start(self.edit_mode_btn, False, False, 0)

        self.edit_label_stack = Gtk.Stack()
        self.edit_label_stack.set_homogeneous(True)
        self.edit_prompt_label = Gtk.Label()
        self.edit_prompt_label.set_markup("<b>" + _("Enable") + "\n" + _("Editing Mode") + "</b>")
        self.edit_prompt_label.set_halign(Gtk.Align.START)
        self.edit_label_stack.add_named(self.edit_prompt_label, "normal")
        self.edit_mode_label = Gtk.Label()
        self.edit_mode_label.set_markup("<b>" + _("Editing Mode") + ":\n" + _("Enabled") + "</b>")
        self.edit_mode_label.set_halign(Gtk.Align.START)
        self.edit_label_stack.add_named(self.edit_mode_label, "edit")
        self.edit_label_stack.set_visible_child_name("normal")
        self.edit_preset_label = Gtk.Label()
        self.edit_preset_label.set_halign(Gtk.Align.START)
        self.edit_label_stack.add_named(self.edit_preset_label, "edit_preset")
        edit_controls_box.pack_start(self.edit_label_stack, False, False, 0)

        button_align_box.pack_start(edit_controls_box, False, False, 0)

        # --- 2. OPCIONES DE EDICIÓN (centro, solo visibles en modo edición) ---
        self.spanned_switch_edit = Gtk.Switch(active=False)
        self.spanned_switch_edit.set_tooltip_text(_("Span image across all active screens"))
        self.spanned_switch_edit.connect("notify::active", self._on_spanned_edit_changed)

        self.aspect_combo_edit = Gtk.ComboBoxText()
        for key, label in ConfigHandler.ASPECT_MODES.items():
            self.aspect_combo_edit.append_text(_(label))
        self.aspect_combo_edit.set_tooltip_text(_("Picture aspect") + "\n" + " " + _("for current composition"))
        self.aspect_combo_edit.connect("changed", self._on_aspect_edit_changed)

        self.image_effect_combo_edit = Gtk.ComboBoxText()
        for key, label in ConfigHandler.IMAGE_EFFECT.items():
            self.image_effect_combo_edit.append_text(_(label))
        self.image_effect_combo_edit.set_active(0)
        self.image_effect_combo_edit.connect("changed", self._on_image_effect_edit_changed)

        edit_aspects_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        edit_aspects_box.get_style_context().add_class("edit-aspects-box")
        edit_aspects_box.set_halign(Gtk.Align.CENTER)

        hbox_dist = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        hbox_dist.pack_start(Gtk.Label(label=_("Spanned") + ":"), False, False, 0)
        hbox_dist.pack_start(self.spanned_switch_edit, False, False, 0)
        edit_aspects_box.pack_start(hbox_dist, False, False, 0)

        hbox_aspect = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        hbox_aspect.pack_start(Gtk.Label(label=_("Aspect ratio:")), False, False, 0)
        hbox_aspect.pack_start(self.aspect_combo_edit, False, False, 0)
        edit_aspects_box.pack_start(hbox_aspect, False, False, 0)

        hbox_effect = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        hbox_effect.pack_start(Gtk.Label(label=_("Effects") + ":"), False, False, 0)
        hbox_effect.pack_start(self.image_effect_combo_edit, False, False, 0)
        edit_aspects_box.pack_start(hbox_effect, False, False, 0)

        # Control de visibilidad (inicialmente oculto con opacidad y no sensible)
        self.edit_aspects_box = edit_aspects_box
        self.edit_aspects_box.set_sensitive(False)
        GLib.idle_add(lambda: self.edit_aspects_box.set_opacity(0.0) if self.edit_aspects_box else None)

        button_align_box.pack_start(edit_aspects_box, True, True, 0)

        # --- 3. GRUPO DERECHO (Checkbox Favorito + Aceptar + Refrescar) ---
        right_group = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)

        self.fav_checkbox = Gtk.CheckButton(label="")
        self.fav_checkbox.set_tooltip_text(_("Create/update preset on accept"))
        self.fav_checkbox.connect("toggled", self._on_fav_checkbox_toggled)
        right_group.pack_start(self.fav_checkbox, False, False, 0)

        self.accept_btn = Gtk.Button.new_from_icon_name("emblem-ok-symbolic", Gtk.IconSize.BUTTON)
        self.accept_btn.set_tooltip_text(_("Save composition as preset"))
        self.accept_btn.set_sensitive(False)
        self.accept_btn.connect("clicked", self._on_accept_monitors)
        right_group.pack_start(self.accept_btn, False, False, 0)

        refresh_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        refresh_btn.set_tooltip_text(_("Refresh real display status"))
        refresh_btn.connect("clicked", self._on_refresh_monitors)
        right_group.pack_start(refresh_btn, False, False, 0)

        button_align_box.pack_end(right_group, False, False, 0)

        monitor_group_box.pack_end(button_align_box, False, False, 0)

        # ------------------------------------------------------
        # Añadir el grupo completo a inner_box
        # ------------------------------------------------------
        inner_box.pack_start(monitor_group_box, False, False, 0)

        self.right_col.pack_start(vbox, False, True, 0)

    # --- MODO NORMAL ---

    def _on_align_label_clicked(self, widget, event):
        """Detecta clic en el control de alineación y actualiza el estado."""
        if event.button != 1:
            return False
        width = widget.get_allocated_width()
        x = event.x
        # Quitar la clase activa de todos los labels
        for lbl in (self.align_label_start, self.align_label_center, self.align_label_end):
            lbl.get_style_context().remove_class("align-active")
        # Aplicar alineación y marcar el label correspondiente
        if x < width / 3:
            self.monitor_group_box.set_halign(Gtk.Align.START)
            self.align_label_start.get_style_context().add_class("align-active")
            self.backend.save_setting("monitor_group_align", "START")
        elif x > 2 * width / 3:
            self.monitor_group_box.set_halign(Gtk.Align.END)
            self.align_label_end.get_style_context().add_class("align-active")
            self.backend.save_setting("monitor_group_align", "END")
        else:
            self.monitor_group_box.set_halign(Gtk.Align.CENTER)
            self.align_label_center.get_style_context().add_class("align-active")
            self.backend.save_setting("monitor_group_align", "CENTER")
        return True

    def _update_align_labels(self, align):
        """Actualiza las clases CSS de los labels de alineación según el valor."""
        for lbl in (self.align_label_start, self.align_label_center, self.align_label_end):
            lbl.get_style_context().remove_class("align-active")
        if align == Gtk.Align.START:
            self.align_label_start.get_style_context().add_class("align-active")
        elif align == Gtk.Align.CENTER:
            self.align_label_center.get_style_context().add_class("align-active")
        elif align == Gtk.Align.END:
            self.align_label_end.get_style_context().add_class("align-active")

    def _on_monitors_layout_resized(self, widget, allocation):
        """Reposiciona los monitores cuando el layout cambia de tamaño."""
        if self._monitor_widgets:
            GLib.idle_add(self._load_monitors)

    def _on_container_resized(self, widget, allocation):
        """
        Reposiciona los monitores solo si el tamaño del contenedor cambia realmente.
        """
        new_size = (allocation.width, allocation.height)
        if new_size == self._last_container_size:
            return
        self._last_container_size = new_size
        # Cancelar temporizador de debounce anterior
        if hasattr(self, '_debounce_timer_id') and self._debounce_timer_id:
            GLib.source_remove(self._debounce_timer_id)
        # Programar nueva actualización tras 150ms de inactividad
        self._debounce_timer_id = GLib.timeout_add(150, self._debounced_load_monitors)

    def _debounced_load_monitors(self):
        """Se ejecuta tras el debounce para actualizar los monitores."""
        if self._monitor_widgets:
            self._load_monitors()
        self._debounce_timer_id = None
        return False  # Para que GLib no repita el timeout

    def _load_monitors(self):
        for widget in self._monitor_widgets.values():
            self.monitors_fixed.remove(widget)
        self._monitor_widgets.clear()

        layout_w = self.monitors_fixed.get_allocated_width()
        if layout_w < 50:
            GLib.idle_add(self._load_monitors)
            return

        target_height = 0 # 335
        layout_data = self.handler.get_monitors_layout_data(layout_w, target_height)
        if not layout_data:
            return

        settings = self.backend.load_settings()
        wall_mode = settings.get("wallpaper_mode", "fit")

        # Construir img_source desde active_session (una sola vez)
        vault = self.backend.load_vault()
        active_session = vault.get("active_session", {})
        img_source = {}
        for m_hash in [d['hash'] for d in layout_data]:
            entry = active_session.get(m_hash, {})
            if isinstance(entry, dict):
                img_source[m_hash] = entry
            else:
                img_source[m_hash] = {"path": entry if entry else "", "active": True}

        # Crear EventBox vacíos y posicionarlos (sin añadir imágenes)
        for data in layout_data:
            m_hash = data['hash']
            x, y, w, h = data['x'], data['y'], data['w'], data['h']

            eb = Gtk.EventBox()
            eb.get_style_context().add_class("monitor-frame")
            eb.set_size_request(w, h)
            eb.set_tooltip_text(f"Monitor {m_hash}")
            eb.m_hash = m_hash
            eb.connect("button-press-event", self._on_monitor_event, m_hash)

            self.monitors_fixed.put(eb, x, y)
            eb.set_size_request(w, h)
            self._monitor_widgets[m_hash] = eb

        # Obtener configuración actual de aspecto y distribución
        settings = self.backend.load_settings()
        wallpaper_mode = settings.get("wallpaper_mode", "fit")
        spanned_enabled = settings.get("spanned_enabled", False)
        wallpaper_effect_scope = settings.get("wallpaper_effect_scope", "blur")
        wallpaper_effect = settings.get("wallpaper_effect", "none")

        # Ahora los EventBox ya están en el Fixed: pintar miniaturas
        self.ie.paint_monitors_thumbnails(
            fixed_widget=self.monitors_fixed,
            layout_data=layout_data,
            img_source=img_source,
            wallpaper_mode=wallpaper_mode,
            spanned_enabled=spanned_enabled,
            color_tuple=self.backend.get_background_color_tuple(),
            wallpaper_effect_scope=wallpaper_effect_scope,
            image_effect=wallpaper_effect
        )

        # Ajustar tamaño y switches
        if layout_data:
            min_x = min(d['x'] for d in layout_data)
            max_x = max(d['x'] + d['w'] for d in layout_data)
            max_y = max(d['y'] + d['h'] for d in layout_data)
            monitors_width = int(max_x - min_x)
            if monitors_width > 0:
                GLib.idle_add(self._adjust_fixed_size, monitors_width, max_y)
        self.monitors_fixed.show_all()
        self._build_monitor_switches()
        GLib.idle_add(self._update_monitor_tooltips)

    def _adjust_fixed_size(self, monitors_width, max_y):
        """
        Ajusta el tamaño del Fixed, la barra de botones, el espaciador
        y la caja de switches para que todo comparta el mismo ancho.
        """
        self.monitors_fixed.set_size_request(monitors_width + 10, int(max_y) + 10)
        if hasattr(self, 'btn_box') and self.btn_box is not None:
            self.btn_box.set_size_request(monitors_width, -1)
            spacer_width = monitors_width - 150
            if spacer_width < 0:
                spacer_width = 0
            if hasattr(self, 'btn_spacer'):
                self.btn_spacer.set_size_request(spacer_width, -1)
        # Ajustar también el ancho de la caja de switches para que coincida con los monitores
        if hasattr(self, 'monitor_switches_box') and self.monitor_switches_box is not None:
            self.monitor_switches_box.set_size_request(monitors_width, -1)
        if hasattr(self, 'edit_align_box') and self.edit_align_box is not None:
            self.edit_align_box.set_size_request(monitors_width, -1)
        return False

    def _build_monitor_switches(self):
        """Crea o actualiza los switches de activación por monitor."""
        self._updating_switches = True
        # Elegir la fuente de datos según el modo
        if self.backend.edit_mode_active:
            state_source = self.backend.edit_active_states
        else:
            state_source = self.backend.get_active_session()

        for m_hash, eb in self._monitor_widgets.items():
            if self.backend.edit_mode_active:
                is_active = state_source.get(m_hash, True)
            else:
                entry = state_source.get(m_hash, {})
                if isinstance(entry, str):
                    is_active = True
                else:
                    is_active = entry.get("active", True)

            if m_hash in self._monitor_switches:
                self._monitor_switches[m_hash][0].set_active(is_active)
            else:
                hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
                # Construir etiqueta informativa del monitor
                info = self.handler.get_monitor_info(m_hash)
                if info:
                    mfg_map = self.handler.get_mfg_map()
                    manufacturer_code = info.get("manufacturer", "")
                    connector = info.get("connector", "?")
                    manufacturer_name = mfg_map.get(manufacturer_code, manufacturer_code)

                    if manufacturer_name and manufacturer_name != connector:
                        display_name = f"{connector}:{manufacturer_name}"
                    else:
                        display_name = connector

                    w_mm = info.get("width_mm", 0)
                    h_mm = info.get("height_mm", 0)
                    if w_mm > 0 and h_mm > 0:
                        diag_mm = (w_mm**2 + h_mm**2) ** 0.5
                        inches = int(round(diag_mm / 25.4))      # ← redondeo a entero
                        label_text = f"{display_name} ({inches}\")"  # ← sin decimales
                    else:
                        label_text = display_name
                else:
                    label_text = _("Display") + " " + m_hash[:6]
                # Resaltar el monitor primario en amarillo
                if info and info.get("primary", False):
                    label = Gtk.Label()
                    label.set_markup(f"<span foreground='yellow'>{label_text}</span>")
                else:
                    label = Gtk.Label(label=label_text)
                # Guardar el nombre enriquecido para usarlo en tooltips
                self._monitor_display_names[m_hash] = label_text

                switch = Gtk.Switch(active=is_active)
                switch.connect("notify::active", self._on_monitor_active_toggled, m_hash)
                switch.set_tooltip_text(_("Enable/disable image"))

                hbox.pack_start(label, False, False, 0)
                hbox.pack_start(switch, False, False, 0)
                # Envolver en EventBox para capturar eventos de ratón
                switch_event_box = Gtk.EventBox()
                switch_event_box.add(hbox)
                # Los eventos ahora van en el switch, no en el EventBox
                switch_event_box.connect("enter-notify-event", self._on_switch_enter, m_hash)
                switch_event_box.connect("leave-notify-event", self._on_switch_leave, m_hash)

                self.monitor_switches_box.pack_start(switch_event_box, False, False, 4)
                self._monitor_switches[m_hash] = (switch, switch_event_box)

        # Eliminar switches de monitores que ya no existen
        for m_hash in list(self._monitor_switches.keys()):
            if m_hash not in self._monitor_widgets:
                switch, widget = self._monitor_switches.pop(m_hash)
                widget.destroy()

        # Insensibilizar switch "Distribuido" si solo hay un monitor
        if hasattr(self, 'spanned_switch') and self.spanned_switch is not None:
            self.spanned_switch.set_sensitive(len(self._monitor_widgets) > 1)
            if len(self._monitor_widgets) <= 1:
                self.spanned_switch.set_active(False)

        # Insensibilizar los switches si el modo Distribuido está activo
        settings = self.backend.load_settings()
        if settings.get("spanned_enabled", False):
            self._set_monitor_switches_sensitive(False)

        self.monitor_switches_box.show_all()
        self._updating_switches = False

    def _update_monitor_tooltips(self):
        """Actualiza los tooltips de los monitores con los nombres enriquecidos."""
        for m_hash, eb in self._monitor_widgets.items():
            name = self._monitor_display_names.get(m_hash, _("Display") + " " + m_hash[:6])
            eb.set_tooltip_text(name)
        return False  # Para GLib.idle_add

    def _on_fav_checkbox_toggled(self, checkbox):
        if not self.backend.edit_mode_active:
            self.accept_btn.set_sensitive(checkbox.get_active())

    def _on_monitor_active_toggled(self, switch, param, m_hash):
        """Activa o desactiva la imagen de un monitor."""
        if self._loading:
            return
        if self._updating_switches:
            return
        if self.backend.edit_mode_active:
            # En modo edición, solo actualizar el estado temporal y la vista en la copia
            self.backend.edit_active_states[m_hash] = switch.get_active()
            self._load_preset_to_edit_monitors(self.backend.edit_active_session)
            return

        # Modo normal: lógica de guardado delegada al backend
        if self.backend.toggle_monitor_active(m_hash, switch.get_active()):
            self._notify_engine({"action": "apply_manual_selection"})

        if m_hash in self._monitor_widgets:
            eb = self._monitor_widgets[m_hash]
            thumb = eb.get_child()
            w, h = eb.get_size_request()
            inner_w, inner_h = w - 2, h - 2
            active = switch.get_active()
            if active:
                img_path = self.backend.get_image_path(m_hash)
                if img_path:
                    blurred = self.handler.get_composite_thumbnail(img_path, inner_w, inner_h)
                else:
                    blurred = None
            else:
                color_tuple = self.backend.get_background_color_tuple()
                blurred = self.handler.get_composite_thumbnail(color_tuple, inner_w, inner_h)

            if thumb is not None:
                if not thumb.get_style_context().has_class("monitor-image"):
                    thumb.get_style_context().add_class("monitor-image")
                if blurred:
                    thumb.set_from_file(blurred)
                else:
                    thumb.set_from_icon_name("image-missing", Gtk.IconSize.DIALOG)

        self._build_monitor_switches()

    def _on_switch_enter(self, widget, event, m_hash):
        if self.backend.edit_mode_active:
            for eb in self.monitors_fixed_edit.get_children():
                if getattr(eb, 'm_hash', None) == m_hash:
                    eb.get_style_context().add_class("dnd-target")
                    eb.queue_draw()
                    return False
        else:
            for eb in self._monitor_widgets.values():
                if getattr(eb, 'm_hash', None) == m_hash:
                    eb.get_style_context().add_class("dnd-target")
                    eb.queue_draw()
                    return False
        return False

    def _on_switch_leave(self, widget, event, m_hash):
        if self.backend.edit_mode_active:
            for eb in self.monitors_fixed_edit.get_children():
                if getattr(eb, 'm_hash', None) == m_hash:
                    eb.get_style_context().remove_class("dnd-target")
                    eb.queue_draw()
                    return False
        else:
            for eb in self._monitor_widgets.values():
                if getattr(eb, 'm_hash', None) == m_hash:
                    eb.get_style_context().remove_class("dnd-target")
                    eb.queue_draw()
                    return False
        return False

    def _on_monitor_event(self, widget, event, m_hash):
        if event.button == 3:
            pass
        return False

    def _on_refresh_monitors(self, widget):
        if self.backend.edit_mode_active:
            for m_hash in self.backend.edit_active_session:
                self.backend.edit_active_session[m_hash] = ""
                self.backend.edit_active_states[m_hash] = True
            self._load_monitors_edit()
            self._build_monitor_switches()
            print(" [Edición] Monitores reseteados a vacío.")
            return
        self._load_monitors()
        self._current_preset_name = None
        self._build_monitor_switches()
        print(" [Monitores] Vista refrescada desde el motor.")

    def _on_accept_monitors(self, widget):
        """Guarda los cambios de edición y crea/actualiza el preset si procede."""
        if self.backend.edit_mode_active:
            # Delegar en el backend la lógica de datos
            log_msg, temp_settings, new_preset_name = self.backend.apply_edit_and_save(
                fav_checkbox_active=self.fav_checkbox.get_active(),
                preset_name=self._current_preset_name,
                monitor_hashes=list(self._monitor_widgets.keys()),
                get_path_func=lambda h: self.backend.edit_active_session.get(h, ""),
                get_active_func=lambda h: self.backend.edit_active_states.get(h, True)
            )

            # Refrescar listas de presets si se guardó uno nuevo
            if self.fav_checkbox.get_active():
                self._load_presets()
                self._load_bookmarks_single()

            # Notificar al motor
            self._notify_engine({
                "action": "apply_manual_selection",
                "temp_settings": temp_settings
            })
            print(f" [Notificacion] {action} enviada al motor")
            # Desactivar slideshow
            settings = self.backend.load_settings()
            settings["slideshow_enabled"] = False
            self.backend.save_settings(settings)

            # Salir del modo edición
            self._exit_edit_mode()

            if log_msg:
                print(f" [Edición] {log_msg}")
            else:
                print(" [Edición] Cambios aplicados y modo edición finalizado.")
            return

        # Modo normal: guardar preset si el checkbox está activo
        if self.fav_checkbox.get_active():
            current_composition = {}
            for m_hash, eb in self._monitor_widgets.items():
                vault_entry = self.backend.get_active_session().get(m_hash, {})
                if isinstance(vault_entry, dict):
                    path = vault_entry.get("path", "")
                    active = vault_entry.get("active", True)
                else:
                    path = vault_entry if vault_entry else ""
                    active = True
                current_composition[m_hash] = {"path": path, "active": active}

            settings = self.backend.load_settings()
            current_composition["__mode__"] = settings.get("wallpaper_mode", "fit")
            current_composition["__spanned__"] = settings.get("spanned_enabled", False)
            current_composition["__effect__"] = settings.get("wallpaper_effect", "none")
            current_composition["__effect_scope__"] = settings.get("wallpaper_effect_scope", "blur")

            preset_name = f"Bookmark {self.handler.get_next_bookmark_id():02d}"
            self.handler.save_current_state_as_bookmark(preset_name, current_composition)
            self._load_presets()
            self._load_bookmarks_single()
            print(f" [Monitores] Preset guardado: {preset_name}")
            self.fav_checkbox.set_active(False)
            self.accept_btn.set_sensitive(False)
        else:
            print(" [Monitores] No se ha marcado Favorito, no se guarda nada.")

    # --- MODO EDICIÓN ---

    def _on_toggle_edit_mode(self, widget):
        """Activa o desactiva el modo edición de monitores."""
        # 1. Guardar estado anterior y actualizar el nuevo
        was_active = self.backend.edit_mode_active
        self.backend.edit_mode_active = widget.get_active()
        # 2. Cambiar la etiqueta del stack según el modo
        page = "edit" if self.backend.edit_mode_active else "normal"
        self.edit_label_stack.set_visible_child_name(page)

        if self.backend.edit_mode_active:
            # ============================================================
            # ACTIVAR MODO EDICIÓN
            # ============================================================

            # 2.1 Limpiar sesión de edición si es la primera activación
            if not was_active:
                self.backend.edit_active_session.clear()
            # 2.2 Cargar estados activos desde la sesión real del vault
            active_session = self.backend.get_active_session()
            self.backend.edit_active_states = {}
            for m_hash, entry in active_session.items():
                if isinstance(entry, dict):
                    self.backend.edit_active_states[m_hash] = entry.get("active", True)
                else:
                    self.backend.edit_active_states[m_hash] = True
            # 2.3 Pintar los monitores virtuales en el modo edición
            self._load_monitors_edit()
            # 2.4 Sincronizar los switches de activación por monitor
            self._build_monitor_switches()
            self.monitors_stack.set_visible_child_name("edit")
            # 2.5 Mostrar el panel de opciones de edición (Distribuido, Rel. Aspecto, Efectos)
            self.edit_aspects_box.set_opacity(1.0)
            self.edit_aspects_box.set_sensitive(True)
            # 2.6 Inicializar los valores temporales desde settings.json
            settings = self.backend.load_settings()

            # Relación de aspecto
            current_wp_mode = settings.get("wallpaper_mode", "fit")
            keys = list(ConfigHandler.ASPECT_MODES.keys())
            index = keys.index(current_wp_mode) if current_wp_mode in keys else 0
            self.aspect_combo_edit.set_active(index)
            self.backend.edit_temp_wp_mode = current_wp_mode

            # Modo distribuido
            spanned_enabled = settings.get("spanned_enabled", False)
            self.spanned_switch_edit.set_active(spanned_enabled)
            self.backend.edit_temp_spanned_enabled = spanned_enabled

            # Efecto de imagen
            img_effect = settings.get("wallpaper_effect", "none")
            keys = list(ConfigHandler.IMAGE_EFFECT.keys())
            index = keys.index(img_effect) if img_effect in keys else 0
            self.image_effect_combo_edit.set_active(index)
            self.backend.edit_temp_image_effect = img_effect

            # Efecto de fondo (alcance)
            wp_scope = settings.get("wallpaper_effect_scope", "blur")
            # Nota: no hay combo específico en edición para esto, pero se guarda por consistencia
            self.backend.edit_temp_wp_scope = wp_scope
            # 2.7 Habilitar botón de aceptar cambios
            self.accept_btn.set_sensitive(True)

        else:
            # ============================================================
            # DESACTIVAR MODO EDICIÓN
            # ============================================================

            self._exit_edit_mode()
            self.edit_aspects_box.set_opacity(0.0)
            self.edit_aspects_box.set_sensitive(False)

    def _exit_edit_mode(self):
        self.backend.cancel_edit()
        self.edit_mode_btn.set_active(False)
        self.edit_label_stack.set_visible_child_name("normal")
        self.monitors_stack.set_visible_child_name("normal")
        self._load_monitors()
        self._build_monitor_switches()
        self.accept_btn.set_sensitive(False)
        self.fav_checkbox.set_active(False)
        self._current_preset_name = None

    def _on_aspect_edit_changed(self, combo):
        if self._loading:
            return
        index = combo.get_active()
        keys = list(ConfigHandler.ASPECT_MODES.keys())
        if 0 <= index < len(keys):
            mode = keys[index]
            self.backend.edit_temp_wp_mode = mode
            # Insensibilizar switches si es spanned
            if self.backend.edit_mode_active:
                self._set_monitor_switches_sensitive(mode != "spanned")
                # Refrescar vista previa (de momento solo estructura)
                self._load_monitors_edit()
                # Si hay sesión de edición activa, regenerar miniaturas
                if self.backend.edit_active_session:
                    self._load_preset_to_edit_monitors(self.backend.edit_active_session)

    def _load_monitors_edit(self):
        for widget in self.monitors_fixed_edit.get_children():
            self.monitors_fixed_edit.remove(widget)
        self._edit_monitor_widgets.clear()

        layout_w = self.monitors_fixed.get_allocated_width()
        if layout_w < 50:
            layout_w = 400

        target_height = 0 #335
        layout_data = self.handler.get_monitors_layout_data(layout_w, target_height)
        if not layout_data:
            return

        for data in layout_data:
            m_hash = data['hash']
            x, y, w, h = data['x'], data['y'], data['w'], data['h']

            eb = Gtk.EventBox()
            eb.get_style_context().add_class("monitor-frame")
            eb.set_size_request(w, h)
            eb.set_tooltip_text(self._monitor_display_names.get(m_hash, _("Display") + " " + m_hash[:6]) + " (" + _("editing") + ")")
            eb.m_hash = m_hash
            eb.drag_dest_set(
                Gtk.DestDefaults.ALL,
                [Gtk.TargetEntry.new("text/plain", Gtk.TargetFlags.SAME_APP, 0)],
                Gdk.DragAction.COPY
            )
            eb.drag_dest_set_track_motion(True)
            eb.connect("drag-motion", self._on_edit_drag_motion, m_hash)
            eb.connect("drag-leave", self._on_edit_drag_leave, m_hash)
            eb.connect("drag-data-received", self._on_edit_drag_data_received, m_hash)
            self.monitors_fixed_edit.put(eb, x, y)
            self._edit_monitor_widgets[m_hash] = eb
            eb.show()

        if layout_data:
            min_x = min(d['x'] for d in layout_data)
            max_x = max(d['x'] + d['w'] for d in layout_data)
            monitors_width = int(max_x - min_x)
            if monitors_width > 0:
                self.monitors_fixed_edit.set_size_request(monitors_width + 10, -1)

        self.monitors_fixed_edit.show_all()

    def _load_preset_to_edit_monitors(self, preset_data):
        # Obtener geometría escalada para el layout de edición
        layout_w = self.monitors_fixed.get_allocated_width()
        if layout_w < 50:
            layout_w = 400
        target_height = 0  # 335
        layout_data = self.handler.get_monitors_layout_data(layout_w, target_height)
        if not layout_data:
            return

        # Obtener valores temporales (o globales si no existen)
        wall_mode = self.backend.edit_temp_wp_mode or self.backend.load_settings().get("wallpaper_mode", "fit")
        wp_scope = self.backend.edit_temp_wp_scope or self.backend.load_settings().get("wallpaper_effect_scope", "blur")
        wp_effect = self.backend.edit_temp_image_effect or self.backend.load_settings().get("wallpaper_effect", "none")
        spanned_enabled = self.backend.edit_temp_spanned_enabled
        if spanned_enabled is None:
            spanned_enabled = self.backend.load_settings().get("spanned_enabled", False)

        # Construir img_source completo con todos los monitores visibles
        img_source = {}
        for data in layout_data:
            m_hash = data['hash']
            path = self.backend.edit_active_session.get(m_hash, "")
            active = self.backend.edit_active_states.get(m_hash, True)
            img_source[m_hash] = {"path": path, "active": active}
        # Delegar en el motor unificado
        self.ie.paint_monitors_thumbnails(
            fixed_widget=self.monitors_fixed_edit,
            layout_data=layout_data,
            img_source=img_source,
            wallpaper_mode=wall_mode,
            spanned_enabled=spanned_enabled,
            color_tuple=self.backend.get_background_color_tuple(),
            wallpaper_effect_scope=wp_scope,
            image_effect=wp_effect,
        )
        self._build_monitor_switches()

    def _on_edit_drag_motion(self, widget, context, x, y, time, m_hash):
        Gdk.drag_status(context, Gdk.DragAction.COPY, time)
        widget.get_style_context().add_class("dnd-target")
        return True

    def _on_edit_drag_leave(self, widget, context, time, m_hash):
        widget.get_style_context().remove_class("dnd-target")

    def _on_edit_drag_data_received(self, widget, context, x, y, data, info, time, m_hash):
        try:
            img_path = base64.b64decode(data.get_text().encode('ascii')).decode('utf-8')
        except Exception:
            img_path = data.get_text()
        if not img_path:
            Gtk.drag_finish(context, False, False, time)
            return

        # Actualizar la sesión de edición
        self.backend.edit_active_session[m_hash] = img_path
        if not self.backend.edit_active_states.get(m_hash, True):
            self.backend.edit_active_states[m_hash] = True
            if m_hash in self._monitor_switches:
                switch, hbox = self._monitor_switches[m_hash]
                switch.set_active(True)

        # Evitar que _build_monitor_switches dispare _on_monitor_active_toggled
        self._updating_switches = True
        if not self._repaint_scheduled:
            self._repaint_scheduled = True
            GLib.idle_add(self._idle_repaint_edit_monitors)
        self._updating_switches = False

        widget.get_style_context().remove_class("dnd-target")
        Gtk.drag_finish(context, True, False, time)
        print(f" [Edición] Imagen asignada a {m_hash}: {img_path}")

    def _idle_repaint_edit_monitors(self):
        """Repinta los monitores en edición tras un drag o cambio de switch."""
        self._repaint_scheduled = False
        if self.backend.edit_mode_active and self.backend.edit_active_session:
            self._load_preset_to_edit_monitors(self.backend.edit_active_session)
        return False

    # ==========================================================
    # SECCIÓN: GALERÍA (THUMBNAILS)
    # ==========================================================
    def _build_thumbnails_section(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header_box.pack_start(self._create_section_label(_("Thumbnails")), False, False, 0)
        nav_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, halign=Gtk.Align.CENTER)
        nav_box.set_hexpand(True)
        header_box.pack_start(nav_box, True, True, 0)
        self.btn_h = Gtk.Button()
        label_h = Gtk.Label()
        label_h.set_markup("<b>" + _("Horizontal") + "</b>")
        self.btn_h.add(label_h)
        self.btn_h.set_relief(Gtk.ReliefStyle.NONE)
        self.btn_h.connect("clicked", self._scroll_to_h)
        nav_box.pack_start(self.btn_h, False, False, 0)
        self.btn_v = Gtk.Button()
        label_v = Gtk.Label()
        label_v.set_markup("<b>" + _("Vertical") + "</b>")
        self.btn_v.add(label_v)
        self.btn_v.set_relief(Gtk.ReliefStyle.NONE)
        self.btn_v.connect("clicked", self._scroll_to_v)
        nav_box.pack_start(self.btn_v, False, False, 0)
        refresh_thumb = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        refresh_thumb.set_tooltip_text(_("Reload thumbnails"))
        refresh_thumb.connect("clicked", self._load_thumbnails)
        header_box.pack_end(refresh_thumb, False, False, 0)
        vbox.pack_start(header_box, False, False, 0)

        scrolled = Gtk.ScrolledWindow()
        self.thumbnails_flowbox = Gtk.FlowBox()
        self.thumbnails_flowbox.set_homogeneous(False)
        self.thumbnails_flowbox.set_row_spacing(4)
        self.thumbnails_flowbox.set_column_spacing(4)
        self.thumbnails_flowbox.set_valign(Gtk.Align.START)
        scrolled.add(self.thumbnails_flowbox)
        vbox.pack_start(scrolled, True, True, 0)
        self.right_col.pack_start(vbox, True, True, 0)

    def _load_thumbnails(self, widget=None):
        if self._thumbnails_loading:
            return
        self._thumbnails_loading = True
        # ... el resto del código existente permanece INTACTO ...
        for child in self.thumbnails_flowbox.get_children():
            self.thumbnails_flowbox.remove(child)
        h_list, v_list = self.handler.get_flat_lists()
        all_images = [(img, "h") for img in h_list] + [(img, "v") for img in v_list]
        total = len(all_images)
        if total == 0:
            self._thumbnails_loading = False  # Liberar el flag
            self._decrement_busy()
            self._set_progress_active(False)
            placeholder = Gtk.Label(label=_("No images found."))
            self.thumbnails_flowbox.add(placeholder)
            self._set_progress_active(False)
            return
        self._increment_busy()
        self._set_progress_active(True, _("Generating thumbnails..."))
        self._progress_count = 0
        self._progress_total = total
        self._progress_images = all_images
        self._progress_h_list = h_list
        self._progress_v_list = v_list
        GLib.idle_add(self._generate_next_thumbnail)

    def _generate_next_thumbnail(self):
        if self._progress_count < self._progress_total:
            img_data, orient = self._progress_images[self._progress_count]
            img_path = img_data[0]
            self.handler.get_thumbnail(img_path)
            self._progress_count += 1
            fraction = self._progress_count / self._progress_total
            self.scan_progress.set_fraction(fraction)
            self.scan_progress.set_text(_("Processing") + " " + str(self._progress_count) + "/" + str(self._progress_total))
            return True
        else:
            self._build_thumbnail_items()
            self._decrement_busy()
            self._set_progress_active(False)
            return False

    def _build_thumbnail_items(self):
        self._first_h_item = None
        self._first_v_item = None
        favorites = set()
        fav_list = self.backend.load_json("bookmarks_single")
        for entry in fav_list:
            if entry and len(entry) > 0:
                favorites.add(entry[0])
        h_list = self._progress_h_list
        v_list = self._progress_v_list
        for img in h_list:
            if self.handler._is_path_active(img[0]):
                self._add_thumbnail_item(img[0], favorites)
        for img in v_list:
            if self.handler._is_path_active(img[0]):
                self._add_thumbnail_item(img[0], favorites)
        children = self.thumbnails_flowbox.get_children()
        if h_list and len(children) > 0:
            self._first_h_item = children[0]
        if v_list and len(children) > len(h_list):
            self._first_v_item = children[len(h_list)]
        if not self.thumbnails_flowbox.get_children():
            placeholder = Gtk.Label(label=_("No images found."))
            self.thumbnails_flowbox.add(placeholder)
        self.thumbnails_flowbox.show_all()
        self._thumbnails_loading = False # NUEVO: Liberamos al final de todo
        self._set_progress_active(False)
        print(" >>> [SISTEMA] Thumbnails cargados.")

    def _add_thumbnail_item(self, img_path, favorites):
        item_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        item_box.set_margin_start(4)
        item_box.set_margin_end(4)
        thumb_path = self.handler.get_thumbnail(img_path)
        img = Gtk.Image.new_from_file(thumb_path)
        img.set_tooltip_text(img_path)
        img.set_size_request(-1, 160)
        item_box.pack_start(img, False, False, 0)
        name_label = Gtk.Label(label=os.path.basename(img_path))
        name_label.set_max_width_chars(20)
        name_label.set_ellipsize(Pango.EllipsizeMode.END)
        name_label.set_halign(Gtk.Align.CENTER)
        item_box.pack_start(name_label, False, False, 0)
        if img_path in favorites:
            item_box.get_style_context().add_class("favorite-thumbnail")
        event_box = Gtk.EventBox()
        event_box.add(item_box)
        event_box.connect("button-press-event", self._on_thumbnail_click, img_path, favorites)
        event_box.connect("button-press-event", self._on_thumbnail_double_click, img_path)
        event_box.drag_source_set(
            Gdk.ModifierType.BUTTON1_MASK,
            [Gtk.TargetEntry.new("text/plain", Gtk.TargetFlags.SAME_APP, 0)],
            Gdk.DragAction.COPY
        )
        event_box.connect("drag-data-get", self._on_thumbnail_drag_data_get, img_path)
        event_box.connect("drag-begin", self._on_thumbnail_drag_begin, img_path)
        event_box.connect("drag-end", self._on_thumbnail_drag_end, img_path)
        self.thumbnails_flowbox.add(event_box)

    def _scroll_to_h(self, widget):
        if self._first_h_item:
            self.thumbnails_flowbox.select_child(self._first_h_item)
            self._first_h_item.grab_focus()

    def _scroll_to_v(self, widget):
        if self._first_v_item:
            self.thumbnails_flowbox.select_child(self._first_v_item)
            self._first_v_item.grab_focus()

    def _on_thumbnail_click(self, widget, event, img_path, favorites):
        if event.button != 3:
            return False
        menu = Gtk.Menu()
        if img_path in favorites:
            item = Gtk.MenuItem(label=_("Remove from favorites"))
            item.connect("activate", self._remove_from_favorites, img_path)
        else:
            item = Gtk.MenuItem(label=_("Add to favorites"))
            item.connect("activate", self._add_to_favorites, img_path)
        menu.append(item)
        menu.show_all()
        menu.popup(None, None, None, None, event.button, event.time)
        return True

    def _on_thumbnail_double_click(self, widget, event, img_path):
        if event.type == Gdk.EventType._2BUTTON_PRESS and event.button == 1:
            self.handler.open_in_file_manager(img_path)
            return True
        return False

    def _on_thumbnail_drag_data_get(self, widget, context, data, info, time, img_path):
        encoded = base64.b64encode(img_path.encode('utf-8')).decode('ascii')
        data.set_text(encoded, -1)

    def _on_thumbnail_drag_begin(self, widget, context, img_path):
        widget.get_style_context().add_class("dnd-source")
        widget.queue_resize()
        thumb_path = self.handler.get_thumbnail(img_path)
        if thumb_path and os.path.exists(thumb_path):
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(thumb_path)
            max_size = 100
            width = pixbuf.get_width()
            height = pixbuf.get_height()
            if width > height:
                new_w = max_size
                new_h = int(height * max_size / width)
            else:
                new_h = max_size
                new_w = int(width * max_size / height)
            pixbuf = pixbuf.scale_simple(new_w, new_h, GdkPixbuf.InterpType.BILINEAR)
            widget.drag_source_set_icon_pixbuf(pixbuf)

    def _on_thumbnail_drag_end(self, widget, context, img_path):
        widget.get_style_context().remove_class("dnd-source")

    def _add_to_favorites(self, widget, img_path):
        if self.handler.add_to_favorites(img_path):
            self._load_bookmarks_single()
            self._load_thumbnails()

    def _remove_from_favorites(self, widget, img_path):
        if self.handler.remove_from_favorites(img_path):
            self._load_bookmarks_single()
            self._load_thumbnails()

    def _handle_panel_signal(self, signum, frame):
        """
        Manejador de la señal SIGUSR1 enviada por el motor.
        Lee command_panel.json y actualiza la UI según el evento recibido.
        """
        print(" [PANEL] Señal SIGUSR1 recibida del motor.")
        command_path = os.path.join(self.handler.data_dir, "command_panel.json")
        try:
            if os.path.exists(command_path):
                with open(command_path, "r", encoding="utf-8") as f:
                    event = json.load(f)
                action = event.get("action", "")
                print(f" [PANEL] Evento recibido: {action}")

                # Despachar según la acción
                if action == "wallpaper_changed":
                    GLib.idle_add(self._load_monitors)
                elif action == "settings_updated":
                    GLib.idle_add(self._load_settings)
                elif action == "bookmarks_updated":
                    GLib.idle_add(self._load_presets)
                    GLib.idle_add(self._load_bookmarks_single)
                elif action == "hardware_changed":
                    GLib.idle_add(self._load_monitors)
                else:
                    print(f" [PANEL] Acción desconocida: {action}")

                # Limpiar el buzón
                os.remove(command_path)
        except Exception as e:
            print(f" [PANEL] Error al procesar señal: {e}")
            self.handler.log_error(f"Error al procesar señal: {e}", reason="PANEL_SIGNAL")

    def _on_delete_event(self, widget, event):
        # Limpiar archivo PID del panel
        pid_path = os.path.join(self.handler.cache_dir, "pid_panel.pid")
        if os.path.exists(pid_path):
            try:
                os.remove(pid_path)
                print(" [PANEL] Archivo PID eliminado. Cierre limpio.")
            except Exception as e:
                print(f" [PANEL] Error al eliminar PID: {e}")
                self.handler.log_error(f"Error al eliminar PID: {e}", reason="PANEL_PID")

        app = self.get_application()
        if app:
            # Guardar la alineación actual antes de cerrar
            if hasattr(self, 'monitor_group_box'):
                align = self.monitor_group_box.get_halign()
                align_str = "START" if align == Gtk.Align.START else "CENTER" if align == Gtk.Align.CENTER else "END"
                self.backend.save_setting("monitor_group_align", align_str)
            app.quit()
        return True

    # ==========================================================
    # SECCIÓN: Carga inicial de variables en el Panel
    # ==========================================================
    def _load_settings(self):
        self._loading = True
        settings = self.backend.load_settings()
        self.slideshow_switch.set_active(settings.get("slideshow_enabled", True))
        self.mode_switch.set_active(settings.get("slideshow_mode", "sync") == "sync")
        self.max_interval_spin.set_value(settings.get("slideshow_max_interval", 60))
        self.rotation_spin.set_value(settings.get("slideshow_interval", 15))
        self.fav_rotation_switch.set_active(settings.get("slideshow_bookmark", False))
        max_val = settings.get("slideshow_max_interval", 60)
        if settings.get("slideshow_interval", 15) > max_val:
            self.rotation_spin.set_value(max_val)
        mode = settings.get("wallpaper_mode", "fit")
        keys = list(ConfigHandler.ASPECT_MODES.keys())
        index = keys.index(mode) if mode in keys else 2
        self.aspect_combo.set_active(index)
        self._update_mode_info_label()
        color_mode = settings.get("color_mode", "solid_color")
        # Efectos visuales
        wallpaper_effect = settings.get("wallpaper_effect", "blur")
        index = list(ConfigHandler.IMAGE_EFFECT.keys()).index(wallpaper_effect) if wallpaper_effect in ConfigHandler.IMAGE_EFFECT else 0
        self.image_effect_combo.set_active(index)
        wallpaper_effect_scope = settings.get("wallpaper_effect_scope", "blur")
        index = list(ConfigHandler.BACK_EFFECT.keys()).index(wallpaper_effect_scope) if wallpaper_effect_scope in ConfigHandler.BACK_EFFECT else 0
        self.back_effect_combo.set_active(index)
        # Switch spanned
        self.spanned_switch.set_active(settings.get("spanned_enabled", False))
        self._set_monitor_switches_sensitive(not settings.get("spanned_enabled", False))
        keys = list(ConfigHandler.COLOR_MODES.keys())
        index = keys.index(color_mode) if color_mode in keys else 0
        self.bg_mode_combo.set_active(index)
        self._update_bg_color_buttons(color_mode)

        self._set_btn_color(self.solid_color_btn, settings.get("solid_color", "#000000"))
        grad_h = settings.get("gradient_h", ["#000000", "#8D9797"])
        self._set_btn_color(self.grad_h_start_btn, grad_h[0])
        self._set_btn_color(self.grad_h_end_btn, grad_h[1])
        grad_v = settings.get("gradient_v", ["#000000", "#8D9797"])
        self._set_btn_color(self.grad_v_start_btn, grad_v[0])
        self._set_btn_color(self.grad_v_end_btn, grad_v[1])
        self.accept_btn.set_sensitive(False)
        self._loading = False
        self._current_preset_name = None
        self._monitor_widgets = {}
        vault = self.backend.load_vault()
        self.persist_switch.set_active(not settings.get("persist_on_reboot", True))
        # Restaurar la última alineación del grupo de monitores
        align_value = settings.get("monitor_group_align", "START")
        align_map = {
            "START": Gtk.Align.START,
            "CENTER": Gtk.Align.CENTER,
            "END": Gtk.Align.END
        }
        if hasattr(self, 'monitor_group_box') and self.monitor_group_box is not None:
            self.monitor_group_box.set_halign(align_map.get(align_value, Gtk.Align.START))
            # Sincronizar el control visual (los labels)
            if hasattr(self, 'align_label_start'):
                self._update_align_labels(align_map.get(align_value, Gtk.Align.START))
        # Modo Debug
        debug_mode = settings.get("debug_mode", False)
        self._opened_in_debug = debug_mode
        self.debug_mode_switch.set_active(debug_mode)
        self.debug_mode_label.set_text(_("Debug mode ON") if debug_mode else _("Debug mode OFF"))
        title = _("Control Panel")
        if debug_mode:
            title += " (DEBUG)"
        self.set_title(title)
        if hasattr(self, 'restart_btn') and self.restart_btn:
            if self._opened_in_debug:
                self.restart_btn.set_visible(True)
            else:
                self.restart_btn.set_visible(debug_mode)
        if hasattr(self, 'view_log_btn') and self.view_log_btn:
            if self._opened_in_debug:
                self.view_log_btn.set_visible(True)
            else:
                self.view_log_btn.set_visible(debug_mode)

# ==========================================================
# APLICACIÓN GTK (INSTANCIA ÚNICA)
# ==========================================================
class PanelApplication(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="org.wmm.Panel")
        self.window = None

    def do_activate(self):
        if not self.window:
            self.window = WMMControlPanel(self)
            self.add_window(self.window)
        self.window.present()


# ==========================================================
# PUNTO DE ENTRADA
# ==========================================================
if __name__ == "__main__":
    app = PanelApplication()
    app.run(sys.argv)
