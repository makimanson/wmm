#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

"""
WMM - Wallpaper Multi-Monitor Manager

online_section.py – Vista Online del panel de control.
===================================================
Gestiona filtros, búsquedas asíncronas, miniaturas y selección Online.
No modifica Sources, el índice ni la caché de la biblioteca local.
La descarga de originales y su disponibilidad residen en online_wallpapers.py.
"""
import os
import json
import threading
import time
import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Gio
from online_wallpapers import (get_online_providers, get_online_provider_identity,
                               read_online_api_key, online_provider_available,
                               get_online_original_filename, search_wallpapers,
                               download_online_original, OnlineProviderRateLimited,
                               promote_online_preview_original, get_online_source_page)
from debug_logger import log_event
from i18n import _

class OnlineSection:
    """Vista Online independiente, alojada por ThumbnailsSection en su Stack."""

    # ==========================================================
    # RESPONSIBLE USE POLICY — EXTERNAL PROVIDERS
    # ==========================================================
    # The limit of five original images per batch is a deliberate
    # WMM design decision, not an official provider restriction.
    #
    # Online is intended for browsing wallpapers and manually
    # downloading small, user-selected batches. It is not designed
    # for mass downloading or automatically chaining download batches.
    #
    # Increasing or removing this limit without reconsidering its
    # impact on external providers goes against the principles of
    # responsible resource usage behind this integration.
    MAX_ONLINE_SELECTION = 5

    def __init__(self, handler):
        self.handler = handler

        # El Panel conserva la autoridad sobre la sincronización de Sources.
        self._library_sync_callback = None

        # Download sólo comunica traslados; la sesión pertenece a Monitors.
        self._online_promotion_callback = None

        # Descarta resultados tardíos de búsquedas ya sustituidas.
        self._online_request_id = 0
        self._online_visible_count = 0

        # Separador de la página nueva, pendiente de navegación.
        self._online_page_header = None

        # Página a la que pertenece la cuadrícula actualmente visible.
        self._online_displayed_page = 1

        # Cada pareja página/proveedor conserva su propia cuadrícula.
        # Evita mezclar resultados cuando intervienen varios proveedores.
        self._online_provider_flowboxes = {}

        # La selección pertenece exclusivamente a la búsqueda vigente.
        self._online_selected_items = {}

        # Botones de los resultados visibles, identificados por proveedor e ID.
        self._online_result_buttons = {}

        # Identidades de originales presentes en la biblioteca.
        # Se actualizan al iniciar cada búsqueda, sin persistencia propia.
        self._online_library_filenames = set()

        # Impide iniciar otra descarga mientras una anterior sigue activa.
        self._online_downloading = False

        # Procedencias confirmadas durante el lote de descarga.
        # Se persisten conjuntamente antes de sincronizar Sources.
        self._online_pending_origins = []

        # Parámetros de la última búsqueda iniciada.
        # Search sólo se habilita cuando cambia alguno de ellos.
        self._online_search_criteria = None

        # Página siguiente de la búsqueda vigente; None si no hay más.
        self._online_next_page = None

        # Evita reactivar Load More al restaurar filtros
        # mientras todavía se está cargando una página.
        self._online_loading_more = False

        # El formulario operativo conserva su construcción original.
        # La lectura responsable ocupa una vista independiente.
        self.widget = Gtk.Stack()
        self.widget.set_transition_type(Gtk.StackTransitionType.NONE)
        self.widget.add_named(self._build(), "browser")
        self.widget.add_named(self._build_responsible_use_view(), "responsible_use")
        self.prepare_open()

    def set_library_sync_callback(self, callback):
        """Conecta Online con el flujo de sincronización del Panel."""
        self._library_sync_callback = callback

    def set_online_promotion_callback(self, callback):
        """Comunica al editor los originales incorporados desde Download."""
        self._online_promotion_callback = callback

    # ==========================================================
    # VISTA ONLINE
    # ==========================================================
    def _create_online_flowbox(self):
        """Crea la cuadrícula independiente de una página Online."""
        flowbox = Gtk.FlowBox()
        flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
        flowbox.set_homogeneous(False)
        flowbox.set_row_spacing(2)
        flowbox.set_column_spacing(2)
        flowbox.set_max_children_per_line(128)
        flowbox.set_valign(Gtk.Align.START)
        flowbox.set_hexpand(True)
        return flowbox

    def _start_online_page(self, page):
        """Separa visualmente una página sin modificar las anteriores."""
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.set_hexpand(True)
        header.set_margin_top(6)

        for _index in range(2):
            separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
            separator.set_hexpand(True)
            separator.set_valign(Gtk.Align.CENTER)

            if _index == 0:
                header.pack_start(separator, True, True, 0)
            else:
                header.pack_end(separator, True, True, 0)

        page_label = Gtk.Label()
        page_label.set_markup(f"<b>{GLib.markup_escape_text(_('Page'))} {page}</b>")
        header.pack_start(page_label, False, False, 0)

        self.online_pages_box.pack_start(header, False, False, 0)
        self._online_page_header = header

        self.online_flowbox = self._create_online_flowbox()
        self.online_pages_box.pack_start(self.online_flowbox, False, False, 0)
        self._online_displayed_page = page

        header.show_all()
        self.online_flowbox.show_all()

    def _get_online_provider_flowbox(self, page, item):
        """Agrupa las miniaturas por proveedor dentro de cada página."""
        provider = item["provider"]
        key = (page, provider)

        flowbox = self._online_provider_flowboxes.get(key)
        if flowbox is not None:
            self.online_flowbox = flowbox
            return flowbox

        # _start_online_page() crea una cuadrícula provisional.
        # Sólo se sustituye cuando existe una miniatura válida.
        if (self.online_flowbox.get_parent() is self.online_pages_box
                and not self.online_flowbox.get_children()
                and self.online_flowbox not in self._online_provider_flowboxes.values()):
            self.online_pages_box.remove(self.online_flowbox)

        identity = get_online_provider_identity(provider) or {}
        name = identity.get("name") or item["provider_name"]
        website = identity.get("website")
        logo = identity.get("logo")

        # El banner ocupa toda la anchura, pero el logo conserva
        # sus proporciones originales y permanece alineado a la izquierda.
        banner = Gtk.Button()
        banner.get_style_context().add_class("text-button")
        banner.set_relief(Gtk.ReliefStyle.NONE)
        banner.set_hexpand(True)
        banner.set_halign(Gtk.Align.FILL)
        banner.set_margin_top(2)

        content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        content.set_hexpand(True)

        logo_widget = Gtk.Label(label=name)

        if logo:
            logo_path = os.path.join(
                self.handler.app_root, "wmm_platform", "shell", "logos", logo)

            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(logo_path, -1, 25, True)
                logo_widget = Gtk.Image.new_from_pixbuf(pixbuf)
            except (GLib.Error, OSError) as error:
                log_event(f"Logo Online no disponible ({provider}): {error}",
                    origin="ONLINE_SECT", level="WARN", reason="LIBRARY")

        content.pack_start(logo_widget, False, False, 8)
        banner.add(content)

        # El banner abre la página principal, no una imagen individual.
        if website:
            banner.set_tooltip_text(_("Visit") + " " + name)
            banner.connect("clicked", self._open_online_source_page, website)
        else:
            banner.set_sensitive(False)

        self.online_pages_box.pack_start(banner, False, False, 0)

        flowbox = self._create_online_flowbox()
        self.online_pages_box.pack_start(flowbox, False, False, 0)

        self._online_provider_flowboxes[key] = flowbox
        self.online_flowbox = flowbox

        banner.show_all()
        flowbox.show_all()
        return flowbox

    def _build(self):
        """Construye el buscador online y su galería independiente."""
        online_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        online_box.set_hexpand(True)
        online_box.set_vexpand(True)

        # El contenedor exterior ocupa la anchura disponible.
        # La fila interior conserva su anchura natural sin expandirse.
        filters_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        filters_container.set_hexpand(True)

        filters = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        filters.set_halign(Gtk.Align.START)
        filters.set_hexpand(False)
        filters.set_valign(Gtk.Align.START)
        filters_container.pack_start(filters, False, False, 0)

        # Texto de búsqueda con etiqueta superior.
        search_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        search_label = Gtk.Label(label=_("Search"))
        search_label.set_halign(Gtk.Align.START)
        search_box.pack_start(search_label, False, False, 0)

        self.online_search_entry = Gtk.Entry()

        # Reutilizar el borde de contraste de los campos Win32.
        self.online_search_entry.get_style_context().add_class("wmm-entry-border")

        self.online_search_entry.set_placeholder_text(_("Search wallpapers") + "...")
        self.online_search_entry.set_width_chars(22)
        search_box.pack_start(self.online_search_entry, False, False, 0)

        filters.pack_start(search_box, False, False, 0)

        # Cada proveedor aplica los filtros según las capacidades de su API.
        # El catálogo lo publica online_wallpapers, no la vista GTK.
        fields = (
            ("online_aspect_ratio", _("Aspect ratio"), (
                ("any", _("Any")),
                (None, ""),
                ("horizontal", _("Horizontal")),
                ("32:9", "32:9"),
                ("21:9", "21:9"),
                ("16:9", "16:9"),
                ("16:10", "16:10"),
                ("4:3", "4:3"),
                ("3:2", "3:2"),
                ("1:1", "1:1"),
                (None, ""),
                ("vertical", _("Vertical")),
                ("9:16", "9:16"),
                ("9:21", "9:21"),
            )),
            ("online_provider", _("Provider"), (
                ("any", _("Any")),
                *get_online_providers(),
            )),
        )

        for attribute, title, choices in fields:
            field_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

            field_label = Gtk.Label(label=title)
            field_label.set_halign(Gtk.Align.START)
            field_box.pack_start(field_label, False, False, 0)

            combo = Gtk.ComboBoxText()
            for key, label in choices:
                combo.append(key, label)

            if attribute == "online_aspect_ratio":
                # Las filas sin ID son separadores, no filtros seleccionables.
                combo.set_row_separator_func(
                    lambda model, treeiter, id_column:
                        model.get_value(treeiter, id_column) is None,
                    combo.get_id_column())

            combo.set_active(0)
            setattr(self, attribute, combo)
            field_box.pack_start(combo, False, False, 0)
            filters.pack_start(field_box, False, False, 0)

        # Botón y Enter comparten _search_online().
        # La consulta se ejecuta fuera del hilo GTK.
        self.online_search_button = Gtk.Button(label=_("Search"))
        self.online_search_button.set_valign(Gtk.Align.END)
        self.online_search_button.connect("clicked", self._search_online)
        self.online_search_entry.connect("activate", self._search_online)
        filters.pack_start(self.online_search_button, False, False, 0)
        self.online_search_entry.connect("changed", self._update_online_search_button)
        self.online_aspect_ratio.connect("changed", self._update_online_search_button)
        self.online_provider.connect("changed", self._update_online_search_button)

        # Las claves API tienen su acceso independiente, alineado
        # al extremo derecho sin alterar los filtros de búsqueda.
        self.online_api_keys_button = Gtk.Button(label=_("API Keys"))
        self.online_api_keys_button.set_valign(Gtk.Align.END)
        self.online_api_keys_button.connect("clicked", self._on_online_api_keys_clicked)
        filters_container.pack_end(self.online_api_keys_button, False, False, 0)

        online_box.pack_start(filters_container, False, False, 0)

        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        online_box.pack_start(separator, False, False, 0)

        # Galería destinada exclusivamente a miniaturas online.
        self.online_scrolled = Gtk.ScrolledWindow()
        self.online_scrolled.set_policy(
            Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        # El contenedor vertical organiza páginas y separadores.
        # Cada página conserva su propia cuadrícula de miniaturas.
        self.online_pages_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.online_pages_box.set_hexpand(True)
        self.online_pages_box.set_valign(Gtk.Align.START)

        self.online_flowbox = self._create_online_flowbox()
        self.online_pages_box.pack_start(self.online_flowbox, False, False, 0)

        placeholder = Gtk.Label(
            label=_("Online wallpaper results will appear here."))
        placeholder.set_margin_top(24)
        self.online_flowbox.add(placeholder)

        self.online_scrolled.add(self.online_pages_box)
        online_box.pack_start(self.online_scrolled, True, True, 0)

        # Progreso de transferencia de originales, independiente de Sources.
        self.online_download_progress = Gtk.ProgressBar()
        self.online_download_progress.set_show_text(True)
        self.online_download_progress.set_no_show_all(True)
        self.online_download_progress.set_size_request(100, -1)
        self.online_download_progress.set_valign(Gtk.Align.CENTER)
        self.online_download_progress.hide()

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        # Identificar el pie de Online para compartir el estilo de Sources.
        footer.get_style_context().add_class("wmm-online-footer")

        self.online_download_button = Gtk.Button(
            label=f"{_('Download')} (0/{self.MAX_ONLINE_SELECTION})")
        self.online_download_button.set_tooltip_text(_("Download selected images"))
        self.online_download_button.set_sensitive(False)
        self.online_download_button.connect("clicked", self._online_download_selected)
        footer.pack_end(self.online_download_button, False, False, 0)

        self.online_load_more_button = Gtk.Button(label=_("Load more") + "...")
        self.online_load_more_button.set_sensitive(False)
        self.online_load_more_button.connect("clicked", self._online_load_more)
        footer.pack_end(self.online_load_more_button, False, False, 0)

        self.online_download_status = Gtk.Label()
        self.online_download_status.set_halign(Gtk.Align.START)
        self.online_download_status.set_hexpand(False)
        footer.pack_start(self.online_download_status, False, False, 0)
        footer.pack_start(self.online_download_progress, False, False, 0)
        online_box.pack_start(footer, False, False, 0)

        return online_box

    # ========================================================================
    # API KEYS — Formulario de gestión de credenciales Online
    # ========================================================================
    # Diálogo independiente para vincular/desvincular archivos de claves API.
    # Solo persiste sus rutas; las credenciales se leen de los archivos.
    # ========================================================================
    def _on_online_api_key_action(self, button, dialog, provider, entry):
        """Vincula o desvincula el archivo personal de un proveedor."""

        def show_error(message):
            warning = Gtk.MessageDialog(
                transient_for=dialog,
                flags=Gtk.DialogFlags.MODAL,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.CLOSE,
                text=_("Could not update API key."))
            warning.format_secondary_text(str(message))
            warning.run()
            warning.destroy()

        settings = self.handler.load_json("settings")
        global_settings = settings.setdefault("global", {})
        paths = global_settings.setdefault("online_api_key_files", {})

        if not isinstance(paths, dict):
            show_error(_("Invalid API key configuration."))
            return

        if paths.get(provider):
            # Desvincular exclusivamente la ruta, sin modificar el archivo.
            paths.pop(provider)
            if not paths:
                global_settings.pop("online_api_key_files", None)

            self.handler.save_json("settings", settings)
            saved = self.handler.load_json("settings").get(
                "global", {}).get("online_api_key_files", {})

            if not isinstance(saved, dict) or provider in saved:
                show_error(_("Could not save settings.json."))
                return

            entry.set_text("")
            entry.set_placeholder_text("")
            entry.set_tooltip_text(None)
            button.get_child().set_visible_child_name("browse")
            return

        # El selector permite cualquier extensión: la validez pertenece
        # al contenido del archivo, no a su nombre.
        # GTK/GIO en Win32 puede emitir GLib-GIO-CRITICAL al seleccionar la raíz
        # de una unidad (C:\, D:\, etc.) porque el FileChooser consulta un GFileInfo
        # sin standard::type. El contenido del volumen, la navegación y la selección
        # de carpetas siguen siendo correctos; es ruido interno del toolkit y no debe
        # tratarse como un fallo funcional de WMM.
        chooser = Gtk.FileChooserDialog(
            title=_("Select API key file"),
            parent=dialog,
            action=Gtk.FileChooserAction.OPEN)

        # Identificar el selector para aplicar las correcciones
        # visuales del modo oscuro de Windows.
        chooser.get_style_context().add_class("wmm-api-key-file-chooser")

        # En Windows las unidades ya aparecen en la barra lateral.
        # Ocultar "Otras ubicaciones" evita las acciones de montaje
        # de GTK y conserva la navegación normal por carpetas.
        if os.name == "nt":
            def hide_other_locations(container):
                if isinstance(container, Gtk.PlacesSidebar):
                    container.set_show_other_locations(False)
                    return

                if isinstance(container, Gtk.Container):
                    for child in container.get_children():
                        hide_other_locations(child)

            hide_other_locations(chooser)
        chooser.add_buttons(
            _("Cancel"), Gtk.ResponseType.CANCEL,
            _("Open"), Gtk.ResponseType.OK)

        response = chooser.run()
        path = chooser.get_filename() if response == Gtk.ResponseType.OK else None
        chooser.destroy()

        if not path:
            return

        # Validar antes de persistir: una selección incorrecta no altera
        # la configuración ni reemplaza la credencial anterior.
        try:
            key = read_online_api_key(path)
        except (RuntimeError, ValueError, TypeError) as error:
            show_error(error)
            return

        paths[provider] = path
        self.handler.save_json("settings", settings)

        # ConfigHandler registra los errores de escritura sin propagarlos;
        # comprobamos la persistencia antes de cambiar el estado visual.
        saved = self.handler.load_json("settings").get(
            "global", {}).get("online_api_key_files", {})

        if not isinstance(saved, dict) or saved.get(provider) != path:
            show_error(_("Could not save settings.json."))
            return

        entry.set_text(key)
        entry.set_placeholder_text("")
        entry.set_tooltip_text(None)
        button.get_child().set_visible_child_name("unlink")

    def _on_online_api_keys_clicked(self, button):
        """Gestiona las claves personales en un diálogo independiente de Online."""
        dialog = Gtk.Dialog(
            title=_("API Keys"),
            transient_for=self.widget.get_toplevel(),
            flags=Gtk.DialogFlags.MODAL)
        dialog.get_style_context().add_class("wmm-api-keys-dialog")
        dialog.add_button(_("Close"), Gtk.ResponseType.CLOSE)
        dialog.set_default_size(-1, -1)
        dialog.set_resizable(False)

        # Mantener la identidad visual del Panel.
        icon_path = self.handler._platform.icon_path
        if os.path.isfile(icon_path):
            dialog.set_icon_from_file(icon_path)

        # El pie permanece separado del contenido desplazable.
        action_area = dialog.get_action_area()
        action_area.set_spacing(12)
        action_area.set_margin_start(12)
        action_area.set_margin_end(12)
        action_area.set_margin_bottom(12)
        action_area.set_margin_top(4)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_propagate_natural_height(True)
        dialog.get_content_area().pack_start(scroll, True, True, 0)

        grid = Gtk.Grid(column_spacing=12, row_spacing=12)
        grid.set_hexpand(True)
        grid.set_margin_top(12)
        grid.set_margin_bottom(12)
        grid.set_margin_start(12)
        grid.set_margin_end(12)
        scroll.add(grid)

        # El estado visual pertenece al Panel, no a las credenciales.
        settings = self.handler.load_json("settings")
        tip_expanded = settings.get("panel", {}).get("online_api_tip_expanded", True)

        def fit_dialog():
            """Ajusta la altura al contenido, sin invadir el área útil."""
            native = dialog.get_window()
            if native is None:
                return False

            width, current_height = dialog.get_size()
            _, natural_height = dialog.get_preferred_height_for_width(width)

            monitor = dialog.get_display().get_monitor_at_window(native)
            if monitor:
                natural_height = min(
                    natural_height, max(1, monitor.get_workarea().height - 48))

            if natural_height != current_height:
                dialog.resize(width, natural_height)

            return False

        # TIP conserva el patrón visual de los desplegables de Options.
        notice_text = self._read_online_document("API_KEYS.txt")
        if notice_text:
            header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)

            tip_toggle = Gtk.EventBox()
            tip_toggle.set_events(Gdk.EventMask.BUTTON_PRESS_MASK)

            tip_title = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            tip_arrow = Gtk.Image.new_from_icon_name(
                "media-playback-start-symbolic", Gtk.IconSize.BUTTON)
            tip_arrow.set_pixel_size(10)
            tip_arrow.set_valign(Gtk.Align.CENTER)

            if tip_expanded:
                tip_arrow.get_style_context().add_class("wmm-playback-down")

            tip_title.pack_start(tip_arrow, False, False, 0)

            tip_label = Gtk.Label(label="TIP", halign=Gtk.Align.START)
            tip_label.get_style_context().add_class("wmm-label-bold")
            tip_title.pack_start(tip_label, False, False, 0)

            tip_toggle.add(tip_title)
            header.pack_start(tip_toggle, False, False, 0)

            notice = Gtk.Label(label=notice_text)
            notice.set_xalign(0)
            notice.set_yalign(0)
            notice.set_line_wrap(True)
            notice.set_max_width_chars(56)
            notice.set_selectable(True)

            # show_all() no debe desplegar un TIP guardado como cerrado.
            notice.set_no_show_all(True)
            header.pack_start(notice, False, False, 0)

            # El separador permanece visible en ambos estados.
            header.pack_start(
                Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL),
                False, False, 0)

            grid.attach(header, 0, 0, 1, 1)

            def on_tip_toggle(widget, event):
                expanded = not notice.get_visible()
                notice.set_visible(expanded)

                arrow_style = tip_arrow.get_style_context()
                if expanded:
                    arrow_style.add_class("wmm-playback-down")
                else:
                    arrow_style.remove_class("wmm-playback-down")

                # Recargar antes de guardar evita sobrescribir otros ajustes.
                current = self.handler.load_json("settings")
                current.setdefault("panel", {})["online_api_tip_expanded"] = expanded
                self.handler.save_json("settings", current)

                grid.queue_resize()
                GLib.idle_add(fit_dialog)
                return True

            tip_toggle.connect("button-press-event", on_tip_toggle)

        # Cabecera permanente de la lista de proveedores.
        providers_title = Gtk.Label(label=_("Providers"), halign=Gtk.Align.START)
        providers_title.get_style_context().add_class("wmm-label-bold")
        grid.attach(providers_title, 0, 1, 1, 1)

        # Las rutas son persistentes; las claves se leen al abrir.
        api_key_files = settings.get("global", {}).get("online_api_key_files", {})
        if not isinstance(api_key_files, dict):
            api_key_files = {}

        # Cada proveedor registrado aporta su identidad y su enlace web.
        width_rows = []
        for index, (provider, provider_name) in enumerate(get_online_providers()):
            identity = get_online_provider_identity(provider) or {}
            name = identity.get("name") or provider_name
            website = identity.get("website")
            logo = identity.get("logo")

            # Reutiliza el hover común de los banners Online en Windows.
            # El botón conserva su anchura natural, alineado a la izquierda.
            provider_button = Gtk.Button()
            provider_button.get_style_context().add_class("wmm-online-source-link")
            provider_button.set_relief(Gtk.ReliefStyle.NONE)
            provider_button.set_halign(Gtk.Align.START)
            provider_button.set_tooltip_text(_("Visit") + " " + name)

            logo_widget = Gtk.Label(label=name)
            if logo:
                logo_path = os.path.join(
                    self.handler.app_root, "wmm_platform", "shell", "logos", logo)
                try:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                        logo_path, -1, 15, True)
                    logo_widget = Gtk.Image.new_from_pixbuf(pixbuf)
                except (GLib.Error, OSError) as error:
                    log_event(f"Logo Online no disponible ({provider}): {error}",
                        origin="ONLINE_SECT", level="WARN", reason="LIBRARY")

            provider_button.add(logo_widget)
            if website:
                provider_button.connect(
                    "clicked", self._open_online_source_page, website)
            else:
                provider_button.set_sensitive(False)

            # La clave será visible, pero nunca editable directamente.
            key_entry = Gtk.Entry()
            key_entry.set_editable(False)
            key_entry.set_hexpand(False)
            # Claves de 32 caracteres; pequeño margen para mayúsculas.
            key_entry.set_width_chars(33)
            key_entry.get_style_context().add_class("wmm-entry-border")

            # La vinculación depende de la ruta, no del resultado de lectura.
            linked_path = api_key_files.get(provider)

            if linked_path:
                try:
                    key_entry.set_text(read_online_api_key(linked_path))
                except (RuntimeError, ValueError, TypeError) as error:
                    key_entry.set_placeholder_text(_("Could not read API key"))
                    key_entry.set_tooltip_text(str(error))

            # Mantener estable la anchura del botón al cambiar de acción.
            # Gtk.Stack reserva el texto más largo en el idioma activo.
            action_stack = Gtk.Stack()
            action_stack.set_hhomogeneous(True)
            action_stack.add_named(Gtk.Label(label=_("Browse")), "browse")
            action_stack.add_named(Gtk.Label(label=_("Unlink")), "unlink")
            action_stack.show_all()
            action_stack.set_visible_child_name("unlink" if linked_path else "browse")

            browse_button = Gtk.Button()
            # Gtk.Stack sustituye al Gtk.Label nativo: restaurar su clase CSS.
            browse_button.get_style_context().add_class("text-button")
            browse_button.add(action_stack)
            browse_button.connect("clicked", self._on_online_api_key_action, dialog, provider, key_entry)

            # Identidad del proveedor a la izquierda; credenciales y
            # acción agrupadas en el extremo derecho de cada fila.
            controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            controls.pack_start(key_entry, False, False, 0)
            controls.pack_start(browse_button, False, False, 0)

            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            row.set_hexpand(True)
            row.pack_start(provider_button, False, False, 0)
            row.pack_end(controls, False, False, 0)
            grid.attach(row, 0, index + 2, 1, 1)

            width_rows.append((
                provider, row, controls, key_entry,
                provider_button, browse_button))

        dialog.show_all()

        # Restaurar el último estado antes de calcular la altura inicial.
        if notice_text:
            notice.set_visible(tip_expanded)

        GLib.idle_add(fit_dialog)

        # Diagnóstico temporal: anchuras mínima, natural y asignada.
        # No se lee ni registra el contenido de ninguna clave API.
        def report_api_width():
            def widths(widget):
                minimum, natural = widget.get_preferred_width()
                allocated = widget.get_allocated_width()
                return f"{minimum}/{natural}/{allocated}"

            details = []
            for provider, row, controls, entry, identity, button in width_rows:
                details.append(
                    f"{provider}: row={widths(row)}, "
                    f"controls={widths(controls)}, "
                    f"entry={widths(entry)}, "
                    f"identity={widths(identity)}, "
                    f"button={widths(button)}")

            log_event(
                f"[API WIDTH] window={dialog.get_size()} "
                f"dialog={widths(dialog)} "
                f"scroll={widths(scroll)} "
                f"grid={widths(grid)} | " + " | ".join(details),
                origin="ONLINE_SECT", level="INFO", reason="SETTINGS")
            return False

        GLib.idle_add(report_api_width)

        try:
            dialog.run()
        finally:
            dialog.destroy()

    # ==========================================================
    # LECTURA Y ACEPTACIÓN DEL USO RESPONSABLE
    # ==========================================================
    def _read_online_document(self, filename, include_copyright=False):
        """Lee un documento WMM trilingüe utilizando el idioma de sesión."""
        path = os.path.join(self.handler.app_root, "licenses", "WMM", filename)

        try:
            with open(path, "r", encoding="utf-8-sig") as document:
                lines = document.read().splitlines(keepends=True)
        except (OSError, UnicodeError) as error:
            log_event(f"No se pudo leer {filename}: {error}",
                origin="ONLINE", level="ERROR", reason="SETTINGS")
            return None

        # Los marcadores son claves explícitas, no títulos interpretados.
        markers = ("[English]", "[Català]", "[Castellano]")
        positions = {line.rstrip("\r\n"): index for index, line in enumerate(lines)
                     if line.rstrip("\r\n") in markers}

        if (len(positions) != 3 or
                not positions[markers[0]] < positions[markers[1]] < positions[markers[2]]):
            log_event(f"Marcadores lingüísticos inválidos en {filename}",
                origin="ONLINE", level="ERROR", reason="SETTINGS")
            return None

        # Mismo criterio de idioma que Docs Viewer, incluido Windows.
        raw = (os.environ.get("LANGUAGE") or os.environ.get("LC_ALL")
               or os.environ.get("LC_MESSAGES") or os.environ.get("LANG") or "en")
        language = raw.split(":", 1)[0].split(".", 1)[0].replace("-", "_").split("_", 1)[0].lower()
        marker = {"ca": markers[1], "es": markers[2]}.get(language, markers[0])

        # Responsible Use conserva su firma; API Keys sólo contiene información.
        # La firma delimita el documento, aunque no deba mostrarse.
        footer_index = next((index for index, line in enumerate(lines)
                             if line.rstrip("\r\n") == "[Copyright]"), None)

        if footer_index is None or footer_index <= positions["[Castellano]"]:
            log_event(f"Firma común inválida en {filename}",
                origin="ONLINE", level="ERROR", reason="SETTINGS")
            return None

        start = positions[marker] + 1
        end = next((positions[m] for m in markers
                    if positions[m] > positions[marker]), footer_index)

        text = "".join(lines[start:end]).strip()
        footer = "".join(lines[footer_index + 1:]).strip() if include_copyright else ""

        if not text or (include_copyright and not footer):
            log_event(f"Contenido incompleto en {filename}",
                origin="ONLINE", level="ERROR", reason="SETTINGS")
            return None

        return f"{text}\n\n{footer}" if include_copyright else text

    def _read_responsible_use(self):
        """Conserva el contrato de lectura y firma de Responsible Use."""
        return self._read_online_document(
            "RESPONSIBLE_USE.txt", include_copyright=True)

    def _build_responsible_use_view(self):
        """Documento y aceptación dentro de un único desplazamiento."""
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        # Barra convencional: reservar su espacio para facilitar
        # la interacción directa, sin superponerla al documento.
        scrolled.set_overlay_scrolling(False)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_border_width(12)

        # Espacio adicional al pie de la pantalla de aceptación.
        content.set_margin_bottom(12)

        text = self._read_responsible_use()
        self._online_document_ready = text is not None

        document = Gtk.Label(
            label=text or _("Responsible use document unavailable."))
        document.set_xalign(0)
        document.set_yalign(0)
        document.set_line_wrap(True)
        document.set_max_width_chars(90)
        document.set_selectable(True)
        content.pack_start(document, False, False, 0)

        # La aceptación precede a la preferencia de ocultar el documento.
        self.online_understood = Gtk.CheckButton(
            label=_("I have read and understood this document"))
        self.online_understood.set_sensitive(self._online_document_ready)
        content.pack_start(self.online_understood, False, False, 0)

        self.online_dont_show = Gtk.CheckButton(label=_("Do not show again"))
        self.online_dont_show.set_sensitive(self._online_document_ready)
        content.pack_start(self.online_dont_show, False, False, 0)

        # Aviso contextual a la izquierda y confirmación a la derecha.
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        path = _("About") + " > " + _("License") + " > WMM"
        self.online_notice = Gtk.Label()
        self.online_notice.set_markup(
            GLib.markup_escape_text(_("You can consult this document at any time from:"))
            + "\n<b>" + GLib.markup_escape_text(path) + "</b>")
        self.online_notice.set_xalign(0)
        self.online_notice.set_line_wrap(True)
        self.online_notice.set_hexpand(True)
        self.online_notice.set_no_show_all(True)
        actions.pack_start(self.online_notice, True, True, 0)

        self.online_dont_show.connect("toggled", lambda check:
            self.online_notice.set_visible(check.get_active()))

        self.online_accept = Gtk.Button(label=_("Accept"))
        self.online_accept.set_sensitive(False)
        self.online_accept.set_valign(Gtk.Align.CENTER)
        self.online_accept.connect("clicked", self._accept_responsible_use)
        actions.pack_end(self.online_accept, False, False, 0)

        self.online_understood.connect("toggled", lambda check:
            self.online_accept.set_sensitive(check.get_active()))

        content.pack_start(actions, False, False, 0)

        # Los controles no permanecen fijos: están tras el documento.
        scrolled.add_with_viewport(content)

        # Conservar la escala del Panel frente a los 9 pt nativos de GTK win32.
        scrolled.get_child().get_style_context().add_class("wmm-online-terms-viewport")

        self.online_terms_scrolled = scrolled
        return scrolled

    def prepare_open(self):
        """Omitir la lectura solo cuando ambas preferencias lo autorizan."""
        settings = self.handler.load_json("settings").get("global", {})

        if (settings.get("online_responsible_use_accepted") and
                settings.get("online_responsible_use_dont_show_again")):
            self.widget.set_visible_child_name("browser")
            return

        # Cada apertura requiere una nueva confirmación si no se omitió.
        # Reflejar la aceptación ya registrada, aunque el aviso reaparezca.
        self.online_understood.set_active(
            bool(settings.get("online_responsible_use_accepted", False)))
        self.online_dont_show.set_active(False)
        self.online_terms_scrolled.get_vadjustment().set_value(0)
        self.widget.set_visible_child_name("responsible_use")

    def _accept_responsible_use(self, button):
        """Persistir las preferencias únicamente tras la aceptación expresa."""
        if not self._online_document_ready or not self.online_understood.get_active():
            return

        settings = self.handler.load_json("settings")
        global_settings = settings.setdefault("global", {})
        global_settings["online_responsible_use_accepted"] = True
        global_settings["online_responsible_use_dont_show_again"] = self.online_dont_show.get_active()

        self.handler.save_json("settings", settings)
        self.widget.set_visible_child_name("browser")

    def _online_show_message(self, message):
        """Sustituye el contenido de la galería por un mensaje de estado."""

        # Los resultados anteriores dejan de pertenecer a la vista activa.
        self._online_selected_items.clear()
        self._online_result_buttons.clear()
        self._update_online_download_button()

        if not self._online_downloading:
            self.online_download_status.set_text("")
            self.online_download_progress.hide()

        self._online_page_header = None

        # Las agrupaciones anteriores no pertenecen a la nueva búsqueda.
        self._online_provider_flowboxes.clear()

        # Una búsqueda nueva retira todas las páginas anteriores.
        for child in self.online_pages_box.get_children():
            self.online_pages_box.remove(child)

        self.online_flowbox = self._create_online_flowbox()
        self.online_pages_box.pack_start(self.online_flowbox, False, False, 0)
        self._online_displayed_page = 1

        label = Gtk.Label(label=message)
        label.set_margin_top(24)
        self.online_flowbox.add(label)
        self.online_pages_box.show_all()

    def _get_online_search_criteria(self):
        """Devuelve los tres valores que identifican una búsqueda."""
        return (self.online_search_entry.get_text().strip(),
                self.online_aspect_ratio.get_active_id(),
                self.online_provider.get_active_id())

    def _update_online_search_button(self, widget=None):
        """Sólo permitir buscar cuando los parámetros sean diferentes."""

        # Ambos botones responden a una única comparación:
        # Search requiere cambios; Load More requiere coincidencia.
        same_criteria = (self._online_search_criteria is not None
            and self._get_online_search_criteria() == self._online_search_criteria)

        self.online_search_button.set_sensitive(not same_criteria)
        self.online_load_more_button.set_sensitive(
            same_criteria and self._online_next_page is not None
            and not self._online_loading_more)

    def _search_online(self, widget):
        """Inicia una búsqueda online sin bloquear el hilo GTK."""
        criteria = self._get_online_search_criteria()
        if criteria == self._online_search_criteria:
            return

        self._online_request_id += 1
        request_id = self._online_request_id

        # Los parámetros quedan fijados al iniciar la búsqueda.
        # Una pulsación de Enter tampoco debe repetirla.
        self._online_search_criteria = criteria
        self._update_online_search_button()

        # Una búsqueda nueva sustituye la galería y su paginación.
        self._online_next_page = None
        self._online_loading_more = False
        self.online_load_more_button.set_sensitive(False)

        provider = self.online_provider.get_active_id()

        if not online_provider_available(provider):
            self._online_show_message(_("Provider not yet available."))
            return

        text = self.online_search_entry.get_text().strip()

        # El selector reúne orientación general y proporciones concretas.
        # La búsqueda mantiene el contrato independiente de ambos filtros.
        selection = self.online_aspect_ratio.get_active_id()
        if selection in ("any", "horizontal", "vertical"):
            orientation, aspect = selection, "any"
        else:
            orientation, aspect = "any", selection

        # Consultar una sola vez las imágenes conocidas por WMM.
        # Descartar rutas obsoletas que ya no existen físicamente.
        h_list, v_list = self.handler.get_flat_lists()
        self._online_library_filenames = {
            os.path.normcase(os.path.basename(entry[0]))
            for images in (h_list, v_list) for entry in images
            if os.path.isfile(entry[0])
        }

        self._online_visible_count = 0
        self._online_show_message(_("Searching wallpapers") + "...")

        threading.Thread(
            target=self._online_search_worker,
            args=(request_id, provider, text, orientation, aspect),
            name="WMM-OnlineSearch",
            daemon=True
        ).start()

    def _online_load_more(self, button):
        """Añade una página conservando los resultados de la búsqueda vigente."""
        if self._online_search_criteria is None or self._online_next_page is None:
            return
        if not button.get_sensitive():
            return

        # No leer los campos actuales: pueden haberse modificado sin buscar.
        text, selection, provider = self._online_search_criteria
        if selection in ("any", "horizontal", "vertical"):
            orientation, aspect = selection, "any"
        else:
            orientation, aspect = "any", selection

        # Any conserva cursores independientes, pero una sola página visual.
        provider_pages = (self._online_next_page
            if isinstance(self._online_next_page, dict) else None)
        page = (self._online_displayed_page + 1
            if provider_pages is not None else self._online_next_page)

        self._online_loading_more = True
        button.set_sensitive(False)

        threading.Thread(
            target=self._online_search_worker,
            args=(self._online_request_id, provider, text, orientation, aspect,
                page, provider_pages),
            name="WMM-OnlineMore",
            daemon=True
        ).start()

    def _online_search_worker(self, request_id, provider,
        text, orientation, aspect, page=1, provider_pages=None):
        """Comunica los resultados preparados al hilo GTK sin tratar proveedores."""

        def on_result(item, path):
            GLib.idle_add(self._online_add_result, request_id, page, item, path)

        def on_error(provider_name, error, log_only):
            GLib.idle_add(self._online_search_error,
                request_id, provider_name, error, log_only)

        # La configuración conserva rutas, nunca el contenido de las claves.
        key_files = self.handler.load_json("settings").get(
            "global", {}).get("online_api_key_files", {})

        # La vista conserva la autoridad sobre la vigencia de su petición.
        # La consulta, Any y la caché de miniaturas pertenecen al servicio.
        summary = search_wallpapers(text, orientation, aspect, provider,
            self.handler.cache_dir, on_result, on_error,
            is_cancelled=lambda: request_id != self._online_request_id,
            page=page, api_key_files=key_files, provider_pages=provider_pages)

        if summary is not None:
            GLib.idle_add(self._online_search_finished, request_id, *summary)
        elif page > 1:
            GLib.idle_add(self._online_load_more_failed, request_id)

    def _online_load_more_failed(self, request_id):
        """Permite reintentar una página fallida sin perder las anteriores."""
        if request_id == self._online_request_id:
            self._online_loading_more = False
            self._update_online_search_button()
        return False

    def _online_mark_downloaded(self, button):
        """Representa un original descargado y bloquea su selección."""
        button.set_active(False)
        button.set_image(Gtk.Image.new_from_icon_name(
            "object-select-symbolic", Gtk.IconSize.LARGE_TOOLBAR))
        button.get_accessible().set_name(_("Downloaded"))
        button.set_tooltip_text(_("Downloaded"))
        button.get_style_context().add_class("wmm-online-downloaded")
        button.set_sensitive(False)

    def _update_online_download_button(self):
        """Mantiene el contador y la disponibilidad de Download."""
        count = len(self._online_selected_items)
        self.online_download_button.set_label(
            f"{_('Download')} ({count}/{self.MAX_ONLINE_SELECTION})")
        self.online_download_button.set_sensitive(
            count > 0 and not self._online_downloading)

    def _online_selection_changed(self, button):
        """Limita el lote manual y actualiza su contador."""
        item = button._wmm_online_item
        key = (item["provider"], item["id"])

        if button.get_active():
            if len(self._online_selected_items) >= self.MAX_ONLINE_SELECTION:

                # Rechazar únicamente la nueva selección, sin alterar las cinco.
                button.set_active(False)
                warning = _("Download the 5 selected images before selecting more.")
                button.set_tooltip_text(warning)
                self.online_download_status.set_text(warning)
                return

            self._online_selected_items[key] = item
            log_event(f"Original Online seleccionado: {item['provider']}/{item['id']} "
                f"({len(self._online_selected_items)}/{self.MAX_ONLINE_SELECTION})",
                origin="ONLINE_SECT", level="INFO", reason="LIBRARY")
        else:
            removed = self._online_selected_items.pop(key, None)
            if removed is not None:
                log_event(f"Original Online desmarcado: {item['provider']}/{item['id']} "
                    f"({len(self._online_selected_items)}/{self.MAX_ONLINE_SELECTION})",
                    origin="ONLINE_SECT", level="INFO", reason="LIBRARY")

        button.set_tooltip_text(_("Selected") if button.get_active() else _("Select"))
        if not self._online_downloading:
            self.online_download_status.set_text("")

        self._update_online_download_button()

    def _online_download_selected(self, button):
        """Descarga la selección en el directorio configurado para Online."""
        if self._online_downloading or not self._online_selected_items:
            return

        destination = self.handler.get_online_source_path()

        # Sources es la única autoridad sobre la ubicación de descarga.
        if not destination or not os.path.isdir(destination):
            self.online_download_status.set_text(
                _("Configure a valid Online folder in Sources."))
            return

        # La selección queda fijada al iniciar la operación.
        items = tuple(self._online_selected_items.values())
        self._online_pending_origins.clear()
        self._online_downloading = True
        self._update_online_download_button()
        self.online_download_status.set_text(_("Downloading selected images") + "...")
        self.online_download_progress.set_fraction(0.0)
        self.online_download_progress.set_text("0%")
        self.online_download_progress.show()

        threading.Thread(
            target=self._online_download_worker,
            args=(items, destination),
            name="WMM-OnlineDownload",
            daemon=True
        ).start()

    def _online_download_worker(self, items, destination):
        """Descarga un lote manual con pausa y respeto a las restricciones."""
        successes = 0
        last_error = None

        for index, item in enumerate(items, 1):
            GLib.idle_add(self._online_download_file_started, index, len(items))

            def on_progress(received, expected):
                GLib.idle_add(self._online_update_download_progress,
                    index, len(items), received, expected)

            try:
                filename = get_online_original_filename(item)
                if not filename:
                    raise ValueError("El proveedor no dispone de un original identificable")

                # Una vista previa anterior también puede haber dejado el
                # original en /temp: incorporarlo antes de acudir al proveedor.
                source = os.path.join(self.handler.cache_dir, "online", "temp", filename)

                if os.path.isfile(source) and os.path.getsize(source) > 0:
                    target = promote_online_preview_original(
                        source, self.handler.cache_dir, destination)

                    # Distinguir la reutilización local de una descarga de red.
                    log_event(f"Download desde /temp: {item['provider']}/{item['id']} -> {target}",
                        origin="ONLINE_SECT", level="INFO", reason="LIBRARY")
                else:
                    source = None
                    target = download_online_original(item, destination, on_progress=on_progress)

                successes += 1
                GLib.idle_add(self._online_download_file_completed,
                    index, len(items), item, target, source)

            except OnlineProviderRateLimited as error:
                last_error = f"{item['id']}: {error}"

                # Un 429 interrumpe el lote; no intentar los originales restantes.
                break

            except Exception as error:
                last_error = f"{item['id']}: {error}"

            # ======================================================
            # RESPONSIBLE DOWNLOADING — EXTERNAL PROVIDERS
            # ======================================================
            # The one-second delay between downloads is intentional.
            # It applies after each download attempt, except the last.
            #
            # Its purpose is to avoid immediate consecutive requests
            # to external servers, regardless of transfer speed.
            #
            # This delay is not imposed by the provider. It is a
            # voluntary measure adopted by WMM out of respect for
            # the resources and infrastructure of external services.
            #
            # Reducing or removing this delay without reassessing
            # its impact contradicts WMM's responsible use policy.
            #
            # The delay runs exclusively in the download worker
            # and never blocks the GTK interface.
            if index < len(items):
                time.sleep(1)

        GLib.idle_add(
            self._online_download_finished, successes, len(items), last_error)

    def _online_download_file_started(self, index, total):
        """Prepara el indicador para la siguiente imagen del lote."""
        self.online_download_progress.set_fraction(0.0)
        self.online_download_progress.set_text(f"{index}/{total} · 0%")
        self.online_download_status.set_text(f"{_('Downloading')}: {index}/{total}")
        return False

    def _online_update_download_progress(self, index, total, received, expected):
        """Refleja los bytes transferidos sin intervenir en el hilo de descarga."""
        if expected is not None and expected > 0:
            fraction = min(received / expected, 1.0)
            self.online_download_progress.set_fraction(fraction)
            self.online_download_progress.set_text(f"{index}/{total} · {fraction:.0%}")
        else:
            # Sin Content-Length no existe un porcentaje verificable.
            # Cada bloque recibido impulsa la barra sin temporizadores.
            self.online_download_progress.pulse()
            self.online_download_progress.set_text(
                f"{index}/{total} · {received / 1048576:.1f} MiB")

        return False

    def _online_download_file_completed(self, index, total, item, target, source):
        """Marca el original disponible y lo retira de las descargas pendientes."""
        # El traslado ya terminó; sólo GTK puede actualizar el editor.
        if source and self._online_promotion_callback:
            try:
                self._online_promotion_callback(source, target)
            except Exception as error:
                log_event(f"Error al actualizar ruta Online: {error}",
                    origin="ONLINE_SECT", level="ERROR", reason="LIBRARY")

        key = (item["provider"], item["id"])

        # Una descarga correcta ya no pertenece a la selección pendiente.
        self._online_selected_items.pop(key, None)

        # Conservar la procedencia confirmada hasta el cierre del lote.
        # No escribir todavía: Download persiste todas las altas juntas.
        page_url = get_online_source_page(item)
        if page_url:
            self._online_pending_origins.append((target, item, page_url))

        self._update_online_download_button()

        # Reconocer también el original mientras Sources completa su Sync.
        self._online_library_filenames.add(
            os.path.normcase(os.path.basename(target)))

        # Sólo actuar sobre widgets de la búsqueda actualmente visible.
        button = self._online_result_buttons.get(key)
        if button is not None:
            self._online_mark_downloaded(button)

        self.online_download_progress.set_fraction(1.0)
        self.online_download_progress.set_text(f"{index}/{total} · 100%")
        return False

    def mark_incorporated_originals(self, paths):
        """Actualiza la búsqueda visible al incorporar originales desde edición."""
        filenames = {os.path.normcase(os.path.basename(path))
            for path in paths if isinstance(path, str) and path}
        if not filenames:
            return

        # También cubre resultados aún pendientes de la búsqueda activa.
        self._online_library_filenames.update(filenames)

        for key, button in self._online_result_buttons.items():
            try:
                filename = get_online_original_filename(button._wmm_online_item)
            except ValueError:
                continue

            if filename and os.path.normcase(filename) in filenames:
                self._online_selected_items.pop(key, None)
                self._online_mark_downloaded(button)

        self._update_online_download_button()

    def _online_download_finished(self, successes, total, last_error):
        """Restablece Download y presenta el resultado desde GTK."""
        self._online_downloading = False
        self._update_online_download_button()
        self.online_download_status.set_text(f"{_('Downloaded')}: {successes}/{total}")

        log_event(f"Online originales: {successes}/{total} descargados"
            + (f"; último error: {last_error}" if last_error else ""),
            origin="ONLINE_SECT", level="WARN" if last_error else "INFO",
            reason="LIBRARY")

        # Persistir las altas confirmadas en una única escritura.
        # También conservar los éxitos si el lote terminó parcialmente.
        pending = self._online_pending_origins
        self._online_pending_origins = []

        if pending:
            saved = self.handler.record_online_origins(pending)
            expected = {
                os.path.normcase(os.path.abspath(path))
                for path, _, _ in pending
            }

            if saved != expected:
                log_event(
                    f"Procedencias Online: {len(saved)}/{len(expected)} registradas",
                    origin="ONLINE_SECT", level="WARN", reason="LIBRARY")

        # Sólo solicitar sincronización si hay originales disponibles.
        if successes and self._library_sync_callback:
            self._library_sync_callback(None)

        return False

    # ==========================================================
    # DRAG & DROP (ORIGEN ONLINE)
    # ==========================================================
    def _online_drag_data_get(self, widget, context, data, info, time, item):
        """Transporta el resultado Online, sin iniciar descargas."""
        payload = json.dumps(item, ensure_ascii=False).encode("utf-8")
        data.set(data.get_target(), 8, payload)

    def _online_drag_begin(self, widget, context, pixbuf):
        """Reutiliza la miniatura ya cargada para el icono de arrastre."""
        max_side = max(pixbuf.get_width(), pixbuf.get_height())
        if max_side > 100:
            factor = 100 / max_side
            pixbuf = pixbuf.scale_simple(
                max(1, int(pixbuf.get_width() * factor)),
                max(1, int(pixbuf.get_height() * factor)),
                GdkPixbuf.InterpType.BILINEAR)
        widget.drag_source_set_icon_pixbuf(pixbuf)

    def _open_online_source_page(self, button, page_url):
        """Abre la página informativa con el navegador predeterminado."""
        try:
            # Win32 necesita un contexto explícito para lanzar el navegador.
            # Linux conserva el contexto predeterminado.
            context = Gio.AppLaunchContext() if os.name == "nt" else None
            Gio.AppInfo.launch_default_for_uri(page_url, context)
        except GLib.Error as error:
            log_event(f"No se pudo abrir la página Online: {error}",
                origin="ONLINE_SECT", level="WARN", reason="LIBRARY")

    def _on_online_overlay_tooltip(self, overlay, x, y, keyboard_mode,
                                   tooltip, description, source_button, select):
        """Unifica los tooltips sin perder los estados de Download."""
        if not keyboard_mode:
            controls = (
                (source_button, source_button.get_tooltip_text()
                    if source_button else None),
                (select, select.get_tooltip_text() if select else None),
            )

            for button, text in controls:
                if button is None or not text:
                    continue

                position = button.translate_coordinates(overlay, 0, 0)
                if position is None:
                    continue

                bx, by = position
                width = button.get_allocated_width()
                height = button.get_allocated_height()

                if bx <= x < bx + width and by <= y < by + height:
                    tooltip.set_text(text)
                    return True

        tooltip.set_text(description)
        return True

    def _online_add_result(self, request_id, page, item, thumb_path):
        """Añade una miniatura descargada a la galería GTK."""
        if request_id != self._online_request_id:
            return False

        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                thumb_path,
                self.handler.thumbnail_max_width,
                self.handler.thumbnail_max_height,
                True)
        except (GLib.Error, OSError) as error:
            log_event(f"Miniatura online ilegible ({item['id']}): {error}",
                origin="ONLINE_SECT", level="WARN", reason="LIBRARY")
            return False

        # Retirar el mensaje inicial cuando llega la primera miniatura.
        if self._online_visible_count == 0:
            for child in self.online_flowbox.get_children():
                self.online_flowbox.remove(child)

        # Abrir una nueva sección sólo al recibir una miniatura válida.
        # Si falla la página, no aparece un separador vacío.
        if page > self._online_displayed_page:
            self._start_online_page(page)

        # La identidad del resultado decide en qué cuadrícula se incorpora.
        flowbox = self._get_online_provider_flowbox(page, item)

        item_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        item_box.set_margin_start(4)
        item_box.set_margin_end(4)

        image = Gtk.Image.new_from_pixbuf(pixbuf)
        description = (
            f"{item['provider_name']} · {item['width']} × {item['height']}\n{item['url']}")

        # El Overlay conserva el tamaño natural de la miniatura.
        overlay = Gtk.Overlay()
        overlay.set_halign(Gtk.Align.CENTER)
        overlay.add(image)
        source_button = None
        page_url = get_online_source_page(item)
        if page_url:
            source_button = Gtk.Button.new_from_icon_name(
                "help-about-symbolic", Gtk.IconSize.LARGE_TOOLBAR)
            source_button.get_style_context().add_class("wmm-online-source-link")
            source_button.set_tooltip_text(_("View on") + " " + item["provider_name"])
            source_button.set_relief(Gtk.ReliefStyle.NONE)
            source_button.set_halign(Gtk.Align.END)
            source_button.set_valign(Gtk.Align.END)
            source_button.set_margin_end(2)
            source_button.set_margin_bottom(2)
            source_button.connect("clicked", self._open_online_source_page, page_url)
            overlay.add_overlay(source_button)

        # La matriz resuelve la identidad; la biblioteca confirma su presencia.
        # Un original sin identidad válida sigue mostrándose normalmente.
        try:
            filename = get_online_original_filename(item)
        except ValueError:
            filename = None

        downloaded = bool(filename and os.path.normcase(filename)
            in self._online_library_filenames)

        select = None

        # La vista presenta la capacidad de descarga que publica el servicio.
        if item["downloadable"]:
            select = Gtk.ToggleButton()
            select.set_image(Gtk.Image.new_from_icon_name(
                "document-save-symbolic", Gtk.IconSize.LARGE_TOOLBAR))
            select.get_accessible().set_name(_("Select"))
            select.set_tooltip_text(_("Select"))
            select.set_relief(Gtk.ReliefStyle.NONE)
            select.set_halign(Gtk.Align.START)
            select.set_valign(Gtk.Align.END)
            select.set_margin_start(2)
            select.set_margin_bottom(2)
            select._wmm_online_item = item
            select.connect("toggled", self._online_selection_changed)

            # La clase selecciona los estilos Online del CSS común.
            # No requiere un proveedor particular por botón.
            style = select.get_style_context()
            style.add_class("wmm-online-select")

            if downloaded:
                self._online_mark_downloaded(select)

            key = (item["provider"], item["id"])
            self._online_result_buttons[key] = select

            overlay.add_overlay(select)

        # Un único punto resuelve la información de imagen y controles.
        # Download conserva sus tooltips dinámicos y su gestión de eventos.
        overlay.set_has_tooltip(True)
        overlay.connect("query-tooltip", self._on_online_overlay_tooltip,
            description, source_button, select)

        # El EventBox recoge el arrastre sin convertir el botón Download
        # en fuente de D&D; éste conserva sus eventos de selección.
        if item["downloadable"]:
            drag_source = Gtk.EventBox()
            drag_source.add(overlay)
            drag_source.drag_source_set(
                Gdk.ModifierType.BUTTON1_MASK,
                [Gtk.TargetEntry.new("application/x-wmm-online-image",
                    Gtk.TargetFlags.SAME_APP, 0)],
                Gdk.DragAction.COPY)
            drag_source.connect("drag-data-get", self._online_drag_data_get, item)
            drag_source.connect("drag-begin", self._online_drag_begin, pixbuf)
            item_box.pack_start(drag_source, False, False, 0)
        else:
            item_box.pack_start(overlay, False, False, 0)

        label = Gtk.Label(
            label=f"{item['width']} × {item['height']}")
        label.set_halign(Gtk.Align.CENTER)
        item_box.pack_start(label, False, False, 0)

        flowbox.add(item_box)
        flowbox.show_all()
        self._online_visible_count += 1

        # Navegar al recibir la primera miniatura válida de la nueva
        # página, sin esperar a que termine toda la búsqueda.
        if self._online_page_header is not None:
            GLib.idle_add(self._scroll_to_online_page, self._online_page_header)

        return False

    def _scroll_to_online_page(self, header, final=False):
        """Sitúa la nueva página arriba cuando hay altura suficiente."""
        if (header is not self._online_page_header
                or header.get_parent() is not self.online_pages_box):
            return False

        position = header.translate_coordinates(self.online_pages_box, 0, 0)
        if position is None:
            return False

        adjustment = self.online_scrolled.get_vadjustment()
        maximum = max(adjustment.get_lower(),
                      adjustment.get_upper() - adjustment.get_page_size())

        # Conservar la solicitud hasta que GTK permita colocar el
        # encabezado arriba. Al finalizar, usar la posición disponible.
        if maximum >= position[1] or final:
            adjustment.set_value(min(max(position[1], adjustment.get_lower()), maximum))
            self._online_page_header = None

        return False

    def _online_search_finished(self, request_id, provider_name, total, failures,
                                last_error, all_failed=False, next_page=None):
        """Finaliza la presentación de los resultados de la búsqueda."""
        if request_id != self._online_request_id:
            return False

        # Respaldo para páginas que terminan sin suficiente altura.
        if self._online_page_header is not None:
            GLib.idle_add(self._scroll_to_online_page, self._online_page_header, True)

        self._online_loading_more = False
        self._online_next_page = next_page
        self._update_online_search_button()

        if self._online_visible_count == 0:
            message = _("No wallpapers found.") if total == 0 else \
                _("Could not load wallpaper thumbnails.")
            self._online_show_message(message)

        if failures:
            log_event(
                f"{provider_name}: {failures} descargas fallidas; último error: {last_error}",
                origin="ONLINE_SECT", level="WARN", reason="LIBRARY")

        if self._online_visible_count:
            log_event(
                f"{provider_name}: {self._online_visible_count}/{total} miniaturas mostradas",
                origin="ONLINE_SECT", level="INFO", reason="LIBRARY")

        return False

    def _online_search_error(self, request_id, provider_name, error, log_only=False):
        """Registra un error sin destruir resultados de otros proveedores."""
        if request_id != self._online_request_id:
            return False

        # En búsquedas múltiples, el estado de la galería corresponde al
        # resultado conjunto, no al fallo individual de un proveedor.
        if not log_only:
            self._online_show_message(_("Online search failed."))

        log_event(f"Error de búsqueda {provider_name}: {error}",
            origin="ONLINE_SECT", level="ERROR", reason="LIBRARY")
        return False