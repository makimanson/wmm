"""
Módulo de plataforma para macOS.
Contiene funciones comunes a macOS (independientes del escritorio).
"""
import subprocess

def get_terminal():
    """
    Devuelve el comando del terminal por defecto en macOS.
    """
    return "Terminal"  # o 'iTerm2' según preferencias

def open_file(path):
    """
    Abre un archivo o directorio con la aplicación predeterminada en macOS.
    """
    subprocess.run(['open', path], check=False)

def setup_translations():
    """
    Configura el sistema de traducciones para macOS.
    """
    # TODO: Implementar según la estructura de macOS
    pass

def _(text):
    """
    Función de traducción para macOS.
    Por ahora, devuelve el texto original.
    """
    # TODO: Implementar gettext para macOS
    return text

def send_notification(title, message, level="info"):
    """
    Envía una notificación en macOS.
    """
    # TODO: Implementar usando osascript o PyObjC
    print(f"[NOTIFICACIÓN] {title}: {message}")
