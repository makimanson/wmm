/*
* SPDX-FileCopyrightText: 2026 makimanson
* SPDX-License-Identifier: GPL-3.0-or-later
*
* extension.js: WMM Extension - GNOME Shell Edition
* Panel indicator for Wallpaper Multi-Monitor Manager.
*/

import Gio from 'gi://Gio';
import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import St from 'gi://St';
import Meta from 'gi://Meta';
import Gettext from 'gettext';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import * as Slider from 'resource:///org/gnome/shell/ui/slider.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';

// Mutter's window/workarea information is only available from inside GNOME Shell.
// Expose the minimum interface required by gnome.py to query the usable area
// of the monitor containing a WMM window.
const workareaBusName = 'org.maki.wmm.Gnome';
const workareaObjectPath = '/org/maki/wmm/Gnome';

const workareaInterface = `
<node>
  <interface name="org.maki.wmm.Gnome">
    <method name="GetWindowAvailableArea">
      <arg name="pid" type="u" direction="in"/>
      <arg name="area" type="s" direction="out"/>
    </method>
    <method name="PurgeBackgroundCache">
      <arg name="path" type="s" direction="in"/>
      <arg name="purged" type="b" direction="out"/>
    </method>
  </interface>
</node>`;

// ── Translations ──────────────────────────────────────────
// bindtextdomain() is safe before the catalog exists. The first dgettext()
// lookup is delayed until the engine has completed its initial setup,
// because a failed lookup is cached for the lifetime of GNOME Shell.
Gettext.bindtextdomain('wmm@maki', GLib.get_user_data_dir() + '/locale');

function _(text) {
    return Gettext.dgettext('wmm@maki', text);
}

export default class WMMExtension {
    constructor(metadata) {
        this.metadata = metadata;
        this.appletPath = metadata.path;
        this.enginePath = this.appletPath + '/python/main.py';
        this.commandsPath = this.appletPath + '/data/commands.json';
        this.settingsPath = this.appletPath + '/data/settings.json';
        this.bookmarksPath = this.appletPath + '/data/bookmarks.json';
        this._cachedSettings = null;
        this._cachedBookmarks = null;
        this._currentMaxInterval = 60;
        this.favItems = [];
        this._keepMenuOpen = false;
        this._isForcedOpen = false;
        this._button = null;
        this._menu = null;
        this._workareaDbus = null;
        this._workareaOwnerId = 0;
    }

    enable() {
        // Start the engine
        GLib.spawn_async(null, ["python3", this.enginePath], null, GLib.SpawnFlags.SEARCH_PATH, null);

        // Panel button
        this._button = new PanelMenu.Button(0.0, 'WMM', false);

        let icon = new St.Icon({
            icon_name: 'video-display',
            style_class: 'system-status-icon'
        });

        this._button.add_child(icon);
        Main.panel.addToStatusArea('wmm-indicator', this._button);

        let cssFile = Gio.File.new_for_path(this.metadata.path + '/wmm_platform/shell/gnome/stylesheet.css');
        St.ThemeContext.get_for_stage(global.stage).get_theme().load_stylesheet(cssFile);

        // Export the workarea bridge used by the GNOME platform backend.
        // The query itself must run inside GNOME Shell because Meta.Window belongs
        // to Mutter's live compositor context.
        this._workareaDbus = Gio.DBusExportedObject.wrapJSObject(workareaInterface, this);
        this._workareaDbus.export(Gio.DBus.session, workareaObjectPath);

        this._workareaOwnerId = Gio.bus_own_name_on_connection(
            Gio.DBus.session,
            workareaBusName,
            Gio.BusNameOwnerFlags.NONE,
            null,
            null
        );

        /*
         * The engine compiles translations during its initial setup before
         * acquiring org.maki.wmm. Wait for that point before the first gettext
         * lookup so a missing catalog is never cached by GNOME Shell.
         */
        this._engineWatchId = Gio.bus_watch_name_on_connection(
            Gio.DBus.session,
            'org.maki.wmm',
            Gio.BusNameWatcherFlags.NONE,
            () => {
                if (this._engineWatchId) {
                    Gio.bus_unwatch_name(this._engineWatchId);
                    this._engineWatchId = 0;
                }

                this._initializeTranslatedUI();
            },
            null
        );
    }

    _initializeTranslatedUI() {
        if (!this._button || this._menu)
            return;

        // From this point the translation catalog is already available.
        this._button.container.tooltip_text = 'WMM: ' + _('Wallpaper Multi-Monitor Manager') + '\n' +
            _('Click action') + ': ' + _('Next Background') + '\n' +
            _('Secondary Click') + ': ' + _('Context Menu');

        this._menu = this._button.menu;
        this._populateMenu();

        this._menu.connect('open-state-changed', (menu, open) => {
            if (!open && this._keepMenuOpen) {
                this._keepMenuOpen = false;
                GLib.idle_add(GLib.PRIORITY_DEFAULT, () => {
                    this._isForcedOpen = true;
                    menu.open();
                    this._refreshSettingsFromDisk(false);
                    return false;
                });
            }
        });
    }

    disable() {
        /*
         * GNOME Shell puede descargar temporalmente una extensión sin que el
         * usuario la haya deshabilitado. Solo cerramos WMM cuando el UUID ha
         * desaparecido realmente de la lista de extensiones habilitadas.
         */
        const shellSettings = new Gio.Settings({ schema_id: 'org.gnome.shell' });
        const shutdownWMM = !shellSettings.get_strv('enabled-extensions').includes(this.metadata.uuid);
        // Stop a pending engine watcher if the extension is unloaded before startup completes.
        if (this._engineWatchId) {
            Gio.bus_unwatch_name(this._engineWatchId);
            this._engineWatchId = 0;
        }

        // Remove the workarea bridge together with the GNOME Shell integration.
        if (this._workareaDbus) {
            this._workareaDbus.unexport();
            this._workareaDbus = null;
        }

        if (this._workareaOwnerId) {
            Gio.bus_unown_name(this._workareaOwnerId);
            this._workareaOwnerId = 0;
        }

        /*
         * Una deshabilitación explícita de la extensión representa "Salir de WMM".
         * Se utiliza el Shutdown D-Bus normal del engine y se impide la
         * autoactivación para no arrancarlo accidentalmente si ya estaba detenido.
         */
        if (shutdownWMM) {
            Gio.DBus.session.call(
                'org.maki.wmm',
                '/org/maki/wmm',
                'org.maki.wmm',
                'Shutdown',
                null,
                null,
                Gio.DBusCallFlags.NO_AUTO_START,
                1000,
                null,
                (connection, result) => {
                    try {
                        connection.call_finish(result);
                    } catch (e) {
                        // El engine puede haber terminado ya; no requiere recuperación.
                    }
                }
            );
        }

        // Clean up the UI
        this._destroyUI();

        if (this._button) {
            this._button.destroy();
            this._button = null;
        }
    }

    /**
     * Return the usable area of the monitor containing the window identified by PID.
     *
     * Mutter already resolves which monitor owns the window and calculates its
     * current workarea, including desktop reservations that GDK does not expose
     * reliably under GNOME/Wayland.
     *
     * The result is returned as "x,y,width,height". An empty string means that
     * Mutter could not find a window for the requested PID.
     */
    GetWindowAvailableArea(pid) {
        const window = global.display.list_all_windows().find(window => window.get_pid() === pid);

        if (!window)
            return '';

        const area = window.get_work_area_current_monitor();
        return `${area.x},${area.y},${area.width},${area.height}`;
    }

    PurgeBackgroundCache(path) {
        try {
            const file = Gio.File.new_for_path(path);
            Meta.BackgroundImageCache.get_default().purge(file);
            return true;
        } catch (e) {
            log('WMM background cache purge ERROR: ' + e.message);
            return false;
        }
    }
    // ── Menu construction (same as Cinnamon) ──────────────
    _populateMenu() {
        // this._menu ya está creado en enable()

        // Next Wallpaper — primera opción del menú
        let rotateItem = new PopupMenu.PopupMenuItem(_('Next Background'));
        rotateItem.connect('activate', () => {
            this._keepMenuOpen = true;
            this._sendActionToEngine({ action: 'force_rotation' });
        });
        this._menu.addMenuItem(rotateItem);
        this._menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        // Settings
        let settingsItem = new PopupMenu.PopupMenuItem('WMM ' + _('Settings'));
        settingsItem.connect('activate', () => this._openSettingsPanel());
        this._menu.addMenuItem(settingsItem);
        this._menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        // Bookmarks
        this.menuBookmarks = new PopupMenu.PopupSubMenuMenuItem(_('Favorites'));
        this.menuBookmarks.menu.actor.add_style_class_name('wmm-submenu');
        this._menu.addMenuItem(this.menuBookmarks);

        this.favRotationSwitch = new PopupMenu.PopupSwitchMenuItem(_('Favorites Only'), false);
        this.favRotationSwitch.add_style_class_name('wmm-menu-idle');

        this.favRotationSwitch.connect('notify::hover', () => {
            if (this.favRotationSwitch.hover)
                this.favRotationSwitch.remove_style_class_name('wmm-menu-idle');
            else
                this.favRotationSwitch.add_style_class_name('wmm-menu-idle');
        });

        this.favRotationSwitch.connect('toggled', (item, state) => {
            this._keepMenuOpen = true;
            if (state && !this.masterItem.state) this._syncTimerUI(true);
            this._updateTimerSettings();
        });
        this.menuBookmarks.menu.addMenuItem(this.favRotationSwitch);
        this.menuBookmarks.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        let addBookmarkItem = new PopupMenu.PopupBaseMenuItem({ activate: false, reactive: false });
        addBookmarkItem.add_style_class_name('wmm-flat-row');
        let addBookmarkButton = new St.Button({
            label: _('Add Preset Favorite'),
            style_class: 'button',
            reactive: true,
            can_focus: true,
            track_hover: true
        });
        addBookmarkButton.connect('clicked', () => {
            this._sendActionToEngine({ action: "add_bookmark" });
        });
        addBookmarkItem.add_child(addBookmarkButton);
        this.menuBookmarks.menu.addMenuItem(addBookmarkItem);

        this.menuBookmarks.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        // Timer
        this.menuTimer = new PopupMenu.PopupSubMenuMenuItem(_('Slideshow'));
        this._menu.addMenuItem(this.menuTimer);

        // Switch maestro
        this.masterItem = new PopupMenu.PopupSwitchMenuItem(_('Disabled'), false);
        this.masterItem.add_style_class_name('wmm-menu-idle');

        this.masterItem.connect('notify::hover', () => {
            if (this.masterItem.hover)
                this.masterItem.remove_style_class_name('wmm-menu-idle');
            else
                this.masterItem.add_style_class_name('wmm-menu-idle');
        });

        this.masterItem.connect('toggled', (item, state) => {
            this._keepMenuOpen = true;
            item.label.set_text(state ? _('Enabled') : _('Disabled'));
            this._syncTimerUI(state);
            this._updateTimerSettings();
        });
        this.menuTimer.menu.addMenuItem(this.masterItem);
        this.menuTimer.menu.actor.add_style_class_name('wmm-submenu');
        // --- Selector de intervalo ---
        let intervalItem = new PopupMenu.PopupBaseMenuItem({ activate: false });
        intervalItem.add_style_class_name('wmm-flat-row');
        let intervalBox = new St.BoxLayout({ vertical: true, x_expand: true, style: 'spacing: 4px;' });
        this._currentInterval = 15;
        this.intervalLabel = new St.Label({
            text: this._currentInterval + ' ' + _('minutes'),
            x_expand: true,
            x_align: Clutter.ActorAlign.CENTER
        });
        let ratio = (this._currentInterval - 1) / (this._currentMaxInterval - 1);
        this.intervalSlider = new Slider.Slider(ratio);

        this.intervalSlider.connect('notify::value', () => {
            let interval = 1 + Math.round(this.intervalSlider.value * (this._currentMaxInterval - 1));
            this._currentInterval = interval;
            this.intervalLabel.set_text(this._currentInterval + ' ' + _('minutes'));
        });
        this.intervalSlider.connect('drag-end', () => {
            if (this.masterItem && this.masterItem.state)
                this._updateTimerSettings();
        });
        intervalBox.add_child(this.intervalLabel);
        intervalBox.add_child(this.intervalSlider);
        intervalItem.add_child(intervalBox);
        this.menuTimer.menu.addMenuItem(intervalItem);

        // Switch modo sync/async
        this.modeSwitch = new PopupMenu.PopupSwitchMenuItem(_('Displays') + ': ' + _('ASYNC (One)'), false);
        this.modeSwitch.connect('toggled', (item, state) => {
            this._keepMenuOpen = true;
            item.label.set_text(state ? _('Displays') + ': ' + _('SYNC (All)') : _('Displays') + ': ' + _('ASYNC (One)'));
            this._updateTimerSettings();
        });
        this._menu.addMenuItem(this.modeSwitch);

        // Switch spanned
        this.spannedSwitch = new PopupMenu.PopupSwitchMenuItem(_('Spanned Mode'), false);
        this.spannedSwitch.connect('toggled', () => {
            this._keepMenuOpen = true;
            this._updateTimerSettings();
        });
        this._menu.addMenuItem(this.spannedSwitch);

        // Footer
        this._menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        let syncItem = new PopupMenu.PopupMenuItem(_('Sync Library'));
        syncItem.connect('activate', () => this._sendActionToEngine({ action: 'sync_library' }));
        this._menu.addMenuItem(syncItem);

        let helpItem = new PopupMenu.PopupMenuItem(_('Help'));
        helpItem.connect('activate', () => {
            this._sendActionToEngine({ action: "open_help" });
        });
        this._menu.addMenuItem(helpItem);

        // Exit WMM
        //
        // La salida se realiza deshabilitando la propia extensión. De este modo,
        // tanto esta opción como el gestor de extensiones de GNOME recorren
        // exactamente el mismo lifecycle y terminan en disable().
        this._menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        let exitItem = new PopupMenu.PopupMenuItem(_('Exit') + ' WMM');
        exitItem.connect('activate', () => {
            GLib.spawn_async(
                null,
                ['gnome-extensions', 'disable', this.metadata.uuid],
                null,
                GLib.SpawnFlags.SEARCH_PATH,
                null
            );
        });
        this._menu.addMenuItem(exitItem);

        this._menuOpenSignalId = this._menu.connect('open-state-changed', (menu, open) => {
            if (open) {
                if (this._isForcedOpen) {
                    this._isForcedOpen = false;
                    this._refreshSettingsFromDisk(false);
                } else {
                    this._refreshSettingsFromDisk();
                }
            }
        });
    }

    _syncTimerUI(enabled) {
        if (!this.masterItem) return;

        this.masterItem.setToggleState(enabled);
        this.masterItem.label.set_text(enabled ? _('Enabled') : _('Disabled'));

        if (this.intervalSlider) {
            this.intervalSlider.reactive = enabled;
            this.intervalSlider.can_focus = enabled;
            this.intervalSlider.opacity = enabled ? 255 : 128;
        }

        if (this.intervalLabel)
            this.intervalLabel.opacity = enabled ? 255 : 128;
    }

    _applySettingsToUI(config) {
        if (!this.masterItem || !this.intervalLabel || !this.intervalSlider) return;
        this._currentMaxInterval = config.slideshow_max_interval || 60;
        let isEnabled = config.slideshow_enabled;
        let isSync = (config.slideshow_mode === 'sync');
        let isFavSlideshow = config.slideshow_bookmark || false;

        this._syncTimerUI(isEnabled);
        this.modeSwitch.setToggleState(isSync);
        this.modeSwitch.label.set_text(isSync ? _('Displays') + ': ' + _('SYNC (All)') : _('Displays') + ': ' + _('ASYNC (One)'));
        this.favRotationSwitch.setToggleState(isFavSlideshow);

        this._currentInterval = config.slideshow_interval || 15;
        let ratio = (this._currentInterval - 1) / (this._currentMaxInterval - 1);
        this.intervalSlider.value = ratio;
        this.intervalLabel.set_text(this._currentInterval + ' ' + _('minutes'));

        let isSpanned = config.spanned_enabled || false;
        this.spannedSwitch.setToggleState(isSpanned);
    }

    _clearBookmarksUI() {
        this.favItems.forEach(item => item.destroy());
        this.favItems = [];
    }

    _paintBookmarks(bookmarks) {
        this._clearBookmarksUI();

        let keys = Object.keys(bookmarks);
        log('WMM bookmarks: ' + keys.length + ' presets found');

        if (keys.length === 0) {
            let info = new PopupMenu.PopupMenuItem(_('No saved favorites'), { reactive: false });
            this.menuBookmarks.menu.addMenuItem(info);
            this.favItems.push(info);
            return;
        }

        let section = new PopupMenu.PopupMenuSection();

        keys.forEach(name => {
            let rowItem = new PopupMenu.PopupBaseMenuItem({
                reactive: false,
                can_focus: false,
            });
            rowItem.add_style_class_name('wmm-flat-row');
            rowItem.set_style('padding: 2px 6px;');

            let row = new St.BoxLayout({
                x_expand: true,
                style: 'spacing: 4px; padding: 0;'
            });

            // Botón del preset
            let nameBtn = new St.Button({
                reactive: true,
                can_focus: true,
                track_hover: true,
                x_expand: true,
                style_class: 'popup-menu-item wmm-preset-button wmm-preset-idle',
            });

            nameBtn.connect('notify::hover', () => {
                if (nameBtn.hover)
                    nameBtn.remove_style_class_name('wmm-preset-idle');
                else
                    nameBtn.add_style_class_name('wmm-preset-idle');
            });

            let nameLabel = new St.Label({
                text: name,
                x_expand: true,
                style: 'overflow: hidden; white-space: nowrap; text-overflow: ellipsis;'
            });

            nameBtn.set_child(nameLabel);

            nameBtn.connect('clicked', () => {
                this._keepMenuOpen = true;
                this._syncTimerUI(false);
                this._sendActionToEngine({
                    action: 'load_bookmark',
                    name: name,
                    timer_force_off: true
                });
            });

            // Botón de eliminar
            let deleteBtn = new St.Button({
                reactive: true,
                can_focus: true,
                track_hover: true,
                style_class: 'popup-menu-item wmm-preset-button wmm-preset-idle',
            });

            deleteBtn.connect('notify::hover', () => {
                if (deleteBtn.hover)
                    deleteBtn.remove_style_class_name('wmm-preset-idle');
                else
                    deleteBtn.add_style_class_name('wmm-preset-idle');
            });

            deleteBtn.set_width(28);

            let deleteIcon = new St.Icon({
                icon_name: 'user-trash-symbolic',
                style_class: 'popup-menu-icon',
                icon_size: 16,
                reactive: false
            });

            deleteBtn.set_child(deleteIcon);

            deleteBtn.connect('clicked', () => {
                this._confirmDeleteBookmark(name);
                this._button.menu.close();
            });

            row.add_child(nameBtn);
            row.add_child(deleteBtn);

            rowItem.add_child(row);
            section.addMenuItem(rowItem);
        });

        let scrollView = new St.ScrollView({
            hscrollbar_policy: St.PolicyType.NEVER,
            vscrollbar_policy: St.PolicyType.AUTOMATIC,
            style: 'border: none; background-color: transparent; padding: 0; margin: 0;'
        });

        scrollView.set_size(200, Math.min(keys.length * 30, 90));

        if (typeof scrollView.add_actor === 'function') {
            scrollView.add_actor(section.actor);
        } else {
            scrollView.add_child(section.actor);
        }
        this.menuBookmarks.menu.box.add_child(scrollView);

        this.favItems.push(scrollView);
    }
    _refreshSettingsFromDisk(forceRefresh = true) {
        // 1. Aplicar caché si existe (apertura instantánea)
        if (this._cachedSettings) {
            this._applySettingsToUI(this._cachedSettings);
        }
        if (this._cachedBookmarks) {
            this._paintBookmarks(this._cachedBookmarks);
        } else {
            this._clearBookmarksUI();
        }

        // 2. Cargar Settings Globales de forma asíncrona (solo si no es reapertura forzada)
        if (forceRefresh) {
            let settingsFile = Gio.File.new_for_path(this.settingsPath);
            if (!settingsFile.query_exists(null)) {
                this._refreshBookmarks(); // intenta cargar bookmarks aunque settings no exista
                return;
            }
            settingsFile.load_contents_async(null, (file, res) => {
                try {
                    let [s, content] = file.load_contents_finish(res);
                    if (!s || content.length === 0) return;
                    let config;
                    try {
                        config = JSON.parse(new TextDecoder().decode(content)).global;
                    } catch (e) {
                        return;
                    }
                    if (!config) return;

                    // Comparar con caché: si no cambió, no tocamos la UI
                    let cached = this._cachedSettings;
                    if (!cached ||
                        cached.slideshow_enabled !== config.slideshow_enabled ||
                        cached.slideshow_interval !== config.slideshow_interval ||
                        cached.slideshow_mode !== config.slideshow_mode ||
                        cached.slideshow_bookmark !== config.slideshow_bookmark ||
                        cached.spanned_enabled !== config.spanned_enabled ||
                        cached.debug_mode !== config.debug_mode) {

                        this._applySettingsToUI(config);
                        this._cachedSettings = config;
                    }
                } catch (e) {
                    // ignorar errores de parseo
                }
            });
        }

        // 3. Cargar Favoritos Dinámicos (async)
        this._refreshBookmarks();
    }

    _refreshBookmarks() {
        let bookmarksFile = Gio.File.new_for_path(this.bookmarksPath);
        if (!bookmarksFile.query_exists(null)) {
            this._clearBookmarksUI();
            return;
        }
        bookmarksFile.load_contents_async(null, (file, res) => {
            try {
                let [s, content] = file.load_contents_finish(res);
                if (!s || content.length === 0) {
                    this._clearBookmarksUI();
                    return;
                }
                let bookmarks;
                try {
                    bookmarks = JSON.parse(new TextDecoder().decode(content));
                } catch (e) {
                    this._clearBookmarksUI();
                    return;
                }

                // Comparar con caché: si no cambió, no repintar
                let cached = this._cachedBookmarks;
                if (cached && JSON.stringify(cached) === JSON.stringify(bookmarks)) {
                    return; // sin cambios, no tocamos la UI
                }

                this._cachedBookmarks = bookmarks;
                this._paintBookmarks(bookmarks);
            } catch (e) {
                log('WMM bookmarks ERROR: ' + e.message);
                log('WMM bookmarks STACK: ' + e.stack);
                this._clearBookmarksUI();
            }
        });
    }

    _confirmDeleteBookmark(name) {
        let args = ['--question', '--title=' + _('Delete favorite'), '--text=' + _('Delete') + ' "' + name + '"?', '--width=200'];
        try {
            let proc = new Gio.Subprocess({ argv: ['zenity'].concat(args), flags: Gio.SubprocessFlags.NONE });
            proc.init(null);
            proc.wait_async(null, (proc, result) => {
                try {
                    proc.wait_finish(result);
                    if (proc.get_exit_status() === 0)
                        this._sendActionToEngine({ action: 'delete_bookmark', name: name });
                } catch (e) { log('WMM zenity: ' + e.message); }
            });
        } catch (e) {
            log('WMM zenity launch: ' + e.message);
        }
    }

    _updateTimerSettings() {
        // Actualizar el caché inmediatamente para que la UI no revierta al reabrir el menú
        if (!this._cachedSettings) this._cachedSettings = {};
        this._cachedSettings.slideshow_enabled = this.masterItem.state;
        this._cachedSettings.slideshow_interval = this._currentInterval;
        this._cachedSettings.slideshow_mode = this.modeSwitch.state ? 'sync' : 'async';
        this._cachedSettings.slideshow_bookmark = this.favRotationSwitch.state;
        this._cachedSettings.spanned_enabled = this.spannedSwitch.state;

        this._sendActionToEngine({
            action: 'update_timer_settings',
            enabled: this.masterItem.state,
            interval: this._currentInterval,
            mode: this.modeSwitch.state ? 'sync' : 'async',
            slideshow_bookmark: this.favRotationSwitch.state,
            spanned_enabled: this.spannedSwitch.state
        });
    }

    _sendActionToEngine(command) {
        try {
            let cmd = JSON.stringify(command);
            GLib.spawn_async(null, ["python3", this.appletPath + "/python/send_command.py", cmd], null, GLib.SpawnFlags.SEARCH_PATH, null);
        } catch (e) {
            log('WMM send: ' + e.message);
        }
    }

    _openSettingsPanel() {
        this._sendActionToEngine({ action: "open_panel" });
    }

    _destroyUI() {

        // Desconectar señal del menú
        if (this._menu && this._menuOpenSignalId) {
            this._menu.disconnect(this._menuOpenSignalId);
            this._menuOpenSignalId = null;
        }

        // Destruir los switches y liberar referencias
        if (this.masterItem) {
            this.masterItem.destroy();
            this.masterItem = null;
        }
        if (this.favRotationSwitch) {
            this.favRotationSwitch.destroy();
            this.favRotationSwitch = null;
        }
        if (this.modeSwitch) {
            this.modeSwitch.destroy();
            this.modeSwitch = null;
        }
        if (this.spannedSwitch) {
            this.spannedSwitch.destroy();
            this.spannedSwitch = null;
        }

        // Destruir submenús
        if (this.menuBookmarks) {
            this.menuBookmarks.destroy();
            this.menuBookmarks = null;
        }
        if (this.menuTimer) {
            this.menuTimer.destroy();
            this.menuTimer = null;
        }

        // Destruir etiquetas y otros widgets
        if (this.intervalLabel) {
            this.intervalLabel.destroy();
            this.intervalLabel = null;
        }

        if (this._masterLabel) {
            this._masterLabel.destroy();
            this._masterLabel = null;
        }
        if (this._modeLabel) {
            this._modeLabel.destroy();
            this._modeLabel = null;
        }

        // Destruir elementos de favoritos
        this.favItems.forEach(item => item.destroy());
        this.favItems = [];

        // Destruir menú si no se hizo ya
        if (this._menu) {
            this._menu.destroy();
            this._menu = null;
        }
    }
}
