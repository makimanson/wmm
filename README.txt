====================================================
 WMM – Wallpaper Multi-Monitor Manager
 Version 1.2.3
====================================================


ENGLISH VERSION
====================================================

Thank you for downloading WMM!

WMM is a wallpaper manager for multi-monitor systems,
compatible with Cinnamon, GNOME and KDE Plasma.


PREREQUISITES

Before installing, make sure your system has:

  - Python 3
  - GTK 3.0 (already included in Cinnamon/GNOME)
  - libnotify (for desktop notifications)

Other dependencies (Pillow, NumPy, GetText, Zenity)
will be installed automatically if needed.


QUICK INSTALLATION

1. Open a terminal in this folder.

2. Run the installer:

       ./install.sh

   The script will check dependencies and ask for
   confirmation to install any missing ones.
   Then it will copy the files to the correct
   location based on your desktop (Cinnamon,
   GNOME or KDE).

3. Restart your desktop or reload applets/extensions.

   - Cinnamon:
     Go to Settings > Applets and enable "WMM Manager".

   - GNOME:
     Open Extensions and enable "WMM Manager".

   - KDE Plasma (coming soon):
     The engine will start automatically and you can
     use the integrated control panel.


MANUAL INSTALLATION (if you prefer not to use the script)

1. Copy the "contents" of the "wmm" folder next to
   this file into the corresponding location:

   - Cinnamon:
     ~/.local/share/cinnamon/applets/wmm@maki/

   - GNOME:
     ~/.local/share/gnome-shell/extensions/wmm@maki/

   - KDE Plasma:
     ~/.local/share/wmm/

2. Make sure the system dependencies listed above
   are installed.

3. Restart your desktop if using Wayland, or reload
   applets/extensions if using X11.


MORE INFORMATION

  - Official repository:
    https://github.com/makimanson/wmm

  - Problems or suggestions?
    https://github.com/makimanson/wmm/issues

  - Detailed changelog in the CHANGELOG.md file
    included in this package.


TIP

If you downloaded WMM from GitHub Releases, you can
drag the folder directly to your file manager and
run install.sh from there.


NOTE FOR GNOME EXTENSIONS USERS

WMM translations are compiled automatically the first
time the engine runs. If you do not see WMM in your
language after installation, restart the session or
open the control panel once to force compilation.




VERSION EN CASTELLANO
====================================================

¡Gracias por descargar WMM!

WMM es un gestor de fondos de pantalla para sistemas
multi-monitor, compatible con Cinnamon, GNOME y KDE Plasma.


REQUISITOS PREVIOS

Antes de instalar, asegurate de que tu sistema tiene:

  - Python 3
  - GTK 3.0 (ya incluido en Cinnamon/GNOME)
  - libnotify (para notificaciones de escritorio)

El resto de dependencias (Pillow, NumPy, GetText, Zenity)
se instalaran automaticamente si es necesario.


INSTALACION RAPIDA

1. Abre una terminal en esta carpeta.

2. Ejecuta el instalador:

       ./install.sh

   El script comprobara las dependencias y te pedira
   confirmacion para instalar las que falten.
   Despues copiara los archivos al lugar correcto
   segun tu escritorio (Cinnamon, GNOME o KDE).

3. Reinicia el escritorio o vuelve a cargar los
   applets / extensiones.

   - Cinnamon:
     Ve a Configuracion > Applets y activa "WMM Manager".

   - GNOME:
     Abre Extensiones y activa "WMM Manager".

   - KDE Plasma (proximamente):
     El motor se iniciara automaticamente y podras usar
     el panel de control integrado.


INSTALACION MANUAL (si prefieres no usar el script)

1. Copia el "contenido" de la carpeta "wmm" que acompana
   a este archivo a la ubicacion correspondiente:

   - Cinnamon:
     ~/.local/share/cinnamon/applets/wmm@maki/

   - GNOME:
     ~/.local/share/gnome-shell/extensions/wmm@maki/

   - KDE Plasma:
     ~/.local/share/wmm/

2. Asegurate de que las dependencias del sistema estan
   instaladas (consulta la lista de arriba).

3. Reinicia el escritorio si usas Wayland o recarga
   applets/extensiones si usas X11.


MAS INFORMACION

  - Repositorio oficial:
    https://github.com/makimanson/wmm

  - ¿Problemas o sugerencias?
    https://github.com/makimanson/wmm/issues

  - Changelog detallado en el archivo CHANGELOG.md
    incluido en este paquete.


CONSEJO

Si descargaste WMM desde GitHub Releases, puedes
arrastrar la carpeta directamente a tu gestor de
archivos y ejecutar install.sh desde alli.


NOTA PARA USUARIOS DE GNOME EXTENSIONS

Las traducciones de WMM se compilan automaticamente
la primera vez que se ejecuta el motor. Si no ves
WMM en tu idioma tras instalarlo, reinicia la sesion
o abre el panel de control una vez para forzar la
compilacion.
