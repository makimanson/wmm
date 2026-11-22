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

    property string currentIcon: motorBusy ? "view-refresh" : "video-display"
    Plasmoid.icon: currentIcon
    Plasmoid.onSecondaryActivated: root.sendCommand("force_rotation")

    toolTipMainText: "Wallpaper Multi-Monitor Manager"

    toolTipSubText:
    _("Click action") + ": " + _("Main Menu") + "\n" +
    _("Middle Click") + ": " + _("Next Background") + "\n" +
    _("Secondary Click") + ": " + _("Context Menu")

    property bool spannedEnabled: false
    property bool metadataEnabled: false
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

   // Consultar la combinación efectiva cada vez que se abre el menú.
   // No necesita sincronización permanente ni sondeos.
   onExpandedChanged: {
       if (expanded)
           refreshKeybinding()
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
   property bool motorBusy: true

   // Texto consultado a KGlobalAccel a través del backend existente.
   // No representa una segunda configuración del atajo.
   property string currentKeybinding: ""

   DBus.SignalWatcher {
        service: "org.maki.wmm"
        path: "/org/maki/wmm"
        iface: "org.maki.wmm"

        function dbusSettingsChanged(jsonData) {
            try {
                var data = JSON.parse(jsonData)
                cachedSettings = data.global || data
                applySettings()
            }
            catch(e) {console.error("WMM: Invalid SettingsChanged:", e)}
        }

        function dbusBookmarksChanged(jsonData) {
            try {cachedBookmarks = JSON.parse(jsonData)}
            catch(e) {console.error("WMM: Invalid BookmarksChanged:", e)}
        }

        function dbusBusyChanged(busy) {
            motorBusy = busy
        }
    }

    // ==========================================================
    // COMUNICACIÓN D-BUS
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
        // FRONTEND GUARD:
        // force_rotation es deliberadamente no acumulativo.
        // El frontend descarta nuevas peticiones mientras conoce
        // que una rotación está activa.
        if (action === "force_rotation") {
            if (motorBusy)
                return

                // Cerrar inmediatamente la ventana entre el click local
                // y la recepción posterior de BusyChanged(true).
                motorBusy = true
        }

        var cmd = {
            action: action
        }

        if (params) { for (var key in params) cmd[key] = params[key] }

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

                if (action === "force_rotation")
                    refreshBusyState()
            }

            reply.destroy()
        })
    }

    //----------------------------------------------------------
    // Activa una herramienta independiente del engine
    //----------------------------------------------------------

    function activateIndependentService(serviceName)
    {
        var reply = DBus.SessionBus.asyncCall({
            service: "org.freedesktop.DBus",
            path: "/org/freedesktop/DBus",
            iface: "org.freedesktop.DBus",
            member: "StartServiceByName",
            signature: "(su)",
            arguments: [serviceName, new DBus.uint32(0)]
        })

        reply.finished.connect(function() {
            if (reply.isError) {
                console.error("WMM: Could not activate service:", serviceName, reply.error.message)}

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
                try { var data = JSON.parse(reply.value); cachedSettings = data.global || data }
                catch(e) { console.error(e) }
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
                    console.log("Bookmarks cargados:", Object.keys(cachedBookmarks).length)
                }
                catch(e) { console.error(e) }
            }

            if (callback) callback()
            reply.destroy()
        })
    }

    //----------------------------------------------------------
    // Obtiene el estado busy del engine
    //----------------------------------------------------------

    function refreshBusyState(callback){
        var reply = DBus.SessionBus.asyncCall({
            service: "org.maki.wmm",
            path: "/org/maki/wmm",
            iface: "org.maki.wmm",
            member: "GetBusy"
        })

        reply.finished.connect(function() {
            if (!reply.isError)
                motorBusy = Boolean(reply.value)

                if (callback) callback()
                    reply.destroy()
        })
    }

    //----------------------------------------------------------
    // Recupera el texto del atajo registrado en KDE
    //----------------------------------------------------------

    function refreshKeybinding() {
        var reply = DBus.SessionBus.asyncCall({
            service: "org.maki.wmm",
            path: "/org/maki/wmm",
            iface: "org.maki.wmm",
            member: "GetKeybinding"
        })

        reply.finished.connect(function() {
            if (reply.isError) {
                console.error("WMM: GetKeybinding:", reply.error.message)
                currentKeybinding = ""
            } else {
                currentKeybinding = reply.value || ""
            }

            reply.destroy()
        })
    }

    //----------------------------------------------------------
    // Sincroniza los datos necesarios para la interfaz
    //----------------------------------------------------------

    function refreshMenuData(callback) {
        var pending = 3

        function finished() {
            if (--pending === 0 && callback)
                callback()
        }

        refreshSettings(finished)
        refreshBookmarks(finished)
        refreshBusyState(finished)
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

        // La presentación de metadatos depende del ajuste global del Engine.
        metadataEnabled = Boolean(settings.exif_metadata_enabled)

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
    // CIERRE GLOBAL DE WMM
    // ==========================================================

    function shutdownEngine() {
        var reply = DBus.SessionBus.asyncCall({
            service: "org.maki.wmm",
            path: "/org/maki/wmm",
            iface: "org.maki.wmm",
            member: "Shutdown"
        })

        reply.finished.connect(function() {reply.destroy()})
    }

    // ==========================================================
    // MENÚ CONTEXTUAL
    // ==========================================================
    //
    // Acciones estáticas disponibles desde la inicialización
    // del plasmoide, independientes del estado del engine.
    //
    // ==========================================================

     Plasmoid.contextualActions: [
         PlasmaCore.Action {
             text: root._("Settings")
             icon.name: "preferences-system"
             onTriggered: root.sendCommand("open_panel")
         },
         PlasmaCore.Action {
             text: root._("Sync Library")
             icon.name: "view-refresh"
             onTriggered: root.sendCommand("sync_library")
         },
         PlasmaCore.Action {
             text: root._("Install Manager")
             icon.name: "system-software-install"
             onTriggered: root.activateIndependentService("org.maki.wmm.InstallManager")
         },
         PlasmaCore.Action {
             text: root._("Debug Log Viewer")
             icon.name: "text-x-log"
             onTriggered: root.activateIndependentService("org.maki.wmm.DebugLogViewer")
         },
         PlasmaCore.Action {
             text: root._("Help")
             icon.name: "help-contents"
             onTriggered: root.sendCommand("open_help")
         },
         PlasmaCore.Action {
             isSeparator: true
         },
         PlasmaCore.Action {
             text: root._("Exit") + " WMM"
             icon.name: "application-exit"
             onTriggered: root.shutdownEngine()
         }
     ]

     // ==========================================================
     // LIFECYCLE DEL PLASMOIDE
     // ==========================================================
     //
     // Plasma marca destroyed=true cuando el usuario elimina
     // permanentemente el plasmoide mediante Applet::destroy().
     // No utilizar Component.onDestruction para esta decisión:
     // el QML también puede destruirse durante recargas de Plasma.
     // ==========================================================

     Connections {
         target: plasmoid

         function onDestroyedChanged(destroyed) {
            if (!destroyed)
                return

            console.log("WMM: Plasma frontend removed; shutting down engine")
            root.shutdownEngine()
         }
     }

    // ==========================================================
    // INICIALIZACIÓN
    // ==========================================================

    Component.onCompleted: {
        console.log("WMM: Plasma frontend initialized")
        refreshMenuData(function() {applySettings()})
    }

    // ==========================================================
    // FINALIZACIÓN
    // ==========================================================

    Component.onDestruction: {
        console.log("WMM: Plasma frontend unloaded")
    }
}
