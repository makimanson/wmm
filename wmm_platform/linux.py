"""
Módulo de plataforma para Linux.
Contiene funciones comunes a todos los escritorios de Linux.
"""
import os
import subprocess

def get_terminal():
    """
    Detecta el terminal por defecto del usuario en Linux.
    Retorna el comando del terminal (ej: 'gnome-terminal', 'kgx', 'xfce4-terminal').
    """
    mime_path = os.path.expanduser("~/.config/mimeapps.list")
    if os.path.exists(mime_path):
        with open(mime_path, "r") as f:
            for line in f:
                if line.startswith("x-scheme-handler/terminal="):
                    return line.split("=", 1)[1].strip()
    # Fallback: terminal genérico del sistema
    return "x-terminal-emulator"

def open_in_terminal(command):
    """
    Abre una terminal en Linux y ejecuta el comando especificado.
    Detecta automáticamente el terminal por defecto del usuario.
    """
    terminal = get_terminal()
    subprocess.Popen([terminal, "-e", command], start_new_session=True)

def open_file(path):
    """
    Abre un archivo o directorio con la aplicación predeterminada en Linux.
    """
    subprocess.run(['xdg-open', path], check=False)

def setup_translations():
    """
    Configura el sistema de traducciones para Linux.
    """
    import gettext
    locale_dir = os.path.expanduser('~/.local/share/locale')
    gettext.bindtextdomain('wmm-applet@maki', locale_dir)

def _(text):
    """
    Función de traducción personalizada para Linux.
    Busca primero en el sistema, luego en nuestro dominio.
    """
    import gettext
    translated = gettext.dgettext('cinnamon', text)  # 'cinnamon' como fallback del sistema
    if translated != text:
        return translated
    return gettext.dgettext('wmm-applet@maki', text)

def send_notification(title, message, level="info"):
    """
    Envía una notificación de escritorio en Linux usando notify-send.
    """
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
            "-a", "WMM_DEBUG"
        ], check=False)
    except Exception as e:
        print(f" [!] Error en notificación: {e}")
