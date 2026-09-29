#!/bin/bash
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later
#################################
# wmm-add_to_bookmarks.sh
#################################
# WMM File manager adapter
# Add selected image to WMM favorites.
# shell_add_favorite

DATA_BASE="${XDG_DATA_HOME:-$HOME/.local/share}"
ROOT="$DATA_BASE/wmm@maki"
SEND_COMMAND="$ROOT/python/send_command.py"

if [ ! -f "$SEND_COMMAND" ]; then
    notify-send -u critical "WMM Error" "No se encontró send_command.py en: $SEND_COMMAND"
    exit 1
fi

IMAGE_PATH="$1"

CMD=$(python3 -c "import json, sys; print(json.dumps({'action':'shell_add_favorite','image_path':sys.argv[1]}))" "$IMAGE_PATH")
python3 "$SEND_COMMAND" "$CMD"
