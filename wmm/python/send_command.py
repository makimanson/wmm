#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
==========================================================
WMM - Send Command
==========================================================

Punto de entrada para el envío de comandos externos al motor.

Este script constituye la API de línea de comandos de WMM y es
utilizado por scripts, paneles, lanzadores, atajos de teclado
y cualquier otro cliente externo basado en Python.

El transporte utilizado es completamente transparente para este
módulo. Los canales de comunicación disponibles son registrados
por la capa del sistema operativo y el comando se envía a través
de la infraestructura de comunicación de WMM.

Uso:

    python3 send_command.py '{"action":"force_rotation"}'
    python3 send_command.py '{"action":"force_rotation"}' "HOTKEY"

==========================================================
"""

import json
import os
import sys

# ----------------------------------------------------------
# Configuración del entorno
# ----------------------------------------------------------

# Añadir la raíz del proyecto al path de Python.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

# ----------------------------------------------------------
# Módulos del proyecto
# ----------------------------------------------------------

from debug_logger import log_event, set_cache_dir
from wmm_platform.core import PlatformManager


def main():
    """
    Procesa un comando externo y lo envía al motor de WMM.

    El script verifica que el motor esté en ejecución, registra
    los canales de comunicación soportados por el sistema
    operativo y delega el envío al gestor de comunicaciones.
    """

    # ------------------------------------------------------
    # Validar argumentos
    # ------------------------------------------------------

    if len(sys.argv) < 2:
        log_event("falta el comando JSON", origin="SEND_COMM", level="ERROR", reason="COMMAND")
        sys.exit(1)

    try:
        command = json.loads(sys.argv[1])
    except json.JSONDecodeError as e:
        log_event(f"JSON inválido: {e}", origin="SEND_COMM", level="ERROR", reason="COMMAND")
        sys.exit(1)

    # ------------------------------------------------------
    # Inicializar plataforma
    # ------------------------------------------------------

    pm = PlatformManager()

    # Inicializar el sistema de logging.
    set_cache_dir(pm.cache_dir)

    # Verificar que el motor está en ejecución.
    pid_path = os.path.join(pm.cache_dir, "pid_main.pid")

    if not os.path.exists(pid_path):
        log_event("motor no está corriendo", origin="SEND_COMM", level="ERROR", reason="COMMAND")
        sys.exit(1)

    # ------------------------------------------------------
    # Envío del comando
    # ------------------------------------------------------

    try:

        # Registrar los canales soportados por el sistema operativo.
        pm.init_channels()

        # Delegar el envío a la infraestructura de comunicación.
        pm.send_command(command)

        source = sys.argv[2] if len(sys.argv) > 2 else None
        source_str = f" ({source})" if source else ""

        log_event(f"comando enviado: {command.get('action', 'unknown')}{source_str}", origin="SEND_COMM", level="INFO", reason="COMMAND")

    except Exception as e:
        log_event(f"error al enviar comando: {e}", origin="SEND_COMM", level="ERROR", reason="COMMAND")
        sys.exit(1)


if __name__ == "__main__":
    main()
