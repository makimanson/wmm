#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

"""
WMM - Wallpaper Multi-Monitor Manager

restart_engine.py - Restart Engine Script
===============================
Lanza el motor y notifica al usuario tras un reinicio solicitado desde el panel.
"""

import os
import sys
import time
import subprocess
import fcntl

# Configurar el path del proyecto
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

from wmm_platform.core import PlatformManager
from config_handler import ConfigHandler
from debug_logger import log_event, set_cache_dir
from i18n import _, initialize

def main():
    # Obtener rutas reales desde PlatformManager
    pm = PlatformManager()
    initialize(pm)

    cache_dir = pm.cache_dir
    set_cache_dir(cache_dir)  # Configurar el logger
    ch = ConfigHandler(cache_base_dir=cache_dir, platform=pm)

    pid_path = os.path.join(cache_dir, "pid_main.pid")
    engine_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")

    # 1. Lanzar el nuevo motor
    subprocess.Popen(
        ["python3", engine_path],
        start_new_session=True,
        env=os.environ.copy(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    # 2. Verificar que el nuevo engine mantiene el lock de instancia
    time.sleep(0.9)  # Margen para completar el arranque

    engine_running = False

    if os.path.exists(pid_path):
        try:
            with open(pid_path, "r+") as pid_file:
                try:
                    fcntl.flock(
                        pid_file.fileno(),
                        fcntl.LOCK_EX | fcntl.LOCK_NB
                    )
                except BlockingIOError:
                    # El lock pertenece al engine activo.
                    engine_running = True
                else:
                    # Nadie mantiene el lock: el archivo es sólo un resto obsoleto.
                    fcntl.flock(pid_file.fileno(), fcntl.LOCK_UN)

        except OSError:
            pass

    if engine_running:
        ch._send_notification(
            reason="WMM: " + _("Engine restarted"),
            detail_msg=_("The engine has been restarted successfully."),
            level="info"
        )
        log_event(
            "Engine reiniciado correctamente",
            origin="RESTART",
            level="INFO",
            reason="COMMAND"
        )
    else:
        ch._send_notification(
            reason="WMM: " + _("Engine restart failed"),
            detail_msg=_("The engine could not be started. Check the debug log."),
            level="error"
        )
        log_event(
            "El engine no arrancó tras el reinicio",
            origin="RESTART",
            level="ERROR",
            reason="COMMAND"
        )

if __name__ == "__main__":
    main()
