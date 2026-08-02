/*
 * WMM Plugin de Wallpaper - main.qml
 * ===================================
 * Muestra el lienzo maestro generado por el engine.
 *
 * Este plugin es pasivo: solo muestra la imagen y se actualiza
 * automáticamente cuando el engine escribe un nuevo archivo.
 * No tiene lógica de control; toda la inteligencia reside en el engine.
 *
 * Principios:
 * - Sin polling: usa KDirWatch para monitoreo reactivo.
 * - Mínimo código: solo la carga y actualización de la imagen.
 * - Compatible con el flujo de WMM: el engine escribe wallpaper_master.jpg
 *   y el plugin la muestra sin intervención adicional.
 */

import QtQuick 2.15
import org.kde.plasma.wallpapers.image 2.0
import org.kde.kcoreaddons 1.0 as KCoreAddons

ImageWallpaper {
    id: root

    // Ruta de la imagen generada por el engine
    readonly property string wallpaperPath: "file://" + KCoreAddons.StandardDirs.cacheHome() + "/wmm/wallpaper_master.jpg"

    // Monitor reactivo de cambios en el archivo (sin polling)
    KCoreAddons.KDirWatch {
        id: fileWatcher
        onCreated: root.reloadImage()
        onDirty: root.reloadImage()
        onModified: root.reloadImage()

        Component.onCompleted: {
            // Eliminar protocolo file:// para KDirWatch
            var localPath = wallpaperPath.replace("file://", "")
            addFile(localPath)
        }
    }

    // Cargar la imagen al iniciar
    Component.onCompleted: {
        source = wallpaperPath
    }

    /*
     * reloadImage()
     * Fuerza la recarga de la imagen cuando el motor la sobrescribe.
     * La breve asignación a cadena vacía es necesaria para que QML
     * detecte el cambio y vuelva a cargar el archivo desde disco.
     */
    function reloadImage() {
        source = ""
        source = wallpaperPath
    }
}
