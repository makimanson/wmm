#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

"""
WMM - Wallpaper Multi-Monitor Manager

thumbnails_section.py – Sección de miniaturas del panel de control.
==========================================================
Muestra la galería de imágenes indexadas, permite filtrar por orientación,
añadir/eliminar favoritos, arrastrar imágenes a los monitores virtuales
y regenerar las miniaturas bajo demanda.
"""

import os
import base64
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Pango
from debug_logger import log_event
from i18n import _

class ThumbnailsSection:
    """
    Sección de la galería de miniaturas del panel de control.
    """

    def __init__(self, handler, backend, right_col, scan_progress=None, btn_spacer=None):
        """
        Args:
            handler:      Instancia de ConfigHandler.
            backend:      Instancia de WMMBackend.
            right_col:    El Gtk.Box derecho donde se empaquetará la sección.
            callbacks:    Diccionario con funciones de callback para
                          comunicarse con otras secciones y el panel:
                          - 'begin_sources_operation': () -> bool
                          - 'finish_sources_operation': () -> bool
                          - 'is_sources_operation_active': () -> bool
                          - 'set_progress_active': (active, text=None) -> None
                          - 'load_bookmarks_single': () -> None
                          - 'load_thumbnails': () -> None
            scan_progress: Gtk.ProgressBar de la sección Sources, para
                           mostrar el progreso de generación de miniaturas.
            btn_spacer:    Gtk.Box espaciador de la sección Sources, para
                           alternar visibilidad con la barra de progreso.
        """
        self.handler = handler
        self.backend = backend
        self._callbacks = {}  # Se configurarán después con set_callbacks()

        # Widgets de progreso (compartidos con SourcesSection)
        self.scan_progress = scan_progress
        self.btn_spacer = btn_spacer

        # Estado interno
        self._thumbnails_loading = False
        self._first_h_item = None
        self._first_v_item = None
        self._progress_count = 0
        self._progress_total = 0
        self._progress_images = []
        self._progress_h_list = []
        self._progress_v_list = []
        self._favorite_paths = set()
        self._thumbnail_items = {}

        # Construir la interfaz
        self.widget = self._build()
        right_col.pack_start(self.widget, True, True, 0)

    def set_callbacks(self, callbacks):
        """Asigna los callbacks después de que la instancia exista."""
        self._callbacks = callbacks or {}

    # ==========================================================
    # PROPIEDADES DE ACCESO RÁPIDO A CALLBACKS
    # ==========================================================
    def _begin_sources_operation(self):
        cb = self._callbacks.get('begin_sources_operation')
        return cb() if cb else False

    def _finish_sources_operation(self):
        cb = self._callbacks.get('finish_sources_operation')
        return cb() if cb else False

    def _is_sources_operation_active(self):
        cb = self._callbacks.get('is_sources_operation_active')
        return cb() if cb else False

    def _set_progress_active(self, active, text=None):
        cb = self._callbacks.get('set_progress_active')
        if cb:
            cb(active, text)

    def _load_bookmarks_single(self):
        cb = self._callbacks.get('load_bookmarks_single')
        if cb:
            cb()

    def _reload_thumbnails(self):
        cb = self._callbacks.get('load_thumbnails')
        if cb:
            cb()

    # ==========================================================
    # CONSTRUCCIÓN DE LA INTERFAZ
    # ==========================================================
    def _build(self):
        """Construye y devuelve el widget principal de la sección."""
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        # ----------------------------------------------------------
        # CABECERA: Etiqueta + Navegación H/V + Botón de refresco
        # ----------------------------------------------------------
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        label = Gtk.Label()
        text = _("Thumbnails")
        label.set_markup(f"<span weight='bold' size='large'>{text}</span>")
        label.set_halign(Gtk.Align.START)
        header_box.pack_start(label, False, False, 0)

        nav_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6,
                          halign=Gtk.Align.CENTER)
        nav_box.set_hexpand(True)
        header_box.pack_start(nav_box, True, True, 0)

        # Botón Horizontal
        self.btn_h = Gtk.Button()
        label_h = Gtk.Label()
        label_h.set_markup("<b>" + _("Horizontal") + "</b>")
        self.btn_h.add(label_h)
        self.btn_h.set_relief(Gtk.ReliefStyle.NONE)
        self.btn_h.connect("clicked", self._scroll_to_h)
        nav_box.pack_start(self.btn_h, False, False, 0)

        # Botón Vertical
        self.btn_v = Gtk.Button()
        label_v = Gtk.Label()
        label_v.set_markup("<b>" + _("Vertical") + "</b>")
        self.btn_v.add(label_v)
        self.btn_v.set_relief(Gtk.ReliefStyle.NONE)
        self.btn_v.connect("clicked", self._scroll_to_v)
        nav_box.pack_start(self.btn_v, False, False, 0)

        # Botón Favorites
        self.btn_favorites = Gtk.Button()
        label_favorites = Gtk.Label()
        label_favorites.set_markup("<b>" + _("Favorites") + "</b>")
        self.btn_favorites.add(label_favorites)
        self.btn_favorites.set_relief(Gtk.ReliefStyle.NONE)
        self.btn_favorites.connect("clicked", self._show_favorites)
        nav_box.pack_start(self.btn_favorites, False, False, 0)

        # Botón de refresco de miniaturas
        refresh_thumb = Gtk.Button.new_from_icon_name("view-refresh-symbolic",
                                                      Gtk.IconSize.BUTTON)
        refresh_thumb.set_tooltip_text(_("Reload thumbnails"))
        refresh_thumb.connect("clicked", self._load_thumbnails)
        header_box.pack_end(refresh_thumb, False, False, 0)

        vbox.pack_start(header_box, False, False, 0)

        # ----------------------------------------------------------
        # VISTAS DE MINIATURAS
        # ----------------------------------------------------------
        self.thumbnails_stack = Gtk.Stack()

        # Vista normal H/V
        self.thumbnails_scrolled = Gtk.ScrolledWindow()
        self.thumbnails_flowbox = Gtk.FlowBox()
        self.thumbnails_flowbox.set_homogeneous(False)
        self.thumbnails_flowbox.set_row_spacing(2)
        self.thumbnails_flowbox.set_column_spacing(2)
        self.thumbnails_flowbox.set_max_children_per_line(128)
        self.thumbnails_flowbox.set_valign(Gtk.Align.START)
        self.thumbnails_scrolled.add(self.thumbnails_flowbox)
        self.thumbnails_stack.add_named(self.thumbnails_scrolled, "library")

        # Vista Favorites
        self.favorites_scrolled = Gtk.ScrolledWindow()
        self.favorites_flowbox = Gtk.FlowBox()
        self.favorites_flowbox.set_homogeneous(False)
        self.favorites_flowbox.set_row_spacing(2)
        self.favorites_flowbox.set_column_spacing(2)
        self.favorites_flowbox.set_max_children_per_line(128)
        self.favorites_flowbox.set_valign(Gtk.Align.START)
        self.favorites_scrolled.add(self.favorites_flowbox)
        self.thumbnails_stack.add_named(self.favorites_scrolled, "favorites")

        self.thumbnails_stack.set_visible_child_name("library")
        vbox.pack_start(self.thumbnails_stack, True, True, 0)

        return vbox

    # ==========================================================
    # CARGA DE MINIATURAS
    # ==========================================================
    def _load_thumbnails(self, widget=None, inherited_operation=False):
        """
        Inicia la carga asíncrona de todas las miniaturas de la biblioteca.

        Si forma parte de Sources, hereda la operación global ya abierta.
        Una recarga independiente abre su propia operación y la cerrará al FIN.
        """
        if self._thumbnails_loading:
            return False

        if inherited_operation:
            # Sources → Sync → Thumbnails es una sola operación:
            # esta fase final nunca debe abrir un segundo lifecycle.
            if not self._is_sources_operation_active():
                log_event("Thumbnails recibió una operación heredada sin lifecycle activo",
                    origin="PANEL", level="ERROR", reason="LIBRARY")
                return False
        elif not self._begin_sources_operation():
            return False

        self._thumbnails_loading = True
        log_event("Carga de miniaturas iniciada",
            origin="PANEL", level="INFO", reason="LIBRARY")

        # Limpiar el flowbox actual
        self._thumbnail_items.clear()
        for child in self.thumbnails_flowbox.get_children():
            self.thumbnails_flowbox.remove(child)

        h_list, v_list = self.handler.get_flat_lists()
        all_images = [(img, "h") for img in h_list] + [(img, "v") for img in v_list]
        total = len(all_images)

        if total == 0:
            self._thumbnails_loading = False
            self._set_progress_active(False)
            placeholder = Gtk.Label(label=_("No images found."))
            self.thumbnails_flowbox.add(placeholder)
            self._finish_sources_operation()
            return False

        self._set_progress_active(True, _("Generating thumbnails") + "...")
        self._progress_count = 0
        self._progress_total = total
        self._progress_images = all_images
        self._progress_h_list = h_list
        self._progress_v_list = v_list
        self._thumbnail_mtimes = {}
        self._thumbnail_paths = {}
        GLib.idle_add(self._generate_next_thumbnail)
        return False

    def _generate_next_thumbnail(self):
        """Genera la siguiente miniatura de la cola de forma asíncrona."""
        if self._progress_count < self._progress_total:
            img_data, orient = self._progress_images[self._progress_count]
            img_path = img_data[0]
            thumb_path = self.handler.get_thumbnail(img_path)
            self._thumbnail_paths[img_path] = thumb_path

            try:
                self._thumbnail_mtimes[img_path] = os.stat(thumb_path).st_mtime_ns if thumb_path else 0
            except OSError:
                self._thumbnail_mtimes[img_path] = 0

            self._progress_count += 1
            fraction = self._progress_count / self._progress_total
            if self.scan_progress:
                self.scan_progress.set_fraction(fraction)
                self.scan_progress.set_text(_("Processing") + " "
                    + str(self._progress_count) + "/" + str(self._progress_total))
            return True  # Continuar en el bucle GLib
        else:
            self._build_thumbnail_items()
            self._set_progress_active(False)
            self._finish_sources_operation()
            return False  # FIN global: sólo aquí Sources vuelve al usuario

    def _build_thumbnail_items(self):
        """Construye los widgets de miniatura a partir de las listas H/V."""
        self._first_h_item = None
        self._first_v_item = None

        # Conjunto de rutas favoritas para marcar visualmente
        self._favorite_paths.clear()
        fav_list = self.backend.load_json("bookmarks_single")

        for entry in fav_list:
            if entry and len(entry) > 0:
                self._favorite_paths.add(entry[0])

        # Estado de Sources compartido por toda esta reconstrucción.
        sources_data = self.handler.load_json("sources").get("sources", [])
        index = self.handler.load_json("index")

        h_list = sorted(self._progress_h_list,
            key=lambda img: self._thumbnail_mtimes.get(img[0], 0), reverse=True)
        v_list = sorted(self._progress_v_list,
            key=lambda img: self._thumbnail_mtimes.get(img[0], 0), reverse=True)

        for img in h_list:
            if self.handler._is_path_active(img[0], sources_data, index):
                self._add_thumbnail_item(
                    img[0], self._favorite_paths, self.thumbnails_flowbox,
                    self._thumbnail_paths.get(img[0]))

        for img in v_list:
            if self.handler._is_path_active(img[0], sources_data, index):
                self._add_thumbnail_item(
                    img[0], self._favorite_paths, self.thumbnails_flowbox,
                    self._thumbnail_paths.get(img[0]))

        children = self.thumbnails_flowbox.get_children()
        if h_list and len(children) > 0:
            self._first_h_item = children[0]
        if v_list and len(children) > len(h_list):
            self._first_v_item = children[len(h_list)]

        if not self.thumbnails_flowbox.get_children():
            placeholder = Gtk.Label(label=_("No images found."))
            self.thumbnails_flowbox.add(placeholder)

        self.thumbnails_flowbox.show_all()
        self._thumbnails_loading = False
        log_event(f"Thumbnails cargados: {len(self._progress_h_list)}H / {len(self._progress_v_list)}V",
            origin="PANEL", level="INFO", reason="LIBRARY")

    def _add_thumbnail_item(self, img_path, favorites, flowbox, thumb_path=None):
        """
        Crea un elemento de miniatura con su imagen, nombre y eventos.
        Args:
            img_path:  Ruta absoluta de la imagen.
            favorites: Conjunto de rutas favoritas para marcar el borde.
        """
        item_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        item_box.set_margin_start(4)
        item_box.set_margin_end(4)

        if thumb_path is None:
            thumb_path = self.handler.get_thumbnail(img_path)

        img = Gtk.Image.new_from_file(thumb_path)
        img.set_tooltip_text(img_path)
        img.set_size_request(-1, self.handler.thumbnail_max_height)
        item_box.pack_start(img, False, False, 0)

        name_label = Gtk.Label(label=os.path.basename(img_path))
        name_label.set_max_width_chars(20)
        name_label.set_ellipsize(Pango.EllipsizeMode.END)
        name_label.set_halign(Gtk.Align.CENTER)
        item_box.pack_start(name_label, False, False, 0)

        if img_path in favorites:
            item_box.get_style_context().add_class("favorite-thumbnail")

        if flowbox is self.thumbnails_flowbox:
            self._thumbnail_items[img_path] = item_box

        event_box = Gtk.EventBox()
        event_box.add(item_box)
        event_box.connect("button-press-event", self._on_thumbnail_click, img_path, favorites)
        event_box.connect("button-press-event", self._on_thumbnail_double_click, img_path)

        # Configurar como fuente de Drag & Drop
        event_box.drag_source_set(
            Gdk.ModifierType.BUTTON1_MASK,
            [Gtk.TargetEntry.new("text/plain", Gtk.TargetFlags.SAME_APP, 0)],
            Gdk.DragAction.COPY
        )
        event_box.connect("drag-data-get", self._on_thumbnail_drag_data_get, img_path)
        event_box.connect("drag-begin", self._on_thumbnail_drag_begin, img_path)
        event_box.connect("drag-end", self._on_thumbnail_drag_end, img_path)

        flowbox.add(event_box)

    # ==========================================================
    # NAVEGACIÓN H/V
    # ==========================================================
    def _scroll_to_h(self, widget):
        """Muestra la biblioteca normal y desplaza hasta el primer elemento horizontal."""
        self.thumbnails_stack.set_visible_child_name("library")
        if self._first_h_item:
            self.thumbnails_flowbox.select_child(self._first_h_item)
            self._first_h_item.grab_focus()

    def _scroll_to_v(self, widget):
        """Muestra la biblioteca normal y desplaza hasta el primer elemento vertical."""
        self.thumbnails_stack.set_visible_child_name("library")
        if self._first_v_item:
            self.thumbnails_flowbox.select_child(self._first_v_item)
            self._first_v_item.grab_focus()

    # ==========================================================
    # VISTA DE FAVORITOS
    # ==========================================================
    def _load_favorites_view(self):
        """Reconstruye la vista de miniaturas favoritas desde bookmarks_single_list.json."""
        for child in self.favorites_flowbox.get_children():
            self.favorites_flowbox.remove(child)

        fav_list = self.backend.load_json("bookmarks_single")
        favorites = {entry[0] for entry in fav_list if entry and len(entry) > 0}
        visible_count = 0

        for entry in fav_list:
            if not entry or len(entry) == 0:
                continue

            img_path = entry[0]

            if not img_path or not os.path.exists(img_path):
                continue

            self._add_thumbnail_item(img_path, self._favorite_paths, self.favorites_flowbox)
            visible_count += 1

        if visible_count == 0:
            self.favorites_flowbox.add(Gtk.Label(label=_("No favorite images.")))

        self.favorites_flowbox.show_all()
        log_event(f"Vista de favoritos cargada: {visible_count} imágenes", origin="PANEL", level="INFO", reason="BOOKMARK")

    def _show_favorites(self, widget):
        """Muestra la galería específica de imágenes favoritas."""
        self._load_favorites_view()
        self.thumbnails_stack.set_visible_child_name("favorites")

    # ==========================================================
    # EVENTOS DE RATÓN SOBRE MINIATURAS
    # ==========================================================
    def _on_thumbnail_click(self, widget, event, img_path, favorites):
        """Clic derecho: menú contextual para añadir/eliminar favoritos."""
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
        menu.popup_at_pointer(event)
        return True

    def _on_thumbnail_double_click(self, widget, event, img_path):
        """Doble clic: abre la imagen con el visor del sistema."""
        if event.type == Gdk.EventType._2BUTTON_PRESS and event.button == 1:
            self.handler.open_file(img_path)
            return True
        return False

    # ==========================================================
    # DRAG & DROP (ORIGEN)
    # ==========================================================
    def _on_thumbnail_drag_data_get(self, widget, context, data, info, time, img_path):
        """Prepara los datos para el Drag & Drop (ruta codificada en base64)."""
        encoded = base64.b64encode(img_path.encode('utf-8')).decode('ascii')
        data.set_text(encoded, -1)

    def _on_thumbnail_drag_begin(self, widget, context, img_path):
        """Inicia el Drag & Drop: aplica estilo visual y crea el icono de arrastre."""
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
        """Finaliza el Drag & Drop: restaura el estilo visual."""
        widget.get_style_context().remove_class("dnd-source")

    # ==========================================================
    # GESTIÓN DE FAVORITOS
    # ==========================================================
    def _refresh_favorite_state(self):
        """Actualiza el estado visual de favoritos sin reconstruir Thumbnails."""
        fav_list = self.backend.load_json("bookmarks_single")
        favorites = {entry[0] for entry in fav_list if entry and len(entry) > 0}

        self._favorite_paths.clear()
        self._favorite_paths.update(favorites)

        for img_path, item_box in self._thumbnail_items.items():
            context = item_box.get_style_context()

            if img_path in self._favorite_paths:
                context.add_class("favorite-thumbnail")
            else:
                context.remove_class("favorite-thumbnail")

        return False

    def _notify_single_favorites_changed(self):
        cb = self._callbacks.get('on_single_favorites_changed')
        if cb:
            cb()

    def _add_to_favorites(self, widget, img_path):
        """Añade una imagen a la lista plana de favoritos."""
        if self.handler.add_to_favorites(img_path):
            self._notify_single_favorites_changed()

    def _remove_from_favorites(self, widget, img_path):
        """Elimina una imagen de favoritos y sincroniza sus vistas."""
        if self.handler.remove_from_favorites(img_path):
            self._notify_single_favorites_changed()
