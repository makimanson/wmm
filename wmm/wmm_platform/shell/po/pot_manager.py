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
generates a temporary .pot in ~/.cache/wmm/pot_manager/ and
allows comparing it with the current .pot before applying changes.
"""

import ast
import os
import sys
import subprocess
import shutil
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
CACHE_DIR = os.path.join(GLib.get_user_cache_dir(), "wmm", "pot_manager")
POT_TEMP = os.path.join(CACHE_DIR, "wmm_temp.pot")

SOURCE_DIRS = [
    os.path.join(PROJECT_ROOT, "python"),
    os.path.join(PROJECT_ROOT, "wmm_platform", "shell"),
]

TYPE_COLUMN_DEFAULT_CHARS = 12
STRING_COLUMN_DEFAULT_CHARS = 32

# ==========================================================
# BASIC .POT FILE PARSING
# ==========================================================

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


def parse_pot_entries(pot_path):
    """Returns the msgid entries from a .pot file."""
    return list(parse_pot(pot_path).keys())


def format_locations(references):
    """Formats POT references using only filename and line numbers."""
    grouped = {}

    for reference in references:
        path, separator, line = reference.rpartition(":")

        if not separator:
            filename = os.path.basename(reference)
            grouped.setdefault(filename, [])
            continue

        filename = os.path.basename(path)
        lines = grouped.setdefault(filename, [])

        if line not in lines:
            lines.append(line)

    parts = []

    for filename, lines in grouped.items():
        if lines:
            parts.append(filename + ":" + ", ".join(lines))
        else:
            parts.append(filename)

    return " / ".join(parts)

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
    """
    Compares two .pot files and returns two lists:
    - new_entries: entries present in new_path but not in old_path.
    - modified: entries whose msgid exists in both but has changed.
    """
    old_entries = set(parse_pot_entries(old_path))
    new_entries = parse_pot_entries(new_path)

    new_strings = [e for e in new_entries if e not in old_entries]
    # In a .pot, msgid is the key; if changed, it's a new entry.
    # "Modified" in the strict sense would require comparing msgstr, not available.
    # We simplify: "new" are the ones not in old, "modified" are those in old but not in new (removed).
    # For this tool, we focus on "new" and "removed" as informative.
    return new_strings, []


# ==========================================================
# GRAPHICAL INTERFACE
# ==========================================================

class POTManagerWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="WMM - " + i18n._("Translation Manager"))
        self.set_default_size(700, 500)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.connect("destroy", Gtk.main_quit)

        # Main container
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        main_box.set_border_width(12)
        self.add(main_box)

        # --- Toolbar ---
        toolbar = Gtk.Box(spacing=6)
        main_box.pack_start(toolbar, False, False, 0)

        self.btn_generate = Gtk.Button.new_with_label(i18n._("Generate temporary .pot"))
        self.btn_generate.connect("clicked", self.on_generate_temp)
        toolbar.pack_start(self.btn_generate, False, False, 0)

        self.btn_apply = Gtk.Button.new_with_label(i18n._("Apply changes"))
        self.btn_apply.set_sensitive(False)
        self.btn_apply.connect("clicked", self.on_apply_changes)
        toolbar.pack_end(self.btn_apply, False, False, 0)

        # --- Statistics panel ---
        stats_box = Gtk.Box(spacing=20)
        main_box.pack_start(stats_box, False, False, 6)

        self.lbl_current = Gtk.Label()
        self.lbl_temp = Gtk.Label()
        self.lbl_new = Gtk.Label()
        self.lbl_modified = Gtk.Label()

        for lbl, text in [
            (self.lbl_current, i18n._("Current") + ": --"),
            (self.lbl_temp, i18n._("Temporary") + ": --"),
            (self.lbl_new, i18n._("New") + ": --"),
            (self.lbl_modified, i18n._("Modified") + ": --")
        ]:
            lbl.set_markup(f"<b>{text}</b>")
            stats_box.pack_start(lbl, False, False, 0)

        # --- Difference list ---
        difference_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=4
        )
        main_box.pack_start(difference_box, True, True, 0)

        # Header
        self._type_column_width = None
        self._string_column_width = None
        self._column_resize_state = None

        header = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=0
        )
        header.set_margin_start(4)
        header.set_margin_end(4)

        self.header_type = Gtk.Label()
        self.header_type.set_markup(
            "<b>" + GLib.markup_escape_text(i18n._("Type")) + "</b>"
        )
        self.header_type.set_xalign(0)
        self.header_type.set_width_chars(TYPE_COLUMN_DEFAULT_CHARS)
        self.header_type.set_ellipsize(Pango.EllipsizeMode.END)

        self.header_string = Gtk.Label()
        self.header_string.set_markup(
            "<b>" + GLib.markup_escape_text(i18n._("String")) + "</b>"
        )
        self.header_string.set_xalign(0)
        self.header_string.set_width_chars(STRING_COLUMN_DEFAULT_CHARS)
        self.header_string.set_ellipsize(Pango.EllipsizeMode.END)

        header_location = Gtk.Label()
        header_location.set_markup(
            "<b>" + GLib.markup_escape_text(i18n._("Location")) + "</b>"
        )
        header_location.set_xalign(0)

        header.pack_start(self.header_type, False, False, 0)
        header.pack_start(self._create_column_resizer("type"), False, False, 0)
        header.pack_start(self.header_string, False, False, 0)
        header.pack_start(self._create_column_resizer("string"), False, False, 0)
        header.pack_start(header_location, True, True, 0)

        difference_box.pack_start(header, False, False, 0)

        GLib.idle_add(self._initialize_column_widths)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        difference_box.pack_start(scroll, True, True, 0)

        self.difference_list = Gtk.ListBox()
        self.difference_list.set_selection_mode(Gtk.SelectionMode.NONE)
        scroll.add(self.difference_list)

        # --- Status bar ---
        self.statusbar = Gtk.Statusbar()
        main_box.pack_start(self.statusbar, False, False, 0)
        self.statusbar.push(0, i18n._("Ready."))

        # Load initial statistics
        self.update_stats()

    def _create_column_resizer(self, column):
        """Creates a draggable separator for a difference-list column."""
        handle = Gtk.EventBox()
        handle.set_size_request(12, -1)
        handle.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK |
            Gdk.EventMask.BUTTON_RELEASE_MASK |
            Gdk.EventMask.POINTER_MOTION_MASK
        )

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
            cursor = Gdk.Cursor.new_from_name(
                window.get_display(),
                "col-resize"
            )
            window.set_cursor(cursor)


    def _initialize_column_widths(self):
        """Converts the initial character widths to resizable pixel widths."""
        self._type_column_width = self.header_type.get_allocated_width()
        self._string_column_width = self.header_string.get_allocated_width()

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

        width = (
            self._type_column_width
            if column == "type"
            else self._string_column_width
        )

        self._column_resize_state = (
            column,
            event.x_root,
            width
        )
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

        row_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=12
        )
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

        location_label = Gtk.Label()
        location_label.set_xalign(0)

        targets = {}
        parts = []

        for index, (path, lines) in enumerate(group_source_references(references)):
            uri = f"wmm-source:{index}"
            targets[uri] = (path, lines[0])

            filename = GLib.markup_escape_text(os.path.basename(path))
            line_text = ", ".join(str(line) for line in lines)

            parts.append(
                f'<a href="{uri}">{filename}</a>:{line_text}'
            )

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

    def _on_source_link(self, label, uri):
        """Opens a source file at its first associated line."""
        target = getattr(label, "_wmm_source_targets", {}).get(uri)

        if not target:
            return True

        path, line = target

        try:
            platform.open_file(
                path,
                capability="open_at_line",
                line=line
            )
        except Exception as error:
            self.statusbar.push(0, str(error))

        return True

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

        # Build xgettext command
        cmd = [
            "xgettext",
            "--language=Python",
            "--keyword=_",
            "--keyword=N_",
            "--from-code=UTF-8",
            "--add-location=full",
            f"--output={POT_TEMP}"
        ]
        # Add source files (.py)
        for src_dir in SOURCE_DIRS:
            if os.path.isdir(src_dir):
                for root, dirs, files in os.walk(src_dir):
                    for f in files:
                        if f.endswith(".py") or f.endswith(".js"):
                            cmd.append(os.path.join(root, f))

        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            self.statusbar.push(0, i18n._("Temporary .pot generated successfully."))
        except subprocess.CalledProcessError as e:
            self.statusbar.push(0, i18n._("Error generating temporary .pot: ") + e.stderr)
            return False

        # Compare with official if it exists
        self._clear_difference_list()
        if os.path.exists(POT_OFFICIAL):
            new_entries, _ = compare_pots(POT_OFFICIAL, POT_TEMP)

            text_new = i18n._("New") + ": " + str(len(new_entries))
            text_modified = i18n._("Modified") + ": 0"

            self.lbl_new.set_markup(f"<b>{text_new}</b>")
            self.lbl_modified.set_markup(f"<b>{text_modified}</b>")

            temp_entries = parse_pot(POT_TEMP)

            for entry in new_entries:
                self._add_difference_row(i18n._("New"), entry, temp_entries.get(entry, []))
        else:
            self.lbl_new.set_markup("<b>" + i18n._("New") + ": --</b>")
            self.lbl_modified.set_markup("<b>" + i18n._("Modified") + ": --</b>")
            self.statusbar.push(0, i18n._("No official .pot to compare."))

        self.update_stats()
        self.btn_apply.set_sensitive(os.path.exists(POT_TEMP))
        return False

    def on_apply_changes(self, widget):
        """Applies changes: renames official and copies temporary."""
        if not os.path.exists(POT_TEMP):
            self.statusbar.push(0, i18n._("No temporary .pot to apply."))
            return

        # Backup official if it exists
        if os.path.exists(POT_OFFICIAL):
            backup = POT_OFFICIAL + ".bak"
            shutil.copy2(POT_OFFICIAL, backup)
            self.statusbar.push(0, i18n._("Backup") + ": " + backup)

        # Replace official with temporary
        shutil.copy2(POT_TEMP, POT_OFFICIAL)
        self.statusbar.push(0, i18n._("Changes applied successfully."))

        # Update interface
        self.update_stats()
        self.btn_apply.set_sensitive(False)


# ==========================================================
# ENTRY POINT
# ==========================================================

if __name__ == "__main__":
    window = POTManagerWindow()
    window.show_all()
    Gtk.main()
