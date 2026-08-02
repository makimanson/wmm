#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
WMM - Restart Engine Script
Lanza el motor y notifica al usuario tras un reinicio solicitado desde el panel.
"""

import os
import sys
import time
import subprocess

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

    # 1. Verificar que el PID antiguo ya no existe (con margen mínimo)
    if os.path.exists(pid_path):
        time.sleep(0.3)  # Margen de seguridad mínimo
        if os.path.exists(pid_path):
            try:
                os.remove(pid_path)
            except OSError:
                pass

    # 2. Lanzar el nuevo motor
    subprocess.Popen(
        ["python3", engine_path],
        start_new_session=True,
        env=os.environ.copy(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    # 3. Verificar que arrancó
    time.sleep(0.3)
    if os.path.exists(pid_path):
        try:
            with open(pid_path, "r") as f:
                new_pid = int(f.read().strip())
            os.kill(new_pid, 0)
            ch._send_notification(
                reason="WMM: " + _("Engine restarted"),
                detail_msg=_("The engine has been restarted successfully."),
                level="info"
            )
            log_event("Motor reiniciado correctamente", origin="RESTART", level="INFO", reason="COMMAND")
        except (FileNotFoundError, ProcessLookupError, ValueError):
            ch._send_notification(
                reason="WMM: " + _("Engine restart failed"),
                detail_msg=_("The engine could not be started. Check the debug log."),
                level="error"
            )
            log_event("El motor no arrancó tras el reinicio", origin="RESTART", level="ERROR", reason="COMMAND")
    else:
        ch._send_notification(
            reason="WMM: " + _("Engine restart failed"),
            detail_msg=_("The engine could not be started. Check the debug log."),
            level="error"
        )
        log_event("PID no encontrado tras lanzar el motor", origin="RESTART", level="ERROR", reason="COMMAND")

if __name__ == "__main__":
    main()
