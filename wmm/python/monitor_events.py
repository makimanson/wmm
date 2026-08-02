#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
WMM - Monitor Events Engine
============================
Centraliza la monitorización de cambios de hardware (conexión/desconexión de monitores).

Este módulo se encarga de:
    - Detectar el entorno (escritorio, SO) y elegir la estrategia de monitorización adecuada.
    - Iniciar la escucha de eventos (D-Bus, Gdk, etc.).
    - Notificar al motor cuando se produce un cambio.

No depende de GTK ni de la lógica de negocio. Solo usa los módulos de plataforma
para implementar la monitorización específica de cada escritorio.

Flujo típico:
    1. main.py llama a monitor_events.init_monitor_events(callback).
    2. El módulo decide qué estrategia usar (GNOME D-Bus, fallback Gdk).
    3. Inicia la escucha y llama al callback cuando se detecta un cambio.

Autor: WMM Project
Fecha: 2026-08-02
"""

from debug_logger import log_event


# ==========================================================
# 1. Estrategia para GNOME (D-Bus)
# ==========================================================
def init_gnome_events(callback):
    """
    Inicia la monitorización de hardware en GNOME usando D-Bus
    (org.gnome.Mutter.DisplayConfig).
    """
    try:
        import dbus
        bus = dbus.SessionBus()
        display_config = bus.get_object(
            "org.gnome.Mutter.DisplayConfig",
            "/org/gnome/Mutter/DisplayConfig"
        )

        def on_monitors_changed(*args):
            log_event("Señal MonitorsChanged recibida desde D-Bus", origin="MON_EVENT", level="DEBUG", reason="HARDWARE")
            callback("hardware_changed")

        display_config.connect_to_signal("MonitorsChanged", on_monitors_changed)
        log_event("Monitor D-Bus de GNOME iniciado correctamente", origin="MON_EVENT", level="INFO", reason="D-BUS")
        return True
    except Exception as e:
        log_event(f"Error al iniciar monitor D-Bus de GNOME: {e}", origin="MON_EVENT", level="ERROR", reason="D-BUS")
        return False


# ==========================================================
# 2. Estrategia de fallback (Gdk signals)
# ==========================================================
def init_gdk_events(callback):
    """
    Inicia la monitorización de hardware usando señales de Gdk.
    Es el fallback genérico para escritorios sin método específico.
    """
    try:
        import gi
        gi.require_version('Gdk', '3.0')
        from gi.repository import Gdk

        display = Gdk.Display.get_default()
        if not display:
            log_event("No se pudo obtener Gdk.Display para monitorización", origin="MON_EVENT", level="WARN", reason="HARDWARE")
            return False

        def _on_monitor_event(display, monitor):
            callback("hardware_changed")

        display.connect("monitor-added", _on_monitor_event)
        display.connect("monitor-removed", _on_monitor_event)

        log_event("Monitorización Gdk iniciada (fallback)", origin="MON_EVENT", level="INFO", reason="HARDWARE")
        return True

    except Exception as e:
        log_event(f"Error al iniciar monitorización Gdk: {e}", origin="MON_EVENT", level="ERROR", reason="HARDWARE")
        return False


# ==========================================================
# 3. Orquestador principal
# ==========================================================
def init_monitor_events(callback):
    """
    Inicia la monitorización de cambios de hardware usando la mejor estrategia disponible.
    Estrategias (por orden de prioridad):
        1. GNOME → init_gnome_events() (D-Bus)
        2. Otros → init_gdk_events() (fallback)
        3. Fallback → False
    """
    from wmm_platform.core import PlatformManager
    pm = PlatformManager()
    desktop = getattr(pm, 'desktop', None)

    # 1. GNOME: D-Bus
    if desktop == "gnome":
        log_event("Intentando monitorización GNOME vía D-Bus", origin="MON_EVENT", level="DEBUG", reason="HARDWARE")
        if init_gnome_events(callback):
            return True
        else:
            log_event("D-Bus falló, usando fallback Gdk", origin="MON_EVENT", level="WARN", reason="HARDWARE")

    # 2. Fallback: Gdk signals
    log_event("Usando monitorización Gdk (fallback)", origin="MON_EVENT", level="DEBUG", reason="HARDWARE")
    return init_gdk_events(callback)
