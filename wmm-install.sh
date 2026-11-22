#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

# WMM - Wallpaper Multi-Monitor Manager
# Installation / Upgrade / Repair Manager

set -u
set -o pipefail
trap 'if [ "${WMM_INSTALL_MANAGER:-0}" != "1" ] && [ -t 0 ]; then echo ""; read -r -p "Press Enter to exit..." _ || true; fi' EXIT

# Colores de salida
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
DIM='\033[2m'
NC='\033[0m'
ok()   { printf "${GREEN}[OK]${NC} %s\n" "$1"; }
info() { printf "[..] %s\n" "$1"; }
warn() { printf "${YELLOW}[!!]${NC} %s\n" "$1" >&2; }
fail() { printf "${RED}[!!]${NC} %s\n" "$1" >&2; }

# ----------------------------------------------------------
# Paquete de instalación
# Los documentos del repositorio se instalan junto al árbol WMM.
# ----------------------------------------------------------
INSTALLER_FILE="$(realpath "$0")"
SCRIPT_DIR="$(dirname "$INSTALLER_FILE")"
PROJECT_DIR="$SCRIPT_DIR/wmm"
README_FILE="$SCRIPT_DIR/README.md"
CHANGELOG_FILE="$SCRIPT_DIR/CHANGELOG.md"
LICENSE_FILE="$SCRIPT_DIR/LICENSE"
UNINSTALLER="$SCRIPT_DIR/wmm-uninstall.sh"
INSTALLER_REL_DIR="wmm_platform/shell/installer"

[ -f "$README_FILE" ] || { fail "README.md not found."; exit 1; }
[ -f "$CHANGELOG_FILE" ] || { fail "CHANGELOG.md not found."; exit 1; }
[ -f "$LICENSE_FILE" ] || { fail "LICENSE not found."; exit 1; }
[ -f "$UNINSTALLER" ] || { fail "wmm-uninstall.sh not found."; exit 1; }

# Versión y año pertenecen siempre a la misma cabecera.
# Si no contiene una fecha válida, la versión sigue siendo instalable sin año de release.
WMM_VERSION=''
WMM_RELEASE_YEAR=''
read -r WMM_VERSION WMM_RELEASE_YEAR < <(
    awk '
        $1=="#" && $2~/^v[0-9]+\.[0-9]+\.[0-9]+$/ {
            version=$2
            sub(/^v/,"",version)
            release_year="null"

            if ($3=="-" && $4~/^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]$/)
                release_year=substr($4,1,4)

            print version, release_year
            exit
        }
    ' "$CHANGELOG_FILE"
)

[[ "$WMM_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { fail "Could not determine WMM version."; exit 1; }

# ----------------------------------------------------------
# Context: detected once for the whole run
# ----------------------------------------------------------
PLATFORM="$(uname -s | tr '[:upper:]' '[:lower:]')"
[ "$PLATFORM" = "linux" ] || { fail "Unsupported platform: $PLATFORM"; exit 1; }

DESKTOP="${XDG_CURRENT_DESKTOP:-${DESKTOP_SESSION:-unknown}}"
DESKTOP="$(printf '%s' "$DESKTOP" | tr '[:upper:]' '[:lower:]')"

# Normalizar los nombres que puede exponer la sesión.
case "$DESKTOP" in
    x-cinnamon|cinnamon2d) DESKTOP=cinnamon ;;
    ubuntu*|gnome*)        DESKTOP=gnome ;;
    kde*|plasma*)          DESKTOP=kde ;;
    mate*)                 DESKTOP=mate ;;
    xfce*)                 DESKTOP=xfce ;;
esac

# Confirmar que el escritorio detectado está realmente disponible.
case "$DESKTOP" in
    cinnamon) command -v cinnamon >/dev/null 2>&1 || DESKTOP=unknown ;;
    gnome) command -v gnome-shell >/dev/null 2>&1 || DESKTOP=unknown ;;
    kde)
        command -v plasmashell >/dev/null 2>&1 || DESKTOP=unknown
        if [ "$DESKTOP" = kde ]; then
            PLASMA_VERSION="$(plasmashell --version 2>/dev/null | awk '{print $2}')"
            PLASMA_MAJOR="${PLASMA_VERSION%%.*}"
            [ -n "$PLASMA_MAJOR" ] && [ "$PLASMA_MAJOR" -ge 6 ] 2>/dev/null \
                || { fail "WMM requires KDE Plasma 6 or newer. Detected: ${PLASMA_VERSION:-unknown}"; exit 1; }
        fi
        ;;
    mate) command -v mate-panel >/dev/null 2>&1 || DESKTOP=unknown ;;
    xfce) command -v xfce4-panel >/dev/null 2>&1 || DESKTOP=unknown ;;
    *) DESKTOP=unknown ;;
esac
[ "$DESKTOP" != unknown ] || { fail "Could not detect a supported desktop environment."; exit 1; }

# Detectar el motor gráfico de la sesión.
if [ -n "${WAYLAND_DISPLAY:-}" ] || [ "${XDG_SESSION_TYPE:-}" = wayland ]; then
    GRAPHICS_ENGINE=wayland
else
    GRAPHICS_ENGINE=x11
fi
DATA_BASE="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_BASE="${XDG_CONFIG_HOME:-$HOME/.config}"
CACHE_BASE="${XDG_CACHE_HOME:-$HOME/.cache}"
SYSTEM_DATA_DIRS="${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"

# Identidad y rutas comunes de WMM.
WMM_ID='wmm@maki'
APP_DIR="$DATA_BASE/$WMM_ID"
APP_CONFIG="$CONFIG_BASE/$WMM_ID"
DATA_DIR="$APP_CONFIG/data"
CACHE_DIR="$CACHE_BASE/wmm"
LOCALE_DIR="$DATA_BASE/locale"

DBUS_DIR="$DATA_BASE/dbus-1/services"
APPLICATIONS_DIR="$DATA_BASE/applications"
AUTOSTART_DIR="$CONFIG_BASE/autostart"

LEGACY_APP_DIR=""
FRONTEND_DIR=""
LAUNCHER=""
PLASMOID_DIR=""
AUTOSTART=""
MATE_APPLETS_DIR=""
MATE_DESCRIPTOR=""
MATE_SERVICE=""
INSTALL_MANAGER_SERVICE=""
DEBUG_LOG_VIEWER_SERVICE=""
LEGACY_KDE_LAUNCHER=""
LEGACY_KDE_AUTOSTART=""

# Resolver las rutas propias de cada escritorio.
case "$DESKTOP" in

    cinnamon)
        APP_DOMAIN='wmm@maki'
        FRONTEND_DIR="$DATA_BASE/cinnamon/applets/$APP_DOMAIN"
        LEGACY_APP_DIR="$DATA_BASE/cinnamon/applets/wmm-applet@maki"
        LAUNCHER="$APPLICATIONS_DIR/org.maki.wmm.cinnamon.desktop"
        ;;

    gnome)
        APP_DOMAIN='wmm@maki'
        FRONTEND_DIR="$DATA_BASE/gnome-shell/extensions/$APP_DOMAIN"
        LAUNCHER="$APPLICATIONS_DIR/org.maki.wmm.gnome.desktop"
        ;;

    kde)
        APP_DOMAIN='org.maki.wmm'
        LEGACY_APP_DIR="$DATA_BASE/plasma/$APP_DOMAIN"
        PLASMOID_DIR="$DATA_BASE/plasma/plasmoids/$APP_DOMAIN"
        FRONTEND_DIR="$PLASMOID_DIR"
        KDE_ABOUT_ICON="$DATA_BASE/icons/hicolor/128x128/apps/org.maki.wmm.png"
        LAUNCHER="$APPLICATIONS_DIR/org.maki.wmm.kde.desktop"
        AUTOSTART="$AUTOSTART_DIR/org.maki.wmm.kde.desktop"
        LEGACY_KDE_LAUNCHER="$APPLICATIONS_DIR/org.maki.wmm.desktop"
        LEGACY_KDE_AUTOSTART="$AUTOSTART_DIR/org.maki.wmm.desktop"
        INSTALL_MANAGER_SERVICE="$DBUS_DIR/org.maki.wmm.InstallManager.service"
        DEBUG_LOG_VIEWER_SERVICE="$DBUS_DIR/org.maki.wmm.DebugLogViewer.service"
        ;;

    mate)
        APP_DOMAIN='wmm@maki'
        FRONTEND_DIR="$APP_DIR/frontends/mate"
        LAUNCHER="$APPLICATIONS_DIR/org.maki.wmm.mate.desktop"
        MATE_SERVICE="$DBUS_DIR/org.mate.panel.applet.WMMAppletFactory.service"

        IFS=':' read -ra _dirs <<< "$SYSTEM_DATA_DIRS"
        for d in "${_dirs[@]}"; do
            if [ -d "$d/mate-panel/applets" ]; then
                MATE_APPLETS_DIR="$d/mate-panel/applets"
                break
            fi
        done

        [ -n "$MATE_APPLETS_DIR" ] || {
            fail "Unable to locate the MATE Panel applets directory."
            exit 1
        }

        MATE_DESCRIPTOR="$MATE_APPLETS_DIR/org.maki.wmm.mate-panel-applet"
        ;;

    xfce)
        APP_DOMAIN='wmm@maki'
        FRONTEND_DIR="$APP_DIR/frontends/xfce"
        LAUNCHER="$APPLICATIONS_DIR/org.maki.wmm.xfce.desktop"
        AUTOSTART="$AUTOSTART_DIR/org.maki.wmm.xfce.desktop"
        WMM_NEXT="/usr/local/bin/wmm-next.sh"
        ;;
esac

# Servicio D-Bus común del engine WMM.
DBUS_SERVICE="$DBUS_DIR/org.maki.wmm.service"

# ----------------------------------------------------------
# Installed state and version
# about.json -> metadata.json fallback
# ----------------------------------------------------------
WMM_PRESENT=0
INSTALLED_ROOT=""
INSTALLED_DATA_DIR=""
INSTALLED_VERSION=""
INSTALLED_VERSION_SOURCE=""

# GNOME conserva en memoria el módulo JS de una extensión durante la sesión.
# Sólo es seguro relanzarla en caliente cuando tanto su topología como
# extension.js siguen siendo compatibles con el frontend ya cargado.
GNOME_SESSION_RESTART_REQUIRED=0

# Lee una cadena simple de un JSON de metadatos sin añadir dependencias externas.
json_value() { [ -f "$1" ] && sed -n "s/.*\"$2\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p" "$1" | head -n1; }

# Valida el formato de versión que usa WMM: X.Y.Z.
valid_version() { [[ "${1:-}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; }

# Comprueba que un servicio instalado pertenece realmente a la ruta WMM esperada.
service_owned_by() { [ -f "$1" ] && grep -Fq "$2" "$1"; }

# Comprueba que el helper global conserva la firma de autoría de WMM.
wmm_next_owned_by() { [ -f "$1" ] && grep -Fqx '# SPDX-FileCopyrightText: 2026 makimanson' "$1"; }

# ----------------------------------------------------------
# FUNCIÓN: Detectar instalación WMM existente
# Revisa únicamente los recursos propios del escritorio activo.
# Guarda el resultado y la versión para reutilizarlos durante todo el flujo.
# ----------------------------------------------------------
detect_installation() {
    local metadata="" v=""
    case "$DESKTOP" in
        cinnamon)
            # Cinnamon ha tenido tres topologías distintas. Identificar
            # explícitamente la encontrada evita confundir el frontend actual
            # con el nuevo core común durante Upgrade/Reinstall.
            if [ -f "$APP_DIR/python/main.py" ]; then
                INSTALLED_ROOT="$APP_DIR"
                INSTALLED_DATA_DIR="$DATA_DIR"
                metadata="$FRONTEND_DIR/metadata.json"

            elif [ -f "$FRONTEND_DIR/python/main.py" ]; then
                INSTALLED_ROOT="$FRONTEND_DIR"
                INSTALLED_DATA_DIR="$FRONTEND_DIR/data"
                metadata="$FRONTEND_DIR/metadata.json"

            elif [ -f "$LEGACY_APP_DIR/python/main.py" ]; then
                INSTALLED_ROOT="$LEGACY_APP_DIR"
                INSTALLED_DATA_DIR="$LEGACY_APP_DIR/data"
                metadata="$LEGACY_APP_DIR/metadata.json"
            fi

            [ -n "$INSTALLED_ROOT" ] && WMM_PRESENT=1
            [ -f "$LAUNCHER" ] && WMM_PRESENT=1

            if service_owned_by "$DBUS_SERVICE" "$APP_DIR" \
                || service_owned_by "$DBUS_SERVICE" "$FRONTEND_DIR" \
                || service_owned_by "$DBUS_SERVICE" "$LEGACY_APP_DIR"; then
                WMM_PRESENT=1
            fi
            ;;

        gnome)
            # GNOME ha tenido dos topologías bajo el mismo UUID. Distinguirlas
            # por la ubicación real del engine permite preservar los datos legacy
            # sin confundir el frontend actual con el core común.
            metadata="$FRONTEND_DIR/metadata.json"

            if [ -f "$APP_DIR/python/main.py" ]; then
                INSTALLED_ROOT="$APP_DIR"
                INSTALLED_DATA_DIR="$DATA_DIR"

            elif [ -f "$FRONTEND_DIR/python/main.py" ]; then
                INSTALLED_ROOT="$FRONTEND_DIR"
                INSTALLED_DATA_DIR="$FRONTEND_DIR/data"
            fi

            [ -n "$INSTALLED_ROOT" ] && WMM_PRESENT=1
            [ -d "$FRONTEND_DIR" ] && WMM_PRESENT=1
            [ -f "$LAUNCHER" ] && WMM_PRESENT=1

            if service_owned_by "$DBUS_SERVICE" "$APP_DIR" \
                || service_owned_by "$DBUS_SERVICE" "$FRONTEND_DIR"; then
                WMM_PRESENT=1
            fi
            ;;

        kde)
            # KDE <= 1.4.x alojaba el core y los datos bajo plasma/org.maki.wmm.
            # Desde v1.5.0 el core y los datos pertenecen a la topología común.
            metadata="$PLASMOID_DIR/metadata.json"

            if [ -f "$APP_DIR/python/main.py" ]; then
                INSTALLED_ROOT="$APP_DIR"
                INSTALLED_DATA_DIR="$DATA_DIR"

            elif [ -f "$LEGACY_APP_DIR/python/main.py" ]; then
                INSTALLED_ROOT="$LEGACY_APP_DIR"
                INSTALLED_DATA_DIR="$LEGACY_APP_DIR/data"
            fi

            [ -n "$INSTALLED_ROOT" ] && WMM_PRESENT=1

            { [ -d "$PLASMOID_DIR" ] \
                || [ -f "$LAUNCHER" ] \
                || [ -f "$AUTOSTART" ] \
                || [ -f "$LEGACY_KDE_LAUNCHER" ] \
                || [ -f "$LEGACY_KDE_AUTOSTART" ]; } \
                && WMM_PRESENT=1

            if service_owned_by "$DBUS_SERVICE" "$APP_DIR" \
                || service_owned_by "$DBUS_SERVICE" "$LEGACY_APP_DIR"; then
                WMM_PRESENT=1
            fi
            ;;

        mate)
            # MATE mantiene el core en APP_DIR, pero desde v1.5.0 separa
            # frontend y datos. APP_DIR/data se conserva como fallback legacy.
            if [ -d "$APP_DIR" ]; then
                WMM_PRESENT=1
                INSTALLED_ROOT="$APP_DIR"

                if [ -d "$DATA_DIR" ]; then
                    INSTALLED_DATA_DIR="$DATA_DIR"

                elif [ -d "$APP_DIR/data" ]; then
                    INSTALLED_DATA_DIR="$APP_DIR/data"
                fi
            fi

            [ -d "$FRONTEND_DIR" ] && WMM_PRESENT=1

            { [ -f "$LAUNCHER" ] \
                || [ -f "$MATE_SERVICE" ] \
                || [ -f "$MATE_DESCRIPTOR" ]; } \
                && WMM_PRESENT=1

            service_owned_by "$DBUS_SERVICE" "$APP_DIR" && WMM_PRESENT=1
            ;;

        xfce)
            [ -d "$APP_DIR" ] && { WMM_PRESENT=1; INSTALLED_ROOT="$APP_DIR"; }
            [ -d "$FRONTEND_DIR" ] && WMM_PRESENT=1
            { [ -f "$LAUNCHER" ] || [ -f "$AUTOSTART" ]; } && WMM_PRESENT=1
            service_owned_by "$DBUS_SERVICE" "$APP_DIR" && WMM_PRESENT=1
            wmm_next_owned_by "$WMM_NEXT" && WMM_PRESENT=1
            ;;
    esac
    [ "$WMM_PRESENT" -eq 1 ] || return 0

    # Primera autoridad de versión: about.json.
    # En escritorios con datos separados, INSTALLED_DATA_DIR identifica
    # la ubicación viva correspondiente a la topología detectada.
    if [ -n "$INSTALLED_DATA_DIR" ]; then
        v="$(json_value "$INSTALLED_DATA_DIR/about.json" version 2>/dev/null || true)"
    elif [ "$DESKTOP" = xfce ]; then
        v="$(json_value "$DATA_DIR/about.json" version 2>/dev/null || true)"
    elif [ -n "$INSTALLED_ROOT" ]; then
        v="$(json_value "$INSTALLED_ROOT/data/about.json" version 2>/dev/null || true)"
    fi

    if valid_version "$v"; then
        INSTALLED_VERSION="$v"
        INSTALLED_VERSION_SOURCE=about.json
        return 0
    fi

    # Segunda autoridad de versión: metadata.json del frontend.
    case "$DESKTOP" in
        cinnamon) v="$(json_value "$metadata" version 2>/dev/null || true)" ;;
        gnome) v="$(json_value "$metadata" version-name 2>/dev/null || true)" ;;
        kde) v="$(json_value "$metadata" Version 2>/dev/null || true)" ;;
        *) v="" ;;
    esac
    valid_version "$v" && { INSTALLED_VERSION="$v"; INSTALLED_VERSION_SOURCE=metadata.json; }
}

# ----------------------------------------------------------
# FUNCIÓN: Comparar versiones
# Compara dos versiones X.Y.Z y devuelve -1, 0 o 1.
# ----------------------------------------------------------
version_cmp() {
    local a1 a2 a3 b1 b2 b3
    IFS=. read -r a1 a2 a3 <<< "$1"
    IFS=. read -r b1 b2 b3 <<< "$2"

    ((a1 < b1)) && { echo -1; return; }
    ((a1 > b1)) && { echo 1; return; }
    ((a2 < b2)) && { echo -1; return; }
    ((a2 > b2)) && { echo 1; return; }
    ((a3 < b3)) && { echo -1; return; }
    ((a3 > b3)) && { echo 1; return; }

    echo 0
}

# ----------------------------------------------------------
# FUNCIÓN: Mostrar cabecera del gestor
# Presenta plataforma, escritorio y motor gráfico detectados.
# ----------------------------------------------------------
show_header() {
    local cols line a b p1 p2
    clear
    cols="$(tput cols 2>/dev/null || echo 80)"
    line="$(printf '%*s' "$cols" | tr ' ' '=')"

    a='WMM - Wallpaper Multi-Monitor Manager'
    b="SO: $PLATFORM | Desktop: $DESKTOP | Graphics: $GRAPHICS_ENGINE"

    p1=$(( (cols - ${#a}) / 2 ))
    p2=$(( (cols - ${#b}) / 2 ))
    ((p1 < 0)) && p1=0
    ((p2 < 0)) && p2=0

    echo
    printf '%s\n%*s%s\n%*s%b\n%s\n'         "$line" "$p1" '' "$a" "$p2" '' "${GREEN}${b}${NC}" "$line"
}

# ----------------------------------------------------------
# FUNCIÓN: Mostrar menú principal
# Mantiene una numeración fija y deshabilita visualmente las acciones
# que no corresponden al estado de instalación detectado.
# ----------------------------------------------------------
show_menu() {
    local choice
    while true; do
        show_header
        echo
        printf 'Package version:   %s\n' "$WMM_VERSION"
        if [ "$WMM_PRESENT" -eq 1 ]; then
            [ -n "$INSTALLED_VERSION" ] && printf 'Installed version: %s (%s)\n' "$INSTALLED_VERSION" "$INSTALLED_VERSION_SOURCE" \
                || echo 'Installed version: unavailable (repairable installation detected)'
        else
            echo 'Installed version: not installed'
        fi

        echo
        echo 'WMM Manager'
        echo
        if [ "$WMM_PRESENT" -eq 0 ]; then
            echo '1. Install WMM'
            printf "${DIM}2. Upgrade / Reinstall WMM    [Not available]${NC}\n"
            printf "${DIM}3. Uninstall WMM              [Not available]${NC}\n"
        else
            printf "${DIM}1. Install WMM                [Not available]${NC}\n"
            echo '2. Upgrade / Reinstall WMM'
            echo '3. Uninstall WMM'
        fi

        echo '4. Exit'
        echo
        read -r -p 'Select an option [1-4]: ' choice || choice=4
        case "$choice" in
            1) [ "$WMM_PRESENT" -eq 0 ] && { ACTION=install; return; } ;;
            2) [ "$WMM_PRESENT" -eq 1 ] && { ACTION=replace; return; } ;;
            3) [ "$WMM_PRESENT" -eq 1 ] && { ACTION=uninstall; return; } ;;
            4) ACTION=exit; return ;;
        esac
        warn 'That option is not available.'
        read -r -p 'Press Enter to return to the menu...' _ || true
    done
}

# ----------------------------------------------------------
# Dependencies
# Campos: type, group, label, test command, package base, unavailable message.
# Se usa ASCII Unit Separator para que los comandos puedan contener pipes.
# ----------------------------------------------------------
DEP_SEP=$'\x1f'
DEPS=()
# Las dependencias son obligatorias salvo que se registren explícitamente
# como opcionales mediante add_optional_dep().
add_dep() { DEPS+=("required${DEP_SEP}$1${DEP_SEP}$2${DEP_SEP}$3${DEP_SEP}$4${DEP_SEP}"); }
add_optional_dep() { DEPS+=("optional${DEP_SEP}$1${DEP_SEP}$2${DEP_SEP}$3${DEP_SEP}$4${DEP_SEP}$5"); }

# ----------------------------------------------------------
# FUNCIÓN: Construir lista de dependencias
# Añade las dependencias comunes y sólo las específicas del escritorio
# o gestores de archivos realmente presentes en el sistema.
# ----------------------------------------------------------
build_deps() {
    DEPS=()
    add_dep GTK 'PyGObject (GTK bindings)' "python3 -c 'import gi'" python3-gi
    add_dep GTK 'GTK 3.0 Introspection' \
        "python3 -c 'import gi; gi.require_version(\"Gtk\",\"3.0\"); from gi.repository import Gtk'" gir1.2-gtk-3.0
    add_dep GTK 'GLib 2.0 Introspection' \
        "python3 -c 'import gi; gi.require_version(\"GLib\",\"2.0\"); from gi.repository import GLib'" gir1.2-glib-2.0
    # PangoCairo requiere el puente PyGObject-Cairo; importar gi no garantiza su presencia.
    add_dep GTK 'PyGObject Cairo integration' \
        "python3 -c 'import cairo, gi; gi.require_foreign(\"cairo\")'" python3-gi-cairo
    # Dependencias específicas del escritorio.
    if [ "$DESKTOP" = gnome ]; then
        add_dep GNOME \
            'GNOME Shell Extensions' \
            'command -v gnome-extensions' \
            gnome-shell-extension-prefs

        add_dep GNOME \
            'GNOME Shell Extension Manager' \
            'command -v gnome-extensions-app' \
            gnome-shell-extension-prefs
    fi

    if [ "$DESKTOP" = kde ]; then
        add_dep KDE KDialog 'command -v kdialog' kdialog
    fi

    if [ "$DESKTOP" = mate ]; then
        add_dep MATE \
            'MATE Panel Applet 4.0 Introspection' \
            "python3 -c 'import gi; gi.require_version(\"MatePanelApplet\",\"4.0\"); from gi.repository import MatePanelApplet'" \
            gir1.2-matepanelapplet-4.0
    fi

    if [ "$DESKTOP" = xfce ]; then
        add_dep XFCE \
            'Wnck 3.0 Introspection' \
            "python3 -c 'import gi; gi.require_version(\"Wnck\",\"3.0\"); from gi.repository import Wnck'" \
            gir1.2-wnck-3.0

        add_dep XFCE \
            'XFCE configuration client' \
            'command -v xfconf-query' \
            xfconf
    fi

    # Dependencias opcionales de gestores de archivos instalados.
    if command -v nautilus >/dev/null 2>&1; then
        add_optional_dep 'File manager' \
            'Nautilus Python' \
            "python3 -c 'import gi; from gi.repository import Nautilus'" \
            python3-nautilus \
            'Nautilus contextual actions will not be available.'
    fi

    if command -v thunar >/dev/null 2>&1; then
        add_optional_dep 'File manager' \
            'Thunarx 3.0 Introspection' \
            "python3 -c 'import gi; gi.require_version(\"Thunarx\",\"3.0\"); from gi.repository import Thunarx'" \
            gir1.2-thunarx-3.0 \
            'XFCE desktop contextual actions will not be available.'

        add_optional_dep 'File manager' \
            'Thunarx Python' \
            'find /usr/lib /usr/lib64 -maxdepth 3 -type f -name thunarx-python.so -print -quit 2>/dev/null | grep -q .' \
            thunarx-python \
            'XFCE desktop contextual actions will not be available.'
    fi

    if command -v caja >/dev/null 2>&1; then
        add_optional_dep 'File manager' \
            'Caja Python' \
            "python3 -c 'import gi; gi.require_version(\"Caja\",\"2.0\"); from gi.repository import Caja'" \
            python3-caja \
            'Caja contextual actions will not be available.'
    fi

    add_dep WMM 'Python 3' 'python3 --version' python3
    add_dep WMM 'VTE 2.91 Introspection' \
    "python3 -c 'import gi; gi.require_version(\"Vte\",\"2.91\"); from gi.repository import Vte'" \
    gir1.2-vte-2.91
    add_dep WMM 'Pillow (Python Imaging)' "python3 -c 'from PIL import Image'" python3-pillow
    add_dep WMM 'NumPy (Python scientific computing)' "python3 -c 'import numpy'" python3-numpy
    add_dep WMM 'Libnotify (notifications)' 'command -v notify-send' libnotify-bin
    add_dep WMM GetText 'command -v xgettext' gettext
    add_dep WMM 'D-Bus client' 'command -v dbus-send' dbus
}

# Ejecuta la prueba asociada a una dependencia.
dep_ok() { eval "$1" >/dev/null 2>&1; }

# ----------------------------------------------------------
# FUNCIÓN: Mostrar checklist de dependencias
# Puede filtrar por tipo (required/optional) y devuelve cuántas
# dependencias del conjunto mostrado siguen faltando.
# ----------------------------------------------------------
print_deps() {
    local wanted_type="${1:-}" spec type group name test pkg unavailable current='' missing=0
    echo

    for spec in "${DEPS[@]}"; do
        IFS="$DEP_SEP" read -r type group name test pkg unavailable <<< "$spec"

        [ -z "$wanted_type" ] || [ "$type" = "$wanted_type" ] || continue

        [ "$group" = "$current" ] || {
            current="$group"
            printf "${GREEN}[%s dependencies]${NC}\n" "$group"
        }

        dep_ok "$test" \
            && printf "  ${GREEN}[✔]${NC} %s\n" "$name" \
            || { printf "  ${RED}[✘]${NC} %s\n" "$name"; ((missing++)); }
    done

    return "$missing"
}

# ----------------------------------------------------------
# FUNCIÓN: Adaptar nombres de paquetes
# Traduce el nombre base cuando DNF o Pacman usan otro paquete.
# Una cadena vacía indica que el gestor no dispone de un paquete
# soportado para esa dependencia opcional.
# ----------------------------------------------------------
pkg_map() {
    case "$1:$2" in
        dnf:python3-gi)                  echo python3-gobject ;;
        dnf:python3-gi-cairo)            echo python3-gobject ;;
        dnf:gir1.2-gtk-3.0)             echo gtk3 ;;
        dnf:gir1.2-glib-2.0)            echo glib2 ;;
        dnf:gir1.2-wnck-3.0)            echo libwnck3 ;;
        dnf:gir1.2-thunarx-3.0)         echo Thunar ;;
        dnf:thunarx-python)             echo '' ;;
        dnf:gir1.2-matepanelapplet-4.0) echo mate-panel-libs ;;
        dnf:python3-nautilus)            echo nautilus-python ;;
        dnf:gir1.2-vte-2.91)             echo vte291 ;;

        pacman:python3)                   echo python ;;
        pacman:python3-pillow)            echo python-pillow ;;
        pacman:python3-numpy)             echo python-numpy ;;
        pacman:libnotify-bin)             echo libnotify ;;
        pacman:gnome-shell-extension-prefs) echo gnome-shell-extensions ;;
        pacman:python3-gi)                echo python-gobject ;;
        pacman:python3-gi-cairo)          echo python-cairo ;;
        pacman:gir1.2-gtk-3.0)           echo gtk3 ;;
        pacman:gir1.2-glib-2.0)          echo glib2 ;;
        pacman:gir1.2-wnck-3.0)          echo libwnck3 ;;
        pacman:gir1.2-thunarx-3.0)       echo thunar ;;
        pacman:thunarx-python)           echo '' ;;
        pacman:gir1.2-matepanelapplet-4.0) echo mate-panel ;;
        pacman:python3-nautilus)          echo nautilus-python ;;
        pacman:python3-caja)              echo python-caja ;;
        pacman:gir1.2-vte-2.91)          echo vte3 ;;

        *) echo "$2" ;;
    esac
}

# ----------------------------------------------------------
# FUNCIÓN: Verificar / instalar dependencias
# Resuelve primero las dependencias obligatorias, que bloquean la acción
# si no pueden satisfacerse. Después procesa las integraciones opcionales
# de forma independiente; sus fallos sólo deshabilitan su funcionalidad.
# ----------------------------------------------------------
ensure_deps() {
    local answer manager='' spec type group name test pkg unavailable mapped
    local -a missing=()
    local -A seen=()

    build_deps

    if command -v apt >/dev/null; then
        manager=apt
    elif command -v dnf >/dev/null; then
        manager=dnf
    elif command -v pacman >/dev/null; then
        manager=pacman
    fi

    # ------------------------------------------------------
    # REQUIRED
    # Las dependencias obligatorias deben quedar resueltas
    # antes de continuar con cualquier integración opcional.
    # ------------------------------------------------------
    if print_deps required; then
        ok 'Required dependencies are available.'
    else
        [ -n "$manager" ] || {
            fail 'No supported package manager found.'
            return 1
        }

        echo
        read -r -p 'Install the missing required dependencies? (y/n): ' answer || answer=n
        [[ "$answer" =~ ^[Yy]$ ]] || {
            warn 'Required dependency installation cancelled.'
            return 1
        }

        missing=()
        seen=()

        for spec in "${DEPS[@]}"; do
            IFS="$DEP_SEP" read -r type group name test pkg unavailable <<< "$spec"
            [ "$type" = required ] || continue
            dep_ok "$test" && continue

            mapped="$(pkg_map "$manager" "$pkg")"
            [ -n "$mapped" ] || {
                fail "No package mapping for required dependency: $name"
                return 1
            }

            [ -n "${seen[$mapped]:-}" ] || {
                seen[$mapped]=1
                missing+=("$mapped")
            }
        done

        info "Installing required dependencies: ${missing[*]}"

        case "$manager" in
            apt)    sudo apt install -y "${missing[@]}" ;;
            dnf)    sudo dnf install -y "${missing[@]}" ;;
            pacman) sudo pacman -Sy --noconfirm "${missing[@]}" ;;
        esac || return 1

        info 'Verifying required dependencies...'
        print_deps required || {
            fail 'Some required dependencies are still missing.'
            return 1
        }

        ok 'Required dependencies verified.'
    fi

    # ------------------------------------------------------
    # OPTIONAL
    # Las integraciones opcionales amplían WMM, pero su
    # ausencia nunca impide instalar o reparar la aplicación.
    # ------------------------------------------------------
    if print_deps optional; then
        ok 'Optional integrations are available.'
        return 0
    fi

    [ -n "$manager" ] || {
        warn 'No supported package manager found for optional integrations.'
        return 0
    }

    echo
    read -r -p 'Install the missing optional integrations? (y/n): ' answer || answer=n

    if [[ "$answer" =~ ^[Yy]$ ]]; then
        for spec in "${DEPS[@]}"; do
            IFS="$DEP_SEP" read -r type group name test pkg unavailable <<< "$spec"
            [ "$type" = optional ] || continue
            dep_ok "$test" && continue

            mapped="$(pkg_map "$manager" "$pkg")"

            [ -n "$mapped" ] || continue

            info "Installing optional integration: $mapped"

            case "$manager" in
                apt)    sudo apt install -y "$mapped" ;;
                dnf)    sudo dnf install -y "$mapped" ;;
                pacman) sudo pacman -Sy --noconfirm "$mapped" ;;
            esac || :
        done
    else
        warn 'Optional integration installation skipped.'
    fi

    info 'Verifying optional integrations...'

    if print_deps optional; then
        ok 'Optional integrations are available.'
        return 0
    fi

    seen=()

    for spec in "${DEPS[@]}"; do
        IFS="$DEP_SEP" read -r type group name test pkg unavailable <<< "$spec"
        [ "$type" = optional ] || continue

        if ! dep_ok "$test" && [ -n "$unavailable" ] && [ -z "${seen[$unavailable]:-}" ]; then
            seen[$unavailable]=1
            warn "$unavailable"
        fi
    done

    return 0
}

# ----------------------------------------------------------
# Source / templates / staging
# ----------------------------------------------------------

# ----------------------------------------------------------
# FUNCIÓN: Verificar integridad del paquete
# Comprueba que existen los archivos comunes y los recursos necesarios
# para el escritorio actual antes de modificar la instalación viva.
# ----------------------------------------------------------
validate_source() {
    local p failed=0
    local -a req=(
        python
        wmm_platform
        wmm_platform/shell/data
        help
        licenses/WMM/RESPONSIBLE_USE.txt
        wmm_platform/shell/po
        python/main.py
        wmm_platform/shell/data/about.json
        wmm_platform/shell/linux/org.maki.wmm.service
        wmm_platform/shell/linux/settings_core.ini
    )

    # Añadir los recursos obligatorios del escritorio actual.
    case "$DESKTOP" in
        cinnamon)
            req+=(
                icon.png
                wmm_platform/shell/cinnamon/metadata.cinnamon.json
                wmm_platform/shell/cinnamon/applet.cinnamon.js
                wmm_platform/shell/cinnamon/org.maki.wmm.cinnamon.desktop
                wmm_platform/shell/cinnamon/stylesheet.css
            )
            ;;

        gnome)
            req+=(
                wmm_platform/shell/gnome/metadata.gnome.json
                wmm_platform/shell/gnome/extension.gnome.js
                wmm_platform/shell/gnome/stylesheet.css
                wmm_platform/shell/gnome/org.maki.wmm.gnome.desktop
            )
            ;;

        kde)
            req+=(
                wmm_platform/shell/kde/plasmoid_contents/contents
                wmm_platform/shell/kde/plasmoid_contents/metadata.kde_plasmoid.json
                wmm_platform/shell/kde/org.maki.wmm.kde.desktop
                wmm_platform/shell/linux/org.maki.wmm.InstallManager.service
                wmm_platform/shell/linux/org.maki.wmm.DebugLogViewer.service
            )
            ;;

        mate)
            req+=(
                wmm_platform/shell/mate/mate-applet.py
                wmm_platform/shell/mate/mate-launcher.py
                wmm_platform/shell/mate/mate-applet.css
                wmm_platform/shell/mate/org.maki.wmm.mate-panel-applet
                wmm_platform/shell/mate/org.mate.panel.applet.WMMAppletFactory.service
                wmm_platform/shell/mate/org.maki.wmm.mate.desktop
            )
            ;;

        xfce)
            req+=(
                wmm_platform/shell/xfce/xfce-frontend.py
                wmm_platform/shell/xfce/xfce-frontend.css
                wmm_platform/shell/xfce/org.maki.wmm.xfce.desktop
                wmm_platform/shell/linux/wmm-next.sh
            )
            ;;
    esac

    for p in "${req[@]}"; do
        [ -e "$PROJECT_DIR/$p" ] || {
            fail "Missing required source: wmm/$p"
            failed=1
        }
    done
    [ "$failed" -eq 0 ]
}

PYTHON3_BIN=''
DBUS_SEND_BIN=''
# ----------------------------------------------------------
# FUNCIÓN: Resolver herramientas de runtime
# Obtiene las rutas reales de python3 y dbus-send usadas en las plantillas.
# ----------------------------------------------------------
prepare_tools() {
    PYTHON3_BIN="$(command -v python3 || true)"
    DBUS_SEND_BIN="$(command -v dbus-send || true)"

    [ -n "$PYTHON3_BIN" ] && [ -n "$DBUS_SEND_BIN" ] || {
        fail 'python3 or dbus-send is unavailable.'
        return 1
    }
}

# Resuelve los tokens comunes antes de instalar una plantilla.
template() {
    sed \
        -e "s|@PLATFORM@|$PLATFORM|g" \
        -e "s|@DESKTOP@|$DESKTOP|g" \
        -e "s|@GRAPHICS_ENGINE@|$GRAPHICS_ENGINE|g" \
        -e "s|@WMM_ID@|$WMM_ID|g" \
        -e "s|@APP_DOMAIN@|$APP_DOMAIN|g" \
        -e "s|@VERSION@|$WMM_VERSION|g" \
        -e "s|@DATA_BASE@|$DATA_BASE|g" \
        -e "s|@CONFIG_BASE@|$CONFIG_BASE|g" \
        -e "s|@CACHE_BASE@|$CACHE_BASE|g" \
        -e "s|@APP_DIR@|$APP_DIR|g" \
        -e "s|@APP_CONFIG@|$APP_CONFIG|g" \
        -e "s|@DATA_DIR@|$DATA_DIR|g" \
        -e "s|@FRONTEND_DIR@|$FRONTEND_DIR|g" \
        -e "s|@CACHE_DIR@|$CACHE_DIR|g" \
        -e "s|@LOCALE_DIR@|$LOCALE_DIR|g" \
        -e "s|@PYTHON3@|$PYTHON3_BIN|g" \
        -e "s|@DBUS_SEND@|$DBUS_SEND_BIN|g" \
        -e "s|@RELEASE_YEAR@|$WMM_RELEASE_YEAR|g" \
        "$1" > "$2"
}

PRESERVE=(
    settings.json
    sources.json
    monitor_vault.json
    bookmarks.json
    bookmarks_single_list.json
    rotation_h.json
    rotation_v.json
    sel_rotation_h.json
    sel_rotation_v.json
    bookmark_rotation_h.json
    bookmark_rotation_v.json
    history.json
    history_vault.json
    history_presets.json
    image_cache.json
    image_online.json
    scan_index.json
)

STAGING=''
DATA_STAGING=''
OLD_APP=''
OLD_DATA=''
OLD_PLASMOID=''
EXTERNAL_BACKUP=''
MATE_APPLET_STATE=''
PLASMOID_SWAPPED=0

# ----------------------------------------------------------
# FUNCIÓN: Preparar herramientas de mantenimiento
# Copia los instaladores al árbol destino y genera una copia limpia de
# esta versión para futuras reparaciones sin depender de Internet.
# ----------------------------------------------------------
prepare_installer_payload() {
    local installer_dir="$STAGING/$INSTALLER_REL_DIR"
    local repair_zip="$installer_dir/wmm-repair.zip"

    mkdir -p "$installer_dir" || return 1

    # Copiar los dos motores de mantenimiento junto al futuro frontend.
    cp -f "$INSTALLER_FILE" "$installer_dir/wmm-install.sh" || return 1
    cp -f "$UNINSTALLER" "$installer_dir/wmm-uninstall.sh" || return 1
    chmod 755 "$installer_dir/wmm-install.sh" "$installer_dir/wmm-uninstall.sh"

    # Generar una fuente limpia y autocontenida de esta versión.
    "$PYTHON3_BIN" - \
        "$repair_zip" \
        "$WMM_VERSION" \
        "$README_FILE" \
        "$CHANGELOG_FILE" \
        "$LICENSE_FILE" \
        "$INSTALLER_FILE" \
        "$UNINSTALLER" \
        "$PROJECT_DIR" <<'PYCODE'
import os
import sys
import zipfile

repair_zip, version, readme, changelog, license_file, installer, uninstaller, project_dir = sys.argv[1:]
archive_root = f"WMM-v{version}"

with zipfile.ZipFile(
    repair_zip,
    "w",
    compression=zipfile.ZIP_DEFLATED,
    compresslevel=9
) as archive:
    root_files = (
        (readme, "README.md"),
        (changelog, "CHANGELOG.md"),
        (license_file, "LICENSE"),
        (installer, "wmm-install.sh"),
        (uninstaller, "wmm-uninstall.sh"),
    )

    for source, name in root_files:
        archive.write(source, f"{archive_root}/{name}")

    project_parent = os.path.dirname(project_dir)

    for current_root, dirs, files in os.walk(project_dir):
        dirs[:] = [name for name in dirs if name != "__pycache__"]

        for name in files:
            if name.endswith(".pyc") or name == "wmm-repair.zip":
                continue

            source = os.path.join(current_root, name)
            relative = os.path.relpath(source, project_parent)
            archive.write(source, f"{archive_root}/{relative}")
PYCODE

    [ -s "$repair_zip" ] || return 1

    ok 'Installer tools and repair package prepared.'
}

# ----------------------------------------------------------
# FUNCIÓN: Preparar staging limpio
# Prepara por separado el árbol de aplicación y los datos persistentes.
# Ninguno de los dos sustituye todavía a la instalación viva.
# ----------------------------------------------------------
prepare_staging() {
    local preserve="$1" parent config_parent preserve_source f

    parent="$(dirname "$APP_DIR")"
    config_parent="$(dirname "$APP_CONFIG")"

    # Durante una migración, los datos vivos pueden pertenecer todavía
    # a la topología detectada y no al nuevo DATA_DIR de destino.
    preserve_source="${INSTALLED_DATA_DIR:-$DATA_DIR}"

    mkdir -p "$parent" "$config_parent" || return 1

    STAGING="$(mktemp -d "$parent/.wmm-install-new.XXXXXX")" || return 1
    DATA_STAGING="$(mktemp -d "$config_parent/.wmm-data-new.XXXXXX")" || return 1

    info 'Preparing clean staging trees...'

    # ----------------------------------------------------------
    # CORE WMM
    # ----------------------------------------------------------
    # Copiar una versión limpia del proyecto y la documentación.
    cp -a "$PROJECT_DIR/." "$STAGING/" || return 1

    # El README fuente utiliza rutas relativas al repositorio.
    # Al instalar, /wmm se convierte en la raíz de APP_DIR.
    # Adaptar las rutas de presentación y recursos comunes.
    sed \
        -e 's|wmm/WMM-presentation\.jpg|WMM-presentation.jpg|g' \
        -e 's|wmm/wmm_platform/shell/logos/|wmm_platform/shell/logos/|g' \
        "$README_FILE" > "$STAGING/README.md" \
        || return 1

    cp -f "$CHANGELOG_FILE" "$STAGING/CHANGELOG.md" || return 1
    cp -f "$LICENSE_FILE" "$STAGING/LICENSE" || return 1

    # ----------------------------------------------------------
    # DATA WMM
    # ----------------------------------------------------------
    # Sembrar el nuevo árbol de datos desde su ubicación en shell.
    cp -a "$PROJECT_DIR/wmm_platform/shell/data/." "$DATA_STAGING/" || return 1

    # about.json contiene valores propios de esta versión.
    template \
        "$PROJECT_DIR/wmm_platform/shell/data/about.json" \
        "$DATA_STAGING/about.json" \
        || return 1

    # En Upgrade/Reinstall, los datos vivos prevalecen sobre los
    # valores distribuidos por el paquete. Durante una migración,
    # preserve_source conserva la ubicación real de la instalación detectada.
    if [ "$preserve" -eq 1 ] && [ -d "$preserve_source" ]; then
        for f in "${PRESERVE[@]}"; do
            if [ -f "$preserve_source/$f" ]; then
                cp -p "$preserve_source/$f" "$DATA_STAGING/$f" || return 1
            fi
        done
    fi

    # ----------------------------------------------------------
    # FRONTEND
    # ----------------------------------------------------------
    case "$DESKTOP" in
        cinnamon)
            # El frontend Cinnamon se instala después en su ruta propia.
            ;;

        gnome)
            # El frontend GNOME se instala después en su ruta propia.
            ;;

        mate)
            # MATE aloja su unidad runtime dentro del espacio propio de WMM.
            # settings_core.ini enlaza el frontend con core y datos comunes.
            mkdir -p "$STAGING/frontends/mate" || return 1

            cp -f \
                "$PROJECT_DIR/wmm_platform/shell/mate/mate-applet.py" \
                "$STAGING/frontends/mate/mate-applet.py" \
                || return 1

            cp -f \
                "$PROJECT_DIR/wmm_platform/shell/mate/mate-launcher.py" \
                "$STAGING/frontends/mate/mate-launcher.py" \
                || return 1

            cp -f \
                "$PROJECT_DIR/wmm_platform/shell/mate/mate-applet.css" \
                "$STAGING/frontends/mate/mate-applet.css" \
                || return 1

            template \
                "$PROJECT_DIR/wmm_platform/shell/linux/settings_core.ini" \
                "$STAGING/frontends/mate/settings_core.ini" \
                || return 1
            ;;

        kde)
            # KDE instala el frontend como recurso externo.
            ;;

        xfce)
            # XFCE materializa su unidad runtime dentro del espacio propio de WMM.
            # Código, estilos y configuración viajan juntos como frontend.
            mkdir -p "$STAGING/frontends/xfce" || return 1

            cp -f \
                "$PROJECT_DIR/wmm_platform/shell/xfce/xfce-frontend.py" \
                "$STAGING/frontends/xfce/xfce-frontend.py" \
                || return 1

            cp -f \
                "$PROJECT_DIR/wmm_platform/shell/xfce/xfce-frontend.css" \
                "$STAGING/frontends/xfce/xfce-frontend.css" \
                || return 1

            template \
                "$PROJECT_DIR/wmm_platform/shell/linux/settings_core.ini" \
                "$STAGING/frontends/xfce/settings_core.ini" \
                || return 1
            ;;
    esac

    # Limpiar artefactos de desarrollo antes de activar los staging.
    find "$STAGING" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
    find "$STAGING" -type f -name '*.pyc' -delete 2>/dev/null
    find "$STAGING" -type f -exec chmod -x {} \;
    find "$DATA_STAGING" -type f -exec chmod -x {} \;

    # file_utils.py es legado: el bloqueo de archivos pertenece ahora
    # directamente a la capa de cada sistema operativo.
    rm -f "$STAGING/wmm_platform/file_utils.py"

    # Instalar las herramientas locales y crear el paquete de reparación.
    prepare_installer_payload || return 1

    # Validación común.
    [ -f "$STAGING/python/main.py" ] \
        && [ -f "$DATA_STAGING/about.json" ] \
        && [ -f "$DATA_STAGING/monitor_mfg.json" ] \
        && [ -f "$DATA_STAGING/launch_profiles.json" ] \
        && [ -f "$STAGING/README.md" ] \
        && [ -f "$STAGING/CHANGELOG.md" ] \
        && [ -f "$STAGING/LICENSE" ] \
        && [ -f "$STAGING/$INSTALLER_REL_DIR/wmm-install.sh" ] \
        && [ -f "$STAGING/$INSTALLER_REL_DIR/wmm-uninstall.sh" ] \
        && [ -s "$STAGING/$INSTALLER_REL_DIR/wmm-repair.zip" ] \
        || return 1

    # Validación específica del frontend.
    case "$DESKTOP" in
        cinnamon)
            # El frontend Cinnamon se valida durante su instalación externa.
            ;;

        gnome)
            # El frontend GNOME se valida durante su instalación externa.
            ;;

        mate)
            [ -f "$STAGING/frontends/mate/mate-applet.py" ] || return 1
            [ -f "$STAGING/frontends/mate/mate-launcher.py" ] || return 1
            [ -f "$STAGING/frontends/mate/mate-applet.css" ] || return 1
            [ -f "$STAGING/frontends/mate/settings_core.ini" ] || return 1
            ;;

        kde)
            # KDE no añade archivos de frontend al APP_DIR.
            ;;

        xfce)
            [ -f "$STAGING/frontends/xfce/xfce-frontend.py" ] || return 1
            [ -f "$STAGING/frontends/xfce/xfce-frontend.css" ] || return 1
            [ -f "$STAGING/frontends/xfce/settings_core.ini" ] || return 1
            ;;
    esac

    ok 'Clean WMM app and data staging trees prepared.'
}

# ----------------------------------------------------------
# FUNCIÓN: Activar staging
# Aparta temporalmente core y datos anteriores y activa ambos árboles
# nuevos. Las copias anteriores se conservan hasta el commit final.
# ----------------------------------------------------------
activate_staging() {
    local app_parent data_parent old

    app_parent="$(dirname "$APP_DIR")"
    data_parent="$(dirname "$DATA_DIR")"

    mkdir -p "$data_parent" || return 1

    # Apartar el core vivo sin destruirlo.
    if [ -d "$APP_DIR" ]; then
        old="$(mktemp -d "$app_parent/.wmm-install-old.XXXXXX")" || return 1
        rmdir "$old" || return 1
        mv "$APP_DIR" "$old" || return 1
        OLD_APP="$old"
    fi

    # Activar el nuevo core.
    if ! mv "$STAGING" "$APP_DIR"; then
        [ -n "$OLD_APP" ] && mv "$OLD_APP" "$APP_DIR" || true
        OLD_APP=''
        return 1
    fi
    STAGING=''

    # Apartar los datos vivos sin destruirlos.
    if [ -d "$DATA_DIR" ]; then
        old="$(mktemp -d "$data_parent/.wmm-data-old.XXXXXX")" || {
            rm -rf "$APP_DIR"
            [ -n "$OLD_APP" ] && mv "$OLD_APP" "$APP_DIR" || true
            OLD_APP=''
            return 1
        }

        rmdir "$old" || {
            rm -rf "$APP_DIR"
            [ -n "$OLD_APP" ] && mv "$OLD_APP" "$APP_DIR" || true
            OLD_APP=''
            return 1
        }

        mv "$DATA_DIR" "$old" || {
            rm -rf "$old"
            rm -rf "$APP_DIR"
            [ -n "$OLD_APP" ] && mv "$OLD_APP" "$APP_DIR" || true
            OLD_APP=''
            return 1
        }

        OLD_DATA="$old"
    fi

    # Activar los nuevos datos.
    if ! mv "$DATA_STAGING" "$DATA_DIR"; then
        if [ -n "$OLD_DATA" ] && [ -d "$OLD_DATA" ]; then
            mv "$OLD_DATA" "$DATA_DIR" || {
                fail "CRITICAL: previous data remains at $OLD_DATA"
                return 1
            }
            OLD_DATA=''
        fi

        rm -rf "$APP_DIR"

        if [ -n "$OLD_APP" ] && [ -d "$OLD_APP" ]; then
            mv "$OLD_APP" "$APP_DIR" || {
                fail "CRITICAL: previous installation remains at $OLD_APP"
                return 1
            }
            OLD_APP=''
        fi

        rmdir "$APP_CONFIG" 2>/dev/null || true
        return 1
    fi

    DATA_STAGING=''

    ok 'Clean WMM app and data trees activated.'
}

# ----------------------------------------------------------
# Replacement lifecycle
# ----------------------------------------------------------
# Comprueba sin activar el servicio si un nombre D-Bus tiene owner en la sesión.
# Sin argumento conserva el comportamiento histórico para el engine WMM.
dbus_owner() {
    local bus_name="${1:-org.maki.wmm}"

    "$DBUS_SEND_BIN" \
        --session \
        --print-reply \
        --dest=org.freedesktop.DBus \
        /org/freedesktop/DBus \
        org.freedesktop.DBus.NameHasOwner \
        string:"$bus_name" \
        2>/dev/null | grep -q 'boolean true'
}

# Espera la terminación real de procesos concretos mediante pidfd.
# El descriptor queda ligado a la identidad del proceso, evitando sondeos
# repetidos de /proc, sleeps y ambigüedad por reutilización posterior del PID.
terminate_pids_and_wait() {
    local timeout_ms="$1"
    shift

    [ "$#" -gt 0 ] || return 0

    "$PYTHON3_BIN" - "$timeout_ms" "$@" <<'PY'
import os
import select
import signal
import sys
import time

timeout_ms = int(sys.argv[1])
pids = [int(value) for value in sys.argv[2:]]
deadline = time.monotonic() + timeout_ms / 1000.0

poller = select.poll()
pidfds = {}

if not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal"):
    print("pidfd process control is unavailable.", file=sys.stderr)
    raise SystemExit(2)

try:
    for pid in pids:
        try:
            fd = os.pidfd_open(pid)
        except ProcessLookupError:
            continue
        except OSError as error:
            print(f"Unable to open pidfd for PID {pid}: {error}", file=sys.stderr)
            raise SystemExit(2)

        pidfds[fd] = pid
        poller.register(fd, select.POLLIN | select.POLLHUP | select.POLLERR)

    # Abrir primero todos los pidfd fija la identidad exacta tanto para
    # señalizar como para esperar; nunca se vuelve al PID numérico capturado.
    for fd, pid in pidfds.items():
        try:
            signal.pidfd_send_signal(fd, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except OSError as error:
            print(f"Unable to send SIGTERM to PID {pid}: {error}", file=sys.stderr)
            raise SystemExit(2)
    while pidfds:
        remaining_ms = int(max(0.0, deadline - time.monotonic()) * 1000)
        if remaining_ms <= 0:
            raise SystemExit(1)

        events = poller.poll(remaining_ms)
        if not events:
            raise SystemExit(1)

        for fd, _event in events:
            if fd not in pidfds:
                continue

            poller.unregister(fd)
            os.close(fd)
            del pidfds[fd]

finally:
    for fd in pidfds:
        try:
            os.close(fd)
        except OSError:
            pass
PY
}

# ----------------------------------------------------------
# FUNCIÓN: Evaluar política de recarga GNOME
# GNOME sólo puede reutilizar con seguridad el frontend ya cargado cuando
# permanecen estables su topología, extension.js y los metadatos funcionales.
# version-name se excluye porque sólo identifica la release publicada.
# ----------------------------------------------------------
evaluate_gnome_reload_policy() {
    GNOME_SESSION_RESTART_REQUIRED=0

    [ "$DESKTOP" = gnome ] || return 0
    [ "$WMM_PRESENT" -eq 1 ] || return 0

    # APP_DIR identifica la topología común actual. Cualquier otra raíz
    # corresponde a una topología anterior o incompleta.
    if [ "$INSTALLED_ROOT" != "$APP_DIR" ]; then
        GNOME_SESSION_RESTART_REQUIRED=1
        return 0
    fi

    # GNOME mantiene extension.js en memoria durante la sesión.
    if [ ! -f "$FRONTEND_DIR/extension.js" ] \
        || ! cmp -s \
            "$FRONTEND_DIR/extension.js" \
            "$PROJECT_DIR/wmm_platform/shell/gnome/extension.gnome.js"; then

        GNOME_SESSION_RESTART_REQUIRED=1
        return 0
    fi

    # metadata.json también se carga junto con la extensión. Comparar su
    # contrato funcional ignorando únicamente version-name, que cambia en
    # cada release sin alterar el lifecycle del frontend.
    if ! "$PYTHON3_BIN" - \
        "$FRONTEND_DIR/metadata.json" \
        "$PROJECT_DIR/wmm_platform/shell/gnome/metadata.gnome.json" <<'PY'
import json
import sys

installed_path, package_path = sys.argv[1:3]

try:
    with open(installed_path, "r", encoding="utf-8") as file:
        installed = json.load(file)

    with open(package_path, "r", encoding="utf-8") as file:
        package = json.load(file)
except (OSError, json.JSONDecodeError):
    raise SystemExit(1)

installed.pop("version-name", None)
package.pop("version-name", None)

raise SystemExit(0 if installed == package else 1)
PY
    then
        GNOME_SESSION_RESTART_REQUIRED=1
    fi
}

# ----------------------------------------------------------
# FUNCIÓN: Preparar el frontend para un reemplazo
# Sólo realiza las acciones previas necesarias para el escritorio actual.
# ----------------------------------------------------------
unload_frontend() {
    # Preparar únicamente los frontends que mantienen estado o proceso propio
    # que no debe sobrevivir al reemplazo del árbol instalado.
    case "$DESKTOP" in
        gnome)
            # Si el paquete requiere una sesión nueva, conservar la extensión
            # habilitada evita reactivar en caliente un módulo JS que GNOME
            # mantiene cacheado. El nuevo frontend se cargará en el próximo login.
            if [ "$GNOME_SESSION_RESTART_REQUIRED" -eq 0 ] \
                && command -v gnome-extensions >/dev/null 2>&1; then

                gnome-extensions disable "$APP_DOMAIN" >/dev/null 2>&1 || true
            fi
            ;;

        mate)
            MATE_APPLET_STATE="$(
                "$PYTHON3_BIN" "$PROJECT_DIR/wmm_platform/shell/mate/mate-launcher.py" --unload
            )" || return 1
            ;;

        xfce)
            # El frontend XFCE es un proceso residente independiente.
            # Capturar sus PID antes de SIGTERM permite esperar su terminación
            # real mediante pidfd, sin sondeo periódico ni sleeps.
            local -a frontend_pids=()
            mapfile -t frontend_pids < <(
                pgrep -f -- "$FRONTEND_DIR/xfce-frontend.py" || true
            )

            if [ "${#frontend_pids[@]}" -gt 0 ]; then
                # No sustituir el árbol mientras una instancia capturada
                # todavía pueda estar ejecutando código desde él.
                if ! terminate_pids_and_wait 2000 "${frontend_pids[@]}"; then
                    fail 'XFCE frontend could not be stopped safely.'
                    return 1
                fi

                # Comprobación final única: una nueva instancia aparecida durante
                # la transición tampoco puede sobrevivir al reemplazo del árbol.
                if pgrep -f -- "$FRONTEND_DIR/xfce-frontend.py" >/dev/null 2>&1; then
                    fail 'XFCE frontend reappeared while stopping.'
                    return 1
                fi
            fi
            ;;

        cinnamon|kde)
            ;;
    esac
}

# ----------------------------------------------------------
# FUNCIÓN: Detener WMM antes del reemplazo
# Solicita el cierre coordinado y confirma que engine/panel ya no usan
# los archivos que van a ser sustituidos.
# ----------------------------------------------------------
stop_wmm() {
    local root
    local -a roots=("$APP_DIR") process_pids=()

    # INSTALLED_ROOT conserva la ubicación real desde la que puede seguir
    # ejecutándose la instalación sustituida durante una migración.
    [ -n "$INSTALLED_ROOT" ] \
        && [ "$INSTALLED_ROOT" != "$APP_DIR" ] \
        && [ -d "$INSTALLED_ROOT" ] \
        && roots+=("$INSTALLED_ROOT")

    [ -n "$LEGACY_APP_DIR" ] \
        && [ "$LEGACY_APP_DIR" != "$INSTALLED_ROOT" ] \
        && [ -d "$LEGACY_APP_DIR" ] \
        && roots+=("$LEGACY_APP_DIR")

    info 'Stopping current WMM...'

    # Pedir primero el cierre coordinado para que engine y panel recorran
    # su lifecycle normal siempre que el servicio continúe disponible.
    if dbus_owner; then
        "$DBUS_SEND_BIN" \
            --session \
            --print-reply \
            --reply-timeout=2000 \
            --dest=org.maki.wmm \
            /org/maki/wmm \
            org.maki.wmm.Shutdown \
            >/dev/null 2>&1 || true
    fi

    # Capturar una sola vez los procesos que todavía ejecutan código desde
    # cualquiera de los árboles sustituidos. sort -u evita esperar dos veces
    # una misma instancia si dos raíces históricas llegaran a solaparse.
    mapfile -t process_pids < <(
        for root in "${roots[@]}"; do
            pgrep -f -- "$root/python/main.py" || true
            pgrep -f -- "$root/python/panel.py" || true
            pgrep -f -- "$root/python/about.py" || true
            pgrep -f -- "$root/python/debug_log_viewer.py" || true
            pgrep -f -- "$root/python/docs_viewer.py" || true
            pgrep -f -- "$root/python/add_bookmark.py" || true
            pgrep -f -- "$root/python/shell_add_bookmark.py" || true
            pgrep -f -- "$root/python/shell_send_to_monitor.py" || true
            pgrep -f -- "$root/python/send_command.py" || true
        done | sort -u
    )

    if [ "${#process_pids[@]}" -gt 0 ]; then
        if ! terminate_pids_and_wait 2000 "${process_pids[@]}"; then
            fail 'WMM could not be stopped safely.'
            return 1
        fi
    fi

    # Barrera final única: ningún proceso nuevo asociado al árbol puede haber
    # aparecido durante la transición antes de que sustituyamos sus archivos.
    for root in "${roots[@]}"; do
        if pgrep -f -- "$root/python/main.py" >/dev/null 2>&1 \
            || pgrep -f -- "$root/python/panel.py" >/dev/null 2>&1 \
            || pgrep -f -- "$root/python/about.py" >/dev/null 2>&1 \
            || pgrep -f -- "$root/python/debug_log_viewer.py" >/dev/null 2>&1 \
            || pgrep -f -- "$root/python/docs_viewer.py" >/dev/null 2>&1 \
            || pgrep -f -- "$root/python/add_bookmark.py" >/dev/null 2>&1 \
            || pgrep -f -- "$root/python/shell_add_bookmark.py" >/dev/null 2>&1 \
            || pgrep -f -- "$root/python/shell_send_to_monitor.py" >/dev/null 2>&1 \
            || pgrep -f -- "$root/python/send_command.py" >/dev/null 2>&1; then

            fail 'WMM processes reappeared while stopping.'
            return 1
        fi
    done

    ok 'WMM stopped.'
    return 0
}

# ----------------------------------------------------------
# External resources
# ----------------------------------------------------------

# ----------------------------------------------------------
# FUNCIÓN: Refrescar registros del escritorio
# Actualiza D-Bus y las bases de datos de aplicaciones/servicios cuando
# acabamos de instalar o retirar recursos externos.
# ----------------------------------------------------------
refresh() {
    # Recargar el registro D-Bus de la sesión.
    if command -v busctl >/dev/null 2>&1; then
        busctl --user call \
            org.freedesktop.DBus \
            /org/freedesktop/DBus \
            org.freedesktop.DBus \
            ReloadConfig \
            >/dev/null 2>&1 || true
    else
        "$DBUS_SEND_BIN" \
            --session \
            --type=method_call \
            --dest=org.freedesktop.DBus \
            /org/freedesktop/DBus \
            org.freedesktop.DBus.ReloadConfig \
            >/dev/null 2>&1 || true
    fi

    # Refrescar los lanzadores instalados.
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database "$APPLICATIONS_DIR" >/dev/null 2>&1 || true
    fi

    # KDE mantiene además su propia caché de servicios/aplicaciones.
    # En Upgrade puede cambiar el storage ID del launcher; una actualización
    # incremental no garantiza que KService resuelva inmediatamente la nueva
    # identidad antes de que el engine registre sus acciones en KGlobalAccel.
    if [ "$DESKTOP" = kde ] && command -v kbuildsycoca6 >/dev/null 2>&1; then
        kbuildsycoca6 --noincremental >/dev/null 2>&1 || true
    fi
}

# ----------------------------------------------------------
# FUNCIÓN: Respaldar recursos externos existentes
# Guarda sólo los archivos externos que el reemplazo puede sobrescribir.
# El plasmoide KDE mantiene su propio backup durante el swap.
# ----------------------------------------------------------
backup_external_resources() {
    local backup_root="${TMPDIR:-/tmp}"

    EXTERNAL_BACKUP="$(mktemp -d "$backup_root/wmm-external-old.XXXXXX")" || return 1

    if [ -f "$DBUS_SERVICE" ]; then
        cp -a "$DBUS_SERVICE" "$EXTERNAL_BACKUP/dbus.service" || {
            discard_external_backup
            return 1
        }
    fi

    if [ -f "$LAUNCHER" ]; then
        cp -a "$LAUNCHER" "$EXTERNAL_BACKUP/launcher.desktop" || {
            discard_external_backup
            return 1
        }
    fi

    case "$DESKTOP" in

        gnome)
            # En GNOME <= 1.4.x el directorio de la extensión contiene también
            # el core y los datos. Preservarlo completo permite restaurar esa
            # topología si falla cualquier fase posterior del reemplazo.
            if [ -d "$FRONTEND_DIR" ]; then
                cp -a "$FRONTEND_DIR" "$EXTERNAL_BACKUP/gnome-frontend" || {
                    discard_external_backup
                    return 1
                }

                printf 'present\n' > "$EXTERNAL_BACKUP/gnome-frontend.state"
            else
                printf 'absent\n' > "$EXTERNAL_BACKUP/gnome-frontend.state"
            fi
            ;;

        kde)
            if [ -f "$AUTOSTART" ]; then
                cp -a "$AUTOSTART" "$EXTERNAL_BACKUP/autostart.desktop" || {
                    discard_external_backup
                    return 1
                }
            fi

            if [ -f "$INSTALL_MANAGER_SERVICE" ]; then
                cp -a "$INSTALL_MANAGER_SERVICE" "$EXTERNAL_BACKUP/install-manager.service" || {
                    discard_external_backup
                    return 1
                }
            fi

            if [ -f "$DEBUG_LOG_VIEWER_SERVICE" ]; then
                cp -a "$DEBUG_LOG_VIEWER_SERVICE" "$EXTERNAL_BACKUP/debug-log-viewer.service" || {
                    discard_external_backup
                    return 1
                }
            fi

            # El icono del About vive fuera del árbol del plasmoide.
            # Conservar el anterior permite recuperar también pruebas
            # manuales o personalizaciones si falla la instalación.
            if [ -f "$KDE_ABOUT_ICON" ]; then
                cp -a "$KDE_ABOUT_ICON" "$EXTERNAL_BACKUP/kde-about-icon.png" || {
                    discard_external_backup
                    return 1
                }
            fi

            ;;

        mate)
            if [ -f "$MATE_SERVICE" ]; then
                cp -a "$MATE_SERVICE" "$EXTERNAL_BACKUP/mate.service" || {
                    discard_external_backup
                    return 1
                }
            fi
            if [ -f "$MATE_DESCRIPTOR" ]; then
                cp -a "$MATE_DESCRIPTOR" "$EXTERNAL_BACKUP/mate-descriptor" || {
                    discard_external_backup
                    return 1
                }
            fi
            ;;

        xfce)
            # Launcher y autostart usan la misma plantilla, pero son recursos
            # XDG independientes y deben poder restaurarse por separado.
            if [ -f "$AUTOSTART" ]; then
                cp -a "$AUTOSTART" "$EXTERNAL_BACKUP/autostart.desktop" || {
                    discard_external_backup
                    return 1
                }
            fi

            # El helper vive en un espacio global compartido. Guardamos
            # explícitamente si existía antes para poder restaurar ese estado.
            if [ -e "$WMM_NEXT" ]; then
                if ! wmm_next_owned_by "$WMM_NEXT"; then
                    fail "Existing helper does not belong to WMM: $WMM_NEXT"
                    discard_external_backup
                    return 1
                fi

                cp -f "$WMM_NEXT" "$EXTERNAL_BACKUP/wmm-next.sh" || {
                    discard_external_backup
                    return 1
                }

                printf 'present\n' > "$EXTERNAL_BACKUP/wmm-next.state"
            else
                printf 'absent\n' > "$EXTERNAL_BACKUP/wmm-next.state"
            fi
            ;;
    esac

    ok 'Existing external resources backed up.'
}

restore_external_file() {
    local backup_file="$1"
    local target_file="$2"

    if [ -f "$backup_file" ]; then
        mkdir -p "$(dirname "$target_file")" || return 1
        cp -a "$backup_file" "$target_file" || return 1
    else
        rm -f "$target_file" || return 1
    fi
}

# ----------------------------------------------------------
# FUNCIÓN: Restaurar recursos externos
# Devuelve launcher, servicio D-Bus y recursos equivalentes al estado
# anterior. Si antes no existían, elimina los creados por el reemplazo.
# ----------------------------------------------------------
restore_external_resources() {
    [ -n "$EXTERNAL_BACKUP" ] && [ -d "$EXTERNAL_BACKUP" ] || return 0

    restore_external_file "$EXTERNAL_BACKUP/dbus.service" "$DBUS_SERVICE" || return 1
    restore_external_file "$EXTERNAL_BACKUP/launcher.desktop" "$LAUNCHER" || return 1

    case "$DESKTOP" in
        gnome)
            # GNOME observa el directorio de extensiones en vivo. Reconstruir el
            # frontend directamente en su ruta permitió que Shell intentara cargar
            # una copia todavía incompleta durante un rollback. Prepararlo como
            # hermano y publicarlo con un único rename evita ese estado intermedio.
            local restore_parent restore_dir

            case "$(cat "$EXTERNAL_BACKUP/gnome-frontend.state" 2>/dev/null)" in
                present)
                    restore_parent="$(dirname "$FRONTEND_DIR")"
                    mkdir -p "$restore_parent" || return 1
                    restore_dir="$(mktemp -d "$restore_parent/.wmm-gnome-restore.XXXXXX")" \
                        || return 1

                    cp -a "$EXTERNAL_BACKUP/gnome-frontend/." "$restore_dir/" \
                        || { rm -rf "$restore_dir"; return 1; }

                    [ -f "$restore_dir/extension.js" ] \
                        && [ -f "$restore_dir/metadata.json" ] \
                        || { rm -rf "$restore_dir"; return 1; }

                    if command -v gnome-extensions >/dev/null 2>&1; then
                        gnome-extensions disable "$APP_DOMAIN" >/dev/null 2>&1 || true
                    fi

                    rm -rf "$FRONTEND_DIR" \
                        || { rm -rf "$restore_dir"; return 1; }
                    mv "$restore_dir" "$FRONTEND_DIR" \
                        || { rm -rf "$restore_dir"; return 1; }
                    ;;

                absent)
                    if command -v gnome-extensions >/dev/null 2>&1; then
                        gnome-extensions disable "$APP_DOMAIN" >/dev/null 2>&1 || true
                    fi
                    rm -rf "$FRONTEND_DIR" || return 1
                    ;;

                *)
                    fail "Invalid or missing GNOME frontend backup state."
                    return 1
                    ;;
            esac
            ;;

        kde)
            restore_external_file "$EXTERNAL_BACKUP/autostart.desktop" "$AUTOSTART" || return 1
            restore_external_file "$EXTERNAL_BACKUP/install-manager.service" "$INSTALL_MANAGER_SERVICE" || return 1
            restore_external_file "$EXTERNAL_BACKUP/debug-log-viewer.service" "$DEBUG_LOG_VIEWER_SERVICE" || return 1
            # Recuperar el estado exacto del icono previo al reemplazo.
            restore_external_file "$EXTERNAL_BACKUP/kde-about-icon.png" "$KDE_ABOUT_ICON" || return 1
            ;;

        mate)
            restore_external_file "$EXTERNAL_BACKUP/mate.service" "$MATE_SERVICE" || return 1

            if [ -f "$EXTERNAL_BACKUP/mate-descriptor" ]; then
                sudo install -m 0644 "$EXTERNAL_BACKUP/mate-descriptor" "$MATE_DESCRIPTOR" || return 1
            else
                sudo rm -f "$MATE_DESCRIPTOR" || return 1
            fi
            ;;

        xfce)
            restore_external_file \
                "$EXTERNAL_BACKUP/autostart.desktop" \
                "$AUTOSTART" \
                || return 1

            # Restaurar exactamente el estado previo del helper global.
            case "$(cat "$EXTERNAL_BACKUP/wmm-next.state" 2>/dev/null)" in
                present)
                    # Si alguien sustituyó el helper durante la operación,
                    # no sobrescribir ese archivo ajeno durante el rollback.
                    if [ -e "$WMM_NEXT" ] && ! wmm_next_owned_by "$WMM_NEXT"; then
                        fail "Rollback cannot overwrite unrelated file: $WMM_NEXT"
                        return 1
                    fi

                    sudo install -m 0755 \
                        "$EXTERNAL_BACKUP/wmm-next.sh" \
                        "$WMM_NEXT" \
                        || return 1
                    ;;

                absent)
                    # Antes del reemplazo no existía helper: retirar únicamente
                    # el creado por WMM y preservar cualquier archivo ajeno.
                    if [ -e "$WMM_NEXT" ]; then
                        if wmm_next_owned_by "$WMM_NEXT"; then
                            sudo rm -f -- "$WMM_NEXT" || return 1
                        else
                            fail "Rollback cannot remove unrelated file: $WMM_NEXT"
                            return 1
                        fi
                    fi
                    ;;

                *)
                    fail "Invalid or missing XFCE helper backup state."
                    return 1
                    ;;
            esac
            ;;
    esac
}

discard_external_backup() {
    [ -n "$EXTERNAL_BACKUP" ] && [ -d "$EXTERNAL_BACKUP" ] && rm -rf "$EXTERNAL_BACKUP"
    EXTERNAL_BACKUP=''
}

# ----------------------------------------------------------
# FUNCIÓN: Migrar UUID legacy del applet Cinnamon
# Conserva panel, posición e ID de instancia; sólo cambia la identidad
# persistida del frontend cuando procede de Cinnamon <= v1.2.2.
# ----------------------------------------------------------
migrate_cinnamon_applet_uuid() {
    [ "$DESKTOP" = cinnamon ] || return 0

    "$PYTHON3_BIN" - "$APP_DOMAIN" <<'PY'
import sys

try:
    import gi
    gi.require_version("Gio", "2.0")
    from gi.repository import Gio
except Exception as error:
    print(f"[!!] Could not load Gio for Cinnamon applet migration: {error}", file=sys.stderr)
    raise SystemExit(1)

current_uuid = sys.argv[1]
legacy_uuid = "wmm-applet@maki"
settings = Gio.Settings.new("org.cinnamon")
original = list(settings.get_strv("enabled-applets"))

def entry_uuid(entry):
    parts = entry.split(":")
    return parts[3] if len(parts) >= 4 else None

legacy_present = any(entry_uuid(entry) == legacy_uuid for entry in original)

if not legacy_present:
    raise SystemExit(0)

current_present = any(entry_uuid(entry) == current_uuid for entry in original)
updated = []

if current_present:
    # Si ya existe la identidad actual, ésta prevalece. Retirar únicamente
    # las instancias legacy para evitar duplicados.
    updated = [ entry for entry in original if entry_uuid(entry) != legacy_uuid ]
else:
    # Conservar íntegramente panel, zona, posición e ID de instancia.
    for entry in original:
        parts = entry.split(":")

        if len(parts) >= 4 and parts[3] == legacy_uuid:
            parts[3] = current_uuid
            entry = ":".join(parts)

        updated.append(entry)

try:
    if not settings.set_strv("enabled-applets", updated):
        raise RuntimeError("Cinnamon rejected the updated applet list")

    Gio.Settings.sync()

    if list(settings.get_strv("enabled-applets")) != updated:
        raise RuntimeError("Cinnamon did not persist the updated applet list")

except Exception as error:
    try:
        if not settings.set_strv("enabled-applets", original):
            raise RuntimeError("Cinnamon rejected the previous applet list")

        Gio.Settings.sync()

        if list(settings.get_strv("enabled-applets")) != original:
            raise RuntimeError("Cinnamon did not restore the previous applet list")

    except Exception as restore_error:
        print( "[!!] CRITICAL: Cinnamon applet registration could not be "
            f"restored: {restore_error}", file=sys.stderr, )

    print(f"[!!] Cinnamon applet UUID migration failed: {error}", file=sys.stderr, )
    raise SystemExit(1)

print( f"[OK] Cinnamon applet registration migrated: " f"{legacy_uuid} -> {current_uuid}" )
PY
}

# ----------------------------------------------------------
# FUNCIÓN: Instalar integración del escritorio
# Instala servicio D-Bus, launcher y los recursos específicos de Cinnamon,
# GNOME, KDE o MATE fuera de APP_DIR.
# ----------------------------------------------------------
install_external() {
    local parent new old next_tmp

    info 'Installing desktop integration resources...'
    mkdir -p "$DBUS_DIR" "$APPLICATIONS_DIR" "$CACHE_DIR/thumbnails" || return 1

    # Servicio D-Bus común a todos los escritorios.
    template \
        "$PROJECT_DIR/wmm_platform/shell/linux/org.maki.wmm.service" \
        "$DBUS_SERVICE" \
        || return 1
    chmod 644 "$DBUS_SERVICE"

    # Instalar los recursos específicos del escritorio activo.
    case "$DESKTOP" in
        cinnamon)
            # Preparar primero el frontend completo. El temporal es hermano
            # del destino para que la activación final sea un simple rename.
            parent="$(dirname "$FRONTEND_DIR")"
            mkdir -p "$parent" || return 1
            new="$(mktemp -d "$parent/.wmm-cinnamon-new.XXXXXX")" || return 1

            cp -f \
                "$PROJECT_DIR/wmm_platform/shell/cinnamon/applet.cinnamon.js" \
                "$new/applet.js" \
                || { rm -rf "$new"; return 1; }

            cp -f \
                "$PROJECT_DIR/wmm_platform/shell/cinnamon/stylesheet.css" \
                "$new/stylesheet.css" \
                || { rm -rf "$new"; return 1; }

            cp -f "$PROJECT_DIR/icon.png" "$new/icon.png" \
                || { rm -rf "$new"; return 1; }

            template \
                "$PROJECT_DIR/wmm_platform/shell/cinnamon/metadata.cinnamon.json" \
                "$new/metadata.json" \
                || { rm -rf "$new"; return 1; }

            template \
                "$PROJECT_DIR/wmm_platform/shell/linux/settings_core.ini" \
                "$new/settings_core.ini" \
                || { rm -rf "$new"; return 1; }

            [ -f "$new/applet.js" ] \
                && [ -f "$new/stylesheet.css" ] \
                && [ -f "$new/icon.png" ] \
                && [ -f "$new/metadata.json" ] \
                && [ -f "$new/settings_core.ini" ] \
                || { rm -rf "$new"; return 1; }

            # El launcher también debe quedar generado antes de alterar
            # cualquier frontend Cinnamon existente.
            template \
                "$PROJECT_DIR/wmm_platform/shell/cinnamon/org.maki.wmm.cinnamon.desktop" \
                "$LAUNCHER" \
                || { rm -rf "$new"; return 1; }

            # Conservar el frontend actual hasta haber activado y validado
            # completamente el nuevo.
            old=""

            if [ -d "$FRONTEND_DIR" ]; then
                old="$(mktemp -d "$parent/.wmm-cinnamon-old.XXXXXX")" \
                    || { rm -rf "$new"; return 1; }

                rmdir "$old" \
                    || { rm -rf "$new" "$old"; return 1; }

                mv "$FRONTEND_DIR" "$old" \
                    || { rm -rf "$new"; return 1; }
            fi

            if ! mv "$new" "$FRONTEND_DIR"; then
                if [ -n "$old" ] && [ -d "$old" ] \
                    && ! mv "$old" "$FRONTEND_DIR"; then
                    fail "CRITICAL: previous Cinnamon frontend remains at $old"
                fi
                return 1
            fi

            # Cinnamon <= v1.2.2 persistía el UUID wmm-applet@maki.
            # Migrar únicamente esa identidad después de activar el frontend
            # nuevo, pero mientras el árbol legacy sigue disponible.
            if ! migrate_cinnamon_applet_uuid; then
                rm -rf "$FRONTEND_DIR"

                if [ -n "$old" ] && [ -d "$old" ] \
                    && ! mv "$old" "$FRONTEND_DIR"; then
                    fail "CRITICAL: previous Cinnamon frontend remains at $old"
                fi

                return 1
            fi

            # La transacción local ya está confirmada. El árbol
            # wmm-applet@maki se conserva todavía hasta commit().
            if [ -n "$old" ] && [ -d "$old" ]; then
                rm -rf "$old" \
                    || warn "Could not remove temporary Cinnamon frontend backup: $old"
            fi
            ;;

        gnome)
            # Preparar el frontend GNOME completo fuera del core. El temporal
            # es hermano del destino para que la activación final sea un rename.
            parent="$(dirname "$FRONTEND_DIR")"
            mkdir -p "$parent" || return 1
            new="$(mktemp -d "$parent/.wmm-gnome-new.XXXXXX")" || return 1

            cp -f \
                "$PROJECT_DIR/wmm_platform/shell/gnome/extension.gnome.js" \
                "$new/extension.js" \
                || { rm -rf "$new"; return 1; }

            template \
                "$PROJECT_DIR/wmm_platform/shell/gnome/metadata.gnome.json" \
                "$new/metadata.json" \
                || { rm -rf "$new"; return 1; }

            cp -f \
                "$PROJECT_DIR/wmm_platform/shell/gnome/stylesheet.css" \
                "$new/stylesheet.css" \
                || { rm -rf "$new"; return 1; }

            template \
                "$PROJECT_DIR/wmm_platform/shell/linux/settings_core.ini" \
                "$new/settings_core.ini" \
                || { rm -rf "$new"; return 1; }

            [ -f "$new/extension.js" ] \
                && [ -f "$new/metadata.json" ] \
                && [ -f "$new/stylesheet.css" ] \
                && [ -f "$new/settings_core.ini" ] \
                || { rm -rf "$new"; return 1; }

            # Generar también el launcher antes de alterar el frontend existente.
            template \
                "$PROJECT_DIR/wmm_platform/shell/gnome/org.maki.wmm.gnome.desktop" \
                "$LAUNCHER" \
                || { rm -rf "$new"; return 1; }

            # El frontend anterior ya está protegido por
            # backup_external_resources(). Sustituirlo sólo cuando el nuevo
            # árbol está completo y validado.
            rm -rf "$FRONTEND_DIR" \
                || { rm -rf "$new"; return 1; }

            mv "$new" "$FRONTEND_DIR" || return 1
            ;;

        mate)
            template \
                "$PROJECT_DIR/wmm_platform/shell/mate/org.mate.panel.applet.WMMAppletFactory.service" \
                "$MATE_SERVICE" \
                || return 1
            chmod 644 "$MATE_SERVICE"

            sudo install -m 0644 \
                "$PROJECT_DIR/wmm_platform/shell/mate/org.maki.wmm.mate-panel-applet" \
                "$MATE_DESCRIPTOR" \
                || return 1

            template \
                "$PROJECT_DIR/wmm_platform/shell/mate/org.maki.wmm.mate.desktop" \
                "$LAUNCHER" \
                || return 1
            ;;
        xfce)
            # Launcher y autostart reutilizan la misma plantilla XFCE.
            mkdir -p "$AUTOSTART_DIR" || return 1

            template \
                "$PROJECT_DIR/wmm_platform/shell/xfce/org.maki.wmm.xfce.desktop" \
                "$LAUNCHER" \
                || return 1

            template \
                "$PROJECT_DIR/wmm_platform/shell/xfce/org.maki.wmm.xfce.desktop" \
                "$AUTOSTART" \
                || return 1

            # /usr/local/bin es compartido con el resto del sistema.
            # No sobrescribir un archivo preexistente que no pertenezca a WMM.
            if [ -e "$WMM_NEXT" ] && ! wmm_next_owned_by "$WMM_NEXT"; then
                fail "Refusing to overwrite unrelated file: $WMM_NEXT"
                return 1
            fi

            next_tmp="$(mktemp)" || return 1

            template \
                "$PROJECT_DIR/wmm_platform/shell/linux/wmm-next.sh" \
                "$next_tmp" \
                || { rm -f "$next_tmp"; return 1; }

            sudo install -m 0755 "$next_tmp" "$WMM_NEXT" \
                || { rm -f "$next_tmp"; return 1; }

            rm -f "$next_tmp"
            ;;

        kde)
            # Launcher, autostart y plasmoide viven fuera de APP_DIR.
            mkdir -p "$AUTOSTART_DIR" "$(dirname "$PLASMOID_DIR")" || return 1

            template \
                "$PROJECT_DIR/wmm_platform/shell/kde/org.maki.wmm.kde.desktop" \
                "$LAUNCHER" \
                || return 1

            template \
                "$PROJECT_DIR/wmm_platform/shell/kde/org.maki.wmm.kde.desktop" \
                "$AUTOSTART" \
                || return 1

            # Servicios D-Bus de las herramientas independientes del engine.
            template \
                "$PROJECT_DIR/wmm_platform/shell/linux/org.maki.wmm.InstallManager.service" \
                "$INSTALL_MANAGER_SERVICE" \
                || return 1

            template \
                "$PROJECT_DIR/wmm_platform/shell/linux/org.maki.wmm.DebugLogViewer.service" \
                "$DEBUG_LOG_VIEWER_SERVICE" \
                || return 1

            chmod 644 "$INSTALL_MANAGER_SERVICE" "$DEBUG_LOG_VIEWER_SERVICE"

            # Preparar el nuevo plasmoide en staging propio.
            parent="$(dirname "$PLASMOID_DIR")"
            new="$(mktemp -d "$parent/.wmm-plasmoid-new.XXXXXX")" || return 1

            cp -a \
                "$PROJECT_DIR/wmm_platform/shell/kde/plasmoid_contents/contents" \
                "$new/" \
                || {
                    rm -rf "$new"
                    return 1
                }

            template \
                "$PROJECT_DIR/wmm_platform/shell/kde/plasmoid_contents/metadata.kde_plasmoid.json" \
                "$new/metadata.json" \
                || {
                    rm -rf "$new"
                    return 1
                }

            # El About nativo resuelve KPlugin.Icon mediante el tema de iconos.
            # La plantilla conserva video-display como fallback cuando
            # icon.png no está disponible en el paquete de instalación.
            if [ -s "$PROJECT_DIR/icon.png" ]; then
                mkdir -p "$(dirname "$KDE_ABOUT_ICON")" || return 1

                install -m 0644 "$PROJECT_DIR/icon.png" "$KDE_ABOUT_ICON" \
                    || return 1

                # Publicar el nombre propio sólo después de instalar el PNG.
                sed -i 's|"Icon": "video-display"|"Icon": "org.maki.wmm"|' \
                    "$new/metadata.json" \
                    || {
                        rm -rf "$new"
                        return 1
                    }
            fi

            # settings_core.ini enlaza el frontend Plasma con el core y los
            # datos comunes. Debe quedar completo antes de publicar el plasmoide.
            template \
                "$PROJECT_DIR/wmm_platform/shell/linux/settings_core.ini" \
                "$new/settings_core.ini" \
                || {
                    rm -rf "$new"
                    return 1
                }

            # Apartar el plasmoide anterior hasta confirmar el commit.
            if [ -d "$PLASMOID_DIR" ]; then
                old="$(mktemp -d "$parent/.wmm-plasmoid-old.XXXXXX")" || {
                    rm -rf "$new"
                    return 1
                }

                rmdir "$old"
                mv "$PLASMOID_DIR" "$old" || {
                    rm -rf "$new"
                    return 1
                }
                OLD_PLASMOID="$old"
            fi

            if ! mv "$new" "$PLASMOID_DIR"; then
                [ -n "$OLD_PLASMOID" ] && mv "$OLD_PLASMOID" "$PLASMOID_DIR" || true
                OLD_PLASMOID=''
                return 1
            fi
            PLASMOID_SWAPPED=1

            # Registrar el paquete sólo cuando no existía una instalación previa.
            # En Replace, el plasmoide ya se sustituye atómicamente conservando
            # el mismo ID y la misma ruta. No usar --upgrade sobre PLASMOID_DIR:
            # KPackage elimina primero esa ruta y destruye así su propia fuente.
            if command -v kpackagetool6 >/dev/null 2>&1 && [ -z "$OLD_PLASMOID" ]; then
                kpackagetool6 -t Plasma/Applet --install "$PLASMOID_DIR" >/dev/null 2>&1 || true
            fi
            ;;
    esac

    refresh
    ok 'Desktop integration resources installed.'
}

# ----------------------------------------------------------
# FUNCIÓN: Relanzar frontend
# Tras Upgrade/Reinstall vuelve a poner operativo el frontend correspondiente.
# Cada escritorio utiliza su lifecycle nativo de recarga/activación.
# ----------------------------------------------------------
relaunch_frontend() {
    info 'Reloading WMM frontend...'
    case "$DESKTOP" in
        cinnamon)
            [ "$GRAPHICS_ENGINE" = x11 ] || { warn 'Cinnamon reload requires X11; restart the session.'; return 1; }
            if "$DBUS_SEND_BIN" \
                --session \
                --type=method_call \
                --dest=org.Cinnamon \
                /org/Cinnamon \
                org.Cinnamon.RestartCinnamon \
                boolean:true \
                >/dev/null 2>&1; then
                ok 'Cinnamon frontend reload requested.'
                return 0
            fi
            ;;
        gnome)
            command -v gnome-extensions >/dev/null 2>&1 || {
                warn 'gnome-extensions command is unavailable.'
                break
            }

            local enable_error readiness_status readiness_rc

            if ! enable_error="$(gnome-extensions enable "$APP_DOMAIN" 2>&1)"; then
                warn 'GNOME rejected the extension enable request.'
                [ -z "$enable_error" ] || warn "$enable_error"
                break
            fi

            # El comando enable sólo confirma que GNOME aceptó la petición.
            # El reemplazo queda validado cuando tanto la extensión como el
            # engine nuevo publican sus nombres D-Bus. La espera es reactiva:
            # no se sondea estado ni se introducen sleeps. Si vence el plazo,
            # conservar qué frontera no llegó a estar operativa evita convertir
            # extensión y engine en un único fallo opaco.
            readiness_status="$("$PYTHON3_BIN" - <<'PY' 2>&1
import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

names = ("org.maki.wmm.Gnome", "org.maki.wmm")
required = set(names)
loop = GLib.MainLoop()
watch_ids = []

def name_appeared(_connection, name, _owner):
    required.discard(name)
    if not required:
        loop.quit()

for bus_name in names:
    watch_ids.append(
        Gio.bus_watch_name(
            Gio.BusType.SESSION,
            bus_name,
            Gio.BusNameWatcherFlags.NONE,
            name_appeared, None, ))

def timeout():
    loop.quit()
    return GLib.SOURCE_REMOVE

timeout_id = GLib.timeout_add_seconds(10, timeout)
loop.run()

for watch_id in watch_ids:
    Gio.bus_unwatch_name(watch_id)

if not required:
    GLib.source_remove(timeout_id)
    raise SystemExit(0)

for bus_name in names:
    state = "missing" if bus_name in required else "present"
    print(f"{bus_name}: {state}")

raise SystemExit(1)
PY
)"
            readiness_rc=$?

            if [ "$readiness_rc" -eq 0 ]; then
                ok 'GNOME extension and engine relaunched.'
                return 0
            fi

            warn 'GNOME frontend readiness was not completed.'
            while IFS= read -r line; do
                [ -z "$line" ] || warn "$line"
            done <<< "$readiness_status"
            ;;

        kde)
            if "$DBUS_SEND_BIN" \
                --session \
                --type=method_call \
                --print-reply \
                --dest=org.freedesktop.DBus \
                /org/freedesktop/DBus \
                org.freedesktop.DBus.StartServiceByName \
                string:org.maki.wmm \
                uint32:0 \
                >/dev/null 2>&1; then
                ok 'KDE frontend relaunched.'
                return 0
            fi
            ;;

        mate)
            if [ -n "$MATE_APPLET_STATE" ]; then
                "$PYTHON3_BIN" "$PROJECT_DIR/wmm_platform/shell/mate/mate-launcher.py" \
                    --restore "$MATE_APPLET_STATE" >/dev/null 2>&1 && {
                        MATE_APPLET_STATE=''
                        ok 'MATE frontend relaunched.'
                        return 0
                    }
            else
                "$PYTHON3_BIN" "$FRONTEND_DIR/mate-launcher.py" >/dev/null 2>&1 && {
                    ok 'MATE frontend relaunched.'
                    return 0
                }
            fi
            ;;

        xfce)
            # Tras Replace, lanzar el frontend residente desde el árbol nuevo.
            # El relanzado sólo se considera válido cuando D-Bus confirma
            # reactivamente que la nueva instancia ha reclamado su nombre.
            nohup "$PYTHON3_BIN" "$FRONTEND_DIR/xfce-frontend.py" \
                >/dev/null 2>&1 &

            if "$PYTHON3_BIN" - <<'PY'
import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

bus_name = "org.maki.wmm.XfceFrontend"
appeared = False
loop = GLib.MainLoop()

def name_appeared(_connection, _name, _owner):
    global appeared
    appeared = True
    loop.quit()

def timeout():
    loop.quit()
    return GLib.SOURCE_REMOVE

watch_id = Gio.bus_watch_name(
    Gio.BusType.SESSION,
    bus_name,
    Gio.BusNameWatcherFlags.NONE,
    name_appeared,
    None,
)

timeout_id = GLib.timeout_add(2000, timeout)
loop.run()

Gio.bus_unwatch_name(watch_id)

if appeared:
    GLib.source_remove(timeout_id)
    raise SystemExit(0)

raise SystemExit(1)
PY
            then
                ok 'XFCE frontend relaunched.'
                return 0
            fi
            ;;
    esac
    warn 'Frontend reload could not be completed automatically.'; return 1
}

# ----------------------------------------------------------
# FUNCIÓN: Recuperar runtime tras abortar un reemplazo
# En GNOME con activación diferida la extensión nunca se deshabilitó; sólo
# hay que recuperar el engine anterior. El resto usa su relanzado normal.
# ----------------------------------------------------------
recover_runtime_after_abort() {
    if [ "$DESKTOP" = gnome ] && [ "$GNOME_SESSION_RESTART_REQUIRED" -eq 1 ]; then
        "$DBUS_SEND_BIN" \
            --session \
            --print-reply \
            --dest=org.freedesktop.DBus \
            /org/freedesktop/DBus \
            org.freedesktop.DBus.StartServiceByName \
            string:org.maki.wmm \
            uint32:0 \
            >/dev/null 2>&1 || true
        return 0
    fi

    relaunch_frontend || true
}

# ----------------------------------------------------------
# Rollback / commit
# ----------------------------------------------------------

# ----------------------------------------------------------
# FUNCIÓN: Rollback
# Restaura la instalación anterior si falla una fase posterior al swap.
# En instalación limpia elimina únicamente los recursos creados por WMM.
# ----------------------------------------------------------
rollback() {
    local external_restore_failed=0

    warn 'Restoring previous WMM installation...'

    # MATE y XFCE pueden haber materializado un frontend nuevo antes de que
    # el relaunch falle. Retirarlo antes del core evita dejar código vivo sobre
    # el árbol que rollback va a borrar. En MATE se descarta deliberadamente
    # el estado devuelto: MATE_APPLET_STATE conserva la identidad original.
    if [ "$WMM_PRESENT" -eq 1 ]; then
        case "$DESKTOP" in
            mate)
                "$PYTHON3_BIN" "$PROJECT_DIR/wmm_platform/shell/mate/mate-launcher.py" \
                    --unload >/dev/null || {
                        fail 'CRITICAL: failed MATE frontend could not be stopped before rollback.'
                        return 1
                    }
                ;;

            xfce)
                if ! unload_frontend; then
                    fail 'CRITICAL: failed XFCE frontend could not be stopped before rollback.'
                    return 1
                fi
                ;;
        esac
    fi

    # Un fallo posterior al relanzado puede dejar vivo el runtime nacido del
    # árbol que vamos a retirar. Detenerlo antes de restaurar evita conservar
    # procesos huérfanos ejecutándose sobre core/data que ya no existen.
    if ! stop_wmm; then
        fail 'CRITICAL: failed WMM runtime could not be stopped before rollback.'
        return 1
    fi

    # Restaurar el core anterior.
    rm -rf "$APP_DIR" 2>/dev/null || true

    if [ -n "$OLD_APP" ] && [ -d "$OLD_APP" ]; then
        mv "$OLD_APP" "$APP_DIR" || {
            fail "CRITICAL: previous installation remains at $OLD_APP"
            return 1
        }
        OLD_APP=''
    fi

    # Restaurar los datos anteriores.
    rm -rf "$DATA_DIR" 2>/dev/null || true

    if [ -n "$OLD_DATA" ] && [ -d "$OLD_DATA" ]; then
        mv "$OLD_DATA" "$DATA_DIR" || {
            fail "CRITICAL: previous data remains at $OLD_DATA"
            return 1
        }
        OLD_DATA=''
    fi

    if [ "$DESKTOP" = kde ] && [ "$PLASMOID_SWAPPED" -eq 1 ]; then
        rm -rf "$PLASMOID_DIR" 2>/dev/null || true

        if [ -n "$OLD_PLASMOID" ] && [ -d "$OLD_PLASMOID" ]; then
            mv "$OLD_PLASMOID" "$PLASMOID_DIR" || return 1
            OLD_PLASMOID=''
        fi

        PLASMOID_SWAPPED=0
    fi

    if [ "$WMM_PRESENT" -eq 0 ]; then
        rmdir "$APP_CONFIG" 2>/dev/null || true
        rm -f "$DBUS_SERVICE" "$LAUNCHER" 2>/dev/null || true

        if [ "$DESKTOP" = gnome ]; then
            # Una instalación limpia fallida no tiene frontend anterior que
            # preservar. Retirar también el árbol GNOME creado en esta operación.
            rm -rf "$FRONTEND_DIR" 2>/dev/null || true
        fi

        if [ "$DESKTOP" = kde ]; then
            rm -f \
                "$AUTOSTART" \
                "$INSTALL_MANAGER_SERVICE" \
                "$DEBUG_LOG_VIEWER_SERVICE" \
                2>/dev/null || true

            rm -rf "$PLASMOID_DIR" 2>/dev/null || true

            # Sólo restaurar si el respaldo llegó a completarse.
            # Si falló antes de instalar recursos, no tocar el icono previo.
            if [ -n "$EXTERNAL_BACKUP" ] && [ -d "$EXTERNAL_BACKUP" ]; then
                restore_external_file \
                    "$EXTERNAL_BACKUP/kde-about-icon.png" \
                    "$KDE_ABOUT_ICON" \
                    || external_restore_failed=1
            fi
        fi

        if [ "$DESKTOP" = mate ]; then
            rm -f "$MATE_SERVICE" 2>/dev/null || true
            sudo rm -f "$MATE_DESCRIPTOR" >/dev/null 2>&1 || true
        fi

        if [ "$DESKTOP" = xfce ]; then
            # En una instalación limpia fallida, retirar también el autostart
            # creado junto al launcher.
            rm -f "$AUTOSTART" 2>/dev/null || true

            if [ -e "$WMM_NEXT" ]; then
                if wmm_next_owned_by "$WMM_NEXT"; then
                    sudo rm -f -- "$WMM_NEXT" || external_restore_failed=1
                else
                    warn "Preserved unrelated file during rollback: $WMM_NEXT"
                fi
            fi
        fi

        refresh
    else
        restore_external_resources || external_restore_failed=1
        refresh
        recover_runtime_after_abort
    fi

    if [ "$external_restore_failed" -ne 0 ]; then
        if [ "$WMM_PRESENT" -eq 0 ]; then
            fail "Clean-install rollback is incomplete."
        else
            fail "External resource rollback is incomplete. Backup preserved at: $EXTERNAL_BACKUP"
        fi
        return 1
    fi

    discard_external_backup
    ok 'Previous WMM installation restored.'
}

# ----------------------------------------------------------
# FUNCIÓN: Confirmar instalación
# Elimina las copias temporales sólo cuando el nuevo árbol, su integración
# y el relanzado del frontend han terminado correctamente.
# ----------------------------------------------------------
commit() {
    [ -n "$OLD_APP" ] && [ -d "$OLD_APP" ] && rm -rf "$OLD_APP"
    [ -n "$OLD_DATA" ] && [ -d "$OLD_DATA" ] && rm -rf "$OLD_DATA"
    [ -n "$OLD_PLASMOID" ] && [ -d "$OLD_PLASMOID" ] && rm -rf "$OLD_PLASMOID"

    # GNOME <= 1.4.x instalaba el servicio del engine bajo el UUID de la
    # extensión. Retirarlo sólo tras confirmar la nueva instalación y
    # únicamente si todavía pertenece a una topología WMM conocida.
    if [ "$DESKTOP" = gnome ] \
        && { service_owned_by "$DBUS_DIR/wmm@maki.service" "$FRONTEND_DIR" \
            || service_owned_by "$DBUS_DIR/wmm@maki.service" "$APP_DIR"; }; then

        rm -f "$DBUS_DIR/wmm@maki.service"
        refresh
    fi

    [ -n "$LEGACY_APP_DIR" ] \
        && [ "$LEGACY_APP_DIR" != "$APP_DIR" ] \
        && [ -d "$LEGACY_APP_DIR" ] \
        && rm -rf "$LEGACY_APP_DIR"

    if [ "$DESKTOP" = kde ] \
        && { [ -f "$LEGACY_KDE_LAUNCHER" ] || [ -f "$LEGACY_KDE_AUTOSTART" ]; }; then
        rm -f "$LEGACY_KDE_LAUNCHER" "$LEGACY_KDE_AUTOSTART"
        refresh
    fi

    discard_external_backup

    OLD_APP=''
    OLD_DATA=''
    OLD_PLASMOID=''
    PLASMOID_SWAPPED=0
}

# ----------------------------------------------------------
# Operation flows
# ----------------------------------------------------------
MODE=repair
FORCED_MODE=''
# ----------------------------------------------------------
# FUNCIÓN: Resolver tipo de reemplazo
# Determina Upgrade, Repair/Reinstall o Downgrade comparando versiones.
# ----------------------------------------------------------
resolve_mode() {
    [ -n "$FORCED_MODE" ] && { MODE="$FORCED_MODE"; return; }
    [ -z "$INSTALLED_VERSION" ] && { MODE=repair; return; }
    case "$(version_cmp "$INSTALLED_VERSION" "$WMM_VERSION")" in
        -1) MODE=upgrade ;;
         0) MODE=repair ;;
         1) MODE=downgrade ;;
    esac
}
# ----------------------------------------------------------
# FUNCIÓN: Presentar / confirmar reemplazo
# Informa de la operación calculada y pide confirmación extra sólo si
# el paquete implica un downgrade.
# ----------------------------------------------------------
confirm_replace() {
    local answer; resolve_mode; echo
    case "$MODE" in
        upgrade) info "Upgrade: WMM $INSTALLED_VERSION -> $WMM_VERSION" ;;
        repair)
            if [ -n "$INSTALLED_VERSION" ]; then
                info "Repair / Reinstall: WMM $WMM_VERSION"
            else
                info 'Repair / Reinstall: installed version unavailable.'
            fi
            ;;
        downgrade)
            warn "Installed WMM $INSTALLED_VERSION is newer than package $WMM_VERSION."
            read -r -p 'Continue with downgrade? (y/n): ' answer || answer=n
            [[ "$answer" =~ ^[Yy]$ ]] || {
                info 'Downgrade cancelled.'
                return 1
            }
            ;;
    esac
}

# Preflight común: dependencias, herramientas e integridad del paquete.
prepare_action() { ensure_deps && prepare_tools && validate_source; }

# ----------------------------------------------------------
# FUNCIÓN: Ejecutar instalación limpia
# Verifica, prepara staging, activa WMM e instala la integración inicial.
# ----------------------------------------------------------
run_install() {
    prepare_action || return 1

    prepare_staging 0 || {
        [ -n "$STAGING" ] && rm -rf "$STAGING"
        [ -n "$DATA_STAGING" ] && rm -rf "$DATA_STAGING"
        fail 'Could not prepare staging.'
        return 1
    }

    activate_staging || {
        [ -n "$STAGING" ] && rm -rf "$STAGING"
        [ -n "$DATA_STAGING" ] && rm -rf "$DATA_STAGING"
        return 1
    }

    # KDE puede encontrar un icono preexistente incluso en instalación
    # limpia. Respaldarlo antes de sustituirlo evita perderlo ante un fallo.
    if [ "$DESKTOP" = kde ]; then
        backup_external_resources || {
            fail 'Could not back up existing KDE integration resources.'
            rollback
            return 1
        }
    fi

    install_external || {
        fail 'Desktop integration failed.'
        rollback
        return 1
    }

    commit

    echo
    ok "WMM $WMM_VERSION installed successfully."
    info "Installation path: $APP_DIR"

    # Indicación final propia de cada escritorio.
    case "$DESKTOP" in
        cinnamon) echo "Enable 'WMM Manager' from Menu > Graphics or from Cinnamon Applets" ;;
        gnome)    echo "Restart session and launch Aplications > WMM Manager icon or enable 'WMM Manager' in GNOME Extensions." ;;
        kde)
            # Plasma >= 6.6.6 corrige KDE bug 515234, que hacía inseguro
            # reiniciar plasmashell en determinadas topologías multimonitor.
            # En versiones anteriores se conserva deliberadamente el cierre
            # de sesión como frontera segura.
            if [ "$(version_cmp "$PLASMA_VERSION" "6.6.6")" -ge 0 ]; then
                info "Restarting Plasma Shell..."

                if systemctl --user restart plasma-plasmashell.service; then
                    ok "Plasma Shell restarted."
                    echo "Launch 'WMM Manager' from Menu > Graphics."
                else
                    warn "Plasma Shell could not be restarted automatically."
                    echo "Restart session and launch 'WMM Manager' from Menu > Graphics."
                fi
            else
                echo "Restart session and launch 'WMM Manager' from Menu > Graphics."
            fi
            ;;
        mate)     echo "Add 'WMM Manager' to the MATE panel or use Menu > Graphics." ;;
        xfce)     echo "Launch 'WMM Manager' from Menu > Graphics. It will start automatically on future sessions." ;;
    esac
}

# ----------------------------------------------------------
# FUNCIÓN: Ejecutar Upgrade / Reinstall / Downgrade
# Preserva datos, sustituye el árbol de forma limpia, actualiza integración
# y relanza siempre el frontend correspondiente.
# ----------------------------------------------------------
run_replace() {
    confirm_replace || return 0
    prepare_action || return 1
    evaluate_gnome_reload_policy

    [ "$DESKTOP" != mate ] || sudo -v || {
        fail 'Administrator permission is required for the MATE descriptor.'
        return 1
    }

    prepare_staging 1 || {
        [ -n "$STAGING" ] && rm -rf "$STAGING"
        [ -n "$DATA_STAGING" ] && rm -rf "$DATA_STAGING"
        fail 'Could not prepare staging.'
        return 1
    }

    unload_frontend || {
        [ -n "$STAGING" ] && rm -rf "$STAGING"
        [ -n "$DATA_STAGING" ] && rm -rf "$DATA_STAGING"
        fail 'Could not unload the current frontend safely.'
        return 1
    }

    stop_wmm || {
        [ -n "$STAGING" ] && rm -rf "$STAGING"
        [ -n "$DATA_STAGING" ] && rm -rf "$DATA_STAGING"
        recover_runtime_after_abort
        return 1
    }

    activate_staging || {
        [ -n "$STAGING" ] && rm -rf "$STAGING"
        [ -n "$DATA_STAGING" ] && rm -rf "$DATA_STAGING"
        recover_runtime_after_abort
        return 1
    }

    backup_external_resources || {
        fail 'Could not back up the existing desktop integration resources.'
        rollback
        return 1
    }

    install_external || {
        fail 'Desktop integration failed.'
        rollback
        return 1
    }

    if [ "$DESKTOP" = cinnamon ]; then
        # En Cinnamon, install_external() ya ha construido y validado el
        # frontend antes del hachazo. Un fallo posterior de carga pertenece
        # al runtime y no debe revertir una instalación ya completada.
        commit
        relaunch_frontend || true

    elif [ "$DESKTOP" = gnome ] \
        && [ "$GNOME_SESSION_RESTART_REQUIRED" -eq 1 ]; then

        # GNOME mantiene el módulo JS anterior en memoria durante la sesión.
        # La instalación queda confirmada en disco y el frontend nuevo será
        # cargado desde cero cuando el usuario inicie una sesión nueva.
        commit

    else
        if ! relaunch_frontend; then
            fail 'The new WMM frontend could not be relaunched.'
            rollback
            return 1
        fi

        commit
    fi

    echo

    case "$MODE" in
        upgrade)
            ok "WMM upgraded successfully to $WMM_VERSION."
            ;;
        repair)
            ok "WMM $WMM_VERSION repaired/reinstalled successfully."
            ;;
        downgrade)
            ok "WMM downgraded successfully to $WMM_VERSION."
            ;;
    esac

    if [ "$DESKTOP" = gnome ] \
        && [ "$GNOME_SESSION_RESTART_REQUIRED" -eq 1 ]; then

        warn 'GNOME requires a new session to activate the updated WMM extension.'
        warn 'Sign out and back in to complete the update.'
    fi

    info "Installation path: $APP_DIR"
}

# ----------------------------------------------------------
# FUNCIÓN PRINCIPAL
# Detecta la instalación una vez, muestra el gestor y deriva la opción
# elegida al flujo Install, Replace, Uninstall o Exit.
# ----------------------------------------------------------
main() {
    detect_installation

    case "${1:-}" in

        --upgrade)
            [ "$WMM_PRESENT" -eq 1 ] || { fail 'WMM is not installed.'; return 1; }
            [ -n "$INSTALLED_VERSION" ] || { fail 'Installed WMM version is unavailable.'; return 1; }

            if [ "$(version_cmp "$INSTALLED_VERSION" "$WMM_VERSION")" != "-1" ]; then
                fail "Package WMM $WMM_VERSION is not newer than installed WMM $INSTALLED_VERSION."
                return 1
            fi

            FORCED_MODE=upgrade
            ACTION=replace
            ;;

        --repair)
            [ "$WMM_PRESENT" -eq 1 ] || { fail 'WMM is not installed.'; return 1; }
            FORCED_MODE=repair
            ACTION=replace
            ;;

        "")
            show_menu
            ;;

        *)
            fail "Unknown option: $1"
            return 2
            ;;
    esac

    case "$ACTION" in
        install) run_install ;;
        replace) run_replace ;;
        uninstall) [ -f "$UNINSTALLER" ] || { fail "Uninstaller not found: $UNINSTALLER"; return 1; }; exec bash "$UNINSTALLER" --managed ;;
        exit) return 0 ;;
    esac
}
main "$@"
