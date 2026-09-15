#!/bin/bash
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later
#################################
# wmm-span-image.sh
#################################
# WMM File manager Script Router
# Span image across all active screens
# shell_spanned_image

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
    *mate*)
        ROOT="$DATA_BASE/wmm@maki"
        ;;
esac

if [ -z "$ROOT" ] || [ ! -d "$ROOT" ]; then
    notify-send -u critical "WMM Error" "No se encontró la instalación de WMM para el escritorio: $DESKTOP"
    exit 1
fi

IMAGE_PATH="$1"

CMD=$(python3 -c "import json, sys; print(json.dumps({'action':'shell_spanned_image','image_path':sys.argv[1]}))" "$IMAGE_PATH")
python3 "$ROOT/python/$SCRIPT_NAME" "$CMD"
