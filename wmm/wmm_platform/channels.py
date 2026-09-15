#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

"""
WMM - Wallpaper Multi-Monitor Manager

channels.py – Gestor central de canales de comunicación.
==========================================================
Centraliza los distintos mecanismos de intercambio de comandos entre los
componentes de WMM.
Cada canal implementa una interfaz común basada en dos operaciones:
    - send(command)
    - start_receiving_commands(callback)
permitiendo seleccionar el mecanismo de transporte más adecuado para
cada escenario sin modificar la lógica de los componentes que lo utilizan.
"""
import json
import os
import time
import dbus
import dbus.service

from gi.repository import Gio
from debug_logger import log_event


# ----------------------------------------------------------
# Registro de canales disponibles
# ----------------------------------------------------------

_channels = {}

def register_channel(name, channel):
    """Registra un canal de comunicación disponible."""
    _channels[name] = channel

def emit_busy_changed(busy):
    """
    Publica el estado busy en los canales que soportan estado reactivo.

    La autoridad del estado pertenece al engine. Los canales únicamente
    transportan su valor hacia los clientes que puedan consumirlo.
    """
    for channel in _channels.values():
        try:
            if hasattr(channel, "emit_busy_changed"):
                channel.emit_busy_changed(bool(busy))
        except Exception as e:
            log_event(f"{channel.__class__.__name__}: {e}",
                origin="CHANNELS", level="ERROR", reason="COMMAND")

# ==========================================================
# COMUNICACIÓN AGNÓSTICA
# ==========================================================

def send_command(command):
    """
    Envía un comando a través de todos los canales registrados.

    Cada canal decide de forma autónoma si implementa el envío
    del comando o si simplemente lo ignora.

    Esta función no conoce protocolos, escritorios ni sistemas
    operativos. Su única responsabilidad es delegar el envío en
    todos los adaptadores de comunicación disponibles.

    De este modo WMM permanece completamente agnóstico al medio
    de transporte utilizado por cada cliente.
    """

    for channel in _channels.values():
        try:
            channel.send(command)
        except Exception as e:
            log_event(f"{channel.__class__.__name__}: {e}",
                origin="CHANNELS", level="ERROR", reason="COMMAND")


def start_receiving_commands(command_callback):
    """
    Activa la recepción de comandos en todos los canales registrados.

    Cada canal inicia, si procede, su propio mecanismo de escucha
    (monitor de archivos, D-Bus, sockets, etc.) y reenvía los
    comandos recibidos al callback común del motor.

    Todos los canales permanecen activos simultáneamente, permitiendo
    que distintos clientes utilicen protocolos diferentes sin que el
    motor conozca ni dependa de ellos.
    """

    for channel in _channels.values():
        try:
            channel.start_receiving_commands(command_callback)
        except Exception as e:
            log_event(f"{channel.__class__.__name__}: {e}",
                origin="CHANNELS", level="ERROR", reason="COMMAND")

# ==========================================================
# CANAL FILE (commands.json)
# ==========================================================

class FileChannel:
    """
    Canal de comunicación basado en commands.json.

    Este canal implementa el mecanismo de comunicación tradicional de WMM
    mediante un archivo JSON compartido.

    Se utiliza principalmente para la comunicación entre el motor,
    el panel de configuración y los scripts auxiliares, garantizando
    compatibilidad con todos los escritorios soportados.

    Implementa la interfaz común de canales mediante los métodos:

        - send(command)
        - start_receiving_commands(callback)
    """

    def __init__(self):
        """
        Inicializa el canal de comunicación basado en archivos.

        Actualmente obtiene internamente la ubicación de commands.json
        a partir de la estructura estándar del proyecto.

        NOTA:
            Esta resolución de ruta es provisional. En una futura revisión
            arquitectónica, la ruta será suministrada por el componente
            responsable de la estructura del proyecto, evitando que este
            canal conozca dicha organización.
        """
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._path = os.path.join(project_root, "data", "commands.json")
        self._monitor = None

    def send(self, command):
        """
        Envía un comando escribiéndolo en commands.json.

        Args:
            command: Diccionario con la orden a transmitir.
        """
        with open(self._path, "w") as f:
            json.dump(command, f)

    def start_receiving_commands(self, callback):
        """
        Inicia la monitorización de commands.json.

        Cada vez que se detecta un nuevo comando válido, éste se entrega
        al callback recibido y el archivo vuelve a quedar vacío para
        evitar procesados duplicados.

        Args:
            callback: Función que recibirá (order, action_data).
        """

        if not os.path.exists(self._path):
            with open(self._path, "w") as f:
                json.dump({}, f)

        commands_file = Gio.File.new_for_path(self._path)
        self._monitor = commands_file.monitor_file(Gio.FileMonitorFlags.NONE, None)

        def on_file_changed(monitor, file, other_file, event_type):
            try:

                if event_type != Gio.FileMonitorEvent.CHANGES_DONE_HINT:
                    return
                with open(self._path, "r") as f:
                    action_data = json.load(f)
                if action_data and "action" in action_data:

                    #
                    # Vaciar inmediatamente el archivo para evitar
                    # reprocesar el mismo comando.
                    #
                    with open(self._path, "w") as f:
                        json.dump({}, f)
                    order = action_data.get("action")
                    if order:
                        callback(order, action_data)

            except Exception as e:
                log_event(f"Error al leer commands.json: {e}",
                    origin="CHANNELS", level="ERROR", reason="COMMAND")

        self._monitor.connect("changed", on_file_changed)

        #
        # Mantener una referencia global evita que el monitor sea
        # liberado por el recolector de basura mientras permanezca
        # activo.
        #
        global _monitor
        _monitor = self._monitor

        log_event("Monitor de commands.json iniciado",
            origin="CHANNELS", level="INFO", reason="COMMAND")

# ==========================================================
# CANAL D-Bus
# ==========================================================

dbus_method = dbus.service.method("org.maki.wmm", in_signature="s")


class DBusChannel:
    """
    Canal de comunicación basado en D-Bus.

    Expone el servicio D-Bus del motor para que clientes externos
    (como el plasmoide de Plasma) puedan enviar comandos directamente
    al núcleo de WMM.
    """

    def __init__(self):
        from dbus.mainloop.glib import DBusGMainLoop

        self._bus = dbus.SessionBus(private=True, mainloop=DBusGMainLoop())
        self._bus_name = dbus.service.BusName("org.maki.wmm", self._bus)
        self._object = _DBusObject(self._bus_name)

    def set_callback(self, callback):
        self._object.set_callback(callback)

    def send(self, command):
        """D-Bus no utiliza envío desde el motor."""
        pass

    def start_receiving_commands(self, callback):
        self._object.set_callback(callback)

    def emit_busy_changed(self, busy):
        """Publica el estado busy actual a través del objeto D-Bus."""
        self._object.set_busy_state(busy)


class _DBusObject(dbus.service.Object):
    """
    Objeto que publica la interfaz D-Bus de WMM.

    Cada método expuesto representa un comando que puede invocar un
    cliente externo. Todos ellos delegan finalmente en el mismo
    callback del motor.
    """

    # ----------------------------------------------------------
    # SEÑALES
    # ----------------------------------------------------------

    @dbus.service.signal('org.maki.wmm', signature='s')
    def SettingsChanged(self, json_data):
        """Emitida cuando cambia settings.json."""
        pass

    @dbus.service.signal('org.maki.wmm', signature='s')
    def BookmarksChanged(self, json_data):
        """Emitida cuando cambia bookmarks.json."""
        pass

    @dbus.service.signal('org.maki.wmm', signature='b')
    def BusyChanged(self, busy):
        """Emitida cuando cambia el estado busy del engine."""
        pass

    def __init__(self, bus_name):
        super().__init__(bus_name, "/org/maki/wmm")
        self._callback = None
        self._busy = True

        # Rutas de los archivos a monitorizar
        data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
        self._settings_path = os.path.join(data_dir, 'settings.json')
        self._bookmarks_path = os.path.join(data_dir, 'bookmarks.json')

        # Monitores de archivos para emitir señales automáticamente
        self._monitor_settings = Gio.File.new_for_path(self._settings_path).monitor_file(
            Gio.FileMonitorFlags.NONE, None
        )
        self._monitor_bookmarks = Gio.File.new_for_path(self._bookmarks_path).monitor_file(
            Gio.FileMonitorFlags.NONE, None
        )

        self._monitor_settings.connect('changed', self._on_settings_changed)
        self._monitor_bookmarks.connect('changed', self._on_bookmarks_changed)

    def set_busy_state(self, busy):
        """Actualiza y publica el estado busy recibido desde el engine."""
        busy = bool(busy)

        if self._busy == busy:
            return

        self._busy = busy
        self.BusyChanged(busy)

    def set_callback(self, callback):
        self._callback = callback
        log_event("Callback D-Bus registrado",
            origin="DBUS", level="DEBUG", reason="COMMAND")

    def _on_settings_changed(self, monitor, file, other_file, event_type):
        """Emite SettingsChanged cuando settings.json termina de modificarse."""
        if event_type == Gio.FileMonitorEvent.CHANGES_DONE_HINT:
            try:
                with open(self._settings_path, 'r') as f:
                    content = f.read()
                self.SettingsChanged(content)
            except Exception as e:
                log_event(f"Error al emitir SettingsChanged: {e}",
                    origin="DBUS", level="ERROR", reason="COMMAND")

    def _on_bookmarks_changed(self, monitor, file, other_file, event_type):
        """Emite BookmarksChanged cuando bookmarks.json termina de modificarse."""
        if event_type == Gio.FileMonitorEvent.CHANGES_DONE_HINT:
            try:
                with open(self._bookmarks_path, 'r') as f:
                    content = f.read()
                self.BookmarksChanged(content)
            except Exception as e:
                log_event(f"Error al emitir BookmarksChanged: {e}",
                    origin="DBUS", level="ERROR", reason="COMMAND")

    def _dispatch(self, action, json_data):
        """
        Reenvía un comando D-Bus al callback del motor.

        Args:
            action: Nombre de la acción solicitada.
            json_data: Parámetros recibidos desde D-Bus en formato JSON.
        """
        if self._callback:
            self._callback(action, json.loads(json_data) if json_data else {})

    # ----------------------------------------------------------
    # COMANDOS DEL MOTOR
    # ----------------------------------------------------------

    @dbus_method
    def force_rotation(self, json_data):
        self._dispatch("force_rotation", json_data)

    @dbus_method
    def sync_library(self, json_data):
        self._dispatch("sync_library", json_data)

    @dbus_method
    def open_panel(self, json_data):
        self._dispatch("open_panel", json_data)

    @dbus_method
    def open_help(self, json_data):
        self._dispatch("open_help", json_data)

    @dbus_method
    def add_bookmark(self, json_data):
        self._dispatch("add_bookmark", json_data)

    @dbus_method
    def load_bookmark(self, json_data):
        self._dispatch("load_bookmark", json_data)

    @dbus_method
    def delete_bookmark(self, json_data):
        self._dispatch("delete_bookmark", json_data)

    @dbus_method
    def update_timer_settings(self, json_data):
        self._dispatch("update_timer_settings", json_data)

    # ----------------------------------------------------------
    # MÉTODOS DE CONSULTA
    # ----------------------------------------------------------

    @dbus.service.method("org.maki.wmm", out_signature="s")
    def GetSettings(self):
        settings_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "settings.json")
        try:
            with open(settings_path, "r") as f:
                return f.read()
        except Exception:
            return "{}"

    @dbus.service.method("org.maki.wmm", out_signature="s")
    def GetBookmarks(self):
        bookmarks_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "bookmarks.json")
        try:
            with open(bookmarks_path, "r") as f:
                return f.read()
        except Exception:
            return "{}"

    @dbus.service.method("org.maki.wmm", out_signature="b")
    def GetBusy(self):
        """Devuelve el último estado busy publicado por el engine."""
        return self._busy

    # ----------------------------------------------------------
    # CONTROL DEL MOTOR
    # ----------------------------------------------------------

    @dbus.service.method("org.maki.wmm")
    def Shutdown(self):
        if self._callback:
            self._callback("shutdown", {})
