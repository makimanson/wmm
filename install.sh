#!/bin/bash
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

# ==========================================================
# WMM - Wallpaper Multi-Monitor Manager
# Interactive installer and dependency checker
# ==========================================================

# Mantener la terminal abierta al finalizar (éxito o error)
trap 'echo ""; read -p "Press Enter to exit..." dummy' EXIT

# Colores para el checklist
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No color

# ----------------------------------------------------------
# FUNCIÓN: Mostrar mensaje de progreso en la misma línea
# Uso: progress_msg "Mensaje"
# ----------------------------------------------------------
progress_msg() {
    local msg="$1"
    local cols=$(tput cols 2>/dev/null || echo 80)
    # Si el mensaje es más largo que el ancho de la terminal, se trunca
    if [ ${#msg} -gt $cols ]; then
        msg="${msg:0:$((cols-1))}"
    fi
    printf "\r\033[K%s" "$msg"
    sleep 0.1
}
# ----------------------------------------------------------
# OBTENER RUTAS DEL SCRIPT
# ----------------------------------------------------------
SCRIPT_DIR="$(dirname "$(realpath "$0")")"
PROJECT_DIR="$SCRIPT_DIR/wmm"

# ----------------------------------------------------------
# 1. DETECCIÓN DE PLATAFORMA
# ----------------------------------------------------------
PLATFORM=$(uname -s | tr '[:upper:]' '[:lower:]')
if [ "$PLATFORM" != "linux" ]; then
    echo -e "${RED}ERROR: Unsupported platform: $PLATFORM${NC}"
    exit 1
fi

# ----------------------------------------------------------
# 2. DETECCIÓN DEL ESCRITORIO
# ----------------------------------------------------------
DESKTOP="${XDG_CURRENT_DESKTOP:-${DESKTOP_SESSION:-unknown}}"
DESKTOP=$(echo "$DESKTOP" | tr '[:upper:]' '[:lower:]')

# Normalizar variantes conocidas (X-Cinnamon -> cinnamon, ubuntu:GNOME -> gnome, etc.)
case "$DESKTOP" in
    x-cinnamon|cinnamon2d) DESKTOP="cinnamon" ;;
    ubuntu*|gnome*)        DESKTOP="gnome" ;;
    kde*)                  DESKTOP="kde" ;;
    plasma*)               DESKTOP="kde" ;;
esac

# Verificar que el escritorio está realmente instalado
case "$DESKTOP" in
    cinnamon)
        command -v cinnamon >/dev/null 2>&1 || DESKTOP="unknown"
        ;;
    gnome)
        command -v gnome-shell >/dev/null 2>&1 || DESKTOP="unknown"
        ;;
    kde)
        if ! command -v plasmashell >/dev/null 2>&1; then
            DESKTOP="unknown"
        else
            PLASMA_VERSION=$(plasmashell --version 2>/dev/null | awk '{print $2}')
            PLASMA_MAJOR=${PLASMA_VERSION%%.*}

            if [ -z "$PLASMA_MAJOR" ] || [ "$PLASMA_MAJOR" -lt 6 ] 2>/dev/null; then
                echo -e "${RED}ERROR: WMM requires KDE Plasma 6 or newer. Detected: ${PLASMA_VERSION:-unknown}${NC}"
                exit 1
            fi
        fi
        ;;
    *)
        DESKTOP="unknown"
        ;;
esac

if [ "$DESKTOP" = "unknown" ]; then
    echo -e "${RED}ERROR: Could not detect a supported desktop environment.${NC}"
    exit 1
fi


# ----------------------------------------------------------
# 2b. DETECCIÓN DEL MOTOR GRÁFICO
# ----------------------------------------------------------
if [ -n "$WAYLAND_DISPLAY" ]; then
    GRAPHICS_ENGINE="wayland"
elif [ "$XDG_SESSION_TYPE" = "wayland" ]; then
    GRAPHICS_ENGINE="wayland"
elif [ "$XDG_SESSION_TYPE" = "x11" ]; then
    GRAPHICS_ENGINE="x11"
else
    GRAPHICS_ENGINE="x11"  # Fallback seguro
fi
echo -e "${GREEN}Graphics Engine: $GRAPHICS_ENGINE${NC}"

# ----------------------------------------------------------
# 3. RUTAS XDG (BASE DE DATOS Y CACHÉ)
# ----------------------------------------------------------
DATA_BASE="${XDG_DATA_HOME:-$HOME/.local/share}"
CACHE_BASE="${XDG_CACHE_HOME:-$HOME/.cache}"

# ----------------------------------------------------------
# 4. DEFINIR DOMINIO Y RUTAS DE INSTALACIÓN SEGÚN ESCRITORIO
# ----------------------------------------------------------
case "$DESKTOP" in
    cinnamon)
        APP_DOMAIN="wmm@maki"
        APP_DIR="$DATA_BASE/cinnamon/applets/$APP_DOMAIN"
        ;;
    gnome)
        APP_DOMAIN="wmm@maki"
        APP_DIR="$DATA_BASE/gnome-shell/extensions/$APP_DOMAIN"
        ;;
    kde)
        APP_DOMAIN="org.maki.wmm"
        APP_DIR="$DATA_BASE/plasma/$APP_DOMAIN"                     # Engine compartido
        PLASMOID_DIR="$DATA_BASE/plasma/plasmoids/$APP_DOMAIN"      # Plasmoide
        ;;
    *)
        echo -e "${RED}ERROR: Unsupported desktop: $DESKTOP${NC}"
        exit 1
        ;;
esac

CACHE_DIR="$CACHE_BASE/wmm"

# ----------------------------------------------------------
# 4b. RECURSOS DE INTEGRACIÓN DEL SISTEMA
# ----------------------------------------------------------
# Directorio XDG donde D-Bus busca automáticamente los
# servicios de sesión instalados por el usuario.
DBUS_SERVICES_DIR="$DATA_BASE/dbus-1/services"

# Plantilla del servicio D-Bus incluida con WMM.
DBUS_SERVICE_TEMPLATE="$PROJECT_DIR/wmm_platform/shell/linux/org.maki.wmm.service"

# Destino final del servicio.
DBUS_SERVICE_FILE="$DBUS_SERVICES_DIR/$APP_DOMAIN.service"

# ----------------------------------------------------------
# 5. GENERAR settings_core.ini
# ----------------------------------------------------------
INI_FILE="$PROJECT_DIR/data/settings_core.ini"

# ----------------------------------------------------------
# 6. DEPENDENCIAS DE WMM (INSTALABLES)
# ----------------------------------------------------------
declare -A WMM_DEPENDENCIES
WMM_DEPENDENCIES=(
    ["Python 3"]="python3 --version|python3"
    ["Pillow (Python Imaging)"]="python3 -c 'from PIL import Image'|python3-pillow"
    ["NumPy (Python scientific computing)"]="python3 -c 'import numpy'|python3-numpy"
    ["Libnotify (notifications)"]="command -v notify-send|libnotify-bin"
    ["GetText"]="command -v xgettext|gettext"
    ["Zenity (dialogs)"]="command -v zenity|zenity"
)

# ----------------------------------------------------------
# 7. DEPENDENCIAS DE GNOME (SOLO SI EL ESCRITORIO ES GNOME)
# ----------------------------------------------------------
declare -A GNOME_DEPENDENCIES
if [ "$DESKTOP" = "gnome" ]; then
    GNOME_DEPENDENCIES=(
        ["GNOME Shell Extensions"]="command -v gnome-extensions|gnome-shell-extension-prefs"
        ["GNOME Shell Extension Manager"]="command -v gnome-extensions-app|gnome-shell-extension-prefs"
    )
fi

# Dependencias específicas de KDE
declare -A KDE_DEPENDENCIES
if [ "$DESKTOP" = "kde" ]; then
    KDE_DEPENDENCIES=(
        ["KDialog"]="command -v kdialog|kdialog"
    )
fi

# ----------------------------------------------------------
# 8. DEPENDENCIAS GTK COMUNES A TODOS LOS ESCRITORIOS
# ----------------------------------------------------------
declare -A GTK_DEPENDENCIES
GTK_DEPENDENCIES=(
    ["PyGObject (GTK bindings)"]="python3 -c 'import gi'|python3-gi"
    ["GTK 3.0 Introspection"]="python3 -c 'import gi; gi.require_version(\"Gtk\", \"3.0\"); from gi.repository import Gtk'|gir1.2-gtk-3.0"
    ["GLib 2.0 Introspection"]="python3 -c 'import gi; gi.require_version(\"GLib\", \"2.0\"); from gi.repository import GLib'|gir1.2-glib-2.0"
)

# ----------------------------------------------------------
# 9. FUNCIONES DE VERIFICACIÓN Y CHECKLIST
# ----------------------------------------------------------

# ----------------------------------------------------------
# FUNCIÓN PARA VERIFICAR UNA DEPENDENCIA
# ----------------------------------------------------------
check_dep() {
    local test_cmd="$1"
    if eval "$test_cmd" &> /dev/null; then
        echo 1 # Instalada
    else
        echo 0 # No instalada
    fi
}

# ----------------------------------------------------------
# FUNCIÓN PARA MOSTRAR EL CHECKLIST
# ----------------------------------------------------------
print_checklist() {
    local installed_count=0
    local missing_count=0

    # --- Bloque 1: Dependencias de escritorios GTK (solo si no es KDE) ---
        echo -e "${GREEN}[GTK dependencies]${NC}"
        for dep_name in "${!GTK_DEPENDENCIES[@]}"; do
            test_cmd="${GTK_DEPENDENCIES[$dep_name]%%|*}"
            status=$(check_dep "$test_cmd")

            if [ "$status" -eq 1 ]; then
                echo -e "  ${GREEN}[✔]${NC} $dep_name"
                ((installed_count++))
            else
                echo -e "  ${RED}[✘]${NC} $dep_name"
                ((missing_count++))
            fi
        done

    # --- Bloque 2: Dependencias de GNOME (solo si estamos en GNOME) ---
    if [ "$DESKTOP" = "gnome" ]; then
        echo -e "${GREEN}[GNOME dependencies]${NC}"
        for dep_name in "${!GNOME_DEPENDENCIES[@]}"; do
            test_cmd="${GNOME_DEPENDENCIES[$dep_name]%%|*}"
            status=$(check_dep "$test_cmd")
            if [ "$status" -eq 1 ]; then
                echo -e "  ${GREEN}[✔]${NC} $dep_name"
                ((installed_count++))
            else
                echo -e "  ${RED}[✘]${NC} $dep_name"
                ((missing_count++))
            fi
        done
    fi

    # --- Bloque 3: Dependencias de KDE (solo si estamos en KDE) ---
    if [ "$DESKTOP" = "kde" ]; then
        echo -e "${GREEN}[KDE dependencies]${NC}"
        for dep_name in "${!KDE_DEPENDENCIES[@]}"; do
            test_cmd="${KDE_DEPENDENCIES[$dep_name]%%|*}"
            status=$(check_dep "$test_cmd")
            if [ "$status" -eq 1 ]; then
                echo -e "  ${GREEN}[✔]${NC} $dep_name"
                ((installed_count++))
            else
                echo -e "  ${RED}[✘]${NC} $dep_name"
                ((missing_count++))
            fi
        done
    fi

    # --- Bloque 4: Dependencias de WMM (instalables, comunes a todos) ---
    echo -e "${GREEN}[WMM dependencies]${NC}"
    for dep_name in "${!WMM_DEPENDENCIES[@]}"; do
        test_cmd="${WMM_DEPENDENCIES[$dep_name]%%|*}"
        status=$(check_dep "$test_cmd")
        if [ "$status" -eq 1 ]; then
            echo -e "  ${GREEN}[✔]${NC} $dep_name"
            ((installed_count++))
        else
            echo -e "  ${RED}[✘]${NC} $dep_name"
            ((missing_count++))
        fi
    done

    echo -e "${GREEN}$installed_count installed${NC}, ${RED}$missing_count missing${NC}"
    return $missing_count
}

# ----------------------------------------------------------
# FUNCIÓN PARA INSTALAR UNA PLANTILLA
# Sustituye los marcadores de la plantilla y la copia al
# destino indicado.
# ----------------------------------------------------------
install_template() {

    local template="$1"
    local destination="$2"

    sed \
        -e "s|@APP_DIR@|$APP_DIR|g" \
        -e "s|@PYTHON3@|$PYTHON3_BIN|g" \
        -e "s|@DBUS_SEND@|$DBUS_SEND_BIN|g" \
        "$template" > "$destination"
}

# ----------------------------------------------------------
# FUNCIÓN PARA INSTALAR LOS ARCHIVOS DE WMM
# ----------------------------------------------------------
install_files() {

    # ----------------------------------------------------------
    # Detectar ruta absoluta de python3 para el servicio D-Bus.
    # Las dependencias ya han sido verificadas en este punto.
    # ----------------------------------------------------------
    PYTHON3_BIN="$(command -v python3)"

    if [ -z "$PYTHON3_BIN" ]; then
        echo -e "${RED}ERROR: python3 not found after dependency verification.${NC}"
        exit 1
    fi

    DBUS_SEND_BIN=""

    if [ "$DESKTOP" = "kde" ]; then
        DBUS_SEND_BIN="$(command -v dbus-send)"

        if [ -z "$DBUS_SEND_BIN" ]; then
            echo -e "${RED}ERROR: dbus-send not found.${NC}"
            exit 1
        fi
    fi

    # Generar .ini (si no se hizo antes, se asegura)
    cat > "$INI_FILE" << EOF
# WMM Platform Configuration
# Generated by install.sh on $(date)
platform=$PLATFORM
desktop=$DESKTOP
app_domain=$APP_DOMAIN
data_base=$DATA_BASE
cache_base=$CACHE_BASE
graphics_engine=$GRAPHICS_ENGINE
EOF

    # Progreso inicial: rutas y configuración
    progress_msg "Data base: $DATA_BASE"
    progress_msg "Cache base: $CACHE_BASE"
    progress_msg "App domain: $APP_DOMAIN"
    progress_msg "Installation path: $APP_DIR"
    progress_msg "Cache path: $CACHE_DIR"
    progress_msg "Generating platform configuration..."
    progress_msg "Configuration saved to $INI_FILE"

    # ----------------------------------------------------------
    # VERIFICACIÓN DE INTEGRIDAD DEL PROYECTO
    # ----------------------------------------------------------
    # Comprobamos que el directorio del proyecto existe
    if [ ! -d "$PROJECT_DIR" ]; then
        echo "ERROR: Project directory not found: $PROJECT_DIR"
        echo "Make sure the 'wmm' folder is next to this script."
        exit 1
    fi

    # Directorios obligatorios (independientes del escritorio)
    MISSING=0
    for dir in python wmm_platform data help po; do
        if [ ! -d "$PROJECT_DIR/$dir" ]; then
            echo "ERROR: Missing required directory: $dir"
            MISSING=1
        fi
    done

    # Archivos de metadatos según el escritorio detectado
    case "$DESKTOP" in
        cinnamon)
            if [ ! -f "$PROJECT_DIR/wmm_platform/shell/cinnamon/metadata.cinnamon.json" ]; then
                echo "ERROR: Missing metadata.cinnamon.json for Cinnamon"
                MISSING=1
            fi
            ;;
        gnome)
            if [ ! -f "$PROJECT_DIR/wmm_platform/shell/gnome/metadata.gnome.json" ]; then
                echo "ERROR: Missing metadata.gnome.json for GNOME"
                MISSING=1
            fi
            ;;
        kde)
            if [ ! -f "$PROJECT_DIR/wmm_platform/shell/kde/plasmoid_contents/metadata.kde_plasmoid.json" ]; then
                echo "ERROR: Missing KDE plasmoid metadata"
                MISSING=1
            fi

            if [ ! -f "$PROJECT_DIR/wmm_platform/shell/kde/org.maki.wmm.desktop" ]; then
                echo "ERROR: Missing KDE launcher"
                MISSING=1
            fi
            ;;
        *)
            echo "ERROR: Unsupported desktop: $DESKTOP"
            exit 1
            ;;
    esac

    # Si falta algo, abortar
    if [ $MISSING -eq 1 ]; then
        echo ""
        echo "WMM project folder is incomplete."
        echo "Make sure the 'wmm' folder is next to this script and contains"
        echo "all required files for your desktop ($DESKTOP)."
        exit 1
    fi

    # Crear los directorios necesarios
    mkdir -p "$APP_DIR/data" "$APP_DIR/python" "$APP_DIR/wmm_platform"
    mkdir -p "$CACHE_DIR/thumbnails"
    mkdir -p "$DBUS_SERVICES_DIR"

    # Copiar todo el contenido de wmm/ al destino
    progress_msg "Creating directory structure and copying files..."
    cp -r "$PROJECT_DIR"/* "$APP_DIR/" || {
        echo "Error copying files. Do you have write permission on $APP_DIR?"
        exit 1
    }
    progress_msg "Files copied successfully."

    # ----------------------------------------------------------
    # Instalar el servicio de activación D-Bus
    # ----------------------------------------------------------
    if [ -f "$DBUS_SERVICE_TEMPLATE" ]; then
        progress_msg "Installing D-Bus activation service..."

        install_template \
            "$DBUS_SERVICE_TEMPLATE" \
            "$DBUS_SERVICE_FILE"

        chmod 644 "$DBUS_SERVICE_FILE"

        if command -v busctl &>/dev/null; then
            busctl --user call org.freedesktop.DBus /org/freedesktop/DBus org.freedesktop.DBus ReloadConfig >/dev/null 2>&1
        fi

        progress_msg "D-Bus activation service installed."
    else
        echo -e "${RED}Warning: D-Bus service template not found.${NC}"
    fi

    # Limpieza de permisos: quitar ejecución a todos los archivos
    # El motor usa python3 para ejecutar los .py, y los .sh se gestionan
    # desde ensure_shell_actions cuando se copian a sus destinos finales.
    find "$APP_DIR" -type f -exec chmod -x {} \;
    progress_msg "Execution permissions removed from all files (security hardening)."

    # Copiar el metadata.json y los archivos específicos del escritorio
    case "$DESKTOP" in
        cinnamon)
            mkdir -p "$HOME/.local/share/applications"

            cp -f "$PROJECT_DIR/wmm_platform/shell/cinnamon/metadata.cinnamon.json" "$APP_DIR/metadata.json"
            cp -f "$PROJECT_DIR/wmm_platform/shell/cinnamon/applet.cinnamon.js" "$APP_DIR/applet.js"

            install_template \
                "$PROJECT_DIR/wmm_platform/shell/cinnamon/org.maki.wmm.cinnamon.desktop" \
                "$HOME/.local/share/applications/org.maki.wmm.cinnamon.desktop"

            progress_msg "Cinnamon files and application launcher installed."
            ;;
		gnome)
			mkdir -p "$HOME/.local/share/applications"

			cp -f "$PROJECT_DIR/wmm_platform/shell/gnome/metadata.gnome.json" "$APP_DIR/metadata.json"
			cp -f "$PROJECT_DIR/wmm_platform/shell/gnome/extension.gnome.js" "$APP_DIR/extension.js"
			cp -f "$PROJECT_DIR/wmm_platform/shell/gnome/org.maki.wmm.gnome.desktop" "$HOME/.local/share/applications/org.maki.wmm.gnome.desktop"
			progress_msg "GNOME files and application launcher installed."
			;;
        kde)
            # 1. Crear destinos
            mkdir -p "$PLASMOID_DIR/contents/ui"
            mkdir -p "$HOME/.local/share/applications"
            mkdir -p "$HOME/.config/autostart"
            progress_msg "WMM: Destination folders created"
            # 2. Copiar el plasmoide
            cp -r "$PROJECT_DIR/wmm_platform/shell/kde/plasmoid_contents/contents" "$PLASMOID_DIR/"
            cp -f "$PROJECT_DIR/wmm_platform/shell/kde/plasmoid_contents/metadata.kde_plasmoid.json" "$PLASMOID_DIR/metadata.json"
            progress_msg "KDE Plasmoid copied to $PLASMOID_DIR"
            # 3. Instalar lanzador y autoarranque
            install_template \
                "$PROJECT_DIR/wmm_platform/shell/kde/org.maki.wmm.desktop" \
                "$HOME/.local/share/applications/org.maki.wmm.desktop"
            install_template \
                "$PROJECT_DIR/wmm_platform/shell/kde/org.maki.wmm.desktop" \
                "$HOME/.config/autostart/org.maki.wmm.desktop"
            progress_msg "KDE launcher and autostart entry installed."
            # 4. Registrar paquetes
            if command -v kpackagetool6 &>/dev/null; then
                kpackagetool6 -t Plasma/Applet --install "$PLASMOID_DIR" 2>/dev/null
                progress_msg "Components registered with kpackagetool6"
            else
                echo -e "${RED}Warning: kpackagetool6 not found. Components will not be automatically registered.${NC}"
            fi
            # 5. Refrescar menú de aplicaciones
            if command -v kbuildsycoca6 &>/dev/null; then
                kbuildsycoca6 >/dev/null 2>&1
                progress_msg "KDE application database refreshed."
            fi
            ;;
    esac

    # Limpiar archivos de desarrollo...
    find "$APP_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
    find "$APP_DIR" -type f -name "*.pyc" -delete 2>/dev/null
    progress_msg "Development files cleaned."

    # Asegurar que el .ini existe en el destino
    if [ ! -f "$APP_DIR/data/settings_core.ini" ]; then
        cp "$INI_FILE" "$APP_DIR/data/settings_core.ini"
        progress_msg "Platform configuration copied."
    fi

    # Limpiar la línea de progreso y dejar paso al recuadro
    printf "\r\033[K\n"

    # ==========================================================
    # ÉXITO (recuadro centrado)
    # ==========================================================
    local cols=$(tput cols 2>/dev/null || echo 80)
    local line=$(printf '%*s' "$cols" | tr ' ' '=')
    local msg1="Installation completed successfully!"
    local msg2="WMM has been installed at: $APP_DIR"
    local pad1=$(( (cols - ${#msg1}) / 2 ))
    local pad2=$(( (cols - ${#msg2}) / 2 ))
    echo ""
    printf "%s\n" "$line"
    printf "%*s%s\n" "$pad1" "" "$msg1"
    printf "%*s%s\n" "$pad2" "" "$msg2"
    printf "%s\n" "$line"

    # Instrucciones según escritorio
    case "$DESKTOP" in
        cinnamon)
            echo ""
            echo "To enable the applet, go to Cinnamon Applets settings"
            echo "and activate 'WMM Manager',"
            echo "or click the WMM icon in Menu > Graphics."
            ;;
        gnome)
            echo ""
            echo "To enable the extension, restart your session,"
            echo "open GNOME Extensions and enable 'WMM Manager'."
            ;;
        kde)
            echo ""
            echo "WMM will start automatically with your next KDE Plasma session."
            echo "You can also start it manually from the application menu."
            ;;
        *)
            echo ""
            echo "WMM has been installed successfully."
            echo "Restart your desktop session to load applet/extension/plasmoid."
            ;;
    esac
}

# ----------------------------------------------------------
# FUNCIÓN PRINCIPAL
# ----------------------------------------------------------
main() {
    # ----------------------------------------------------------
    # CABECERA CENTRADA CON INFORMACIÓN DE PLATAFORMA
    # ----------------------------------------------------------
    clear
    local cols=$(tput cols 2>/dev/null || echo 80)
    local line=$(printf '%*s' "$cols" | tr ' ' '=')
    local text1="WMM - Wallpaper Multi-Monitor Manager"
    local text2="SO: $PLATFORM | Desktop: $DESKTOP | Graphics: $GRAPHICS_ENGINE"
    local pad1=$(( (cols - ${#text1}) / 2 ))
    local pad2=$(( (cols - ${#text2}) / 2 ))
    echo ""
    printf "%s\n" "$line"
    printf "%*s%s\n" "$pad1" "" "$text1"
    printf "%*s%b\n" "$pad2" "" "${GREEN}${text2}${NC}"
    printf "%s\n" "$line"

    # First pass: show current status
    print_checklist
    local missing=$?

    if [ $missing -eq 0 ]; then
        install_files
        return 0
    fi

    # If dependencies are missing, ask whether to install them
    echo -e "\nDo you want to install the missing dependencies? (y/n)"
    read -p "Option: " answer || true
    if [ "$answer" != "y" ] && [ "$answer" != "Y" ]; then
        echo "Installation cancelled. No dependencies will be installed."
        echo "You can install them manually later."
        return 1
    fi

    # Attempt to install the missing dependencies
    echo -e "\nInstalling dependencies..."

    # Detect package manager
    if command -v apt &> /dev/null; then
        PKG_MANAGER="apt"
        INSTALL_CMD="sudo apt install -y"
    elif command -v dnf &> /dev/null; then
        PKG_MANAGER="dnf"
        INSTALL_CMD="sudo dnf install -y"
        # Package name mapping for Fedora
        declare -A DNF_MAP
        DNF_MAP=(
            ["python3-gi"]="python3-gobject"
            ["gir1.2-gtk-3.0"]="gtk3"
            ["gir1.2-glib-2.0"]="glib2"
        )
    elif command -v pacman &> /dev/null; then
        PKG_MANAGER="pacman"
        INSTALL_CMD="sudo pacman -Sy --noconfirm"
        # Package name mapping for Arch
        declare -A PACMAN_MAP
        PACMAN_MAP=(
            ["python3"]="python"
            ["python3-pillow"]="python-pillow"
            ["python3-numpy"]="python-numpy"
            ["libnotify-bin"]="libnotify"
            ["gnome-shell-extension-prefs"]="gnome-shell-extensions"
            ["python3-gi"]="python-gobject"
            ["gir1.2-gtk-3.0"]="gtk3"
            ["gir1.2-glib-2.0"]="glib2"
        )
    else
        echo "Could not detect package manager."
        echo "Please install the packages listed above manually."
        return 1
    fi

    # Build list of missing packages
    MISSING_PKGS=""
    for dep_name in "${!WMM_DEPENDENCIES[@]}" "${!GTK_DEPENDENCIES[@]}" "${!GNOME_DEPENDENCIES[@]}" "${!KDE_DEPENDENCIES[@]}"; do
        if [ -n "${WMM_DEPENDENCIES[$dep_name]}" ]; then
            test_cmd="${WMM_DEPENDENCIES[$dep_name]%%|*}"
            packages="${WMM_DEPENDENCIES[$dep_name]##*|}"
        elif [ -n "${GNOME_DEPENDENCIES[$dep_name]}" ]; then
            test_cmd="${GNOME_DEPENDENCIES[$dep_name]%%|*}"
            packages="${GNOME_DEPENDENCIES[$dep_name]##*|}"
        elif [ -n "${KDE_DEPENDENCIES[$dep_name]}" ]; then
            test_cmd="${KDE_DEPENDENCIES[$dep_name]%%|*}"
            packages="${KDE_DEPENDENCIES[$dep_name]##*|}"
        elif [ -n "${GTK_DEPENDENCIES[$dep_name]}" ]; then
            test_cmd="${GTK_DEPENDENCIES[$dep_name]%%|*}"
            packages="${GTK_DEPENDENCIES[$dep_name]##*|}"
        fi

        status=$(check_dep "$test_cmd")
        if [ "$status" -eq 0 ]; then
            if [ "$PKG_MANAGER" = "dnf" ]; then
                for pkg in $packages; do
                    MISSING_PKGS="$MISSING_PKGS ${DNF_MAP[$pkg]:-$pkg}"
                done
            elif [ "$PKG_MANAGER" = "pacman" ]; then
                for pkg in $packages; do
                    MISSING_PKGS="$MISSING_PKGS ${PACMAN_MAP[$pkg]:-$pkg}"
                done
            else
                MISSING_PKGS="$MISSING_PKGS $packages"
            fi
        fi
    done

    # Install
    if [ -n "$MISSING_PKGS" ]; then
        echo "Running: $INSTALL_CMD $MISSING_PKGS"
        echo "Installing dependencies..."
        $INSTALL_CMD $MISSING_PKGS
        echo "Package installation completed."
    else
        echo "No pending packages."
    fi

    # Second pass: verify after installation
    echo -e "\nVerifying dependencies after installation..."
    print_checklist
    missing=$?

    if [ $missing -eq 0 ]; then
        echo "All dependencies have been successfully installed."
        install_files
        return 0
    else
        echo -e "\nSome dependencies could not be installed."
        echo "Check the error messages and try manually."
        return 1
    fi
}

# ----------------------------------------------------------
# INICIO DEL SCRIPT
# ----------------------------------------------------------
main
