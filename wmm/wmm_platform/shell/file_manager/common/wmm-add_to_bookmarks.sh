#!/bin/bash
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later
#################################
# wmm-add_to_bookmarks.sh
#################################
# WMM File manager Script Router
# Actúa como intermediario para ejecutar el script de Python correcto
# según el escritorio que esté activo en este momento.
# shell_add_favorite

SCRIPT_NAME="send_command.py"

DESKTOP="${XDG_CURRENT_DESKTOP:-${DESKTOP_SESSION:-unknown}}"
DESKTOP=$(echo "$DESKTOP" | tr '[:upper:]' '[:lower:]')
DATA_BASE="${XDG_DATA_HOME:-$HOME/.local/share}"

ROOT=""

case "$DESKTOP" in
    *cinnamon*)
        ROOT="$DATA_BASE/cinnamon/applets/wmm@maki"
        ;;
    *gnome*|*ubuntu*)
        ROOT="$DATA_BASE/gnome-shell/extensions/wmm@maki"
        ;;
    *kde*|*plasma*)
        ROOT="$DATA_BASE/plasma/org.maki.wmm"
        ;;
    *mate*)
        ROOT="$DATA_BASE/wmm@maki"
        ;;
    *)
        if [ -d "$DATA_BASE/cinnamon/applets/wmm@maki" ]; then
            ROOT="$DATA_BASE/cinnamon/applets/wmm@maki"
        elif [ -d "$DATA_BASE/gnome-shell/extensions/wmm@maki" ]; then
            ROOT="$DATA_BASE/gnome-shell/extensions/wmm@maki"
        fi
        ;;
esac

if [ -z "$ROOT" ] || [ ! -d "$ROOT" ]; then
    notify-send -u critical "WMM Error" "No se encontró la instalación de WMM para el escritorio: $DESKTOP"
    exit 1
fi

# Obtener la ruta de la imagen: desde variable de entorno (Nautilus) o desde argumentos (Nemo)
if [ -n "$NAUTILUS_SCRIPT_SELECTED_FILE_PATHS" ]; then
    IMAGE_PATH=$(echo "$NAUTILUS_SCRIPT_SELECTED_FILE_PATHS" | head -n1)
else
    IMAGE_PATH="$1"
fi
# Ejecutar el script de Python objetivo con los argumentos restantes
CMD=$(python3 -c "import json, sys; print(json.dumps({'action':'shell_add_favorite','image_path':sys.argv[1]}))" "$IMAGE_PATH")
python3 "$ROOT/python/$SCRIPT_NAME" "$CMD"
