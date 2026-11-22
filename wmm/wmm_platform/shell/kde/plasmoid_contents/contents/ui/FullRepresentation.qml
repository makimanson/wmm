/*
 * SPDX-FileCopyrightText: 2026 makimanson
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 ***************************************************************************
 *  WMM - Wallpaper Multi-Monitor Manager
 *
 *  Plasma 6 Frontend
 *
 *  FullRepresentation.qml: Este archivo implementa la interfaz gráfica del plasmoide KDE Plasma.
 */

import QtQuick 2.15
import QtQuick.Layouts 1.15

import org.kde.plasma.components 3.0 as PlasmaComponents
import org.kde.kirigami as Kirigami
import org.kde.plasma.extras as PlasmaExtras

PlasmaExtras.Representation {
    id: menuRepresentation

    // ==========================================================
    // TRADUCCIÓN (dominio centralizado de WMM)
    // ==========================================================

    function _(text) {
        return i18nd("org.maki.wmm", text)
    }

    // ==========================================================
    // REFERENCIA AL PLASMOIDE
    // ==========================================================

    required property var rootItem

    implicitWidth: 260
    implicitHeight: 460

    Kirigami.PromptDialog {
        id: deletePresetDialog

        property string presetName: ""

        title: _("Delete preset")
        PlasmaComponents.Label {
            text: deletePresetDialog.presetName
            ? _("Delete") + ' "' + deletePresetDialog.presetName + '"?'
            : ""

            topPadding: Kirigami.Units.largeSpacing
            wrapMode: Text.WordWrap
        }

        padding: Kirigami.Units.largeSpacing
        preferredWidth: Kirigami.Units.gridUnit * 14

        standardButtons: Kirigami.Dialog.Yes | Kirigami.Dialog.No

        onAccepted: {
            if (presetName)
                rootItem.sendCommand("delete_bookmark", {name: presetName})
        }

        onClosed: presetName = ""
    }

    contentItem: ColumnLayout {

        anchors.fill: parent
        anchors.margins: 12
        spacing: 10

        // ------------------------------------------------------
        // Displays
        // ------------------------------------------------------

        RowLayout {
            Layout.fillWidth: true
            PlasmaComponents.Label {
                text: _("Displays") + ": " +
                (rootItem.syncMode ? _("SYNC (All)") : _("ASYNC (One)"))
                Layout.fillWidth: true
            }

            PlasmaComponents.Switch {
                checked: rootItem.syncMode
                onToggled: rootItem.sendCommand(
                    "update_timer_settings", {mode: checked ? "sync" : "async"})
            }
        }

        // ------------------------------------------------------
        // Spanned Mode
        // ------------------------------------------------------

        RowLayout {
            Layout.fillWidth: true
            PlasmaComponents.Label {text:_("Spanned Mode"); Layout.fillWidth: true}
            PlasmaComponents.Switch {
                checked: rootItem.spannedEnabled
                onToggled: rootItem.sendCommand(
                    "update_timer_settings", {spanned_enabled: checked})
            }
        }

        // ------------------------------------------------------
        // Image Metadata
        // ------------------------------------------------------

        RowLayout {
            Layout.fillWidth: true
            PlasmaComponents.Label {text:_("Image Metadata"); Layout.fillWidth: true}
            PlasmaComponents.Switch {
                checked: rootItem.metadataEnabled
                onToggled: rootItem.sendCommand(
                    "set_metadata_enabled", {enabled: checked})
            }
        }

        PlasmaComponents.MenuSeparator {Layout.fillWidth: true}

        // ------------------------------------------------------
        // Slideshow
        // ------------------------------------------------------

        RowLayout {
            Layout.fillWidth: true
            PlasmaComponents.Label { text: _("Slideshow"); Layout.fillWidth: true }
            PlasmaComponents.Switch {
                checked: rootItem.slideshowEnabled
                onToggled: {rootItem.sendCommand("update_timer_settings", {enabled: checked})}
            }
        }

        PlasmaComponents.Label {text: rootItem.slideshowInterval + " " + _("minutes")}

        PlasmaComponents.Slider {
            Layout.fillWidth: true
            from: 1
            to: rootItem.slideshowMaxInterval
            value: rootItem.slideshowInterval
            onMoved: {
                rootItem.slideshowInterval = value
                rootItem.sendCommand("update_timer_settings", {interval: Math.round(value)})
            }
        }

        PlasmaComponents.MenuSeparator {Layout.fillWidth: true}

        // ------------------------------------------------------
        // Favorites
        // ------------------------------------------------------

        RowLayout {
            Layout.fillWidth: true
            PlasmaComponents.Label {text:_("Favorites Only"); Layout.fillWidth: true}
            PlasmaComponents.Switch {
                checked: rootItem.slideshowBookmark
                onToggled: {
                    rootItem.sendCommand("update_timer_settings", {slideshow_bookmark: checked})
                }
            }
        }

        PlasmaComponents.Button {
            id: addPresetButton

            Layout.fillWidth: true
            text: _("Add Preset Favorite")
            icon.name: "bookmark-new"

            onClicked: {
                // Capturar el punto mientras el plasmoide conserva todavía
                // su geometría; después de cerrarlo ya no es una referencia fiable.
                const anchor = addPresetButton.mapToGlobal(
                    Qt.point(addPresetButton.width / 2,
                             addPresetButton.height / 2))

                rootItem.expanded = false
                rootItem.sendCommand("add_bookmark", {x: Math.round(anchor.x), y: Math.round(anchor.y)})
            }
        }

        PlasmaComponents.ScrollView {

            Layout.fillWidth: true
            Layout.fillHeight: true

            ListView {
                model: Object.keys(rootItem.cachedBookmarks)
                delegate: RowLayout {
                    width: ListView.view.width
                    PlasmaComponents.ItemDelegate {
                        Layout.fillWidth: true
                        text: modelData
                        onClicked: {rootItem.sendCommand("load_bookmark", {name: modelData})}
                    }
                    PlasmaComponents.ToolButton {
                        icon.name: "user-trash"

                        onClicked: {
                            deletePresetDialog.presetName = modelData
                            deletePresetDialog.open()
                        }
                    }
                }
            }
        }

        PlasmaComponents.MenuSeparator {Layout.fillWidth: true}

        PlasmaComponents.Button {
            id: nextBackgroundButton

            Layout.fillWidth: true
            icon.name: "view-refresh"
            enabled: !rootItem.motorBusy

            // Una sola superficie interactiva para toda la fila.
            // El atajo ocupa su propio extremo derecho, sin formar
            // parte del texto de la acción ni alterar sus clics.
            contentItem: RowLayout {
                spacing: Kirigami.Units.smallSpacing

                Kirigami.Icon {
                    source: nextBackgroundButton.icon.name
                    Layout.preferredWidth: Kirigami.Units.iconSizes.small
                    Layout.preferredHeight: Kirigami.Units.iconSizes.small
                }

                PlasmaComponents.Label {
                    text: _("Next Background")
                    Layout.fillWidth: true
                    verticalAlignment: Text.AlignVCenter
                }

                PlasmaComponents.Label {
                    text: rootItem.currentKeybinding
                    font.italic: true
                    visible: text.length > 0
                    Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
                    Layout.rightMargin: Kirigami.Units.smallSpacing * 4
                }
            }

            onClicked: {
                rootItem.sendCommand("force_rotation")
            }

            TapHandler {
                acceptedButtons: Qt.RightButton

                onTapped: {
                    // Capturar el centro del menú antes de cerrarlo.
                    // El formulario GTK utilizará este punto como anclaje.
                    const anchor = menuRepresentation.mapToGlobal(
                        Qt.point(menuRepresentation.width / 2,
                                 menuRepresentation.height / 2))

                    rootItem.expanded = false
                    rootItem.sendCommand("open_keybinding", {
                        x: Math.round(anchor.x),
                                         y: Math.round(anchor.y)
                    })
                }
            }

            PlasmaComponents.ToolTip {
                text: _("Secondary click: assign a keyboard shortcut")
            }
        }
    }
}
