────────────────────────────────────────

Copyright © 2026 makimanson
WMM — Wallpaper Multi-Monitor Manager

────────────────────────────────────────

WMM MANAGER - README
====================

WMM - Wallpaper Multi-Monitor Manager
=====================================

A wallpaper manager for multi-monitor setups on Linux and Windows, supporting Cinnamon,
GNOME Shell, KDE Plasma 6, MATE and XFCE.

Forget distorted, cropped or repeated wallpapers.
With WMM, you're in full control.

Presentation image: wmm/WMM-presentation.jpg

MAIN FEATURES
-------------

- True multi-monitor management: Assign different wallpapers to each monitor or span
  (Spanned) a panoramic image across all of them.
- Smart image assignment: Tries to select the most suitable image for each monitor
  according to its portrait or landscape orientation.
- Flexible aspect modes: Control how images fit: Scaled (without distortion), Zoom
  (fill by cropping) or Stretched (fill by stretching).
- Visual effects: Apply Sepia or Black & White filters to images on individual monitors.
- Background effects: Apply Blur or Color to the background when an image does not fill
  the entire monitor area.
- Automatic rotation: Set a timer to change wallpapers synchronously (SYNC) or
  asynchronously (ASYNC).
- Selective rotation: Choose which source folders participate in rotation, with
  independent pools for the general library, selected folders and favorites.
- Spanned mode: Compose a single logical image across all monitors while respecting
  their positions and geometry.
- Favorites: Save individual images and complete wallpaper combinations as Presets
  for quick access.
- Wallpapers Online: Search for wallpapers from participating wallpaper providers,
  filter results by orientation and aspect ratio, and browse result pages.
- Online editing: Drag images from providers directly onto virtual monitors to
  preview them on your desktop before adding them to your library.
- Image library: Organize your sources, browse thumbnails and keep your images
  synchronized from the Control Panel.
- Image metadata: Display EXIF/XMP information and location data on wallpapers,
  with configurable presentation options.
- Control Panel: Manage sources, monitors, favorites, effects, thumbnails and
  options through a shared interface across supported desktops.
- Desktop integration: Native applets for Cinnamon and MATE, a GNOME Shell extension,
  a KDE Plasma 6 plasmoid, a dedicated StatusNotifier frontend for XFCE and an
  application integrated into the Windows system tray.
- Native file manager integration: Select an image to add it to favorites, send it
  to a specific monitor or span it across all of them.
- Install Manager: Install, update, reinstall or uninstall WMM using the tools
  provided for each platform.
- Internationalization: Interface available in English, Spanish and Catalan, using
  WMM's own translation domain independent of the desktop environment.

SUPPORTED ENVIRONMENTS
----------------------

Desktop             Support          Notes
------------------  ---------------  -------------------------------------------
Cinnamon            Full             Native applet. Current support on X11
GNOME Shell         Full             Native extension. GNOME Shell 45-51
KDE Plasma 6        Full             Native plasmoid. Requires Plasma 6
MATE                Full             Native applet. Current support on X11
XFCE                Full             StatusNotifier frontend. XFCE 4.20 / X11
Windows             Full             Native system tray and Explorer frontend
macOS               In development   Implementation in progress

DESKTOP INTEGRATION
-------------------

WMM adapts wallpaper handling to the capabilities of each desktop environment.

- Cinnamon and GNOME Shell use their own integration to apply compositions generated
  by WMM.
- KDE Plasma 6 applies wallpapers per monitor through Plasma's native API,
  preserving its visual transitions.
- MATE uses its own wallpaper backend and a native applet integrated into MATE Panel.
- XFCE uses a dedicated StatusNotifier frontend, an xfconf wallpaper backend and
  XFCE's native shortcut integration.
- Windows provides a system tray icon, control menus, Windows Explorer integration,
  notifications, global shortcuts and light/dark theme support.

WMM automatically manages the settings needed for normal operation; there is no need
to manually configure a common wallpaper mode for every desktop.

INSTALLATION
------------

LINUX

1. Download the latest available version from this repository to your computer.
2. Open a terminal in the project root directory.
3. Run:

    chmod +x wmm-install.sh
    ./wmm-install.sh

The installer automatically detects Cinnamon, GNOME Shell, KDE Plasma 6, MATE or XFCE,
checks required dependencies and can install missing ones through your distribution's
package manager.

If an existing installation is detected, the same manager can update,
reinstall/repair or uninstall it.

After a fresh installation:

- Cinnamon: Restart your session, open Applets settings and enable WMM Manager, or
  launch WMM from Menu > Graphics.
- GNOME Shell: Restart your session, open Extensions and enable WMM Manager, or
  launch WMM from Applications > WMM.
- KDE Plasma 6: On Plasma 6.6.6 or later, the installer restarts Plasma Shell without
  requiring a session restart. Launch WMM Manager from Menu > Graphics. Earlier
  Plasma 6 versions require a session restart.
- MATE: Add WMM Manager to the panel using Add to Panel, or launch WMM from
  Menu > Graphics.
- XFCE: Launch WMM Manager from Menu > Graphics.

WINDOWS - OPEN-CODE

This option lets you install WMM directly from its open-source distribution.

1. Download the WMM source code from GitHub and extract it to a folder.
2. Run wmm-install.cmd from the package's root directory.
3. The manager displays the available version and the operations you can perform.
4. Select Install and confirm.
5. If the additional wmm-runtime.zip package is missing, the installer will offer
   to download it from GitHub, provided it is available.
6. Follow the instructions to complete the installation.

You can also download wmm-runtime.zip separately and place it in the same directory
as wmm-install.cmd before running the installer.
Once installed, you will find WMM Manager in the Windows Start menu. You can also
create a desktop shortcut and enable automatic startup.

The same manager lets you update or reinstall WMM and perform other maintenance
operations when available.

WINDOWS - COMPILED VERSION

This option provides a conventional installer that includes all required components.

1. Download WMM-Manager-Setup from the corresponding release.
2. Run the installer and follow the wizard's instructions.
3. Choose your preferred installation options.
4. Once installation is complete, launch WMM Manager from the Start menu or its
   shortcut.

There is no need to download Python, GTK or any additional package.
If you already have an earlier version of this distribution installed, you can
use the new installer to update it.

DEPENDENCIES
------------

LINUX

Using wmm-install.sh is recommended instead of installing dependencies manually.
The script checks common and desktop-specific requirements and uses the appropriate
package names for distributions based on apt, dnf or pacman.

Components used by WMM include:

- Python 3.
- Pillow and NumPy for image processing.
- GTK 3, GLib and PyGObject for the Control Panel and shared components.
- VTE 2.91 for the embedded terminal in Install Manager.
- libnotify for notifications.
- gettext for translations.
- Additional GNOME, KDE, MATE or XFCE components when required by desktop integration.

The list maintained by wmm-install.sh is the authoritative reference for
platform-specific dependencies.

WINDOWS - OPEN-CODE

This option requires the additional wmm-runtime.zip package, which contains the
components needed to run WMM on Windows.

You can obtain it in two ways:

- Download it from GitHub and place it next to wmm-install.cmd.
- Accept the download offered by Install Manager when available.

The runtime is distributed separately from the WMM source code, so it does not need
to be downloaded again for every update as long as it remains compatible.

WINDOWS - COMPILED VERSION

The WMM-Manager-Setup installer already includes all required dependencies.
No additional installation is needed.

UNINSTALLATION
--------------

LINUX

WMM can be uninstalled from Install Manager or by running the included uninstaller:

    chmod +x wmm-uninstall.sh
    ./wmm-uninstall.sh

You can also select Uninstall when running wmm-install.sh over an existing installation.

The uninstaller removes WMM and its desktop integrations, but does not automatically
remove packages installed as dependencies, since other applications may still use them.

WINDOWS - OPEN-CODE

1. Open WMM Install Manager from the Start menu, or run wmm-install.cmd from the
   source distribution.
2. Select Uninstall.
3. Confirm the operation.

This uninstallation removes WMM, its Windows integrations, application settings
and cache.

WINDOWS - COMPILED VERSION

1. Open Windows Installed apps or use the WMM uninstaller in the Start menu.
2. Select Uninstall and follow the instructions.
3. Choose whether to keep or remove your settings and thumbnail cache.

KEYBOARD SHORTCUTS
------------------

WMM lets you assign a key combination to the Next Background action, so you can
change wallpapers without opening the Control Panel.

- Linux: Configure the combination through your desktop's keyboard shortcut settings.
- Windows: Configure the global shortcut through WMM's options.

You can change the combination to suit your preferences.

DEBUG LOG VIEWER / EVENT LOG
----------------------------

WMM includes an integrated logging system that shows activity from the engine,
Control Panel and desktop integrations in real time.

- Integrated viewer: Open it from the Control Panel.
- Real-time updates: Filter by origin, level and reason, or search for specific text.
- Manual inspection: You can also open the log file with a text editor.

Log location on Linux:

    ~/.cache/wmm/debug.log

Log location on Windows:

    %LOCALAPPDATA%\WMM Manager\cache\debug.log

This log can help identify and diagnose issues.

TRANSLATION
-----------

WMM is available in English, Spanish and Catalan, and automatically selects the
language matching the user's session when a translation is available.
English is the default when no translation is available.

Project translation files are located at:

    wmm/wmm_platform/shell/po/

If you'd like to help translate WMM into your language, you're more than welcome!

LICENSE
-------

WMM is distributed under GPL-3.0 (LICENSE). You are free to use, modify and distribute
this software, provided you keep the same license and attribution to the original
authors.

ACKNOWLEDGEMENTS AND CONTRIBUTIONS
----------------------------------

WMM thanks the following wallpaper providers for making their services and content
available, helping to expand the project's image sources.

Their logos link directly to their websites, and each image retains a link to its
original page, even from the local library.

Wallhaven: https://wallhaven.cc/

Alpha Coders: https://alphacoders.com/

GEOGRAPHIC DATA

WMM thanks dr5hn and the contributors to Countries States Cities Database for their
work compiling and maintaining the geographic data used by this project.

Source: https://github.com/dr5hn/countries-states-cities-database
Data license: Open Database License (ODbL) v1.0
https://github.com/dr5hn/countries-states-cities-database/blob/master/LICENSE