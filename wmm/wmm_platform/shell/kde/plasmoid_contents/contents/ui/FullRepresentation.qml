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
import org.kde.plasma.extras as PlasmaExtras

PlasmaExtras.Representation {

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
    implicitHeight: 360

    contentItem: ColumnLayout {

        anchors.fill: parent
        anchors.margins: 12
        spacing: 10

        // ------------------------------------------------------
        // Slideshow
        // ------------------------------------------------------

        RowLayout {

            Layout.fillWidth: true

            PlasmaComponents.Label {
                text: _("Slideshow")
                Layout.fillWidth: true
            }

            PlasmaComponents.Switch {

                checked: rootItem.slideshowEnabled

                onToggled: {
                    rootItem.sendCommand(
                        "update_timer_settings",
                        {
                            enabled: checked
                        }
                    )
                }
            }
        }

        PlasmaComponents.Label {
            text: rootItem.slideshowInterval + " " + _("minutes")
        }

        PlasmaComponents.Slider {

            Layout.fillWidth: true

            from: 1
            to: rootItem.slideshowMaxInterval

            value: rootItem.slideshowInterval

            onMoved: {

                rootItem.slideshowInterval = value

                rootItem.sendCommand(
                    "update_timer_settings",
                    {
                        interval: Math.round(value)
                    }
                )
            }
        }

        PlasmaComponents.MenuSeparator {
            Layout.fillWidth: true
        }

        // ------------------------------------------------------
        // Favorites
        // ------------------------------------------------------

        RowLayout {

            Layout.fillWidth: true

            PlasmaComponents.Label {
                text: _("Favorites Only")
                Layout.fillWidth: true
            }

            PlasmaComponents.Switch {

                checked: rootItem.slideshowBookmark

                onToggled: {

                    rootItem.sendCommand(
                        "update_timer_settings",
                        {
                            slideshow_bookmark: checked
                        }
                    )
                }
            }
        }

        PlasmaComponents.Button {

            Layout.fillWidth: true

            text: _("Add Preset Favorite")

            icon.name: "bookmark-new"

            onClicked: {
                rootItem.sendCommand("add_bookmark")
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

                        onClicked: {

                            rootItem.sendCommand(
                                "load_bookmark",
                                {
                                    name: modelData
                                }
                            )
                        }
                    }

                    PlasmaComponents.ToolButton {

                        icon.name: "user-trash"

                        onClicked: {

                            rootItem.sendCommand(
                                "delete_bookmark",
                                {
                                    name: modelData
                                }
                            )
                        }
                    }
                }
            }
        }
        PlasmaComponents.MenuSeparator {
            Layout.fillWidth: true
        }

        PlasmaComponents.Button {

            Layout.fillWidth: true

            text: _("Next Background")

            icon.name: "view-refresh"

            onClicked: {
                rootItem.sendCommand(
                    "force_rotation"
                )
            }
        }
    }
}
