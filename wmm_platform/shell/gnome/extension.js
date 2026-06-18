/**
 * WMM Extension - GNOME Shell Edition
 * Panel indicator for Wallpaper Multi-Monitor Manager.
 */

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';

// ── Translations ──────────────────────────────────────────
const Gettext = imports.gettext;
Gettext.bindtextdomain('wmm@maki', GLib.get_user_data_dir() + '/locale');
Gettext.bindtextdomain('gnome-shell', '/usr/share/locale');

function __(text) {
    let translated = Gettext.dgettext('wmm@maki', text);
    if (translated !== text) return translated;
    return Gettext.dgettext('gnome-shell', text);
}

export default class WMMExtension {
    constructor(metadata) {
        this.metadata = metadata;
        this.appletPath = metadata.path;
        this.enginePath = this.appletPath + '/python/main.py';
        this.commandsPath = this.appletPath + '/data/commands.json';
        this.settingsPath = this.appletPath + '/data/settings.json';
        this.bookmarksPath = this.appletPath + '/data/bookmarks.json';

        this._currentMaxInterval = 60;
        this.favItems = [];
        this._button = null;
        this._menu = null;
        this._last_click_time = 0;
        this._icon_restore_timeout = 0;        

        // Start the engine
        GLib.spawn_command_line_async('python3 ' + this.enginePath);
    }

    enable() {
        // Panel button (importación correcta de PanelMenu)
        this._button = new PanelMenu.Button(0.0, 'WMM', false);
        let icon = new St.Icon({
            icon_name: 'video-display',
            style_class: 'system-status-icon'
        });
        this._button.add_child(icon);
        
        // Tooltip en el botón (volvemos a lo que originalmente funcionó sin error)
        this._button.container.tooltip_text = 'WMM: ' + __('Wallpaper Multi-Monitor Manager') + '\n' +
            __('Click action') + ': ' + __('Next Background') + '\n' +
            __('Secondary Click') + ': ' + __('Context Menu');
        
        // Construir el menú (usando el menú del botón)
        this._menu = this._button.menu;
        this._populateMenu();

        // Desactivar el gestor de clic interno para evitar que el menú se abra con clic izquierdo
        this._button._clickGesture.set_enabled(false);
        this._button.connect('button-press-event', (actor, event) => {
            if (event.get_button() === 1) { // Botón izquierdo
                let now = Date.now();
                let cooldown = 1000; // milisegundos

                // Si está en cooldown, mostrar feedback y salir
                if (this._last_click_time && (now - this._last_click_time) < cooldown) {
                    this._button.get_children().forEach(child => {
                        if (child instanceof St.Icon) {
                            child.icon_name = 'video-display-symbolic';
                        }
                    });

                    // Cancelar la restauración anterior si existe
                    if (this._icon_restore_timeout) {
                        GLib.source_remove(this._icon_restore_timeout);
                        this._icon_restore_timeout = 0;
                    }
                    // Programar restauración del icono
                    this._icon_restore_timeout = GLib.timeout_add(GLib.PRIORITY_DEFAULT, cooldown, () => {
                        this._button.get_children().forEach(child => {
                            if (child instanceof St.Icon) {
                                child.icon_name = 'video-display';
                            }
                        });
                        this._icon_restore_timeout = 0;
                        return false; // GLib.SOURCE_REMOVE
                    });
                    return true;
                }

                // Primer clic o fuera de cooldown: ejecutar rotación
                this._last_click_time = now;
                this._sendActionToEngine({ action: 'force_rotation' });
                return true;
            } else if (event.get_button() === 3) { // Botón derecho
                this._button.menu.toggle();
                return true;
            }
            return false;
        });

        Main.panel.addToStatusArea('wmm-indicator', this._button);
    }

    disable() {
        // Kill engine
        try {
            let pidPath = GLib.get_user_cache_dir() + '/wmm/pid_main.pid';
            let file = Gio.File.new_for_path(pidPath);
            let [success, content] = file.load_contents(null);
            if (success) {
                let pid = parseInt(content.toString().trim());
                if (pid > 0) GLib.spawn_command_line_async('kill -9 ' + pid);
            }
        } catch (e) { log('WMM cleanup: ' + e.message); }

        if (this._menu) {
            this._menu.destroy();
            this._menu = null;
        }

        if (this._button) {
            this._button.destroy();
            this._button = null;
        }
    }

    // ── Menu construction (same as Cinnamon) ──────────────
    _populateMenu() {
        // this._menu ya está creado en enable()

        // Settings
        let settingsItem = new PopupMenu.PopupMenuItem('WMM ' + __('Settings'));
        settingsItem.connect('activate', () => this._openSettingsPanel());
        this._menu.addMenuItem(settingsItem);
        this._menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        // Bookmarks
        this.menuBookmarks = new PopupMenu.PopupSubMenuMenuItem(__('Favorites'));
        this._menu.addMenuItem(this.menuBookmarks);

        this.favRotationSwitch = new PopupMenu.PopupSwitchMenuItem(__('Favorites Only'), false);
        this.favRotationSwitch.connect('toggled', (item, state) => {
            if (state && !this.masterItem.state) this._syncTimerUI(true);
            this._updateTimerSettings();
        });
        this.menuBookmarks.menu.addMenuItem(this.favRotationSwitch);
        
        this.menuBookmarks.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        let addBookmarkItem = new PopupMenu.PopupMenuItem(__('Add Preset Favorite'));
        addBookmarkItem.connect('activate', () => {
            GLib.spawn_command_line_async('python3 ' + this.appletPath + '/python/add_bookmark.py');
        });
        this.menuBookmarks.menu.addMenuItem(addBookmarkItem);
        this.menuBookmarks.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        // Timer
        this.menuTimer = new PopupMenu.PopupSubMenuMenuItem(__('Slideshow'));
        this._menu.addMenuItem(this.menuTimer);

        // Switch maestro
        this.masterItem = new PopupMenu.PopupSwitchMenuItem(__('Disabled'), false);
        this.masterItem.connect('toggled', (item, state) => {
            item.label.set_text(state ? __('Enabled') : __('Disabled'));
            this._syncTimerUI(state);
            this._updateTimerSettings();
        });
        this.menuTimer.menu.addMenuItem(this.masterItem);

        let infoItem = new PopupMenu.PopupBaseMenuItem({ reactive: false });
        let infoBox = new St.BoxLayout({ style: 'margin-left: 110px;' });
        this.labelMin = new St.Label({ text: '' });
        infoBox.add_child(this.labelMin);
        infoItem.add_child(infoBox);
        this.menuTimer.menu.addMenuItem(infoItem);

        // --- Selector de intervalo con SpinButton (mismo control que panel.py) ---
        let intervalItem = new PopupMenu.PopupBaseMenuItem({ activate: false });
        let intervalBox = new St.BoxLayout({ style: 'spacing: 8px;' });
        let minusBtn = new St.Button({ label: '−', style_class: 'button' });
        this.intervalLabel = new St.Label({ text: '15 ' + __('minutes') });
        let plusBtn = new St.Button({ label: '+', style_class: 'button' });

        this._currentInterval = 15; // valor por defecto

        minusBtn.connect('clicked', () => {
            if (this._currentInterval > 1) {
                this._currentInterval--;
                this.intervalLabel.set_text(this._currentInterval + ' ' + __('minutes'));
                if (this.masterItem && this.masterItem.state) this._updateTimerSettings();
            }
        });
        plusBtn.connect('clicked', () => {
            if (this._currentInterval < 60) {
                this._currentInterval++;
                this.intervalLabel.set_text(this._currentInterval + ' ' + __('minutes'));
                if (this.masterItem && this.masterItem.state) this._updateTimerSettings();
            }
        });

        intervalBox.add_child(minusBtn);
        intervalBox.add_child(this.intervalLabel);
        intervalBox.add_child(plusBtn);
        intervalItem.add_child(intervalBox);
        this.menuTimer.menu.addMenuItem(intervalItem);

        // Switch modo sync/async
        this.modeSwitch = new PopupMenu.PopupSwitchMenuItem(__('Displays') + ': ' + __('ASYNC (One)'), false);
        this.modeSwitch.connect('toggled', (item, state) => {
            item.label.set_text(state ? __('Displays') + ': ' + __('SYNC (All)') : __('Displays') + ': ' + __('ASYNC (One)'));
            this._updateTimerSettings();
        });
        this._menu.addMenuItem(this.modeSwitch);

        // Switch spanned
        this.spannedSwitch = new PopupMenu.PopupSwitchMenuItem(__('Spanned Mode'), false);
        this.spannedSwitch.connect('toggled', () => this._updateTimerSettings());
        this._menu.addMenuItem(this.spannedSwitch);

        // Footer
        this._menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        let syncItem = new PopupMenu.PopupMenuItem(__('Sync Library'));
        syncItem.connect('activate', () => this._sendActionToEngine({ action: 'sync_library' }));
        this._menu.addMenuItem(syncItem);

        let helpItem = new PopupMenu.PopupMenuItem(__('Help'));
        helpItem.connect('activate', () => {
            GLib.spawn_command_line_async('python3 ' + this.appletPath + '/python/help_viewer.py');
        });
        this._menu.addMenuItem(helpItem);

        this._menu.connect('open-state-changed', (menu, open) => {
            if (open) this._refreshSettingsFromDisk();
        });
    }

    _syncTimerUI(enabled) {
        if (!this.masterItem) return;
        this.masterItem.setToggleState(enabled);
        this.masterItem.label.set_text(enabled ? __('Enabled') : __('Disabled'));
    }

    _refreshSettingsFromDisk() {
        try {
            let [s, content] = GLib.file_get_contents(this.settingsPath);
            if (!s) return;
            let config = JSON.parse(content.toString()).global;
            this._currentMaxInterval = config.slideshow_max_interval || 60;
            let isEnabled = config.slideshow_enabled;
            let isSync = (config.slideshow_mode === 'sync');
            let isFavSlideshow = config.slideshow_bookmark || false;
            this._syncTimerUI(isEnabled);
            this.modeSwitch.setToggleState(isSync);
            this.modeSwitch.label.set_text(isSync ? __('Displays') + ': ' + __('SYNC (All)') : __('Displays') + ': ' + __('ASYNC (One)'));
            this.favRotationSwitch.setToggleState(isFavSlideshow);
            this._currentInterval = config.slideshow_interval || 15;
            this.intervalLabel.set_text(this._currentInterval + ' ' + __('minutes'));
            let isSpanned = config.spanned_enabled || false;
            this.spannedSwitch.setToggleState(isSpanned);
            this._refreshBookmarks();
        } catch (e) {
            log('WMM refresh: ' + e.message);
        }
    }

    _refreshBookmarks() {
        this.favItems.forEach(item => item.destroy());
        this.favItems = [];
        try {
            let [s, content] = GLib.file_get_contents(this.bookmarksPath);
            if (!s) return;
            let bookmarks = JSON.parse(content.toString());
            let keys = Object.keys(bookmarks);
            log('WMM bookmarks: ' + keys.length + ' presets found');
            if (keys.length === 0) {
                let info = new PopupMenu.PopupMenuItem(__('No saved favorites'), { reactive: false });
                this.menuBookmarks.menu.addMenuItem(info);
                this.favItems.push(info);
                return;
            }
            // Contenedor sin usar actor
            let scrollItem = new PopupMenu.PopupBaseMenuItem({ reactive: false, activate: false });
            let favBox = new St.BoxLayout({
                vertical: true,
                style: 'margin-left: 10px; padding: 0;'
            });
            keys.forEach(name => {
                let row = new St.BoxLayout({ style: 'padding: 3px 0px; spacing: 0px;' });
                let nameBtn = new St.Button({
                    reactive: true,
                    can_focus: true,
                    track_hover: true,
                });
                let nameLabel = new St.Label({
                    text: name,
                    style: 'overflow: hidden; white-space: nowrap; text-overflow: ellipsis;'
                });
                nameBtn.set_child(nameLabel);
                nameBtn.connect('clicked', () => {
                    this._syncTimerUI(false);
                    this._sendActionToEngine({ action: 'load_bookmark', name: name, timer_force_off: true });
                    this._button.menu.close();
                });
                let deleteBtn = new St.Button({ reactive: true, can_focus: true, track_hover: true });
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
                row.add_child(nameBtn, { expand: true, x_fill: true });
                row.add_child(deleteBtn);
                favBox.add_child(row, { expand: true, x_fill: true });
            });
            let scrollView = new St.ScrollView({
                hscrollbar_policy: St.PolicyType.AUTOMATIC,
                vscrollbar_policy: St.PolicyType.AUTOMATIC,
                style: 'border: none; background-color: transparent; padding: 0; margin: 0;'
            });
            scrollView.set_size(200, Math.min(keys.length * 38, 125));
            scrollView.add_child(favBox);
            scrollItem.add_child(scrollView, { expand: false });
            log('WMM bookmarks: adding scrollItem to menu');
            this.menuBookmarks.menu.addMenuItem(scrollItem);
            this.favItems.push(scrollItem);
        } catch (e) {
            log('WMM bookmarks: ' + e.message);
        }
    }

    _confirmDeleteBookmark(name) {
        let args = ['--question', '--title=' + __('Delete favorite'), '--text=' + __('Delete') + ' "' + name + '"?', '--width=200'];
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
        this._sendActionToEngine({
            action: 'update_timer_settings',
            enabled: this.masterItem.state,
            interval: this._currentInterval, // ← ya no usa slider.value
            mode: this.modeSwitch.state ? 'sync' : 'async',
            slideshow_bookmark: this.favRotationSwitch.state,
            spanned_enabled: this.spannedSwitch.state
        });
    }

    _sendActionToEngine(command) {
        try {
            let file = Gio.File.new_for_path(this.commandsPath);
            let raw = JSON.stringify(command, null, 4);
            file.replace_contents(raw, null, false, Gio.FileCreateFlags.REPLACE_DESTINATION, null);
            GLib.spawn_command_line_async('pkill -USR1 -f main.py');
        } catch (e) {
            log('WMM send: ' + e.message);
        }
    }

    _openSettingsPanel() {
        GLib.spawn_command_line_async('python3 ' + this.appletPath + '/python/panel.py');
    }
}
