"""
Módulo de plataforma para Cinnamon (Linux).
Contiene solo las implementaciones específicas de este entorno.
"""
import os
import glob
import hashlib
import subprocess
import time
import json
import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib
from debug_logger import log_event
from i18n import _

# Variable global para mantener vivo el monitor de archivos
_monitor = None

def get_install_path(data_base, app_domain):
    """Devuelve la ruta de instalación para Cinnamon."""
    return os.path.join(data_base, 'cinnamon', 'applets', app_domain)

def _force_desktop_settings(config_handler):
    """
    Fuerza los ajustes del sistema necesarios para que WMM funcione
    correctamente en Cinnamon:
      - picture-options     = 'spanned'  (no deformar el lienzo)
      - slideshow           = false      (evitar interferencias)
      - color-shading-type  = 'solid'    (evitar mezclas de color)
    Verifica cada ajuste y notifica al usuario si alguno no se aplicó.
    """
    try:
        subprocess.run(
            ["gsettings", "set", "org.cinnamon.desktop.background", "picture-options", "spanned"],
            check=False
        )
        log_event("Forzando picture-options a 'spanned'", origin="DESKTOP", level="DEBUG", reason="HARDWARE")

        subprocess.run(
            ["gsettings", "set", "org.cinnamon.desktop.background.slideshow", "slideshow-enabled", "false"],
            check=False
        )
        log_event("Forzando slideshow a 'false'", origin="DESKTOP", level="DEBUG", reason="HARDWARE")

        subprocess.run(
            ["gsettings", "set", "org.cinnamon.desktop.background", "color-shading-type", "solid"],
            check=False
        )
        log_event("Forzando color-shading-type a 'solid'", origin="DESKTOP", level="DEBUG", reason="HARDWARE")

        issues = []

        result = subprocess.run(
            ["gsettings", "get", "org.cinnamon.desktop.background", "picture-options"],
            capture_output=True, text=True
        )
        if result.stdout.strip().lower().replace("'", "") != "spanned":
            issues.append("Picture aspect")

        result = subprocess.run(
            ["gsettings", "get", "org.cinnamon.desktop.background.slideshow", "slideshow-enabled"],
            capture_output=True, text=True
        )
        if result.stdout.strip().lower() != "false":
            issues.append("Slideshow")

        result = subprocess.run(
            ["gsettings", "get", "org.cinnamon.desktop.background", "color-shading-type"],
            capture_output=True, text=True
        )
        if result.stdout.strip().lower().replace("'", "") != "solid":
            issues.append("Background color type")

        if issues:
            log_event(
                f"No se pudieron forzar algunos ajustes: {', '.join(issues)}. Notificando al usuario.",
                origin="DESKTOP", level="WARN", reason="HARDWARE"
            )
            config_handler._send_notification(
                reason="WMM: " + _("Configuration issue"),
                detail_msg=_("For WMM to function correctly, please check the following settings in 'System Settings > Backgrounds':")
                + "\n" + "\n".join(f"• {issue}" for issue in issues),
                level="warn"
            )
        else:
            log_event("Todos los ajustes del sistema forzados correctamente", origin="DESKTOP", level="DEBUG", reason="HARDWARE")

    except Exception as e:
        log_event(f"Error al forzar ajustes de Cinnamon: {e}", origin="DESKTOP", level="ERROR", reason="NOTIFY")

def set_wallpaper(final_path, config_handler):
    """
    Aplica el fondo de pantalla usando gsettings (Cinnamon).
    Fuerza los ajustes del sistema y aplica una transición suave.
    """
    from PIL import Image

    _force_desktop_settings(config_handler)

    try:
        settings = config_handler.load_json("settings").get("global", {})
        sl_mode = settings.get("slideshow_mode", "sync")

        if sl_mode == "sync":
            from gi.repository import Gdk
            result_color = subprocess.run(
                ["gsettings", "get", "org.cinnamon.desktop.background", "primary-color"],
                capture_output=True, text=True
            )
            color_str = result_color.stdout.strip().lower().replace("'", "")
            rgba = Gdk.RGBA()
            if rgba.parse(color_str):
                r = int(rgba.red * 255)
                g = int(rgba.green * 255)
                b = int(rgba.blue * 255)
            else:
                r, g, b = 0, 0, 0
            fade_color_path = os.path.join(config_handler.cache_dir, "fade_color.png")
            Image.new('RGB', (1, 1), (r, g, b)).save(fade_color_path)

            os.system(f"gsettings set org.cinnamon.desktop.background picture-uri 'file://{fade_color_path}'")
            time.sleep(1.5)
            os.system(f"gsettings set org.cinnamon.desktop.background picture-uri 'file://{final_path}'")
            log_event("Transición Cine aplicada (sync)", origin="DESKTOP", level="INFO", reason="LIBRARY")
        else:
            os.system(f"gsettings set org.cinnamon.desktop.background picture-uri 'file://{final_path}'")
            log_event("Transicion Crossfade aplicada (async)", origin="DESKTOP", level="INFO", reason="LIBRARY")

    except Exception as e:
        log_event(f"Cinnamon no respondió: {e}", origin="DESKTOP", level="ERROR", reason="NOTIFY")

def ensure_keybindings(app_dir):
    """
    Instala el atajo de teclado de WMM si todavía no existe.

    No modifica atajos existentes del usuario.
    Si el atajo de WMM ya está registrado, simplemente termina.
    """
    import re

    # ----------------------------------------------------------
    # 1. Ruta del script
    # ----------------------------------------------------------
    script_path = os.path.join(app_dir, "wmm_platform", "shell", "cinnamon", "wmm-next.sh")

    if not os.path.exists(script_path):
        log_event(f"Script no encontrado: {script_path}", origin="DESKTOP", level="WARN", reason="SETTINGS")
        return

    # ----------------------------------------------------------
    # 2. Permisos
    # ----------------------------------------------------------
    if not os.access(script_path, os.X_OK):
        try:
            os.chmod(script_path, 0o755)
            log_event(f"Permisos de ejecución añadidos a {script_path}", origin="DESKTOP", level="INFO", reason="SETTINGS")
        except Exception as e:
            log_event(f"No se pudieron establecer permisos: {e}", origin="DESKTOP", level="WARN", reason="SETTINGS")

    # ----------------------------------------------------------
    # 3. Nombre traducido
    # ----------------------------------------------------------
    full_name = f"WMM - { _('Next Background') }"

    schema_main = "org.cinnamon.desktop.keybindings"
    schema_custom = "org.cinnamon.desktop.keybindings.custom-keybinding"
    base_path = "/org/cinnamon/desktop/keybindings/custom-keybindings/"

    settings = Gio.Settings.new(schema_main)

    # Cinnamon utiliza "custom-list"
    custom_list = settings.get_strv("custom-list")

    # ----------------------------------------------------------
    # 4. ¿Ya existe un atajo de WMM?
    # ----------------------------------------------------------
    for item in custom_list:

        if item == "__dummy__":
            continue

        path = f"{base_path}{item}/"

        try:
            ks = Gio.Settings.new_with_path(schema_custom, path)

            if ks.get_string("command") == script_path:
                log_event("Atajo de WMM ya instalado", origin="DESKTOP", level="INFO", reason="SETTINGS")
                return

        except Exception:
            pass

    # ----------------------------------------------------------
    # 5. Buscar primer índice libre
    # ----------------------------------------------------------
    used = []

    pattern = re.compile(r"custom(\d+)")

    for item in custom_list:
        m = pattern.fullmatch(item)
        if m:
            used.append(int(m.group(1)))

    index = 0
    while index in used:
        index += 1

    name = f"custom{index}"
    path = f"{base_path}{name}/"

    # ----------------------------------------------------------
    # 6. Crear el nuevo atajo
    # ----------------------------------------------------------
    ks = Gio.Settings.new_with_path(schema_custom, path)

    ks.set_string("name", full_name)
    ks.set_string("command", script_path)
    ks.set_strv("binding", [])

    ks.sync()

    # ----------------------------------------------------------
    # 7. Añadirlo a la lista principal
    # ----------------------------------------------------------
    custom_list.append(name)

    settings.set_strv("custom-list", custom_list)
    settings.sync()

    log_event(f"Atajo instalado correctamente ({name})", origin="DESKTOP", level="INFO", reason="SETTINGS")

# --- BLOQUE DE AUTODIAGNÓSTICO ---
if __name__ == "__main__":
    print("\n" + "═" * 50)
    print("  WMM PLATFORM DIAGNOSTIC - CINNAMON")
    print("═" * 50)

    active = get_monitors()
    if active:
        from monitor_manager import get_total_canvas_geometry
        canvas_w, canvas_h = get_total_canvas_geometry(active)

        print(f"\n[MONITORES]")
        for m_hash, data in active.items():
            print(f"  ID: {m_hash} | {data['width']}x{data['height']} en ({data['x']},{data['y']}) | {data['orientation']}")

        print(f"\n[LIENZO]")
        print(f"  Lienzo Maestro Requerido: {canvas_w}x{canvas_h}")
    else:
        print("\n[!] No se detectaron monitores.")

    print("\n" + "═" * 50)
    print("  Diagnóstico completado.")
    print("═" * 50 + "\n")
