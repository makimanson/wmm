#!/bin/bash
echo '{"action":"force_rotation"}' > ~/.local/share/cinnamon/applets/wmm-applet@maki/data/commands.json && pkill -USR1 -f main.py
