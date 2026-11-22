#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

"""
WMM - Wallpaper Multi-Monitor Manager

options_section.py – Sección de Opciones del panel de control.
==========================================================
Gestiona todas las opciones de configuración de WMM: persistencia,
modo distribuido, aspecto, efectos, colores, presentación de diapositivas
y los botones de acción (reiniciar, visor de logs, ayuda).
"""

import os
import sys
import time
import subprocess
import gi

gi.require_version('Gtk', '3.0')

from gi.repository import Gtk, Gdk, GLib
from config_handler import ConfigHandler
from i18n import _, N_
from debug_logger import log_event

class OptionsSection:
    """
    Sección de Opciones del panel de control.
    """

    def __init__(self, handler, backend, ie, left_col):
        """
        Args:
            handler:  Instancia de ConfigHandler.
            backend:  Instancia de WMMBackend.
            ie:       Instancia de ImageEngine.
            left_col: El Gtk.Box donde se empaquetará esta sección.
            callbacks: Diccionario con funciones de callback para
                       comunicarse con el panel principal:
                       - 'create_section_label': (text) -> Gtk.Label
                       - 'notify_engine': (action_dict)
                       - 'load_monitors': ()
                       - 'set_monitor_switches_sensitive': (bool)
                       - 'get_edit_mode_active': () -> bool
                       - 'get_loading_state': () -> bool
                       - 'get_fav_rotation_switch': () -> Gtk.Switch
                       - 'get_parent_window': () -> Gtk.Window
                       - 'get_application': () -> Gtk.Application
        """
        self.handler = handler
        self.backend = backend
        self.ie = ie
        self._callbacks = {}  # Se configurarán después con set_callbacks()

        # Construir la interfaz
        self.widget = self._build()
        left_col.pack_start(self.widget, False, False, 0)

    def set_callbacks(self, callbacks):
        """Asigna los callbacks después de que la instancia exista."""
        self._callbacks = callbacks or {}

    # ==========================================================
    # PROPIEDADES DE ACCESO RÁPIDO A CALLBACKS
    # ==========================================================
    @property
    def _loading(self):
        """Devuelve True si el panel está en estado de carga."""
        cb = self._callbacks.get('get_loading_state')
        return cb() if cb else False

    @property
    def _edit_mode_active(self):
        """Devuelve True si el modo edición está activo."""
        cb = self._callbacks.get('get_edit_mode_active')
        return cb() if cb else False

    @property
    def _parent_window(self):
        """Devuelve la ventana principal del panel."""
        cb = self._callbacks.get('get_parent_window')
        return cb() if cb else None

    def _create_section_label(self, text):
        """Crea una etiqueta de sección usando el callback del panel."""
        cb = self._callbacks.get('create_section_label')
        if cb:
            return cb(text)
        # Fallback si no hay callback
        label = Gtk.Label()
        label.set_markup(f"<span weight='bold' size='medium'>{text}</span>")
        label.set_halign(Gtk.Align.START)
        return label

    def _notify_engine(self, action=None):
        """Envía una acción al motor."""
        cb = self._callbacks.get('notify_engine')
        if cb:
            cb(action)

    def _load_monitors(self):
        """Refresca la vista de monitores."""
        cb = self._callbacks.get('load_monitors')
        if cb:
            cb()

    def _set_monitor_switches_sensitive(self, sensitive):
        """Activa/desactiva los switches de monitor."""
        cb = self._callbacks.get('set_monitor_switches_sensitive')
        if cb:
            cb(sensitive)

    # ==========================================================
    # CONSTRUCCIÓN DE LA INTERFAZ
    # ==========================================================
    def _build(self):
        """Construye y devuelve el widget principal de la sección."""
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)

        # ----------------------------------------------------------
        # CABECERA DE OPTIONS
        # ----------------------------------------------------------
        # --- Options: despliegue de la sección principal ---
        hbox_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.options_toggle = Gtk.EventBox()
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)

        # Icono independiente del texto para conservar su geometría entre sistemas.
        self.options_arrow = Gtk.Image.new_from_icon_name(
            "media-playback-start-symbolic", Gtk.IconSize.BUTTON)
        self.options_arrow.set_pixel_size(12)
        self.options_arrow.set_valign(Gtk.Align.CENTER)
        self.options_arrow.get_style_context().add_class("wmm-playback-down")
        title_box.pack_start(self.options_arrow, False, False, 0)

        self.options_label = self._create_section_label(_("Options"))
        self.options_label.set_margin_top(8)
        self.options_label.set_margin_bottom(8)
        title_box.pack_start(self.options_label, False, False, 0)
        self.options_toggle.add(title_box)
        self.options_toggle.set_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.options_toggle.connect("button-press-event", self._on_options_toggle)
        hbox_header.pack_start(self.options_toggle, True, True, 0)

        # --- Botones de acción de la cabecera ---
        action_block = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        action_block.set_valign(Gtk.Align.CENTER)

        # --- Open Help ---
        self.help_btn = Gtk.Button.new_from_icon_name("help-contents", Gtk.IconSize.BUTTON)
        self.help_btn.set_tooltip_text(_("Open Help"))
        self.help_btn.connect("clicked", self._on_open_help)
        action_block.pack_start(self.help_btn, False, False, 0)

        # --- Open Debug Log Viewer ---
        self.debug_log_btn = Gtk.Button.new_from_icon_name("text-x-generic", Gtk.IconSize.BUTTON)
        self.debug_log_btn.set_tooltip_text(_("Open Debug Log Viewer"))
        self.debug_log_btn.connect("clicked", self._on_open_debug_log)
        action_block.pack_start(self.debug_log_btn, False, False, 0)

        # --- Restart engine and panel ---
        self.restart_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        self.restart_btn.set_tooltip_text(_("Restart engine and panel"))
        self.restart_btn.set_margin_start(10)
        self.restart_btn.connect("clicked", self._on_restart_clicked)
        action_block.pack_start(self.restart_btn, False, False, 0)

        # --- Collapse side panel ---
        self.collapse_btn = Gtk.Button.new_from_icon_name(
            "media-playback-start-symbolic", Gtk.IconSize.BUTTON)
        self.collapse_btn.get_image().set_pixel_size(14)
        self.collapse_btn.get_image().get_style_context().add_class("wmm-playback-left")

        self.collapse_btn.set_tooltip_text(_("Collapse side panel"))
        self.collapse_btn.set_margin_start(8)
        self.collapse_btn.connect("clicked", self._on_collapse_clicked)
        action_block.pack_start(self.collapse_btn, False, False, 0)

        hbox_header.pack_end(action_block, False, False, 0)

        vbox.pack_start(hbox_header, False, False, 0)
        vbox.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0)

        # ----------------------------------------------------------
        # CONTENIDO PLEGABLE: SECCIONES EN ORDEN VISUAL
        # ----------------------------------------------------------
        self.options_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        vbox.pack_start(self.options_content, False, False, 0)

        # ----------------------------------------------------------
        # CHANGE WALLPAPER ON STARTUP
        # ----------------------------------------------------------
        # --- Cabecera: Change wallpaper on startup ---
        # La cabecera despliega las opciones; el switch conserva
        # exclusivamente la función de cambiar el fondo al arrancar.
        self.persist_switch = Gtk.Switch(active=True, halign=Gtk.Align.END)
        self.persist_switch.set_tooltip_text(
            _("If enabled, the wallpaper is changed at startup; if disabled, the last wallpaper is kept."))
        self.persist_switch.connect("notify::active", self._on_persist_changed)

        hbox_persist = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.persist_toggle = Gtk.EventBox()
        self.persist_toggle.set_events(Gdk.EventMask.BUTTON_PRESS_MASK)

        title_persist = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.persist_arrow = Gtk.Image.new_from_icon_name(
            "media-playback-start-symbolic", Gtk.IconSize.BUTTON)
        self.persist_arrow.set_pixel_size(10)
        self.persist_arrow.set_valign(Gtk.Align.CENTER)
        self.persist_arrow.get_style_context().add_class("wmm-playback-down")
        title_persist.pack_start(self.persist_arrow, False, False, 0)
        title_persist.pack_start(Gtk.Label(
            label=_("Change wallpaper on startup"),
            halign=Gtk.Align.START), False, False, 0)

        self.persist_toggle.add(title_persist)
        self.persist_toggle.connect(
            "button-press-event", self._on_persist_section_toggle)
        hbox_persist.pack_start(self.persist_toggle, True, True, 0)
        hbox_persist.pack_start(self.persist_switch, False, False, 0)
        self.options_content.pack_start(hbox_persist, False, False, 1)

        # Los controles de rotación son independientes del switch de arranque.
        self.persist_content = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=1)
        self.options_content.pack_start(self.persist_content, False, False, 1)

        # --- Match monitor orientation ---
        # La orientación filtra la selección, independientemente
        # del cambio de fondo al iniciar o del temporizador.
        self.match_orientation_switch = Gtk.Switch(
            active=True, halign=Gtk.Align.END)
        self.match_orientation_switch.set_tooltip_text(
            _("Selects images matching the monitor's orientation. "
              "When disabled, images of any orientation can be used."))
        self.match_orientation_switch.connect(
            "notify::active", self._on_match_orientation_changed)

        hbox_orientation = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        hbox_orientation.pack_start(Gtk.Label(
            label=_("Select by monitor orientation"),
            halign=Gtk.Align.START), True, True, 0)
        hbox_orientation.pack_start(
            self.match_orientation_switch, False, False, 0)
        self.persist_content.pack_start(hbox_orientation, False, False, 1)

        # --- Selective rotation ---

        # El modo puede desactivarse sin perder las carpetas marcadas.
        self.selective_rotation_switch = Gtk.Switch(
            active=False, halign=Gtk.Align.END)

        # El contenedor conserva el tooltip cuando GTK deshabilita el switch.
        self.selective_rotation_tooltip = Gtk.EventBox()
        self.selective_rotation_tooltip.set_visible_window(False)
        self.selective_rotation_tooltip.add(self.selective_rotation_switch)
        self.selective_rotation_switch.connect(
            "notify::active", self._on_selective_rotation_changed)

        hbox_selective = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        hbox_selective.pack_start(Gtk.Label(
            label=_("Selective rotation"), halign=Gtk.Align.START), True, True, 0)
        hbox_selective.pack_start(
            self.selective_rotation_tooltip, False, False, 0)
        self.persist_content.pack_start(hbox_selective, False, False, 1)

        # --- Slideshow mode ---
        self.mode_switch = Gtk.Switch(active=True, halign=Gtk.Align.END)
        self.mode_switch.set_tooltip_text(
            _("Sync: All Screens change at once") + "\n" + _("Async: Change by turns"))
        self.mode_switch.connect("notify::active", self._on_mode_changed)
        self.mode_info_label = Gtk.Label(label="", halign=Gtk.Align.CENTER, margin_left=8)
        hbox_mode = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        hbox_mode.pack_start(Gtk.Label(label=
            _("Rotation") + ":", halign=Gtk.Align.START), False, False, 0)
        hbox_mode.pack_start(self.mode_info_label, True, True, 0)
        hbox_mode.pack_start(self.mode_switch, False, False, 0)
        self.persist_content.pack_start(hbox_mode, False, False, 1)

        # El separador pertenece al contenido plegable.
        self.persist_content.pack_start(
            Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0)

        # ----------------------------------------------------------
        # SPANNED
        # ----------------------------------------------------------
        # --- Cabecera: Spanned ---
        self.spanned_switch = Gtk.Switch(active=False, halign=Gtk.Align.END)
        self.spanned_switch.set_tooltip_text(
            _("Span image across all active screens (Only if more than one)"))
        self.spanned_switch.connect("notify::active", self._on_spanned_changed)

        # Cabecera plegable: el título controla el despliegue;
        # el switch mantiene exclusivamente la función panorámica.
        hbox_spanned = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.spanned_toggle = Gtk.EventBox()
        self.spanned_toggle.set_events(Gdk.EventMask.BUTTON_PRESS_MASK)

        title_spanned = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.spanned_arrow = Gtk.Image.new_from_icon_name(
            "media-playback-start-symbolic", Gtk.IconSize.BUTTON)
        self.spanned_arrow.set_pixel_size(10)
        self.spanned_arrow.set_valign(Gtk.Align.CENTER)
        self.spanned_arrow.get_style_context().add_class("wmm-playback-down")
        title_spanned.pack_start(self.spanned_arrow, False, False, 0)
        title_spanned.pack_start(Gtk.Label(
            label=_("Spanned") + ":", halign=Gtk.Align.START), False, False, 0)

        self.spanned_toggle.add(title_spanned)
        self.spanned_toggle.connect("button-press-event", self._on_spanned_section_toggle)
        hbox_spanned.pack_start(self.spanned_toggle, True, True, 0)
        hbox_spanned.pack_start(self.spanned_switch, False, False, 0)
        self.options_content.pack_start(hbox_spanned, False, False, 1)

        # Contenedor de los parámetros dependientes de Imagen panorámica.
        self.spanned_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.options_content.pack_start(self.spanned_content, False, False, 1)

        # --- Picture aspect ---
        hbox_aspect = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        hbox_aspect.pack_start(Gtk.Label(label=
            _("Picture aspect") + ":", halign=Gtk.Align.START), True, True, 0)
        self.aspect_combo = Gtk.ComboBoxText()
        self.aspect_combo.set_valign(Gtk.Align.CENTER)
        for key, label in ConfigHandler.ASPECT_MODES.items():
            self.aspect_combo.append_text(_(label))
        self.aspect_combo.set_active(0)
        self.aspect_combo.connect("changed", self._on_aspect_changed)
        hbox_aspect.pack_start(self.aspect_combo, False, False, 0)
        self.spanned_content.pack_start(hbox_aspect, False, False, 1)

        # --- Image Effect ---
        self.image_effect_combo = Gtk.ComboBoxText()
        self.image_effect_combo.set_valign(Gtk.Align.CENTER)
        for key, label in ConfigHandler.IMAGE_EFFECT.items():
            self.image_effect_combo.append_text(_(label))
        self.image_effect_combo.set_active(0)
        self.image_effect_combo.connect("changed", self._on_image_effect_changed)
        hbox_img_effect = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        hbox_img_effect.pack_start(Gtk.Label(label=
            _("Image Effect") + ":", halign=Gtk.Align.START), True, True, 0)
        hbox_img_effect.pack_start(self.image_effect_combo, False, False, 0)
        self.spanned_content.pack_start(hbox_img_effect, False, False, 1)

        # --- Background Effect ---
        self.back_effect_combo = Gtk.ComboBoxText()
        self.back_effect_combo.set_valign(Gtk.Align.CENTER)
        for key, label in ConfigHandler.BACK_EFFECT.items():
            self.back_effect_combo.append_text(_(label))
        self.back_effect_combo.set_active(0)
        self.back_effect_combo.connect("changed", self._on_back_effect_changed)
        hbox_back_effect = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        hbox_back_effect.pack_start(Gtk.Label(
            label=_("Background Effect") + ":", halign=Gtk.Align.START), True, True, 0)
        hbox_back_effect.pack_start(self.back_effect_combo, False, False, 0)
        self.spanned_content.pack_start(hbox_back_effect, False, False, 1)

        # --- Background color ---
        hbox_color = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        hbox_color.pack_start(Gtk.Label(label=
            _("Background color") + ":", halign=Gtk.Align.START), True, True, 0)

        self.bg_mode_combo = Gtk.ComboBoxText()
        self.bg_mode_combo.set_valign(Gtk.Align.CENTER)
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

        color_controls_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        color_controls_box.pack_end(self.bg_mode_combo, False, False, 0)
        color_controls_box.pack_end(self.bg_color_box, False, False, 0)
        hbox_color.pack_end(color_controls_box, False, False, 0)
        self.spanned_content.pack_start(hbox_color, False, False, 1)
        # El separador pertenece al contenido plegable.
        self.spanned_content.pack_start(
            Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0)

        # ----------------------------------------------------------
        # SLIDESHOW
        # ----------------------------------------------------------
        # --- Cabecera: Slideshow ---
        self.slideshow_switch = Gtk.Switch(active=True, halign=Gtk.Align.END)
        self.slideshow_switch.set_tooltip_text(_("Enable/Disable Timer"))
        self.slideshow_switch.connect("notify::active", self._on_slideshow_changed)

        # Cabecera plegable: título y switch independientes.
        hbox_slideshow = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.slideshow_toggle = Gtk.EventBox()
        self.slideshow_toggle.set_events(Gdk.EventMask.BUTTON_PRESS_MASK)

        title_slideshow = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.slideshow_arrow = Gtk.Image.new_from_icon_name(
            "media-playback-start-symbolic", Gtk.IconSize.BUTTON)
        self.slideshow_arrow.set_pixel_size(10)
        self.slideshow_arrow.set_valign(Gtk.Align.CENTER)
        self.slideshow_arrow.get_style_context().add_class("wmm-playback-down")
        title_slideshow.pack_start(self.slideshow_arrow, False, False, 0)
        title_slideshow.pack_start(Gtk.Label(
            label=_("Slideshow"), halign=Gtk.Align.START), False, False, 0)

        self.slideshow_toggle.add(title_slideshow)
        self.slideshow_toggle.connect(
            "button-press-event", self._on_slideshow_section_toggle)
        hbox_slideshow.pack_start(self.slideshow_toggle, True, True, 0)
        hbox_slideshow.pack_start(self.slideshow_switch, False, False, 0)
        self.options_content.pack_start(hbox_slideshow, False, False, 1)

        # Parámetros plegables; independientes de la activación del temporizador.
        self.slideshow_content = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.options_content.pack_start(self.slideshow_content, False, False, 1)
        self._slideshow_typed_spins = set()

        # --- Max. Frequency ---
        hbox_max = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        hbox_max.pack_start(Gtk.Label(label=_("Max. Frequency") + ": " + "(" + _("minutes") + ")",
            halign=Gtk.Align.START), True, True, 0)
        self.max_interval_spin = Gtk.SpinButton.new_with_range(1, 999, 1)
        self.max_interval_spin.set_value(60)
        self._max_interval_changed_id = self.max_interval_spin.connect(
            "value-changed", self._on_max_interval_changed)
        self.max_interval_spin.connect("changed", self._on_slideshow_spin_text_changed)
        self.max_interval_spin.connect("activate", self._on_slideshow_spin_activate)
        self.max_interval_spin.connect("focus-out-event", self._on_slideshow_spin_focus_out)
        hbox_max.pack_start(self.max_interval_spin, False, False, 0)
        self.slideshow_content.pack_start(hbox_max, False, False, 1)

        # --- Slideshow every ---
        hbox_rot = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        hbox_rot.pack_start(Gtk.Label(label=_("Slideshow every") + ": " + "(" + _("minutes") + ")",
            halign=Gtk.Align.START), True, True, 0)
        self.rotation_spin = Gtk.SpinButton.new_with_range(1, 99, 1)
        self.rotation_spin.set_value(15)
        self.rotation_spin.connect("value-changed", self._on_rotation_changed)
        self.rotation_spin.connect("changed", self._on_slideshow_spin_text_changed)
        self.rotation_spin.connect("activate", self._on_slideshow_spin_activate)
        self.rotation_spin.connect("focus-out-event", self._on_slideshow_spin_focus_out)
        hbox_rot.pack_start(self.rotation_spin, False, False, 0)
        self.slideshow_content.pack_start(hbox_rot, False, False, 1)

        # El separador pertenece al contenido plegable.
        self.slideshow_content.pack_start(
            Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0)

        # ----------------------------------------------------------
        # IMAGE METADATA
        # ----------------------------------------------------------
        # --- Cabecera: Image Metadata ---
        # La cabecera despliega los ajustes; el switch sólo habilita la función.
        self.metadata_switch = Gtk.Switch(active=False, halign=Gtk.Align.END)
        self.metadata_switch.set_tooltip_text(_("Show/Hide image metadata"))
        self.metadata_switch.connect("notify::active", self._on_metadata_changed)

        hbox_metadata = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.metadata_toggle = Gtk.EventBox()
        self.metadata_toggle.set_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        title_metadata = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.metadata_arrow = Gtk.Image.new_from_icon_name(
            "media-playback-start-symbolic", Gtk.IconSize.BUTTON)
        self.metadata_arrow.set_pixel_size(10)
        self.metadata_arrow.set_valign(Gtk.Align.CENTER)
        self.metadata_arrow.get_style_context().add_class("wmm-playback-down")
        title_metadata.pack_start(self.metadata_arrow, False, False, 0)
        title_metadata.pack_start(Gtk.Label(
            label=_("Image Metadata"), halign=Gtk.Align.START), False, False, 1)
        self.metadata_toggle.add(title_metadata)
        self.metadata_toggle.connect(
            "button-press-event", self._on_metadata_section_toggle)
        hbox_metadata.pack_start(self.metadata_toggle, True, True, 0)
        hbox_metadata.pack_start(self.metadata_switch, False, False, 0)
        self.options_content.pack_start(hbox_metadata, False, False, 0)

        self.metadata_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.options_content.pack_start(self.metadata_content, False, False, 1)

        # --- Visible fields ---
        hbox_fields = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        hbox_fields.pack_start(Gtk.Label(
            label=_("Visible fields") + ":", halign=Gtk.Align.START), True, True, 0)

        self.metadata_fields_button = Gtk.Button(label=_("Select"))
        self.metadata_fields_button.connect("clicked", self._on_metadata_fields_clicked)
        hbox_fields.pack_start(self.metadata_fields_button, False, False, 0)
        self.metadata_content.pack_start(hbox_fields, False, False, 1)

        # --- Font and size ---
        hbox_metadata_font = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        hbox_metadata_font.pack_start(Gtk.Label(
            label=_("Font and size") + ":", halign=Gtk.Align.START), True, True, 0)
        self.metadata_font_button = Gtk.FontButton()
        self.metadata_font_button.set_use_font(True)
        self.metadata_font_button.set_use_size(False)
        self.metadata_font_button.connect("font-set", self._on_metadata_font_changed)
        self.metadata_font_button.connect("notify::font", self._truncate_metadata_font_label)
        hbox_metadata_font.pack_start(self.metadata_font_button, False, False, 0)
        self.metadata_content.pack_start(hbox_metadata_font, False, False, 1)

        # --- Position ---
        hbox_metadata_position = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        hbox_metadata_position.pack_start(Gtk.Label(
            label=_("Position") + ":", halign=Gtk.Align.START), True, True, 0)

        self.metadata_position_combo = Gtk.ComboBoxText()
        self.metadata_position_combo.set_valign(Gtk.Align.CENTER)
        for key, label in ConfigHandler.METADATA_POSITIONS.items():
            self.metadata_position_combo.append(key, _(label))
        self.metadata_position_combo.set_active_id("top_left")
        self.metadata_position_combo.connect(
            "changed", self._on_metadata_position_changed)

        hbox_metadata_position.pack_start(
            self.metadata_position_combo, False, False, 0)
        self.metadata_content.pack_start(hbox_metadata_position, False, False, 1)

        # --- Horizontal margin ---
        # Márgenes independientes para adaptar los metadatos a los paneles del escritorio.
        hbox_metadata_margin_x = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        hbox_metadata_margin_x.pack_start(Gtk.Label(
            label=_("Horizontal margin") + ":", halign=Gtk.Align.START), True, True, 0)

        self.metadata_margin_x_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.metadata_margin_x_scale.set_digits(0)
        self.metadata_margin_x_scale.set_value_pos(Gtk.PositionType.LEFT)
        self.metadata_margin_x_scale.set_size_request(180, -1)
        self.metadata_margin_x_scale.set_value(64)

        # Ambos márgenes comparten una confirmación para evitar recomposiciones duplicadas.
        self._metadata_margin_dragging = False
        self._metadata_margin_commit_id = None

        self.metadata_margin_x_scale.connect(
            "format-value", lambda scale, value: f"{round(value)} px")
        self.metadata_margin_x_scale.connect(
            "button-press-event", self._on_metadata_margin_pressed)
        self.metadata_margin_x_scale.connect(
            "value-changed", self._on_metadata_margin_changed)
        self.metadata_margin_x_scale.connect(
            "button-release-event", self._on_metadata_margin_released)

        hbox_metadata_margin_x.pack_start(
            self.metadata_margin_x_scale, False, False, 0)
        self.metadata_content.pack_start(hbox_metadata_margin_x, False, False, 0)

        # --- Vertical margin ---
        hbox_metadata_margin_y = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        hbox_metadata_margin_y.pack_start(Gtk.Label(
            label=_("Vertical margin") + ":", halign=Gtk.Align.START), True, True, 0)

        self.metadata_margin_y_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.metadata_margin_y_scale.set_digits(0)
        self.metadata_margin_y_scale.set_value_pos(Gtk.PositionType.LEFT)
        self.metadata_margin_y_scale.set_size_request(180, -1)
        self.metadata_margin_y_scale.set_value(42)
        self.metadata_margin_y_scale.connect(
            "format-value", lambda scale, value: f"{round(value)} px")
        self.metadata_margin_y_scale.connect(
            "button-press-event", self._on_metadata_margin_pressed)
        self.metadata_margin_y_scale.connect(
            "value-changed", self._on_metadata_margin_changed)
        self.metadata_margin_y_scale.connect(
            "button-release-event", self._on_metadata_margin_released)

        hbox_metadata_margin_y.pack_start(
            self.metadata_margin_y_scale, False, False, 0)
        self.metadata_content.pack_start(hbox_metadata_margin_y, False, False, 0)

        # --- Background opacity ---
        # Opacidad del fondo del bloque EXIF (0 = transparente, 100 = opaco).
        hbox_metadata_opacity = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        hbox_metadata_opacity.pack_start(Gtk.Label(
            label=_("Background opacity") + ":", halign=Gtk.Align.START), True, True, 0)

        self.metadata_opacity_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.metadata_opacity_scale.set_digits(0)
        self.metadata_opacity_scale.set_value_pos(Gtk.PositionType.LEFT)
        self.metadata_opacity_scale.set_size_request(170, -1)
        self.metadata_opacity_scale.set_value(40)
        self._metadata_opacity_dragging = False
        self._metadata_opacity_commit_id = None
        self.metadata_opacity_scale.connect(
            "format-value", lambda scale, value: f"{round(value)}%")
        self.metadata_opacity_scale.connect(
            "button-press-event", self._on_metadata_opacity_pressed)
        self.metadata_opacity_scale.connect(
            "value-changed", self._on_metadata_opacity_changed)
        self.metadata_opacity_scale.connect(
            "button-release-event", self._on_metadata_opacity_released)

        hbox_metadata_opacity.pack_start(
            self.metadata_opacity_scale, False, False, 0)
        self.metadata_content.pack_start(hbox_metadata_opacity, False, False, 0)

        # ----------------------------------------------------------
        # TOOLTIPS DE DESCUBRIMIENTO DE LAS SUBSECCIONES
        # ----------------------------------------------------------
        # Cada texto enumera controles ocultos y reutiliza sus traducciones.
        # La cabecera sólo muestra el tooltip si su contenido está plegado.
        self._subsection_tooltips = {
            "persist": (self.persist_toggle,
                "• " + _("Select by monitor orientation") + "\n"
                "• " + _("Selective rotation") + "\n"
                "• " + _("Rotation")),
            "spanned": (self.spanned_toggle,
                "• " + _("Picture aspect") + "\n"
                "• " + _("Image Effect") + "\n"
                "• " + _("Background Effect") + "\n"
                "• " + _("Background color")),
            "slideshow": (self.slideshow_toggle,
                "• " + _("Max. Frequency") + "\n"
                "• " + _("Slideshow every")),
            "metadata": (self.metadata_toggle,
                "• " + _("Visible fields") + "\n"
                "• " + _("Font and size") + "\n"
                "• " + _("Position") + "\n"
                "• " + _("Horizontal margin") + "\n"
                "• " + _("Vertical margin") + "\n"
                "• " + _("Background opacity"))
        }

        self.options_content.pack_start(Gtk.Separator(
            orientation=Gtk.Orientation.HORIZONTAL), False, False, 0)

        return vbox

    def _update_subsection_tooltip(self, name, expanded):
        """Enumera los controles ocultos sólo mientras su cabecera está plegada."""
        toggle, description = self._subsection_tooltips[name]
        toggle.set_tooltip_text(None if expanded else description)

    def _on_persist_section_toggle(self, widget, event):
        """Pliega las opciones de rotación sin alterar el switch de arranque."""
        expanded = not self.persist_content.get_visible()
        self.persist_content.set_visible(expanded)

        arrow_style = self.persist_arrow.get_style_context()
        if expanded:
            arrow_style.add_class("wmm-playback-down")
            self._parent_window._expand_section_to_fit(
                "options", requested_subsection="persist")
        else:
            arrow_style.remove_class("wmm-playback-down")
            GLib.idle_add(self._parent_window._fit_collapsed)

        self._update_subsection_tooltip("persist", expanded)
        self._parent_window._save_options_subsection_states()
        self.widget.queue_resize()
        return True

    def _on_metadata_section_toggle(self, widget, event):
        """Pliega los ajustes EXIF sin alterar la activación del overlay."""
        expanded = not self.metadata_content.get_visible()
        self.metadata_content.set_visible(expanded)
        arrow_style = self.metadata_arrow.get_style_context()
        if expanded:
            arrow_style.add_class("wmm-playback-down")
            self._parent_window._expand_section_to_fit(
                "options", requested_subsection="metadata")
        else:
            arrow_style.remove_class("wmm-playback-down")
            GLib.idle_add(self._parent_window._fit_collapsed)

        self._update_subsection_tooltip("metadata", expanded)
        self._parent_window._save_options_subsection_states()
        self.widget.queue_resize()
        return True

    def _on_spanned_section_toggle(self, widget, event):
        """Pliega los parámetros sin modificar el estado panorámico."""
        expanded = not self.spanned_content.get_visible()
        self.spanned_content.set_visible(expanded)

        arrow_style = self.spanned_arrow.get_style_context()
        if expanded:
            arrow_style.add_class("wmm-playback-down")
            self._parent_window._expand_section_to_fit(
                "options", requested_subsection="spanned")
        else:
            arrow_style.remove_class("wmm-playback-down")
            GLib.idle_add(self._parent_window._fit_collapsed)

        self._update_subsection_tooltip("spanned", expanded)
        self._parent_window._save_options_subsection_states()
        self.widget.queue_resize()
        return True

    def _on_slideshow_section_toggle(self, widget, event):
        """Pliega los parámetros sin modificar el estado del temporizador."""
        expanded = not self.slideshow_content.get_visible()
        self.slideshow_content.set_visible(expanded)

        arrow_style = self.slideshow_arrow.get_style_context()
        if expanded:
            arrow_style.add_class("wmm-playback-down")
            self._parent_window._expand_section_to_fit(
                "options", requested_subsection="slideshow")
        else:
            arrow_style.remove_class("wmm-playback-down")
            GLib.idle_add(self._parent_window._fit_collapsed)

        self._update_subsection_tooltip("slideshow", expanded)
        self._parent_window._save_options_subsection_states()
        self.widget.queue_resize()
        return True

    def _on_options_toggle(self, widget, event):
        """Pliega o despliega el contenido de Opciones."""
        expanded = not self.options_content.get_visible()

        if expanded:
            self._parent_window._expand_section_to_fit("options")
        else:
            self.set_expanded(False)

        self._parent_window._save_section_state("options", expanded)

        if not expanded:
            GLib.idle_add(self._parent_window._fit_collapsed)

    def set_expanded(self, expanded):
        """Aplica el estado de despliegue de Opciones sin persistirlo."""
        self.options_content.set_visible(expanded)
        # Sólo cambia la orientación; la etiqueta conserva su formato.
        arrow_style = self.options_arrow.get_style_context()
        if expanded:
            arrow_style.add_class("wmm-playback-down")
        else:
            arrow_style.remove_class("wmm-playback-down")
        self.widget.queue_resize()

    def set_subsection_expanded(self, name, expanded):
        """Modifica el plegado visual sin alterar los controles funcionales."""
        subsections = {
            "persist": (self.persist_content, self.persist_arrow),
            "spanned": (self.spanned_content, self.spanned_arrow),
            "slideshow": (self.slideshow_content, self.slideshow_arrow),
            "metadata": (self.metadata_content, self.metadata_arrow),
        }

        content, arrow = subsections[name]
        content.set_visible(expanded)

        style = arrow.get_style_context()
        if expanded:
            style.add_class("wmm-playback-down")
        else:
            style.remove_class("wmm-playback-down")

        self._update_subsection_tooltip(name, expanded)
        self.widget.queue_resize()

    def restore_subsection_states(self, states):
        """Restaura los cuatro desplegables sin modificar sus interruptores."""
        for name, content, arrow in (
                ("persist", self.persist_content, self.persist_arrow),
                ("spanned", self.spanned_content, self.spanned_arrow),
                ("slideshow", self.slideshow_content, self.slideshow_arrow),
                ("metadata", self.metadata_content, self.metadata_arrow)):
            expanded = states.get(name, name != "persist")
            content.set_visible(expanded)
            style = arrow.get_style_context()
            if expanded:
                style.add_class("wmm-playback-down")
            else:
                style.remove_class("wmm-playback-down")
            self._update_subsection_tooltip(name, expanded)

    # ==========================================================
    # EVENTOS DE OPCIONES
    # ==========================================================
    def _refresh_metadata_preview(self):
        """Recompone las imágenes actuales usando el circuito manual existente."""
        self._notify_engine({"action": "apply_manual_selection"})
        if not self._edit_mode_active:
            self._load_monitors()

    def _on_aspect_changed(self, combo):
        if self._loading:
            return
        index = combo.get_active()
        keys = list(ConfigHandler.ASPECT_MODES.keys())
        if 0 <= index < len(keys):
            mode = keys[index]
            self.backend.save_setting("wallpaper_mode", mode)
            self._notify_engine({"action": "apply_manual_selection"})
            if not self._edit_mode_active:
                self._load_monitors()

    def _on_bg_mode_changed(self, combo):
        if self._loading:
            return
        index = combo.get_active()
        keys = list(ConfigHandler.COLOR_MODES.keys())
        if 0 <= index < len(keys):
            mode = keys[index]
            self.backend.save_setting("color_mode", mode)
            self._notify_engine({"action": "apply_manual_selection"})
            self._update_bg_color_buttons(mode)
            if not self._edit_mode_active:
                self._load_monitors()

    def _update_bg_color_buttons(self, mode):
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
        if self._loading:
            return
        color = button.get_rgba()
        hex_color = "#{:02X}{:02X}{:02X}".format(
            int(color.red * 255), int(color.green * 255), int(color.blue * 255))
        self.backend.save_setting("solid_color", hex_color)
        self._notify_engine({"action": "apply_manual_selection"})
        if not self._edit_mode_active:
            self._load_monitors()

    def _on_gradient_h_changed(self, button):
        if self._loading:
            return
        start = self.grad_h_start_btn.get_rgba()
        end = self.grad_h_end_btn.get_rgba()
        hex_start = "#{:02X}{:02X}{:02X}".format(
            int(start.red*255), int(start.green*255), int(start.blue*255))
        hex_end = "#{:02X}{:02X}{:02X}".format(
            int(end.red*255), int(end.green*255), int(end.blue*255))
        self.backend.save_setting("gradient_h", [hex_start, hex_end])
        self._notify_engine({"action": "apply_manual_selection"})
        if not self._edit_mode_active:
            self._load_monitors()

    def _on_gradient_v_changed(self, button):
        if self._loading:
            return
        start = self.grad_v_start_btn.get_rgba()
        end = self.grad_v_end_btn.get_rgba()
        hex_start = "#{:02X}{:02X}{:02X}".format(
            int(start.red*255), int(start.green*255), int(start.blue*255))
        hex_end = "#{:02X}{:02X}{:02X}".format(
            int(end.red*255), int(end.green*255), int(end.blue*255))
        self.backend.save_setting("gradient_v", [hex_start, hex_end])
        self._notify_engine({"action": "apply_manual_selection"})
        if not self._edit_mode_active:
            self._load_monitors()

    def _on_metadata_fields_clicked(self, button):
        """Selecciona campos EXIF; Aplicar confirma sin cerrar y Cancelar descarta lo pendiente."""
        field_groups = ConfigHandler.METADATA_FIELD_GROUPS
        saved = self.backend.load_settings().get("exif_metadata_fields", [])
        selected = set(saved) if isinstance(saved, list) else set()

        dialog = Gtk.Dialog(title=_("Metadata") + ": " + _("Visible fields"),
            transient_for=self._parent_window, flags=Gtk.DialogFlags.MODAL)
        dialog.add_buttons(
            _("Cancel"), Gtk.ResponseType.CANCEL,
            _("Apply"), Gtk.ResponseType.APPLY,
            _("Save"), Gtk.ResponseType.OK)
        dialog.set_default_size(-1, -1)
        dialog.set_resizable(False)

        # Utilizar el icono propio de WMM cuando esté disponible.
        icon_path = self.handler._platform.icon_path
        if os.path.isfile(icon_path):
            dialog.set_icon_from_file(icon_path)

        # Conservar los márgenes laterales e inferior, sin espacio superior.
        action_area = dialog.get_action_area()
        action_area.set_spacing(12)
        action_area.set_border_width(0)
        action_area.set_margin_start(12)
        action_area.set_margin_end(12)
        action_area.set_margin_bottom(12)
        action_area.set_margin_top(4)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_propagate_natural_height(True)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5, margin=12)
        content.get_style_context().add_class("wmm-themed-separators")
        scroll.add(content)
        dialog.get_content_area().pack_start(scroll, True, True, 0)

        checks = []
        for group, fields in field_groups:
            label = Gtk.Label(halign=Gtk.Align.START)
            label.set_markup(f"<b>{GLib.markup_escape_text(_(group))}</b>")
            label.get_style_context().add_class("heading")
            content.pack_start(label, False, False, 0)
            grid = Gtk.Grid(column_spacing=14, row_spacing=3)
            content.pack_start(grid, False, False, 0)

            for index, (key, text) in enumerate(fields):
                field_label = _(text)
                if key == "Geolocation.distance_km":
                    field_label += " (km)"
                elif key == "GPSInfo.AltitudeMeters":
                    field_label += " (m)"

                check = Gtk.CheckButton(label=field_label)
                check.set_active(key in selected)
                grid.attach(check, index % 2, index // 2, 1, 1)
                checks.append((key, check))

            # Reconocer la fuente de referencia geográfica utilizada por WMM.
            # La atribución es informativa y no interviene en la selección.
            if group == "Geolocation":
                attribution = Gtk.Label()
                attribution.set_halign(Gtk.Align.START)
                attribution.set_margin_top(6)
                attribution.set_markup(
                    '<span size="small">'
                    f'{GLib.markup_escape_text(_("Geographic reference data:"))}\n'
                    '<a href="https://github.com/dr5hn/countries-states-cities-database">'
                    'Countries States Cities Database (dr5hn)</a>'
                    '</span>')
                attribution.set_track_visited_links(False)
                content.pack_start(attribution, False, False, 0)

            # Delimitar cada grupo de campos, incluido el último.
            content.pack_start(
                Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL),
                False, False, 0)

        # Referencia persistida: Aplicar establece un nuevo punto de confirmación.
        applied = [key for key, check in checks if check.get_active()]

        dialog.show_all()
        try:
            while True:
                response = dialog.run()
                if response not in (Gtk.ResponseType.APPLY, Gtk.ResponseType.OK):
                    break

                selected = [key for key, check in checks if check.get_active()]
                if selected != applied:
                    self.backend.save_setting("exif_metadata_fields", selected)
                    applied = selected
                    self._refresh_metadata_preview()

                if response == Gtk.ResponseType.OK:
                    break
        finally:
            dialog.destroy()

    def _on_metadata_changed(self, switch, param):
        if self._loading:
            return
        self.backend.save_setting("exif_metadata_enabled", switch.get_active())
        self._refresh_metadata_preview()

    def _truncate_metadata_font_label(self, button, param):
        """Limita el texto visible sin alterar la fuente seleccionada."""
        container = button.get_child()
        if not isinstance(container, Gtk.Box):
            return

        for child in container.get_children():
            if isinstance(child, Gtk.Label):
                name = child.get_text()
                if len(name) > 18:
                    child.set_text(name[:17] + "…")
                break

        button.set_tooltip_text(button.get_font())

    def _cancel_metadata_margin_commit(self):
        """Cancela la confirmación pendiente de ambos márgenes."""
        if self._metadata_margin_commit_id is not None:
            GLib.source_remove(self._metadata_margin_commit_id)
            self._metadata_margin_commit_id = None

    def _on_metadata_margin_pressed(self, scale, event):
        """Evita persistir valores intermedios durante el arrastre."""
        if event.button == 1:
            self._metadata_margin_dragging = True
            self._cancel_metadata_margin_commit()
        return False

    def _on_metadata_margin_changed(self, scale):
        """Agrupa los cambios de teclado y rueda de ambos márgenes."""
        if self._loading or self._metadata_margin_dragging:
            return

        self._cancel_metadata_margin_commit()
        self._metadata_margin_commit_id = GLib.timeout_add(
            800, self._commit_metadata_margins)

    def _commit_metadata_margins(self):
        """Persiste los márgenes modificados y recompone una sola vez."""
        self._metadata_margin_commit_id = None
        if self._loading:
            return False

        settings = self.backend.load_settings()
        margin_x = round(self.metadata_margin_x_scale.get_value())
        margin_y = round(self.metadata_margin_y_scale.get_value())
        changed = False

        if margin_x != settings.get("exif_metadata_margin_x", 64):
            self.backend.save_setting("exif_metadata_margin_x", margin_x)
            changed = True

        if margin_y != settings.get("exif_metadata_margin_y", 42):
            self.backend.save_setting("exif_metadata_margin_y", margin_y)
            changed = True

        if changed:
            self._refresh_metadata_preview()

        return False

    def _on_metadata_margin_released(self, scale, event):
        """Confirma ambos márgenes al liberar el botón izquierdo."""
        if event.button == 1:
            self._metadata_margin_dragging = False
            self._cancel_metadata_margin_commit()
            self._commit_metadata_margins()
        return False

    def _cancel_metadata_opacity_commit(self):
        """Cancela una confirmación pendiente sin alterar el valor del control."""
        if self._metadata_opacity_commit_id is not None:
            GLib.source_remove(self._metadata_opacity_commit_id)
            self._metadata_opacity_commit_id = None

    def _on_metadata_opacity_pressed(self, scale, event):
        """Impide confirmar cambios intermedios durante el uso del ratón."""
        if event.button == 1:
            self._metadata_opacity_dragging = True
            self._cancel_metadata_opacity_commit()
        return False

    def _on_metadata_opacity_changed(self, scale):
        """Agrupa cambios de teclado y rueda sin escribir durante el arrastre."""
        if self._loading or self._metadata_opacity_dragging:
            return

        self._cancel_metadata_opacity_commit()
        self._metadata_opacity_commit_id = GLib.timeout_add(
            800, self._commit_metadata_opacity)

    def _commit_metadata_opacity(self):
        """Persiste y recompone únicamente cuando cambia la opacidad efectiva."""
        self._metadata_opacity_commit_id = None
        if self._loading:
            return False

        opacity = round(self.metadata_opacity_scale.get_value())
        if opacity != self.backend.load_settings().get("exif_metadata_background_opacity", 40):
            self.backend.save_setting("exif_metadata_background_opacity", opacity)
            self._refresh_metadata_preview()
        return False

    def _on_metadata_opacity_released(self, scale, event):
        """Confirma inmediatamente la opacidad al liberar el botón izquierdo."""
        if event.button == 1:
            self._metadata_opacity_dragging = False
            self._cancel_metadata_opacity_commit()
            self._commit_metadata_opacity()
        return False

    def _on_metadata_position_changed(self, combo):
        """Guarda la esquina seleccionada, sin intervenir en el renderizado."""
        if self._loading:
            return
        position = combo.get_active_id()
        if position in ConfigHandler.METADATA_POSITIONS:
            self.backend.save_setting("exif_metadata_position", position)
            self._refresh_metadata_preview()

    def _on_metadata_font_changed(self, button):
        if self._loading:
            return
        self.backend.save_setting("exif_metadata_font", button.get_font())
        self._refresh_metadata_preview()

    def _on_slideshow_changed(self, switch, param):
        if self._loading:
            return
        self._notify_engine(
            {"action": ConfigHandler.CMD_UPDATE_TIMER, "enabled": switch.get_active()})

    def _on_mode_changed(self, switch, param):
        if self._loading:
            return
        mode = "sync" if switch.get_active() else "async"
        self.backend.save_setting("slideshow_mode", mode)
        self._update_mode_info_label()

    def _on_persist_changed(self, switch, param):
        if self._loading:
            return
        self.backend.save_setting("persist_on_reboot", not switch.get_active())

    def _on_match_orientation_changed(self, switch, param):
        """Guarda el filtro H/V sin forzar una nueva rotación."""
        if self._loading:
            return
        self.backend.save_setting("match_orientation", switch.get_active())

    def refresh_selective_rotation_availability(self):
        """Sincroniza la disponibilidad con las carpetas activas y marcadas."""
        index = self.backend.load_json("index")
        available = any(
            isinstance(entry, list) and len(entry) == 2
            and entry[0] and entry[1]
            for entry in index.values())

        switch = self.selective_rotation_switch
        switch.set_sensitive(available)

        tooltip = (
            _("Enable selective rotation without changing folder selections")
            if available else
            _("Select at least one active folder in Sources to enable selective rotation"))
        self.selective_rotation_tooltip.set_tooltip_text(tooltip)

        if available:
            return

        # Sin carpetas elegibles, el modo tampoco puede permanecer
        # activado en settings.json tras un cambio de Sources.
        saved = self.backend.load_settings().get(
            "selective_rotation_enabled", False)
        was_active = switch.get_active()

        if saved:
            self.backend.save_setting("selective_rotation_enabled", False)
        if was_active:
            switch.set_active(False)

        if saved or was_active:
            cb = self._callbacks.get("set_selective_rotation_mode")
            if cb:
                cb(False)

    def _on_selective_rotation_changed(self, switch, param):
        """Solicita al motor el cambio de autoridad de rotación."""
        if self._loading:
            return

        enabled = switch.get_active()

        # No reenviar estados que ya están persistidos.
        if enabled == self.backend.load_settings().get(
                "selective_rotation_enabled", False):
            return

        # El motor resuelve conjuntamente Selective, Favorites y Slideshow.
        # El Panel reflejará el estado confirmado mediante settings_updated.
        self._notify_engine({
            "action": ConfigHandler.CMD_SET_SELECTIVE_ROTATION,
            "enabled": enabled,
        })

    def _on_spanned_changed(self, switch, param):
        if self._loading:
            return
        self.backend.save_setting("spanned_enabled", switch.get_active())
        self._notify_engine({"action": "apply_manual_selection"})
        self._set_monitor_switches_sensitive(not switch.get_active())
        if not self._edit_mode_active:
            self._load_monitors()

    def _on_image_effect_changed(self, combo):
        if self._loading:
            return
        keys = list(ConfigHandler.IMAGE_EFFECT.keys())
        index = combo.get_active()
        if 0 <= index < len(keys):
            self.backend.save_setting("wallpaper_effect", keys[index])
            self._notify_engine({"action": "apply_manual_selection"})
            if not self._edit_mode_active:
                self._load_monitors()

    def _on_back_effect_changed(self, combo):
        if self._loading:
            return
        keys = list(ConfigHandler.BACK_EFFECT.keys())
        index = combo.get_active()
        if 0 <= index < len(keys):
            self.backend.save_setting("wallpaper_effect_scope", keys[index])
            self._notify_engine({"action": "apply_manual_selection"})
            if not self._edit_mode_active:
                self._load_monitors()

    def _on_slideshow_spin_text_changed(self, spin):
        """Distingue la edición textual de los incrementos del selector."""
        if not self._loading and spin.get_text() != str(spin.get_value_as_int()):
            self._slideshow_typed_spins.add(spin)

    def _on_slideshow_spin_activate(self, spin):
        """Confirma inmediatamente la edición mediante Enter."""
        if self._loading:
            return
        spin.update()
        self._slideshow_typed_spins.discard(spin)
        self._commit_slideshow_now()
        self._parent_window.set_focus(None)

    def _on_slideshow_spin_focus_out(self, spin, event):
        """Confirma al perder el foco sólo si existió edición textual."""
        if not self._loading and spin in self._slideshow_typed_spins:
            spin.update()
            self._slideshow_typed_spins.discard(spin)
            self._commit_slideshow_now()
        return False

    def _commit_slideshow_now(self):
        """La confirmación textual prevalece sobre el debounce pendiente."""
        if getattr(self, "_rotation_debounce_id", None):
            GLib.source_remove(self._rotation_debounce_id)
            self._rotation_debounce_id = None
        self._commit_rotation_change()

    def _queue_slideshow_commit(self):
        """Agrupa los cambios escalonados de ambos intervalos durante 800 ms."""
        if getattr(self, "_rotation_debounce_id", None):
            GLib.source_remove(self._rotation_debounce_id)
        self._rotation_debounce_id = GLib.timeout_add(800, self._commit_rotation_change)

    def _on_max_interval_changed(self, spin):
        if self._loading:
            return

        max_val = spin.get_value_as_int()
        if self.rotation_spin.get_value_as_int() > max_val:
            self.rotation_spin.set_value(max_val)

        self._queue_slideshow_commit()

    def _on_rotation_changed(self, spin):
        if self._loading:
            return

        rot_val = spin.get_value_as_int()

        if rot_val > self.max_interval_spin.get_value_as_int():
            self.max_interval_spin.handler_block(self._max_interval_changed_id)
            self.max_interval_spin.set_value(rot_val)
            self.max_interval_spin.handler_unblock(self._max_interval_changed_id)

        self._queue_slideshow_commit()

    def _commit_rotation_change(self):
        self._rotation_debounce_id = None
        if self._loading:
            return False

        settings = self.backend.load_settings()
        rot_val = self.rotation_spin.get_value_as_int()
        max_val = self.max_interval_spin.get_value_as_int()

        # Ambos intervalos se coordinan en memoria; sólo aquí se persisten.
        if max_val != settings.get("slideshow_max_interval", 60):
            self.backend.save_setting("slideshow_max_interval", max_val)

        if rot_val != settings.get("slideshow_interval", 15):
            self._notify_engine({"action": ConfigHandler.CMD_UPDATE_TIMER, "interval": rot_val})

        return False

    def _update_mode_info_label(self):
        sync_active = self.mode_switch.get_active()
        fav_only = False
        fav_cb = self._callbacks.get('get_fav_rotation_switch')
        if fav_cb:
            fav_switch = fav_cb()
            if fav_switch:
                fav_only = fav_switch.get_active()
        if sync_active:
            mode_text = _("Synchronized")
            scope = _("Presets") if fav_only else _("All")
        else:
            mode_text = _("Asynchronous")
            scope = _("Favorites") if fav_only else _("Single")
        self.mode_info_label.set_text(f"{mode_text} ({scope})")

    # ==========================================================
    # BOTONES DE ACCIÓN
    # ==========================================================
    def _on_restart_clicked(self, widget):
        self.backend.save_json("commands", {})
        pid_path = os.path.join(self.handler.cache_dir, "pid_main.pid")

        # Detener únicamente una instancia que posea realmente el lock del engine.
        # Un PID obsoleto reutilizado por otro proceso nunca debe recibir señales.
        if os.path.exists(pid_path):
            stage = "abrir archivo PID"
            old_pid = None

            try:
                with open(pid_path, "r+") as pid_file:
                    stage = "comprobar bloqueo"
                    lock_acquired = self.handler._platform.try_lock_file(pid_file)

                    if not lock_acquired:
                        # El archivo está bloqueado por el engine activo.
                        stage = "leer PID"
                        pid_file.seek(0)
                        old_pid = int(pid_file.read().strip())

                        stage = "detener Engine"
                        self.handler._platform.terminate_process(old_pid)
                        time.sleep(0.3)

                        log_event("Engine antiguo detenido",
                            origin="OPTIONS_SECT", level="INFO", reason="COMMAND")

                    else:
                        # Archivo presente pero sin owner:
                        # es un resto de una instancia anterior.
                        stage = "liberar bloqueo obsoleto"
                        self.handler._platform.unlock_file(pid_file)

                        log_event("PID obsoleto detectado; no pertenece a un engine activo",
                            origin="OPTIONS_SECT", level="DEBUG", reason="COMMAND")

            except FileNotFoundError as error:
                # La desaparición del archivo antes de abrirlo es esperable.
                if stage != "abrir archivo PID":
                    log_event(
                        f"Reinicio: recurso desaparecido durante {stage}; "
                        f"pid={old_pid}, archivo={pid_path!r}: {error}",
                        origin="OPTIONS_SECT", level="WARN", reason="COMMAND")

            except (OSError, ValueError) as error:
                log_event(
                    f"Reinicio: fallo al {stage}; "
                    f"pid={old_pid}, archivo={pid_path!r}: {error}",
                    origin="OPTIONS_SECT", level="ERROR", reason="COMMAND")

        # Lanzar el script de reinicio en segundo plano
        restart_script = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "restart_engine.py")
        subprocess.Popen(
            [sys.executable, restart_script], start_new_session=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Restart abandona la aplicación directamente y no pasa por delete-event.
        save_window_size = self._callbacks.get('save_window_size')
        if save_window_size:
            save_window_size()

        app = self._callbacks.get('get_application', lambda: None)()
        if app:
            app.quit()

    def _on_open_debug_log(self, widget):
        # Gestionado por el panel principal mediante callback
        cb = self._callbacks.get('on_open_debug_log')
        if cb:
            cb()

    def _on_open_help(self, widget):
        # Gestionado por el panel principal mediante callback
        cb = self._callbacks.get('on_open_help')
        if cb:
            cb()

    def _on_collapse_clicked(self, widget):
        """Solicita al panel principal plegar el bloque izquierdo."""
        cb = self._callbacks.get('collapse_left_panel')
        if cb:
            cb()
