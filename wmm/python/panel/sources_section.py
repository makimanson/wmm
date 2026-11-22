#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

"""
WMM - Wallpaper Multi-Monitor Manager

sources_section.py – Sección de fuentes de imagen del panel de control.
==========================================================
Gestiona las fuentes de sources.json, el árbol de carpetas conocido
por scan_index.json y la sincronización de la biblioteca física.

La selección de carpetas sólo filtra la vista local de Thumbnails:
no modifica el índice ni la caché de imágenes.

"All" es una entrada de navegación, no una fuente persistente.
"Online" permite configurar su carpeta, independientemente del
buscador remoto y su galería en thumbnails_section.py.
"""

import os

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Gio, Pango

from debug_logger import log_event
from i18n import _

class SourcesSection:
    """
    Sección de fuentes de imagen del panel de control.
    """

    def __init__(self, handler, backend, ie, left_col, scan_progress=None, btn_spacer=None):
        """
        Args:
            handler: Instancia de ConfigHandler.
            backend: Instancia de WMMBackend.
            ie:      Instancia de ImageEngine.
            left_col: El Gtk.Box donde se empaquetará esta sección.
        """
        self.handler = handler
        self.backend = backend
        self.scan_progress = scan_progress
        self.btn_spacer = btn_spacer

        # Las selecciones producidas al reconstruir Sources no representan
        # una petición de navegación del usuario.
        self._rebuilding_sources_tree = False

        # Copia de lectura para representar las marcas sin acceder
        # al disco en cada repintado del TreeView.
        self._selective_index = {}

        # Construir la interfaz
        self.widget = self._build()
        left_col.pack_start(self.widget, True, True, 0)

    def set_callbacks(self, callbacks):
        """Asigna los callbacks después de que la instancia exista."""
        self._callbacks = callbacks or {}

    # ==========================================================
    # PROPIEDADES DE ACCESO RÁPIDO A CALLBACKS
    # ==========================================================
    @property
    def _parent_window(self):
        """Devuelve la ventana principal del panel."""
        cb = self._callbacks.get('get_parent_window')
        return cb() if cb else None

    # ==========================================================
    # CONSTRUCCIÓN DE LA INTERFAZ
    # ==========================================================
    def _build(self):
        """Construye y devuelve el widget principal de la sección."""
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        # --- Cabecera ---
        self.sources_toggle = Gtk.EventBox()
        self.sources_toggle.set_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)

        # Icono independiente del texto para conservar su geometría entre sistemas.
        self.sources_arrow = Gtk.Image.new_from_icon_name(
            "media-playback-start-symbolic", Gtk.IconSize.BUTTON)
        self.sources_arrow.set_pixel_size(12)
        self.sources_arrow.set_valign(Gtk.Align.CENTER)
        self.sources_arrow.get_style_context().add_class("wmm-playback-down")
        title_box.pack_start(self.sources_arrow, False, False, 0)

        self.sources_label = Gtk.Label()
        self.sources_label.set_markup(
            "<span weight='bold' size='medium'>" + _("Image Sources") + "</span>")
        self.sources_label.set_halign(Gtk.Align.START)
        title_box.pack_start(self.sources_label, False, False, 0)
        self.sources_toggle.add(title_box)
        self.sources_toggle.connect("button-press-event", self._on_sources_toggle)
        vbox.pack_start(self.sources_toggle, False, False, 0)

        # --- Contenido ---
        self.sources_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        vbox.pack_start(self.sources_content, True, True, 0)

        # Contener el árbol sin propagar la anchura de sus carpetas al formulario.
        # El árbol adapta sus columnas al espacio disponible.
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scrolled_sources = scrolled

        # Identificar el área de fuentes para diferenciar su fondo en Win32.
        scrolled.get_style_context().add_class("wmm-sources-scroll")

        # Modelo: [icono, nombre, ruta, active, recursive, is_raiz]
        self.sources_model = Gtk.TreeStore(str, str, str, bool, bool, bool)
        self.sources_tree = Gtk.TreeView(model=self.sources_model)
        self.sources_tree.connect("row-activated", self._on_source_row_activated)

        # Actualizar el botón de eliminar al cambiar la selección
        selection = self.sources_tree.get_selection()
        selection.connect("changed", self._update_delete_button)
        self.sources_model.connect("row-changed", self._update_delete_button)

        # Actualizar también el mensaje informativo al cambiar de fuente.
        selection.connect("changed", self._update_resync_notice)

        # Columna "Source" con icono y texto
        col_name = Gtk.TreeViewColumn(_("Source"))
        ri, rt = Gtk.CellRendererPixbuf(), Gtk.CellRendererText()
        self._source_text_renderer = rt
        col_name.pack_start(ri, False)
        col_name.pack_start(rt, True)
        col_name.set_cell_data_func(ri, self._render_source_icon)
        col_name.set_cell_data_func(rt, self._render_source_text)

        # Source absorbe el espacio libre, no el ancho de los nombres.
        # Los nombres demasiado largos se truncan dentro de la columna.
        rt.set_property("ellipsize", Pango.EllipsizeMode.END)
        col_name.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        col_name.set_fixed_width(1)
        col_name.set_expand(True)
        self.sources_tree.append_column(col_name)

        # Columna "Recursive" con toggle
        renderer_rec = Gtk.CellRendererToggle()
        renderer_rec.connect("toggled", self.on_recursive_toggled)
        self.col_recursive = Gtk.TreeViewColumn(_("Recursive"), renderer_rec, active=4)
        self.col_recursive.set_cell_data_func(renderer_rec, self._hide_checkbox_in_children)
        self.sources_tree.append_column(self.col_recursive)

        self.sources_tree.set_has_tooltip(True)
        self.sources_tree.connect("query-tooltip", self._on_sources_tooltip)

        self.sources_tree.connect("button-press-event", self.on_tree_button_press)
        scrolled.add(self.sources_tree)
        self.sources_content.pack_start(scrolled, True, True, 0)

        # Barra de botones inferior
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)

        # Identificar el pie de Sources para su presentación en Windows.
        btn_box.get_style_context().add_class("wmm-sources-footer")

        self.refresh_btn = Gtk.Button.new_from_icon_name(
            "view-refresh-symbolic", Gtk.IconSize.BUTTON)
        self.refresh_btn.set_tooltip_text(_("Resync Image Sources"))
        self.refresh_btn.connect("clicked", self.on_refresh_sources_clicked)
        btn_box.pack_start(self.refresh_btn, False, False, 0)

        self.center_stack = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.center_stack.pack_start(self.scan_progress, True, True, 0)

        self.resync_notice = Gtk.Label(label=_("Sources need resynchronization"))
        self.resync_notice.set_halign(Gtk.Align.CENTER)
        self.resync_notice.set_no_show_all(True)
        self.resync_notice.hide()
        self.center_stack.pack_start(self.resync_notice, True, True, 0)

        self.center_stack.pack_start(self.btn_spacer, True, True, 0)
        btn_box.pack_start(self.center_stack, True, True, 0)

        self.add_btn = Gtk.Button.new_from_icon_name("folder-new", Gtk.IconSize.BUTTON)
        self.add_btn.set_tooltip_text(_("Add Image Source"))
        self.add_btn.connect("clicked", self.on_add_source_clicked)
        self.del_btn = Gtk.Button.new_from_icon_name("user-trash", Gtk.IconSize.BUTTON)
        self.del_btn.get_style_context().add_class("wmm-trash-symbolic")
        self.del_btn.set_tooltip_text(_("Delete image source"))
        self.del_btn.connect("clicked", self._on_delete_button_clicked)

        btn_box.pack_end(self.del_btn, False, False, 0)
        btn_box.pack_end(self.add_btn, False, False, 5)

        self.sources_content.pack_start(btn_box, False, False, 0)

        return vbox

    def _on_sources_toggle(self, widget, event):
        """Pliega o despliega el contenido de Fuentes de imágenes."""
        expanded = not self.sources_content.get_visible()

        if expanded:
            self._parent_window._expand_section_to_fit("sources")
        else:
            self.set_expanded(False)

        self._parent_window._save_section_state("sources", expanded)

        if not expanded:
            GLib.idle_add(self._parent_window._fit_collapsed)

    def set_expanded(self, expanded):
        """Aplica el estado de despliegue de Fuentes de imágenes sin persistirlo."""
        self.sources_content.set_visible(expanded)

        parent = self.widget.get_parent()
        if parent:
            parent.queue_resize()
            parent.child_set_property(self.widget, "expand", expanded)
            parent.child_set_property(self.widget, "fill", expanded)

        # La expansión modifica el icono sin reconstruir la etiqueta.
        arrow_style = self.sources_arrow.get_style_context()
        if expanded:
            arrow_style.add_class("wmm-playback-down")
        else:
            arrow_style.remove_class("wmm-playback-down")

        self.widget.queue_resize()

    # ==========================================================
    # CARGA Y EXPANSIÓN DEL TREEVIEW
    # ==========================================================
    def load_sources_into_treeview(self):
        """Reconstruye Sources sin confundir sus selecciones con navegación."""
        self._rebuilding_sources_tree = True
        try:
            self._rebuild_sources_tree()
        finally:
            self._rebuilding_sources_tree = False

    def _rebuild_sources_tree(self):
        # Guardar posición actual del scroll
        vadj = self.scrolled_sources.get_vadjustment()
        saved_value = vadj.get_value()

        # La selección se conserva por identidad lógica, no por posición.
        # También debe sobrevivir a la reconstrucción el filtro de Thumbnails.
        selection = self.sources_tree.get_selection()
        model, selected_iter = selection.get_selected()
        selected_path = model.get_value(selected_iter, 2) if selected_iter else None

        # Las ramas expandidas se identifican por su ruta física.
        # Las posiciones GTK pueden cambiar al reconstruir Sources.
        expanded_paths = set()
        def save_expanded_paths(model, parent_iter=None):
            if parent_iter is None:
                parent_iter = model.get_iter_first()
            while parent_iter:
                if model.iter_has_child(parent_iter):
                    tree_path = model.get_path(parent_iter)
                    if self.sources_tree.row_expanded(tree_path):
                        expanded_paths.add(model.get_value(parent_iter, 2))
                    # Una única llamada procesa todos los hijos y sus hermanos.
                    # Evita recorrer repetidamente las mismas ramas.
                    save_expanded_paths(model, model.iter_children(parent_iter))
                parent_iter = model.iter_next(parent_iter)
        save_expanded_paths(self.sources_model)

        self.sources_model.clear()
        sources_data = self.backend.load_json("sources").get("sources", [])
        index_data = self.backend.load_json("index")
        self._selective_index = index_data
        self._selective_enabled = self.backend.load_settings().get(
            "selective_rotation_enabled", False)

        # "All" pertenece sólo a la navegación visual del árbol.
        # Su identificador no representa una ruta ni una Source real.
        self.sources_model.append(None, [
            "", _("All"), "__all__", True, False, False])

        # sources.json define las raíces; scan_index aporta la estructura lógica
        # conocida y el estado Active/Inactive de sus hijas.
        for s in sources_data:
            root_path = s.get('path')

            if s.get('type') == 'virtual':
                continue

            # Mostrar Online aunque todavía no tenga ubicación.
            # Sin carpeta configurada no admite operaciones de Sources.
            if not root_path:
                if s.get('id') == 'online':
                    self.sources_model.append(None, [
                        "", s.get('name', 'Online'), "", False, False, False
                    ])
                continue

            root_name = s.get('name', os.path.basename(root_path))
            is_recursive = s.get('recursive', False)

            root_active = self.handler.get_index_active(
                root_path, index_data, default=s.get('active', True))

            parent_iter = self.sources_model.append(None, [
                "", root_name, root_path, root_active, is_recursive, True ])

            # Recursive decide si las hijas conocidas forman parte del árbol;
            # su presencia aquí no depende de que conserven image_cache.
            if is_recursive:
                prefix = root_path if root_path.endswith(os.sep) else root_path + os.sep
                sub_paths = sorted([p for p in index_data if p.startswith(prefix)])
                path_to_iter = {root_path: parent_iter}

                for sub in sub_paths:
                    parent_path = os.path.dirname(sub)
                    if parent_path in path_to_iter:
                        sub_active = self.handler.get_index_active(sub, index_data)

                        current_iter = self.sources_model.append(path_to_iter[parent_path],
                            ["", os.path.basename(sub), sub, sub_active, False, False])
                        path_to_iter[sub] = current_iter

        log_event("Vista de fuentes reconstruida",
            origin="SOURCES_SECT", level="INFO", reason="LIBRARY")

        self.sources_tree.set_model(None)
        self.sources_tree.set_model(self.sources_model)
        self._update_resync_notice()

        # Restaurar posición del scroll
        def restore_scroll():
            # All está en la cabecera del árbol y debe permanecer visible.
            # Las carpetas conservan el desplazamiento previo.
            model, tree_iter = self.sources_tree.get_selection().get_selected()
            selected = model.get_value(tree_iter, 2) if tree_iter else None

            vadj.set_value(vadj.get_lower() if selected == "__all__" else saved_value)
            return False

        GLib.idle_add(restore_scroll)

        # Restaurar las ramas antes de recuperar la selección:
        # GTK no permite seleccionar una fila oculta por sus ancestros.
        def restore_expanded_paths():

            # Recorrer el nuevo modelo en orden jerárquico permite
            # desplegar cada padre antes de sus posibles descendientes.
            def restore_expanded_row(model, tree_path, tree_iter, *args):
                folder_path = model.get_value(tree_iter, 2)
                if folder_path in expanded_paths:
                    self.sources_tree.expand_row(tree_path, open_all=False)
                return False

            self.sources_model.foreach(restore_expanded_row)

            # Recuperar la carpeta por su ruta, no por la posición
            # que ocupaba antes de reconstruir el modelo.
            selection_restored = False

            if selected_path is not None:
                def restore_selection(model, path, tree_iter, *args):
                    nonlocal selection_restored
                    if model.get_value(tree_iter, 2) == selected_path:
                        self.sources_tree.get_selection().select_iter(tree_iter)
                        selection_restored = True
                        return True
                    return False

                self.sources_model.foreach(restore_selection)

            # Si la carpeta desapareció, All representa la vista restante.
            # Evitar que Sources quede sin referencia visual.
            if not selection_restored:
                all_iter = self.sources_model.get_iter_first()
                if all_iter:
                    self.sources_tree.get_selection().select_iter(all_iter)
            return False

        # La restauración debe ser inmediata, no mediante GLib.idle_add().
        # Aplazarla permitió mostrar brevemente miniaturas sin el filtro
        # de la carpeta seleccionada durante la reconstrucción de Sources.
        restore_expanded_paths()

    # ==========================================================
    # RENDERERS DEL TREEVIEW
    # ==========================================================
    def _on_sources_tooltip(self, treeview, x, y, keyboard_mode, tooltip):
        if keyboard_mode:
            return False

        bin_x, bin_y = treeview.convert_widget_to_bin_window_coords(x, y)
        hit = treeview.get_path_at_pos(bin_x, bin_y)
        if not hit:
            return False

        path, column, cell_x, cell_y = hit
        tree_iter = self.sources_model.get_iter(path)

        # Online permanece visible sin directorio, pero necesita informar
        # al usuario antes de poder participar en Sources.
        if not self.sources_model.get_value(tree_iter, 2):
            tooltip.set_text(_("Set a destination folder."))
            return True

        # Mostrar el nombre completo sólo cuando su representación
        # supera el espacio disponible en la celda Source.
        if column == treeview.get_column(0):
            folder_path = self.sources_model.get_value(tree_iter, 2)
            if folder_path == "__all__":
                return False

            name = self.sources_model.get_value(tree_iter, 1)
            position = column.cell_get_position(self._source_text_renderer)
            if position is None:
                return False

            offset, width = position
            area = treeview.get_cell_area(path, column)
            xpad = self._source_text_renderer.get_padding()[0]

            # La celda real puede ser más estrecha en ramas anidadas.
            available = max(0, min(width, area.width - offset) - 2 * xpad)
            layout = treeview.create_pango_layout(name)
            text_width = layout.get_pixel_size()[0]

            if text_width <= available:
                return False

            tooltip.set_text(name)
            treeview.set_tooltip_cell(
                tooltip, path, column, self._source_text_renderer)
            return True

        if column != self.col_recursive:
            return False

        if not self.sources_model.get_value(tree_iter, 5):
            return False

        tooltip.set_text(
            _("Enabled") + ": " + _("Adds all subdirectories to the library.") + "\n"
            + _("Disabled") + ": " + _("Removes subdirectories from the library."))
        return True

    def _hide_checkbox_in_children(self, column, cell, model, iter, data):
        is_raiz = model.get_value(iter, 5)
        cell.set_property("visible", is_raiz)
        cell.set_property("activatable", is_raiz)

    def on_recursive_toggled(self, widget, path):
        tree_iter = self.sources_model.get_iter(path)
        current_val = self.sources_model.get_value(tree_iter, 4)
        new_val = not current_val
        path_disk = self.sources_model.get_value(tree_iter, 2)

        if not self.handler.update_source_recursive(path_disk, new_val):
            return

        # Activar Recursive descubre estructura lógica únicamente:
        # no materializa imágenes ni genera thumbnails por sí mismo.
        if new_val:
            self.handler.discover_recursive_folders(path_disk)

        log_event(f"Recursividad cambiada: '{path_disk}' -> {new_val}",
            origin="SOURCES_SECT", level="INFO", reason="LIBRARY")

        self.load_sources_into_treeview()

        if new_val:
            GLib.idle_add(self._expand_source_row, path_disk)

        self._update_resync_notice()

        # Refrescar Thumbnails sólo si existe materialización reutilizable;
        # Recursive no debe provocar una reconstrucción implícita del cache.
        if self.handler.has_child_cache(path_disk):
            load_thumbnails = self._callbacks.get('load_thumbnails')
            if load_thumbnails:
                load_thumbnails()

    def set_selective_mode(self, enabled):
        """Actualiza la representación de Sources sin alterar sus marcas."""
        self._selective_enabled = enabled
        self.sources_tree.queue_draw()

    def _render_source_icon(self, column, cell, model, iter, data):
        is_active = model.get_value(iter, 3)
        is_recursive = model.get_value(iter, 4)
        is_raiz = model.get_value(iter, 5)
        path = model.get_value(iter, 2)

        if path == "__all__":
            icon_name = "view-grid-symbolic"
        else:
            icon_name = "folder-remote" if (is_raiz and is_recursive) else "folder"

        icon = Gio.ThemedIcon.new(icon_name)

        if path and path != "__all__":
            entry = self._selective_index.get(path, False)
            selected = isinstance(entry, list) and len(entry) > 1 and entry[1]

            # Active/Inactive tiene prioridad sobre rotación selectiva.
            emblem_name = (
                "window-close-symbolic" if not is_active
                else "object-select-symbolic" if selected
                else None
            )

            if emblem_name:
                emblem = Gio.Emblem.new(Gio.ThemedIcon.new(emblem_name))
                icon = Gio.EmblemedIcon.new(icon, emblem)

        cell.set_property("icon-name", None)
        cell.set_property("gicon", icon)
        cell.set_property("sensitive", is_active)

    def _render_source_text(self, column, cell, model, iter, data):
        text = model.get_value(iter, 1)
        path = model.get_value(iter, 2)
        is_active = model.get_value(iter, 3)

        entry = self._selective_index.get(path, False)
        selected = isinstance(entry, list) and len(entry) > 1 and entry[1]

        partial = False
        if model.iter_has_child(iter):
            prefix = path if path.endswith(os.sep) else path + os.sep
            states = [selected]
            states.extend(
                isinstance(value, list) and len(value) > 1 and bool(value[1])
                for folder, value in self._selective_index.items()
                if folder.startswith(prefix)
            )
            partial = any(states) and not all(states)

        label = GLib.markup_escape_text(text)

        if is_active:
            if partial:
                alpha = "100%" if self._selective_enabled else "75%"
                label = f'<span foreground="#D69E2E" alpha="{alpha}">{label}</span>'
            elif selected:
                alpha = "100%" if self._selective_enabled else "75%"
                label = f'<span foreground="#2EAD59" alpha="{alpha}">{label}</span>'
            elif self._selective_enabled and path != "__all__":
                label = f'<span alpha="75%">{label}</span>'

        cell.set_property("foreground-set", False)
        cell.set_property("markup", label)
        cell.set_property("sensitive", is_active)

    # ==========================================================
    # EVENTOS DEL TREEVIEW
    # ==========================================================
    def on_tree_button_press(self, treeview, event):
        if event.button != 3:
            return False

        # El destino del menú es siempre la fila pulsada, nunca
        # una selección anterior que GTK todavía no haya actualizado.
        hit = treeview.get_path_at_pos(int(event.x), int(event.y))
        if not hit:
            return True

        tree_path = hit[0]
        tree_iter = self.sources_model.get_iter(tree_path)
        folder_path = self.sources_model.get_value(tree_iter, 2)

        # All y Online sin directorio no admiten acciones contextuales.
        if not folder_path or folder_path == "__all__":
            return True

        # Sincronizar primero la selección para que también coincidan
        # el filtro de Thumbnails y la carpeta sobre la que actuamos.
        treeview.get_selection().select_path(tree_path)
        self.show_context_menu(folder_path, tree_iter, event)
        return True

    def _on_source_row_activated(self, treeview, path, column):
        model = treeview.get_model()
        iter = model.get_iter(path)
        folder_path = model.get_value(iter, 2)
        if folder_path and folder_path != "__all__":
            self.handler.open_file(folder_path)

    def _on_delete_button_clicked(self, widget):
        """Elimina una fuente raíz o alterna el estado de una subcarpeta."""
        model, tree_iter = self.sources_tree.get_selection().get_selected()
        if not tree_iter:
            return

        path = model.get_value(tree_iter, 2)

        # All no es una fuente y Online sin ruta no admite eliminación.
        # La representación visual del botón pertenece a _update_delete_button().
        if not path or path == "__all__":
            return

        if model.get_value(tree_iter, 5):
            self.on_remove_source_clicked(widget)
        else:
            self.toggle_child_active(widget, model, tree_iter)

    def _update_delete_button(self, *args):
        """Actualiza el icono y el tooltip del botón según el elemento seleccionado."""

        # La papelera utiliza la variante simbólica en Win32.
        # Las subcarpetas recuperan el estilo original de sus iconos.
        self.del_btn.get_style_context().add_class("wmm-trash-symbolic")

        selection = self.sources_tree.get_selection()
        model, tree_iter = selection.get_selected()

        # La identidad Online procede de sources.json, no del texto visible.
        # Sin ruta, es la única fuente representada con path vacío.
        selected_path = model.get_value(tree_iter, 2) if tree_iter else None
        online_source = next(
            (s for s in self.backend.load_json("sources").get("sources", [])
             if s.get("id") == "online"), None)

        is_online = bool(online_source and tree_iter and (
            (not selected_path and not online_source.get("path"))
            or (model.get_value(tree_iter, 5)
                and selected_path == online_source.get("path"))
        ))

        if is_online:
            # Online desvincula su directorio; nunca activa ni desactiva carpetas.
            # Restaurar el icono evita heredar el estado visual de una subcarpeta.
            self.del_btn.set_image(Gtk.Image.new_from_icon_name(
                "user-trash", Gtk.IconSize.BUTTON))
            self.add_btn.set_tooltip_text(
                _("Change Online folder") if selected_path
                else _("Set Online folder"))
            self.del_btn.set_tooltip_text(
                _("Remove Online folder link. This folder and its contents will not be deleted."))

            # El manejador de Añadir distingue Online de las fuentes normales.
            self.add_btn.set_sensitive(self.sources_tree.get_sensitive())

            # Se protege la fuente, no su vinculación al directorio.
            self.del_btn.set_sensitive(
                bool(selected_path) and self.sources_tree.get_sensitive())
            return

        self.add_btn.set_tooltip_text(_("Add Image Source"))
        self.add_btn.set_sensitive(self.sources_tree.get_sensitive())

        if not tree_iter or selected_path in (None, "", "__all__"):
            # Sin selección: icono de papelera inactivo
            self.del_btn.set_image(Gtk.Image.new_from_icon_name(
                "user-trash", Gtk.IconSize.BUTTON))
            self.del_btn.set_tooltip_text(_("Delete image source"))
            self.del_btn.set_sensitive(False)
            return

        is_raiz = model.get_value(tree_iter, 5)  # Columna 5: is_raiz
        is_active = model.get_value(tree_iter, 3)  # Columna 3: active

        if is_raiz:
            # Carpeta padre: papelera
            self.del_btn.set_image(Gtk.Image.new_from_icon_name(
                "user-trash", Gtk.IconSize.BUTTON))
            self.del_btn.set_tooltip_text(_("Delete image source"))
            self.del_btn.set_sensitive(True)
        else:
            # Subcarpeta: ojo con aspa (desactivar) u ojo sin aspa (activar)
            self.del_btn.get_style_context().remove_class("wmm-trash-symbolic")

            if is_active:
                self.del_btn.set_image(Gtk.Image.new_from_icon_name(
                    "view-conceal", Gtk.IconSize.BUTTON))
                self.del_btn.set_tooltip_text(_("Deactivate folder"))
            else:
                self.del_btn.set_image(Gtk.Image.new_from_icon_name(
                    "view-reveal", Gtk.IconSize.BUTTON))
                self.del_btn.set_tooltip_text(_("Activate folder"))
            self.del_btn.set_sensitive(True)

    def _expand_source_row(self, source_path):
        """Despliega la raíz indicada en el árbol de Sources."""
        tree_iter = self.sources_model.get_iter_first()

        while tree_iter:
            if self.sources_model.get_value(tree_iter, 2) == source_path:
                tree_path = self.sources_model.get_path(tree_iter)
                if tree_path:
                    self.sources_tree.expand_row(tree_path, open_all=False)
                break

            tree_iter = self.sources_model.iter_next(tree_iter)

        return False

    # ==========================================================
    # CONTROL DE OCUPACIÓN (PROGRESS BAR)
    # ==========================================================

    def _set_sources_sensitive(self, sensitive):
        self.sources_tree.set_sensitive(sensitive)
        if hasattr(self, 'refresh_btn'):
            self.refresh_btn.set_sensitive(sensitive)
        if hasattr(self, 'add_btn'):
            self.add_btn.set_sensitive(sensitive)
        if hasattr(self, 'del_btn'):
            self.del_btn.set_sensitive(sensitive)

    def _update_resync_notice(self, *args):
        """Actualiza el mensaje del espacio compartido con la barra de progreso."""
        if self.scan_progress.get_visible():
            self.resync_notice.hide()
            self.btn_spacer.hide()
            return

        needs_resync = self.handler.needs_sources_resync()

        # Online es la única fuente visible que admite una ruta vacía.
        selection = self.sources_tree.get_selection()
        model, tree_iter = selection.get_selected()
        online_pending = (tree_iter is not None and not model.get_value(tree_iter, 2))

        if needs_resync:
            self.resync_notice.set_text(_("Sources need resynchronization"))
        elif online_pending:
            self.resync_notice.set_text(_("Set a destination folder."))

        show_notice = needs_resync or online_pending
        self.resync_notice.set_visible(show_notice)
        self.btn_spacer.set_visible(not show_notice)

    # ==========================================================
    # SINCRONIZACIÓN Y PROGRESO
    # ==========================================================
    def _on_sync_error(self, _message):
        """Comunica el fallo sin exponer detalles técnicos al usuario.

        ConfigHandler ya registra la excepción original en Debug Logger.
        Sources sólo informa del fallo y libera la operación del Panel.
        """
        self._callbacks['set_progress_active'](False)
        self._callbacks['finish_sources_operation']()

        self.handler._send_notification(
            reason=_("Could not synchronize the image library"),
            detail_msg=_("For more information, see the WMM Debug Logger."),
            level="error")

    def _on_sync_folder_start(self, folder_path):
        """Mantiene el contrato asíncrono de sync_library.

        El progreso se actualiza mediante _on_sync_progress; no es
        necesaria ninguna acción adicional al comenzar cada carpeta.
        """
        return False

    def _on_sync_progress(self, current, total):
        if total > 0:
            fraction = current / total
            self.scan_progress.set_fraction(fraction)
            self.scan_progress.set_text(
                _("Scanning") + " " + str(current) + "/" + str(total) + " " + _("folders") + "...")

    def show_context_menu(self, path, iter, event):
        is_active = self.sources_model.get_value(iter, 3)

        # La identidad raíz/hija pertenece al modelo Sources.
        # No debe reconstruirse mediante comparaciones de rutas.
        is_root = self.sources_model.get_value(iter, 5)

        menu = self._parent_window.create_context_menu()

        # Las raíces recursivas conservan sus acciones históricas.
        # Una carpeta hija también puede administrar sus descendientes.
        has_children = self.sources_model.iter_has_child(iter)
        if (is_root and self.sources_model.get_value(iter, 4)) or has_children:
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

        has_cache = self.handler.has_folder_cache(path)
        # Sólo una hija activa y sin cache puede materializarse explícitamente:
        # Generate thumbnails no debe resolver otras Sources pendientes.
        if not is_root:
            item_generate = Gtk.MenuItem(label=_("Generate thumbnails"))
            item_generate.set_sensitive(is_active and not has_cache)
            item_generate.connect("activate", self.on_generate_thumbnails_clicked, path)
            menu.append(item_generate)
        # Delete cache pertenece a hijas inactivas; permanece visible aunque
        # ya no exista cache y sólo se deshabilita mediante set_sensitive().
        if not is_active:
            item_purge = Gtk.MenuItem(label=_("Delete cache"))
            item_purge.set_sensitive(self.handler.has_folder_cache(path))
            item_purge.connect("activate", self.on_purge_cache_clicked, path)
            menu.append(item_purge)

        # Rotación selectiva: sólo disponible en carpetas activas.
        if is_active:
            index = self.handler.load_json("index")
            entry = index.get(path, False)
            selected = isinstance(entry, list) and len(entry) > 1 and entry[1]

            menu.append(Gtk.SeparatorMenuItem())

            item_selective = Gtk.MenuItem(
                label=_("Remove from selective rotation") if selected
                else _("Add to selective rotation"))
            item_selective.connect(
                "activate", self._on_selective_rotation_toggled,
                path, not selected)
            menu.append(item_selective)

        menu.show_all()
        menu.popup_at_pointer(event)

    def _on_selective_rotation_toggled(self, widget, path, state):
        """Actualiza la selección y el estado global de rotación selectiva."""
        if not self.handler.set_index_selective_state(path, state):
            return

        self._selective_index = self.handler.load_json("index")

        # La disponibilidad del modo depende de las marcas actuales.
        refresh = self._callbacks.get("refresh_selective_rotation_availability")
        if refresh:
            refresh()

        # Las marcas son independientes de la activación del modo.
        # Sólo el switch de Options modifica selective_rotation_enabled.

        self.sources_tree.queue_draw()
        log_event(f"Rotación selectiva: {path} -> {state}",
            origin="SOURCES_SECT", level="INFO", reason="LIBRARY")

    def toggle_child_active(self, widget, model, iter):
        path = model.get_value(iter, 2)
        new_state = not model.get_value(iter, 3)
        model.set_value(iter, 3, new_state)

        if self.handler.update_index_active_state(path, new_state):
            log_event(f"Estado cambiado: {path} -> {new_state}",
                origin="SOURCES_SECT", level="INFO", reason="LIBRARY")

            # Active modifica la elegibilidad, pero conserva la marca Selective.
            refresh = self._callbacks.get("refresh_selective_rotation_availability")
            if refresh:
                refresh()

        # Desactivar oculta inmediatamente la carpeta.
        # Reactivar reutiliza thumbnails sólo si su cache todavía existe.
        has_cache = self.handler.has_folder_cache(path)

        # Reactivar sin cache no materializa implícitamente:
        # queda pendiente de Sync o Generate thumbnails.
        should_reload_thumbnails = not new_state or has_cache

        if should_reload_thumbnails:
            load_thumbnails = self._callbacks.get('load_thumbnails')
            if load_thumbnails:
                load_thumbnails()

        self._update_resync_notice()

    def on_purge_cache_clicked(self, widget, folder_path):
        dialog = Gtk.MessageDialog(
            transient_for=self._callbacks.get('get_parent_window', lambda: None)(),
            flags=0,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=_("Delete cache of this folder?"))
        dialog.format_secondary_text(
            _("Will be removed from your library") + ":" + "\n" +
            folder_path + "\n" +
            _("Images will no longer be available"))
        response = dialog.run()
        if response == Gtk.ResponseType.YES:
            # El borrado afecta sólo a la materialización de esta hija;
            # su estado lógico Inactive permanece en scan_index.
            deleted_count = self.handler.purge_folder_cache(folder_path)
            if deleted_count > 0:
                self.handler._send_notification(
                    reason=_("Cache deleted"),
                    detail_msg=str(deleted_count) + " " + _("thumbnails have been removed from cache"),
                    level="info")
            else:
                self.handler._send_notification(
                    reason=_("No cache"),
                    detail_msg=_("No thumbnails found in cache for this folder."),
                    level="info")
            self._update_resync_notice()
        dialog.destroy()

    def on_generate_thumbnails_clicked(self, widget, folder_path):
        if not self._callbacks['begin_sources_operation']():
            return

        self._callbacks['set_progress_active'](True, _("Scanning folder") + "...")

        def materialize():
            # Materialización explícita y local: sólo esta carpeta recupera cache.
            success, total = self.handler.materialize_folder_cache(folder_path)

            if not success:
                self._callbacks['set_progress_active'](False)
                self._update_resync_notice()
                self._callbacks['finish_sources_operation']()
                return False

            log_event(f"Generación explícita solicitada: {folder_path} ({total} imágenes)",
                origin="SOURCES_SECT", level="INFO", reason="LIBRARY")

            load_thumbnails = self._callbacks.get('load_thumbnails')
            if load_thumbnails:
                load_thumbnails(None, True)
            else:
                self._callbacks['set_progress_active'](False)
                self._update_resync_notice()
                self._callbacks['finish_sources_operation']()

                # Registro rechazado antes de iniciar Sync.
                # Comunicarlo sin presentar el rechazo como un fallo de escaneo.
                if is_online:
                    reason = _("Could not assign folder to Online")
                    detail = _("Check that the folder is available and not already used by another source.")
                else:
                    reason = _("Image source not added")
                    detail = _("This folder may already be registered as an image source.")

                self.handler._send_notification(
                    reason=reason, detail_msg=detail, level="warn")

            return False

        GLib.idle_add(materialize)

    def on_bulk_toggle(self, widget, parent_path, new_state):
        if self.handler.toggle_all_children(parent_path, new_state):
            log_event(f"Cambio masivo: {parent_path} -> {new_state}",
                origin="SOURCES_SECT", level="INFO", reason="LIBRARY")
            self.load_sources_into_treeview()

            # Reevaluar una sola vez tras actualizar toda la rama.
            refresh = self._callbacks.get("refresh_selective_rotation_availability")
            if refresh:
                refresh()

            # El cambio masivo modifica únicamente Active/Inactive.
            # Desactivar oculta; reactivar sólo reutiliza lo que aún conserva cache.
            should_reload_thumbnails = not new_state or self.handler.has_child_cache(parent_path)

            if should_reload_thumbnails:
                load_thumbnails = self._callbacks.get('load_thumbnails')
                if load_thumbnails:
                    load_thumbnails()

    # ==========================================================
    # BOTONES DE ACCIÓN
    # ==========================================================
    def on_refresh_sources_clicked(self, widget):
        log_event("Refresco manual de fuentes solicitado",
            origin="SOURCES_SECT", level="INFO", reason="LIBRARY")

        if not self._callbacks['begin_sources_operation']():
            return

        self._callbacks['set_progress_active'](True, _("Scanning sources") + "...")

        # Sync y Thumbnails forman una única operación global:
        # Thumbnails recibe el FIN y libera Sources.
        load_thumbnails = self._callbacks.get('load_thumbnails')

        def on_complete():
            if load_thumbnails:
                GLib.idle_add(load_thumbnails, None, True)
            else:
                self._callbacks['set_progress_active'](False)
                self._callbacks['finish_sources_operation']()

        self.handler.sync_library(
            on_progress=self._on_sync_progress,
            on_folder=self._on_sync_folder_start,
            on_complete=on_complete,
            on_error=self._on_sync_error)

    def on_add_source_clicked(self, widget):

        selection = self.sources_tree.get_selection()
        model, tree_iter = selection.get_selected()
        sources = self.backend.load_json("sources").get("sources", [])
        online = next((s for s in sources if s.get("id") == "online"), None)
        selected_path = model.get_value(tree_iter, 2) if tree_iter else None

        is_online = bool(online and tree_iter and (
            (not selected_path and not online.get("path"))
            or (model.get_value(tree_iter, 5)
                and selected_path == online.get("path"))
        ))

        # GTK/GIO en Win32 puede emitir GLib-GIO-CRITICAL al seleccionar la raíz
        # de una unidad (C:\, D:\, etc.) porque el FileChooser consulta un GFileInfo
        # sin standard::type. El contenido del volumen, la navegación y la selección
        # de carpetas siguen siendo correctos; es ruido interno del toolkit y no debe
        # tratarse como un fallo funcional de WMM.
        dialog = Gtk.FileChooserDialog(
            title=_("Select Online Folder") if is_online else _("Select Image Folder"),
            parent=self._callbacks.get('get_parent_window', lambda: None)(),
            action=Gtk.FileChooserAction.SELECT_FOLDER)

        # Identificar el selector de Sources para su presentación Win32.
        dialog.get_style_context().add_class("wmm-sources-folder-chooser")

        # En Windows las unidades ya aparecen en la barra lateral.
        # Ocultar "Otras ubicaciones" evita exponer las acciones de
        # montaje/desmontaje de GTK sin alterar la navegación.
        if os.name == "nt":
            def hide_other_locations(container):
                if isinstance(container, Gtk.PlacesSidebar):
                    container.set_show_other_locations(False)
                    return

                if isinstance(container, Gtk.Container):
                    for child in container.get_children():
                        hide_other_locations(child)

            hide_other_locations(dialog)

        dialog.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
        dialog.add_button(_("Set Online folder") if is_online else _("Add Source"),
            Gtk.ResponseType.OK)

        pictures_dir = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES)
        initial_folder = (online.get("path") if is_online and online.get("path")
            and os.path.isdir(online["path"]) else pictures_dir)
        if initial_folder:
            dialog.set_current_folder(initial_folder)

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
        if not is_online:
            dialog.set_extra_widget(content_box)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            path = dialog.get_filename()
            if path:
                name = os.path.basename(path)
                recursive = check_rec.get_active()
                dialog.destroy()

                if not self._callbacks['begin_sources_operation']():
                    return

                self._callbacks['set_progress_active'](True, _("Scanning") + ": " + name + "...")

                # add_source registra la nueva Source; la materialización física
                # se delega inmediatamente al flujo normal de Sync Library.
                success = (self.handler.set_online_source_path(path) if is_online
                    else self.handler.add_source(name, path, recursive))
                if success:
                    if is_online:
                        self.load_sources_into_treeview()

                    load_thumbnails = self._callbacks.get('load_thumbnails')

                    def on_complete():
                        if load_thumbnails:
                            GLib.idle_add(load_thumbnails, None, True)
                        else:
                            self._callbacks['set_progress_active'](False)
                            self._callbacks['finish_sources_operation']()

                    # Mantener una única operación Sources → Sync → Thumbnails → FIN.
                    self.handler.sync_library(
                        on_progress=self._on_sync_progress,
                        on_folder=self._on_sync_folder_start,
                        on_complete=on_complete,
                        on_error=self._on_sync_error)
                else:
                    self._callbacks['set_progress_active'](False)
                    self._callbacks['finish_sources_operation']()
        else:
            dialog.destroy()

    def on_remove_source_clicked(self, widget):
        selection = self.sources_tree.get_selection()
        model, treeiter = selection.get_selected()
        if treeiter:
            source_name = model[treeiter][1]
            source_path = model[treeiter][2]
            online = next((s
                for s in self.backend.load_json("sources").get("sources", [])
                if s.get("id") == "online"), None)

            # Online conserva su identidad protegida: Eliminar sólo
            # desvincula el directorio, sin tocar sus archivos.
            if (online and model[treeiter][5] and source_path
                    and source_path == online.get("path")):
                dialog = Gtk.MessageDialog(
                    transient_for=self._callbacks.get('get_parent_window', lambda: None)(),
                    flags=0,
                    message_type=Gtk.MessageType.QUESTION,
                    buttons=Gtk.ButtonsType.YES_NO,
                    text=_("Remove Online folder link?"))
                dialog.format_secondary_text(
                    _("This folder and its contents will not be deleted.")
                    + "\n" + source_path)

                response = dialog.run()
                dialog.destroy()

                if response == Gtk.ResponseType.YES:
                    if self.handler.clear_online_source_path():
                        self.load_sources_into_treeview()

                        # Reutilizar la sincronización existente para retirar
                        # las referencias de biblioteca que ya no estén cubiertas.
                        self.on_refresh_sources_clicked(None)
                return

            dialog = Gtk.MessageDialog(
                transient_for=self._callbacks.get('get_parent_window', lambda: None)(),
                flags=0,
                message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.YES_NO,
                text=_("Delete image source?"))
            dialog.format_secondary_text(
                source_name + " " + _("will be removed from your library") + "\n" +
                _("Images will no longer be available"))
            response = dialog.run()
            if response == Gtk.ResponseType.YES:
                # Una raíz se elimina como Source completa; no comparte la
                # semántica diferida de Active/Inactive de una hija.
                if self.handler.remove_source(source_path):
                    # ConfigHandler ya ha resuelto la eliminación lógica y física;
                    # aquí sólo reconstruimos las vistas que dependían de esa Source.
                    self.load_sources_into_treeview()
                    # Refrescar la sección de miniaturas para reflejar los cambios
                    load_thumbnails = self._callbacks.get('load_thumbnails')
                    if load_thumbnails:
                        load_thumbnails()
            dialog.destroy()
