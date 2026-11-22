@echo off
rem SPDX-FileCopyrightText: 2026 makimanson
rem SPDX-License-Identifier: GPL-3.0-or-later

rem WMM - Wallpaper Multi-Monitor Manager
rem Windows installer launcher

rem Launch PowerShell with Windows Forms support.
rem Bypass applies only to this process, not the system policy.
powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File "%~dp0wmm-install.ps1"

exit /b %ERRORLEVEL%