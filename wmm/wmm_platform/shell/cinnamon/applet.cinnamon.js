/*
 * SPDX-FileCopyrightText: 2026 makimanson
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * applet.js: WMM Applet - Cinnamon Edition
 * -----------------------------------------
 * Gestión de fondos multi-monitor con soporte para temporizador, favoritos,
 * modos SYNC/ASYNC y Spanned.
 *
 * MAPA DE NAVEGACIÓN DEL ARCHIVO:
 * 1. Arranque y lifecycle: engine, traducciones y construcción inicial.
 * 2. Menú principal (izquierdo): Favorites, Slideshow, Displays,
 *    Spanned Mode, Image Metadata y Next Background; diálogo de borrado.
 * 3. Menú contextual (derecho): Settings, Sync Library, Install Manager,
 *    Debug Log Viewer, Help, About y Exit.
 * 4. Sincronización: settings y favoritos desde disco; persistencia.
 * 5. Engine y estado: órdenes, rotación y señalización busy.
 * 6. Eventos del applet: clics y retirada del panel.
 *
 * CONTRATO DE MENÚS:
 * - Principal: permanece abierto salvo al añadir/eliminar favoritos y
 *   al abrir Keybinding Manager. La confirmación de borrado mantiene
 *   su comportamiento de diálogo hijo ya validado.
 * - Contextual: todas las opciones lo cierran antes de actuar.
 *
 * FLUJO DE CONTROL:
 * UI (JS) -> send_command.py -> engine -> settings/bookmarks/estado.
 * El menú principal relee settings/bookmarks al abrirse.
 */

const Applet = imports.ui.applet;
const AppletManager = imports.ui.appletManager;
const Main = imports.ui.main;
const Tooltips = imports.ui.tooltips;
const Util = imports.misc.util;
const PopupMenu = imports.ui.popupMenu;
const Clutter = imports.gi.Clutter;
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

    // ================================================================
    // 1. ARRANQUE Y LIFECYCLE · Cinnamon, engine y traducciones
    // ================================================================

    /** Rutas del frontend, menús compartidos y bootstrap hasta tener gettext listo. */
    constructor(metadata, orientation, panel_height, instance_id) {
        super(orientation, panel_height, instance_id);

        try {
            /*
             * ICONO PROVISIONAL DEL BOOTSTRAP
             *
             * Se establece antes de resolver appletPath. El actor dispone
             * así de un icono válido durante la inicialización, mientras
             * permanece invisible hasta que el engine esté preparado.
             *
             * _onEngineAppeared() sustituye este icono por la identidad
             * gráfica definitiva mediante _setNormalAppletIcon().
             */
            this.set_applet_icon_name("video-display");

            /*
             * El actor padre del applet es la única autoridad de puntero.
             * El icono interior no necesita recibir eventos y, si los recibe,
             * puede provocar falsas transiciones de hover en el tooltip nativo.
             */
            this._applet_icon.reactive = false;
            this._applet_icon.track_hover = false;
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
            this._deleteConfirmMenu = null;

            /*
             * Cinnamon ya administra el menú contextual mediante _menuManager.
             * Registrar el menú principal en ese mismo manager conserva una única
             * autoridad para apertura/cierre entre ambos popups.
             */
            this._mainMenu = new Applet.AppletPopupMenu(this, orientation);
            this._mainMenu.actor.add_style_class_name("wmm-menu");

            this._applet_context_menu.actor.add_style_class_name("wmm-menu");

            this._menuManager.addMenu(this._mainMenu);

            /*
             * BOOTSTRAP DE TRADUCCIONES
             *
             * Cinnamon puede cargar el applet antes de que el engine compile los
             * catálogos .mo. bindtextdomain() puede ejecutarse antes, pero una
             * primera consulta dgettext() sin catálogo puede quedar cacheada en
             * el proceso del shell y mantener textos sin traducir durante la sesión.
             *
             * Por eso no se construyen los menús ni el tooltip traducible hasta
             * detectar org.maki.wmm por D-Bus: el engine publica ese servicio
             * después de preparar las traducciones.
             *
             * Mientras tanto, el applet permanece invisible y sin interacción,
             * conservando su geometría para evitar la regresión de Flashspot.
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

    /**
     * CONTEXTUAL — Anulación permanente de la construcción nativa.
     *
     * WMM construye su menú contextual mediante _populateContextMenu(),
     * después de que el engine haya preparado las traducciones.
     *
     * La sobrescritura vacía impide que Cinnamon añada sus elementos
     * nativos, tanto durante el bootstrap como posteriormente.
     * No delegar en super.finalizeContextMenu().
     */
    finalizeContextMenu() {}

    /** Construye ambos menús al estar disponible el engine y su catálogo gettext. */
    _onEngineAppeared() {
        if (this._uiReady) return;
        this._uiReady = true;

        /*
         * org.maki.wmm sólo aparece después de que el engine haya preparado
         * las traducciones. A partir de aquí ya es seguro materializar la UI.
         */
        this._setNormalAppletIcon();

        const tooltipTitle = GLib.markup_escape_text("Wallpaper Multi-Monitor Manager", -1);
        const tooltipActions = GLib.markup_escape_text(
            _("Click action") + ": " + _("Main Menu") + "\n" +
            _("Middle Click") + ": " + _("Next Background") + "\n" +
            _("Secondary Click") + ": " + _("Context Menu"), -1);

        this.set_applet_tooltip("<b>" + tooltipTitle + "</b>\n" + tooltipActions, true);

        /*
         * El tooltip nativo centra por presentación sus líneas. WMM utiliza varias
         * acciones independientes, por lo que la lectura resulta más clara alineada
         * desde un mismo margen izquierdo.
         */
        this._applet_tooltip._tooltip.set_style('text-align: left;');

        this._populateMenu();
        this._populateContextMenu();

        // Settings y presets pertenecen al menú principal; el contextual no
        // necesita provocar lecturas ni reconstrucciones de ese estado.
        this._mainMenu.connect('open-state-changed', (menu, open) => {
            if (open)
                this._refreshSettingsFromDisk();
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

    // ================================================================
    // 2. MENÚ PRINCIPAL · orden visual y opciones (clic izquierdo)
    // ================================================================

    /**
     * MENÚ PRINCIPAL · orden físico de arriba abajo.
     * Se reconstruye tras el bootstrap de traducciones y sincroniza estado al abrir.
     * El menú permanece abierto salvo añadir/borrar favoritos y abrir Keybinding Manager.
     */
    _populateMenu() {
        try {
            this._mainMenu.removeAll();
            this._mainMenu.actor.width_request = 200;

            this._buildFavoritesMenu();
            this._buildSlideshowMenu();
            this._buildDisplayControls();
            this._mainMenu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
            this._buildNextBackgroundAction();
        }
        catch (e) { global.logError("WMM PopulateMenu Error: " + e.message); }
    }

    /** Impide que las columnas del submenú modifiquen el ancho del principal. */
    _isolateSubmenuLayout(submenuItem) {
        submenuItem.actor.add_style_class_name("wmm-submenu-header");

        /*
         * Cinnamon sincroniza las columnas de todos los PopupBaseMenuItem y
         * Eso permite que una columna interna ensanche el menú principal aunque
         * su contenido ya quepa dentro del ancho total disponible.
         *
         * WMM convierte la cabecera en una única fila local que ocupa todo el
         * ancho asignado y corta únicamente la propagación de columnas hacia
         * arriba. setColumnWidths() permanece intacto, por lo que el ancho del
         * menú principal sigue distribuyéndose normalmente hacia abajo.
         */
        let headerRow = new St.BoxLayout();

        submenuItem.removeActor(submenuItem.label);
        submenuItem.removeActor(submenuItem._triangleBin);

        headerRow.add(submenuItem.label, {
            expand: true,
            x_fill: true
        });

        headerRow.add(submenuItem._triangleBin, {
            expand: false,
            x_fill: false
        });

        submenuItem.addActor(headerRow, {
            span: -1,
            expand: true
        });

        /*
         * La cabecera y su contenido son una unidad geométrica subordinada al
         * menú principal: reciben el ancho disponible, pero sus columnas locales
         * no participan en el cálculo de las columnas del nivel superior.
         */
        submenuItem.getColumnWidths = () => [];
        submenuItem.menu.getColumnWidths = () => [];
    }

    /** PRINCIPAL/Favorites: cabecera, Favorites Only y Add Preset Favorite. */
    _buildFavoritesMenu() {
        // FAVORITOS · cabecera y política de rotación exclusiva.
        this.menuBookmarks = new PopupMenu.PopupSubMenuMenuItem(_("Favorites"));
        this._isolateSubmenuLayout(this.menuBookmarks);
        this._mainMenu.addMenuItem(this.menuBookmarks);
        this.favRotationSwitch = new PopupMenu.PopupSwitchMenuItem(_("Favorites Only"), false);
        this.favRotationSwitch.connect('toggled', (item, state) => {
            if (state && !this.masterItem.state) this._syncTimerUI(true);
            this._updateTimerSettings();
        });
        this.menuBookmarks.menu.addMenuItem(this.favRotationSwitch);
        this.menuBookmarks.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        // FAVORITOS · añadir preset: esta operación sí abandona el menú principal.
        let itemAddBookmark = new PopupMenu.PopupBaseMenuItem();

        let addBookmarkRow = new St.BoxLayout();

        let addBookmarkLabel = new St.Label({text: _("Add Preset Favorite")});

        addBookmarkRow.add(addBookmarkLabel, {
            expand: true,
            x_fill: true
        });

        itemAddBookmark.addActor(addBookmarkRow, {
            span: -1,
            expand: true
        });

        itemAddBookmark.actor.label_actor = addBookmarkLabel;

        itemAddBookmark.connect('activate', () => {
            const [x, y] = itemAddBookmark.actor.get_transformed_position();
            const [width, height] = itemAddBookmark.actor.get_transformed_size();

            this._mainMenu.close();

            this._sendActionToEngine({
                action: "add_bookmark",
                x: Math.round(x + width / 2),
                y: Math.round(y + height / 2)
            });
        });

        this.menuBookmarks.menu.addMenuItem(itemAddBookmark);
        this.menuBookmarks.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
    }

    /** Elimina solo los elementos dinámicos; la cabecera y el switch son fijos. */
    _clearBookmarksUI() { this.favItems.forEach(item => item.destroy()); this.favItems = []; }

    /**
     * FAVORITOS · filas dinámicas con dos controles independientes.
     * Nombre y papelera mantienen hover propio; la lista crece hasta 115 px
     * y luego ofrece desplazamiento vertical, sin estirar las filas.
     */
    _paintBookmarks(bookmarks) {
        this._clearBookmarksUI();
        let keys = Object.keys(bookmarks);
        if (keys.length === 0) {
            let info = new PopupMenu.PopupMenuItem(_("No saved favorites"), {reactive: false});
            this.menuBookmarks.menu.addMenuItem(info);
            this.favItems.push(info);
            return;
        }

        // Item estructural neutro que aloja el ScrollView.
        let scrollItem = new PopupMenu.PopupBaseMenuItem({reactive: false, activate: false});

        scrollItem.actor.add_style_class_name("wmm-favorites-scroll-item");
        scrollItem.actor.remove_all_children();

        // Contenido vertical. El padding derecho da aire a la papelera respecto al borde.
        let favBox = new St.BoxLayout({vertical: true});

        favBox.add_style_class_name("wmm-favorites-box");

        keys.forEach(name => {
            let row = new St.BoxLayout();
            row.add_style_class_name("wmm-favorite-row");

            // Nombre del preset: item de menú nativo con hover independiente.
            let nameItem = new PopupMenu.PopupMenuItem(name, {
                reactive: true,
                activate: true,
                focusOnHover: false
            });

            nameItem.actor.add_style_class_name("wmm-favorite-action");
            nameItem.connect('activate', () => {
                this._syncTimerUI(false);
                // Cargar un preset no cierra el principal: permite seguir operando.
                this._sendActionToEngine({ action: "load_bookmark", name: name, timer_force_off: true });
            });

            // Papelera: item independiente para disponer de hover y zona de clic propios.
            let deleteItem = new PopupMenu.PopupBaseMenuItem({
                reactive: true,
                activate: false,
                focusOnHover: false
            });

            deleteItem.actor.add_style_class_name("wmm-favorite-action");

            let deleteIcon = new St.Icon({
                icon_name: 'user-trash-symbolic',
                style_class: 'popup-menu-icon',
                reactive: false
            });

            deleteIcon.add_style_class_name("wmm-favorite-delete-icon");
            deleteItem.addActor(deleteIcon, {
                expand: false,
                align: St.Align.MIDDLE
            });

            deleteItem.actor.connect('button-release-event',
                (actor, event) => {
                    if (event.get_button() !== 1)
                        return false;

                    this._confirmDeleteBookmark(name, deleteItem.actor);
                    return true;
                });

            row.add(nameItem.actor, { expand: true, x_fill: true, x_align: St.Align.START });
            row.add(deleteItem.actor, { expand: false, x_fill: false });

            // IMPORTANTE: false evita repartir artificialmente la altura del ScrollView entre filas.
            favBox.add(row, { expand: false, x_fill: true });
        });

        // Altura natural hasta 115 px; después, scroll vertical automático.
        let scrollView = new St.ScrollView();
        scrollView.add_style_class_name("wmm-favorites-scroll");
        scrollView.set_policy(PolicyType.NEVER, PolicyType.AUTOMATIC);
        scrollView.add_actor(favBox);
        scrollItem.addActor(scrollView, { expand: true, span: -1 });
        this.menuBookmarks.menu.addMenuItem(scrollItem);
        this.favItems.push(scrollItem);
    }

    /** Libera el diálogo hijo antes de abrir otro o retirar el applet. */
    _destroyDeleteConfirmMenu() {
        if (!this._deleteConfirmMenu)
            return;

        const menu = this._deleteConfirmMenu;
        this._deleteConfirmMenu = null;

        if (this._mainMenu.isChildMenu(menu))
            this._mainMenu.removeChildMenu(menu);

        menu.destroy();
    }

    /**
     * FAVORITOS · confirmación con apariencia de diálogo Cinnamon.
     * Conservar su geometría, señales y cierre: comportamiento ya validado.
     */
    _confirmDeleteBookmark(name, sourceActor) {
        this._destroyDeleteConfirmMenu();

        const monitor = Main.layoutManager.findMonitorForActor(sourceActor);
        const [sourceX] = sourceActor.get_transformed_position();
        const [sourceWidth] = sourceActor.get_transformed_size();

        let orientation = St.Side.LEFT;

        // La confirmación se abre hacia el interior del monitor para no
        // invadir el monitor contiguo cuando la papelera está junto al borde.
        if (monitor &&
                sourceX + sourceWidth / 2 >
                monitor.x + monitor.width / 2) {
            orientation = St.Side.RIGHT;
        }

        const menu = new PopupMenu.PopupMenu(sourceActor, orientation);

        menu.actor.add_style_class_name("wmm-menu");
        Main.uiGroup.add_actor(menu.actor);
        menu.actor.hide();

        this._deleteConfirmMenu = menu;
        this._mainMenu.addChildMenu(menu);

        /*
         * Conservamos la composición de GNOME, pero usamos las clases
         * nativas de diálogo de Cinnamon para que el tema proporcione
         * fondo, borde, tipografía y botones reales.
         */
        const content = new St.BoxLayout({
            vertical: true,
            style_class: "dialog"
        });

        const dialogContent = new St.BoxLayout({
            vertical: true,
            style_class: "dialog-content-box"
        });

        const messageContent = new St.BoxLayout({
            vertical: true,
            style_class: "message-dialog-content"
        });

        const title = new St.Label({
            text: _("Delete preset"),
            style_class: "message-dialog-title"
        });

        const body = new St.Label({
            text: _("Delete") + ' "' + name + '"?',
            style_class: "message-dialog-description"
        });

        const buttons = new St.Widget({
            style_class: "dialog-button-box",
            layout_manager: new Clutter.BoxLayout({
                homogeneous: true,
                spacing: 12
            })
        });

        const cancelButton = new St.Button({
            label: _("Cancel"),
            style_class: "dialog-button",
            important: true,
            reactive: true,
            can_focus: true,
            x_expand: true,
            y_expand: true
        });

        const deleteButton = new St.Button({
            label: _("Delete"),
            style_class: "dialog-button",
            important: true,
            reactive: true,
            can_focus: true,
            x_expand: true,
            y_expand: true
        });

        deleteButton.add_style_pseudo_class("destructive-action");

        messageContent.add_child(title);
        messageContent.add_child(body);
        dialogContent.add_child(messageContent);

        buttons.add_child(cancelButton);
        buttons.add_child(deleteButton);

        content.add_child(dialogContent);
        content.add_child(buttons);

        menu.box.add_child(content);

        cancelButton.connect('clicked', () => { menu.close(true); });

        deleteButton.connect('clicked', () => { menu.close(true);
            this._sendActionToEngine({action: "delete_bookmark", name: name}); });

        menu.connect('open-state-changed', (currentMenu, open) => {
            if (open)
                return;

            GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
                if (this._deleteConfirmMenu === currentMenu)
                    this._destroyDeleteConfirmMenu();

                return GLib.SOURCE_REMOVE;
            });
        });

        menu.open(true);
    }

    /** PRINCIPAL/Slideshow: maestro e intervalo con sus señales. */
    _buildSlideshowMenu() {
        // SLIDESHOW · interruptor maestro, intervalo y deslizador.
        this.menuTimer = new PopupMenu.PopupSubMenuMenuItem(_("Slideshow"));
        this._isolateSubmenuLayout(this.menuTimer);
        this._mainMenu.addMenuItem(this.menuTimer);
        this.masterItem = new PopupMenu.PopupSwitchMenuItem(_("Disabled"), false);
        this.menuTimer.menu.addMenuItem(this.masterItem);

        let infoItem = new PopupMenu.PopupBaseMenuItem({ reactive: false });
        this.labelMin = new St.Label();

        let infoBox = new St.Bin({x_align: St.Align.MIDDLE});
        infoBox.child = this.labelMin;
        infoItem.addActor(infoBox, {span: -1, expand: true});

        this.menuTimer.menu.addMenuItem(infoItem);

        this.slider = new PopupMenu.PopupSliderMenuItem(0.25);

        /*
         * El tema de Cinnamon impone min-width: 15em al slider nativo.
         * Dentro del submenú ese mínimo supera el ancho ya disponible y obliga
         * al popup completo a crecer. WMM necesita que el slider se adapte al
         * ancho existente, que PopupSliderMenuItem ya sabe repartir.
         */
        this.slider._slider.add_style_class_name("wmm-slider");

        this.menuTimer.menu.addMenuItem(this.slider);

        // SLIDESHOW · las señales pertenecen a los controles que acaban de crearse.
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
    }

    _syncTimerUI(enabled) {
        if (!this.masterItem) return;

        this.masterItem.setToggleState(enabled);
        this.masterItem.label.set_text(enabled ? _("Enabled") : _("Disabled"));
        this.slider.setSensitive(enabled);
        this.slider.actor.reactive = enabled;
    }

    /** PRINCIPAL/Displays, Spanned Mode e Image Metadata. */
    _buildDisplayControls() {
        // DISPLAYS · SYNC/ASYNC, aplicación a todos o un monitor.
        this.modeSwitch = new PopupMenu.PopupSwitchMenuItem(_("Displays") + ": " + _("ASYNC (One)"), false);
        this._mainMenu.addMenuItem(this.modeSwitch);

        // SPANNED · tratamiento de imagen panorámica.
        this.spannedSwitch = new PopupMenu.PopupSwitchMenuItem(_("Spanned Mode"), false);
        this.spannedSwitch.connect('toggled', () => this._updateTimerSettings());
        this._mainMenu.addMenuItem(this.spannedSwitch);

        // IMAGE METADATA · visibilidad de información EXIF.
        this.metadataSwitch = new PopupMenu.PopupSwitchMenuItem(_("Image Metadata"), false);
        this.metadataSwitch.connect('toggled', (_item, state) => {
            // Reflejar inmediatamente el cambio mientras el Engine lo persiste.
            if (this._cachedSettings) this._cachedSettings.exif_metadata_enabled = state;
            this._sendActionToEngine({ action: "set_metadata_enabled", enabled: state });
        });
        this._mainMenu.addMenuItem(this.metadataSwitch);

        this.modeSwitch.connect('toggled', (item, state) => {
            item.label.set_text(state ? _("Displays") + ": " + _("SYNC (All)")
                : _("Displays") + ": " + _("ASYNC (One)"));
            this._updateTimerSettings();
        });
    }

    /** PRINCIPAL/Next Background: rotación y acceso al gestor de atajos. */
    _buildNextBackgroundAction() {
        /*
         * Next Background es una fila propia: activate:false evita que Cinnamon
         * cierre el menú al rotar. La etiqueta del atajo comparte una sola fila
         * y no añade columnas globales que ensanchen el popup.
         * Clic secundario: cerrar antes de abrir el gestor de atajos.
         */
        this.nextBackgroundItem = new PopupMenu.PopupBaseMenuItem({
            reactive: true,
            activate: false,
            focusOnHover: true
        });

        let nextBackgroundRow = new St.BoxLayout();

        let nextBackgroundLabel = new St.Label({text: _("Next Background")});

        this.nextBackgroundHotkeyLabel = new St.Label({
            text: "", style_class: "wmm-hotkey-label"
        });

        nextBackgroundRow.add(nextBackgroundLabel, {
            expand: true
        });

        nextBackgroundRow.add(this.nextBackgroundHotkeyLabel);

        this.nextBackgroundItem.addActor(nextBackgroundRow, {
            span: -1,
            expand: true
        });

        this.nextBackgroundItem.actor.label_actor = nextBackgroundLabel;

        this.nextBackgroundItem.actor.connect('button-release-event',
            (actor, event) => {
                const button = event.get_button();

                if (button === 1) {
                    this._requestNextBackground();
                    return true;
                }

                if (button === 3) {
                    const [x, y] = actor.get_transformed_position();
                    const [width, height] = actor.get_transformed_size();

                    this._mainMenu.close();

                    this._sendActionToEngine({
                        action: "open_keybinding",
                        x: Math.round(x + width / 2),
                        y: Math.round(y + height / 2)
                    });

                    return true;
                }

                return false;
            });

        this._nextBackgroundTooltip = new Tooltips.Tooltip(
            this.nextBackgroundItem.actor, _("Secondary click: assign a keyboard shortcut")
        );

        this._mainMenu.addMenuItem(this.nextBackgroundItem);
    }

    /** Recupera el acelerador antes de mostrar el menú y evitar un relayout. */
    _refreshNextBackgroundKeybinding() {
        if (!this.nextBackgroundItem)
            return;

        let text = "";

        try {
            const mainSettings = Gio.Settings.new("org.cinnamon.desktop.keybindings");

            const schema = "org.cinnamon.desktop.keybindings.custom-keybinding";
            const basePath = "/org/cinnamon/desktop/keybindings/custom-keybindings/";
            const fullName = "WMM - " + _("Next Background");

            for (const item of mainSettings.get_strv("custom-list")) {
                if (item === "__dummy__")
                    continue;

                const custom = Gio.Settings.new_with_path(schema, basePath + item + "/");

                if (custom.get_string("name") !== fullName)
                    continue;

                const bindings = custom.get_strv("binding");
                const binding = bindings.length > 0 ? bindings[0] : "";

                if (binding) {
                    const [keyval, modifiers] = Gtk.accelerator_parse(binding);

                    if (keyval)
                        text = Gtk.accelerator_get_label(keyval, modifiers);
                }

                break;
            }
        } catch (e) {
            global.logError("WMM: Error leyendo el atajo Next Background: " + e.message);
        }

        this.nextBackgroundHotkeyLabel.set_text(text);
    }

    // ================================================================
    // 3. MENÚ CONTEXTUAL · acciones externas y cierre (clic derecho)
    // ================================================================

    /**
     * MENÚ CONTEXTUAL · clic derecho; cada opción cierra antes de ejecutarse.
     * La reconstrucción sustituye el About/Remove nativo de Cinnamon tras bootstrap.
     * Ningún elemento del contextual se crea desde el menú principal.
     */
    _populateContextMenu() {
        this._applet_context_menu.removeAll();
        this._applet_context_menu.actor.width_request = 200;

        // SETTINGS · panel de configuración del engine.
        let itemControlPanel = new PopupMenu.PopupMenuItem(_("Settings"));
        itemControlPanel.connect('activate', () => {
            this._applet_context_menu.close();
            this._openSettingsPanel();
        });
        this._applet_context_menu.addMenuItem(itemControlPanel);

        // SYNC LIBRARY · reconciliar las fuentes y miniaturas disponibles.
        let itemSync = new PopupMenu.PopupMenuItem(_("Sync Library"));
        itemSync.connect('activate', () => {
            this._applet_context_menu.close();
            this._sendActionToEngine({ action: "sync_library" });
        });
        this._applet_context_menu.addMenuItem(itemSync);

        // INSTALL MANAGER · proceso GTK independiente del engine.
        let itemInstallManager = new PopupMenu.PopupMenuItem(_("Install Manager"));
        itemInstallManager.connect('activate', () => {
            this._applet_context_menu.close();
            this._launchIndependentTool(
                this.appDir + "/wmm_platform/shell/installer/wmm-install_manager.py");
        });
        this._applet_context_menu.addMenuItem(itemInstallManager);

        // DEBUG LOG VIEWER · visor independiente de diagnóstico.
        let itemDebugLog = new PopupMenu.PopupMenuItem(_("Debug Log Viewer"));
        itemDebugLog.connect('activate', () => {
            this._applet_context_menu.close();
            this._launchIndependentTool(this.appDir + "/python/debug_log_viewer.py");
        });
        this._applet_context_menu.addMenuItem(itemDebugLog);

        // HELP · documentación de WMM mediante el engine.
        let itemHelp = new PopupMenu.PopupMenuItem(_("Help"));
        itemHelp.connect('activate', () => {
            this._applet_context_menu.close();
            this._sendActionToEngine({ action: "open_help" });
        });
        this._applet_context_menu.addMenuItem(itemHelp);

        this._applet_context_menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        // ABOUT · información, licencia e historia del proyecto.
        let itemAbout = new PopupMenu.PopupMenuItem(_("About") + " WMM Manager");
        itemAbout.connect('activate', () => {
            this._applet_context_menu.close();
            this._sendActionToEngine({ action: "open_about" });
        });
        this._applet_context_menu.addMenuItem(itemAbout);

        // EXIT · retirar el applet mediante AppletManager, sin confirmación nativa.
        // Conserva on_applet_removed_from_panel(), que solicita Shutdown al engine.
        let itemExit = new PopupMenu.PopupMenuItem(_("Exit") + " WMM");
        itemExit.connect('activate', () => {
            this._applet_context_menu.close();
            AppletManager._removeAppletFromPanel(this._uuid, this.instance_id);
        });
        this._applet_context_menu.addMenuItem(itemExit);
    }

    /** El panel se solicita al engine; no se crea desde Cinnamon. */
    _openSettingsPanel() { this._sendActionToEngine({ action: "open_panel" }); }

    /** Abre herramientas GTK independientes sin gestionar su ciclo de vida. */
    _launchIndependentTool(path) {
        try { Util.spawn(["python3", path]); }
        catch (e) { global.logError("WMM Tool Launch Error (" + path + "): " + e.message); }
    }

    // ================================================================
    // 4. SINCRONIZACIÓN · configuración, favoritos y persistencia
    // ================================================================

    /** Aplica el snapshot global sin persistirlo ni recrear widgets. */
    _applySettingsToUI(config) {
        if (!this.masterItem || !this.slider) return;

        this._currentMaxInterval = config.slideshow_max_interval || 60;

        let isEnabled = config.slideshow_enabled;
        let isSync = config.slideshow_mode === "sync";
        let isFavSlideshow = config.slideshow_bookmark || false;
        let isSpanned = config.spanned_enabled || false;
        let isMetadataEnabled = Boolean(config.exif_metadata_enabled);

        this._syncTimerUI(isEnabled);

        this.modeSwitch.setToggleState(isSync);
        this.modeSwitch.label.set_text(isSync ? _("Displays") + ": " + _("SYNC (All)") : _("Displays") + ": " + _("ASYNC (One)"));

        this.favRotationSwitch.setToggleState(isFavSlideshow);

        let ratio = config.slideshow_interval / this._currentMaxInterval;
        this.slider.setValue(ratio);
        this.labelMin.set_text(config.slideshow_interval + " " + _("minutes"));

        this.spannedSwitch.setToggleState(isSpanned);
        this.metadataSwitch.setToggleState(isMetadataEnabled);
    }

    /**
     * Al abrir: mostrar la caché inmediatamente y reconciliarla en asíncrono.
     * Un JSON parcial no debe reemplazar el último estado válido.
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
                        cached.spanned_enabled !== config.spanned_enabled ||
                        cached.exif_metadata_enabled !== config.exif_metadata_enabled)

                    { this._applySettingsToUI(config); this._cachedSettings = config; }
                }

                catch (e) { /* Escritura parcial o JSON todavía incompleto: se ignora este evento. */}
            });

            // 3. Cargar favoritos dinámicos.
            this._refreshBookmarks();

        }

        catch (e) { global.logError("WMM Refresh Error: " + e.message); }
    }

    /** Reconciliación asíncrona de favoritos: repintar solo si cambian. */
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

    /** Escribe una petición coherente de Slideshow/Favorites/Displays/Spanned. */
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

    // ================================================================
    // 5. ENGINE Y ESTADO · transporte de órdenes y rotación manual
    // ================================================================

    /** Canal común de órdenes; la lógica pertenece al engine, no al applet. */
    _sendActionToEngine(command) {
        try {
            let cmd = JSON.stringify(command);
            Util.spawn(["python3", this.appDir + "/python/send_command.py", cmd]);
            return true;
        }

        catch (e) {
            global.logError("WMM Send Error (" +
                (command.action || "unknown") + "): " + e.message);
            return false;
        }
    }

    /** Rotación manual con barrera local hasta recibir el busy del engine. */
    _requestNextBackground() {
        if (this._motorBusy) {
            this.set_applet_icon_name("view-refresh");
            return;
        }

        /*
         * Cerramos localmente la carrera entre el gesto y busy=true del engine.
         * El propio engine y send_command.py conservan además sus barreras.
         */
        this.set_applet_icon_name("view-refresh");
        this._ignoreNextBusy = true;
        this._setMotorBusy(true);

        if (!this._sendActionToEngine({ action: "force_rotation" })) {
            this._ignoreNextBusy = false;
            this._setMotorBusy(false);
        }
    }

    /**
     * ICONO NORMAL · Identidad gráfica propia de WMM.
     *
     * El instalador coloca icon.png junto a applet.js. metadata.path,
     * conservado en this.appletPath, identifica ese directorio real.
     *
     * Si el recurso no está disponible, utilizar el icono del tema.
     * El estado busy mantiene independientemente su icono view-refresh.
     */
    _setNormalAppletIcon() {
        const iconPath = this.appletPath + "/icon.png";

        if (GLib.file_test(iconPath, GLib.FileTest.IS_REGULAR)) {
            try {
                this.set_applet_icon_path(iconPath);
                return;
            } catch (error) {
                global.logError("WMM Icon Error: " + error.message);
            }
        }

        /*
         * FALLBACK DEL ICONO NORMAL
         *
         * A diferencia del icono provisional del constructor, aquí ya
         * conocemos la ruta de icon.png. Sólo utilizamos video-display
         * si el archivo no existe o no ha podido cargarse.
         *
         * Este respaldo también se aplica al recuperar el estado normal
         * después de una operación busy.
         */
        this.set_applet_icon_name("video-display");
    }

    /** Busy cambia la apariencia sin desactivar el clic secundario del atajo. */
    _setMotorBusy(busy) {
        /*
         * Busy bloquea únicamente la rotación. Next Background conserva
         * reactividad porque el clic secundario sigue abriendo la configuración
         * del atajo incluso mientras el engine está ocupado.
         */
        this._motorBusy = Boolean(busy);

        if (this.nextBackgroundItem) {
            this.nextBackgroundItem.actor.change_style_pseudo_class(
                "insensitive",
                this._motorBusy
            );
        }

        if (this._motorBusy) {
            if (!this._ignoreNextBusy)
                this.set_applet_icon_name("view-refresh");
        } else {
            this._ignoreNextBusy = false;
            this._setNormalAppletIcon();
        }
    }

    /** Refresca busy al recibir eventos del archivo de estado; sin polling. */
    _updateIconFromStatus() {
        let file = Gio.File.new_for_path(GLib.get_user_cache_dir() + "/wmm/engine_status.json");
        if (!file.query_exists(null)) return;

        file.load_contents_async(null, (statusFile, res) => {
            try {
                let [success, contents] = statusFile.load_contents_finish(res);
                if (!success || contents.length === 0) return;
                let status = JSON.parse(contents);
                this._setMotorBusy(status.busy);
            }

            catch (e) {/* JSON a medias: ignorar hasta el siguiente evento. */}
        });
    }

    // ================================================================
    // 6. EVENTOS DEL APPLET · clics, convivencia de menús y retirada
    // ================================================================

    _onButtonPressEvent(actor, event) {
        /*
         * El menú principal es propio de WMM, mientras que el contextual sigue
         * abriéndose mediante el lifecycle nativo de Cinnamon. Al recibir botón
         * derecho se cierra primero el principal para que ambos nunca coexistan.
         */
        if (event.get_button() === 3 && this._mainMenu.isOpen)
            this._mainMenu.close();

        return super._onButtonPressEvent(actor, event);
    }

    /** Clic izquierdo: refrescar atajo antes de abrir y alternar principal. */
    on_applet_clicked(event) {
        /*
         * El acelerador debe formar parte de la geometría inicial del popup.
         * Leerlo después de abrir obliga a Cinnamon a esperar al siguiente
         * relayout —normalmente provocado por el hover— para mostrarlo.
         */
        if (!this._mainMenu.isOpen)
            this._refreshNextBackgroundKeybinding();

        this._mainMenu.toggle();
    }

    /** Clic central: rotar sin abrir ninguno de los menús. */
    on_applet_middle_clicked(event) {
        this._requestNextBackground();
    }

    /** Exit: retirar confirmación y watcher; pedir Shutdown sin autoarranque. */
    on_applet_removed_from_panel() {
        this._destroyDeleteConfirmMenu();

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

}

function main(metadata, orientation, panel_height, instance_id) {
    return new WMMApplet(metadata, orientation, panel_height, instance_id);
}
