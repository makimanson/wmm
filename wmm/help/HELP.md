<!--
SPDX-FileCopyrightText: 2026 makimanson
SPDX-License-Identifier: GPL-3.0-or-later

WMM - Wallpaper Multi-Monitor Manager

HELP.md -- Help file in English

WMM-Title: Help
WMM-Contents: Contents
-->

# Desktop environments

WMM currently provides full integration with **Cinnamon**, **GNOME Shell**, **KDE Plasma 6** and **MATE**.

Control Panel and main features are shared across all environments. Some controls may look slightly different or appear in a different place depending on desktop, but they use the same configuration.

# Settings

Open WMM menu from its applet, extension or plasmoid and select **Settings** to open Control Panel.

## Options

This section contains general WMM options. You can change startup behavior, aspect mode, image effects, background and slideshow settings. Changes are reflected on virtual monitors in **Monitors** section.

### Help icon

Opens this help in a separate window.

### Log Viewer icon

Opens debug log viewer in a separate window. It shows WMM activity in real time and lets you filter the log.

### Restart icon

Fully restarts engine and Control Panel. Useful when you need to reload WMM during a session.

### Collapse / Expand icon

Collapses side column to leave more room for monitor and thumbnail sections. Press it again to restore full view.

WMM remembers whether side column was collapsed or expanded.

### Collapse / expand sections

Different Control Panel sections can be **collapsed or expanded** by clicking their header.

* **Expanded**: shows all controls and options in that section.
* **Collapsed**: hides its contents and leaves only header visible.

This helps reduce space used by sections you are not working with and keeps focus on options you need at that moment.

Collapsing only affects Control Panel display: **it does not enable, disable or change any WMM option**.

### Change wallpaper at startup

When **enabled**, engine picks new images at WMM startup and generates a new composition.

When **disabled**, last saved composition is kept.

### Panoramic Mode

Enables or disables **Panoramic Mode** (*Spanned*). When enabled, one panoramic image is stretched across all monitors at once.

Only available when more than one monitor is active.

### Aspect ratio

Controls how image fits inside each monitor:

- **Scaled**: image is reduced or enlarged without distortion. If it does not fill whole monitor, remaining space uses selected background color or effect.
- **Zoom**: image is scaled to cover whole monitor. If image and monitor use different proportions, excess areas are cropped.
- **Stretched**: image is fitted exactly to monitor size, even if this may distort it.

### Image effect

Applies a visual effect to image on each monitor:

- **None**: no effect.
- **Sepia**: applies an aged tone to image.
- **Black and White**: converts image to grayscale.

### Background effect

Fills remaining space when image does not fully cover monitor. Mainly visible in **Scaled** mode.

- **Blur**: uses a blurred copy of image itself as background.
- **Color**: uses solid or gradient color selected under **Background color**.

### Background color

Defines background used when an image does not fill whole screen or when a monitor has no image assigned.

- **Solid color**: one flat color.
- **Gradient H**: two-color gradient from left to right.
- **Gradient V**: two-color gradient from top to bottom.

### Slideshow

Enables or disables automatic image rotation. When enabled, engine changes wallpapers according to configured interval and mode.

### Maximum frequency

Sets maximum rotation interval, in minutes, available from WMM menu.

### Slides every...

Defines how many minutes pass between automatic wallpaper changes.

### Slideshow mode

Controls how images change and which transition effect is used during slideshow:

- **Sync**:
    - Applies a fade to black effect (Fade-out > Fade-in).
    - All monitors change at once.
    - If **Favorites only** is enabled: rotation uses saved presets.

- **Async**:
    - Applies an image-to-image blend effect (Crossfade).
    - Monitors change independently, one after another.
    - If **Favorites only** is enabled: rotation uses individual images from favorites list.

## Favorites

Manage your favorite wallpaper combinations. You can create, load, modify and delete presets. A *preset* is a saved composition you can restore at any time.

### "Favorites only" switch

When enabled, slideshow uses only your favorites.

- In **sync** mode, saved presets are used.
- In **async** mode, individual images from favorites list are used.

### Presets box (left)

- **Load a preset on monitors**: right-click preset name and select *"Load on monitors"*. Preset opens in edit mode so you can review and modify it before applying.
- **Rename a preset**: make a slow click on preset name. When text becomes editable, type new name and press Enter.
- **Delete a preset**: right-click preset and select *"Delete preset"*. You can also select it and press trash button.
- **Remove an image from a preset**: right-click image inside preset and select *"Remove image"*. Monitor keeps its position in preset but is left without an image.
- **Open a preset image**: double-click image to open it with system default image viewer.

### Favorites box (right)

- **Add an image to favorites**: from thumbnail gallery, right-click an image and select *"Add to favorites"*. You can also do this from file managers supported by WMM.
- **Select multiple images**: use **Ctrl+click** for non-contiguous selection or **Shift+click** to select a range.
- **Remove an image from favorites**: right-click image and select *"Remove from favorites"*.
- **Open an image**: double-click to open it with system default image viewer.

### Delete buttons

Both Presets and Favorites boxes have a trash button at bottom right.

Button deletes currently selected item. If several images are selected in favorites list, all of them are removed from list.

## Image sources

From here you can add, remove and manage folders WMM uses as image library.

If a source is recursive, its subfolders are also shown and you can choose which ones remain active.

In this section **WMM never deletes original folders or images from disk**. Cleanup operations only affect internal library and cached thumbnails.

### "Add source" button

Opens a dialog to select a folder from system.

- **Include subfolders (Recursive)**: enable it if you want WMM to include subfolders from that source.
- If disabled, only images stored directly in root folder are used.
- Pressing **Add** registers new source, syncs its contents and updates gallery.
- When operation finishes, available images appear in **Thumbnails** section.

### "Remove source" button

Removes selected source from WMM library.

A confirmation dialog is shown first. If accepted:

- Source disappears from list.
- Its images are no longer available to WMM.
- Data associated with that source is removed from library and cache.

Original files remain untouched on disk.

### "Resync" button

Checks configured sources and brings library up to date with actual folder contents.

Use it when:

- you have added, deleted, moved or renamed images outside WMM;
- you have modified images with another application;
- folder structure has changed;
- **"Sources need resynchronization"** warning appears;
- you want to globally reconcile state of all sources.

During synchronization, WMM detects new, modified or deleted images and updates library and required thumbnails.

### "Sources need resynchronization" warning

This warning means current source configuration and content WMM has ready to display do not fully match yet.

It is not an error. It may appear, for example, after enabling or disabling folders, changing **Recursive** option or re-enabling a folder whose cache had already been deleted.

Press **Resync** to update library globally.

If you only want to recover an active subfolder with no cache, use **Generate thumbnails** from its context menu.

### Folder tree navigation

#### Double-click a folder

Opens folder with system default file manager.

#### Right-click a folder

Context menu offers actions available for that folder type and state:

- **Enable / Disable folder**: changes whether its images are part of active library. Visibility changes immediately and does not start a full synchronization by itself.
- **Enable subfolders / Disable subfolders**: on a recursive source, changes state of all its subfolders at once.
- **Generate thumbnails**: available for an active subfolder that does not yet have cached content ready. Processes only that subfolder.
- **Delete cache**: appears for inactive folders. Removes cache associated with that folder from WMM but does not touch original images.

If a folder is re-enabled while its cache still exists, WMM can reuse it immediately.

If it is re-enabled after cache has been deleted, folder remains active but its images do not appear until you use **Resync** or **Generate thumbnails**.

### Enable / Disable recursion

**Recursive** column appears on root sources.

- **Enabled**: subfolders are part of source.
- **Disabled**: WMM uses only root folder.

Change is reflected immediately in tree and image visibility.

Enabling **Recursive** lets WMM discover subfolders, but it does not force images or thumbnails no longer present in cache to be rebuilt automatically. In that case use **Resync** for whole library or **Generate thumbnails** for a specific subfolder.

## Monitors

Your monitors are shown here as thumbnails. Section updates when wallpapers, geometry or screen state change.

### Alignment buttons

Header contains three buttons: `[` , `•` and `]`. They change horizontal alignment of monitor block inside window:

- **`[`**: align left.
- **`•`**: center.
- **`]`**: align right.

Useful when monitors have very different geometries and you want to adjust preview visually.

### Normal mode

In normal mode, section shows a thumbnail for each monitor with its assigned image and a switch to enable or disable it.

#### Monitor switches

- **Enabled**: monitor shows assigned image. If none is assigned, WMM can pick one based on orientation.
- **Disabled**: monitor is filled with selected background and does not participate in slideshow rotation.

When **Panoramic Mode** is enabled, switches are locked because one image is used for whole composition.

#### Action buttons

- **"Favorite" checkbox**: when checked, pressing **Accept** saves current composition as a preset.
- **Accept**: applies changes to displays. If **Favorite** checkbox is checked, preset is also saved.
- **Refresh**: refreshes monitor view from engine.

### Edit mode

Press **Edit mode** button with pencil icon to assign images manually to monitors.

#### Drag & Drop

You can drag any image from thumbnail gallery and drop it onto virtual monitor where you want to assign it.

#### Edit options panel

When edit mode is active, composition-specific options appear:

- **Spanned**: enables or disables Panoramic Mode for this composition.
- **Aspect ratio**: chooses image fitting mode.
- **Effects**: applies an image effect to composition.

Changes can be previewed while editing.

These values are stored with preset and take priority over global settings when that preset is used.

#### Action buttons in edit mode

- **"Favorite" checkbox**: lets you save edited composition as a preset.
- **Accept**: applies changes and leaves edit mode. If checkbox is checked, preset is also saved.
- **Refresh**: clears images assigned to monitors so you can rebuild composition from scratch.

## Thumbnails

This section shows images available in WMM library. Thumbnails are cached so browsing stays fast.

### Refresh button

Reloads thumbnail view and rebuilds any thumbnails required from library already synchronized by WMM.

This button **does not replace Resync**. If you added, deleted, moved or modified original files outside WMM, use **Resync** first to update library.

### H / V buttons

**Horizontal** and **Vertical** buttons let you jump quickly to first item of each orientation in gallery.

### Favorites button

Shows a dedicated view with images saved as favorites, including images that are part of your **Presets**.

### Layout and order

Thumbnails are displayed in a grid that adapts to available width.

Order is:

- **Horizontal** images first, with most recently added to library shown first.
- **Vertical** images afterwards, also with most recently added first.

### Working with thumbnails

You can interact with any thumbnail in several ways:

- **Double-click**: opens original image with system default viewer.
- **Right-click**:
  - *"Add to favorites"*: adds image to favorites list.
  - *"Remove from favorites"*: removes it from list when already marked as favorite.
- **Drag & Drop**: in edit mode, drag a thumbnail onto a virtual monitor to assign that image.

### Favorite frame

Images included in favorites list are highlighted with a green frame.

# Favorites

WMM **Favorites** menu gives quick access to saved presets and lets you create new ones from current composition.

### "Favorites only" switch

When enabled, slideshow uses only content saved as favorite:

- **Sync mode**: selects a preset and applies full composition.
- **Async mode**: uses individual images from favorites list.

If you enable **Favorites only** while slideshow is off, WMM enables it automatically so rotation can work.

### Add a preset

Press **"Add Preset Favorite"** to save current composition.

A dialog opens where you can enter preset name. WMM suggests an automatic name, for example *"Bookmark 01"*, which you can replace with any name you want.

- **Blank name**: WMM warns you and does not save preset.
- **Duplicate name**: choose a different name.
- **Saving preset**: current monitor configuration is stored, including images and options associated with composition.

### Preset list

Saved presets appear below controls.

- **Load a preset**: click its name to apply it. WMM stops timer if active and loads saved composition.
- **Delete a preset**: click trash icon and confirm deletion.

# Slideshow

This menu lets you control automatic wallpaper changes without opening Control Panel.

### "Enabled / Disabled" switch

Main switch turns rotation timer on or off.

- **Enabled**: countdown to next change starts.
- **Disabled**: current composition stays in place until slideshow is enabled again or you force a manual rotation.

State stays synchronized with Control Panel.

### Interval

Sets how many minutes pass between changes.

Depending on desktop environment, control may appear as slider or adjustment buttons. Minimum is 1 minute and maximum comes from **Maximum frequency** in Control Panel.

Interval changes are applied to WMM timer.

# Monitors (Rotation Mode)

Controls how wallpaper changes are distributed across displays.

- **ASYNC (One)**: monitors change one at a time. Each cycle gives only one monitor a new image.
- **SYNC (All)**: all monitors change at once.

Mode change is immediate and does not require restarting slideshow.

# Panoramic Mode (Spanned)

Enables or disables panoramic wallpaper.

When active, WMM uses one image to build a composition covering all monitors while respecting their position and geometry.

This option only has an effect when more than one monitor is active.

While **Spanned** is enabled, individual monitor switches are locked because composition is shared across all displays.

# Tools

**Tools** menu groups common WMM operational shortcuts:

- **Settings**: opens Control Panel.
- **Sync Library**: checks all sources and updates library.
- **Install Manager**: lets you update, reinstall or uninstall WMM.
- **Debug Log Viewer**: opens activity and diagnostic viewer.
- **Help**: opens this manual.

## Sync Library

Checks all configured sources and updates WMM library so it matches current disk contents.

Synchronization detects new, modified and deleted images, updates required references and rebuilds thumbnails when needed.

Especially useful after making changes to folders outside WMM or when **"Sources need resynchronization"** warning appears.

Synchronization does not modify or delete original images.

## Install Manager

**Install Manager** lets you perform WMM maintenance tasks from a graphical interface.

Window shows installed version and detected desktop environment.

### Upgrade

If a newer version is available, lets you download it, validate it and start upgrade.

### Reinstall

Reinstalls current version to repair or recover a damaged installation while keeping relevant user data.

### Uninstall

Starts WMM uninstaller and removes application and desktop integrations.

Before operations that require it, integrated terminal may ask for administrator password. Type password directly in that terminal.

During maintenance operation, other controls stay disabled until process finishes.

## Debug Log Viewer

Log viewer shows WMM activity in real time and is useful for checking what engine, panel or desktop integrations are doing.

### Filters

You can filter entries by **Origin**, **Level** and **Reason**, plus free-text search.

### Auto-scroll

Keeps view following new log entries automatically.

### Reverse order

Lets you show newest entries first or keep normal chronological order.

### Clear log

Clear button empties log after asking for confirmation.

Viewer remembers **Auto-scroll**, **Reverse order** and window size.

## Help

Opens WMM help window.

Navigation index appears on left and formatted Markdown content on right so you can jump directly to section you need.

# About WMM Manager

Shows basic WMM information, including installed version, application name and license.
On some desktop environments it also provides useful links.

# File managers

WMM integrates with **Nemo**, **Nautilus**, **Dolphin** and **Caja** when those file managers are available on system.

Right-clicking an image can show WMM actions for:

- **Add to favorites**.
- **Send to a monitor**.
- **Distribute image across all displays**.

Depending on file manager, these actions may be grouped under **WMM Manager** or shown individually.

On MATE, Caja integration may also provide an action to distribute current image from desktop context menu.

# Keyboard shortcuts

WMM registers **Next Background** action with shortcut systems provided by **Cinnamon**, **GNOME Shell**, **KDE Plasma 6** and **MATE**.

You choose key combination from shortcut settings provided by your desktop.

## On Cinnamon

1. Open **System Settings → Keyboard → Keyboard shortcuts**.
2. Open **Custom shortcuts**.
3. Find **"WMM - Next Background"**.
4. Assign any combination you prefer, for example `Ctrl+Alt+N`.

## On GNOME Shell

1. Open **Keyboard** settings and custom shortcuts.
2. Find WMM action for **Next Background**.
3. Assign key combination you prefer.

## On KDE Plasma 6

1. Open **System Settings → Shortcuts**.
2. Find **WMM Manager** and **Next Background**.
3. Assign key combination you want to use.

## On MATE

1. Open MATE **Keyboard Shortcuts** settings.
2. Find **"WMM - Next Background"**.
3. Assign key combination you prefer.

Shortcut requests a manual rotation using current WMM mode and configuration.
