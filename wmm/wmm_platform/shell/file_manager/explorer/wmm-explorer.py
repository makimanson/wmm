#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

"""
WMM - Wallpaper Multi-Monitor Manager

wmm-explorer.py - Adaptador del menú contextual del Explorador de Windows.
Recibe acciones de imagen o escritorio y reutiliza send_command.py.
"""

import json
import os
from pathlib import Path
import runpy
import sys


def main():
    """Convierte la selección o el contexto del escritorio al contrato de WMM."""
    image_actions = {"shell_add_favorite", "shell_send_to_monitor", "shell_spanned_image"}
    desktop_actions = {"shell_add_favorite_current", "shell_spanned_current"}
    if len(sys.argv) == 3 and sys.argv[1] in image_actions:
        action, image_path = sys.argv[1:]
        if not os.path.isfile(image_path):
            raise SystemExit(1)
        command = {"action": action, "image_path": image_path}
    elif len(sys.argv) == 2 and sys.argv[1] in desktop_actions:
        # La posición pertenece al clic que abrió el menú, no al puntero
        # cuando se selecciona el subcomando. La completa el receptor Win32.
        command = {"action": sys.argv[1], "explorer_desktop": True}
    else:
        raise SystemExit(1)

    # Topología instalada: wmm_platform/shell/file_manager/explorer/wmm-explorer.py.
    app_root = Path(__file__).resolve().parents[4]
    sender = app_root / "python" / "send_command.py"
    if not sender.is_file():
        raise SystemExit(1)

    # pythonw no crea consola. Los imports del cliente común viven en python/;
    # run_path por sí solo no incorpora ese directorio a sys.path.
    sys.path.insert(0, str(sender.parent))
    payload = json.dumps(command, ensure_ascii=False)
    sys.argv = [str(sender), payload, "EXPLORER"]

    if getattr(sys, "frozen", False):
        # En PyInstaller, send_command vive en PYZ y no como archivo físico.
        runpy.run_module("send_command", run_name="__main__")
    else:
        runpy.run_path(str(sender), run_name="__main__")

if __name__ == "__main__":
    main()