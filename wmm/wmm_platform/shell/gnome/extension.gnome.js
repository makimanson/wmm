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
import GObject from 'gi://GObject';
import St from 'gi://St';
import Meta from 'gi://Meta';
import Gettext from 'gettext';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import * as Slider from 'resource:///org/gnome/shell/ui/slider.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';

const WMMPanelButton = GObject.registerClass(
class WMMPanelButton extends PanelMenu.Button {
    _init(owner) {
        super._init(0.0, 'WMM', false);

        this._owner = owner;

        /*
         * GNOME <= 49 procesa los clics desde vfunc_event().
         * GNOME >= 50 usa un ClickGesture interno que se ejecuta antes.
         * Desactivarlo cuando existe deja una única autoridad para todo
         * el rango soportado: nuestro vfunc_event().
         */
        this._clickGesture?.set_enabled(false);
    }

    vfunc_event(event) {
        if (event.type() === Clutter.EventType.BUTTON_PRESS) {
            const result = this._owner?._onPanelButtonPress(event);

            if (result === Clutter.EVENT_STOP)
                return Clutter.EVENT_STOP;
        }

        return super.vfunc_event(event);
    }
});

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
    <method name="GetPointAvailableArea">
      <arg name="x" type="i" direction="in"/>
      <arg name="y" type="i" direction="in"/>
      <arg name="area" type="s" direction="out"/>
    </method>
    <method name="PurgeBackgroundCache">
      <arg name="path" type="s" direction="in"/>
      <arg name="handled" type="b" direction="out"/>
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

        // Desde v1.5.0 la extensión contiene únicamente el frontend GNOME.
        // settings_core.ini enlaza ese frontend con el core y los datos comunes.
        let coreFile = Gio.File.new_for_path(this.appletPath + '/settings_core.ini');
        let [success, contents] = coreFile.load_contents(null);

        if (!success)
            throw new Error('Could not read settings_core.ini');

        let coreConfig = {};

        new TextDecoder().decode(contents).split('\n').forEach(line => {
            line = line.trim();
            if (!line || line.startsWith('#') || line.startsWith(';'))
                return;
            let separator = line.indexOf('=');
            if (separator < 0)
                return;
            coreConfig[line.slice(0, separator).trim()] =
                line.slice(separator + 1).trim();
        });

        this.appDir = coreConfig.app_dir;
        this.dataDir = coreConfig.data_dir;

        if (!this.appDir || !this.dataDir)
            throw new Error('settings_core.ini does not define app_dir/data_dir');

        this.enginePath = this.appDir + '/python/main.py';
        this.installManagerPath = this.appDir + '/wmm_platform/shell/installer/wmm-install_manager.py';
        this.debugLogViewerPath = this.appDir + '/python/debug_log_viewer.py';
        this.commandsPath = this.dataDir + '/commands.json';
        this.settingsPath = this.dataDir + '/settings.json';
        this.bookmarksPath = this.dataDir + '/bookmarks.json';
        this._cachedSettings = null;
        this._cachedBookmarks = null;
        this._currentMaxInterval = 60;
        this.favItems = [];
        this._syncingUI = false;
        this._button = null;
        this._menu = null;
        this._contextMenu = null;
        this._contextMenuManager = null;
        this._deleteConfirmMenu = null;
        this._icon = null;
        this._tooltip = null;
        this._tooltipTitle = null;
        this._tooltipText = null;
        this._tooltipTimeoutId = 0;
        this._tooltipHoverSignalId = 0;
        this._motorBusy = true;
        this._busySignalId = 0;
        this._bookmarksSignalId = 0;
        this._workareaDbus = null;
        this._workareaOwnerId = 0;
    }

    enable() {
        // Start the engine
        GLib.spawn_async(null, ["python3", this.enginePath], null, GLib.SpawnFlags.SEARCH_PATH, null);

        // Panel button
        this._button = new WMMPanelButton(this);

        // GNOME 50+ abre PanelMenu.Button mediante un ClickGesture interno,
        // mientras que versiones anteriores lo hacen desde el evento del actor.
        // WMM necesita distinguir ambos botones de forma uniforme en GNOME 45–51.
        this._icon = new St.Icon({
            icon_name: 'view-refresh',
            style_class: 'system-status-icon'
        });

        this._button.add_child(this._icon);
        Main.panel.addToStatusArea('wmm-indicator', this._button);

        let cssFile = Gio.File.new_for_path(this.appletPath + '/stylesheet.css');
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

        // Cubrir también una ventana About ya existente si la extensión
        // se recarga mientras WMM continúa ejecutándose.
        for (const window of global.display.list_all_windows())
            this._keepAboutWindowAbove(window);

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
        this._menu = this._button.menu;

        // GNOME Shell cierra el submenú anterior al abrir otro.
        // WMM permite mantener varios desplegados hasta que el usuario los cierre.
        this._menu._setOpenedSubMenu = () => {};

        this._populateMenu();

        this._contextMenu = new PopupMenu.PopupMenu(
            this._button, 0.0, St.Side.TOP
        );
        this._contextMenu.actor.add_style_class_name('panel-menu');
        Main.uiGroup.add_child(this._contextMenu.actor);
        this._contextMenu.actor.hide();

        this._contextMenuManager = new PopupMenu.PopupMenuManager(this._button);
        this._contextMenuManager.addMenu(this._contextMenu);

        this._populateContextMenu();
        this._createTooltip();
        this._subscribeBookmarksState();
        this._subscribeBusyState();
        this._refreshBusyState();
    }

    _createTooltip() {
        if (this._tooltip || !this._button)
            return;

        this._tooltip = new St.BoxLayout({
            style_class: 'wmm-tooltip',
            reactive: false,
            visible: false
        });
        this._tooltip.get_layout_manager().set_orientation(
            Clutter.Orientation.VERTICAL
        );

        this._tooltipTitle = new St.Label({
            style_class: 'wmm-tooltip-title'
        });

        this._tooltipText = new St.Label();

        this._tooltip.add_child(this._tooltipTitle);
        this._tooltip.add_child(this._tooltipText);

        Main.uiGroup.add_child(this._tooltip);

        this._button.set_track_hover(true);
        this._tooltipHoverSignalId = this._button.connect(
            'notify::hover',
            () => {
                if (this._button.hover)
                    this._scheduleTooltip();
                else
                    this._hideTooltip();
            }
        );
    }

    _scheduleTooltip() {
        this._cancelTooltipTimeout();

        // Retardo deliberado: pasar simplemente sobre el icono no debe
        // convertir el tooltip en ruido visual.
        this._tooltipTimeoutId = GLib.timeout_add(
            GLib.PRIORITY_DEFAULT,
            400,
            () => {
                this._tooltipTimeoutId = 0;

                if (this._button?.hover &&
                        !this._menu?.isOpen &&
                        !this._contextMenu?.isOpen)
                    this._showTooltip();

                return GLib.SOURCE_REMOVE;
            }
        );
    }

    _scheduleMenuItemTooltip(item) {
        this._cancelTooltipTimeout();

        this._tooltipTimeoutId = GLib.timeout_add(
            GLib.PRIORITY_DEFAULT,
            400,
            () => {
                this._tooltipTimeoutId = 0;

                if (item?.hover && this._menu?.isOpen) {
                    this._tooltipTitle.hide();
                    this._tooltipText.set_text(_('Secondary click: assign a keyboard shortcut'));
                    this._showTooltipFor(item, true);
                }

                return GLib.SOURCE_REMOVE;
            }
        );
    }

    _cancelTooltipTimeout() {
        if (!this._tooltipTimeoutId)
            return;

        GLib.Source.remove(this._tooltipTimeoutId);
        this._tooltipTimeoutId = 0;
    }

    _showTooltip() {
        if (!this._tooltip)
            return;

        this._tooltipTitle.set_text('Wallpaper Multi-Monitor Manager');
        this._tooltipTitle.show();

        const text =
            _('Click action') + ': ' + _('Main Menu') + '\n' +
            _('Middle Click') + ': ' + _('Next Background') + '\n' +
            _('Secondary Click') + ': ' + _('Context Menu');

        const escapedText = GLib.markup_escape_text(text, -1);

        this._tooltipText.get_clutter_text().set_markup(
            `<span line_height="1.18">${escapedText}</span>`
        );

        this._showTooltipFor(this._button, false);
    }

    _showTooltipFor(source, preferRight) {
        if (!this._tooltip || !source)
            return;

        const monitor = Main.layoutManager.findMonitorForActor(source);
        if (!monitor)
            return;

        const [sourceX, sourceY] = source.get_transformed_position();
        const [sourceWidth, sourceHeight] = source.get_transformed_size();

        const [, tooltipWidth] = this._tooltip.get_preferred_width(-1);
        const [, tooltipHeight] =
            this._tooltip.get_preferred_height(tooltipWidth);

        const margin = 8;

        const left = monitor.x + margin;
        const right = monitor.x + monitor.width - margin;
        const top = monitor.y + margin;
        const bottom = monitor.y + monitor.height - margin;

        let x;
        let y;

        if (preferRight) {
            // Mostrar junto a la entrada sin abandonar nunca su monitor.
            x = sourceX + sourceWidth + margin;
            y = sourceY + (sourceHeight - tooltipHeight) / 2;

            if (x + tooltipWidth > right)
                x = sourceX - tooltipWidth - margin;
        } else {
            // Tooltip del icono del panel.
            x = sourceX + (sourceWidth - tooltipWidth) / 2;
            y = sourceY + sourceHeight + margin;

            if (y + tooltipHeight > bottom)
                y = sourceY - tooltipHeight - margin;
        }

        x = Math.max(
            left,
            Math.min(x, right - tooltipWidth)
        );

        y = Math.max(
            top,
            Math.min(y, bottom - tooltipHeight)
        );

        this._tooltip.set_position(Math.round(x), Math.round(y));
        this._tooltip.show();
    }

    _hideTooltip() {
        this._cancelTooltipTimeout();

        if (this._tooltip)
            this._tooltip.hide();
    }

    _setMotorBusy(busy) {
        this._motorBusy = Boolean(busy);

        if (this._icon)
            this._icon.icon_name = this._motorBusy ? 'view-refresh' : 'video-display';
    }

    _subscribeBookmarksState() {
        if (this._bookmarksSignalId)
            return;

        this._bookmarksSignalId = Gio.DBus.session.signal_subscribe(
            'org.maki.wmm',
            'org.maki.wmm',
            'BookmarksChanged',
            '/org/maki/wmm',
            null,
            Gio.DBusSignalFlags.NONE,
            (_connection, _sender, _path, _interface, _signal, parameters) => {
                try {
                    const [jsonData] = parameters.deepUnpack();
                    const bookmarks = JSON.parse(jsonData);

                    if (!bookmarks || typeof bookmarks !== 'object')
                        return;

                    this._cachedBookmarks = bookmarks;
                    this._paintBookmarks(bookmarks);
                } catch (e) {
                    log('WMM BookmarksChanged: ' + e.message);
                }
            }
        );
    }

    _subscribeBusyState() {
        if (this._busySignalId)
            return;

        this._busySignalId = Gio.DBus.session.signal_subscribe(
            'org.maki.wmm',
            'org.maki.wmm',
            'BusyChanged',
            '/org/maki/wmm',
            null,
            Gio.DBusSignalFlags.NONE,
            (_connection, _sender, _path, _interface, _signal, parameters) => {
                const [busy] = parameters.deepUnpack();
                this._setMotorBusy(busy);
            }
        );
    }

    _refreshBusyState() {
        Gio.DBus.session.call(
            'org.maki.wmm',
            '/org/maki/wmm',
            'org.maki.wmm',
            'GetBusy',
            null,
            GLib.VariantType.new('(b)'),
            Gio.DBusCallFlags.NO_AUTO_START,
            1000,
            null,
            (connection, result) => {
                try {
                    const reply = connection.call_finish(result);
                    const [busy] = reply.deepUnpack();
                    this._setMotorBusy(busy);
                } catch (e) {
                    log('WMM GetBusy: ' + e.message);
                }
            }
        );
    }

    _keepAboutWindowAbove(window) {
        if (!window || window.get_gtk_application_id() !== 'org.maki.wmm.About')
            return;

        if (!window.is_above())
            window.make_above();
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

        if (this._bookmarksSignalId) {
            Gio.DBus.session.signal_unsubscribe(this._bookmarksSignalId);
            this._bookmarksSignalId = 0;
        }

        if (this._busySignalId) {
            Gio.DBus.session.signal_unsubscribe(this._busySignalId);
            this._busySignalId = 0;
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
    /**
     * Return the usable area of the monitor containing a global stage point.
     *
     * El punto procede de un actor de GNOME Shell, por lo que Mutter debe
     * conservar la autoridad sobre la selección del monitor y su workarea.
     */
    GetPointAvailableArea(x, y) {
        const monitorIndex = Main.layoutManager.monitors.findIndex(monitor =>
            x >= monitor.x &&
            x < monitor.x + monitor.width &&
            y >= monitor.y &&
            y < monitor.y + monitor.height
        );

        if (monitorIndex < 0)
            return '';

        const workspace = global.workspace_manager.get_active_workspace();
        if (!workspace)
            return '';

        const area = workspace.get_work_area_for_monitor(monitorIndex);
        return `${area.x},${area.y},${area.width},${area.height}`;
    }

    GetWindowAvailableArea(pid) {
        const window = global.display.list_all_windows().find(window => window.get_pid() === pid);

        if (!window)
            return '';

        const area = window.get_work_area_current_monitor();
        return `${area.x},${area.y},${area.width},${area.height}`;
    }

    PurgeBackgroundCache(path) {
        try {
            // GNOME 51 invalida la caché mediante la vigilancia del archivo.
            // Las versiones anteriores conservan la purga explícita.
            if (Meta.BackgroundImageCache) {
                const file = Gio.File.new_for_path(path);
                Meta.BackgroundImageCache.get_default().purge(file);
            }
            return true;
        } catch (e) {
            log('WMM background cache purge ERROR: ' + e.message);
            return false;
        }
    }

    _onPanelButtonPress(event) {
        const button = event.get_button();
        this._hideTooltip();
        if (button === 1) {
            if (this._contextMenu?.isOpen)
                this._contextMenu.close();

            if (this._menu) {
                // Leer antes de abrir evita cambios de geometría posteriores.
                // Al regresar del formulario, recuperamos el binding definitivo.
                if (!this._menu.isOpen)
                    this._refreshNextBackgroundKeybinding();

                this._menu.toggle();
            }

            return Clutter.EVENT_STOP;
        }

        if (button === 2) {
            if (this._menu?.isOpen)
                this._menu.close();

            if (this._contextMenu?.isOpen)
                this._contextMenu.close();

            if (this._motorBusy)
                return Clutter.EVENT_STOP;

            this._setMotorBusy(true);

            if (!this._sendActionToEngine({ action: 'force_rotation' }))
                this._refreshBusyState();

            return Clutter.EVENT_STOP;
        }

        if (button === 3) {
            if (this._menu?.isOpen)
                this._menu.close();

            if (this._contextMenu)
                this._contextMenu.toggle();

            return Clutter.EVENT_STOP;
        }

        return Clutter.EVENT_PROPAGATE;
    }

    _refreshNextBackgroundKeybinding() {
        if (!this.nextBackgroundHotkeyLabel)
            return;

        let binding = '';

        /*
         * GNOME conserva el atajo en GSettings, no en settings.json.
         * Identificamos la entrada por el comando WMM que ejecuta,
         * nunca por su nombre traducido ni por el índice customN.
         */
        try {
            const settings = Gio.Settings.new(
                'org.gnome.settings-daemon.plugins.media-keys'
            );

            const schema =
                'org.gnome.settings-daemon.plugins.media-keys.custom-keybinding';

            const scriptPath = GLib.canonicalize_filename(
                this.appDir + '/python/send_command.py',
                GLib.get_current_dir()
            );

            for (const path of settings.get_strv('custom-keybindings')) {
                try {
                    const custom = Gio.Settings.new_with_path(schema, path);
                    const command = custom.get_string('command');

                    const [, argv] = GLib.shell_parse_argv(command);

                    if (argv.length !== 4 ||
                        GLib.canonicalize_filename(argv[1], GLib.get_current_dir()) !== scriptPath ||
                        argv[3] !== 'HOTKEY')
                        continue;

                    const payload = JSON.parse(argv[2]);

                    if (payload.action !== 'force_rotation' ||
                        Object.keys(payload).length !== 1)
                        continue;

                    // GNOME admite versiones del esquema con binding s o as.
                    const type = custom.get_value('binding').get_type_string();

                    if (type === 's')
                        binding = custom.get_string('binding');
                    else if (type === 'as')
                        binding = custom.get_strv('binding')[0] || '';

                    break;

                } catch (_error) {
                    // Una entrada ajena o inválida no debe impedir
                    // localizar el atajo propio de WMM.
                    continue;
                }
            }

        } catch (error) {
            log('WMM: Error leyendo el atajo Next Background: ' + error.message);
        }

        // GNOME Shell no necesita GTK para presentar el acelerador.
        const labels = {
            Control: 'Ctrl',
            Primary: 'Ctrl',
            Alt: 'Alt',
            Mod1: 'Alt',
            Shift: _('Shift'),
            Super: 'Super',
            Mod4: 'Super',
            Meta: 'Meta',
            Hyper: 'Hyper'
        };

        const parts = [];

        const key = binding.replace(/<([^>]+)>/g, (_match, modifier) => {
            parts.push(labels[modifier] || modifier);
            return '';
        });

        if (key)
            parts.push(key.length === 1 ? key.toUpperCase() : key);

        this.nextBackgroundHotkeyLabel.set_text(parts.join(' + '));
    }

    // ── Menu construction ──
    _populateMenu() {
        // this._menu ya está creado en enable()

        // Next Wallpaper — primera opción del menú
        let rotateItem = new PopupMenu.PopupMenuItem(_('Next Background'));

        // El acelerador se presenta a la derecha, sin alterar la acción
        // ni los botones admitidos por Next Background.
        rotateItem.label.x_expand = true;

        this.nextBackgroundHotkeyLabel = new St.Label({
            text: '',
            style_class: 'wmm-hotkey-label',
            y_align: Clutter.ActorAlign.CENTER
        });

        rotateItem.add_child(this.nextBackgroundHotkeyLabel);

        rotateItem.set_track_hover(true);
        rotateItem.connect('notify::hover', () => {
            if (rotateItem.hover)
                this._scheduleMenuItemTooltip(rotateItem);
            else
                this._hideTooltip();
        });
        rotateItem.connect('activate', (_item, event) => {
            // GNOME conecta su cierre después de nuestro callback.
            // Detener esta emisión conserva el menú abierto sin reabrirlo.
            GObject.signal_stop_emission_by_name(rotateItem, 'activate');

            // Sólo el botón izquierdo ejecuta la rotación.
            // El derecho queda reservado para configurar el atajo.
            const type = event?.type();
            if (type === Clutter.EventType.BUTTON_PRESS ||
                type === Clutter.EventType.BUTTON_RELEASE) {
                const button = event.get_button();
                if (button === 3) {
                    // Utilizar el centro del menú antes de cerrarlo: Mutter
                    // delimitará el formulario a la workarea del monitor.
                    const [x, y] = this._menu.actor.get_transformed_position();
                    const [width, height] = this._menu.actor.get_transformed_size();

                    this._menu.close();
                    this._sendActionToEngine({
                        action: 'open_keybinding',
                        x: Math.round(x + width / 2),
                        y: Math.round(y + height / 2)
                    });
                    return;
                }
                if (button !== 1)
                    return;
            }
            if (this._motorBusy)
                return;
            this._setMotorBusy(true);
            if (!this._sendActionToEngine({ action: 'force_rotation' }))
                this._refreshBusyState();
        });
        this._menu.addMenuItem(rotateItem);
        this._menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        // Bookmarks
        this.menuBookmarks = new PopupMenu.PopupSubMenuMenuItem(_('Favorites'));
        this.menuBookmarks.label.add_style_class_name('wmm-inline-header');
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
            if (this._syncingUI) return;

            if (state && !this.masterItem.state) this._syncTimerUI(true);
            this._updateTimerSettings();
        });
        this.favRotationSwitch.connect('activate', () => {
            // Evitar el cierre nativo del menú principal al activar un switch inline.
            GObject.signal_stop_emission_by_name(this.favRotationSwitch, 'activate');
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
            const [x, y] = addBookmarkButton.get_transformed_position();
            const [width, height] = addBookmarkButton.get_transformed_size();

            this._menu.close();

            this._sendActionToEngine({
                action: "add_bookmark",
                x: Math.round(x + width / 2),
                y: Math.round(y + height / 2)
            });
        });
        addBookmarkItem.add_child(addBookmarkButton);
        this.menuBookmarks.menu.addMenuItem(addBookmarkItem);

        this.menuBookmarks.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        // Timer
        this.menuTimer = new PopupMenu.PopupSubMenuMenuItem(_('Slideshow'));
        this.menuTimer.label.add_style_class_name('wmm-inline-header');
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
            if (this._syncingUI) return;

            item.label.set_text(state ? _('Enabled') : _('Disabled'));
            this._syncTimerUI(state);
            this._updateTimerSettings();
        });
        this.masterItem.connect('activate', () => {
            // Conservar el submenú abierto sin cerrar y reabrir el popup principal.
            GObject.signal_stop_emission_by_name(this.masterItem, 'activate');
        });
        this.menuTimer.menu.addMenuItem(this.masterItem);

        this.menuTimer.menu.actor.add_style_class_name('wmm-submenu');

        // --- Selector de intervalo ---
        let intervalItem = new PopupMenu.PopupBaseMenuItem({ activate: false });
        intervalItem.add_style_class_name('wmm-flat-row');
        let intervalBox = new St.BoxLayout({x_expand: true, style: 'spacing: 4px;'});
        intervalBox.get_layout_manager().set_orientation(Clutter.Orientation.VERTICAL);
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
            if (this._syncingUI) return;

            item.label.set_text(state ? _('Displays') + ': ' + _('SYNC (All)') : _('Displays') + ': ' + _('ASYNC (One)'));
            this._updateTimerSettings();
        });
        this.modeSwitch.connect('activate', () => {
            // Evitar el cierre nativo del menú tras modificar el modo de presentación.
            GObject.signal_stop_emission_by_name(this.modeSwitch, 'activate');
        });
        this._menu.addMenuItem(this.modeSwitch);

        // Switch spanned
        this.spannedSwitch = new PopupMenu.PopupSwitchMenuItem(_('Spanned Mode'), false);
        this.spannedSwitch.connect('toggled', () => {
            if (this._syncingUI) return;

            this._updateTimerSettings();
        });
        this.spannedSwitch.connect('activate', () => {
            // Conservar el menú abierto sin recurrir al cierre y reapertura.
            GObject.signal_stop_emission_by_name(this.spannedSwitch, 'activate');
        });

        this._menu.addMenuItem(this.spannedSwitch);

        // Image Metadata
        this.metadataSwitch = new PopupMenu.PopupSwitchMenuItem(_('Image Metadata'), false);
        this.metadataSwitch.connect('toggled', (item, state) => {
            if (this._syncingUI) return;

            // Conservar el estado local mientras el Engine persiste el cambio.
            if (!this._cachedSettings) this._cachedSettings = {};
            this._cachedSettings.exif_metadata_enabled = state;

            this._sendActionToEngine({
                action: 'set_metadata_enabled',
                enabled: state
            });
        });
        this.metadataSwitch.connect('activate', () => {
            // Mantener abierto el menú, igual que los demás switches de GNOME.
            GObject.signal_stop_emission_by_name(this.metadataSwitch, 'activate');
        });
        this._menu.addMenuItem(this.metadataSwitch);

        this._menuOpenSignalId = this._menu.connect('open-state-changed', (menu, open) => {
            if (open)
                this._refreshSettingsFromDisk();
        });
    }

    _populateContextMenu() {
        let settingsItem = new PopupMenu.PopupMenuItem(_('Settings'));
        settingsItem.connect('activate', () => this._openSettingsPanel());
        this._contextMenu.addMenuItem(settingsItem);

        let syncItem = new PopupMenu.PopupMenuItem(_('Sync Library'));
        syncItem.connect('activate', () =>
            this._sendActionToEngine({ action: 'sync_library' }));
        this._contextMenu.addMenuItem(syncItem);

        let installManagerItem =
            new PopupMenu.PopupMenuItem(_('Install Manager'));
        installManagerItem.connect('activate', () =>
            this._launchTool(this.installManagerPath));
        this._contextMenu.addMenuItem(installManagerItem);

        let debugLogItem =
            new PopupMenu.PopupMenuItem(_('Debug Log Viewer'));
        debugLogItem.connect('activate', () =>
            this._launchTool(this.debugLogViewerPath));
        this._contextMenu.addMenuItem(debugLogItem);

        let helpItem = new PopupMenu.PopupMenuItem(_('Help'));
        helpItem.connect('activate', () =>
            this._sendActionToEngine({ action: 'open_help' }));
        this._contextMenu.addMenuItem(helpItem);

        this._contextMenu.addMenuItem(
            new PopupMenu.PopupSeparatorMenuItem());

        let aboutItem =
            new PopupMenu.PopupMenuItem(_('About') + ' WMM Manager');
        aboutItem.connect('activate', () =>
            this._sendActionToEngine({ action: 'open_about' }));
        this._contextMenu.addMenuItem(aboutItem);

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
        this._contextMenu.addMenuItem(exitItem);
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
        let isSpanned = config.spanned_enabled || false;
        let isMetadataEnabled = config.exif_metadata_enabled || false;

        this._syncingUI = true;

        try {
            this._syncTimerUI(isEnabled);
            this.modeSwitch.setToggleState(isSync);
            this.modeSwitch.label.set_text(isSync ? _('Displays') + ': ' + _('SYNC (All)') : _('Displays') + ': ' + _('ASYNC (One)'));
            this.favRotationSwitch.setToggleState(isFavSlideshow);
            this.spannedSwitch.setToggleState(isSpanned);
            this.metadataSwitch.setToggleState(isMetadataEnabled);
        } finally {
            this._syncingUI = false;
        }

        this._currentInterval = config.slideshow_interval || 15;
        let ratio = (this._currentInterval - 1) / (this._currentMaxInterval - 1);
        this.intervalSlider.value = ratio;
        this.intervalLabel.set_text(this._currentInterval + ' ' + _('minutes'));
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
                this._confirmDeleteBookmark(name, deleteBtn);
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
                    if (
                        !cached ||
                        cached.slideshow_enabled !== config.slideshow_enabled ||
                        cached.slideshow_interval !== config.slideshow_interval ||
                        cached.slideshow_mode !== config.slideshow_mode ||
                        cached.slideshow_bookmark !== config.slideshow_bookmark ||
                        cached.spanned_enabled !== config.spanned_enabled ||
                        cached.exif_metadata_enabled !== config.exif_metadata_enabled
                    ) {
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

    _destroyDeleteConfirmMenu() {
        if (!this._deleteConfirmMenu)
            return;

        const menu = this._deleteConfirmMenu;
        this._deleteConfirmMenu = null;

        if (this._contextMenuManager)
            this._contextMenuManager.removeMenu(menu);

        menu.destroy();
    }

    _confirmDeleteBookmark(name, sourceActor) {
        this._destroyDeleteConfirmMenu();

        const monitor = Main.layoutManager.findMonitorForActor(sourceActor);
        const [sourceX] = sourceActor.get_transformed_position();
        const [sourceWidth] = sourceActor.get_transformed_size();

        let arrowSide = St.Side.LEFT;

        // La confirmación se abre hacia el interior del monitor para no
        // invadir el monitor contiguo cuando la papelera está junto al borde.
        if (monitor &&
                sourceX + sourceWidth / 2 >
                monitor.x + monitor.width / 2) {
            arrowSide = St.Side.RIGHT;
        }

        const menu = new PopupMenu.PopupMenu(
            sourceActor, 0.5, arrowSide
        );

        menu.actor.add_style_class_name('panel-menu');
        Main.uiGroup.add_child(menu.actor);
        menu.actor.hide();

        this._deleteConfirmMenu = menu;
        this._contextMenuManager.addMenu(menu);

        /*
         * PopupMenu proporciona únicamente el contenedor flotante y su anclaje.
         * El contenido no utiliza PopupMenuItem para evitar su semántica visual
         * de lista: esta confirmación necesita composición de diálogo compacta.
         */
        const content = new St.BoxLayout({
            style_class: 'wmm-delete-confirm'
        });
        content.get_layout_manager().set_orientation(
            Clutter.Orientation.VERTICAL
        );

        const title = new St.Label({
            text: _('Delete preset'),
            style_class: 'wmm-delete-confirm-title',
            x_expand: true,
            x_align: Clutter.ActorAlign.CENTER
        });

        const body = new St.Label({
            text: _('Delete') + ' "' + name + '"?',
            style_class: 'wmm-delete-confirm-body'
        });

        const buttons = new St.BoxLayout({
            style_class: 'wmm-delete-confirm-buttons',
            x_expand: true,
            x_align: Clutter.ActorAlign.END
        });
        buttons.get_layout_manager().set_orientation(
            Clutter.Orientation.HORIZONTAL
        );

        const cancelButton = new St.Button({
            label: _('Cancel'),
            style_class: 'button',
            reactive: true,
            can_focus: true,
            track_hover: true
        });

        const deleteButton = new St.Button({
            label: _('Delete'),
            style_class: 'button',
            reactive: true,
            can_focus: true,
            track_hover: true
        });

        buttons.add_child(cancelButton);
        buttons.add_child(deleteButton);

        content.add_child(title);
        content.add_child(body);
        content.add_child(buttons);

        menu.box.add_child(content);

        cancelButton.connect('clicked', () => {
            menu.close();
        });

        deleteButton.connect('clicked', () => {
            menu.close();

            this._sendActionToEngine({
                action: 'delete_bookmark',
                name: name
            });
        });

        menu.connect('open-state-changed', (currentMenu, open) => {
            if (open)
                return;

            // La destrucción se difiere al siguiente ciclo para no desmontar
            // el popup mientras procesa su propia señal de cierre.
            GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
                if (this._deleteConfirmMenu === currentMenu)
                    this._destroyDeleteConfirmMenu();

                return GLib.SOURCE_REMOVE;
            });
        });

        menu.open();
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

    _launchTool(path) {
        this._menu.close();

        try {
            GLib.spawn_async(null, ['python3', path], null, GLib.SpawnFlags.SEARCH_PATH, null);
        } catch (e) {
            log('WMM tool launch: ' + path + ': ' + e.message);
        }
    }

    _sendActionToEngine(command) {
        try {
            let cmd = JSON.stringify(command);
             GLib.spawn_async(null, ["python3", this.appDir + "/python/send_command.py", cmd], null, GLib.SpawnFlags.SEARCH_PATH, null);
            return true;
        } catch (e) {
            log('WMM send: ' + e.message);
            return false;
        }
    }

    _openSettingsPanel() {
        this._sendActionToEngine({ action: "open_panel" });
    }

    _destroyUI() {

        this._cancelTooltipTimeout();

        if (this._button && this._tooltipHoverSignalId) {
            this._button.disconnect(this._tooltipHoverSignalId);
            this._tooltipHoverSignalId = 0;
        }

        if (this._tooltip) {
            this._tooltip.destroy();
            this._tooltip = null;
        }

        this._tooltipTitle = null;
        this._tooltipText = null;

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
        if (this.metadataSwitch) {
            this.metadataSwitch.destroy();
            this.metadataSwitch = null;
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
        this._destroyDeleteConfirmMenu();

        if (this._menu) {
            // El menú contextual no pertenece al PanelMenu.Button nativo:
            // retirarlo de su manager antes de destruir su actor.
            if (this._contextMenuManager && this._contextMenu)
                this._contextMenuManager.removeMenu(this._contextMenu);

            if (this._contextMenu) {
                this._contextMenu.destroy();
                this._contextMenu = null;
            }

            this._contextMenuManager = null;
            this._menu.destroy();
            this._menu = null;
            // La etiqueta pertenece al menú y ya ha sido destruida con él.
            this.nextBackgroundHotkeyLabel = null;
        }
    }
}
