"""
Módulo de plataforma para Windows.
Contiene funciones comunes a Windows (independientes del escritorio).
"""
import os

def get_terminal():
    """
    Devuelve el comando de la terminal por defecto en Windows (cmd o PowerShell).
    """
    return "cmd.exe"  # o 'powershell.exe'

def open_in_terminal(command):
    """
    Abre una terminal en Windows y ejecuta el comando especificado.
    Detecta automáticamente entre cmd.exe y powershell.exe.
    """
    terminal = os.environ.get("ComSpec", "cmd.exe")  # ComSpec apunta a cmd.exe por defecto
    # Si el usuario prefiere PowerShell, podemos detectarlo con WT_SESSION o PATHEXT
    # Pero por simplicidad, usaremos cmd.exe como fallback y powershell si está disponible.
    if "powershell" in terminal.lower() or os.environ.get("PSModulePath"):
        subprocess.Popen([terminal, "-Command", command], start_new_session=True)
    else:
        subprocess.Popen([terminal, "/c", command], start_new_session=True)

def open_file(path):
    """
    Abre un archivo o directorio con la aplicación predeterminada en Windows.
    """
    os.startfile(path)

def setup_translations():
    """
    Configura el sistema de traducciones para Windows.
    """
    # TODO: Implementar gettext para Windows con rutas locales
    pass

def _(text):
    """
    Función de traducción para Windows.
    Por ahora, devuelve el texto original.
    """
    # TODO: Implementar gettext para Windows
    return text

def send_notification(title, message, level="info"):
    """
    Envía una notificación en Windows.
    """
    # TODO: Implementar usando win32api o toasts
    print(f"[NOTIFICACIÓN] {title}: {message}")
