#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later

# ==========================================================
# WMM - Wallpaper Multi-Monitor Manager
# Unified Uninstaller
# ==========================================================

set -u
set -o pipefail

# Modo gestionado: utilizado cuando otro componente WMM ya ha
# presentado su propia interfaz/confirmación al usuario.
MANAGED=0

case "${1:-}" in
    --managed)
        MANAGED=1
        ;;
    "")
        ;;
    *)
        printf '[!!] Unknown option: %s\n' "$1" >&2
        exit 2
        ;;
esac

# La cabecera y la confirmación pertenecen únicamente a una
# ejecución directa e interactiva desde terminal.
DIRECT_CONSOLE=0

if [ "$MANAGED" -eq 0 ] && [ -t 0 ] && [ -t 1 ]; then
    DIRECT_CONSOLE=1
fi

# Mantener la terminal abierta al finalizar cuando el script se ejecuta
# directamente. El Install Manager conserva la salida dentro de VTE.
if [ "${WMM_INSTALL_MANAGER:-0}" != "1" ] && [ -t 0 ]; then
    trap 'echo ""; read -r -p "Press Enter to exit..." dummy' EXIT
fi

# Colores
GREEN='\033[0;32m'
NC='\033[0m' # No color

# ----------------------------------------------------------
# RUTAS XDG COMUNES
# ----------------------------------------------------------
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"
SYSTEM_DATA_DIRS="${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"

CACHE_DIR="$CACHE_HOME/wmm"
DBUS_DIR="$DATA_HOME/dbus-1/services"
APPLICATIONS_DIR="$DATA_HOME/applications"
AUTOSTART_DIR="$HOME/.config/autostart"

ok()   { printf '[OK] %s\n' "$1"; }
info() { printf '[..] %s\n' "$1"; }
warn() { printf '[!!] %s\n' "$1" >&2; }

# ----------------------------------------------------------
# HELPERS DE LIMPIEZA
# ----------------------------------------------------------
remove_file() {
    local path="$1"

    if [ -f "$path" ] || [ -L "$path" ]; then
        if rm -f -- "$path"; then
            ok "Removed: $path"
        else
            warn "Could not remove: $path"
        fi
    fi
}

remove_tree() {
    local path="$1"

    if [ -d "$path" ] || [ -L "$path" ]; then
        if rm -rf -- "$path"; then
            ok "Removed: $path"
        else
            warn "Could not remove: $path"
        fi
    fi
}

remove_service_if_owned() {
    local path="$1"

    if [ ! -f "$path" ]; then
        return
    fi

    if grep -Fq "$APP_DIR" "$path"; then
        remove_file "$path"
    else
        warn "Preserved D-Bus service because it does not reference the current WMM installation: $path"
    fi
}

remove_legacy_mate_entry_if_owned() {
    local path="$1"

    if [ ! -f "$path" ]; then
        return
    fi

    if grep -Fq "$APP_DIR" "$path" || grep -Fq "mate-launcher.py" "$path"; then
        remove_file "$path"
    fi
}

# ----------------------------------------------------------
# PARADA DEL ENGINE COMÚN
# ----------------------------------------------------------
stop_wmm_engine() {
    info "Stopping WMM..."

    # Solicitar primero el cierre coordinado del engine común.
    if command -v dbus-send >/dev/null 2>&1; then
        if dbus-send \
            --session \
            --type=method_call \
            --print-reply \
            --dest=org.maki.wmm \
            /org/maki/wmm \
            org.maki.wmm.Shutdown \
            >/dev/null 2>&1; then

            ok "WMM engine shutdown requested through D-Bus."
        fi
    fi

    # Fallback: terminar únicamente procesos pertenecientes
    # a la instalación WMM del escritorio actual.
    for pattern in \
        "$APP_DIR/python/main.py" \
        "$APP_DIR/python/panel.py" \
        "$APP_DIR/python/about.py"
    do
        if pgrep -f -- "$pattern" >/dev/null 2>&1; then
            pkill -TERM -f -- "$pattern" >/dev/null 2>&1 || true
        fi
    done

    # Cinnamon <= v1.2.2 podía seguir ejecutándose desde el
    # antiguo UUID wmm-applet@maki y no disponía del lifecycle
    # D-Bus actual. Terminar únicamente procesos pertenecientes
    # a ese árbol legacy.
    if [ "$DESKTOP" = "cinnamon" ]; then
        for pattern in \
            "$LEGACY_APP_DIR/python/main.py" \
            "$LEGACY_APP_DIR/python/panel.py" \
            "$LEGACY_APP_DIR/python/debug_log_viewer.py"
        do
            if pgrep -f -- "$pattern" >/dev/null 2>&1; then
                pkill -TERM -f -- "$pattern" >/dev/null 2>&1 || true
            fi
        done
    fi
}

# ----------------------------------------------------------
# LIMPIEZA ESPECÍFICA: CINNAMON
# ----------------------------------------------------------
cleanup_cinnamon_runtime() {
    info "Removing Cinnamon runtime registrations..."

    # Retirar únicamente las instancias del applet WMM y sus atajos
    # personalizados. El resto de applets y keybindings se conserva.
    if command -v python3 >/dev/null 2>&1; then
        APP_DIR="$APP_DIR" \
        APP_DOMAIN="$APP_DOMAIN" \
        LEGACY_APP_DIR="$LEGACY_APP_DIR" \
        LEGACY_APP_DOMAIN="$LEGACY_APP_DOMAIN" \
        python3 <<'PY'
import os

try:
    import gi
    gi.require_version("Gio", "2.0")
    from gi.repository import Gio
except Exception as error:
    print(f"[!!] Could not load Gio for Cinnamon cleanup: {error}")
    raise SystemExit(0)


app_dir = os.environ.get("APP_DIR", "")
app_domain = os.environ.get("APP_DOMAIN", "wmm@maki")
legacy_app_dir = os.environ.get("LEGACY_APP_DIR", "")
legacy_app_domain = os.environ.get("LEGACY_APP_DOMAIN", "wmm-applet@maki")


# ----------------------------------------------------------
# Cinnamon applet registration(s)
# ----------------------------------------------------------
try:
    cinnamon_settings = Gio.Settings.new("org.cinnamon")
    enabled_applets = list(cinnamon_settings.get_strv("enabled-applets"))

    remaining_applets = []
    removed_applets = 0

    for entry in enabled_applets:
        parts = entry.split(":")
        uuid = parts[3] if len(parts) >= 4 else ""

        if uuid in (app_domain, legacy_app_domain):
            removed_applets += 1
        else:
            remaining_applets.append(entry)

    if removed_applets:
        cinnamon_settings.set_strv("enabled-applets", remaining_applets)
        Gio.Settings.sync()

        print(
            f"[OK] Removed {removed_applets} "
            "WMM Cinnamon applet registration(s)."
        )

except Exception as error:
    print(f"[!!] Could not clean Cinnamon applet registration: {error}")


# ----------------------------------------------------------
# Cinnamon custom keybinding(s)
# ----------------------------------------------------------
try:
    main_schema = "org.cinnamon.desktop.keybindings"
    custom_schema = "org.cinnamon.desktop.keybindings.custom-keybinding"
    base_path = "/org/cinnamon/desktop/keybindings/custom-keybindings/"

    settings = Gio.Settings.new(main_schema)
    custom_list = list(settings.get_strv("custom-list"))

    remaining_items = []
    removed_keybindings = 0

    for item in custom_list:
        if item == "__dummy__":
            remaining_items.append(item)
            continue

        try:
            custom = Gio.Settings.new_with_path(
                custom_schema,
                f"{base_path}{item}/"
            )
            command = custom.get_string("command")

        except Exception:
            remaining_items.append(item)
            continue

        command_lower = command.lower()

        belongs_to_current_wmm = (
            (app_dir and app_dir.lower() in command_lower)
            or app_domain.lower() in command_lower
        )

        belongs_to_legacy_wmm = (
            (legacy_app_dir and legacy_app_dir.lower() in command_lower)
            or legacy_app_domain.lower() in command_lower
        )

        is_wmm_rotation = (
            "force_rotation" in command_lower
            or "wmm-next.sh" in command_lower
        )

        if (belongs_to_current_wmm and is_wmm_rotation) or belongs_to_legacy_wmm:
            for key in ("name", "command", "binding"):
                try:
                    custom.reset(key)
                except Exception:
                    pass

            removed_keybindings += 1

        else:
            remaining_items.append(item)

    if removed_keybindings:
        settings.set_strv("custom-list", remaining_items)
        Gio.Settings.sync()

        print(
            f"[OK] Removed {removed_keybindings} "
            "WMM Cinnamon keyboard shortcut(s)."
        )

except Exception as error:
    print(f"[!!] Could not clean Cinnamon keyboard shortcuts: {error}")
PY
    fi
}

# ----------------------------------------------------------
# LIMPIEZA ESPECÍFICA: GNOME
# ----------------------------------------------------------
cleanup_gnome_runtime() {
    info "Removing GNOME runtime registrations..."

    # Desactivar la extensión antes de retirar sus archivos.
    # GNOME realiza así su lifecycle normal de disable().
    if command -v gnome-extensions >/dev/null 2>&1; then
        if gnome-extensions disable "$APP_DOMAIN" >/dev/null 2>&1; then
            ok "GNOME Shell extension disabled."
        else
            info "GNOME Shell extension was not enabled or could not be disabled."
        fi
    else
        warn "gnome-extensions is not available; the extension files will still be removed."
    fi

    # Retirar únicamente los atajos personalizados que pertenecen
    # a WMM. El resto de custom keybindings de GNOME se conserva.
    if command -v python3 >/dev/null 2>&1; then
        APP_DIR="$APP_DIR" APP_DOMAIN="$APP_DOMAIN" python3 <<'PY'
import os

try:
    import gi
    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib
except Exception as error:
    print(f"[!!] Could not load Gio for GNOME shortcut cleanup: {error}")
    raise SystemExit(0)


app_dir = os.environ.get("APP_DIR", "")
app_domain = os.environ.get("APP_DOMAIN", "wmm@maki")

schema_main = "org.gnome.settings-daemon.plugins.media-keys"
schema_custom = "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding"


# ----------------------------------------------------------
# GNOME custom keybinding(s)
# ----------------------------------------------------------
try:
    settings = Gio.Settings.new(schema_main)
    current_paths = list(settings.get_strv("custom-keybindings"))

except GLib.Error as error:
    print(f"[!!] Could not read GNOME custom keybindings: {error}")
    raise SystemExit(0)


remaining_paths = []
removed_paths = []

for path in current_paths:
    try:
        custom = Gio.Settings.new_with_path(schema_custom, path)
        command = custom.get_string("command")

    except GLib.Error:
        remaining_paths.append(path)
        continue

    command_lower = command.lower()

    belongs_to_wmm = (
        (app_dir and app_dir.lower() in command_lower)
        or app_domain.lower() in command_lower
    )

    is_wmm_rotation = (
        "force_rotation" in command_lower
        or "wmm-next.sh" in command_lower
    )

    if belongs_to_wmm and is_wmm_rotation:
        for key in custom.list_keys():
            custom.reset(key)

        removed_paths.append(path)

    else:
        remaining_paths.append(path)


if removed_paths:
    settings.set_strv("custom-keybindings", remaining_paths)
    Gio.Settings.sync()

    print(
        f"[OK] Removed {len(removed_paths)} "
        "WMM GNOME keyboard shortcut(s)."
    )
PY
    fi
}

# ----------------------------------------------------------
# LIMPIEZA ESPECÍFICA: KDE PLASMA
# ----------------------------------------------------------
cleanup_kde_runtime() {
    # ----------------------------------------------------------
    # Atajo global KDE
    # ----------------------------------------------------------
    info "Removing KDE global shortcut..."

    if command -v dbus-send >/dev/null 2>&1; then
        shortcut_result=$(dbus-send \
            --session \
            --type=method_call \
            --print-reply \
            --dest=org.kde.kglobalaccel \
            /kglobalaccel \
            org.kde.KGlobalAccel.unregister \
            string:org.maki.wmm.desktop \
            string:next-background \
            2>/dev/null || true)

        if [[ "$shortcut_result" == *"boolean true"* ]]; then
            ok "KDE global shortcut removed."
        elif [[ "$shortcut_result" == *"boolean false"* ]]; then
            info "KDE global shortcut was not registered."
        elif [ -n "$shortcut_result" ]; then
            warn "Unexpected response while removing KDE global shortcut: $shortcut_result"
        else
            warn "Could not remove the KDE global shortcut through KGlobalAccel."
        fi
    else
        warn "dbus-send is not available; KDE global shortcut could not be removed automatically."
    fi

    # ----------------------------------------------------------
    # Plasmoide WMM
    # ----------------------------------------------------------
    info "Removing Plasma widget..."

    if command -v kpackagetool6 >/dev/null 2>&1; then
        kpackagetool6 -t Plasma/Applet -r org.maki.wmm >/dev/null 2>&1 || true
    fi

    remove_tree "$PLASMOID_DIR"
}

# ----------------------------------------------------------
# LIMPIEZA ESPECÍFICA: MATE
# ----------------------------------------------------------
cleanup_mate_runtime() {
    info "Removing MATE runtime registrations..."

    # Retirar únicamente el objeto de MATE Panel perteneciente a WMM
    # y sus keybindings. El resto de applets y atajos se conserva.
    if command -v python3 >/dev/null 2>&1; then
        APP_DIR="$APP_DIR" python3 <<'PY'
import os
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)

try:
    import gi
    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib
except Exception as error:
    print(f"[!!] Could not load Gio for MATE cleanup: {error}")
    raise SystemExit(0)


app_dir = os.environ.get("APP_DIR", "")
wmm_iid = "WMMAppletFactory::WMMApplet"

panel_schema = "org.mate.panel"
object_schema = "org.mate.panel.object"
object_base_path = "/org/mate/panel/objects/"

keybinding_schema = "org.mate.control-center.keybinding"
keybinding_base_path = "/org/mate/desktop/keybindings/"


def reset_settings(settings):
    for key in settings.list_keys():
        settings.reset(key)

def wait_for_frontend_shutdown(timeout_ms=3000):
    """Da a MATE Panel la oportunidad de retirar limpiamente el frontend."""
    loop = GLib.MainLoop()
    stopped = False
    timeout_fired = False

    def on_vanished(_connection, _name):
        nonlocal stopped
        stopped = True
        loop.quit()

    def on_timeout():
        nonlocal timeout_fired
        timeout_fired = True
        loop.quit()
        return GLib.SOURCE_REMOVE

    watch_id = Gio.bus_watch_name(
        Gio.BusType.SESSION,
        "org.maki.wmm.MateApplet",
        Gio.BusNameWatcherFlags.NONE,
        None,
        on_vanished,
    )
    timeout_id = GLib.timeout_add(timeout_ms, on_timeout)

    loop.run()
    Gio.bus_unwatch_name(watch_id)

    if not timeout_fired:
        GLib.source_remove(timeout_id)

    return stopped

# ----------------------------------------------------------
# MATE Panel applet registration(s)
# ----------------------------------------------------------
try:
    panel_settings = Gio.Settings.new(panel_schema)
    object_ids = list(panel_settings.get_strv("object-id-list"))
    wmm_ids = []

    for object_id in object_ids:
        settings = Gio.Settings.new_with_path(
            object_schema,
            f"{object_base_path}{object_id}/"
        )

        if (
            settings.get_string("object-type") == "applet"
            and settings.get_string("applet-iid") == wmm_iid
        ):
            wmm_ids.append(object_id)

    if wmm_ids:
        remaining_ids = [
            object_id
            for object_id in object_ids
            if object_id not in wmm_ids
        ]

        panel_settings.set_strv("object-id-list", remaining_ids)
        Gio.Settings.sync()

        if not wait_for_frontend_shutdown():
            print("[!!] MATE frontend did not stop cleanly; fallback cleanup will continue.")

        for object_id in wmm_ids:
            settings = Gio.Settings.new_with_path(
                object_schema,
                f"{object_base_path}{object_id}/"
            )
            reset_settings(settings)

        Gio.Settings.sync()

        print(
            f"[OK] Removed {len(wmm_ids)} "
            "WMM applet registration(s) from MATE Panel."
        )

except Exception as error:
    print(f"[!!] Could not clean MATE Panel registration: {error}")


# ----------------------------------------------------------
# MATE custom keybinding(s)
# ----------------------------------------------------------
removed_keybindings = 0

for index in range(100):
    try:
        settings = Gio.Settings.new_with_path(
            keybinding_schema,
            f"{keybinding_base_path}custom{index}/"
        )

        action = settings.get_string("action")
        action_lower = action.lower()

        belongs_to_wmm = (
            (app_dir and app_dir.lower() in action_lower)
            or "wmm@maki" in action_lower
        )

        is_wmm_rotation = (
            "force_rotation" in action_lower
            or "wmm-next.sh" in action_lower
        )

        if belongs_to_wmm and is_wmm_rotation:
            reset_settings(settings)
            removed_keybindings += 1

    except Exception:
        continue

if removed_keybindings:
    Gio.Settings.sync()

    print(
        f"[OK] Removed {removed_keybindings} "
        "WMM MATE keybinding(s)."
    )
PY
    fi

    # mate-applet.py pertenece exclusivamente a la integración MATE.
    # El engine, panel y About ya son tratados por stop_wmm_engine().
    if pgrep -f -- "$APP_DIR/mate-applet.py" >/dev/null 2>&1; then
        pkill -TERM -f -- "$APP_DIR/mate-applet.py" >/dev/null 2>&1 || true
    fi
}

# ----------------------------------------------------------
# RECURSOS DE INSTALACIÓN ESPECÍFICOS DEL ESCRITORIO
# ----------------------------------------------------------
cleanup_desktop_installation_resources() {
    case "$DESKTOP" in
        cinnamon)
            info "Removing Cinnamon launcher and D-Bus activation service..."

            remove_file "$LAUNCHER"
            remove_service_if_owned "$DBUS_SERVICE"

            # Posible nombre legacy: sólo se elimina si apunta
            # realmente a esta instalación Cinnamon.
            remove_service_if_owned "$DBUS_DIR/org.maki.wmm.service"
            ;;

        gnome)
            info "Removing GNOME launcher and D-Bus activation service..."

            remove_file "$LAUNCHER"
            remove_service_if_owned "$DBUS_SERVICE"

            # Posible nombre legacy: sólo se elimina si apunta
            # realmente a esta instalación GNOME.
            remove_service_if_owned "$DBUS_DIR/org.maki.wmm.service"
            ;;

        kde)
            info "Removing KDE launcher, autostart and D-Bus activation services..."

            remove_file "$LAUNCHER"
            remove_file "$AUTOSTART"

            remove_service_if_owned "$DBUS_SERVICE"
            remove_service_if_owned "$INSTALL_MANAGER_SERVICE"
            remove_service_if_owned "$DEBUG_LOG_VIEWER_SERVICE"
            ;;

        mate)
            info "Removing MATE D-Bus activation services..."

            # Servicio específico de la factoría MATE: pertenece
            # exclusivamente a WMM.
            remove_file "$MATE_DBUS_SERVICE"

            # Servicio común actual.
            remove_service_if_owned "$DBUS_SERVICE"

            # Posible nombre legacy: sólo si apunta a esta instalación.
            remove_service_if_owned "$DBUS_DIR/org.maki.wmm.service"

            info "Removing MATE launcher and legacy autostart entries..."

            remove_file "$LAUNCHER"

            # Entradas legacy bajo applications.
            remove_legacy_mate_entry_if_owned "$APPLICATIONS_DIR/wmm@maki.desktop"
            remove_legacy_mate_entry_if_owned "$APPLICATIONS_DIR/org.maki.wmm.desktop"

            # El instalador MATE actual no crea autostart, pero limpiamos
            # entradas específicas o legacy pertenecientes a WMM.
            remove_file "$AUTOSTART_DIR/org.maki.wmm.mate.desktop"
            remove_legacy_mate_entry_if_owned "$AUTOSTART_DIR/wmm@maki.desktop"
            remove_legacy_mate_entry_if_owned "$AUTOSTART_DIR/org.maki.wmm.desktop"

            # El descriptor de MATE Panel es el único recurso instalado
            # fuera del espacio XDG del usuario.
            info "Removing MATE Panel system descriptor..."

            IFS=':' read -r -a system_data_dirs <<< "$SYSTEM_DATA_DIRS"

            for data_dir in "${system_data_dirs[@]}"; do
                descriptor="$data_dir/mate-panel/applets/org.maki.wmm.mate-panel-applet"

                if [ -f "$descriptor" ] || [ -L "$descriptor" ]; then
                    if sudo rm -f -- "$descriptor"; then
                        ok "Removed: $descriptor"
                    else
                        warn "Could not remove MATE Panel descriptor: $descriptor"
                    fi
                fi
            done
            ;;
    esac
}

# ----------------------------------------------------------
# INTEGRACIONES DE GESTORES DE ARCHIVOS
# ----------------------------------------------------------
cleanup_file_manager_integrations() {
    info "Removing WMM file-manager integrations..."

    # ----------------------------------------------------------
    # Dolphin / KIO
    # ----------------------------------------------------------
    DOLPHIN_DIR="$DATA_HOME/kio/servicemenus"

    remove_file "$DOLPHIN_DIR/wmm-menu.desktop"
    remove_file "$DOLPHIN_DIR/wmm-add_to_bookmark.desktop"
    remove_file "$DOLPHIN_DIR/wmm-send-to.desktop"
    remove_file "$DOLPHIN_DIR/wmm-span-image.desktop"

    # Copias legacy de versiones anteriores.
    remove_file "$DOLPHIN_DIR/wmm-add_to_bookmarks.sh"
    remove_file "$DOLPHIN_DIR/wmm-send-to-monitor.sh"

    # ----------------------------------------------------------
    # Caja
    # ----------------------------------------------------------
    CAJA_ACTIONS_DIR="$DATA_HOME/file-manager/actions"
    CAJA_EXTENSIONS_DIR="$DATA_HOME/caja-python/extensions"

    remove_file "$CAJA_ACTIONS_DIR/wmm-menu.desktop"
    remove_file "$CAJA_ACTIONS_DIR/wmm-send-to-monitor.desktop"
    remove_file "$CAJA_ACTIONS_DIR/wmm-add-to-favorites.desktop"
    remove_file "$CAJA_EXTENSIONS_DIR/wmm-span-image.desktop"
    remove_file "$CAJA_EXTENSIONS_DIR/wmm-spanned-current.py"

    # ----------------------------------------------------------
    # Nemo
    # ----------------------------------------------------------
    NEMO_ACTIONS_DIR="$DATA_HOME/nemo/actions"

    remove_file "$NEMO_ACTIONS_DIR/wmm-send-to.nemo_action"
    remove_file "$NEMO_ACTIONS_DIR/wmm-add_to_bookmarks.nemo_action"
    remove_file "$NEMO_ACTIONS_DIR/wmm-span-image.nemo_action"
    remove_file "$NEMO_ACTIONS_DIR/wmm-spanned-current.nemo_action"

    # Copias legacy de versiones anteriores.
    remove_file "$NEMO_ACTIONS_DIR/wmm-add_to_bookmarks.sh"
    remove_file "$NEMO_ACTIONS_DIR/wmm-send-to-monitor.sh"

    # ----------------------------------------------------------
    # Nautilus
    # ----------------------------------------------------------
    NAUTILUS_EXTENSIONS_DIR="$DATA_HOME/nautilus-python/extensions"
    NAUTILUS_SCRIPTS_DIR="$DATA_HOME/nautilus/scripts"

    remove_file "$NAUTILUS_EXTENSIONS_DIR/wmm-nautilus.py"

    # Copias legacy de versiones anteriores.
    remove_file "$NAUTILUS_SCRIPTS_DIR/wmm-add_to_bookmarks.sh"
    remove_file "$NAUTILUS_SCRIPTS_DIR/wmm-send-to-monitor.sh"

    # Los gestores de archivos no se reinician durante la desinstalación.
    # Cualquier extensión que permanezca cargada desaparecerá al reiniciar sesión.
    #
    # actions-tree.json de Nemo se conserva porque pasa a ser configuración
    # del usuario una vez creado.
}

# ----------------------------------------------------------
# INSTALACIÓN ACTUAL Y DATOS COMPARTIDOS
# ----------------------------------------------------------
cleanup_installation_and_shared_data() {
    info "Removing the $DESKTOP_NAME WMM installation..."

    # APP_DIR pertenece íntegramente a la instalación WMM
    # del escritorio actual.
    remove_tree "$APP_DIR"

    # Cinnamon <= v1.2.2 utilizaba el UUID wmm-applet@maki.
    # Si todavía existe esa instalación legacy, retirarla también.
    if [ "$DESKTOP" = "cinnamon" ]; then
        remove_tree "$LEGACY_APP_DIR"
    fi

    # Cache y traducciones son recursos compartidos entre las
    # distintas instalaciones WMM del mismo usuario. Después de
    # retirar la actual, comprobar todas las ubicaciones conocidas.
    OTHER_WMM_INSTALL=0

    for other_dir in \
        "$DATA_HOME/cinnamon/applets/wmm@maki" \
        "$DATA_HOME/cinnamon/applets/wmm-applet@maki" \
        "$DATA_HOME/gnome-shell/extensions/wmm@maki" \
        "$DATA_HOME/plasma/org.maki.wmm" \
        "$DATA_HOME/plasma/plasmoids/org.maki.wmm" \
        "$DATA_HOME/wmm@maki"
    do
        if [ -d "$other_dir" ]; then
            OTHER_WMM_INSTALL=1
            break
        fi
    done

    if [ "$OTHER_WMM_INSTALL" -eq 0 ]; then
        remove_tree "$CACHE_DIR"

        # Eliminar únicamente los catálogos de traducción propios
        # de WMM; nunca se toca la jerarquía locale del usuario.
        if [ -d "$DATA_HOME/locale" ]; then
            while IFS= read -r -d '' mo_file; do
                remove_file "$mo_file"
            done < <(
                find "$DATA_HOME/locale" \
                    -type f \
                    \( \
                        -name 'wmm@maki.mo' \
                        -o -name 'wmm-applet@maki.mo' \
                        -o -name 'org.maki.wmm.mo' \
                    \) \
                    -print0 \
                    2>/dev/null
            )
        fi
    else
        info "Another WMM installation was detected; shared cache and translations were preserved."
    fi
}

# ----------------------------------------------------------
# REFRESCO DE D-BUS Y BASES DE APLICACIONES
# ----------------------------------------------------------
refresh_system_registries() {
    info "Refreshing D-Bus and application databases..."

    # Recargar la configuración de servicios de sesión para que
    # D-Bus descarte inmediatamente los servicios WMM eliminados.
    if command -v busctl >/dev/null 2>&1; then
        busctl --user call \
            org.freedesktop.DBus \
            /org/freedesktop/DBus \
            org.freedesktop.DBus \
            ReloadConfig \
            >/dev/null 2>&1 || true

    elif command -v dbus-send >/dev/null 2>&1; then
        dbus-send \
            --session \
            --type=method_call \
            --dest=org.freedesktop.DBus \
            /org/freedesktop/DBus \
            org.freedesktop.DBus.ReloadConfig \
            >/dev/null 2>&1 || true
    fi

    # Refrescar los launchers del usuario sin tocar el directorio
    # genérico de aplicaciones.
    if command -v update-desktop-database >/dev/null 2>&1 \
        && [ -d "$APPLICATIONS_DIR" ]; then
        update-desktop-database "$APPLICATIONS_DIR" >/dev/null 2>&1 || true
    fi

    # KDE mantiene además su propia caché de servicios/aplicaciones.
    if [ "$DESKTOP" = "kde" ] && command -v kbuildsycoca6 >/dev/null 2>&1; then
        kbuildsycoca6 >/dev/null 2>&1 || true
    fi
}

# ----------------------------------------------------------
# FINALIZACIÓN SEGÚN ESCRITORIO
# ----------------------------------------------------------
finalize_uninstall() {
    case "$DESKTOP" in
        cinnamon)
            # En X11, pedir a Cinnamon su reinicio nativo para que
            # desaparezca inmediatamente cualquier estado cargado del applet.
            if [ "$SESSION_TYPE" = "x11" ]; then
                echo
                info "Cinnamon will restart to complete the cleanup."
                info "Your open applications will remain running."

                if command -v dbus-send >/dev/null 2>&1; then
                    if dbus-send \
                        --session \
                        --print-reply \
                        --dest=org.Cinnamon \
                        /org/Cinnamon \
                        org.Cinnamon.RestartCinnamon \
                        boolean:true \
                        >/dev/null 2>&1; then

                        ok "Cinnamon restart requested through D-Bus."
                    else
                        warn "Could not request the Cinnamon restart through D-Bus."
                    fi
                else
                    warn "dbus-send is not available; Cinnamon was not restarted."
                fi
            else
                echo
                info "Cinnamon was not restarted because this is not a confirmed X11 session."
                info "Any remaining shell state will disappear after the next session restart."
            fi

            printf '\nWMM Cinnamon uninstall completed.\n'
            printf 'Installed dependencies were intentionally left untouched.\n'
            printf 'Your personal wallpaper files were not touched.\n'
            printf 'Cinnamon wallpaper settings were intentionally left untouched.\n\n'
            ;;

        gnome)
            printf '\nWMM GNOME uninstall completed.\n'
            printf 'Installed dependencies were intentionally left untouched.\n'
            printf 'Your personal wallpaper files were not touched.\n'
            printf 'GNOME wallpaper settings were intentionally left untouched.\n\n'
            ;;

        kde)
            printf '\nWMM KDE Plasma 6 uninstall completed.\n'
            printf 'Installed dependencies were intentionally left untouched.\n'
            printf 'Your personal wallpaper files were not touched.\n'
            printf 'Plasma wallpaper settings were intentionally left untouched.\n'
            printf 'You can select your preferred Plasma wallpaper plugin again if needed.\n\n'
            ;;

        mate)
            printf '\nWMM MATE uninstall completed.\n'
            printf 'Installed dependencies were intentionally left untouched.\n'
            printf 'MATE wallpaper settings were intentionally left untouched.\n\n'
            ;;
    esac
}

# ----------------------------------------------------------
# DETECCIÓN DE PLATAFORMA Y ESCRITORIO
# ----------------------------------------------------------
PLATFORM="$(uname -s | tr '[:upper:]' '[:lower:]')"

if [ "$PLATFORM" != "linux" ]; then
    warn "Unsupported platform: $PLATFORM"
    exit 1
fi

DESKTOP="${XDG_CURRENT_DESKTOP:-${DESKTOP_SESSION:-unknown}}"
DESKTOP=$(printf '%s' "$DESKTOP" | tr '[:upper:]' '[:lower:]')

# Mantener la misma normalización utilizada por install.sh.
case "$DESKTOP" in
    x-cinnamon|cinnamon2d) DESKTOP="cinnamon" ;;
    ubuntu*|gnome*)        DESKTOP="gnome" ;;
    kde*|plasma*)          DESKTOP="kde" ;;
    mate*)                 DESKTOP="mate" ;;
    *)                     DESKTOP="unknown" ;;
esac

if [ "$DESKTOP" = "unknown" ]; then
    warn "Could not detect a supported desktop environment."
    exit 1
fi


# ----------------------------------------------------------
# DETECCIÓN DEL TIPO DE SESIÓN
# ----------------------------------------------------------
# No se utiliza fallback para acciones dependientes de X11.
if [ -n "${WAYLAND_DISPLAY:-}" ]; then
    SESSION_TYPE="wayland"
elif [ "${XDG_SESSION_TYPE:-}" = "wayland" ]; then
    SESSION_TYPE="wayland"
elif [ "${XDG_SESSION_TYPE:-}" = "x11" ]; then
    SESSION_TYPE="x11"
else
    SESSION_TYPE="unknown"
fi


# ----------------------------------------------------------
# CABECERA
# ----------------------------------------------------------
case "$DESKTOP" in
    cinnamon) DESKTOP_NAME="Cinnamon" ;;
    gnome)    DESKTOP_NAME="GNOME Shell" ;;
    kde)      DESKTOP_NAME="KDE Plasma 6" ;;
    mate)     DESKTOP_NAME="MATE" ;;
esac

if [ "$DIRECT_CONSOLE" -eq 1 ]; then
    clear 2>/dev/null || true

    cols=$(tput cols 2>/dev/null || echo 80)
    line=$(printf '%*s' "$cols" | tr ' ' '=')

    text1="WMM - Wallpaper Multi-Monitor Manager"
    text2="$DESKTOP_NAME Uninstaller"

    pad1=$(( (cols - ${#text1}) / 2 ))
    pad2=$(( (cols - ${#text2}) / 2 ))

    [ "$pad1" -lt 0 ] && pad1=0
    [ "$pad2" -lt 0 ] && pad2=0

    echo ""
    printf "%s\n" "$line"
    printf "%*s%s\n" "$pad1" "" "$text1"
    printf "%*s%b\n" "$pad2" "" "${GREEN}${text2}${NC}"
    printf "%s\n\n" "$line"
fi

ok "$DESKTOP_NAME session detected."
info "Session type: $SESSION_TYPE"

# ----------------------------------------------------------
# RUTAS DE INSTALACIÓN SEGÚN ESCRITORIO
# ----------------------------------------------------------
case "$DESKTOP" in
    cinnamon)
        APP_DOMAIN="wmm@maki"
        APP_DIR="$DATA_HOME/cinnamon/applets/$APP_DOMAIN"

        # Instalaciones Cinnamon <= v1.2.2.
        LEGACY_APP_DOMAIN="wmm-applet@maki"
        LEGACY_APP_DIR="$DATA_HOME/cinnamon/applets/$LEGACY_APP_DOMAIN"

        LAUNCHER="$APPLICATIONS_DIR/org.maki.wmm.cinnamon.desktop"
        DBUS_SERVICE="$DBUS_DIR/$APP_DOMAIN.service"
        ;;

    gnome)
        APP_DOMAIN="wmm@maki"
        APP_DIR="$DATA_HOME/gnome-shell/extensions/$APP_DOMAIN"
        LAUNCHER="$APPLICATIONS_DIR/org.maki.wmm.gnome.desktop"
        DBUS_SERVICE="$DBUS_DIR/$APP_DOMAIN.service"
        ;;

    kde)
        APP_DOMAIN="org.maki.wmm"
        APP_DIR="$DATA_HOME/plasma/$APP_DOMAIN"
        PLASMOID_DIR="$DATA_HOME/plasma/plasmoids/$APP_DOMAIN"
        LAUNCHER="$APPLICATIONS_DIR/org.maki.wmm.desktop"
        AUTOSTART="$AUTOSTART_DIR/org.maki.wmm.desktop"
        DBUS_SERVICE="$DBUS_DIR/$APP_DOMAIN.service"
        INSTALL_MANAGER_SERVICE="$DBUS_DIR/$APP_DOMAIN.InstallManager.service"
        DEBUG_LOG_VIEWER_SERVICE="$DBUS_DIR/$APP_DOMAIN.DebugLogViewer.service"
        ;;

    mate)
        APP_DOMAIN="wmm@maki"
        APP_DIR="$DATA_HOME/$APP_DOMAIN"
        LAUNCHER="$APPLICATIONS_DIR/org.maki.wmm.mate.desktop"
        DBUS_SERVICE="$DBUS_DIR/$APP_DOMAIN.service"
        MATE_DBUS_SERVICE="$DBUS_DIR/org.mate.panel.applet.WMMAppletFactory.service"
        ;;
esac


# ----------------------------------------------------------
# PREFLIGHT: INSTALACIÓN WMM
# ----------------------------------------------------------
# Sólo cuentan artefactos propios del escritorio actual.
# Las integraciones de gestores de archivos son compartibles
# y no demuestran por sí mismas que WMM esté instalado aquí.
WMM_PRESENT=0

case "$DESKTOP" in
    cinnamon)
        [ -d "$APP_DIR" ] && WMM_PRESENT=1
        [ -d "$LEGACY_APP_DIR" ] && WMM_PRESENT=1
        [ -f "$LAUNCHER" ] && WMM_PRESENT=1

        for service_path in \
            "$DBUS_SERVICE" \
            "$DBUS_DIR/org.maki.wmm.service"
        do
            if [ -f "$service_path" ] && grep -Fq "$APP_DIR" "$service_path"; then
                WMM_PRESENT=1
                break
            fi
        done

        if command -v gsettings >/dev/null 2>&1; then
            enabled_applets=$(gsettings get org.cinnamon enabled-applets 2>/dev/null || true)

            if printf '%s\n' "$enabled_applets" \
                | grep -Eq 'wmm@maki|wmm-applet@maki'; then
                WMM_PRESENT=1
            fi
        fi

        if command -v dconf >/dev/null 2>&1; then
            if dconf dump /org/cinnamon/desktop/keybindings/custom-keybindings/ \
                2>/dev/null | grep -Eq 'wmm@maki|wmm-applet@maki'; then
                WMM_PRESENT=1
            fi
        fi
        ;;

    gnome)
        [ -d "$APP_DIR" ] && WMM_PRESENT=1
        [ -f "$LAUNCHER" ] && WMM_PRESENT=1

        for service_path in \
            "$DBUS_SERVICE" \
            "$DBUS_DIR/org.maki.wmm.service"
        do
            if [ -f "$service_path" ] && grep -Fq "$APP_DIR" "$service_path"; then
                WMM_PRESENT=1
                break
            fi
        done

        if command -v gnome-extensions >/dev/null 2>&1; then
            if gnome-extensions list 2>/dev/null | grep -Fxq "$APP_DOMAIN"; then
                WMM_PRESENT=1
            fi
        fi

        if command -v dconf >/dev/null 2>&1; then
            if dconf dump /org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/ \
                2>/dev/null | grep -Fq "$APP_DOMAIN"; then
                WMM_PRESENT=1
            fi
        fi
        ;;

    kde)
        [ -d "$APP_DIR" ] && WMM_PRESENT=1
        [ -d "$PLASMOID_DIR" ] && WMM_PRESENT=1
        [ -f "$LAUNCHER" ] && WMM_PRESENT=1
        [ -f "$AUTOSTART" ] && WMM_PRESENT=1

        for service_path in \
            "$DBUS_SERVICE" \
            "$INSTALL_MANAGER_SERVICE" \
            "$DEBUG_LOG_VIEWER_SERVICE"
        do
            if [ -f "$service_path" ] && grep -Fq "$APP_DIR" "$service_path"; then
                WMM_PRESENT=1
                break
            fi
        done

        if [ -f "$HOME/.config/kglobalshortcutsrc" ] \
            && grep -Fq "org.maki.wmm.desktop" "$HOME/.config/kglobalshortcutsrc"; then
            WMM_PRESENT=1
        fi
        ;;

    mate)
        [ -d "$APP_DIR" ] && WMM_PRESENT=1
        [ -f "$LAUNCHER" ] && WMM_PRESENT=1
        [ -f "$MATE_DBUS_SERVICE" ] && WMM_PRESENT=1

        for service_path in \
            "$DBUS_SERVICE" \
            "$DBUS_DIR/org.maki.wmm.service"
        do
            if [ -f "$service_path" ] && grep -Fq "$APP_DIR" "$service_path"; then
                WMM_PRESENT=1
                break
            fi
        done

        IFS=':' read -r -a system_data_dirs <<< "$SYSTEM_DATA_DIRS"
        for data_dir in "${system_data_dirs[@]}"; do
            if [ -f "$data_dir/mate-panel/applets/org.maki.wmm.mate-panel-applet" ]; then
                WMM_PRESENT=1
                break
            fi
        done

        if command -v dconf >/dev/null 2>&1; then
            if dconf dump /org/mate/panel/objects/ \
                2>/dev/null | grep -Fq "WMMAppletFactory::WMMApplet"; then
                WMM_PRESENT=1
            fi

            if dconf dump /org/mate/desktop/keybindings/ \
                2>/dev/null | grep -Fq "$APP_DOMAIN"; then
                WMM_PRESENT=1
            fi
        fi
        ;;
esac

if [ "$WMM_PRESENT" -eq 0 ]; then
    info "No WMM $DESKTOP_NAME installation or runtime registration was found."
    exit 0
fi

ok "WMM $DESKTOP_NAME installation detected."

if [ "$DIRECT_CONSOLE" -eq 1 ]; then
    echo
    echo "WMM and its desktop integration will be removed from this system."

    choice=""
    read -r -p "Do you want to continue? [y/N]: " choice || choice=""

    case "$choice" in
        y|Y|yes|YES|Yes)
            echo
            ;;
        *)
            info "Uninstallation cancelled."
            exit 0
            ;;
    esac
fi

# ----------------------------------------------------------
# 1. DETENER WMM Y LIMPIAR REGISTROS DEL ESCRITORIO
# ----------------------------------------------------------
stop_wmm_engine

case "$DESKTOP" in
    cinnamon)
        cleanup_cinnamon_runtime
        ;;

    gnome)
        cleanup_gnome_runtime
        ;;

    kde)
        cleanup_kde_runtime
        ;;

    mate)
        cleanup_mate_runtime
        ;;
esac

cleanup_desktop_installation_resources
cleanup_file_manager_integrations
cleanup_installation_and_shared_data
refresh_system_registries
finalize_uninstall
