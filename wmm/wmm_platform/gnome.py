"""
Módulo de plataforma para GNOME (Linux).
Contiene solo las implementaciones específicas de este entorno.
"""
import os
import glob
import subprocess
import time
import json
import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib
from debug_logger import log_event
from i18n import _

def get_install_path(data_base, app_domain):
    """Devuelve la ruta de instalación para GNOME."""
    return os.path.join(data_base, 'gnome-shell', 'extensions', app_domain)

def _force_desktop_settings(config_handler):
    """
    Fuerza los ajustes del sistema necesarios para que WMM funcione
    correctamente en GNOME:
      - picture-options     = 'spanned'  (no deformar el lienzo)
      - slideshow           = false      (evitar interferencias)
      - color-shading-type  = 'solid'    (evitar mezclas de color)
    """
    try:
        subprocess.run(
            ["gsettings", "set", "org.gnome.desktop.background", "picture-options", "spanned"],
            check=False
        )
        log_event("Forzando picture-options a 'spanned'", origin="GNOME", level="DEBUG", reason="HARDWARE")

        subprocess.run(
            ["gsettings", "set", "org.gnome.desktop.background", "picture-uri", ""],
            check=False
        )
        log_event("Desactivando slideshow", origin="GNOME", level="DEBUG", reason="HARDWARE")

        subprocess.run(
            ["gsettings", "set", "org.gnome.desktop.background", "color-shading-type", "solid"],
            check=False
        )
        log_event("Forzando color-shading-type a 'solid'", origin="GNOME", level="DEBUG", reason="HARDWARE")

        issues = []

        result = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.background", "picture-options"],
            capture_output=True, text=True
        )
        if result.stdout.strip().lower().replace("'", "") != "spanned":
            issues.append("Picture aspect")

        result = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.background", "color-shading-type"],
            capture_output=True, text=True
        )
        if result.stdout.strip().lower().replace("'", "") != "solid":
            issues.append("Background color type")

        if issues:
            log_event(
                f"No se pudieron forzar algunos ajustes: {', '.join(issues)}. Notificando al usuario.",
                origin="GNOME", level="WARN", reason="HARDWARE"
            )
            config_handler._send_notification(
                reason="WMM: " + _("Configuration issue"),
                detail_msg=_("For WMM to function correctly, please check the following settings in 'Settings > Background':")
                + "\n" + "\n".join(f"• {issue}" for issue in issues),
                level="warn"
            )
        else:
            log_event("Todos los ajustes del sistema forzados correctamente", origin="GNOME", level="DEBUG", reason="HARDWARE")

    except Exception as e:
        log_event(f"Error al forzar ajustes de GNOME: {e}", origin="GNOME", level="ERROR", reason="NOTIFY")

def set_wallpaper(path, config_handler=None):
    """Aplica el fondo de pantalla usando gsettings (GNOME)."""
    if config_handler:
        _force_desktop_settings(config_handler)
    subprocess.run(
        ["gsettings", "set", "org.gnome.desktop.background", "picture-uri", f"file://{path}"],
        check=False
    )
    # Aplicar también el fondo oscuro si la clave existe (GNOME 42+)
    try:
        result = subprocess.run(
            ["gsettings", "list-keys", "org.gnome.desktop.background"],
            capture_output=True, text=True, check=False
        )
        if "picture-uri-dark" in result.stdout:
            subprocess.run(
                ["gsettings", "set", "org.gnome.desktop.background", "picture-uri-dark", f"file://{path}"],
                check=False
            )
    except Exception:
        pass  # Si falla la verificación, simplemente no se aplica el fondo oscuro
    log_event("Fondo aplicado en GNOME", origin="GNOME", level="INFO", reason="LIBRARY")

def ensure_keybindings(app_dir):
    """
    Crea el atajo "WMM - Next Background" si aún no existe.

    app_dir: ruta de instalación
             (ej. ~/.local/share/gnome-shell/extensions/wmm@maki)
    """

    # ----------------------------------------------------------
    # 1. Construir ruta del script
    # ----------------------------------------------------------
    script_path = os.path.join(
        app_dir,
        "wmm_platform",
        "shell",
        "gnome",
        "wmm-next.sh"
    )

    if not os.path.exists(script_path):
        log_event(f"Script no encontrado: {script_path}", origin="GNOME", level="WARN", reason="SETTINGS")
        return

    # ----------------------------------------------------------
    # 2. Asegurar permisos de ejecución
    # ----------------------------------------------------------
    if not os.access(script_path, os.X_OK):
        try:
            os.chmod(script_path, 0o755)
            log_event(f"Permisos de ejecución añadidos a {script_path}", origin="GNOME", level="INFO", reason="SETTINGS")
        except Exception as e:
            log_event(f"No se pudieron establecer permisos: {e}", origin="GNOME", level="WARN", reason="SETTINGS")

    # ----------------------------------------------------------
    # 3. Nombre traducido
    # ----------------------------------------------------------
    name = _("Next Background")
    full_name = f"WMM- {name}"

    # ----------------------------------------------------------
    # 4. Esquemas GSettings
    # ----------------------------------------------------------
    schema_main = "org.gnome.settings-daemon.plugins.media-keys"
    schema_custom = "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding"

    base_path = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/"

    try:
        settings = Gio.Settings.new(schema_main)
    except GLib.GError as e:
        log_event(f"Error al acceder al esquema '{schema_main}': {e}", origin="GNOME", level="ERROR", reason="SETTINGS")
        return

    # ----------------------------------------------------------
    # 5. Obtener lista actual
    # ----------------------------------------------------------
    current_list = settings.get_strv("custom-keybindings")

    # ----------------------------------------------------------
    # 6. ¿Ya existe un atajo de WMM?
    # ----------------------------------------------------------
    for path in current_list:
        try:
            existing = Gio.Settings.new_with_path(schema_custom, path)

            if existing.get_string("command") == script_path:
                log_event("Atajo de WMM ya instalado", origin="GNOME", level="INFO", reason="SETTINGS")
                return

        except GLib.GError:
            continue

    # ----------------------------------------------------------
    # 7. Calcular siguiente índice libre
    # ----------------------------------------------------------
    import re

    pattern = re.compile(
        rf"{re.escape(base_path)}custom(\d+)/"
    )

    indices = [
        int(match.group(1))
        for path in current_list
        for match in [pattern.search(path)]
        if match
    ]

    next_index = max(indices) + 1 if indices else 0

    new_path = f"{base_path}custom{next_index}/"

    # ----------------------------------------------------------
    # 8. Crear nuevo atajo
    # ----------------------------------------------------------
    try:
        custom = Gio.Settings.new_with_path(schema_custom, new_path)

        custom.set_strv("binding", [])
        custom.set_string("command", script_path)
        custom.set_string("name", full_name)
        custom.set_boolean("enable-in-lockscreen", False)

        custom.sync()

    except GLib.GError as e:
        log_event(f"Error al escribir el atajo en {new_path}: {e}", origin="GNOME", level="ERROR", reason="SETTINGS")
        return

    # ----------------------------------------------------------
    # 9. Añadir a la lista principal
    # ----------------------------------------------------------
    current_list.append(new_path)

    settings.set_strv("custom-keybindings", current_list)
    settings.sync()

    log_event(f"Atajo GNOME creado: {full_name}", origin="GNOME", level="INFO", reason="SETTINGS")
