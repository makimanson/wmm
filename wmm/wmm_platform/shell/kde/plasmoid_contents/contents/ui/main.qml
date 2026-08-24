/*
 * SPDX-FileCopyrightText: 2026 makimanson
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 ***************************************************************************
 *  WMM - Wallpaper Multi-Monitor Manager
 *
 *  Plasma 6 Frontend
 *
 *  main.qml: Este archivo implementa la interfaz gráfica del plasmoide KDE Plasma.
 *
 *  Filosofía de diseño
 *  -------------------
 *
 *  Este frontend NO contiene lógica del motor.
 *
 *  Toda la lógica reside en:
 *
 *      python/main.py
 *
 *  El plasmoide actúa únicamente como cliente gráfico:
 *
 *      • solicita información al motor
 *      • envía comandos mediante D-Bus
 *      • representa el estado del motor
 *
 *  La implementación de referencia de la interfaz de usuario es:
 *
 *      shell/gnome/extension.js
 *
 *  Este archivo es una traducción funcional de dicha implementación
 *  utilizando las APIs propias de Plasma 6.
 ***************************************************************************/

import QtQuick 2.15
import org.kde.plasma.plasmoid 2.0
import org.kde.plasma.core 2.0 as PlasmaCore
import org.kde.plasma.components 3.0 as PlasmaComponents
import org.kde.plasma.workspace.dbus as DBus

PlasmoidItem {
    id: root

    // ==========================================================
    // TRADUCCIÓN (dominio centralizado de WMM)
    // ==========================================================

    function _(text) {
        return i18nd("org.maki.wmm", text)
    }

    // ==========================================================
    // IDENTIDAD DEL PLASMOIDE
    // ==========================================================
    //
    // Información visual mostrada por Plasma.
    //
    // El icono puede modificarse dinámicamente en futuras versiones
    // (por ejemplo mostrando estados del motor).
    // ==========================================================

    property string currentIcon: "video-display"
    Plasmoid.icon: currentIcon
    toolTipMainText: "WMM: " + _("Wallpaper Multi-Monitor Manager")

    property bool spannedEnabled: false
    property bool syncMode: false
    property bool slideshowEnabled: false
    property int slideshowInterval: 15
    property bool slideshowBookmark: false
    property int slideshowMaxInterval: 60

    // ==========================================================
    // REPRESENTACIÓN DEL PLARMOIDE
    // ==========================================================
    //
    // Icono mostrado en el panel de Plasma.
    //
    // Actualmente WMM utiliza únicamente un icono estático con
    // soporte para tooltip.
    //
    // ==========================================================

   // compactRepresentation: Item {
   //     width: PlasmaCore.Units.iconSizes.smallMedium
   //     height: width
   //     PlasmaCore.ToolTipArea {
   //         anchors.fill: parent
   //         mainText: root.toolTipMainText
   //     }
   // }

   fullRepresentation: FullRepresentation {
       rootItem: root
   }

   // ==========================================================
   // ESTADO LOCAL SINCRONIZADO
   // ==========================================================
   //
   // Último estado recibido desde el motor.
   //
   // Se obtiene inicialmente mediante consultas D-Bus y se mantiene
   // actualizado de forma reactiva mediante DBus.SignalWatcher.
   //
   // Nunca contiene información persistente.
   //
   // ==========================================================

   property var cachedSettings: ({ })
   property var cachedBookmarks: ({ })

    DBus.SignalWatcher {
        service: "org.maki.wmm"
        path: "/org/maki/wmm"
        iface: "org.maki.wmm"

        function dbusSettingsChanged(jsonData) {
            try {
                var data = JSON.parse(jsonData)
                cachedSettings = data.global || data
                applySettings()
                buildMenu()
            }
            catch(e) {
                console.error("WMM: Invalid SettingsChanged:", e)
            }
        }

        function dbusBookmarksChanged(jsonData) {
            try {
                cachedBookmarks = JSON.parse(jsonData)
            }
            catch(e) {
                console.error("WMM: Invalid BookmarksChanged:", e)
            }
        }
    }
    // ==========================================================
    // ESTADO DEL MENÚ
    // ==========================================================
    //
    // Lista de acciones que Plasma utilizará para construir el
    // menú contextual.
    //
    // buildMenu() genera completamente este array cada vez que
    // Plasma solicita abrir el menú.
    //
    // ==========================================================

    property var menuActions: [ ]

    // ==========================================================
    // COMUNICACIÓN CON EL MOTOR
    // ==========================================================
    //
    // Todas las órdenes enviadas al motor pasan por esta capa.
    //
    // El resto del plasmoide nunca realiza llamadas D-Bus
    // directamente.
    //
    // De esta forma el protocolo queda centralizado en un único
    // punto y cualquier modificación futura únicamente afectará
    // a estas funciones.
    //
    // ==========================================================

    //----------------------------------------------------------
    // Envía un comando al motor
    //----------------------------------------------------------

    function sendCommand(action, params)
    {
        var cmd = {
            action: action
        }

        if (params) {
            for (var key in params)
                cmd[key] = params[key]
        }

        var json = JSON.stringify(cmd)
        var reply = DBus.SessionBus.asyncCall({
            service: "org.maki.wmm",
            path: "/org/maki/wmm",
            iface: "org.maki.wmm",
            member: action,
            signature: "(s)",
            arguments: [ json ]
        })

        reply.finished.connect(function() {
            if (reply.isError) {
                console.error("WMM:", action, reply.error.message)
            }
            reply.destroy()
        })
    }

    //----------------------------------------------------------
    // Obtiene settings.json
    //----------------------------------------------------------

    function refreshSettings(callback){
        var reply = DBus.SessionBus.asyncCall({
            service: "org.maki.wmm",
            path: "/org/maki/wmm",
            iface: "org.maki.wmm",
            member: "GetSettings"
        })

        reply.finished.connect(function() {

            if (!reply.isError && reply.value) {
                try {
                    var data = JSON.parse(reply.value)
                    cachedSettings = data.global || data
                }
                catch(e) {
                    console.error(e)
                }
            }
            if (callback)
                callback()
            reply.destroy()
        })
    }

    //----------------------------------------------------------
    // Obtiene bookmarks.json
    //----------------------------------------------------------

    function refreshBookmarks(callback){
        var reply = DBus.SessionBus.asyncCall({
            service: "org.maki.wmm",
            path: "/org/maki/wmm",
            iface: "org.maki.wmm",
            member: "GetBookmarks"
        })
        reply.finished.connect(function() {
            if (!reply.isError && reply.value) {
                try {
                    cachedBookmarks = JSON.parse(reply.value)
                    console.log(
                        "Bookmarks cargados:",
                        Object.keys(cachedBookmarks).length
                    )
                }
                catch(e) {
                    console.error(e)
                }
            }
            if (callback)
                callback()
            reply.destroy()
        })
    }

    //----------------------------------------------------------
    // Sincroniza todos los datos necesarios para construir menú
    //----------------------------------------------------------

    function refreshMenuData(callback)
    {
        var pending = 2

        function finished()
        {
            pending--

            if (pending === 0 && callback)
                callback()
        }

        refreshSettings(finished)
        refreshBookmarks(finished)
    }

    //----------------------------------------------------------
    // Aplica únicamente el estado necesario para la interfaz
    //----------------------------------------------------------

    function applySettings()
    {
        var settings = cachedSettings

        if (!settings)
            return

            slideshowEnabled = settings.slideshow_enabled
            slideshowInterval = settings.slideshow_interval
            slideshowMaxInterval = settings.slideshow_max_interval
            slideshowBookmark = settings.slideshow_bookmark
            syncMode = (settings.slideshow_mode === "sync")
            spannedEnabled = settings.spanned_enabled

            console.log(
                "WMM UI state:",
                "slideshow=", slideshowEnabled,
                "interval=", slideshowInterval,
                "bookmark=", slideshowBookmark,
                "sync=", syncMode,
                "spanned=", spannedEnabled
            )
    }

    // ==========================================================
    // CONSTRUCTORES DE LA INTERFAZ
    // ==========================================================
    //
    // Estos helpers encapsulan la creación de los distintos
    // elementos utilizados por el menú contextual.
    //
    // buildMenu() nunca crea objetos directamente.
    //
    // Toda la construcción del menú pasa por estas funciones.
    //
    // ==========================================================

    //----------------------------------------------------------
    // Acción estándar
    //----------------------------------------------------------

    function createAction(text, iconName, callback){
        var component = Qt.createComponent("Action.qml")
        if (component.status === Component.Ready) {
            var obj = component.createObject(root, {
                text: text,
                icon: {
                    name: iconName
                }
            })
            if (obj) {
                obj.triggered.connect(callback)
                return obj
            }
        }

        //------------------------------------------------------
        // Fallback
        //------------------------------------------------------

        var qml =
                'import org.kde.plasma.core 2.0 as PlasmaCore;' +
                'PlasmaCore.Action {' +
                'text: "' + text + '";' +
                'icon.name: "' + iconName + '"' +
                '}'
        var fallback =
                Qt.createQmlObject(
                    qml,
                    root,
                    "ActionFallback"
                )
        if (fallback) {
            fallback.triggered.connect(callback)
            return fallback
        }
        return null
    }

    //----------------------------------------------------------
    // Separador
    //----------------------------------------------------------

    function createSeparator(){
        var separator =
                createAction(
                    "────────────────────────",
                    "",
                    function(){}
                )
        separator.enabled = false
        return separator
    }

    //----------------------------------------------------------
    // Cabecera de sección
    //----------------------------------------------------------

    function createHeader(title){
        var header =
                createAction(
                    title,
                    "",
                    function(){}
                )
        header.enabled = false
        return header
    }

    //----------------------------------------------------------
    // Entrada informativa
    //----------------------------------------------------------

    function createLabel(text){
        var label =
                createAction(
                    text,
                    "",
                    function(){}
                )
        label.enabled = false
        return label
    }

    //----------------------------------------------------------
    // Checkbox: Slideshow bookmarks
    //----------------------------------------------------------

    function createSlideshowBookmarksAction()
    {
        var action = createAction(
            _("Favorites Only"),
            "bookmark",
            function() {
                root.slideshowBookmark = !root.slideshowBookmark
                action.checked = root.slideshowBookmark
                sendCommand(
                    "update_timer_settings",
                    {
                        slideshow_bookmark: root.slideshowBookmark
                    }
                )
            }
        )

        action.checkable = true
        action.checked = root.slideshowBookmark

        return action
    }

    //----------------------------------------------------------
    // Cargar favorito
    //----------------------------------------------------------

    function createBookmarkAction(bookmarkName)
    {
        return createAction(
            bookmarkName,
            "bookmark",
            function() {
                sendCommand(
                    "load_bookmark",
                    {
                        name: bookmarkName
                    }
                )
            }
        )
    }

    //----------------------------------------------------------
    // Eliminar favorito
    //----------------------------------------------------------

    function createDeleteBookmarkAction(bookmarkName)
    {
        return createAction(
            _("Delete") + ": " + bookmarkName,
            "edit-delete",
            function() {
                sendCommand(
                    "delete_bookmark",
                    {
                        name: bookmarkName
                    }
                )
            }
        )
    }

    //----------------------------------------------------------
    // Añadir favorito
    //----------------------------------------------------------

    function createAddBookmarkAction()
    {
        return createAction(
            _("Add bookmark"),
            "list-add",
            function() {
                sendCommand("add_bookmark")
            }
        )
    }

    // ==========================================================
    // CONSTRUCCIÓN DEL MENÚ CONTEXTUAL
    // ==========================================================
    //
    // Esta función genera completamente el contenido del menú.
    //
    // El menú se construye:
    //
    //     • durante la inicialización del plasmoide
    //     • cuando SettingsChanged notifica un cambio externo
    //
    // De esta forma las acciones ya contienen el estado correcto
    // antes de que Plasma abra el menú contextual.
    //
    // ==========================================================

    function buildMenu(){
        var actions = []

        //------------------------------------------------------
        // Settings
        //------------------------------------------------------
        actions.push(
            createAction(
                _("Settings"),
                "preferences-system",
                function() {
                    sendCommand("open_panel")
                }
            )
        )

        //------------------------------------------------------
        // Displays
        //------------------------------------------------------
        function displayModeText() {
            return _("Displays") + ": " +
            (root.syncMode
            ? _("SYNC (All)")
            : _("ASYNC (One)"))
        }

        var displaysAction = createAction(
            displayModeText(),
            "",
            function() {

                root.syncMode = !root.syncMode

                displaysAction.checked = root.syncMode
                displaysAction.text = displayModeText()

                sendCommand(
                    "update_timer_settings",
                    {
                        mode: root.syncMode ? "sync" : "async"
                    }
                )
            }
        )

        displaysAction.checkable = true
        displaysAction.checked = root.syncMode

        actions.push(displaysAction)

        //------------------------------------------------------
        // Spanned Mode
        //------------------------------------------------------

        var spannedAction = createAction(
            _("Spanned Mode"),
            "",
            function() {
                root.spannedEnabled = !root.spannedEnabled

                spannedAction.checked = root.spannedEnabled

                sendCommand(
                    "update_timer_settings",
                    {
                        spanned_enabled: root.spannedEnabled
                    }
                )
            }
        )

        spannedAction.checkable = true
        spannedAction.checked = root.spannedEnabled

        actions.push(spannedAction)

        //------------------------------------------------------
        // Sync Library
        //------------------------------------------------------

        actions.push(
            createAction(
                _("Sync Library"),
                "view-refresh",
                function() {
                    sendCommand("sync_library")
                }
            )
        )

        //------------------------------------------------------
        // Help
        //------------------------------------------------------

        actions.push(
            createAction(
                _("Help"),
                "help-contents",
                function() {
                    sendCommand("open_help")
                }
            )
        )

        //------------------------------------------------------
        // Exit WMM
        //------------------------------------------------------

        actions.push(createSeparator())

        actions.push(
            createAction(
                _("Exit") + " WMM",
                         "application-exit",
                         function() {
                             var reply = DBus.SessionBus.asyncCall({
                                 service: "org.maki.wmm",
                                 path: "/org/maki/wmm",
                                 iface: "org.maki.wmm",
                                 member: "Shutdown"
                             })

                             reply.finished.connect(function() {
                                 reply.destroy()
                             })
                         }
            )
        )

        //------------------------------------------------------
        // Publicar menú
        //------------------------------------------------------
        menuActions = actions
     }

     // ==========================================================
     // MENÚ CONTEXTUAL
     // ==========================================================
     //
     // Plasma utiliza una lista de acciones mantenida previamente
     // sincronizada con el estado del motor.
     //
     // ==========================================================

     Plasmoid.contextualActions: menuActions

    // ==========================================================
    // INICIALIZACIÓN
    // ==========================================================

    Component.onCompleted: {
        console.log("WMM: Plasma frontend initialized")

        refreshMenuData(function() {

            applySettings()
            buildMenu()

        })
    }

    // ==========================================================
    // FINALIZACIÓN
    // ==========================================================

    Component.onDestruction: {
        console.log("WMM: Plasma frontend unloaded")
    }
}
