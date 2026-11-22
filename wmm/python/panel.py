#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

"""
WMM - Wallpaper Multi-Monitor Manager

panel.py – Panel de control de WMM (Ajustes). ORQUESTADOR.
===============================
Instancia las secciones (Opciones, Favoritos, Fuentes, Monitores,
Thumbnails) y las empaqueta en la ventana principal.
Gestiona la comunicación entre secciones mediante callbacks.
"""

import os
import sys
import traceback
import json
import time
import gi
gi.require_version('Gdk', '3.0')
gi.require_version('Gtk', '3.0')
gi.require_version('Gio', '2.0')  # <--- Añadido para Gio.FileMonitor
from gi.repository import Gtk, Gdk, GLib, Gio

# ==========================================================
# CONFIGURACIÓN DEL PATH DEL PROYECTO
# ==========================================================
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

# ==========================================================
# IMPORTS DE MÓDULOS DEL PROYECTO
# ==========================================================
from wmm_platform.core import PlatformManager
from config_handler import ConfigHandler
from backend import WMMBackend
from image_engine import ImageEngine
from debug_logger import log_event
from i18n import _, initialize

# Secciones del panel
from panel.options_section import OptionsSection
from panel.favorites_section import FavoritesSection
from panel.sources_section import SourcesSection
from panel.monitors_section import MonitorsSection
from panel.thumbnails_section import ThumbnailsSection

class WMMControlPanel(Gtk.ApplicationWindow):
    """
    Ventana principal de configuración de WMM.
    """
    _WORKAREA_MARGIN = 65
    _LEFT_PANEL_TRANSITION_MS = 220

    def __init__(self, app):

        # ----------------------------------------------------------
        # INICIALIZACIÓN DE DEPENDENCIAS
        # ----------------------------------------------------------
        # Obtener la ruta de caché de la plataforma
        self.platform = PlatformManager()
        if hasattr(self.platform, "prepare_gtk_color_scheme"):
            self.platform.prepare_gtk_color_scheme()
        if hasattr(self.platform, "set_process_name"):
            self.platform.set_process_name("WMM Panel")
        log_event(f"Cache dir desde PlatformManager: {self.platform.cache_dir}",
            origin="PANEL", level="DEBUG", reason="SETTINGS")
        self.handler = ConfigHandler(cache_base_dir=self.platform.cache_dir)
        self.backend = WMMBackend(self.handler)
        self.ie = ImageEngine(self.handler, None)

        # Configurar el sistema de traducciones
        initialize(self.platform)

        # ----------------------------------------------------------
        # VARIABLES DE ESTADO DEL PANEL
        # ----------------------------------------------------------
        self._loading = False
        self._sources_operation_active = False

        # ----------------------------------------------------------
        # CSS COMPARTIDO DE WMM
        # ----------------------------------------------------------
        # Durante la migración conservamos el CSS incrustado como
        # respaldo. La ubicación del recurso es común a las plataformas.
        css_path = os.path.join(
            self.platform.app_dir, "wmm_platform", "shell", "common", "wmm.css")

        if os.path.isfile(css_path):
            shared_css_provider = Gtk.CssProvider()
            shared_css_provider.load_from_path(css_path)
            Gtk.StyleContext.add_provider_for_screen(
                Gdk.Screen.get_default(),
                shared_css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        else:
            log_event(f"CSS compartido no disponible: {css_path}",
                origin="PANEL", level="WARN", reason="SETTINGS")

        # ----------------------------------------------------------
        # CONSTRUCCIÓN DE LA INTERFAZ
        # ----------------------------------------------------------
        super().__init__(application=app, title="WMM - " + _("Control Center"))
        self.set_icon_name("preferences-system")
        self.set_position(Gtk.WindowPosition.CENTER)
        self.connect("map-event", self._on_initial_map)
        self.main_layout = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        # Limitar los switches compactos al contenido del Panel.
        self.main_layout.get_style_context().add_class("wmm-panel-switches")

        # Los separadores propios del Panel no deben afectar
        # a otras ventanas GTK que carguen el CSS compartido.
        self.main_layout.get_style_context().add_class("wmm-control-panel")
        self.main_layout.get_style_context().add_class("wmm-themed-separators")
        self.main_layout.set_border_width(10)
        self.add(self.main_layout)

        # BLOQUE IZQUIERDO
        self.left_wrapper = Gtk.Stack()
        self.left_wrapper.set_transition_type(Gtk.StackTransitionType.OVER_LEFT_RIGHT)
        self.left_wrapper.set_transition_duration(self._LEFT_PANEL_TRANSITION_MS)
        self.left_wrapper.set_hhomogeneous(False)
        self.left_wrapper.set_vhomogeneous(False)
        self.left_wrapper.set_interpolate_size(True)
        self.left_wrapper.connect("notify::transition-running", self._on_left_panel_transition_running)
        self.main_layout.pack_start(self.left_wrapper, False, False, 0)

        self.expanded_wrapper = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)

        self.left_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.left_col.set_size_request(350, -1)
        self.expanded_wrapper.pack_start(self.left_col, True, True, 0)

        separator = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        self.expanded_wrapper.pack_start(separator, False, False, 4)

        self.left_wrapper.add_named(self.expanded_wrapper, "expanded")

        self.collapsed_wrapper = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)

        self.collapsed_bar = self._build_collapsed_bar()
        self.collapsed_wrapper.pack_start(self.collapsed_bar, False, False, 0)

        separator = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        self.collapsed_wrapper.pack_start(separator, False, False, 4)

        self.left_wrapper.add_named(self.collapsed_wrapper, "collapsed")

        # COLUMNA DERECHA
        # Cabecera Displays fija; el Paned reparte únicamente
        # el espacio entre los monitores virtuales y Thumbnails.
        self.right_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.main_layout.pack_start(self.right_col, True, True, 0)

        self.monitors_header_slot = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.right_col.pack_start(self.monitors_header_slot, False, False, 0)

        self.monitor_thumb_paned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        self.monitor_thumb_paned.set_wide_handle(True)
        self.monitor_thumb_paned.get_style_context().add_class("wmm-monitors-split")
        self.right_col.pack_start(self.monitor_thumb_paned, True, True, 0)

        self.monitors_slot = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.thumbnails_slot = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        self.monitor_thumb_paned.pack1(self.monitors_slot, False, True)
        self.monitor_thumb_paned.pack2(self.thumbnails_slot, True, False)

        # ----------------------------------------------------------
        # WIDGETS COMPARTIDOS ENTRE SECCIONES
        # ----------------------------------------------------------
        # Estos widgets son usados por más de una sección.
        # Los creamos aquí y los pasamos como parámetros.

        # Checkbox de favorito (usado por Monitors y Favorites)
        self.fav_checkbox = Gtk.CheckButton(label="")

        # Botón Aceptar (usado por Monitors y Favorites)
        # MonitorsSection resuelve los tooltips según el origen de edición.
        self.accept_btn = Gtk.Button.new_from_icon_name("object-select-symbolic", Gtk.IconSize.BUTTON)
        self.accept_btn.set_sensitive(False)

        # Recurso visual único para las fases secuenciales Sources → Thumbnails:
        # progress, resync_notice y spacer comparten el mismo espacio visual.
        self.scan_progress = Gtk.ProgressBar()
        self.scan_progress.set_no_show_all(True)
        self.scan_progress.hide()
        self.btn_spacer = Gtk.Box()
        # ----------------------------------------------------------
        # INSTANCIACIÓN DE SECCIONES
        # ----------------------------------------------------------
        # Todas las secciones que requieren callbacks se crean sin ellos
        # y los reciben después mediante set_callbacks(), evitando
        # dependencias circulares.

        # 1. Monitores
        self.monitors_section = MonitorsSection(
            self.handler, self.backend, self.ie, self.monitors_slot,
            header_col=self.monitors_header_slot,
            fav_checkbox=self.fav_checkbox,
            accept_btn=self.accept_btn,
            spanned_switch=None)

        # 2. Opciones
        self.options_section = OptionsSection(
            self.handler, self.backend, self.ie, self.left_col)

        # 3. Favoritos
        self.favorites_section = FavoritesSection(
            self.handler, self.backend, self.ie, self.left_col)

        # 4. Asignar callbacks a las tres primeras
        self.monitors_section.set_callbacks(self._build_monitors_callbacks())
        self.options_section.set_callbacks(self._build_options_callbacks())
        self.favorites_section.set_callbacks(self._build_favorites_callbacks())

        # 5. Asignar spanned_switch de Options a Monitors
        self.monitors_section.spanned_switch = self.options_section.spanned_switch

        # 6. Fuentes (independiente)
        self.sources_section = SourcesSection(
            self.handler, self.backend, self.ie, self.left_col,
            scan_progress=self.scan_progress, btn_spacer=self.btn_spacer)

        # El Panel conserva la autoridad de la operación global de Sources.
        # Progress representa visualmente sus fases, pero no gobierna su interactividad.
        self.sources_section.set_callbacks({
            'begin_sources_operation': self._begin_sources_operation,
            'finish_sources_operation': self._finish_sources_operation,
            'is_sources_operation_active': self._is_sources_operation_active,
            'set_progress_active': self._set_progress_active,
            'refresh_selective_rotation_availability':
                self.options_section.refresh_selective_rotation_availability,
            'get_parent_window': lambda: self,
        })

        # 7. Thumbnails (sin callbacks aún)
        self.thumbnails_section = ThumbnailsSection(
            self.handler, self.backend, self.thumbnails_slot,
            scan_progress=self.scan_progress,
            btn_spacer=self.btn_spacer)

        # Ahora que existe, le asignamos sus callbacks
        self.thumbnails_section.set_callbacks(self._build_thumbnails_callbacks())

        # Adaptar la representación al tirador y al espacio disponible.
        self.monitor_thumb_paned.connect("notify::position", self._on_monitor_split_changed)

        # Detectar el final real del ajuste, sin temporizadores ni polling.
        self._monitor_split_drag_start = None
        self.monitor_thumb_paned.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK)
        self.monitor_thumb_paned.connect("button-press-event", self._on_monitor_split_pressed)
        self.monitor_thumb_paned.connect_after("button-release-event", self._on_monitor_split_released)
        self.monitor_thumb_paned.connect("size-allocate", self._on_monitor_split_changed)

        # Puente explícito entre fases: al terminar Sources, continuar con Thumbnails.
        self.sources_section._callbacks['load_thumbnails'] = self.thumbnails_section._load_thumbnails

        # Al descargar originales Online, ejecutar la misma sincronización de Sources.
        self.thumbnails_section.online_section.set_library_sync_callback(
            self.sources_section.on_refresh_sources_clicked)

        # El Panel comunica traslados a Monitors sin exponer su sesión a Online.
        self.thumbnails_section.online_section.set_online_promotion_callback(
            self.monitors_section.on_online_original_promoted)

        # La selección de Sources sólo filtra la vista local ya construida.
        self.sources_section.sources_tree.get_selection().connect(
            "changed", self.thumbnails_section.on_source_selection_changed)

        # El clic sobre una fuente ya seleccionada también debe abrir Library.
        self.sources_section.sources_tree.connect(
            "button-press-event", self.thumbnails_section.on_source_row_pressed)

        # ----------------------------------------------------------
        # CARGA INICIAL DE DATOS
        # ----------------------------------------------------------
        self.sources_section.load_sources_into_treeview()
        self._load_settings()
        self.favorites_section._load_presets()
        # Una única mutación de bookmarks_single debe reflejarse en sus tres vistas:
        # lista de Favorites, marcas de thumbnails y vista filtrada de favoritos.
        self.favorites_section._load_bookmarks_single()
        self.thumbnails_section._load_thumbnails()
        GLib.idle_add(self.monitors_section._load_monitors_normal)

        # ----------------------------------------------------------
        # SEÑALES DEL SISTEMA
        # ----------------------------------------------------------
        self._setup_panel_communications()
        log_event("Registro de PID completado.", origin="PANEL", level="DEBUG", reason="NOTIFY")
        self.connect("delete-event", self._on_delete_event)
        # El tamaño persistido es sólo la petición inicial; tras el primer map,
        # la plataforma vuelve a imponer los límites de la workarea actual.
        self._restore_window_size()

        self.show_all()
        self.sources_section._update_resync_notice()
        self._restore_section_states()
        self._restore_left_panel_state()

        # Activar el flag de monitores tras el primer layout completo
        GLib.timeout_add(300, self._initialize_monitor_split)

    # ==========================================================
    # ESTADO VISUAL DE LAS SECCIONES
    # ==========================================================
    def _save_section_state(self, section, expanded):
        """Guarda el estado de despliegue de una sección del panel."""
        settings = self.backend.load_json("settings")
        panel_state = settings.setdefault("panel", {})
        sections = panel_state.setdefault("sections", {})
        sections[section] = bool(expanded)
        self.backend.save_json("settings", settings)
        log_event(f"Estado de sección guardado: {section}={expanded}",
            origin="PANEL", level="DEBUG", reason="SETTINGS")

    def _save_options_subsection_states(self):
        """Persiste el estado visual de las subsecciones de Opciones."""
        options = self.options_section
        states = {
            "persist": options.persist_content.get_visible(),
            "spanned": options.spanned_content.get_visible(),
            "slideshow": options.slideshow_content.get_visible(),
            "metadata": options.metadata_content.get_visible()
        }

        settings = self.backend.load_json("settings")
        settings.setdefault("panel", {})["options_subsections"] = states
        self.backend.save_json("settings", settings)

    def _fold_options_subsections_to_fit(self, required_height, available_height,
            protected=None):
        """Pliega subsecciones sólo cuando las secciones principales no bastan."""
        options = self.options_section

        if not options.options_content.get_visible():
            return required_height()

        subsections = (
            ("metadata", options.metadata_content),
            ("slideshow", options.slideshow_content),
            ("spanned", options.spanned_content),
            ("persist", options.persist_content),
        )

        for name, content in subsections:
            if required_height() <= available_height:
                break

            if name == protected or not content.get_visible():
                continue

            options.set_subsection_expanded(name, False)
            log_event(
                f"Subsección {name} plegada automáticamente",
                origin="PANEL", level="DEBUG", reason="LAYOUT")

        return required_height()

    def _expand_section_to_fit(self, requested, requested_subsection=None):
        """Abre una sección cerrando antes otras si la altura disponible lo exige."""
        sections = {
            "options": (self.options_section, self.options_section.options_content),
            "favorites": (self.favorites_section, self.favorites_section.favorites_container),
            "sources": (self.sources_section, self.sources_section.sources_content),
        }

        section, _ = sections[requested]

        self._preserve_window_position_on_expand()
        section.set_expanded(True)

        area = self.platform.get_window_available_area(os.getpid())
        if not area:
            return

        available_height = area["height"] - self._WORKAREA_MARGIN
        border = self.main_layout.get_border_width()

        def required_height():
            # Sólo la columna izquierda participa en las decisiones de plegado.
            left_minimum, _ = self.left_col.get_preferred_size()
            return left_minimum.height + (border * 2)

        required = required_height()

        for candidate in ("sources", "favorites"):
            if required <= available_height:
                break
            if candidate == requested:
                continue

            candidate_section, candidate_content = sections[candidate]
            if not candidate_content.get_visible():
                continue

            candidate_section.set_expanded(False)
            required = required_height()
            log_event(f"{candidate.capitalize()} plegada automáticamente al abrir {requested}: requerido={required}, disponible={available_height}",
                origin="PANEL", level="DEBUG", reason="LAYOUT")

        # Segundo nivel: conservar la petición del usuario y plegar
        # subsecciones sólo después de agotar las secciones principales.
        if required > available_height:
            required = self._fold_options_subsections_to_fit(
                required_height, available_height,
                protected=requested_subsection)

        if required > available_height:
            log_event(f"El panel sigue excediendo el área disponible al abrir {requested}: requerido={required}, disponible={available_height}",
                origin="PANEL", level="WARN", reason="LAYOUT")

        self.main_layout.queue_resize()

    def _restore_section_states(self):
        """Restaura el último estado de despliegue de las secciones del bloque izquierdo."""
        settings = self.backend.load_json("settings")
        sections = settings.get("panel", {}).get("sections", {})

        self.options_section.set_expanded(sections.get("options", True))
        self.favorites_section.set_expanded(sections.get("favorites", True))
        self.sources_section.set_expanded(sections.get("sources", True))
        self.options_section.restore_subsection_states(
            settings.get("panel", {}).get("options_subsections", {}))

        # Recuperar la última selección por identidad lógica.
        # Expandir sus ancestros antes de seleccionarla evita perder
        # el puntero cuando la carpeta está dentro de una rama plegada.
        selected_path = settings.get("panel", {}).get("selected_source_path")

        if selected_path is not None:
            tree = self.sources_section.sources_tree

            def restore_selection(model, path, tree_iter, *args):
                if model.get_value(tree_iter, 2) != selected_path:
                    return False

                tree.expand_to_path(path)
                tree.get_selection().select_path(path)
                tree.scroll_to_cell(path, None, True, 0.5, 0.0)
                return True

            self.sources_section.sources_model.foreach(restore_selection)

        GLib.idle_add(self._fit_collapsed)

    def _save_left_panel_state(self, collapsed):
        """Guarda el estado de plegado del bloque izquierdo."""
        settings = self.backend.load_json("settings")
        panel_state = settings.setdefault("panel", {})
        panel_state["collapsed"] = bool(collapsed)
        self.backend.save_json("settings", settings)
        log_event(f"Estado del bloque izquierdo guardado: collapsed={collapsed}",
            origin="PANEL", level="DEBUG", reason="SETTINGS")


    def _set_left_panel_collapsed(self, collapsed, persist=True, animate=True):
        """Alterna entre el bloque izquierdo completo y la barra lateral compacta."""
        if not collapsed:
            area = self.platform.get_window_available_area(os.getpid())

            if area:
                available_height = area["height"] - self._WORKAREA_MARGIN
                border = self.main_layout.get_border_width()

                def required_height():
                    left_minimum, _ = self.left_col.get_preferred_size()
                    right_minimum, _ = self.right_col.get_preferred_size()
                    return max(left_minimum.height, right_minimum.height) + (border * 2)

                required = required_height()

                if required > available_height and self.sources_section.sources_content.get_visible():
                    self.sources_section.set_expanded(False)
                    required = required_height()
                    log_event(
                        f"Fuentes plegada automáticamente para ajustar el panel: "
                        f"requerido={required}, disponible={available_height}",
                        origin="PANEL", level="DEBUG", reason="LAYOUT")

                if required > available_height and self.favorites_section.favorites_container.get_visible():
                    self.favorites_section.set_expanded(False)
                    required = required_height()
                    log_event(
                        f"Favoritos plegada automáticamente para ajustar el panel: "
                        f"requerido={required}, disponible={available_height}",
                        origin="PANEL", level="DEBUG", reason="LAYOUT")

                # Si Fuentes y Favoritos no liberan suficiente altura,
                # continuar con las subsecciones de Opciones.
                if required > available_height:
                    required = self._fold_options_subsections_to_fit(
                        required_height, available_height)

                if required > available_height:
                    log_event(
                        f"El panel sigue excediendo el área disponible tras el ajuste: "
                        f"requerido={required}, disponible={available_height}",
                        origin="PANEL", level="WARN", reason="LAYOUT")

        duration = self._LEFT_PANEL_TRANSITION_MS if animate else 0
        self.left_wrapper.set_transition_duration(duration)

        if persist:
            self._save_left_panel_state(collapsed)

        log_event(f"Bloque izquierdo {'plegado' if collapsed else 'desplegado'}",
            origin="PANEL", level="DEBUG", reason="SETTINGS")

        # Al plegar, desvanecer primero el contenido mientras todavía dispone
        # de todo su ancho. Sólo después comienza la reducción del Gtk.Stack,
        # evitando que los textos lleguen a refluir.
        if collapsed and animate:
            fade_values = (
                0.94, 0.88, 0.82, 0.76,
                0.70, 0.64, 0.58, 0.52,
                0.46, 0.40, 0.34, 0.28,
                0.22, 0.16, 0.08, 0.0
            )
            self.left_col.set_opacity(fade_values[0])
            fade_index = 1

            def fade_before_collapse():
                nonlocal fade_index

                self.left_col.set_opacity(fade_values[fade_index])
                fade_index += 1

                if fade_index < len(fade_values):
                    return GLib.SOURCE_CONTINUE

                self.left_wrapper.set_visible_child_name("collapsed")

                # Si GTK no ejecuta animaciones, no habrá transición posterior
                # que restaure la opacidad mediante notify::transition-running.
                if not self.left_wrapper.get_transition_running():
                    self.left_col.set_opacity(1.0)

                self.main_layout.queue_resize()
                return GLib.SOURCE_REMOVE

            GLib.timeout_add(16, fade_before_collapse)
            return

        # Desplegado y restauraciones de estado sin animación.
        self.left_col.set_opacity(1.0)
        self.left_wrapper.set_visible_child_name(
            "collapsed" if collapsed else "expanded"
        )

        self.main_layout.queue_resize()

    def _on_left_panel_transition_running(self, stack, _param):
        """Restaura el contenido expandido al terminar la transición."""
        if not stack.get_transition_running():
            self.left_col.set_opacity(1.0)

    def _restore_left_panel_state(self):
        """Prepara el bloque izquierdo plegado antes del primer mapeo."""
        settings = self.backend.load_json("settings")
        self._initial_left_panel_collapsed = settings.get("panel", {}).get("collapsed", False)
        self._set_left_panel_collapsed(True, persist=False, animate=False)

    def _build_collapsed_bar(self):
        """Construye la barra lateral mostrada cuando el bloque izquierdo está plegado."""
        bar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        bar.set_size_request(40, -1)
        bar.set_margin_start(0)
        bar.set_margin_end(6)

        expand_btn = Gtk.Button.new_from_icon_name(
            "media-playback-start-symbolic", Gtk.IconSize.BUTTON)
        expand_btn.get_image().set_pixel_size(14)

        expand_btn.set_tooltip_text(_("Expand side panel"))
        expand_btn.connect("clicked", lambda *_: self._set_left_panel_collapsed(False))
        bar.pack_start(expand_btn, False, False, 0)

        help_btn = Gtk.Button.new_from_icon_name("help-contents", Gtk.IconSize.BUTTON)
        help_btn.set_tooltip_text(_("Open Help"))
        help_btn.set_margin_top(10)
        help_btn.connect("clicked", self._on_open_help)
        bar.pack_start(help_btn, False, False, 0)

        debug_log_btn = Gtk.Button.new_from_icon_name("text-x-generic", Gtk.IconSize.BUTTON)
        debug_log_btn.set_tooltip_text(_("Open Debug Log Viewer"))
        debug_log_btn.connect("clicked", self._on_open_debug_log)
        bar.pack_start(debug_log_btn, False, False, 0)

        restart_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        restart_btn.set_tooltip_text(_("Restart engine and panel"))
        restart_btn.set_margin_top(10)
        restart_btn.connect("clicked", lambda widget: self.options_section._on_restart_clicked(widget))
        bar.pack_start(restart_btn, False, False, 0)

        return bar

    # ==========================================================
    # CALLBACKS PARA OPTIONS SECTION
    # ==========================================================
    def _build_options_callbacks(self):
        """Construye el diccionario de callbacks para OptionsSection."""
        return {
            'create_section_label': self._create_section_label,
            'notify_engine': self._notify_engine,
            'load_monitors': self.monitors_section._load_monitors_normal,
            'set_monitor_switches_sensitive': self.monitors_section._set_monitor_switches_sensitive,
            'get_edit_mode_active': lambda: self.backend.edit_mode_active,
            'get_loading_state': lambda: self._loading,
            'get_fav_rotation_switch': lambda: self.favorites_section.fav_rotation_switch,
            'set_selective_rotation_mode':
                lambda enabled: self.sources_section.set_selective_mode(enabled),
            'get_parent_window': lambda: self,
            'refresh_online_sources': lambda: self.sources_section.on_refresh_sources_clicked(None),
            'get_application': lambda: self.get_application(),
            'save_window_size': self._save_window_size,
            'on_open_debug_log': self._on_open_debug_log,
            'on_open_help': self._on_open_help,
            'collapse_left_panel': lambda: self._set_left_panel_collapsed(True),
        }

    # ==========================================================
    # CALLBACKS PARA MONITORS SECTION
    # ==========================================================
    def _build_monitors_callbacks(self):
        """Construye el diccionario de callbacks para MonitorsSection."""
        return {
            'create_section_label': self._create_section_label,
            'notify_engine': self._notify_engine,
            'load_monitors': self.monitors_section._load_monitors_normal,
            'load_presets': self.favorites_section._load_presets,
            'load_bookmarks_single': self.favorites_section._load_bookmarks_single,
            'set_monitor_switches_sensitive': self.monitors_section._set_monitor_switches_sensitive,
            'get_loading_state': lambda: self._loading,
            'get_edit_mode_active': lambda: self.backend.edit_mode_active,
            'get_parent_window': lambda: self,
            'refresh_online_sources': lambda: self.sources_section.on_refresh_sources_clicked(None),
            'mark_online_incorporated': lambda paths:
                self.thumbnails_section.online_section.mark_incorporated_originals(paths),
        }

    # ==========================================================
    # CALLBACKS PARA FAVORITES SECTION
    # ==========================================================
    def _build_favorites_callbacks(self):
        """Construye el diccionario de callbacks para FavoritesSection."""
        return {
            'on_load_preset_to_edit': self._on_load_preset_to_edit,
            'on_update_mode_info_label': self.options_section._update_mode_info_label,
            'notify_engine': self._notify_engine,
            'on_show_warning_dialog': self._show_warning_dialog,
            'on_single_favorites_changed': self._refresh_single_favorites,
            'get_loading_state': lambda: self._loading,
            'get_parent_window': lambda: self,
        }

    # ==========================================================
    # CALLBACKS PARA THUMBNAILS SECTION
    # ==========================================================
    def _build_thumbnails_callbacks(self):
        """Construye el diccionario de callbacks para ThumbnailsSection."""
        return {
            'begin_sources_operation': self._begin_sources_operation,
            'finish_sources_operation': self._finish_sources_operation,
            'is_sources_operation_active': self._is_sources_operation_active,
            'is_sources_tree_rebuilding': lambda: self.sources_section._rebuilding_sources_tree,
            'set_progress_active': self._set_progress_active,
            'get_parent_window': lambda: self,
            'on_single_favorites_changed': self._refresh_single_favorites,
        }

    # ==========================================================
    # MÉTODOS AUXILIARES DEL PANEL
    # ==========================================================
    def _refresh_single_favorites(self):
        """Sincroniza las vistas que representan bookmarks_single."""
        self.favorites_section._load_bookmarks_single()
        self.thumbnails_section._refresh_favorite_state()
        self.thumbnails_section._load_favorites_view()
        return False

    def create_context_menu(self):
        """Crea un menú GTK y delega su presentación nativa al SO."""
        menu = Gtk.Menu()
        menu.get_style_context().add_class("wmm-themed-separators")

        # Windows desactiva las decoraciones que generan el marco azul
        # del tema win32. Linux conserva el comportamiento GTK original.
        if hasattr(self.platform, "prepare_gtk_context_menu"):
            self.platform.prepare_gtk_context_menu(menu)

        return menu

    def _create_section_label(self, text):
        """Crea una etiqueta de sección con formato."""
        label = Gtk.Label()
        label.set_markup(f"<span weight='bold' size='large'>{text}</span>")
        label.set_halign(Gtk.Align.START)
        return label

    def _monitor_header_offset(self):
        """Altura fija anterior al Paned, incluida la separación visual."""
        return (self.monitors_section._header_box.get_preferred_height()[1]
            + self.right_col.get_spacing())

    def _on_monitor_split_pressed(self, paned, event):
        """Registra únicamente movimientos iniciados sobre el tirador."""
        if event.button == 1 and event.window == paned.get_handle_window():
            self._monitor_split_drag_start = paned.get_position()
        return False

    def _on_monitor_split_released(self, paned, event):
        """Consolida la calidad cuando termina un movimiento del tirador."""
        if event.button != 1 or self._monitor_split_drag_start is None:
            return False

        initial = self._monitor_split_drag_start
        self._monitor_split_drag_start = None

        if paned.get_position() != initial:
            self._on_monitor_split_changed(paned)
            self.monitors_section._refresh_visual_preview_quality()

        return False

    def _initialize_monitor_split(self):
        """Aplica el reparto natural inicial o la posición persistida."""
        section = self.monitors_section
        section.on_panel_realized()

        if not self._monitor_split_has_saved_position:
            natural_h = section.monitor_group_box.get_preferred_height()[1]
            self.monitor_thumb_paned.set_position(natural_h)

        self._on_monitor_split_changed(self.monitor_thumb_paned)
        return GLib.SOURCE_REMOVE

    def _on_monitor_split_changed(self, paned, _pspec=None):
        """Limita la expansión vertical al espacio útil de los monitores."""
        section = self.monitors_section
        if not section._panel_realized:
            return

        controls_h = (section._switch_align_box.get_preferred_height()[1]
            + section._button_align_box.get_preferred_height()[1])

        area_w = section._monitor_resize_area.get_allocated_width()
        position = paned.get_position()

        # La anchura física limita cuánto pueden crecer los monitores.
        max_canvas_h = section._get_max_visual_area_height(area_w)
        if max_canvas_h is not None:
            max_position = controls_h + max_canvas_h
            if position > max_position:
                position = max_position
                paned.set_position(position)

        # Por debajo del mínimo visual, conservar el recorte progresivo.
        section._apply_visual_layout(area_w, position - controls_h)

    def _restore_window_size(self):
        """Solicita el último tamaño guardado; la workarea actual conserva la autoridad final."""
        settings = self.backend.load_json("settings")
        panel_state = settings.get("panel", {})

        # La posición persistida incluye la cabecera fija.
        split_position = panel_state.get("monitors_split_position")
        self._monitor_split_has_saved_position = (
            type(split_position) is int and split_position > 0)

        if self._monitor_split_has_saved_position:
            self.monitor_thumb_paned.set_position(
                max(0, split_position - self._monitor_header_offset()))

        window_size = panel_state.get("window_size", {})

        if not isinstance(window_size, dict):
            return

        width = window_size.get("width")
        height = window_size.get("height")

        if type(width) is not int or type(height) is not int or width <= 0 or height <= 0:
            return

        self.set_default_size(width, height)
        log_event(f"Tamaño guardado del Panel solicitado: {width}x{height}",
            origin="PANEL", level="DEBUG", reason="LAYOUT")

    def _save_window_size(self):
        """Guarda tamaño y selección de Sources al finalizar limpiamente."""
        width, height = self.get_size()

        if width <= 0 or height <= 0:
            return

        settings = self.backend.load_json("settings")
        panel_state = settings.setdefault("panel", {})
        panel_state["window_size"] = { "width": int(width), "height": int(height), }

        # Persistir el reparto junto con la geometría de la ventana,
        # nunca durante cada movimiento del separador.
        split_position = self.monitor_thumb_paned.get_position()
        if split_position > 0:
            panel_state["monitors_split_position"] = int(
                split_position + self._monitor_header_offset())

        # La selección se identifica por su ruta, no por su posición GTK.
        # Se guarda junto al tamaño para evitar escrituras en cada clic.
        selection = self.sources_section.sources_tree.get_selection()
        model, tree_iter = selection.get_selected()
        panel_state["selected_source_path"] = (
            model.get_value(tree_iter, 2) if tree_iter else None)

        self.backend.save_json("settings", settings)
        log_event(f"Tamaño del Panel guardado: {width}x{height}",
            origin="PANEL", level="DEBUG", reason="SETTINGS")

    def _update_window_size_limit(self):
        """Actualiza el tamaño máximo según la workarea del monitor actual."""
        if not hasattr(self.platform, "set_window_size_limit"):
            return False

        area = self.platform.get_window_available_area(os.getpid())
        if not area:
            return False

        max_width = area["width"]
        max_height = max(1, area["height"] - self._WORKAREA_MARGIN)

        self.platform.set_window_size_limit(self, max_width, max_height)
        return False

    def _preserve_window_position_on_expand(self):
        """Delega en la plataforma cualquier corrección previa a una expansión."""
        self._update_window_size_limit()
        self.platform.preserve_window_position_on_expand(os.getpid())

    def _on_initial_map(self, widget, event):
        """Aplica una corrección específica de plataforma tras el primer mapeo."""
        self.disconnect_by_func(self._on_initial_map)
        self._update_window_size_limit()
        GLib.timeout_add(50, self._correct_initial_window_position)
        return False

    def _correct_initial_window_position(self):
        self.platform.correct_initial_window_position(os.getpid())

        if not self._initial_left_panel_collapsed:
            self._set_left_panel_collapsed(False, persist=False, animate=False)

        return False

    def _fit_collapsed(self):
        """Limita la ventana al tamaño disponible de su área de trabajo."""
        area = self.platform.get_window_available_area(os.getpid())

        if not area:
            return False

        window_w, window_h = self.get_size()
        available_width = area["width"]
        available_height = max(1, area["height"] - self._WORKAREA_MARGIN)
        fitted_w = min(window_w, available_width)
        fitted_h = min(window_h, available_height)

        if fitted_w != window_w or fitted_h != window_h:
            log_event(f"Panel reajustado: {window_w}x{window_h} -> {fitted_w}x{fitted_h} "
                f"(workarea={area['width']}x{area['height']}, margen={self._WORKAREA_MARGIN})",
                origin="PANEL", level="DEBUG", reason="LAYOUT")
            self.resize(fitted_w, fitted_h)

        return False

    def _notify_engine(self, action=None):
        if action is None:
            action = {"action": "force_rotation"}
        self.backend.notify_engine(action)
        time.sleep(0.05)

    def _begin_sources_operation(self):
        """Abre una operación global y mantiene Sources no interactiva hasta su FIN."""
        if self._sources_operation_active:
            return False

        self._sources_operation_active = True
        self._set_sources_sensitive(False)
        return True

    def _finish_sources_operation(self):
        """Cierra la operación global y devuelve Sources al usuario una sola vez."""
        if not self._sources_operation_active:
            return False

        self._sources_operation_active = False
        self._set_sources_sensitive(True)

        # La representación final de Sources se reconstruye sólo al alcanzar el FIN global.
        if hasattr(self, 'sources_section'):
            GLib.idle_add(self.sources_section.load_sources_into_treeview)

        return False

    def _is_sources_operation_active(self):
        """Indica si existe una operación global que mantiene Sources bloqueada."""
        return self._sources_operation_active

    def _set_sources_sensitive(self, sensitive):
        """Activa/desactiva la sección de fuentes durante operaciones largas."""
        if hasattr(self, 'sources_section'):
            self.sources_section._set_sources_sensitive(sensitive)

    def _set_progress_active(self, active, text=None):
        """Muestra/oculta la barra de progreso."""
        # Barra, aviso de resincronización y spacer son mutuamente excluyentes:
        # representan fases distintas dentro del mismo espacio visual.
        if active:
            log_event(f"Barra de progreso activada: {text or ''}",
                      origin="PANEL", level="INFO", reason="LIBRARY")
        else:
            log_event("Barra de progreso desactivada",
                      origin="PANEL", level="INFO", reason="LIBRARY")
        if active:
            # Mientras una fase está activa, progress ocupa el espacio compartido
            # y oculta cualquier aviso pendiente de Sources.
            self.btn_spacer.hide()
            if hasattr(self, 'sources_section'):
                self.sources_section.resync_notice.hide()

            self.scan_progress.show()
            self.scan_progress.set_fraction(0.0)
            if text:
                self.scan_progress.set_show_text(True)
                self.scan_progress.set_text(text)
        else:
            self.scan_progress.hide()
            self.scan_progress.set_fraction(0.0)
            self.scan_progress.set_show_text(False)

            if hasattr(self, 'sources_section'):
            # Al liberar progress, devolver el espacio al estado global de Sources:
            # resync_notice si queda trabajo pendiente; spacer en caso contrario.
                self.sources_section._update_resync_notice()
            else:
                self.btn_spacer.show()

    def _show_warning_dialog(self, message):
        """Muestra un diálogo de advertencia."""
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.OK,
            text=message
        )
        dialog.run()
        dialog.destroy()

    # ==========================================================
    # CARGA DE PREFERENCIAS DESDE SETTINGS.JSON
    # ==========================================================

    def _load_settings(self):
        """Carga los ajustes desde settings.json y actualiza la interfaz."""
        self._loading = True
        settings = self.backend.load_settings()
        opts = self.options_section

        # ----------------------------------------------------------
        # CHANGE WALLPAPER ON STARTUP
        # ----------------------------------------------------------
        # --- Change wallpaper on startup ---
        opts.persist_switch.set_active(
            not settings.get("persist_on_reboot", True))

        # --- Match monitor orientation ---
        opts.match_orientation_switch.set_active(
            settings.get("match_orientation", True))

        # --- Selective rotation ---
        opts.selective_rotation_switch.set_active(
            settings.get("selective_rotation_enabled", False))
        opts.refresh_selective_rotation_availability()

        # Durante la carga, notify::active no propaga cambios a Sources.
        # Reflejar explícitamente el estado persistido del modo selectivo.
        self.sources_section.set_selective_mode(
            opts.selective_rotation_switch.get_active())

        # --- Slideshow mode ---
        opts.mode_switch.set_active(
            settings.get("slideshow_mode", "sync") == "sync")

        # ----------------------------------------------------------
        # SPANNED
        # ----------------------------------------------------------
        # --- Spanned ---
        opts.spanned_switch.set_active(
            settings.get("spanned_enabled", False))

        # --- Picture aspect ---
        mode = settings.get("wallpaper_mode", "fit")
        keys = list(ConfigHandler.ASPECT_MODES.keys())
        index = keys.index(mode) if mode in keys else 0
        opts.aspect_combo.set_active(index)

        # --- Image Effect ---
        wallpaper_effect = settings.get("wallpaper_effect", "none")
        keys = list(ConfigHandler.IMAGE_EFFECT.keys())
        index = (keys.index(wallpaper_effect)
            if wallpaper_effect in ConfigHandler.IMAGE_EFFECT else 0)
        opts.image_effect_combo.set_active(index)

        # --- Background Effect ---
        wallpaper_effect_scope = settings.get("wallpaper_effect_scope", "blur")
        keys = list(ConfigHandler.BACK_EFFECT.keys())
        index = (keys.index(wallpaper_effect_scope)
            if wallpaper_effect_scope in ConfigHandler.BACK_EFFECT else 0)
        opts.back_effect_combo.set_active(index)

        # --- Background color ---
        color_mode = settings.get("color_mode", "solid_color")
        keys = list(ConfigHandler.COLOR_MODES.keys())
        index = keys.index(color_mode) if color_mode in keys else 0
        opts.bg_mode_combo.set_active(index)
        opts._update_bg_color_buttons(color_mode)

        self._set_btn_color(
            opts.solid_color_btn, settings.get("solid_color", "#000000"))
        grad_h = settings.get("gradient_h", ["#000000", "#8D9797"])
        self._set_btn_color(opts.grad_h_start_btn, grad_h[0])
        self._set_btn_color(opts.grad_h_end_btn, grad_h[1])
        grad_v = settings.get("gradient_v", ["#000000", "#8D9797"])
        self._set_btn_color(opts.grad_v_start_btn, grad_v[0])
        self._set_btn_color(opts.grad_v_end_btn, grad_v[1])

        # ----------------------------------------------------------
        # SLIDESHOW
        # ----------------------------------------------------------
        # --- Slideshow ---
        opts.slideshow_switch.set_active(
            settings.get("slideshow_enabled", True))

        # --- Max. Frequency ---
        opts.max_interval_spin.set_value(
            settings.get("slideshow_max_interval", 60))

        # --- Slideshow every ---
        opts.rotation_spin.set_value(
            settings.get("slideshow_interval", 15))

        # ----------------------------------------------------------
        # IMAGE METADATA
        # ----------------------------------------------------------
        # --- Image Metadata ---
        opts.metadata_switch.set_active(
            settings.get("exif_metadata_enabled", False))

        # --- Visible fields ---
        # Los campos se leen al abrir su diálogo, no durante esta carga.

        # --- Font and size ---
        opts.metadata_font_button.set_font(
            settings.get("exif_metadata_font", "Sans 12"))

        # --- Position ---
        position = settings.get("exif_metadata_position", "top_left")
        if position not in ConfigHandler.METADATA_POSITIONS:
            position = "top_left"
        opts.metadata_position_combo.set_active_id(position)

        # --- Horizontal margin ---
        opts.metadata_margin_x_scale.set_value(
            max(0, min(100, settings.get("exif_metadata_margin_x", 64))))

        # --- Vertical margin ---
        opts.metadata_margin_y_scale.set_value(
            max(0, min(100, settings.get("exif_metadata_margin_y", 42))))

        # --- Background opacity ---
        opacity = settings.get("exif_metadata_background_opacity", 40)
        opts.metadata_opacity_scale.set_value(
            max(0, min(100, opacity)))

        # ----------------------------------------------------------
        # FAVORITES
        # ----------------------------------------------------------
        # --- Favorites rotation ---
        self.favorites_section.fav_rotation_switch.set_active(
            settings.get("slideshow_bookmark", False))

        # La etiqueta Sync/Async depende también del modo Favorites.
        # Actualizarla sólo después de cargar ambos switches.
        opts._update_mode_info_label()

        # ----------------------------------------------------------
        # DISPLAYS
        # ----------------------------------------------------------
        # --- Monitor group alignment ---
        align_value = settings.get("monitor_group_align", "START")
        align_map = {
            "START": Gtk.Align.START,
            "CENTER": Gtk.Align.CENTER,
            "END": Gtk.Align.END
        }
        self.monitors_section.monitor_group_box.set_halign(
            align_map.get(align_value, Gtk.Align.START))
        self.monitors_section._update_align_labels(
            align_map.get(align_value, Gtk.Align.START))

        self._loading = False

    @staticmethod
    def _set_btn_color(btn, hex_color):
        """Aplica un color hexadecimal a un Gtk.ColorButton."""
        rgba = Gdk.RGBA()
        rgba.parse(hex_color)
        btn.set_rgba(rgba)

    # ==========================================================
    # CARGA DE PRESET EN MODO EDICIÓN (LLAMADO DESDE FAVORITOS)
    # ==========================================================
    def _on_load_preset_to_edit(self, preset_name):
        """Callback cuando FavoritesSection solicita cargar un preset en modo edición."""
        # Activar modo edición si no lo está
        if not self.backend.edit_mode_active:
            self.monitors_section.edit_mode_btn.set_active(True)

        # Delegar en el backend la carga de datos del preset
        preset_monitors = self.backend.load_preset_for_edit(preset_name)
        if preset_monitors is None:
            return

        # Cargar un preset restablece la edición virtual, incluso si
        # anteriormente estaba activa la vista física desde Online.
        self.monitors_section._edit_live_preview = False

        # Actualizar UI
        self.monitors_section._current_preset_name = preset_name
        self.fav_checkbox.set_active(True)

        # Sincronizar UI de edición con valores temporales del backend
        # Restaurar la relación de aspecto sin interpretar el cambio
        # visual del combo como una nueva edición de la composición.
        if self.backend.edit_temp_wp_mode is not None:
            keys = list(ConfigHandler.ASPECT_MODES.keys())
            mode = self.backend.edit_temp_wp_mode
            index = keys.index(mode) if mode in keys else 0

            combo = self.monitors_section.aspect_combo_edit
            callback = self.monitors_section._on_aspect_edit_changed

            combo.handler_block_by_func(callback)
            try:
                combo.set_active(index)
            finally:
                combo.handler_unblock_by_func(callback)

        if self.backend.edit_temp_spanned_enabled is not None:
            self.monitors_section.spanned_switch_edit.set_active(self.backend.edit_temp_spanned_enabled)
        if self.backend.edit_temp_image_effect is not None:
            keys = list(ConfigHandler.IMAGE_EFFECT.keys())
            index = keys.index(self.backend.edit_temp_image_effect) if self.backend.edit_temp_image_effect in keys else 0
            self.monitors_section.image_effect_combo_edit.set_active(index)
        if self.backend.edit_temp_wp_scope is not None:
            # No hay combo para esto en edición, se guarda por consistencia
            pass

        # Pintar los monitores virtuales con los datos del preset
        self.monitors_section._load_monitors_edit()
        self.monitors_section._load_preset_to_edit_monitors(preset_monitors)

        # Sincronizar los switches de activación
        self.monitors_section._build_monitor_switches()

        # Actualizar la etiqueta de edición con el nombre del preset
        self.monitors_section.edit_preset_label.set_markup(
            "<b>" + _("Editing") + ":" + "\n" + preset_name + "</b>"
        )
        self.monitors_section.edit_preset_label.set_ellipsize(3)  # Pango.EllipsizeMode.END
        self.monitors_section.edit_preset_label.set_max_width_chars(24)
        self.monitors_section.edit_label_stack.set_visible_child_name("edit_preset")

        log_event(f"Preset cargado en edición: {preset_name}",
            origin="PANEL", level="INFO", reason="BOOKMARK")

    # ==========================================================
    # APERTURA DE VENTANAS EXTERNAS
    # ==========================================================
    def _on_open_debug_log(self, widget=None):
        """Abre Debug Log Viewer como herramienta independiente del engine."""
        debug_log_viewer_path = os.path.join(os.path.dirname(__file__), "debug_log_viewer.py")

        try:
            Gio.Subprocess.new(
                [sys.executable, debug_log_viewer_path],
                Gio.SubprocessFlags.NONE)
        except GLib.Error as error:
            log_event(f"No se pudo abrir Debug Log Viewer: {error}",
                origin="PANEL", level="ERROR", reason="COMMAND")

    def _on_open_help(self, widget=None):
        """Solicita al motor abrir la documentación de ayuda."""
        self._notify_engine({"action": ConfigHandler.CMD_OPEN_HELP})

    # ==========================================================
    # GESTIÓN DE PID Y SEÑALES DEL MOTOR
    # ==========================================================
    def _setup_panel_communications(self):
        """Instala el canal de eventos entre el engine y el panel."""

        # Las plataformas con transporte nativo reciben los eventos del engine
        # directamente. Las demás conservan command_panel.json + FileMonitor.
        if self.platform.start_receiving_panel_events(
                self._process_panel_event):
            log_event("Canal nativo de eventos del panel iniciado",
                origin="PANEL", level="INFO", reason="COMMAND")
        else:
            self._setup_panel_monitor()

    def _setup_panel_monitor(self):
        """Configura el Gio.FileMonitor para escuchar command_panel.json."""
        command_path = os.path.join(self.handler.data_dir, "command_panel.json")
        # Asegurar que el archivo existe para evitar warnings iniciales
        if not os.path.exists(command_path):
            with open(command_path, 'w') as f:
                json.dump({}, f)

        command_file = Gio.File.new_for_path(command_path)
        self._panel_monitor = command_file.monitor_file(Gio.FileMonitorFlags.NONE, None)
        self._panel_monitor.connect("changed", self._on_panel_file_changed)
        log_event("Monitor de command_panel.json iniciado. Esperando eventos del motor...",
            origin="PANEL", level="INFO", reason="COMMAND")

    def _process_panel_event(self, event):
        """
        Procesa un evento recibido del engine independientemente del transporte.

        FileMonitor y los transportes nativos convergen aquí para mantener una
        única autoridad sobre las acciones que actualizan el panel.
        """
        action = event.get("action", "")

        if not action:
            return

        log_event(f"Evento recibido del motor: {action}",
            origin="PANEL", level="DEBUG", reason="COMMAND")

        if action == "wallpaper_changed":
            GLib.idle_add(self.monitors_section._load_monitors_normal)

        elif action == "settings_updated":
            GLib.idle_add(self._load_settings)

        elif action == "bookmarks_updated":
            GLib.idle_add(self.favorites_section._load_presets)
            GLib.idle_add(self._refresh_single_favorites)

        elif action == "hardware_changed":
            GLib.idle_add(self.monitors_section._refresh_after_hardware_change)

            # Windows: workaround GTK para recuperar el D&D después
            # de un cambio de topología física de monitores.
            if self.platform.platform == "win32":
                GLib.idle_add(self.platform.recover_dnd_after_topology_change, self)

        elif action == "shutdown":
            log_event("Cierre solicitado por el engine",
                origin="PANEL", level="INFO", reason="COMMAND")
            self._on_delete_event(None, None)

        else:
            log_event(f"Acción desconocida recibida del motor: {action}",
                origin="PANEL", level="WARN", reason="COMMAND")

    def _on_panel_file_changed(self, monitor, file, other_file, event_type):
        """Recibe eventos del engine mediante command_panel.json."""
        try:
            if event_type != Gio.FileMonitorEvent.CHANGES_DONE_HINT:
                return

            command_path = file.get_path()

            with open(command_path, "r", encoding="utf-8") as f:
                event = json.load(f)

            if not event.get("action"):
                return

            # Vaciar inmediatamente el buzón para evitar reprocesados.
            with open(command_path, "w", encoding="utf-8") as f:
                json.dump({}, f)

            self._process_panel_event(event)

        except json.JSONDecodeError:
            # El archivo estaba a medias, lo ignoramos.
            pass

        except Exception as e:
            log_event(f"Error al procesar evento del motor: {e}",
                origin="PANEL", level="ERROR", reason="COMMAND")

    def _on_delete_event(self, widget, event):
        """Guarda el tamaño final y limpia el monitor al cerrar."""
        self._save_window_size()

        # Cancelar el monitor de archivos
        if hasattr(self, '_panel_monitor') and self._panel_monitor:
            self._panel_monitor.cancel()

        app = self.get_application()
        if app:
            app.quit()
        return True


class PanelApplication(Gtk.Application):
    """Aplicación GTK para el panel de control (instancia única)."""
    def __init__(self):
        super().__init__(application_id="org.wmm.Panel")
        self.window = None

    def do_activate(self):
        """Crea o presenta el panel y evita instancias huérfanas si falla el arranque."""
        def present(window):
            if hasattr(window.platform, "present_window"):
                window.platform.present_window(window)
            else:
                window.present()

        if self.window:
            present(self.window)
            return

        try:
            window = WMMControlPanel(self)
            self.add_window(window)
            self.window = window
            present(window)

        except Exception as e:
            # El traceback debe quedar disponible incluso si el logger de WMM
            # todavía no ha terminado de inicializarse.
            traceback.print_exc()

            try:
                log_event(f"Error fatal al iniciar el Panel: {e}",
                    origin="PANEL", level="ERROR", reason="INIT")
            except Exception:
                pass

            # Si la ventana no ha podido construirse, esta Gtk.Application no
            # debe permanecer registrada sin ventana y recibir futuras activaciones.
            self.window = None
            self.quit()

if __name__ == "__main__":
    app = PanelApplication()
    app.run(sys.argv)
