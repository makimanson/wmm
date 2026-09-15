#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

"""
WMM - Wallpaper Multi-Monitor Manager

sources_section.py – Sección de fuentes de imagen del panel de control.
==========================================================
Gestiona el treeview de carpetas, la adición/eliminación de fuentes,
la sincronización de la biblioteca y el escaneado de imágenes.
"""

import os
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib
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
        self.ie = ie
        self.scan_progress = scan_progress
        self.btn_spacer = btn_spacer

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
        self.sources_label = Gtk.Label()
        self.sources_label.set_markup(f"<span weight='bold' size='large'>▼ {_('Image Sources')}</span>")
        self.sources_label.set_halign(Gtk.Align.START)
        self.sources_toggle.add(self.sources_label)
        self.sources_toggle.connect("button-press-event", self._on_sources_toggle)
        vbox.pack_start(self.sources_toggle, False, False, 0)

        # --- Contenido ---
        self.sources_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        vbox.pack_start(self.sources_content, True, True, 0)

        # ScrolledWindow para el treeview
        scrolled = Gtk.ScrolledWindow()
        # scrolled.set_min_content_height(150)
        self.scrolled_sources = scrolled

        # Modelo: [icono, nombre, ruta, active, recursive, is_raiz]
        self.sources_model = Gtk.TreeStore(str, str, str, bool, bool, bool)
        self.sources_tree = Gtk.TreeView(model=self.sources_model)
        self.sources_tree.connect("row-activated", self._on_source_row_activated)

        # Actualizar el botón de eliminar al cambiar la selección
        selection = self.sources_tree.get_selection()
        selection.connect("changed", self._update_delete_button)
        self.sources_model.connect("row-changed", self._update_delete_button)

        # Columna "Source" con icono y texto
        col_name = Gtk.TreeViewColumn(_("Source"))
        ri, rt = Gtk.CellRendererPixbuf(), Gtk.CellRendererText()
        col_name.pack_start(ri, False)
        col_name.pack_start(rt, True)
        col_name.set_cell_data_func(ri, self._render_source_icon)
        col_name.set_cell_data_func(rt, self._render_source_text)
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

        self.refresh_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
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

        arrow = "▼ " if expanded else "▶ "
        self.sources_label.set_markup(f"<span weight='bold' size='large'>{arrow}{_('Image Sources')}</span>")
        self.widget.queue_resize()

    # ==========================================================
    # CARGA Y EXPANSIÓN DEL TREEVIEW
    # ==========================================================
    def load_sources_into_treeview(self):
        # Guardar posición actual del scroll
        vadj = self.scrolled_sources.get_vadjustment()
        saved_value = vadj.get_value()

        # Guardar las rutas expandidas para restaurarlas después de la recarga
        expanded_paths = []
        def save_expanded_paths(model, parent_iter=None):
            if parent_iter is None:
                parent_iter = model.get_iter_first()
            while parent_iter:
                if model.iter_has_child(parent_iter):
                    tree_path = model.get_path(parent_iter)
                    if self.sources_tree.row_expanded(tree_path):
                        expanded_paths.append(tree_path.to_string())
                    # Recursivo para subniveles expandidos
                    child_iter = model.iter_children(parent_iter)
                    while child_iter:
                        save_expanded_paths(model, child_iter)
                        child_iter = model.iter_next(child_iter)
                parent_iter = model.iter_next(parent_iter)
        save_expanded_paths(self.sources_model)

        self.sources_model.clear()
        sources_data = self.backend.load_json("sources").get("sources", [])
        index_data = self.backend.load_json("index")

        # sources.json define las raíces; scan_index aporta la estructura lógica
        # conocida y el estado Active/Inactive de sus hijas.
        for s in sources_data:
            root_path = s.get('path')
            if not root_path or s.get('type') == 'virtual':
                continue

            root_name = s.get('name', os.path.basename(root_path))
            is_recursive = s.get('recursive', False)

            root_active = self.handler.get_index_active(
                root_path, index_data, default=s.get('active', True)
            )

            parent_iter = self.sources_model.append(None, [
                "", root_name, root_path, root_active, is_recursive, True
            ])

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

        log_event("Vista de fuentes reconstruida", origin="PANEL", level="INFO", reason="LIBRARY")

        self.sources_tree.set_model(None)
        self.sources_tree.set_model(self.sources_model)
        self._update_resync_notice()

        # Restaurar posición del scroll
        def restore_scroll():
            vadj.set_value(saved_value)
            return False
        GLib.idle_add(restore_scroll)

        # Restaurar las rutas expandidas tras la recarga
        def restore_expanded_paths():
            for path_str in expanded_paths:
                path = Gtk.TreePath.new_from_string(path_str)
                self.sources_tree.expand_row(path, open_all=False)
            return False
        GLib.idle_add(restore_expanded_paths)

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
        if column != self.col_recursive:
            return False

        tree_iter = self.sources_model.get_iter(path)
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
            origin="PANEL", level="INFO", reason="LIBRARY")

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

    # ==========================================================
    # EVENTOS DEL TREEVIEW
    # ==========================================================
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

    def _on_source_row_activated(self, treeview, path, column):
        model = treeview.get_model()
        iter = model.get_iter(path)
        folder_path = model.get_value(iter, 2)
        if folder_path:
            self.handler.open_file(folder_path)

    def _on_delete_button_clicked(self, widget):
        """Elimina una fuente (padre) o desactiva una subcarpeta (hijo)."""
        selection = self.sources_tree.get_selection()
        model, tree_iter = selection.get_selected()
        if not tree_iter:
            return

        is_raiz = model.get_value(tree_iter, 5)
        path = model.get_value(tree_iter, 2)

        if is_raiz:
            # Es un padre: eliminar la fuente completamente
            self.on_remove_source_clicked(widget)
        else:
            # Es un hijo: desactivarlo inmediatamente
            self.toggle_child_active(widget, model, tree_iter)

    def _update_delete_button(self, *args):
        """Actualiza el icono y el tooltip del botón según el elemento seleccionado."""
        selection = self.sources_tree.get_selection()
        model, tree_iter = selection.get_selected()

        if not tree_iter:
            # Sin selección: icono de papelera inactivo
            self.del_btn.set_image(Gtk.Image.new_from_icon_name("user-trash", Gtk.IconSize.BUTTON))
            self.del_btn.set_tooltip_text(_("Delete image source"))
            self.del_btn.set_sensitive(False)
            return

        is_raiz = model.get_value(tree_iter, 5)  # Columna 5: is_raiz
        is_active = model.get_value(tree_iter, 3)  # Columna 3: active

        if is_raiz:
            # Carpeta padre: papelera
            self.del_btn.set_image(Gtk.Image.new_from_icon_name("user-trash", Gtk.IconSize.BUTTON))
            self.del_btn.set_tooltip_text(_("Delete image source"))
            self.del_btn.set_sensitive(True)
        else:
            # Subcarpeta: ojo con aspa (desactivar) u ojo sin aspa (activar)
            if is_active:
                self.del_btn.set_image(Gtk.Image.new_from_icon_name("view-conceal", Gtk.IconSize.BUTTON))
                self.del_btn.set_tooltip_text(_("Deactivate folder"))
            else:
                self.del_btn.set_image(Gtk.Image.new_from_icon_name("view-reveal", Gtk.IconSize.BUTTON))
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

    def _update_resync_notice(self):
        """Actualiza el aviso global sin competir con la barra de progreso."""
        if self.scan_progress.get_visible():
            self.resync_notice.hide()
            self.btn_spacer.hide()
            return
        # El aviso representa el estado global de Sources, no la última carpeta tocada:
        # permanece activo mientras exista cualquier diferencia lógica/materializada.
        needs_resync = self.handler.needs_sources_resync()
        self.resync_notice.set_visible(needs_resync)
        self.btn_spacer.set_visible(not needs_resync)

    # ==========================================================
    # SINCRONIZACIÓN Y PROGRESO
    # ==========================================================
    def _on_sync_folder_start(self, folder_path):
        pass

    def _on_sync_progress(self, current, total):
        if total > 0:
            fraction = current / total
            self.scan_progress.set_fraction(fraction)
            self.scan_progress.set_text(_("Scanning") + " " + str(current) + "/" + str(total) + " " + _("folders") + "...")

    def show_context_menu(self, path, iter, event):
        is_active = self.sources_model.get_value(iter, 3)
        menu = Gtk.Menu()
        parent_source = self._get_parent_source(path)
        is_root = (path == parent_source.get("path")) if parent_source else True

        if is_root and self.sources_model.get_value(iter, 4):
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
        menu.show_all()
        menu.popup_at_pointer(event)

    def toggle_child_active(self, widget, model, iter):
        path = model.get_value(iter, 2)
        new_state = not model.get_value(iter, 3)
        model.set_value(iter, 3, new_state)

        if self.handler.update_index_active_state(path, new_state):
            log_event(f"Estado cambiado: {path} -> {new_state}",
                origin="PANEL", level="INFO", reason="LIBRARY")
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
            text=_("Delete cache of this folder?")
        )
        dialog.format_secondary_text(
            _("Will be removed from your library") + ":" + "\n" +
            folder_path + "\n" +
            _("Images will no longer be available")
        )
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
                origin="PANEL", level="INFO", reason="LIBRARY")

            load_thumbnails = self._callbacks.get('load_thumbnails')
            if load_thumbnails:
                load_thumbnails(None, True)
            else:
                self._callbacks['set_progress_active'](False)
                self._update_resync_notice()
                self._callbacks['finish_sources_operation']()

            return False

        GLib.idle_add(materialize)

    def on_bulk_toggle(self, widget, parent_path, new_state):
        if self.handler.toggle_all_children(parent_path, new_state):
            log_event(f"Cambio masivo: {parent_path} -> {new_state}",
                origin="PANEL", level="INFO", reason="LIBRARY")
            self.load_sources_into_treeview()
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
            origin="PANEL", level="INFO", reason="LIBRARY")

        if not self._callbacks['begin_sources_operation']():
            return

        self._callbacks['set_progress_active'](True, _("Scanning sources") + "...")

        # Sync y Thumbnails forman una única operación global:
        # Thumbnails recibe el FIN y libera Sources.
        load_thumbnails = self._callbacks.get('load_thumbnails')

        def on_error(message):
            self._callbacks['set_progress_active'](False)
            self._callbacks['finish_sources_operation']()

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
            on_error=on_error
        )

    def on_add_source_clicked(self, widget):
        dialog = Gtk.FileChooserDialog(
            title=_("Select Image Folder"),
            parent=self._callbacks.get('get_parent_window', lambda: None)(),
            action=Gtk.FileChooserAction.SELECT_FOLDER
        )
        dialog.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
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

                if not self._callbacks['begin_sources_operation']():
                    return

                self._callbacks['set_progress_active'](True, _("Scanning") + ": " + name + "...")

                # add_source registra la nueva Source; la materialización física
                # se delega inmediatamente al flujo normal de Sync Library.
                success = self.handler.add_source(name, path, recursive)
                if success:
                    load_thumbnails = self._callbacks.get('load_thumbnails')

                    def on_error(message):
                        self._callbacks['set_progress_active'](False)
                        self._callbacks['finish_sources_operation']()

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
                        on_error=on_error
                    )
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
            dialog = Gtk.MessageDialog(
                transient_for=self._callbacks.get('get_parent_window', lambda: None)(),
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
