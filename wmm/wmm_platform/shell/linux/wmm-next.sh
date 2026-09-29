#!/bin/bash
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

# wmm-next.sh - Generic Linux keyboard shortcut helper for WMM wallpaper rotation

exec "@PYTHON3@" "@APP_DIR@/python/send_command.py" '{"action":"force_rotation"}' "HOTKEY"
