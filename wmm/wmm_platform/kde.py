#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

"""
WMM - Wallpaper Multi-Monitor Manager

kde.py - Módulo de plataforma para KDE Plasma (Linux).
==========================================================
Contiene solo las implementaciones específicas de este entorno.
"""
import os
import re
import glob
import subprocess
import time
from PIL import Image
from debug_logger import log_event
from i18n import _

def get_install_path(data_base, app_domain):
    """Devuelve la ruta de instalación (esqueleto)."""
    return os.path.join(data_base, app_domain)

def _strip_ansi(text):
    """Elimina códigos de escape ANSI de una cadena."""
    ansi_escape = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')
    return ansi_escape.sub('', text)

def get_window_available_area(pid):
    """
    Devuelve el área máxima disponible que KWin concede a la ventana
    identificada por PID.

    Returns:
        dict: {"x": int, "y": int, "width": int, "height": int}
        None: si KWin no puede resolver la ventana o la consulta falla.
    """
    import tempfile
    import dbus
    import dbus.service
    from dbus.mainloop.glib import DBusGMainLoop
    from gi.repository import GLib

    pid = int(pid)

    reply_path = "/org/maki/wmm/KWinAreaReply"
    reply_interface = "org.maki.wmm.KWinAreaReply"

    bus = None
    receiver = None
    temp_path = None
    script_id = None
    loop = GLib.MainLoop()

    class _AreaReply(dbus.service.Object):
        def __init__(self, connection):
            super().__init__(connection, reply_path)
            self.result = None
            self.done = False

        @dbus.service.method(
            reply_interface,
            in_signature="dddd",
            out_signature=""
        )
        def SetArea(self, x, y, width, height):
            self.done = True

            width = float(width)
            height = float(height)

            if width > 0 and height > 0:
                self.result = {
                    "x": int(round(float(x))),
                    "y": int(round(float(y))),
                    "width": int(round(width)),
                    "height": int(round(height)),
                }

            if loop.is_running():
                loop.quit()

    try:
        # Conexión privada: no registra ningún servicio D-Bus nuevo.
        bus = dbus.SessionBus(
            private=True,
            mainloop=DBusGMainLoop()
        )

        receiver = _AreaReply(bus)
        reply_service = bus.get_unique_name()

        # El JavaScript vive dentro de kde.py.
        script = f"""
const TARGET_PID = {pid};
const REPLY_SERVICE = "{reply_service}";
const REPLY_PATH = "{reply_path}";
const REPLY_INTERFACE = "{reply_interface}";

let found = false;

for (const win of workspace.stackingOrder) {{
    if (Number(win.pid) === TARGET_PID) {{
        const area = workspace.clientArea(KWin.MaximizeArea, win);

        callDBus(
            REPLY_SERVICE,
            REPLY_PATH,
            REPLY_INTERFACE,
            "SetArea",
            Number(area.x),
            Number(area.y),
            Number(area.width),
            Number(area.height)
        );

        found = true;
        break;
    }}
}}

if (!found) {{
    callDBus(
        REPLY_SERVICE,
        REPLY_PATH,
        REPLY_INTERFACE,
        "SetArea",
        0, 0, 0, 0
    );
}}
"""

        # KWin necesita una ruta de archivo para loadScript().
        # El archivo es efímero y preferentemente vive en XDG_RUNTIME_DIR.
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
        if not runtime_dir or not os.path.isdir(runtime_dir):
            runtime_dir = None

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".js",
            prefix="wmm_kwin_",
            dir=runtime_dir,
            delete=False
        ) as tmp:
            tmp.write(script)
            temp_path = tmp.name

        # Cargar el script temporal en KWin.
        scripting = bus.get_object("org.kde.KWin", "/Scripting")
        scripting_iface = dbus.Interface(
            scripting,
            "org.kde.kwin.Scripting"
        )

        script_id = int(
            scripting_iface.loadScript(temp_path)
        )

        if script_id < 0:
            raise RuntimeError("KWin rechazó la carga del script temporal")

        # Ejecutar la instancia cargada.
        script_obj = bus.get_object(
            "org.kde.KWin",
            f"/Scripting/Script{script_id}"
        )
        script_iface = dbus.Interface(
            script_obj,
            "org.kde.kwin.Script"
        )

        script_iface.run()

        # Esperar únicamente a la respuesta del script.
        timed_out = False

        if not receiver.done:
            def _timeout():
                nonlocal timed_out
                timed_out = True
                loop.quit()
                return False

            timeout_id = GLib.timeout_add(1500, _timeout)
            loop.run()

            if not timed_out:
                GLib.source_remove(timeout_id)

            if receiver.result is None:
                if timed_out:
                    log_event(f"Timeout consultando el área útil de KWin para PID {pid}", origin="KDE", level="WARN", reason="D-BUS")
                else:
                    log_event(f"KWin no localizó una ventana válida para PID {pid}", origin="KDE", level="WARN", reason="HARDWARE")
                return None

        log_event(f"Área útil KWin obtenida para PID {pid}: {receiver.result}", origin="KDE", level="DEBUG", reason="HARDWARE")

        return receiver.result

    except Exception as e:
        log_event(f"Error consultando MaximizeArea en KWin: {e}", origin="KDE", level="ERROR", reason="D-BUS")
        return None

    finally:
        # Detener y retirar la instancia temporal del script de KWin.
        if script_id is not None and script_id >= 0 and bus is not None:
            try:
                script_obj = bus.get_object(
                    "org.kde.KWin",
                    f"/Scripting/Script{script_id}"
                )
                dbus.Interface(
                    script_obj,
                    "org.kde.kwin.Script"
                ).stop()
            except Exception:
                pass

        # Eliminar el archivo efímero.
        if temp_path:
            try:
                os.remove(temp_path)
            except OSError:
                pass

        # Retirar el objeto D-Bus temporal.
        if receiver is not None:
            try:
                receiver.remove_from_connection()
            except Exception:
                pass

        # Cerrar la conexión privada.
        if bus is not None:
            try:
                bus.close()
            except Exception:
                pass

def _get_uuid_to_container_map():
    """
    Construye y devuelve:
        uuid_to_container: UUID -> container_id
        connector_to_uuid: connector -> UUID
        uuid_to_screen: UUID -> screenNum

    Los monitores se ordenan por prioridad y se relacionan con lastScreen.
    """
    env = os.environ.copy()
    env['NO_COLOR'] = '1'

    try:
        result = subprocess.run(
            ['kscreen-doctor', '-o'],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, check=True, env=env
        )
        raw_output = result.stdout
    except subprocess.CalledProcessError as e:
        log_event(f"Error en kscreen-doctor -o: {e}", origin="KDE", level="ERROR", reason="HARDWARE")
        return {}, {}, {}

    clean = _strip_ansi(raw_output)

    # Parsear monitores: prioridad, conector y UUID
    monitors = []
    current_name = None
    current_uuid = None
    current_priority = None

    for line in clean.splitlines():
        line = line.strip()

        if line.startswith('Output:'):
            if current_name and current_uuid and current_priority is not None:
                monitors.append((current_priority, current_name, current_uuid))

            parts = line.split()
            if len(parts) >= 4:
                current_name = parts[2]
                current_uuid = parts[3]
                current_priority = None

        elif 'priority' in line:
            match = re.search(r'priority\s+(\d+)', line)
            if match and current_name:
                current_priority = int(match.group(1))

    if current_name and current_uuid and current_priority is not None:
        monitors.append((current_priority, current_name, current_uuid))

    if not monitors:
        log_event("No se encontraron monitores", origin="KDE", level="WARN", reason="HARDWARE")
        return {}, {}, {}

    # Plasma ordena las pantallas según prioridad.
    monitors.sort(key=lambda x: x[0])
    log_event(f"Monitores ordenados por prioridad: {monitors}", origin="KDE", level="INFO", reason="HARDWARE")

    connector_to_uuid = {name: uuid for _, name, uuid in monitors}
    uuid_to_screen = {uuid: i for i, (_, _, uuid) in enumerate(monitors)}

    appconfig = os.path.expanduser('~/.config/plasma-org.kde.plasma.desktop-appletsrc')

    if not os.path.exists(appconfig):
        log_event(f"{appconfig} no encontrado", origin="KDE", level="ERROR", reason="HARDWARE")
        return {}, connector_to_uuid, uuid_to_screen

    with open(appconfig, 'r') as f:
        content = f.read()

    wallpaper_containers = set(
        re.findall(r'\[Containments\]\[(\d+)\]\[Wallpaper\]\[org\.kde\.image\]', content)
    )

    lastscreen_to_cid = {}

    for cid in wallpaper_containers:
        sec = re.search(
            rf'^\[Containments\]\[{cid}\]$(.*?)(?=^\[|\Z)',
            content,
            re.MULTILINE | re.DOTALL
        )

        if not sec:
            continue

        section = sec.group(1)

        if 'plugin=org.kde.panel' in section:
            continue

        match = re.search(r'^lastScreen=(\d+)', section, re.MULTILINE)

        if match:
            lastscreen = int(match.group(1))
            if lastscreen not in lastscreen_to_cid:
                lastscreen_to_cid[lastscreen] = cid

    uuid_to_container = {}

    for i, (prio, name, uuid) in enumerate(monitors):
        cid = lastscreen_to_cid.get(i)

        if cid:
            uuid_to_container[uuid] = cid
            log_event(f"Prioridad {prio}: {name} (UUID {uuid}) -> screen {i} -> contenedor {cid}", origin="KDE", level="INFO", reason="HARDWARE")
        else:
            log_event(f"Prioridad {prio}: {name} sin contenedor para screen {i}", origin="KDE", level="WARN", reason="HARDWARE")

    if uuid_to_container:
        log_event(f"Mapeo uuid->contenedor final: {uuid_to_container}", origin="KDE", level="INFO", reason="HARDWARE")

    return uuid_to_container, connector_to_uuid, uuid_to_screen

def _get_wallpaper_target_for_hash(monitors_map):
    """
    Devuelve:
        {
            monitor_hash: {
                "container": container_id,
                "screen": screen_num
            }
        }

    utilizando el mapeo UUID/conector ya existente.
    """
    if not monitors_map:
        return {}

    uuid_to_container, connector_to_uuid, uuid_to_screen = _get_uuid_to_container_map()

    if not uuid_to_container:
        return {}

    target_map = {}

    for m_hash, info in monitors_map.items():
        connector = info.get('connector')

        if not connector:
            continue

        uuid = connector_to_uuid.get(connector)

        if not uuid:
            log_event(f"No se encontró UUID para el conector {connector}", origin="KDE", level="WARN", reason="HARDWARE")
            continue

        cid = uuid_to_container.get(uuid)
        screen = uuid_to_screen.get(uuid)

        if cid and screen is not None:
            target_map[m_hash] = {
                "container": cid,
                "screen": screen,
            }
            log_event(f"Mapeo wallpaper: {m_hash} ({connector}) -> screen {screen}, contenedor {cid}", origin="KDE", level="INFO", reason="HARDWARE")
        else:
            log_event(f"UUID {uuid} ({connector}) sin destino Plasma válido", origin="KDE", level="WARN", reason="HARDWARE")

    return target_map

def render_master_wallpaper(self, processed_images, monitors_map, config_handler):
    """
    Prepara los destinos Plasma correspondientes a las imágenes procesadas
    y delega en set_wallpaper() la generación y transición final.

    processed_images contiene únicamente los monitores que deben cambiar
    durante el ciclo actual.
    """
    log_event(f"processed_images recibidas: {list(processed_images.keys())}", origin="KDE", level="INFO", reason="LIBRARY")

    if not processed_images:
        log_event("No hay imágenes procesadas para KDE", origin="KDE", level="ERROR", reason="LIBRARY")
        return False

    target_map = _get_wallpaper_target_for_hash(monitors_map)

    if not target_map:
        log_event("No se pudo obtener el mapeo hash->destino Plasma. Abortando.", origin="KDE", level="ERROR", reason="LIBRARY")
        return False

    active_targets = {}

    for m_hash in processed_images:
        target = target_map.get(m_hash)

        if not target:
            log_event(f"No hay destino Plasma para el hash {m_hash}. Se omite.", origin="KDE", level="WARN", reason="LIBRARY")
            continue

        active_targets[m_hash] = target

    if not active_targets:
        log_event("No hay destinos Plasma válidos para las imágenes procesadas.", origin="KDE", level="WARN", reason="LIBRARY")
        return False

    log_event(f"Aplicando {len(active_targets)} imágenes mediante PlasmaShell.setWallpaper", origin="KDE", level="INFO", reason="LIBRARY")
    return self.set_wallpaper(processed_images, active_targets, config_handler)

def _force_desktop_settings(config_handler, active_containers=None):
    """
    Fuerza la configuración necesaria en KDE para que el trigger funcione sin parpadeo.
    - FillMode = 0 (escalado y recorte) para evitar bandas al estirar el trigger.
    - plugin = org.kde.image (por si el usuario lo ha cambiado).
    """
    if not active_containers:
        log_event("No hay contenedores activos para forzar ajustes", origin="KDE", level="WARN", reason="HARDWARE")
        return

    appconfig = os.path.expanduser('~/.config/plasma-org.kde.plasma.desktop-appletsrc')

    for cid in active_containers:
        # Forzar plugin (por si el usuario lo cambió)
        subprocess.run([
            'kwriteconfig6', '--file', appconfig,
            '--group', 'Containments', '--group', cid,
            '--group', 'Wallpaper',
            '--key', 'plugin', 'org.kde.image'
        ], check=False, capture_output=True)

        # Forzar FillMode = 0 (escalado y recorte)
        subprocess.run([
            'kwriteconfig6', '--file', appconfig,
            '--group', 'Containments', '--group', cid,
            '--group', 'Wallpaper', '--group', 'org.kde.image', '--group', 'General',
            '--key', 'FillMode', '0'
        ], check=False, capture_output=True)

    log_event("Ajustes de sistema forzados para KDE (FillMode=0)", origin="KDE", level="INFO", reason="HARDWARE")

def set_wallpaper(processed_images, targets, config_handler):
    """
    Aplica fondos independientes en Plasma 6 mediante
    org.kde.PlasmaShell.setWallpaper().

    Usa dos archivos alternos por contenedor para garantizar que cada cambio
    modifica realmente la fuente Image y permite a org.kde.image ejecutar
    su transición nativa.

    sync:
        imagen actual -> negro -> nueva imagen

    async:
        imagen actual -> nueva imagen
    """
    if not config_handler or not config_handler.cache_dir:
        return False

    if not processed_images or not targets:
        return False

    from gi.repository import Gio, GLib

    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        settings = config_handler.load_json("settings").get("global", {})
        sl_mode = settings.get("slideshow_mode", "sync")

        def get_wallpaper(screen):
            reply = bus.call_sync(
                "org.kde.plasmashell",
                "/PlasmaShell",
                "org.kde.PlasmaShell",
                "wallpaper",
                GLib.Variant("(u)", (screen,)),
                GLib.VariantType.new("(a{sv})"),
                Gio.DBusCallFlags.NONE,
                2000,
                None
            )
            return reply.unpack()[0]

        def apply_wallpaper(path, screen):
            parameters = {"Image": GLib.Variant("s", path)}
            bus.call_sync(
                "org.kde.plasmashell",
                "/PlasmaShell",
                "org.kde.PlasmaShell",
                "setWallpaper",
                GLib.Variant("(sa{sv}u)", ("org.kde.image", parameters, screen)),
                None,
                Gio.DBusCallFlags.NONE,
                2000,
                None
            )

        prepared = {}

        # Preparar cada nueva imagen en el slot que Plasma no está mostrando.
        for m_hash, img in processed_images.items():
            target = targets.get(m_hash)

            if not target:
                continue

            cid = target["container"]
            screen = target["screen"]

            current = get_wallpaper(screen)
            current_path = current.get("Image", "")

            if current_path.startswith("file://"):
                current_path = current_path[7:]

            path_0 = os.path.join(config_handler.cache_dir, f"wallpaper_master_{cid}_0.jpg")
            path_1 = os.path.join(config_handler.cache_dir, f"wallpaper_master_{cid}_1.jpg")
            master_path = path_1 if current_path == path_0 else path_0

            try:
                img.save(master_path, "JPEG", quality=95)
                prepared[m_hash] = {"container": cid, "screen": screen, "path": master_path}
                log_event(f"Imagen preparada para screen {screen}, contenedor {cid}: {master_path}", origin="KDE", level="INFO", reason="LIBRARY")
            except Exception as e:
                log_event(f"Error guardando imagen para contenedor {cid}: {e}", origin="KDE", level="ERROR", reason="LIBRARY")

        if not prepared:
            log_event("No se pudo preparar ninguna imagen para Plasma.", origin="KDE", level="WARN", reason="LIBRARY")
            return False

        # SYNC: transición coordinada hacia negro.
        if sl_mode == "sync":
            fade_path = os.path.join(config_handler.cache_dir, "fade_black.png")

            if not os.path.exists(fade_path):
                Image.new("RGB", (1, 1), (0, 0, 0)).save(fade_path, "PNG")

            for target in prepared.values():
                apply_wallpaper(fade_path, target["screen"])

            time.sleep(1.2)

        # Aplicar las imágenes finales.
        for target in prepared.values():
            apply_wallpaper(target["path"], target["screen"])

        if sl_mode == "sync":
            log_event(f"Transición Fade out/in aplicada en {len(prepared)} pantallas KDE", origin="KDE", level="INFO", reason="LIBRARY")
        else:
            log_event(f"Transición Crossfade aplicada en {len(prepared)} pantallas KDE", origin="KDE", level="INFO", reason="LIBRARY")

        return True

    except Exception as e:
        log_event(f"PlasmaShell no respondió al aplicar los fondos: {e}", origin="KDE", level="ERROR", reason="D-BUS")
        return False

def ensure_keybindings(app_dir):
    """
    Registra en KGlobalAccel las acciones globales declaradas
    por la aplicación WMM en org.maki.wmm.desktop.

    No asigna ninguna combinación de teclas por defecto.
    La configuración del atajo pertenece siempre al usuario.
    """
    import dbus

    desktop_id = "org.maki.wmm.desktop"
    action_key = "next-background"
    action_name = _("Next Background")
    component_name = "WMM Manager"

    data_home = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    desktop_path = os.path.join(data_home, "applications", desktop_id)

    if not os.path.exists(desktop_path):
        log_event(f"Lanzador KDE no encontrado: {desktop_path}", origin="KDE", level="WARN", reason="GENERIC")
        return False

    log_event(f"KDE shortcut data: desktop_id='{desktop_id}', action='{action_key}', action_name='{action_name}'", origin="KDE", level="DEBUG", reason="GENERIC")

    try:
        bus = dbus.SessionBus()
        accel = bus.get_object("org.kde.kglobalaccel", "/kglobalaccel")
        accel_iface = dbus.Interface(accel, "org.kde.KGlobalAccel")
    except Exception as e:
        log_event(f"No se pudo conectar con kglobalaccel: {e}", origin="KDE", level="ERROR", reason="D-BUS")
        return False

    action_id = [desktop_id, action_key, component_name, action_name]

    try:
        accel_iface.doRegister(action_id)

        empty_shortcuts = dbus.Array([], signature="(ai)")
        set_present = dbus.UInt32(2)
        accel_iface.setShortcutKeys(action_id, empty_shortcuts, set_present)

        # La primera llamada puede crear el KServiceActionComponent tomando
        # el Name del .desktop. Ahora que la acción existe, esta segunda
        # llamada actualiza los nombres amigables del componente y la acción.
        accel_iface.doRegister(action_id)

        component_path = accel_iface.getComponent(desktop_id)
        component = bus.get_object("org.kde.kglobalaccel", component_path)
        component_iface = dbus.Interface(component, "org.kde.kglobalaccel.Component")
        actions = list(component_iface.shortcutNames())

        if action_key not in actions:
            log_event(f"Acción KDE no disponible tras el registro: {action_key}", origin="KDE", level="ERROR", reason="GENERIC")
            return False

        log_event(f"Atajo KDE disponible: {desktop_id} → {action_name}", origin="KDE", level="INFO", reason="GENERIC")
        return True

    except Exception as e:
        log_event(f"No se pudo registrar atajo KDE: {e}", origin="KDE", level="ERROR", reason="GENERIC")
        return False
