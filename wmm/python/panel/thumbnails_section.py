#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

"""
WMM - Wallpaper Multi-Monitor Manager

thumbnails_section.py – Sección de miniaturas del panel de control.
==========================================================
Gestiona Library y Favorites y aloja Online como una sección independiente.

La biblioteca presenta miniaturas horizontales y verticales, permite
gestionarlas como favoritos y arrastrarlas a los monitores virtuales.
La selección de Sources sólo filtra su presentación: no modifica las
fuentes, el índice ni la caché de imágenes.

Online delega sus búsquedas, selección y miniaturas en OnlineSection.
Esa vista no participa en Sources ni en la sincronización local.

La recarga local puede ser independiente o formar parte de la operación
global Sources → Sync → Thumbnails → FIN.
"""

import os
import base64
import hashlib
import time
import queue
import threading
import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Gio, Pango
from panel.online_section import OnlineSection
from online_wallpapers import get_online_source_page, get_online_provider_identity
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
            right_col:    Gtk.Box donde se empaqueta la sección.
            scan_progress: Gtk.ProgressBar compartida con SourcesSection.
            btn_spacer:    Argumento de compatibilidad con el Panel;
                           su gestión corresponde a SourcesSection.

        Los callbacks se asignan mediante set_callbacks() después de
        construir las secciones implicadas del Panel.
        """
        self.handler = handler
        self.backend = backend
        self._callbacks = {}  # Se configurarán después con set_callbacks()

        # Widgets de progreso (compartidos con SourcesSection)
        self.scan_progress = scan_progress

        # Estado interno
        self._thumbnails_loading = False
        self._first_h_item = None
        self._first_v_item = None
        self._progress_h_list = []
        self._progress_v_list = []
        self._favorite_paths = set()
        self._thumbnail_items = {}
        self._online_origins = {}

        # El filtro de Sources es sólo visual. None equivale a "All";
        # una cadena vacía representa una fuente sin directorio.
        self._source_filter_prefix = None
        self._thumbnail_filter_paths = {}

        # H/V comparten Library: conservar la última navegación elegida.
        # La sincronización visual nunca debe provocar otra navegación.
        self._library_nav_orientation = "h"
        self._nav_syncing = False

        # Referencia de navegación de Library durante su reconstrucción.
        self._library_navigation = None

        # Restauración pendiente hasta que GTK asigne la nueva geometría.
        self._library_restore_handler = None

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

    @property
    def _parent_window(self):
        """Accede al Panel mediante el callback ya establecido."""
        cb = self._callbacks.get('get_parent_window')
        return cb() if cb else None

    # ==========================================================
    # CONSTRUCCIÓN DE LA INTERFAZ
    # ==========================================================
    def _build(self):
        """Construye y devuelve el widget principal de la sección."""
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        vbox.set_margin_top(4)

        # ----------------------------------------------------------
        # CABECERA: Etiqueta + Navegación H/V + Botón de refresco
        # ----------------------------------------------------------
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        # Identificar la cabecera común para diferenciar su fondo en Win32.
        header_box.get_style_context().add_class("wmm-thumbnails-header")

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
        self.btn_h = Gtk.RadioButton.new_from_widget(None)
        self.btn_h.set_mode(False)
        label_h = Gtk.Label()
        label_h.set_markup("<b>" + _("Horizontal") + "</b>")
        self.btn_h.add(label_h)
        self.btn_h.set_relief(Gtk.ReliefStyle.NONE)
        self.btn_h.connect("clicked", self._scroll_to_h)
        nav_box.pack_start(self.btn_h, False, False, 0)

        # Botón Vertical
        self.btn_v = Gtk.RadioButton.new_from_widget(self.btn_h)
        self.btn_v.set_mode(False)
        label_v = Gtk.Label()
        label_v.set_markup("<b>" + _("Vertical") + "</b>")
        self.btn_v.add(label_v)
        self.btn_v.set_relief(Gtk.ReliefStyle.NONE)
        self.btn_v.connect("clicked", self._scroll_to_v)
        nav_box.pack_start(self.btn_v, False, False, 0)

        # Botón Favorites
        self.btn_favorites = Gtk.RadioButton.new_from_widget(self.btn_h)
        self.btn_favorites.set_mode(False)
        label_favorites = Gtk.Label()
        label_favorites.set_markup("<b>" + _("Favorites") + "</b>")
        self.btn_favorites.add(label_favorites)
        self.btn_favorites.set_relief(Gtk.ReliefStyle.NONE)
        self.btn_favorites.connect("clicked", self._show_favorites)
        nav_box.pack_start(self.btn_favorites, False, False, 0)

        # Acceso a la galería online, independiente de Sources y Favoritos.
        self.btn_online = Gtk.RadioButton.new_from_widget(self.btn_h)
        self.btn_online.set_mode(False)
        label_online = Gtk.Label()
        label_online.set_markup("<b>" + _("Online") + "</b>")
        self.btn_online.add(label_online)
        self.btn_online.set_relief(Gtk.ReliefStyle.NONE)
        self.btn_online.connect("clicked", self._show_online)
        nav_box.pack_start(self.btn_online, False, False, 0)

        # --- Thumbnails navigation style ---
        # Los RadioButton sin indicador se representan como button.radio.
        # La clase permite adaptar su aspecto sin afectar a otros controles.
        for button in (self.btn_h, self.btn_v, self.btn_favorites, self.btn_online):
            button.get_style_context().add_class("wmm-thumbnail-nav")

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

        # Superficie propia para cubrir las áreas sin miniaturas.
        self.thumbnails_stack.get_style_context().add_class("wmm-thumbnail-stack")

        # Sources también puede cambiar la página sin usar la botonera.
        self.thumbnails_stack.connect("notify::visible-child-name",
                                      self._on_thumbnails_view_changed)

        # Vista normal H/V
        self.thumbnails_scrolled = Gtk.ScrolledWindow()
        self.thumbnails_flowbox = Gtk.FlowBox()
        self.thumbnails_flowbox.set_homogeneous(False)
        self.thumbnails_flowbox.set_row_spacing(2)
        self.thumbnails_flowbox.set_column_spacing(2)
        self.thumbnails_flowbox.set_max_children_per_line(128)
        self.thumbnails_flowbox.set_valign(Gtk.Align.START)
        self.thumbnails_flowbox.set_filter_func(self._filter_source_thumbnail)
        self.thumbnails_scrolled.add(self.thumbnails_flowbox)

        # Los gestos del usuario invalidan cualquier restauración pendiente.
        self.thumbnails_scrolled.connect(
            "scroll-event", self._on_library_user_navigation)
        self.thumbnails_flowbox.connect(
            "key-press-event", self._on_library_user_navigation)

        scrollbar = self.thumbnails_scrolled.get_vscrollbar()
        scrollbar.connect("change-value", self._on_library_user_navigation)
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

        # Online posee sus controles y búsquedas; aquí sólo se aloja su vista.
        self.online_section = OnlineSection(self.handler)
        self.thumbnails_stack.add_named(self.online_section.widget, "online")

        self.thumbnails_stack.set_visible_child_name("library")
        vbox.pack_start(self.thumbnails_stack, True, True, 0)

        return vbox

    def _on_thumbnails_view_changed(self, stack, pspec):
        """Sincroniza el indicador con la vista real sin navegar de nuevo."""
        page = stack.get_visible_child_name()
        target = {
            "library": self.btn_h if self._library_nav_orientation == "h" else self.btn_v,
            "favorites": self.btn_favorites,
            "online": self.btn_online,
        }.get(page)

        if target is not None and not target.get_active():
            self._nav_syncing = True
            try:
                target.set_active(True)
            finally:
                self._nav_syncing = False

    # ==========================================================
    # FILTRADO VISUAL DESDE SOURCES
    # ==========================================================
    def _filter_source_thumbnail(self, child, *args):
        """Filtra la galería y muestra su mensaje cuando no hay coincidencias."""
        prefix = self._source_filter_prefix
        image_path = self._thumbnail_filter_paths.get(child.get_child())

        # El mensaje no tiene ruta de imagen. Sólo debe mostrarse
        # cuando ninguna miniatura pertenece a la fuente seleccionada.
        if image_path is None:
            if prefix is None:
                return not self._thumbnail_filter_paths
            return not prefix or not any(
                path.startswith(prefix) for path in self._thumbnail_filter_paths.values())

        if prefix is None:
            return True

        return bool(prefix and image_path.startswith(prefix))

    def on_source_selection_changed(self, selection):
        """Aplica la carpeta seleccionada en Sources a la galería local."""
        model, tree_iter = selection.get_selected()
        selected_path = model.get_value(tree_iter, 2) if tree_iter else None

        if selected_path in (None, "__all__"):
            self._source_filter_prefix = None
        elif not selected_path:
            self._source_filter_prefix = ""
        else:
            # Incluir el separador impide confundir carpetas hermanas
            # como Photos y Photos_OLD.
            folder = os.path.normcase(os.path.abspath(selected_path))
            self._source_filter_prefix = folder.rstrip(os.sep) + os.sep

        self.thumbnails_flowbox.invalidate_filter()

        # La reconstrucción de Sources debe actualizar el filtro,
        # pero no modificar la vista elegida por el usuario.
        if tree_iter and not self._callbacks['is_sources_tree_rebuilding']():
            self._on_library_user_navigation()
            self.thumbnails_stack.set_visible_child_name("library")

    def on_source_row_pressed(self, treeview, event):
        """Vuelve a Library al pulsar una fuente que ya estaba seleccionada."""
        if event.button != 1 or event.type != Gdk.EventType.BUTTON_PRESS:
            return False

        hit = treeview.get_path_at_pos(int(event.x), int(event.y))
        if not hit or hit[1] != treeview.get_column(0):
            return False

        # 'changed' no se emite al pulsar de nuevo la misma fila.
        # Aquí sólo navegamos: el filtro ya corresponde a esa selección.
        if treeview.get_selection().path_is_selected(hit[0]):
            self.thumbnails_stack.set_visible_child_name("library")

        return False

    # ==========================================================
    # CARGA DE MINIATURAS
    # ==========================================================
    def _capture_library_navigation(self):
        """Conserva la selección y la referencia visible antes de reconstruir Library."""
        vadj = self.thumbnails_scrolled.get_vadjustment()
        scroll_y = vadj.get_value()

        selected = self.thumbnails_flowbox.get_selected_children()
        selected_path = (
            self._thumbnail_filter_paths.get(selected[0].get_child())
            if selected else None
        )

        visible = [
            child for child in self.thumbnails_flowbox.get_children()
            if child.get_child_visible()
            and child.get_child() in self._thumbnail_filter_paths
        ]

        anchor = next((
            child for child in visible
            if child.get_allocation().y + child.get_allocation().height > scroll_y
        ), None)

        self._library_navigation = {
            "selected_path": selected_path,
            "anchor_path": (
                self._thumbnail_filter_paths.get(anchor.get_child())
                if anchor else None
            ),
            "anchor_offset": (
                scroll_y - anchor.get_allocation().y if anchor else 0
            ),
            "anchor_index": visible.index(anchor) if anchor else 0,
            "scroll_y": scroll_y,
        }

    def _queue_library_navigation_restore(self):
        """Espera a la geometría final antes de restaurar Library."""
        if self._library_restore_handler is not None:
            self.thumbnails_flowbox.disconnect(self._library_restore_handler)
            self._library_restore_handler = None

        # La navegación que debemos preservar es la de la vista activa.
        # Favorites y Online conservan sus propias galerías.
        if self.thumbnails_stack.get_visible_child_name() != "library":
            self._library_navigation = None
            return

        self._library_restore_handler = self.thumbnails_flowbox.connect(
            "size-allocate", self._on_library_size_allocate)

    def _on_library_size_allocate(self, widget, allocation):
        """La nueva distribución está disponible: restaurar una sola vez."""
        widget.disconnect(self._library_restore_handler)
        self._library_restore_handler = None
        GLib.idle_add(self._restore_library_navigation)

    def _restore_library_navigation(self):
        """Recupera selección y posición sin cambiar el foco ni la vista."""
        state = self._library_navigation
        self._library_navigation = None

        if not state or self.thumbnails_stack.get_visible_child_name() != "library":
            return False

        visible = [
            child for child in self.thumbnails_flowbox.get_children()
            if child.get_child_visible()
            and child.get_child() in self._thumbnail_filter_paths
        ]

        by_path = {
            self._thumbnail_filter_paths[child.get_child()]: child
            for child in visible
        }

        # Recuperar la selección sólo si la imagen sigue disponible.
        selected = by_path.get(state["selected_path"])
        if selected:
            self.thumbnails_flowbox.select_child(selected)

        # Priorizar la misma imagen visible, aunque haya cambiado de fila.
        anchor = by_path.get(state["anchor_path"])

        # Si desapareció, recuperar la posición ordinal más próxima.
        if anchor is None and visible:
            anchor = visible[min(state["anchor_index"], len(visible) - 1)]

        vadj = self.thumbnails_scrolled.get_vadjustment()

        position = (
            anchor.get_allocation().y + state["anchor_offset"]
            if anchor else state["scroll_y"]
        )

        # Nunca solicitar un desplazamiento fuera del rango disponible.
        lower = vadj.get_lower()
        upper = max(lower, vadj.get_upper() - vadj.get_page_size())
        vadj.set_value(max(lower, min(position, upper)))

        return False

    def _load_thumbnails(self, widget=None, inherited_operation=False):
        """PREPARE: fijar el orden y abrir la operación de Thumbnails."""
        if self._thumbnails_loading:
            return False

        if inherited_operation:
            if not self._is_sources_operation_active():
                log_event(
                    "Thumbnails recibió una operación heredada sin lifecycle activo",
                    origin="THUMB_SECT", level="ERROR", reason="LIBRARY")
                return False
        elif not self._begin_sources_operation():
            return False

        self._thumbnails_loading = True
        log_event("Carga de miniaturas iniciada",
            origin="THUMB_SECT", level="INFO", reason="LIBRARY")

        self._capture_library_navigation()
        self._first_h_item = None
        self._first_v_item = None
        self._thumbnail_items.clear()
        self._thumbnail_filter_paths.clear()
        origins = self.handler.load_json("online_origins")
        self._online_origins = origins if isinstance(origins, dict) else {}

        for child in self.thumbnails_flowbox.get_children():
            self.thumbnails_flowbox.remove(child)

        h_list, v_list = self.handler.get_flat_lists()
        total = len(h_list) + len(v_list)
        self._progress_h_list = h_list
        self._progress_v_list = v_list

        if total == 0:
            self._library_navigation = None
            self._thumbnails_loading = False
            self._set_progress_active(False)
            self.thumbnails_flowbox.add(
                Gtk.Label(label=_("No images found.")))
            self.thumbnails_flowbox.show_all()
            self._finish_sources_operation()
            return False

        # Consultar una sola vez los JPEG existentes.
        profile_start = time.perf_counter()
        cached = {}

        try:
            with os.scandir(self.handler.thumbnails_dir) as entries:
                for entry in entries:
                    if len(entry.name) != 36 or not entry.name.endswith(".jpg"):
                        continue
                    try:
                        cached[entry.name] = entry.stat().st_mtime_ns
                    except OSError:
                        continue
        except OSError as error:
            log_event(
                f"No se pudo consultar la caché de miniaturas: {error}",
                origin="THUMB_SECT", level="WARN", reason="LIBRARY")

        # Orden inmutable: H antes que V.
        # JPEG nuevos primero, ordenados por fecha del original.
        # JPEG existentes después, ordenados por fecha de miniatura.
        # El worker publicará en este orden y GTK sólo añadirá al final.
        plan = []
        missing_count = 0

        for images, orient in ((h_list, "h"), (v_list, "v")):
            missing = []
            existing = []

            for ordinal, img in enumerate(images):
                img_path = img[0]
                thumb_name = hashlib.md5(
                    img_path.encode()).hexdigest() + ".jpg"
                thumb_mtime = cached.get(thumb_name)

                if thumb_mtime is None:
                    missing_count += 1
                    original_mtime = img[3] if len(img) > 3 else 0
                    missing.append((
                        original_mtime or 0, ordinal,
                        img_path, orient, None))
                else:
                    existing.append((
                        thumb_mtime, ordinal, img_path, orient,
                        os.path.join(
                            self.handler.thumbnails_dir, thumb_name)))

            missing.sort(key=lambda entry: (-entry[0], entry[1]))
            existing.sort(key=lambda entry: (-entry[0], entry[1]))
            plan.extend(entry[2:] for entry in missing + existing)

        self._thumbnail_sources = self.handler.load_json(
            "sources").get("sources", [])
        self._thumbnail_index = self.handler.load_json("index")

        fav_list = self.backend.load_json("bookmarks_single")
        self._favorite_paths.clear()
        self._favorite_paths.update(
            entry[0] for entry in fav_list if entry)

        # Única cola y único consumidor GTK.
        self._thumbnail_ready = queue.SimpleQueue()
        self._thumbnail_ready_lock = threading.Lock()
        self._thumbnail_drain_scheduled = False
        self._thumbnail_worker_finished = False

        self._thumbnail_total = total
        self._thumbnail_processed = 0
        self._thumbnail_shown = 0
        self._thumbnail_first_visible = None
        self._thumbnail_ui_seconds = 0.0
        self._thumbnail_started_at = time.perf_counter()

        log_event(
            f"Miniaturas: {total - missing_count} reutilizadas; "
            f"{missing_count} pendientes; "
            f"preparación={time.perf_counter() - profile_start:.3f}s",
            origin="THUMB_SECT", level="INFO", reason="LIBRARY")

        # El progreso también informa cuando todos los JPEG están en caché.
        self._set_progress_active(True, _("Thumbnails") + "...")

        threading.Thread(
            target=self._generate_thumbnails_worker,
            args=(tuple(plan),),
            name="WMM-Thumbnails",
            daemon=True).start()

        return False

    def _generate_thumbnails_worker(self, plan):
        """WORK: generar y publicar resultados sin acceder a GTK."""
        try:
            for img_path, orient, thumb_path in plan:
                if thumb_path is None:
                    thumb_path = self.handler.get_thumbnail(img_path)

                self._enqueue_thumbnail_result(
                    (img_path, orient, thumb_path))

        except Exception as error:
            log_event(
                f"Fallo en generación de thumbnails: {error}",
                origin="THUMB_SECT", level="ERROR", reason="LIBRARY")
        finally:
            # El terminal siempre sucede después del último resultado.
            self._enqueue_thumbnail_result(None)

    def _enqueue_thumbnail_result(self, result):
        """Publicar una ruta y despertar un único consumidor."""
        self._thumbnail_ready.put(result)

        with self._thumbnail_ready_lock:
            if self._thumbnail_drain_scheduled:
                return
            self._thumbnail_drain_scheduled = True

        GLib.idle_add(self._start_thumbnail_drain)

    def _start_thumbnail_drain(self):
        """Registrar el consumidor en el hilo principal GTK."""
        self.widget.add_tick_callback(self._drain_thumbnail_results)
        return False

    def _drain_thumbnail_results(self, widget, frame_clock):
        """MAIN: incorporar widgets sin reorganizar los anteriores."""
        deadline = time.perf_counter() + 0.003
        processed = 0

        while processed < 8 and time.perf_counter() < deadline:
            try:
                result = self._thumbnail_ready.get_nowait()
            except queue.Empty:
                break

            if result is None:
                self._thumbnail_worker_finished = True
                continue

            try:
                self._present_thumbnail_result(*result)
            except Exception as error:
                log_event(
                    f"Error mostrando miniatura {result[0]}: {error}",
                    origin="THUMB_SECT", level="ERROR", reason="LIBRARY")

            processed += 1
            self._thumbnail_processed += 1

        if processed and self.scan_progress:
            self.scan_progress.set_fraction(
                self._thumbnail_processed / self._thumbnail_total)
            self.scan_progress.set_text(
                _("Thumbnails") +
                f" {self._thumbnail_processed}/{self._thumbnail_total}")

        # Restaurar una recarga previa sólo una vez.
        # Cualquier navegación del usuario cancela esta restauración.
        if (self._library_navigation is not None
                and self._library_restore_handler is None):
            path = self._library_navigation["anchor_path"]
            if path is None or path in self._thumbnail_items:
                self._queue_library_navigation_restore()

        with self._thumbnail_ready_lock:
            if not self._thumbnail_ready.empty():
                return True
            self._thumbnail_drain_scheduled = False

        if self._thumbnail_worker_finished:
            self._finish_thumbnail_presentation()

        return False

    def _present_thumbnail_result(self, img_path, orient, thumb_path):
        """MAIN: añadir al final sin mover las miniaturas existentes."""
        if not thumb_path or img_path in self._thumbnail_items:
            return

        if not self.handler._is_path_active(
                img_path, self._thumbnail_sources, self._thumbnail_index):
            return

        start = time.perf_counter()

        child = self._add_thumbnail_item(
            img_path, self._favorite_paths,
            self.thumbnails_flowbox, thumb_path)

        if orient == "h" and self._first_h_item is None:
            self._first_h_item = child
        elif orient == "v" and self._first_v_item is None:
            self._first_v_item = child

        child.show_all()

        if self._thumbnail_first_visible is None:
            self._thumbnail_first_visible = (
                time.perf_counter() - self._thumbnail_started_at)

        self._thumbnail_shown += 1
        self._thumbnail_ui_seconds += time.perf_counter() - start

    def _finish_thumbnail_presentation(self):
        """COMMIT: cerrar únicamente cuando WORK y la cola terminaron."""
        try:
            placeholder = Gtk.Label(label=_("No images found."))
            self.thumbnails_flowbox.add(placeholder)
            placeholder.show_all()

            # FIN no ejecuta una nueva navegación.
            self._library_navigation = None

            if self._library_restore_handler is not None:
                self.thumbnails_flowbox.disconnect(
                    self._library_restore_handler)
                self._library_restore_handler = None

        finally:
            self._thumbnails_loading = False
            self._set_progress_active(False)
            self._finish_sources_operation()

        first = (self._thumbnail_first_visible
            if self._thumbnail_first_visible is not None else 0)

        log_event(
            f"Thumbnails cargados: "
            f"{len(self._progress_h_list)}H / {len(self._progress_v_list)}V; "
            f"visibles={self._thumbnail_shown}; "
            f"primera={first:.3f}s; "
            f"GTK={self._thumbnail_ui_seconds:.3f}s; "
            f"total={time.perf_counter() - self._thumbnail_started_at:.3f}s",
            origin="THUMB_SECT", level="INFO", reason="LIBRARY")

    def _on_library_website_tooltip(self, button, x, y, keyboard_mode, tooltip):
        """Responde a GTK con la procedencia publicada por el botón."""
        tooltip.set_text(button.get_tooltip_text() or _("Website"))
        return True

    def _open_library_source_page(self, button, page_url):
        """Abre la página informativa registrada para una imagen local."""
        try:
            # Win32 necesita un contexto explícito para lanzar el navegador.
            # Linux conserva el contexto predeterminado.
            context = Gio.AppLaunchContext() if os.name == "nt" else None
            Gio.AppInfo.launch_default_for_uri(page_url, context)
        except GLib.Error as error:
            log_event(f"No se pudo abrir procedencia Online: {error}",
                origin="THUMB_SECT", level="WARN", reason="LIBRARY")

    def _on_thumbnail_overlay_tooltip(self, overlay, x, y, keyboard_mode,
                                     tooltip, img_path, source_button):
        """Un único tooltip distingue la imagen de su enlace Website."""
        if source_button is not None and not keyboard_mode:
            position = source_button.translate_coordinates(overlay, 0, 0)

            if position is not None:
                bx, by = position
                width = source_button.get_allocated_width()
                height = source_button.get_allocated_height()

                if bx <= x < bx + width and by <= y < by + height:
                    tooltip.set_text(source_button.get_tooltip_text() or _("Website"))
                    return True

        tooltip.set_text(img_path)
        return True

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
        img.set_size_request(-1, self.handler.thumbnail_max_height)

        overlay = Gtk.Overlay()
        overlay.add(img)
        source_button = None
        overlay.set_tooltip_text(img_path)

        # Library muestra el enlace sólo cuando conserva una procedencia
        # registrada. No intenta reconstruirla a partir del nombre.
        if flowbox is self.thumbnails_flowbox:
            key = os.path.normcase(os.path.abspath(img_path))
            origin = self._online_origins.get(key)
            page_url = get_online_source_page(origin)

            if page_url:
                source_button = Gtk.Button.new_from_icon_name(
                    "help-about-symbolic", Gtk.IconSize.LARGE_TOOLBAR)
                source_button.get_style_context().add_class("wmm-online-source-link")

                # La procedencia registrada determina el nombre mostrado.
                # Si el proveedor ya no existe, conservar el tooltip genérico.
                identity = get_online_provider_identity(origin.get("provider"))
                source_button.set_tooltip_text(_("View on") + " " + identity["name"]
                    if identity else _("Website"))

                # Diagnóstico: proporcionar el tooltip desde la consulta GTK.
                source_button.connect("query-tooltip",
                    self._on_library_website_tooltip)

                source_button.set_relief(Gtk.ReliefStyle.NONE)
                source_button.set_halign(Gtk.Align.END)
                source_button.set_valign(Gtk.Align.END)
                source_button.set_margin_end(2)
                source_button.set_margin_bottom(2)
                source_button.connect("clicked", self._open_library_source_page, page_url)
                overlay.add_overlay(source_button)

        # El Overlay resuelve ambos tooltips en la misma jerarquía GTK.
        # Evita depender de qué hijo selecciona GTK al mostrarlo.
        overlay.set_has_tooltip(True)
        overlay.connect("query-tooltip", self._on_thumbnail_overlay_tooltip,
            img_path, source_button)

        item_box.pack_start(overlay, False, False, 0)

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
        event_box.drag_source_set(Gdk.ModifierType.BUTTON1_MASK,
            [Gtk.TargetEntry.new("text/plain", Gtk.TargetFlags.SAME_APP, 0)],
            Gdk.DragAction.COPY)
        event_box.connect("drag-data-get", self._on_thumbnail_drag_data_get, img_path)
        event_box.connect("drag-begin", self._on_thumbnail_drag_begin, img_path)
        event_box.connect("drag-end", self._on_thumbnail_drag_end, img_path)

        # El filtro necesita la ruta del original, nunca la del JPEG de caché.
        if flowbox is self.thumbnails_flowbox:
            self._thumbnail_filter_paths[event_box] = os.path.normcase(os.path.abspath(img_path))

        flowbox.add(event_box)

        return event_box.get_parent()

    def _on_library_user_navigation(self, *args):
        """La navegación del usuario cancela restauraciones pendientes."""
        self._library_navigation = None

        if self._library_restore_handler is not None:
            self.thumbnails_flowbox.disconnect(
                self._library_restore_handler)
            self._library_restore_handler = None

        return False

    # ==========================================================
    # NAVEGACIÓN H/V
    # ==========================================================
    def _scroll_thumbnail_to_top(self, child):
        """Selecciona una miniatura y alinea su fila con el borde superior."""
        self.thumbnails_flowbox.select_child(child)
        child.grab_focus()

        # La posición Y pertenece al FlowBox: todas las miniaturas
        # de una misma fila comparten esta coordenada.
        vadj = self.thumbnails_scrolled.get_vadjustment()
        vadj.set_value(child.get_allocation().y)

    def _scroll_to_h(self, widget):
        """Navega hasta la primera miniatura horizontal visible."""
        if self._nav_syncing or not widget.get_active():
            return
        self._library_nav_orientation = "h"
        self._on_library_user_navigation()
        self.thumbnails_stack.set_visible_child_name("library")

        if not self._first_h_item:
            return

        # Las horizontales preceden a las verticales. El filtro de Sources
        # puede ocultar la primera H sin eliminarla del FlowBox.
        for child in self.thumbnails_flowbox.get_children():
            if child == self._first_v_item:
                break

            if child.get_child_visible():
                self._scroll_thumbnail_to_top(child)
                return

    def _scroll_to_v(self, widget):
        """Navega hasta la primera miniatura vertical visible."""
        if self._nav_syncing or not widget.get_active():
            return
        self._library_nav_orientation = "v"
        self._on_library_user_navigation()
        self.thumbnails_stack.set_visible_child_name("library")

        if not self._first_v_item:
            return

        # La primera V marca el límite entre orientaciones incluso
        # cuando esa miniatura está oculta por el filtro de Sources.
        in_verticals = False

        for child in self.thumbnails_flowbox.get_children():
            if child == self._first_v_item:
                in_verticals = True

            if in_verticals and child.get_child_visible():
                self._scroll_thumbnail_to_top(child)
                return

    # ==========================================================
    # VISTA DE FAVORITOS
    # ==========================================================
    def _load_favorites_view(self):
        """Reconstruye la vista de miniaturas favoritas desde bookmarks_single_list.json."""
        for child in self.favorites_flowbox.get_children():
            self.favorites_flowbox.remove(child)

        fav_list = self.backend.load_json("bookmarks_single")
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
        log_event(f"Vista de favoritos cargada: {visible_count} imágenes",
            origin="THUMB_SECT", level="INFO", reason="BOOKMARK")

    def _show_favorites(self, widget):
        """Muestra la galería específica de imágenes favoritas."""
        if self._nav_syncing or not widget.get_active():
            return
        self._load_favorites_view()
        self.thumbnails_stack.set_visible_child_name("favorites")

    def _show_online(self, widget):
        """Muestra Online respetando la decisión de lectura responsable."""
        if self._nav_syncing or not widget.get_active():
            return

        self.online_section.prepare_open()
        self.thumbnails_stack.set_visible_child_name("online")

    # ==========================================================
    # EVENTOS DE RATÓN SOBRE MINIATURAS
    # ==========================================================
    def _on_thumbnail_click(self, widget, event, img_path, favorites):
        """Clic derecho: menú contextual para añadir/eliminar favoritos."""
        if event.button != 3:
            return False

        menu = self._parent_window.create_context_menu()

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
