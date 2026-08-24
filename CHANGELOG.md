<!--
SPDX-FileCopyrightText: 2026 makimanson
SPDX-License-Identifier: GPL-3.0-or-later

WMM - Wallpaper Multi-Monitor Manager
-->

# Changelog

## v1.3.0 - 2026-08-24

**KDE Plasma 6 integration**

WMM 1.3.0 introduces full support for KDE Plasma 6, including independent wallpapers per monitor, native Plasma crossfades, coordinated SYNC transitions, Spanned compositions distributed across Plasma containments, panel/workarea integration on Wayland, plasmoid lifecycle management, global shortcuts, Dolphin integration and D-Bus activation.

KDE wallpaper application now uses the native `org.kde.PlasmaShell.setWallpaper()` API through Gio/GLib. The previous refresh workaround based on `plasma-apply-wallpaperimage`, `evaluateScript()` and `reloadConfig()` is no longer used by the active wallpaper path.

**Added**

**Wallpapers, composition and transitions**

- Independent wallpapers, SYNC/ASYNC rotation and Spanned composition across supported desktop environments.
- Native KDE Plasma 6 Crossfade transitions through `org.kde.image`.
- Coordinated KDE SYNC transition using `current image → black → new image`.
- Double-buffered KDE masters per containment to guarantee a real URI change and preserve native transitions.
- GNOME and Cinnamon SYNC transitions reordered around a fixed black fade resource to avoid visible races while replacing the master image.
- Opportunistic preview caching and an optimized preview pipeline that reduces images before effects and composition.
- Shared Spanned reference-monitor resolution through `get_spanned_reference_hash()`.
- `active_composition` vault state for temporary composition overrides without duplicating global settings.

**Monitor detection and workarea integration**

- Stable KDE monitor/container mapping based on connector, UUID, priority and Plasma containment.
- Runtime-only resolution of Plasma `screenNum`; it is never used as persistent monitor identity.
- GNOME Wayland monitor detection through `org.gnome.Mutter.DisplayConfig`.
- Reactive GNOME monitor updates through `MonitorsChanged`.
- Real window workarea detection for the WMM panel on KDE/KWin, GNOME/Mutter and Cinnamon.

**Panel and thumbnails**

- Persistent expanded/collapsed state for Options, Favorites and Image Sources in `settings.json`.
- Persistent complete collapse of the left panel through `panel.collapsed`.
- Compact collapsed sidebar with Expand, Help, Debug Log Viewer and Restart actions.
- Visual separators between the side panel, Monitors and Thumbnails areas.
- New Favorites view in Thumbnails using `Gtk.Stack`, fed directly from `bookmarks_single_list.json`.
- Favorite thumbnails retain normal interactions: double-click opens the image and right-click removes it from favorites immediately.

**Favorites and slideshow UI**

- Reactive favorites/settings synchronization in desktop frontends.
- GNOME native slideshow slider with live minute display.
- GNOME Favorites list with a dedicated scroll area and fixed controls.
- Cinnamon Favorites list with independent hover for preset name and trash action.
- Cinnamon Favorites ScrollView now grows naturally up to a maximum height and only then enables vertical scrolling.
- Cinnamon scroll policy compatibility through runtime selection of `St.PolicyType` or `Gtk.PolicyType`.

**Desktop integration**

- KDE Plasma 6 plasmoid with D-Bus activation tied to `org.maki.wmm`.
- Global `Exit WMM` action with coordinated frontend, panel and engine shutdown.
- Native application launchers and autostart integration.
- KDE global shortcut through the `next-background` Desktop Action and KGlobalAccel.
- GNOME Shell extension support for versions 45–50.
- GNOME D-Bus bridge through `org.maki.wmm.Gnome`.
- Cinnamon applet lifecycle coordinated with the WMM engine.
- Dolphin and Nemo desktop/file-manager integration retained across their respective environments.

**Installation and compatibility**

- GTK, GLib, PyGObject and common runtime requirements are treated as shared dependencies across desktops, including KDE.
- Plasma 6 minimum-version validation during installation.
- GNOME Shell metadata compatibility declared for versions 45–50.
- Runtime capability detection used where GNOME/Cinnamon APIs differ between releases.
- D-Bus services, translations, desktop launchers and desktop-specific integrations are installed and refreshed during setup.

**Changed**

**Wallpaper application and composition**

- KDE wallpaper application migrated from configuration/reload-based refreshes to live `PlasmaShell.setWallpaper()` calls via Gio/GLib.
- KDE masters changed from one persistent path per containment to two alternating slots.
- KDE SYNC and ASYNC now rely on Plasma's native `org.kde.image` transition mechanism.
- Spanned reference selection is centralized and shared between engine and panel.
- Preview generation now performs early resizing and reuses in-memory results instead of reloading temporary previews from disk.
- Temporary composition state is separated from global configuration and is cleared when returning to normal rotation.

**Panel and UI**

- Panel expansion preserves the top position of the window when sections grow beyond the available workarea.
- The right side of the panel automatically absorbs the space freed when the left side is collapsed.
- Options header now integrates Help, Debug Log Viewer, Restart and Collapse without consuming an additional row.
- Horizontal and Vertical remain navigation controls in Thumbnails; Favorites is a separate view and does not alter H/V semantics.
- Cinnamon Favorites rows use natural height instead of distributing unused ScrollView height between items.

**Frontend synchronization and lifecycle**

- KDE plasmoid settings/bookmarks synchronization uses `DBus.SignalWatcher` instead of polling.
- Settings/bookmarks file monitoring reacts to completed logical writes rather than every intermediate file event.
- KDE, GNOME and Cinnamon keyboard rotation paths invoke `send_command.py` directly.
- Frontend destruction no longer implicitly shuts down the engine; explicit Exit/Remove actions control global shutdown.
- GNOME extension startup waits for the WMM service before constructing translatable UI.
- GNOME monitor-event handling uses its own D-Bus connection/main-loop context.
- GNOME and Cinnamon shortcut setup detects runtime schema capabilities instead of assuming one desktop version.

**Fixed**

**Wallpapers and Spanned**

- Incorrect KDE containment association with identical monitors.
- Global KDE flicker caused by the former workaround around KDE bug 506862.
- Missing KDE transition when image bytes changed under an unchanged URI.
- Spanned vault corruption when the primary monitor did not match the canvas orientation.
- Divergence between physical and preview composition during temporary effects/bookmarks.
- Accidental double application of effects in Fit mode.
- Busy state left active after exceptions, which could block future rotations.
- Cinnamon race where `wallpaper_master.jpg` could be overwritten while still visible.
- GNOME reuse of stale cached wallpaper content after replacing a same-path master.
- GNOME fade-resource cache races and interference from the desktop primary color.

**Panel and favorites**

- Panel position shifts when expanding sections near the workarea limit.
- KDE contextual menu/settings updates appearing one opening late.
- GNOME Favorites lists disappearing or remaining empty across API differences between Shell versions.
- GNOME Favorites scroll affecting the entire submenu instead of only the preset list.
- GNOME slideshow slider remaining interactive while disabled.
- Cinnamon Favorites ScrollView using only part of the available menu width.
- Cinnamon favorite rows showing excessive vertical separation because each row expanded into unused ScrollView space.

**Integration and startup**

- KDE D-Bus channel registration failure on first clean startup.
- D-Bus activation race immediately after installing a new user service.
- KDE global-shortcut registration races caused by dynamic `.desktop` discovery through KSycoca.
- Incorrect or unfriendly KDE shortcut naming.
- GTK dependencies omitted from KDE installation flow.
- GNOME shortcut setup failures caused by schema differences in `binding` and `enable-in-lockscreen`.
- GNOME monitor-event handling falling back incorrectly because no D-Bus main loop was attached.
- GNOME Wayland panel sizing based on inaccurate `Gdk.Monitor.get_workarea()` results.
- GNOME first-run translation failures caused by gettext cache timing.

**Removed**

- Active KDE wallpaper workaround based on:
  - `trigger_transparent.png`
  - `plasma-apply-wallpaperimage`
  - manual `Image` writes in `appletsrc`
  - `evaluateScript()`
  - `reloadConfig()`
- Legacy global KDE FillMode forcing from the active wallpaper path.
- Duplicate historical Spanned-selection logic.
- Redundant preview disk reloads and GTK rescaling.
- KDE/GNOME/Cinnamon `wmm-next.sh` wrappers.
- Auxiliary KDE shortcut launcher and KSycoca retry logic.
- KDE launcher dependency on `gdbus` side-effect activation.
- Automatic engine shutdown from plasmoid destruction.
- GNOME dependency on `Gdk.Monitor.get_workarea()` for real Wayland workarea.
- Obsolete GNOME Favorites container hierarchy and unconditional `add_actor()` usage.
- GNOME slideshow +/- interval buttons.
- Hardcoded GNOME hover/active colors where the desktop theme can provide them.

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
