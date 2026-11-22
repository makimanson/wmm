#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

"""
WMM - Wallpaper Multi-Monitor Manager

pot_manager.py - Translation Manager (POT Manager)
========================================
Graphical tool to analyze, compare and update
the project's wmm.pot file.

Uses xgettext to extract strings from .py and .js files,
generates a temporary .pot in WMM's platform cache under pot_manager/
and allows comparing it with the current .pot before applying changes.
"""

import ast
import json
import os
import sys
import subprocess
import re
import shutil
import tempfile
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Gdk, Pango

# ----------------------------------------------------------
# PATH CONFIGURATION AND TRANSLATION IMPORT
# ----------------------------------------------------------

# Add python/ to path to import i18n and PlatformManager
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", "..", ".."))
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, os.path.join(_PROJECT_ROOT, "python"))

from wmm_platform.core import PlatformManager
import i18n

# Inicializar plataforma y traducciones
platform = PlatformManager()
i18n.initialize(platform)

# Use platform paths instead of hardcoded ones
PROJECT_ROOT = platform.app_dir  # Root of the installed project
POT_OFFICIAL = os.path.join(PROJECT_ROOT, "wmm_platform", "shell", "po", "wmm.pot")
PO_DIR = os.path.dirname(POT_OFFICIAL)
CACHE_DIR = os.path.join(platform.cache_dir, "pot_manager")
POT_TEMP = os.path.join(CACHE_DIR, "wmm_temp.pot")

SOURCE_DIRS = [
    os.path.join(PROJECT_ROOT, "python"),
    os.path.join(PROJECT_ROOT, "wmm_platform", "shell"),
]

TYPE_COLUMN_DEFAULT_CHARS = 12
STRING_COLUMN_DEFAULT_CHARS = 32

# ==========================================================
# IDENTIDAD DEL PROCESO
# ==========================================================

def _set_process_identity():
    """Asigna nombre e icono propios al proceso WMM Translator."""
    GLib.set_prgname("WMM Translator")
    GLib.set_application_name("WMM Translator")
    Gtk.Window.set_default_icon_name("accessories-text-editor")

    # Linux conserva por separado el nombre corto visible del proceso;
    # definirlo evita que el Translator aparezca simplemente como python3.
    try:
        with open("/proc/self/comm", "w", encoding="ascii") as process_name:
            process_name.write("WMM Translator")
    except OSError:
        pass

# ==========================================================
# BASIC .POT FILE PARSING
# ==========================================================

def discover_po_catalogs():
    """Descubre dinámicamente los catálogos .po disponibles."""
    if not os.path.isdir(PO_DIR):
        return []

    catalogs = []

    for filename in os.listdir(PO_DIR):
        if not filename.endswith(".po"):
            continue

        language = os.path.splitext(filename)[0]
        catalogs.append((language, os.path.join(PO_DIR, filename)))

    return sorted(catalogs, key=lambda item: item[0].casefold())

def parse_pot(pot_path):
    """
    Extracts msgid entries and their source references from a .pot file.
    Returns {msgid: [references]}.
    """
    entries = {}
    if not os.path.exists(pot_path):
        return entries

    def process_block(block):
        if not block:
            return

        references = []
        for line in block:
            if line.startswith("#:"):
                references.extend(line[2:].strip().split())

        msgid_index = next(
            (i for i, line in enumerate(block) if line.startswith("msgid ")),
            None
        )
        if msgid_index is None:
            return

        try:
            msgid = ast.literal_eval(block[msgid_index][6:].strip())

            i = msgid_index + 1
            while i < len(block) and block[i].startswith('"'):
                msgid += ast.literal_eval(block[i])
                i += 1
        except (SyntaxError, ValueError):
            return

        if msgid:
            entries[msgid] = references

    block = []

    with open(pot_path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.rstrip("\n")

            if not line.strip():
                process_block(block)
                block = []
            else:
                block.append(line)

    process_block(block)

    return entries

def parse_po(po_path):
    """
    Lee un catálogo .po conservando la localización real de cada entrada.
    La cabecera msgid "" y las entradas plurales quedan fuera del editor.
    """
    entries = {}

    if not os.path.exists(po_path):
        return entries

    try:
        with open(po_path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return entries

    def parse_field(block, keyword):
        """Extrae un campo gettext simple, incluyendo sus líneas continuadas."""
        prefix = keyword + " "
        field_index = next(
            (i for i, line in enumerate(block) if line.startswith(prefix)), None)

        if field_index is None:
            return None, None, None

        try:
            value = ast.literal_eval(block[field_index][len(prefix):].strip())

            i = field_index + 1
            while i < len(block) and block[i].startswith('"'):
                value += ast.literal_eval(block[i])
                i += 1
        except (SyntaxError, ValueError):
            return None, None, None

        return value, field_index, i

    def process_block(block, block_start):
        if not block:
            return

        # El editor actual trabaja con msgid/msgstr simples. Las formas
        # plurales necesitan una interfaz distinta y se dejan intactas.
        if any(line.startswith("msgid_plural ") for line in block):
            return

        msgid, _, _ = parse_field(block, "msgid")
        msgstr, msgstr_start, msgstr_end = parse_field(block, "msgstr")

        # msgid "" es la cabecera administrativa del catálogo.
        if not msgid or msgstr is None:
            return

        references = []
        for line in block:
            if line.startswith("#:"):
                references.extend(line[2:].strip().split())

        fuzzy = any(line.startswith("#,") and
            "fuzzy" in [flag.strip() for flag in line[2:].split(",")]
            for line in block)

        entries[msgid] = {
            "msgstr": msgstr,
            "fuzzy": fuzzy,
            "references": references,
            "block_start": block_start,
            "block_end": block_start + len(block),
            "msgstr_start": block_start + msgstr_start,
            "msgstr_end": block_start + msgstr_end,
        }

    block = []
    block_start = 0

    for line_index, line in enumerate(lines):
        if not line.strip():
            process_block(block, block_start)
            block = []
            block_start = line_index + 1
        else:
            if not block:
                block_start = line_index
            block.append(line)

    process_block(block, block_start)

    return entries

def parse_pot_entries(pot_path):
    """Returns the msgid entries from a .pot file."""
    return list(parse_pot(pot_path).keys())

def group_source_references(references):
    """Groups POT references by source file and line numbers."""
    grouped = {}

    for reference in references:
        path, separator, line = reference.rpartition(":")

        if not separator or not line.isdigit():
            continue

        if not os.path.isabs(path):
            path = os.path.join(PROJECT_ROOT, path)

        path = os.path.normpath(path)
        line = int(line)

        lines = grouped.setdefault(path, [])
        if line not in lines:
            lines.append(line)

    return [(path, sorted(lines)) for path, lines in grouped.items()]

def count_pot_entries(pot_path):
    """Counts entries in a .pot file."""
    return len(parse_pot_entries(pot_path))

# ==========================================================
# .POT FILE COMPARISON
# ==========================================================

def compare_pots(old_path, new_path):
    """Compara dos POT y devuelve las cadenas nuevas y eliminadas."""
    old_entries = parse_pot_entries(old_path)
    new_entries = parse_pot_entries(new_path)

    old_entry_set = set(old_entries)
    new_entry_set = set(new_entries)

    # Conservamos el orden original de cada POT para que la interfaz muestre
    # las diferencias en el mismo orden en que aparecen en sus archivos.
    new_strings = [ entry for entry in new_entries if entry not in old_entry_set ]
    removed_strings = [ entry for entry in old_entries if entry not in new_entry_set ]

    return new_strings, removed_strings

# ==========================================================
# GRAPHICAL INTERFACE
# ==========================================================

class POTManagerWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="WMM - " + i18n._("Translation Manager"))

        if hasattr(platform, "prepare_gtk_color_scheme"):
            platform.prepare_gtk_color_scheme()

        # ----------------------------------------------------------
        # CSS COMPARTIDO DE WMM
        # ----------------------------------------------------------
        # El Translation Manager es autónomo: carga el recurso común
        # en su propio proceso antes de construir los indicadores.
        css_path = os.path.join(
            PROJECT_ROOT, "wmm_platform", "shell", "common", "wmm.css")

        if os.path.isfile(css_path):
            css_provider = Gtk.CssProvider()
            css_provider.load_from_path(css_path)
            Gtk.StyleContext.add_provider_for_screen(
                Gdk.Screen.get_default(), css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        else:
            print(f"[WMM POT] CSS compartido no disponible: {css_path}",
                file=sys.stderr)

        # El Translation Manager es autónomo: sólo persiste su estado visual
        # directamente en settings.json, sin depender de ConfigHandler ni Engine.
        self._settings_path = os.path.join(platform.data_dir, "settings.json")
        self._manager_preferences = self._load_manager_preferences()

        self.set_default_size(*self._manager_preferences["window_size"])
        self.set_position(Gtk.WindowPosition.CENTER)
        self.connect("delete-event", self._on_delete_event)
        self.connect("destroy", Gtk.main_quit)

        # El pie ocupa todo el ancho; los márgenes pertenecen
        # únicamente al contenido principal del formulario.
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(main_box)

        # El manager separa el flujo secuencial del POT del mantenimiento
        # puntual de traducciones, compartiendo únicamente el estado global.
        notebook = Gtk.Notebook()
        notebook.set_margin_start(12)
        notebook.set_margin_end(12)
        notebook.set_margin_top(12)
        notebook.set_margin_bottom(6)
        main_box.pack_start(notebook, True, True, 0)

        pot_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        search_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

        # Cabeceras destacadas y con espacio lateral propio.
        # La traducción de Search se escapa antes de aplicar Pango markup.
        pot_tab = Gtk.Label()
        pot_tab.set_markup("<b>POT</b>")

        search_tab = Gtk.Label()
        search_tab.set_markup(
            "<b>" + GLib.markup_escape_text(i18n._("Search")) + "</b>")

        for tab in (pot_tab, search_tab):
            tab.set_margin_start(12)
            tab.set_margin_end(12)

        notebook.append_page(pot_box, pot_tab)
        notebook.append_page(search_box, search_tab)

        # Search usa un desplegable transitorio: mientras se escribe, los resultados
        # aparecen bajo el campo y desaparecen al escoger la cadena deseada.
        search_toolbar = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        search_toolbar.set_margin_top(8)
        search_toolbar.set_border_width(12)
        search_label = Gtk.Label(label=i18n._("Search"))
        search_label.set_xalign(0)

        self.search_entry = Gtk.Entry()
        self.search_entry.get_style_context().add_class("wmm-entry-border")
        self.search_entry.set_placeholder_text(i18n._("Filter by text") + "...")
        self.search_entry.connect("changed", self._on_search_changed)
        self.search_entry.connect("key-press-event", self._on_search_key_press)
        search_toolbar.pack_start(search_label, False, False, 0)
        search_toolbar.pack_start(self.search_entry, True, True, 0)
        search_box.pack_start(search_toolbar, False, False, 0)

        search_box.pack_start(
            Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 2)

        # La cadena capturada queda visible como autoridad de trabajo de Search;
        # el desplegable vuelve a ser sólo un mecanismo transitorio de selección.
        search_selected_header = Gtk.Label()
        search_selected_header.set_markup(
            "<b>" + GLib.markup_escape_text(i18n._("Selected string")) + "</b>")
        search_selected_header.set_xalign(0)
        search_box.pack_start(search_selected_header, False, False, 4)

        self.search_selected_label = Gtk.Label()
        self.search_selected_label.set_xalign(0)
        self.search_selected_label.set_margin_start(8)
        self.search_selected_label.set_selectable(True)
        self.search_selected_label.set_line_wrap(True)
        search_box.pack_start(self.search_selected_label, False, False, 0)

        search_box.pack_start(
            Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 2)

        # Location permanece visible como sección propia y puede plegarse cuando
        # interesa dedicar todo el espacio disponible al editor de traducciones.
        location_header_box, self.search_location_arrow, self.search_location_header = (
            self._create_fold_header(i18n._("Location")))

        search_location_event = Gtk.EventBox()
        search_location_event.set_visible_window(False)
        search_location_event.add(location_header_box)
        search_location_event.connect(
            "button-press-event", self._on_search_location_toggle)
        search_box.pack_start(search_location_event, False, False, 4)

        # Cada archivo ocupa una fila y expone directamente sus líneas como enlaces.
        self.search_location_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.search_location_box.set_margin_start(8)
        search_box.pack_start(self.search_location_box, False, False, 0)

        search_box.pack_start(
            Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 2)

        # Search dispone de su propio editor de traducciones para la cadena activa;
        # los idiomas se poblarán después, cuando los catálogos ya estén descubiertos.
        search_translations_header = Gtk.Label()
        search_translations_header.set_markup(
            "<b>" + GLib.markup_escape_text(i18n._("Translations")) + "</b>")
        search_translations_header.set_xalign(0)
        search_box.pack_start(search_translations_header, False, False, 4)

        self.search_translations_list = Gtk.ListBox()
        self.search_translations_list.set_margin_start(8)
        self.search_translations_list.set_selection_mode(Gtk.SelectionMode.NONE)
        search_box.pack_start(self.search_translations_list, False, False, 0)

        # El Popover actúa como lista de autocompletado sin apropiarse del foco:
        # el usuario puede seguir escribiendo mientras los resultados se actualizan.
        self.search_popover = Gtk.Popover.new(self.search_entry)
        self.search_popover.set_position(Gtk.PositionType.BOTTOM)
        self.search_popover.set_modal(False)

        self.search_results_scroll = Gtk.ScrolledWindow()
        self.search_results_scroll.set_overlay_scrolling(False)
        self.search_results_scroll.set_policy(
            Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.search_results_scroll.set_min_content_height(180)

        self.search_results_list = Gtk.ListBox()
        self.search_results_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.search_results_list.set_activate_on_single_click(True)
        self.search_results_list.connect(
            "row-activated", self._on_search_result_activated)
        self.search_results_scroll.add(self.search_results_list)
        self.search_popover.add(self.search_results_scroll)

        # La ventana observa los clics antes que sus hijos para poder cerrar Search
        # al pulsar fuera, sin convertir el Popover en modal ni robar foco al Entry.
        self.search_outside_gesture = Gtk.GestureMultiPress.new(self)
        self.search_outside_gesture.set_button(1)
        self.search_outside_gesture.set_propagation_phase(
            Gtk.PropagationPhase.CAPTURE)
        self.search_outside_gesture.connect(
            "pressed", self._on_search_outside_press)

        # La página POT conserva arriba el flujo de generación/revisión y
        # reserva abajo el espacio de trabajo para las cadenas ya aplicadas.
        self.pot_paned = Gtk.VPaned()
        self.pot_paned.set_position(self._manager_preferences["pot_split_position"])
        pot_box.pack_start(self.pot_paned, True, True, 0)

        pot_top_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=6)
        self.pot_paned.pack1(pot_top_box, True, False)

        pot_bottom_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=4)
        self.pot_paned.pack2(pot_bottom_box, True, False)

        # Separa visualmente la revisión del POT de la fase posterior de traducción.
        pot_bottom_box.pack_start(
            Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 2)

        # Las cadenas nuevas de la sesión y las pendientes anteriores
        # comparten la columna izquierda frente al editor de traducciones.
        self.translations_paned = Gtk.HPaned()
        self.translations_paned.set_position(
            self._manager_preferences["translations_split_position"])
        pot_bottom_box.pack_start(self.translations_paned, True, True, 0)

        strings_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=4)

        # La cabecera permite plegar la lista sin alterar su selección funcional.
        new_header_box, self.new_strings_arrow, self.new_strings_header = (
            self._create_fold_header(i18n._("New strings")))

        new_strings_header_box = Gtk.EventBox()
        new_strings_header_box.set_visible_window(False)
        new_strings_header_box.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        new_strings_header_box.add(new_header_box)
        new_strings_header_box.connect(
            "button-press-event", self._on_strings_section_toggle, "new")
        strings_box.pack_start(new_strings_header_box, False, False, 0)

        self.new_strings_scroll = Gtk.ScrolledWindow()
        self.new_strings_scroll.set_margin_start(8)
        self.new_strings_scroll.set_overlay_scrolling(False)
        self.new_strings_scroll.set_policy(
            Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        self.new_strings_list = Gtk.ListBox()
        self.new_strings_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.new_strings_list.set_activate_on_single_click(False)
        self.new_strings_list.connect("row-selected", self._on_pending_string_selected)
        self.new_strings_list.connect("row-activated", self._on_pending_row_activated)
        self.new_strings_list.connect("button-press-event", self._on_pending_button_press)
        self.new_strings_scroll.add(self.new_strings_list)
        strings_box.pack_start(self.new_strings_scroll, True, True, 0)

        # Separa visualmente las cadenas nuevas de las pendientes anteriores.
        strings_box.pack_start(
            Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 2)

        # Pending comparte el mismo plegado visual, pero conserva su ListBox
        # independiente y la selección coordinada con New.
        pending_header_box_content, self.pending_strings_arrow, self.pending_strings_header = (
            self._create_fold_header(i18n._("Pending strings")))

        pending_header_box = Gtk.EventBox()
        pending_header_box.set_visible_window(False)
        pending_header_box.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        pending_header_box.add(pending_header_box_content)
        pending_header_box.connect(
            "button-press-event", self._on_strings_section_toggle, "pending")
        strings_box.pack_start(pending_header_box, False, False, 0)

        self.pending_strings_scroll = Gtk.ScrolledWindow()
        self.pending_strings_scroll.set_margin_start(8)
        self.pending_strings_scroll.set_overlay_scrolling(False)
        self.pending_strings_scroll.set_policy(
            Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        self.pending_strings_list = Gtk.ListBox()
        self.pending_strings_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.pending_strings_list.set_activate_on_single_click(False)
        self.pending_strings_list.connect("row-selected", self._on_pending_string_selected)
        self.pending_strings_list.connect("row-activated", self._on_pending_row_activated)
        self.pending_strings_list.connect("button-press-event", self._on_pending_button_press)
        self.pending_strings_scroll.add(self.pending_strings_list)
        strings_box.pack_start(self.pending_strings_scroll, True, True, 0)

        self.translations_paned.pack1(strings_box, True, False)

        translations_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        translations_header = Gtk.Label()
        translations_header.set_markup(
            "<b>" + GLib.markup_escape_text(i18n._("Translations")) + "</b>")
        translations_header.set_xalign(0)
        translations_box.pack_start(translations_header, False, False, 0)

        translations_scroll = Gtk.ScrolledWindow()
        translations_scroll.set_margin_start(8)
        translations_scroll.set_overlay_scrolling(False)
        translations_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        self.translations_list = Gtk.ListBox()
        self.translations_list.set_selection_mode(Gtk.SelectionMode.NONE)
        translations_scroll.add(self.translations_list)
        self._populate_translation_languages()

        # Search comparte los catálogos ya descubiertos por POT, pero mantiene
        # editores propios porque ambos flujos conservan selecciones independientes.
        self._populate_search_translation_languages()

        translations_box.pack_start(translations_scroll, True, True, 0)

        self.translations_paned.pack2(translations_box, True, False)

        # --- Toolbar ---
        toolbar = Gtk.Box(spacing=6)
        toolbar.set_margin_top(12)
        toolbar.set_margin_start(12)
        toolbar.set_margin_end(12)
        pot_top_box.pack_start(toolbar, False, False, 0)

        self.btn_generate = Gtk.Button.new_with_label(i18n._("Generate temporary .pot"))
        self.btn_generate.connect("clicked", self.on_generate_temp)
        toolbar.pack_start(self.btn_generate, False, False, 0)

        self.btn_apply = Gtk.Button.new_with_label(i18n._("Apply changes"))
        self.btn_apply.set_sensitive(False)
        self.btn_apply.connect("clicked", self.on_apply_changes)
        toolbar.pack_end(self.btn_apply, False, False, 0)

        # --- Statistics panel ---
        stats_box = Gtk.Box(spacing=20)
        stats_box.set_margin_start(12)
        pot_top_box.pack_start(stats_box, False, False, 6)

        self.lbl_current = Gtk.Label()
        self.lbl_temp = Gtk.Label()
        self.lbl_new = Gtk.Label()
        self.lbl_removed = Gtk.Label()

        for lbl, text in [
            (self.lbl_current, i18n._("Current") + ": --"),
            (self.lbl_temp, i18n._("Temporary") + ": --"),
            (self.lbl_new, i18n._("New") + ": --"),
            (self.lbl_removed, i18n._("Removed") + ": --")
        ]:
            lbl.set_markup(f"<b>{text}</b>")
            stats_box.pack_start(lbl, False, False, 0)

        # --- Difference list ---
        difference_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        pot_top_box.pack_start(difference_box, True, True, 0)

        # Header
        self._type_column_width = None
        self._string_column_width = None
        self._column_resize_state = None

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        header.set_margin_start(4)
        header.set_margin_end(4)

        self.header_type = Gtk.Label()
        self.header_type.set_markup(
            "<b>" + GLib.markup_escape_text(i18n._("Type")) + "</b>")
        self.header_type.set_xalign(0)
        self.header_type.set_width_chars(TYPE_COLUMN_DEFAULT_CHARS)
        self.header_type.set_ellipsize(Pango.EllipsizeMode.END)

        self.header_string = Gtk.Label()
        self.header_string.set_markup(
            "<b>" + GLib.markup_escape_text(i18n._("String")) + "</b>")
        self.header_string.set_xalign(0)
        self.header_string.set_width_chars(STRING_COLUMN_DEFAULT_CHARS)
        self.header_string.set_ellipsize(Pango.EllipsizeMode.END)

        header_location = Gtk.Label()
        header_location.set_markup(
            "<b>" + GLib.markup_escape_text(i18n._("Location")) + "</b>")
        header_location.set_xalign(0)

        header.pack_start(self.header_type, False, False, 0)
        header.pack_start(self._create_column_resizer("type"), False, False, 0)
        header.pack_start(self.header_string, False, False, 0)
        header.pack_start(self._create_column_resizer("string"), False, False, 0)
        header.pack_start(header_location, True, True, 0)

        # La cabecera queda encuadrada como un bloque completo: los tiradores
        # mantienen las divisiones verticales y el marco delimita también la fase
        # de comparación respecto a las estadísticas mostradas encima.
        header_frame = Gtk.Frame()
        header_frame.get_style_context().add_class("wmm-pot-header-frame")
        header_frame.set_shadow_type(Gtk.ShadowType.IN)
        header_frame.add(header)

        difference_box.pack_start(header_frame, False, False, 0)

        GLib.idle_add(self._initialize_column_widths)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        difference_box.pack_start(scroll, True, True, 0)

        self.difference_list = Gtk.ListBox()
        self.difference_list.set_selection_mode(Gtk.SelectionMode.NONE)
        scroll.add(self.difference_list)

        # --- Status bar ---
        # El contenedor define la superficie del pie completo;
        # el Statusbar conserva únicamente los mensajes de estado.
        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        footer.get_style_context().add_class("wmm-pot-footer")

        self.statusbar = Gtk.Statusbar()
        self.statusbar.get_style_context().add_class("wmm-pot-statusbar")

        footer.pack_start(self.statusbar, True, True, 0)
        main_box.pack_start(footer, False, False, 0)
        self.statusbar.push(0, i18n._("Ready."))

        # Conserva las cadenas detectadas en la comparación actual hasta
        # que el POT se aplique y los catálogos .po queden sincronizados.
        self._new_entries = []
        self._selected_msgid = None
        self._pending_copy_label = None
        self._populate_pending_strings()

        # Search trabaja sobre una fotografía en memoria del POT y los catálogos;
        # el filtrado posterior no necesita volver a acceder a disco.
        self._build_search_index()

        # Load initial statistics
        self.update_stats()

    def _create_fold_header(self, title):
        """Construye una cabecera con indicador Adwaita independiente del texto."""
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)

        arrow = Gtk.Image.new_from_icon_name(
            "media-playback-start-symbolic", Gtk.IconSize.BUTTON)
        arrow.set_pixel_size(12)
        arrow.set_valign(Gtk.Align.CENTER)

        style = arrow.get_style_context()
        style.add_class("wmm-pot-arrow-down")
        box.pack_start(arrow, False, False, 0)

        label = Gtk.Label()
        label.set_markup("<b>" + GLib.markup_escape_text(title) + "</b>")
        label.set_xalign(0)
        box.pack_start(label, False, False, 0)

        return box, arrow, label

    # ==========================================================
    # PLEGADO DE NEW / PENDING
    # ==========================================================
    def _on_strings_section_toggle(self, widget, event, section):
        """Pliega o despliega una de las listas de cadenas."""
        # Sólo el primer clic izquierdo cambia el estado; un doble clic no debe
        # provocar un segundo cambio al recibir su evento _2BUTTON_PRESS.
        if event.button != 1 or event.type != Gdk.EventType.BUTTON_PRESS:
            return False

        scroll = (self.new_strings_scroll
            if section == "new"
            else self.pending_strings_scroll)

        self._set_strings_section_expanded(section, not scroll.get_visible())
        return True

    def _set_strings_section_expanded(self, section, expanded):
        """Aplica el plegado visual sin persistirlo entre sesiones."""
        if section == "new":
            scroll = self.new_strings_scroll
            arrow = self.new_strings_arrow
        else:
            scroll = self.pending_strings_scroll
            arrow = self.pending_strings_arrow

        # Ocultar sólo el área desplazable conserva la cabecera y permite que
        # la otra lista reciba automáticamente el espacio vertical liberado.
        scroll.set_visible(expanded)

        # Sólo cambia la orientación del indicador, no el texto de la cabecera.
        style = arrow.get_style_context()
        if expanded:
            style.add_class("wmm-pot-arrow-down")
        else:
            style.remove_class("wmm-pot-arrow-down")

        self.translations_paned.queue_resize()

    # ==========================================================
    # CATÁLOGOS DE TRADUCCIÓN
    # ==========================================================
    def _populate_translation_languages(self):
        """Crea un editor y acción de guardado por cada catálogo .po existente."""
        self.po_catalogs = discover_po_catalogs()
        self.translation_editors = {}

        for language, po_path in self.po_catalogs:
            row = Gtk.ListBoxRow()

            # La fila sólo actúa como contenedor: no debe competir por el foco con
            # los editores de traducción ni reaccionar al clic sobre sus controles.
            row.set_selectable(False)
            row.set_activatable(False)
            row.set_can_focus(False)
            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row_box.set_border_width(4)
            row.add(row_box)

            language_label = Gtk.Label(label=language.upper() + ":")
            language_label.set_xalign(0)
            language_label.set_width_chars(6)

            # El editor conserva una altura compacta para cadenas normales y
            # cambia a TextView únicamente cuando existe un salto real de línea.
            editor_stack = Gtk.Stack()
            editor_stack.set_hhomogeneous(False)
            editor_stack.set_vhomogeneous(False)
            editor_stack.set_hexpand(True)

            translation_entry = Gtk.Entry()
            translation_entry.get_style_context().add_class("wmm-entry-border")
            translation_entry.set_sensitive(False)
            editor_stack.add_named(translation_entry, "single")

            multiline_scroll = Gtk.ScrolledWindow()

            # El borde pertenece al contenedor desplazable, no al editor interno.
            multiline_scroll.get_style_context().add_class("wmm-entry-border")

            multiline_scroll.set_overlay_scrolling(False)
            multiline_scroll.set_policy(
                Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            multiline_scroll.set_min_content_height(72)

            translation_view = Gtk.TextView()

            # El editor multilínea debe conservar interacción propia dentro del ListBox:
            # foco, cursor y edición pertenecen al TextView, no a la fila contenedora.
            translation_view.set_editable(True)
            translation_view.set_cursor_visible(True)
            translation_view.set_can_focus(True)
            translation_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
            translation_view.set_sensitive(False)
            multiline_scroll.add(translation_view)
            editor_stack.add_named(multiline_scroll, "multiline")
            editor_stack.set_visible_child_name("single")

            save_button = Gtk.Button.new_with_label(i18n._("Save"))
            save_button.set_sensitive(False)
            save_button.connect(
                "clicked", self._on_translation_save_clicked, language, po_path)

            # Save refleja el estado de la edición visible: tras guardar pasa a Saved,
            # y cualquier modificación posterior devuelve inmediatamente la acción a Save.
            translation_entry.connect(
                "changed", self._on_translation_editor_changed, save_button)
            translation_view.get_buffer().connect(
                "changed", self._on_translation_editor_changed, save_button)

            row_box.pack_start(language_label, False, False, 0)
            row_box.pack_start(editor_stack, True, True, 0)
            row_box.pack_start(save_button, False, False, 0)

            self.translation_editors[language] = {
                "stack": editor_stack,
                "entry": translation_entry,
                "view": translation_view,
                "save": save_button,
            }
            self.translations_list.add(row)

    def _populate_search_translation_languages(self):
        """Crea los editores de Search usando los catálogos ya descubiertos."""
        self.search_translation_editors = {}

        for language, po_path in self.po_catalogs:
            row = Gtk.ListBoxRow()

            # Igual que en POT, la fila es sólo estructura: el foco pertenece
            # al Entry o al TextView que esté activo para esta traducción.
            row.set_selectable(False)
            row.set_activatable(False)
            row.set_can_focus(False)

            row_box = Gtk.Box(
                orientation=Gtk.Orientation.HORIZONTAL,
                spacing=8)
            row_box.set_border_width(4)
            row.add(row_box)

            language_label = Gtk.Label(label=language.upper() + ":")
            language_label.set_xalign(0)
            language_label.set_width_chars(6)

            # Ambos editores existen desde el inicio; al seleccionar una msgid
            # se mostrará el adecuado según exista o no contenido multilínea.
            editor_stack = Gtk.Stack()
            editor_stack.set_hhomogeneous(False)
            editor_stack.set_vhomogeneous(False)
            editor_stack.set_hexpand(True)

            translation_entry = Gtk.Entry()
            translation_entry.get_style_context().add_class("wmm-entry-border")
            translation_entry.set_sensitive(False)
            editor_stack.add_named(translation_entry, "single")

            multiline_scroll = Gtk.ScrolledWindow()

            # El borde pertenece al contenedor desplazable, no al editor interno.
            multiline_scroll.get_style_context().add_class("wmm-entry-border")

            multiline_scroll.set_overlay_scrolling(False)
            multiline_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            multiline_scroll.set_min_content_height(72)

            translation_view = Gtk.TextView()
            translation_view.set_editable(True)
            translation_view.set_cursor_visible(True)
            translation_view.set_can_focus(True)
            translation_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
            translation_view.set_sensitive(False)

            multiline_scroll.add(translation_view)
            editor_stack.add_named(multiline_scroll, "multiline")
            editor_stack.set_visible_child_name("single")

            save_button = Gtk.Button.new_with_label(i18n._("Save"))
            save_button.set_sensitive(False)
            save_button.connect("clicked",
                self._on_search_translation_save_clicked, language, po_path)

            # El mismo contrato Save/Saved se aplica a ambos formularios.
            translation_entry.connect(
                "changed", self._on_translation_editor_changed, save_button)
            translation_view.get_buffer().connect(
                "changed", self._on_translation_editor_changed, save_button)

            row_box.pack_start(language_label, False, False, 0)
            row_box.pack_start(editor_stack, True, True, 0)
            row_box.pack_start(save_button, False, False, 0)

            self.search_translation_editors[language] = {
                "stack": editor_stack,
                "entry": translation_entry,
                "view": translation_view,
                "save": save_button,
            }

            self.search_translations_list.add(row)

    def _on_translation_editor_changed(self, editor, save_button):
        """Devuelve la acción a Save cuando el contenido vuelve a modificarse."""
        save_button.set_label(i18n._("Save"))

    def _on_search_translation_save_clicked(
            self, button, language, po_path):
        """Guarda una traducción desde Search sin alterar el flujo New/Pending."""
        msgid = getattr(self, "_search_selected_msgid", None)
        if not msgid:
            return

        editor = self.search_translation_editors.get(language)
        if not editor:
            return

        if editor["stack"].get_visible_child_name() == "multiline":
            buffer = editor["view"].get_buffer()
            start, end = buffer.get_bounds()
            translation = buffer.get_text(start, end, True)
        else:
            translation = editor["entry"].get_text()

        if not self._write_po_translation(
                po_path, msgid, translation):
            self.statusbar.push(0, i18n._("Error saving") + f" {language}.po")
            return

        # Search conserva una fotografía de los catálogos en memoria; tras escribir
        # el .po se actualiza sólo la entrada afectada para que futuras búsquedas
        # reflejen inmediatamente la nueva traducción sin releer los archivos.
        translation_data = (self.search_index.get(msgid, {})
            .get("translations", {})
            .get(language))

        if translation_data is not None:
            translation_data["msgstr"] = translation
            translation_data["fuzzy"] = False
            translation_data["exists"] = True

        # Saved pertenece únicamente a esta edición visible; cualquier cambio
        # posterior en el editor restaurará Save mediante la señal changed.
        button.set_label(i18n._("Saved"))

        self.statusbar.push(
            0,
            i18n._("Translation saved") + f": {language.upper()}")

    def _build_search_index(self):
        """Construye el índice cruzado usado por la pestaña Search."""
        self.search_index = {}

        if not os.path.exists(POT_OFFICIAL):
            return

        # El POT define el universo de cadenas y sus referencias actuales.
        # Los .po sólo enriquecen cada msgid con la traducción de su idioma.
        pot_entries = parse_pot(POT_OFFICIAL)
        catalogs = {language: parse_po(po_path) for language, po_path in self.po_catalogs}

        for msgid, references in pot_entries.items():
            translations = {}

            for language, _ in self.po_catalogs:
                entry = catalogs[language].get(msgid)
                translations[language] = {
                    "msgstr": entry["msgstr"] if entry else "",
                    "fuzzy": entry["fuzzy"] if entry else False,
                    "exists": entry is not None,
                }

            self.search_index[msgid] = { "references": references, "translations": translations, }

    def _on_search_changed(self, entry):
        """Filtra el índice Search mientras el usuario escribe."""
        query = entry.get_text().strip().casefold()

        for row in self.search_results_list.get_children():
            self.search_results_list.remove(row)

        if not query:
            self.search_popover.popdown()
            return

        for msgid, data in self.search_index.items():
            matched_language = None
            matched_translation = ""

            if query not in msgid.casefold():
                for language, translation_data in data["translations"].items():
                    msgstr = translation_data["msgstr"]

                    if msgstr and query in msgstr.casefold():
                        matched_language = language
                        matched_translation = msgstr
                        break

                if matched_language is None:
                    continue

            row = Gtk.ListBoxRow()
            row_box = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                spacing=2)
            row_box.set_border_width(4)
            row.add(row_box)

            # La msgid identifica siempre el resultado; si la coincidencia procede
            # de una traducción, ésta se muestra debajo para explicar el match.
            source_label = Gtk.Label(
                label=msgid.replace("\n", " ↵ "))
            source_label.set_xalign(0)
            source_label.set_ellipsize(Pango.EllipsizeMode.END)
            row_box.pack_start(source_label, False, False, 0)

            if matched_language:
                translation_label = Gtk.Label(
                    label=matched_language.upper() + ": "
                    + matched_translation.replace("\n", " ↵ "))
                translation_label.set_xalign(0)
                translation_label.set_ellipsize(Pango.EllipsizeMode.END)

                context = translation_label.get_style_context()
                context.add_class("dim-label")

                row_box.pack_start(translation_label, False, False, 0)

            row._wmm_msgid = msgid

            self.search_results_list.add(row)

        # El Popover no hereda automáticamente el ancho del widget al que está
        # anclado; el área de resultados reclama explícitamente ese mismo ancho.
        self.search_results_scroll.set_size_request(
            self.search_entry.get_allocated_width(), 180)

        if self.search_results_list.get_children():
            self.search_popover.show_all()
            self.search_popover.popup()
        else:
            self.search_popover.popdown()

    def _on_search_key_press(self, entry, event):
        """Cierra los resultados con Escape sin alterar la búsqueda escrita."""
        if event.keyval != Gdk.KEY_Escape:
            return False

        self.search_popover.popdown()
        return True

    def _on_search_outside_press(self, gesture, n_press, x, y):
        """Cierra Search al pulsar fuera del campo y de su desplegable."""
        if not self.search_popover.get_visible():
            return

        event = Gtk.get_current_event()
        event_widget = Gtk.get_event_widget(event) if event else None

        # Los clics dentro del propio buscador o de sus resultados pertenecen
        # al ámbito de Search y no deben provocar el cierre anticipado.
        widget = event_widget
        while widget:
            if widget is self.search_entry or widget is self.search_popover:
                return
            widget = widget.get_parent()

        self.search_popover.popdown()

    def _on_search_result_activated(self, listbox, row):
        """Captura un resultado como cadena activa de Search."""
        msgid = getattr(row, "_wmm_msgid", None)
        if not msgid:
            return

        self._search_selected_msgid = msgid
        self.search_selected_label.set_text(msgid)

        # La cadena activa puede aparecer en varios archivos y varias líneas.
        # Cada archivo recibe una fila propia y cada línea conserva su destino exacto.
        for child in self.search_location_box.get_children():
            self.search_location_box.remove(child)

        data = self.search_index.get(msgid, {})

        for path, lines in group_source_references(
                data.get("references", [])):
            location_row = Gtk.Box(
                orientation=Gtk.Orientation.HORIZONTAL,
                spacing=4)

            filename_label = Gtk.Label(
                label=os.path.basename(path) + ":")
            filename_label.set_xalign(0)
            location_row.pack_start(
                filename_label, False, False, 0)

            lines_label = Gtk.Label()
            lines_label.set_xalign(0)

            targets = {}
            line_links = []

            for index, line in enumerate(lines):
                uri = f"wmm-search-source:{index}"
                targets[uri] = (path, line)
                line_links.append(f'<a href="{uri}">{line}</a>')

            lines_label.set_markup(", ".join(line_links))
            lines_label._wmm_source_targets = targets
            lines_label.connect(
                "activate-link", self._on_source_link)

            location_row.pack_start(
                lines_label, False, False, 0)

            self.search_location_box.pack_start(
                location_row, False, False, 0)
            location_row.show_all()

        # Search carga las traducciones desde su índice en memoria; seleccionar una
        # cadena no provoca nuevas lecturas de los catálogos en disco.
        source_multiline = "\n" in msgid
        translations = data.get("translations", {})

        for language, _ in self.po_catalogs:
            editor = self.search_translation_editors.get(language)
            if not editor:
                continue

            # Cada nueva cadena inicia una operación visual independiente.
            editor["save"].set_label(i18n._("Save"))

            translation_data = translations.get(language)

            if not translation_data or not translation_data["exists"]:
                editor["entry"].set_text("")
                editor["entry"].set_sensitive(False)
                editor["view"].get_buffer().set_text("")
                editor["view"].set_sensitive(False)
                editor["save"].set_sensitive(False)
                editor["stack"].set_visible_child_name("single")
                continue

            translation = translation_data["msgstr"]
            multiline = source_multiline or "\n" in translation

            # Igual que en POT, el tipo de editor depende del contenido semántico
            # y no de cómo gettext haya distribuido físicamente la entrada.
            if multiline:
                editor["view"].get_buffer().set_text(translation)
                editor["view"].set_sensitive(True)
                editor["entry"].set_sensitive(False)
                editor["stack"].set_visible_child_name("multiline")
            else:
                editor["entry"].set_text(translation)
                editor["entry"].set_sensitive(True)
                editor["view"].set_sensitive(False)
                editor["stack"].set_visible_child_name("single")

            editor["save"].set_sensitive(True)

        self.search_popover.popdown()

    def _on_search_location_toggle(self, widget, event):
        """Pliega o despliega las ubicaciones de la cadena activa."""
        if event.button != 1 or event.type != Gdk.EventType.BUTTON_PRESS:
            return False

        self._set_search_location_expanded(
            not self.search_location_box.get_visible())
        return True

    def _set_search_location_expanded(self, expanded):
        """Aplica el estado visual de la sección Location sin persistirlo."""
        self.search_location_box.set_visible(expanded)

        # Conservamos el texto y modificamos únicamente el indicador.
        style = self.search_location_arrow.get_style_context()
        if expanded:
            style.add_class("wmm-pot-arrow-down")
        else:
            style.remove_class("wmm-pot-arrow-down")

    def _sync_po_catalogs(self, catalogs, pot_path):
        """Sincroniza los catálogos indicados contra el POT suministrado."""
        msgmerge = (platform.resolve_gettext_tool("msgmerge")
            if hasattr(platform, "resolve_gettext_tool")
            else "msgmerge")

        if not msgmerge:
            self.statusbar.push(
                0, i18n._("Error updating") + ": msgmerge not found.")
            return False

        for language, po_path in catalogs:
            try:
                subprocess.run(
                    [msgmerge, "--update", "--backup=none", "--no-fuzzy-matching",
                     po_path, pot_path], check=True)
            except (OSError, subprocess.CalledProcessError) as error:
                detail = getattr(error, "stderr", "") or str(error)
                self.statusbar.push(
                    0, i18n._("Error updating") + f" {language}.po: {detail}")
                return False

        return True

    def _clear_pending_text_selection(self):
        """Devuelve la cadena pendiente al modo normal de selección por fila."""
        if self._pending_copy_label:
            self._pending_copy_label.set_selectable(False)
            self._pending_copy_label.set_ellipsize(Pango.EllipsizeMode.END)
            self._pending_copy_label = None

    def _on_pending_button_press(self, listbox, event):
        """Muestra las referencias fuente de la fila pulsada con botón derecho."""
        if event.button != 3 or event.type != Gdk.EventType.BUTTON_PRESS:
            return False

        row = listbox.get_row_at_y(int(event.y))
        if not row:
            return False

        # El contexto debe pertenecer siempre a la misma cadena que queda activa
        # en el editor, incluso si el clic derecho se hace sobre otra fila.
        if listbox.get_selected_row() is not row:
            listbox.select_row(row)

        menu = self._build_pending_source_menu(row)
        if not menu:
            return False

        menu.popup_at_pointer(event)
        return True

    def _on_pending_row_activated(self, listbox, row):
        # La activación de fila corresponde al doble clic: la selección funcional
        # sigue perteneciendo a row-selected y aquí sólo habilitamos la copia del texto.
        self._clear_pending_text_selection()

        label = getattr(row, "_wmm_label", None)
        if not label:
            return

        # Durante la copia debe exponerse la msgid completa, aunque normalmente
        # la columna la muestre elidida para respetar el ancho disponible.
        label.set_ellipsize(Pango.EllipsizeMode.NONE)

        # El Label permanece no seleccionable durante el uso normal; sólo se habilita
        # temporalmente para seleccionar el msgid completo y facilitar Ctrl+C.
        label.set_selectable(True)
        label.select_region(0, -1)
        label.grab_focus()
        self._pending_copy_label = label

    def _on_pending_string_selected(self, listbox, row):
        """Carga las traducciones reales de la cadena seleccionada."""

        # New y Pending son dos listas visuales, pero comparten una única
        # selección funcional dentro del Translation Manager.
        if row:
            other_list = (self.pending_strings_list
                if listbox is self.new_strings_list
                else self.new_strings_list)
            other_list.unselect_all()

        selected_label = getattr(row, "_wmm_label", None) if row else None
        if self._pending_copy_label is not selected_label:
            self._clear_pending_text_selection()
        self._selected_msgid = getattr(row, "_wmm_msgid", None) if row else None

        # Sin selección no existe una entrada válida sobre la que editar.
        if not self._selected_msgid:
            for editor in self.translation_editors.values():
                editor["entry"].set_text("")
                editor["entry"].set_sensitive(False)
                editor["view"].get_buffer().set_text("")
                editor["view"].set_sensitive(False)
                editor["save"].set_sensitive(False)
                editor["stack"].set_visible_child_name("single")
            return

        source_multiline = "\n" in self._selected_msgid

        for language, po_path in self.po_catalogs:
            editor = self.translation_editors.get(language)
            if not editor:
                continue

            # Una nueva cadena inicia una nueva operación de edición, con independencia
            # del estado visual que hubiera dejado la selección anterior.
            editor["save"].set_label(i18n._("Save"))

            po_entry = parse_po(po_path).get(self._selected_msgid)

            if po_entry is None:
                editor["entry"].set_text("")
                editor["entry"].set_sensitive(False)
                editor["view"].get_buffer().set_text("")
                editor["view"].set_sensitive(False)
                editor["save"].set_sensitive(False)
                continue

            translation = po_entry["msgstr"]
            multiline = source_multiline or "\n" in translation

            # El tipo de editor responde al contenido semántico, no a cómo
            # gettext haya distribuido físicamente el texto dentro del .po.
            if multiline:
                editor["view"].get_buffer().set_text(translation)
                editor["view"].set_sensitive(True)
                editor["entry"].set_sensitive(False)
                editor["stack"].set_visible_child_name("multiline")
            else:
                editor["entry"].set_text(translation)
                editor["entry"].set_sensitive(True)
                editor["view"].set_sensitive(False)
                editor["stack"].set_visible_child_name("single")

            editor["save"].set_sensitive(True)

    def _on_translation_save_clicked(self, button, language, po_path):
        """Guarda la traducción actual y retira la fila cuando queda completa."""
        if not self._selected_msgid:
            return

        editor = self.translation_editors.get(language)
        if not editor:
            return

        if editor["stack"].get_visible_child_name() == "multiline":
            buffer = editor["view"].get_buffer()
            start, end = buffer.get_bounds()
            translation = buffer.get_text(start, end, True)
        else:
            translation = editor["entry"].get_text()

        if not self._write_po_translation(
                po_path, self._selected_msgid, translation):
            self.statusbar.push(0, i18n._("Error saving") + f" {language}.po")
            return

        # Saved confirma únicamente esta edición y este guardado; si el usuario
        # vuelve a modificar el contenido, la señal changed restaurará Save.
        button.set_label(i18n._("Saved"))

        self.statusbar.push(0, i18n._("Translation saved") + f": {language.upper()}")

        # La cadena continúa visible mientras cualquier catálogo carezca de
        # traducción válida; no reconstruimos ambas listas por una sola edición.
        for _, catalog_path in self.po_catalogs:
            entry = parse_po(catalog_path).get(self._selected_msgid)
            if entry is None or not entry["msgstr"] or entry["fuzzy"]:
                return

        selected_row = self.new_strings_list.get_selected_row()
        strings_list = self.new_strings_list

        if selected_row is None:
            selected_row = self.pending_strings_list.get_selected_row()
            strings_list = self.pending_strings_list

        if selected_row:
            strings_list.remove(selected_row)

        self._selected_msgid = None
        self._on_pending_string_selected(strings_list, None)

    def _write_po_translation(self, po_path, msgid, translation):
        """Sustituye únicamente el msgstr activo y valida cualquier fuzzy previo."""
        po_entry = parse_po(po_path).get(msgid)
        if po_entry is None:
            return False

        try:
            with open(po_path, "r", encoding="utf-8") as f:
                raw_content = f.read()
        except OSError:
            return False

        lines = raw_content.splitlines()
        trailing_newline = raw_content.endswith("\n")

        # Las cadenas con saltos reales se serializan en el formato multilineal
        # estándar de gettext; las demás permanecen en una única línea msgstr.
        if "\n" in translation:
            replacement = ["msgstr \"\""]
            replacement.extend(
                json.dumps(part, ensure_ascii=False)
                for part in translation.splitlines(keepends=True))
        else:
            replacement = ["msgstr " + json.dumps(translation, ensure_ascii=False)]

        start = po_entry["msgstr_start"]
        end = po_entry["msgstr_end"]
        lines[start:end] = replacement

        block_end = po_entry["block_end"] + len(replacement) - (end - start)

        # Una traducción guardada manualmente ya ha sido validada: si msgmerge
        # dejó el flag fuzzy, se elimina sin alterar otros flags del bloque.
        for index in range(po_entry["block_start"], block_end):
            line = lines[index]
            if not line.startswith("#,"):
                continue

            flags = [flag.strip() for flag in line[2:].split(",")]
            if "fuzzy" not in flags:
                continue

            flags.remove("fuzzy")
            if flags:
                lines[index] = "#, " + ", ".join(flags)
            else:
                del lines[index]
            break

        try:
            content = "\n".join(lines)
            if trailing_newline:
                content += "\n"

            with open(po_path, "w", encoding="utf-8") as f:
                f.write(content)
        except OSError:
            return False

        return True

    def _clear_pending_strings(self):
        """Vacía las listas visuales de cadenas nuevas y pendientes."""
        for strings_list in (self.new_strings_list, self.pending_strings_list):
            for row in strings_list.get_children():
                strings_list.remove(row)

    def _populate_pending_strings(self):
        """
        Muestra las nuevas cadenas que aún necesitan atención en algún idioma.
        Un msgstr vacío o fuzzy mantiene la cadena en la lista pendiente.
        """
        self._clear_pending_strings()

        new_msgids = set(self._new_entries)
        catalogs = {language: parse_po(po_path) for language, po_path in self.po_catalogs}
        pot_entries = parse_pot(POT_OFFICIAL)

        for msgid in pot_entries:
            pending = False

            for language, _ in self.po_catalogs:
                entry = catalogs[language].get(msgid)

                if entry is None or not entry["msgstr"] or entry["fuzzy"]:
                    pending = True
                    break

            if not pending:
                continue

            row = Gtk.ListBoxRow()

            # Un salto real se hace visible sin modificar la msgid almacenada.
            display_msgid = msgid.replace("\n", " ↵ ")
            label = Gtk.Label(label=display_msgid)
            label.set_xalign(0)
            label.set_selectable(False)
            label.set_ellipsize(Pango.EllipsizeMode.END)
            label.set_margin_start(4)
            label.set_margin_end(4)
            label.set_margin_top(4)
            label.set_margin_bottom(4)
            row.add(label)
            row._wmm_label = label
            row._wmm_msgid = msgid
            row._wmm_references = pot_entries.get(msgid, [])

            strings_list = (self.new_strings_list
                if msgid in new_msgids
                else self.pending_strings_list)
            strings_list.add(row)
            row.show_all()

    # ==========================================================
    # ESTADO VISUAL DEL TRANSLATION MANAGER
    # ==========================================================
    def _load_manager_preferences(self):
        """Carga únicamente el estado visual propio del Translation Manager."""
        defaults = {
            "window_size": [700, 500],
            "pot_split_position": 300,
            "translations_split_position": 260,
            "type_column_width": None,
            "string_column_width": None,
        }

        try:
            with open(self._settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)
        except (OSError, json.JSONDecodeError):
            return defaults

        if not isinstance(settings, dict):
            return defaults

        manager_state = settings.get("pot_manager", {})
        if not isinstance(manager_state, dict):
            return defaults

        preferences = defaults.copy()

        window_size = manager_state.get("window_size")
        if (isinstance(window_size, list) and len(window_size) == 2
                and all(type(value) is int and value > 0 for value in window_size)):
            preferences["window_size"] = window_size

        for key in (
            "pot_split_position",
            "translations_split_position",
            "type_column_width",
            "string_column_width",
        ):
            value = manager_state.get(key)
            if type(value) is int and value > 0:
                preferences[key] = value

        return preferences

    def _save_manager_state(self):
        """Guarda sólo la parcela pot_manager sin reformatear settings.json."""
        width, height = self.get_size()

        type_column_width = (self._type_column_width or self.header_type.get_allocated_width())
        string_column_width = (self._string_column_width or self.header_string.get_allocated_width())

        manager_state = {
            "window_size": [width, height],
            "pot_split_position": self.pot_paned.get_position(),
            "translations_split_position": self.translations_paned.get_position(),
            "type_column_width": type_column_width,
            "string_column_width": string_column_width,
        }

        try:
            with open(self._settings_path, "r", encoding="utf-8") as f:
                raw_settings = f.read()
            settings = json.loads(raw_settings)
        except (OSError, json.JSONDecodeError):
            return

        if not isinstance(settings, dict):
            return

        if settings.get("pot_manager") == manager_state:
            return

        manager_block = ('    "pot_manager": {\n'
            f'        "window_size": [{width}, {height}],\n'
            f'        "pot_split_position": {manager_state["pot_split_position"]},\n'
            f'        "translations_split_position": {manager_state["translations_split_position"]},\n'
            f'        "type_column_width": {type_column_width},\n'
            f'        "string_column_width": {string_column_width}\n'
            "    }")

        # Esta parcela no contiene objetos anidados: puede sustituirse como
        # bloque sin alterar formato, orden ni espaciado del resto del archivo.
        match = re.search(
            r'^[ \t]*"pot_manager"\s*:\s*\{.*?^[ \t]*\}',
            raw_settings,
            re.MULTILINE | re.DOTALL)

        if match:
            updated = raw_settings[:match.start()] + manager_block + raw_settings[match.end():]
        else:
            end = raw_settings.rfind("}")
            if end < 0:
                return

            prefix = raw_settings[:end].rstrip()
            separator = "," if prefix and not prefix.endswith("{") else ""
            updated = prefix + separator + "\n" + manager_block + "\n" + raw_settings[end:]

        try:
            with open(self._settings_path, "w", encoding="utf-8") as f:
                f.write(updated)
        except OSError:
            return

    def _on_delete_event(self, widget, event):
        """Captura tamaño y separadores mientras GTK conserva su geometría real."""
        self._save_manager_state()
        return False

    def _create_column_resizer(self, column):
        """Creates a draggable separator for a difference-list column."""
        handle = Gtk.EventBox()
        handle.set_size_request(12, -1)
        handle.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK |
            Gdk.EventMask.BUTTON_RELEASE_MASK |
            Gdk.EventMask.POINTER_MOTION_MASK)

        separator = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        separator.set_margin_start(5)
        separator.set_margin_end(5)
        handle.add(separator)

        handle.connect("realize", self._on_column_resizer_realize)
        handle.connect("button-press-event", self._on_column_resize_press, column)
        handle.connect("motion-notify-event", self._on_column_resize_motion)
        handle.connect("button-release-event", self._on_column_resize_release)

        return handle

    def _on_column_resizer_realize(self, handle):
        """Shows the standard horizontal-resize cursor over a column separator."""
        window = handle.get_window()

        if window:
            cursor = Gdk.Cursor.new_from_name(window.get_display(), "col-resize")
            window.set_cursor(cursor)

    def _initialize_column_widths(self):
        """Converts the initial character widths to resizable pixel widths."""
        self._type_column_width = (
            self._manager_preferences["type_column_width"]
            or self.header_type.get_allocated_width())
        self._string_column_width = (
            self._manager_preferences["string_column_width"]
            or self.header_string.get_allocated_width())

        self.header_type.set_width_chars(-1)
        self.header_string.set_width_chars(-1)

        self._apply_column_widths()
        return False

    def _apply_column_widths(self):
        """Applies the current column widths to the header and all rows."""
        if self._type_column_width is None or self._string_column_width is None:
            return

        self.header_type.set_size_request(self._type_column_width, -1)
        self.header_string.set_size_request(self._string_column_width, -1)

        for row in self.difference_list.get_children():
            type_label = getattr(row, "_wmm_type_label", None)
            string_label = getattr(row, "_wmm_string_label", None)

            if type_label:
                type_label.set_size_request(self._type_column_width, -1)

            if string_label:
                string_label.set_size_request(self._string_column_width, -1)

    def _on_column_resize_press(self, handle, event, column):
        """Starts dragging a column separator."""
        if event.button != 1:
            return False

        width = (self._type_column_width
            if column == "type"
            else self._string_column_width)

        self._column_resize_state = (column, event.x_root, width)
        return True

    def _on_column_resize_motion(self, handle, event):
        """Updates the selected column while its separator is dragged."""
        if not self._column_resize_state:
            return False

        column, start_x, start_width = self._column_resize_state
        width = max(24, int(start_width + event.x_root - start_x))

        if column == "type":
            self._type_column_width = width
        else:
            self._string_column_width = width

        self._apply_column_widths()
        return True

    def _on_column_resize_release(self, handle, event):
        """Finishes a column-resize operation."""
        if event.button != 1:
            return False

        self._column_resize_state = None
        return True

    def _clear_difference_list(self):
        """Removes all rows from the difference list."""
        for row in self.difference_list.get_children():
            self.difference_list.remove(row)

    def _add_difference_row(self, entry_type, text, references):
        """Adds one difference row with clickable source-file links."""
        row = Gtk.ListBoxRow()

        row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row_box.set_border_width(4)
        row.add(row_box)

        type_label = Gtk.Label(label=entry_type)
        type_label.set_xalign(0)
        type_label.set_ellipsize(Pango.EllipsizeMode.END)

        text_label = Gtk.Label(label=text)
        text_label.set_xalign(0)
        text_label.set_ellipsize(Pango.EllipsizeMode.END)
        text_label.set_selectable(True)

        if self._type_column_width is not None:
            type_label.set_size_request(self._type_column_width, -1)

        if self._string_column_width is not None:
            text_label.set_size_request(self._string_column_width, -1)

        # Location conserva la presentación compacta en una sola línea, pero cada
        # número representa directamente la referencia concreta que abrirá.
        location_label = Gtk.Label()
        location_label.set_xalign(0)

        targets = {}
        parts = []
        target_index = 0

        for path, lines in group_source_references(references):
            filename = GLib.markup_escape_text(os.path.basename(path))
            line_links = []

            for line in lines:
                uri = f"wmm-source:{target_index}"
                targets[uri] = (path, line)
                line_links.append(f'<a href="{uri}">{line}</a>')
                target_index += 1

            parts.append(filename + ": " + ", ".join(line_links))

        location_label.set_markup(" / ".join(parts))
        location_label._wmm_source_targets = targets
        location_label.connect("activate-link", self._on_source_link)

        row_box.pack_start(type_label, False, False, 0)
        row_box.pack_start(text_label, False, False, 0)
        row_box.pack_start(location_label, True, True, 0)

        row._wmm_type_label = type_label
        row._wmm_string_label = text_label

        self.difference_list.add(row)
        row.show_all()

    def _open_source_at_line(self, path, line):
        """Abre un archivo fuente en la línea indicada."""
        try:
            platform.open_file(path, capability="open_at_line", line=line)
        except Exception as error:
            self.statusbar.push(0, str(error))

    def _on_source_link(self, label, uri):
        """Abre la referencia fuente asociada al enlace."""
        target = getattr(label, "_wmm_source_targets", {}).get(uri)

        if not target:
            return True

        path, line = target
        self._open_source_at_line(path, line)
        return True

    def _build_pending_source_menu(self, row):
        """Construye el menú contextual de referencias fuente de una cadena."""
        references = getattr(row, "_wmm_references", [])
        grouped = group_source_references(references)

        if not grouped:
            return None

        menu = Gtk.Menu()

        # Cada archivo actúa como cabecera de su propio grupo y debajo se
        # muestran directamente las líneas disponibles como destinos.
        for index, (path, lines) in enumerate(grouped):
            if index:
                menu.append(Gtk.SeparatorMenuItem())

            file_header = Gtk.MenuItem.new_with_label(os.path.basename(path))
            file_header.set_sensitive(False)
            menu.append(file_header)

            for line in lines:
                line_item = Gtk.MenuItem.new_with_label("    " + i18n._("Line") + f" {line}")
                line_item.connect("activate", self._on_pending_source_activate, path, line)
                menu.append(line_item)

        menu.show_all()
        return menu

    def _on_pending_source_activate(self, item, path, line):
        """Abre una referencia concreta seleccionada desde New/Pending."""
        self._open_source_at_line(path, line)

    def update_stats(self):
        current_count = count_pot_entries(POT_OFFICIAL)
        temp_count = count_pot_entries(POT_TEMP) if os.path.exists(POT_TEMP) else 0

        text_current = i18n._("Current") + ": " + str(current_count) + " " + i18n._("strings")
        text_temp = i18n._("Temporary") + ": " + str(temp_count) + " " + i18n._("strings")

        self.lbl_current.set_markup(f"<b>{text_current}</b>")
        self.lbl_temp.set_markup(f"<b>{text_temp}</b>")

    def on_generate_temp(self, widget):
        """Generates the temporary .pot and updates the interface."""
        self.statusbar.push(0, i18n._("Generating temporary .pot..."))
        GLib.idle_add(self._generate_temp)

    def _generate_temp(self):
        # Create cache directory if it doesn't exist
        os.makedirs(CACHE_DIR, exist_ok=True)

        # Cada lenguaje debe pasar por su parser real de xgettext. Las distintas
        # extracciones se acumulan en un único POT temporal mediante --join-existing.
        source_files = { "Python": [], "JavaScript": [], }

        for src_dir in SOURCE_DIRS:
            if not os.path.isdir(src_dir):
                continue

            for root, _, files in os.walk(src_dir):
                for filename in files:
                    extension = os.path.splitext(filename)[1]

                    if extension == ".py":
                        language = "Python"
                    elif extension == ".js":
                        language = "JavaScript"
                    else:
                        continue

                    # Las referencias del POT deben ser portables entre instalaciones:
                    # xgettext resuelve contra PROJECT_ROOT y conserva la ruta relativa.
                    source_files[language].append(
                        os.path.relpath(os.path.join(root, filename), PROJECT_ROOT))

        xgettext = (platform.resolve_gettext_tool("xgettext")
            if hasattr(platform, "resolve_gettext_tool")
            else "xgettext")

        if not xgettext:
            self.statusbar.push(
                0, i18n._("Error generating temporary .pot: ") + "xgettext not found.")
            return False

        try:
            first_pass = True

            for language, files in source_files.items():
                if not files:
                    continue

                cmd = [
                    xgettext,
                    f"--language={language}",
                    "--keyword=_",
                    "--keyword=N_",
                    "--from-code=UTF-8",
                    "--add-location=full",
                    f"--directory={PROJECT_ROOT}",
                    f"--output={POT_TEMP}",
                ]

                # La primera extracción crea el POT; las siguientes incorporan sus
                # cadenas al mismo archivo sin descartar las obtenidas anteriormente.
                if not first_pass:
                    cmd.append("--join-existing")

                cmd.extend(files)

                subprocess.run(cmd, check=True, capture_output=True, text=True)

                first_pass = False

            self.statusbar.push(0, i18n._("Temporary .pot generated successfully."))

        except subprocess.CalledProcessError as error:
            self.statusbar.push(0, i18n._("Error generating temporary .pot: ") + error.stderr)
            return False

        # Compare with official if it exists
        self._clear_difference_list()
        if os.path.exists(POT_OFFICIAL):
            new_entries, removed_entries = compare_pots(
                POT_OFFICIAL, POT_TEMP)

            self._new_entries = list(new_entries)

            text_new = i18n._("New") + ": " + str(len(new_entries))
            text_removed = (i18n._("Removed") + ": " + str(len(removed_entries)))

            self.lbl_new.set_markup(f"<b>{text_new}</b>")
            self.lbl_removed.set_markup(f"<b>{text_removed}</b>")

            temp_entries = parse_pot(POT_TEMP)
            official_entries = parse_pot(POT_OFFICIAL)

            # Las cadenas nuevas sólo existen en el POT temporal; las eliminadas sólo
            # conservan sus referencias en el POT oficial que estamos comparando.
            for entry in new_entries:
                self._add_difference_row(i18n._("New"), entry, temp_entries.get(entry, []))

            for entry in removed_entries:
                self._add_difference_row(i18n._("Removed"), entry, official_entries.get(entry, []))
        else:
            self._new_entries = []
            self.lbl_new.set_markup("<b>" + i18n._("New") + ": --</b>")
            self.lbl_removed.set_markup("<b>" + i18n._("Removed") + ": --</b>")
            self.statusbar.push(0, i18n._("No official .pot to compare."))

        self.update_stats()
        self.btn_apply.set_sensitive(os.path.exists(POT_TEMP))
        return False

    def on_apply_changes(self, widget):
        """Valida y aplica el POT y sus catálogos como una única operación lógica."""
        if not os.path.exists(POT_TEMP):
            self.statusbar.push(0, i18n._("No temporary .pot to apply."))
            return

        os.makedirs(CACHE_DIR, exist_ok=True)

        try:
            with tempfile.TemporaryDirectory(prefix="apply_", dir=CACHE_DIR) as staging_dir:

                merged_dir = os.path.join(staging_dir, "merged")
                backup_dir = os.path.join(staging_dir, "backup")
                os.makedirs(merged_dir)
                os.makedirs(backup_dir)

                # msgmerge trabaja primero sobre copias: ningún catálogo real se
                # modifica hasta que todos hayan sido procesados correctamente.
                staged_catalogs = []

                for language, po_path in self.po_catalogs:
                    staged_path = os.path.join(merged_dir, os.path.basename(po_path))
                    shutil.copy2(po_path, staged_path)
                    staged_catalogs.append((language, po_path, staged_path))

                catalogs_to_sync = [(language, staged_path)
                    for language, _, staged_path in staged_catalogs]

                if not self._sync_po_catalogs(catalogs_to_sync, POT_TEMP):
                    self.update_stats()
                    self.btn_apply.set_sensitive(False)
                    return

                # Conservamos una fotografía interna de todos los originales
                # para poder deshacer también un fallo durante la fase de copia.
                pot_snapshot = None

                if os.path.exists(POT_OFFICIAL):
                    pot_snapshot = os.path.join(backup_dir, os.path.basename(POT_OFFICIAL))
                    shutil.copy2(POT_OFFICIAL, pot_snapshot)

                po_snapshots = []

                for _, po_path, _ in staged_catalogs:
                    snapshot_path = os.path.join(backup_dir, os.path.basename(po_path))
                    shutil.copy2(po_path, snapshot_path)
                    po_snapshots.append((po_path, snapshot_path))

                # El .bak visible conserva la semántica histórica: contiene el
                # POT oficial inmediatamente anterior a la aplicación.
                if pot_snapshot is not None:
                    backup = POT_OFFICIAL + ".bak"
                    shutil.copy2(pot_snapshot, backup)
                    self.statusbar.push(0, i18n._("Backup") + ": " + backup)

                try:
                    shutil.copy2(POT_TEMP, POT_OFFICIAL)

                    for _, po_path, staged_path in staged_catalogs:
                        shutil.copy2(staged_path, po_path)

                except OSError as error:
                    rollback_error = None

                    try:
                        if pot_snapshot is not None:
                            shutil.copy2(pot_snapshot, POT_OFFICIAL)
                        elif os.path.exists(POT_OFFICIAL):
                            os.remove(POT_OFFICIAL)

                        for po_path, snapshot_path in po_snapshots:
                            shutil.copy2(snapshot_path, po_path)

                    except OSError as restore_error:
                        rollback_error = restore_error

                    detail = str(error)
                    if rollback_error is not None:
                        detail += f"; rollback: {rollback_error}"

                    self.statusbar.push(0, i18n._("Error updating") + ": " + detail)
                    self.update_stats()
                    self.btn_apply.set_sensitive(False)
                    return

        except OSError as error:
            self.statusbar.push(0, i18n._("Error updating") + ": " + str(error))
            self.update_stats()
            self.btn_apply.set_sensitive(False)
            return

        self._populate_pending_strings()

        # El POT y los catálogos acaban de cambiar: Search reconstruye su fotografía
        # en memoria para incorporar inmediatamente las nuevas cadenas y referencias.
        self._build_search_index()

        self.statusbar.push(
            0, i18n._("Changes applied successfully."))

        self.update_stats()
        self.btn_apply.set_sensitive(False)

# ==========================================================
# ENTRY POINT
# ==========================================================

if __name__ == "__main__":
    _set_process_identity()
    window = POTManagerWindow()
    window.show_all()
    if hasattr(platform, "present_window"):
        platform.present_window(window)
    Gtk.main()
