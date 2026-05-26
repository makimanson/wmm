# WMM - Wallpaper Multi-Monitor Manager

Un applet para Cinnamon que revoluciona la gestión de fondos de pantalla en configuraciones multi-monitor. Olvídate de fondos deformados, recortados o repetidos. Con WMM, tú tienes el control total.

## ✨ Características principales

*   **Gestión multi-monitor real**: Asigna fondos diferentes a cada monitor o "extiende" (spanned) una imagen panorámica por todos ellos.
*   **Modos de aspecto flexibles**: Controla cómo se ajusta la imagen: `Scaled` (sin deformar), `Zoom` (llenar recortando) o `Stretched` (llenar deformando).
*   **Efectos visuales**: Aplica filtros `Sepia` o `Blanco y Negro` a las imágenes por monitor.
*   **Rotación automática**: Configura un temporizador para cambiar los fondos automáticamente, ya sea de forma síncrona o asíncrona.
*   **Favoritos (Presets)**: Guarda tus combinaciones de fondos favoritas como "Presets" y carga la que quieras al instante.
*   **Internacionalización**: Interfaz preparada para múltiples idiomas (Inglés, Español, Catalán) con soporte para heredar traducciones del sistema.

## 📋 Dependencias

Antes de instalar, asegúrate de tener estas dependencias. Puedes instalarlas manualmente o dejar que el script `install.sh` lo haga por ti.

| Paquete | Descripción |
|---|---|
| `python3` | Intérprete de Python 3 |
| `python3-pillow` | Librería de manipulación de imágenes |
| `python3-gi` | Bindings de GTK para Python |
| `python3-gi-cairo` | Bindings de Cairo para Python |
| `gir1.2-gtk-3.0` | Información de tipos para GTK+ 3.0 |
| `gir1.2-glib-2.0` | Información de tipos para GLib 2.0 |
| `gettext` | Herramientas de internacionalización |
| `libnotify-bin` | Para enviar notificaciones de escritorio |
| `zenity` | Para mostrar diálogos gráficos |
| `procps` | Para la herramienta de gestión de procesos `pkill` |

### Instalación rápida de dependencias (si no usas `install.sh`)

*   **Linux Mint / Ubuntu / Debian**:

    sudo apt install python3 python3-pillow python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-glib-2.0 gettext libnotify-bin zenity procps

*   **Fedora**:

sudo dnf install python3 python3-pillow python3-gobject gtk3 glib2 gettext libnotify zenity procps-ng

*   **Arch Linux / Manjaro**:

sudo pacman -S python python-pillow python-gobject gtk3 glib2 gettext libnotify zenity procps-ng

-------------------------------------------------------------------

🚀 Instalación

    Descarga o clona este repositorio en tu ordenador.

    Abre una terminal en la carpeta raíz del proyecto (wmm-applet@maki).

    Ejecuta el script de instalación:
    bash

    chmod +x install.sh
    ./install.sh

    El script comprobará tus dependencias y te preguntará si quieres instalarlas automáticamente.

    Activa el applet: Ve a la configuración de Applets de Cinnamon, busca "WMM - Wallpaper Master Manager" y actívalo.

🛠️ Modo Debug

Para solucionar problemas o ver qué está pasando entre bambalinas, puedes abrir el panel de control en modo debug. Verás una terminal con todos los mensajes de diagnóstico.

    Desde el applet: Haz clic derecho en el icono de WMM > Ajustes WMM (Debug).

    Manual: Abre una terminal y ejecuta WMM_DEBUG=1 python3 ~/.local/share/cinnamon/applets/wmm-applet@maki/python/panel.py.

## 🌍 Traducción

WMM soporta múltiples idiomas. Las traducciones se instalan automáticamente al ejecutar `install.sh`.
Los archivos fuente se encuentran en la carpeta `locale/` del proyecto.
La interfaz se mostrará automáticamente en tu idioma si las traducciones están disponibles.
Si quieres ayudarnos a traducir WMM a tu idioma, ¡serás más que bienvenido!

## Licencia

WMM se distribuye bajo la licencia [GPL-3.0](LICENSE).
