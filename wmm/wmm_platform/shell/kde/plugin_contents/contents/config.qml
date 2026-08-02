/*
 * WMM Plugin de Wallpaper - Configuración
 * ========================================
 * Interfaz de diagnóstico y control para ajustar la configuración de KDE
 * necesaria para que WMM funcione correctamente.
 *
 * Muestra y permite modificar:
 * - FillMode (modo de relleno: 0=Escalado, 1=Escalado y recorte, 2=Zoom, 3=Span)
 * - Plugin de wallpaper activo
 * - Slideshow nativo de KDE (activado/desactivado)
 * - Color de fondo (activado/desactivado) y color actual
 * - Estado del engine de WMM
 *
 * Esta interfaz nos servirá para identificar la combinación exacta
 * que hace que WMM funcione en Plasma 6.
 */

import QtQuick 2.15
import QtQuick.Controls 2.15 as Controls
import org.kde.kirigami 2.20 as Kirigami
import org.kde.plasma.core 2.0 as PlasmaCore
import org.kde.plasma.components 3.0 as PlasmaComponents
import org.kde.kcoreaddons 1.0 as KCoreAddons

PlasmaComponents.Page {
    id: configPage

    // ==========================================================
    // 1. PROPIEDADES DE ESTADO
    // ==========================================================

    property string currentFillMode: "desconocido"
    property string currentPlugin: "desconocido"
    property bool slideshowEnabled: false
    property bool backgroundModeEnabled: true      // true = "Solid", false = "None"
    property string currentColor: "#000000"
    property string wallpaperPath: ""
    property string engineStatus: "desconocido"
    property bool isApplying: false

    // ==========================================================
    // 2. RUTAS (mismo engine que el plasmoide)
    // ==========================================================

    readonly property string engineDir:
        KCoreAddons.StandardDirs.writableLocation(KCoreAddons.StandardDirs.GenericDataLocation)
        + "/plasma/org.maki.wmm"

    readonly property string settingsPath: engineDir + "/data/settings.json"
    readonly property string commandsPath: engineDir + "/data/commands.json"

    // La imagen maestra se genera en la caché
    readonly property string masterImagePath:
        KCoreAddons.StandardDirs.cacheHome() + "/wmm/wallpaper_master.jpg"

    // ==========================================================
    // 3. FUNCIONES DE LECTURA (diagnóstico)
    // ==========================================================

    /*
     * readFillMode()
     * Lee el FillMode actual de KDE usando kreadconfig6.
     * Retorna el valor numérico (0-3) o -1 si no se puede leer.
     */
    function readFillMode() {
        try {
            var process = new QProcess()
            process.command = "kreadconfig6"
            process.arguments = ["--file", "plasmarc", "--group", "Wallpaper", "--key", "fillMode"]
            process.finished.connect(function(exitCode, exitStatus) {
                if (exitStatus === QProcess.NormalExit && exitCode === 0) {
                    var output = process.readAllStandardOutput()
                    var fillMode = parseInt(output.toString().trim())
                    if (!isNaN(fillMode)) {
                        currentFillMode = fillMode.toString()
                        fillModeLabel.text = currentFillMode
                    }
                }
            })
            process.start()
        } catch(e) {
            console.log("WMM config: Error reading fillMode:", e)
        }
    }

    /*
     * readPlugin()
     * Lee el plugin de wallpaper activo.
     * Retorna el nombre del plugin o cadena vacía.
     */
    function readPlugin() {
        try {
            var process = new QProcess()
            process.command = "kreadconfig6"
            process.arguments = ["--file", "plasmarc", "--group", "Wallpaper", "--key", "plugin"]
            process.finished.connect(function(exitCode, exitStatus) {
                if (exitStatus === QProcess.NormalExit && exitCode === 0) {
                    var output = process.readAllStandardOutput()
                    currentPlugin = output.toString().trim() || "ninguno"
                    pluginLabel.text = currentPlugin
                }
            })
            process.start()
        } catch(e) {
            console.log("WMM config: Error reading plugin:", e)
        }
    }

    /*
     * readSlideshow()
     * Lee si el slideshow nativo está activo.
     * Retorna true/false.
     */
    function readSlideshow() {
        try {
            var process = new QProcess()
            process.command = "kreadconfig6"
            process.arguments = ["--file", "plasmarc", "--group", "Wallpaper", "--key", "slideshow"]
            process.finished.connect(function(exitCode, exitStatus) {
                if (exitStatus === QProcess.NormalExit && exitCode === 0) {
                    var output = process.readAllStandardOutput()
                    slideshowEnabled = output.toString().trim() === "true"
                    slideshowSwitch.checked = slideshowEnabled
                    slideshowControlSwitch.checked = slideshowEnabled
                }
            })
            process.start()
        } catch(e) {
            console.log("WMM config: Error reading slideshow:", e)
        }
    }

    /*
     * readBackgroundMode()
     * Lee el modo de fondo actual de KDE.
     * Retorna "Solid", "Image", "None" o cadena vacía.
     */
    function readBackgroundMode() {
        try {
            var process = new QProcess()
            process.command = "kreadconfig6"
            process.arguments = ["--file", "plasmarc", "--group", "Wallpaper", "--key", "backgroundMode"]
            process.finished.connect(function(exitCode, exitStatus) {
                if (exitStatus === QProcess.NormalExit && exitCode === 0) {
                    var output = process.readAllStandardOutput()
                    var mode = output.toString().trim()
                    backgroundModeEnabled = (mode !== "None")
                    backgroundModeSwitch.checked = backgroundModeEnabled
                    backgroundControlSwitch.checked = backgroundModeEnabled
                }
            })
            process.start()
        } catch(e) {
            console.log("WMM config: Error reading backgroundMode:", e)
        }
    }

    /*
     * readColor()
     * Lee el color de fondo actual.
     * Retorna cadena en formato #RRGGBB o vacío.
     */
    function readColor() {
        try {
            var process = new QProcess()
            process.command = "kreadconfig6"
            process.arguments = ["--file", "plasmarc", "--group", "Wallpaper", "--key", "color"]
            process.finished.connect(function(exitCode, exitStatus) {
                if (exitStatus === QProcess.NormalExit && exitCode === 0) {
                    var output = process.readAllStandardOutput()
                    currentColor = output.toString().trim() || "#000000"
                    colorDisplay.text = currentColor
                }
            })
            process.start()
        } catch(e) {
            console.log("WMM config: Error reading color:", e)
        }
    }

    /*
     * readWallpaperPath()
     * Lee la ruta de la imagen actual del wallpaper desde el archivo de estado.
     */
    function readWallpaperPath() {
        wallpaperPathLabel.text = masterImagePath
    }

    /*
     * readEngineStatus()
     * Lee el estado del engine desde engine_status.json.
     */
    function readEngineStatus() {
        var statusPath = KCoreAddons.StandardDirs.cacheHome() + "/wmm/engine_status.json"
        try {
            var process = new QProcess()
            process.command = "cat"
            process.arguments = [statusPath]
            process.finished.connect(function(exitCode, exitStatus) {
                if (exitStatus === QProcess.NormalExit && exitCode === 0) {
                    try {
                        var output = process.readAllStandardOutput()
                        var data = JSON.parse(output.toString())
                        engineStatus = data.busy ? "ocupado" : "idle"
                    } catch(e) {
                        engineStatus = "error"
                    }
                } else {
                    engineStatus = "no running"
                }
                engineStatusLabel.text = engineStatus
            })
            process.start()
        } catch(e) {
            console.log("WMM config: Error reading engine status:", e)
        }
    }

    // ==========================================================
    // 4. FUNCIONES DE ESCRITURA (control)
    // ==========================================================

    /*
     * applyFillMode(mode)
     * Escribe el FillMode en KDE usando kwriteconfig6.
     * mode: 0, 1, 2, 3
     */
    function applyFillMode(mode) {
        try {
            var process = new Process()
            process.command = "kwriteconfig6"
            process.arguments = ["--file", "plasmarc", "--group", "Wallpaper", "--key", "fillMode", mode.toString()]
            process.start()
            process.waitForFinished()
            console.log("WMM config: FillMode set to", mode)
            return true
        } catch(e) {
            console.log("WMM config: Error setting fillMode:", e)
            return false
        }
    }

    /*
     * applyPlugin(plugin)
     * Cambia el plugin de wallpaper activo.
     * plugin: "org.kde.image", "org.maki.wmm", etc.
     */
    function applyPlugin(plugin) {
        try {
            var process = new Process()
            process.command = "kwriteconfig6"
            process.arguments = ["--file", "plasmarc", "--group", "Wallpaper", "--key", "plugin", plugin]
            process.start()
            process.waitForFinished()
            console.log("WMM config: Plugin set to", plugin)
            return true
        } catch(e) {
            console.log("WMM config: Error setting plugin:", e)
            return false
        }
    }

    /*
     * applySlideshow(enabled)
     * Activa o desactiva el slideshow nativo.
     */
    function applySlideshow(enabled) {
        try {
            var process = new Process()
            process.command = "kwriteconfig6"
            process.arguments = ["--file", "plasmarc", "--group", "Wallpaper", "--key", "slideshow", enabled ? "true" : "false"]
            process.start()
            process.waitForFinished()
            console.log("WMM config: Slideshow set to", enabled)
            return true
        } catch(e) {
            console.log("WMM config: Error setting slideshow:", e)
            return false
        }
    }

    /*
     * applyBackgroundMode(enabled)
     * Activa/desactiva el color de fondo.
     * enabled: true -> establece "Solid", false -> establece "None"
     */
    function applyBackgroundMode(enabled) {
        try {
            var mode = enabled ? "Solid" : "None"
            var process = new Process()
            process.command = "kwriteconfig6"
            process.arguments = ["--file", "plasmarc", "--group", "Wallpaper", "--key", "backgroundMode", mode]
            process.start()
            process.waitForFinished()
            console.log("WMM config: BackgroundMode set to", mode)
            return true
        } catch(e) {
            console.log("WMM config: Error setting backgroundMode:", e)
            return false
        }
    }

    /*
     * reloadWallpaper()
     * Fuerza la recarga del wallpaper actual mediante D-Bus.
     */
    function reloadWallpaper() {
        try {
            var process = new Process()
            process.command = "qdbus"
            process.arguments = [
                "org.kde.plasmashell",
                "/PlasmaShell",
                "org.kde.PlasmaShell.evaluateScript",
                "var d = desktops()[0]; d.reloadConfig();"
            ]
            process.start()
            process.waitForFinished()
            console.log("WMM config: Wallpaper reloaded")
            return true
        } catch(e) {
            console.log("WMM config: Error reloading wallpaper:", e)
            return false
        }
    }

    /*
     * sendCommand(command)
     * Envía un comando al engine de WMM mediante commands.json.
     */
    function sendCommand(command) {
        try {
            var file = Platform.File
            var content = JSON.stringify(command, null, 4)
            file.write(commandsPath, content)
            console.log("WMM config: Command sent to engine:", command)
        } catch(e) {
            console.log("WMM config: Error sending command:", e)
        }
    }

    // ==========================================================
    // 5. ACTUALIZACIÓN DE LA UI
    // ==========================================================

    /*
     * refreshAll()
     * Lee todos los valores y actualiza la interfaz.
     * Se ejecuta al iniciar y al pulsar "Refresh".
     */
    function refreshAll() {
        var fillMode = readFillMode()
        currentFillMode = fillMode !== -1 ? fillMode.toString() : "no leído"

        var plugin = readPlugin()
        currentPlugin = plugin || "ninguno"

        slideshowEnabled = readSlideshow()

        var bgMode = readBackgroundMode()
        backgroundModeEnabled = (bgMode !== "None")
        currentColor = readColor() || "#000000"

        wallpaperPath = readWallpaperPath()
        engineStatus = readEngineStatus()

        // Actualizar los elementos de la UI manualmente
        fillModeLabel.text = currentFillMode
        pluginLabel.text = currentPlugin
        slideshowSwitch.checked = slideshowEnabled
        backgroundModeSwitch.checked = backgroundModeEnabled
        colorDisplay.text = currentColor
        wallpaperPathLabel.text = wallpaperPath || "no disponible"
        engineStatusLabel.text = engineStatus

        // Actualizar el combo de FillMode
        var index = fillModeCombo.find(currentFillMode)
        if (index >= 0) fillModeCombo.currentIndex = index

        // Actualizar el switch de control manual de slideshow
        slideshowControlSwitch.checked = slideshowEnabled

        // Actualizar el switch de control manual de color de fondo
        backgroundControlSwitch.checked = backgroundModeEnabled
    }

    // ==========================================================
    // 6. INTERFAZ DE USUARIO
    // ==========================================================

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Kirigami.Units.largeSpacing
        spacing: Kirigami.Units.mediumSpacing

        // --- Título ---
        Kirigami.Heading {
            level: 2
            text: "WMM - KDE Plasma Diagnostics"
            Layout.fillWidth: true
        }

        Kirigami.Separator {
            Layout.fillWidth: true
        }

        // --- Sección: Diagnóstico ---
        Kirigami.Heading {
            level: 3
            text: "Diagnóstico actual"
            Layout.fillWidth: true
        }

        GridLayout {
            columns: 2
            rowSpacing: Kirigami.Units.smallSpacing
            columnSpacing: Kirigami.Units.mediumSpacing
            Layout.fillWidth: true

            Controls.Label { text: "FillMode:" }
            Controls.Label {
                id: fillModeLabel
                text: "cargando..."
                font.bold: true
            }

            Controls.Label { text: "Plugin activo:" }
            Controls.Label {
                id: pluginLabel
                text: "cargando..."
                font.bold: true
            }

            Controls.Label { text: "Slideshow nativo:" }
            Controls.Switch {
                id: slideshowSwitch
                enabled: false
                checked: false
            }

            Controls.Label { text: "Color de fondo:" }
            RowLayout {
                Controls.Switch {
                    id: backgroundModeSwitch
                    enabled: false
                    checked: true
                }
                Controls.Label {
                    id: colorDisplay
                    text: "#000000"
                    Layout.minimumWidth: 80
                    font.bold: true
                }
            }

            Controls.Label { text: "Imagen actual:" }
            Controls.Label {
                id: wallpaperPathLabel
                text: "cargando..."
                font.bold: true
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }

            Controls.Label { text: "Estado del engine:" }
            Controls.Label {
                id: engineStatusLabel
                text: "cargando..."
                font.bold: true
            }
        }

        Kirigami.Separator {
            Layout.fillWidth: true
        }

        // --- Sección: Acciones ---
        Kirigami.Heading {
            level: 3
            text: "Control manual"
            Layout.fillWidth: true
        }

        RowLayout {
            Controls.Label { text: "Set FillMode:" }
            Controls.ComboBox {
                id: fillModeCombo
                model: ["0 (Escalado)", "1 (Escalado y recorte)", "2 (Zoom)", "3 (Span)"]
                currentIndex: 3
                Layout.preferredWidth: 200
            }
            Controls.Button {
                text: "Aplicar"
                onClicked: {
                    var mode = fillModeCombo.currentIndex
                    if (applyFillMode(mode)) {
                        refreshAll()
                        reloadWallpaper()
                    }
                }
            }
        }

        RowLayout {
            Controls.Label { text: "Set plugin:" }
            Controls.ComboBox {
                id: pluginCombo
                model: ["org.kde.image", "org.maki.wmm"]
                currentIndex: 1
                Layout.preferredWidth: 200
            }
            Controls.Button {
                text: "Aplicar"
                onClicked: {
                    var plugin = pluginCombo.model[pluginCombo.currentIndex]
                    if (applyPlugin(plugin)) {
                        refreshAll()
                        reloadWallpaper()
                    }
                }
            }
        }

        RowLayout {
            Controls.Label { text: "Slideshow:" }
            Controls.Switch {
                id: slideshowControlSwitch
                checked: slideshowEnabled
                onCheckedChanged: {
                    applySlideshow(checked)
                    refreshAll()
                    reloadWallpaper()
                }
            }
        }

        RowLayout {
            Controls.Label { text: "Color de fondo:" }
            Controls.Switch {
                id: backgroundControlSwitch
                checked: backgroundModeEnabled
                onCheckedChanged: {
                    applyBackgroundMode(checked)
                    refreshAll()
                    reloadWallpaper()
                }
            }
        }

        RowLayout {
            Controls.Button {
                text: "Recargar wallpaper"
                icon.name: "view-refresh"
                onClicked: {
                    reloadWallpaper()
                }
            }
            Controls.Button {
                text: "Refresh state"
                icon.name: "view-refresh"
                onClicked: refreshAll()
            }
            Controls.Button {
                text: "Force rotation (WMM)"
                icon.name: "media-seek-forward"
                onClicked: {
                    sendCommand({ action: "force_rotation" })
                }
            }
            Controls.Button {
                text: "Sync library"
                icon.name: "folder-sync"
                onClicked: {
                    sendCommand({ action: "sync_library" })
                }
            }
        }

        // --- Sección: Notas ---
        Kirigami.Separator {
            Layout.fillWidth: true
        }

        Controls.Label {
            text: "Nota: Los cambios en FillMode, plugin, slideshow y color de fondo se aplican directamente a KDE.\n" +
                  "Los comandos de WMM se envían al engine mediante commands.json."
            wrapMode: Text.WordWrap
            font.italic: true
            color: "gray"
            Layout.fillWidth: true
        }
    }

    // ==========================================================
    // 7. INICIALIZACIÓN
    // ==========================================================

    Component.onCompleted: {
        // Retardo mínimo para no bloquear la carga de Plasma
        loadTimer.start()
    }

    Timer {
        id: loadTimer
        interval: 100
        repeat: false
        onTriggered: refreshAll()
    }
}
