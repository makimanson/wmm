/*
 * SPDX-FileCopyrightText: 2026 makimanson
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * applet.js: WMM Applet - Cinnamon Edition
 * -----------------------------------------
 * Gestión de fondos multi-monitor con soporte para temporizador, favoritos,
 * modos SYNC/ASYNC y Spanned.
 *
 * FLUJO DE CONTROL:
 * 1. UI (JS) -> send_command.py -> commands.json / canal del engine.
 * 2. Engine (Python) -> ejecuta la acción -> actualiza settings/bookmarks/estado.
 * 3. UI (JS) -> sincroniza settings/bookmarks al abrir el menú.
 */

const Applet = imports.ui.applet;
const AppletManager = imports.ui.appletManager;
const Util = imports.misc.util;
const PopupMenu = imports.ui.popupMenu;
const Gio = imports.gi.Gio;
const GLib = imports.gi.GLib;
const St = imports.gi.St;
const Gtk = imports.gi.Gtk;

const Gettext = imports.gettext;

// Cinnamon 5.4+ expone St.PolicyType; versiones anteriores utilizan Gtk.PolicyType.
const PolicyType = St.PolicyType || Gtk.PolicyType;

// Dominio de traducciones propio del applet.
Gettext.bindtextdomain('wmm@maki', GLib.get_user_data_dir() + '/locale');

function _(text) { return Gettext.dgettext('wmm@maki', text); }

class WMMApplet extends Applet.IconApplet {

    /**
     * BLOQUE 1: CONSTRUCTOR
     * Configuración de rutas, UI inicial y arranque del engine.
     */
    constructor(metadata, orientation, panel_height, instance_id) {
        super(orientation, panel_height, instance_id);

        try {
            this.set_applet_icon_name("video-display");
            this.appletPath = metadata.path;

            // Desde v1.5.0 el frontend Cinnamon ya no contiene el core ni data.
            // settings_core.ini es la autoridad instalada para resolver ambos.
            let coreFile = Gio.File.new_for_path(this.appletPath + "/settings_core.ini");
            let [success, contents] = coreFile.load_contents(null);
            if (!success) throw new Error("Could not read settings_core.ini");

            let coreConfig = {};
            imports.byteArray.toString(contents).split("\n").forEach(line => {
                line = line.trim();
                if (!line || line.startsWith("#") || line.startsWith(";")) return;

                let separator = line.indexOf("=");
                if (separator < 0) return;

                coreConfig[line.slice(0, separator).trim()] =
                    line.slice(separator + 1).trim();
            });

            this.appDir = coreConfig.app_dir;
            this.dataDir = coreConfig.data_dir;

            if (!this.appDir || !this.dataDir)
                throw new Error("settings_core.ini does not define app_dir/data_dir");

            this.enginePath = this.appDir + "/python/main.py";
            this.commandsPath = this.dataDir + "/commands.json";
            this.settingsPath = this.dataDir + "/settings.json";
            this.bookmarksPath = this.dataDir + "/bookmarks.json";

            this._currentMaxInterval = 60;
            this.favItems = [];
            this._motorBusy = false;
            this._ignoreNextBusy = false;
            this._cachedSettings = null;
            this._cachedBookmarks = null;

            /*
             * Cinnamon carga el applet antes que el engine. Mantenerlo oculto
             * evita materializar textos traducidos antes de que el engine haya
             * podido compilar los catálogos pendientes.
             */
            this._uiReady = false;
            this._engineWatchId = 0;

            /*
             * El actor debe conservar geometría mientras Cinnamon prepara su
             * Flashspot. Ocultarlo eliminaría sus dimensiones y convertiría
             * ese destello local en uno de escritorio completo.
             *
             * _applet_enabled bloquea los clics en el propio lifecycle de
             * Cinnamon sin alterar la reactividad del actor.
             */
            this._bootstrapState = {
                opacity: this.actor.opacity,
                appletEnabled: this._applet_enabled
            };

            this._applet_enabled = false;
            this.actor.opacity = 0;

            this._engineWatchId = Gio.bus_watch_name(
                Gio.BusType.SESSION,
                "org.maki.wmm",
                Gio.BusNameWatcherFlags.NONE,
                () => this._onEngineAppeared(),
                null
            );

            Util.spawn(["python3", this.enginePath]);
        }
        catch (e) { global.logError("WMM Constructor Error: " + e.message); }
    }

    finalizeContextMenu() {
        /*
         * Cinnamon finaliza automáticamente el menú nada más cargar el applet.
         * Su implementación base traduce metadata.name con dgettext(uuid, ...);
         * si el catálogo aún no existe, ese fallo queda cacheado durante la vida
         * del proceso Cinnamon. Aplazar la finalización hasta org.maki.wmm evita
         * consultar el dominio antes de que el engine haya creado los .mo.
         */
        if (!this._uiReady) return;
        super.finalizeContextMenu();
    }

    _onEngineAppeared() {
        if (this._uiReady) return;
        this._uiReady = true;

        /*
         * org.maki.wmm sólo aparece después de que el engine haya preparado
         * las traducciones. A partir de aquí ya es seguro materializar la UI.
         */
        this.set_applet_icon_name("video-display");
        this.set_applet_tooltip(
            "WMM: " + _("Wallpaper Multi-Monitor Manager") + "\n" +
            _("Click action") + ": " + _("Next Background") + "\n" +
            _("Secondary Click") + ": " + _("Context Menu"));

        this._populateMenu();

        /*
         * El menú propio se construye primero porque _populateMenu() hace
         * removeAll(). Sólo después Cinnamon puede añadir sus entradas estándar,
         * ya con el catálogo de WMM disponible.
         */
        this.finalizeContextMenu();

        // Lectura de settings/bookmarks únicamente al abrir el menú principal.
        this._applet_context_menu.connect('open-state-changed', (menu, open) => {
            if (open) this._refreshSettingsFromDisk();
        });

        // Estado operativo del engine para reflejar busy en el icono del applet.
        let statusPath = GLib.get_user_cache_dir() + "/wmm/engine_status.json";
        let statusFile = Gio.File.new_for_path(statusPath);
        this._statusMonitor = statusFile.monitor_file(Gio.FileMonitorFlags.NONE, null);
        this._statusMonitor.connect("changed", () => this._updateIconFromStatus());
        this._updateIconFromStatus();

        /*
         * Restaurar exactamente el estado previo al bootstrap. No se fuerza
         * ningún valor propio sobre el actor administrado por Cinnamon.
         */
        this.actor.opacity = this._bootstrapState.opacity;
        this._applet_enabled = this._bootstrapState.appletEnabled;
        this._bootstrapState = null;
    }

    _bindSubmenuHeaderBold(submenuItem) {
        // Resalta la cabecera únicamente mientras su submenú permanece abierto.
        submenuItem.menu.connect('open-state-changed', (menu, open) => {
            submenuItem.label.set_style(open ? 'font-weight: bold;' : null);
        });
    }


    /**
     * BLOQUE 2: CONSTRUCCIÓN DE LA INTERFAZ
     * Esqueleto del menú contextual del applet.
     */
    _populateMenu() {
        try {
            this._applet_context_menu.removeAll();
            this._applet_context_menu.actor.width_request = 200;

            // --- 2.2 SUBMENÚ FAVORITOS ---
            this.menuBookmarks = new PopupMenu.PopupSubMenuMenuItem(_("Favorites"));
            this._bindSubmenuHeaderBold(this.menuBookmarks);
            this._applet_context_menu.addMenuItem(this.menuBookmarks);

            this.favRotationSwitch = new PopupMenu.PopupSwitchMenuItem(_("Favorites Only"), false);
            this.favRotationSwitch.connect('toggled', (item, state) => {
                if (state && !this.masterItem.state) this._syncTimerUI(true);
                this._updateTimerSettings();
            });
            this.menuBookmarks.menu.addMenuItem(this.favRotationSwitch);
            this.menuBookmarks.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

            let itemAddBookmark = new PopupMenu.PopupMenuItem(_("Add Preset Favorite"));
            itemAddBookmark.connect('activate', () => this._sendActionToEngine({ action: "add_bookmark" }));
            this.menuBookmarks.menu.addMenuItem(itemAddBookmark);
            this.menuBookmarks.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

            // --- 2.3 SUBMENÚ TEMPORIZADOR ---
            this.menuTimer = new PopupMenu.PopupSubMenuMenuItem(_("Slideshow"));
            this._bindSubmenuHeaderBold(this.menuTimer);
            this._applet_context_menu.addMenuItem(this.menuTimer);

            this.masterItem = new PopupMenu.PopupSwitchMenuItem(_("Disabled"), false);
            this.menuTimer.menu.addMenuItem(this.masterItem);

            let infoItem = new PopupMenu.PopupBaseMenuItem({ reactive: false });
            let infoBox = new St.BoxLayout({ style: "margin-left: 110px;" });
            this.labelMin = new St.Label();
            infoBox.add(this.labelMin);
            infoItem.addActor(infoBox);
            this.menuTimer.menu.addMenuItem(infoItem);

            this.slider = new PopupMenu.PopupSliderMenuItem(0.25);
            this.menuTimer.menu.addMenuItem(this.slider);

            // --- 2.4 MODO SYNC/ASYNC ---
            this.modeSwitch = new PopupMenu.PopupSwitchMenuItem(_("Displays") + ": " + _("ASYNC (One)"), false);
            this._applet_context_menu.addMenuItem(this.modeSwitch);

            // --- 2.4b MODO SPANNED ---
            this.spannedSwitch = new PopupMenu.PopupSwitchMenuItem(_("Spanned Mode"), false);
            this.spannedSwitch.connect('toggled', () => this._updateTimerSettings());
            this._applet_context_menu.addMenuItem(this.spannedSwitch);

            // --- 2.5 EVENTOS Y LÓGICA ---
            this.slider.connect('value-changed', () => {
                if (!this.masterItem || !this.masterItem.state) {
                    if (this.masterItem) this._refreshSettingsFromDisk();
                    return;
                }

                let mins = Math.max(1, Math.round(this.slider.value * this._currentMaxInterval));
                this.labelMin.set_text(mins + " " + _("minutes"));
            });

            this.slider.connect('drag-end', () => {
                if (this.masterItem && this.masterItem.state) this._updateTimerSettings();
            });

            this.masterItem.connect('toggled', (item, state) => {
                item.label.set_text(state ? _("Enabled") : _("Disabled"));
                this._syncTimerUI(state);
                this._updateTimerSettings();
            });

            this.modeSwitch.connect('toggled', (item, state) => {
                item.label.set_text(state ? _("Displays") + ": " + _("SYNC (All)") : _("Displays") + ": " + _("ASYNC (One)"));
                this._updateTimerSettings();
            });

            // --- 2.6 TOOLS ---
            this._applet_context_menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

            this.menuTools = new PopupMenu.PopupSubMenuMenuItem(_("Tools"));
            this._bindSubmenuHeaderBold(this.menuTools);
            this._applet_context_menu.addMenuItem(this.menuTools);

            let itemControlPanel = new PopupMenu.PopupMenuItem(_("Settings"));
            itemControlPanel.connect('activate', () => this._openSettingsPanel());
            this.menuTools.menu.addMenuItem(itemControlPanel);

            let itemSync = new PopupMenu.PopupMenuItem(_("Sync Library"));
            itemSync.connect('activate', () => this._sendActionToEngine({ action: "sync_library" }));
            this.menuTools.menu.addMenuItem(itemSync);

            let itemInstallManager = new PopupMenu.PopupMenuItem(_("Install Manager"));
            itemInstallManager.connect('activate', () => this._launchIndependentTool(
                this.appDir + "/wmm_platform/shell/installer/wmm-install_manager.py"));
            this.menuTools.menu.addMenuItem(itemInstallManager);

            let itemDebugLog = new PopupMenu.PopupMenuItem(_("Debug Log Viewer"));
            itemDebugLog.connect('activate', () => this._launchIndependentTool(
                this.appDir + "/python/debug_log_viewer.py"));
            this.menuTools.menu.addMenuItem(itemDebugLog);

            let itemHelp = new PopupMenu.PopupMenuItem(_("Help"));
            itemHelp.connect('activate', () => this._sendActionToEngine({ action: "open_help" }));
            this.menuTools.menu.addMenuItem(itemHelp);

            /*
             * WMM sustituye deliberadamente el bloque nativo About/Remove de
             * Cinnamon por sus propias acciones una vez finalizado el bootstrap.
             */
            this._applet_context_menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

            let itemAbout = new PopupMenu.PopupMenuItem(_("About") + " WMM Manager");
            itemAbout.connect('activate', () => this._sendActionToEngine({ action: "open_about" }));
            this._applet_context_menu.addMenuItem(itemAbout);

            let itemExit = new PopupMenu.PopupMenuItem(_("Exit") + " WMM");
            itemExit.connect('activate', () => {
                /*
                 * Exit WMM omite deliberadamente la confirmación genérica de Cinnamon.
                 * La retirada sigue pasando por AppletManager para conservar el lifecycle
                 * nativo y llegar a on_applet_removed_from_panel(), que detiene el engine.
                 */
                AppletManager._removeAppletFromPanel(this._uuid, this.instance_id);
            });
            this._applet_context_menu.addMenuItem(itemExit);
        }
        catch (e) { global.logError("WMM PopulateMenu Error: " + e.message); }
    }

    /**
     * BLOQUE 3: SINCRONIZACIÓN EN CALIENTE
     * Actualiza la UI sin realizar lecturas de disco.
     */
    _syncTimerUI(enabled) {
        if (!this.masterItem) return;

        this.masterItem.setToggleState(enabled);
        this.masterItem.label.set_text(enabled ? _("Enabled") : _("Disabled"));
        this.slider.setSensitive(enabled);
        this.slider.actor.reactive = enabled;
    }

    _applySettingsToUI(config) {
        if (!this.masterItem || !this.slider) return;

        this._currentMaxInterval = config.slideshow_max_interval || 60;

        let isEnabled = config.slideshow_enabled;
        let isSync = config.slideshow_mode === "sync";
        let isFavSlideshow = config.slideshow_bookmark || false;
        let isSpanned = config.spanned_enabled || false;

        this._syncTimerUI(isEnabled);

        this.modeSwitch.setToggleState(isSync);
        this.modeSwitch.label.set_text(isSync ? _("Displays") + ": " + _("SYNC (All)") : _("Displays") + ": " + _("ASYNC (One)"));

        this.favRotationSwitch.setToggleState(isFavSlideshow);

        let ratio = config.slideshow_interval / this._currentMaxInterval;
        this.slider.setValue(ratio);
        this.labelMin.set_text(config.slideshow_interval + " " + _("minutes"));

        this.spannedSwitch.setToggleState(isSpanned);
    }

    /**
     * Destruye únicamente los items dinámicos creados por _paintBookmarks().
     */
    _clearBookmarksUI() { this.favItems.forEach(item => item.destroy()); this.favItems = []; }

    /**
     * Pinta la lista dinámica de presets favoritos.
     *
     * - El ScrollView crece de forma natural hasta 115 px.
     * - A partir del máximo aparece scroll vertical.
     * - Nombre y papelera son items independientes con hover propio.
     * - Las filas no expanden verticalmente: cada una conserva su altura natural.
     */
    _paintBookmarks(bookmarks) {
        this._clearBookmarksUI();
        let keys = Object.keys(bookmarks);
        if (keys.length === 0) {
            let info = new PopupMenu.PopupMenuItem(_("No saved favorites"), { reactive: false });
            this.menuBookmarks.menu.addMenuItem(info);
            this.favItems.push(info);
            return;
        }

        // Item estructural neutro que aloja el ScrollView.
        let scrollItem = new PopupMenu.PopupBaseMenuItem({ reactive: false, activate: false });
        scrollItem.actor.style = 'padding: 0; margin: 0; background-color: transparent;';
        scrollItem.actor.remove_all_children();

        // Contenido vertical. El padding derecho da aire a la papelera respecto al borde.
        let favBox = new St.BoxLayout({
            vertical: true,
            style: 'margin-left: 10px; padding: 0 6px 0 0; spacing: 3px;'
        });

        keys.forEach(name => {
            let row = new St.BoxLayout({ style: 'padding: 0; spacing: 2px;' });

            // Nombre del preset: item de menú nativo con hover independiente.
            let nameItem = new PopupMenu.PopupMenuItem(name, {
                reactive: true,
                activate: true,
                focusOnHover: false
            });
            nameItem.actor.style = 'padding: 1px 6px; spacing: 0px;';

            nameItem.connect('activate', () => {
                this._syncTimerUI(false);
                this._sendActionToEngine({ action: "load_bookmark", name: name, timer_force_off: true });
                this._applet_context_menu.close();
            });

            // Papelera: item independiente para disponer de hover y zona de clic propios.
            let deleteItem = new PopupMenu.PopupBaseMenuItem({
                reactive: true,
                activate: true,
                focusOnHover: false
            });

            deleteItem.actor.style = 'padding: 1px 6px; spacing: 0px;';

            let deleteIcon = new St.Icon({
                icon_name: 'user-trash-symbolic',
                style_class: 'popup-menu-icon',
                icon_size: 16,
                reactive: false
            });

            deleteItem.addActor(deleteIcon, { expand: false, align: St.Align.MIDDLE });

            deleteItem.connect('activate', () => {
                this._confirmDeleteBookmark(name);
                this._applet_context_menu.close();
            });

            row.add(nameItem.actor, { expand: true, x_fill: true, x_align: St.Align.START });
            row.add(deleteItem.actor, { expand: false, x_fill: false });

            // IMPORTANTE: false evita repartir artificialmente la altura del ScrollView entre filas.
            favBox.add(row, { expand: false, x_fill: true });
        });

        // Altura natural hasta 115 px; después, scroll vertical automático.
        let scrollView = new St.ScrollView({
            style: 'border: none; background-color: transparent; padding: 0; margin: 0; max-height: 115px;'
        });

        scrollView.set_policy(PolicyType.NEVER, PolicyType.AUTOMATIC);
        scrollView.add_actor(favBox);

        scrollItem.addActor(scrollView, { expand: true, span: -1 });
        this.menuBookmarks.menu.addMenuItem(scrollItem);
        this.favItems.push(scrollItem);
    }

    /**
     * BLOQUE 4: REFRESH DISCO -> UI
     * Sincroniza el applet con el estado persistido.
     */
    _refreshSettingsFromDisk() {
        try {
            if (!this.masterItem || !this.slider) return;

            // 1. Aplicar caché disponible para apertura instantánea.
            if (this._cachedSettings) this._applySettingsToUI(this._cachedSettings);
            if (this._cachedBookmarks) this._paintBookmarks(this._cachedBookmarks);
            else this._clearBookmarksUI();

            // 2. Cargar settings globales de forma asíncrona.
            let settingsFile = Gio.File.new_for_path(this.settingsPath);
            if (!settingsFile.query_exists(null)) { this._refreshBookmarks(); return; }
            settingsFile.load_contents_async(null, (file, res) => {
                try {
                    let [success, content] = file.load_contents_finish(res);
                    if (!success || content.length === 0) return;
                    let config;
                    try { config = JSON.parse(content).global; }
                    catch (e) { return; }
                    if (!config) return;
                    let cached = this._cachedSettings;
                    if (
                        !cached ||
                        cached.slideshow_enabled !== config.slideshow_enabled ||
                        cached.slideshow_interval !== config.slideshow_interval ||
                        cached.slideshow_mode !== config.slideshow_mode ||
                        cached.slideshow_bookmark !== config.slideshow_bookmark ||
                        cached.spanned_enabled !== config.spanned_enabled)

                    { this._applySettingsToUI(config); this._cachedSettings = config; }
                }

                catch (e) { /* Escritura parcial o JSON todavía incompleto: se ignora este evento. */}
            });

            // 3. Cargar favoritos dinámicos.
            this._refreshBookmarks();

        }

        catch (e) { global.logError("WMM Refresh Error: " + e.message); }
    }

    _refreshBookmarks() {
        let bookmarksFile = Gio.File.new_for_path(this.bookmarksPath);
        if (!bookmarksFile.query_exists(null)) { this._clearBookmarksUI(); return; }
        bookmarksFile.load_contents_async(null, (file, res) => {
            try {
                let [success, content] = file.load_contents_finish(res);
                if (!success || content.length === 0) { this._clearBookmarksUI(); return; }
                let bookmarks;
                try { bookmarks = JSON.parse(content); }
                catch (e) { this._clearBookmarksUI(); return; }
                let cached = this._cachedBookmarks;
                if (cached && JSON.stringify(cached) === JSON.stringify(bookmarks)) return;
                this._cachedBookmarks = bookmarks;
                this._paintBookmarks(bookmarks);
                }
                catch (e) { this._clearBookmarksUI(); }
                });
    }

    _confirmDeleteBookmark(name) {
        let args = [
            '--question',
            '--title=' + _("Delete favorite"),
            '--text=' + _("Delete") + ' "' + name + '"?',
            '--width=200'];

        try {let proc = new Gio.Subprocess(
            {argv: ['zenity'].concat(args), flags: Gio.SubprocessFlags.NONE});
            proc.init(null);
            proc.wait_async(null, (process, result) => {
                try {process.wait_finish(result);
                    if (process.get_exit_status() === 0)
                        this._sendActionToEngine({ action: "delete_bookmark", name: name });}
                    catch (e) { global.logError("WMM: Error en wait_finish del diálogo: " + e.message); }
            });
        }
            catch (e) { global.logError("WMM: Error al lanzar zenity: " + e.message); }
    }

    /**
     * BLOQUE 5: COMUNICACIÓN JS -> ENGINE
     */
    _updateTimerSettings() {
        this._sendActionToEngine({
            action: "update_timer_settings",
            enabled: this.masterItem.state,
            interval: Math.max(1, Math.round(this.slider.value * this._currentMaxInterval)),
            mode: this.modeSwitch.state ? "sync" : "async",
            slideshow_bookmark: this.favRotationSwitch.state,
            spanned_enabled: this.spannedSwitch.state
        });
    }

    _sendActionToEngine(command) {
        try {
            let cmd = JSON.stringify(command);
            Util.spawn(["python3", this.appDir + "/python/send_command.py", cmd]);
        }

        catch (e) { global.logError("WMM Send Error (" + (command.action || 'unknown') + "): " + e.message); }

    }

    _launchIndependentTool(path) {
        try { Util.spawn(["python3", path]); }
        catch (e) { global.logError("WMM Tool Launch Error (" + path + "): " + e.message); }
    }

    _openSettingsPanel() { this._sendActionToEngine({ action: "open_panel" }); }

    /**
     * BLOQUE 6: EVENTOS DEL SISTEMA
     */
    on_applet_clicked(event) {
        if (this._motorBusy) { this.set_applet_icon_name("view-refresh"); return; }

        this.set_applet_icon_name("view-refresh");
        this._ignoreNextBusy = true;
        this._sendActionToEngine({ action: "force_rotation" });
    }

    on_applet_removed_from_panel() {
        if (this._engineWatchId) {
            Gio.bus_unwatch_name(this._engineWatchId);
            this._engineWatchId = 0;
        }

        /*
         * Quitar explícitamente el applet representa "Salir de WMM".
         * Se solicita Shutdown por D-Bus sin terminar procesos ni manipular PIDs.
         * NO_AUTO_START evita arrancar accidentalmente el engine si ya estaba detenido.
         */
        Gio.DBus.session.call(
            "org.maki.wmm",
            "/org/maki/wmm",
            "org.maki.wmm",
            "Shutdown",
            null, null,
            Gio.DBusCallFlags.NO_AUTO_START,
            1000, null,
            (connection, result) => {
                try { connection.call_finish(result); }
                catch (e) { /* El engine puede haber terminado ya; no requiere recuperación */ }
            }
        );
    }

    _updateIconFromStatus() {
        let file = Gio.File.new_for_path(GLib.get_user_cache_dir() + "/wmm/engine_status.json");
        if (!file.query_exists(null)) return;

        file.load_contents_async(null, (statusFile, res) => {
            try {
                let [success, contents] = statusFile.load_contents_finish(res);
                if (!success || contents.length === 0) return;
                let status = JSON.parse(contents);
                this._motorBusy = status.busy;
                if (status.busy) {
                    if (!this._ignoreNextBusy) this.set_applet_icon_name("view-refresh"); }
                else {
                    this._ignoreNextBusy = false;
                    this.set_applet_icon_name("video-display"); }
            }

            catch (e) {/* JSON a medias: ignorar hasta el siguiente evento. */}
        });
    }
}

function main(metadata, orientation, panel_height, instance_id) {
    return new WMMApplet(metadata, orientation, panel_height, instance_id);
}
