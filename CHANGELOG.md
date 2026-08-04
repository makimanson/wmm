Changelog

## v1.2.4 - 2026-08-04

**Fixed**

- Critical bugfix: source files (`applet.js`, `extension.js`, etc.) were packaged with unresolved Git conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`) in the v1.2.3 release. This caused `expected expression, got '<<'` errors when loading the applet/extension on some systems.
- All conflict markers have been removed and the source tree is now clean. The applet and extension load correctly again.
- No functional changes: this release only fixes the packaging issue.

**Note for users**

If you are using v1.2.3, please update to v1.2.4 as soon as possible. The previous version may not load correctly on your system.

## v1.2.3 - 2026-08-02

**Added**

-   New image selection engine (`image_selection.py`): centralises all selection logic (sync/async modes, spanned, presets, history) and cuts `main.py` load by over 30%, improving maintainability and responsibility isolation.
-   New monitor detection engine (`monitor_detection.py`): unifies detection strategies across X11 (libXrandr), GNOME Wayland (D-Bus), and generic GDK fallback. Detection logic is now fully decoupled from the rest of the engine.
-   New hardware events engine (`monitor_events.py`): centralises monitor change monitoring (connect/disconnect) using D-Bus on GNOME and GDK signals as fallback, following same modular pattern as other engines.
-   Full GNOME Wayland support: monitors detected via D-Bus (org.gnome.Mutter.DisplayConfig) with complete information (connector, model, serial, real size, orientation, physical dimensions, inches, and primary). Orientation correctly obtained (`current_transform` in CRTCs).
-   Enhanced `get_monitor_display_name` in `config_handler.py`: now generates rich monitor names (e.g. "Samsung LC49G95T (49")" or "Generic Monitor DP-3 (49")") with clear logic prioritising model, then manufacturer, and finally connector as last resort.
-   Monitor switches in control panel now show descriptive names including model, manufacturer, and inches, improving visual identification in multi‑monitor setups.

**Changed**

-   Deep refactor of `main.py`: duplicate selection methods (`_build_selection`, `_handle_selection_mode`, `_resolve_async_targets`, `_get_smart_favorite`) removed; they now live in `image_selection.py`. Main orchestrator shrinks from ~1200 to ~800 lines, gaining clarity and reducing coupling.
-   Refactored `linux.py` and `gnome.py`: monitor detection functions (`get_x11_monitors`, `get_gdk_wayland_monitors`, `get_monitors_from_dbus`) extracted to new `monitor_detection.py`, and event functions (`init_monitor_events`) moved to new `monitor_events.py`. These files now focus exclusively on OS‑ or desktop‑specific implementations.
-   `PlatformManager` (`core.py`) now delegates detection and events to the new orchestration engines instead of assigning functions from platform modules. This unifies usage patterns and eases extension to future desktops (KDE, etc.).
-   Improved monitor identification on Wayland: position‑based identification removed; now uses `current_crtc` provided by D‑Bus, ensuring exact output‑to‑CRTC pairing.
-   Wayland monitor orientation now calculated from actual CRTC size (width, height), no heuristics or assumptions.
-   GDK fallback on Wayland retained as backup for environments without D‑Bus (e.g., experimental Cinnamon Wayland), though limited (no model or physical dimensions).
-   Experimental Cinnamon Wayland support: not functional. Will be revisited when development matures. Currently not viable.

**Fixed**

-   Fixed issue where Spanned mode on Wayland incorrectly picked first monitor in list instead of primary, causing distortion. Now correctly selects main monitor.
-   Fixed monitor orientation on GNOME Wayland: rotated (vertical) monitors now correctly detected and reflected in `geometry.json` with proper orientation.
-   Fixed monitor name generation in control panel switches and tooltips: now displays full model (e.g. "LC49G95T") instead of connector (e.g. "DP-3"), and includes connector for identical monitors when model is missing.
-   Removed "first available image" fallback in Spanned mode, which had been causing inappropriate vertical images. Now intelligently selects using `get_smart_selection`.
-   Removed redundant logs and noise from log viewer generated during Wayland monitor detection.
-   Ensured compatibility with Cinnamon X11 after refactorings: all X11 tests (Cinnamon, GNOME) pass without regressions.
-   Fixed translation fallback in GNOME extension: removed `gnome-shell` domain dependency, now uses exclusive WMM translation domain (`wmm@maki`) for consistent and self‑contained i18n across all desktop environments.

**Removed**

-   Removed `get_primary_monitor` method (GDK‑based) from `linux.py`, obsolete after new D‑Bus detection.
-   Removed position‑based monitor detection heuristic from `_get_spanned_master_image`; now uses D‑Bus `current_crtc`.

## v1.2.2 - 2026-06-23

**Added**

-   Implemented a new event-driven communication layer using Gio.FileMonitor to listen for commands.json and command_panel.json changes, creating a 100% asynchronous and agnostic communication channel between the engine, applet, and panel.
-   Added unified shell script wrappers (wmm-add_to_bookmarks.sh, wmm-send-to-monitor.sh) for file manager integration. These scripts dynamically detect the active desktop environment (Cinnamon, GNOME, KDE) and route execution to the correct Python script, resolving path conflicts when using Nemo in GNOME or Nautilus in Cinnamon.

**Changed**

-   Major Architecture Refactor: Completely removed SIGUSR1 signals and pkill subprocess calls for Inter-Process
-   Communication (IPC). The engine and panel now react to file changes via Gio.FileMonitor instead of relying on system signals.
-   Future-Proofing: This IPC refactoring is the foundational step to prepare the codebase for KDE Plasma (next milestone) and Windows/macOS (planned). By eliminating POSIX-only dependencies, the core engine is now fully platform-agnostic.
-   Restructured file manager integration scripts into a single wmm_platform/shell/file_manager/ directory.
-   Renamed nemo_add_bookmark.py and nemo_send_to_monitor.py to shell_add_bookmark.py and shell_send_to_monitor.py to reflect their file-manager-agnostic nature.
-   Nemo .nemo_action files now call the unified .sh wrappers instead of using hardcoded absolute paths, ensuring seamless operation across dual-boot desktop environments.
-   Cleaned up obsolete imports (signal, subprocess) across backend and UI scripts following the IPC overhaul.
-   Updated bundled wmm-next.sh keyboard shortcut scripts to remove pkill commands, matching the new file-monitor-based architecture.

**Fixed**

-    Resolved 4 warnings reported by Cinnamon Spices and GNOME Extensions reviewers regarding synchronous file I/O operations blocking the main loop in applet.js / extension.js
-    Implemented an automatic cleanup routine in ensure_shell_actions to remove legacy nemo and nautilus directories and old router scripts during engine startup, preventing duplicate context menu entries after an update.

## v1.2.1 - 2026-06-18

**Added**
- "Next Wallpaper" menu item as the first option in the GNOME context menu, providing a reliable way to force wallpaper rotation without depending on left-click behavior that varies across GNOME versions.
- Keyboard shortcut support via bundled `wmm-next.sh` scripts for both Cinnamon and GNOME, documented in the README with step-by-step instructions in English and Spanish.
- Dark mode wallpaper support for GNOME 46+: `set_wallpaper` now also sets `picture-uri-dark` so wallpapers display correctly in both light and dark modes.

**Changed**
- The GNOME extension no longer attempts to intercept left-click for wallpaper rotation. Left-click now behaves as GNOME expects (opens the menu), making the extension fully compatible with GNOME 46 and avoiding fragile reliance on internal Shell APIs.
- `gettext` moved from system dependencies to installable dependencies in `install.sh`, as it is not always preinstalled on minimal GNOME setups.

**Fixed**
- Wallpaper not applying in dark mode on GNOME 46 due to the new `picture-uri-dark` key being ignored. The fix is version-safe and silently skips the key if it does not exist.
- Removed left-click interception and anti-spam code from the GNOME extension. The underlying Shell APIs (such as `_clickGesture`) proved highly incompatible across versions, making the behavior fragile and impossible to maintain reliably.
- Improved object cleanup in `disable()` with a dedicated `_destroyUI()` method, addressing multiple review warnings from `shexli`.

## v1.2.0 - 2026-06-18

**Added**

-    Full GNOME Shell compatibility: new extension.js with panel indicator, context menu, slideshow controls, favorites management, and one-click wallpaper rotation with anti-spam protection.
-    Desktop-specific metadata and JavaScript files are now stored under wmm_platform/shell/cinnamon/ and wmm_platform/shell/gnome/, keeping the project root clean.
-    install.sh now detects the desktop environment and automatically copies the correct metadata.json and JS file (applet.js or extension.js) to the installation path.
-    GNOME Shell Extension Manager (gnome-shell-extension-prefs) is now offered as an installable dependency when running under GNOME.
-    Nautilus scripts integration: "Send to Monitor" and "Add to Favorites" actions are now available in the GNOME file manager.

**Changed**

-    All translatable strings are now centralized within WMM's own translation domain, completely independent of desktop environment system translations. This ensures full compatibility across Cinnamon, GNOME, and future platforms.
-    The interval selector in GNOME now uses plus/minus buttons instead of a slider, matching the Control Panel design and avoiding compatibility issues with GNOME 50.1.
-    Switches in the GNOME menu now use a custom implementation to prevent the menu from closing unexpectedly on activation.
-    metadata.json is no longer hardcoded; two templates are provided and the installer picks the right one at install time.

**Fixed**

-    Cache path inconsistencies that could spawn two engine instances have been resolved; settings_core.ini is now completed before ConfigHandler is created.
-    Progress bar visibility restored during source scanning and thumbnail generation, which had been broken after the panel refactoring.
-    Deleting an image source now correctly cleans its entries from image_cache.json and removes the associated thumbnails, including previously deactivated subfolders.
-    Auxiliary scripts (nemo_add_bookmark.py, nemo_send_to_monitor.py, add_bookmark.py) now use the correct cache path instead of a local fallback.
-    Source tree now shows expansion arrows immediately after adding a new source, without requiring a manual refresh.
-    Stale debug messages have been removed from the log viewer.

## v1.1.0 - 2026-06-16

**Added**

-    Thumbnail generation now runs automatically after adding a new image source; the gallery refreshes without any extra click.
-    Thumbnail gallery also refreshes immediately when an image source is removed or a folder is activated/deactivated from the context menu.
-    Source tree now preserves its expanded branches after actions such as activating or deactivating subfolders, so the view stays as you left it.
-    Strategic log_event calls have been added to trace key actions—thumbnail generation start/end, progress bar state, and a summary of active, inactive and deleted folders during sync—without spamming the log viewer.
-    A dedicated internal command (single_favorite_added) distinguishes single images added to favorites from full presets, keeping logs and notifications more precise.

**Changed**

-    Source tree now automatically shows expansion arrows for parent nodes right after a new source is added, eliminating the need for a manual refresh.
-    Translation support: All translatable strings are now centralized within WMM's own translation domain, completely independent of Cinnamon's system translations. This ensures full compatibility with other desktop environments and operating systems, while preserving English, Spanish and Catalan support.

**Fixed**

-    Control panel no longer creates its cache inside the applet folder; settings_core.ini is now completed with all derived keys in every installation scenario, so the cache reliably lives under ~/.cache/wmm.
-    Progress bar is again visible during source scanning and thumbnail generation, restoring feedback that had disappeared after the panel refactoring.
-    Deleting an image source now correctly cleans its entries from image_cache.json and removes the associated thumbnails, including previously deactivated subfolders.
-    Auxiliary scripts (nemo_add_bookmark.py, nemo_send_to_monitor.py, add_bookmark.py) now use the correct cache path instead of a local fallback, so their logs and notifications stay in sync with the engine.
-    Leftover debug messages that cluttered the log viewer have been removed.

## v1.0.0 - 2026-06-10 (Initial release)

WMM is a Cinnamon applet that gives you full control over your wallpapers across multiple monitors.

-    Built-in log viewer: real‑time event logging with filters and search, no terminal required.
-    Refactored Control Panel split into independent modules for better performance and maintainability.
-    Stability improvements: hardware change detection, startup checks and file locking to prevent crashes and data corruption.
-    Usability enhancements: contextual buttons in the image sources tree, visual feedback on the applet icon, and a multilingual help system.
-    Translation support for English, Spanish and Catalan, with the ability to inherit Cinnamon system translations.
