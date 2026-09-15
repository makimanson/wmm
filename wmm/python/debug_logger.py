#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

"""
WMM - Wallpaper Multi-Monitor Manager

debug_logger.py – Módulo centralizado de logging para depuración.
==========================================================
PROPÓSITO:
    Proporcionar un sistema de logging simple, seguro y unificado para
    todos los componentes de WMM (motor, panel, scripts auxiliares, etc.).
    Los eventos se escriben en un único archivo en cache_dir con bloqueo
    atómico para evitar líneas mutiladas por concurrencia.

USO:
    from debug_logger import log_event, read_log

    log_event("Mensaje de prueba", origin="MOTOR", level="INFO")
    contenido = read_log()

FORMATO DE LÍNEA:
    [YYYY-MM-DD HH:MM:SS] [ORIGEN] [NIVEL] mensaje

AUTOR:
    WMM Project
"""

import os
import sys
from datetime import datetime
# ----------------------------------------------------------------------
# BLOQUEO DE ARCHIVOS
# ----------------------------------------------------------------------
from wmm_platform.file_utils import lock_file as _lock_file, unlock_file as _unlock_file

# ----------------------------------------------------------------------
# CONSTANTES
# ----------------------------------------------------------------------

# Niveles de log permitidos
VALID_LEVELS = ("DEBUG", "INFO", "WARN", "ERROR")

# Límite de líneas del log (truncado perezoso)
MAX_LOG_LINES = 500          # Número de líneas que se conservan al truncar
TRUNCATE_THRESHOLD = 1000    # Umbral que dispara el truncado

# RUNTIME-02: el log se mantiene deliberadamente pequeño y acotado.
# La relectura completa hasta este umbral fue medida y se acepta frente
# a introducir contadores auxiliares o estado compartido entre procesos.

# ----------------------------------------------------------------------
# RUTAS DEL LOG (configurables externamente)
# ----------------------------------------------------------------------

# Estas variables se inicializan a None y se configuran mediante
# set_cache_dir(), llamada desde ConfigHandler al iniciar.
# Así el logger no depende de rutas hardcodeadas y se adapta al SO.
_LOG_PATH = None

def set_cache_dir(cache_dir):
    """
    Configura la ruta del archivo de log.
    Se llama desde ConfigHandler una vez que la plataforma ha
    determinado la ruta de caché correcta para el SO actual.
    """
    global _LOG_PATH
    os.makedirs(cache_dir, exist_ok=True)
    _LOG_PATH = os.path.join(cache_dir, "debug.log")

# ----------------------------------------------------------------------
# FUNCIONES PÚBLICAS
# ----------------------------------------------------------------------

def log_event(message, origin="UNKNOW", level="INFO", reason="GENERIC"):
    """
    Escribe un evento en el archivo de log centralizado.

    Args:
        message (str): Mensaje descriptivo del evento.
        origin (str):  Componente que genera el evento (ej. 'MOTOR', 'PANEL',
                       'SHELL'). Útil para filtrar en el visor.
        level (str):   Nivel del evento. Debe ser uno de: DEBUG, INFO, WARN,
                       ERROR. Por defecto: INFO.

    Seguridad:
        - Crea el directorio de caché si no existe.
        - Usa bloqueo exclusivo (si está disponible) durante la escritura,
          garantizando que las líneas se escriban completas incluso si
          varios procesos escriben simultáneamente.
        - Captura cualquier excepción y la imprime en stderr para no
          interrumpir el flujo del componente llamante.

    Ejemplo:
        log_event("Rotación manual solicitada", origin="MOTOR", level="INFO")
    """
    # Si el logger aún no ha sido configurado, no escribir
    if not _LOG_PATH:
        return

    # Validar nivel
    if level not in VALID_LEVELS:
        level = "INFO"

    # Construir línea con formato estándar
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{origin}] [{level}] [{reason}] {message}\n"

    # Asegurar que el directorio existe
    os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)

    try:
        with open(_LOG_PATH, "a+", encoding="utf-8") as f:
            _lock_file(f)
            # Escritura y mantenimiento forman una única sección crítica:
            # ningún otro proceso puede escribir mientras se evalúa o trunca el log.
            f.write(line)
            f.flush()  # Forzar escritura inmediata al disco
            # Truncado perezoso: si el archivo supera el umbral, conservar solo las últimas líneas
            # RUNTIME-02: esta relectura es intencionada. debug.log sigue siendo la
            # única autoridad global; las pruebas multiproceso validaron este modelo
            # y un contador auxiliar resultó más complejo sin mejora runtime suficiente.
            f.seek(0)
            lines = f.readlines()
            if len(lines) > TRUNCATE_THRESHOLD:
                f.seek(0)
                f.truncate()
                f.writelines(lines[-MAX_LOG_LINES:])
                print(f"[DEBUG_LOGGER] Log truncado: {len(lines)} -> {MAX_LOG_LINES} líneas", file=sys.stderr)
            _unlock_file(f)
    except Exception as e:
        # Fallback silencioso: no queremos que un fallo de logging
        # interrumpa el componente que nos llama.
        print(f"[DEBUG_LOGGER] Error al escribir log: {e}", file=sys.stderr)

def read_log():
    """
    Lee el contenido completo del archivo de log.

    Returns:
        str: Contenido del archivo de log, o cadena vacía si no existe
             o no se puede leer.
    """
    if not os.path.exists(_LOG_PATH):
        return ""
    try:
        with open(_LOG_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"[DEBUG_LOGGER] Error al leer log: {e}", file=sys.stderr)
        return ""

def get_log_path():
    """
    Retorna la ruta completa al archivo de log.

    Returns:
        str: Ruta absoluta al archivo debug.log en el directorio de caché.
    """
    return _LOG_PATH

def clear_log():
    """
    Vacía el contenido del archivo de log.

    Útil al iniciar una nueva sesión de depuración para no arrastrar
    eventos de sesiones anteriores.
    """
    try:
        os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)

        # Abrir sin truncar: Clear debe respetar la misma exclusión
        # que los escritores antes de modificar el contenido del log.
        with open(_LOG_PATH, "a+", encoding="utf-8") as f:
            _lock_file(f)

            # El truncado sólo ocurre después de adquirir el lock:
            # ningún log_event() activo puede perder su escritura por carrera.
            f.seek(0)
            f.truncate(0)
            f.flush()

            _unlock_file(f)

    except Exception as e:
        print(f"[DEBUG_LOGGER] Error al limpiar log: {e}", file=sys.stderr)


# ----------------------------------------------------------------------
# DIAGNÓSTICO RÁPIDO (solo si se ejecuta directamente)
# ----------------------------------------------------------------------
if __name__ == "__main__":
    print("═" * 50)
    print("  WMM DEBUG LOGGER")
    print("═" * 50)

    print(f"\n[CONFIG]")
    print(f"  Ruta del log: {get_log_path()}")

    print(f"\n[CONTENIDO DEL LOG]")
    print(read_log() or "(vacío)")

    print("\n" + "═" * 50)
    print("  Lectura completada.")
    print("═" * 50 + "\n")
