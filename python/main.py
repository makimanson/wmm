import os
import time
import subprocess
import gi
import signal
import atexit
import random
import json
# import locale
import gettext

gi.require_version('Gdk', '3.0')
from gi.repository import Gdk, GLib
from monitor_manager import MonitorManager
from config_handler import ConfigHandler
from image_engine import ImageEngine
from PIL import Image

# ==========================================================
# Traducciones
# ==========================================================

# Captura de traducibles
_ = gettext.gettext
# Usa el idioma configurado en el sistema
# locale.setlocale(locale.LC_ALL, '')
# Ruta estándar de traducciones para extensiones de Cinnamon
locale_dir = os.path.expanduser('~/.local/share/locale')
# Usar el dominio 'wmm-applet@maki'
gettext.bindtextdomain('wmm-applet@maki', locale_dir)
# También vincular el dominio 'cinnamon' para heredar traducciones del sistema
# gettext.bindtextdomain('cinnamon', None)
# Establecer el dominio principal
# gettext.textdomain('wmm-applet@maki')

# Función de traducción personalizada: busca primero en el sistema, luego en nuestro dominio
def _(text):
    translated = gettext.dgettext('cinnamon', text)
    if translated != text:
        return translated
    return gettext.dgettext('wmm-applet@maki', text)

class WMMDaemon:
    def __init__(self):
        self.mm = MonitorManager()
        self.ch = ConfigHandler()
        self.ie = ImageEngine(self.ch, self.mm)
        self.loop = GLib.MainLoop()
        self.timer_id = None
        self.rotation_queue = []
        self.last_rotated_hash = None
        self.display = Gdk.Display.get_default()

        # 1. Gestión del archivo PID
        self._manage_pid_file()

        # 2. Registro de limpieza al salir (DENTRO del __init__)
        atexit.register(self._cleanup_on_exit)

        # 3. Registro de señales del sistema
        signal.signal(signal.SIGUSR1, self._handle_sigusr1)

        if self.display:
            self.display.connect("monitor-added", self.on_hardware_change)
            self.display.connect("monitor-removed", self.on_hardware_change)

    def _do_cycle_and_notify(self, reason, target_hashes, target_bookmark, temp_settings, event_dict):
        """
        Ejecuta el ciclo de rotación y, al terminar, notifica al panel.
        """
        self.execute_full_cycle(
            reason=reason,
            target_hashes=target_hashes,
            target_bookmark=target_bookmark,
            temp_settings=temp_settings
        )
        self._notify_panel(event_dict)
        return False  # Para GLib.idle_add

    def _notify_panel(self, event_dict):
        """
        Envía un evento al panel de control, si está abierto.

        Args:
            event_dict (dict): Diccionario con la acción y parámetros.
                               Ej: {"action": "wallpaper_changed"}
        """
        pid_path = os.path.join(self.ch.cache_dir, "pid_panel.pid")

        # 1. Verificar si el panel está vivo
        if not os.path.exists(pid_path):
            return  # Panel no está abierto, nada que hacer

        try:
            with open(pid_path, "r") as f:
                content = f.read().strip()
                if not content:
                    return
                panel_pid = int(content)

            # 2. Comprobar que el proceso sigue corriendo
            os.kill(panel_pid, 0)
        except (OSError, ValueError, FileNotFoundError):
            # El proceso no existe o el archivo es inválido
            try:
                os.remove(pid_path)
            except:
                pass
            return

        # 3. Escribir el evento en el buzón del panel
        command_path = os.path.join(self.ch.data_dir, "command_panel.json")
        try:
            with open(command_path, "w", encoding="utf-8") as f:
                json.dump(event_dict, f)
            print(f" [MOTOR] Evento '{event_dict.get('action')}' enviado al panel (PID {panel_pid}).")
        except Exception as e:
            print(f" [MOTOR] Error al escribir command_panel.json: {e}")
            self.ch.log_error(f"Error al escribir command_panel.json: {e}", reason="MOTOR")
            return

        # 4. Enviar la señal al panel
        try:
            os.kill(panel_pid, signal.SIGUSR1)
        except Exception as e:
            print(f" [MOTOR] Error al enviar SIGUSR1 al panel: {e}")
            self.ch.log_error(f"Error al enviar SIGUSR1 al panel: {e}", reason="MOTOR")

    def _cleanup_on_exit(self):
        """Borra el rastro del motor al cerrarse."""
        pid_path = os.path.join(self.ch.cache_dir, "pid_main.pid")
        if os.path.exists(pid_path):
            try:
                os.remove(pid_path)
                print(" [SISTEMA] Archivo PID eliminado. Cierre limpio.")
            except: pass

    def _manage_pid_file(self):
        """Crea el archivo PID y asegura su limpieza al cerrar."""
        pid_path = os.path.join(self.ch.cache_dir, "pid_main.pid")
        os.makedirs(os.path.dirname(pid_path), exist_ok=True)

        # Si el archivo existe, comprobamos si el proceso sigue vivo
        if os.path.exists(pid_path):
            try:
                with open(pid_path, "r") as f:
                    content = f.read().strip()
                    if content:
                        old_pid = int(content)
                        os.kill(old_pid, 0)
                        print(f" [!] El motor ya está corriendo (PID {old_pid}). Abortando.")
                        exit(1)
            except (OSError, ValueError):
                # Si el PID no existe o el archivo no tiene un número válido, seguimos
                pass

        # Escribimos el PID actual
        with open(pid_path, "w") as f:
            f.write(str(os.getpid()))

        # Registro de limpieza automática
        atexit.register(lambda: os.remove(pid_path) if os.path.exists(pid_path) else None)
        print(f" [SISTEMA] PID {os.getpid()} registrado en {pid_path}")

    def _handle_sigusr1(self, signum, frame):
        """
        Manejador de la señal USR1 enviada por el Applet.
        Sincroniza el estado del motor leyendo comandos.json.
        ---
        MODIFICACIÓN MÍNIMA:
        1. Se añade un pequeño sleep para evitar lectura de archivo vacío.
        2. Se añade soporte para 'timer_force_off' solicitado por favoritos.
        """
        # Espera de seguridad para asegurar que el disco terminó de escribir
        time.sleep(0.05)

        action_data = self.ch.load_json("commands")

        if action_data and "action" in action_data:
            order = action_data["action"]

            # Limpieza del buzón para evitar ejecuciones duplicadas
            self.ch.save_json("commands", {})

            # --- 1. ACTUALIZACIÓN DE SETTINGS ---
            if order == ConfigHandler.CMD_UPDATE_TIMER:
                settings = self.ch.load_json("settings")
                g = settings["global"]

                # Sincronización de variables desde el Applet
                g["slideshow_enabled"] = action_data.get("enabled", g["slideshow_enabled"])
                g["slideshow_interval"] = int(action_data.get("interval", g["slideshow_interval"]))
                g["slideshow_mode"] = action_data.get("mode", g["slideshow_mode"])
                g["slideshow_bookmark"] = action_data.get("slideshow_bookmark", g["slideshow_bookmark"])
                g["spanned_enabled"] = action_data.get("spanned_enabled", g.get("spanned_enabled", False))

                self.ch.save_json("settings", settings)
                GLib.idle_add(self._notify_panel, {"action": "settings_updated"})
                # Gestión del Temporizador
                GLib.idle_add(self.manage_timer, "start")

                # REPORTES DE TERMINAL RECUPERADOS (Tal cual los tenías)
                print("\n" + "="*40)
                print(" [NOTIFICACIÓN] Ajustes de Temporizador")
                print("-" * 40)
                print(f"  Estado:      {'ACTIVADO' if g['slideshow_enabled'] else 'DESACTIVADO'}")
                print(f"  Intervalo:  {g['slideshow_interval']} minutos")
                print(f"  Modo:        {g['slideshow_mode'].upper()}")
                print(f"  Imagenes:  {'SOLO FAVORITOS' if g['slideshow_bookmark'] else 'BIBLIOTECA GENERAL'}")
                print("-" * 40)
                print(f"  Modo Distribuido:  {'ACTIVADO' if g['spanned_enabled'] else 'DESACTIVADO'}")
                print("="*40 + "\n")

            # --- 2. CARGA DE FAVORITO ESPECÍFICO ---
            elif order == ConfigHandler.CMD_LOAD_BOOKMARK:
                name = action_data.get("name")

                # Soporte para apagar el timer si el favorito es una carga manual
                if action_data.get("timer_force_off"):
                    settings = self.ch.load_json("settings")
                    settings["global"]["slideshow_enabled"] = False
                    self.ch.save_json("settings", settings)
                    GLib.idle_add(self.manage_timer, "stop")
                    print(f" [INFO] Favorito detectado: Deteniendo Temporizador.")

                print(f" [ACCIÓN] Cargando favorito: {name}")
                # Llamada original al ciclo: (Reason, target_hashes, target_bookmark)
                GLib.idle_add(
                    self._do_cycle_and_notify,
                    f"Carga de favorito: {name}",
                    None,
                    name,
                    None,
                    {"action": "wallpaper_changed"}
                )

            # --- 2.1 ELIMINACION DE FAVORITO ESPECÍFICO ---

            elif order == ConfigHandler.CMD_DELETE_BOOKMARK:
                name = action_data.get("name")
                if name:
                    print(f" [ACCIÓN] Eliminando favorito: {name}")
                    if self.ch.delete_bookmark(name):
                        print(f" [OK] Favorito '{name}' eliminado.")
                        self._notify_panel({"action": "bookmarks_updated"})
                        # Notificación de confirmación usando el sistema interno
                        self.ch._send_notification(
                            reason=_("Favorite deleted"),
                            detail_msg = _("Preset") + " '" + name + "'\n" + _("deleted successfully."),
                            level="info"
                        )
                    else:
                        print(f" [ERROR] No se pudo eliminar '{name}'.")

            # --- 3. ACCIONES MANUALES ---
            elif order == ConfigHandler.CMD_FORCE_ROTATION:
                print(" [ACCIÓN] Rotación manual solicitada (Click en Applet)")
                GLib.idle_add(
                    self._do_cycle_and_notify,
                    ConfigHandler.REASON_MANUAL,
                    None,
                    None,
                    None,
                    {"action": "wallpaper_changed"}
                )

            # --- 4. MANTENIMIENTO ---
            elif order == ConfigHandler.CMD_SYNC_LIBRARY:
                print(" [ACCIÓN] Sincronizando biblioteca de imágenes...")
                result = self.ch.sync_library()  # Devuelve (total_h, total_v, has_changes, detail_msg)
                if result and len(result) == 4:
                    total_h, total_v, has_changes, detail_msg = result
                    if has_changes:
                        reason = _("Changes detected")
                    else:
                        reason = _("No changes")
                    body = f"{reason}\n{_("Total library") + ": {}H | {}V".format(total_h, total_v)}"
                    # Si hay detalle adicional (altas/bajas), lo añadimos
                    if detail_msg:
                        body = f"{detail_msg}\n{body}"
                    self.ch._send_notification(
                        reason="WMM: " + _("Synchronization"),
                        detail_msg=body,
                        level="info"
                    )

            # --- 5. ABRIR PANEL DE CONTROL ---
            elif order == ConfigHandler.CMD_OPEN_PANEL:
                debug_mode = action_data.get("debug", False)
                print(f" [ACCIÓN] Abriendo panel de control (debug={debug_mode})...")
                panel_path = os.path.join(os.path.dirname(__file__), "panel.py")
                try:
                    if debug_mode:
                        # Abrir con terminal y variable de entorno WMM_DEBUG=1
                        subprocess.Popen(
                            ["gnome-terminal", "--", "bash", "-c",
                             f"WMM_DEBUG=1 python3 {panel_path}; echo 'Cerrando en 2 segundos...'; sleep 2"],
                            start_new_session=True
                        )
                    else:
                        subprocess.Popen(
                            ["python3", panel_path],
                            start_new_session=True
                        )
                    print(f" [OK] Panel lanzado: {panel_path}")
                except Exception as e:
                    print(f" [ERROR] No se pudo abrir el panel: {e}")
                    self.ch.log_error(f"No se pudo abrir el panel: {e}", reason="PANEL")

            # --- 6. APLICAR SELECCIÓN MANUAL ---
            elif order == ConfigHandler.CMD_APPLY_SELECTION:
                print(" [ACCIÓN] Aplicando selección manual desde el panel.")
                temp_settings = action_data.get("temp_settings", None)
                GLib.idle_add(
                    self._do_cycle_and_notify,
                    ConfigHandler.REASON_SELECTION,
                    None,
                    None,
                    temp_settings,
                    {"action": "wallpaper_changed"}
                )

            # --- 7. Añadir PRESET desde add_bookmark.py ---
            elif order == ConfigHandler.CMD_BOOKMARK_ADDED:
                print(" [ACCIÓN] Se ha añadido un nuevo PRESET.")
                item_name = action_data.get("name", _("Unknown"))
                self.ch._send_notification(
                    reason=_("Favorite added"),
                    detail_msg=item_name + "'\n" + _("added successfully."),
                    level="info"
                )

                self._notify_panel({"action": "bookmarks_updated"})
        else:
            # Mantenemos tu aviso de depuración original
            print(" [AVISO] Señal recibida pero el archivo de comandos está vacío.")

    def _timer_callback(self):
        self._do_cycle_and_notify(
            reason=ConfigHandler.REASON_TIMER,
            target_hashes=None,
            target_bookmark=None,
            temp_settings=None,
            event_dict={"action": "wallpaper_changed"}
        )
        return True

    def manage_timer(self, action="start"):
        if self.timer_id:
            GLib.source_remove(self.timer_id)
            self.timer_id = None

        if action == "stop":
            return

        # Acceder a la ruta real: global -> slideshow_...
        settings = self.ch.load_json("settings").get("global", {})
        enabled = settings.get("slideshow_enabled", True)
        interval_min = int(settings.get("slideshow_interval", 15))

        if enabled and interval_min > 0:
            self.timer_id = GLib.timeout_add_seconds(interval_min * 60, self._timer_callback)
            print(f" -> Temporizador activo: {interval_min} min.")
        else:
            print(" -> Temporizador detenido por el usuario.")

    def execute_full_cycle(self, reason=ConfigHandler.REASON_TIMER, target_hashes=None, target_bookmark=None, temp_settings=None):
        """
        Orquestador principal del cambio de fondo.
        Respeta el flujo de estabilización, gestión de hardware, lógica async
        e integra el soporte para favoritos y bookmarks específicos.
        """
        friendly_reason = ConfigHandler.EXECUTION_REASONS.get(reason, reason)
        print(f"[{time.strftime('%H:%M:%S')}] INICIANDO: {friendly_reason}")

        # 1. Estabilización de eventos GDK (Crítico para evitar desajustes)
        context = GLib.MainContext.default()
        while context.pending():
            context.iteration(False)

        # 2. Obtener la realidad actual del hardware
        monitors_map_real = self.mm.get_active_monitors_map()
        active_hashes = list(monitors_map_real.keys())

        # --- MODO SELECCIÓN MANUAL (aplicar lo que hay en el vault sin rotar) ---
        if reason == ConfigHandler.REASON_SELECTION:
            # Cargar la sesión activa del vault
            vault = self.ch.load_json("vault")
            active_session = vault.get("active_session", {})
            selection = {}

            # Leer los ajustes de color una sola vez
            settings = self.ch.load_json("settings").get("global", {})
            solid_color = settings.get("solid_color", "#000000")
            color_mode = settings.get("color_mode", "solid_color")
            gradient_h = settings.get("gradient_h", ["#000000", "#8D9797"])
            gradient_v = settings.get("gradient_v", ["#000000", "#8D9797"])
            wallpaper_effect_scope = settings.get("wallpaper_effect_scope", "blur")
            # Leer el efecto de imagen, dando prioridad a los ajustes temporales enviados desde el panel
            wallpaper_effect = temp_settings.get("wallpaper_effect", settings.get("wallpaper_effect", "none")) if temp_settings else settings.get("wallpaper_effect", "none")
            spanned_enabled = temp_settings.get("spanned_enabled", settings.get("spanned_enabled", False)) if temp_settings else settings.get("spanned_enabled", False)
            wp_mode = temp_settings.get("wallpaper_mode", settings.get("wallpaper_mode", "fit")) if temp_settings else settings.get("wallpaper_mode", "fit")

            for m_hash in active_hashes:
                entry = active_session.get(m_hash, {})
                if isinstance(entry, dict):
                    path = entry.get("path")
                    is_active = entry.get("active", True)
                else:
                    path = entry if entry else None
                    is_active = True

                if is_active:
                    if path and os.path.exists(path):
                        # Usar la ruta existente y registrarla en el historial
                        selection[m_hash] = path
                        self.ch._update_history(path)
                    else:
                        # Monitor activo pero sin imagen: asignar una aleatoria
                        m = monitors_map_real.get(m_hash, {})
                        if m:
                            orient = m.get('orientation', 'horizontal')[0].lower()
                            new_path = self.ch.get_smart_selection(m.get('width', 1920), m.get('height', 1080), orientation=orient)
                            if new_path:
                                selection[m_hash] = new_path
                                self.ch.update_monitor_image(m_hash, new_path)
                                self.ch._update_history(new_path)
                            else:
                                # Fallback: si no hay imágenes en la biblioteca, usar color sólido
                                selection[m_hash] = ("color", color_mode, solid_color, gradient_h, gradient_v)
                        else:
                            # Sin datos del monitor, color sólido
                            selection[m_hash] = ("color", color_mode, solid_color, gradient_h, gradient_v)
                else:
                    # Monitor inactivo: pintar color de fondo
                    selection[m_hash] = ("color", color_mode, solid_color, gradient_h, gradient_v)

            if selection:
                # Renderizar y aplicar directamente
                master_path = self.ie.render_master_wallpaper(
                    selection,
                    full_canvas=spanned_enabled,
                    solid_color=solid_color,
                    color_mode=color_mode,
                    gradient_h=gradient_h,
                    gradient_v=gradient_v,
                    wallpaper_effect_scope=wallpaper_effect_scope,
                    wallpaper_mode=wp_mode,
                    image_effect=wallpaper_effect
                )
                self.apply_to_cinnamon(master_path)
                if self.timer_id is None:
                    self.manage_timer(action="start")
            else:
                print(" [AVISO] Selección manual: no hay imágenes que aplicar.")
            return  # Salimos sin ejecutar el resto del ciclo

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
        _, vault = self.ch.sync_vault(active_hashes)
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
        # Nuevo: leer el efecto de imagen global
        wallpaper_effect = settings.get("wallpaper_effect", "none")

        # TRAZA TEMPORAL para diagnóstico
        # print(f"[DIAG] spanned_enabled={spanned_enabled} | wallpaper_effect_scope={wallpaper_effect_scope} | wallpaper_mode={wp_mode} | color_mode={color_mode}")
        selection = {}
        target_hashes = active_hashes if target_hashes is None else target_hashes

        # El centinela: Controla si el motor encuentra material NUEVO o VÁLIDO en este ciclo
        valid_assets_found = False

        # --- LÓGICA ASYNC (Rotación por turnos) ---
        # NUEVO: spanned ya no es un modo, es una opción independiente. La condición de async
        # solo se aplica si NO está activado spanned.
        if sl_mode == "async" and reason in ConfigHandler.ASYNC_ROTATION_REASONS and not spanned_enabled and not target_bookmark:
            # Calcular qué monitores realmente tienen imagen (active:true)
            active_image_hashes = []
            for h in active_hashes:
                entry = active_session.get(h, {})
                if isinstance(entry, dict):
                    if entry.get("active", True):
                        active_image_hashes.append(h)
                else:
                    active_image_hashes.append(h)  # formato antiguo, asumimos activo

            # Filtrar la cola actual para quitar monitores que ya no tienen imagen
            self.rotation_queue = [h for h in self.rotation_queue if h in active_image_hashes]

            # Si la cola quedó vacía o es inválida, reconstruirla
            invalid_queue = not set(self.rotation_queue).issubset(set(active_image_hashes))
            if not self.rotation_queue or invalid_queue:
                if not active_image_hashes:
                    target_hashes = []
                    self.rotation_queue = []
                else:
                    new_queue = list(active_image_hashes)
                    if len(new_queue) > 1:
                        while True:
                            random.shuffle(new_queue)
                            if new_queue[0] != self.last_rotated_hash: break
                    else:
                        random.shuffle(new_queue)
                    self.rotation_queue = new_queue

                    target_hashes = [self.rotation_queue.pop(0)]
                    self.last_rotated_hash = target_hashes[0]
                    print(f" -> Modo Async: Turno del monitor {target_hashes[0]}.")
            else:
                # La cola es válida y no está vacía: rotar normalmente
                target_hashes = [self.rotation_queue.pop(0)]
                self.last_rotated_hash = target_hashes[0]
                print(f" -> Modo Async: Turno del monitor {target_hashes[0]}.")

        # --- CONSTRUCCIÓN DE LA SELECCIÓN ---
        if reason in ConfigHandler.RECONFIGURATION_REASONS:
            # --- RECONFIGURACIÓN SIN ROTACIÓN (cambio de hardware o inicio) ---
            for m_hash in active_hashes:
                if m_hash not in monitors_map:
                    continue
                entry = active_session.get(m_hash, {})
                if isinstance(entry, dict):
                    path = entry.get("path")
                    is_active = entry.get("active", True)
                else:
                    path = entry if entry else None
                    is_active = True

                if not is_active:
                    selection[m_hash] = ("color", color_mode, solid_color, gradient_h, gradient_v)
                    continue

                if path and os.path.exists(path):
                    selection[m_hash] = path
                    self.ch._update_history(path)
                else:
                    m = monitors_map[m_hash]
                    orient = m.get('orientation', 'horizontal')[0].lower()
                    new_path = self.ch.get_smart_selection(m.get('width', 1920), m.get('height', 1080), orientation=orient)
                    if new_path:
                        selection[m_hash] = new_path
                        self.ch.update_monitor_image(m_hash, new_path)
                        self.ch._update_history(new_path)
                    else:
                        selection[m_hash] = ("color", color_mode, solid_color, gradient_h, gradient_v)
            valid_assets_found = bool(selection)
        else:
        # --- ROTACIÓN NORMAL ---
            target_preset = None
            preset_assigned_paths = []
            # Variables que pueden ser sobrescritas por el preset
            preset_wp_mode = None
            preset_spanned = None
            preset_effect_scope = None
            # Nuevo: variable para el efecto de imagen del preset
            preset_effect = None

            # 1. Determinamos qué preset usar (Manual o Automático)
            if target_bookmark or (sl_mode == "sync" and fav_mode):
                bookmarks = self.ch.load_json("bookmarks")

                if target_bookmark:
                    target_preset = target_bookmark
                    print(f" [BOOKMARK] Aplicando composición manual: '{target_preset}'")
                else:
                    if bookmarks:
                        # Cargar historial de presets
                        presets_history = self.ch.load_json("history_presets").get("log", [])
                        # Filtrar los que no han salido recientemente
                        available = [k for k in bookmarks if k not in presets_history]
                        if not available:
                            # Todos han salido → vaciamos el log para empezar ciclo nuevo
                            self.ch.save_json("history_presets", {
                                "last_update": time.time(),
                                "log": [],
                                "parent_total": len(bookmarks)
                            })
                            available = list(bookmarks.keys())

                        target_preset = random.choice(available)
                        print(f" [SYNC] Preset global elegido: {target_preset}")

                # 2. Validación y Pre-carga de rutas para la regla de exclusión
                if target_preset:
                    bm_data = bookmarks.get(target_preset, {})
                    if not bm_data:
                        print(f" [!] Error: El favorito '{target_preset}' no existe en el JSON.")
                    else:
                        # --- Extraer preferencias del preset (NUEVO) ---
                        # Las claves reservadas __mode__, __spanned__ y __effect_scope__
                        # definen la configuración visual del preset sin alterar los ajustes globales.
                        if "__mode__" in bm_data:
                            preset_wp_mode = bm_data.pop("__mode__")
                        if "__spanned__" in bm_data:
                            preset_spanned = bm_data.pop("__spanned__")
                        if "__effect_scope__" in bm_data:
                            preset_effect_scope = bm_data.pop("__effect_scope__")
                        # Extraer el efecto de imagen del preset
                        if "__effect__" in bm_data:
                            preset_effect = bm_data.pop("__effect__")

                        # Migrar formato antiguo (string) a dict si es necesario
                        for m_hash, val in list(bm_data.items()):
                            if m_hash.startswith("__"):
                                continue  # Saltar cualquier otra clave reservada
                            if isinstance(val, str):
                                bm_data[m_hash] = {"path": val if val else "", "active": True}
                        self.ch._update_history(target_preset, mode="presets")
                        # Guardamos las rutas que YA están en el preset para que el relleno no las use
                        preset_assigned_paths = [v.get("path", "") for v in bm_data.values() if isinstance(v, dict) and v.get("path")]
                        # Asegurar que bm_data esté disponible más abajo
                        target_preset_data = bm_data

            # --- APLICAR PREFERENCIAS DEL PRESET (NUEVO) ---
            # Si el preset definía valores, sobrescriben temporalmente los globales
            if preset_wp_mode:
                wp_mode = preset_wp_mode
            if preset_spanned is not None:
                spanned_enabled = preset_spanned
            if preset_effect_scope:
                wallpaper_effect_scope = preset_effect_scope
            # Nuevo: aplicar el efecto de imagen del preset
            if preset_effect is not None:
                wallpaper_effect = preset_effect

            # NUEVO: spanned ya no es un modo de aspecto, es una opción independiente
            if spanned_enabled:
                # Caso A: Distribución sobre el lienzo completo (Spanned)
                # La imagen maestra se asigna únicamente al monitor principal
                canvas_w, canvas_h = self.mm.get_total_canvas_geometry(monitors_map)

                # Buscar el monitor principal (o el primero si no hay)
                primary_hash = None
                for m_hash in active_hashes:
                    if monitors_map.get(m_hash, {}).get("primary", False):
                        primary_hash = m_hash
                        break
                if primary_hash is None:
                    primary_hash = active_hashes[0]  # Fallback: primer monitor

                entry = active_session.get(primary_hash)
                if isinstance(entry, dict):
                    current_path = entry.get("path")
                else:
                    current_path = entry

                if reason == ConfigHandler.REASON_HARDWARE and current_path and os.path.exists(current_path):
                    path = current_path
                else:
                    # Prioridad: 1. Bookmark seleccionado | 2. Rotación de Favoritos | 3. Smart Selection
                    if target_bookmark:
                        # En spanned, cogemos la primera ruta disponible del preset
                        path = preset_assigned_paths[0] if preset_assigned_paths else self._get_smart_favorite(primary_hash, "sync", "h", target_bookmark)
                    elif fav_mode:
                        path = self.ch.get_vault_selection(orientation="h")
                    else:
                        path = self.ch.get_smart_selection(canvas_w, canvas_h, orientation="h")

                if not path:
                     print(" [!] Spanned: Imposible encontrar imagen.")
                else:
                    selection = {primary_hash: path}
                    valid_assets_found = True
                    self.ch.update_monitor_image(primary_hash, path)
            else:
                # Caso B: Cada monitor con su imagen ajustada (modo real: fit/zoom/stretched)
                current_f_mode = sl_mode.lower()

                for m_hash in active_hashes:
                    if m_hash not in monitors_map: continue
                    # Leer el estado activo del monitor desde el vault
                    vault_entry = active_session.get(m_hash, {})
                    if isinstance(vault_entry, dict):
                        is_active = vault_entry.get("active", True)
                    else:
                        is_active = True

                    if not is_active:
                        # Monitor inactivo: pintar color de fondo
                        selection[m_hash] = ("color", color_mode, solid_color, gradient_h, gradient_v)
                        continue
                    m = monitors_map[m_hash]
                    m_orient = m['orientation'][0].lower()
                    entry = active_session.get(m_hash)
                    if isinstance(entry, dict):
                        current_vault_path = entry.get("path")
                    else:
                        current_vault_path = entry

                    is_target = (m_hash in target_hashes) if reason in ConfigHandler.ASYNC_ROTATION_REASONS else True
                    # 2. Selección de ruta
                    img_path = None
                    # --- Caso 1: Favoritos (Manual o por Temporizador) ---
                    # Si hay un preset elegido (target_preset) y es el momento de cambiar (is_target)
                    if is_target and (target_preset or fav_mode):
                        # Si tenemos un preset específico cargado, aplicamos su composición
                        if target_preset and m_hash in target_preset_data:
                            entry = target_preset_data[m_hash]  # dict con "path" y "active"
                            # Monitor inactivo en el preset → pintar color de fondo
                            if not entry.get("active", True):
                                selection[m_hash] = ("color", color_mode, solid_color, gradient_h, gradient_v)
                                continue  # ya está asignado, pasar al siguiente monitor
                            # Monitor activo con imagen definida en el preset
                            elif entry.get("path"):
                                img_path = entry["path"]
                                if os.path.exists(img_path):
                                    selection[m_hash] = img_path
                                    self.ch.update_monitor_image(m_hash, img_path)
                                    valid_assets_found = True
                                    continue  # asignado, siguiente monitor
                                else:
                                    # La imagen del preset no existe en disco; se dejará caer
                                    # al fallback de _get_smart_favorite para rellenar
                                    pass
                        # Si no se ha asignado nada (monitor sin entrada en el preset,
                        # o preset no definido), usar el comportamiento normal de favoritos
                        img_path = self._get_smart_favorite(
                            m_hash,
                            current_f_mode,
                            m_orient,
                            forced_bookmark=target_preset,
                            exclude_paths=preset_assigned_paths
                        )

                    # --- Caso 2: Biblioteca Normal (Si no hay favoritos o no toca favoritos) ---
                    elif is_target:
                        img_path = self.ch.get_smart_selection(m['width'], m['height'], orientation=m_orient)

                    # Persistencia para evitar pantallas en negro
                    if img_path:
                        selection[m_hash] = img_path
                        self.ch.update_monitor_image(m_hash, img_path)
                        valid_assets_found = True
                    elif current_vault_path and os.path.exists(str(current_vault_path)):
                        selection[m_hash] = current_vault_path
                    else:
                        # Último recurso
                        img_path = self.ch.get_smart_selection(m['width'], m['height'], orientation=m_orient)
                        if img_path:
                            selection[m_hash] = img_path
                            self.ch.update_monitor_image(m_hash, img_path)
                            valid_assets_found = True

        # 5. Renderizado y Aplicación final
        # Si todos los monitores están inactivos, pintar el color de fondo global
        if not valid_assets_found and selection:
            # selection contiene tuplas ("color", ...) para todos los monitores
            master_path = self.ie.render_master_wallpaper(
                selection,
                full_canvas=spanned_enabled,
                solid_color=solid_color,
                color_mode=color_mode,
                gradient_h=gradient_h,
                gradient_v=gradient_v,
                wallpaper_effect_scope=wallpaper_effect_scope,
                wallpaper_mode=wp_mode,
                image_effect=wallpaper_effect
            )
            self.apply_to_cinnamon(master_path)

        elif valid_assets_found and selection:
            # NUEVO: full_canvas se decide por spanned_enabled (opción independiente)
            master_path = self.ie.render_master_wallpaper(
                selection,
                full_canvas=spanned_enabled,
                solid_color=solid_color,
                color_mode=color_mode,
                gradient_h=gradient_h,
                gradient_v=gradient_v,
                wallpaper_effect_scope=wallpaper_effect_scope,
                wallpaper_mode=wp_mode,
                image_effect=wallpaper_effect
            )
            self.apply_to_cinnamon(master_path)

            # Aseguramos que el temporizador esté corriendo si no lo está
            if self.timer_id is None:
                self.manage_timer(action="start")
        else:
            # LA RED DE SEGURIDAD FINAL
            # 1. Se preserva wallpaper_master.jpg intacto en .cache/
            # 2. Se registra la incidencia en el log.
            msg = _("Cycle aborted: not enough images available to complete selection.")
            print(f" [{time.strftime('%H:%M:%S')}] [AVISO] {msg}")
            self.ch._send_notification(
                reason=_("No images available"),
                action=_("Check status of Image Sources in Control Panel."),
                detail_msg=msg,
                level="error"
            )
            # Forzamos el inicio del timer para que reintente en el próximo intervalo
            if self.timer_id is None:
                self.manage_timer(action="start")

    def _get_smart_favorite(self, m_hash, mode, target_orient, forced_bookmark=None, fname=None, exclude_paths=None):
        """
        Versión Definitiva V5: Respeta el Relleno Dinámico y gestiona imágenes desaparecidas.
        """
        exclude_paths = exclude_paths or [] # <--- PRESERVADO: El escudo anti-duplicados
        actual_settings = self.ch.load_json("settings")
        real_mode = actual_settings.get("global", {}).get("slideshow_mode", "async").lower()
        t_orient = target_orient[0].lower()

        # --- MODO SYNC O PRESET ESPECÍFICO ---
        if real_mode == "sync" or forced_bookmark:
            bookmarks = self.ch.load_json("bookmarks")
            if not forced_bookmark and bookmarks:
                forced_bookmark = random.choice(list(bookmarks.keys()))

            preset_data = bookmarks.get(forced_bookmark, {}) if forced_bookmark else {}
            path = preset_data.get(m_hash)

            # CASO A: La imagen no existe en el preset o el archivo ha sido borrado físicamente
            if not path or not os.path.exists(path):
                if path and not os.path.exists(path):
                    fname = os.path.basename(path)
                    # Aquí es donde lanzamos el aviso al sistema
                    msg = _("Image: '{image}' from preset: '{preset}' not found.").format(image=fname, preset=forced_bookmark)
                    print(f" [!] {msg}") # Consola
                    self.ch._send_notification(
                        reason=_("PRESET image not found"),
                        action=_("Assigning a random one"),
                        detail_msg=msg,
                        level="warn"
                    )
                # RELLENO DINÁMICO: Buscamos una alternativa que no esté ya en otro monitor
                path = self.ch.get_vault_selection(orientation=t_orient, exclude=exclude_paths)

            return path

        # --- MODO ASYNC ---
        else:
            # Rotación libre de favoritos evitando los que ya están en pantalla
            return self.ch.get_vault_selection(orientation=t_orient, exclude=exclude_paths)

    def apply_to_cinnamon(self, final_path):
        try:
            # ------------------------------------------------------
            # 1. Imponer el entorno visual ideal para WMM
            #    Todos los cambios son necesarios para garantizar
            #    una transición limpia y una visualización correcta.
            # ------------------------------------------------------

            # Desactivar el pase de diapositivas nativo para que no interfiera
            os.system("gsettings set org.cinnamon.desktop.background.slideshow slideshow-enabled false")

            # La imagen debe ocupar todo el lienzo sin deformarse
            os.system("gsettings set org.cinnamon.desktop.background picture-options spanned")

            # El tipo de sombreado debe ser sólido, sin degradados
            os.system("gsettings set org.cinnamon.desktop.background color-shading-type 'solid'")

            # ------------------------------------------------------
            # 2. Verificar que los ajustes se han aplicado realmente.
            #    Si alguno falla, se añade un texto descriptivo a la
            #    lista 'issues' para notificarlo al usuario.
            # ------------------------------------------------------
            issues = []

            # Comprobar 'slideshow-enabled'
            result_slideshow = subprocess.run(
                ["gsettings", "get", "org.cinnamon.desktop.background.slideshow", "slideshow-enabled"],
                capture_output=True, text=True
            )
            if result_slideshow.stdout.strip().lower() != "false":
                issues.append(_("Slideshow disabled"))

            # Comprobar 'picture-options'
            result = subprocess.run(
                ["gsettings", "get", "org.cinnamon.desktop.background", "picture-options"],
                capture_output=True, text=True
            )
            if "spanned" not in result.stdout.lower():
                issues.append(_("Picture aspect set to 'Spanned'"))

            # Comprobar 'color-shading-type'
            result_shading = subprocess.run(
                ["gsettings", "get", "org.cinnamon.desktop.background", "color-shading-type"],
                capture_output=True, text=True
            )
            if "solid" not in result_shading.stdout.lower():
                issues.append(_("Color shading type set to 'solid'"))

            # Si alguna verificación falló, notificar al usuario
            if issues:
                self.ch._send_notification(
                    reason="WMM: " + _("Configuration issue"),
                    detail_msg=_("Please set the following in 'System Settings > Backgrounds':") +
                               "\n" + "\n".join(issues),
                    level="warn"
                )

            # ------------------------------------------------------
            # 3. Aplicar la imagen final según el modo de rotación
            # ------------------------------------------------------
            settings = self.ch.load_json("settings").get("global", {})
            sl_mode = settings.get("slideshow_mode", "sync")
            print(f">>> [DIAG] apply_to_cinnamon: final_path={final_path}, sl_mode={sl_mode}")
            if sl_mode == "sync":
                # 1.1 Capturar el color de fondo actual y generar imagen temporal para transición
                result_color = subprocess.run(
                    ["gsettings", "get", "org.cinnamon.desktop.background", "primary-color"],
                    capture_output=True, text=True
                )
                color_str = result_color.stdout.strip().lower().replace("'", "")
                rgba = Gdk.RGBA()
                if rgba.parse(color_str):
                    r = int(rgba.red * 255)
                    g = int(rgba.green * 255)
                    b = int(rgba.blue * 255)
                else:
                    r, g, b = 0, 0, 0
                fade_color_path = os.path.join(self.ch.cache_dir, "fade_color.png")
                Image.new('RGB', (1, 1), (r, g, b)).save(fade_color_path)

                os.system(f"gsettings set org.cinnamon.desktop.background picture-uri 'file://{fade_color_path}'")
                time.sleep(1.5)
                os.system(f"gsettings set org.cinnamon.desktop.background picture-uri 'file://{final_path}'")
                print(" -> [Sync] Transición Cine aplicada.")
                # Cambio inmediato
                os.system(f"gsettings set org.cinnamon.desktop.background picture-uri 'file://{final_path}'")
                print(" -> [Async] Transicion Crossfade aplicada.")

        except Exception as e:
            print(f" [ERROR] Cinnamon no respondió: {e}")
            self.ch.log_error(f"Cinnamon no respondió: {e}", reason="CINNAMON")

    def on_hardware_change(self, display, monitor):
        print(f"\n[{time.strftime('%H:%M:%S')}] Cambio físico detectado. Estabilizando geometría...")

        # Cancelamos cualquier ciclo de estabilización previo si existe
        if hasattr(self, '_reconfig_timer') and self._reconfig_timer:
            GLib.source_remove(self._reconfig_timer)

        # Damos 1.5 - 2 segundos para que Cinnamon reorganice el escritorio
        self._reconfig_timer = GLib.timeout_add(1000, self._final_hardware_sync)

    def _final_hardware_sync(self):
        self._reconfig_timer = None
        print(" [SISTEMA] Ejecutando sincronización final de geometría.")
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
        canvas_w, canvas_h = self.mm.get_total_canvas_geometry(monitors_map_real)
        geo_snapshot = {
            "timestamp": time.time(),
            "canvas": {"w": canvas_w, "h": canvas_h},
            "monitors": monitors_map_real
        }
        self.ch.save_json("geometry", geo_snapshot)
        print(f" [GEOMETRÍA] ¡Reset por {reason}! Nuevo lienzo: {canvas_w}x{canvas_h}")
        return geo_snapshot, canvas_w, canvas_h

    def startup_sync(self):
        """
        Sincronización inicial de geometría y vault, sin cambiar el fondo.
        Se ejecuta siempre al arrancar el motor.
        """
        print("[SISTEMA] Sincronizando geometría inicial...")
        monitors_map_real = self.mm.get_active_monitors_map()
        self._update_geometry(monitors_map_real, "Inicio de Servicio")

        # Sincronizar el vault con los monitores detectados
        active_hashes = list(monitors_map_real.keys())
        has_changed, _ = self.ch.sync_vault(active_hashes)
        if has_changed:
            print(" [VAULT] Sincronizado con la geometría actual.")

    def run(self):
        # print("--- WMM DAEMON INICIADO ---")
        # Limpiar miniaturas blur_ acumuladas de sesiones anteriores
        self.ch._cleanup_blur_thumbnails()
        try:
            result = self.ch.sync_library()
            if result and len(result) == 3:
                h, v, _ = result
                print(f" -> Biblioteca: {h}H / {v}V")
            else:
                print(" -> Biblioteca: No se pudo obtener el total.")
        except Exception as e:
            print(f" [ERROR] Escaneo inicial: {e}")
            self.ch.log_error(f"Escaneo inicial: {e}", reason="SYNC_LIB")

        # Sincronizar geometría y vault siempre
        self.startup_sync()

        # Al iniciar, si el usuario no quiere cambios, nos saltamos el ciclo.
        settings = self.ch.load_json("settings").get("global", {})
        if not settings.get("persist_on_reboot", True):  # Por defecto, mantener
            self.execute_full_cycle(reason=ConfigHandler.REASON_SERVICE)
        else:
            print(" -> Persistencia activa. Se mantiene el fondo actual.")

        try:
            self.loop.run()
        except (KeyboardInterrupt, SystemExit):
            print("\nCerrando WMM...")
            self.manage_timer(action="stop")
            self.loop.quit()

if __name__ == "__main__":
    daemon = WMMDaemon()
    daemon.run()
