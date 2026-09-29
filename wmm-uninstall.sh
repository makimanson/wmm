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
UNINSTALL_SCOPE=""

# Una anomalía al cerrar procesos WMM nunca bloquea la retirada. Se conserva
# únicamente para recomendar al final un reinicio de sesión de cortesía.
SESSION_RESTART_RECOMMENDED=0
UNINSTALL_SESSION_RESTART_STATUS=10

case "${1:-}" in
    --managed)
        MANAGED=1

        case "${2:-}" in
            --current)
                UNINSTALL_SCOPE="current"
                ;;
            --all|"")
                # Compatibilidad con el Install Manager actual, cuya
                # confirmación corresponde a una desinstalación completa.
                UNINSTALL_SCOPE="all"
                ;;
            *)
                printf '[!!] Unknown uninstall scope: %s\n' "$2" >&2
                exit 2
                ;;
        esac
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
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
STATE_HOME="${XDG_STATE_HOME:-$HOME/.local/state}"
CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"
SYSTEM_DATA_DIRS="${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"

CACHE_DIR="$CACHE_HOME/wmm"
DBUS_DIR="$DATA_HOME/dbus-1/services"
APPLICATIONS_DIR="$DATA_HOME/applications"
AUTOSTART_DIR="$CONFIG_HOME/autostart"

# Topología común de WMM. El core, la configuración y el estado son únicos;
# cada escritorio aporta únicamente su propia integración.
WMM_ROOT="$DATA_HOME/wmm@maki"
WMM_CONFIG="$CONFIG_HOME/wmm@maki"
WMM_STATE="$STATE_HOME/wmm"
WMM_DBUS_SERVICE="$DBUS_DIR/org.maki.wmm.service"
WMM_LEGACY_DBUS_SERVICE="$DBUS_DIR/wmm@maki.service"

# Integraciones de escritorio conocidas.
CINNAMON_FRONTEND="$DATA_HOME/cinnamon/applets/wmm@maki"
CINNAMON_LEGACY_FRONTEND="$DATA_HOME/cinnamon/applets/wmm-applet@maki"
CINNAMON_LAUNCHER="$APPLICATIONS_DIR/org.maki.wmm.cinnamon.desktop"

GNOME_FRONTEND="$DATA_HOME/gnome-shell/extensions/wmm@maki"
GNOME_LAUNCHER="$APPLICATIONS_DIR/org.maki.wmm.gnome.desktop"

KDE_LEGACY_ROOT="$DATA_HOME/plasma/org.maki.wmm"
KDE_PLASMOID="$DATA_HOME/plasma/plasmoids/org.maki.wmm"
KDE_LAUNCHER="$APPLICATIONS_DIR/org.maki.wmm.kde.desktop"
KDE_AUTOSTART="$AUTOSTART_DIR/org.maki.wmm.kde.desktop"
KDE_LEGACY_LAUNCHER="$APPLICATIONS_DIR/org.maki.wmm.desktop"
KDE_LEGACY_AUTOSTART="$AUTOSTART_DIR/org.maki.wmm.desktop"
KDE_INSTALL_MANAGER_SERVICE="$DBUS_DIR/org.maki.wmm.InstallManager.service"
KDE_DEBUG_LOG_VIEWER_SERVICE="$DBUS_DIR/org.maki.wmm.DebugLogViewer.service"

MATE_FRONTEND="$WMM_ROOT/frontends/mate"
MATE_LAUNCHER="$APPLICATIONS_DIR/org.maki.wmm.mate.desktop"
MATE_DBUS_SERVICE="$DBUS_DIR/org.mate.panel.applet.WMMAppletFactory.service"

XFCE_LAUNCHER="$APPLICATIONS_DIR/org.maki.wmm.xfce.desktop"
XFCE_AUTOSTART="$AUTOSTART_DIR/org.maki.wmm.xfce.desktop"
XFCE_NEXT="/usr/local/bin/wmm-next.sh"

ok()   { printf '[OK] %s\n' "$1"; }
info() { printf '[..] %s\n' "$1"; }
warn() { printf '[!!] %s\n' "$1" >&2; }

# ----------------------------------------------------------
# HELPERS DE LIMPIEZA
# ----------------------------------------------------------

# Los procesos WMM no pueden bloquear una desinstalación solicitada. pidfd
# conserva la identidad exacta durante el cierre normal y forzado. Cualquier
# anomalía se registra para recomendar un nuevo inicio de sesión, pero nunca
# impide retirar los archivos y recursos propiedad de WMM.
terminate_pids_and_wait() {
    local timeout_ms="$1"
    local python_status
    shift

    [ "$#" -gt 0 ] || return 0

    # WMM necesita Python para funcionar, pero una instalación dañada podría
    # haberlo perdido. La ausencia del helper no convierte WMM en indesinstalable.
    if ! command -v python3 >/dev/null 2>&1; then
        warn "Python 3 is unavailable; forcing captured WMM processes directly."
        kill -KILL "$@" >/dev/null 2>&1 || true
        SESSION_RESTART_RECOMMENDED=1
        return 0
    fi

    python3 - "$timeout_ms" "$@" <<'PY'
import os
import select
import signal
import sys
import time

timeout_ms = int(sys.argv[1])
pids = list(dict.fromkeys(int(value) for value in sys.argv[2:]))

# Códigos internos:
#   0  cierre confirmado;
#   10 cierre forzado pero con alguna anomalía o confirmación pendiente;
#   20 no puede utilizarse pidfd y el shell debe aplicar el fallback final.
if not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal"):
    print(
        "[!!] pidfd process control is unavailable.",
        file=sys.stderr,
    )
    raise SystemExit(20)

poller = select.poll()
pidfds = {}
warning = False


def wait_until(deadline):
    while pidfds:
        remaining_ms = int(max(0.0, deadline - time.monotonic()) * 1000)

        if remaining_ms <= 0:
            return False

        try:
            events = poller.poll(remaining_ms)
        except InterruptedError:
            continue

        if not events:
            return False

        for fd, _event in events:
            if fd not in pidfds:
                continue

            poller.unregister(fd)
            os.close(fd)
            del pidfds[fd]

    return True


def send_signal(sig):
    global warning

    for fd, pid in tuple(pidfds.items()):
        try:
            signal.pidfd_send_signal(fd, sig)
        except ProcessLookupError:
            pass
        except OSError as error:
            warning = True
            print(
                f"[!!] Could not send {signal.Signals(sig).name} "
                f"to WMM PID {pid}: {error}",
                file=sys.stderr,
            )


try:
    # Abrir primero todos los pidfd fija la identidad exacta de los procesos
    # antes de enviar señales y evita actuar después sobre un PID reutilizado.
    for pid in pids:
        try:
            fd = os.pidfd_open(pid)
        except ProcessLookupError:
            continue
        except OSError as error:
            warning = True
            print(
                f"[!!] Could not open pidfd for WMM PID {pid}: {error}",
                file=sys.stderr,
            )

            # Si pidfd falla para una captura ya identificada, intentar igualmente
            # la retirada forzada y dejar la sesión como última frontera de higiene.
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except OSError as kill_error:
                print(
                    f"[!!] Could not force WMM PID {pid}: {kill_error}",
                    file=sys.stderr,
                )
            continue

        pidfds[fd] = pid
        poller.register(fd, select.POLLIN | select.POLLHUP | select.POLLERR)

    if not pidfds:
        raise SystemExit(10 if warning else 0)

    # SIGTERM conserva la oportunidad de una salida normal.
    send_signal(signal.SIGTERM)

    if wait_until(time.monotonic() + timeout_ms / 1000.0):
        raise SystemExit(10 if warning else 0)

    # La voluntad de desinstalar prevalece sobre cualquier proceso WMM
    # resistente: agotada la cortesía, su terminación se fuerza.
    send_signal(signal.SIGKILL)

    if wait_until(time.monotonic() + timeout_ms / 1000.0):
        raise SystemExit(10 if warning else 0)

    # Linux permite retirar el árbol aunque un proceso conserve referencias
    # abiertas. La sesión posterior eliminará cualquier superviviente anómalo.
    survivors = ", ".join(str(pid) for pid in sorted(pidfds.values()))
    print(
        f"[!!] Termination could not be confirmed for WMM PID(s): "
        f"{survivors}. Continuing complete removal.",
        file=sys.stderr,
    )
    raise SystemExit(10)

finally:
    for fd in tuple(pidfds):
        try:
            os.close(fd)
        except OSError:
            pass
PY

    python_status=$?

    case "$python_status" in
        0)
            return 0
            ;;

        10)
            SESSION_RESTART_RECOMMENDED=1
            return 0
            ;;

        *)
            # Un fallo de la propia vía reactiva tampoco concede al proceso
            # autoridad para conservar WMM instalado.
            warn "Reactive WMM shutdown encountered an error; forcing captured processes directly."
            kill -KILL "$@" >/dev/null 2>&1 || true
            SESSION_RESTART_RECOMMENDED=1
            return 0
            ;;
    esac
}

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

# wmm@maki.service pertenece a topologías anteriores de WMM, pero vive
# en un directorio D-Bus compartido. Sólo retirarlo si su Exec conserva
# la firma estructural del engine WMM.
remove_legacy_wmm_service_if_owned() {
    local path="$1"

    [ -f "$path" ] || return

    if grep -Fq '/wmm@maki/' "$path" \
        && grep -Fq '/python/main.py' "$path"; then

        remove_file "$path"
    else
        warn "Preserved legacy D-Bus service because it does not identify itself as WMM: $path"
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

# Las extensiones Python externas pueden dejar bytecode tras retirar su fuente.
# __pycache__ pertenece al entorno compartido: sólo se eliminan archivos WMM.
remove_python_bytecode() {
    local extensions_dir="$1"
    local module_name="$2"
    local cache_dir="$extensions_dir/__pycache__"
    local pyc_file

    [ -d "$cache_dir" ] || return

    while IFS= read -r -d '' pyc_file; do
        remove_file "$pyc_file"
    done < <(
        find "$cache_dir" \
            -maxdepth 1 \
            -type f \
            -name "${module_name}.*.pyc" \
            -print0 \
            2>/dev/null
    )
}

remove_wmm_next_if_owned() {
    local path="$1"

    if [ ! -f "$path" ]; then
        return
    fi

    # /usr/local/bin queda fuera del espacio XDG de WMM.
    # Sólo se elimina si conserva la firma de autoría del helper original.
    if grep -Fqx '# SPDX-FileCopyrightText: 2026 makimanson' "$path"; then
        if sudo rm -f -- "$path"; then
            ok "Removed: $path"
        else
            warn "Could not remove: $path"
        fi
    else
        warn "Preserved helper because it does not identify itself as a WMM file: $path"
    fi
}

# Comprueba sin activar el servicio si org.maki.wmm tiene owner en la sesión.
dbus_owner() {
    command -v dbus-send >/dev/null 2>&1 || return 1

    dbus-send \
        --session \
        --print-reply \
        --dest=org.freedesktop.DBus \
        /org/freedesktop/DBus \
        org.freedesktop.DBus.NameHasOwner \
        string:org.maki.wmm \
        2>/dev/null | grep -q 'boolean true'
}

# ----------------------------------------------------------
# PARADA DEL ENGINE COMÚN
# ----------------------------------------------------------
stop_wmm_engine() {
    local target="${1:-$DESKTOP}"
    local -a roots=("$WMM_ROOT")
    local -a targets=("$target")
    local -a patterns=()
    local -a process_pids=()
    local -a remaining_pids=()
    local integration root pattern pid ancestor parent
    local -A protected_pids=()

    info "Stopping WMM..."

    # Solicitar el cierre coordinado una sola vez: org.maki.wmm pertenece
    # al engine común, no a ninguna integración de escritorio concreta.
    if dbus_owner; then
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

    # Una desinstalación completa debe cubrir también procesos heredados
    # de cualquier integración detectada, aunque no pertenezcan al escritorio
    # desde el que se está ejecutando el uninstaller.
    if [ "$UNINSTALL_SCOPE" = "all" ]; then
        targets=("${INSTALLED_INTEGRATIONS[@]}")
    fi

    for integration in "${targets[@]}"; do
        case "$integration" in
            cinnamon)
                roots+=(
                    "$CINNAMON_FRONTEND"
                    "$CINNAMON_LEGACY_FRONTEND"
                )
                ;;

            gnome)
                roots+=("$GNOME_FRONTEND")
                ;;

            kde)
                roots+=("$KDE_LEGACY_ROOT")
                ;;
        esac
    done

    # Inventariar los procesos comunes que pueden seguir ejecutando código
    # desde cualquiera de los árboles WMM que la desinstalación va a retirar.
    for root in "${roots[@]}"; do
        [ -n "$root" ] || continue

        patterns+=(
            "$root/python/main.py"
            "$root/python/panel.py"
            "$root/python/about.py"
            "$root/python/debug_log_viewer.py"
            "$root/python/docs_viewer.py"
            "$root/python/add_bookmark.py"
            "$root/python/shell_add_bookmark.py"
            "$root/python/shell_send_to_monitor.py"
            "$root/python/send_command.py"
            "$root/wmm_platform/shell/installer/wmm-install_manager.py"
        )
    done

    # Si el desinstalador está siendo ejecutado desde el Install Manager,
    # ese manager forma parte de la cadena ancestral que mantiene vivo el VTE.
    # Proteger los ancestros evita cortar el propio canal de desinstalación;
    # cualquier otra instancia WMM equivalente continúa siendo terminable.
    ancestor="$$"

    while [[ "$ancestor" =~ ^[0-9]+$ ]] && [ "$ancestor" -gt 1 ]; do
        protected_pids["$ancestor"]=1

        parent="$(
            ps -o ppid= -p "$ancestor" 2>/dev/null \
                | tr -d '[:space:]'
        )"

        [ -n "$parent" ] || break
        [ "$parent" != "$ancestor" ] || break

        ancestor="$parent"
    done

    # Capturar una sola vez las instancias todavía vivas. La identidad queda
    # fijada después por pidfd antes de enviar ninguna señal.
    mapfile -t process_pids < <(
        for pattern in "${patterns[@]}"; do
            pgrep -f -- "$pattern" || true
        done | sort -u
    )

    remaining_pids=()

    for pid in "${process_pids[@]}"; do
        [ -n "${protected_pids[$pid]:-}" ] || remaining_pids+=("$pid")
    done

    if [ "${#remaining_pids[@]}" -gt 0 ]; then
        terminate_pids_and_wait 2000 "${remaining_pids[@]}"
    fi

    # Una instancia puede aparecer mientras se cierra la captura anterior.
    # Esta segunda captura es una barrera puntual contra reapariciones, no
    # polling: no existe espera ni sondeo periódico.
    mapfile -t process_pids < <(
        for pattern in "${patterns[@]}"; do
            pgrep -f -- "$pattern" || true
        done | sort -u
    )

    remaining_pids=()

    for pid in "${process_pids[@]}"; do
        [ -n "${protected_pids[$pid]:-}" ] || remaining_pids+=("$pid")
    done

    if [ "${#remaining_pids[@]}" -gt 0 ]; then
        warn "WMM processes reappeared while stopping; forcing them again."
        terminate_pids_and_wait 2000 "${remaining_pids[@]}"
    fi

    # La comprobación final sólo informa del estado real. Si todavía aparece
    # algún proceso WMM, se fuerza una última vez y se continúa retirando el
    # árbol: Linux permite desvincular sus archivos aunque conserve referencias
    # abiertas, y un nuevo inicio de sesión eliminará cualquier superviviente.
    mapfile -t process_pids < <(
        for pattern in "${patterns[@]}"; do
            pgrep -f -- "$pattern" || true
        done | sort -u
    )

    remaining_pids=()

    for pid in "${process_pids[@]}"; do
        [ -n "${protected_pids[$pid]:-}" ] || remaining_pids+=("$pid")
    done

    if [ "${#remaining_pids[@]}" -gt 0 ]; then
        warn "Some WMM processes are still visible after forced shutdown: ${remaining_pids[*]}"
        warn "Complete removal will continue; a new login session will be recommended."
        kill -KILL "${remaining_pids[@]}" >/dev/null 2>&1 || true
        SESSION_RESTART_RECOMMENDED=1
    else
        ok "WMM processes stopped."
    fi

    return 0
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
        local component shortcut_result removed=0 failed=0

        for component in \
            org.maki.wmm.kde.desktop \
            org.maki.wmm.desktop
        do
            shortcut_result=$(dbus-send \
                --session \
                --type=method_call \
                --print-reply \
                --dest=org.kde.kglobalaccel \
                /kglobalaccel \
                org.kde.KGlobalAccel.unregister \
                string:"$component" \
                string:next-background \
                2>/dev/null || true)

            if [[ "$shortcut_result" == *"boolean true"* ]]; then
                removed=1
            elif [[ "$shortcut_result" == *"boolean false"* ]]; then
                :
            elif [ -n "$shortcut_result" ]; then
                warn "Unexpected response while removing KDE global shortcut '$component': $shortcut_result"
                failed=1
            else
                warn "Could not remove KDE global shortcut '$component' through KGlobalAccel."
                failed=1
            fi
        done

        if [ "$removed" -eq 1 ]; then
            ok "KDE global shortcut removed."
        elif [ "$failed" -eq 0 ]; then
            info "KDE global shortcut was not registered."
        fi
    else
        warn "dbus-send is not available; KDE global shortcut could not be removed automatically."
    fi

    # ----------------------------------------------------------
    # Registro del plasmoide WMM
    # ----------------------------------------------------------
    info "Removing Plasma widget registration..."

    if command -v kpackagetool6 >/dev/null 2>&1; then
        kpackagetool6 -t Plasma/Applet -r org.maki.wmm >/dev/null 2>&1 || true
    fi
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

    # Red de seguridad para el frontend MATE actual y para instalaciones legacy.
    # El camino normal sigue siendo la retirada limpia desde MATE Panel; cualquier
    # superviviente se captura una sola vez y pasa por la política común TERM/KILL.
    local -a mate_pids=()

    mapfile -t mate_pids < <(
        {
            pgrep -f -- "$FRONTEND_DIR/mate-applet.py" || true
            pgrep -f -- "$APP_DIR/mate-applet.py" || true
        } | sort -u
    )

    if [ "${#mate_pids[@]}" -gt 0 ]; then
        warn "MATE frontend is still running after panel cleanup; forcing final shutdown."
        terminate_pids_and_wait 2000 "${mate_pids[@]}"
    fi
}

# ----------------------------------------------------------
# LIMPIEZA ESPECÍFICA: XFCE
# ----------------------------------------------------------
cleanup_xfce_runtime() {
    info "Removing XFCE runtime registrations..."

    local property command
    local removed_keybindings=0
    local -a xfce_pids=()

    # El frontend XFCE es un proceso residente independiente del engine.
    # Capturarlo una sola vez permite aplicar la política común TERM/KILL
    # sin polling antes de retirar el árbol desde el que se ejecutaba.
    mapfile -t xfce_pids < <(
        pgrep -f -- "$FRONTEND_DIR/xfce-frontend.py" || true
    )

    if [ "${#xfce_pids[@]}" -gt 0 ]; then
        terminate_pids_and_wait 2000 "${xfce_pids[@]}"
    fi

    command -v xfconf-query >/dev/null 2>&1 || {
        warn "xfconf-query is not available; XFCE shortcut registration could not be cleaned."
        return
    }

    # La propiedad cambia cuando el usuario asigna una combinación real.
    # Identificar WMM por el comando conserva intactos los demás atajos.
    while read -r property command; do
        [ "$command" = "wmm-next.sh" ] || continue

        if xfconf-query \
            -c xfce4-keyboard-shortcuts \
            -p "$property" \
            -r \
            >/dev/null 2>&1; then

            removed_keybindings=$((removed_keybindings + 1))
        else
            warn "Could not remove XFCE shortcut: $property"
        fi
    done < <(
        xfconf-query \
            -c xfce4-keyboard-shortcuts \
            -p /commands/custom \
            -lv \
            2>/dev/null
    )

    if [ "$removed_keybindings" -gt 0 ]; then
        ok "Removed $removed_keybindings WMM XFCE keyboard shortcut(s)."
    fi
}

# ----------------------------------------------------------
# LIMPIEZA RUNTIME DE UNA INTEGRACIÓN
# ----------------------------------------------------------
cleanup_desktop_runtime() {
    local target="${1:-$DESKTOP}"

    # Las funciones específicas existentes utilizan estas variables.
    # Se resuelven aquí para que puedan limpiar cualquier integración
    # instalada, independientemente del escritorio de la sesión actual.
    local APP_DIR=""
    local APP_DOMAIN=""
    local LEGACY_APP_DIR=""
    local LEGACY_APP_DOMAIN=""
    local FRONTEND_DIR=""

    case "$target" in
        cinnamon)
            APP_DIR="$CINNAMON_FRONTEND"
            APP_DOMAIN="wmm@maki"
            LEGACY_APP_DIR="$CINNAMON_LEGACY_FRONTEND"
            LEGACY_APP_DOMAIN="wmm-applet@maki"
            cleanup_cinnamon_runtime
            ;;

        gnome)
            APP_DIR="$GNOME_FRONTEND"
            APP_DOMAIN="wmm@maki"
            cleanup_gnome_runtime
            ;;

        kde)
            cleanup_kde_runtime
            ;;

        mate)
            APP_DIR="$WMM_ROOT"
            FRONTEND_DIR="$MATE_FRONTEND"
            cleanup_mate_runtime
            ;;

        xfce)
            FRONTEND_DIR="$WMM_ROOT/frontends/xfce"
            cleanup_xfce_runtime
            ;;
    esac
}

# ----------------------------------------------------------
# RECURSOS DE INSTALACIÓN ESPECÍFICOS DEL ESCRITORIO
# ----------------------------------------------------------
cleanup_desktop_installation_resources() {
    local target="${1:-$DESKTOP}"
    local data_dir descriptor
    local -a system_data_dirs

    case "$target" in
        cinnamon)
            info "Removing Cinnamon integration resources..."

            remove_tree "$CINNAMON_FRONTEND"
            remove_tree "$CINNAMON_LEGACY_FRONTEND"
            remove_file "$CINNAMON_LAUNCHER"
            ;;

        gnome)
            info "Removing GNOME integration resources..."

            remove_tree "$GNOME_FRONTEND"
            remove_file "$GNOME_LAUNCHER"
            ;;

        kde)
            info "Removing KDE integration resources..."

            remove_tree "$KDE_LEGACY_ROOT"
            remove_tree "$KDE_PLASMOID"
            remove_file "$KDE_LAUNCHER"
            remove_file "$KDE_AUTOSTART"
            remove_file "$KDE_LEGACY_LAUNCHER"
            remove_file "$KDE_LEGACY_AUTOSTART"

            # Los nombres D-Bus son exclusivos de herramientas WMM/KDE.
            # Se eliminan por identidad para cubrir también topologías legacy.
            remove_file "$KDE_INSTALL_MANAGER_SERVICE"
            remove_file "$KDE_DEBUG_LOG_VIEWER_SERVICE"
            ;;

        mate)
            info "Removing MATE integration resources..."

            remove_tree "$MATE_FRONTEND"
            remove_file "$MATE_DBUS_SERVICE"
            remove_file "$MATE_LAUNCHER"

            # Limpieza legacy: MATE <= 1.4.x alojaba estos ejecutables
            # directamente en la raíz común de WMM.
            remove_file "$WMM_ROOT/mate-applet.py"
            remove_file "$WMM_ROOT/mate-launcher.py"

            # Descriptor de MATE Panel instalado fuera del espacio XDG.
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

        xfce)
            info "Removing XFCE integration resources..."

            remove_tree "$WMM_ROOT/frontends/xfce"
            remove_file "$XFCE_LAUNCHER"
            remove_file "$XFCE_AUTOSTART"

            # /usr/local/bin es compartido con el resto del sistema.
            remove_wmm_next_if_owned "$XFCE_NEXT"
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
    remove_file "$CAJA_ACTIONS_DIR/wmm-span-image.desktop"
    remove_file "$CAJA_EXTENSIONS_DIR/wmm-desktop-actions.py"
    remove_python_bytecode "$CAJA_EXTENSIONS_DIR" "wmm-desktop-actions"

    # Copia legacy de versiones anteriores.
    remove_file "$CAJA_EXTENSIONS_DIR/wmm-spanned-current.py"
    remove_python_bytecode "$CAJA_EXTENSIONS_DIR" "wmm-spanned-current"

    # caja-actions.conf pertenece a Caja Actions, no a WMM. Retirar
    # únicamente nuestros identificadores del orden de nivel cero y
    # conservar íntegramente el resto de la configuración del usuario.
    CAJA_CONFIG="$CONFIG_HOME/caja-actions/caja-actions.conf"

    if [ -f "$CAJA_CONFIG" ]; then
        if python3 - "$CAJA_CONFIG" <<'PY'
import os
import re
import stat
import sys
import tempfile

path = sys.argv[1]

wmm_items = {
    "wmm-menu",
    "wmm-span-image",
    "wmm-send-to-monitor",
    "wmm-add-to-favorites",
}

key_pattern = re.compile(
    r'^(\s*items-level-zero-order\s*=\s*)(.*?)(\r?\n)?$')

section = None
changed = False
updated = []

def split_keyfile_list(value):
    """Separa una lista GLib sin interpretar separadores escapados."""
    items = []
    current = []
    escaped = False

    for char in value:
        if escaped:
            current.append(char)
            escaped = False
            continue

        if char == "\\":
            current.append(char)
            escaped = True
            continue

        if char == ";":
            items.append("".join(current))
            current = []
            continue

        current.append(char)

    if current:
        items.append("".join(current))

    return items

with open(path, "r", encoding="utf-8", newline="") as f:
    lines = f.readlines()

for line in lines:
    stripped = line.strip()

    if stripped.startswith("[") and stripped.endswith("]"):
        section = stripped[1:-1]

    if section == "runtime":
        match = key_pattern.match(line)

        if match:
            prefix, value, newline = match.groups()
            items = split_keyfile_list(value)
            cleaned = [item for item in items if item not in wmm_items]

            if cleaned != items:
                serialized = ";".join(cleaned)

                if serialized:
                    serialized += ";"

                line = prefix + serialized + (newline or "")
                changed = True

    updated.append(line)

if changed:
    mode = stat.S_IMODE(os.stat(path).st_mode)
    directory = os.path.dirname(path)

    fd, temp_path = tempfile.mkstemp(
        prefix=".caja-actions.conf.wmm.",
        dir=directory)

    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.writelines(updated)

        os.chmod(temp_path, mode)
        os.replace(temp_path, path)

    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise
PY
        then
            info "Caja Actions WMM ordering entries removed from $CAJA_CONFIG"
        else
            warn "Could not clean WMM ordering entries from $CAJA_CONFIG"
        fi
    fi
    # ----------------------------------------------------------
    # Nemo
    # ----------------------------------------------------------
    NEMO_ACTIONS_DIR="$DATA_HOME/nemo/actions"
    NEMO_LAYOUT="$CONFIG_HOME/nemo/actions-tree.json"

    remove_file "$NEMO_ACTIONS_DIR/wmm-send-to.nemo_action"
    remove_file "$NEMO_ACTIONS_DIR/wmm-add_to_bookmarks.nemo_action"
    remove_file "$NEMO_ACTIONS_DIR/wmm-span-image.nemo_action"
    remove_file "$NEMO_ACTIONS_DIR/wmm-spanned-current.nemo_action"
    remove_file "$NEMO_ACTIONS_DIR/wmm-add_favorite_current.nemo_action"

    # Copias legacy de versiones anteriores.
    remove_file "$NEMO_ACTIONS_DIR/wmm-add_to_bookmarks.sh"
    remove_file "$NEMO_ACTIONS_DIR/wmm-send-to-monitor.sh"

    # Retirar únicamente la estructura perteneciente a WMM. Si el usuario
    # colocó elementos ajenos dentro de sus submenús, se conservan y promocionan
    # al nivel donde estaba el submenú eliminado.
    if [ -f "$NEMO_LAYOUT" ]; then
        if python3 - "$NEMO_LAYOUT" <<'PY'
import json
import os
import stat
import sys
import tempfile

path = sys.argv[1]

wmm_submenus = {
    "WMM Manager",
    "WMM Manager0",
}

wmm_actions = {
    "wmm-add_to_bookmarks.nemo_action",
    "wmm-send-to.nemo_action",
    "wmm-span-image.nemo_action",
    "wmm-spanned-current.nemo_action",
    "wmm-add_favorite_current.nemo_action",
}


def strip_wmm_structure(nodes):
    cleaned = []
    changed = False

    for node in nodes:
        if not isinstance(node, dict):
            cleaned.append(node)
            continue

        children = node.get("children")
        if isinstance(children, list):
            children, child_changed = strip_wmm_structure(children)
            node["children"] = children
            changed = changed or child_changed

        node_uuid = node.get("uuid")
        node_type = node.get("type")

        if node_type == "submenu" and node_uuid in wmm_submenus:
            if isinstance(node.get("children"), list):
                cleaned.extend(node["children"])
            changed = True
            continue

        if node_type == "action" and node_uuid in wmm_actions:
            changed = True
            continue

        cleaned.append(node)

    return cleaned, changed


try:
    with open(path, "r", encoding="utf-8") as f:
        layout = json.load(f)

    toplevel = layout.get("toplevel")
    if not isinstance(toplevel, list):
        raise ValueError("actions-tree.json has no valid toplevel list")

    layout["toplevel"], changed = strip_wmm_structure(toplevel)

    if changed:
        mode = stat.S_IMODE(os.stat(path).st_mode)
        directory = os.path.dirname(path)
        fd, temp_path = tempfile.mkstemp(
            prefix=".actions-tree.json.wmm.",
            dir=directory)

        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                json.dump(layout, f, ensure_ascii=False, indent=2)

            os.chmod(temp_path, mode)
            os.replace(temp_path, path)

        except Exception:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise

        # Nemo 6.6.x reacciona a una escritura completada sobre el archivo,
        # no únicamente al replace atómico.
        with open(path, "rb") as f:
            persisted_layout = f.read()
        with open(path, "wb") as f:
            f.write(persisted_layout)

except Exception as error:
    print(f"[!!] Could not clean Nemo actions-tree.json: {error}")
    raise SystemExit(1)
PY
        then
            info "Nemo WMM layout removed from $NEMO_LAYOUT"
        else
            warn "Could not remove WMM structure from $NEMO_LAYOUT"
        fi
    fi

    remove_file "$WMM_STATE/nemo-layout-initialized"
    remove_file "$WMM_STATE/nemo-desktop-layout-initialized"

    # ----------------------------------------------------------
    # Nautilus
    # ----------------------------------------------------------
    NAUTILUS_EXTENSIONS_DIR="$DATA_HOME/nautilus-python/extensions"
    NAUTILUS_SCRIPTS_DIR="$DATA_HOME/nautilus/scripts"

    remove_file "$NAUTILUS_EXTENSIONS_DIR/wmm-nautilus.py"
    remove_python_bytecode "$NAUTILUS_EXTENSIONS_DIR" "wmm-nautilus"

    # Copias legacy de versiones anteriores.
    remove_file "$NAUTILUS_SCRIPTS_DIR/wmm-add_to_bookmarks.sh"
    remove_file "$NAUTILUS_SCRIPTS_DIR/wmm-send-to-monitor.sh"

    # ----------------------------------------------------------
    # Thunar
    # ----------------------------------------------------------
    THUNAR_UCA="$CONFIG_HOME/Thunar/uca.xml"
    THUNARX_EXTENSIONS_DIR="$DATA_HOME/thunarx-python/extensions"

    remove_file "$THUNARX_EXTENSIONS_DIR/wmm-xfce-desktop.py"
    remove_python_bytecode "$THUNARX_EXTENSIONS_DIR" "wmm-xfce-desktop"

    if [ -f "$THUNAR_UCA" ]; then
        if python3 - "$THUNAR_UCA" <<'PY'
import os
import re
import stat
import sys
import tempfile

path = sys.argv[1]

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

pattern = re.compile(r"<action\b[^>]*>.*?</action>", re.DOTALL)
marker = "<submenu>WMM Manager</submenu>"

updated = pattern.sub(
    lambda match: "" if marker in match.group(0) else match.group(0),
    content)

if updated != content:
    mode = stat.S_IMODE(os.stat(path).st_mode)
    fd, temp_path = tempfile.mkstemp(
        prefix=".uca.xml.wmm.",
        dir=os.path.dirname(path))

    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(updated)

        os.chmod(temp_path, mode)
        os.replace(temp_path, path)

    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise
PY
        then
            info "Thunar WMM actions removed from $THUNAR_UCA"
        else
            warn "Could not remove WMM actions from $THUNAR_UCA"
        fi
    fi

    # Los gestores de archivos no se reinician durante la desinstalación.
    # Cualquier extensión que permanezca cargada desaparecerá al reiniciar sesión.
    #
    # actions-tree.json de Nemo se conserva como configuración del usuario;
    # únicamente se retiran de él los nodos pertenecientes a WMM.
}

# ----------------------------------------------------------
# INSTALACIÓN ACTUAL Y DATOS COMPARTIDOS
# ----------------------------------------------------------
cleanup_installation_and_shared_data() {
    # Una desinstalación de integración conserva íntegramente WMM.
    if [ "$UNINSTALL_SCOPE" != "all" ]; then
        info "Shared WMM core, configuration and data were preserved."
        return
    fi

    info "Removing shared WMM installation and data..."

    # Impedir nuevas activaciones antes de retirar el core. El servicio
    # legacy se elimina sólo si todavía conserva una firma inequívoca de WMM.
    remove_file "$WMM_DBUS_SERVICE"
    remove_legacy_wmm_service_if_owned "$WMM_LEGACY_DBUS_SERVICE"

    remove_tree "$WMM_ROOT"
    remove_tree "$WMM_CONFIG"
    remove_tree "$CACHE_DIR"
    remove_tree "$WMM_STATE"

    # Eliminar únicamente los catálogos de traducción propios de WMM;
    # nunca se toca la jerarquía locale del usuario.
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
    # Las acciones sobre el escritorio activo sólo tienen sentido cuando
    # realmente se ha retirado su integración WMM.
    if [ "$CURRENT_INTEGRATION_PRESENT" -eq 1 ]; then
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
                ;;
        esac
    fi

    if [ "$UNINSTALL_SCOPE" = "all" ]; then
        printf '\nWMM uninstall completed.\n'
        printf 'Installed dependencies were intentionally left untouched.\n'
        printf 'Your personal wallpaper files were not touched.\n'
        printf 'Desktop wallpaper settings were intentionally left untouched.\n'

        if [ "$CURRENT_INTEGRATION_PRESENT" -eq 1 ] && [ "$DESKTOP" = "kde" ]; then
            printf 'You can select your preferred Plasma wallpaper plugin again if needed.\n'
        fi

        printf '\n'
        return
    fi

    case "$DESKTOP" in
        cinnamon)
            printf '\nWMM Cinnamon integration uninstall completed.\n'
            printf 'Installed dependencies were intentionally left untouched.\n'
            printf 'Your personal wallpaper files were not touched.\n'
            printf 'Cinnamon wallpaper settings were intentionally left untouched.\n\n'
            ;;

        gnome)
            printf '\nWMM GNOME integration uninstall completed.\n'
            printf 'Installed dependencies were intentionally left untouched.\n'
            printf 'Your personal wallpaper files were not touched.\n'
            printf 'GNOME wallpaper settings were intentionally left untouched.\n\n'
            ;;

        kde)
            printf '\nWMM KDE Plasma 6 integration uninstall completed.\n'
            printf 'Installed dependencies were intentionally left untouched.\n'
            printf 'Your personal wallpaper files were not touched.\n'
            printf 'Plasma wallpaper settings were intentionally left untouched.\n'
            printf 'You can select your preferred Plasma wallpaper plugin again if needed.\n\n'
            ;;

        mate)
            printf '\nWMM MATE integration uninstall completed.\n'
            printf 'Installed dependencies were intentionally left untouched.\n'
            printf 'MATE wallpaper settings were intentionally left untouched.\n\n'
            ;;

        xfce)
            printf '\nWMM XFCE integration uninstall completed.\n'
            printf 'Installed dependencies were intentionally left untouched.\n'
            printf 'XFCE wallpaper settings were intentionally left untouched.\n\n'
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
    xfce*)                 DESKTOP="xfce" ;;
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
    xfce)     DESKTOP_NAME="XFCE" ;;
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
# INVENTARIO DE INTEGRACIONES WMM
# ----------------------------------------------------------
# El core común no identifica ningún escritorio concreto. Una integración
# existe únicamente cuando conserva algún artefacto propio de ese escritorio.
INSTALLED_INTEGRATIONS=()

detect_installed_integrations() {
    local enabled_applets="" data_dir
    local mate_descriptor_present=0
    local -a system_data_dirs

    INSTALLED_INTEGRATIONS=()

    # Cinnamon: frontend actual, topología legacy o registros de sesión.
    if [ -d "$CINNAMON_FRONTEND" ] \
        || [ -d "$CINNAMON_LEGACY_FRONTEND" ] \
        || [ -f "$CINNAMON_LAUNCHER" ]; then

        INSTALLED_INTEGRATIONS+=("cinnamon")

    elif command -v gsettings >/dev/null 2>&1; then
        enabled_applets=$(gsettings get org.cinnamon enabled-applets 2>/dev/null || true)

        if printf '%s\n' "$enabled_applets" \
            | grep -Eq 'wmm@maki|wmm-applet@maki'; then

            INSTALLED_INTEGRATIONS+=("cinnamon")

        elif command -v dconf >/dev/null 2>&1 \
            && dconf dump /org/cinnamon/desktop/keybindings/custom-keybindings/ \
                2>/dev/null | grep -Eq 'wmm@maki|wmm-applet@maki'; then

            INSTALLED_INTEGRATIONS+=("cinnamon")
        fi

    elif command -v dconf >/dev/null 2>&1 \
        && dconf dump /org/cinnamon/desktop/keybindings/custom-keybindings/ \
            2>/dev/null | grep -Eq 'wmm@maki|wmm-applet@maki'; then

        INSTALLED_INTEGRATIONS+=("cinnamon")
    fi

    # GNOME: extensión, launcher o registros propios de GNOME Shell.
    if [ -d "$GNOME_FRONTEND" ] || [ -f "$GNOME_LAUNCHER" ]; then
        INSTALLED_INTEGRATIONS+=("gnome")

    elif command -v gnome-extensions >/dev/null 2>&1 \
        && gnome-extensions list 2>/dev/null | grep -Fxq 'wmm@maki'; then

        INSTALLED_INTEGRATIONS+=("gnome")

    elif command -v dconf >/dev/null 2>&1 \
        && dconf dump /org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/ \
            2>/dev/null | grep -Fq 'wmm@maki'; then

        INSTALLED_INTEGRATIONS+=("gnome")
    fi

    # KDE: aceptar tanto la topología actual como la identidad publicada
    # anteriormente bajo el nombre genérico.
    if [ -d "$KDE_LEGACY_ROOT" ] \
        || [ -d "$KDE_PLASMOID" ] \
        || [ -f "$KDE_LAUNCHER" ] \
        || [ -f "$KDE_AUTOSTART" ] \
        || [ -f "$KDE_LEGACY_LAUNCHER" ] \
        || [ -f "$KDE_LEGACY_AUTOSTART" ] \
        || [ -f "$KDE_INSTALL_MANAGER_SERVICE" ] \
        || [ -f "$KDE_DEBUG_LOG_VIEWER_SERVICE" ]; then

        INSTALLED_INTEGRATIONS+=("kde")

    elif [ -f "$HOME/.config/kglobalshortcutsrc" ] \
        && grep -Eq 'org\.maki\.wmm(\.kde)?\.desktop' "$HOME/.config/kglobalshortcutsrc"; then

        INSTALLED_INTEGRATIONS+=("kde")
    fi

    # MATE: frontend actual, recursos externos o restos legacy.
    IFS=':' read -r -a system_data_dirs <<< "$SYSTEM_DATA_DIRS"

    for data_dir in "${system_data_dirs[@]}"; do
        if [ -f "$data_dir/mate-panel/applets/org.maki.wmm.mate-panel-applet" ]; then
            mate_descriptor_present=1
            break
        fi
    done

    if [ -d "$MATE_FRONTEND" ] \
        || [ -f "$MATE_LAUNCHER" ] \
        || [ -f "$MATE_DBUS_SERVICE" ] \
        || [ -f "$WMM_ROOT/mate-applet.py" ] \
        || [ -f "$WMM_ROOT/mate-launcher.py" ] \
        || [ "$mate_descriptor_present" -eq 1 ]; then

        INSTALLED_INTEGRATIONS+=("mate")

    elif command -v dconf >/dev/null 2>&1 \
        && {
            dconf dump /org/mate/panel/objects/ 2>/dev/null \
                | grep -Fq 'WMMAppletFactory::WMMApplet' \
            || dconf dump /org/mate/desktop/keybindings/ 2>/dev/null \
                | grep -Fq 'wmm@maki'
        }; then

        INSTALLED_INTEGRATIONS+=("mate")
    fi

    # XFCE: frontend propio, launcher/autostart, helper o atajo registrado.
    if [ -d "$WMM_ROOT/frontends/xfce" ] \
        || [ -f "$XFCE_LAUNCHER" ] \
        || [ -f "$XFCE_AUTOSTART" ]; then

        INSTALLED_INTEGRATIONS+=("xfce")

    elif [ -f "$XFCE_NEXT" ] \
        && grep -Fqx '# SPDX-FileCopyrightText: 2026 makimanson' "$XFCE_NEXT"; then

        INSTALLED_INTEGRATIONS+=("xfce")

    elif command -v xfconf-query >/dev/null 2>&1 \
        && xfconf-query \
            -c xfce4-keyboard-shortcuts \
            -p /commands/custom \
            -lv \
            2>/dev/null \
            | grep -Eq '[[:space:]]wmm-next\.sh[[:space:]]*$'; then

        INSTALLED_INTEGRATIONS+=("xfce")
    fi
}

# ----------------------------------------------------------
# PREFLIGHT: INTEGRACIONES Y ALCANCE
# ----------------------------------------------------------
detect_installed_integrations

CURRENT_INTEGRATION_PRESENT=0
OTHER_INTEGRATIONS=()

for integration in "${INSTALLED_INTEGRATIONS[@]}"; do
    if [ "$integration" = "$DESKTOP" ]; then
        CURRENT_INTEGRATION_PRESENT=1
    else
        OTHER_INTEGRATIONS+=("$integration")
    fi
done

# Un alcance "all" pertenece a WMM completo, no al escritorio desde el
# que se ejecuta. Debe poder reparar también instalaciones incompletas.
if [ "$UNINSTALL_SCOPE" = "all" ]; then
    if [ "$CURRENT_INTEGRATION_PRESENT" -eq 1 ]; then
        ok "WMM $DESKTOP_NAME integration detected."
    else
        info "No WMM $DESKTOP_NAME integration was found; complete uninstall will continue."
    fi

    if [ "${#OTHER_INTEGRATIONS[@]}" -gt 0 ]; then
        info "Other WMM desktop integrations detected: ${OTHER_INTEGRATIONS[*]}"
    fi

else
    if [ "$CURRENT_INTEGRATION_PRESENT" -eq 0 ]; then
        info "No WMM $DESKTOP_NAME integration was found."
        exit 0
    fi

    ok "WMM $DESKTOP_NAME integration detected."

    # Sin otras integraciones, retirar la actual equivale necesariamente
    # a retirar WMM completo: no debe quedar un core sin frontend.
    if [ "${#OTHER_INTEGRATIONS[@]}" -eq 0 ]; then
        UNINSTALL_SCOPE="all"

        if [ "$DIRECT_CONSOLE" -eq 1 ]; then
            echo
            echo "WMM and its $DESKTOP_NAME integration will be removed from this system."

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

        elif [ "$MANAGED" -eq 0 ]; then
            warn "Non-interactive uninstall requires an explicit managed scope."
            exit 2
        fi

    else
        info "Other WMM desktop integrations detected: ${OTHER_INTEGRATIONS[*]}"

        # Sólo la consola directa decide aquí. En modo gestionado el alcance
        # debe haber llegado ya explícitamente desde la interfaz que confirmó.
        if [ -z "$UNINSTALL_SCOPE" ]; then
            if [ "$DIRECT_CONSOLE" -eq 0 ]; then
                warn "Multiple WMM desktop integrations were detected but no uninstall scope was provided."
                exit 2
            fi

            echo
            echo "Choose what you want to uninstall:"
            echo "  1) WMM integration for $DESKTOP_NAME only"
            echo "  2) WMM completely, including all desktop integrations"
            echo "  3) Cancel"
            echo

            choice=""
            read -r -p "Selection [1-3]: " choice || choice=""

            case "$choice" in
                1)
                    UNINSTALL_SCOPE="current"
                    echo
                    ;;
                2)
                    UNINSTALL_SCOPE="all"
                    echo
                    ;;
                *)
                    info "Uninstallation cancelled."
                    exit 0
                    ;;
            esac
        fi
    fi
fi

# ----------------------------------------------------------
# 1. DETENER WMM
# ----------------------------------------------------------
stop_wmm_engine "$DESKTOP"

# ----------------------------------------------------------
# 2. RETIRAR INTEGRACIONES DE ESCRITORIO
# ----------------------------------------------------------
if [ "$UNINSTALL_SCOPE" = "current" ]; then
    info "Removing only the $DESKTOP_NAME WMM integration..."

    cleanup_desktop_runtime "$DESKTOP"
    cleanup_desktop_installation_resources "$DESKTOP"

else
    info "Removing all WMM desktop integrations..."

    for integration in "${INSTALLED_INTEGRATIONS[@]}"; do
        cleanup_desktop_runtime "$integration"
        cleanup_desktop_installation_resources "$integration"
    done
fi

# ----------------------------------------------------------
# 3. RETIRAR RECURSOS GLOBALES
# ----------------------------------------------------------
if [ "$UNINSTALL_SCOPE" = "all" ]; then
    cleanup_file_manager_integrations
fi

cleanup_installation_and_shared_data
refresh_system_registries
finalize_uninstall
if [ "$SESSION_RESTART_RECOMMENDED" -eq 1 ]; then
    echo
    warn "WMM was removed, but one or more running processes could not be fully verified during shutdown."
    info "Log out and log back in to ensure that no process from the previous WMM installation remains active."
    exit "$UNINSTALL_SESSION_RESTART_STATUS"
fi
