<!--
SPDX-FileCopyrightText: 2026 makimanson
SPDX-License-Identifier: GPL-3.0-or-later

WMM - Wallpaper Multi-Monitor Manager

HELP_en.md -- English help file

WMM-Title: Help
WMM-Contents: Contents
-->

# Desktop environments

WMM currently provides full integration with **Cinnamon**, **GNOME Shell**, **KDE Plasma 6**, **MATE**, **XFCE**, and **Windows 11**.

The control panel and main features are shared across all environments. Some controls may differ slightly in appearance or location depending on the desktop, but they share the same configuration.

# Settings

Open the WMM menu from its panel or system tray icon and select **Settings** to open the control panel.

## Options

This section brings together WMM's general settings in four groups: **Change wallpaper on startup**, **Spanned Mode**, **Slideshow**, and **Image Metadata**.

Each group can be collapsed or expanded by clicking its heading. The switch on the right enables or disables the corresponding function, regardless of whether its controls are visible. WMM remembers which sections are expanded.

### Help icon

Opens this help in a separate window.

### Debug Log Viewer icon

Opens the debug log viewer in a separate window. It displays WMM activity and allows you to filter the log.

### Restart icon

Restarts the engine and control panel to reload WMM during the current session.

### Collapse / Expand icon

Collapses the panel's sidebar to leave more room for **Monitors** and **Thumbnails**. Click again to restore the full view. WMM remembers the panel's state.

### Change wallpaper on startup

The switch in the heading determines what happens when WMM starts:

- **Enabled**: the engine selects new images and generates a new composition.
- **Disabled**: the last saved composition is retained.

The three controls beneath this heading operate independently of that switch and can also be used when it is disabled.

#### Selection by monitor orientation

- **Enabled**: WMM selects images matching the monitor's horizontal or vertical orientation.
- **Disabled**: images of any orientation may be used.

This filter affects image selection but does not trigger a wallpaper change on its own.

#### Selective rotation

Limits automatic wallpaper rotation to folders you have explicitly marked under **Image Sources**.

To set up the selection, right-click an active folder and choose **Add to selective rotation**. **Remove from selective rotation** removes its mark. Marking folders does not enable the mode by itself.

- **Enabled**: rotation uses active folders that are marked for selection.
- **Disabled**: the selective filter is no longer applied, but the folder marks are retained for later use.

The switch is available only when at least one folder is both active and marked. If no folder meets both conditions, WMM disables selective rotation.

Enabling it also enables **Slideshow** if it was off and disables **Favorites only**, because the two selection modes are mutually exclusive. Disabling selective rotation does not automatically restore the previous mode.

#### Rotation

Determines how wallpaper changes are distributed across monitors. The label shows the mode and the type of selection in use:

- **Synchronous (Sync)**: all monitors change at the same time. With **Favorites only**, complete presets are used.
- **Asynchronous (Async)**: monitors change independently, taking turns. With **Favorites only**, individual images from the favorites list are used.

For transitions, synchronous mode uses a fade to black and asynchronous mode blends between images, depending on what the desktop environment supports.

### Spanned Mode

The switch enables or disables **Spanned**, which stretches one image across the entire monitor arrangement. It only takes effect when more than one monitor is active.

This heading also groups the general composition settings, which remain available even when **Spanned** is disabled.

#### Aspect ratio

Controls how an image fits the available area:

- **Scaled**: preserves proportions. Any remaining space is filled with the selected background.
- **Zoom**: fills the entire area without distorting the image, cropping any excess.
- **Stretched**: fits the exact dimensions, even if the image becomes distorted.

#### Image effect

- **None**: applies no effect.
- **Sepia**: gives the image an aged tone.
- **Black and White**: converts the image to grayscale.

#### Background effect

Determines how to fill the space left uncovered by the image, mainly when using **Scaled**:

- **Blur**: displays a blurred copy of the image.
- **Color**: uses the solid color or gradient configured under **Background color**.

#### Background color

Used when an image does not fill the screen or when no image is assigned to a monitor:

- **Solid color**: lets you choose one color.
- **Horizontal gradient**: blends two colors from left to right.
- **Vertical gradient**: blends two colors from top to bottom.

### Slideshow

Its switch enables or disables the automatic wallpaper rotation timer. Both values in this subsection can be adjusted without starting it.

#### Maximum frequency

Sets, in minutes, the highest value that can be selected for the rotation interval from the WMM menu.

#### Change slides every...

Sets how many minutes pass between automatic wallpaper changes. Its value is coordinated with the configured maximum so the interval cannot exceed it.

### Image Metadata

Allows image information to be displayed over the wallpaper generated by WMM. The switch in the heading enables or disables this information without modifying the original files.

#### Visible fields

Click **Select** to choose which data to display. The dialog groups fields into categories such as image, author, source, dates, and geolocation. Only information available for each image can be displayed.

- **Apply**: confirms the selection and updates the result without closing the dialog.
- **Save**: confirms the selection and closes the dialog.
- **Cancel**: closes the dialog without saving changes pending since the last application.

#### Font and size

Lets you choose the typeface and size used to display metadata.

#### Position

Places the information block in one of the four corners: top left, bottom left, top right, or bottom right.

#### Horizontal margin

Adjusts the horizontal distance between the block and the selected edge, from **0 to 100 pixels**.

#### Vertical margin

Adjusts the vertical distance between the block and the selected edge, from **0 to 100 pixels**.

#### Background opacity

Controls the opacity of the background behind the metadata, from **0% (transparent)** to **100% (opaque)**.

Changes to appearance, position, margins, and opacity become visible when the wallpaper is recomposed.

## Favorites

Manage your favorite wallpaper combinations. You can create, load, edit, and delete presets. A *preset* is a saved composition that you can restore at any time.

### "Favorites only" switch

When enabled, the slideshow uses only your favorites.

- In **synchronous** mode, saved presets are used.
- In **asynchronous** mode, individual images from the favorites list are used.

### Presets box (left)

- **Load a preset onto the monitors**: right-click the preset name and select *"Load onto monitors"*. The preset opens in edit mode so you can review and modify it before applying it.
- **Rename a preset**: slowly click the preset name. When the text becomes editable, enter the new name and press Enter.
- **Delete a preset**: right-click the preset and select *"Delete preset"*. You can also select it and click the trash button.
- **Remove an image from a preset**: right-click the image within the preset and select *"Remove image"*. The monitor keeps its position in the preset but will have no image assigned.
- **Open an image from a preset**: double-click the image to open it with the system's default image viewer.

### Favorites box (right)

- **Add an image to favorites**: right-click an image in the thumbnail gallery and select *"Add to favorites"*. You can also do this from file managers compatible with WMM.
- **Select multiple images**: use **Ctrl+click** for noncontiguous selections or **Shift+click** to select a range.
- **Remove an image from favorites**: right-click the image and select *"Remove from favorites"*.
- **Open an image**: double-click it to open it with the system's default image viewer.

### Delete buttons

Both the Presets and Favorites boxes have a trash button in the lower-right corner.

The button removes the currently selected item. If several images are selected in the favorites list, all of them are removed from that list.

## Image Sources

Here you can add, remove, and manage the folders WMM uses as its image library.

If a source is recursive, its subfolders are also displayed and you can choose which ones remain active.

In this section, **WMM never deletes the original folders or images from disk**. Cleanup operations affect only the internal library and cached thumbnails.

### "Add a source" button

Opens a dialog for choosing a folder on the system.

- **Include subfolders (Recursive)**: enable this if you want WMM to include the source's subfolders.
- If you leave it disabled, only images located directly in the root folder are used.
- When you click **Add**, WMM registers the new source, synchronizes its content, and updates the gallery.
- When the operation finishes, the available images appear under **Thumbnails**.

### Online folder

The **Online** entry in the source tree lets you link a system directory to images downloaded through the Online feature.

To set its location, select **Online** in the tree and click **Add a source**. A folder picker opens so you can choose the directory to use.

If a directory is already linked, you can use the same procedure to change its location.

This operation sets or changes the folder used by Online without deleting the original files from the previous location.

### "Remove a source" button

Removes the selected source from the WMM library.

A confirmation dialog appears first. If you confirm:

- The source disappears from the list.
- Its images are no longer available to WMM.
- Data associated with that source is removed from the library and cache.

The original files remain untouched on disk.

### "Resynchronize" button

Checks the configured sources and brings the library up to date with the actual contents of the folders.

Use it when:

- you have added, deleted, moved, or renamed images outside WMM;
- you have edited images with another program;
- you have changed the folder structure;
- the **"Sources need resynchronization"** notice appears;
- you want to reconcile the state of all sources globally.

During synchronization, WMM detects new, modified, or removed images and updates the library and any necessary thumbnails.

### "Sources need resynchronization" notice

This notice indicates that the current source configuration and the content WMM has prepared for display do not yet fully match.

It is not an error. It may appear, for example, after enabling or disabling folders, changing **Recursive**, or reactivating a folder whose cache was previously deleted.

Click **Resynchronize** to update the entire library.

If you only want to restore an active subfolder with no cache, you can use **Generate thumbnails** from its context menu.

### Navigating the folder tree

#### Selecting a folder

When you select a folder in the tree, the **Thumbnails** section displays only the images belonging to that folder.

To display the entire library again, select **ALL**.

#### Double-clicking a folder

Opens the folder in the system's default file manager.

#### Right-clicking a folder

The context menu provides actions depending on the folder's type and state:

- **Enable / Disable folder**: determines whether its images belong to the active library. The visibility change takes effect immediately and does not start a full synchronization on its own.
- **Enable subfolders / Disable subfolders**: for a recursive source, changes the state of all its subfolders at once.
- **Generate thumbnails**: available for an active subfolder whose content has not yet been prepared in the cache. Processes only that subfolder.
- **Delete cache**: appears for inactive folders. Removes that folder's cache from WMM without touching the original images.
- **Add to selective rotation / Remove from selective rotation**: available only for active folders. Includes or excludes the folder and all its subfolders from selective rotation. This action does not enable or disable the mode, which is controlled under **Options**. Inactive folders do not participate in rotation even if they retain their mark.

If a folder is reactivated while its cache still exists, WMM can reuse it immediately.

If it is reactivated after its cache was removed, it will be active but its images will not appear until you use **Resynchronize** or **Generate thumbnails**.

### Enable / Disable recursion

The **Recursive** column appears for root sources.

- **Enabled**: subfolders are included in the source.
- **Disabled**: WMM uses only the root folder.

The change is immediately reflected in the tree and image visibility.

Enabling **Recursive** lets WMM discover subfolders, but it does not necessarily rebuild images or thumbnails that are no longer cached. In that case, use **Resynchronize** for the entire library or **Generate thumbnails** for a specific subfolder.

## Monitors

Your monitors appear here as thumbnails. The section updates when wallpapers, screen geometry, or monitor status change.

### Alignment buttons

The header contains three buttons: `[` , `•`, and `]`. They change the horizontal alignment of the monitor group inside the window:

- **`[`**: left alignment.
- **`•`**: centered alignment.
- **`]`**: right alignment.

This is useful when monitors have very different geometries and you want to adjust the preview layout.

### Normal mode

In normal mode, the section shows a thumbnail of each monitor with its assigned image and a switch to enable or disable it.

#### Monitor switches

- **Enabled**: the monitor shows its assigned image. If none is assigned, WMM may select one based on the monitor's orientation.
- **Disabled**: the monitor is filled with the selected background color and does not participate in slideshow rotation.

When **Spanned Mode** is enabled, the switches are locked because a single image is used for the entire composition.

#### Action buttons

- **"Favorite" checkbox**: if checked, clicking **Accept** also saves the current composition as a preset.
- **Accept**: applies changes to the screens. If **Favorite** is checked, also saves the preset.
- **Refresh**: refreshes the monitor view from the engine.

### Edit mode

Click the pencil-shaped **Edit mode** button to assign images to monitors manually.

#### Drag & Drop

You can drag any image from the thumbnail gallery and drop it onto the virtual monitor where you want to assign it.

#### Edit options panel

When edit mode is active, composition-specific options appear:

- **Span (Spanned)**: enables or disables Spanned Mode for this composition.
- **Aspect ratio**: selects how images are fitted.
- **Effects**: applies an image effect to the composition.

You can preview changes while editing.

These values are saved with the preset and take precedence over the global configuration whenever that preset is used.

#### Action buttons in edit mode

- **"Favorite" checkbox**: allows the edited composition to be saved as a preset.
- **Accept**: applies changes and exits edit mode. If the checkbox is selected, also saves the preset.
- **Refresh**: clears the images assigned to the monitors so you can rebuild the composition from scratch.

## Thumbnails

This section displays the images available in the WMM library. Thumbnails are cached for fast navigation.

### Refresh button

Reloads the thumbnail view and rebuilds any thumbnails needed from the library WMM has already synchronized.

This button **does not replace Resynchronize**. If you have added, deleted, moved, or modified original files outside WMM, use **Resynchronize** to update the library first.

### H / V buttons

The **Horizontal** and **Vertical** buttons let you jump directly to the first item of each orientation in the gallery.

### Favorites button

Displays a dedicated view of images saved as favorites, including images belonging to your **Presets**.

### Online button

Opens the Internet wallpaper search tool. It lets you browse images from external services, download them, and add them to the WMM library.

Online has a gallery separate from local thumbnails. Searches do not modify the library or original images.

#### Responsible use

When you access Online, the **Responsible Use of Third-Party Services and Resources** document is presented. It explains the principles governing integrations, provider conditions, and responsibilities relating to their content.

To proceed, check **I have read and understood this document** and click **Accept**.

The **Do not show again** checkbox allows you to skip this screen on later visits once you have read and understood the document.

You can consult it again under **About WMM > Licenses**.

#### Search and filters

The search tool lets you combine three criteria:

- **Search**: enter words or terms related to the images you want to find, **in English**. You can also search without entering any text.
- **Aspect ratio**: select any ratio, a horizontal or vertical orientation, or a specific ratio such as 16:9, 21:9, 32:9, or 9:16.
- **Provider**: select **Any** to query all available providers or choose one individually.

WMM currently integrates **Wallhaven** and **Alpha Coders**.

Click **Search** or press Enter to start the query.

The search button becomes available again when you change any of the criteria. Filters are applied according to each provider's capabilities.

#### Results and navigation

Found images appear progressively as thumbnails, showing their resolution and source.

When multiple providers are queried, results are grouped by service. You can click a provider's name or logo to visit its website.

Each thumbnail includes a link to its original page, which opens in the default browser.

The **Load more** button retrieves the next page of results without discarding earlier pages.

If you change the search criteria, you must click **Search** again before loading additional results.

#### Online downloads folder

Downloaded images are saved in the **Online** folder, whose location is configured under **Image Sources**.

To set or change it, select the **Online** entry in the source tree and use **Add a source**.

If no valid Online folder is configured, WMM informs you and does not start the download.

Unlinking this folder from WMM does not delete its original files from disk.

#### Selection and download

Thumbnails whose original images can be downloaded display a selection button.

You can select up to **5 images per batch**. The **Download** button shows how many images you have selected and lets you start downloading them.

During the operation, progress is shown for each file. WMM respects provider limits and adds a preventive pause between consecutive downloads.

Successfully downloaded images are marked as **Downloaded** and can no longer be selected for another download, preventing redundant downloads.

When finished, WMM automatically requests source synchronization to add the new images to the library and generate their thumbnails.

Added images then become available for WMM's usual features.

#### Dragging images to monitors

In **Edit mode**, you can drag an Online thumbnail directly onto a virtual monitor.

WMM prepares the original image for preview in the composition without requiring you to download it first using the **Download** button.

When you click **Accept** in the editor, the image is permanently added to the Online folder and synchronized with the library.

#### API Keys

The **API Keys** button opens the form for managing personal credentials for the available providers.

At the top is an expandable **TIP** section with information about these keys.

Each provider has an information field and two alternative actions:

- **Browse**: lets you select a file containing your personal API key.
- **Unlink**: removes the association with that file without modifying or deleting it.

WMM checks the validity of the content before linking it. Keys are not stored directly in the configuration: only the path to the corresponding file is retained.

The use of personal keys depends on the characteristics and terms of each provider.

### Layout and order

Thumbnails are displayed in a grid that adapts to the available width.

Images are grouped by orientation first:

- **Horizontal (H)**: shown first.
- **Vertical (V)**: shown next.

Within each group, images are ordered by the date they were added to the WMM library, with the most recently added first.

### Interacting with thumbnails

You can interact with each thumbnail in several ways:

- **Double-click**: opens the original image in the system's default viewer.
- **Right-click**:
  - *"Add to favorites"*: adds the image to the favorites list.
  - *"Remove from favorites"*: removes it from that list if it is already a favorite.
- **Drag (Drag & Drop)**: in edit mode, drag a thumbnail onto a virtual monitor to assign that image.

### Favorite border

Images in the favorites list are highlighted with a border whose color adapts to the active visual theme.

# WMM icon (panel or system tray)

The WMM icon provides access to its controls and tools without opening the configuration panel.

- **Left-click**: opens the main menu.
- **Middle-click**: requests the next wallpaper.
- **Right-click**: opens the context menu.

## Main menu

Provides access to rotation controls, favorites, slideshow, Spanned Mode, and image metadata, as well as the command for changing the wallpaper immediately.

### Favorites

The WMM **Favorites** menu lets you quickly access saved presets and create new ones from the current composition.

#### "Favorites only" switch

When enabled, the slideshow uses only saved favorite content:

- **Synchronous mode**: selects a preset and applies the entire composition.
- **Asynchronous mode**: uses individual images from the favorites list.

If you enable **Favorites only** while the slideshow is off, WMM enables it automatically so rotation can work.

#### Add a preset

Click **"Add Preset to Favorites"** to save the current composition.

A dialog opens where you can enter the preset's name. WMM suggests an automatic name, such as *"Bookmark 01"*, which you can replace.

- **Blank name**: WMM warns you and does not save the preset.
- **Duplicate name**: you must choose a different name.
- **Saving the preset**: saves the current monitor configuration, including images and the options associated with the composition.

#### Preset list

The saved preset list appears beneath the controls.

- **Load a preset**: click its name to apply it. WMM stops the timer if it was running and loads the saved composition.
- **Delete a preset**: click the trash icon and confirm the deletion.

### Slideshow

This menu lets you control automatic wallpaper changes without opening the control panel.

#### "Enabled / Disabled" switch

The main switch turns the rotation timer on or off.

- **Enabled**: starts the countdown to the next change.
- **Disabled**: keeps the current composition until you enable the slideshow again or force a manual rotation.

The state is automatically synchronized with the control panel.

#### Interval

Sets how many minutes should pass between changes.

Depending on the desktop environment, the control may appear as a slider or adjustment buttons. The minimum value is 1 minute and the maximum is set by **Maximum frequency** in the control panel.

Interval changes are applied to the WMM timer.

### Monitors (Rotation Mode)

Controls how wallpaper changes are distributed across screens.

- **ASYNC (One)**: monitors take turns changing. Only one receives a new image per cycle.
- **SYNC (All)**: all monitors change at the same time.

The mode changes immediately without restarting the slideshow.

### Spanned Mode

Enables or disables panoramic wallpaper.

When enabled, WMM uses a single image to build a composition that covers the monitor arrangement, respecting each screen's position and geometry.

This option only takes effect when more than one monitor is active.

While **Spanned** is enabled, the individual monitor switches are locked because the composition is shared across all screens.

### Image Metadata

Lets you show or hide image information directly from the WMM main menu without opening the control panel.

- **Enabled**: displays metadata using the configured fields, font, position, and other settings.
- **Disabled**: hides metadata without losing its configuration.

Changes are applied to the wallpaper and synchronized with **Image Metadata** in the control panel.

### Next wallpaper

Requests an immediate wallpaper change using WMM's current rotation mode and configuration.

- **Left-click**: requests the next wallpaper without waiting for the timer.
- **Right-click**: opens the keyboard shortcut configuration form.

If a keyboard shortcut has been assigned, the combination appears to the right of "Next wallpaper".

#### Keyboard shortcuts

WMM lets you assign a global keyboard shortcut to request the next wallpaper without opening its main menu.

To configure it, right-click "Next wallpaper". A form opens showing the currently registered combination and allowing you to change it.

- **Assign or change**: press the desired combination in the capture field. You do not have to type it manually.
- **Clear**: clears the capture field to remove the current shortcut or enter a new one.
- **Accept**: validates and registers the chosen combination. If the field is empty, the registered shortcut is removed.
- **Cancel**: discards the changes and keeps the previous combination.

The form warns you if a combination is unsupported, incomplete, or detected as already in use. In these cases, choose another combination.

During configuration, the previous shortcut is temporarily suspended so it can be changed. If you cancel, WMM automatically restores it.

Confirmed changes are retained between sessions, and the registered combination is displayed beside "Next wallpaper" in the main menu.

## Context menu

The context menu brings together WMM's configuration, maintenance, and information tools:

- **Settings**: opens the control panel.
- **Synchronize library**: checks all sources and updates the library.
- **Installation Manager**: available on Linux and Windows Open Code. Provides WMM maintenance operations. The compiled Windows version uses Inno Setup.
- **Debug Log Viewer**: opens the activity and diagnostics viewer.
- **Help**: opens this manual.
- **Start WMM with Windows** (Windows only): enables or disables automatic startup when you sign in.
- **About WMM Manager**: displays information about the application.
- **Exit WMM**: closes WMM.

### Synchronize library

Checks all configured sources and updates the WMM library to match the current contents of the disk.

Synchronization detects new, modified, and removed images, updates the required references, and rebuilds the appropriate thumbnails.

It is especially useful after changing folders outside WMM or when the **"Resynchronize sources"** notice appears.

Synchronization does not modify or delete original images.

### Installation Manager

WMM provides different maintenance mechanisms depending on the operating system and type of installation.

#### Linux

The Installation Manager lets you update, reinstall, or uninstall WMM through a graphical interface.

The window shows the installed version and detected desktop environment.

- **Update**: checks whether a newer version has been published on GitHub and lets you download and install it.
- **Reinstall**: reinstalls the current version using a clean copy of the repair package prepared during installation.
- **Uninstall**: removes WMM, its desktop integrations, configuration, and associated data.

Operations are performed using WMM's installation and uninstallation scripts.

The manager includes a terminal where you can view progress and operation messages. If administrative privileges are required, enter your password directly in that terminal.

During a maintenance operation, the other controls remain locked until it finishes.

#### Windows Open Code

The Open Code distribution has its own maintenance manager, built in PowerShell and available from the WMM context menu.

The window displays the installed version, local package version, and latest version available on GitHub when it can be checked.

Available operations depend on the versions detected and the packages available:

- **Install**: installs WMM from a valid local distribution when it is not yet installed.
- **Update**: installs a newer version from either the local package or GitHub.
- **Reinstall**: restores the installed version using the corresponding local package or WMM's repair copy.
- **Downgrade**: lets you install an older version when its local distribution is available.
- **Uninstall**: removes WMM, its Windows integrations, configuration, and cache.

The manager requests confirmation before each operation and identifies the version and origin of the selected package.

If only the runtime is missing from an otherwise valid local distribution, WMM can offer to download it from GitHub after obtaining your permission.

Operations display their progress in a separate window. Original wallpaper files are not removed during uninstallation.

#### Windows — Inno Setup

The compiled Windows distribution uses the Inno Setup installer and does not include the Open Code Installation Manager.

- **Install**: run the WMM installer and follow the wizard's instructions.
- **Update or reinstall**: run the installer for the version you want to install. Inno Setup manages replacement of application files.
- **Uninstall**: use the WMM uninstall option in Windows or the corresponding Start menu shortcut.

The Inno Setup uninstaller provides two independent checkboxes for choosing whether to remove:

- **Thumbnail cache**: temporary files generated for displaying images.
- **WMM configuration data**: persistent information such as preferences, sources, favorites, profiles, and history.

These options appear before uninstallation begins and let you choose which additional data to remove. Some auxiliary configuration files are removed as part of routine cleanup.

Uninstallation never deletes the user's original image files.

### Debug Log Viewer

The log viewer displays WMM activity in real time and helps you see what the engine, control panel, or desktop integrations are doing.

#### Filters

You can filter entries by **Source**, **Level**, and **Reason**, as well as search for text.

#### Auto-scroll

Automatically follows new log entries.

#### Reverse order

Lets you show the most recent entries first or keep the normal chronological order.

#### Clear log

The clear button empties the log after asking for confirmation.

The viewer remembers your **Auto-scroll** and **Reverse order** preferences, as well as its window size.

### Help

Opens this WMM help window.

The navigation index appears on the left, and the formatted Markdown content on the right, so you can jump directly to the section you need.

### About WMM Manager

Displays basic information about WMM, including the installed version, application name, and license.
Some desktop environments also provide useful links.

# File managers

WMM integrates with **Nemo**, **Nautilus**, **Dolphin**, **Caja**, **Thunar**, and **Explorer** when those file managers are available on the system.

When you right-click an image, you may find WMM actions to:

- **Add to favorites**.
- **Send to a monitor**.
- **Span the image across all screens**.

Depending on the file manager, these actions may be grouped under **WMM Manager** or shown separately.

In MATE, the Caja integration may also provide an action to span the current image from the desktop's context menu.

# Keyboard shortcuts

WMM registers the **Next wallpaper** action through the shortcut mechanisms of **Cinnamon**, **GNOME Shell**, **KDE Plasma 6**, **MATE**, and **XFCE**.

You can configure the key combination through your desktop environment's keyboard shortcut settings.

Since WMM 2.0, you can also assign, change, or remove the shortcut directly from the main menu of the WMM icon. Right-click **Next wallpaper** to open the configuration form.

The following instructions explain how to manage the shortcut from each Linux desktop environment.

## In Cinnamon

1. Open **System Settings → Keyboard → Keyboard shortcuts**.
2. Go to **Custom Shortcuts**.
3. Find **"WMM - Next wallpaper"**.
4. Assign your preferred combination, for example `Ctrl+Alt+N`.

## In GNOME Shell

1. Open **Keyboard** settings and the custom shortcuts section.
2. Find the WMM action for **Next wallpaper**.
3. Assign your preferred key combination.

## In KDE Plasma 6

1. Open **System Settings → Shortcuts**.
2. Find **WMM Manager** and **Next wallpaper**.
3. Assign the key combination you want to use.

## In MATE

1. Open MATE's **Keyboard Shortcuts** settings.
2. Find **"WMM - Next wallpaper"**.
3. Assign your preferred combination.

## In XFCE

1. Open **Settings → Keyboard → Application Shortcuts**.
2. Find the **wmm-next.sh** command registered by WMM.
3. Select the entry and edit its shortcut.
4. Assign your preferred key combination.

The shortcut requests a manual rotation using WMM's current mode and configuration.
