#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

"""
WMM - Wallpaper Multi-Monitor Manager

mate-applet.py - MATE Panel Applet
==================================
Frontend nativo de WMM para MATE Panel.

El applet actúa únicamente como cliente del engine común:
- activa org.maki.wmm mediante D-Bus cuando es necesario;
- envía acciones normales mediante python/send_command.py;
- consulta settings/bookmarks por D-Bus;
- escucha SettingsChanged/BookmarksChanged;
- refleja engine_status.json en el icono;
- la eliminación explícita del applet del panel solicita Shutdown.
"""

import gettext
import json
import os
import sys
import gi
import dbus
import dbus.service

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("MatePanelApplet", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk, MatePanelApplet
from dbus.mainloop.glib import DBusGMainLoop

# ==========================================================
# D-BUS: HEALTH ENDPOINT DEL APPLET
# ==========================================================
DBusGMainLoop(set_as_default=True)

mate_applet_bus_name = "org.maki.wmm.MateApplet"
mate_applet_object_path = "/org/maki/wmm/MateApplet"
mate_applet_interface = "org.maki.wmm.MateApplet"

# ==========================================================
# RUTAS WMM
# ==========================================================
app_dir = os.path.dirname(os.path.abspath(__file__))
send_command_path = os.path.join(app_dir, "python", "send_command.py")
cache_dir = os.path.join(GLib.get_user_cache_dir(), "wmm")
status_path = os.path.join(cache_dir, "engine_status.json")
css_path = os.path.join(app_dir, "wmm_platform", "shell", "mate", "mate-applet.css")
install_manager_path = os.path.join(app_dir, "wmm_platform", "shell", "installer", "wmm-install_manager.py")
debug_log_viewer_path = os.path.join(app_dir, "python", "debug_log_viewer.py")

# ==========================================================
# CONFIGURACIÓN LOCAL DEL FRONTEND
# ==========================================================
favorites_visible_rows = 4

# ==========================================================
# ESTADO DE LA FACTORÍA
# ==========================================================

_active_wmm_instance = None

# ==========================================================
# HOJA DE ESTILOS
# ==========================================================

wmm_css_provider = None

def _load_wmm_css():
    """Carga una sola vez los estilos propios del applet MATE."""
    global wmm_css_provider

    if wmm_css_provider is not None or not os.path.isfile(css_path):
        return

    try:
        provider = Gtk.CssProvider()
        provider.load_from_path(css_path)

        screen = Gdk.Screen.get_default()
        if screen is None:
            return

        Gtk.StyleContext.add_provider_for_screen(screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        wmm_css_provider = provider

    except GLib.Error as error:
        print(f"[WMM MATE] No se pudo cargar mate-applet.css: {error}", file=sys.stderr)

# ==========================================================
# TRADUCCIONES
# ==========================================================
gettext.bindtextdomain("wmm@maki", os.path.join(GLib.get_user_data_dir(), "locale"))

def _(text):
    """Traduce una cadena usando el dominio gettext propio de WMM."""
    return gettext.dgettext("wmm@maki", text)


class WMMMateAppletDBus(dbus.service.Object):
    """Health endpoint D-Bus del proceso de la factoría MATE de WMM."""

    def __init__(self):
        """Registra un único endpoint de salud para el proceso de la factoría."""
        self.bus = dbus.SessionBus()
        self.bus_name = dbus.service.BusName(mate_applet_bus_name, bus=self.bus, do_not_queue=True)
        super().__init__(self.bus_name, mate_applet_object_path)

    @dbus.service.method(mate_applet_interface, in_signature="", out_signature="s")
    def Ping(self):
        """Devuelve una respuesta mínima para comprobar que el applet está vivo."""
        return "pong"

    @dbus.service.method(mate_applet_interface, in_signature="", out_signature="s")
    def GetObjectId(self):
        """Devuelve el object-id de la instancia WMM activa."""
        if _active_wmm_instance is None:
            return ""

        return _active_wmm_instance.panel_object_id or ""

class WMMMateApplet:
    """Controlador de una instancia de WMM dentro de MATE Panel."""

    def __init__(self, applet):
        """Inicializa una instancia visual del applet y conecta sus fuentes de estado."""
        self.applet = applet
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)

        self.panel_settings = Gio.Settings.new("org.mate.panel")
        self.panel_object_id = self._find_panel_object_id()
        self._panel_objects_signal_id = self.panel_settings.connect("changed::object-id-list", self._on_panel_objects_changed)
        self._panel_removal_shutdown = False

        self._destroyed = False
        self._syncing_ui = False
        self._motor_busy = False
        self._ignore_next_busy = False

        self._current_interval = 15
        self._current_max_interval = 60
        self._cached_bookmarks = {}

        self._status_monitor = None
        self._settings_signal_id = 0
        self._bookmarks_signal_id = 0

        _load_wmm_css()
        self._build_applet()
        self._build_menu()
        self._subscribe_engine_signals()
        self._start_status_monitor()
        self._start_engine(self._refresh_all)

    # ==========================================================
    # APPLET
    # ==========================================================

    def _build_applet(self):
        """Construye el icono del panel, tooltip y eventos propios del applet."""
        self.icon = Gtk.Image.new_from_icon_name("video-display", Gtk.IconSize.MENU)
        self.icon.set_pixel_size(max(1, int(self.applet.get_size())))
        self.icon.set_margin_start(5)
        self.icon.set_margin_end(5)
        self.applet.add(self.icon)

        tooltip = (
            "WMM: " + _("Wallpaper Multi-Monitor Manager") + "\n" +
            _("Click action") + ": " + _("Next Background") + "\n" +
            _("Secondary Click") + ": " + _("Context Menu")
        )
        self.applet.set_tooltip_text(tooltip)

        self.applet.connect("button-press-event", self._on_button_press)
        self.applet.connect("change-size", self._on_change_size)
        self.applet.connect("destroy", self._on_destroy)

    def _on_button_press(self, widget, event):
        """Procesa clic izquierdo para rotación y deja el derecho al menú nativo."""
        if event.button == 1:
            if self._motor_busy:
                self._set_icon("view-refresh")
                return True

            self._set_icon("view-refresh")
            self._ignore_next_busy = True
            self._send_action_to_engine({"action": "force_rotation"})
            return True

        if event.button == 3:
            self._refresh_all()
            return False

        return False

    def _on_change_size(self, applet, size):
        """Adapta el icono al tamaño actual del panel MATE."""
        self.icon.set_pixel_size(max(1, int(size)))

    def _set_icon(self, icon_name):
        """Actualiza el icono del applet respetando el tamaño actual del panel."""
        if self._destroyed:
            return
        self.icon.set_from_icon_name(icon_name, Gtk.IconSize.MENU)
        self.icon.set_pixel_size(max(1, int(self.applet.get_size())))

    # ==========================================================
    # MENÚ NATIVO DE MATE
    # ==========================================================

    def _build_menu(self):
        """Construye el menú nativo y añade las secciones inline de WMM.

        setup_menu() crea los Gtk.MenuItem nativos de MATE a partir del XML.
        Favorites y Slideshow se declaran como cabeceras normales y después se
        amplían con widgets GTK insertados directamente bajo cada cabecera.

        MATE sigue exponiendo setup_menu() mediante Gtk.ActionGroup; por eso
        Gtk.Action/Gtk.ToggleAction se mantienen solo para los items nativos.
        Sus DeprecationWarning no se silencian: documentan una limitación
        estructural de la API pública de MATE, no un fallo de WMM.
        """
        self.actions = Gtk.ActionGroup(name="WMMActions")

        # Acciones visibles gestionadas por el menú nativo de MATE.
        self.favorites_menu_action = self._add_action("FavoritesMenu", _("Favorites"))
        self.slideshow_menu_action = self._add_action("SlideshowMenu", _("Slideshow"))
        self.sync_action = self._add_toggle_action(
            "DisplaysSync", _("Displays") + ": " + _("ASYNC (One)"), self._on_sync_mode)
        self.spanned_action = self._add_toggle_action("Spanned", _("Spanned Mode"), self._on_spanned)
        self.tools_menu_action = self._add_action("ToolsMenu", _("Tools"))
        self.settings_action = self._add_action("Settings", _("Settings"), self._on_settings, "preferences-system")
        self.sync_library_action = self._add_action(
            "SyncLibrary", _("Sync Library"), self._on_sync_library, "emblem-synchronizing")
        self.install_manager_action = self._add_action(
            "InstallManager", _("Install Manager"), self._on_install_manager, "system-software-install")
        self.debug_log_viewer_action = self._add_action(
            "DebugLogViewer", _("Debug Log Viewer"), self._on_debug_log_viewer, "edit-find")
        self.help_action = self._add_action("Help", _("Help"), self._on_help, "help-faq")
        self.about_action = self._add_action("AboutWMM", _("About") + " WMM Manager", self._on_about, "user-info")

        menu_xml = """
        <menuitem name="WMMFavorites" action="FavoritesMenu"/>
        <menuitem name="WMMSlideshow" action="SlideshowMenu"/>
        <menuitem name="WMMDisplaysSync" action="DisplaysSync"/>
        <menuitem name="WMMSpanned" action="Spanned"/>
        <separator/>
        <menuitem name="WMMTools" action="ToolsMenu"/>
        <menuitem name="WMMSettings" action="Settings"/>
        <menuitem name="WMMSyncLibrary" action="SyncLibrary"/>
        <menuitem name="WMMInstallManager" action="InstallManager"/>
        <menuitem name="WMMDebugLogViewer" action="DebugLogViewer"/>
        <menuitem name="WMMHelp" action="Help"/>
        <separator/>
        <menuitem name="WMMAbout" action="AboutWMM"/>
        """

        self.applet.setup_menu(menu_xml, self.actions)

        # Estas tres secciones sustituyen los antiguos submenús/diálogos.
        self._build_favorites_inline()
        self._build_slideshow_inline()
        self._build_tools_inline()

    def _build_favorites_inline(self):
        """Construye Favorites inline bajo la cabecera nativa de MATE.

        La lista conserva altura natural hasta favorites_visible_rows filas.
        A partir de ahí Gtk.ScrolledWindow mantiene el GtkAdjustment y WMM
        gestiona la rueda manualmente, con la scrollbar oculta mediante CSS.
        """
        header_item = next((proxy
            for proxy in self.favorites_menu_action.get_proxies()
            if isinstance(proxy.get_parent(), Gtk.Menu)), None)

        if not header_item:
            return

        menu = header_item.get_parent()
        position = menu.get_children().index(header_item) + 1

        self._favorites_expanded = False
        self._favorites_hover_widget = None
        self.favorites_header_item = header_item

        # Indicador de expansión en la misma columna visual que los checkboxes.
        self.favorites_indicator = Gtk.Image.new_from_icon_name("pan-end-symbolic", Gtk.IconSize.MENU)
        self.favorites_header_item.set_image(self.favorites_indicator)
        self.favorites_header_item.set_always_show_image(True)

        # Favorites Only.
        self.favorites_switch_item = Gtk.MenuItem()
        switch_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        switch_box.set_margin_start(0)
        switch_box.set_margin_end(0)

        switch_label = Gtk.Label(label=_("Favorites Only"), xalign=0)
        self.favorites_only_switch = Gtk.Switch()
        self.favorites_only_switch.connect("notify::active", self._on_favorites_only_switch_changed)

        switch_box.pack_start(switch_label, True, True, 0)
        switch_box.pack_end(self.favorites_only_switch, False, False, 0)
        self.favorites_switch_item.add(switch_box)

        # Add Preset Favorite.
        self.favorites_add_item = Gtk.ImageMenuItem.new_with_label(_("Add Preset Favorite"))

        add_icon = Gtk.Image.new_from_icon_name("list-add", Gtk.IconSize.MENU)
        self.favorites_add_item.set_image(add_icon)
        self.favorites_add_item.set_always_show_image(True)

        # Scrollbox de favoritos: Gtk.ScrolledWindow limita la altura y
        # mantiene el GtkAdjustment; la navegación se realiza con la rueda.
        self.favorites_scroll_item = Gtk.MenuItem()

        self.favorites_scrolled = Gtk.ScrolledWindow()
        self.favorites_scrolled.set_overlay_scrolling(True)
        self.favorites_scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.favorites_scrolled.set_propagate_natural_height(True)
        self.favorites_scrolled.set_margin_start(0)
        self.favorites_scrolled.set_margin_end(0)

        favorites_scrollbar = self.favorites_scrolled.get_vscrollbar()
        favorites_scrollbar.get_style_context().add_class("wmm-hidden-scrollbar")

        self.favorites_inline_list = Gtk.ListBox()
        self.favorites_inline_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.favorites_scrolled.add(self.favorites_inline_list)
        self.favorites_scroll_item.add(self.favorites_scrolled)

        menu.insert(self.favorites_switch_item, position)
        menu.insert(self.favorites_add_item, position + 1)
        menu.insert(self.favorites_scroll_item, position + 2)

        self.favorites_switch_item.show_all()
        self.favorites_add_item.show_all()
        self.favorites_scroll_item.show_all()
        self.favorites_switch_item.hide()
        self.favorites_add_item.hide()
        self.favorites_scroll_item.hide()

        self._paint_inline_bookmarks()

    def _build_slideshow_inline(self):
        """Inserta Switch y slider bajo Slideshow y conecta el controlador inline.

        Gtk.Menu conserva el grab del puntero mientras está abierto. Por eso los
        widgets internos no pueden depender de su interacción GTK normal: el menú
        captura press/motion/release/scroll y delega manualmente en Switch, slider
        y lista de favoritos sin cerrar el popup.

        También se conserva el toplevel real del popup: su señal unmap permite
        replegar siempre las secciones al cerrar el menú y su Gdk.Window permite
        reajustar la geometría cuando Favorites o Slideshow cambian de altura.
        """
        header_item = next((proxy for proxy in self.slideshow_menu_action.get_proxies()
            if isinstance(proxy.get_parent(), Gtk.Menu)), None)
        if not header_item:
            return

        menu = header_item.get_parent()
        position = menu.get_children().index(header_item) + 1

        self.inline_menu = menu
        self.inline_menu_toplevel = self.inline_menu.get_toplevel()
        self.inline_menu_toplevel.connect("unmap", self._on_inline_menu_toplevel_unmap)
        self._slideshow_scale_dragging = False

        self.inline_menu.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK |
            Gdk.EventMask.BUTTON_RELEASE_MASK |
            Gdk.EventMask.POINTER_MOTION_MASK |
            Gdk.EventMask.SCROLL_MASK
        )
        self.inline_menu.connect("button-press-event", self._on_inline_menu_button_press)
        self.inline_menu.connect("motion-notify-event", self._on_inline_menu_motion)
        self.inline_menu.connect("button-release-event", self._on_inline_menu_button_release)
        self.inline_menu.connect("scroll-event", self._on_inline_menu_scroll)

        self._slideshow_expanded = False
        self.slideshow_header_item = header_item

        self.slideshow_indicator = Gtk.Image.new_from_icon_name("pan-end-symbolic", Gtk.IconSize.MENU)
        self.slideshow_header_item.set_image(self.slideshow_indicator)
        self.slideshow_header_item.set_always_show_image(True)

        # Switch maestro.
        self.slideshow_switch_item = Gtk.MenuItem()
        switch_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        switch_box.set_margin_start(0)
        switch_box.set_margin_end(0)

        self.slideshow_switch_label = Gtk.Label(label=_("Disabled"), xalign=0)
        self.slideshow_switch = Gtk.Switch()
        self.slideshow_switch.connect("notify::active", self._on_slideshow_switch_changed)

        switch_box.pack_start(self.slideshow_switch_label, True, True, 0)
        switch_box.pack_end(self.slideshow_switch, False, False, 0)
        self.slideshow_switch_item.add(switch_box)

        # Intervalo + slider.
        self.slideshow_interval_item = Gtk.MenuItem()
        interval_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        interval_box.set_margin_start(0)
        interval_box.set_margin_end(0)

        self.slideshow_interval_label = Gtk.Label(label=str(self._current_interval) + " " + _("minutes"))
        self.slideshow_interval_label.set_halign(Gtk.Align.CENTER)

        self.slideshow_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, self._current_max_interval, 1)
        self.slideshow_scale.set_draw_value(False)
        self.slideshow_scale.set_value(self._current_interval)
        self.slideshow_scale.set_hexpand(True)
        self.slideshow_scale.set_size_request(-1, -1)
        self.slideshow_scale.connect("value-changed", self._on_slideshow_scale_changed)

        interval_box.pack_start(self.slideshow_interval_label, False, False, 0)
        interval_box.pack_start(self.slideshow_scale, False, False, 0)
        self.slideshow_interval_item.add(interval_box)

        menu.insert(self.slideshow_switch_item, position)
        menu.insert(self.slideshow_interval_item, position + 1)

        self.slideshow_switch_item.show_all()
        self.slideshow_interval_item.show_all()
        self.slideshow_switch_item.hide()
        self.slideshow_interval_item.hide()

    def _build_tools_inline(self):
        """Convierte Tools en una sección desplegable inline del menú de MATE."""
        header_item = next((proxy
                for proxy in self.tools_menu_action.get_proxies()
                if isinstance(proxy.get_parent(), Gtk.Menu)), None)

        if not header_item:
            return

        self._tools_expanded = False
        self.tools_header_item = header_item

        self.tools_indicator = Gtk.Image.new_from_icon_name("pan-end-symbolic", Gtk.IconSize.MENU)
        self.tools_header_item.set_image(self.tools_indicator)
        self.tools_header_item.set_always_show_image(True)

        self.tools_inline_items = []

        for action in (
            self.settings_action,
            self.sync_library_action,
            self.install_manager_action,
            self.debug_log_viewer_action,
            self.help_action,
        ):
            proxy = next((proxy
                    for proxy in action.get_proxies()
                    if isinstance(proxy.get_parent(), Gtk.Menu)),None)

            if proxy:
                self.tools_inline_items.append(proxy)
                proxy.hide()

    # ==========================================================
    # MENÚ INLINE: CICLO DE VIDA Y GEOMETRÍA
    # ==========================================================

    def _on_inline_menu_toplevel_unmap(self, widget):
        """Repliega las secciones inline para que cada nueva apertura empiece cerrada."""
        self._favorites_expanded = False
        self._slideshow_expanded = False
        self._tools_expanded = False

        self.favorites_switch_item.hide()
        self.favorites_add_item.hide()
        self.favorites_scroll_item.hide()

        self.slideshow_switch_item.hide()
        self.slideshow_interval_item.hide()

        for item in self.tools_inline_items:
            item.hide()

        self.favorites_indicator.set_from_icon_name("pan-end-symbolic", Gtk.IconSize.MENU)
        self.slideshow_indicator.set_from_icon_name("pan-end-symbolic", Gtk.IconSize.MENU)
        self.tools_indicator.set_from_icon_name("pan-end-symbolic", Gtk.IconSize.MENU)

    def _resize_inline_menu_native_window(self):
        """Adapta la ventana nativa del popup al tamaño natural del menú.

        Gtk.Menu conserva la altura asignada al abrirse y activa su scroll interno
        si después aumenta el contenido. El reajuste se difiere con idle_add() y se
        aplica sobre la Gdk.Window real, nivel en el que MATE acepta el nuevo tamaño.
        """
        _, natural = self.inline_menu.get_preferred_size()
        native_window = self.inline_menu_toplevel.get_window()

        if native_window is not None:
            native_window.resize(natural.width, natural.height)

        return False

    # ==========================================================
    # MENÚ INLINE: CONTROL DE EVENTOS
    # ==========================================================

    def _set_slideshow_scale_from_event(self, menu, event):
        """Convierte la posición del puntero en un valor del slider de Slideshow."""
        if not self.slideshow_scale.get_sensitive():
            return False

        menu_window = menu.get_window()
        if menu_window is None:
            return False

        _, origin_x, origin_y = menu_window.get_origin()
        menu_x = int(event.x_root - origin_x)
        menu_y = int(event.y_root - origin_y)

        translated = menu.translate_coordinates(self.slideshow_scale, menu_x, menu_y)
        if translated is None:
            return False

        x, y = translated
        width = self.slideshow_scale.get_allocated_width()
        height = self.slideshow_scale.get_allocated_height()

        if width <= 0 or height <= 0:
            return False

        if x < 0 or x > width or y < 0 or y > height:
            return False

        fraction = max(0.0, min(1.0, x / width))

        if self.slideshow_scale.get_direction() == Gtk.TextDirection.RTL:
            fraction = 1.0 - fraction

        adjustment = self.slideshow_scale.get_adjustment()
        value = adjustment.get_lower() + fraction * (adjustment.get_upper() - adjustment.get_lower())

        self.slideshow_scale.set_value(round(value))
        return True

    def _on_inline_menu_button_press(self, menu, event):
        """Inicia el drag manual del slider cuando el clic cae dentro de su área."""
        if event.button != 1:
            return False

        selected_item = menu.get_selected_item()

        if selected_item is self.slideshow_interval_item and not self.slideshow_scale.get_sensitive():
            return True

        if not self._set_slideshow_scale_from_event(menu, event):
            return False

        self._slideshow_scale_dragging = True
        return True

    def _on_inline_menu_motion(self, menu, event):
        """Actualiza el slider durante drag o el hover manual de los favoritos."""
        if self._slideshow_scale_dragging:
            self._set_slideshow_scale_from_event(menu, event)
            return True

        self._update_favorites_hover(menu, event)
        return False

    def _on_inline_menu_scroll(self, menu, event):
        """Desplaza la lista de favoritos con la rueda sin mostrar scrollbar."""
        selected_item = menu.get_selected_item()

        if selected_item is not self.favorites_scroll_item:
            return False

        adjustment = self.favorites_scrolled.get_vadjustment()
        step = max(adjustment.get_step_increment(), 24.0)

        if event.direction == Gdk.ScrollDirection.UP:
            delta = -step
        elif event.direction == Gdk.ScrollDirection.DOWN:
            delta = step
        elif event.direction == Gdk.ScrollDirection.SMOOTH:
            success, delta_x, delta_y = event.get_scroll_deltas()
            if not success:
                return True
            delta = delta_y * step
        else:
            return True

        lower = adjustment.get_lower()
        upper = max(lower, adjustment.get_upper() - adjustment.get_page_size())
        adjustment.set_value(max(lower, min(upper, adjustment.get_value() + delta)))

        return True

    def _event_inside_widget(self, menu, event, widget):
        """Comprueba por coordenadas si un evento del Gtk.Menu cae en un widget."""
        if widget is None or not widget.get_visible():
            return False

        menu_window = menu.get_window()
        if menu_window is None:
            return False

        _, origin_x, origin_y = menu_window.get_origin()
        menu_x = int(event.x_root - origin_x)
        menu_y = int(event.y_root - origin_y)

        translated = menu.translate_coordinates(widget, menu_x, menu_y)
        if translated is None:
            return False

        x, y = translated
        width = widget.get_allocated_width()
        height = widget.get_allocated_height()

        return 0 <= x < width and 0 <= y < height

    def _update_favorites_hover(self, menu, event):
        """Aplica PRELIGHT a nombre/papelera según la posición real del puntero."""
        hover_widget = None

        if self._favorites_expanded:
            for row in self.favorites_inline_list.get_children():
                if self._event_inside_widget(menu, event, getattr(row, "wmm_delete_widget", None)):
                    hover_widget = row.wmm_delete_widget
                    break

                if self._event_inside_widget(menu, event, getattr(row, "wmm_name_widget", None)):
                    hover_widget = row.wmm_name_widget
                    break

        previous = self._favorites_hover_widget

        if previous is hover_widget:
            return

        if previous is not None:
            previous.unset_state_flags(Gtk.StateFlags.PRELIGHT)

        self._favorites_hover_widget = hover_widget

        if hover_widget is not None:
            hover_widget.set_state_flags(Gtk.StateFlags.PRELIGHT, False)

    def _on_inline_menu_button_release(self, menu, event):
        """Despacha controles inline sin cerrar el popup salvo cuando es necesario.

        Al desplegar o replegar Favorites/Slideshow programa también el reajuste
        de la ventana nativa para que el popup siga la nueva altura del contenido.
        """
        if event.button != 1:
            return False

        if self._slideshow_scale_dragging:
            self._set_slideshow_scale_from_event(menu, event)
            self._slideshow_scale_dragging = False

            if self.slideshow_switch.get_active():
                self._update_timer_settings()

            return True

        selected_item = menu.get_selected_item()

        # Favorites: expandir/replegar.
        if selected_item is self.favorites_header_item:
            self._favorites_expanded = not self._favorites_expanded
            if self._favorites_expanded:
                self._update_favorites_scroll_height()
            self.favorites_switch_item.set_visible(self._favorites_expanded)
            self.favorites_add_item.set_visible(self._favorites_expanded)
            self.favorites_scroll_item.set_visible(self._favorites_expanded)
            self.favorites_indicator.set_from_icon_name("pan-down-symbolic"
                if self._favorites_expanded else "pan-end-symbolic", Gtk.IconSize.MENU)
            GLib.idle_add(self._resize_inline_menu_native_window)
            return True

        # Favorites Only: el Gtk.Menu posee el grab, así que accionamos el Switch.
        if selected_item is self.favorites_switch_item:
            self.favorites_only_switch.set_active(not self.favorites_only_switch.get_active())
            return True

        # Add abre un formulario externo: aquí sí cerramos el popup.
        if selected_item is self.favorites_add_item:
            menu.popdown()
            self._send_action_to_engine({"action": "add_bookmark"})
            return True

        # Lista inline: nombre carga y mantiene abierto; papelera abre confirmación.
        if selected_item is self.favorites_scroll_item:
            for row in self.favorites_inline_list.get_children():
                name = getattr(row, "wmm_name", None)
                if not name:
                    continue

                if self._event_inside_widget(menu, event, getattr(row, "wmm_delete_widget", None)):
                    menu.popdown()
                    self._confirm_delete_favorite(name)
                    return True

                if self._event_inside_widget(menu, event, getattr(row, "wmm_name_widget", None)):
                    self._load_favorite(name)
                    return True

            return True

        # Slideshow: expandir/replegar.
        if selected_item is self.slideshow_header_item:
            self._slideshow_expanded = not self._slideshow_expanded
            self.slideshow_switch_item.set_visible(self._slideshow_expanded)
            self.slideshow_interval_item.set_visible(self._slideshow_expanded)
            self.slideshow_indicator.set_from_icon_name("pan-down-symbolic"
                if self._slideshow_expanded else "pan-end-symbolic", Gtk.IconSize.MENU)
            GLib.idle_add(self._resize_inline_menu_native_window)
            return True

        # Tools: expandir/replegar.
        if selected_item is self.tools_header_item:
            self._tools_expanded = not self._tools_expanded

            for item in self.tools_inline_items:
                item.set_visible(self._tools_expanded)

            self.tools_indicator.set_from_icon_name("pan-down-symbolic"
                if self._tools_expanded else "pan-end-symbolic", Gtk.IconSize.MENU)

            GLib.idle_add(self._resize_inline_menu_native_window)
            return True

        # Switch de Slideshow gobernado manualmente por el Gtk.Menu.
        if selected_item is self.slideshow_switch_item:
            self.slideshow_switch.set_active(not self.slideshow_switch.get_active())
            return True

        # Clic sobre la fila del slider: mantener el menú abierto.
        if selected_item is self.slideshow_interval_item:
            return True

        return False

    # ==========================================================
    # MENÚ INLINE: CALLBACKS DE CONTROLES
    # ==========================================================

    def _on_slideshow_switch_changed(self, switch, pspec):
        """Sincroniza la UI y envía el nuevo estado de Slideshow al engine."""
        if self._syncing_ui:
            return

        self._sync_slideshow_ui(switch.get_active())
        self._update_timer_settings()

    def _on_slideshow_scale_changed(self, scale):
        """Actualiza en vivo el intervalo mostrado mientras se mueve el slider."""
        self._current_interval = int(round(scale.get_value()))
        self.slideshow_interval_label.set_text(str(self._current_interval) + " " + _("minutes"))

    # ==========================================================
    # MENÚ NATIVO: HELPERS GTK.ACTION
    # ==========================================================

    def _add_action(self, name, label, callback=None, icon_name=None):
        """Crea y registra una Gtk.Action usada por setup_menu()."""
        action = Gtk.Action(name=name, label=label, tooltip=None, stock_id=None)

        if icon_name:
            action.set_icon_name(icon_name)
            action.set_always_show_image(True)

        if callback:
            action.connect("activate", callback)

        self.actions.add_action(action)
        return action

    def _add_toggle_action(self, name, label, callback):
        """Crea y registra una Gtk.ToggleAction usada por setup_menu()."""
        action = Gtk.ToggleAction(name=name, label=label, tooltip=None, stock_id=None)
        action.connect("toggled", callback)
        self.actions.add_action(action)
        return action

    # ==========================================================
    # ACCIONES DEL MENÚ
    # ==========================================================

    def _launch_independent_tool(self, path):
        """Lanza una herramienta independiente sin depender del engine."""
        if self._destroyed or not os.path.isfile(path):
            return

        try:
            Gio.Subprocess.new([sys.executable, path], Gio.SubprocessFlags.NONE)

        except GLib.Error as error:
            self._report_error("No se pudo lanzar la herramienta " + path, error)


    def _on_install_manager(self, action):
        """Abre WMM Install Manager directamente desde el applet."""
        self._launch_independent_tool(install_manager_path)


    def _on_debug_log_viewer(self, action):
        """Abre WMM Debug Log Viewer directamente desde el applet."""
        self._launch_independent_tool(debug_log_viewer_path)

    def _on_settings(self, action):
        """Abre el panel principal de WMM."""
        self._send_action_to_engine({"action": "open_panel"})

    def _on_favorites_only_switch_changed(self, switch, pspec):
        """Activa Favorites Only y fuerza Slideshow ON cuando sea necesario."""
        if self._syncing_ui:
            return

        if switch.get_active() and not self.slideshow_switch.get_active():
            self._sync_slideshow_ui(True)

        self._update_timer_settings()

    def _on_sync_mode(self, action):
        """Actualiza modo SYNC/ASYNC y lo propaga al engine."""
        if self._syncing_ui:
            return
        self._update_sync_label()
        self._update_timer_settings()

    def _on_spanned(self, action):
        """Propaga el cambio de Spanned al engine."""
        if self._syncing_ui:
            return
        self._update_timer_settings()

    def _on_sync_library(self, action):
        """Solicita al engine la sincronización de la biblioteca."""
        self._send_action_to_engine({"action": "sync_library"})

    def _on_help(self, action):
        """Solicita al engine abrir la ayuda de WMM."""
        self._send_action_to_engine({"action": "open_help"})

    def _on_about(self, action):
        """Abre la información común de WMM mediante el engine."""
        self._send_action_to_engine({"action": "open_about"})

    # ==========================================================
    # SETTINGS
    # ==========================================================

    def _apply_settings(self, data):
        """Aplica el bloque global recibido del engine a los controles del menú."""
        if not isinstance(data, dict):
            return

        config = data.get("global", data)
        if not isinstance(config, dict):
            return

        self._current_max_interval = max(1, int(config.get("slideshow_max_interval", 60) or 60))
        self._current_interval = int(config.get("slideshow_interval", 15) or 15)
        self._current_interval = max(1, min(self._current_interval, self._current_max_interval))

        enabled = bool(config.get("slideshow_enabled", False))
        is_sync = config.get("slideshow_mode", "async") == "sync"
        favorites_only = bool(config.get("slideshow_bookmark", False))
        spanned = bool(config.get("spanned_enabled", False))

        self._syncing_ui = True
        self.sync_action.set_active(is_sync)
        if hasattr(self, "favorites_only_switch"):
            self.favorites_only_switch.set_active(favorites_only)
        self.spanned_action.set_active(spanned)
        self._syncing_ui = False

        self._sync_slideshow_ui(enabled)
        self._update_sync_label()
        self._update_interval_label()
        self.settings_action.set_label(_("Settings"))

    def _sync_slideshow_ui(self, enabled):
        """Sincroniza Switch, etiqueta y sensibilidad del slider de Slideshow."""
        if not hasattr(self, "slideshow_switch"):
            return

        syncing = self._syncing_ui
        self._syncing_ui = True
        self.slideshow_switch.set_active(enabled)
        self._syncing_ui = syncing

        self.slideshow_switch_label.set_text(_("Enabled") if enabled else _("Disabled"))
        self.slideshow_scale.set_sensitive(enabled)

    def _update_sync_label(self):
        """Actualiza la etiqueta de Displays según SYNC/ASYNC."""
        label = _("Displays") + ": " + (_("SYNC (All)") if self.sync_action.get_active() else _("ASYNC (One)"))
        self.sync_action.set_label(label)

    def _update_interval_label(self):
        """Actualiza rango, posición y texto del slider desde el estado actual."""
        if not hasattr(self, "slideshow_scale"):
            return

        self.slideshow_scale.set_range(1, self._current_max_interval)
        self.slideshow_scale.set_value(self._current_interval)
        self.slideshow_interval_label.set_text(str(self._current_interval) + " " + _("minutes"))

    def _update_timer_settings(self):
        """Envía al engine el estado conjunto de Slideshow/Displays/Spanned."""
        self._send_action_to_engine({
            "action": "update_timer_settings",
            "enabled": self.slideshow_switch.get_active(),
            "interval": self._current_interval,
            "mode": "sync" if self.sync_action.get_active() else "async",
            "slideshow_bookmark": self.favorites_only_switch.get_active(),
            "spanned_enabled": self.spanned_action.get_active(),
        })

    # ==========================================================
    # FAVORITOS
    # ==========================================================

    def _paint_inline_bookmarks(self):
        """Reconstruye la lista inline de favoritos desde la caché recibida."""
        if not hasattr(self, "favorites_inline_list"):
            return

        for child in self.favorites_inline_list.get_children():
            child.destroy()

        names = list(self._cached_bookmarks.keys())

        if not names:
            row = Gtk.ListBoxRow()
            row.set_selectable(False)
            row.set_activatable(False)
            row.get_style_context().add_class("wmm-favorite-row")

            label = Gtk.Label(label=_("No saved favorites"), xalign=0)
            label.set_sensitive(False)
            label.get_style_context().add_class("wmm-favorite-empty")

            row.add(label)
            self.favorites_inline_list.add(row)

        else:
            for name in names:
                row = Gtk.ListBoxRow()
                row.set_selectable(False)
                row.set_activatable(False)
                row.wmm_name = name
                row.get_style_context().add_class("wmm-favorite-row")

                row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
                row_box.get_style_context().add_class("wmm-favorite-row-box")

                name_button = Gtk.Button()
                name_button.set_relief(Gtk.ReliefStyle.NONE)
                name_button.set_can_focus(False)
                name_button.set_focus_on_click(False)
                name_button.set_hexpand(True)
                name_button.get_style_context().add_class("wmm-favorite-button")

                name_label = Gtk.Label(label=name, xalign=0)
                name_label.set_ellipsize(3)  # Pango.EllipsizeMode.END
                name_button.add(name_label)

                delete_button = Gtk.Button()
                delete_button.set_relief(Gtk.ReliefStyle.NONE)
                delete_button.set_can_focus(False)
                delete_button.set_focus_on_click(False)
                delete_button.get_style_context().add_class("wmm-favorite-button")

                delete_icon = Gtk.Image.new_from_icon_name("user-trash-symbolic", Gtk.IconSize.MENU)
                delete_button.add(delete_icon)

                # El Gtk.Menu recibe los eventos; guardamos las zonas para hit-testing.
                row.wmm_name_widget = name_button
                row.wmm_delete_widget = delete_button

                row_box.pack_start(name_button, True, True, 0)
                row_box.pack_end(delete_button, False, False, 0)
                row.add(row_box)
                self.favorites_inline_list.add(row)

        self.favorites_inline_list.show_all()
        self._update_favorites_scroll_height()

    def _update_favorites_scroll_height(self):
        """Limita Favorites a un número máximo de filas reales según el tema GTK.

        La altura se obtiene de las filas ya estilizadas, no de un valor fijo en
        píxeles. Así el menú conserva el mismo número de favoritos visibles aunque
        cambien tema, métricas o tipografía.
        """
        if not hasattr(self, "favorites_scrolled"):
            return

        rows = self.favorites_inline_list.get_children()
        if not rows:
            return

        target_height = 0

        for row in rows[:favorites_visible_rows]:
            _, natural_height = row.get_preferred_height()
            target_height += natural_height

        # Incluye padding/borde propios del ListBox que pueda aportar el tema.
        style = self.favorites_inline_list.get_style_context()
        state = style.get_state()
        padding = style.get_padding(state)
        border = style.get_border(state)

        target_height += padding.top + padding.bottom
        target_height += border.top + border.bottom
        target_height = max(1, target_height)

        # Liberar primero el máximo evita min > max al cambiar dinámicamente
        # entre listas de distinta altura.
        self.favorites_scrolled.set_max_content_height(-1)
        self.favorites_scrolled.set_min_content_height(target_height)
        self.favorites_scrolled.set_max_content_height(target_height)
        self.favorites_scrolled.queue_resize()
        self.favorites_scroll_item.queue_resize()

    def _load_favorite(self, name):
        """Carga un preset y refleja de inmediato el timer forzado a OFF."""
        self._sync_slideshow_ui(False)
        self._send_action_to_engine({"action": "load_bookmark", "name": name, "timer_force_off": True})

    def _confirm_delete_favorite(self, name):
        """Solicita confirmación antes de borrar un favorito."""
        dialog = Gtk.MessageDialog(
            transient_for=None,
            flags=Gtk.DialogFlags.MODAL,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=_("Delete") + ' "' + name + '"?'
        )
        dialog.set_title(_("Delete favorite"))

        response = dialog.run()
        dialog.destroy()

        if response == Gtk.ResponseType.YES:
            self._send_action_to_engine({"action": "delete_bookmark", "name": name})

    # ==========================================================
    # D-BUS: ACTIVACIÓN, CONSULTAS Y SEÑALES
    # ==========================================================

    def _start_engine(self, callback=None):
        """Activa org.maki.wmm por D-Bus y ejecuta callback cuando está disponible."""
        if self._destroyed:
            return

        self.bus.call(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            "StartServiceByName",
            GLib.Variant("(su)", ("org.maki.wmm", 0)),
            GLib.VariantType.new("(u)"),
            Gio.DBusCallFlags.NONE,
            5000,
            None,
            self._on_engine_started,
            callback
        )

    def _on_engine_started(self, connection, result, callback):
        """Finaliza StartServiceByName y continúa la operación pendiente."""
        try:
            connection.call_finish(result)
        except GLib.Error as error:
            self._report_error("No se pudo activar org.maki.wmm", error)
            return

        if callback and not self._destroyed:
            callback()

    def _send_action_to_engine(self, command):
        """Asegura el engine activo y envía una acción mediante send_command.py."""
        if self._destroyed:
            return
        self._start_engine(lambda: self._spawn_send_command(command))

    def _spawn_send_command(self, command):
        """Lanza send_command.py con el comando JSON ya preparado."""
        if self._destroyed or not os.path.isfile(send_command_path):
            return

        try:
            Gio.Subprocess.new(
                [sys.executable, send_command_path, json.dumps(command,
                ensure_ascii=False, separators=(",", ":"))], Gio.SubprocessFlags.NONE)
        except GLib.Error as error:
            self._report_error("No se pudo enviar el comando " + str(command.get("action", "unknown")), error)

    def _refresh_all(self):
        """Refresca settings, favoritos e icono de estado."""
        self._refresh_settings()
        self._refresh_bookmarks()
        self._update_icon_from_status()

    def _refresh_settings(self):
        """Solicita al engine el bloque de settings actual."""
        self._call_engine_query("GetSettings", self._on_settings_reply)

    def _refresh_bookmarks(self):
        """Solicita al engine la colección actual de favoritos."""
        self._call_engine_query("GetBookmarks", self._on_bookmarks_reply)

    def _call_engine_query(self, method, callback):
        """Ejecuta una consulta D-Bus de lectura sin autoarrancar el engine."""
        if self._destroyed:
            return

        self.bus.call(
            "org.maki.wmm",
            "/org/maki/wmm",
            "org.maki.wmm",
            method, None,
            GLib.VariantType.new("(s)"),
            Gio.DBusCallFlags.NO_AUTO_START,
            1500, None, callback, None
        )

    def _on_settings_reply(self, connection, result, user_data):
        """Decodifica GetSettings y sincroniza la interfaz."""
        try:
            reply = connection.call_finish(result)
            raw = reply.unpack()[0]
            self._apply_settings(json.loads(raw) if raw else {})
        except (GLib.Error, json.JSONDecodeError, TypeError, ValueError):
            pass

    def _on_bookmarks_reply(self, connection, result, user_data):
        """Decodifica GetBookmarks, actualiza caché y repinta la lista inline."""
        try:
            reply = connection.call_finish(result)
            raw = reply.unpack()[0]
            bookmarks = json.loads(raw) if raw else {}
            self._cached_bookmarks = bookmarks if isinstance(bookmarks, dict) else {}
            self._paint_inline_bookmarks()
        except (GLib.Error, json.JSONDecodeError, TypeError, ValueError):
            pass

    def _subscribe_engine_signals(self):
        """Suscribe el applet a SettingsChanged y BookmarksChanged del engine."""
        self._settings_signal_id = self.bus.signal_subscribe(
            "org.maki.wmm",
            "org.maki.wmm",
            "SettingsChanged",
            "/org/maki/wmm",
            None,
            Gio.DBusSignalFlags.NONE,
            self._on_settings_changed
        )
        self._bookmarks_signal_id = self.bus.signal_subscribe(
            "org.maki.wmm",
            "org.maki.wmm",
            "BookmarksChanged",
            "/org/maki/wmm",
            None,
            Gio.DBusSignalFlags.NONE,
            self._on_bookmarks_changed
        )

    def _on_settings_changed(self, connection, sender_name, object_path, interface_name, signal_name, parameters):
        """Aplica una actualización push de settings recibida por D-Bus."""
        if self._destroyed:
            return
        try:
            raw = parameters.unpack()[0]
            self._apply_settings(json.loads(raw) if raw else {})
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    def _on_bookmarks_changed(self, connection, sender_name, object_path, interface_name, signal_name, parameters):
        """Aplica una actualización push de favoritos recibida por D-Bus."""
        if self._destroyed:
            return
        try:
            raw = parameters.unpack()[0]
            bookmarks = json.loads(raw) if raw else {}
            self._cached_bookmarks = bookmarks if isinstance(bookmarks, dict) else {}
            self._paint_inline_bookmarks()
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    # ==========================================================
    # ESTADO BUSY DEL ENGINE
    # ==========================================================

    def _start_status_monitor(self):
        """Monitoriza cambios de engine_status.json sin polling."""
        try:
            os.makedirs(cache_dir, exist_ok=True)
            directory = Gio.File.new_for_path(cache_dir)
            self._status_monitor = directory.monitor_directory(Gio.FileMonitorFlags.NONE, None)
            self._status_monitor.connect("changed", self._on_status_changed)
            self._update_icon_from_status()
        except GLib.Error as error:
            self._report_error("No se pudo monitorizar engine_status.json", error)

    def _on_status_changed(self, monitor, file, other_file, event_type):
        """Reacciona solo a cambios relacionados con engine_status.json."""
        if self._destroyed:
            return

        basename = file.get_basename() if file else None
        other_basename = other_file.get_basename() if other_file else None

        if basename == "engine_status.json" or other_basename == "engine_status.json":
            self._update_icon_from_status()

    def _update_icon_from_status(self):
        """Carga asíncronamente el estado busy y ajusta el icono."""
        if self._destroyed:
            return

        status_file = Gio.File.new_for_path(status_path)
        if not status_file.query_exists(None):
            self._motor_busy = False
            self._ignore_next_busy = False
            self._set_icon("video-display")
            return

        status_file.load_contents_async(None, self._on_status_loaded, None)

    def _on_status_loaded(self, status_file, result, user_data):
        """Interpreta engine_status.json y refleja busy/idle en el icono."""
        if self._destroyed:
            return

        try:
            loaded = status_file.load_contents_finish(result)
            success, contents = loaded[0], loaded[1]
            if not success or not contents:
                return

            if isinstance(contents, bytes):
                contents = contents.decode("utf-8")

            status = json.loads(contents)
            busy = bool(status.get("busy", False))
            self._motor_busy = busy

            if busy:
                if not self._ignore_next_busy:
                    self._set_icon("view-refresh")
            else:
                self._ignore_next_busy = False
                self._set_icon("video-display")

        except (GLib.Error, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
            pass

    # ==========================================================
    # LIFECYCLE
    # ==========================================================

    def _find_panel_object_id(self):
        """Obtiene el object-id exacto de esta instancia desde MATE Panel."""
        preferences_path = self.applet.get_preferences_path() or ""
        prefix = "/org/mate/panel/objects/"
        suffix = "/prefs/"

        if not preferences_path.startswith(prefix) or not preferences_path.endswith(suffix):
            return None

        object_id = preferences_path[len(prefix):-len(suffix)]
        return object_id or None

    def _shutdown_if_removed(self):
        """Solicita Shutdown solo cuando MATE ha eliminado explícitamente el applet."""
        if self._panel_removal_shutdown or not self.panel_object_id:
            return

        if self.panel_object_id in self.panel_settings.get_strv("object-id-list"):
            return

        self._panel_removal_shutdown = True

        try:
            self.bus.call_sync(
                "org.maki.wmm",
                "/org/maki/wmm",
                "org.maki.wmm",
                "Shutdown",
                None, None,
                Gio.DBusCallFlags.NO_AUTO_START,
                1000, None
            )
        except GLib.Error:
            pass

    def _on_panel_objects_changed(self, settings, key):
        """Comprueba si el cambio de object-id-list corresponde a una eliminación."""
        self._shutdown_if_removed()

    def _on_destroy(self, widget):
        """Libera monitores/señales de la instancia al destruirse el applet."""
        global _active_wmm_instance

        self._shutdown_if_removed()
        self._destroyed = True

        if _active_wmm_instance is self:
            _active_wmm_instance = None

        if self._panel_objects_signal_id:
            self.panel_settings.disconnect(self._panel_objects_signal_id)
            self._panel_objects_signal_id = 0

        if self._status_monitor:
            try:
                self._status_monitor.cancel()
            except GLib.Error:
                pass
            self._status_monitor = None

        if self._settings_signal_id:
            self.bus.signal_unsubscribe(self._settings_signal_id)
            self._settings_signal_id = 0

        if self._bookmarks_signal_id:
            self.bus.signal_unsubscribe(self._bookmarks_signal_id)
            self._bookmarks_signal_id = 0

    @staticmethod
    def _report_error(message, error):
        """Escribe errores operativos del frontend MATE en stderr."""
        print(f"[WMM MATE] {message}: {error}", file=sys.stderr)

# ==========================================================
# FACTORÍA MATE
# ==========================================================

def _remove_duplicate_panel_object(applet):
    """Retira del panel una instancia WMM duplicada ya materializada."""
    preferences_path = applet.get_preferences_path() or ""

    prefix = "/org/mate/panel/objects/"
    suffix = "/prefs/"

    if not preferences_path.startswith(prefix) or not preferences_path.endswith(suffix):
        return GLib.SOURCE_REMOVE

    object_id = preferences_path[len(prefix):-len(suffix)]
    if not object_id:
        return GLib.SOURCE_REMOVE

    if (
        _active_wmm_instance is not None
        and object_id == _active_wmm_instance.panel_object_id
    ):
        print(
            f"[WMM MATE] Se evitó retirar la instancia activa '{object_id}'.",
            file=sys.stderr
        )
        return GLib.SOURCE_REMOVE

    panel_settings = getattr(applet, "_wmm_duplicate_panel_settings", None)
    if panel_settings is None:
        return GLib.SOURCE_REMOVE

    object_ids = list(panel_settings.get_strv("object-id-list"))

    if object_id not in object_ids:
        return GLib.SOURCE_REMOVE

    signal_id = getattr(applet, "_wmm_duplicate_signal_id", 0)

    if signal_id:
        panel_settings.disconnect(signal_id)
        applet._wmm_duplicate_signal_id = 0

    panel_settings.set_strv(
        "object-id-list",
        [
            current_id
            for current_id in object_ids
            if current_id != object_id
        ]
    )
    Gio.Settings.sync()

    applet._wmm_duplicate_panel_settings = None

    print(
        f"[WMM MATE] Instancia duplicada '{object_id}' retirada del panel.",
        file=sys.stderr
    )

    return GLib.SOURCE_REMOVE

def _on_duplicate_panel_objects_changed(settings, key, applet):
    """Reintenta la retirada cuando MATE publica cambios en object-id-list."""
    _remove_duplicate_panel_object(applet)

def applet_factory(applet, iid, user_data):
    """Crea una única instancia activa de WMM dentro de la factoría MATE."""
    global _active_wmm_instance

    if str(iid).rsplit("::", 1)[-1] != "WMMApplet":
        return False

    if _active_wmm_instance is not None:
        print(
            "[WMM MATE] Segunda instancia detectada; se retirará del panel.",
            file=sys.stderr
        )

        panel_settings = Gio.Settings.new("org.mate.panel")

        applet._wmm_duplicate_panel_settings = panel_settings
        applet._wmm_duplicate_signal_id = panel_settings.connect(
            "changed::object-id-list",
            _on_duplicate_panel_objects_changed,
            applet
        )

        GLib.idle_add(_remove_duplicate_panel_object, applet)

        applet.show_all()
        return True

    try:
        instance = WMMMateApplet(applet)
        applet._wmm_instance = instance
        applet.show_all()

        _active_wmm_instance = instance
        return True

    except Exception as error:
        print(f"[WMM MATE] Error creando el applet: {error}", file=sys.stderr)
        return False


if __name__ == "__main__":
    health_service = WMMMateAppletDBus()

    raise SystemExit(
        MatePanelApplet.Applet.factory_main(
            "WMMAppletFactory",
            True,
            MatePanelApplet.Applet.__gtype__,
            applet_factory, None))
