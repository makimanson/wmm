<!--
SPDX-FileCopyrightText: 2026 makimanson
SPDX-License-Identifier: GPL-3.0-or-later

WMM - Wallpaper Multi-Monitor Manager

Changelog
-->

# v2.0.0 - 2026-11-20

## HIGHLIGHTS

### GNOME Shell 51

- Extended WMM support to **GNOME Shell 51**, retaining compatibility with GNOME Shell 45 onward.

### Windows — native integration

- First WMM system-tray frontend for Windows, with menus, rotation, presets and tools.
- Native IPC, single-instance management, shortcuts, notifications and Explorer integration.
- Private runtime, standalone executable, light/dark themes and unified PowerShell 5.1 maintenance.

### Wallpapers Online

- Online gallery with filtered search, **Load More** pagination, thumbnails, selection and original-image downloads.
- Online editing via drag-and-drop onto virtual monitors, with live desktop preview.
- Automatic Sources, Library and Thumbnails import/synchronization; duplicate downloads avoided through cached originals.
- Persistent per-image **Website** provenance, provider branding and links to original pages.
- Personal API key management from the Panel, without storing credentials in settings.
- Preventive request limits, HTTP 429 handling and explicit acceptance of responsible-use terms.
- WebP thumbnail support in the Windows runtime, verified in compiled and installed builds.
- **Integrated providers:** Wallhaven and Alpha Coders.

### Image metadata

- Wallpaper metadata overlay for images containing supported EXIF/XMP data.
- Configurable visible fields, including geographic information when available.
- Per-monitor overlay positioning, opacity and display settings.
- Per-monitor settings adapt the overlay to each wallpaper.

### Thumbnails — progressive display

- Sequential generation and incremental rendering of new and cached thumbnails.
- Stable Library navigation as the gallery grows, without reordering visible items.

### Selective rotation and favorites

- Selectable Sources folders for rotation, with independent Active/Inactive flags.
- Separate H/V rotation queues for the full library, Selective Rotation and Favorites Only.
- Verified mutual exclusion between Selective Rotation and Favorites Only, with Slideshow remaining enabled.

### Panel — adaptive geometry

- Resizable Displays/Thumbnails divider with persistent position.
- Smooth virtual-monitor scaling with preserved image references.

## Added

### Windows

- `win32.py` backend with Named Pipes, `LockFileEx` and private gettext resolution.
- System-tray frontend with main/context menus and recovery after Explorer restart.
- Favorites, Slideshow, interval, SYNC/ASYNC, Spanned, preset and tool menus.
- Event-driven *busy* detection via `ReadDirectoryChangesW`, without polling.
- Configurable global shortcut via `RegisterHotKey`.
- Notifications via `Shell_NotifyIconW` and `WM_COPYDATA`.
- Explorer and desktop actions to send, span or favorite images.
- Per-user autostart via `HKCU\...\Run`.
- Light/dark theme tracking in the frontend and GTK forms.
- PyInstaller build with a private runtime.

### Windows — installation and maintenance

- `wmm-install.ps1` as the authoritative Install, Upgrade, Downgrade, Reinstall and Uninstall manager.
- `wmm-install.cmd` as the PowerShell 5.1 STA launcher.
- Windows Forms operation/progress dialogs with a separate runspace worker.
- Self-contained `wmm-repair.zip` containing the runtime using `ZIP_STORED`.
- Transactional staging, data/settings preservation, integration backups and rollback.
- Start menu/desktop shortcuts and uninstall registration managed by PowerShell.
- Operation selection based on installed, local and GitHub-published versions.
- Asynchronous GitHub queries that do not block local operations.
- Worker-side verification of the selected source and version.
- Localized forms and operations in English, Spanish and Catalan.
- Windows theming for native forms and compatible title bars.
- Milestone-based progress replacing `Marquee`.
- Reinstall and repair through Install Manager.
- Previous-installation recovery if replacement fails.

### Wallpapers Online

- `online_wallpapers.py`: shared provider registry, search, thumbnail/original caches, image downloads and source-page links.
- `online_section.py`: filters, asynchronous gallery, multi-selection, download states and criteria-bound, on-demand **Load More** pagination.
- `application/x-wmm-online-image` D&D target for dragging gallery images onto virtual monitors.
- Original-image resolution from Sources, temporary cache or download, reusing existing files.
- Live Online editor preview via `apply_edit_preview`.
- Import of originals into Sources and path updates when edits are accepted.
- Library synchronization and differential thumbnail regeneration after an edit or download.
- Optional preset saving and Favorites updates.
- Reactive *Downloaded* indicator to avoid duplicate downloads.
- Persistent per-image Website provenance and provider links from Online and Library.
- `image_online.json` with compact `[provider, id, url]` records and batched writes.
- Provenance removal/recovery when Online originals are removed and re-imported.
- Responsible-use screen with explicit consent and independent **Do not show again** preference.
- Preventive request throttling: 40 local Wallhaven queries per 60 seconds, plus HTTP 429 and `Retry-After` handling.
- Per-provider branding with banners, logos and text fallback.
- Dedicated **API Keys** form accessible from Online, with provider selection, linked personal file and **Browse**/**Unlink** actions.
- Only personal-file paths persisted in `settings.json`; credentials read from selected files.
- File validation before linking, persistence checks and unlinking without modifying user files.
- Alpha Coders shared key fallback when no personal path is configured; the shared key is neither displayed nor stored in the form.
- API Keys file chooser adapted to Windows light/dark themes and drive navigation.
- WebP thumbnail support on Windows.
- Reuse of previously downloaded or previewed originals to prevent duplicate downloads.
- **Integrated providers:** Wallhaven and Alpha Coders.

### Thumbnails — worker and diagnostics

- Sequential `WMM-Thumbnails` worker, handing widgets to the GTK main thread.
- Progressive rendering of new and cached thumbnails.
- Progress tracked through completion of both generation and on-screen rendering.
- Pillow `Truncated File Read` warnings logged with the source-image path.

### Selective rotation by Sources

- Per-folder `[active, selective]` state in `scan_index.json`.
- Context actions to select/deselect folders and subtrees for rotation.
- Green/amber indicators for full or partial selection.
- **Selective rotation** switch in Options, independent of persisted selection flags.
- `sel_rotation_h.json` and `sel_rotation_v.json` added to persisted-state preservation.
- Differential reconciliation of selective lists on Sources changes.
- Informationally disabled switch when no active folders are selected.
- Event-driven Selective availability updates on Sources events.

### Individual-favorite rotation

- `bookmark_rotation_h.json` and `bookmark_rotation_v.json`, independent of other rotation pools.
- H/V reconciliation on changes to `bookmarks_single_list.json`.
- Migration of the previous favorites rotation history to the new queues.

### Virtual monitors

- Direct D&D from Thumbnails, with live wallpaper application and selective Vault updates.
- Image swapping between active monitors via `application/x-wmm-monitor`.
- Source-monitor selection when spanning one image across all monitors.

### Linux and common tools

- Shortcut manager for GNOME, KDE Plasma 6, MATE and XFCE.
- GNOME Shell frontend supporting versions 45–51 and event-driven preset updates.
- Separate Favorites, Slideshow and Tools submenus in GNOME.
- Contextual placement of `Add Preset Favorite` in GNOME, KDE and MATE.
- `licenses/` tree integrated into Docs Viewer.
- Transactional POT/PO validation in Translation Manager.
- Dedicated WMM icon for Plasma, installed/removed with its integration.
- Actual **Next Background** shortcut displayed in the KDE menu.

### Documentation

- Updated `README_es.md`, `README.md` and `Readme.txt` for Windows, GNOME Shell 45–51, Online providers and installation/uninstallation procedures by distribution type.
- Updated bilingual quick-install guide to v2.0.0, covering Windows open-code and compiled distributions.
- Online-provider information retained in the acknowledgments section.

### Image metadata

- Extraction and normalization of XMP/Dublin Core, XMP GPS and `Iptc4xmpExt:LocationCreated`.
- EXIF/XMP cache migrated to schema 3, with differential reuse.
- Demo-image metadata available from the first wallpaper.
- Initial Image Metadata preferences and compact confirmation dialog.
- Asynchronous EXIF extraction, `mtime_ns`-based caching and inter-process exclusion.
- Local GPS enrichment via `geo_lookup.py`.
- Options for font, position, margins, opacity and visible fields.
- Metadata overlay rendering via PangoCairo/Pillow, including Spanned compositions.
- Metadata changes applied without forcing wallpaper rotation.

## Changed

### General rotation and Panel

- Replaced anti-repeat history with `rotation_h.json` and `rotation_v.json`.
- Differential Sources reconciliation while preserving consumed images.
- One-time `match_orientation` initialization, respecting subsequent user changes.
- Panel options reordered to match their visual layout.
- Selective Rotation retains folder flags when disabled; selecting folders does not automatically enable it.
- `get_smart_selection()` consumes only the active pool and honors H/V filtering.
- Full-library, selective and favorites pools retain independent progress.
- Selective Rotation and Favorites Only are mutually exclusive at Engine level.
- Enabling Favorites Only or Selective Rotation keeps Slideshow enabled.

### Panel — layout and presentation

- Displays and Thumbnails arranged in a vertical `Gtk.Paned`.
- Virtual monitors scaled from `GdkPixbuf` references without recomposition during dragging.
- Expansion constrained by available width; progressive Displays contraction.
- Persistent divider position and spacing around its handle.
- Virtual layout and dimensions centralized in `monitor_manager.py`.
- D&D frames and targets unified across Normal and Edit modes.
- Options controls normalized using `pack_start` and vertical containers with `spacing=2`.
- Monitor switches use a local 2-pixel margin and native GTK sizing.

### Wallpapers Online and Library

- Compact search controls without removing filters.
- Orientation and aspect ratio grouped in a visual H/V selector.
- **Search** and **Load More** react to filter changes and restored criteria.
- Provider-specific capability rules.
- Batched provenance insertion through `ConfigHandler`.
- Compact provenance format and decoupled reading in `image_online.json`.
- Horizontal/Vertical ordering planned before progressive Library rendering.
- New thumbnails appended visually without reordering rendered items.
- Thumbnail generation separated from GTK presentation.
- Thumbnail preparation optimized with `os.scandir()` and JPEG quality 75.

### Wallpapers Online — compatibility and originals

- Previously downloaded originals reused from temporary storage when importing into Sources, without a second download.
- After import, monitor paths referring to temporary files are updated; Sources and thumbnails are synchronized.
- Alpha Coders retains the standard `thumb` thumbnail while alternatives are evaluated; Wallhaven uses a higher-resolution thumbnail with fallback where applicable.

### Windows — maintenance experience

- Manager operations differentiated by effective version and source.
- Compact selector with dynamic buttons and two-column version details.
- Progress dialog with long messages and line-fitted log output.
- Graceful frontend shutdown before replacements, with a process barrier during Reinstall.

### Windows — GTK presentation

- Windows `GtkSpinButton` sizing and visual states adjusted for both themes.
- File chooser headers and columns adjusted for contrast without changing behavior.
- API Keys file chooser integrated with existing Panel/dialog styles.

### Editing and Library

- Deferred application in normal editing and presets; immediate live preview in Online editing.
- Temporary selection and Spanned source centralized in `image_selection.py`.
- Accept action and preset checkbox adapted to editing context.
- Contextual editing tooltips and active-view navigation in Thumbnails.

### Frontends and platform

- Independent GNOME Shell 45–51 gestures and menus.
- Persistent menus and available-area-aware tooltips in MATE and XFCE.
- Shortcut capture split into Clear, Cancel and Accept actions.
- Single Panel instance via `Gtk.Application`.
- Send to Monitor coordinated through platform locks.
- Slideshow and metadata changes coalesced to avoid repeated recompositions.
- Common data assets centralized in `wmm_platform/shell/data`.
- Gettext resolution delegated to `PlatformManager`.
- XFCE **Next Background** entry uses separate action and shortcut labels.

## Fixed

### Panel and Library

- Intermittently missing virtual-monitor frames after Panel resize.
- `Gtk.Fixed` synchronization in Normal, Edit and preset-loading modes.
- Visual aspect-ratio restoration when loading presets.
- Repeated monitor scaling without cumulative quality loss.
- Virtual-monitor updates when displays are connected/disconnected during editing.
- Preservation of images assigned to unavailable monitors when updating presets.
- Unintended thumbnail shifts/reordering during generation.
- Recoverable EXIF/TIFF warnings identified by source file in Debug Log.

### Common Engine

- Slideshow startup with `persist_on_reboot` and no initial rotation; corrected timer initialization in `WMMDaemon.run()`.
- [Issue #14](https://github.com/makimanson/wmm/issues/14) fix verified with persistence enabled and disabled (Thanks **Nilloow** for helping identify this issue).

### Linux and Library

- Automatic Options/Favorites/Sources collapse based on usable left-column height.
- GNOME Shell 51 adaptation for `St.BoxLayout` and wallpaper cache.
- Stable Cinnamon menu/submenu widths.
- D&D between monitors and source-image selection in Spanned mode.
- H/V orientation based on EXIF and `exif_transpose()` without modifying originals.
- EXIF reading and validation of valid PNG files.
- Pillow import and `__*__` key filtering in `sync_bookmarks_flat_list()`.
- Sources synchronization and *Downloaded* updates after Online image imports.
- Online live preview isolated from deferred behavior in other edit modes.
- `gi-cairo` dependency added for Linux metadata rendering.
- Slideshow activation from Favorites Only in the Panel via `update_timer_settings`.
- Selective availability updated on selection and Sources Active/Inactive changes.
- XFCE **Next Background** width no longer reserves `Gtk.AccelLabel` space.

## Removed

- Legacy `history.json` and `history_vault.json` from regular rotation.
- Legacy geometry methods `_center_monitor_layout()` and `_adjust_fixed_size()`.
- `set_window_size_limit()` from the Windows backend.
- Unused Panel variables `cache_base` and `self._sources_need_refresh`.
- POSIX dependencies and `msvcrt.locking()` from native Windows paths.
- Legacy PID-based single-instance and Send to Monitor controls.
- `GtkMenuShell` from primary Windows popups.
- Immediate shortcut removal on Clear and obsolete state from the previous dialog.
- Temporary Online diagnostic traces.
- Separate `wmm-uninstall.ps1`, superseded by functions in `wmm-install.ps1`.
- Redundant detail controls and unused translation keys from the Windows selector.
- Discarded thumbnail-insertion pagination/sorting and navigation-compensation attempts.

# v1.5.0 - 2026-09-29

WMM 1.5.0 introduces full support for **XFCE 4.20 / X11** and consolidates a common Linux architecture for **Cinnamon, GNOME Shell, KDE Plasma 6, MATE and XFCE**, separating the core, persistent data, cache and desktop-specific frontends.

This release also strengthens the Install, Upgrade, Reinstall and Uninstall lifecycles, expands file manager and desktop integrations, consolidates the Translation Manager, and completes migration from previous layouts without losing user configuration.

## Added

- Added built-in branded wallpaper fallback when the user library contains no images, with automatic horizontal, vertical and Spanned selection.
- Added dedicated `WMM-presentation.jpg` project artwork while keeping `screenshots/` reserved for the four functional fallback wallpapers.

### XFCE

- Added full support for **XFCE 4.20 / X11**.
- Added a new wallpaper backend based on a virtual master canvas applied through `xfconf`.
- Added reactive XRandR integration for monitor topology and primary-monitor changes.
- Added a dedicated `StatusNotifierItem` frontend without requiring a C plugin or compiled library.
- Added a main menu with Favorites, Slideshow, ASYNC/SYNC, Spanned Mode and presets.
- Added automatic frontend recovery after `xfce4-panel` restarts, without polling or artificial delays.
- Added `org.maki.wmm.xfce.desktop` launcher and autostart integration.
- Added integration with native XFCE shortcuts while leaving the actual key combination to the user.
- Added WMM actions to Thunar for:
  - Add to favorites;
  - Send to Monitor;
  - Span image across all screens.
- Added a Thunarx provider for operating on the wallpaper of the selected monitor directly from the XFCE desktop.
- Added XFCE-specific preflight checks for xfconf-query and Wnck 3.0 Introspection.

### Desktop integrations

- Added a Cinnamon frontend separated from the common core.
- Added a GNOME frontend separated from the common core.
- Added a dedicated MATE runtime unit under `frontends/mate/`.
- Added `settings_core.ini` to frontends to explicitly resolve the common core and persistent data.
- Added a Caja desktop context menu with **Span image across all active screens** and **Add to favorites**.
- Added an independent Nemo desktop context menu for actions on the active wallpaper.
- Updated Dolphin integration to use the common topology.

### Translation Manager

- Consolidated `pot_manager.py` as a standalone **Translation Manager**.
- Added POT and Search views.
- Added POT generation and comparison for Python and JavaScript.
- Added detection of New and Removed strings.
- Added search by `msgid`, translations and source references.
- Added direct editing and validation of `.po` catalogs.
- Added independent persistence of its visual state.

### Installer

- Added optional dependencies for Nautilus, Caja and Thunarx integrations without blocking the main installation.
- Added local `wmm-repair.zip` package for Repair/Reinstall.
- Normalized launcher identities as `org.maki.wmm.<desktop>.desktop`.
- Added optional Thunarx 3.0 Introspection and thunarx-python dependencies for XFCE desktop integration without blocking the main WMM installation.

## Changed

### Common architecture

- Separated the common WMM core from desktop-specific frontends.
- The Linux topology now uses:
  - core: `~/.local/share/wmm@maki/`;
  - persistent data: `~/.config/wmm@maki/data/`;
  - cache: `~/.cache/wmm/`;
  - desktop-specific frontend according to the active environment.
- ConfigHandler, communication channels and common tools now use platform-resolved paths.
- About, Debug Log Viewer, Docs Viewer, Install Manager and launch profiles were adapted to the new topology.
- Main WMM processes now use specific visible process names under Linux instead of appearing generically as `python3`.

### Install / Upgrade / Reinstall

- Upgrade and Reinstall now use clean staging while preserving persistent data.
- The previous frontend is unloaded before stopping the engine and replacing installed trees.
- Rollback now stops any newly started runtime before restoring the previous installation.
- Cinnamon, GNOME, KDE, MATE and XFCE use recovery cycles adapted to their native lifecycle.
- Legacy resources remain recoverable until `commit()` and are removed only after a successful transition.
- WMM-owned process shutdown now uses Linux `pidfd` handles with event-driven waiting, preventing PID reuse races and stale runtimes without introducing polling.
- Replace now aborts safely if an existing WMM runtime cannot be stopped, instead of forcing an unsafe replacement or using a SIGKILL fallback.

### KDE Plasma 6

- KDE now uses the common core while keeping the plasmoid as a native frontend under `plasma/plasmoids/org.maki.wmm`.
- The current launcher and global-shortcut identity is now `org.maki.wmm.kde.desktop`.
- KGlobalAccel management now belongs exclusively to `kde.py`; the installer no longer modifies shortcuts.
- Upgrades from WMM 1.4.x preserve the user's selected key combination while replacing the legacy KGlobalAccel identity.
- On clean installations with **Plasma >= 6.6.6**, the installer restarts `plasma-plasmashell.service` so WMM can be materialized without ending the user session.
- On older Plasma versions, or when the automatic restart fails, session restart remains the safe fallback.

### Cinnamon / GNOME / MATE

- Cinnamon automatically migrates older installations using the `wmm-applet@maki` UUID while preserving panel, position and instance.
- GNOME protects and replaces the extension as a frontend independent from the core.
- MATE uses its native `--unload/--restore` lifecycle while preserving applet identity and position.
- Cinnamon and MATE keep their frontends hidden until the engine has prepared translations and acquired `org.maki.wmm`.
- Cinnamon now also defers its native `finalizeContextMenu()` until translation readiness, preventing Cinnamon's own early `dgettext()` lookup from caching a missing WMM catalog during a completely cold first load.

### File managers

- Centralized preparation of the common wrappers used by Dolphin, Caja and Thunar.
- Nemo now keeps WMM file actions and wallpaper actions in separate menus.
- Missing optional integrations no longer prevent WMM from starting or using the remaining functionality.

## Fixed

### XFCE

- Fixed wallpaper refresh when XFCE repeatedly received a logically equivalent path by introducing double buffering.
- Fixed races between autostart, the engine and `StatusNotifierWatcher`.
- Fixed icon re-registration after `xfce4-panel -r`.
- Prevented duplicate frontend instances.
- Fixed menu geometry when expanding or collapsing sections.
- Fixed interaction with internal controls under the `Gtk.Menu` grab.
- Fixed Favorites height, scrolling and alignment.
- Fixed Replace and Uninstall lifecycle so XFCE processes cannot remain running from deleted code.
- Validated the post-refactor XFCE Uninstall → Install → Reinstall → startup lifecycle with a clean WMM process inventory.
- The icon is now shown only when the frontend is fully built, operational and translated.

### Installer / rollback

- Fixed rollback after a failed relaunch so orphaned engines cannot continue running from already removed trees.
- Fixed detection and recovery of partially dismantled installations.
- Fixed historical path inconsistencies between the core, persistent data, communication channels and configuration.
- Fixed the installed README presentation-image path when the package `/wmm` level becomes the installed `APP_DIR` root, while preserving the source/GitHub path unchanged.

### Cinnamon / Nemo

- Fixed Upgrade from Cinnamon installations using the legacy UUID.
- Preserved the exact applet position and instance during migration.
- Restored the WMM icon in Cinnamon Settings.
- Fixed premature UI loading before translations are available.
- Fixed completely cold Cinnamon first-load translations by deferring the native `finalizeContextMenu()` until `org.maki.wmm` readiness, so Cinnamon cannot cache a failed WMM-domain lookup before the `.mo` catalogs exist.
- Removed a redundant Cinnamon bootstrap icon assignment while preserving the initial geometry-producing icon and the normal idle/busy icon lifecycle.
- Fixed duplicate and incomplete WMM action migrations in `actions-tree.json`.
- Nemo can now refresh its contextual layout without requiring a session restart.

### GNOME

- Fixed migration so core and persistent data remain outside the extension directory.
- Fixed publication of partially built frontends during Replace or rollback.
- Recovery is now validated through actual D-Bus availability of both the extension and the engine.
- Fixed legacy launcher, service and shortcut remnants after Upgrade.

### KDE Plasma 6

- Fixed detection and migration of KDE layouts from WMM <= 1.4.x.
- Fixed migration of legacy `Exec=` entries in the modern Dolphin Service Menu.
- Fixed cleanup of current and legacy KDE resources during Uninstall.
- Fixed KGlobalAccel migration from 1.4.x → 1.5.0:
  - the user-selected shortcut is temporarily preserved;
  - the previous identity is removed;
  - KSycoca is rebuilt;
  - the current identity is registered;
  - the user's key combination is restored and confirmed.
- Validated a real **1.4.0 → 1.5.0** Upgrade while preserving the global shortcut.
- Validated a clean 1.5.0 installation on Plasma 6.6.6 with a hot Plasma restart and WMM fully operational without starting a new session.
- Resolved the historical installer limitation caused by KDE bug 515234: on clean installations, Plasma >= 6.6.6 can safely restart `plasma-plasmashell.service` to materialize WMM without ending the session, while older versions retain session restart as the safe fallback.

### MATE / Caja

- Fixed initial popup geometry with a vertical panel and an adjacent monitor.
- Fixed dynamic menu growth with panels in any orientation.
- Fixed icon margins so they no longer artificially increase applet thickness.
- Fixed a regression that prevented the icon from being materialized correctly.
- Fixed untranslated first load.
- Fixed MATE frontend runtime paths.
- Validated the MATE Install/Reinstall/Uninstall lifecycle after the final runtime fixes.
- Suppressed duplicate DEBUG logging during deliberate MATE fade-transition settings refreshes without changing the visual transition timing.
- Consolidated the Caja **WMM Manager** context submenu for the active wallpaper.

### Uninstaller

- Full Uninstall now continues even when part of the desktop integration is already missing.
- Legacy cleanup is limited to artifacts historically proven to belong to WMM.
- Python extension cleanup removes only WMM bytecode while preserving shared directories.
- Caja Actions preserves unrelated configuration and actions when removing WMM.
- Fixed the possibility of accidentally activating the D-Bus service during Uninstall.
- WMM-owned processes are now terminated through stable `pidfd` handles; Uninstall remains recoverable if a runtime cannot be stopped cleanly and reports when logout/login is the safe final boundary.

## Removed

- Removed direct KGlobalAccel management from the installer; it is now centralized in `kde.py`.
- Removed historical `APP_DIR/data` hardcodes.
- Removed the legacy XFCE persistent-data topology.
- Removed dependency on XFCE's native slideshow.
- Removed sleeps and polling previously used to wait for frontends.
- Removed the possibility of leaving XFCE frontends indefinitely waiting for D-Bus names.
- Removed the dependency on `Gtk.ImageMenuItem` and the duplicate `xfce-frontend.css`.
- Removed the old `wmm-test.py` PoC; XFCE Desktop integration is now formally implemented through Thunarx.
- Removed assumed MATE legacy resources that were never part of a published release.
- Removed dependency on a self-contained GNOME extension embedding core and persistent data.
- Removed old Caja provider names as runtime authorities; they are retained only for legacy cleanup.
- Removed premature UI materialization before translations are available.

# v1.4.0 - 2026-09-16

## Added

### MATE integration

- Added full **MATE** support, including wallpaper backend, multi-monitor composition, transitions, MATE Panel integration and dedicated launcher.
- Added native MATE Panel applet with:
  - manual rotation on click;
  - busy/idle visual state;
  - Slideshow and Favorites controls;
  - access to Control Panel, Sync Library, Install Manager, Debug Log Viewer, Help and About.
- Added Wnck-based geometry and workarea support to keep Control Panel correctly positioned and sized under MATE/X11.
- Added custom **Next Background** shortcut through MATE native keybinding system.
- Added **Caja Actions** integration for:
  - Add to Favorites;
  - Send to Monitor;
  - Span image across all screens.
- Added native `python-caja` extension for **Span Current Image** from desktop context menu.
- Added single-instance protection for MATE applet.
- Added themed icons to MATE applet menu for Add Preset Favorite, Tools and About WMM Manager.
- Added visual separator between Tools and About WMM Manager.

### Panel and user experience

- Added animated side collapse/expand transition for Control Panel, validated on Cinnamon, GNOME, KDE Plasma and MATE.
- Added global **Sources need resynchronization** notice when logical folder state and cache materialization still need reconciliation.
- Added **Generate thumbnails** context action to explicitly materialize an active child folder with no cache.
- Added permanent contextual help under **Recursive** to distinguish structural scope from Active/Inactive state.
- Added a new generic `docs_viewer.py` capable of displaying different WMM Markdown documents with automatic language resolution.
- Added independent application and process identities for each opened document, allowing documents such as **Help**, **Changelog**, **README**, and **License** to remain open at the same time.
- Added direct **Help** and **Changelog** actions to the Cinnamon, GNOME, KDE Plasma, and MATE launchers.
- Added internal access from **About** to **Changelog**, **Help**, and **License**, while keeping GitHub as an external link.

### File manager integration

- Added native **Nautilus** integration through `nautilus-python` and `Nautilus.MenuProvider`.
- Added Nautilus GI **4.0 and 4.1** compatibility.
- Added **Span image across all screens** action for images selected in Caja, Nautilus, Dolphin and Nemo.
- Added dedicated file-manager dependency category (`FILE_MANAGER_DEPENDENCIES`).
- Added unified Dolphin `wmm-menu.desktop` template for KIO **6.30.0+**, grouping WMM actions under **WMM Manager** submenu:
  - Add to favorites;
  - Send to monitor;
  - Span image across all active screens.

### Common tools and maintenance

- Added common GTK3-based **About WMM Manager** viewer backed by `about.json`.
- Added **Install Manager**, standalone GTK interface for Upgrade, Reinstall/Repair, Uninstall and output inspection through VTE.
- Added local `wmm-repair.zip` package for self-contained repairs/reinstalls.
- Added pre-validation for Upgrade packages.
- Added standalone services for Install Manager and Debug Log Viewer where desktop environment requires them.
- Added Desktop Actions to `.desktop` launchers for Install Manager, Debug Log Viewer and About WMM Manager.
- Verified integration of these tools with Cinnamon, GNOME and KDE; under MATE they remain available even if standard menu does not expose every Desktop Action.
- Verified compatibility with **Cinnamenu v5.6.2+**.

### Translation and development tools

- Added contextual opening from `pot_manager.py` at first relevant source line.
- Added common `open_file()` API for Linux, Windows, macOS and fallback.
- Added `launch_profiles.json`.
- Added resizing for main `pot_manager.py` columns.

## Changed

### Installation and maintenance lifecycle

- Reworked installation system around `wmm-install.sh` for Install, Upgrade and Reinstall/Repair.
- `wmm-uninstall.sh` remains official standalone uninstaller.
- Upgrade and Reinstall now use clean staging while preserving persistent data.
- Upgrade/Reinstall now stops the previous engine after unloading the desktop frontend and before activating the staged tree, preventing the old runtime from surviving across replacement.
- After Reinstall/Upgrade, desktop integration is restored through the native lifecycle of each supported environment.
- Cinnamon keeps its specific reload cycle for translations.
- KDE Plasma Reinstall/Upgrade now preserves the installed plasmoid through the atomic swap without invoking `kpackagetool6 --upgrade` on its own installed directory.
- KDE Plasma restores WMM after Reinstall/Upgrade by reactivating `org.maki.wmm` through D-Bus; the System Tray rematerializes the existing plasmoid instances without restarting `plasmashell`.
- `about.json` is now primary installed-version source, with fallback to `metadata.json`.
- Direct `wmm-uninstall.sh` execution now shows header and confirmation.
- Added internal `--managed` mode.
- Installers launched from a real console keep final pause.
- Improved Install Manager VTE terminal.
- Improved maintenance button handling.
- Late results from asynchronous checks no longer re-enable Upgrade during maintenance.
- After Reinstall/Upgrade, actually installed version is re-read before actions are recalculated.
- `wmm-uninstall.sh` now removes `wmm-menu.desktop` as well as legacy Dolphin Service Menus.
- Under MATE, Upgrade/Reinstall now validates administrative credentials with `sudo -v` before unloading frontend, avoiding half-finished WMM lifecycle when authorization cannot be obtained.
- Install Manager VTE terminal receives focus immediately after maintenance starts, making password entry on `sudo` prompts unambiguous.
- MATE Reinstall/Upgrade unloads and restores applet through native `mate-launcher.py` lifecycle (`--unload` / `--restore`) while preserving MATE Panel object identity, position and anchoring.
- MATE applet state is preserved during swap and also participates in rollback path, preventing failed replacement from leaving frontend missing.
- `wmm-uninstall.sh` deliberately keeps a more defensive policy than Reinstall: it tries to clean runtime gracefully, but retains forceful termination as fallback and does not depend on WMM tree to complete removal of a damaged install.

### Frontend menus and recovery tools

- Unified final menu structure:
  - `Tools`;
  - `About WMM Manager`;
  - `Exit WMM` where applicable.
- `Tools` groups operational utilities while About stays outside.
- Install Manager and Debug Log Viewer now launch directly from frontends, with no engine dependency.
- `force_rotation` is now deliberately **non-cumulative**.
- Paths using `send_command.py` share a common admission guard, while `_dispatch_command()` keeps a second authoritative defense.
- KDE and GNOME receive engine busy state through reactive D-Bus (`GetBusy` / `BusyChanged`), with no polling.
- KDE and GNOME show `view-refresh` while engine is busy.
- KDE plasmoid **Next Background** button is disabled while busy.
- GNOME keeps menu open during repeated **Next Background** activations while busy, preserving `_keepMenuOpen`.
- Cinnamon and MATE keep local guards and visual feedback.

### MATE

- WMM now forces/verifies:
  - `picture-options = spanned`;
  - `draw-background = true`;
  - `background-fade = true`.
- `gtk-enable-animations` remains user-controlled.
- Refined MATE transitions to use native Crossfade.
- Improved icon feedback when manual rotation starts.
- Reworked MATE menu with Favorites, Slideshow and Tools as inline blocks.
- Replaced MATE-specific About with common About viewer.

### File managers

- Nemo and Caja actions are created only when missing, preserving user customizations.
- Nemo **WMM Manager** submenu adds only missing official actions.
- If user deliberately removes WMM submenu after initialization, WMM does not recreate it automatically.
- Custom Caja context extension remains kept up to date.
- Nautilus dependencies are checked only when Nautilus is installed.
- Dolphin detects installed KIO version through package manager:
  - RPM/Fedora: `kf6-kio-core`;
  - dpkg/Debian/Ubuntu: `libkf6kiocore6`;
  - conservative fallback for unknown version.
- With KIO **6.30.0 or newer**, Dolphin installs `wmm-menu.desktop` and uses **WMM Manager** submenu.
- With KIO older than 6.30.0, or undetectable version, WMM keeps three individual Service Menus to avoid upstream `X-KDE-Submenu` regression.
- When migrating to KIO 6.30+, WMM validates new descriptor and all three wrappers before removing legacy Service Menus.
- Detection validated on:
  - Fedora 44 / KIO 6.30.0 → submenu branch;
  - Kubuntu / KIO 6.24.0 → individual legacy branch.
- `X-KDE-Submenu` regression verified as fixed at runtime with KIO 6.30.0.

### Panel and interface

- Expanded/collapsed section state is saved in `settings.json`.
- Control Panel remembers last effective size through `panel.window_size` in `settings.json`; restores it on open while keeping current workarea as authoritative limit, and also persists it on Restart path, which exits application without going through `delete-event`.
- Improved dynamic Control Panel height adjustment.
- Validated/refined geometry on Cinnamon and MATE.
- Removed fixed FlowBox column limit; maximum is now 128.
- Debug Log Viewer remembers Auto-scroll, Reverse order and last window size; `window_size` is captured once when close is requested and restored on open.
- Replaced the dedicated `help_viewer.py` with the new generic `docs_viewer.py`.
- The WMM **Help** action keeps using the internal `open_help` command, but now opens `help/HELP.md` through the document viewer.
- Localized documents are now resolved automatically from the session language, with fallback to the base document.
- Replaced the **Issues** and **Wiki** links in **About** with **Changelog** and **Help** respectively.
- The **License** link in **About** now opens the local `LICENSE` file through the document viewer instead of GitHub.
- Thumbnails: horizontal first, vertical after; within each orientation, newest materialization first.
- Child Active/Inactive changes update state/visibility immediately while deferring cache/thumbnail reconciliation.
- **Recursive** now represents structural scope only.
- Recursive changes update tree/visibility immediately, with cleanup deferred to Sync/restart.
- Re-enabling Recursive before cleanup reuses existing cache.
- Enabling Recursive after cleanup rebuilds lightweight structure without materializing images automatically.
- **Activate subfolders** / **Deactivate subfolders** affect `active` only.
- **Sources need resynchronization** is computed from real global state.
- **Delete cache** remains available for inactive child folders when cache exists.
- **Generate thumbnails** rebuilds selected folder only.
- `slideshow_enabled` and `slideshow_interval` changes update resident engine timer.
- Interval selector applies 800 ms debounce.
- `slideshow_interval` / `slideshow_max_interval` keep bidirectional relationship.
- Sync Library now uses per-image freshness through `mtime_ns`.
- `scan_index.json` now represents logical structure and Active/Inactive only through booleans.
- Sync Library now performs per-image differential reconciliation.
- Thumbnail invalidation is selective.
- In-place changes keep **Modified** semantics.
- Favorite-derived metadata is refreshed from `image_cache`.
- Improved reconciliation traceability in Debug Log.
- Simplified **Sources → Sync → COMMIT → Thumbnails** lifecycle: one global Panel operation keeps interaction blocked from start until real END.
- Sources lock affects interactive controls only (tree, buttons and checkboxes); progress bar and informational text stay outside functional sensitivity.
- `progress` is now decoupled from lifecycle: `N/N` and `0/0` report progress but no longer control UI release.
- Thumbnail loads inherited from Add Source/Resync continue already-open global operation; independent Reload/Refresh Thumbnails opens and closes its own operation.
- Sync success and error paths now have explicit terminal closures; failures clear `_async_state` and release operation without faking completed progress.

### Runtime and IPC

- `commands.json` and `command_panel.json` now process only `Gio.FileMonitorEvent.CHANGES_DONE_HINT`.
- Intermediate `CHANGED` events return immediately.
- Removed `sleep(0.02)` from both FileMonitor callbacks.
- JSON reading now uses logical change-completion boundary instead of fixed delay.
- New path validated across multiple rotations with no loss, duplication, partial reads or JSON errors.
- Architecture remains reactive and introduces no polling.
- Completed rotation-cost audit on modern and older hardware: CPU/RSS peaks stay bounded, threads remain stable and no cumulative degradation appears; no general rotation worker is introduced in v1.4.0.
- Reviewed real `set_wallpaper()` implementations in Cinnamon, GNOME, KDE and MATE; each remains desktop-specific COMMIT instead of being moved wholesale into a thread.
- Validated KDE SYNC on Plasma 6.6.6/Wayland: transition stays smooth and synchronized, and second `force_rotation` during busy is discarded with no queueing or reentrancy.
- Validated helper-process lifecycle on KDE and GNOME: Panel, Help, About, Debug Log Viewer and Install Manager disappear on close and leave no zombies or accumulated processes.
- Validated Install Manager Replace on GNOME with no staging, helpers or residual processes after new engine settles.
- Validated new MATE Reinstall lifecycle without false MATE Panel crash warning.
- Closed **RUNTIME-10**: recovered historical Sources exclusion contract and simplified lifecycle after worker implementation.
- During Add Source, Resync Sources and Generate Thumbnails, Sources stays non-interactive for whole global operation, whether it lasts seconds or minutes.
- Removed historical dependency between visual progress completion and Sources release; UI returns to user only after global END.
- Removed second terminal `N/N` progress from COMMIT and duplicate visual closure from Thumbnails.
- Sync no-change fast path now continues through `on_complete()` and Thumbnails before reaching global END.
- Added explicit `on_error` to asynchronous Sync so `_async_state`, progress and global operation close correctly on both WORK and COMMIT errors.
- Validated resulting lifecycle with no sensitivity flicker, no intermediate release and no Sources left locked after completion.

### Translations

- Reorganized translation resources under `wmm_platform/shell/po/`.
- Updated dependent paths and tools.
- File opening now uses default application through GIO, with line-aware capabilities only where supported.

## Fixed

- Fixed possibility of signaling an unrelated process when an old engine PID had been recycled.
- Fixed accidental close/reopen of Favorites menu on GNOME.
- Fixed KDE plasmoid lifecycle when removed from panel.
- Fixed Reinstall/Upgrade lifecycle regression where the previous WMM engine could survive the installation swap and prevent the freshly installed engine from starting.
- Fixed KDE Plasma Reinstall/Upgrade removing the installed WMM plasmoid when `kpackagetool6 --upgrade` was invoked using the plasmoid installation directory itself as the package source.
- Fixed KDE Plasma Reinstall/Upgrade leaving WMM stopped after replacement; the engine is now reactivated through D-Bus and the System Tray restores the existing plasmoid instances without restarting Plasma Shell.
- Fixed broken screenshot links in the English and Spanish README files caused by referencing `.png` instead of the actual `.jpg` image.
- Fixed MATE Crossfade transition when `background-fade` was disabled.
- Fixed MATE frontend indentation defect that could stay hidden behind an old resident factory.
- Fixed creation of multiple active MATE applet instances.
- Fixed Control Panel lifecycle that could leave orphaned `Gtk.Application` instance after an error.
- Fixed MATE applet busy visual state when starting manual rotation.
- Fixed incremental integration of new Nemo actions inside **WMM Manager**.
- Fixed Install Manager control state after Uninstall/Reinstall.
- After successful Uninstall, actions for a missing installation are no longer offered.
- After successful Reinstall, actions are recalculated from actually installed version.
- Fixed deferred cleanup of disabled recursive child folders.
- Fixed reactivation of child folder with no cache to avoid useless loads.
- Fixed reconciliation when disabling **Recursive**.
- Fixed visual race between progress bar and **Sources need resynchronization**.
- Fixed reliance on directory `mtime` for change detection.
- Fixed update of individual favorites when source dimensions/orientation change.
- Fixed ghost rotations after disabling Slideshow from Control Panel.
- Fixed `force_rotation` accumulation: requests received while busy are discarded and never run later.
- Fixed KDE direct D-Bus `force_rotation` path through reactive local guard.
- Fixed GNOME to apply same frontend anti-spam without breaking `_keepMenuOpen`.
- Fixed initial/reactive busy state for D-Bus clients through `GetBusy` / `BusyChanged`.
- Fixed `Gio.FileMonitor` handling in `commands.json` and `command_panel.json`: intermediate events are no longer processed and main context is no longer blocked by fixed 20 ms sleeps.
- Fixed Dolphin integration on KIO 6.30+ stacks to restore **WMM Manager** submenu after upstream `X-KDE-Submenu` regression.
- Fixed Install Manager to move focus to VTE terminal when starting an operation, avoiding ambiguity on `sudo` password prompts.
- Fixed MATE Reinstall/Upgrade to unload applet through native MATE Panel registration and restore it after Replace, removing false unexpected-termination warning caused by forceful frontend termination.
- Fixed premature/intermediate Sources release during Sync/Thumbnails cycle: user cannot manipulate Sources until global operation END.
- Fixed opposite risk of leaving Sources permanently insensitive due to incomplete busy-counter balancing between phases.
- Fixed asynchronous Sync error closure: `_async_state` no longer remains resident after UI is released.
- Restored double-click on Sources folders after migration from old `open_in_file_manager()` API to `open_file()`.

## Removed

- Legacy Sync Library reconciliation path based on `_process_next_folder_async()` and `state['index']`.
- `folder_mtime` as freshness authority for `scan_index`.
- Mass thumbnail invalidation for individual image changes.
- `sleep(0.02)` from FileMonitor callbacks in `commands.json` and `command_panel.json`.
- Direct termination of `mate-applet.py` as normal `unload_frontend()` mechanism during Reinstall/Upgrade; MATE frontend is now unloaded through `mate-launcher.py --unload` and restored with `--restore`.
- Local/per-phase busy counters used to control Sources lifecycle; authority now belongs to one global Panel operation.
- `on_progress(N,N)` / `on_progress(0,0)` as UI closure/release mechanism.
- Duplicate visual progress-bar closure after Thumbnails.
* Removed the legacy `help_viewer.py`, superseded by the generic document viewer.

# v1.3.0 - 2026-08-24

**KDE Plasma 6 integration**

WMM 1.3.0 introduces full support for KDE Plasma 6, including independent wallpapers per monitor, native Plasma crossfades, coordinated SYNC transitions, Spanned compositions distributed across Plasma containments, panel/workarea integration on Wayland, plasmoid lifecycle management, global shortcuts, Dolphin integration and D-Bus activation.

KDE wallpaper application now uses the native `org.kde.PlasmaShell.setWallpaper()` API through Gio/GLib. The previous refresh workaround based on `plasma-apply-wallpaperimage`, `evaluateScript()` and `reloadConfig()` is no longer used by the active wallpaper path.

## Added

### Wallpapers, composition and transitions

- Independent wallpapers, SYNC/ASYNC rotation and Spanned composition across supported desktop environments.
- Native KDE Plasma 6 Crossfade transitions through `org.kde.image`.
- Coordinated KDE SYNC transition using `current image → black → new image`.
- Double-buffered KDE masters per containment to guarantee a real URI change and preserve native transitions.
- GNOME and Cinnamon SYNC transitions reordered around a fixed black fade resource to avoid visible races while replacing the master image.
- Opportunistic preview caching and an optimized preview pipeline that reduces images before effects and composition.
- Shared Spanned reference-monitor resolution through `get_spanned_reference_hash()`.
- `active_composition` vault state for temporary composition overrides without duplicating global settings.

### Monitor detection and workarea integration

- Stable KDE monitor/container mapping based on connector, UUID, priority and Plasma containment.
- Runtime-only resolution of Plasma `screenNum`; it is never used as persistent monitor identity.
- GNOME Wayland monitor detection through `org.gnome.Mutter.DisplayConfig`.
- Reactive GNOME monitor updates through `MonitorsChanged`.
- Real window workarea detection for the WMM panel on KDE/KWin, GNOME/Mutter and Cinnamon.

### Panel and thumbnails

- Persistent expanded/collapsed state for Options, Favorites and Image Sources in `settings.json`.
- Persistent complete collapse of the left panel through `panel.collapsed`.
- Compact collapsed sidebar with Expand, Help, Debug Log Viewer and Restart actions.
- Visual separators between the side panel, Monitors and Thumbnails areas.
- New Favorites view in Thumbnails using `Gtk.Stack`, fed directly from `bookmarks_single_list.json`.
- Favorite thumbnails retain normal interactions: double-click opens the image and right-click removes it from favorites immediately.

### Favorites and slideshow UI

- Reactive favorites/settings synchronization in desktop frontends.
- GNOME native slideshow slider with live minute display.
- GNOME Favorites list with a dedicated scroll area and fixed controls.
- Cinnamon Favorites list with independent hover for preset name and trash action.
- Cinnamon Favorites ScrollView now grows naturally up to a maximum height and only then enables vertical scrolling.
- Cinnamon scroll policy compatibility through runtime selection of `St.PolicyType` or `Gtk.PolicyType`.

### Desktop integration

- KDE Plasma 6 plasmoid with D-Bus activation tied to `org.maki.wmm`.
- Global `Exit WMM` action with coordinated frontend, panel and engine shutdown.
- Native application launchers and autostart integration.
- KDE global shortcut through the `next-background` Desktop Action and KGlobalAccel.
- GNOME Shell extension support for versions 45–50.
- GNOME D-Bus bridge through `org.maki.wmm.Gnome`.
- Cinnamon applet lifecycle coordinated with the WMM engine.
- Dolphin and Nemo desktop/file-manager integration retained across their respective environments.

### Installation and compatibility

- GTK, GLib, PyGObject and common runtime requirements are treated as shared dependencies across desktops, including KDE.
- Plasma 6 minimum-version validation during installation.
- GNOME Shell metadata compatibility declared for versions 45–50.
- Runtime capability detection used where GNOME/Cinnamon APIs differ between releases.
- D-Bus services, translations, desktop launchers and desktop-specific integrations are installed and refreshed during setup.

## Changed

### Wallpaper application and composition

- KDE wallpaper application migrated from configuration/reload-based refreshes to live `PlasmaShell.setWallpaper()` calls via Gio/GLib.
- KDE masters changed from one persistent path per containment to two alternating slots.
- KDE SYNC and ASYNC now rely on Plasma's native `org.kde.image` transition mechanism.
- Spanned reference selection is centralized and shared between engine and panel.
- Preview generation now performs early resizing and reuses in-memory results instead of reloading temporary previews from disk.
- Temporary composition state is separated from global configuration and is cleared when returning to normal rotation.

### Panel and UI

- Panel expansion preserves the top position of the window when sections grow beyond the available workarea.
- The right side of the panel automatically absorbs the space freed when the left side is collapsed.
- Options header now integrates Help, Debug Log Viewer, Restart and Collapse without consuming an additional row.
- Horizontal and Vertical remain navigation controls in Thumbnails; Favorites is a separate view and does not alter H/V semantics.
- Cinnamon Favorites rows use natural height instead of distributing unused ScrollView height between items.

### Frontend synchronization and lifecycle

- KDE plasmoid settings/bookmarks synchronization uses `DBus.SignalWatcher` instead of polling.
- Settings/bookmarks file monitoring reacts to completed logical writes rather than every intermediate file event.
- KDE, GNOME and Cinnamon keyboard rotation paths invoke `send_command.py` directly.
- Frontend destruction no longer implicitly shuts down the engine; explicit Exit/Remove actions control global shutdown.
- GNOME extension startup waits for the WMM service before constructing translatable UI.
- GNOME monitor-event handling uses its own D-Bus connection/main-loop context.
- GNOME and Cinnamon shortcut setup detects runtime schema capabilities instead of assuming one desktop version.

## Fixed

### Wallpapers and Spanned

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

### Panel and favorites

- Panel position shifts when expanding sections near the workarea limit.
- KDE contextual menu/settings updates appearing one opening late.
- GNOME Favorites lists disappearing or remaining empty across API differences between Shell versions.
- GNOME Favorites scroll affecting the entire submenu instead of only the preset list.
- GNOME slideshow slider remaining interactive while disabled.
- Cinnamon Favorites ScrollView using only part of the available menu width.
- Cinnamon favorite rows showing excessive vertical separation because each row expanded into unused ScrollView space.

### Integration and startup

- KDE D-Bus channel registration failure on first clean startup.
- D-Bus activation race immediately after installing a new user service.
- KDE global-shortcut registration races caused by dynamic `.desktop` discovery through KSycoca.
- Incorrect or unfriendly KDE shortcut naming.
- GTK dependencies omitted from KDE installation flow.
- GNOME shortcut setup failures caused by schema differences in `binding` and `enable-in-lockscreen`.
- GNOME monitor-event handling falling back incorrectly because no D-Bus main loop was attached.
- GNOME Wayland panel sizing based on inaccurate `Gdk.Monitor.get_workarea()` results.
- GNOME first-run translation failures caused by gettext cache timing.

### Removed

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

# v1.2.4 - 2026-08-04

## Fixed

- Critical bugfix: source files (`applet.js`, `extension.js`, etc.) were packaged with unresolved Git conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`) in the v1.2.3 release. This caused `expected expression, got '<<'` errors when loading the applet/extension on some systems.
- All conflict markers have been removed and the source tree is now clean. The applet and extension load correctly again.
- No functional changes: this release only fixes the packaging issue.

**Note for users**

If you are using v1.2.3, please update to v1.2.4 as soon as possible. The previous version may not load correctly on your system.

# v1.2.3 - 2026-08-02

## Added

- New image selection engine (`image_selection.py`): centralises all selection logic (sync/async modes, spanned, presets, history) and cuts `main.py` load by over 30%, improving maintainability and responsibility isolation.
- New monitor detection engine (`monitor_detection.py`): unifies detection strategies across X11 (libXrandr), GNOME Wayland (D-Bus), and generic GDK fallback. Detection logic is now fully decoupled from the rest of the engine.
- New hardware events engine (`monitor_events.py`): centralises monitor change monitoring (connect/disconnect) using D-Bus on GNOME and GDK signals as fallback, following same modular pattern as other engines.
- Full GNOME Wayland support: monitors detected via D-Bus (org.gnome.Mutter.DisplayConfig) with complete information (connector, model, serial, real size, orientation, physical dimensions, inches, and primary). Orientation correctly obtained (`current_transform` in CRTCs).
- Enhanced `get_monitor_display_name` in `config_handler.py`: now generates rich monitor names (e.g. "Samsung LC49G95T (49")" or "Generic Monitor DP-3 (49")") with clear logic prioritising model, then manufacturer, and finally connector as last resort.
- Monitor switches in control panel now show descriptive names including model, manufacturer, and inches, improving visual identification in multi‑monitor setups.

## Changed

- Deep refactor of `main.py`: duplicate selection methods (`_build_selection`, `_handle_selection_mode`, `_resolve_async_targets`, `_get_smart_favorite`) removed; they now live in `image_selection.py`. Main orchestrator shrinks from ~1200 to ~800 lines, gaining clarity and reducing coupling.
- Refactored `linux.py` and `gnome.py`: monitor detection functions (`get_x11_monitors`, `get_gdk_wayland_monitors`, `get_monitors_from_dbus`) extracted to new `monitor_detection.py`, and event functions (`init_monitor_events`) moved to new `monitor_events.py`. These files now focus exclusively on OS‑ or desktop‑specific implementations.
- `PlatformManager` (`core.py`) now delegates detection and events to the new orchestration engines instead of assigning functions from platform modules. This unifies usage patterns and eases extension to future desktops (KDE, etc.).
- Improved monitor identification on Wayland: position‑based identification removed; now uses `current_crtc` provided by D‑Bus, ensuring exact output‑to‑CRTC pairing.
- Wayland monitor orientation now calculated from actual CRTC size (width, height), no heuristics or assumptions.
- GDK fallback on Wayland retained as backup for environments without D‑Bus (e.g., experimental Cinnamon Wayland), though limited (no model or physical dimensions).
- Experimental Cinnamon Wayland support: not functional. Will be revisited when development matures. Currently not viable.

## Fixed

- Fixed issue where Spanned mode on Wayland incorrectly picked first monitor in list instead of primary, causing distortion. Now correctly selects main monitor.
- Fixed monitor orientation on GNOME Wayland: rotated (vertical) monitors now correctly detected and reflected in `geometry.json` with proper orientation.
- Fixed monitor name generation in control panel switches and tooltips: now displays full model (e.g. "LC49G95T") instead of connector (e.g. "DP-3"), and includes connector for identical monitors when model is missing.
- Removed "first available image" fallback in Spanned mode, which had been causing inappropriate vertical images. Now intelligently selects using `get_smart_selection`.
- Removed redundant logs and noise from log viewer generated during Wayland monitor detection.
- Ensured compatibility with Cinnamon X11 after refactorings: all X11 tests (Cinnamon, GNOME) pass without regressions.
- Fixed translation fallback in GNOME extension: removed `gnome-shell` domain dependency, now uses exclusive WMM translation domain (`wmm@maki`) for consistent and self‑contained i18n across all desktop environments.

## Removed

- Removed `get_primary_monitor` method (GDK‑based) from `linux.py`, obsolete after new D‑Bus detection.
- Removed position‑based monitor detection heuristic from `_get_spanned_master_image`; now uses D‑Bus `current_crtc`.

# v1.2.2 - 2026-06-23

## Added

- Implemented a new event-driven communication layer using Gio.FileMonitor to listen for commands.json and command_panel.json changes, creating a 100% asynchronous and agnostic communication channel between the engine, applet, and panel.
- Added unified shell script wrappers (wmm-add_to_bookmarks.sh, wmm-send-to-monitor.sh) for file manager integration. These scripts dynamically detect the active desktop environment (Cinnamon, GNOME, KDE) and route execution to the correct Python script, resolving path conflicts when using Nemo in GNOME or Nautilus in Cinnamon.

## Changed

- Major Architecture Refactor: Completely removed SIGUSR1 signals and pkill subprocess calls for Inter-Process
- Communication (IPC). The engine and panel now react to file changes via Gio.FileMonitor instead of relying on system signals.
- Future-Proofing: This IPC refactoring is the foundational step to prepare the codebase for KDE Plasma (next milestone) and Windows/macOS (planned). By eliminating POSIX-only dependencies, the core engine is now fully platform-agnostic.
- Restructured file manager integration scripts into a single wmm_platform/shell/file_manager/ directory.
- Renamed nemo_add_bookmark.py and nemo_send_to_monitor.py to shell_add_bookmark.py and shell_send_to_monitor.py to reflect their file-manager-agnostic nature.
- Nemo .nemo_action files now call the unified .sh wrappers instead of using hardcoded absolute paths, ensuring seamless operation across dual-boot desktop environments.
- Cleaned up obsolete imports (signal, subprocess) across backend and UI scripts following the IPC overhaul.
- Updated bundled wmm-next.sh keyboard shortcut scripts to remove pkill commands, matching the new file-monitor-based architecture.

## Fixed

- Resolved 4 warnings reported by Cinnamon Spices and GNOME Extensions reviewers regarding synchronous file I/O operations blocking the main loop in applet.js / extension.js
- Implemented an automatic cleanup routine in ensure_shell_actions to remove legacy nemo and nautilus directories and old router scripts during engine startup, preventing duplicate context menu entries after an update.

# v1.2.1 - 2026-06-18

## Added

- "Next Wallpaper" menu item as the first option in the GNOME context menu, providing a reliable way to force wallpaper rotation without depending on left-click behavior that varies across GNOME versions.
- Keyboard shortcut support via bundled `wmm-next.sh` scripts for both Cinnamon and GNOME, documented in the README with step-by-step instructions in English and Spanish.
- Dark mode wallpaper support for GNOME 46+: `set_wallpaper` now also sets `picture-uri-dark` so wallpapers display correctly in both light and dark modes.

## Changed

- The GNOME extension no longer attempts to intercept left-click for wallpaper rotation. Left-click now behaves as GNOME expects (opens the menu), making the extension fully compatible with GNOME 46 and avoiding fragile reliance on internal Shell APIs.
- `gettext` moved from system dependencies to installable dependencies in `install.sh`, as it is not always preinstalled on minimal GNOME setups.

### Fixed

- Wallpaper not applying in dark mode on GNOME 46 due to the new `picture-uri-dark` key being ignored. The fix is version-safe and silently skips the key if it does not exist.
- Removed left-click interception and anti-spam code from the GNOME extension. The underlying Shell APIs (such as `_clickGesture`) proved highly incompatible across versions, making the behavior fragile and impossible to maintain reliably.
- Improved object cleanup in `disable()` with a dedicated `_destroyUI()` method, addressing multiple review warnings from `shexli`.

# v1.2.0 - 2026-06-18

## Added

- Full GNOME Shell compatibility: new extension.js with panel indicator, context menu, slideshow controls, favorites management, and one-click wallpaper rotation with anti-spam protection.
- Desktop-specific metadata and JavaScript files are now stored under wmm_platform/shell/cinnamon/ and wmm_platform/shell/gnome/, keeping the project root clean.
- install.sh now detects the desktop environment and automatically copies the correct metadata.json and JS file (applet.js or extension.js) to the installation path.
- GNOME Shell Extension Manager (gnome-shell-extension-prefs) is now offered as an installable dependency when running under GNOME.
- Nautilus scripts integration: "Send to Monitor" and "Add to Favorites" actions are now available in the GNOME file manager.

## Changed

- All translatable strings are now centralized within WMM's own translation domain, completely independent of desktop environment system translations. This ensures full compatibility across Cinnamon, GNOME, and future platforms.
- The interval selector in GNOME now uses plus/minus buttons instead of a slider, matching the Control Panel design and avoiding compatibility issues with GNOME 50.1.
- Switches in the GNOME menu now use a custom implementation to prevent the menu from closing unexpectedly on activation.
- metadata.json is no longer hardcoded; two templates are provided and the installer picks the right one at install time.

## Fixed

- Cache path inconsistencies that could spawn two engine instances have been resolved; settings_core.ini is now completed before ConfigHandler is created.
- Progress bar visibility restored during source scanning and thumbnail generation, which had been broken after the panel refactoring.
- Deleting an image source now correctly cleans its entries from image_cache.json and removes the associated thumbnails, including previously deactivated subfolders.
- Auxiliary scripts (nemo_add_bookmark.py, nemo_send_to_monitor.py, add_bookmark.py) now use the correct cache path instead of a local fallback.
- Source tree now shows expansion arrows immediately after adding a new source, without requiring a manual refresh.
- Stale debug messages have been removed from the log viewer.

# v1.1.0 - 2026-06-16

## Added

- Thumbnail generation now runs automatically after adding a new image source; the gallery refreshes without any extra click.
- Thumbnail gallery also refreshes immediately when an image source is removed or a folder is activated/deactivated from the context menu.
- Source tree now preserves its expanded branches after actions such as activating or deactivating subfolders, so the view stays as you left it.
- Strategic log_event calls have been added to trace key actions—thumbnail generation start/end, progress bar state, and a summary of active, inactive and deleted folders during sync—without spamming the log viewer.
- A dedicated internal command (single_favorite_added) distinguishes single images added to favorites from full presets, keeping logs and notifications more precise.

## Changed

- Source tree now automatically shows expansion arrows for parent nodes right after a new source is added, eliminating the need for a manual refresh.
- Translation support: All translatable strings are now centralized within WMM's own translation domain, completely independent of Cinnamon's system translations. This ensures full compatibility with other desktop environments and operating systems, while preserving English, Spanish and Catalan support.

## Fixed

- Control panel no longer creates its cache inside the applet folder; settings_core.ini is now completed with all derived keys in every installation scenario, so the cache reliably lives under ~/.cache/wmm.
- Progress bar is again visible during source scanning and thumbnail generation, restoring feedback that had disappeared after the panel refactoring.
- Deleting an image source now correctly cleans its entries from image_cache.json and removes the associated thumbnails, including previously deactivated subfolders.
- Auxiliary scripts (nemo_add_bookmark.py, nemo_send_to_monitor.py, add_bookmark.py) now use the correct cache path instead of a local fallback, so their logs and notifications stay in sync with the engine.
- Leftover debug messages that cluttered the log viewer have been removed.

# v1.0.0 - 2026-06-10 (Initial release)

**WMM is a Cinnamon applet that gives you full control over your wallpapers across multiple monitors.**

- Built-in log viewer: real‑time event logging with filters and search, no terminal required.
- Refactored Control Panel split into independent modules for better performance and maintainability.
- Stability improvements: hardware change detection, startup checks and file locking to prevent crashes and data corruption.
- Usability enhancements: contextual buttons in the image sources tree, visual feedback on the applet icon, and a multilingual help system.
- Translation support for English, Spanish and Catalan, with the ability to inherit Cinnamon system translations.
