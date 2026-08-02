"""
Módulo de plataforma para Linux.
Contiene funciones comunes a todos los escritorios de Linux.
"""
import os
import subprocess
import fcntl
import shutil
import hashlib

from wmm_platform.file_utils import lock_file, unlock_file
from debug_logger import log_event

def _generate_gdk_wayland_hash(connector, manufacturer, x, y, width, height):
    """Hash estable para Wayland basado en modelo y posición."""
    return hashlib.shake_128(f"{connector}-{manufacturer}-{x}-{y}-{width}-{height}".encode()).hexdigest(4)

# Registro de generadores de hash por motor gráfico
HASH_GENERATORS = {
    'wayland': _generate_gdk_wayland_hash,
}

def generate_hash_for_engine(graphics_engine, connector, manufacturer, x, y, width, height):
    """
    Devuelve un hash estable para el monitor, usando el generador
    correspondiente al motor gráfico indicado.
    """
    generator = HASH_GENERATORS.get(graphics_engine, get_x11_monitors)
    return generator(connector, manufacturer, x, y, width, height)

def ensure_shell_actions(app_root, data_base):
    """
    Detecta qué gestores de archivos (Nemo, Nautilus, Dolphin) están realmente
    instalados en el SO y copia sus scripts de integración correspondientes.
    Opera de forma agnóstica al escritorio activo.
    
    Nota: En Plasma 6, los archivos .desktop para Dolphin deben tener permisos
    de ejecución (chmod +x) para ser reconocidos como servicios válidos.
    """
    source_dir = os.path.join(app_root, "wmm_platform", "shell", "file_manager")
    if not os.path.isdir(source_dir):
        return

    # --- 1. LIMPIEZA DE DIRECTORIOS ANTIGUOS (legacy) ---
    legacy_dirs = [
        os.path.join(app_root, "wmm_platform", "shell", "nemo"),
        os.path.join(app_root, "wmm_platform", "shell", "nautilus")
    ]
    for old_dir in legacy_dirs:
        if os.path.isdir(old_dir):
            try:
                shutil.rmtree(old_dir)
                log_event(f"Directorio legacy eliminado: {old_dir}", origin="LINUX", level="INFO", reason="SETTINGS")
            except Exception as e:
                log_event(f"No se pudo eliminar {old_dir}: {e}", origin="LINUX", level="WARN", reason="SETTINGS")

    # --- 2. DEFINICIÓN DE GESTORES Y SUS RUTAS ---
    managers = {
        "nemo": (os.path.join(data_base, "nemo", "actions"), (".nemo_action", ".sh")),
        "nautilus": (os.path.join(data_base, "nautilus", "scripts"), (".sh",)),
        "dolphin": (os.path.join(data_base, "kio", "servicemenus"), (".desktop", ".sh"))
    }

    # --- 3. DETECCIÓN Y COPIA ---
    for binary, (target_dir, extensions) in managers.items():
        if not shutil.which(binary):
            continue

        os.makedirs(target_dir, exist_ok=True)

        for action_file in os.listdir(source_dir):
            if action_file.endswith(extensions):
                src = os.path.join(source_dir, action_file)
                dst = os.path.join(target_dir, action_file)
                try:
                    shutil.copy2(src, dst)
                    # Establecer permisos de ejecución:
                    # - .sh siempre se ejecuta (necesario para scripts)
                    # - .desktop necesita ejecución en Plasma 6 (Dolphin)
                    # - .nemo_action no necesita ejecución
                    if action_file.endswith(".sh") or action_file.endswith(".desktop"):
                        os.chmod(dst, 0o755)
                        log_event(f"Permisos de ejecución establecidos para {action_file}", origin="LINUX", level="DEBUG", reason="SETTINGS")
                except Exception as e:
                    log_event(f"Error copiando {action_file} a {target_dir}: {e}", origin="LINUX", level="WARN", reason="SETTINGS")

        log_event(f"Integración con {binary.capitalize()} verificada/instalada en {target_dir}", origin="LINUX", level="INFO", reason="SETTINGS")

def normalize_platform(raw_platform):
    if raw_platform.startswith('linux'):
        return 'linux'
    return raw_platform

def normalize_desktop(desktop):
    desktop = desktop.lower()
    if desktop.startswith('x-cinnamon') or desktop == 'cinnamon2d':
        return 'cinnamon'
    if 'gnome' in desktop:
        return 'gnome'
    if 'plasma' in desktop:
        return 'kde'
    return desktop

def detect_desktop():
    desktop = os.environ.get('XDG_CURRENT_DESKTOP',
                             os.environ.get('DESKTOP_SESSION', 'unknown'))
    return desktop.lower()

def get_system_paths():
    data_base = os.environ.get('XDG_DATA_HOME',
                               os.path.expanduser('~/.local/share'))
    cache_base = os.environ.get('XDG_CACHE_HOME',
                                os.path.expanduser('~/.cache'))
    locale_dir = os.path.join(data_base, 'locale')
    cache_dir = os.path.join(cache_base, 'wmm')
    return {
        'data_base': data_base,
        'cache_base': cache_base,
        'locale_dir': locale_dir,
        'cache_dir': cache_dir,
    }

def open_file(path):
    subprocess.run(['xdg-open', path], check=False)

def compile_translations(app_root, locale_dir, app_domain):
    po_dir = os.path.join(app_root, "po")
    if not os.path.isdir(po_dir):
        return
    for po_file in os.listdir(po_dir):
        if not po_file.endswith(".po"):
            continue
        lang = os.path.splitext(po_file)[0]
        mo_dir = os.path.join(locale_dir, lang, "LC_MESSAGES")
        mo_file = os.path.join(mo_dir, f"{app_domain}.mo")
        po_path = os.path.join(po_dir, po_file)
        if not os.path.exists(mo_file) or os.path.getmtime(po_path) > os.path.getmtime(mo_file):
            try:
                os.makedirs(mo_dir, exist_ok=True)
                result = subprocess.run(
                    ["msgfmt", po_path, "-o", mo_file],
                    check=False,
                    capture_output=True,
                    text=True
                )
                if result.returncode != 0:
                    log_event(f"Error compilando traducción '{po_file}': {result.stderr.strip()}", origin="LINUX", level="ERROR", reason="SETTINGS")
            except Exception as e:
                log_event(f"Excepción compilando traducción '{po_file}': {e}", origin="LINUX", level="ERROR", reason="SETTINGS")

def send_notification(title, message, level="info"):
    icon_map = {
        "info": "dialog-information-symbolic",
        "warn": "dialog-warning-symbolic",
        "error": "dialog-error-symbolic"
    }
    selected_icon = icon_map.get(level, "dialog-information")
    try:
        subprocess.run([
            "notify-send",
            "-i", selected_icon,
            title,
            message,
            "-a", "WMM"
        ], check=False)
    except Exception as e:
        print(f" [!] Error en notificación: {e}")

def init_channels():
    """
    Registra todos los canales de comunicación soportados por Linux.

    La función expone al núcleo todos los mecanismos de comunicación
    disponibles en este sistema operativo. No decide qué cliente
    utilizará cada canal; únicamente los registra para que la
    infraestructura de comunicación de WMM pueda utilizarlos.
    """

    from wmm_platform.channels import register_channel, DBusChannel, FileChannel

    # FileChannel
    try:
        register_channel("file", FileChannel())
        log_event("Canal File registrado", origin="LINUX", level="INFO", reason="COMMAND")
    except Exception as e:
        log_event(f"No se pudo registrar FileChannel: {e}", origin="LINUX", level="ERROR", reason="COMMAND")

    # D-Bus
    try:
        register_channel("dbus", DBusChannel())
        log_event("Canal D-Bus registrado", origin="LINUX", level="INFO", reason="COMMAND")
    except Exception as e:
        log_event(f"No se pudo registrar DBusChannel: {e}", origin="LINUX", level="ERROR", reason="COMMAND")
