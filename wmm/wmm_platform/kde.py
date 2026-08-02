"""
Módulo de plataforma para KDE Plasma (Linux).
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
    """Devuelve la ruta de instalación (esqueleto)."""
    return os.path.join(data_base, app_domain)

def get_monitors():
    """Devuelve un diccionario con la geometría de todos los monitores activos usando Gdk."""
    import hashlib
    gi.require_version('Gdk', '3.0')
    from gi.repository import Gdk
    from monitor_manager import calculate_inches

    display = Gdk.Display.get_default()
    if display:
        display.sync()

    monitors_data = {}
    n_monitors = display.get_n_monitors()

    for i in range(n_monitors):
        monitor = display.get_monitor(i)
        geometry = monitor.get_geometry()
        connector = monitor.get_model() or "Unknown"
        manufacturer = monitor.get_manufacturer()
        w_mm = monitor.get_width_mm()
        h_mm = monitor.get_height_mm()
        is_primary = monitor.is_primary()

        m_hash = hashlib.shake_128(connector.encode()).hexdigest(4)
        orientation = "horizontal" if geometry.width >= geometry.height else "vertical"
        inches = calculate_inches(w_mm, h_mm)

        monitors_data[m_hash] = {
            "connector": connector,
            "manufacturer": manufacturer,
            "x": geometry.x,
            "y": geometry.y,
            "width": geometry.width,
            "height": geometry.height,
            "width_mm": w_mm,
            "height_mm": h_mm,
            "inches": inches,
            "orientation": orientation,
            "primary": is_primary,
        }

    return monitors_data

def _force_desktop_settings(config_handler):
    """
    Fuerza los ajustes del sistema necesarios para que WMM funcione
    correctamente en KDE Plasma:
      - Cambiar el plugin de wallpaper a 'org.kde.image'
      - Forzar FillMode=3 (Spanned)
      - Desactivar slideshow
    """
    try:
        # 1. Forzar plugin, FillMode y slideshow
        subprocess.run(["kwriteconfig6", "--file", "plasmarc", "--group", "Wallpaper", "--key", "plugin", "org.kde.image"], check=False)
        subprocess.run(["kwriteconfig6", "--file", "plasmarc", "--group", "Wallpaper", "--key", "fillMode", "3"], check=False)
        subprocess.run(["kwriteconfig6", "--file", "plasmarc", "--group", "Wallpaper", "--key", "slideshow", "false"], check=False)

        # 2. También forzar en el archivo de applets (para el contenedor del escritorio)
        appconfig = os.path.expanduser("~/.config/plasma-org.kde.plasma.desktop-appletsrc")
        if os.path.exists(appconfig):
            subprocess.run(["kwriteconfig6", "--file", appconfig, "--group", "Containments", "--group", "1", "--group", "Wallpaper", "--group", "org.kde.image", "--group", "General", "--key", "FillMode", "3"], check=False)

        log_event("Ajustes de KDE forzados (plugin=org.kde.image, FillMode=3, slideshow=false)", origin="DESKTOP", level="DEBUG", reason="HARDWARE")

        # Notificar al usuario si algo falló (pero no interrumpimos)
        issues = []
        # Verificar plugin
        result = subprocess.run(["kreadconfig6", "--file", "plasmarc", "--group", "Wallpaper", "--key", "plugin"], capture_output=True, text=True)
        if result.stdout.strip().lower().replace("'", "") != "org.kde.image":
            issues.append("Plugin de wallpaper")
        # Verificar fillMode
        result = subprocess.run(["kreadconfig6", "--file", "plasmarc", "--group", "Wallpaper", "--key", "fillMode"], capture_output=True, text=True)
        if result.stdout.strip() != "3":
            issues.append("Modo de relleno (FillMode)")
        if issues:
            log_event(f"No se pudieron forzar algunos ajustes: {', '.join(issues)}", origin="DESKTOP", level="WARN", reason="HARDWARE")

    except Exception as e:
        log_event(f"Error al forzar ajustes de KDE: {e}", origin="DESKTOP", level="ERROR", reason="NOTIFY")

def set_wallpaper(image_path, config_handler=None):
    """
    Aplica el fondo de pantalla en KDE Plasma 6.
    Estrategia: aplicar imagen con FillMode=3 (Spanned) y usar el truco del
    color sólido para forzar la transición suave (workaround para bug de refresco).
    """
    if not os.path.exists(image_path):
        log_event(f"Imagen no encontrada: {image_path}", origin="DESKTOP", level="ERROR")
        return False

    # Forzar parámetros de configuración (plugin, FillMode, slideshow)
    if config_handler:
        _force_desktop_settings(config_handler)

    try:
        # 1. Aplicar la imagen con plasma-apply-wallpaperimage
        subprocess.run(["plasma-apply-wallpaperimage", image_path], check=True)
        log_event(f"Imagen aplicada: {image_path}", origin="DESKTOP", level="INFO")

        # 2. Leer el color actual (si no existe, usar negro por defecto)
        result = subprocess.run(
            ["kreadconfig6", "--file", "plasmarc", "--group", "Wallpaper", "--key", "color"],
            capture_output=True, text=True
        )
        current_color = result.stdout.strip() or "#000000"
        log_event(f"Color actual: {current_color}", origin="DESKTOP", level="DEBUG")

        # 3. Truco del color sólido (forzar refresco visual)
        temp_color = "#000001"  # Casi negro, imperceptible
        script_template = """
        var allDesktops = desktops();
        for (var i = 0; i < allDesktops.length; i++) {{
            var d = allDesktops[i];
            d.currentConfigGroup = ['Wallpaper', 'org.kde.image', 'General'];
            d.writeConfig('Color', '{}');
            d.reloadConfig();
        }}
        """

        # Cambiar a color temporal
        subprocess.run([
            "kwriteconfig6", "--file", "plasmarc",
            "--group", "Wallpaper", "--key", "color", temp_color
        ], check=True)
        subprocess.run([
            "dbus-send", "--session", "--dest=org.kde.plasmashell",
            "--type=method_call", "/PlasmaShell",
            "org.kde.PlasmaShell.evaluateScript",
            f"string:{script_template.format(temp_color)}"
        ], check=False)

        # Restaurar el color original
        subprocess.run([
            "kwriteconfig6", "--file", "plasmarc",
            "--group", "Wallpaper", "--key", "color", current_color
        ], check=True)
        subprocess.run([
            "dbus-send", "--session", "--dest=org.kde.plasmashell",
            "--type=method_call", "/PlasmaShell",
            "org.kde.PlasmaShell.evaluateScript",
            f"string:{script_template.format(current_color)}"
        ], check=False)

        log_event("Fondo aplicado y refresco visual forzado", origin="DESKTOP", level="INFO")
        return True

    except subprocess.CalledProcessError as e:
        log_event(f"Error al aplicar wallpaper: {e}", origin="DESKTOP", level="ERROR")
        return False
    except Exception as e:
        log_event(f"Error en set_wallpaper: {e}", origin="DESKTOP", level="ERROR")
        return False

def ensure_keybindings(app_dir):
    """
    Registra el atajo 'WMM - Next Background' en KDE Plasma 6.
    app_dir: ruta de instalación (ej. ~/.local/share/plasma/org.maki.wmm)
    """
    import dbus
    import time

    # 1. Construir ruta del script
    script_path = os.path.join(app_dir, 'wmm_platform', 'shell', 'kde', 'wmm-next.sh')
    if not os.path.exists(script_path):
        log_event(f"Script no encontrado: {script_path}", origin="KDE", level="WARN")
        return

    # 2. Asegurar permisos de ejecución
    if not os.access(script_path, os.X_OK):
        try:
            os.chmod(script_path, 0o755)
            log_event(f"Permisos de ejecución añadidos a {script_path}", origin="KDE", level="INFO")
        except Exception as e:
            log_event(f"No se pudieron establecer permisos: {e}", origin="KDE", level="WARN")

    # 3. Datos del componente KDE
    name = _("Next Background")
    full_name = f"WMM- {name}"
    desktop_id = "net.local.wmm-next.sh.desktop"
    log_event(f"KDE shortcut data: desktop_id='{desktop_id}', full_name='{full_name}'", origin="KDE", level="DEBUG")

    # 4. Crear lanzador .desktop si no existe
    try:
        os.makedirs(desktop_dir, exist_ok=True)
        if not os.path.exists(desktop_path) or True:
            desktop_content = f"""[Desktop Entry]
Exec={script_path}
Name={full_name}
NoDisplay=true
StartupNotify=false
Type=Application
X-KDE-GlobalAccel-CommandShortcut=true
"""
            with open(desktop_path, "w", encoding="utf-8") as f:
                f.write(desktop_content)
            os.chmod(desktop_path, 0o755)
            log_event(f"Lanzador KDE creado: {desktop_path}", origin="KDE", level="INFO")
    except Exception as e:
        log_event(f"No se pudo crear lanzador KDE: {e}", origin="KDE", level="ERROR")
        return

    # 5. Conectar con kglobalaccel
    try:
        bus = dbus.SessionBus()
        accel = bus.get_object("org.kde.kglobalaccel", "/kglobalaccel")
        accel_iface = dbus.Interface(accel, "org.kde.KGlobalAccel")
    except Exception as e:
        log_event(f"No se pudo conectar con kglobalaccel: {e}", origin="KDE", level="ERROR")
        return

    action_id = [desktop_id, full_name, "", ""]
    log_event(f"Registrando KDE action_id={action_id}", origin="KDE", level="DEBUG")

    # 6. Registrar componente
    try:
        accel_iface.doRegister(action_id)
        log_event("doRegister KDE completado", origin="KDE", level="DEBUG")
        log_event(f"Componentes KDE tras doRegister: {accel_iface.getComponent(desktop_id)}", origin="KDE", level="DEBUG")
    except Exception as e:
        log_event(f"Error registrando componente KDE: {e}", origin="KDE", level="ERROR")
        return

    # 7. Esperar a que KDE cree el componente
    component_path = None
    for attempt in range(10):
        try:
            component_path = accel_iface.getComponent(desktop_id)
            log_event(f"Componente KDE obtenido en intento {attempt}: {component_path}", origin="KDE", level="DEBUG")
            break
        except Exception as e:
            log_event(f"getComponent intento {attempt}: {e}", origin="KDE", level="DEBUG")
            time.sleep(0.2)

    if not component_path:
        log_event(f"No se pudo obtener componente KDE: {desktop_id}", origin="KDE", level="ERROR")
        return

    # 8. Obtener interfaz del componente
    try:
        component = bus.get_object("org.kde.kglobalaccel", component_path)
        component_iface = dbus.Interface(component, "org.kde.kglobalaccel.Component")
    except Exception as e:
        log_event(f"No se pudo abrir componente KDE: {e}", origin="KDE", level="ERROR")
        return

    # 9. Liberar registro temporal para que KDE gestione el atajo
    try:
        accel_iface.unRegister(action_id)
        log_event(f"Atajo KDE registrado: {full_name}", origin="KDE", level="INFO")
    except Exception as e:
        log_event(f"No se pudo liberar registro KDE: {e}", origin="KDE", level="WARN")
