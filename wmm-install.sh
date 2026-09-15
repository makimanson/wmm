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
CACHE_BASE="${XDG_CACHE_HOME:-$HOME/.cache}"
SYSTEM_DATA_DIRS="${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"
CACHE_DIR="$CACHE_BASE/wmm"
DBUS_DIR="$DATA_BASE/dbus-1/services"
APPLICATIONS_DIR="$DATA_BASE/applications"
AUTOSTART_DIR="$HOME/.config/autostart"

LEGACY_APP_DIR=""
PLASMOID_DIR=""
AUTOSTART=""
MATE_APPLETS_DIR=""
MATE_DESCRIPTOR=""
MATE_SERVICE=""
INSTALL_MANAGER_SERVICE=""
DEBUG_LOG_VIEWER_SERVICE=""

# Resolver las rutas propias de cada escritorio.
case "$DESKTOP" in
    cinnamon)
        APP_DOMAIN='wmm@maki'
        APP_DIR="$DATA_BASE/cinnamon/applets/$APP_DOMAIN"
        LEGACY_APP_DIR="$DATA_BASE/cinnamon/applets/wmm-applet@maki"
        LAUNCHER="$APPLICATIONS_DIR/org.maki.wmm.cinnamon.desktop"
        ;;
    gnome)
        APP_DOMAIN='wmm@maki'
        APP_DIR="$DATA_BASE/gnome-shell/extensions/$APP_DOMAIN"
        LAUNCHER="$APPLICATIONS_DIR/org.maki.wmm.gnome.desktop"
        ;;
    kde)
        APP_DOMAIN='org.maki.wmm'
        APP_DIR="$DATA_BASE/plasma/$APP_DOMAIN"
        PLASMOID_DIR="$DATA_BASE/plasma/plasmoids/$APP_DOMAIN"
        LAUNCHER="$APPLICATIONS_DIR/org.maki.wmm.desktop"
        AUTOSTART="$AUTOSTART_DIR/org.maki.wmm.desktop"
        INSTALL_MANAGER_SERVICE="$DBUS_DIR/org.maki.wmm.InstallManager.service"
        DEBUG_LOG_VIEWER_SERVICE="$DBUS_DIR/org.maki.wmm.DebugLogViewer.service"
        ;;
    mate)
        APP_DOMAIN='wmm@maki'
        APP_DIR="$DATA_BASE/$APP_DOMAIN"
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
esac
DBUS_SERVICE="$DBUS_DIR/$APP_DOMAIN.service"

# ----------------------------------------------------------
# Installed state and version
# about.json -> metadata.json fallback
# ----------------------------------------------------------
WMM_PRESENT=0
INSTALLED_ROOT=""
INSTALLED_VERSION=""
INSTALLED_VERSION_SOURCE=""
# Lee una cadena simple de un JSON de metadatos sin añadir dependencias externas.
json_value() { [ -f "$1" ] && sed -n "s/.*\"$2\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p" "$1" | head -n1; }
# Valida el formato de versión que usa WMM: X.Y.Z.
valid_version() { [[ "${1:-}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; }
# Comprueba que un servicio instalado pertenece realmente a la ruta WMM esperada.
service_owned_by() { [ -f "$1" ] && grep -Fq "$2" "$1"; }

# ----------------------------------------------------------
# FUNCIÓN: Detectar instalación WMM existente
# Revisa únicamente los recursos propios del escritorio activo.
# Guarda el resultado y la versión para reutilizarlos durante todo el flujo.
# ----------------------------------------------------------
detect_installation() {
    local metadata="" v=""
    case "$DESKTOP" in
        cinnamon)
            if [ -d "$APP_DIR" ]; then
                INSTALLED_ROOT="$APP_DIR"
            elif [ -d "$LEGACY_APP_DIR" ]; then
                INSTALLED_ROOT="$LEGACY_APP_DIR"
            fi

            [ -n "$INSTALLED_ROOT" ] && WMM_PRESENT=1
            [ -f "$LAUNCHER" ] && WMM_PRESENT=1

            if service_owned_by "$DBUS_SERVICE" "$APP_DIR" \
                || service_owned_by "$DBUS_SERVICE" "$LEGACY_APP_DIR"; then
                WMM_PRESENT=1
            fi

            [ -n "$INSTALLED_ROOT" ] && metadata="$INSTALLED_ROOT/metadata.json"
            ;;
        gnome)
            [ -d "$APP_DIR" ] && { WMM_PRESENT=1; INSTALLED_ROOT="$APP_DIR"; }
            [ -f "$LAUNCHER" ] && WMM_PRESENT=1
            service_owned_by "$DBUS_SERVICE" "$APP_DIR" && WMM_PRESENT=1
            metadata="$APP_DIR/metadata.json"
            ;;
        kde)
            [ -d "$APP_DIR" ] && { WMM_PRESENT=1; INSTALLED_ROOT="$APP_DIR"; }
            { [ -d "$PLASMOID_DIR" ] || [ -f "$LAUNCHER" ] || [ -f "$AUTOSTART" ]; } && WMM_PRESENT=1
            service_owned_by "$DBUS_SERVICE" "$APP_DIR" && WMM_PRESENT=1
            metadata="$PLASMOID_DIR/metadata.json"
            ;;
        mate)
            [ -d "$APP_DIR" ] && { WMM_PRESENT=1; INSTALLED_ROOT="$APP_DIR"; }
            { [ -f "$LAUNCHER" ] || [ -f "$MATE_SERVICE" ] || [ -f "$MATE_DESCRIPTOR" ]; } && WMM_PRESENT=1
            service_owned_by "$DBUS_SERVICE" "$APP_DIR" && WMM_PRESENT=1
            ;;
    esac
    [ "$WMM_PRESENT" -eq 1 ] || return 0

    # Autoridad de versión: about.json.
    [ -n "$INSTALLED_ROOT" ]         && v="$(json_value "$INSTALLED_ROOT/data/about.json" version 2>/dev/null || true)"

    if valid_version "$v"; then
        INSTALLED_VERSION="$v"
        INSTALLED_VERSION_SOURCE=about.json
        return 0
    fi

    # Fallback de compatibilidad: metadata del frontend.

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
# group|label|test command|APT package name
# ----------------------------------------------------------
DEPS=()
# Registra una dependencia como grupo | nombre | prueba | paquete base.
add_dep() { DEPS+=("$1|$2|$3|$4"); }
# ----------------------------------------------------------
# FUNCIÓN: Construir lista de dependencias
# Añade las dependencias comunes y sólo las específicas del escritorio
# o gestores de archivos realmente presentes en el sistema.
# ----------------------------------------------------------
build_deps() {
    DEPS=()
    add_dep GTK 'PyGObject (GTK bindings)' "python3 -c 'import gi'" python3-gi
    add_dep GTK 'GTK 3.0 Introspection' "python3 -c 'import gi; gi.require_version(\"Gtk\",\"3.0\"); from gi.repository import Gtk'" gir1.2-gtk-3.0
    add_dep GTK 'GLib 2.0 Introspection' "python3 -c 'import gi; gi.require_version(\"GLib\",\"2.0\"); from gi.repository import GLib'" gir1.2-glib-2.0
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

    # Dependencias opcionales de gestores de archivos instalados.
    if command -v nautilus >/dev/null 2>&1; then
        add_dep 'File manager' \
            'Nautilus Python' \
            "python3 -c 'import gi; from gi.repository import Nautilus'" \
            python3-nautilus
    fi

    if command -v caja >/dev/null 2>&1; then
        add_dep 'File manager' \
            'Caja Python' \
            "python3 -c 'import gi; gi.require_version(\"Caja\",\"2.0\"); from gi.repository import Caja'" \
            python3-caja
    fi
    add_dep WMM 'Python 3' 'python3 --version' python3
    add_dep WMM 'VTE 2.91 Introspection' \
    "python3 -c 'import gi; gi.require_version(\"Vte\",\"2.91\"); from gi.repository import Vte'" \
    gir1.2-vte-2.91
    add_dep WMM 'Pillow (Python Imaging)' "python3 -c 'from PIL import Image'" python3-pillow
    add_dep WMM 'NumPy (Python scientific computing)' "python3 -c 'import numpy'" python3-numpy
    add_dep WMM 'Libnotify (notifications)' 'command -v notify-send' libnotify-bin
    add_dep WMM GetText 'command -v xgettext' gettext
    add_dep WMM 'Zenity (dialogs)' 'command -v zenity' zenity
    add_dep WMM 'D-Bus client' 'command -v dbus-send' dbus
}

# Ejecuta la prueba asociada a una dependencia.
dep_ok() { eval "$1" >/dev/null 2>&1; }
# ----------------------------------------------------------
# FUNCIÓN: Mostrar checklist de dependencias
# Ejecuta las pruebas definidas y devuelve cuántas dependencias faltan.
# ----------------------------------------------------------
print_deps() {
    local spec group name test pkg current='' missing=0
    echo
    for spec in "${DEPS[@]}"; do
        IFS='|' read -r group name test pkg <<< "$spec"
        [ "$group" = "$current" ] || { current="$group"; printf "${GREEN}[%s dependencies]${NC}\n" "$group"; }
        dep_ok "$test" && printf "  ${GREEN}[✔]${NC} %s\n" "$name" || { printf "  ${RED}[✘]${NC} %s\n" "$name"; ((missing++)); }
    done
    return "$missing"
}

# ----------------------------------------------------------
# FUNCIÓN: Adaptar nombres de paquetes
# Traduce el nombre base del paquete cuando DNF o Pacman usan otro nombre.
# ----------------------------------------------------------
pkg_map() {
    case "$1:$2" in
        dnf:python3-gi)                  echo python3-gobject ;;
        dnf:gir1.2-gtk-3.0)             echo gtk3 ;;
        dnf:gir1.2-glib-2.0)            echo glib2 ;;
        dnf:gir1.2-matepanelapplet-4.0) echo mate-panel-libs ;;
        dnf:python3-nautilus)            echo nautilus-python ;;
        dnf:gir1.2-vte-2.91)             echo vte291 ;;

        pacman:python3)                   echo python ;;
        pacman:python3-pillow)            echo python-pillow ;;
        pacman:python3-numpy)             echo python-numpy ;;
        pacman:libnotify-bin)             echo libnotify ;;
        pacman:gnome-shell-extension-prefs) echo gnome-shell-extensions ;;
        pacman:python3-gi)                echo python-gobject ;;
        pacman:gir1.2-gtk-3.0)           echo gtk3 ;;
        pacman:gir1.2-glib-2.0)          echo glib2 ;;
        pacman:gir1.2-matepanelapplet-4.0) echo mate-panel ;;
        pacman:python3-nautilus)          echo nautilus-python ;;
        pacman:python3-caja)              echo python-caja ;;
        pacman:gir1.2-vte-2.91)          echo vte3 ;;

        *) echo "$2" ;;
    esac
}

# ----------------------------------------------------------
# FUNCIÓN: Verificar / instalar dependencias
# Comprueba una vez; si instala paquetes, repite la comprobación porque
# esa acción acaba de cambiar el estado del sistema.
# ----------------------------------------------------------
ensure_deps() {
    local answer manager spec group name test pkg mapped; local -a missing=(); local -A seen=()
    build_deps; print_deps && { ok 'All dependencies are available.'; return 0; }
    echo; read -r -p 'Install the missing dependencies? (y/n): ' answer || answer=n
    [[ "$answer" =~ ^[Yy]$ ]] || { warn 'Dependency installation cancelled.'; return 1; }
    # Seleccionar el gestor de paquetes disponible.
    if command -v apt >/dev/null; then
        manager=apt
    elif command -v dnf >/dev/null; then
        manager=dnf
    elif command -v pacman >/dev/null; then
        manager=pacman
    else
        fail 'No supported package manager found.'
        return 1
    fi
    for spec in "${DEPS[@]}"; do
        IFS='|' read -r group name test pkg <<< "$spec"
        dep_ok "$test" && continue
        mapped="$(pkg_map "$manager" "$pkg")"
        [ -n "${seen[$mapped]:-}" ] || { seen[$mapped]=1; missing+=("$mapped"); }
    done
    info "Installing: ${missing[*]}"
    # Instalar con el gestor detectado.
    case "$manager" in
        apt)    sudo apt install -y "${missing[@]}" ;;
        dnf)    sudo dnf install -y "${missing[@]}" ;;
        pacman) sudo pacman -Sy --noconfirm "${missing[@]}" ;;
    esac || return 1

    info 'Verifying dependencies after package installation...'
    print_deps && { ok 'Dependencies verified.'; return 0; }
    fail 'Some dependencies are still missing.'; return 1
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
        data
        help
        wmm_platform/shell/po
        python/main.py
        data/about.json
        wmm_platform/shell/linux/org.maki.wmm.service
    )

    # Añadir los recursos obligatorios del escritorio actual.
    case "$DESKTOP" in
        cinnamon)
            req+=(
                wmm_platform/shell/cinnamon/metadata.cinnamon.json
                wmm_platform/shell/cinnamon/applet.cinnamon.js
                wmm_platform/shell/cinnamon/org.maki.wmm.cinnamon.desktop
            )
            ;;

        gnome)
            req+=(
                wmm_platform/shell/gnome/metadata.gnome.json
                wmm_platform/shell/gnome/extension.gnome.js
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
                wmm_platform/shell/mate/org.maki.wmm.mate-panel-applet
                wmm_platform/shell/mate/org.mate.panel.applet.WMMAppletFactory.service
                wmm_platform/shell/mate/org.maki.wmm.mate.desktop
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
        -e "s|@APP_DIR@|$APP_DIR|g" \
        -e "s|@PYTHON3@|$PYTHON3_BIN|g" \
        -e "s|@DBUS_SEND@|$DBUS_SEND_BIN|g" \
        -e "s|@VERSION@|$WMM_VERSION|g" \
        -e "s|@RELEASE_YEAR@|$WMM_RELEASE_YEAR|g" \
        "$1" > "$2"
}

PRESERVE=(
    settings.json
    sources.json
    monitor_vault.json
    bookmarks.json
    bookmarks_single_list.json
    history.json
    history_vault.json
    history_presets.json
    image_cache.json
    scan_index.json
)

STAGING=''
OLD_APP=''
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
# Copia una versión limpia del paquete y, en reemplazos, recupera sólo
# los datos persistentes del usuario antes de regenerar metadatos/config.
# ----------------------------------------------------------
prepare_staging() {
    local preserve="$1" parent f
    parent="$(dirname "$APP_DIR")"
    mkdir -p "$parent" || return 1
    STAGING="$(mktemp -d "$parent/.wmm-install-new.XXXXXX")" || return 1

    info 'Preparing clean staging tree...'

    # Copiar el árbol WMM y los documentos únicos de la raíz del repositorio.
    cp -a "$PROJECT_DIR/." "$STAGING/" || return 1
    cp -f "$README_FILE" "$STAGING/README.md" || return 1
    cp -f "$CHANGELOG_FILE" "$STAGING/CHANGELOG.md" || return 1
    cp -f "$LICENSE_FILE" "$STAGING/LICENSE" || return 1

    # En Upgrade/Reinstall, recuperar únicamente los datos persistentes.
    if [ "$preserve" -eq 1 ] && [ -n "$INSTALLED_ROOT" ]; then
        for f in "${PRESERVE[@]}"; do
            if [ -f "$INSTALLED_ROOT/data/$f" ]; then
                cp -p "$INSTALLED_ROOT/data/$f" "$STAGING/data/$f" || return 1
            fi
        done
    fi
    cat > "$STAGING/data/settings_core.ini" <<CFG
# WMM Platform Configuration
# Generated by wmm-install.sh on $(date)
platform=$PLATFORM
desktop=$DESKTOP
app_domain=$APP_DOMAIN
version=$WMM_VERSION
data_base=$DATA_BASE
cache_base=$CACHE_BASE
graphics_engine=$GRAPHICS_ENGINE
CFG
    template "$PROJECT_DIR/data/about.json" "$STAGING/data/about.json" || return 1

    # Preparar dentro del staging los archivos propios del frontend.
    case "$DESKTOP" in
        cinnamon)
            template \
                "$PROJECT_DIR/wmm_platform/shell/cinnamon/metadata.cinnamon.json" \
                "$STAGING/metadata.json" \
                || return 1

            cp -f \
                "$PROJECT_DIR/wmm_platform/shell/cinnamon/applet.cinnamon.js" \
                "$STAGING/applet.js" \
                || return 1
            ;;

        gnome)
            template \
                "$PROJECT_DIR/wmm_platform/shell/gnome/metadata.gnome.json" \
                "$STAGING/metadata.json" \
                || return 1

            cp -f \
                "$PROJECT_DIR/wmm_platform/shell/gnome/extension.gnome.js" \
                "$STAGING/extension.js" \
                || return 1
            ;;

        mate)
            cp -f \
                "$PROJECT_DIR/wmm_platform/shell/mate/mate-applet.py" \
                "$STAGING/mate-applet.py" \
                || return 1

            cp -f \
                "$PROJECT_DIR/wmm_platform/shell/mate/mate-launcher.py" \
                "$STAGING/mate-launcher.py" \
                || return 1
            ;;

        kde)
            # KDE instala el frontend como recurso externo.
            ;;
    esac

    # Limpiar artefactos de desarrollo antes de activar el staging.
    find "$STAGING" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
    find "$STAGING" -type f -name '*.pyc' -delete 2>/dev/null
    find "$STAGING" -type f -exec chmod -x {} \;

    # Instalar las herramientas locales y crear el paquete de reparación.
    prepare_installer_payload || return 1

    [ -f "$STAGING/python/main.py" ] \
        && [ -f "$STAGING/data/settings_core.ini" ] \
        && [ -f "$STAGING/data/about.json" ] \
        && [ -f "$STAGING/README.md" ] \
        && [ -f "$STAGING/CHANGELOG.md" ] \
        && [ -f "$STAGING/LICENSE" ] \
        && [ -f "$STAGING/$INSTALLER_REL_DIR/wmm-install.sh" ] \
        && [ -f "$STAGING/$INSTALLER_REL_DIR/wmm-uninstall.sh" ] \
        && [ -s "$STAGING/$INSTALLER_REL_DIR/wmm-repair.zip" ] \
        || return 1

    # Validar los archivos que acabamos de generar/copiar por escritorio.
    case "$DESKTOP" in
        cinnamon)
            [ -f "$STAGING/metadata.json" ] || return 1
            [ -f "$STAGING/applet.js" ] || return 1
            ;;

        gnome)
            [ -f "$STAGING/metadata.json" ] || return 1
            [ -f "$STAGING/extension.js" ] || return 1
            ;;

        mate)
            [ -f "$STAGING/mate-applet.py" ] || return 1
            [ -f "$STAGING/mate-launcher.py" ] || return 1
            ;;

        kde)
            # KDE no añade archivos de frontend al APP_DIR.
            # El plasmoide se instala como recurso externo.
            ;;
    esac
    ok 'Clean staging tree prepared.'
}

# ----------------------------------------------------------
# FUNCIÓN: Activar staging
# Aparta temporalmente la instalación anterior y coloca el árbol nuevo
# en APP_DIR. La copia anterior se conserva hasta el commit final.
# ----------------------------------------------------------
activate_staging() {
    local parent old
    parent="$(dirname "$APP_DIR")"

    # Apartar la instalación viva sin destruirla.
    if [ -d "$APP_DIR" ]; then
        old="$(mktemp -d "$parent/.wmm-install-old.XXXXXX")" || return 1
        rmdir "$old" || return 1
        mv "$APP_DIR" "$old" || return 1
        OLD_APP="$old"
    fi

    # Activar el árbol limpio preparado.
    if ! mv "$STAGING" "$APP_DIR"; then
        [ -n "$OLD_APP" ] && mv "$OLD_APP" "$APP_DIR" || true
        OLD_APP=''
        return 1
    fi

    STAGING=''
    ok 'Clean WMM app tree activated.'
}

# ----------------------------------------------------------
# Replacement lifecycle
# ----------------------------------------------------------
# Comprueba sin activar el servicio si org.maki.wmm tiene owner en la sesión.
dbus_owner() {
    "$DBUS_SEND_BIN" \
        --session \
        --print-reply \
        --dest=org.freedesktop.DBus \
        /org/freedesktop/DBus \
        org.freedesktop.DBus.NameHasOwner \
        string:org.maki.wmm \
        2>/dev/null | grep -q 'boolean true'
}

# ----------------------------------------------------------
# FUNCIÓN: Preparar el frontend para un reemplazo
# Sólo realiza las acciones previas necesarias para el escritorio actual.
# ----------------------------------------------------------
unload_frontend() {
    # Sólo GNOME y MATE necesitan una preparación explícita antes del swap.
    case "$DESKTOP" in
        gnome)
            if command -v gnome-extensions >/dev/null 2>&1; then
                gnome-extensions disable "$APP_DOMAIN" >/dev/null 2>&1 || true
            fi
            ;;

        mate)
            MATE_APPLET_STATE="$(
                "$PYTHON3_BIN" "$PROJECT_DIR/wmm_platform/shell/mate/mate-launcher.py" --unload
            )" || return 1
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
    local root process attempts=20 running; local -a roots=("$APP_DIR")
    [ -n "$LEGACY_APP_DIR" ] && [ -d "$LEGACY_APP_DIR" ] && roots+=("$LEGACY_APP_DIR")
    info 'Stopping current WMM...'
    # Pedir cierre coordinado sólo si el servicio ya tiene owner.
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
    # Cerrar cualquier engine/panel que siga asociado al árbol actual.
    for root in "${roots[@]}"; do
        for process in "$root/python/main.py" "$root/python/panel.py"; do
            if pgrep -f -- "$process" >/dev/null 2>&1; then
                pkill -TERM -f -- "$process" >/dev/null 2>&1 || true
            fi
        done
    done

    # Esperar sólo a que los procesos que usan el árbol hayan desaparecido.
    while ((attempts-- > 0)); do
        running=0

        for root in "${roots[@]}"; do
            if pgrep -f -- "$root/python/main.py" >/dev/null 2>&1 || pgrep -f -- "$root/python/panel.py" >/dev/null 2>&1; then
                running=1
                break
            fi
        done

        if [ "$running" -eq 0 ]; then
            ok 'WMM stopped.'
            return 0
        fi

        sleep .1
    done

    fail 'WMM could not be stopped safely.'
    return 1
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

    # KDE mantiene además su propia caché de servicios.
    if [ "$DESKTOP" = kde ] && command -v kbuildsycoca6 >/dev/null 2>&1; then
        kbuildsycoca6 >/dev/null 2>&1 || true
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
        kde)
            restore_external_file "$EXTERNAL_BACKUP/autostart.desktop" "$AUTOSTART" || return 1
            restore_external_file "$EXTERNAL_BACKUP/install-manager.service" "$INSTALL_MANAGER_SERVICE" || return 1
            restore_external_file "$EXTERNAL_BACKUP/debug-log-viewer.service" "$DEBUG_LOG_VIEWER_SERVICE" || return 1
            ;;

        mate)
            restore_external_file "$EXTERNAL_BACKUP/mate.service" "$MATE_SERVICE" || return 1

            if [ -f "$EXTERNAL_BACKUP/mate-descriptor" ]; then
                sudo install -m 0644 "$EXTERNAL_BACKUP/mate-descriptor" "$MATE_DESCRIPTOR" || return 1
            else
                sudo rm -f "$MATE_DESCRIPTOR" || return 1
            fi
            ;;
    esac
}

discard_external_backup() {
    [ -n "$EXTERNAL_BACKUP" ] && [ -d "$EXTERNAL_BACKUP" ] && rm -rf "$EXTERNAL_BACKUP"
    EXTERNAL_BACKUP=''
}

# ----------------------------------------------------------
# FUNCIÓN: Instalar integración del escritorio
# Instala servicio D-Bus, launcher y los recursos específicos de Cinnamon,
# GNOME, KDE o MATE fuera de APP_DIR.
# ----------------------------------------------------------
install_external() {
    local parent new old

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
            template \
                "$PROJECT_DIR/wmm_platform/shell/cinnamon/org.maki.wmm.cinnamon.desktop" \
                "$LAUNCHER" \
                || return 1
            ;;

        gnome)
            template \
                "$PROJECT_DIR/wmm_platform/shell/gnome/org.maki.wmm.gnome.desktop" \
                "$LAUNCHER" \
                || return 1
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

            # Actualizar el registro de paquetes de Plasma si la herramienta existe.
            if command -v kpackagetool6 >/dev/null 2>&1; then
                if [ -n "$OLD_PLASMOID" ]; then
                    kpackagetool6 -t Plasma/Applet --upgrade "$PLASMOID_DIR" >/dev/null 2>&1 \
                        || kpackagetool6 -t Plasma/Applet --install "$PLASMOID_DIR" >/dev/null 2>&1 \
                        || true
                else
                    kpackagetool6 -t Plasma/Applet --install "$PLASMOID_DIR" >/dev/null 2>&1 || true
                fi
            fi
            ;;
    esac

    refresh
    ok 'Desktop integration resources installed.'
}

# ----------------------------------------------------------
# FUNCIÓN: Relanzar frontend
# Tras Upgrade/Reinstall vuelve a cargar applet/extensión/plasmoide.
# El frontend es quien pone de nuevo en marcha el engine.
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
            command -v gnome-extensions >/dev/null 2>&1 && gnome-extensions enable "$APP_DOMAIN" >/dev/null 2>&1 \
                && { ok 'GNOME extension re-enabled.'; return 0; }
            ;;
        kde)
            command -v kquitapp6 >/dev/null 2>&1 || {
                warn 'kquitapp6 unavailable; restart Plasma Shell manually.'
                return 1
            }

            kquitapp6 plasmashell >/dev/null 2>&1 || true
            sleep .3
            nohup plasmashell --replace >/dev/null 2>&1 &

            ok 'Plasma Shell frontend relaunched.'
            return 0
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
                "$PYTHON3_BIN" "$APP_DIR/mate-launcher.py" >/dev/null 2>&1 && {
                    ok 'MATE frontend relaunched.'
                    return 0
                }
            fi
            ;;
    esac
    warn 'Frontend reload could not be completed automatically.'; return 1
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
    rm -rf "$APP_DIR" 2>/dev/null || true

    if [ -n "$OLD_APP" ] && [ -d "$OLD_APP" ]; then
        mv "$OLD_APP" "$APP_DIR" || {
            fail "CRITICAL: previous installation remains at $OLD_APP"
            return 1
        }
        OLD_APP=''
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
        rm -f "$DBUS_SERVICE" "$LAUNCHER" 2>/dev/null || true

        if [ "$DESKTOP" = kde ]; then
            rm -f \
                "$AUTOSTART" \
                "$INSTALL_MANAGER_SERVICE" \
                "$DEBUG_LOG_VIEWER_SERVICE" \
                2>/dev/null || true

            rm -rf "$PLASMOID_DIR" 2>/dev/null || true
        fi

        if [ "$DESKTOP" = mate ]; then
            rm -f "$MATE_SERVICE" 2>/dev/null || true
            sudo rm -f "$MATE_DESCRIPTOR" >/dev/null 2>&1 || true
        fi

        refresh
    else
        restore_external_resources || external_restore_failed=1
        refresh
        relaunch_frontend || true
    fi

    if [ "$external_restore_failed" -ne 0 ]; then
        fail "External resource rollback is incomplete. Backup preserved at: $EXTERNAL_BACKUP"
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
    [ -n "$OLD_PLASMOID" ] && [ -d "$OLD_PLASMOID" ] && rm -rf "$OLD_PLASMOID"

    [ -n "$LEGACY_APP_DIR" ] \
        && [ "$LEGACY_APP_DIR" != "$APP_DIR" ] \
        && [ -d "$LEGACY_APP_DIR" ] \
        && rm -rf "$LEGACY_APP_DIR"

    discard_external_backup

    OLD_APP=''
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
        fail 'Could not prepare staging.'
        return 1
    }

    activate_staging || return 1

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
        kde)      echo 'Restart session and add the WMM plasmoid if it is NOT already present in taskbar.' ;;
        mate)     echo "Add 'WMM Manager' to the MATE panel or use Menu > Graphics." ;;
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

    [ "$DESKTOP" != mate ] || sudo -v || {
        fail 'Administrator permission is required for the MATE descriptor.'
        return 1
    }

    prepare_staging 1 || {
        [ -n "$STAGING" ] && rm -rf "$STAGING"
        fail 'Could not prepare staging.'
        return 1
    }

    unload_frontend || {
        [ -n "$STAGING" ] && rm -rf "$STAGING"
        fail 'Could not unload the current frontend safely.'
        return 1
    }

    activate_staging || {
        relaunch_frontend || true
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

    if ! relaunch_frontend; then
        fail 'The new WMM frontend could not be relaunched.'
        rollback
        return 1
    fi

    commit
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
