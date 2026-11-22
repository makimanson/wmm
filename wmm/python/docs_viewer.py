#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

"""
WMM - Wallpaper Multi-Monitor Manager

docs_viewer.py - Visor común de documentación Markdown.
=======================================================
Carga un documento Markdown recibido por parámetro, resuelve automáticamente
su variante de idioma y genera un índice de navegación a partir de sus títulos.

El visor es deliberadamente independiente del engine:
sólo utiliza PlatformManager para consumir capacidades propias del sistema operativo.
"""

# ==========================================================
# IMPORTS DE LIBRERÍA ESTÁNDAR
# ==========================================================
import hashlib
import json
import os
import re
import sys

# ==========================================================
# RUTAS Y RESOLUCIÓN DEL DOCUMENTO
# ==========================================================
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# ==========================================================
# IMPORTS DE TERCEROS (GTK)
# ==========================================================
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Pango, GLib

# ==========================================================
# IMPORTS DE MÓDULOS DEL PROYECTO
# ==========================================================
from wmm_platform.core import PlatformManager
from debug_logger import set_cache_dir
from i18n import _, initialize

def _resolve_base_path(argument):
    """Resuelve rutas relativas respecto a la raíz de WMM, no al CWD."""
    path = os.path.expanduser(argument)
    if not os.path.isabs(path):
        path = os.path.join(_PROJECT_ROOT, path)
    return os.path.abspath(path)

def _get_session_language():
    """Obtiene el código corto de idioma de la sesión."""
    raw = (os.environ.get("LANGUAGE") or os.environ.get("LC_ALL")
        or os.environ.get("LC_MESSAGES") or os.environ.get("LANG") or "en")
    raw = raw.split(":", 1)[0].split(".", 1)[0]
    return raw.split("_", 1)[0].lower() or "en"

def _resolve_document(base_path):
    """Prefiere nombre_<idioma>.ext y usa el documento base como fallback."""
    root, ext = os.path.splitext(base_path)
    localized_path = f"{root}_{_get_session_language()}{ext}"
    return localized_path if os.path.isfile(localized_path) else base_path

def _build_settings_key(base_path):
    """Deriva una clave estable y legible de la ruta base del documento."""
    relative_path = os.path.relpath(base_path, _PROJECT_ROOT)
    if relative_path == ".." or relative_path.startswith(".." + os.sep):
        relative_path = os.path.abspath(base_path)

    stem = os.path.splitext(relative_path)[0]
    safe_name = re.sub(r"[^A-Za-z0-9]+", "_", stem).strip("_").lower() or "document"
    return f"docs_viewer_{safe_name}"

def _build_application_id(base_path):
    """Una aplicación por documento permite coexistencia sin duplicar el mismo visor."""
    normalized = os.path.normcase(os.path.abspath(base_path))
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]
    return f"org.maki.wmm.DocsViewer.d{digest}"

def _set_process_name(base_path):
    """Asigna una identidad visible al proceso según el documento base."""
    stem = os.path.basename(base_path).split(".", 1)[0].upper()
    names = {"HELP": "WMM Help", "CHANGELOG": "WMM Changelog", "README": "WMM README", "LICENSE": "WMM LICENSE"}
    name = names.get(stem, f"WMM {stem.title()}")

    try:
        with open("/proc/self/comm", "w", encoding="utf-8") as file:
            file.write(name[:15])
    except OSError:
        pass

# ==========================================================
# VISOR DE DOCUMENTACIÓN
# ==========================================================
class DocsViewer(Gtk.Window):
    """Ventana común con índice de navegación y contenido Markdown."""

    def __init__(self, base_path, settings_path, parent=None):
        self._base_path = base_path
        self._document_path = _resolve_document(base_path)
        self._document_name = os.path.splitext(os.path.basename(base_path))[0]
        self._settings_key = _build_settings_key(base_path)
        self._settings_path = settings_path

        super().__init__(title=f"WMM - {self._document_name}")

        # ----------------------------------------------------------
        # PREFERENCIAS DEL VISOR
        # ----------------------------------------------------------
        self._viewer_state = self._load_viewer_state()
        self.set_default_size(*self._viewer_state["window_size"])

        self.set_position(Gtk.WindowPosition.CENTER)
        if parent:
            self.set_transient_for(parent)

        self.set_icon_name("text-x-generic")

        # Guardar únicamente al cerrar, cuando GTK conserva la geometría real.
        self.connect("delete-event", self._on_delete_event)

        # ----------------------------------------------------------
        # DEFINICIÓN DE WIDGETS
        # ----------------------------------------------------------

        # --- PANEL IZQUIERDO: ÍNDICE ---
        left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        left_box.set_border_width(6)

        self.index_label = Gtk.Label()
        self.index_label.set_markup(f"<b>{self._document_name}</b>")
        self.index_label.set_halign(Gtk.Align.START)
        left_box.pack_start(self.index_label, False, False, 4)

        scrolled_index = Gtk.ScrolledWindow()
        scrolled_index.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        self.index_store = Gtk.TreeStore(str, int, str)
        self.index_tree = Gtk.TreeView(model=self.index_store)
        self.index_tree.set_headers_visible(False)

        renderer_title = Gtk.CellRendererText()
        column_title = Gtk.TreeViewColumn("", renderer_title, text=0)
        column_title.set_expand(True)
        self.index_tree.append_column(column_title)

        renderer_marker = Gtk.CellRendererText()
        renderer_marker.set_property("xalign", 1.0)
        column_marker = Gtk.TreeViewColumn("", renderer_marker, text=2)
        column_marker.set_min_width(25)
        column_marker.set_max_width(30)
        self.index_tree.append_column(column_marker)

        self.index_tree.connect("cursor-changed", self._on_index_cursor_changed)

        scrolled_index.add(self.index_tree)
        left_box.pack_start(scrolled_index, True, True, 0)

        # --- FUENTE DEL DOCUMENTO ---
        # El índice conserva la zona flexible; el selector queda abajo
        # sin añadir altura ni barras al formulario.
        font_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        font_label = Gtk.Label(label=_("Font and size") + ":", xalign=0)
        font_box.pack_start(font_label, False, False, 0)

        self.font_button = Gtk.FontButton()
        self.font_button.set_use_font(True)
        self.font_button.set_use_size(False)

        # Mantener el selector a la izquierda, sin estirarlo
        # cuando el usuario amplía la columna del índice.
        self.font_button.set_halign(Gtk.Align.START)
        self.font_button.set_hexpand(False)
        self.font_button.set_size_request(180, -1)

        self.font_button.set_font(self._viewer_state["font"])
        self.font_button.connect("font-set", self._on_font_changed)
        self.font_button.connect("notify::font", self._truncate_font_label)
        self._truncate_font_label(self.font_button, None)

        font_box.pack_start(self.font_button, False, False, 0)
        left_box.pack_start(font_box, False, False, 0)

        # --- PANEL DERECHO: CONTENIDO ---
        right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        right_box.set_border_width(6)

        scrolled_content = Gtk.ScrolledWindow()
        scrolled_content.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        self.content_view = Gtk.TextView()
        self.content_view.set_editable(False)
        self.content_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.content_view.set_left_margin(10)
        self.content_view.set_right_margin(10)

        # El CSS compartido conserva los colores del tema GTK
        # para el área interna del visor.
        content_context = self.content_view.get_style_context()
        content_context.add_class("view")
        content_context.add_class("wmm-docs-view")

        # Aplicar la preferencia persistida al documento y su índice.
        self._apply_document_font(self._viewer_state["font"])

        self.textbuffer = self.content_view.get_buffer()
        scrolled_content.add(self.content_view)
        right_box.pack_start(scrolled_content, True, True, 0)

        # ----------------------------------------------------------
        # TAGS DE FORMATO MARKDOWN
        # ----------------------------------------------------------
        self.tag_h1 = self.textbuffer.create_tag("h1", scale=1.5, weight=Pango.Weight.BOLD)
        self.tag_h2 = self.textbuffer.create_tag("h2", scale=1.3, weight=Pango.Weight.BOLD)
        self.tag_h3 = self.textbuffer.create_tag("h3", scale=1.1, weight=Pango.Weight.BOLD)
        self.tag_h4 = self.textbuffer.create_tag("h4", scale=1.0, weight=Pango.Weight.BOLD)
        self.tag_bold = self.textbuffer.create_tag("bold", weight=Pango.Weight.BOLD)
        self.tag_italic = self.textbuffer.create_tag("italic", style=Pango.Style.ITALIC)
        self.tag_list_item = self.textbuffer.create_tag("list-item", left_margin=20)
        self.tag_code = self.textbuffer.create_tag("code", family="Monospace")

        # ----------------------------------------------------------
        # VARIABLES DE CONTROL
        # ----------------------------------------------------------
        self._last_marked_iter = None

        self._marker_line_start = self.textbuffer.create_mark(
            "marker-line-start", self.textbuffer.get_start_iter(), True)
        self._marker_line_end = self.textbuffer.create_mark(
            "marker-line-end", self.textbuffer.get_start_iter(), False)

        # Debe permanecer viva: GTK puede completar el scroll después de la llamada.
        self._section_scroll_mark = self.textbuffer.create_mark(
            "section-scroll", self.textbuffer.get_start_iter(), True)

        # ----------------------------------------------------------
        # ORDEN DE EMPAQUETADO
        # ----------------------------------------------------------
        main_paned = Gtk.HPaned()
        main_paned.set_position(220)
        main_paned.pack1(left_box, False, False)
        main_paned.pack2(right_box, True, False)
        self.add(main_paned)

        # ----------------------------------------------------------
        # CARGA DEL DOCUMENTO
        # ----------------------------------------------------------
        self._load_document()
        self._prepare_restored_section()

        # Restaurar después del mapeo y de completar la activación inicial.
        self._restore_section_id = self.connect("map-event", self._restore_section)
        self.show_all()

    def _load_collection(self):
        """Muestra archivos legales independientes bajo sus carpetas originales."""
        self.set_title("WMM - Licenses")
        self.index_label.set_markup("<b>Licenses</b>")
        self.textbuffer.set_text("")
        self.index_store.clear()
        self._collection_files = {}

        parents = {self._document_path: None}
        first_document = None
        wmm_document = None

        for directory, subdirs, filenames in os.walk(self._document_path):
            subdirs.sort(key=str.casefold)
            parent = parents[directory]

            for name in subdirs:
                path = os.path.join(directory, name)
                parents[path] = self.index_store.append(parent, [name, -1, ""])

            for name in sorted(filenames, key=str.casefold):
                path = os.path.join(directory, name)
                if not os.path.isfile(path):
                    continue

                tree_iter = self.index_store.append(parent, [name, -1, ""])
                tree_path = self.index_store.get_path(tree_iter)
                self._collection_files[tree_path.to_string()] = path

                if first_document is None:
                    first_document = tree_path

                if (wmm_document is None and
                        os.path.relpath(directory, self._document_path).casefold() == "wmm"):
                    wmm_document = tree_path

        if first_document is not None and not self._viewer_state.get("section"):
            initial_document = wmm_document or first_document
            self.index_tree.expand_to_path(initial_document)
            self.index_tree.set_cursor(initial_document)
            GLib.idle_add(self.index_tree.scroll_to_cell,
                initial_document, None, True, 0.5, 0.0)

    def _parse_document_metadata(self, content):
        """Lee metadatos WMM únicamente del comentario HTML inicial."""
        metadata = {}
        match = re.match(r"^\ufeff?\s*<!--(.*?)-->", content, re.DOTALL)

        if not match:
            return metadata

        for line in match.group(1).splitlines():
            key, separator, value = line.strip().partition(":")
            value = value.strip()

            if separator and value and key in ("WMM-Title", "WMM-Contents"):
                metadata[key] = value

        return metadata

    # ----------------------------------------------------------
    # CARGA DEL DOCUMENTO Y GENERACIÓN DEL ÍNDICE
    # ----------------------------------------------------------
    def _load_document(self):
        """Carga el Markdown resuelto y genera el índice desde sus títulos."""
        if os.path.isdir(self._document_path):
            self._load_collection()
            return

        if not os.path.isfile(self._document_path):
            return

        try:
            with open(self._document_path, "r", encoding="utf-8") as file:
                content = file.read()
        except OSError as error:
            self._show_error(f"Could not read document:\n{error}")
            return

        # Los metadatos WMM viven únicamente en el comentario HTML inicial.
        metadata = self._parse_document_metadata(content)

        # Los comentarios HTML son válidos en Markdown pero no forman parte
        # del contenido visible del documento.
        content = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)
        lines = content.splitlines(keepends=True)

        # Textos propios del documento, con fallback si no hay metadatos.
        document_title = metadata.get("WMM-Title", self._document_name)
        contents_title = metadata.get("WMM-Contents", "Contents")

        self.set_title(f"WMM - {document_title}")
        self.index_label.set_markup(
            f"<b>{GLib.markup_escape_text(contents_title)}</b>"
        )

        self.textbuffer.set_text("")
        self.index_store.clear()

        current_parent = None
        current_h2 = None
        buffer = self.textbuffer
        iter = buffer.get_end_iter()

        for line in lines:
            # strip() eliminaría la sangría Markdown necesaria para el subnivel.
            is_indented = line != line.lstrip()
            stripped = line.strip()

            # --- TÍTULOS Y GENERACIÓN DEL ÍNDICE ---
            if stripped.startswith("#"):
                level = min(stripped.count("#", 0, 4), 4)
                title = stripped.lstrip("#").strip()
                tags = {1: self.tag_h1, 2: self.tag_h2, 3: self.tag_h3, 4: self.tag_h4}
                tag = tags.get(level, self.tag_h4)
                buffer.insert_with_tags(iter, title + "\n", tag)

                if level == 1:
                    current_parent = self.index_store.append(None, [title, iter.get_line(), ""])
                    current_h2 = None
                elif level == 2 and current_parent is not None:
                    current_h2 = self.index_store.append(current_parent, [title, iter.get_line(), ""])
                elif level >= 3 and current_h2 is not None:
                    self.index_store.append(current_h2, [title, iter.get_line(), ""])

            # --- LISTAS ---
            elif stripped.startswith("- ") or stripped.startswith("* "):
                text = stripped[2:]
                bullet = "      • " if is_indented else "  • "
                buffer.insert_with_tags(iter, bullet, self.tag_list_item)
                self._insert_markdown_text(buffer, iter, text + "\n")

            # --- PÁRRAFOS NORMALES ---
            elif stripped:
                self._insert_markdown_text(buffer, iter, stripped + "\n")

            else:
                buffer.insert(iter, "\n")

    # ----------------------------------------------------------
    # INSERCIÓN DE TEXTO CON FORMATO MARKDOWN BÁSICO
    # ----------------------------------------------------------
    def _insert_markdown_text(self, buffer, iter, text):
        """Inserta texto parseando negritas, itálicas y código inline."""
        patterns = [
            (r"\*\*(.+?)\*\*", self.tag_bold),
            (r"\*(.+?)\*", self.tag_italic),
            (r"`(.+?)`", self.tag_code),
        ]

        pos = 0
        while pos < len(text):
            next_match = None
            next_tag = None
            next_start = len(text)

            for pattern, tag in patterns:
                match = re.search(pattern, text[pos:])
                if match:
                    start = pos + match.start()
                    if start < next_start:
                        next_match = match
                        next_tag = tag
                        next_start = start

            if next_match is None:
                buffer.insert(iter, text[pos:])
                break

            if next_start > pos:
                buffer.insert(iter, text[pos:next_start])

            buffer.insert_with_tags(iter, next_match.group(1), next_tag)
            pos = next_start + len(next_match.group(0))

    # ----------------------------------------------------------
    # NAVEGACIÓN DESDE EL ÍNDICE
    # ----------------------------------------------------------
    def _on_index_cursor_changed(self, treeview):
        """Marca la sección seleccionada y la centra en el área de lectura."""
        selection = treeview.get_selection()
        model, tree_iter = selection.get_selected()
        if not tree_iter:
            return

        if hasattr(self, "_collection_files"):
            path = model.get_path(tree_iter).to_string()
            document = self._collection_files.get(path)
            if not document:
                return

            try:
                with open(document, "r", encoding="utf-8-sig") as file:
                    content = file.read()
            except (OSError, UnicodeError) as error:
                self._show_error(f"Could not read document:\n{error}")
            else:
                # Los documentos WMM trilingües declaran sus puntos de entrada.
                # Las licencias externas mantienen la lectura literal habitual.
                markers = {"en": "[English]", "ca": "[Català]", "es": "[Castellano]"}
                lines = content.splitlines()
                line_number = 0

                if all(marker in lines for marker in markers.values()):
                    selected = markers.get(_get_session_language(), markers["en"])
                    line_number = lines.index(selected)

                self.textbuffer.set_text(content)
                self.textbuffer.move_mark(
                    self._section_scroll_mark, self.textbuffer.get_iter_at_line(line_number))

                # Posicionar tras actualizar la disposición del nuevo documento.
                GLib.idle_add(self.content_view.scroll_to_mark,
                    self._section_scroll_mark, 0.0, line_number > 0, 0.0, 0.0)
            return

        new_line = model.get_value(tree_iter, 1)

        # --- 1. Restaurar la línea anterior ---
        old_start = self.textbuffer.get_iter_at_mark(self._marker_line_start)
        old_end = self.textbuffer.get_iter_at_mark(self._marker_line_end)
        if not old_start.equal(old_end):
            old_text = self.textbuffer.get_text(old_start, old_end, False)
            if old_text.startswith("▶ "):
                end_marker = old_start.copy()
                end_marker.forward_chars(2)
                self.textbuffer.delete(old_start, end_marker)

        # --- 2. Insertar el marcador en la nueva línea ---
        line_start = self.textbuffer.get_iter_at_line(new_line)
        self.textbuffer.insert(line_start, "▶ ")

        new_line_start = self.textbuffer.get_iter_at_line(new_line)
        new_line_end = new_line_start.copy()
        if not new_line_end.ends_line():
            new_line_end.forward_to_line_end()
        new_line_end.forward_char()
        self.textbuffer.move_mark(self._marker_line_start, new_line_start)
        self.textbuffer.move_mark(self._marker_line_end, new_line_end)

        # --- 3. Actualizar el marcador en el índice ---
        if self._last_marked_iter:
            model.set_value(self._last_marked_iter, 2, "")
        model.set_value(tree_iter, 2, "▶")
        self._last_marked_iter = tree_iter

        # --- 4. Centrar la sección ---
        start_iter = self.textbuffer.get_iter_at_line(new_line)
        self.textbuffer.move_mark(self._section_scroll_mark, start_iter)
        self.content_view.scroll_to_mark(self._section_scroll_mark, 0.0, True, 0.0, 0.5)

    def _apply_document_font(self, font):
        """Aplica una única preferencia tipográfica al documento y su índice."""
        description = Pango.FontDescription.from_string(font)

        # El contenido Markdown conserva las escalas y atributos
        # definidos en sus GtkTextTag.
        self.content_view.override_font(description)

        # El título conserva la negrita definida mediante markup.
        self.index_label.override_font(description)

        # Los elementos del índice se dibujan mediante CellRendererText:
        # su fuente debe actualizarse explícitamente.
        for column in self.index_tree.get_columns():
            for renderer in column.get_cells():
                if isinstance(renderer, Gtk.CellRendererText):
                    renderer.set_property("font-desc", description)

    def _on_font_changed(self, button):
        """Actualiza la tipografía de ambas columnas sin reconstruirlas."""
        font = button.get_font()
        self._apply_document_font(font)
        self._viewer_state["font"] = font
        self._save_viewer_state({"font": font})

    def _truncate_font_label(self, button, _param):
        """Limita el texto del selector sin alterar la fuente seleccionada."""
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

    # ==========================================================
    # PREFERENCIAS DEL VISOR
    # ==========================================================
    def _load_viewer_state(self):
        """Carga tamaño y última sección propios de este documento."""
        # La fuente inicial procede del tema GTK para conservar
        # la apariencia actual mientras no exista elección del usuario.
        gtk_settings = Gtk.Settings.get_default()
        default_font = gtk_settings.get_property("gtk-font-name") if gtk_settings else "Sans 10"

        defaults = {
            "window_size": [900, 650],
            "section": None,
            "font": default_font,
        }

        try:
            with open(self._settings_path, "r", encoding="utf-8") as file:
                settings = json.load(file)
        except (OSError, json.JSONDecodeError):
            return defaults

        if not isinstance(settings, dict):
            return defaults

        viewer_state = settings.get(self._settings_key, {})
        if not isinstance(viewer_state, dict):
            return defaults

        state = defaults.copy()

        window_size = viewer_state.get("window_size", defaults["window_size"])
        valid_size = (isinstance(window_size, list) and len(window_size) == 2
            and all(type(value) is int and value > 0 for value in window_size))
        state["window_size"] = window_size if valid_size else defaults["window_size"]

        section = viewer_state.get("section")
        state["section"] = section if isinstance(section, str) and section else None
        font = viewer_state.get("font")
        state["font"] = font if isinstance(font, str) and font.strip() else defaults["font"]

        return state

    def _prepare_restored_section(self):
        """Expande sólo los ancestros necesarios antes de mostrar la ventana."""
        section = self._viewer_state.get("section")
        if not section or ":" not in section:
            return

        try:
            parent_path = Gtk.TreePath.new_from_string(section.rsplit(":", 1)[0])
            self.index_store.get_iter(parent_path)
        except (TypeError, ValueError):
            return

        self.index_tree.expand_to_path(parent_path)

    def _restore_section(self, widget, event):
        """Difiere una sola vez la restauración hasta completar la activación inicial."""
        if self._restore_section_id:
            self.disconnect(self._restore_section_id)
            self._restore_section_id = 0

        if self._viewer_state.get("section"):
            GLib.idle_add(self._restore_section_idle)

        return False

    def _restore_section_idle(self):
        """Restaura la sección cuando GTK ya ha completado map y present."""
        section = self._viewer_state.get("section")
        if not section:
            return False

        try:
            tree_path = Gtk.TreePath.new_from_string(section)
            self.index_store.get_iter(tree_path)
        except (TypeError, ValueError):
            return False

        self.index_tree.set_cursor(tree_path)
        self.index_tree.scroll_to_cell(tree_path, None, True, 0.5, 0.0)

        return False

    def _save_viewer_state(self, values):
        """Actualiza las preferencias indicadas sin reformatear settings.json."""
        try:
            with open(self._settings_path, "r", encoding="utf-8") as file:
                raw_settings = file.read()
            settings = json.loads(raw_settings)
        except (OSError, json.JSONDecodeError):
            return

        if not isinstance(settings, dict):
            return

        viewer_state = settings.get(self._settings_key)
        if self._settings_key in settings and not isinstance(viewer_state, dict):
            return

        if isinstance(viewer_state, dict) and all(
            viewer_state.get(key) == value for key, value in values.items()
        ):
            return

        escaped_key = re.escape(self._settings_key)
        match = re.search(
            rf'("{escaped_key}"\s*:\s*\{{)(.*?)(\n[ \t]*\}})',
            raw_settings, re.DOTALL
        )

        if match:
            body = match.group(2)
            indent_match = re.search(r"\n([ \t]+)\"", body)
            indent = indent_match.group(1) if indent_match else "        "

            for key, value in values.items():
                serialized_value = json.dumps(value, ensure_ascii=False)
                key_pattern = rf'(^[ \t]*"{re.escape(key)}"\s*:\s*)(?:\[[^\]]*\]|"(?:\\.|[^"\\])*"|null)'

                if re.search(key_pattern, body, re.MULTILINE):
                    body = re.sub(
                        key_pattern,
                        lambda match, replacement=serialized_value: match.group(1) + replacement,
                        body,
                        count=1,
                        flags=re.MULTILINE
                    )
                else:
                    separator = "," if body.strip() else ""
                    body = body.rstrip() + separator + "\n" + indent + f'"{key}": {serialized_value}'

            updated = raw_settings[:match.start(2)] + body + raw_settings[match.end(2):]
        else:
            end = raw_settings.rfind("}")
            if end < 0:
                return

            # Conservar el formato y la separación al crear
            # las preferencias de un documento todavía inexistente.
            prefix = raw_settings[:end].rstrip()
            separator = "," if prefix and not prefix.endswith("{") else ""

            # La primera preferencia puede ser la fuente, antes de que
            # exista geometría persistida para este documento.
            fields = ",\n".join(
                f'        "{key}": {json.dumps(value, ensure_ascii=False)}'
                for key, value in values.items()
            )
            updated = (
                prefix + separator +
                f'\n    "{self._settings_key}": {{\n'
                f'{fields}\n'
                "    }\n" +
                raw_settings[end:]
            )

        try:
            with open(self._settings_path, "w", encoding="utf-8") as file:
                file.write(updated)
        except OSError:
            return

    def _on_delete_event(self, widget, event):
        """Guarda tamaño y sección actual una única vez al cerrar."""
        width, height = self.get_size()

        model, tree_iter = self.index_tree.get_selection().get_selected()
        section = model.get_path(tree_iter).to_string() if tree_iter else None

        self._save_viewer_state({ "window_size": [width, height], "section": section, })
        return False

    # ----------------------------------------------------------
    # ERROR EN EL ÁREA DE CONTENIDO
    # ----------------------------------------------------------
    def _show_error(self, message):
        """Muestra un error dentro del propio visor."""
        self.textbuffer.set_text(message)
        error_tag = self.textbuffer.create_tag("error", foreground="red")
        self.textbuffer.apply_tag(
            error_tag, self.textbuffer.get_start_iter(), self.textbuffer.get_end_iter())

# ==========================================================
# APLICACIÓN GTK
# ==========================================================
class DocsApplication(Gtk.Application):
    """Mantiene una sola instancia por documento base."""

    def __init__(self, base_path, platform):
        super().__init__(application_id=_build_application_id(base_path))
        self.base_path = base_path
        self._platform = platform

    def do_activate(self):
        if hasattr(self._platform, "prepare_gtk_color_scheme"):
            self._platform.prepare_gtk_color_scheme()

        window = self.props.active_window
        if window is None:
            # ----------------------------------------------------------
            # CSS COMPARTIDO DE WMM
            # ----------------------------------------------------------
            # El visor es una aplicación independiente del Panel.
            # Cargar los estilos una sola vez, antes de crear su ventana.
            css_path = os.path.join(
                self._platform.app_dir, "wmm_platform", "shell", "common", "wmm.css")

            if os.path.isfile(css_path):
                css_provider = Gtk.CssProvider()
                css_provider.load_from_path(css_path)
                Gtk.StyleContext.add_provider_for_screen(
                    Gdk.Screen.get_default(), css_provider,
                    Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            else:
                print(f"[WMM DOCS] CSS compartido no disponible: {css_path}",
                    file=sys.stderr)

            settings_path = os.path.join(self._platform.data_dir, "settings.json")

            window = DocsViewer(self.base_path, settings_path)
            window.connect("destroy", lambda *_: self.quit())
            self.add_window(window)

        if hasattr(self._platform, "present_window"):
            self._platform.present_window(window)
        else:
            window.present()

# ==========================================================
# ENTRY POINT
# ==========================================================
def main():
    if len(sys.argv) != 2:
        print(f"Usage: {os.path.basename(sys.argv[0])} <document.md>")
        return 1

    base_path = _resolve_base_path(sys.argv[1])
    _set_process_name(base_path)
    platform = PlatformManager()

    # El selector utiliza el mismo dominio de traducciones que el Panel.
    initialize(platform)

    # El visor autónomo no pasa por ConfigHandler; habilitamos el logger
    # común para registrar el resultado real de la activación Win32.
    set_cache_dir(platform.cache_dir)

    app = DocsApplication(base_path, platform)
    return app.run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
