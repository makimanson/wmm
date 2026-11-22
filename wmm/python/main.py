#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later
"""
WMM - Wallpaper Multi-Monitor Manager
----------------------------
main.py – Motor principal de WMM.
"""
# ==========================================================
# IMPORTS DE LIBRERÍA ESTÁNDAR
# ==========================================================
import os
import sys
import time
import random
import json
import atexit
import subprocess
import threading

# ==========================================================
# CONFIGURACIÓN DEL PATH DEL PROYECTO
# ==========================================================
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

# ==========================================================
# IMPORTS DE TERCEROS (GTK)
# ==========================================================
import gi
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk, GLib

# ==========================================================
# IMPORTS DE MÓDULOS DEL PROYECTO
# ==========================================================
from wmm_platform.core import PlatformManager
from config_handler import ConfigHandler
from image_engine import ImageEngine
from debug_logger import log_event
from i18n import _, initialize
from image_selection import ImageSelectionEngine, build_edit_preview_selection
from monitor_manager import get_spanned_reference_hash
import monitor_detection

class WMMDaemon:
    def __init__(self):
        # ----------------------------------------------------------
        # 1. INICIALIZAR LA PLATAFORMA
        # ----------------------------------------------------------
        self.platform = PlatformManager()

        if hasattr(self.platform, "set_process_name"):
            self.platform.set_process_name("WMM Engine")

        self._translations_changed = False

        # ----------------------------------------------------------
        # 2. COMPLETAR EL .INI SI ES NECESARIO (antes de ConfigHandler)
        # ----------------------------------------------------------
        self._complete_ini_if_needed()

        # ----------------------------------------------------------
        # 3. CONFIGURAR EL SISTEMA DE TRADUCCIONES
        # ----------------------------------------------------------
        initialize(self.platform)

        # ----------------------------------------------------------
        # 4. INICIALIZAR EL GESTOR DE CONFIGURACIÓN
        # ----------------------------------------------------------
        # ConfigHandler recibe la ruta de caché directamente desde PlatformManager
        self.ch = ConfigHandler(cache_base_dir=self.platform.cache_dir, platform=self.platform)

        # Los frontends pueden considerar org.maki.wmm como señal de que WMM
        # está listo. Garantizamos por ello que los catálogos existan antes
        # de publicar el servicio D-Bus más adelante en este mismo __init__.
        self._ensure_translations()

        if getattr(self, "_post_install_needed", False):
            self._post_install_setup()
        # ----------------------------------------------------------
        # 5. INICIALIZAR EL RESTO DE COMPONENTES
        # ----------------------------------------------------------
        self.ie = ImageEngine(self.ch, None)  # None temporal hasta migrar MonitorManager
        self.selection_engine = ImageSelectionEngine(self.ch, self.platform)
        self.loop = GLib.MainLoop()
        self.timer_id = None
        self.rotation_queue = []
        self.last_rotated_hash = None
        self.display = Gdk.Display.get_default()
        self._busy = False
        self._status_path = os.path.join(self.ch.cache_dir, "engine_status.json")

        # 1. Gestión del archivo PID
        self._manage_pid_file()

        # Publicar el estado inicial sólo después de adquirir la instancia.
        # Evita que un busy=True residual de un cierre anómalo bloquee nuevas
        # peticiones y que una instancia duplicada altere el estado del engine válido.
        self._set_busy_state(False)

        # 2. Registro de limpieza al salir (DENTRO del __init__)
        atexit.register(self._cleanup_on_exit)

        # 3. Iniciar comandos y consultas independientes.
        self.platform.init_channels()
        self.platform.start_receiving_commands(
            self._dispatch_command, query_callback=self._query_frontend)

        # Publicar en los canales recién registrados el estado autoritativo
        # que el engine ya estableció después de adquirir la instancia.
        self.platform.emit_busy_changed(self._busy)

        # Iniciar monitorización de cambios de hardware (delegado en la plataforma)
        if not self.platform.init_monitor_events(self._on_hardware_event):
            log_event("No se pudo iniciar la monitorización de hardware...",
                origin="ENGINE", level="WARN", reason="HARDWARE")

    def _query_frontend(self, query):
        """
        Resuelve consultas de lectura mediante las autoridades existentes.
        El canal transporta el resultado; no interpreta estados de plataforma.
        """
        if query != "keybinding" or not hasattr(self.platform, "request_keybindings"):
            return ""

        result = self.platform.request_keybindings(self.ch.data_dir, {"action": "get"})

        if not result.get("ok"):
            log_event(f"No se pudo consultar el atajo: {result.get('error')}",
                origin="ENGINE", level="WARN", reason="SETTINGS")
            return ""

        # Reutilizar exactamente la presentación del formulario común.
        from keybinding_manager import format_keybinding
        return format_keybinding(result.get("shortcut"))

    def _do_cycle_and_notify(self, reason, target_hashes, target_bookmark, temp_settings, event_dict):
        """
        Ejecuta el ciclo de rotación y, al terminar, notifica al panel.
        """
        log_event(f"Ejecutando ciclo: {reason}",
            origin="ENGINE", level="DEBUG", reason="COMMAND")
        was_busy = self._busy
        try:
            self.execute_full_cycle(
                reason=reason,
                target_hashes=target_hashes,
                target_bookmark=target_bookmark,
                temp_settings=temp_settings)
        except Exception as e:
            if not was_busy and self._busy: self._set_busy_state(False)
            log_event(f"Error durante el ciclo '{reason}': {type(e).__name__}: {e}",
                origin="ENGINE", level="ERROR", reason="COMMAND")
            raise
        self._notify_panel(event_dict)
        return False  # Para GLib.idle_add

    def _set_busy_state(self, busy):
        self._busy = busy
        try:
            with open(self._status_path, "w") as f: json.dump({"busy": busy}, f)
        except Exception:
            pass

        self.platform.emit_busy_changed(busy)

    def _notify_panel(self, event_dict):
        """
        Envía un evento al panel de control, si está abierto.

        Las plataformas con transporte nativo pueden entregarlo directamente.
        El archivo command_panel.json permanece como mecanismo histórico para
        las plataformas que no implementan ese canal.
        """
        # Windows evita FileMonitor porque CHANGES_DONE_HINT no tiene allí la
        # misma inmediatez que bajo inotify. Si no existe receptor nativo,
        # conservar el mecanismo histórico sin convertirlo en un error.
        if self.platform.send_panel_event(event_dict):
            log_event(f"Evento '{event_dict.get('action')}' enviado al panel",
                origin="ENGINE", level="DEBUG", reason="COMMAND")
            return

        command_path = os.path.join(self.ch.data_dir, "command_panel.json")

        try:
            with open(command_path, "w", encoding="utf-8") as f:
                json.dump(event_dict, f)

            log_event(f"Evento '{event_dict.get('action')}' enviado al panel",
                origin="ENGINE", level="DEBUG", reason="COMMAND")

        except Exception as e:
            log_event(f"Error al escribir command_panel.json: {e}",
                origin="ENGINE", level="ERROR", reason="COMMAND")

    def _spawn_child(self, argv, env=None):
        """Lanza un proceso hijo y recoge su estado al terminar sin bloquear el engine."""
        process = subprocess.Popen(argv, start_new_session=True, env=env)
        threading.Thread(target=process.wait, name=f"WMMChildWait-{process.pid}", daemon=True).start()

        return process

    def _cleanup_on_exit(self):
        """Libera el lock y borra el PID sólo si pertenece a esta instancia."""
        pid_path = os.path.join(self.ch.cache_dir, "pid_main.pid")
        pid_file = getattr(self, "_pid_file", None)
        removed = False

        try:
            if pid_file is not None and not pid_file.closed and os.path.exists(pid_path):
                try:
                    # Confirmar que la ruta sigue apuntando exactamente
                    # al mismo archivo que esta instancia mantiene bloqueado.
                    locked_stat = os.fstat(pid_file.fileno())
                    path_stat = os.stat(pid_path)

                    if (locked_stat.st_dev, locked_stat.st_ino) == (path_stat.st_dev, path_stat.st_ino):
                        pid_file.seek(0)
                        content = pid_file.read().strip()

                        if content and int(content) == os.getpid():
                            os.remove(pid_path)
                            removed = True

                except (OSError, ValueError):
                    pass

        finally:
            if pid_file is not None and not pid_file.closed:
                try:
                    self.platform.unlock_file(pid_file)
                except OSError:
                    pass

                try:
                    pid_file.close()
                except OSError:
                    pass

            self._pid_file = None

        if removed:
            log_event("Archivo PID eliminado. Cierre limpio.",
                origin="ENGINE", level="INFO", reason="NOTIFY")

    def _manage_pid_file(self):
        """Mantiene un lock exclusivo sobre el archivo PID durante toda la vida del engine."""
        pid_path = os.path.join(self.ch.cache_dir, "pid_main.pid")
        os.makedirs(os.path.dirname(pid_path), exist_ok=True)

        # El descriptor permanece abierto durante toda la vida del engine.
        # La existencia del archivo no determina si WMM está activo:
        # la autoridad es el lock mantenido por el proceso.
        self._pid_file = open(pid_path, "a+")

        try:
            acquired = self.platform.try_lock_file(self._pid_file)
        except OSError:
            self._pid_file.close()
            self._pid_file = None
            raise

        if not acquired:
            self._pid_file.seek(0)
            content = self._pid_file.read().strip()

            self._pid_file.close()
            self._pid_file = None

            pid_text = content if content else "desconocido"
            print(f" [!] El engine ya está corriendo (PID {pid_text}). Abortando.")
            raise SystemExit(1)

        # Tenemos el lock: cualquier contenido anterior es obsoleto.
        self._pid_file.seek(0)
        self._pid_file.truncate()
        self._pid_file.write(str(os.getpid()))
        self._pid_file.flush()

        print(f" [SISTEMA] PID {os.getpid()} registrado en {pid_path}")

    def _apply_edit_preview(self, snapshot):
        """Renderiza una composición temporal sin sincronizar ni escribir el Vault."""
        if self._busy:
            log_event("Vista previa de edición omitida: engine ocupado",
                origin="ENGINE", level="DEBUG", reason="COMMAND")
            return False

        edit_session = snapshot.get("session", {})
        edit_states = snapshot.get("states", {})

        if not isinstance(edit_session, dict) or not isinstance(edit_states, dict):
            log_event("Vista previa de edición con datos inválidos",
                origin="ENGINE", level="ERROR", reason="COMMAND")
            return False

        monitors_map = self.ch.load_json("geometry").get("monitors", {})
        if not monitors_map:
            log_event("Vista previa sin geometría de monitores",
                origin="ENGINE", level="WARN", reason="HARDWARE")
            return False

        self._set_busy_state(True)

        try:
            settings_data = self.ch.load_json("settings")
            settings = settings_data.get("global", {})
            vault_session = self.ch.load_json("vault").get("active_session", {})

            color_mode = settings.get("color_mode", "solid_color")
            solid_color = settings.get("solid_color", "#000000")
            gradient_h = settings.get("gradient_h", ["#000000", "#8D9797"])
            gradient_v = settings.get("gradient_v", ["#000000", "#8D9797"])
            color = ("color", color_mode, solid_color, gradient_h, gradient_v)

            wp_mode = snapshot.get("wallpaper_mode") or settings.get("wallpaper_mode", "fit")
            image_effect = snapshot.get("wallpaper_effect") or settings.get("wallpaper_effect", "none")
            effect_scope = snapshot.get("wallpaper_effect_scope") or settings.get("wallpaper_effect_scope", "blur")
            spanned = snapshot.get("spanned_enabled")
            if spanned is None:
                spanned = settings.get("spanned_enabled", False)

            # La selección temporal pertenece a ImageSelection.
            # Main conserva la orquestación y la aplicación física.
            selection = build_edit_preview_selection(
                monitors_map=monitors_map,
                vault_session=vault_session,
                edit_session=edit_session,
                edit_states=edit_states,
                color=color,
                spanned=spanned,
                source_hash=snapshot.get("source_hash")
            )

            if not selection:
                return False

            processed_images = self.ie._process_single_image(
                selection=selection,
                monitors_map=monitors_map,
                spanned_enabled=spanned,
                solid_color=solid_color,
                color_mode=color_mode,
                gradient_h=gradient_h,
                gradient_v=gradient_v,
                wallpaper_effect_scope=effect_scope,
                wallpaper_mode=wp_mode,
                image_effect=image_effect
            )

            if not processed_images:
                log_event("Vista previa de edición sin imágenes procesadas",
                    origin="ENGINE", level="WARN", reason="LIBRARY")
                return False

            # La edición física tiene prioridad sobre las rotaciones programadas.
            if settings.get("slideshow_enabled", False):
                settings["slideshow_enabled"] = False
                self.ch.save_json("settings", settings_data)
                self._notify_panel({"action": "settings_updated"})

            if self.timer_id is not None:
                self.manage_timer(action="stop")

            applied = self.platform.render_master_wallpaper(
                processed_images=processed_images,
                monitors_map=monitors_map,
                config_handler=self.ch
            )

            if applied is False:
                log_event("No se pudo aplicar la vista previa física",
                    origin="ENGINE", level="ERROR", reason="LIBRARY")
            else:
                log_event(
                    f"Vista previa física aplicada: {len(processed_images)} monitores; "
                    f"spanned={spanned}; modo={wp_mode}; efecto={image_effect}",
                    origin="ENGINE", level="INFO", reason="LIBRARY")

        except Exception as error:
            log_event(f"Error en vista previa física: {type(error).__name__}: {error}",
                origin="ENGINE", level="ERROR", reason="COMMAND")
        finally:
            self._set_busy_state(False)

        return False

    def _apply_spanned_image(self, image_path, monitors_map=None):
        """Aplica una imagen concreta en modo Spanned temporal."""
        if not image_path or not os.path.exists(image_path):
            log_event(f"Ruta de imagen inválida para Spanned: {image_path}",
                origin="ENGINE", level="ERROR", reason="COMMAND")
            return

        if monitors_map is None:
            geometry = self.ch.load_json("geometry")
            monitors_map = geometry.get("monitors", {})

        reference_hash = get_spanned_reference_hash(monitors_map)
        if reference_hash is None:
            log_event("No hay geometría válida para aplicar Spanned",
                origin="ENGINE", level="WARN", reason="COMMAND")
            return

        if self._busy:
            log_event("Acción Spanned ignorada: motor ocupado",
                origin="ENGINE", level="DEBUG", reason="COMMAND")
            return

        self._set_busy_state(True)

        try:
            settings = self.ch.load_json("settings").get("global", {})
            selection = {reference_hash: image_path}

            wp_mode = settings.get("wallpaper_mode", "fit")
            wallpaper_effect = settings.get("wallpaper_effect", "none")
            wallpaper_effect_scope = settings.get("wallpaper_effect_scope", "blur")
            solid_color = settings.get("solid_color", "#000000")
            color_mode = settings.get("color_mode", "solid_color")
            gradient_h = settings.get("gradient_h", ["#000000", "#8D9797"])
            gradient_v = settings.get("gradient_v", ["#000000", "#8D9797"])

            processed_images = self.ie._process_single_image(
                selection=selection,
                monitors_map=monitors_map,
                spanned_enabled=True,
                solid_color=solid_color,
                color_mode=color_mode,
                gradient_h=gradient_h,
                gradient_v=gradient_v,
                wallpaper_effect_scope=wallpaper_effect_scope,
                wallpaper_mode=wp_mode,
                image_effect=wallpaper_effect)

            if not processed_images:
                log_event(f"No se pudo procesar la imagen para Spanned: {image_path}",
                    origin="ENGINE", level="WARN", reason="COMMAND")
                return

            rendered = self.platform.render_master_wallpaper(
                processed_images=processed_images,
                monitors_map=monitors_map,
                config_handler=self.ch)

            if not rendered:
                log_event(f"No se pudo aplicar la imagen en modo Spanned: {image_path}",
                    origin="ENGINE", level="WARN", reason="COMMAND")
                return

            log_event(f"Imagen aplicada en modo Spanned: {image_path}",
                origin="ENGINE", level="INFO", reason="COMMAND")

            if settings.get("slideshow_enabled", False):
                self.manage_timer(action="start")

        finally:
            self._set_busy_state(False)

    def _resolve_contextual_image(self, xid=None, x=None, y=None):
        """Resuelve la imagen activa del monitor señalado por contexto X11."""
        geometry = self.ch.load_json("geometry")
        monitors_map = geometry.get("monitors", {})

        if xid:
            m_hash = monitor_detection.get_monitor_hash_from_xid(xid, monitors_map)
            context = f"XID {xid}"
        elif x is not None and y is not None:
            m_hash = monitor_detection.get_monitor_hash_from_position(x, y, monitors_map)
            context = f"posición {x},{y}"
        else:
            log_event("Acción contextual recibida sin contexto de monitor",
                origin="ENGINE", level="WARN", reason="COMMAND")
            return None

        if not m_hash:
            log_event(f"No se pudo resolver el monitor para {context}",
                origin="ENGINE", level="WARN", reason="COMMAND")
            return None

        vault = self.ch.load_json("vault")
        entry = vault.get("active_session", {}).get(m_hash, {})

        if isinstance(entry, dict):
            image_path = entry.get("path")
            is_active = entry.get("active", True)
        else:
            image_path = entry
            is_active = True

        if not is_active or not image_path or not os.path.exists(image_path):
            log_event(f"No hay una imagen activa válida para el monitor {m_hash}",
                origin="ENGINE", level="WARN", reason="COMMAND")
            return None

        return image_path, monitors_map

    def _apply_contextual_spanned(self, xid=None, x=None, y=None):
        """Aplica en modo Spanned la imagen actualmente expuesta en el monitor señalado por contexto X11."""
        resolved = self._resolve_contextual_image(xid=xid, x=x, y=y)
        if not resolved:
            return

        image_path, monitors_map = resolved
        self._apply_spanned_image(image_path, monitors_map)

    def _dispatch_command(self, order, action_data):
        """
        Ejecuta la acción correspondiente basada en el comando recibido.
        (Antiguo _handle_sigusr1, extraído para separar la recepción de la ejecución)
        """
        # Normalizar acciones contextuales antes del dispatch evita duplicar
        # los workflows finales que ya reciben una ruta de imagen.
        if order == ConfigHandler.CMD_SHELL_ADD_FAV_CURRENT:
            resolved = self._resolve_contextual_image(
                xid=action_data.get("xid"),
                x=action_data.get("x"),
                y=action_data.get("y"))
            if not resolved:
                return

            image_path, _monitors_map = resolved
            order = ConfigHandler.CMD_SHELL_ADD_FAV
            action_data = {"action": order, "image_path": image_path}

        # --- 1. ACTUALIZACIÓN DE SETTINGS ---
        if order == ConfigHandler.CMD_UPDATE_TIMER:
            settings = self.ch.load_json("settings")
            g = settings["global"]
            favorites_was_enabled = g.get("slideshow_bookmark", False)

            # Panel y frontends comparten este comando; los campos omitidos
            # conservan su valor anterior.
            g["slideshow_enabled"] = action_data.get("enabled", g["slideshow_enabled"])
            g["slideshow_interval"] = int(action_data.get("interval", g["slideshow_interval"]))
            g["slideshow_mode"] = action_data.get("mode", g["slideshow_mode"])
            g["slideshow_bookmark"] = action_data.get("slideshow_bookmark", g["slideshow_bookmark"])
            g["spanned_enabled"] = action_data.get("spanned_enabled", g.get("spanned_enabled", False))

            # Una nueva activación de Favorites Only sustituye Selective
            # Rotation y requiere Slideshow. No aplicar esta regla cuando
            # otros controles reenvían un Favorites Only ya activado.
            if g["slideshow_bookmark"] and not favorites_was_enabled:
                g["selective_rotation_enabled"] = False
                g["slideshow_enabled"] = True

            self.ch.save_json("settings", settings)
            GLib.idle_add(self._notify_panel, {"action": "settings_updated"})

            # Gestión del Temporizador
            GLib.idle_add(self.manage_timer, "start")

            log_event(f"Settings actualizados: enabled={g['slideshow_enabled']}, "
                f"interval={g['slideshow_interval']}, mode={g['slideshow_mode']}, "
                f"bookmark={g['slideshow_bookmark']}, spanned={g['spanned_enabled']}",
                origin="ENGINE", level="INFO", reason="SETTINGS")

        # --- 1a. ROTACIÓN SELECTIVA ---
        # La activación selectiva sustituye Favorites Only y requiere Slideshow.
        # La desactivación no restaura automáticamente modos anteriores.
        elif order == ConfigHandler.CMD_SET_SELECTIVE_ROTATION:
            enabled = action_data.get("enabled")
            if not isinstance(enabled, bool):
                return

            # La elegibilidad pertenece al índice, no a los pools pendientes.
            if enabled:
                index = self.ch.load_json("index")
                available = any(
                    isinstance(entry, list) and len(entry) == 2
                    and entry[0] and entry[1]
                    for entry in index.values())

                if not available:
                    log_event("Rotación selectiva rechazada: sin carpetas elegibles",
                        origin="ENGINE", level="WARN", reason="SETTINGS")
                    self._notify_panel({"action": "settings_updated"})
                    return

            settings = self.ch.load_json("settings")
            g = settings["global"]
            slideshow_was_enabled = g.get("slideshow_enabled", True)

            g["selective_rotation_enabled"] = enabled

            if enabled:
                g["slideshow_bookmark"] = False
                g["slideshow_enabled"] = True

            self.ch.save_json("settings", settings)
            GLib.idle_add(self._notify_panel, {"action": "settings_updated"})

            # Sólo arrancar el temporizador si Slideshow estaba apagado.
            if enabled and not slideshow_was_enabled:
                GLib.idle_add(self.manage_timer, "start")

        # --- 1b. METADATOS DE IMAGEN ---
        # Persistir el cambio antes de recomponer: el renderizado consulta
        # settings.json, igual que cuando la operación procede del Panel.
        elif order == ConfigHandler.CMD_SET_METADATA_ENABLED:
            enabled = action_data.get("enabled")
            if not isinstance(enabled, bool):
                return

            settings = self.ch.load_json("settings")
            settings["global"]["exif_metadata_enabled"] = enabled
            self.ch.save_json("settings", settings)

            GLib.idle_add(self._notify_panel, {"action": "settings_updated"})
            GLib.idle_add(self._do_cycle_and_notify, ConfigHandler.REASON_SELECTION,
                None, None, None, {"action": "wallpaper_changed"})

        # --- 2. CARGA DE FAVORITO ESPECÍFICO ---
        elif order == ConfigHandler.CMD_LOAD_BOOKMARK:
            name = action_data.get("name")

            # Soporte para apagar el timer si el favorito es una carga manual
            if action_data.get("timer_force_off"):
                settings = self.ch.load_json("settings")
                settings["global"]["slideshow_enabled"] = False
                self.ch.save_json("settings", settings)
                GLib.idle_add(self.manage_timer, "stop")
                log_event("Temporizador detenido por carga manual de favorito",
                    origin="ENGINE", level="INFO", reason="TIMER")

            log_event(f"Cargando favorito: {name}",
                origin="ENGINE", level="INFO", reason="BOOKMARK")
            GLib.idle_add(self._do_cycle_and_notify, ConfigHandler.REASON_BOOKMARK,
                None, name, None, {"action": "wallpaper_changed"})

        # --- 2.1 ELIMINACION DE FAVORITO ESPECÍFICO ---
        elif order == ConfigHandler.CMD_DELETE_BOOKMARK:
            name = action_data.get("name")
            if name:
                log_event(f"Eliminando favorito: {name}",
                    origin="ENGINE", level="INFO", reason="BOOKMARK")
                if self.ch.delete_bookmark(name):
                    log_event(f"Favorito '{name}' eliminado correctamente",
                        origin="ENGINE", level="INFO", reason="BOOKMARK")
                    self._notify_panel({"action": "bookmarks_updated"})
                    self.ch._send_notification(
                        reason=_("Favorite deleted"),
                        detail_msg=_("Preset") + " '" + name + "'\n" + _("deleted successfully."),
                        level="info")
                else:
                    log_event(f"No se pudo eliminar el favorito '{name}'",
                        origin="ENGINE", level="ERROR", reason="BOOKMARK")

        # --- 3. ACCIONES MANUALES ---
        elif order == ConfigHandler.CMD_FORCE_ROTATION:
            # ENGINE GUARD:
            # Última defensa ante clientes que no aplican admission guard.
            # No sustituye el filtrado temprano: una petición puede haber nacido
            # durante busy y llegar aquí más tarde, cuando el engine ya esté idle.
            if self._busy:
                log_event("force_rotation descartado en dispatch: motor ocupado",
                    origin="ENGINE", level="DEBUG", reason="COMMAND")
                return

            log_event("Rotación manual solicitada",
                origin="ENGINE", level="INFO", reason="LIBRARY")
            GLib.idle_add(self._do_cycle_and_notify, ConfigHandler.REASON_MANUAL,
                None, None, None, {"action": "wallpaper_changed"})

        # --- 4. MANTENIMIENTO ---
        elif order == ConfigHandler.CMD_SYNC_LIBRARY:
            log_event("Sincronizando biblioteca de imágenes...",
                origin="ENGINE", level="INFO", reason="LIBRARY")
            result = self.ch.sync_library()
            if result and len(result) == 4:
                total_h, total_v, has_changes, detail_msg = result
                if has_changes:
                    reason = _("Changes detected")
                else:
                    reason = _("No changes")
                log_event(f"Sincronización completada: {total_h}H / {total_v}V, cambios={has_changes}",
                          origin="ENGINE", level="INFO", reason="LIBRARY")
                body = reason + "\n" + _("Total library") + ": {}H | {}V".format(total_h, total_v)
                if detail_msg:
                    body = f"{detail_msg}\n{body}"
                self.ch._send_notification(
                    reason="WMM: " + _("Synchronization"), detail_msg=body, level="info")

        # --- 5. ABRIR PANEL DE CONTROL ---
        elif order == ConfigHandler.CMD_OPEN_PANEL:
            log_event("Abriendo panel de control", origin="ENGINE", level="INFO", reason="COMMAND")
            panel_path = os.path.join(os.path.dirname(__file__), "panel.py")
            try:
                self._spawn_child([sys.executable, panel_path])
                log_event("Panel lanzado correctamente",
                    origin="ENGINE", level="DEBUG", reason="COMMAND")
            except Exception as e:
                log_event(f"No se pudo abrir el panel: {e}",
                    origin="ENGINE", level="ERROR", reason="COMMAND")

        # --- 5b. AÑADIR FAVORITO (PRESET) ---
        elif order == ConfigHandler.CMD_ADD_BOOKMARK:
            log_event("Lanzando asistente de añadir favorito",
                origin="ENGINE", level="INFO", reason="BOOKMARK")
            add_bookmark_path = os.path.join(os.path.dirname(__file__), "add_bookmark.py")

            command = [sys.executable, add_bookmark_path]

            # Los frontends pueden aportar un punto de apertura; sin él,
            # el formulario conserva su posicionamiento histórico.
            x = action_data.get("x")
            y = action_data.get("y")

            if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                command.extend([str(int(x)), str(int(y))])

            try:
                child_env = self.platform.get_positioned_gtk_child_env()
                self._spawn_child(command, env=child_env)
                log_event("Asistente de favorito lanzado correctamente",
                    origin="ENGINE", level="DEBUG", reason="BOOKMARK")
            except Exception as e:
                log_event(f"No se pudo abrir el asistente de favorito: {e}",
                    origin="ENGINE", level="ERROR", reason="BOOKMARK")

        # --- 5c. ABRIR DOCUMENTACIÓN DE AYUDA ---
        elif order == ConfigHandler.CMD_OPEN_HELP:
            log_event("Lanzando documentación de ayuda",
                origin="ENGINE", level="INFO", reason="COMMAND")
            docs_viewer_path = os.path.join(os.path.dirname(__file__), "docs_viewer.py")
            try:
                self._spawn_child([sys.executable, docs_viewer_path, "help/HELP.md"])
                log_event("Documentación de ayuda lanzada correctamente",
                    origin="ENGINE", level="DEBUG", reason="COMMAND")
            except Exception as e:
                log_event(f"No se pudo abrir la documentación de ayuda: {e}",
                    origin="ENGINE", level="ERROR", reason="COMMAND")

        # --- 5d. ABRIR GESTOR DE ATAJO ---
        elif order == ConfigHandler.CMD_OPEN_KEYBINDING:
            log_event("Lanzando gestor de atajo de teclado",
                origin="ENGINE", level="INFO", reason="COMMAND")

            keybinding_path = os.path.join(
                os.path.dirname(__file__), "keybinding_manager.py")

            command = [sys.executable, keybinding_path]

            # Los frontends pueden aportar un punto de apertura; sin él,
            # el formulario conserva su posicionamiento histórico.
            x = action_data.get("x")
            y = action_data.get("y")

            if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                command.extend([str(int(x)), str(int(y))])

            try:
                child_env = self.platform.get_positioned_gtk_child_env()
                self._spawn_child(command, env=child_env)

                log_event("Gestor de atajo de teclado lanzado correctamente",
                    origin="ENGINE", level="DEBUG", reason="COMMAND")

            except Exception as e:
                log_event(f"No se pudo abrir el gestor de atajo de teclado: {e}",
                    origin="ENGINE", level="ERROR", reason="COMMAND")

        # --- 5e. ABRIR INFORMACIÓN DE WMM ---
        elif order == ConfigHandler.CMD_OPEN_ABOUT:
            log_event("Lanzando información de WMM",
                origin="ENGINE", level="INFO", reason="COMMAND")
            about_path = os.path.join(os.path.dirname(__file__), "about.py")
            try:
                self._spawn_child([sys.executable, about_path])
                log_event("Información de WMM lanzada correctamente",
                    origin="ENGINE", level="DEBUG", reason="COMMAND")
            except Exception as e:
                log_event(f"No se pudo abrir la información de WMM: {e}",
                    origin="ENGINE", level="ERROR", reason="COMMAND")

        # --- 6. APLICAR SELECCIÓN MANUAL ---
        elif order == ConfigHandler.CMD_APPLY_SELECTION:
            log_event("Aplicando selección manual desde el panel",
                origin="ENGINE", level="INFO", reason="COMMAND")
            temp_settings = action_data.get("temp_settings", None)
            target_hash = action_data.get("target_hash")
            target_hashes = [target_hash] if target_hash else None

            GLib.idle_add(self._do_cycle_and_notify, ConfigHandler.REASON_SELECTION,
                target_hashes, None, temp_settings, {"action": "wallpaper_changed"})

        # --- 6b. VISTA PREVIA FÍSICA DEL EDITOR ---
        elif order == ConfigHandler.CMD_APPLY_EDIT_PREVIEW:
            GLib.idle_add(self._apply_edit_preview, action_data)

        # --- 7. Añadir PRESET desde add_bookmark.py ---
        elif order == ConfigHandler.CMD_BOOKMARK_ADDED:
            item_name = action_data.get("name", _("Unknown"))
            log_event(f"Nuevo preset añadido: {item_name}",
                origin="ENGINE", level="INFO", reason="BOOKMARK")
            self.ch._send_notification(
                reason=_("Favorite added"),
                detail_msg=item_name + "'\n" + _("added successfully."),
                level="info")
            self._notify_panel({"action": "bookmarks_updated"})

        # --- 7b. Añadir IMAGEN SUELTA desde shell_add_bookmark.py ---
        elif order == ConfigHandler.CMD_SINGLE_FAVORITE_ADDED:
            item_name = action_data.get("name", _("Unknown"))
            log_event(f"Nueva imagen favorita añadida: {item_name}",
                origin="ENGINE", level="INFO", reason="BOOKMARK")
            self.ch._send_notification(
                reason=_("Favorite added"),
                detail_msg=item_name + "'\n" + _("added successfully."),
                level="info")
            self._notify_panel({"action": "bookmarks_updated"})

        # --- 8. ENVIAR A MONITOR (desde menú contextual del Shell) ---
        elif order == ConfigHandler.CMD_SHELL_SEND_TO:
            image_path = action_data.get("image_path", "")
            if not image_path or not os.path.exists(image_path):
                log_event(f"Ruta de imagen inválida para send_to_monitor: {image_path}",
                    origin="ENGINE", level="ERROR", reason="COMMAND")
                return
            log_event(f"Lanzando diálogo enviar a monitor para: {image_path}",
                origin="ENGINE", level="INFO", reason="COMMAND")
            send_to_monitor_path = os.path.join(os.path.dirname(__file__), "shell_send_to_monitor.py")
            try:
                self._spawn_child([sys.executable, send_to_monitor_path, image_path])
                log_event("Diálogo enviar a monitor lanzado correctamente",
                    origin="ENGINE", level="DEBUG", reason="COMMAND")
            except Exception as e:
                log_event(f"No se pudo abrir el diálogo enviar a monitor: {e}",
                    origin="ENGINE", level="ERROR", reason="COMMAND")

        # --- 9. AÑADIR A FAVORITOS (desde menú contextual del Shell) ---
        elif order == ConfigHandler.CMD_SHELL_ADD_FAV:
            image_path = action_data.get("image_path", "")
            if not image_path or not os.path.exists(image_path):
                log_event(f"Ruta de imagen inválida para shell_add_favorite: {image_path}",
                    origin="ENGINE", level="ERROR", reason="COMMAND")
                return
            log_event(f"Lanzando asistente añadir a favoritos para: {image_path}",
                origin="ENGINE", level="INFO", reason="COMMAND")
            add_fav_path = os.path.join(os.path.dirname(__file__), "shell_add_bookmark.py")
            try:
                self._spawn_child([sys.executable, add_fav_path, image_path])
                log_event("Asistente añadir a favoritos lanzado correctamente",
                    origin="ENGINE", level="DEBUG", reason="COMMAND")
            except Exception as e:
                log_event(f"No se pudo abrir el asistente añadir a favoritos: {e}",
                    origin="ENGINE", level="ERROR", reason="COMMAND")

        # --- 10. DISTRIBUIR IMAGEN ACTUAL DEL MONITOR ---
        elif order == ConfigHandler.CMD_SHELL_SPANNED_CURRENT:
            self._apply_contextual_spanned(
                xid=action_data.get("xid"),
                x=action_data.get("x"),
                y=action_data.get("y"))

        # --- 11. EXTENDER IMAGEN SELECCIONADA ---
        elif order == ConfigHandler.CMD_SHELL_SPANNED_IMAGE:
            self._apply_spanned_image(action_data.get("image_path", ""))

        # --- 12. Cerrar WMM ---
        elif order == "shutdown":
            log_event("Cierre global de WMM solicitado",
                origin="ENGINE", level="INFO", reason="COMMAND")
            self._notify_panel({"action": "shutdown"})
            raise SystemExit

        else:
            log_event(f"Orden desconocida recibida: {order}",
                origin="ENGINE", level="WARN", reason="COMMAND")

    def _timer_callback(self):
        """
        Callback del temporizador. Ejecuta un ciclo de rotación
        y notifica al panel.
        """
        settings = self.ch.load_json("settings").get("global", {})

        if not settings.get("slideshow_enabled", True):
            self.timer_id = None
            log_event("Temporizador cancelado al disparar: Slideshow desactivado",
                      origin="ENGINE", level="INFO", reason="TIMER")
            return False

        log_event("Temporizador disparado: iniciando rotación",
            origin="ENGINE", level="DEBUG", reason="TIMER")
        self._do_cycle_and_notify(
            reason=ConfigHandler.REASON_TIMER,
            target_hashes=None,
            target_bookmark=None,
            temp_settings=None,
            event_dict={"action": "wallpaper_changed"}
        )
        return True

    def manage_timer(self, action="start"):
        """
        Gestiona el temporizador de rotación.
        - 'start': inicia o reinicia el temporizador según la configuración.
        - 'stop': detiene el temporizador si está activo.
        """
        if self.timer_id:
            GLib.source_remove(self.timer_id)
            self.timer_id = None

        if action == "stop":
            log_event("Temporizador detenido", origin="ENGINE", level="INFO", reason="TIMER")
            return

        # Acceder a la ruta real: global -> slideshow_...
        settings = self.ch.load_json("settings").get("global", {})
        enabled = settings.get("slideshow_enabled", True)
        interval_min = int(settings.get("slideshow_interval", 15))

        if enabled and interval_min > 0:
            self.timer_id = GLib.timeout_add_seconds(interval_min * 60, self._timer_callback)
            log_event(f"Temporizador activo: cada {interval_min} min",
                origin="ENGINE", level="INFO", reason="TIMER")
        else:
            log_event("Temporizador no iniciado (desactivado o intervalo inválido)",
                origin="ENGINE", level="INFO", reason="TIMER")

    def execute_full_cycle(self, reason=ConfigHandler.REASON_TIMER,
        target_hashes=None, target_bookmark=None, temp_settings=None):
        """
        Orquestador principal del cambio de fondo.
        Respeta el flujo de estabilización, gestión de hardware, lógica async
        e integra el soporte para favoritos y bookmarks específicos.
        """
        friendly_reason = ConfigHandler.EXECUTION_REASONS.get(reason, reason)
        log_event(f"Iniciando ciclo: {friendly_reason}",
            origin="ENGINE", level="INFO", reason="LIBRARY")

        if self._busy:
            log_event("Ciclo ignorado: motor ocupado",
                origin="ENGINE", level="DEBUG", reason="COMMAND")
            return
        self._set_busy_state(True)

        # 1. Estabilización de eventos GDK (Crítico para evitar desajustes)
        context = GLib.MainContext.default()
        while context.pending():
            context.iteration(False)

        # 2. Obtener la realidad actual del hardware
        monitors_map_real = monitor_detection.detect_monitors()
        active_hashes = list(monitors_map_real.keys())

        # --- GESTIÓN DE GEOMETRÍA ---
        if reason in ConfigHandler.RECONFIGURATION_REASONS:
            geo_snapshot, canvas_w, canvas_h = self._update_geometry(monitors_map_real, reason)
            monitors_map = monitors_map_real
        else:
            geo_snapshot = self.ch.load_json("geometry")
            monitors_map = geo_snapshot.get("monitors", monitors_map_real)
            canvas_w = geo_snapshot.get("canvas", {}).get("w", 0)
            canvas_h = geo_snapshot.get("canvas", {}).get("h", 0)

        monitors_map = geo_snapshot.get("monitors", {})

        # 3. Sincronización con el Vault (Estado persistente)
        _discard, vault = self.ch.sync_vault(active_hashes)
        active_session = vault.get("active_session", {})

        # 4. Carga de parámetros de usuario
        settings = self.ch.load_json("settings").get("global", {})
        color_mode = settings.get("color_mode", "solid_color")
        solid_color = settings.get("solid_color", "#000000")
        gradient_h = settings.get("gradient_h", ["#000000", "#8D9797"])
        gradient_v = settings.get("gradient_v", ["#000000", "#8D9797"])
        sl_mode = settings.get("slideshow_mode", "sync")
        wp_mode = settings.get("wallpaper_mode", "fit")
        fav_mode = settings.get("slideshow_bookmark", False)
        current_f_mode = sl_mode.lower()
        spanned_enabled = settings.get("spanned_enabled", False)
        wallpaper_effect_scope = settings.get("wallpaper_effect_scope", "blur")
        wallpaper_effect = settings.get("wallpaper_effect", "none")

        # El centinela: Controla si el motor encuentra material NUEVO o VÁLIDO en este ciclo
        valid_assets_found = False

        # --- CONSTRUCCIÓN DE LA SELECCIÓN (delegado en ImageSelectionEngine) ---
        selection, valid_assets_found, metadata = self.selection_engine.build_selection(
            reason=reason,
            active_hashes=active_hashes,
            monitors_map=monitors_map,
            active_session=active_session,
            settings=settings,
            target_hashes=target_hashes,  # Mantener el destino explícito si existe
            target_bookmark=target_bookmark,
            temp_settings=temp_settings
        )

        # Extraer metadatos para el renderizado
        spanned_enabled = metadata.get("spanned_enabled", False)
        wp_mode = metadata.get("wp_mode", "fit")
        wallpaper_effect = metadata.get("wallpaper_effect", "none")
        wallpaper_effect_scope = metadata.get("wallpaper_effect_scope", "blur")
        solid_color = metadata.get("solid_color", "#000000")
        color_mode = metadata.get("color_mode", "solid_color")
        gradient_h = metadata.get("gradient_h", ["#000000", "#8D9797"])
        gradient_v = metadata.get("gradient_v", ["#000000", "#8D9797"])

        # Registrar la selección resuelta, antes del procesado.
        # Su resultado no constituye todavía una confirmación de aplicación.
        if selection:
            assigned = []

            for m_hash, source in selection.items():
                monitor = monitors_map.get(m_hash, {})
                connector = monitor.get("connector") or m_hash
                target = f"canvas ({connector})" if spanned_enabled else connector

                if isinstance(source, str):
                    description = os.path.basename(source)
                elif isinstance(source, tuple) and source[0] == "color":
                    description = f"color ({source[1]})"
                else:
                    description = repr(source)

                assigned.append(f"{target}: {description}")

            log_event(f"Selección del ciclo: {'; '.join(assigned)}",
                origin="IMG_SEL", level="INFO", reason="LIBRARY")
            log_event(f"Composición: modo={wp_mode}; efecto={wallpaper_effect}; "
                f"alcance={wallpaper_effect_scope}; spanned={spanned_enabled}",
                origin="IMG_SEL", level="INFO", reason="LIBRARY")

        # 5. Renderizado y Aplicación final
        # Si todos los monitores están inactivos, pintar el color de fondo global
        if not valid_assets_found and selection:
            processed_images = self.ie._process_single_image(
                selection=selection,
                monitors_map=monitors_map,
                spanned_enabled=spanned_enabled,
                solid_color=solid_color,
                color_mode=color_mode,
                gradient_h=gradient_h,
                gradient_v=gradient_v,
                wallpaper_effect_scope=wallpaper_effect_scope,
                wallpaper_mode=wp_mode,
                image_effect=wallpaper_effect
            )
            applied = self.platform.render_master_wallpaper(
                processed_images=processed_images,
                monitors_map=monitors_map,
                config_handler=self.ch
            )

            if applied is False:
                log_event("Error al aplicar el fondo global sin imágenes válidas",
                    origin="ENGINE", level="ERROR", reason="LIBRARY")
            else:
                log_event("Fondo global aplicado sin imágenes válidas",
                    origin="ENGINE", level="INFO", reason="LIBRARY")

        elif valid_assets_found and selection:
            processed_images = self.ie._process_single_image(
                selection=selection,
                monitors_map=monitors_map,
                spanned_enabled=spanned_enabled,
                solid_color=solid_color,
                color_mode=color_mode,
                gradient_h=gradient_h,
                gradient_v=gradient_v,
                wallpaper_effect_scope=wallpaper_effect_scope,
                wallpaper_mode=wp_mode,
                image_effect=wallpaper_effect
            )
            applied = self.platform.render_master_wallpaper(
                processed_images=processed_images,
                monitors_map=monitors_map,
                config_handler=self.ch
            )

            # El backend es quien confirma la aplicación. No anunciar éxito
            # cuando devuelve explícitamente un fallo.
            if applied is False:
                log_event(f"Error al aplicar el fondo: "
                    f"{len(selection)} monitores, spanned={spanned_enabled}",
                    origin="ENGINE", level="WARN", reason="LIBRARY")
            else:
                log_event(f"Fondo aplicado: {len(selection)} monitores, spanned={spanned_enabled}",
                    origin="ENGINE", level="INFO", reason="LIBRARY")

            # Aseguramos que el temporizador esté corriendo si no lo está
            if self.timer_id is None:
                self.manage_timer(action="start")
        else:
            # LA RED DE SEGURIDAD FINAL
            msg = _("Cycle aborted: not enough images available to complete selection.")
            log_event(msg, origin="ENGINE", level="WARN", reason="LIBRARY")
            self.ch._send_notification(
                reason=_("No images available"),
                action=_("Check status of Image Sources in Control Panel."),
                detail_msg=msg,
                level="error")

            # Forzamos el inicio del timer para que reintente en el próximo intervalo
            if self.timer_id is None:
                self.manage_timer(action="start")

        self._set_busy_state(False)

    def _on_hardware_event(self, event_type):
        # Si ya hay un timer pendiente, no logueamos (ya se logueó el primer evento)
        if hasattr(self, '_reconfig_timer') and self._reconfig_timer:
            # Cancelar timer anterior para reiniciar el debounce
            GLib.source_remove(self._reconfig_timer)
        else:
            # Primer evento de la ráfaga: logueamos una sola vez
            log_event("Evento de hardware detectado vía plataforma",
                origin="ENGINE", level="DEBUG", reason="HARDWARE")

        # Programar sincronización tras 1500ms (reinicia el timer)
        self._reconfig_timer = GLib.timeout_add(1500, self._final_hardware_sync)

    def _final_hardware_sync(self):
        """
        Ejecuta la sincronización final tras un cambio de hardware.
        Se llama tras el retardo programado en on_hardware_change.
        """
        # Limpiar el ID del temporizador para permitir futuros eventos
        self._reconfig_timer = None

        log_event("Ejecutando sincronización final de geometría",
            origin="ENGINE", level="INFO", reason="HARDWARE")
        self._do_cycle_and_notify(
            reason=ConfigHandler.REASON_HARDWARE,
            target_hashes=None,
            target_bookmark=None,
            temp_settings=None,
            event_dict={"action": "hardware_changed"}
        )
        return False

    def _update_geometry(self, monitors_map_real, reason):
        """
        Calcula y guarda la geometría del lienzo maestro.
        Retorna una tupla (geo_snapshot, canvas_w, canvas_h).
        """
        canvas_w, canvas_h = self.platform.get_total_canvas_geometry(monitors_map_real)
        geo_snapshot = {
            "timestamp": time.time(),
            "canvas": {"w": canvas_w, "h": canvas_h},
            "monitors": monitors_map_real}

        self.ch.save_json("geometry", geo_snapshot)

        # Confirmar el resultado antes de registrar la actualización.
        saved_check = self.ch.load_json("geometry")
        if saved_check.get("monitors") != geo_snapshot["monitors"]:
            log_event("¡ALERTA! Discrepancia justo después de guardar geometry.json",
                origin="ENGINE", level="ERROR", reason="HARDWARE")
        else:
            log_event(f"Geometría actualizada por {reason}: {canvas_w}x{canvas_h}",
                origin="ENGINE", level="INFO", reason="HARDWARE")

        return geo_snapshot, canvas_w, canvas_h

    def startup_sync(self):
        """
        Sincronización inicial de geometría y vault.
        Garantiza que geometry.json existe y refleja la realidad actual.
        Devuelve True si el vault o la geometría han cambiado.
        """
        # 1. Obtener la realidad actual del hardware
        monitors_map_real = monitor_detection.detect_monitors()

        # 2. Guardar la geometría actual (crea el archivo si no existe)
        self._update_geometry(monitors_map_real, ConfigHandler.REASON_SERVICE)

        # Registrar si el archivo de geometría no existía (primer arranque o archivo borrado)
        if not self.ch.load_json("geometry"):
            log_event("Geometría inicial creada (no existía)",
                origin="ENGINE", level="INFO", reason="HARDWARE")

        # La orientación inicial se decide una sola vez, con la geometría
        # persistida. Los cambios posteriores de hardware no deben
        # sobrescribir una preferencia que ya pertenece al usuario.
        settings_data = self.ch.load_json("settings")
        if "match_orientation" not in settings_data["global"]:
            monitors = self.ch.load_json("geometry").get("monitors", {})
            orientations = {monitor.get("orientation")
                for monitor in monitors.values()}

            if orientations and orientations <= {"horizontal", "vertical"}:
                match_orientation = len(orientations) == 2
                settings_data["global"]["match_orientation"] = match_orientation
                self.ch.save_json("settings", settings_data)

                log_event(f"Orientación inicial: match_orientation={match_orientation}",
                    origin="ENGINE", level="INFO", reason="SETTINGS")

        # 3. Sincronizar el vault con los monitores detectados
        active_hashes = list(monitors_map_real.keys())
        vault_changed, _ = self.ch.sync_vault(active_hashes)

        if vault_changed:
            log_event("Vault sincronizado con la geometría actual",
                origin="ENGINE", level="INFO")
            return True

        # 4. Verificar si la geometría guardada difiere de la real
        saved_monitors = self.ch.load_json("geometry").get("monitors", {})
        if set(active_hashes) != set(saved_monitors.keys()):
            log_event("Cambio de geometría detectado",
                origin="ENGINE", level="INFO", reason="HARDWARE")
            return True

        return False

    def run(self):
        """
        Punto de entrada principal del motor.
        Sincroniza la biblioteca, verifica la geometría y lanza el bucle GLib.
        """
        log_event("ENGINE iniciado", origin="ENGINE", level="INFO", reason="NOTIFY")

        # ----------------------------------------------------------
        # 1. LIMPIEZA Y SINCRONIZACIÓN INICIAL
        # ----------------------------------------------------------
        # Limpieza de miniaturas de efectos de fondo
        self.ch._cleanup_blur_thumbnails()

        # Configuración de plataforma
        self.platform._ensure_platform_config()

        # ----------------------------------------------------------
        # Verificación de integridad de la instalación
        # ----------------------------------------------------------
        # Asegurar que las acciones del shell están instaladas
        if hasattr(self.platform, "ensure_shell_actions"):
            self.platform.ensure_shell_actions(self.ch.app_root, self.platform.data_base)

        # Asegurar que el atajo de teclado está registrado
        if hasattr(self.platform, "ensure_keybindings"):
            self.platform.ensure_keybindings(self.platform.app_dir)

        # Sincronizar liberia
        try:
            result = self.ch.sync_library()
            if result and len(result) >= 3:
                h, v = result[0], result[1]
                log_event(f"Biblioteca sincronizada: {h}H / {v}V",
                    origin="ENGINE", level="INFO", reason="LIBRARY")
            else:
                log_event("Biblioteca: No se pudo obtener el total",
                    origin="ENGINE", level="WARN", reason="LIBRARY")
        except Exception as e:
            log_event(f"Error en escaneo inicial: {e}",
                origin="ENGINE", level="ERROR", reason="LIBRARY")
        # ----------------------------------------------------------
        # 2. DECISIÓN SOBRE LA PERSISTENCIA DEL FONDO
        # ----------------------------------------------------------
        settings = self.ch.load_json("settings").get("global", {})
        persist = settings.get("persist_on_reboot", True)

        # Sincronizar geometría y vault (startup_sync ahora hace todo el trabajo)
        needs_cycle = self.startup_sync()
        if not persist:

            # El usuario quiere cambiar el fondo al iniciar
            log_event("Persistencia desactivada. Generando nuevo fondo.",
                origin="ENGINE", level="INFO", reason="SETTINGS")
            self.execute_full_cycle(reason=ConfigHandler.REASON_SERVICE)

        elif needs_cycle:
            # El hardware ha cambiado: regenerar
            log_event("Cambio de hardware detectado. Regenerando fondo...",
                origin="ENGINE", level="INFO", reason="HARDWARE")
            self.execute_full_cycle(reason=ConfigHandler.REASON_HARDWARE)
        else:
            # Persistencia activa y ninguna condición requiere regeneración.
            log_event("Fondo actual conservado: no se requiere regeneración",
                origin="ENGINE", level="INFO", reason="SETTINGS")

        # Garantizar el temporizador aunque la persistencia evite
        # ejecutar un ciclo inicial. No reiniciar uno ya existente.
        # thanks Nilloow
        if self.timer_id is None:
            self.manage_timer(action="start")

        # ----------------------------------------------------------
        # 3. BUCLE PRINCIPAL
        # ----------------------------------------------------------
        # Si durante este arranque se han creado o actualizado traducciones y
        # la plataforma necesita recargar su shell, programar una única recarga
        # cuando el bucle principal del engine ya esté operativo.
        if self._translations_changed and hasattr(
            self.platform, "refresh_shell_after_translation_update"):
            GLib.idle_add(self._refresh_shell_after_translation_update)

        try:
            self.loop.run()
        except (KeyboardInterrupt, SystemExit):
            log_event("Cerrando motor...",
                origin="ENGINE", level="INFO", reason="NOTIFY")
            self.manage_timer(action="stop")
            self.loop.quit()

    def _ensure_translations(self):
        """
        Asegura que las traducciones estén compiladas y conserva si algún
        catálogo .mo fue creado o actualizado durante este arranque.
        """
        if not hasattr(self.platform, 'compile_translations'):
            return False

        translations_changed = self.platform.compile_translations(
            self.ch.app_root, self.platform.locale_dir, self.platform.app_domain)

        self._translations_changed = self._translations_changed or bool(translations_changed)
        return bool(translations_changed)

    # ----------------------------------------------------------
    # RECARGA DEL SHELL TRAS ACTUALIZAR TRADUCCIONES
    # ----------------------------------------------------------
    def _refresh_shell_after_translation_update(self):
        """Solicita una única recarga del shell cuando la plataforma lo requiere."""
        self._translations_changed = False

        if hasattr(self.platform, "refresh_shell_after_translation_update"):
            self.platform.refresh_shell_after_translation_update()

        return False

    def _complete_ini_if_needed(self):
        """
        Persiste las rutas derivadas que PlatformManager ya puede resolver
        en memoria, conservando en el engine el lifecycle de finalización.
        """
        config = self.platform._ensure_platform_config()
        resolved = self.platform._resolve_common_paths(config)

        derived_keys = ['wmm_id', 'cache_dir', 'locale_dir',
            'app_dir','app_config', 'data_dir']

        # frontend_dir pertenece al frontend, no al espacio común.
        if config.get('desktop') == 'xfce':
            if not resolved.get('frontend_dir') and resolved.get('app_dir'):
                resolved['frontend_dir'] = os.path.join(
                    resolved['app_dir'], 'frontends', 'xfce')
            derived_keys.append('frontend_dir')

        updated = False

        for key in derived_keys:
            if not config.get(key) and resolved.get(key):
                config[key] = resolved[key]
                updated = True

        if updated:
            self.platform.save_ini(config)
            log_event("Archivo settings_core.ini completado con claves derivadas",
                origin="ENGINE", level="INFO", reason="SETTINGS")

            # La instancia ya disponía de las rutas resueltas en memoria;
            # sincronizamos también cualquier clave recién persistida.
            for key in derived_keys:
                if config.get(key):
                    setattr(self.platform, key, config[key])

            self._post_install_needed = True

    def _post_install_setup(self):
        """
        Ejecuta tareas de configuración inicial tras completar el .ini por primera vez.
        Se encarga de instalar las acciones de shell (Nemo, Nautilus, etc.)
        y crear el atajo de teclado.
        """
        log_event("Primer arranque detectado. Ejecutando configuración post-instalación...",
            origin="ENGINE", level="INFO", reason="SETTINGS")

        # 1. Instalar scripts de shell (Nemo, Nautilus, etc.)
        if hasattr(self.platform, 'ensure_shell_actions'):
            self.platform.ensure_shell_actions(self.ch.app_root, self.platform.data_base)
            log_event("Scripts de shell instalados correctamente",
                origin="ENGINE", level="INFO", reason="SETTINGS")

        # 2. Crear atajo de teclado
        if hasattr(self.platform, 'ensure_keybindings'):
            self.platform.ensure_keybindings(self.platform.app_dir)
            log_event("Configuración del atajo solicitada",
                origin="ENGINE", level="INFO", reason="SETTINGS")

        log_event("Configuración post-instalación completada",
            origin="ENGINE", level="INFO", reason="SETTINGS")

if __name__ == "__main__":
    daemon = WMMDaemon()
    daemon.run()
