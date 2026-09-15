#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

"""
WMM - Wallpaper Multi-Monitor Manager

linux.py - Módulo de plataforma para Linux.
==========================================================
Contiene funciones comunes a todos los escritorios de Linux.
"""
import os
import sys
import subprocess
import fcntl
import shutil
import hashlib
import json

from wmm_platform.file_utils import lock_file, unlock_file
from debug_logger import log_event

def set_process_name(name):
    """Asigna un nombre visible al proceso actual en Linux."""
    try:
        with open("/proc/self/comm", "w", encoding="utf-8") as f:
            f.write(name[:15])
        return True
    except OSError:
        return False

def _generate_gdk_wayland_hash(connector, manufacturer, x, y, width, height):
    """Hash estable para Wayland basado en modelo y posición."""
    return hashlib.shake_128(f"{connector}-{manufacturer}-{x}-{y}-{width}-{height}".encode()).hexdigest(4)

# Registro de generadores de hash por motor gráfico
HASH_GENERATORS = {
    'wayland': _generate_gdk_wayland_hash,
}

def generate_hash_for_engine(graphics_engine, connector, manufacturer, x, y, width, height):
    """
    Devuelve un hash estable para el monitor, usando el generador
    correspondiente al motor gráfico indicado.
    """
    generator = HASH_GENERATORS.get(graphics_engine, get_x11_monitors)
    return generator(connector, manufacturer, x, y, width, height)

def _ensure_nemo_wmm_layout(data_base):
    """Mantiene el submenú WMM en el layout de acciones de Nemo."""
    from i18n import _

    config_base = os.environ.get("XDG_CONFIG_HOME", os.path.join(os.path.expanduser("~"), ".config"))
    state_base = os.environ.get("XDG_STATE_HOME", os.path.join(os.path.expanduser("~"), ".local", "state"))
    layout_path = os.path.join(config_base, "nemo", "actions-tree.json")
    state_dir = os.path.join(state_base, "wmm")
    marker_path = os.path.join(state_dir, "nemo-layout-initialized")

    wmm_children = [
        {
            "uuid": "wmm-add_to_bookmarks.nemo_action",
            "type": "action",
            "user-label": _("Add to favorites"),
            "user-icon": "stock_add-bookmark",
            "accelerator": None
        },
        {
            "uuid": "wmm-send-to.nemo_action",
            "type": "action",
            "user-label": _("Send to Monitor"),
            "user-icon": "screen-shared-symbolic",
            "accelerator": None
        },
        {
            "uuid": "wmm-span-image.nemo_action",
            "type": "action",
            "user-label": _("Span image across all screens"),
            "user-icon": "view-fullscreen",
            "accelerator": None
        }
    ]
    wmm_actions = {item["uuid"] for item in wmm_children}

    def mark_initialized():
        try:
            os.makedirs(state_dir, exist_ok=True)
            with open(marker_path, "w", encoding="utf-8") as f:
                f.write("1\n")
        except OSError as e:
            log_event(f"No se pudo registrar la inicialización del layout de Nemo: {e}",
                      origin="LINUX", level="WARN", reason="SETTINGS")

    def find_wmm_submenu(nodes):
        for node in nodes:
            if not isinstance(node, dict):
                continue
            if node.get("uuid") == "WMM Manager" and node.get("type") == "submenu":
                return node
            children = node.get("children")
            if isinstance(children, list):
                submenu = find_wmm_submenu(children)
                if submenu is not None:
                    return submenu
        return None

    def contains_action(nodes, action_uuid):
        for node in nodes:
            if not isinstance(node, dict):
                continue
            if node.get("uuid") == action_uuid:
                return True
            children = node.get("children")
            if isinstance(children, list) and contains_action(children, action_uuid):
                return True
        return False

    def contains_wmm(nodes):
        return any(contains_action(nodes, action_uuid) for action_uuid in wmm_actions)

    def take_action(nodes, action_uuid, protected_node=None):
        for index, node in enumerate(nodes):
            if not isinstance(node, dict):
                continue
            if node is protected_node:
                continue
            if node.get("uuid") == action_uuid and node.get("type") == "action":
                return nodes.pop(index)
            children = node.get("children")
            if isinstance(children, list):
                action = take_action(children, action_uuid, protected_node)
                if action is not None:
                    return action
        return None

    wmm_submenu = {
        "uuid": "WMM Manager",
        "type": "submenu",
        "user-label": "WMM Manager",
        "user-icon": "video-display",
        "accelerator": None,
        "children": wmm_children
    }

    layout_updated = False
    layout_initialized = os.path.exists(marker_path)

    if os.path.exists(layout_path):
        try:
            with open(layout_path, "r", encoding="utf-8") as f:
                layout = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            log_event(f"No se pudo leer el layout de Nemo; se conserva sin cambios: {e}",
                      origin="LINUX", level="WARN", reason="SETTINGS")
            return
        if not isinstance(layout, dict) or not isinstance(layout.get("toplevel"), list):
            log_event(f"Layout de Nemo no reconocido; se conserva sin cambios: {layout_path}",
                      origin="LINUX", level="WARN", reason="SETTINGS")
            return
        existing_submenu = find_wmm_submenu(layout["toplevel"])
        if existing_submenu is not None:
            children = existing_submenu.get("children")
            if not isinstance(children, list):
                log_event("Submenú WMM de Nemo no reconocido; se conserva sin cambios", origin="LINUX", level="WARN", reason="SETTINGS")
                return
            for action_template in wmm_children:
                action_uuid = action_template["uuid"]
                if contains_action(children, action_uuid):
                    continue
                action = take_action(layout["toplevel"], action_uuid, protected_node=existing_submenu)
                if action is None:
                    action = action_template.copy()
                else:
                    if action.get("user-label") is None:
                        action["user-label"] = action_template["user-label"]
                    if action.get("user-icon") is None:
                        action["user-icon"] = action_template["user-icon"]
                children.append(action)
                layout_updated = True
            if not layout_updated:
                if not layout_initialized:
                    mark_initialized()
                log_event("El submenú WMM de Nemo ya contiene todas las acciones; se conserva la configuración existente",
                          origin="LINUX", level="DEBUG", reason="SETTINGS")
                return

        elif layout_initialized:
            log_event("El layout de Nemo ya fue inicializado y no contiene el submenú WMM; se conserva la configuración existente",
                      origin="LINUX", level="DEBUG", reason="SETTINGS")
            return

        elif contains_wmm(layout["toplevel"]):
            mark_initialized()
            log_event("El layout de Nemo contiene acciones WMM fuera del submenú; se conserva la configuración existente", origin="LINUX", level="DEBUG", reason="SETTINGS")
            return

        else:
            layout["toplevel"].append(wmm_submenu)
    else:
        # Reproducir el layout plano que genera Nemo cuando todavía no existe
        # actions-tree.json: descubrir todas las acciones instaladas y ordenarlas.
        action_names = set()
        data_dirs = [path for path in os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(os.pathsep) if path]
        if data_base:
            data_dirs.append(data_base)
        for base_dir in data_dirs:
            actions_dir = os.path.join(base_dir, "nemo", "actions")
            if not os.path.isdir(actions_dir):
                continue
            for filename in os.listdir(actions_dir):
                if filename.endswith(".nemo_action"):
                    action_names.add(filename)
        layout = {
            "toplevel": [
                {
                    "uuid": filename,
                    "type": "action",
                    "user-label": None,
                    "user-icon": None,
                    "accelerator": None
                }
                for filename in sorted(action_names)
                if filename not in wmm_actions
            ]
        }

        layout["toplevel"].append(wmm_submenu)

    try:
        os.makedirs(os.path.dirname(layout_path), exist_ok=True)
        temp_path = f"{layout_path}.wmm.tmp"

        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(layout, f, ensure_ascii=False, indent=2)

        os.replace(temp_path, layout_path)
        mark_initialized()

        if layout_updated:
            log_event(f"Submenú WMM Manager actualizado en el layout de Nemo: {layout_path}",
                      origin="LINUX", level="INFO", reason="SETTINGS")
        else:
            log_event(f"Submenú WMM Manager inicializado en el layout de Nemo: {layout_path}",
                      origin="LINUX", level="INFO", reason="SETTINGS")

    except OSError as e:
        log_event(f"No se pudo actualizar el submenú WMM en Nemo: {e}",
                  origin="LINUX", level="WARN", reason="SETTINGS")

def _get_kio_version():
    """Devuelve la versión instalada de KIO como (major, minor, patch)."""
    probes = []
    # Fedora
    if shutil.which("rpm"):
        probes.append(["rpm", "-q", "--qf", "%{VERSION}\n", "kf6-kio-core"])
    # Ubuntu
    if shutil.which("dpkg-query"):
        probes.append(["dpkg-query", "-W", "-f=${Version}\n", "libkf6kiocore6"])
    # Arch
    if shutil.which("pacman"):
        probes.append(["pacman", "-Q", "kio"])

    for command in probes:
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                continue
            version = result.stdout.strip()
            if command[0] == "pacman":
                version = version.rsplit(" ", 1)[-1]
            version = version.split(":", 1)[-1]
            version = version.split("-", 1)[0]
            parts = version.split(".")
            if len(parts) < 2 or not all(part.isdigit() for part in parts):
                continue
            while len(parts) < 3:
                parts.append("0")
            return tuple(int(part) for part in parts[:3])
        except OSError:
            continue
    return None

def ensure_shell_actions(app_root, data_base):
    """
    Detecta los gestores de archivos instalados y prepara sus integraciones WMM.

    Dolphin utiliza Service Menus que llaman a wrappers comunes de WMM.
    Nautilus utiliza una extensión Python nativa.
    Caja combina acciones de archivo con una extensión Python para el escritorio.
    Nemo utiliza acciones nativas y un layout propio.

    La detección depende exclusivamente del gestor instalado, no del
    escritorio activo.
    """
    source_dir = os.path.join(app_root, "wmm_platform", "shell", "file_manager")
    if not os.path.isdir(source_dir):
        return

    # --- 1. DOLPHIN: SERVICE MENUS ---
    # KIO >= 6.30 utiliza el submenú nativo WMM Manager.
    # Versiones anteriores conservan los Service Menus individuales debido
    # a la regresión de X-KDE-Submenu presente en versiones previas de KIO.
    if shutil.which("dolphin"):
        dolphin_source_dir = os.path.join(source_dir, "dolphin")
        common_source_dir = os.path.join(source_dir, "common")
        dolphin_target_dir = os.path.join(data_base, "kio", "servicemenus")

        dolphin_files = (
            ("wmm-add_to_bookmark.desktop", "wmm-add_to_bookmarks.sh"),
            ("wmm-send-to.desktop", "wmm-send-to-monitor.sh"),
            ("wmm-span-image.desktop", "wmm-span-image.sh"),
        )

        kio_version = _get_kio_version()
        log_event(f"Versión KIO detectada: {kio_version}",
                  origin="LINUX", level="DEBUG", reason="SETTINGS")

        if not os.path.isdir(dolphin_source_dir):
            log_event(f"Directorio de plantillas Dolphin no encontrado: {dolphin_source_dir}",
                      origin="LINUX", level="WARN", reason="SETTINGS")
        elif not os.path.isdir(common_source_dir):
            log_event(f"Directorio de wrappers comunes no encontrado: {common_source_dir}",
                      origin="LINUX", level="WARN", reason="SETTINGS")
        else:
            os.makedirs(dolphin_target_dir, exist_ok=True)
            dolphin_ready = True

            if kio_version and kio_version >= (6, 30, 0):
                source_path = os.path.join(dolphin_source_dir, "wmm-menu.desktop")
                target_path = os.path.join(dolphin_target_dir, "wmm-menu.desktop")
                wrapper_paths = (
                    os.path.join(common_source_dir, "wmm-add_to_bookmarks.sh"),
                    os.path.join(common_source_dir, "wmm-send-to-monitor.sh"),
                    os.path.join(common_source_dir, "wmm-span-image.sh"),
                )

                if not os.path.isfile(source_path):
                    log_event(f"Plantilla Dolphin no encontrada: {source_path}",
                              origin="LINUX", level="WARN", reason="SETTINGS")
                    dolphin_ready = False
                for wrapper_path in wrapper_paths:
                    if not os.path.isfile(wrapper_path):
                        log_event(f"Wrapper común no encontrado: {wrapper_path}",
                                  origin="LINUX", level="WARN", reason="SETTINGS")
                        dolphin_ready = False
                if dolphin_ready:
                    try:
                        for wrapper_path in wrapper_paths:
                            os.chmod(wrapper_path, 0o755)
                        with open(source_path, "r", encoding="utf-8") as f:
                            source_content = f.read()
                        source_content = source_content.replace("@APP_DIR@", app_root)
                        if not os.path.exists(target_path):
                            with open(target_path, "w", encoding="utf-8") as f:
                                f.write(source_content)
                            os.chmod(target_path, 0o755)
                        with open(target_path, "r", encoding="utf-8") as f:
                            installed_content = f.read()
                        for wrapper_path in wrapper_paths:
                            if wrapper_path not in installed_content:
                                dolphin_ready = False
                                log_event(f"Service Menu de Dolphin no apunta al wrapper común esperado: {target_path}",
                                          origin="LINUX", level="WARN", reason="SETTINGS")
                                break
                    except OSError as e:
                        dolphin_ready = False
                        log_event(f"No se pudo preparar la integración de Dolphin wmm-menu.desktop: {e}",
                                  origin="LINUX", level="WARN", reason="SETTINGS")

                # El submenú sustituye a las tres entradas independientes.
                # Sólo se retiran después de validar completamente el descriptor nuevo.
                if dolphin_ready:
                    for filename, _wrapper_name in dolphin_files:
                        legacy_path = os.path.join(dolphin_target_dir, filename)
                        if os.path.isfile(legacy_path):
                            try:
                                os.remove(legacy_path)
                                log_event(f"Service Menu legacy de Dolphin eliminado: {legacy_path}",
                                          origin="LINUX", level="DEBUG", reason="SETTINGS")
                            except OSError as e:
                                log_event(f"No se pudo eliminar el Service Menu legacy de Dolphin {legacy_path}: {e}",
                                          origin="LINUX", level="WARN", reason="SETTINGS")
            else:
                # Service Menus: se crean sólo si no existen. En actualizaciones,
                # únicamente se migra un Exec legacy para preservar personalizaciones.
                for filename, wrapper_name in dolphin_files:
                    source_path = os.path.join(dolphin_source_dir, filename)
                    target_path = os.path.join(dolphin_target_dir, filename)
                    wrapper_path = os.path.join(common_source_dir, wrapper_name)
                    if not os.path.isfile(source_path):
                        log_event(f"Plantilla Dolphin no encontrada: {source_path}",
                                  origin="LINUX", level="WARN", reason="SETTINGS")
                        dolphin_ready = False
                        continue
                    if not os.path.isfile(wrapper_path):
                        log_event(f"Wrapper común no encontrado: {wrapper_path}",
                                  origin="LINUX", level="WARN", reason="SETTINGS")
                        dolphin_ready = False
                        continue
                    try:
                        os.chmod(wrapper_path, 0o755)
                        with open(source_path, "r", encoding="utf-8") as f:
                            source_content = f.read()
                        source_content = source_content.replace("@APP_DIR@", app_root)
                        if not os.path.exists(target_path):
                            with open(target_path, "w", encoding="utf-8") as f:
                                f.write(source_content)
                            os.chmod(target_path, 0o755)
                        else:
                            with open(target_path, "r", encoding="utf-8") as f:
                                current_content = f.read()
                            source_exec = next((line for line in source_content.splitlines() if line.startswith("Exec=")), None)
                            if source_exec and wrapper_name in current_content and wrapper_path not in current_content:
                                lines = current_content.splitlines()
                                migrated = False
                                for index, line in enumerate(lines):
                                    if line.startswith("Exec=") and wrapper_name in line:
                                        lines[index] = source_exec
                                        migrated = True
                                        break
                                if migrated:
                                    migrated_content = "\n".join(lines)
                                    if current_content.endswith("\n"):
                                        migrated_content += "\n"
                                    temp_path = f"{target_path}.wmm.tmp"
                                    with open(temp_path, "w", encoding="utf-8", newline="\n") as f:
                                        f.write(migrated_content)
                                    os.replace(temp_path, target_path)
                                    os.chmod(target_path, 0o755)
                                    log_event(f"Service Menu legacy de Dolphin migrado: {target_path}",
                                              origin="LINUX", level="INFO", reason="SETTINGS")
                        with open(target_path, "r", encoding="utf-8") as f:
                            installed_content = f.read()

                        if wrapper_path not in installed_content:
                            dolphin_ready = False
                            log_event(f"Service Menu de Dolphin no apunta al wrapper común esperado: {target_path}",
                                      origin="LINUX", level="WARN", reason="SETTINGS")
                    except OSError as e:
                        dolphin_ready = False
                        log_event(f"No se pudo preparar la integración de Dolphin {filename}: {e}",
                                  origin="LINUX", level="WARN", reason="SETTINGS")

            # Wrappers legacy: se retiran sólo cuando los Service Menus actuales
            # ya apuntan correctamente a los wrappers compartidos de common/.
            if dolphin_ready:
                for filename in ("wmm-add_to_bookmarks.sh", "wmm-send-to-monitor.sh"):
                    legacy_path = os.path.join(dolphin_target_dir, filename)
                    if os.path.isfile(legacy_path):
                        try:
                            os.remove(legacy_path)
                            log_event(f"Wrapper legacy de Dolphin eliminado: {legacy_path}",
                                      origin="LINUX", level="DEBUG", reason="SETTINGS")
                        except OSError as e:
                            log_event(f"No se pudo eliminar el wrapper legacy de Dolphin {legacy_path}: {e}",
                                      origin="LINUX", level="WARN", reason="SETTINGS")
                log_event(f"Integración con Dolphin verificada/instalada en {dolphin_target_dir}",
                          origin="LINUX", level="INFO", reason="SETTINGS")

    # --- 2. NAUTILUS: EXTENSIÓN NATIVA ---
    # Instala y actualiza la extensión Python de Nautilus que añade
    # las acciones contextuales de WMM mediante el proveedor nativo del gestor.
    if shutil.which("nautilus"):
        nautilus_source = os.path.join(source_dir, "nautilus", "wmm-nautilus.py")
        nautilus_extensions_dir = os.path.join(data_base, "nautilus-python", "extensions")
        nautilus_target = os.path.join(nautilus_extensions_dir, "wmm-nautilus.py")

        # Comprobar el runtime de nautilus-python en un proceso separado para
        # no cargar Nautilus/GTK4 dentro del proceso GTK3 del engine de WMM.
        nautilus_probe = subprocess.run(
            [sys.executable, "-c", 'import gi; from gi.repository import Nautilus'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False)

        if nautilus_probe.returncode != 0:
            log_event("Integración nativa de Nautilus no disponible: falta Nautilus 4.0 para Python",
                      origin="LINUX", level="WARN", reason="SETTINGS")
        elif not os.path.isfile(nautilus_source):
            log_event(f"Extensión nativa de Nautilus no encontrada: {nautilus_source}",
                      origin="LINUX", level="WARN", reason="SETTINGS")
        else:
            try:
                with open(nautilus_source, "r", encoding="utf-8") as f:
                    content = f.read()

                content = content.replace("@PYTHON3@", sys.executable)
                content = content.replace("@APP_DIR@", app_root)

                # Validar la plantilla resuelta antes de sustituir una
                # integración de Nautilus que pueda estar funcionando.
                compile(content, nautilus_source, "exec")

                os.makedirs(nautilus_extensions_dir, exist_ok=True)

                current_content = None
                if os.path.isfile(nautilus_target):
                    with open(nautilus_target, "r", encoding="utf-8") as f:
                        current_content = f.read()

                nautilus_installed = current_content != content

                if nautilus_installed:
                    temp_path = f"{nautilus_target}.wmm.tmp"
                    with open(temp_path, "w", encoding="utf-8", newline="\n") as f:
                        f.write(content)
                    os.replace(temp_path, nautilus_target)

                # Wrappers legacy: se retiran únicamente después de validar
                # correctamente la extensión nativa actual de Nautilus.
                legacy_scripts_dir = os.path.join(data_base, "nautilus", "scripts")

                for filename in ("wmm-add_to_bookmarks.sh", "wmm-send-to-monitor.sh"):
                    legacy_path = os.path.join(legacy_scripts_dir, filename)

                    if os.path.isfile(legacy_path):
                        try:
                            os.remove(legacy_path)
                            log_event(f"Script legacy de Nautilus eliminado: {legacy_path}",
                                      origin="LINUX", level="DEBUG", reason="SETTINGS")
                        except OSError as e:
                            log_event(f"No se pudo eliminar el script legacy de Nautilus {legacy_path}: {e}",
                                      origin="LINUX", level="WARN", reason="SETTINGS")

                if nautilus_installed:
                    log_event(f"Integración nativa con Nautilus instalada en {nautilus_target}",
                              origin="LINUX", level="INFO", reason="SETTINGS")
                else:
                    log_event(f"Integración nativa con Nautilus verificada en {nautilus_target}",
                              origin="LINUX", level="DEBUG", reason="SETTINGS")

            except (OSError, SyntaxError) as e:
                log_event(f"No se pudo instalar la integración nativa de Nautilus: {e}",
                          origin="LINUX", level="WARN", reason="SETTINGS")

    # --- 3. CAJA: ACCIONES Y EXTENSIÓN CONTEXTUAL ---
    # Instala las acciones de archivo de Caja sin sobrescribir personalizaciones
    # y mantiene actualizada la extensión Python usada por el menú del escritorio.
    if shutil.which("caja"):
        caja_source_dir = os.path.join(source_dir, "caja")
        common_source_dir = os.path.join(source_dir, "common")
        caja_actions_dir = os.path.join(data_base, "file-manager", "actions")
        caja_files = (
            "wmm-menu.desktop",
            "wmm-send-to-monitor.desktop",
            "wmm-add-to-favorites.desktop",
            "wmm-span-image.desktop",)
        caja_wrappers = (
            "wmm-add_to_bookmarks.sh",
            "wmm-send-to-monitor.sh",
            "wmm-span-image.sh",)

        if not os.path.isdir(caja_source_dir):
            log_event(f"Directorio de plantillas Caja no encontrado: {caja_source_dir}",
                      origin="LINUX", level="WARN", reason="SETTINGS")
        else:
            os.makedirs(caja_actions_dir, exist_ok=True)
            for wrapper_name in caja_wrappers:
                wrapper_path = os.path.join(common_source_dir, wrapper_name)
                if not os.path.isfile(wrapper_path):
                    log_event(f"Wrapper común no encontrado: {wrapper_path}",
                        origin="LINUX", level="WARN", reason="SETTINGS")
                    continue
                os.chmod(wrapper_path, 0o755)

            # Acciones de archivos: se crean sólo si no existen para preservar
            # traducciones, ajustes o personalizaciones realizadas por el usuario.
            for filename in caja_files:
                source_path = os.path.join(caja_source_dir, filename)
                target_path = os.path.join(caja_actions_dir, filename)
                if os.path.exists(target_path):
                    continue
                if not os.path.exists(source_path):
                    log_event(f"Plantilla Caja no encontrada: {source_path}",
                              origin="LINUX", level="WARN", reason="SETTINGS")
                    continue
                with open(source_path, "r", encoding="utf-8") as f:
                    content = f.read()
                content = content.replace("@PYTHON3@", sys.executable)
                content = content.replace("@APP_DIR@", app_root)
                with open(target_path, "w", encoding="utf-8") as f:
                    f.write(content)
            log_event(f"Integración con Caja verificada/instalada en {caja_actions_dir}",
                      origin="LINUX", level="INFO", reason="SETTINGS")

            # Extensión del escritorio: es código de WMM y se mantiene actualizada
            # cuando cambia la plantilla incluida con la aplicación.
            caja_extension_source = os.path.join(caja_source_dir, "wmm-spanned-current.py")
            caja_extensions_dir = os.path.join(data_base, "caja-python", "extensions")
            caja_extension_target = os.path.join(caja_extensions_dir, "wmm-spanned-current.py")

            if not os.path.isfile(caja_extension_source):
                log_event(f"Extensión nativa de Caja no encontrada: {caja_extension_source}",
                          origin="LINUX", level="WARN", reason="SETTINGS")
            else:
                try:
                    with open(caja_extension_source, "r", encoding="utf-8") as f:
                        content = f.read()
                    content = content.replace("@PYTHON3@", sys.executable)
                    content = content.replace("@APP_DIR@", app_root)
                    compile(content, caja_extension_source, "exec")
                    os.makedirs(caja_extensions_dir, exist_ok=True)
                    current_content = None
                    if os.path.isfile(caja_extension_target):
                        with open(caja_extension_target, "r", encoding="utf-8") as f:
                            current_content = f.read()
                    caja_extension_installed = current_content != content
                    if caja_extension_installed:
                        temp_path = f"{caja_extension_target}.wmm.tmp"
                        with open(temp_path, "w", encoding="utf-8", newline="\n") as f:
                            f.write(content)
                        os.replace(temp_path, caja_extension_target)
                    if caja_extension_installed:
                        log_event(f"Extensión contextual de Caja instalada en {caja_extension_target}",
                                  origin="LINUX", level="INFO", reason="SETTINGS")
                    else:
                        log_event(f"Extensión contextual de Caja verificada en {caja_extension_target}",
                                  origin="LINUX", level="DEBUG", reason="SETTINGS")

                except (OSError, SyntaxError) as e:
                    log_event(f"No se pudo instalar la extensión contextual de Caja: {e}",
                              origin="LINUX", level="WARN", reason="SETTINGS")

    # --- 4. NEMO: ACCIONES CONTEXTUALES ---
    # Instala las acciones nativas de Nemo sin sobrescribir personalizaciones,
    # mantiene el layout WMM y retira wrappers legacy del destino de Nemo.
    if shutil.which("nemo"):
        nemo_source_dir = os.path.join(source_dir, "nemo")
        nemo_actions_dir = os.path.join(data_base, "nemo", "actions")
        nemo_files = (
            "wmm-send-to.nemo_action",
            "wmm-add_to_bookmarks.nemo_action",
            "wmm-spanned-current.nemo_action",
            "wmm-span-image.nemo_action",)

        if not os.path.isdir(nemo_source_dir):
            log_event(f"Directorio de plantillas Nemo no encontrado: {nemo_source_dir}",
                      origin="LINUX", level="WARN", reason="SETTINGS")
        else:
            os.makedirs(nemo_actions_dir, exist_ok=True)

            # Acciones de Nemo: se crean sólo si no existen para preservar
            # traducciones, ajustes o personalizaciones realizadas por el usuario.
            for filename in nemo_files:
                source_path = os.path.join(nemo_source_dir, filename)
                target_path = os.path.join(nemo_actions_dir, filename)

                if os.path.exists(target_path):
                    continue

                if not os.path.exists(source_path):
                    log_event(f"Plantilla Nemo no encontrada: {source_path}",
                              origin="LINUX", level="WARN", reason="SETTINGS")
                    continue

                with open(source_path, "r", encoding="utf-8") as f:
                    content = f.read()

                content = content.replace("@PYTHON3@", sys.executable)
                content = content.replace("@APP_DIR@", app_root)

                with open(target_path, "w", encoding="utf-8") as f:
                    f.write(content)

            if all(os.path.exists(os.path.join(nemo_actions_dir, filename)) for filename in nemo_files):
                _ensure_nemo_wmm_layout(data_base)

                # Wrappers legacy: se retiran únicamente cuando las acciones
                # actuales de Nemo ya están instaladas correctamente.
                for filename in ("wmm-add_to_bookmarks.sh", "wmm-send-to-monitor.sh"):
                    legacy_path = os.path.join(nemo_actions_dir, filename)

                    if os.path.isfile(legacy_path):
                        try:
                            os.remove(legacy_path)
                            log_event(f"Script legacy de Nemo eliminado: {legacy_path}",
                                      origin="LINUX", level="DEBUG", reason="SETTINGS")
                        except OSError as e:
                            log_event(f"No se pudo eliminar el script legacy de Nemo {legacy_path}: {e}",
                                      origin="LINUX", level="WARN", reason="SETTINGS")

            log_event(f"Integración con Nemo verificada/instalada en {nemo_actions_dir}",
                      origin="LINUX", level="INFO", reason="SETTINGS")

def normalize_platform(raw_platform):
    if raw_platform.startswith('linux'):
        return 'linux'
    return raw_platform

def normalize_desktop(desktop):
    desktop = desktop.lower()
    if desktop.startswith('x-cinnamon') or desktop == 'cinnamon2d':
        return 'cinnamon'
    if 'mate' in desktop:
        return 'mate'
    if 'gnome' in desktop:
        return 'gnome'
    if 'plasma' in desktop:
        return 'kde'
    return desktop

def detect_desktop():
    desktop = os.environ.get('XDG_CURRENT_DESKTOP',
                             os.environ.get('DESKTOP_SESSION', 'unknown'))
    return desktop.lower()

def get_system_paths():
    data_base = os.environ.get('XDG_DATA_HOME', os.path.expanduser('~/.local/share'))
    cache_base = os.environ.get('XDG_CACHE_HOME', os.path.expanduser('~/.cache'))
    locale_dir = os.path.join(data_base, 'locale')
    cache_dir = os.path.join(cache_base, 'wmm')
    return {
        'data_base': data_base,
        'cache_base': cache_base,
        'locale_dir': locale_dir,
        'cache_dir': cache_dir,
    }

def _load_launch_profiles():
    """Carga los perfiles estáticos de lanzamiento conocidos por WMM."""
    profiles_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "data", "launch_profiles.json")

    try:
        with open(profiles_path, "r", encoding="utf-8") as f:
            profiles = json.load(f)
        return profiles if isinstance(profiles, dict) else {}

    except (OSError, json.JSONDecodeError) as e:
        log_event(f"No se pudieron cargar perfiles de lanzamiento: {e}",
            origin="LINUX", level="WARN", reason="GENERIC")
        return {}

def _build_launch_command(path, capability, params):
    """Construye un lanzamiento enriquecido para la aplicación predeterminada."""
    try:
        from gi.repository import Gio

        file = Gio.File.new_for_path(path)
        info = file.query_info("standard::content-type", Gio.FileQueryInfoFlags.NONE, None)
        content_type = info.get_content_type()
        app_info = Gio.AppInfo.get_default_for_type(content_type, False) if content_type else None

        if not app_info:
            return None

        executable = app_info.get_executable()
        executable_name = os.path.basename(executable) if executable else ""

        if not executable_name:
            return None

        values = {"file": path, **params}

        for profile in _load_launch_profiles().values():
            if executable_name not in profile.get("executables", []):
                continue
            arguments = profile.get(capability)
            if not isinstance(arguments, list):
                return None
            try:
                return [executable] + [argument.format(**values) for argument in arguments]

            except KeyError as e:
                log_event(f"Parámetro de lanzamiento no disponible: {e}",
                    origin="LINUX", level="WARN", reason="GENERIC")
                return None

    except Exception as e:
        log_event(f"No se pudo resolver la aplicación predeterminada: {e}",
            origin="LINUX", level="WARN", reason="GENERIC")
        return None

def open_file(path, capability=None, **params):
    """
    Abre una ruta con la aplicación predeterminada.

    Si se solicita una capacidad conocida y la aplicación predeterminada
    dispone de un perfil compatible, aplica sus parámetros específicos.
    En cualquier otro caso conserva el comportamiento normal mediante xdg-open.
    """
    if capability:
        command = _build_launch_command(path, capability, params)
        if command:
            try:
                subprocess.Popen(command)
                return

            except OSError as e:
                log_event(f"No se pudo ejecutar lanzamiento enriquecido: {e}",
                    origin="LINUX", level="WARN", reason="GENERIC")
    subprocess.run(["xdg-open", path], check=False)

def compile_translations(app_root, locale_dir, app_domain):
    """Compila traducciones pendientes y devuelve True si algún .mo fue creado o actualizado."""
    po_dir = os.path.join(app_root, "wmm_platform", "shell", "po")
    if not os.path.isdir(po_dir):
        return False

    translations_changed = False

    for po_file in os.listdir(po_dir):
        if not po_file.endswith(".po"):
            continue

        lang = os.path.splitext(po_file)[0]
        mo_dir = os.path.join(locale_dir, lang, "LC_MESSAGES")
        mo_file = os.path.join(mo_dir, f"{app_domain}.mo")
        po_path = os.path.join(po_dir, po_file)

        if not os.path.exists(mo_file) or os.path.getmtime(po_path) > os.path.getmtime(mo_file):
            try:
                os.makedirs(mo_dir, exist_ok=True)
                result = subprocess.run(
                    ["msgfmt", po_path, "-o", mo_file],
                    check=False, capture_output=True, text=True)
                if result.returncode == 0 and os.path.isfile(mo_file):
                    translations_changed = True
                else:
                    log_event(f"Error compilando traducción '{po_file}': {result.stderr.strip()}",
                              origin="LINUX", level="ERROR", reason="SETTINGS")
            except Exception as e:
                log_event(f"Excepción compilando traducción '{po_file}': {e}",
                          origin="LINUX", level="ERROR", reason="SETTINGS")
    return translations_changed

def send_notification(title, message, level="info"):
    icon_map = {
        "info": "dialog-information-symbolic",
        "warn": "dialog-warning-symbolic",
        "error": "dialog-error-symbolic"
    }
    selected_icon = icon_map.get(level, "dialog-information")
    try:
        subprocess.run(["notify-send", "-i", selected_icon, title, message, "-a", "WMM"], check=False)
    except Exception as e:
        print(f" [!] Error en notificación: {e}")

def init_channels():
    """
    Registra todos los canales de comunicación soportados por Linux.

    La función expone al núcleo todos los mecanismos de comunicación
    disponibles en este sistema operativo. No decide qué cliente
    utilizará cada canal; únicamente los registra para que la
    infraestructura de comunicación de WMM pueda utilizarlos.
    """

    from wmm_platform.channels import register_channel, DBusChannel, FileChannel

    # FileChannel
    try:
        register_channel("file", FileChannel())
        log_event("Canal File registrado", origin="LINUX", level="INFO", reason="COMMAND")
    except Exception as e:
        log_event(f"No se pudo registrar FileChannel: {e}",
                  origin="LINUX", level="ERROR", reason="COMMAND")

    # D-Bus
    try:
        register_channel("dbus", DBusChannel())
        log_event("Canal D-Bus registrado", origin="LINUX", level="INFO", reason="COMMAND")
    except Exception as e:
        log_event(f"No se pudo registrar DBusChannel: {e}",
                  origin="LINUX", level="ERROR", reason="COMMAND")
