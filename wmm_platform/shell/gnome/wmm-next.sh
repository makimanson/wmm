#!/bin/bash
echo '{"action":"force_rotation"}' > ~/.local/share/gnome-shell/extensions/wmm@maki/data/commands.json && pkill -USR1 -f main.py
