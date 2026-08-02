#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
WMM - Translation Manager (POT Manager)
========================================
Graphical tool to analyze, compare and update
the project's wmm.pot file.

Uses xgettext to extract strings from .py and .js files,
generates a temporary .pot in ~/.cache/wmm/pot_manager/ and
allows comparing it with the current .pot before applying changes.
"""

import os
import sys
import subprocess
import shutil
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

# ----------------------------------------------------------
# PATH CONFIGURATION AND TRANSLATION IMPORT
# ----------------------------------------------------------

# Add python/ to path to import i18n and PlatformManager
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, os.path.join(_PROJECT_ROOT, "python"))

from wmm_platform.core import PlatformManager
import i18n

# Inicializar plataforma y traducciones
platform = PlatformManager()
i18n.initialize(platform)

# Use platform paths instead of hardcoded ones
PROJECT_ROOT = platform.app_dir  # Root of the installed project
POT_OFFICIAL = os.path.join(PROJECT_ROOT, "po", "wmm.pot")
CACHE_DIR = os.path.join(GLib.get_user_cache_dir(), "wmm", "pot_manager")
POT_TEMP = os.path.join(CACHE_DIR, "wmm_temp.pot")

SOURCE_DIRS = [
    os.path.join(PROJECT_ROOT, "python"),
    os.path.join(PROJECT_ROOT, "wmm_platform", "shell"),
    os.path.join(PROJECT_ROOT, "po"),
]

# ==========================================================
# BASIC .POT FILE PARSING
# ==========================================================

def parse_pot_entries(pot_path):
    """
    Extracts msgid entries from a .pot file.
    Returns a list of strings (the original msgids).
    """
    entries = []
    if not os.path.exists(pot_path):
        return entries

    with open(pot_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    current_msgid = None
    for line in lines:
        if line.startswith("msgid "):
            current_msgid = line[6:].strip().strip('"')
            if current_msgid:
                entries.append(current_msgid)
            current_msgid = None
        elif line.startswith('"') and current_msgid is not None:
            current_msgid += line.strip().strip('"')

    return entries


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
            (self.lbl_current, i18n._("Current: --")),
            (self.lbl_temp, i18n._("Temporary: --")),
            (self.lbl_new, i18n._("New: --")),
            (self.lbl_modified, i18n._("Modified: --"))
        ]:
            lbl.set_markup(f"<b>{text}</b>")
            stats_box.pack_start(lbl, False, False, 0)

        # --- Difference list ---
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        main_box.pack_start(scroll, True, True, 0)

        self.store = Gtk.ListStore(str, str)  # (Type, String)
        self.treeview = Gtk.TreeView(model=self.store)

        renderer_type = Gtk.CellRendererText()
        col_type = Gtk.TreeViewColumn(i18n._("Type"), renderer_type, text=0)
        self.treeview.append_column(col_type)

        renderer_text = Gtk.CellRendererText()
        col_text = Gtk.TreeViewColumn(i18n._("String"), renderer_text, text=1)
        self.treeview.append_column(col_text)

        scroll.add(self.treeview)

        # --- Status bar ---
        self.statusbar = Gtk.Statusbar()
        main_box.pack_start(self.statusbar, False, False, 0)
        self.statusbar.push(0, i18n._("Ready."))

        # Load initial statistics
        self.update_stats()

    def update_stats(self):
        current_count = count_pot_entries(POT_OFFICIAL)
        temp_count = count_pot_entries(POT_TEMP) if os.path.exists(POT_TEMP) else 0
        text_current = i18n._("Current: {} strings").format(current_count)
        text_temp = i18n._("Temporary: {} strings").format(temp_count)
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
        self.store.clear()
        if os.path.exists(POT_OFFICIAL):
            new_entries, _ = compare_pots(POT_OFFICIAL, POT_TEMP)
            text_new = i18n._("New: {}").format(len(new_entries))
            text_modified = i18n._("Modified: {}").format(0)
            self.lbl_new.set_markup(f"<b>{text_new}</b>")
            self.lbl_modified.set_markup(f"<b>{text_modified}</b>")
            for entry in new_entries:
                self.store.append([i18n._("New"), entry])
        else:
            self.lbl_new.set_markup("<b>" + i18n._("New: --") + "</b>")
            self.lbl_modified.set_markup("<b>" + i18n._("Modified: --") + "</b>")
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
            self.statusbar.push(0, i18n._("Backup: ") + backup)

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
