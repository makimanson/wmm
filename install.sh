#!/bin/bash

# ==========================================================
# WMM - Wallpaper Master Manager
# Instalador interactivo y verificación de dependencias
# ==========================================================

set -e

# Colores para el checklist
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # Sin color

APPLET_DIR="$HOME/.local/share/cinnamon/applets/wmm-applet@maki"
CACHE_DIR="$HOME/.cache/wmm"

# ----------------------------------------------------------
# Verificar que Cinnamon está instalado
# ----------------------------------------------------------
if ! command -v cinnamon &> /dev/null; then
    echo -e "${RED}ERROR: Cinnamon no está instalado en este sistema.${NC}"
    echo "WMM es un applet exclusivo para el escritorio Cinnamon."
    echo "Por favor, instala Cinnamon antes de ejecutar este instalador."
    exit 1
fi
echo -e "${GREEN}Cinnamon detectado.${NC}"

# ----------------------------------------------------------
# Definición de dependencias: "Nombre" "Comando de prueba" "Paquete(s)"
# ----------------------------------------------------------
declare -A DEPENDENCIES
DEPENDENCIES=(
    ["Python 3"]="python3 --version|python3"
    ["Pillow (Python Imaging)"]="python3 -c 'from PIL import Image'|python3-pillow"
    ["PyGObject (GTK bindings)"]="python3 -c 'import gi; gi.require_version(\"Gtk\", \"3.0\")'|python3-gi python3-gi-cairo"
    ["GTK 3.0 Introspection"]="pkg-config --exists gtk+-3.0|gir1.2-gtk-3.0"
    ["GLib 2.0 Introspection"]="pkg-config --exists glib-2.0|gir1.2-glib-2.0"
    ["NumPy (Python scientific computing)"]="python3 -c 'import numpy'|python3-numpy"
    ["GetText"]="command -v xgettext|gettext"
    ["Libnotify (notificaciones)"]="command -v notify-send|libnotify-bin"
    ["Zenity (diálogos)"]="command -v zenity|zenity"
    ["pkill (señales)"]="command -v pkill|procps"
)

# ----------------------------------------------------------
# Función para verificar una dependencia
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
# Función para mostrar el checklist
# ----------------------------------------------------------
print_checklist() {
    local installed_count=0
    local missing_count=0
    echo -e "\nEstado de las dependencias:"
    for dep_name in "${!DEPENDENCIES[@]}"; do
        local test_cmd="${DEPENDENCIES[$dep_name]%%|*}"
        local packages="${DEPENDENCIES[$dep_name]##*|}"
        local status=$(check_dep "$test_cmd")
        if [ "$status" -eq 1 ]; then
            echo -e "  ${GREEN}[✔]${NC} $dep_name"
            ((installed_count++))
        else
            echo -e "  ${RED}[✘]${NC} $dep_name"
            ((missing_count++))
        fi
    done
    echo -e "\n${GREEN}$installed_count instaladas${NC}, ${RED}$missing_count faltantes${NC}"
    return $missing_count
}

# ----------------------------------------------------------
# INICIO DEL SCRIPT
# ----------------------------------------------------------
clear
echo "=============================================="
echo "  WMM - Wallpaper Multi-Monitor Manager"
echo "  Verificación de dependencias"
echo "=============================================="

# Primer pase: mostrar estado actual
print_checklist
missing=$?

if [ $missing -eq 0 ]; then
    echo "Todas las dependencias están instaladas."
    # Instalación de archivos
    echo -e "\nCreando estructura de carpetas y copiando archivos..."
    mkdir -p "$APPLET_DIR/data" "$APPLET_DIR/python" "$APPLET_DIR/locale"
    mkdir -p "$CACHE_DIR/thumbnails"
    SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
    cp -r "$SCRIPT_DIR"/* "$APPLET_DIR/"
    # Compilar e instalar traducciones
    echo "Instalando traducciones..."
    for po_file in po/*.po; do
        if [ -f "$po_file" ]; then
            # Extraer el código de idioma del nombre del archivo (ej. "ca" de "ca.po")
            lang=$(basename "$po_file" .po)
            # Crear directorio de destino
            lang_dir="$HOME/.local/share/locale/$lang/LC_MESSAGES"
            mkdir -p "$lang_dir"
            # Compilar .po a .mo y copiarlo
            msgfmt "$po_file" -o "$lang_dir/wmm-applet@maki.mo"
            echo "  Traducción $lang instalada."
        fi
    done
    done
    echo -e "\n=============================================="
    echo "  ¡Instalación completada con éxito!"
    echo "  WMM se ha instalado en: $APPLET_DIR"
    echo "=============================================="
    echo "Cerrando en 5 segundos..."
    sleep 5
    exit 0
fi

# Si faltan dependencias, preguntar si instalarlas
echo -e "\n¿Deseas instalar las dependencias faltantes? (s/n)"
read -p "Opción: " respuesta
if [ "$respuesta" != "s" ] && [ "$respuesta" != "S" ]; then
    echo "Instalación cancelada. No se instalarán dependencias."
    echo "Puedes instalarlas manualmente más tarde."
    exit 1
fi

# Intentar instalar las dependencias faltantes
echo -e "\nInstalando dependencias..."

# Detectar gestor de paquetes
if command -v apt &> /dev/null; then
    PKG_MANAGER="apt"
    INSTALL_CMD="sudo apt install -y"
elif command -v dnf &> /dev/null; then
    PKG_MANAGER="dnf"
    INSTALL_CMD="sudo dnf install -y"
elif command -v pacman &> /dev/null; then
    PKG_MANAGER="pacman"
    INSTALL_CMD="sudo pacman -Sy --noconfirm"
else
    echo "No se pudo detectar el gestor de paquetes."
    echo "Por favor, instala manualmente los paquetes indicados arriba."
    exit 1
fi

# Construir lista de paquetes faltantes
MISSING_PKGS=""
for dep_name in "${!DEPENDENCIES[@]}"; do
    local test_cmd="${DEPENDENCIES[$dep_name]%%|*}"
    local packages="${DEPENDENCIES[$dep_name]##*|}"
    local status=$(check_dep "$test_cmd")
    if [ "$status" -eq 0 ]; then
        MISSING_PKGS="$MISSING_PKGS $packages"
    fi
done

# Instalar
if [ -n "$MISSING_PKGS" ]; then
    echo "Ejecutando: $INSTALL_CMD $MISSING_PKGS"
    $INSTALL_CMD $MISSING_PKGS
else
    echo "No hay paquetes pendientes."
fi

# Segundo pase: verificar después de la instalación
echo -e "\nVerificando dependencias tras la instalación..."
print_checklist
missing=$?

if [ $missing -eq 0 ]; then
    echo "Todas las dependencias han sido instaladas correctamente."
    # Instalación de archivos
    echo -e "\nCreando estructura de carpetas y copiando archivos..."
    mkdir -p "$APPLET_DIR/data" "$APPLET_DIR/python" "$APPLET_DIR/locale"
    mkdir -p "$CACHE_DIR/thumbnails"
    SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
    cp -r "$SCRIPT_DIR"/* "$APPLET_DIR/"
    # Compilar e instalar traducciones
    echo "Instalando traducciones..."
    for po_file in po/*.po; do
        if [ -f "$po_file" ]; then
            # Extraer el código de idioma del nombre del archivo (ej. "ca" de "ca.po")
            lang=$(basename "$po_file" .po)
            # Crear directorio de destino
            lang_dir="$HOME/.local/share/locale/$lang/LC_MESSAGES"
            mkdir -p "$lang_dir"
            # Compilar .po a .mo y copiarlo
            msgfmt "$po_file" -o "$lang_dir/wmm-applet@maki.mo"
            echo "  Traducción $lang instalada."
        fi
    done
    done
    echo -e "\n=============================================="
    echo "  ¡Instalación completada con éxito!"
    echo "  WMM se ha instalado en: $APPLET_DIR"
    echo "=============================================="
    echo "Cerrando en 5 segundos..."
    sleep 5
    exit 0
else
    echo -e "\nAlgunas dependencias no pudieron ser instaladas."
    echo "Revisa los mensajes de error e inténtalo manualmente."
    exit 1
fi
