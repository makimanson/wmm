#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

"""
WMM - Wallpaper Multi-Monitor Manager

monitors_section.py – Sección de Monitores del panel de control.
==========================================================
Muestra los monitores virtuales con sus imágenes, permite activar/desactivar
monitores, cambiar la alineación del grupo, entrar en modo edición para
asignar imágenes manualmente mediante Drag & Drop, y guardar composiciones
como presets.
"""

import os
import base64
import json
import threading
import math
import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib
from config_handler import ConfigHandler
from monitor_manager import (get_virtual_monitor_layout,
    get_max_visual_area_height, get_virtual_canvas_size)
from image_selection import select_spanned_source_hash
from online_wallpapers import (resolve_online_original_for_preview,
    promote_online_preview_original, get_online_source_page)
from debug_logger import log_event
from i18n import _

class MonitorsSection:
    """
    Sección de Monitores del panel de control.
    """
    _MONITOR_AREA_MIN_WIDTH = 650

    # Altura histórica de generación. No limita el escalado visual.
    _PREVIEW_REFERENCE_HEIGHT = 325
    _VISUAL_AREA_MIN_HEIGHT = 100

    def __init__(self, handler, backend, ie, right_col, header_col,
                 fav_checkbox=None, accept_btn=None, spanned_switch=None):
        """
        Args:
            handler:        Instancia de ConfigHandler.
            backend:        Instancia de WMMBackend.
            ie:             Instancia de ImageEngine.
            right_col:      Gtk.Box del cuerpo redimensionable de Monitors.
            header_col:     Gtk.Box fijo para la cabecera Displays.
            callbacks:      Diccionario con funciones de callback para
                            comunicarse con otras secciones y el panel:
                            - 'create_section_label': (text) -> Gtk.Label
                            - 'notify_engine': (action_dict)
                            - 'load_monitors': ()
                            - 'load_presets': ()
                            - 'load_bookmarks_single': ()
                            - 'set_monitor_switches_sensitive': (bool)
                            - 'get_loading_state': () -> bool
                            - 'get_edit_mode_active': () -> bool
                            - 'get_fav_rotation_switch': () -> Gtk.Switch
                            - 'get_parent_window': () -> Gtk.Window
            fav_checkbox:   Gtk.CheckButton de favorito (compartido).
            accept_btn:     Gtk.Button de aceptar (compartido).
            spanned_switch: Gtk.Switch de modo distribuido (de OptionsSection).
        """
        self.handler = handler
        self.backend = backend
        self.ie = ie
        self._callbacks = {}  # Se configurarán después con set_callbacks()

        # Widgets compartidos
        self.fav_checkbox = fav_checkbox
        self.accept_btn = accept_btn
        self.spanned_switch = spanned_switch

        # Estado interno
        self._monitor_widgets = {}
        self._edit_monitor_widgets = {}
        self._monitor_switches = {}
        self._monitor_display_names = {}
        self._updating_switches = False
        self._repaint_scheduled = False
        self._last_container_size = (0, 0)
        self._panel_realized = False

        # Altura de representación vigente. Sólo cambiará cuando
        # Displays reciba realmente otra altura.
        self._visual_area_height = 325

        # Datos físicos y referencias para el escalado exclusivamente visual.
        self._visual_monitors_map = {}
        self._normal_preview_refs = {}
        self._edit_preview_refs = {}
        self._current_preset_name = None

        # Estado de aplicación física durante la edición.
        # Sólo Online habilita la vista previa directa.
        self._edit_live_preview = False

        # Impide aceptaciones Online simultáneas.
        self._online_accept_busy = False

        # Identidades recibidas por D&D Online durante la edición actual.
        # Nunca se reconstruyen desde nombres de archivo locales.
        self._online_drop_sources = {}

        # Construir la cabecera en su contenedor fijo y el cuerpo en el Panel.
        self.widget = self._build(header_col)
        right_col.pack_start(self.widget, True, True, 0)

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
        return cb() if cb else self.backend.edit_mode_active

    def _create_section_label(self, text):
        """Crea una etiqueta de sección usando el callback del panel."""
        cb = self._callbacks.get('create_section_label')
        if cb:
            return cb(text)
        label = Gtk.Label()
        label.set_markup(f"<span weight='bold' size='large'>{text}</span>")
        label.set_halign(Gtk.Align.START)
        return label

    def _notify_engine(self, action=None):
        """Envía una acción al motor."""
        cb = self._callbacks.get('notify_engine')
        if cb:
            cb(action)

    def _notify_edit_preview(self):
        """Envía al Engine la composición temporal sin modificar el Vault."""
        if (not self._edit_live_preview or not self.backend.edit_mode_active
                or not self.backend.edit_active_session):
            return

        # Spanned debe utilizar el mismo origen que la vista virtual:
        # primera imagen activa y válida en el orden de los monitores.
        source_hash = self._get_edit_spanned_source_hash()

        self._notify_engine({
            "action": ConfigHandler.CMD_APPLY_EDIT_PREVIEW,
            "session": dict(self.backend.edit_active_session),
            "states": dict(self.backend.edit_active_states),
            "source_hash": source_hash,
            "wallpaper_mode": self.backend.edit_temp_wp_mode,
            "spanned_enabled": self.backend.edit_temp_spanned_enabled,
            "wallpaper_effect": self.backend.edit_temp_image_effect,
            "wallpaper_effect_scope": self.backend.edit_temp_wp_scope,
        })

    def _load_monitors(self):
        """Refresca la vista de monitores."""
        cb = self._callbacks.get('load_monitors')
        if cb:
            cb()

    def _load_presets(self):
        """Recarga la lista de presets."""
        cb = self._callbacks.get('load_presets')
        if cb:
            cb()

    def _load_bookmarks_single(self):
        """Recarga la lista plana de favoritos."""
        cb = self._callbacks.get('load_bookmarks_single')
        if cb:
            cb()

    def _set_monitor_switches_sensitive(self, sensitive):
        """Activa/desactiva todos los switches de monitor."""
        for switch, _ in self._monitor_switches.values():
            switch.set_sensitive(sensitive)

    # ==========================================================
    # CONSTRUCCIÓN DE LA INTERFAZ
    # ==========================================================
    def _build(self, header_col):
        """Construye la cabecera fija y devuelve el cuerpo redimensionable."""
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # ----------------------------------------------------------
        # CABECERA: Título + Alineación
        # ----------------------------------------------------------
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        header_box.pack_start(self._create_section_label(_("Displays")), False, False, 4)

        # Controles de alineación de 3 estados
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
        header_col.pack_start(header_box, False, False, 0)
        self._header_box = header_box

        # ----------------------------------------------------------
        # CONTENEDOR INTERNO (REDIMENSIONABLE)
        # ----------------------------------------------------------
        inner_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._monitor_resize_area = inner_box
        inner_box.connect("size-allocate", self._on_container_resized)
        vbox.pack_start(inner_box, True, True, 0)

        # ----------------------------------------------------------
        # GRUPO UNIFICADO: Switches + Monitores + Botones
        # ----------------------------------------------------------
        self.monitor_group_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.monitor_group_box.set_halign(Gtk.Align.CENTER)

        # --- Sub-bloque 1: Switches de activación por monitor ---
        switch_align_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self._switch_align_box = switch_align_box
        switch_align_box.set_halign(Gtk.Align.CENTER)
        self.monitor_switches_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        switch_align_box.pack_start(self.monitor_switches_box, False, False, 0)
        self.monitor_group_box.pack_start(switch_align_box, False, False, 0)

        # --- Sub-bloque 2: Stack con páginas normal y edición ---
        self.monitors_stack = Gtk.Stack()
        self.monitors_stack.set_homogeneous(True)
        self.monitor_group_box.pack_start(self.monitors_stack, True, True, 0)

        # Página normal
        normal_page_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        normal_page_box.set_halign(Gtk.Align.CENTER)
        anchor = Gtk.Box()
        anchor.set_size_request(self._MONITOR_AREA_MIN_WIDTH, 0)
        normal_page_box.pack_start(anchor, False, False, 0)
        self.monitors_fixed = Gtk.Fixed()
        self.monitors_fixed.set_halign(Gtk.Align.CENTER)
        self.monitors_fixed.set_valign(Gtk.Align.START)
        normal_page_box.pack_start(self.monitors_fixed, True, True, 0)
        self.monitors_stack.add_named(normal_page_box, "normal")

        # Página edición
        edit_page_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        edit_page_box.set_halign(Gtk.Align.CENTER)
        self.monitors_fixed_edit = Gtk.Fixed()
        edit_page_box.pack_start(self.monitors_fixed_edit, True, True, 0)
        self.monitors_stack.add_named(edit_page_box, "edit")

        # --- Sub-bloque 3: Barra de botones inferior ---
        button_align_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self._button_align_box = button_align_box
        button_align_box.set_margin_bottom(4)

        # 1. BOTÓN DE EDICIÓN (izquierda)
        edit_controls_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        edit_controls_box.set_halign(Gtk.Align.START)

        self.edit_mode_btn = Gtk.ToggleButton()
        self.edit_mode_btn.get_style_context().add_class("wmm-edit-mode-toggle")
        icon = Gtk.Image.new_from_icon_name("document-edit-symbolic", Gtk.IconSize.SMALL_TOOLBAR)

        self.edit_mode_btn.add(icon)
        self.edit_mode_btn.set_valign(Gtk.Align.CENTER)
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

        # 2. OPCIONES DE EDICIÓN (centro)
        self.spanned_switch_edit = Gtk.Switch(active=False)
        self.spanned_switch_edit.set_valign(Gtk.Align.CENTER)
        self.spanned_switch_edit.set_tooltip_text(_("Span image across all active screens"))
        self.spanned_switch_edit.connect("notify::active", self._on_spanned_edit_changed)

        self.aspect_combo_edit = Gtk.ComboBoxText()
        for key, label in ConfigHandler.ASPECT_MODES.items():
            self.aspect_combo_edit.append_text(_(label))
        self.aspect_combo_edit.set_tooltip_text(
            _("Picture aspect") + "\n" + " " + _("for current composition"))
        self.aspect_combo_edit.connect("changed", self._on_aspect_edit_changed)

        self.image_effect_combo_edit = Gtk.ComboBoxText()
        for key, label in ConfigHandler.IMAGE_EFFECT.items():
            self.image_effect_combo_edit.append_text(_(label))
        self.image_effect_combo_edit.set_active(0)
        self.image_effect_combo_edit.connect("changed", self._on_image_effect_edit_changed)

        edit_aspects_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        edit_aspects_box.get_style_context().add_class("edit-aspects-box")
        edit_aspects_box.set_halign(Gtk.Align.CENTER)

        hbox_dist = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        spanned_label = Gtk.Label(label=_("Spanned") + ":")
        spanned_label.set_halign(Gtk.Align.CENTER)
        self.spanned_switch_edit.set_halign(Gtk.Align.CENTER)
        self.spanned_switch_edit.set_valign(Gtk.Align.CENTER)
        hbox_dist.pack_start(spanned_label, False, False, 0)
        hbox_dist.pack_start(self.spanned_switch_edit, False, False, 0)
        edit_aspects_box.pack_start(hbox_dist, False, False, 0)

        hbox_aspect = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        aspect_label = Gtk.Label(label=_("Aspect ratio") + ":")
        aspect_label.set_halign(Gtk.Align.START)
        hbox_aspect.pack_start(aspect_label, False, False, 0)
        hbox_aspect.pack_start(self.aspect_combo_edit, False, False, 0)
        edit_aspects_box.pack_start(hbox_aspect, False, False, 0)

        hbox_effect = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        effect_label = Gtk.Label(label=_("Effects") + ":")
        effect_label.set_halign(Gtk.Align.START)
        hbox_effect.pack_start(effect_label, False, False, 0)
        hbox_effect.pack_start(self.image_effect_combo_edit, False, False, 0)
        edit_aspects_box.pack_start(hbox_effect, False, False, 0)

        self.edit_aspects_box = edit_aspects_box
        self.edit_aspects_box.set_sensitive(False)
        self.edit_aspects_box.set_opacity(0.0)

        button_align_box.pack_start(edit_aspects_box, True, True, 0)

        # 3. GRUPO DERECHO (Checkbox Favorito + Aceptar + Refrescar)
        right_group = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)

        if self.fav_checkbox:
            self.fav_checkbox.connect("toggled", self._on_fav_checkbox_toggled)
            right_group.pack_start(self.fav_checkbox, False, False, 0)

        if self.accept_btn:
            self.accept_btn.set_sensitive(False)
            self.accept_btn.set_valign(Gtk.Align.CENTER)
            self.accept_btn.connect("clicked", self._on_accept_monitors)
            right_group.pack_start(self.accept_btn, False, False, 0)

        refresh_btn = Gtk.Button.new_from_icon_name(
            "view-refresh-symbolic", Gtk.IconSize.BUTTON)
        refresh_btn.set_valign(Gtk.Align.CENTER)
        refresh_btn.connect("clicked", self._on_refresh_monitors)
        right_group.pack_start(refresh_btn, False, False, 0)

        button_align_box.pack_end(right_group, False, False, 0)

        self.monitor_group_box.pack_end(button_align_box, False, False, 0)

        # ----------------------------------------------------------
        # EMPAQUETADO FINAL
        # ----------------------------------------------------------
        # El viewport determina la superficie disponible. El grupo de
        # monitores se representa sobre ella sin imponer su altura natural.
        self.monitors_viewport = Gtk.Overlay()

        viewport_base = Gtk.Box()
        viewport_base.set_size_request(self._MONITOR_AREA_MIN_WIDTH, 0)
        self.monitors_viewport.add(viewport_base)

        self.monitor_group_box.set_valign(Gtk.Align.START)
        self.monitors_viewport.add_overlay(self.monitor_group_box)

        # El Overlay centraliza los tooltips de la botonera sin
        # intervenir en el recorte ni en los eventos de los monitores.
        self.monitors_viewport.set_has_tooltip(True)
        self.monitors_viewport.connect(
            "query-tooltip", self._on_monitors_viewport_tooltip, refresh_btn)

        inner_box.pack_start(self.monitors_viewport, True, True, 0)

        return vbox

    # ==========================================================
    # ALINEACIÓN DEL GRUPO DE MONITORES
    # ==========================================================
    def on_panel_realized(self):
        """Sincroniza la primera geometría con la superficie ya asignada."""
        self._panel_realized = True
        self._last_container_size = (0, 0)

        if self._monitor_widgets:
            self._on_container_resized(
                self._monitor_resize_area,
                self._monitor_resize_area.get_allocation())

    def _on_align_label_clicked(self, widget, event):
        """Detecta clic en el control de alineación y actualiza el estado."""
        if event.button != 1:
            return False
        width = widget.get_allocated_width()
        x = event.x
        for lbl in (self.align_label_start, self.align_label_center, self.align_label_end):
            lbl.get_style_context().remove_class("align-active")
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

    # ==========================================================
    # REDIMENSIONAMIENTO Y DEBOUNCE
    # ==========================================================
    def _on_container_resized(self, widget, allocation):
        """Adapta la anchura conservando la altura elegida con el separador."""
        self._apply_visual_layout(allocation.width, self._visual_area_height)

    def _apply_visual_layout(self, area_w, area_h):
        """
        Escala únicamente la representación de los monitores.
        Reutiliza los Pixbuf procesados y conserva los EventBox/D&D.
        """
        self._visual_area_height = max(self._VISUAL_AREA_MIN_HEIGHT, int(area_h))

        if not self._panel_realized or not self._monitor_widgets or area_w < 50:
            return

        new_size = (int(area_w), self._visual_area_height)
        if new_size == self._last_container_size:
            return

        layout_data = get_virtual_monitor_layout(self._visual_monitors_map, *new_size)
        if not layout_data:
            return

        self._last_container_size = new_size

        self._resize_virtual_monitors(
            self.monitors_fixed, self._monitor_widgets,
            self._normal_preview_refs, layout_data)

        if self._edit_monitor_widgets:
            self._resize_virtual_monitors(
                self.monitors_fixed_edit, self._edit_monitor_widgets,
                self._edit_preview_refs, layout_data)

        # Adaptación visual: ajustar lienzos sin forzar otra distribución.
        self._sync_monitor_canvas(self.monitors_fixed, layout_data)

        if self._edit_monitor_widgets:
            self._sync_monitor_canvas(self.monitors_fixed_edit, layout_data)

    def _sync_monitor_canvas(self, fixed_widget, layout_data, refresh_allocation=False):
        """
        Aplica las dimensiones del lienzo calculadas por monitor_manager.

        Las actualizaciones completas pueden invalidar la asignación anterior
        de GTK. El escalado visual ordinario no necesita hacerlo.
        """
        width, height = get_virtual_canvas_size(layout_data)
        if width <= 0 or height <= 0:
            return

        fixed_widget.set_size_request(width, height)

        if refresh_allocation:
            self._last_container_size = (0, 0)
            self._monitor_resize_area.queue_resize()

    def _resize_virtual_monitors(self, fixed_widget, widgets, previews, layout_data):
        """Adapta la geometría visual reutilizando las imágenes procesadas."""
        for data in layout_data:
            m_hash = data['hash']
            eb = widgets.get(m_hash)
            if eb is None:
                continue

            x, y, w, h = data['x'], data['y'], data['w'], data['h']
            if w < 3 or h < 3:
                continue

            # Escalar siempre desde la imagen procesada original, nunca
            # desde el resultado de una redimensión anterior.
            image = eb.get_child()
            source = previews.get(m_hash)
            if isinstance(image, Gtk.Image) and source is not None:
                inner_w, inner_h = w - 2, h - 2

                if source.get_width() == inner_w and source.get_height() == inner_h:
                    scaled = source
                else:
                    scaled = source.scale_simple(
                        inner_w, inner_h, GdkPixbuf.InterpType.BILINEAR)

                if scaled is not None:
                    image.set_from_pixbuf(scaled)

            # Conservar el EventBox y sus conexiones D&D.
            eb.set_size_request(w, h)
            fixed_widget.move(eb, x, y)

    def _get_max_visual_area_height(self, area_width):
        """Consulta el límite geométrico sin calcularlo en la interfaz."""
        return get_max_visual_area_height(
            self._visual_monitors_map, area_width,
            self._VISUAL_AREA_MIN_HEIGHT)

    def _get_quality_monitor_layout(self, monitors_map, area_width):
        """Calcula la geometría de generación sin reducirla con el tirador."""
        return get_virtual_monitor_layout(monitors_map, area_width,
            max(self._PREVIEW_REFERENCE_HEIGHT, self._visual_area_height))

    def _refresh_visual_preview_quality(self):
        """Mejora la resolución sólo si la representación la ha superado."""
        if not self._panel_realized or not self._visual_monitors_map:
            return

        editing = self.backend.edit_mode_active
        widgets = self._edit_monitor_widgets if editing else self._monitor_widgets
        previews = self._edit_preview_refs if editing else self._normal_preview_refs

        area_w = self._monitor_resize_area.get_allocated_width()
        layout_data = get_virtual_monitor_layout(
            self._visual_monitors_map, area_w, self._visual_area_height)

        if not layout_data or not widgets:
            return

        needs_refresh = any(data["hash"] in widgets
            and (source := previews.get(data["hash"])) is not None
            and (source.get_width() < data["w"] - 2
                 or source.get_height() < data["h"] - 2)
            for data in layout_data)

        if not needs_refresh:
            return

        # Una sola actualización al finalizar; nunca durante el arrastre.
        if editing:
            self._load_preset_to_edit_monitors(self.backend.edit_active_session)
        else:
            self._load_monitors_normal()

    def _create_monitor_event_box(self, data, tooltip):
        """Construye el marco común sin configurar el D&D de cada modo."""
        m_hash = data['hash']

        eb = Gtk.EventBox()
        eb.get_style_context().add_class("monitor-frame")
        eb.set_size_request(data['w'], data['h'])
        eb.set_tooltip_text(tooltip)
        eb.m_hash = m_hash

        # El hover es común; las acciones y destinos D&D dependen del modo.
        eb.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)
        eb.connect("enter-notify-event", self._on_monitor_pointer_enter)
        eb.connect("leave-notify-event", self._on_monitor_pointer_leave)

        return eb

    def _configure_monitor_drop(self, eb, m_hash, targets, receiver):
        """Configura el destino D&D conservando los canales de cada modo."""
        eb.drag_dest_set(Gtk.DestDefaults.ALL, targets, Gdk.DragAction.COPY)
        eb.drag_dest_set_track_motion(True)
        eb.connect("drag-motion", self._on_edit_drag_motion, m_hash)
        eb.connect("drag-leave", self._on_edit_drag_leave, m_hash)
        eb.connect("drag-data-received", receiver, m_hash)

    def _capture_monitor_previews(self, widgets):
        """Conserva los Pixbuf procesados antes del escalado visual."""
        previews = {}

        for m_hash, eb in widgets.items():
            image = eb.get_child()
            if (isinstance(image, Gtk.Image)
                    and image.get_storage_type() == Gtk.ImageType.PIXBUF):
                previews[m_hash] = image.get_pixbuf()

        return previews

    def _refresh_after_hardware_change(self):
        """Actualiza ambas vistas tras un cambio físico de monitores."""
        # Normal actualiza la geometría compartida y los switches.
        self._load_monitors_normal()

        if self.backend.edit_mode_active:
            # Reconstruir los marcos de Edición sin reiniciar su sesión.
            self._load_monitors_edit()

            # Recuperar la composición temporal, incluida la de presets.
            if self.backend.edit_active_session:
                self._load_preset_to_edit_monitors(self.backend.edit_active_session)

        return False

    # ==========================================================
    # CARGA DE MONITORES (MODO NORMAL)
    # ==========================================================
    def _load_monitors_normal(self):
        """Carga los monitores virtuales en el modo normal."""
        geo_check = self.handler.load_json("geometry")
        num_monitors = len(geo_check.get("monitors", {}))
        layout_info = geo_check.get("monitors", {})
        log_event(f"Panel cargando geometría: {num_monitors} monitores encontrados en JSON",
                  origin="MON_SECT", level="DEBUG", reason="HARDWARE")

        for widget in self._monitor_widgets.values():
            self.monitors_fixed.remove(widget)
        self._monitor_widgets.clear()

        # La geometría depende del espacio disponible, no del Fixed redimensionado.
        layout_w = self._monitor_resize_area.get_allocated_width()
        if layout_w < 50:
            GLib.idle_add(self._load_monitors_normal)
            return

        # La carga completa y el redimensionamiento deben utilizar
        # exactamente la misma geometría de presentación.
        self._visual_monitors_map = {m_hash: dict(info) for m_hash, info in layout_info.items()}
        layout_data = get_virtual_monitor_layout(
            self._visual_monitors_map, layout_w, self._visual_area_height)

        if not layout_data:
            return

        # Construir img_source desde active_session
        vault = self.backend.load_vault()
        active_session = vault.get("active_session", {})
        active_composition = vault.get("active_composition", {})
        if not isinstance(active_composition, dict):
            active_composition = {}
        img_source = {}
        for m_hash in [d['hash'] for d in layout_data]:
            entry = active_session.get(m_hash, {})
            if isinstance(entry, dict):
                img_source[m_hash] = entry
            else:
                img_source[m_hash] = {"path": entry if entry else "", "active": True}

        settings = self.backend.load_settings()
        spanned_enabled = active_composition.get(
            "__spanned__", settings.get("spanned_enabled", False))

        # Crear EventBox vacíos y posicionarlos
        for data in layout_data:
            m_hash = data['hash']
            x, y, w, h = data['x'], data['y'], data['w'], data['h']
            eb = self._create_monitor_event_box(data, f"Monitor {m_hash}")
            eb.connect("button-press-event", self._on_monitor_event, m_hash)

            # Normal aplica inmediatamente el Drop y permite intercambiar
            # imágenes entre monitores mediante su canal D&D exclusivo.
            self._configure_monitor_drop(
                eb, m_hash,
                [
                    Gtk.TargetEntry.new("text/plain", Gtk.TargetFlags.SAME_APP, 0),
                    Gtk.TargetEntry.new("application/x-wmm-monitor", Gtk.TargetFlags.SAME_APP, 1),
                    Gtk.TargetEntry.new("application/x-wmm-online-image", Gtk.TargetFlags.SAME_APP, 2),
                ],
                self._on_normal_drag_data_received)

            # Solo los monitores con imagen visible son origen de intercambio.
            # En Spanned no existen intercambios individuales.
            entry = img_source.get(m_hash, {})
            img_path = entry.get("path")

            if (not spanned_enabled and entry.get("active", True)
                    and img_path and os.path.isfile(img_path)):
                eb.drag_source_set(
                    Gdk.ModifierType.BUTTON1_MASK,
                    [Gtk.TargetEntry.new(
                        "application/x-wmm-monitor", Gtk.TargetFlags.SAME_APP, 1)],
                    Gdk.DragAction.COPY)
                eb.connect("drag-data-get", self._on_monitor_drag_data_get, m_hash)

            self.monitors_fixed.put(eb, x, y)
            eb.set_size_request(w, h)
            self._monitor_widgets[m_hash] = eb

        # Pintar miniaturas
        wallpaper_mode = active_composition.get(
            "__mode__", settings.get("wallpaper_mode", "fit"))
        spanned_enabled = active_composition.get(
            "__spanned__", settings.get("spanned_enabled", False))
        wallpaper_effect_scope = active_composition.get(
            "__effect_scope__", settings.get("wallpaper_effect_scope", "blur"))
        wallpaper_effect = active_composition.get(
            "__effect__", settings.get("wallpaper_effect", "none"))

        # Generar con resolución suficiente aunque Displays esté reducido.
        render_layout = self._get_quality_monitor_layout(
            self._visual_monitors_map, layout_w)

        self.ie.paint_monitors_thumbnails(
            fixed_widget=self.monitors_fixed,
            layout_data=render_layout,
            img_source=img_source,
            wallpaper_mode=wallpaper_mode,
            spanned_enabled=spanned_enabled,
            color_tuple=self.backend.get_background_color_tuple(),
            wallpaper_effect_scope=wallpaper_effect_scope,
            image_effect=wallpaper_effect,
            layout_info=layout_info,
            spanned_source_hash=vault.get("spanned_source_hash"),
        )

        # Capturar las fuentes procesadas antes de cualquier escalado visual.
        self._normal_preview_refs = self._capture_monitor_previews(
            self._monitor_widgets)

        # Mostrar al tamaño visual sin alterar las referencias procesadas.
        self._resize_virtual_monitors(
            self.monitors_fixed, self._monitor_widgets,
            self._normal_preview_refs, layout_data)

        # Sincronizar el lienzo de los EventBox reconstruidos.
        self._sync_monitor_canvas(
            self.monitors_fixed, layout_data, refresh_allocation=True)

        self.monitors_fixed.show_all()

        self._build_monitor_switches()
        GLib.idle_add(self._update_monitor_tooltips)

    # ==========================================================
    # SWITCHES DE MONITOR
    # ==========================================================
    def _build_monitor_switches(self):
        """Crea o actualiza los switches de activación por monitor."""
        self._updating_switches = True
        state_source = self.backend.edit_active_states if self.backend.edit_mode_active else self.backend.get_active_session()

        # Ordenar hashes para que el monitor primario aparezca primero
        ordered_hashes = sorted(
            self._monitor_widgets.keys(),
            key=lambda h: (
                not self.handler.get_monitor_info(h).get("primary", False),
                self._monitor_display_names.get(h, "")
            )
        )

        for m_hash in ordered_hashes:
            eb = self._monitor_widgets[m_hash]
            if self.backend.edit_mode_active:
                is_active = state_source.get(m_hash, True)
            else:
                entry = state_source.get(m_hash, {})
                is_active = entry.get("active", True) if isinstance(entry, dict) else True

            if m_hash in self._monitor_switches:
                self._monitor_switches[m_hash][0].set_active(is_active)

            else:
                hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
                hbox.set_property("margin", 2)

                label_text = self.handler.get_monitor_display_name(m_hash)
                info = self.handler.get_monitor_info(m_hash)

                if info and info.get("primary", False):
                    label = Gtk.Label()
                    label.set_markup(f"<b>{label_text}</b>")
                    label.set_tooltip_text(_("Primary monitor"))
                else:
                    label = Gtk.Label(label=label_text)

                self._monitor_display_names[m_hash] = label_text
                switch = Gtk.Switch(active=is_active)
                switch.connect("notify::active", self._on_monitor_active_toggled, m_hash)

                # Conservar la altura natural del switch dentro de su fila.
                # Evita que GTK lo estire verticalmente según el tema.
                switch.set_valign(Gtk.Align.CENTER)

                switch.set_tooltip_text(_("Enable/disable image"))

                hbox.pack_start(label, False, False, 0)
                hbox.pack_start(switch, False, False, 0)

                switch_event_box = Gtk.EventBox()
                switch_event_box.add(hbox)
                switch_event_box.connect("enter-notify-event", self._on_switch_enter, m_hash)
                switch_event_box.connect("leave-notify-event", self._on_switch_leave, m_hash)

                self.monitor_switches_box.pack_start(switch_event_box, False, False, 4)
                self._monitor_switches[m_hash] = (switch, switch_event_box)

        # Eliminar switches huérfanos
        for m_hash in list(self._monitor_switches.keys()):
            if m_hash not in self._monitor_widgets:
                switch, widget = self._monitor_switches.pop(m_hash)
                widget.destroy()

        # Insensibilizar switch "Distribuido" si solo hay un monitor
        if self.spanned_switch is not None:
            self.spanned_switch.set_sensitive(len(self._monitor_widgets) > 1)
            if len(self._monitor_widgets) <= 1:
                self.spanned_switch.set_active(False)

        settings = self.backend.load_settings()
        if settings.get("spanned_enabled", False):
            self._set_monitor_switches_sensitive(False)

        self.monitor_switches_box.show_all()
        log_event(f"Switches de monitor actualizados: {len(self._monitor_switches)} monitores",
                  origin="MON_SECT", level="DEBUG", reason="HARDWARE")
        self._updating_switches = False

    def _update_monitor_tooltips(self):
        """Actualiza los tooltips de los monitores con los nombres enriquecidos."""
        for m_hash, eb in self._monitor_widgets.items():
            name = self._monitor_display_names.get(m_hash, _("Display") + " " + m_hash[:6])
            eb.set_tooltip_text(name)
        return False

    def _on_monitors_viewport_tooltip(self, viewport, x, y, keyboard_mode,
                                     tooltip, refresh_btn):
        """Resuelve los tooltips de la botonera superpuesta al viewport."""
        for button in (self.fav_checkbox, self.accept_btn, refresh_btn):
            if button is None or not button.get_mapped():
                continue

            if keyboard_mode:
                active = button.has_focus()
            else:
                position = button.translate_coordinates(viewport, 0, 0)
                if position is None:
                    continue

                bx, by = position
                width = button.get_allocated_width()
                height = button.get_allocated_height()
                active = bx <= x < bx + width and by <= y < by + height

            if not active:
                continue

            if button is refresh_btn:
                tooltip.set_text(_("Refresh real display status"))
                return True

            # Reutilizar la semántica contextual de Favorito y Aceptar.
            return self._on_accept_controls_tooltip(
                button, x, y, keyboard_mode, tooltip)

        # Los monitores virtuales conservan sus propios tooltips.
        return False

    def _on_accept_controls_tooltip(self, widget, x, y, keyboard_mode, tooltip):
        """Describe Aceptar y su checkbox según el contexto real de edición."""
        editing = self.backend.edit_mode_active
        online = editing and self._edit_live_preview
        preset = editing and not online and bool(self._current_preset_name)
        checked = self.fav_checkbox.get_active() if self.fav_checkbox else False

        # Un preset cargado se actualiza; los demás escenarios crean uno nuevo.
        if widget is self.fav_checkbox:
            message = _("Update preset on accept") if preset else _("Create preset on accept")

        elif not editing:
            message = _("Save current composition as preset")

        elif online:
            message = (_("Add images to library and create a preset")
                       if checked else _("Add images to library"))

        elif preset:
            message = (_("Update preset and apply to monitors")
                       if checked else _("Apply to monitors without updating preset"))

        else:
            message = (_("Create preset and apply to monitors")
                       if checked else _("Apply to monitors"))

        tooltip.set_text(message)
        return True

    def _on_fav_checkbox_toggled(self, checkbox):
        if not self.backend.edit_mode_active:
            if self.accept_btn:
                self.accept_btn.set_sensitive(checkbox.get_active())

    def _on_monitor_active_toggled(self, switch, param, m_hash):
        """Activa o desactiva la imagen de un monitor."""
        if self._loading or self._updating_switches:
            return
        if self.backend.edit_mode_active:
            self.backend.edit_active_states[m_hash] = switch.get_active()
            self._load_preset_to_edit_monitors(self.backend.edit_active_session)
            self._notify_edit_preview()
            return

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
                blurred = self.handler.get_composite_thumbnail(img_path, inner_w, inner_h) if img_path else None
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

            # Mantener la referencia visual sincronizada con el contenido real.
            # Un icono de ausencia de imagen no constituye una miniatura escalable.
            if (isinstance(thumb, Gtk.Image)
                    and thumb.get_storage_type() == Gtk.ImageType.PIXBUF):
                self._normal_preview_refs[m_hash] = thumb.get_pixbuf()
            else:
                self._normal_preview_refs.pop(m_hash, None)

        self._build_monitor_switches()

    def _on_monitor_pointer_enter(self, widget, event):
        """Resalta el monitor virtual sin intervenir en su D&D."""
        widget.get_style_context().add_class("monitor-hover")
        return False

    def _on_monitor_pointer_leave(self, widget, event):
        """Retira únicamente el resaltado del ratón."""
        widget.get_style_context().remove_class("monitor-hover")
        return False

    def _on_switch_enter(self, widget, event, m_hash):
        """Resalta el monitor correspondiente al pasar el ratón sobre el switch."""
        for eb in (self._edit_monitor_widgets.values() if self.backend.edit_mode_active else self._monitor_widgets.values()):
            if getattr(eb, 'm_hash', None) == m_hash:
                eb.get_style_context().add_class("monitor-hover")
                eb.queue_draw()
                return False
        return False

    def _on_switch_leave(self, widget, event, m_hash):
        """Quita el resaltado del monitor al salir el ratón del switch."""
        for eb in (self._edit_monitor_widgets.values() if self.backend.edit_mode_active else self._monitor_widgets.values()):
            if getattr(eb, 'm_hash', None) == m_hash:
                eb.get_style_context().remove_class("monitor-hover")
                eb.queue_draw()
                return False
        return False

    def _on_monitor_event(self, widget, event, m_hash):
        """Evento de clic derecho sobre un monitor virtual (sin acción por ahora)."""
        if event.button == 3:
            pass
        return False

    def _on_monitor_drag_data_get(self, widget, context, data, info, time, m_hash):
        """Entrega la identidad del monitor origen, no su ruta de imagen."""
        data.set(data.get_target(), 8, m_hash.encode("utf-8"))

    def _on_online_drag_data_received(self, widget, context, data, time, m_hash):
        """Recibe una identidad Online sin modificar el Vault ni descargar."""
        try:
            item = json.loads((data.get_data() or b"").decode("utf-8"))
        except (ValueError, UnicodeError, AttributeError):
            Gtk.drag_finish(context, False, False, time)
            return

        if (not isinstance(item, dict)
                or not item.get("downloadable")
                or not isinstance(item.get("provider"), str)
                or not item.get("provider")
                or not isinstance(item.get("id"), str)
                or not item.get("id")
                or m_hash not in self._monitor_widgets):
            Gtk.drag_finish(context, False, False, time)
            return

        # Terminar el protocolo D&D antes de cambiar el Gtk.Stack: activar
        # edición destruye/reconstruye los monitores de su propia vista.
        Gtk.drag_finish(context, True, False, time)
        GLib.idle_add(self._activate_online_edit, m_hash, item)

    def _activate_online_edit(self, m_hash, item):
        """Activa edición y delega la resolución Online fuera de GTK."""
        if not self.backend.edit_mode_active:
            self.edit_mode_btn.set_active(True)

        # Una nueva sesión Online no hereda identidades de ediciones previas.
        if not self._edit_live_preview:
            self._online_drop_sources.clear()

        # Un Drop Online habilita la acción directa en esta sesión.
        self._edit_live_preview = True

        log_event(f"Drop Online recibido: {item['provider']}/{item['id']} -> {m_hash}",
            origin="MON_SECT", level="INFO", reason="LIBRARY")

        threading.Thread(
            target=self._online_drop_worker,
            args=(m_hash, item),
            name="WMM-OnlineDrop",
            daemon=True
        ).start()

        return False

    def _online_drop_worker(self, m_hash, item):
        """Obtiene el original sin bloquear la interfaz GTK."""
        try:
            online_dir = self.handler.get_online_source_path()
            img_path = resolve_online_original_for_preview(
                item, self.handler.cache_dir, online_dir)

        except Exception as error:
            log_event(
                f"No se pudo preparar Online {item['provider']}/{item['id']}: {error}",
                origin="MON_SECT", level="ERROR", reason="LIBRARY")
            return

        # La sesión de edición y sus widgets sólo se modifican desde GTK.
        GLib.idle_add(self._online_drop_ready, m_hash, img_path, item)

    def _online_drop_ready(self, m_hash, img_path, item):
        """Incorpora el original disponible al editor y repinta el monitor."""
        if (not self.backend.edit_mode_active
                or m_hash not in self._edit_monitor_widgets):
            return False

        self.backend.edit_active_session[m_hash] = img_path
        self.backend.edit_active_states[m_hash] = True
        self._online_drop_sources[m_hash] = (img_path, item)

        # Reutilizar el pintado de presets: modos de aspecto, efectos
        # y Spanned se procesan por el circuito existente.
        self._load_preset_to_edit_monitors(self.backend.edit_active_session)

        # La sesión temporal viaja al Engine como una composición completa.
        # No se guarda en Vault: Aceptar mantiene esa responsabilidad.
        self._notify_edit_preview()
        log_event(f"Imagen Online disponible en edición: {m_hash} -> {img_path}",
            origin="MON_SECT", level="INFO", reason="LIBRARY")
        return False

    def on_online_original_promoted(self, source, target):
        """Reconcilia rutas de edición después de un Download desde /temp."""
        # Aceptar ya reemplaza estas rutas mientras procesa su sesión.
        if (not self.backend.edit_mode_active
                or self._online_accept_busy or source == target):
            return

        changed = False

        for m_hash, path in tuple(self.backend.edit_active_session.items()):
            if path != source:
                continue

            self.backend.edit_active_session[m_hash] = target

            origin = self._online_drop_sources.get(m_hash)
            if origin and origin[0] == source:
                self._online_drop_sources[m_hash] = (target, origin[1])

            changed = True

        if changed:
            # D&D Online ya utiliza este repintado y notificación al Engine.
            self._load_preset_to_edit_monitors(self.backend.edit_active_session)
            self._notify_edit_preview()

    def _on_normal_drag_data_received(self, widget, context, x, y, data, info, time, m_hash):
        """Aplica inmediatamente una imagen soltada sobre un monitor normal."""
        widget.get_style_context().remove_class("dnd-target")
        if info == 2:
            self._on_online_drag_data_received(widget, context, data, time, m_hash)
            return

        # Intercambio entre monitores: canal D&D interno independiente
        # del envío de imágenes desde Thumbnails.
        if info == 1:
            source_hash = (data.get_data() or b"").decode("utf-8")
            vault = self.backend.load_vault()
            active_session = vault.get("active_session", {})

            settings = self.backend.load_settings()
            composition = vault.get("active_composition", {})
            if not isinstance(composition, dict):
                composition = {}

            spanned = composition.get(
                "__spanned__", settings.get("spanned_enabled", False))

            if (spanned or self.backend.edit_mode_active
                    or source_hash not in active_session
                    or m_hash not in active_session):
                Gtk.drag_finish(context, False, False, time)
                return

            if source_hash == m_hash:
                Gtk.drag_finish(context, True, False, time)
                return

            source = active_session[source_hash]
            target = active_session[m_hash]

            # Mantener los flags active de cada monitor, incluso si
            # alguna entrada conserva el formato antiguo del Vault.
            if isinstance(source, str):
                source = {"path": source, "active": True}
            if isinstance(target, str):
                target = {"path": target, "active": True}

            source_path = source.get("path")
            target_path = target.get("path")

            if not (source_path and target_path
                    and os.path.isfile(source_path)
                    and os.path.isfile(target_path)):
                Gtk.drag_finish(context, False, False, time)
                return

            # Intercambio único: no hay estado intermedio ni se altera
            # la activación, los efectos o las preferencias globales.
            source["path"], target["path"] = target_path, source_path
            active_session[source_hash] = source
            active_session[m_hash] = target
            self.backend.save_vault(vault)

            Gtk.drag_finish(context, True, False, time)

            self._notify_engine({"action": "apply_manual_selection"})

            # Reconstruir después del evento GTK para no destruir el
            # widget origen mientras termina su operación de arrastre.
            GLib.idle_add(self._load_monitors_normal)

            log_event(f"Imágenes intercambiadas: {source_hash} <-> {m_hash}",
                origin="MON_SECT", level="INFO", reason="VAULT")
            return

        # Spanned también acepta el Drop: la imagen permanece asignada
        # al monitor elegido por el usuario.
        settings = self.backend.load_settings()
        spanned_enabled = settings.get("spanned_enabled", False)

        try:
            img_path = base64.b64decode(
                data.get_text().encode("ascii"), validate=True).decode("utf-8")
        except (AttributeError, ValueError, UnicodeError):
            Gtk.drag_finish(context, False, False, time)
            return

        if not os.path.isfile(img_path) or m_hash not in self._monitor_widgets:
            Gtk.drag_finish(context, False, False, time)
            return

        # La selección inmediata modifica únicamente la asignación elegida.
        # Mantiene los restantes monitores y sus estados en el Vault.
        vault = self.backend.load_vault()
        active_session = vault.setdefault("active_session", {})
        entry = active_session.get(m_hash, {})

        if not isinstance(entry, dict):
            entry = {"path": entry or "", "active": True}

        entry["path"] = img_path
        entry["active"] = True
        active_session[m_hash] = entry
        self.backend.save_vault(vault)

        # Activar el switch sin provocar otra aplicación por notify::active.
        if m_hash in self._monitor_switches:
            self._updating_switches = True
            try:
                self._monitor_switches[m_hash][0].set_active(True)
            finally:
                self._updating_switches = False

        Gtk.drag_finish(context, True, False, time)

        # REASON_SELECTION utiliza directamente settings.json para el
        # aspecto y los efectos, sin entrar en el modo edición.
        action = {"action": "apply_manual_selection"}

        # En Spanned, identificar el origen explícito de esta selección.
        # No se traslada la imagen al monitor de referencia.
        if spanned_enabled:
            action["target_hash"] = m_hash

        self._notify_engine(action)
        self._load_monitors_normal()

        log_event(f"Imagen aplicada mediante Drop: {m_hash} -> {img_path}",
            origin="MON_SECT", level="INFO", reason="BOOKMARK")

    def _on_refresh_monitors(self, widget):
        """Refresca la vista de monitores desde el motor."""
        if self.backend.edit_mode_active:
            self._online_drop_sources.clear()
            for m_hash in self.backend.edit_active_session:
                self.backend.edit_active_session[m_hash] = ""
                self.backend.edit_active_states[m_hash] = True
            self._load_monitors_edit()
            self._build_monitor_switches()
            log_event("Monitores reseteados a vacío",
                origin="MON_SECT", level="INFO", reason="HARDWARE")
            return
        self._load_monitors_normal()
        self._current_preset_name = None

        # Sólo las sesiones iniciadas desde Online aplican cambios físicos
        # durante la edición. El modo estándar permanece virtual.
        self._edit_live_preview = False

        self._build_monitor_switches()
        log_event("Vista de monitores refrescada desde el motor",
            origin="MON_SECT", level="INFO", reason="HARDWARE")

    # ==========================================================
    # ACEPTACIÓN ONLINE: INCORPORACIÓN PREVIA A LA PERSISTENCIA
    # ==========================================================
    def _start_online_accept(self):
        """Prepara los originales definitivos sin bloquear GTK."""
        if self._online_accept_busy:
            return

        self._online_accept_busy = True
        if self.accept_btn:
            self.accept_btn.set_sensitive(False)

        session = dict(self.backend.edit_active_session)
        online_dir = self.handler.get_online_source_path()

        # Fijar únicamente las identidades Online que todavía corresponden
        # a las imágenes presentes en la sesión que se está aceptando.
        online_items = {
            path: item
            for m_hash, (path, item) in self._online_drop_sources.items()
            if session.get(m_hash) == path
        }

        threading.Thread(
            target=self._online_accept_worker,
            args=(session, online_dir, online_items),
            name="WMM-OnlineAccept",
            daemon=True
        ).start()

    def _online_accept_worker(self, session, online_dir, online_items):
        """Traslada originales y comunica sólo incorporaciones confirmadas."""
        replacements = {}
        incorporated = {}
        error = None

        try:
            # Una misma imagen puede estar asignada a varios monitores.
            # Incorporarla una sola vez evita operaciones redundantes.
            paths = dict.fromkeys(
                path for path in session.values()
                if isinstance(path, str) and path
            )

            for path in paths:
                final_path = promote_online_preview_original(
                    path, self.handler.cache_dir, online_dir)

                if final_path != path:
                    replacements[path] = final_path

                # Una imagen reutilizada desde Sources también puede
                # recuperar procedencia si vuelve expresamente por Online.
                if path in online_items:
                    incorporated[final_path] = online_items[path]

        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"

        GLib.idle_add(
            self._online_accept_complete,
            session, replacements, error, incorporated)

    def _online_accept_complete(self, session, replacements, error, incorporated):
        """Actualiza las rutas y continúa con Aceptar sólo si todo terminó."""
        self._online_accept_busy = False

        # Conservar únicamente las procedencias Online confirmadas.
        # Las imágenes procedentes de Library no participan en el lote.
        pending = []

        for path, item in incorporated.items():
            page_url = get_online_source_page(item)
            if page_url:
                pending.append((path, item, page_url))

        # Persistir todas las incorporaciones en una sola operación,
        # incluso cuando un fallo posterior interrumpió la aceptación.
        if pending:
            saved = self.handler.record_online_origins(pending)
            expected = {
                os.path.normcase(os.path.abspath(path))
                for path, _, _ in pending
            }

            if saved != expected:
                log_event(
                    f"Procedencias Online: {len(saved)}/{len(expected)} registradas",
                    origin="MON_SECT", level="WARN", reason="LIBRARY")

        # Comprobar el estado anterior a sustituir las rutas temporales.
        session_unchanged = self.backend.edit_active_session == session

        if self.backend.edit_mode_active:
            # Incluso ante un fallo parcial, las imágenes ya incorporadas
            # deben conservar referencias válidas dentro del editor.
            for m_hash, path in tuple(self.backend.edit_active_session.items()):
                if path in replacements:
                    self.backend.edit_active_session[m_hash] = replacements[path]

        if self.accept_btn:
            self.accept_btn.set_sensitive(self.backend.edit_mode_active)

        if error:
            log_event(f"Incorporación Online interrumpida: {error}",
                origin="MON_SECT", level="ERROR", reason="LIBRARY")

            if self.backend.edit_mode_active:
                dialog = Gtk.MessageDialog(
                    transient_for=self._callbacks.get(
                        'get_parent_window', lambda: None)(),
                    flags=0,
                    message_type=Gtk.MessageType.ERROR,
                    buttons=Gtk.ButtonsType.OK,
                    text=_("Could not incorporate Online images."))
                dialog.format_secondary_text(error)
                dialog.run()
                dialog.destroy()

        elif session_unchanged and self.backend.edit_mode_active \
                and self._edit_live_preview:
            # Sólo ahora entra el circuito habitual de aceptación.
            self._commit_edit_accept()

        elif self.backend.edit_mode_active:
            log_event("Aceptar Online cancelado: la sesión cambió durante el traslado",
                origin="MON_SECT", level="WARN", reason="LIBRARY")

        # Las incorporaciones efectivas deben entrar en Sources/Library,
        # incluso si otra imagen del lote provocó un error posterior.
        if replacements or incorporated:
            mark_callback = self._callbacks.get('mark_online_incorporated')

            if not mark_callback:
                log_event("Marcado Online omitido: callback no registrado",
                    origin="MON_SECT", level="ERROR", reason="LIBRARY")
            else:
                try:
                    mark_callback(tuple(
                        set(replacements.values()) | set(incorporated)))
                except Exception as error:
                    log_event(f"Error al actualizar marcas Online: "
                        f"{type(error).__name__}: {error}",
                        origin="MON_SECT", level="ERROR", reason="LIBRARY")

            callback = self._callbacks.get('refresh_online_sources')

            if not callback:
                log_event("Sincronización Online omitida: callback no registrado",
                    origin="MON_SECT", level="ERROR", reason="LIBRARY")
            else:
                try:
                    callback()
                except Exception as error:
                    log_event(f"Error al solicitar sincronización Online: "
                        f"{type(error).__name__}: {error}",
                        origin="MON_SECT", level="ERROR", reason="LIBRARY")

        return False

    # ==========================================================
    # ACEPTAR CAMBIOS (GUARDAR PRESET)
    # ==========================================================
    def _commit_edit_accept(self):
        """Ejecuta la aceptación habitual con las rutas ya preparadas."""
        log_msg, temp_settings, new_preset_name = self.backend.apply_edit_and_save(
            fav_checkbox_active=self.fav_checkbox.get_active()
                if self.fav_checkbox else False,
            preset_name=self._current_preset_name,
            monitor_hashes=list(self._monitor_widgets.keys()),
            get_path_func=lambda h: self.backend.edit_active_session.get(h, ""),
            get_active_func=lambda h: self.backend.edit_active_states.get(h, True)
        )

        if temp_settings is None:
            log_event("No se pudo completar la aceptación de la composición",
                origin="MON_SECT", level="ERROR", reason="BOOKMARK")
            return False

        if self.fav_checkbox and self.fav_checkbox.get_active():
            self._load_presets()
            self._load_bookmarks_single()

        self._notify_engine({
            "action": "apply_manual_selection",
            "temp_settings": temp_settings
        })
        log_event("apply_manual_selection enviada al motor",
            origin="MON_SECT", level="DEBUG", reason="BOOKMARK")

        settings = self.backend.load_settings()
        settings["slideshow_enabled"] = False
        self.backend.save_settings(settings)

        self._exit_edit_mode()

        if log_msg:
            log_event(log_msg, origin="MON_SECT", level="INFO", reason="BOOKMARK")
        else:
            log_event("Cambios aplicados y modo edición finalizado",
                origin="MON_SECT", level="INFO", reason="NOTIFY")

        return True

    def _on_accept_monitors(self, widget):
        """Guarda los cambios de edición y crea/actualiza el preset si procede."""
        if self.backend.edit_mode_active:
            if self._edit_live_preview:
                self._start_online_accept()
            else:
                self._commit_edit_accept()
            return

        # Modo normal: guardar preset si el checkbox está activo
        if self.fav_checkbox and self.fav_checkbox.get_active():
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
            log_event(f"Preset guardado: {preset_name}",
                origin="MON_SECT", level="INFO", reason="BOOKMARK")
            if self.fav_checkbox:
                self.fav_checkbox.set_active(False)
            if self.accept_btn:
                self.accept_btn.set_sensitive(False)
        else:
            log_event("No se ha marcado Favorito, no se guarda nada",
                origin="MON_SECT", level="INFO", reason="BOOKMARK")

    # ==========================================================
    # MODO EDICIÓN
    # ==========================================================
    def _on_toggle_edit_mode(self, widget):
        """Activa o desactiva el modo edición de monitores."""
        was_active = self.backend.edit_mode_active
        self.backend.edit_mode_active = widget.get_active()
        page = "edit" if self.backend.edit_mode_active else "normal"
        self.edit_label_stack.set_visible_child_name(page)

        if self.backend.edit_mode_active:
            if not was_active:
                self.backend.edit_active_session.clear()
            active_session = self.backend.get_active_session()
            self.backend.edit_active_states = {
                m_hash: entry.get("active", True) if isinstance(entry, dict) else True
                for m_hash, entry in active_session.items()
            }
            self._load_monitors_edit()
            self._build_monitor_switches()
            self.monitors_stack.set_visible_child_name("edit")
            self.edit_aspects_box.set_opacity(1.0)
            self.edit_aspects_box.set_sensitive(True)

            settings = self.backend.load_settings()
            current_wp_mode = settings.get("wallpaper_mode", "fit")
            keys = list(ConfigHandler.ASPECT_MODES.keys())
            index = keys.index(current_wp_mode) if current_wp_mode in keys else 0
            self.aspect_combo_edit.set_active(index)
            self.backend.edit_temp_wp_mode = current_wp_mode

            spanned_enabled = settings.get("spanned_enabled", False)
            self.spanned_switch_edit.set_active(spanned_enabled)
            self.backend.edit_temp_spanned_enabled = spanned_enabled

            img_effect = settings.get("wallpaper_effect", "none")
            keys = list(ConfigHandler.IMAGE_EFFECT.keys())
            index = keys.index(img_effect) if img_effect in keys else 0
            self.image_effect_combo_edit.set_active(index)
            self.backend.edit_temp_image_effect = img_effect

            self.backend.edit_temp_wp_scope = settings.get("wallpaper_effect_scope", "blur")
            # Los valores iniciales proceden de settings y no son overrides.
            self.backend.edit_temp_composition.clear()
            if self.accept_btn:
                self.accept_btn.set_sensitive(True)
        else:
            self._exit_edit_mode()
            self.edit_aspects_box.set_opacity(0.0)
            self.edit_aspects_box.set_sensitive(False)

    def _exit_edit_mode(self):
        """Sale del modo edición y restaura la vista normal."""
        # La próxima edición comienza siempre en modo tranquilo.
        self._edit_live_preview = False
        self._online_drop_sources.clear()
        self.backend.cancel_edit()
        self.edit_mode_btn.set_active(False)
        self.edit_label_stack.set_visible_child_name("normal")
        self.monitors_stack.set_visible_child_name("normal")
        self._load_monitors_normal()
        self._build_monitor_switches()
        if self.accept_btn:
            self.accept_btn.set_sensitive(False)
        if self.fav_checkbox:
            self.fav_checkbox.set_active(False)
        self._current_preset_name = None

    def _on_aspect_edit_changed(self, combo):
        """Actualiza el modo de aspecto en edición y refresca la vista previa."""
        if self._loading:
            return
        index = combo.get_active()
        keys = list(ConfigHandler.ASPECT_MODES.keys())
        if 0 <= index < len(keys):
            mode = keys[index]
            self.backend.edit_temp_wp_mode = mode
            if self.backend.edit_mode_active:
                self.backend.edit_temp_composition["__mode__"] = mode
                self._set_monitor_switches_sensitive(mode != "spanned")
                self._load_monitors_edit()
                if self.backend.edit_active_session:
                    self._load_preset_to_edit_monitors(self.backend.edit_active_session)
                    self._notify_edit_preview()

    def _load_monitors_edit(self):
        """Carga los monitores virtuales en el modo edición."""
        for widget in self.monitors_fixed_edit.get_children():
            self.monitors_fixed_edit.remove(widget)
        self._edit_monitor_widgets.clear()

        # La nueva geometría invalida las referencias visuales anteriores.
        # Se recuperarán del pintado real, nunca de una imagen obsoleta.
        self._edit_preview_refs = {}

        # La geometría depende del espacio disponible, no del Fixed redimensionado.
        layout_w = self._monitor_resize_area.get_allocated_width()

        # Edit/preset: necesitamos construir inmediatamente
        if layout_w < 50:
            layout_w = self._MONITOR_AREA_MIN_WIDTH

        # Edición comparte la geometría visual del modo Normal.
        monitors_map = self._visual_monitors_map or self.handler.load_json("geometry").get("monitors", {})
        layout_data = get_virtual_monitor_layout(monitors_map, layout_w, self._visual_area_height)

        if not layout_data:
            return

        for data in layout_data:
            m_hash = data['hash']
            x, y, w, h = data['x'], data['y'], data['w'], data['h']
            display_name = self._monitor_display_names.get(
                m_hash, _("Display") + " " + m_hash[:6])

            eb = self._create_monitor_event_box(
                data, display_name + " (" + _("editing") + ")")

            # Edición admite imágenes para la composición temporal,
            # pero no el intercambio directo entre monitores.
            self._configure_monitor_drop(eb, m_hash,
                [
                    Gtk.TargetEntry.new("text/plain", Gtk.TargetFlags.SAME_APP, 0),
                    Gtk.TargetEntry.new("application/x-wmm-online-image", Gtk.TargetFlags.SAME_APP, 2),
                ],
                self._on_edit_drag_data_received)
            self.monitors_fixed_edit.put(eb, x, y)
            self._edit_monitor_widgets[m_hash] = eb
            eb.show()

        # Sincronizar el lienzo de los monitores reconstruidos en edición.
        self._sync_monitor_canvas(
            self.monitors_fixed_edit, layout_data, refresh_allocation=True)

        self.monitors_fixed_edit.show_all()

    def _get_edit_spanned_source_hash(self, layout_info=None):
        """Consulta la selección Spanned común con el estado temporal del editor."""
        if layout_info is None:
            layout_info = self.handler.load_json("geometry").get("monitors", {})

        return select_spanned_source_hash(
            layout_info,
            self.backend.edit_active_session,
            active_states=self.backend.edit_active_states,
            fallback_order=tuple(self._edit_monitor_widgets))

    def _load_preset_to_edit_monitors(self, preset_data):
        """Carga los datos de un preset en los monitores virtuales de edición."""
        # La geometría depende del espacio disponible, no del Fixed redimensionado.
        layout_w = self._monitor_resize_area.get_allocated_width()

        # Edit/preset: necesitamos construir inmediatamente
        if layout_w < 50:
            layout_w = self._MONITOR_AREA_MIN_WIDTH

        # Los presets deben coincidir con la geometría visual vigente.
        monitors_map = self._visual_monitors_map or self.handler.load_json("geometry").get("monitors", {})
        layout_data = get_virtual_monitor_layout(monitors_map, layout_w, self._visual_area_height)

        if not layout_data:
            return

        wall_mode = (self.backend.edit_temp_wp_mode
                     or self.backend.load_settings().get("wallpaper_mode", "fit"))
        wp_scope = (self.backend.edit_temp_wp_scope
                    or self.backend.load_settings().get("wallpaper_effect_scope", "blur"))
        wp_effect = (self.backend.edit_temp_image_effect
                     or self.backend.load_settings().get("wallpaper_effect", "none"))
        spanned_enabled = self.backend.edit_temp_spanned_enabled
        if spanned_enabled is None:
            spanned_enabled = self.backend.load_settings().get("spanned_enabled", False)

        img_source = {}
        for data in layout_data:
            m_hash = data['hash']
            path = self.backend.edit_active_session.get(m_hash, "")
            active = self.backend.edit_active_states.get(m_hash, True)
            img_source[m_hash] = {"path": path, "active": active}

        layout_info = self.handler.load_json("geometry").get("monitors", {})
        source_hash = (self._get_edit_spanned_source_hash(layout_info)
                       if spanned_enabled else None)

        render_layout = self._get_quality_monitor_layout(
            monitors_map, layout_w)

        self.ie.paint_monitors_thumbnails(
            fixed_widget=self.monitors_fixed_edit,
            layout_data=render_layout,
            img_source=img_source,
            wallpaper_mode=wall_mode,
            spanned_enabled=spanned_enabled,
            color_tuple=self.backend.get_background_color_tuple(),
            wallpaper_effect_scope=wp_scope,
            image_effect=wp_effect,
            layout_info=layout_info,
            spanned_source_hash=source_hash,
        )

        # Capturar las fuentes procesadas del preset antes del escalado visual.
        self._edit_preview_refs = self._capture_monitor_previews(
            self._edit_monitor_widgets)

        self._resize_virtual_monitors(self.monitors_fixed_edit,
            self._edit_monitor_widgets, self._edit_preview_refs, layout_data)

        # Mantener sincronizada la geometría al actualizar el preset.
        self._sync_monitor_canvas(
            self.monitors_fixed_edit, layout_data, refresh_allocation=True)

        self._build_monitor_switches()

    # ==========================================================
    # DRAG & DROP (MODO EDICIÓN)
    # ==========================================================
    def _on_edit_drag_motion(self, widget, context, x, y, time, m_hash):
        """Resalta el monitor cuando se arrastra una imagen sobre él."""
        Gdk.drag_status(context, Gdk.DragAction.COPY, time)
        widget.get_style_context().add_class("dnd-target")
        return True

    def _on_edit_drag_leave(self, widget, context, time, m_hash):
        """Quita el resaltado cuando la imagen sale del monitor."""
        widget.get_style_context().remove_class("dnd-target")

    def _on_edit_drag_data_received(self, widget, context, x, y, data, info, time, m_hash):
        """Asigna la imagen soltada al monitor correspondiente."""
        if info == 2:
            widget.get_style_context().remove_class("dnd-target")
            self._on_online_drag_data_received(widget, context, data, time, m_hash)
            return
        try:
            img_path = base64.b64decode(data.get_text().encode('ascii')).decode('utf-8')
        except Exception:
            img_path = data.get_text()
        if not img_path:
            Gtk.drag_finish(context, False, False, time)
            return

        self.backend.edit_active_session[m_hash] = img_path

        # Una imagen asignada desde Library no hereda procedencia Online.
        self._online_drop_sources.pop(m_hash, None)

        if not self.backend.edit_active_states.get(m_hash, True):
            self.backend.edit_active_states[m_hash] = True
            if m_hash in self._monitor_switches:
                switch, hbox = self._monitor_switches[m_hash]
                switch.set_active(True)

        self._updating_switches = True
        if not self._repaint_scheduled:
            self._repaint_scheduled = True
            GLib.idle_add(self._idle_repaint_edit_monitors)

        self._updating_switches = False
        widget.get_style_context().remove_class("dnd-target")
        Gtk.drag_finish(context, True, False, time)
        log_event(f"Imagen asignada a {m_hash}: {img_path}",
            origin="MON_SECT", level="INFO", reason="BOOKMARK")

    def _idle_repaint_edit_monitors(self):
        """Repinta los monitores en edición tras un drag o cambio de switch."""
        self._repaint_scheduled = False
        if self.backend.edit_mode_active and self.backend.edit_active_session:
            self._load_preset_to_edit_monitors(self.backend.edit_active_session)
        return False

    # ==========================================================
    # EVENTOS DE EDICIÓN (SPANNED / IMAGE EFFECT)
    # ==========================================================
    def _on_spanned_edit_changed(self, switch, param):
        """Guarda el estado temporal de Distribuido en modo edición."""
        if self._loading:
            return
        self.backend.edit_temp_spanned_enabled = switch.get_active()
        if self.backend.edit_mode_active:
            self.backend.edit_temp_composition["__spanned__"] = self.backend.edit_temp_spanned_enabled

        if self.backend.edit_mode_active and self.backend.edit_active_session:
            self._updating_switches = True
            self._load_preset_to_edit_monitors(self.backend.edit_active_session)
            self._updating_switches = False
            self._notify_edit_preview()

    def _on_image_effect_edit_changed(self, combo):
        """Guarda el estado temporal de efecto de imagen en modo edición."""
        if self._loading:
            return
        keys = list(ConfigHandler.IMAGE_EFFECT.keys())
        index = combo.get_active()
        if 0 <= index < len(keys):
            self.backend.edit_temp_image_effect = keys[index]

            if self.backend.edit_mode_active:
                self.backend.edit_temp_composition["__effect__"] = self.backend.edit_temp_image_effect

            if self.backend.edit_mode_active and self.backend.edit_active_session:
                self._updating_switches = True
                self._load_preset_to_edit_monitors(self.backend.edit_active_session)
                self._updating_switches = False
                self._notify_edit_preview()
