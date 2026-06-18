Changelog

v1.2.0 — 2026-06-18

Added

    Full GNOME Shell compatibility: new extension.js with panel indicator, context menu, slideshow controls, favorites management, and one-click wallpaper rotation with anti-spam protection.

    Desktop-specific metadata and JavaScript files are now stored under wmm_platform/shell/cinnamon/ and wmm_platform/shell/gnome/, keeping the project root clean.

    install.sh now detects the desktop environment and automatically copies the correct metadata.json and JS file (applet.js or extension.js) to the installation path.

    GNOME Shell Extension Manager (gnome-shell-extension-prefs) is now offered as an installable dependency when running under GNOME.

    Nautilus scripts integration: "Send to Monitor" and "Add to Favorites" actions are now available in the GNOME file manager.

Changed

    All translatable strings are now centralized within WMM's own translation domain, completely independent of desktop environment system translations. This ensures full compatibility across Cinnamon, GNOME, and future platforms.

    The interval selector in GNOME now uses plus/minus buttons instead of a slider, matching the Control Panel design and avoiding compatibility issues with GNOME 50.1.

    Switches in the GNOME menu now use a custom implementation to prevent the menu from closing unexpectedly on activation.

    metadata.json is no longer hardcoded; two templates are provided and the installer picks the right one at install time.

Fixed

    Cache path inconsistencies that could spawn two engine instances have been resolved; settings_core.ini is now completed before ConfigHandler is created.

    Progress bar visibility restored during source scanning and thumbnail generation, which had been broken after the panel refactoring.

    Deleting an image source now correctly cleans its entries from image_cache.json and removes the associated thumbnails, including previously deactivated subfolders.

    Auxiliary scripts (nemo_add_bookmark.py, nemo_send_to_monitor.py, add_bookmark.py) now use the correct cache path instead of a local fallback.

    Source tree now shows expansion arrows immediately after adding a new source, without requiring a manual refresh.

    Stale debug messages have been removed from the log viewer.

v1.1.0 — 2026-06-16

Added

    Thumbnail generation now runs automatically after adding a new image source; the gallery refreshes without any extra click.

    Thumbnail gallery also refreshes immediately when an image source is removed or a folder is activated/deactivated from the context menu.

    Source tree now preserves its expanded branches after actions such as activating or deactivating subfolders, so the view stays as you left it.

    Strategic log_event calls have been added to trace key actions—thumbnail generation start/end, progress bar state, and a summary of active, inactive and deleted folders during sync—without spamming the log viewer.

    A dedicated internal command (single_favorite_added) distinguishes single images added to favorites from full presets, keeping logs and notifications more precise.

Changed

    Source tree now automatically shows expansion arrows for parent nodes right after a new source is added, eliminating the need for a manual refresh.

    Translation support: All translatable strings are now centralized within WMM's own translation domain, completely independent of Cinnamon's system translations. This ensures full compatibility with other desktop environments and operating systems, while preserving English, Spanish and Catalan support.

Fixed

    Control panel no longer creates its cache inside the applet folder; settings_core.ini is now completed with all derived keys in every installation scenario, so the cache reliably lives under ~/.cache/wmm.

    Progress bar is again visible during source scanning and thumbnail generation, restoring feedback that had disappeared after the panel refactoring.

    Deleting an image source now correctly cleans its entries from image_cache.json and removes the associated thumbnails, including previously deactivated subfolders.

    Auxiliary scripts (nemo_add_bookmark.py, nemo_send_to_monitor.py, add_bookmark.py) now use the correct cache path instead of a local fallback, so their logs and notifications stay in sync with the engine.

    Leftover debug messages that cluttered the log viewer have been removed.

v1.0.0 — 2026-06-10 (Initial release)

WMM is a Cinnamon applet that gives you full control over your wallpapers across multiple monitors.

    Built-in log viewer: real‑time event logging with filters and search, no terminal required.

    Refactored Control Panel split into independent modules for better performance and maintainability.

    Stability improvements: hardware change detection, startup checks and file locking to prevent crashes and data corruption.

    Usability enhancements: contextual buttons in the image sources tree, visual feedback on the applet icon, and a multilingual help system.

    Translation support for English, Spanish and Catalan, with the ability to inherit Cinnamon system translations.
