# SPDX-FileCopyrightText: 2026 makimanson
# SPDX-License-Identifier: GPL-3.0-or-later
# WMM - Wallpaper Multi-Monitor Manager
# Windows Open Code Installer / Install Manager / Uninstaller
#
# La interfaz y todas las operaciones Windows comparten este único script.
# Las operaciones destructivas usan una copia temporal de este mismo archivo:
# nunca ejecutan su código desde el árbol que van a sustituir o borrar.

param(
    [ValidateSet('install', 'upgrade', 'downgrade', 'repair', 'uninstall')]
    [string]$Operation,
    [switch]$Console,
    [switch]$Worker,
    [string]$PackageRoot,
    [string]$TempRoot,
    [ValidateSet('Auto', 'Local', 'GitHub', 'Repair')]
    [string]$Source = 'Auto',
    [string]$ExpectedVersion,
    [switch]$RecoverRuntime,
    [ValidateSet('Ask', 'Yes', 'No')]
    [string]$DesktopOption = 'Ask',
    [ValidateSet('Ask', 'Yes', 'No')]
    [string]$AutostartOption = 'Ask'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ($env:OS -ne 'Windows_NT') {
    throw 'Unsupported operating system.'
}

$script:WmmManagedBridge = $null
$script:WmmSelfPath = $PSCommandPath
$script:ScriptDir = $PSScriptRoot
$script:ProjectDir = Join-Path $ScriptDir 'wmm'
$script:ReadmeFile = Join-Path $ScriptDir 'README.md'
$script:ChangelogFile = Join-Path $ScriptDir 'CHANGELOG.md'
$script:LicenseFile = Join-Path $ScriptDir 'LICENSE'
$script:RuntimeArchive = Join-Path $ScriptDir 'wmm-runtime.zip'
$script:WmmVersion = $null
$script:WmmReleaseYear = $null
$script:WmmVersion = $null
$script:WmmReleaseYear = $null

# Windows solo está soportado en las releases GitHub desde v2.0.0.
$script:WmmMinGitHubVersion = [version]'2.0.0'

# El runtime tiene una publicación independiente de la versión del código.
# Se reutiliza el asset mientras no cambie su contenido ni compatibilidad.
$script:WmmRuntimeReleaseTag = 'v2.0.0'

# Cero para todas las operaciones existentes; la recuperación de runtime
# añade un hito exclusivo al progreso de Reinstalar.
$script:WmmProgressOffset = 0

$InstallBase = Join-Path $env:LOCALAPPDATA 'Programs'
$InstallDir = Join-Path $InstallBase 'WMM Manager'
$AppConfig = Join-Path $env:APPDATA 'WMM Manager'
$DataDir = Join-Path $AppConfig 'data'
$CacheDir = Join-Path $env:LOCALAPPDATA 'WMM Manager\cache'

# ----------------------------------------------------------
# CONTEXTO DE EJECUCIÓN
# La procedencia depende de dónde se inició el instalador,
# nunca de la disponibilidad de archivos del paquete.
# El worker conserva esa procedencia mediante PackageRoot.
# ----------------------------------------------------------
$script:WmmOriginRoot = if ($Worker) { $PackageRoot } else { $PSScriptRoot }

if (-not $script:WmmOriginRoot) {
    throw 'WMM installer origin was not provided.'
}

$installedManagerRoot = Join-Path $InstallDir 'wmm_platform\shell\installer'

$script:WmmFromInstalled = [string]::Equals(
    [IO.Path]::GetFullPath($script:WmmOriginRoot).TrimEnd('\'),
    [IO.Path]::GetFullPath($installedManagerRoot).TrimEnd('\'),
    [StringComparison]::OrdinalIgnoreCase
)

# ----------------------------------------------------------
# LOCALIZACIÓN: Textos de la interfaz Windows
# Inglés como idioma original y de respaldo.
# La selección utiliza la cultura de interfaz de PowerShell.
# No afecta a los identificadores internos de las operaciones.
# ----------------------------------------------------------
$script:WmmTranslations = @{
    en = @{
        WindowTitle = 'WMM Install Manager'
        PreparingMaintenance = 'Preparing maintenance...'
        InstalledVersion = 'Installed version'
        PackageVersion = 'Package version'
        GitHubVersion = 'GitHub'
        NotAvailable = 'N/A'
        LocalPackageMissingFile = 'Local package incomplete: missing {0}'
        LocalPackage = 'Local package'
        GithubPackage = 'GitHub'
        RepairPackage = 'Repair package'
        RepairPackageMissing = 'Missing wmm-repair.zip; Reinstall unavailable.'
        InstalledPackage = 'Installed WMM'
        TargetVersion = 'Target version'
        PackageSource = 'Source'
        Desktop = 'Desktop'
        Session = 'Session'
        Unknown = 'Unknown'
        NotInstalled = 'Not installed'
        ChooseOperation = 'Choose a maintenance operation.'
        ReadyToInstall = 'WMM is ready for installation.'

        Install = 'Install'
        Upgrade = 'Upgrade'
        Reinstall = 'Reinstall'
        Downgrade = 'Downgrade'
        Uninstall = 'Uninstall'
        Close = 'Close'

        ConfirmInstall = 'Install WMM?'
        ConfirmUpgrade = 'Upgrade WMM?'
        ConfirmReinstall = 'Reinstall WMM?'
        ConfirmRuntimeDownload = 'wmm-runtime.zip is missing from the local package. Download it from GitHub and reinstall WMM {0}?'
        ConfirmRuntimeInstall = 'wmm-runtime.zip is missing from the local package. Download it from GitHub and install WMM {0}?'
        ConfirmDowngrade = 'Install an older version of WMM?'
        ConfirmUninstall = 'WMM and its desktop integration, settings, and cache will be removed. Continue?'
        DesktopShortcut = 'Create a desktop shortcut'
        Autostart = 'Start WMM with Windows'
        InstallationTitle = 'WMM Installation'
        Cancel = 'Cancel'
        UninstallTitle = 'WMM Uninstall'
        DirectUninstall = 'Remove WMM, its settings and cache?'
        StartFailed = 'Unable to start maintenance'

        Settings = 'Settings'
        Help = 'Help'
        Changelog = 'Changelog'
        DebugViewer = 'Debug Log Viewer'
        About = 'About'
		SetupInstaller = 'Setup Installer'
    }

    es = @{
        WindowTitle = 'Gestor de instalación de WMM'
        PreparingMaintenance = 'Preparando mantenimiento...'
        InstalledVersion = 'Versión instalada'
        PackageVersion = 'Versión del paquete'
        GitHubVersion = 'GitHub'
        NotAvailable = 'N/A'
        LocalPackageMissingFile = 'Paquete local incompleto: falta {0}'
        LocalPackage = 'Paquete local'
        GithubPackage = 'GitHub'
        RepairPackage = 'Paquete de reparación'
        RepairPackageMissing = 'Falta wmm-repair.zip; Reinstalar no disponible.'
        InstalledPackage = 'WMM instalado'
        TargetVersion = 'Versión de destino'
        PackageSource = 'Procedencia'
        Desktop = 'Escritorio'
        Session = 'Sesión'
        Unknown = 'Desconocida'
        NotInstalled = 'No instalado'
        ChooseOperation = 'Selecciona una operación de mantenimiento.'
        ReadyToInstall = 'WMM está preparado para instalarse.'

        Install = 'Instalar'
        Upgrade = 'Actualizar'
        Reinstall = 'Reinstalar'
        Downgrade = 'Retroceder'
        Uninstall = 'Desinstalar'
        Close = 'Cerrar'

        ConfirmInstall = '¿Instalar WMM?'
        ConfirmUpgrade = '¿Actualizar WMM?'
        ConfirmReinstall = '¿Reinstalar WMM?'
        ConfirmRuntimeDownload = 'Falta wmm-runtime.zip en el paquete local. ¿Descargarlo desde GitHub y reinstalar WMM {0}?'
        ConfirmRuntimeInstall = 'Falta wmm-runtime.zip en el paquete local. ¿Descargarlo desde GitHub e instalar WMM {0}?'
        ConfirmDowngrade = '¿Instalar una versión anterior de WMM?'
        ConfirmUninstall = 'Se eliminarán WMM, su integración con Windows, la configuración y la caché. ¿Continuar?'
        DesktopShortcut = 'Crear un acceso directo en el escritorio'
        Autostart = 'Iniciar WMM con Windows'
        InstallationTitle = 'Instalación de WMM'
        Cancel = 'Cancelar'
        UninstallTitle = 'Desinstalación de WMM'
        DirectUninstall = '¿Eliminar WMM, su configuración y la caché?'
        StartFailed = 'No se puede iniciar el mantenimiento'

        Settings = 'Ajustes'
        Help = 'Ayuda'
        Changelog = 'Registro de cambios'
        DebugViewer = 'Visor de depuración'
        About = 'Acerca de'
		SetupInstaller = 'Gestor de instalación'
    }

    ca = @{
        WindowTitle = "Gestor d'instal·lació de WMM"
        PreparingMaintenance = 'Preparant el manteniment...'
        InstalledVersion = 'Versió instal·lada'
        PackageVersion = 'Versió del paquet'
        GitHubVersion = 'GitHub'
        NotAvailable = 'N/A'
        LocalPackageMissingFile = 'Paquet local incomplet: falta {0}'
        LocalPackage = 'Paquet local'
        GithubPackage = 'GitHub'
        RepairPackage = 'Paquet de reparació'
        RepairPackageMissing = 'Falta wmm-repair.zip; Reinstal·lar no disponible.'
        InstalledPackage = 'WMM instal·lat'
        TargetVersion = 'Versió de destinació'
        PackageSource = 'Procedència'
        Desktop = 'Escriptori'
        Session = 'Sessió'
        Unknown = 'Desconeguda'
        NotInstalled = 'No instal·lat'
        ChooseOperation = 'Selecciona una operació de manteniment.'
        ReadyToInstall = 'WMM està preparat per instal·lar-se.'

        Install = 'Instal·lar'
        Upgrade = 'Actualitzar'
        Reinstall = 'Reinstal·lar'
        Downgrade = 'Retrocedir'
        Uninstall = 'Desinstal·lar'
        Close = 'Tancar'

        ConfirmInstall = 'Voleu instal·lar WMM?'
        ConfirmUpgrade = 'Voleu actualitzar WMM?'
        ConfirmReinstall = 'Voleu reinstal·lar WMM?'
        ConfirmRuntimeDownload = 'Falta wmm-runtime.zip al paquet local. Voleu descarregar-lo de GitHub i reinstal·lar WMM {0}?'
        ConfirmRuntimeInstall = 'Falta wmm-runtime.zip al paquet local. Voleu descarregar-lo de GitHub i instal·lar WMM {0}?'
        ConfirmDowngrade = 'Voleu instal·lar una versió anterior de WMM?'
        ConfirmUninstall = 'S''eliminaran WMM, la seva integració amb Windows, la configuració i la memòria cau. Voleu continuar?'
        DesktopShortcut = "Crear una drecera a l'escriptori"
        Autostart = 'Iniciar WMM amb Windows'
        InstallationTitle = 'Instal·lació de WMM'
        Cancel = 'Cancel·lar'
        UninstallTitle = 'Desinstal·lació de WMM'
        DirectUninstall = 'Voleu eliminar WMM, la configuració i la memòria cau?'
        StartFailed = 'No es pot iniciar el manteniment'

        Settings = 'Configuració'
        Help = 'Ajuda'
        Changelog = 'Registre de canvis'
        DebugViewer = 'Visor de depuració'
        About = 'Quant a'
		SetupInstaller = "Gestor d'instal·lació"
    }
}

# Seleccionar una única tabla para toda la ejecución.
$script:WmmLanguage = ($PSUICulture -split '-')[0].ToLowerInvariant()
$script:WmmTexts = $script:WmmTranslations['en'].Clone()

if ($script:WmmTranslations.ContainsKey($script:WmmLanguage)) {
    foreach ($entry in $script:WmmTranslations[$script:WmmLanguage].GetEnumerator()) {
        $script:WmmTexts[$entry.Key] = $entry.Value
    }
}

function Get-WmmText([string]$Key) {
    if (-not $script:WmmTexts.ContainsKey($Key)) {
        throw "Missing WMM translation key: $Key"
    }

    return [string]$script:WmmTexts[$Key]
}

# ----------------------------------------------------------
# Mensajes comunes: consola y, cuando existe, hilo Windows Forms.
# ----------------------------------------------------------
function Write-WmmManagedMessage([string]$Prefix, [string]$Message) {
    $bridge = $script:WmmManagedBridge
    if ($null -eq $bridge -or $null -eq $bridge.Form) { return }

    try {
        [void]$bridge.Form.BeginInvoke(
            $bridge.Append, [object[]]@($Prefix, $Message))
    }
    catch [System.InvalidOperationException] {
        # La ventana ha sido cerrada por el propio ciclo de mantenimiento.
    }
}

# ----------------------------------------------------------
# FUNCIÓN: Actualizar el progreso de mantenimiento
# Cada avance corresponde a una etapa alcanzada realmente.
# Reserva el 100 % para la finalización correcta del worker.
# ----------------------------------------------------------
function Set-WmmProgress([int]$Stage) {
    $bridge = $script:WmmManagedBridge

    # El modo consola no necesita interfaz gráfica.
    if ($null -eq $bridge -or $null -eq $bridge.Form -or
            $bridge.ProgressTotal -le 0) {
        return
    }

    # La recuperación añade un hito anterior al ciclo normal.
    $value = [int][Math]::Floor(
        95.0 * ($Stage + $script:WmmProgressOffset) / $bridge.ProgressTotal)

    # Nunca retroceder por mensajes tardíos o fases repetidas.
    $value = [Math]::Min(95, $value)

    if ($value -le $bridge.ProgressValue) {
        return
    }

    $bridge.ProgressValue = $value

    try {
        [void]$bridge.Form.BeginInvoke($bridge.UpdateProgress)
    }
    catch [System.InvalidOperationException] {
        # La interfaz ya no está disponible.
    }
}

function Info([string]$Message) {
    Write-Host "[..] $Message"
    Write-WmmManagedMessage '..' $Message
}

function Ok([string]$Message) {
    Write-Host "[OK] $Message" -ForegroundColor Green
    Write-WmmManagedMessage 'OK' $Message
}

function Warn([string]$Message) {
    Write-Host "[!!] $Message" -ForegroundColor Yellow
    Write-WmmManagedMessage '!!' $Message
}

function Fail([string]$Message) {
    Warn $Message
    throw $Message
}

# ----------------------------------------------------------
# Requisitos del árbol fuente Windows, compartidos entre el
# diagnóstico previo y Test-WmmSource. Mantener una sola lista
# evita ofrecer recuperar el runtime si falta otro recurso.
# ----------------------------------------------------------
function Get-WmmSourceRequirements {
    return @{
        Directories = @(
            'python'
            'wmm_platform'
            'wmm_platform\shell\data'
            'wmm_platform\shell\po'
            'help'
            'licenses'
        )
        Files = @(
            'WMM-icon.ico'
            'licenses\WMM\RESPONSIBLE_USE.txt'
            'wmm_platform\shell\data\about.json'
            'wmm_platform\shell\data\launch_profiles.json'
            'wmm_platform\shell\data\monitor_mfg.json'
            'wmm_platform\shell\windows\windows-frontend.css'
            'wmm_platform\shell\windows\wmm-win32.css'
            'wmm_platform\shell\file_manager\explorer\wmm-explorer-unreg.reg'
        )
    }
}

# ----------------------------------------------------------
# Identidad y disponibilidad del paquete local.
# La versión de CHANGELOG no depende del runtime Windows.
# El árbol instalado no se considera una distribución fuente.
# ----------------------------------------------------------
function Get-WmmLocalPackageInfo([string]$Root) {
    $info = [pscustomobject]@{
        Version = $null
        Available = $false
        MissingFile = $null
    }

    if (-not $Root -or -not (Test-Path -LiteralPath $Root -PathType Container)) {
        return $info
    }

    # IDENTIDAD
    # Leer la versión aunque falten recursos de instalación.
    $changelog = Join-Path $Root 'CHANGELOG.md'

    if (Test-Path -LiteralPath $changelog -PathType Leaf) {
        try {
            foreach ($line in (Get-Content -LiteralPath $changelog -Encoding UTF8 -ErrorAction Stop)) {
                if ($line -match '^#\s+v(?<version>\d+\.\d+\.\d+)(?:\s+-|\s|$)') {
                    $info.Version = $Matches['version']
                    break
                }
            }
        }
        catch {
            # La lectura fallida no debe impedir abrir el gestor.
        }
    }

    # DISPONIBILIDAD
    # Si falta wmm/, no enumerar sus requisitos internos.
    # Los recursos independientes (como el runtime) sí se diagnostican.
    $projectRoot = Join-Path $Root 'wmm'
    $projectPresent = Test-Path -LiteralPath $projectRoot -PathType Container
    $missing = @()
    $requiredFiles = @('README.md', 'CHANGELOG.md', 'LICENSE', 'wmm-runtime.zip')

    if (-not $projectPresent) {
        $missing += 'wmm'
    }
    else {
        $requiredFiles += @(
            'wmm\python\main.py',
            'wmm\wmm_platform\shell\windows\windows-frontend.py'
        )

        $requirements = Get-WmmSourceRequirements
        foreach ($relative in $requirements.Directories) {
            $path = Join-Path $projectRoot $relative
            if (-not (Test-Path -LiteralPath $path -PathType Container)) {
                $missing += 'wmm\' + $relative
            }
        }

        foreach ($relative in $requirements.Files) {
            $requiredFiles += 'wmm\' + $relative
        }
    }

    foreach ($relative in $requiredFiles) {
        if (-not (Test-Path -LiteralPath (Join-Path $Root $relative) -PathType Leaf)) {
            $missing += $relative
        }
    }

    if ($missing.Count -gt 0) {
        $info.MissingFile = $missing -join ', '
        return $info
    }

    # Sin versión reconocible no se habilitan operaciones locales.
    # La integridad completa del ZIP sigue validándose al operar.
    if ($info.Version) {
        $info.Available = $true
    }

    return $info
}

# ----------------------------------------------------------
# Compatibilidad con los consumidores actuales.
# Solo expone una versión si el paquete puede utilizarse.
# La información completa pertenece a Get-WmmLocalPackageInfo.
# ----------------------------------------------------------
function Get-WmmLocalPackageVersion([string]$Root) {
    $info = Get-WmmLocalPackageInfo $Root

    if ($info.Available) {
        return $info.Version
    }

    return $null
}

# ----------------------------------------------------------
# Solo se puede completar automáticamente una distribución
# cuyo único requisito ausente sea el runtime Windows.
# ----------------------------------------------------------
function Test-WmmRuntimeRecovery($Info) {
    return (-not $script:WmmFromInstalled -and $Info.Version -and
        -not $Info.Available -and $Info.MissingFile -eq 'wmm-runtime.zip')
}

# ----------------------------------------------------------
# Las opciones describen la operación y la procedencia; el
# worker no tiene permiso para sustituir una por otra.
# Coincidencias local/GitHub se resuelven en favor del local.
# ----------------------------------------------------------
function Get-WmmOperationChoices {
    param(
        [bool]$Installed,
        [string]$InstalledVersion,
        [string]$LocalVersion,
        [string]$GithubVersion,
        [string]$RecoverableLocalVersion = ''
    )

    $choices = @()
    if ($LocalVersion) {
        if (-not $Installed) {
            $action = 'install'
            $textKey = 'Install'
        }
        elseif ($InstalledVersion) {
            if ([version]$LocalVersion -gt [version]$InstalledVersion) {
                $action = 'upgrade'; $textKey = 'Upgrade'
            }
            elseif ([version]$LocalVersion -lt [version]$InstalledVersion) {
                $action = 'downgrade'; $textKey = 'Downgrade'
            }
            else {
                $action = 'repair'; $textKey = 'Reinstall'
            }
        }
        else {
            # Sin metadatos instalados no es posible decidir la dirección.
            $action = $null
        }

        if ($action) {
            $choices += [pscustomobject]@{
                Action=$action; Source='Local'; Version=$LocalVersion
                TextKey=$textKey; CaptionKey='LocalPackage'
            }
        }
    }

    # Una instalación limpia también puede completar su distribución
    # cuando solamente falta el runtime. La fuente sigue siendo Local.
    if (-not $Installed -and -not $LocalVersion -and $RecoverableLocalVersion) {
        $choices += [pscustomobject]@{
            Action='install'; Source='Local'; Version=$RecoverableLocalVersion
            TextKey='Install'; CaptionKey='LocalPackage'
        }
    }

    # El ZIP de código de GitHub puede carecer del runtime Windows.
    # Solo el gestor instalado puede completarlo con su propio runtime;
    # el instalador fuente nunca debe recurrir a la instalación existente.
    $githubUsable = $script:WmmFromInstalled -and $GithubVersion -and
        ([version]$GithubVersion -ge $script:WmmMinGitHubVersion) -and
        (-not $LocalVersion -or
        ([version]$GithubVersion -ne [version]$LocalVersion))

	if ($githubUsable) {
        if (-not $Installed -and $LocalVersion) {
            $action = 'install'; $textKey = 'Install'
        }
        elseif ($InstalledVersion -and [version]$GithubVersion -gt [version]$InstalledVersion) {
            $action = 'upgrade'; $textKey = 'Upgrade'
        }
        else { $action = $null }

        if ($action) {
            $choices += [pscustomobject]@{
                Action=$action; Source='GitHub'; Version=$GithubVersion
                TextKey=$textKey; CaptionKey='GithubPackage'
            }
        }
    }

    if ($Installed) {
        # La falta del runtime no oculta Reinstalar desde fuentes.
        # No equivale a actualizar ni a cambiar de procedencia.
        if (-not $LocalVersion -and $RecoverableLocalVersion -and $InstalledVersion -and
                ([version]$RecoverableLocalVersion -eq [version]$InstalledVersion)) {
            $choices += [pscustomobject]@{
                Action='repair'; Source='Local'; Version=$RecoverableLocalVersion
                TextKey='Reinstall'; CaptionKey='LocalPackage'
            }
        }

        # Repair package pertenece exclusivamente al gestor instalado.
        # La integridad de la distribución fuente no cambia su procedencia.
        if ($script:WmmFromInstalled -and -not ($LocalVersion -and $InstalledVersion -and
                ([version]$LocalVersion -eq [version]$InstalledVersion))) {
            $choices += [pscustomobject]@{
                Action='repair'; Source='Repair'; Version=$InstalledVersion
                TextKey='Reinstall'; CaptionKey='RepairPackage'
            }
        }
        $choices += [pscustomobject]@{
            Action='uninstall'; Source='Auto'; Version=$null
            TextKey='Uninstall'; CaptionKey='InstalledPackage'
        }
    }
    return $choices
}

# ----------------------------------------------------------
# Presentación: los botones son ranuras reutilizables; al
# completarse la consulta asíncrona se cambia su contenido,
# nunca se añaden procedimientos ni se ejecuta mantenimiento.
# ----------------------------------------------------------
function Update-WmmManagerChoices([System.Windows.Forms.Form]$Form) {
    $state = $Form.Tag
    $choices = @(Get-WmmOperationChoices -Installed $state.Installed `
        -InstalledVersion $state.InstalledVersion -LocalVersion $state.LocalVersion `
        -GithubVersion $state.GithubVersion `
        -RecoverableLocalVersion $state.RecoverableLocalVersion)
    $count = $choices.Count

    for ($i = 0; $i -lt $state.Buttons.Count; $i++) {
        $button = $state.Buttons[$i]
        $caption = $state.Captions[$i]
        if ($i -ge $count) {
            $button.Visible = $false
            $caption.Visible = $false
            $button.Tag = $null
            continue
        }

        $choice = $choices[$i]
        $text = Get-WmmText $choice.TextKey
        if ($choice.Version) { $text += ' ' + $choice.Version }
        $button.Text = $text
        $button.Tag = $choice
        $caption.Text = Get-WmmText $choice.CaptionKey

        # El gestor instalado mantiene visible Reinstalar, pero no
        # permite ejecutarlo sin su paquete de reparación.
        # Reinstalar desde fuentes (Source=Local) no depende de él.
        $button.Enabled = $choice.Source -ne 'Repair' -or (Test-WmmRepairArchive)

        if ($count -eq 4) {
            # Dos filas para conservar legibilidad y ancho compacto.
            $width = 176; $gap = 16
            $left = [int](($Form.ClientSize.Width - (2 * $width + $gap)) / 2)
            $x = $left + ($i % 2) * ($width + $gap)
            $y = 219 + [int][Math]::Floor($i / 2) * 54
        }
        else {
            # Hasta tres opciones: mantener una sola fila centrada.
            $width = 134; $gap = 10
            $left = [int](($Form.ClientSize.Width - ($count * $width + ($count - 1) * $gap)) / 2)
            $x = $left + $i * ($width + $gap)
            $y = 245
        }

        $button.Location = [System.Drawing.Point]::new($x, $y)
        $button.Size = [System.Drawing.Size]::new($width, 30)
        $caption.Location = [System.Drawing.Point]::new($x, ($y + 32))
        $caption.Size = [System.Drawing.Size]::new($width, 18)
        $button.Visible = $true
        $caption.Visible = $true
    }
}

# ----------------------------------------------------------
# Identidad del paquete: se valida íntegramente al operar;
# el gestor instalado (que carece de wmm/ y wmm-runtime.zip).
# ----------------------------------------------------------
function Set-WmmPackage([string]$Root) {
    $resolved = (Resolve-Path -LiteralPath $Root -ErrorAction Stop).Path
    $script:ScriptDir = $resolved
    $script:ProjectDir = Join-Path $resolved 'wmm'
    $script:ReadmeFile = Join-Path $resolved 'README.md'
    $script:ChangelogFile = Join-Path $resolved 'CHANGELOG.md'
    $script:LicenseFile = Join-Path $resolved 'LICENSE'
    $script:RuntimeArchive = Join-Path $resolved 'wmm-runtime.zip'
    $script:WmmVersion = $null
    $script:WmmReleaseYear = $null

    $required = @(
        $ReadmeFile, $ChangelogFile, $LicenseFile,
        (Join-Path $ProjectDir 'python\main.py'),
        (Join-Path $ProjectDir 'wmm_platform\shell\windows\windows-frontend.py'),
        $RuntimeArchive
    )
    foreach ($path in $required) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Incomplete installation package. Missing: $path"
        }
    }

    foreach ($line in (Get-Content -LiteralPath $ChangelogFile -Encoding UTF8)) {
        if ($line -match '^#\s+v(?<version>\d+\.\d+\.\d+)(?:\s+-\s+(?<date>\d{4}-\d{2}-\d{2}))?(?:\s|$)') {
            $script:WmmVersion = $Matches['version']
            $dateText = $Matches['date']
            if ($dateText) {
                $parsedDate = [datetime]::MinValue
                if ([datetime]::TryParseExact(
                    $dateText, 'yyyy-MM-dd',
                    [Globalization.CultureInfo]::InvariantCulture,
                    [Globalization.DateTimeStyles]::None, [ref]$parsedDate)) {
                    $script:WmmReleaseYear = $parsedDate.Year
                }
            }
            break
        }
    }
    if (-not $WmmVersion) { throw 'Could not determine WMM version from CHANGELOG.md.' }

    Info "Package WMM $WmmVersion verified."
}

# ----------------------------------------------------------
# El paquete nuevo puede distribuir una versión más reciente del
# gestor único. Si aún trae el instalador antiguo, conservar el
# vigente para no reintroducir la arquitectura de dos scripts.
# ----------------------------------------------------------
function Get-WmmInstallerSource {
    $candidate = Join-Path $ScriptDir 'wmm-install.ps1'
    if (Test-Path -LiteralPath $candidate -PathType Leaf) {
        $firstLines = @(Get-Content -LiteralPath $candidate -TotalCount 12 -Encoding UTF8)
        if (($firstLines -join "`n").Contains(
            'Windows Open Code Installer / Install Manager / Uninstaller')) {
            return $candidate
        }
    }
    return $script:WmmSelfPath
}

# ----------------------------------------------------------
# FUNCIÓN: Leer la versión instalada
# about.json es la autoridad primaria, como en Linux.
# Una instalación sin metadatos sigue siendo reparable.
# ----------------------------------------------------------
function Get-WmmInstalledVersion {
    $aboutPath = Join-Path $DataDir 'about.json'

    if (-not (Test-Path -LiteralPath $aboutPath -PathType Leaf)) {
        return $null
    }

    try {
        $metadata = Get-Content -LiteralPath $aboutPath -Raw -Encoding UTF8 |
            ConvertFrom-Json

        $version = [string]$metadata.version

        if ($version -match '^\d+\.\d+\.\d+$') {
            return $version
        }
    }
    catch {
        # Los metadatos dañados no deben impedir la reparación.
    }

    return $null
}

# ----------------------------------------------------------
# FUNCIÓN: Verificar integridad del paquete fuente
# Comprueba los recursos comunes y los propios de Windows.
# Los módulos Linux se distribuyen, pero no requieren integración.
# ----------------------------------------------------------
function Test-WmmSource {
    $requirements = Get-WmmSourceRequirements
    $requiredDirectories = $requirements.Directories
    $requiredFiles = $requirements.Files

    foreach ($relative in $requiredDirectories) {
        $path = Join-Path $ProjectDir $relative

        if (-not (Test-Path -LiteralPath $path -PathType Container)) {
            Fail "Missing required source directory: wmm/$relative"
        }
    }

    foreach ($relative in $requiredFiles) {
        $path = Join-Path $ProjectDir $relative

        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            Fail "Missing required source file: wmm/$relative"
        }
    }

    Ok 'WMM source tree verified.'
}

# ----------------------------------------------------------
# FUNCIÓN: Preparar staging del código WMM
# Copia el árbol fuente completo y la documentación.
# El staging reside junto al destino para permitir su
# activación posterior sin trasladarlo entre volúmenes.
# ----------------------------------------------------------
function New-WmmAppStaging {
    New-Item -ItemType Directory -Path $InstallBase -Force | Out-Null

    $stage = Join-Path $InstallBase (
        '.wmm-install-new.' + [guid]::NewGuid().ToString('N')
    )

    New-Item -ItemType Directory -Path $stage | Out-Null

    try {
        Info 'Preparing clean WMM application staging...'

        # CORE WMM
        # Mantener el árbol completo, excluyendo únicamente cachés Python.
        & robocopy.exe $ProjectDir $stage /E /R:1 /W:1 /NP /NFL /NDL /NJH /NJS `
            /XD '__pycache__' /XF '*.pyc' | Out-Null

        if ($LASTEXITCODE -ge 8) {
            throw "Source copy failed (robocopy exit code: $LASTEXITCODE)"
        }

        # data/ en la raíz del paquete sólo existe para compatibilidad
        # con los gestores Linux v1.4.0/v1.5.0. No pertenece al core instalado.
        $legacyData = Join-Path $stage 'data'
        if (Test-Path -LiteralPath $legacyData -PathType Container) {
            Remove-Item -LiteralPath $legacyData -Recurse -Force -ErrorAction Stop
        }

        # DOCUMENTACIÓN
        # Al desaparecer /wmm durante la instalación, adaptar
        # las rutas de presentación y recursos comunes a la nueva raíz.
        $readme = [IO.File]::ReadAllText($ReadmeFile, [Text.Encoding]::UTF8)
        $readme = $readme.Replace(
            'wmm/WMM-presentation.jpg', 'WMM-presentation.jpg'
        )
        $readme = $readme.Replace(
            'wmm/wmm_platform/shell/logos/', 'wmm_platform/shell/logos/'
        )

        $utf8 = New-Object System.Text.UTF8Encoding($false)
        [IO.File]::WriteAllText((Join-Path $stage 'README.md'), $readme, $utf8)

        Copy-Item -LiteralPath $ChangelogFile -Destination $stage
        Copy-Item -LiteralPath $LicenseFile -Destination $stage

        # Componente legado retirado también por el instalador Linux.
        $legacy = Join-Path $stage 'wmm_platform\file_utils.py'
        if (Test-Path -LiteralPath $legacy) {
            Remove-Item -LiteralPath $legacy -Force
        }

        # FRONTEND WINDOWS
        # Materializar su ubicación operativa sin alterar el código fuente.
        $frontendSource = Join-Path $stage 'wmm_platform\shell\windows'
        $frontendTarget = Join-Path $stage 'frontends\windows'

        New-Item -ItemType Directory -Path $frontendTarget -Force | Out-Null

        foreach ($filename in @('windows-frontend.py', 'windows-frontend.css')) {
            Copy-Item -LiteralPath (Join-Path $frontendSource $filename) `
                -Destination (Join-Path $frontendTarget $filename) -ErrorAction Stop
        }

        # VALIDACIÓN
        $required = @(
            'python\main.py'
            'wmm_platform\shell\windows\windows-frontend.py'
            'wmm_platform\shell\windows\wmm-win32.css'
            'frontends\windows\windows-frontend.py'
            'frontends\windows\windows-frontend.css'
            'README.md'
            'CHANGELOG.md'
            'LICENSE'
        )

        foreach ($relative in $required) {
            $path = Join-Path $stage $relative
            if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
                throw "Missing staged file: $relative"
            }
        }

        return $stage
    }
    catch {
        # Ningún fallo de preparación debe abandonar un staging incompleto.
        Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
        throw
    }
}

# ----------------------------------------------------------
# FUNCIÓN: Preparar staging de datos WMM
# Separa los datos iniciales del core y materializa about.json.
# No modifica todavía los datos vivos del usuario.
# ----------------------------------------------------------
function New-WmmDataStaging {
    param([switch]$Preserve)

    $sourceData = Join-Path $ProjectDir 'wmm_platform\shell\data'

    $stage = Join-Path $env:APPDATA (
        '.wmm-data-new.' + [guid]::NewGuid().ToString('N')
    )

    # La raíz temporal representa APPDATA/WMM Manager.
    # settings_core.ini residirá junto a data/, no dentro de ella.
    $stagedDataDir = Join-Path $stage 'data'
    New-Item -ItemType Directory -Path $stagedDataDir -Force | Out-Null

    try {
        Info 'Preparing clean WMM data staging...'

        # DATOS INICIALES
        # Los recursos distribuidos pertenecen exclusivamente a data/.
        & robocopy.exe $sourceData $stagedDataDir /E /R:1 /W:1 /NP /NFL /NDL /NJH /NJS | Out-Null

        if ($LASTEXITCODE -ge 8) {
            throw "Data copy failed (robocopy exit code: $LASTEXITCODE)"
        }

        # ABOUT.JSON
        # La versión y el año proceden de CHANGELOG.md.
        $aboutPath = Join-Path $stagedDataDir 'about.json'
        $about = [IO.File]::ReadAllText($aboutPath, [Text.Encoding]::UTF8)

        $releaseYear = if ($null -ne $WmmReleaseYear) {
            [string]$WmmReleaseYear
        }
        else {
            'null'
        }

        $about = $about.Replace('@VERSION@', $WmmVersion)
        $about = $about.Replace('@RELEASE_YEAR@', $releaseYear)

        $utf8 = New-Object System.Text.UTF8Encoding($false)
        [IO.File]::WriteAllText($aboutPath, $about, $utf8)

        # PRESERVACIÓN DE DATOS
        if ($Preserve -and (Test-Path -LiteralPath $DataDir -PathType Container)) {
            $preserveFiles = @(
                'settings.json'
                'sources.json'
                'monitor_vault.json'
                'bookmarks.json'
                'bookmarks_single_list.json'
                'rotation_h.json'
                'rotation_v.json'
                'sel_rotation_h.json'
                'sel_rotation_v.json'
				'bookmark_rotation_h.json'
				'bookmark_rotation_v.json'
                'history_presets.json'
                'image_cache.json'
                'image_online.json'
                'scan_index.json'
            )

            foreach ($filename in $preserveFiles) {
                $source = Join-Path $DataDir $filename

                if (Test-Path -LiteralPath $source -PathType Leaf) {
                    Copy-Item -LiteralPath $source `
                        -Destination (Join-Path $stagedDataDir $filename) `
                        -Force -ErrorAction Stop
                }
            }
        }

        # VALIDACIÓN
        $required = @(
            'about.json'
            'monitor_mfg.json'
            'launch_profiles.json'
            'countries+states+cities.json'
        )

        foreach ($relative in $required) {
            $path = Join-Path $stagedDataDir $relative

            if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
                throw "Missing staged data file: $relative"
            }
        }

        $metadata = Get-Content -LiteralPath $aboutPath -Raw -Encoding UTF8 |
            ConvertFrom-Json

        if ($metadata.version -ne $WmmVersion) {
            throw 'Staged about.json contains an incorrect version.'
        }

        return $stage
    }
    catch {
        Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
        throw
    }
}

# ----------------------------------------------------------
# FUNCIÓN: Incorporar el runtime al staging de aplicación
# El ZIP ya contiene runtime/ como directorio raíz.
# No modifica la instalación definitiva.
# ----------------------------------------------------------
function Add-WmmRuntimeToStaging {
    param([string]$Stage)

    if (-not (Test-Path -LiteralPath $RuntimeArchive -PathType Leaf)) {
        throw "Runtime archive not available: $RuntimeArchive"
    }

    if (-not (Get-Command tar.exe -ErrorAction SilentlyContinue)) {
        throw 'Windows tar.exe is not available.'
    }

    $runtimeDir = Join-Path $Stage 'runtime'

    if (Test-Path -LiteralPath $runtimeDir) {
        throw "Runtime directory already exists in staging: $runtimeDir"
    }

    Info 'Extracting WMM runtime into application staging...'

    # El archivo ZIP contiene runtime/; extraer en la raíz del staging.
    # Capturar el diagnóstico nativo sin depender del tratamiento de
    # stderr de PowerShell 5.1 ni modificar la política global de errores.
    $tarStart = [System.Diagnostics.ProcessStartInfo]::new()
    $tarStart.FileName = (Get-Command tar.exe -ErrorAction Stop).Source
    $tarStart.Arguments = '-xf "{0}" -C "{1}"' -f $RuntimeArchive, $Stage
    $tarStart.UseShellExecute = $false
    $tarStart.CreateNoWindow = $true
    $tarStart.RedirectStandardError = $true

    $tarProcess = [System.Diagnostics.Process]::Start($tarStart)

    try {
        $tarError = $tarProcess.StandardError.ReadToEnd().Trim()
        $tarProcess.WaitForExit()

        if ($tarProcess.ExitCode -ne 0) {
            # Informar de la causa probable sin ocultar el error nativo.
            # Otros fallos de extracción no implican necesariamente corrupción.
            $message = "Unable to extract: $([System.IO.Path]::GetFileName($RuntimeArchive))."
            $message += "`r`nThe ZIP may be damaged or incomplete; replace it with a valid copy."
            $message += "`r`nTar exit code: $($tarProcess.ExitCode)"
            if ($tarError) { $message += "`r`n$tarError" }
            throw $message
        }
    }
    finally {
        $tarProcess.Dispose()
    }

    # Comprobar los ejecutables necesarios para Windows.
    $required = @(
        'runtime\bin\python.exe'
        'runtime\bin\pythonw.exe'
        'runtime\bin\gdbus.exe'
    )

    foreach ($relative in $required) {
        $path = Join-Path $Stage $relative

        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Missing staged runtime file: $relative"
        }
    }

    Ok 'WMM runtime staging prepared.'
}

# ----------------------------------------------------------
# FUNCIÓN: Preparar settings_core.ini de Windows
# Las rutas corresponden a la instalación definitiva,
# nunca al staging temporal.
# ----------------------------------------------------------
function Write-WmmSettingsCore {
    param([string]$DataStage)

    $iniPath = Join-Path $DataStage 'settings_core.ini'

    $lines = @(
        '# WMM Platform Configuration'
        'platform=win32'
        'desktop=windows'
        'wmm_id=wmm@maki'
        'app_domain=WMM Manager'
        "data_base=$env:APPDATA"
        "config_base=$env:APPDATA"
        "cache_base=$env:LOCALAPPDATA"
        "app_dir=$InstallDir"
        "app_config=$AppConfig"
        "data_dir=$DataDir"
        "cache_dir=$CacheDir"
        "locale_dir=$(Join-Path $AppConfig 'locale')"
    )

    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllLines($iniPath, $lines, $utf8)

    # Comprobar que se ha generado el archivo completo.
    if (-not (Test-Path -LiteralPath $iniPath -PathType Leaf)) {
        throw 'Could not generate settings_core.ini.'
    }

    if ((Get-Content -LiteralPath $iniPath -Encoding UTF8).Count -ne 13) {
        throw 'Incomplete settings_core.ini.'
    }

    Ok 'Windows platform configuration prepared.'
}

# ----------------------------------------------------------
# FUNCIÓN: Crear el paquete local de recuperación
# Reproduce el contenido y estructura de prepare_installer_payload()
# de Linux, utilizando el Python del runtime Windows preparado.
# ----------------------------------------------------------
function New-WmmRepairArchive {
    param(
        [string]$Stage,
        [string]$Destination
    )

    $python = Join-Path $Stage 'runtime\bin\python.exe'
    $projectDir = Join-Path $ScriptDir 'wmm'

    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw "Staged Python runtime not found: $python"
    }

    if (-not (Test-Path -LiteralPath $projectDir -PathType Container)) {
        throw "WMM source directory not found: $projectDir"
    }

    $readme = Join-Path $ScriptDir 'README.md'
    $changelog = Join-Path $ScriptDir 'CHANGELOG.md'
    $license = Join-Path $ScriptDir 'LICENSE'
    $installer = Get-WmmInstallerSource

    Info 'Preparing WMM repair package...'

    # Mismo algoritmo de empaquetado que el instalador Linux.
    # Se conservan las fuentes originales y la topología del paquete.
    $zipCode = @'
import os
import sys
import zipfile

repair_zip, version, readme, changelog, license_file, installer, project_dir, runtime_zip = sys.argv[1:]
archive_root = f"WMM-v{version}"

with zipfile.ZipFile(
    repair_zip,
    "w",
    compression=zipfile.ZIP_DEFLATED,
    compresslevel=9
) as archive:

    root_files = (
        (readme, "README.md"),
        (changelog, "CHANGELOG.md"),
        (license_file, "LICENSE"),
        (installer, "wmm-install.ps1"),
    )

    for source, name in root_files:
        archive.write(source, f"{archive_root}/{name}")

    # El runtime ya está comprimido: conservarlo sin recomprimir.
    archive.write(
        runtime_zip,
        f"{archive_root}/wmm-runtime.zip",
        compress_type=zipfile.ZIP_STORED
    )

    project_parent = os.path.dirname(project_dir)

    for current_root, dirs, files in os.walk(project_dir):
        dirs[:] = [name for name in dirs if name != "__pycache__"]

        for name in files:
            if name.endswith(".pyc") or name == "wmm-repair.zip":
                continue

            source = os.path.join(current_root, name)
            relative = os.path.relpath(source, project_parent)
            relative = relative.replace(os.sep, "/")

            archive.write(source, f"{archive_root}/{relative}")

# Verificar la estructura esencial del archivo generado.
required = {
    f"{archive_root}/README.md",
    f"{archive_root}/CHANGELOG.md",
    f"{archive_root}/LICENSE",
    f"{archive_root}/wmm-install.ps1",
    f"{archive_root}/wmm-runtime.zip",
    f"{archive_root}/wmm/python/main.py",
}

with zipfile.ZipFile(repair_zip, "r") as archive:
    if not required.issubset(archive.namelist()):
        raise RuntimeError("Incomplete WMM repair package.")
'@

    $zipCode | & $python -B - `
        $Destination $WmmVersion $readme $changelog $license `
        $installer $projectDir $RuntimeArchive

    if ($LASTEXITCODE -ne 0) {
        throw "Repair package creation failed (exit code: $LASTEXITCODE)"
    }

    $archive = Get-Item -LiteralPath $Destination -ErrorAction Stop

    if ($archive.Length -le 0) {
        throw 'Generated WMM repair package is empty.'
    }

    Ok 'WMM repair package prepared.'
}

# ----------------------------------------------------------
# FUNCIÓN: Incorporar las herramientas de mantenimiento
# Conserva la ubicación utilizada por el instalador Linux.
# Los scripts se preparan dentro del staging, no en el sistema.
# ----------------------------------------------------------
function Add-WmmInstallerPayload {
    param([string]$Stage)

    $installerDir = Join-Path $Stage 'wmm_platform\shell\installer'
    New-Item -ItemType Directory -Path $installerDir -Force | Out-Null

    # Fuente única: la edición que está ejecutando el mantenimiento.
    # Puede hallarse temporalmente fuera de la instalación.
    Copy-Item -LiteralPath (Get-WmmInstallerSource) `
        -Destination (Join-Path $installerDir 'wmm-install.ps1') -Force -ErrorAction Stop

    # Retirar el desinstalador separado de las distribuciones antiguas.
    $legacy = Join-Path $installerDir 'wmm-uninstall.ps1'
    if (Test-Path -LiteralPath $legacy -PathType Leaf) {
        Remove-Item -LiteralPath $legacy -Force -ErrorAction Stop
    }

    [IO.File]::WriteAllText(
        (Join-Path $Stage '.wmm-open-code'), $WmmVersion,
        (New-Object System.Text.UTF8Encoding($false)))

    New-WmmRepairArchive -Stage $Stage `
        -Destination (Join-Path $installerDir 'wmm-repair.zip')

    Ok 'Unified Windows maintenance script staged.'
}

# ----------------------------------------------------------
# FUNCIÓN: Validar la instalación preparada
# Comprueba las relaciones entre aplicación, runtime y datos
# antes de activar los árboles definitivos.
# ----------------------------------------------------------
function Test-WmmPreparedStaging {
    param(
        [string]$AppStage,
        [string]$DataStage
    )

    $required = @(
        (Join-Path $AppStage 'python\main.py')
        (Join-Path $AppStage 'frontends\windows\windows-frontend.py')
        (Join-Path $AppStage 'runtime\bin\python.exe')
        (Join-Path $AppStage 'runtime\bin\pythonw.exe')
        (Join-Path $AppStage 'runtime\bin\gdbus.exe')
        (Join-Path $AppStage 'wmm_platform\shell\installer\wmm-install.ps1')
        (Join-Path $AppStage 'wmm_platform\shell\installer\wmm-repair.zip')
        (Join-Path $DataStage 'settings_core.ini')
        (Join-Path $DataStage 'data\about.json')
    )

    foreach ($file in $required) {
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
            throw "Incomplete staging: $file"
        }
    }

    # La configuración debe apuntar al destino definitivo.
    $iniPath = Join-Path $DataStage 'settings_core.ini'
    $ini = Get-Content -LiteralPath $iniPath -Encoding UTF8

    $expected = @(
        'platform=win32'
        'desktop=windows'
        "app_dir=$InstallDir"
        "app_config=$AppConfig"
        "data_dir=$DataDir"
        "cache_dir=$CacheDir"
    )

    foreach ($entry in $expected) {
        if ($ini -notcontains $entry) {
            throw "Invalid staged settings_core.ini: $entry"
        }
    }

    # Los metadatos instalados deben corresponder al paquete.
    $aboutPath = Join-Path $DataStage 'data\about.json'
    $about = Get-Content -LiteralPath $aboutPath -Raw -Encoding UTF8 |
        ConvertFrom-Json

    if ($about.version -ne $WmmVersion) {
        throw "Staged version does not match package version."
    }

    Ok 'Prepared WMM installation verified.'
}

# ----------------------------------------------------------
# FUNCIÓN: Restaurar los árboles anteriores
# Retira los árboles nuevos y recupera los originales.
# Un respaldo que no pueda restaurarse nunca se descarta.
# ----------------------------------------------------------
function Restore-WmmStaging {
    param([psobject]$State)

    $errors = @()

    $trees = @(
        @{
            Target = $AppConfig
            Backup = $State.OldConfig
            Activated = $State.NewConfig
        }
        @{
            Target = $InstallDir
            Backup = $State.OldApp
            Activated = $State.NewApp
        }
    )

    foreach ($tree in $trees) {
        try {
            if ($tree.Activated -and (Test-Path -LiteralPath $tree.Target)) {
                Remove-Item -LiteralPath $tree.Target -Recurse -Force -ErrorAction Stop
            }

            if ($tree.Backup -and (Test-Path -LiteralPath $tree.Backup)) {
                if (Test-Path -LiteralPath $tree.Target) {
                    throw "Destination is occupied: $($tree.Target)"
                }

                Move-Item -LiteralPath $tree.Backup `
                    -Destination $tree.Target -ErrorAction Stop
            }
        }
        catch {
            $errors += "$($tree.Target): $($_.Exception.Message)"
        }
    }

    if ($errors.Count -gt 0) {
        throw "CRITICAL: WMM restoration incomplete. $($errors -join '; ')"
    }

    Ok 'Previous WMM trees restored.'
}

# ----------------------------------------------------------
# FUNCIÓN: Activar los árboles preparados
# Aparta los existentes sin destruirlos y activa ambos staging.
# Equivalente a activate_staging() de Linux.
# ----------------------------------------------------------
function Invoke-WmmStagingSwap {
    param(
        [string]$AppStage,
        [string]$DataStage
    )

    foreach ($path in @($AppStage, $DataStage)) {
        if (-not (Test-Path -LiteralPath $path -PathType Container)) {
            throw "Staging directory not found: $path"
        }
    }

    $state = [pscustomobject]@{
        OldApp    = $null
        OldConfig = $null
        NewApp    = $false
        NewConfig = $false
    }

    try {
        # CORE: conservar el anterior hasta el commit.
        if (Test-Path -LiteralPath $InstallDir) {
            $backup = Join-Path $InstallBase (
                '.wmm-install-old.' + [guid]::NewGuid().ToString('N')
            )

            Move-Item -LiteralPath $InstallDir -Destination $backup -ErrorAction Stop
            $state.OldApp = $backup
        }

        Move-Item -LiteralPath $AppStage -Destination $InstallDir -ErrorAction Stop
        $state.NewApp = $true

        # DATOS: Windows aloja settings_core.ini junto a data/.
        # Respaldamos por ello APP_CONFIG completo.
        if (Test-Path -LiteralPath $AppConfig) {
            $backup = Join-Path $env:APPDATA (
                '.wmm-data-old.' + [guid]::NewGuid().ToString('N')
            )

            Move-Item -LiteralPath $AppConfig -Destination $backup -ErrorAction Stop
            $state.OldConfig = $backup
        }

        Move-Item -LiteralPath $DataStage -Destination $AppConfig -ErrorAction Stop
        $state.NewConfig = $true

        Ok 'WMM application and data trees activated.'
        return $state
    }
    catch {
        $failure = $_

        try {
            Restore-WmmStaging -State $state
        }
        catch {
            throw "Activation failed: $($failure.Exception.Message). $($_.Exception.Message)"
        }

        throw $failure
    }
}

# ----------------------------------------------------------
# FUNCIÓN: Confirmar los árboles activados
# Destruye los respaldos únicamente después de completar
# la integración y el relanzado del frontend.
# ----------------------------------------------------------
function Complete-WmmStagingSwap {
    param([psobject]$State)

    foreach ($backup in @($State.OldApp, $State.OldConfig)) {
        if ($backup -and (Test-Path -LiteralPath $backup)) {
            try {
                Remove-Item -LiteralPath $backup -Recurse -Force -ErrorAction Stop
            }
            catch {
                Write-Host "[!!] Could not remove old WMM backup: $backup" -ForegroundColor Yellow
            }
        }
    }

    Ok 'WMM installation committed.'
}

# ----------------------------------------------------------
# FUNCIÓN: Identificar procesos del runtime instalado
# Sólo considera ejecutables pertenecientes al runtime privado
# de WMM. Nunca identifica procesos mediante su nombre aislado.
# ----------------------------------------------------------
function Get-WmmReplacementProcesses {
    $runtimeBin = Join-Path $InstallDir 'runtime\bin'

    Get-CimInstance Win32_Process -Filter (
        "Name = 'python.exe' OR Name = 'pythonw.exe' OR Name = 'gdbus.exe'"
    ) -ErrorAction Stop | Where-Object {
        $executable = $_.ExecutablePath

        if (-not $executable) {
            return $false
        }

        $directory = [IO.Path]::GetDirectoryName($executable)

        [string]::Equals(
            $directory,
            $runtimeBin,
            [StringComparison]::OrdinalIgnoreCase
        )
    }
}

# ----------------------------------------------------------
# FUNCIÓN: Solicitar el cierre ordenado de WMM
# Buscar el HWND oculto mediante EnumWindows, verificando
# su clase y PID antes de solicitar el cierre del frontend.
# El engine conserva su shutdown como vía de respaldo.
# ----------------------------------------------------------
function Request-WmmGracefulShutdown {
    param([object[]]$Processes)

    if ($Processes.Count -eq 0) { return }

    # FRONTEND
    # FindWindow falló en las pruebas anteriores.
    # EnumWindows permite inspeccionar también ventanas ocultas.
    try {
        if (-not ('WmmTrayCloser' -as [type])) {
            Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Runtime.InteropServices;

public static class WmmTrayCloser {
    private delegate bool WindowCallback(IntPtr hwnd, IntPtr data);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool EnumWindows(
        WindowCallback callback, IntPtr data);

    [DllImport("user32.dll", EntryPoint = "GetClassNameW",
        CharSet = CharSet.Unicode)]
    private static extern int GetClassName(
        IntPtr hwnd, StringBuilder name, int capacity);

    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(
        IntPtr hwnd, out uint processId);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool PostMessageW(
        IntPtr hwnd, uint message, IntPtr wparam, IntPtr lparam);

    public static string RequestClose(int[] allowedPids) {
        string result = "not-found";

        WindowCallback callback = delegate(IntPtr hwnd, IntPtr data) {
            StringBuilder name = new StringBuilder(128);

            if (GetClassName(hwnd, name, name.Capacity) == 0 ||
                name.ToString() != "WMMWindowsFrontendWindow")
                return true;

            uint ownerPid = 0;
            GetWindowThreadProcessId(hwnd, out ownerPid);

            bool allowed = false;
            foreach (int pid in allowedPids) {
                if (pid == (int)ownerPid) {
                    allowed = true;
                    break;
                }
            }

            if (!allowed) {
                result = "pid-mismatch:" + ownerPid;
                return true;
            }

            if (PostMessageW(hwnd, 0x0010,
                    IntPtr.Zero, IntPtr.Zero)) {
                result = "sent:" + ownerPid;
            }
            else {
                result = "post-failed:" + ownerPid;
            }

            return false;
        };

        EnumWindows(callback, IntPtr.Zero);
        return result;
    }
}
'@
        }

        $pids = [int[]]@($Processes | ForEach-Object {
            [int]$_.ProcessId
        })

        $result = [WmmTrayCloser]::RequestClose($pids)

        if ($result.StartsWith('sent:')) {
            Info "WMM frontend: WM_CLOSE sent to PID $($result.Substring(5))."
            return
        }

        if ($result -eq 'not-found') {
            Warn 'WMM frontend: native HWND not found by enumeration.'
        }
        elseif ($result.StartsWith('pid-mismatch:')) {
            Warn "WMM frontend: HWND belongs to unexpected PID $($result.Substring(13))."
        }
        else {
            Warn "WMM frontend: WM_CLOSE delivery failed ($result)."
        }
    }
    catch {
        Warn "WMM frontend close request failed: $($_.Exception.Message)"
    }

    # RESPALDO: ENGINE
    # Mantener la solicitud existente cuando el frontend
    # no puede recibir WM_CLOSE.
    Info 'WMM frontend: trying engine shutdown.'

    $python = Join-Path $InstallDir 'runtime\bin\python.exe'
    $sender = Join-Path $InstallDir 'python\send_command.py'

    if ((Test-Path -LiteralPath $python -PathType Leaf) -and
        (Test-Path -LiteralPath $sender -PathType Leaf)) {

        try {
            & $python -B $sender '{\"action\":\"shutdown\"}' | Out-Null
        }
        catch {
            Warn "WMM engine shutdown request failed: $($_.Exception.Message)"
        }
    }
}

# ----------------------------------------------------------
# FUNCIÓN: Detener WMM antes del reemplazo
# Solicita primero el shutdown mediante el canal propio del engine.
# Termina los procesos supervivientes del runtime instalado y espera
# su salida. No permite activar staging mientras sigan ejecutándose.
# ----------------------------------------------------------
function Stop-WmmForReplacement {
    $processes = @(Get-WmmReplacementProcesses)

    if ($processes.Count -eq 0) {
        Ok 'WMM is not running.'
        return
    }

    Info 'Stopping current WMM...'

	# Solicitar primero el cierre del frontend. Su WM_CLOSE
	# también coordina el shutdown del engine y limpia el tray.
	Request-WmmGracefulShutdown -Processes $processes

	# Dar tiempo al cierre ordenado antes de intervenir.
	# Wait-Process bloquea; no hay polling ni temporizadores.
	$remaining = @(Get-WmmReplacementProcesses)

	if ($remaining.Count -gt 0) {
		$pids = @($remaining | ForEach-Object { [int]$_.ProcessId })
		Wait-Process -Id $pids -Timeout 8 -ErrorAction SilentlyContinue
	}

    # SUPERVIVIENTES
    # Equivalente funcional a terminate_pids_and_wait() de Linux.
    # Windows requiere terminación explícita cuando el proceso
    # no dispone de un mecanismo de cierre coordinado accesible.
	$remaining = @(Get-WmmReplacementProcesses)

	if ($remaining.Count -gt 0) {
		$pids = @($remaining | ForEach-Object { [int]$_.ProcessId })

		# La espera ordenada terminó con procesos supervivientes.
		Warn "WMM graceful shutdown incomplete. Forcing PID(s): $($pids -join ', ')."

		Stop-Process -Id $pids -Force -ErrorAction SilentlyContinue
		Wait-Process -Id $pids -Timeout 2 -ErrorAction SilentlyContinue
	}
	else {
		# Todos los procesos salieron sin terminación forzada.
		Ok 'WMM processes exited without forced termination.'
	}

    # BARRERA FINAL
    # Comprobación única antes de sustituir los árboles instalados.
    $remaining = @(Get-WmmReplacementProcesses)

    if ($remaining.Count -gt 0) {
        $remainingPids = ($remaining | ForEach-Object {
            $_.ProcessId
        }) -join ', '

        throw "WMM could not be stopped safely. Remaining PID(s): $remainingPids"
    }

    Ok 'WMM stopped.'
}

# ----------------------------------------------------------
# FUNCIÓN: Respaldar integraciones Windows existentes
# Protege las claves del Registro y los accesos de WMM que
# serán regenerados. Su ausencia también debe poder restaurarse.
# El inicio automático permanece intacto durante el reemplazo.
# ----------------------------------------------------------
function Backup-WmmExternalResources {
    $backupDir = Join-Path $env:TEMP (
        '.wmm-external-old.' + [guid]::NewGuid().ToString('N')
    )

    $registryKeys = @(
        'Software\Classes\SystemFileAssociations\image\shell\WMM.Manager'
        'Software\Classes\WMM.Manager.ImageCommands'
        'Software\Classes\DesktopBackground\shell\WMM.Manager'
        'Software\Classes\WMM.Manager.DesktopCommands'
        'Software\Classes\AppUserModelId\WMM.Manager'
        'Software\Microsoft\Windows\CurrentVersion\Uninstall\WMM-OpenCode'
    )

    New-Item -ItemType Directory -Path $backupDir -ErrorAction Stop | Out-Null

    $state = [pscustomobject]@{
        Directory = $backupDir
        Registry  = @()
    }

    try {
        Info 'Backing up WMM Windows integrations...'

        for ($i = 0; $i -lt $registryKeys.Count; $i++) {
            $relative = $registryKeys[$i]
            $psPath = "HKCU:\$relative"
            $regPath = "HKCU\$relative"
            $present = Test-Path -LiteralPath $psPath
            $backupFile = Join-Path $backupDir "registry-$i.reg"

            if ($present) {
                & reg.exe export $regPath $backupFile /y | Out-Null

                if ($LASTEXITCODE -ne 0) {
                    throw "Could not back up registry key: $regPath"
                }
            }

            $state.Registry += [pscustomobject]@{
                Path    = $psPath
                Present = $present
                File    = $backupFile
            }
        }

        # Los accesos se regeneran, no se heredan de la versión anterior.
        # Sus copias sólo existen para recuperar un reemplazo fallido.
        $menuDir = Join-Path $env:APPDATA `
            'Microsoft\Windows\Start Menu\Programs\WMM Manager'

        $desktopLink = Join-Path (
            [Environment]::GetFolderPath('DesktopDirectory')) 'WMM Manager.lnk'

        if (Test-Path -LiteralPath $menuDir -PathType Container) {
            Copy-Item -LiteralPath $menuDir `
                -Destination (Join-Path $backupDir 'start-menu') `
                -Recurse -ErrorAction Stop
        }

        if (Test-Path -LiteralPath $desktopLink -PathType Leaf) {
            Copy-Item -LiteralPath $desktopLink `
                -Destination (Join-Path $backupDir 'desktop.lnk') `
                -ErrorAction Stop
        }

        Ok 'Existing Windows integrations backed up.'
        return $state
    }
    catch {
        Remove-Item -LiteralPath $backupDir -Recurse -Force `
            -ErrorAction SilentlyContinue
        throw
    }
}

# ----------------------------------------------------------
# FUNCIÓN: Restaurar integraciones Windows
# Recupera el Registro y los accesos anteriores, incluida
# su ausencia original. No altera el inicio automático.
# Conserva el respaldo si la restauración resulta incompleta.
# ----------------------------------------------------------
function Restore-WmmExternalResources {
    param([psobject]$State)

    if ($null -eq $State) {
        return
    }

    Info 'Restoring previous WMM Windows integrations...'
    $errors = @()

    foreach ($entry in $State.Registry) {
        try {
            # Las claves indicadas son espacios propios de WMM.
            # Eliminar primero evita conservar subclaves de la versión nueva.
            if (Test-Path -LiteralPath $entry.Path) {
                Remove-Item -LiteralPath $entry.Path -Recurse -Force `
                    -ErrorAction Stop
            }

            if ($entry.Present) {
                if (-not (Test-Path -LiteralPath $entry.File -PathType Leaf)) {
                    throw "Missing registry backup: $($entry.File)"
                }

                & reg.exe import $entry.File | Out-Null

                if ($LASTEXITCODE -ne 0) {
                    throw "Could not restore registry key: $($entry.Path)"
                }

                if (-not (Test-Path -LiteralPath $entry.Path)) {
                    throw "Restored registry key is missing: $($entry.Path)"
                }
            }
        }
        catch {
            $errors += "$($entry.Path): $($_.Exception.Message)"
        }
    }

    # Recuperar los accesos anteriores o retirar los creados
    # por el reemplazo si originalmente no existían.
    $menuDir = Join-Path $env:APPDATA `
        'Microsoft\Windows\Start Menu\Programs\WMM Manager'

    $desktopLink = Join-Path (
        [Environment]::GetFolderPath('DesktopDirectory')) 'WMM Manager.lnk'

    $shortcuts = @(
        @{
            Target = $menuDir
            Backup = Join-Path $State.Directory 'start-menu'
        }
        @{
            Target = $desktopLink
            Backup = Join-Path $State.Directory 'desktop.lnk'
        }
    )

    foreach ($entry in $shortcuts) {
        try {
            if (Test-Path -LiteralPath $entry.Target) {
                Remove-Item -LiteralPath $entry.Target `
                    -Recurse -Force -ErrorAction Stop
            }

            if (Test-Path -LiteralPath $entry.Backup) {
                New-Item -ItemType Directory `
                    -Path (Split-Path $entry.Target -Parent) `
                    -Force -ErrorAction Stop | Out-Null

                Copy-Item -LiteralPath $entry.Backup `
                    -Destination $entry.Target `
                    -Recurse -ErrorAction Stop
            }
        }
        catch {
            $errors += "$($entry.Target): $($_.Exception.Message)"
        }
    }

    if ($errors.Count -gt 0) {
        throw "Windows integration restoration incomplete. " +
            "Backup preserved at: $($State.Directory). " +
            ($errors -join '; ')
    }

    Ok 'Previous Windows integrations restored.'
}

# ----------------------------------------------------------
# FUNCIÓN: Descartar respaldo externo tras commit
# Nunca se invoca si la restauración ha fallado.
# ----------------------------------------------------------
function Remove-WmmExternalBackup {
    param([psobject]$State)

    if ($null -eq $State) {
        return
    }

    if (Test-Path -LiteralPath $State.Directory) {
        try {
            Remove-Item -LiteralPath $State.Directory -Recurse -Force `
                -ErrorAction Stop
        }
        catch {
            Write-Host "[!!] Could not remove external backup: $($State.Directory)" `
                -ForegroundColor Yellow
        }
    }
}

# ----------------------------------------------------------
# FUNCIÓN: Crear acceso directo Windows
# ----------------------------------------------------------
function New-WmmShortcut {
    param(
        [string]$Path,
        [string]$Executable,
        [string]$Arguments,
        [string]$Icon
    )

    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($Path)

    $shortcut.TargetPath = $Executable
    $shortcut.Arguments = $Arguments
    $shortcut.WorkingDirectory = $InstallDir
    $shortcut.IconLocation = $Icon
    $shortcut.Save()
}


# ----------------------------------------------------------
# FUNCIÓN: Construir los accesos del menú Inicio
# Instalar y reemplazar comparten exactamente las mismas
# entradas. El directorio lo prepara cada operación.
# ----------------------------------------------------------
function New-WmmStartMenuShortcuts {
    $menuDir = Join-Path $env:APPDATA `
        'Microsoft\Windows\Start Menu\Programs\WMM Manager'

    $pythonw = Join-Path $InstallDir 'runtime\bin\pythonw.exe'
    $appIcon = (Join-Path $InstallDir 'WMM-icon.ico') + ',0'
    $shellIcons = Join-Path $env:SystemRoot 'System32\shell32.dll'

	$entries = @(
		@{ Name='WMM Manager'; File='frontends\windows\windows-frontend.py'; Extra=''; Icon=$appIcon }
		@{ Name=(Get-WmmText 'Settings'); File='python\panel.py'; Extra=''; Icon="$shellIcons,314" }
		@{ Name=(Get-WmmText 'Help'); File='python\docs_viewer.py'; Extra='help/HELP.md'; Icon="$shellIcons,23" }
		@{ Name=(Get-WmmText 'Changelog'); File='python\docs_viewer.py'; Extra='CHANGELOG.md'; Icon="$shellIcons,269" }
		@{ Name=(Get-WmmText 'DebugViewer'); File='python\debug_log_viewer.py'; Extra=''; Icon="$shellIcons,171" }
		@{ Name=(Get-WmmText 'About'); File='python\about.py'; Extra=''; Icon="$shellIcons,160" }
	)

    foreach ($entry in $entries) {
        $scriptPath = Join-Path $InstallDir $entry.File
        $arguments = '"' + $scriptPath + '"'

        if ($entry.Extra) {
            $arguments += ' "' + $entry.Extra + '"'
        }

        New-WmmShortcut `
            -Path (Join-Path $menuDir "$($entry.Name).lnk") `
            -Executable $pythonw -Arguments $arguments -Icon $entry.Icon
    }

    # El menú Inicio abre siempre el gestor completo.
    # La operación se selecciona desde su interfaz.
    $powershell = Join-Path $PSHOME 'powershell.exe'
    $managerScript = Join-Path $InstallDir `
        'wmm_platform\shell\installer\wmm-install.ps1'

    $arguments = '-NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File "' +
        $managerScript + '"'

    New-WmmShortcut `
        -Path (Join-Path $menuDir ((Get-WmmText 'SetupInstaller') + '.lnk')) `
        -Executable $powershell -Arguments $arguments `
        -Icon "$shellIcons,314"
}

# ----------------------------------------------------------
# FUNCIÓN: Registrar la desinstalación de Windows
# Aplicaciones instaladas conserva la operación directa.
# El menú Inicio utiliza el gestor, sin parámetros.
# La clave debe haber sido creada por la operación llamante.
# ----------------------------------------------------------
function Set-WmmUninstallRegistration {
    $uninstallKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\WMM-OpenCode'
    $powershell = Join-Path $PSHOME 'powershell.exe'
    $managerScript = Join-Path $InstallDir `
        'wmm_platform\shell\installer\wmm-install.ps1'

    $arguments = '-NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File "' +
        $managerScript + '" -Operation uninstall'

    $properties = @{
        DisplayName = 'WMM Manager (Open Code)'
        DisplayVersion = $WmmVersion
        Publisher = 'makimanson'
        InstallLocation = $InstallDir
        DisplayIcon = (Join-Path $InstallDir 'WMM-icon.ico')
        UninstallString = ('"{0}" {1}' -f $powershell, $arguments)
    }

    foreach ($name in $properties.Keys) {
        New-ItemProperty -Path $uninstallKey -Name $name `
            -PropertyType String -Value $properties[$name] `
            -Force -ErrorAction Stop | Out-Null
    }

    foreach ($name in @('NoModify', 'NoRepair')) {
        New-ItemProperty -Path $uninstallKey -Name $name `
            -PropertyType DWord -Value 1 `
            -Force -ErrorAction Stop | Out-Null
    }
}

# ----------------------------------------------------------
# FUNCIÓN: Activar instalación preparada
# Instala código y datos, registra accesos Windows y mantiene
# rollback si falla antes del commit.
# ----------------------------------------------------------
function Install-WmmPrepared {
    param(
        [string]$AppStage,
        [string]$DataStage
    )

    $menuDir = Join-Path $env:APPDATA `
        'Microsoft\Windows\Start Menu\Programs\WMM Manager'

    $desktopLink = Join-Path (
        [Environment]::GetFolderPath('DesktopDirectory')) 'WMM Manager.lnk'

    $runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
    $uninstallKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\WMM-OpenCode'

    # Instalación limpia: no ocupar recursos existentes.
    foreach ($path in @($InstallDir, $AppConfig, $menuDir, $uninstallKey)) {
        if (Test-Path -LiteralPath $path) {
            throw "Installation resource already exists: $path"
        }
    }

    $existingRun = Get-ItemProperty -Path $runKey `
        -Name 'WMM Manager' -ErrorAction SilentlyContinue

    if ($null -ne $existingRun) {
        throw 'WMM autostart registration already exists.'
    }

    # Consola: mantener las preferencias tradicionales. GUI: el gestor
    # pregunta ANTES de lanzar el proceso que sustituye archivos.
    if ($DesktopOption -eq 'Ask') {
        $desktopAnswer = Read-Host 'Create desktop shortcut? [Y/n]'
        $createDesktop = $desktopAnswer -notmatch '^(n|no)$'
    }
    else { $createDesktop = $DesktopOption -eq 'Yes' }

    if ($createDesktop -and (Test-Path -LiteralPath $desktopLink)) {
        throw "Desktop shortcut already exists: $desktopLink"
    }

    if ($AutostartOption -eq 'Ask') {
        $autostartAnswer = Read-Host 'Start WMM with Windows? [y/N]'
        $enableAutostart = $autostartAnswer -match '^(y|yes|s|si|sí)$'
    }
    else { $enableAutostart = $AutostartOption -eq 'Yes' }

    $swapState = $null
    $menuCreated = $false
    $desktopCreated = $false
    $autostartCreated = $false
    $uninstallCreated = $false

    $cacheRoot = Split-Path $CacheDir -Parent
    $cacheAlreadyExists = Test-Path -LiteralPath $cacheRoot

    try {
        # ACTIVACIÓN
        # Misma infraestructura para instalación limpia y reemplazo.
        # Invoke-WmmStagingSwap restaura internamente si falla el propio swap.
        $swapState = Invoke-WmmStagingSwap -AppStage $AppStage -DataStage $DataStage
        Set-WmmProgress 3  # Árboles activados; todavía falta integración y commit.

        $pythonw = Join-Path $InstallDir 'runtime\bin\pythonw.exe'
        $frontend = Join-Path $InstallDir 'frontends\windows\windows-frontend.py'
        $appIcon = (Join-Path $InstallDir 'WMM-icon.ico') + ',0'

        # La instalación limpia crea un menú inexistente.
        # Registrar su creación para permitir rollback.
        New-Item -ItemType Directory -Path $menuDir -ErrorAction Stop | Out-Null
        $menuCreated = $true

        New-WmmStartMenuShortcuts

        if ($createDesktop) {
            New-WmmShortcut -Path $desktopLink `
                -Executable $pythonw -Arguments ('"' + $frontend + '"') `
                -Icon $appIcon
            $desktopCreated = $true
        }

        # Registro de inicio automático: única autoridad HKCU.
        if ($enableAutostart) {
            $command = '"' + $pythonw + '" "' + $frontend + '"'

            New-ItemProperty -Path $runKey -Name 'WMM Manager' `
                -PropertyType String -Value $command | Out-Null

            $autostartCreated = $true
        }

        # La instalación limpia crea la identidad de desinstalación.
        # Si falla, el rollback debe retirar la clave creada.
        New-Item -Path $uninstallKey -Force -ErrorAction Stop | Out-Null
        $uninstallCreated = $true

        Set-WmmUninstallRegistration

        # Caché inicial; el motor administra después su contenido.
        New-Item -ItemType Directory `
            -Path (Join-Path $CacheDir 'thumbnails') -Force | Out-Null

        # COMMIT
        # Confirmar únicamente después de completar la integración.
        Complete-WmmStagingSwap -State $swapState
        Set-WmmProgress 4  # Commit de instalación confirmado.

        Ok 'WMM Open Code installed successfully.'
        Info "Installation: $InstallDir"
        Info "User data: $AppConfig"
        Info "Start Menu: $menuDir"
    }
    catch {
        $failure = $_
        Write-Host '[!!] Installation failed. Rolling back...' -ForegroundColor Yellow

        if ($autostartCreated) {
            Remove-ItemProperty -Path $runKey -Name 'WMM Manager' `
                -ErrorAction SilentlyContinue
        }

        if ($uninstallCreated) {
            Remove-Item -LiteralPath $uninstallKey -Recurse -Force `
                -ErrorAction SilentlyContinue
        }

        if ($desktopCreated) {
            Remove-Item -LiteralPath $desktopLink -Force `
                -ErrorAction SilentlyContinue
        }

        if ($menuCreated) {
            Remove-Item -LiteralPath $menuDir -Recurse -Force `
                -ErrorAction SilentlyContinue
        }

        if (-not $cacheAlreadyExists -and
                (Test-Path -LiteralPath $cacheRoot)) {
            Remove-Item -LiteralPath $cacheRoot -Recurse -Force `
                -ErrorAction SilentlyContinue
        }

        # ROLLBACK
        # Sólo corresponde aquí si el swap terminó correctamente.
        # Si falló durante su ejecución, ya intentó restaurarse.
        if ($null -ne $swapState) {
            try {
                Restore-WmmStaging -State $swapState
            }
            catch {
                throw "Installation failed: $($failure.Exception.Message). " +
                    "Rollback failed: $($_.Exception.Message)"
            }
        }

        throw $failure
    }
}

# ----------------------------------------------------------
# FUNCIÓN: Ejecutar Upgrade / Reinstall / Downgrade
# Prepara ambos árboles, detiene WMM y sustituye la instalación.
# La integración se reconstruye sin alterar las preferencias
# de escritorio y autostart. El commit exige relanzado solicitado.
# ----------------------------------------------------------
function Invoke-WmmReplacement {
    $stage = $null
    $dataStage = $null
    $swapState = $null
    $externalState = $null
    $stopped = $false
    $launchAttempted = $false

    $menuDir = Join-Path $env:APPDATA `
        'Microsoft\Windows\Start Menu\Programs\WMM Manager'

    $desktopLink = Join-Path (
        [Environment]::GetFolderPath('DesktopDirectory')) 'WMM Manager.lnk'

    $uninstallKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\WMM-OpenCode'

    try {
        # PRESERVAR PREFERENCIAS
        # Un acceso existente debe pertenecer a WMM. Su presencia
        # determina si se reconstruye; no se pregunta de nuevo.
        $createDesktop = Test-Path -LiteralPath $desktopLink -PathType Leaf

        if ($createDesktop) {
            $shell = New-Object -ComObject WScript.Shell
            $shortcut = $shell.CreateShortcut($desktopLink)
            $expected = Join-Path $InstallDir 'runtime\bin\pythonw.exe'

            if (-not [string]::Equals($shortcut.TargetPath,
                    $expected, [StringComparison]::OrdinalIgnoreCase)) {
                throw "Desktop shortcut does not belong to WMM: $desktopLink"
            }
        }

        # PREPARACIÓN
        # Los diez archivos preservados prevalecen sobre los datos
        # distribuidos. La caché permanece fuera de ambos árboles.
        Test-WmmSource

        $stage = New-WmmAppStaging
        $dataStage = New-WmmDataStaging -Preserve

        Write-WmmSettingsCore -DataStage $dataStage
        Add-WmmRuntimeToStaging -Stage $stage
        Add-WmmInstallerPayload -Stage $stage

        Test-WmmPreparedStaging -AppStage $stage -DataStage $dataStage
        Set-WmmProgress 2  # Staging de reemplazo validado.

        # CIERRE
        # Ningún árbol vivo se modifica antes de cerrar el runtime.
        # Una parada parcialmente ejecutada también requiere
        # recuperar el runtime anterior si aborta el reemplazo.
        $stopped = $true
        Stop-WmmForReplacement
        Set-WmmProgress 3  # Runtime anterior detenido y verificado.

        # RESPALDO Y ACTIVACIÓN
        $externalState = Backup-WmmExternalResources
        $swapState = Invoke-WmmStagingSwap `
            -AppStage $stage -DataStage $dataStage
        Set-WmmProgress 4  # Árboles sustituidos; falta integración y commit.

        $pythonw = Join-Path $InstallDir 'runtime\bin\pythonw.exe'
        $frontend = Join-Path $InstallDir 'frontends\windows\windows-frontend.py'
        $appIcon = (Join-Path $InstallDir 'WMM-icon.ico') + ',0'

        # El reemplazo reconstruye el menú completo.
        # El respaldo anterior ya está protegido por externalState.
        if (Test-Path -LiteralPath $menuDir) {
            Remove-Item -LiteralPath $menuDir -Recurse -Force -ErrorAction Stop
        }

        New-Item -ItemType Directory -Path $menuDir -ErrorAction Stop | Out-Null
        New-WmmStartMenuShortcuts

        if ($createDesktop) {
            New-WmmShortcut -Path $desktopLink `
                -Executable $pythonw -Arguments ('"' + $frontend + '"') `
                -Icon $appIcon
        }

        New-Item -Path $uninstallKey -Force -ErrorAction Stop | Out-Null
        Set-WmmUninstallRegistration

        # RELANZADO
        # El frontend Windows inicia el engine cuando es necesario.
        # La preparación interna y las traducciones siguen siendo
        # responsabilidad del frontend y del engine, no del instalador.
        $launchAttempted = $true
        Start-Process -FilePath $pythonw `
            -ArgumentList ('"' + $frontend + '"') `
            -WorkingDirectory $InstallDir -ErrorAction Stop

        # COMMIT
        # Start-Process confirma la solicitud de lanzamiento, no
        # la disponibilidad funcional posterior del frontend.
        Complete-WmmStagingSwap -State $swapState
        Remove-WmmExternalBackup -State $externalState
        Set-WmmProgress 5  # Commit completado y respaldo externo retirado.

        Ok "WMM $WmmVersion replacement completed."
        Info "Installation: $InstallDir"
        Info "User data: $AppConfig"
    }
    catch {
        $failure = $_
        $rollbackErrors = @()

        if ($stopped) {
            Write-Host '[!!] Replacement failed. Rolling back...' `
                -ForegroundColor Yellow

            # Un frontend nuevo que haya comenzado a arrancar no
            # puede permanecer activo durante la restauración.
            if ($launchAttempted) {
                try {
                    Stop-WmmForReplacement
                }
                catch {
                    $rollbackErrors += "Shutdown: $($_.Exception.Message)"
                }
            }

            if ($rollbackErrors.Count -eq 0 -and $null -ne $swapState) {
                try {
                    Restore-WmmStaging -State $swapState
                }
                catch {
                    $rollbackErrors += "Trees: $($_.Exception.Message)"
                }
            }

            if ($rollbackErrors.Count -eq 0 -and $null -ne $externalState) {
                try {
                    Restore-WmmExternalResources -State $externalState
                }
                catch {
                    $rollbackErrors += "Integration: $($_.Exception.Message)"
                }
            }

            if ($rollbackErrors.Count -eq 0) {
                try {
                    # Recuperar el runtime anterior tras el rollback.
                    $oldPythonw = Join-Path $InstallDir 'runtime\bin\pythonw.exe'
                    $oldFrontend = Join-Path $InstallDir `
                        'frontends\windows\windows-frontend.py'

                    Start-Process -FilePath $oldPythonw `
                        -ArgumentList ('"' + $oldFrontend + '"') `
                        -WorkingDirectory $InstallDir -ErrorAction Stop
                }
                catch {
                    $rollbackErrors += "Relaunch: $($_.Exception.Message)"
                }
            }

            if ($rollbackErrors.Count -eq 0) {
                Remove-WmmExternalBackup -State $externalState
                Ok 'Previous WMM installation restored.'
            }
        }

        if ($rollbackErrors.Count -gt 0) {
            throw "Replacement failed: $($failure.Exception.Message). " +
                "CRITICAL rollback error: $($rollbackErrors -join '; '). " +
                "Recovery backups have been preserved."
        }

        throw $failure
    }
    finally {
        # Retirar exclusivamente staging que siga siendo temporal.
        foreach ($path in @($stage, $dataStage)) {
            if ($path -and (Test-Path -LiteralPath $path)) {
                Remove-Item -LiteralPath $path -Recurse -Force `
                    -ErrorAction SilentlyContinue
            }
        }
    }
}


# ==========================================================
# Desinstalación: funciones originales integradas
# ==========================================================
function Test-WmmInstallation {
    # Como en uninstall.sh, inventariar recursos existentes.
    # Una instalación parcial o dañada debe poder retirarse.
    $menuDir = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\WMM Manager'
    $uninstallKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\WMM-OpenCode'

    foreach ($path in @($InstallDir, $AppConfig, $CacheDir, $menuDir, $uninstallKey)) {
        if (Test-Path -LiteralPath $path) {
            return $true
        }
    }

    # Integración externa: inicio automático perteneciente a WMM.
    $runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
    $runEntry = Get-ItemProperty -Path $runKey -Name 'WMM Manager' -ErrorAction SilentlyContinue

    if ($null -ne $runEntry) {
        $command = $runEntry.'WMM Manager'

        if ($command -and $command.IndexOf(
                $InstallDir, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
            return $true
        }
    }

    # Integración externa: acceso directo creado para esta instalación.
    $desktopLink = Join-Path ([Environment]::GetFolderPath('DesktopDirectory')) 'WMM Manager.lnk'

    if (Test-Path -LiteralPath $desktopLink -PathType Leaf) {
        try {
            $shell = New-Object -ComObject WScript.Shell
            $shortcut = $shell.CreateShortcut($desktopLink)
            $expected = Join-Path $InstallDir 'runtime\bin\pythonw.exe'

            if ([string]::Equals($shortcut.TargetPath, $expected,
                    [StringComparison]::OrdinalIgnoreCase)) {
                return $true
            }
        }
        catch {
            Write-Host "[!!] Could not inspect desktop shortcut: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }

    return $false
}

# ----------------------------------------------------------
# FUNCIÓN: Identificar procesos de esta instalación WMM
# Nunca cerrar Python de otras instalaciones.
# ----------------------------------------------------------
function Get-WmmProcesses {
    $runtimeBin = Join-Path $InstallDir 'runtime\bin'

    Get-CimInstance Win32_Process | Where-Object {
        $exe = $_.ExecutablePath

        if (-not $exe) { return $false }

        $directory = [IO.Path]::GetDirectoryName($exe)
        if (-not [string]::Equals($directory, $runtimeBin,
                [StringComparison]::OrdinalIgnoreCase)) {
            return $false
        }

        if ($_.Name -ieq 'gdbus.exe') { return $true }

        return ($_.Name -in @('python.exe', 'pythonw.exe') -and
                $_.CommandLine -and
                $_.CommandLine.IndexOf($InstallDir,
                    [StringComparison]::OrdinalIgnoreCase) -ge 0)
    }
}

# ----------------------------------------------------------
# FUNCIÓN: Cerrar los procesos propios de WMM
# Solicitar WM_CLOSE al frontend y esperar su salida.
# Sólo forzar procesos previamente identificados por ruta.
# ----------------------------------------------------------
function Stop-WmmProcesses {
    $processes = @(Get-WmmProcesses)
    if ($processes.Count -eq 0) { return }

    Info 'Closing WMM processes...'

	# Mismo cierre ordenado que Upgrade / Reinstall / Downgrade.
	Request-WmmGracefulShutdown -Processes $processes

	Wait-Process -Id @($processes.ProcessId) -Timeout 8 -ErrorAction SilentlyContinue

    # Barrera final: recapturar la identidad antes de forzar.
    # Como en uninstall.sh, una anomalía no impide la retirada.
    foreach ($process in @(Get-WmmProcesses)) {
        try {
            Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
        }
        catch {
            Warn "Could not stop WMM PID $($process.ProcessId): $($_.Exception.Message)"
            $script:SessionRestartRecommended = $true
        }
    }

    if (@(Get-WmmProcesses).Count -gt 0) {
        Warn 'Some WMM processes remain active. Continuing uninstallation.'
        $script:SessionRestartRecommended = $true
    }
    else {
        Ok 'WMM processes closed.'
    }
}

# ----------------------------------------------------------
# FUNCIÓN: Confirmación interactiva
# ----------------------------------------------------------
function Confirm-Wmm([string]$Question) {
    $answer = Read-Host "$Question [y/N]"
    return $answer -match '^(y|yes|s|si|sí)$'
}

# ----------------------------------------------------------
# FUNCIÓN: Retirar un recurso WMM existente
# La ausencia de un recurso no constituye un error.
# Un fallo aislado se registra y no bloquea los restantes.
# ----------------------------------------------------------
function Remove-WmmResource {
    param(
        [string]$Path,
        [switch]$Recursive
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    try {
        Remove-Item -LiteralPath $Path -Recurse:$Recursive -Force -ErrorAction Stop
        Ok "Removed: $Path"
    }
    catch {
        Warn "Could not remove: $Path ($($_.Exception.Message))"
        $script:UninstallIncomplete = $true
    }
}


function Invoke-WmmUninstall {
    # ----------------------------------------------------------
    # Entrada principal
    # ----------------------------------------------------------
    if (-not (Test-WmmInstallation)) {
        Info 'No WMM Open Code resources were found.'
        return
    }

    Info "Installation: $InstallDir"


    $script:SessionRestartRecommended = $false
    $script:UninstallIncomplete = $false

    $menuDir = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\WMM Manager'
    $desktopLink = Join-Path ([Environment]::GetFolderPath('DesktopDirectory')) 'WMM Manager.lnk'
    $runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
    $uninstallKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\WMM-OpenCode'

    # ----------------------------------------------------------
    # 1. DETENER WMM
    # ----------------------------------------------------------
    try {
        Stop-WmmProcesses
    }
    catch {
        Warn "WMM shutdown encountered an error: $($_.Exception.Message)"
        $script:SessionRestartRecommended = $true
    }
    Set-WmmProgress 1  # Cierre de procesos intentado; advertencias se conservan.

    # ----------------------------------------------------------
    # 2. RETIRAR INTEGRACIONES WINDOWS
    # ----------------------------------------------------------
    Info 'Removing WMM Windows integrations...'

    # Inicio automático: retirar únicamente el valor de esta instalación.
    try {
        $runEntry = Get-ItemProperty -Path $runKey -Name 'WMM Manager' -ErrorAction SilentlyContinue
        $runValue = if ($null -ne $runEntry) { $runEntry.'WMM Manager' } else { $null }

        if ($runValue -and $runValue.IndexOf(
                $InstallDir, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
            Remove-ItemProperty -Path $runKey -Name 'WMM Manager' -ErrorAction Stop
        }
    }
    catch {
        Write-Host "[!!] Could not remove WMM autostart: $($_.Exception.Message)" -ForegroundColor Yellow
        $script:UninstallIncomplete = $true
    }

    # Claves propias de los menús WMM en Explorer.
    $explorerKeys = @(
        'HKCU:\Software\Classes\SystemFileAssociations\image\shell\WMM.Manager'
        'HKCU:\Software\Classes\WMM.Manager.ImageCommands'
        'HKCU:\Software\Classes\DesktopBackground\shell\WMM.Manager'
        'HKCU:\Software\Classes\WMM.Manager.DesktopCommands'
        'HKCU:\Software\Classes\AppUserModelId\WMM.Manager'
    )

    foreach ($key in $explorerKeys) {
        Remove-WmmResource -Path $key -Recursive
    }

    # Menú Inicio y acceso directo de escritorio.
    Remove-WmmResource -Path $menuDir -Recursive

    if (Test-Path -LiteralPath $desktopLink -PathType Leaf) {
        try {
            $shell = New-Object -ComObject WScript.Shell
            $shortcut = $shell.CreateShortcut($desktopLink)
            $expected = Join-Path $InstallDir 'runtime\bin\pythonw.exe'

            if ([string]::Equals($shortcut.TargetPath, $expected,
                    [StringComparison]::OrdinalIgnoreCase)) {
                Remove-WmmResource -Path $desktopLink
            }
        }
        catch {
            Write-Host "[!!] Could not inspect WMM desktop shortcut: $($_.Exception.Message)" -ForegroundColor Yellow
            $script:UninstallIncomplete = $true
        }
    }

    Remove-WmmResource -Path $uninstallKey -Recursive
    Set-WmmProgress 2  # Retirada de integración recorrida; verificación pendiente.

    # ----------------------------------------------------------
    # 3. RETIRAR INSTALACIÓN Y DATOS
    # ----------------------------------------------------------
    Info 'Removing WMM installation...'

    # No mantener como directorio actual el árbol que se elimina.
    Set-Location $env:TEMP

    # Desinstalación completa, equivalente a cleanup_installation_and_shared_data()
    # de Linux. Los recursos ausentes se omiten sin interrumpir la retirada.
    Remove-WmmResource -Path $InstallDir -Recursive
    Remove-WmmResource -Path $AppConfig -Recursive

    $cacheRoot = Split-Path $CacheDir -Parent
    Remove-WmmResource -Path $cacheRoot -Recursive
    Set-WmmProgress 3  # Árboles retirados o intentados; verificación pendiente.

    # ----------------------------------------------------------
    # 4. FINALIZACIÓN
    # Verificar los residuos reales antes de informar del éxito.
    # La ausencia previa de un recurso también es válida.
    # ----------------------------------------------------------
    Info 'Verifying WMM cleanup...'

    # REGISTRO: Explorer, desinstalación e inicio automático propio.
    $registryClean = -not (Test-Path -LiteralPath $uninstallKey)

    foreach ($key in $explorerKeys) {
        if (Test-Path -LiteralPath $key) {
            $registryClean = $false
        }
    }

    try {
        $runEntry = Get-ItemProperty -Path $runKey -Name 'WMM Manager' -ErrorAction SilentlyContinue

        if ($null -ne $runEntry) {
            $runValue = $runEntry.'WMM Manager'
            if ($runValue -and $runValue.IndexOf(
                    $InstallDir, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
                $registryClean = $false
            }
        }
    }
    catch {
        $registryClean = $false
    }

    # ACCESOS DIRECTOS: menú Inicio y acceso de escritorio propio.
    $shortcutsClean = -not (Test-Path -LiteralPath $menuDir)

    if (Test-Path -LiteralPath $desktopLink -PathType Leaf) {
        try {
            $shell = New-Object -ComObject WScript.Shell
            $shortcut = $shell.CreateShortcut($desktopLink)
            $expected = Join-Path $InstallDir 'runtime\bin\pythonw.exe'

            if ([string]::Equals($shortcut.TargetPath, $expected,
                    [StringComparison]::OrdinalIgnoreCase)) {
                $shortcutsClean = $false
            }
        }
        catch {
            $shortcutsClean = $false
        }
    }

    # DATOS Y CACHÉ: comprobar los directorios completos de WMM.
    $cacheClean = -not (Test-Path -LiteralPath $cacheRoot)
    $dataClean = -not (Test-Path -LiteralPath $AppConfig)

    $checks = @(
        @{ Name = 'Registry keys';          Passed = $registryClean }
        @{ Name = 'Shortcuts / Start Menu'; Passed = $shortcutsClean }
        @{ Name = 'Cache';                  Passed = $cacheClean }
        @{ Name = 'Data files';             Passed = $dataClean }
    )

    foreach ($check in $checks) {
        if ($check.Passed) {
            Ok "$($check.Name): clean"
        }
        else {
            Warn "$($check.Name): cleanup incomplete."
            $script:UninstallIncomplete = $true
        }
    }

    if ($script:UninstallIncomplete) {
        Warn 'WMM uninstallation incomplete: some resources could not be removed.'
    }
    else {
        Ok 'WMM Open Code uninstalled.'
    }

    Info 'Personal wallpaper files and Windows wallpaper settings were not touched.'

    if ($script:SessionRestartRecommended) {
        Warn 'WMM process shutdown could not be fully confirmed.'
        Info 'Log out and log back in to clear any remaining session processes.'
    }

    if ($script:UninstallIncomplete) {
        throw 'WMM uninstallation incomplete.'
    }
    Set-WmmProgress 4  # Verificación final superada.

}


# ==========================================================
# Paquetes de mantenimiento: preparación fuera del runtime WMM
# ==========================================================
function Expand-WmmZip([string]$ZipPath, [string]$Destination) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($ZipPath)
    try {
        $base = [IO.Path]::GetFullPath($Destination).TrimEnd('\') + '\'
        foreach ($entry in $zip.Entries) {
            $relative = $entry.FullName.Replace('/', '\')
            $full = [IO.Path]::GetFullPath((Join-Path $Destination $relative))
            if (-not $full.StartsWith($base, [StringComparison]::OrdinalIgnoreCase) -and
                -not [string]::Equals($full, $base.TrimEnd('\'), [StringComparison]::OrdinalIgnoreCase)) {
                throw "Unsafe archive member: $($entry.FullName)"
            }
        }
    }
    finally { $zip.Dispose() }

    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    [IO.Compression.ZipFile]::ExtractToDirectory($ZipPath, $Destination)
}

function Get-WmmArchiveRoot([string]$Directory) {
    $roots = @(Get-ChildItem -LiteralPath $Directory -Directory)
    if ($roots.Count -ne 1) { throw 'Unexpected WMM package root.' }
    return $roots[0].FullName
}

# ----------------------------------------------------------
# DISPONIBILIDAD DEL PAQUETE DE REPARACIÓN INSTALADO
# Solo determina si existe el archivo necesario para ofrecer
# Reinstalar. Su integridad se valida al ejecutar la operación.
# ----------------------------------------------------------
function Test-WmmRepairArchive {
    $archive = Join-Path $InstallDir 'wmm_platform\shell\installer\wmm-repair.zip'
    return (Test-Path -LiteralPath $archive -PathType Leaf)
}

function Get-WmmRepairPackage([string]$Destination) {
    $archive = Join-Path $InstallDir 'wmm_platform\shell\installer\wmm-repair.zip'
    if (-not (Test-Path -LiteralPath $archive -PathType Leaf)) {
        throw "WMM repair archive was not found: $archive"
    }

    # Este ZIP pertenece a la instalación existente, no al árbol fuente.
    # Igual que con el runtime, un fallo al abrir o extraer el archivo
    # interrumpe el mantenimiento y conserva el diagnóstico original.
    Info "Extracting installed WMM repair package: $archive"

    try {
        Expand-WmmZip -ZipPath $archive -Destination $Destination
    }
    catch {
        $message = "Unable to extract: $([System.IO.Path]::GetFileName($archive))."
        $message += "`r`nThe ZIP may be damaged or incomplete; replace it with a valid copy."
        $message += "`r`n$($_.Exception.Message)"
        throw $message
    }

    return Get-WmmArchiveRoot $Destination
}

function Copy-WmmRuntimeFromRepair([string]$Destination) {
    # Las releases de código fuente de GitHub no incluyen necesariamente
    # el runtime Windows. Reutilizamos el empaquetado de la instalación
    # actual, sin modificar el código de WMM que procede del tag nuevo.
    $archive = Join-Path $InstallDir 'wmm_platform\shell\installer\wmm-repair.zip'
    if (-not (Test-Path -LiteralPath $archive -PathType Leaf)) {
        throw 'Windows runtime unavailable: the installed repair archive is missing.'
    }

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($archive)
    try {
        $matches = @($zip.Entries | Where-Object {
            $_.FullName -match '^[^/]+/wmm-runtime\.zip$'
        })
        if ($matches.Count -ne 1) {
            throw 'The repair archive does not contain a unique Windows runtime.'
        }
        [IO.Compression.ZipFileExtensions]::ExtractToFile($matches[0], $Destination)
    }
    finally { $zip.Dispose() }
}

function Get-WmmUpgradePackage([string]$Destination, [string]$TargetVersion = '') {
    # La GUI fija su versión seleccionada; el acceso directo tradicional
    # sigue consultando latest cuando no se especifica una versión.
    if ($TargetVersion) {
        if ($TargetVersion -notmatch '^\d+\.\d+\.\d+$') {
            throw "Invalid requested GitHub version: $TargetVersion"
        }
        $latest = $TargetVersion
        $tag = "v$latest"
    }
    else {
        Info 'Checking the latest stable GitHub release...'
        [Net.ServicePointManager]::SecurityProtocol =
            [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

        $headers = @{ Accept = 'application/vnd.github+json'; 'User-Agent' = 'WMM-Install-Manager' }
        $release = Invoke-RestMethod -Uri 'https://api.github.com/repos/makimanson/wmm/releases/latest' `
            -Headers $headers -TimeoutSec 30 -ErrorAction Stop
        $tag = [string]$release.tag_name
        if ($tag -notmatch '^v(?<version>\d+\.\d+\.\d+)$') {
            throw "Unexpected GitHub release tag: $tag"
        }
        $latest = $Matches['version']
    }

    # La comprobación también protege las invocaciones directas
    # y las versiones fijadas previamente por la interfaz.
    if ([version]$latest -lt $script:WmmMinGitHubVersion) {
        throw "GitHub release $latest is unsupported on Windows (minimum: $($script:WmmMinGitHubVersion))."
    }

    $script:ExpectedUpgradeVersion = $latest

    $hasInstallation = Test-Path -LiteralPath $InstallDir -PathType Container
    $installed = if ($hasInstallation) { Get-WmmInstalledVersion } else { $null }
    if ($installed -and [version]$latest -le [version]$installed) {
        throw "No newer release available (installed: $installed; latest: $latest)."
    }

    # TLS también en la descarga cuando la consulta a latest se omitió.
    [Net.ServicePointManager]::SecurityProtocol =
        [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    $archive = Join-Path $Destination 'release.zip'
    $extracted = Join-Path $Destination 'source'
    $url = "https://github.com/makimanson/wmm/archive/refs/tags/$tag.zip"

    Info "Downloading WMM $latest..."
    Invoke-WebRequest -Uri $url -Headers @{ 'User-Agent' = 'WMM-Install-Manager' } `
        -UseBasicParsing -TimeoutSec 120 -OutFile $archive -ErrorAction Stop
    Info 'Extracting stable release...'
    Expand-WmmZip -ZipPath $archive -Destination $extracted

    $root = Get-WmmArchiveRoot $extracted
    if ([IO.Path]::GetFileName($root) -ne "wmm-$latest") {
        throw "Unexpected GitHub source root: $root"
    }

    # La descarga del tag puede contener solamente código fuente.
    # Con instalación previa se conserva el runtime validado existente;
    # en instalación limpia se aporta desde la distribución local.
    $runtime = Join-Path $root 'wmm-runtime.zip'
    if (-not (Test-Path -LiteralPath $runtime -PathType Leaf)) {
        if ($hasInstallation) {
            Info 'Reusing the Windows runtime packaged with the installed WMM...'
            Copy-WmmRuntimeFromRepair $runtime
        }
        elseif ($PackageRoot -and (Get-WmmLocalPackageVersion $PackageRoot)) {
            Info 'Reusing the Windows runtime from the local distribution...'
            Copy-Item -LiteralPath (Join-Path $PackageRoot 'wmm-runtime.zip') `
                -Destination $runtime -ErrorAction Stop
        }
        else {
            throw 'GitHub source package has no Windows runtime and no valid local distribution can provide it.'
        }
    }
    return $root
}

# ==========================================================
# Mantenimiento de aplicación, con los métodos validados
# ==========================================================
function Invoke-WmmInstall {
    if (Test-Path -LiteralPath $InstallDir -PathType Container) {
        throw 'Install requires an empty WMM installation target.'
    }
    Test-WmmSource
    Set-WmmProgress 1  # Paquete fuente validado.
    $stage = $null
    $dataStage = $null
    try {
        $stage = New-WmmAppStaging
        $dataStage = New-WmmDataStaging
        Write-WmmSettingsCore -DataStage $dataStage
        Add-WmmRuntimeToStaging -Stage $stage
        Add-WmmInstallerPayload -Stage $stage
        Test-WmmPreparedStaging -AppStage $stage -DataStage $dataStage
        Set-WmmProgress 2  # Staging comprobado antes de activar la instalación.
        Install-WmmPrepared -AppStage $stage -DataStage $dataStage
        $stage = $null
        $dataStage = $null
    }
    finally {
        foreach ($path in @($stage, $dataStage)) {
            if ($path -and (Test-Path -LiteralPath $path)) {
                Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
    }
}

# ----------------------------------------------------------
# RECUPERACIÓN DEL RUNTIME WINDOWS
# La release de referencia del runtime es independiente de la
# versión WMM. Solo completa el paquete fuente autorizado.
# No utiliza recursos de la instalación existente.
# ----------------------------------------------------------
function Install-WmmRuntimeFromGitHub([string]$Root) {
    if ($script:WmmFromInstalled -or
            -not (Test-WmmRuntimeRecovery (Get-WmmLocalPackageInfo $Root))) {
        throw 'Runtime recovery requires a source package missing only wmm-runtime.zip.'
    }

    $tag = $script:WmmRuntimeReleaseTag
    $headers = @{
        Accept = 'application/vnd.github+json'
        'User-Agent' = 'WMM-Install-Manager'
    }
    $api = "https://api.github.com/repos/makimanson/wmm/releases/tags/$tag"

    [Net.ServicePointManager]::SecurityProtocol =
        [Net.ServicePointManager]::SecurityProtocol -bor
        [Net.SecurityProtocolType]::Tls12

    Info "Checking Windows runtime asset in GitHub release $tag..."

    try {
        $release = Invoke-RestMethod -Uri $api -Headers $headers `
            -TimeoutSec 30 -ErrorAction Stop
    }
    catch {
        throw "Unable to consult runtime release $tag (it may not be published yet): $($_.Exception.Message)"
    }

    if ([string]$release.tag_name -ne $tag) {
        throw "Unexpected runtime release identity: $($release.tag_name)"
    }

    $assets = @($release.assets | Where-Object {
        $_.name -ceq 'wmm-runtime.zip'
    })

    if ($assets.Count -ne 1) {
        throw "Runtime asset wmm-runtime.zip is not published in GitHub release $tag."
    }

    $asset = $assets[0]
    $url = [string]$asset.browser_download_url
    $expectedUrl =
        "https://github.com/makimanson/wmm/releases/download/$tag/wmm-runtime.zip"

    if ($url -cne $expectedUrl) {
        throw "Unexpected runtime asset URL: $url"
    }

    # La descarga debe coincidir con la huella publicada.
    # La mera existencia de un ZIP no acredita su integridad.
    $digest = [string]$asset.digest
    if ($digest -match '^sha256:(?<hash>[0-9a-fA-F]{64})$') {
        $expectedHash = $Matches['hash']
    }
    else {
        throw 'Runtime asset lacks a verifiable SHA-256 digest.'
    }

    if ([long]$asset.size -le 0) {
        throw 'Invalid runtime asset size.'
    }

    $tempFile = Join-Path $TempRoot (
        'wmm-runtime-' + [guid]::NewGuid().ToString('N') + '.zip'
    )
    $incoming = Join-Path $Root (
        '.wmm-runtime-' + [guid]::NewGuid().ToString('N') + '.part'
    )
    $target = Join-Path $Root 'wmm-runtime.zip'

    try {
        Info 'Downloading Windows runtime...'

        Invoke-WebRequest -Uri $url `
            -Headers @{ 'User-Agent'='WMM-Install-Manager' } `
            -UseBasicParsing -TimeoutSec 600 `
            -OutFile $tempFile -ErrorAction Stop

        Info 'Verifying Windows runtime size, SHA-256 and ZIP contents...'

        $downloadedSize =
            (Get-Item -LiteralPath $tempFile -ErrorAction Stop).Length

        if ($downloadedSize -ne [long]$asset.size) {
            throw "Runtime size mismatch: expected $($asset.size), got $downloadedSize."
        }

        $downloadedHash =
            (Get-FileHash -LiteralPath $tempFile -Algorithm SHA256).Hash

        if ($downloadedHash -ine $expectedHash) {
            throw 'Runtime SHA-256 does not match the published asset digest.'
        }

        # La estructura del ZIP debe corresponder al runtime
        # que Add-WmmRuntimeToStaging() espera encontrar.
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $zip = [IO.Compression.ZipFile]::OpenRead($tempFile)

        try {
            $required = @(
                'runtime/bin/python.exe'
                'runtime/bin/pythonw.exe'
                'runtime/bin/gdbus.exe'
            )

            $found = @{}
            $seen = [Collections.Generic.HashSet[string]]::new(
                [StringComparer]::OrdinalIgnoreCase
            )

            foreach ($entry in $zip.Entries) {
                $name = $entry.FullName.Replace('\', '/')

                if ($name -ne 'runtime/' -and
                        -not $name.StartsWith(
                            'runtime/', [StringComparison]::OrdinalIgnoreCase)) {
                    throw "Unexpected runtime ZIP entry: $name"
                }

                if ($name -match '(^|/)\.\.?(/|$)' -or
                        $name.Contains(':') -or -not $seen.Add($name)) {
                    throw "Unsafe or duplicate runtime ZIP entry: $name"
                }

                # Impedir enlaces simbólicos en el staging Windows.
                if ((($entry.ExternalAttributes -shr 16) -band 0xF000) -eq 0xA000) {
                    throw "Runtime ZIP contains symbolic link: $name"
                }

                if ($required -contains $name -and $entry.Length -gt 0) {
                    $found[$name] = $true
                }
            }

            foreach ($name in $required) {
                if (-not $found.ContainsKey($name)) {
                    throw "Missing runtime ZIP entry: $name"
                }
            }
        }
        finally {
            $zip.Dispose()
        }

        # Publicación en la fuente solo después de validar.
        # El archivo temporal del mismo volumen permite renombrar
        # sin dejar un wmm-runtime.zip parcialmente copiado.
        Copy-Item -LiteralPath $tempFile -Destination $incoming -ErrorAction Stop

        if (Test-Path -LiteralPath $target) {
            throw 'Runtime archive appeared during download; not overwriting.'
        }

        [IO.File]::Move($incoming, $target)

        Ok 'Windows runtime verified and added to the local source package.'
    }
    finally {
        foreach ($path in @($tempFile, $incoming)) {
            Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
        }
    }
}

# ----------------------------------------------------------
# Preparación compartida para Instalar y Reinstalar desde fuente.
# La autorización llega del diálogo previo; no se altera el
# paquete ni la instalación si falta cualquier otro requisito.
# ----------------------------------------------------------
function Prepare-WmmSourceRuntime([string]$Root, [string]$Operation) {
    if (-not $RecoverRuntime) { return }

    if ($script:WmmFromInstalled -or $Source -ne 'Local' -or
            $Operation -notin @('install', 'repair')) {
        throw 'Runtime recovery is only permitted for local install or reinstall.'
    }

    # No descargar si la operación de destino ya es inviable.
    $installed = Test-Path -LiteralPath $InstallDir -PathType Container
    if ($Operation -eq 'install' -and $installed) {
        throw 'Install requires an empty WMM installation target.'
    }
    if ($Operation -eq 'repair' -and -not $installed) {
        throw 'Reinstall requires an existing WMM installation.'
    }

    $info = Get-WmmLocalPackageInfo $Root
    if (-not (Test-WmmRuntimeRecovery $info)) {
        throw 'Only a missing runtime can be recovered automatically.'
    }
    if ($ExpectedVersion -and $info.Version -ne $ExpectedVersion) {
        throw "Package version mismatch: selected=$ExpectedVersion; package=$($info.Version)."
    }

    if ($Operation -eq 'repair') {
        $currentVersion = Get-WmmInstalledVersion
        if ($currentVersion -and
                [version]$info.Version -ne [version]$currentVersion) {
            throw "Reinstall package $($info.Version) differs from installed WMM $currentVersion."
        }
    }

    Install-WmmRuntimeFromGitHub $Root
    Set-WmmProgress 1  # Runtime descargado y verificado, primer hito.
    $script:WmmProgressOffset = 1
}

function Invoke-WmmSelectedOperation([string]$Selected) {
    # AUTORIDAD DE PROCEDENCIA
    # Desde fuentes solo se instala código y runtime de la distribución.
    # Auto equivale a Local; Repair y GitHub no pueden sustituir ese origen.
    # Uninstall conserva su procedimiento independiente.
    if (-not $script:WmmFromInstalled -and $Selected -ne 'uninstall') {
        if ($Source -in @('Repair', 'GitHub')) {
            throw "Source installer cannot use maintenance source: $Source"
        }

        if ($Source -eq 'Auto') {
            $script:Source = 'Local'
        }
    }

    switch ($Selected) {
        'install' {
            if ($Source -eq 'GitHub') {
                $root = Get-WmmUpgradePackage -Destination (Join-Path $TempRoot 'github-install') `
                    -TargetVersion $ExpectedVersion
            }
            elseif ($Source -in @('Auto', 'Local')) {
                if (-not $PackageRoot) { throw 'Install requires a source package root.' }
                $root = $PackageRoot
            }
            else { throw "Unsupported installation source: $Source" }

            Prepare-WmmSourceRuntime $root 'install'
            Set-WmmPackage $root
            if ($ExpectedVersion -and $WmmVersion -ne $ExpectedVersion) {
                throw "Package version mismatch: selected=$ExpectedVersion; package=$WmmVersion."
            }
            if ($Source -eq 'GitHub' -and $WmmVersion -ne $script:ExpectedUpgradeVersion) {
                throw "GitHub release metadata mismatch: $script:ExpectedUpgradeVersion / $WmmVersion."
            }
            Invoke-WmmInstall
        }
        'upgrade' {
            if (-not (Test-Path -LiteralPath $InstallDir -PathType Container)) {
                throw 'Upgrade requires an existing WMM installation.'
            }
            $installed = Get-WmmInstalledVersion
            if (-not $installed) { throw 'Upgrade requires a known installed version.' }

            if ($Source -eq 'Local') {
                $root = $PackageRoot
            }
            elseif ($Source -in @('Auto', 'GitHub')) {
                $root = Get-WmmUpgradePackage -Destination (Join-Path $TempRoot 'upgrade') `
                    -TargetVersion $ExpectedVersion
            }
            else { throw "Unsupported upgrade source: $Source" }

            Set-WmmPackage $root
            if ($ExpectedVersion -and $WmmVersion -ne $ExpectedVersion) {
                throw "Package version mismatch: selected=$ExpectedVersion; package=$WmmVersion."
            }
            if ($Source -ne 'Local' -and $WmmVersion -ne $script:ExpectedUpgradeVersion) {
                throw "GitHub release metadata mismatch: $script:ExpectedUpgradeVersion / $WmmVersion."
            }
            if ([version]$WmmVersion -le [version]$installed) {
                throw "Upgrade requires a newer version than $installed (package: $WmmVersion)."
            }
            Set-WmmProgress 1  # Fuente y nueva versión verificadas.
            Invoke-WmmReplacement
        }
        'downgrade' {
            if ($Source -notin @('Auto', 'Local')) {
                throw 'Downgrade is only available from a local distribution.'
            }
            if (-not (Test-Path -LiteralPath $InstallDir -PathType Container)) {
                throw 'Downgrade requires an existing WMM installation.'
            }
            $installed = Get-WmmInstalledVersion
            if (-not $installed) { throw 'Downgrade requires a known installed version.' }
            Set-WmmPackage $PackageRoot
            if ($ExpectedVersion -and $WmmVersion -ne $ExpectedVersion) {
                throw "Package version mismatch: selected=$ExpectedVersion; package=$WmmVersion."
            }
            if ([version]$WmmVersion -ge [version]$installed) {
                throw "Downgrade requires an older version than $installed (package: $WmmVersion)."
            }
            Set-WmmProgress 1  # Paquete local anterior verificado.
            Invoke-WmmReplacement
        }
        'repair' {
            if (-not (Test-Path -LiteralPath $InstallDir -PathType Container)) {
                throw 'Reinstall requires an existing WMM installation.'
            }
            if ($Source -eq 'Local') {
                Info "Reinstall source: local distribution ($PackageRoot)"
                $root = $PackageRoot
            }
            elseif ($Source -in @('Auto', 'Repair')) {
                $root = Get-WmmRepairPackage (Join-Path $TempRoot 'repair')
            }
            else { throw "Unsupported reinstall source: $Source" }

            Prepare-WmmSourceRuntime $root 'repair'
            Set-WmmPackage $root
            $installed = Get-WmmInstalledVersion
            if ($ExpectedVersion -and $WmmVersion -ne $ExpectedVersion) {
                throw "Package version mismatch: selected=$ExpectedVersion; package=$WmmVersion."
            }
            if ($installed -and [version]$installed -ne [version]$WmmVersion) {
                throw "Reinstall package $WmmVersion differs from installed WMM $installed."
            }
            Set-WmmProgress 1  # Paquete compatible preparado.
            Invoke-WmmReplacement
        }
        'uninstall' { Invoke-WmmUninstall }
        default { throw "Unsupported WMM maintenance operation: $Selected" }
    }
}

# ----------------------------------------------------------
# FUNCIÓN: Aplicar el tema de Windows a los formularios WMM
# Respeta AppsUseLightTheme y adapta los controles existentes.
# No modifica la geometría ni los estilos tipográficos.
# ----------------------------------------------------------
function Set-WmmFormTheme {
    param([System.Windows.Forms.Form]$Form)

    # TEMA DEL USUARIO
    # Si Windows no publica la preferencia, conservar el modo claro.
    $dark = $false

    try {
        $theme = Get-ItemProperty -Path `
            'HKCU:\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize' `
            -Name AppsUseLightTheme -ErrorAction Stop

        $dark = ([int]$theme.AppsUseLightTheme -eq 0)
    }
    catch {
        # Preferencia no disponible: utilizar colores claros.
    }

    # PALETA
    if ($dark) {
        $background = [System.Drawing.Color]::FromArgb(32, 32, 32)
        $foreground = [System.Drawing.Color]::FromArgb(240, 240, 240)
        $buttonColor = [System.Drawing.Color]::FromArgb(57, 57, 57)
        $fieldColor = [System.Drawing.Color]::FromArgb(40, 40, 40)
        $borderColor = [System.Drawing.Color]::FromArgb(85, 85, 85)
    }
    else {
        $background = [System.Drawing.SystemColors]::Control
        $foreground = [System.Drawing.SystemColors]::ControlText
        $buttonColor = [System.Drawing.SystemColors]::Control
        $fieldColor = [System.Drawing.SystemColors]::Window
        $borderColor = [System.Drawing.SystemColors]::ControlDark
    }

    # CONTROLES
    # Recorrer también los controles anidados en Panel.
    $pending = [System.Collections.Generic.Queue[System.Windows.Forms.Control]]::new()
    $pending.Enqueue($Form)

    while ($pending.Count -gt 0) {
        $control = $pending.Dequeue()

        $control.BackColor = $background
        $control.ForeColor = $foreground

        if ($control -is [System.Windows.Forms.Button]) {
            if ($dark) {
                # Los estilos visuales clásicos no pintan los botones
                # con nuestra paleta oscura.
                $control.FlatStyle = 'Flat'
                $control.UseVisualStyleBackColor = $false
                $control.BackColor = $buttonColor
                $control.FlatAppearance.BorderColor = $borderColor
            }
            else {
                $control.FlatStyle = 'Standard'
                $control.BackColor = $buttonColor
                $control.UseVisualStyleBackColor = $true
            }
        }
        elseif ($control -is [System.Windows.Forms.TextBoxBase]) {
            $control.BackColor = $fieldColor
        }
        elseif ($control -is [System.Windows.Forms.Label] -and
                $control.Height -le 3) {
            # Separadores horizontales: evitar bordes claros en modo oscuro.
            $control.BorderStyle = if ($dark) { 'None' } else { 'Fixed3D' }
            $control.BackColor = if ($dark) { $borderColor } else { $background }
        }

        foreach ($child in $control.Controls) {
            $pending.Enqueue($child)
        }
    }

    # BARRA DE TÍTULO
    # DWM permite que el marco nativo respete el modo oscuro.
    # Una anomalía cosmética aquí no debe impedir el mantenimiento.
    try {
        if ([Environment]::OSVersion.Version.Build -ge 22000) {
            if (-not ('WmmDwmTheme' -as [type])) {
                Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

public static class WmmDwmTheme {
    [DllImport("dwmapi.dll")]
    public static extern int DwmSetWindowAttribute(
        IntPtr window, int attribute, ref int value, int size);
}
'@
            }

            $enabled = if ($dark) { 1 } else { 0 }

            [void][WmmDwmTheme]::DwmSetWindowAttribute(
                $Form.Handle, 20, [ref]$enabled, 4)
        }
    }
    catch {
        # El formulario sigue siendo operativo sin tema en el marco.
    }
}

# ==========================================================
# Windows Forms: gestor y ventana de mantenimiento
# ==========================================================
function New-WmmManagedForm {
    # Textos seleccionados en el runspace principal.
    param([hashtable]$Texts, [byte[]]$IconBytes)

    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    [System.Windows.Forms.Application]::EnableVisualStyles()

    $form = [System.Windows.Forms.Form]::new()
    $form.Text = $Texts['WindowTitle']
    $form.StartPosition = 'CenterScreen'
    $form.FormBorderStyle = 'FixedDialog'
    $form.MaximizeBox = $false
    $form.MinimizeBox = $false
    $form.ClientSize = [System.Drawing.Size]::new(580, 350)
    $form.Font = [System.Drawing.Font]::new('Segoe UI', 9)

    $heading = [System.Windows.Forms.Label]::new()
    $heading.Text = $Texts['WindowTitle']
    $heading.Font = [System.Drawing.Font]::new('Segoe UI', 14, [System.Drawing.FontStyle]::Bold)
    $heading.Location = [System.Drawing.Point]::new(24, 22)
    $heading.AutoSize = $true
    $form.Controls.Add($heading)

    # IDENTIDAD VISUAL WMM
    # El ICO se mantiene en memoria y se libera al cerrar el formulario.
    $brandStream = $null
    $brandIcon = $null
    $brandBitmap = $null

    if ($IconBytes) {
        try {
            $brandStream = [IO.MemoryStream]::new($IconBytes)
            $brandIcon = [System.Drawing.Icon]::new($brandStream, 48, 48)
            $brandBitmap = $brandIcon.ToBitmap()
        }
        catch {
            if ($null -ne $brandBitmap) { $brandBitmap.Dispose() }
            if ($null -ne $brandIcon) { $brandIcon.Dispose() }
            if ($null -ne $brandStream) { $brandStream.Dispose() }

            $brandStream = $null
            $brandIcon = $null
            $brandBitmap = $null
        }
    }

    if ($null -ne $brandBitmap) {
        # ICONO NATIVO
        $form.Icon = $brandIcon

        # LOGOTIPO DE CABECERA
        $brandLogo = [System.Windows.Forms.PictureBox]::new()
        $brandLogo.Image = $brandBitmap
        $brandLogo.Location = [System.Drawing.Point]::new(24, 19)
        $brandLogo.Size = [System.Drawing.Size]::new(48, 48)
        $brandLogo.SizeMode = 'Zoom'
        $form.Controls.Add($brandLogo)

        # Centrar el título en la zona disponible a la derecha.
        $heading.AutoSize = $false
        $heading.Location = [System.Drawing.Point]::new(82, 22)
        $heading.Size = [System.Drawing.Size]::new(474, 42)
        $heading.TextAlign = 'MiddleCenter'
    }

    $status = [System.Windows.Forms.Label]::new()
    $status.Text = $Texts['PreparingMaintenance']
    $status.Location = [System.Drawing.Point]::new(24, 78)

	# Reservar espacio para mensajes extensos sin recortarlos.
	$status.Size = [System.Drawing.Size]::new(532, 64)
	$status.AutoEllipsis = $true

    $form.Controls.Add($status)

    $progress = [System.Windows.Forms.ProgressBar]::new()
    $progress.Location = [System.Drawing.Point]::new(24, 149)
    $progress.Size = [System.Drawing.Size]::new(532, 20)

	# Progreso por hitos confirmados; sin animación temporal.
	$progress.Style = 'Continuous'
	$progress.Minimum = 0
	$progress.Maximum = 100
	$progress.Value = 0

    $form.Controls.Add($progress)

    $details = [System.Windows.Forms.TextBox]::new()
	$details.Location = [System.Drawing.Point]::new(24, 183)
	$details.Size = [System.Drawing.Size]::new(532, 110)
	$details.Multiline = $true
	$details.ReadOnly = $true
	$details.WordWrap = $true
    $details.ScrollBars = 'Vertical'
    $details.Font = [System.Drawing.Font]::new('Consolas', 9)
    $form.Controls.Add($details)

    $close = [System.Windows.Forms.Button]::new()
    $close.Text = $Texts['Close']
    $close.Location = [System.Drawing.Point]::new(456, 307)
    $close.Size = [System.Drawing.Size]::new(100, 28)
    $close.Add_Click({ param($sender, $eventArgs) $sender.FindForm().Close() })
    $form.Controls.Add($close)
    $form.Tag = @{
        Status = $status
        Progress = $progress
        Details = $details
        Close = $close
        BrandStream = $brandStream
        BrandIcon = $brandIcon
        BrandBitmap = $brandBitmap
    }

    # El formulario de progreso utiliza la misma paleta que el gestor.
    $form.Add_Activated({
        param($sender, $eventArgs)
        Set-WmmFormTheme $sender
    })

    return $form
}

function Start-WmmManagedUI {
    # El worker usa un PS1 temporal: resolver el icono desde
    # la distribución fuente o la instalación existente.
    $iconPath = $null

    if ($PackageRoot) {
        $candidate = Join-Path $PackageRoot 'wmm\WMM-icon.ico'
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            $iconPath = $candidate
        }
    }

    if (-not $iconPath) {
        $candidate = Join-Path $InstallDir 'WMM-icon.ico'
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            $iconPath = $candidate
        }
    }

    # Cargar en memoria antes de cualquier sustitución de archivos.
    # Un recurso gráfico inaccesible no debe impedir el mantenimiento.
    $iconBytes = $null
    if ($iconPath) {
        try { $iconBytes = [IO.File]::ReadAllBytes($iconPath) }
        catch { }
    }

    $bridge = [hashtable]::Synchronized(@{
        Ready = [System.Threading.ManualResetEventSlim]::new($false)
        Form = $null
        Append = $null
        Complete = $null
        Working = $true
        Success = $false
		ProgressValue = 0
		ProgressTotal = 0
		UpdateProgress = $null
        Error = $null
        Strings = $script:WmmTexts
        IconBytes = $iconBytes
    })
    $runspace = [runspacefactory]::CreateRunspace()
    $runspace.ApartmentState = 'STA'
    $runspace.ThreadOptions = 'ReuseThread'
    $runspace.Open()
    $shell = [powershell]::Create()
    $shell.Runspace = $runspace
	$formSource = (Get-Command New-WmmManagedForm).Definition
	$themeSource = (Get-Command Set-WmmFormTheme).Definition

	$uiCode = @'
	param($bridge, $formSource, $themeSource)
	try {
		# El runspace gráfico recibe las funciones que necesita.
		. ([scriptblock]::Create("function Set-WmmFormTheme {`n$themeSource`n}"))
		. ([scriptblock]::Create("function New-WmmManagedForm {`n$formSource`n}"))
	# El formulario recibe su traducción sin acceder a variables
	# ni funciones del runspace que ejecuta el mantenimiento.
	$form = New-WmmManagedForm $bridge.Strings $bridge.IconBytes
    $bridge.Form = $form
    $bridge.Append = [System.Action[string,string]] {
        param($prefix, $message)
        $form.Tag.Status.Text = $message
        $form.Tag.Details.AppendText("[$prefix] $message`r`n")
    }
	# La barra sólo se actualiza desde el hilo Windows Forms.
	$bridge.UpdateProgress = [System.Windows.Forms.MethodInvoker] {
		$form.Tag.Progress.Value = [int]$bridge.ProgressValue
	}
    $bridge.Complete = [System.Windows.Forms.MethodInvoker] {
        $form.Tag.Progress.MarqueeAnimationSpeed = 0
        $form.Tag.Progress.Style = 'Continuous'
		# Ante un error, conservar el último hito confirmado.
		$form.Tag.Progress.Value = if ($bridge.Success) {
			100
		} else {
			[int]$bridge.ProgressValue
		}
        $bridge.Working = $false
        $form.Tag.Close.Enabled = $true
    }
    $form.Tag.Close.Enabled = $false
    $form.Add_FormClosing({
        param($sender, $eventArgs)
        if ($bridge.Working) { $eventArgs.Cancel = $true }
    })
    $form.Add_Shown({ $bridge.Ready.Set() })
    try { [void]$form.ShowDialog() }
    finally {
        $bridge.Form = $null
        $resources = $form.Tag
        $form.Dispose()

        # El formulario libera sus controles; estos recursos gráficos
        # proceden de objetos .NET creados expresamente para el ICO.
        foreach ($resource in @(
            $resources.BrandBitmap,
            $resources.BrandIcon,
            $resources.BrandStream
        )) {
            if ($null -ne $resource) { $resource.Dispose() }
        }
    }
}
catch {
    $bridge.Error = $_.ToString()
    $bridge.Ready.Set()
    throw
}
'@
    [void]$shell.AddScript($uiCode)
    [void]$shell.AddArgument($bridge)
    [void]$shell.AddArgument($formSource)
	[void]$shell.AddArgument($themeSource)

    $async = $shell.BeginInvoke()
    if (-not $bridge.Ready.Wait(10000) -or $bridge.Error) {
        $message = if ($bridge.Error) { $bridge.Error } else { 'Windows Forms did not start.' }
        $shell.Dispose()
        $runspace.Dispose()
        $bridge.Ready.Dispose()
        throw $message
    }
    return [pscustomobject]@{ Bridge=$bridge; Shell=$shell; Runspace=$runspace; Async=$async }
}

function Invoke-WmmWorkerUI([string]$Selected) {
    $ui = Start-WmmManagedUI
    $script:WmmManagedBridge = $ui.Bridge

	# Número de hitos reales que supervisamos por operación.
    $recovering = $Selected -in @('install', 'repair') -and $RecoverRuntime -and
        -not $script:WmmFromInstalled -and
        $Source -in @('Auto', 'Local') -and
        -not (Test-Path -LiteralPath (
            Join-Path $PackageRoot 'wmm-runtime.zip') -PathType Leaf)

	$ui.Bridge.ProgressTotal = switch ($Selected) {
		'install'   { if ($recovering) { 5 } else { 4 } }
		'upgrade'   { 5 }
        'downgrade' { 5 }
		'repair'    { if ($recovering) { 6 } else { 5 } }
		'uninstall' { 4 }
	}
    $success = $false

    try {
        Info "Starting WMM $Selected..."
        Invoke-WmmSelectedOperation $Selected
        Ok "WMM $Selected completed."
        $success = $true
    }
    catch {
        Warn "Maintenance failed: $($_.Exception.Message)"
    }
    finally {
        $ui.Bridge.Success = $success
        [void]$ui.Bridge.Form.BeginInvoke($ui.Bridge.Complete)
        # El proceso permanece vivo hasta que el usuario cierre el resultado.
        [void]$ui.Shell.EndInvoke($ui.Async)
        $script:WmmManagedBridge = $null
        $ui.Shell.Dispose()
        $ui.Runspace.Dispose()
        $ui.Bridge.Ready.Dispose()
    }
    return $success
}

function Start-WmmWorker(
    [string]$Selected, [string]$Desktop='Ask', [string]$Autostart='Ask',
    [string]$SelectedSource='Auto', [string]$SelectedVersion='',
    [bool]$RecoverRuntimeAllowed=$false) {
    if ($SelectedVersion -and $SelectedVersion -notmatch '^\d+\.\d+\.\d+$') {
        throw "Invalid selected WMM version: $SelectedVersion"
    }
    $work = Join-Path $env:TEMP ('wmm-maint-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $work -ErrorAction Stop | Out-Null
    $copy = Join-Path $work 'wmm-install.ps1'
    try {
        # Una sola autoridad: copiamos el script vigente, nunca el runtime.
        Copy-Item -LiteralPath $script:WmmSelfPath -Destination $copy -ErrorAction Stop
        $powershell = Join-Path $PSHOME 'powershell.exe'

        # El proceso inicial determina la procedencia; el worker la conserva.
        $root = $script:WmmOriginRoot

        $arguments = '-NoProfile -STA -ExecutionPolicy Bypass '
        if (-not $Console) { $arguments += '-WindowStyle Hidden ' }
        $arguments += '-File "' + $copy + '" -Worker -Operation ' + $Selected +
            ' -TempRoot "' + $work + '" -PackageRoot "' + $root + '"' +
            ' -Source ' + $SelectedSource +
            ' -DesktopOption ' + $Desktop + ' -AutostartOption ' + $Autostart
        if ($SelectedVersion) { $arguments += ' -ExpectedVersion ' + $SelectedVersion }
		if ($RecoverRuntimeAllowed) { $arguments += ' -RecoverRuntime' }
        if ($Console) { $arguments += ' -Console' }

		# El worker no puede mantener como directorio actual
		# el árbol instalado que tendrá que mover o eliminar.
		$launch = @{
			FilePath = $powershell
			ArgumentList = $arguments
			WorkingDirectory = $env:TEMP
			ErrorAction = 'Stop'
		}
        if (-not $Console) { $launch.WindowStyle = 'Hidden' }
        if ($Console) { $launch.Wait = $true; $launch.PassThru = $true }
        $process = Start-Process @launch
        if ($Console) { return ($process.ExitCode -eq 0) }
        return $true
    }
    catch {
        Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
        throw
    }
}

# ----------------------------------------------------------
# FUNCIÓN: Confirmar instalación y recoger preferencias
# Formulario compacto: dos opciones y confirmación única.
# Cancelar no modifica nada ni inicia el worker.
# ----------------------------------------------------------
function Show-WmmInstallConfirmation {
    param([System.Windows.Forms.Form]$Owner)

    $dialog = [System.Windows.Forms.Form]::new()
    $dialog.Text = Get-WmmText 'InstallationTitle'
    $dialog.StartPosition = 'CenterParent'
    $dialog.FormBorderStyle = 'FixedDialog'
    $dialog.MaximizeBox = $false
    $dialog.MinimizeBox = $false
    $dialog.ShowInTaskbar = $false

    # La disposición horizontal se calcula desde esta anchura.
    $dialog.ClientSize = [System.Drawing.Size]::new(300, 145)

    $dialog.Font = [System.Drawing.Font]::new('Segoe UI', 10)

    # OPCIONES
    # Los checkboxes ocupan el ancho disponible y mantienen
    # sus márgenes cuando cambia la anchura del formulario.
    $desktopCheck = [System.Windows.Forms.CheckBox]::new()
    $desktopCheck.Text = Get-WmmText 'DesktopShortcut'
    $desktopCheck.Location = [System.Drawing.Point]::new(16, 20)
    $desktopCheck.Size = [System.Drawing.Size]::new(
        $dialog.ClientSize.Width - 32, 25)
    $desktopCheck.Anchor = 'Top, Left, Right'
    $desktopCheck.Checked = $true
    $dialog.Controls.Add($desktopCheck)

    $autostartCheck = [System.Windows.Forms.CheckBox]::new()
    $autostartCheck.Text = Get-WmmText 'Autostart'
    $autostartCheck.Location = [System.Drawing.Point]::new(16, 52)
    $autostartCheck.Size = [System.Drawing.Size]::new(
        $dialog.ClientSize.Width - 32, 25)
    $autostartCheck.Anchor = 'Top, Left, Right'
    $autostartCheck.Checked = $false
    $dialog.Controls.Add($autostartCheck)

    # CONFIRMAR / CANCELAR
    # Mantener ambos botones agrupados a la derecha, con
    # separación constante e independencia de la anchura.
    $installButton = [System.Windows.Forms.Button]::new()
    $installButton.Text = Get-WmmText 'Install'
    $installButton.Size = [System.Drawing.Size]::new(85, 30)
    $installButton.DialogResult = [System.Windows.Forms.DialogResult]::OK

    $cancelButton = [System.Windows.Forms.Button]::new()
    $cancelButton.Text = Get-WmmText 'Cancel'
    $cancelButton.Size = [System.Drawing.Size]::new(85, 30)
    $cancelButton.DialogResult = [System.Windows.Forms.DialogResult]::Cancel

    $cancelButton.Location = [System.Drawing.Point]::new(
        $dialog.ClientSize.Width - $cancelButton.Width - 16, 99)
    $installButton.Location = [System.Drawing.Point]::new(
        $cancelButton.Left - $installButton.Width - 8, 99)

    $installButton.Anchor = 'Bottom, Right'
    $cancelButton.Anchor = 'Bottom, Right'

    $dialog.Controls.Add($installButton)
    $dialog.Controls.Add($cancelButton)

    # TEMA COMPARTIDO
    $dialog.Add_Activated({param($sender, $eventArgs) Set-WmmFormTheme $sender})

    # RESULTADO
    # El worker continúa recibiendo Yes/No.
    $selection = $null

    try {
        Set-WmmFormTheme $dialog

        if ($dialog.ShowDialog($Owner) -eq
                [System.Windows.Forms.DialogResult]::OK) {
            $selection = @{
                Desktop = if ($desktopCheck.Checked) { 'Yes' } else { 'No' }
                Autostart = if ($autostartCheck.Checked) { 'Yes' } else { 'No' }
            }
        }
    }
    finally {
        $dialog.Dispose()
    }

    return $selection
}

function Show-WmmManager {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    [System.Windows.Forms.Application]::EnableVisualStyles()

    $installed = Test-Path -LiteralPath $InstallDir -PathType Container
    $version = if ($installed) { Get-WmmInstalledVersion } else { $null }

    # La versión identifica la fuente; la disponibilidad autoriza operaciones.
    $localInfo = Get-WmmLocalPackageInfo $PSScriptRoot
    $localVersion = if ($localInfo.Available) { $localInfo.Version } else { $null }

    $recoverableLocalVersion = if (Test-WmmRuntimeRecovery $localInfo) {
        $localInfo.Version
    } else { $null }

    $form = [System.Windows.Forms.Form]::new()
    $form.Text = Get-WmmText 'WindowTitle'
    $form.StartPosition = 'CenterScreen'
    $form.FormBorderStyle = 'FixedDialog'
    $form.MaximizeBox = $false
    $form.MinimizeBox = $false
    $form.ClientSize = [System.Drawing.Size]::new(450, 375)
    $form.Font = [System.Drawing.Font]::new('Segoe UI', 10)

    # CABECERA
    $title = [System.Windows.Forms.Label]::new()
    $title.Text = 'Wallpaper Multi-Monitor Manager'
    $title.Font = [System.Drawing.Font]::new('Segoe UI', 14, [System.Drawing.FontStyle]::Bold)
    $title.Location = [System.Drawing.Point]::new(0, 22)
    $title.Size = [System.Drawing.Size]::new($form.ClientSize.Width, 34)
    $title.TextAlign = 'MiddleCenter'
    $form.Controls.Add($title)

    $subtitle = [System.Windows.Forms.Label]::new()
    $subtitle.Text = Get-WmmText 'WindowTitle'
    $subtitle.Font = [System.Drawing.Font]::new('Segoe UI', 12, [System.Drawing.FontStyle]::Bold)
    $subtitle.Location = [System.Drawing.Point]::new(0, 59)
    $subtitle.Size = [System.Drawing.Size]::new($form.ClientSize.Width, 24)
    $subtitle.TextAlign = 'MiddleCenter'
    $form.Controls.Add($subtitle)

    # IDENTIDAD VISUAL WMM
    # El ICO se carga en memoria para no mantener bloqueado el
    # archivo de la instalación durante futuras operaciones.
    $brandStream = $null
    $brandIcon = $null
    $brandBitmap = $null

    $iconPath = if (-not $script:WmmFromInstalled) {
        Join-Path $PSScriptRoot 'wmm\WMM-icon.ico'
    } else {
        Join-Path $InstallDir 'WMM-icon.ico'
    }

    if (Test-Path -LiteralPath $iconPath -PathType Leaf) {
        $brandStream = [IO.MemoryStream]::new([IO.File]::ReadAllBytes($iconPath))
        $brandIcon = [System.Drawing.Icon]::new($brandStream, 48, 48)
        $brandBitmap = $brandIcon.ToBitmap()

        # ICONO NATIVO
        $form.Icon = $brandIcon

        # LOGOTIPO DE CABECERA
        $brandLogo = [System.Windows.Forms.PictureBox]::new()
        $brandLogo.Image = $brandBitmap
        $brandLogo.Location = [System.Drawing.Point]::new(20, 29)
        $brandLogo.Size = [System.Drawing.Size]::new(48, 48)
        $brandLogo.SizeMode = 'Zoom'
        $form.Controls.Add($brandLogo)

        # Reservar espacio para el logotipo sin ampliar la ventana.
        $title.Location = [System.Drawing.Point]::new(64, 22)
        $title.Size = [System.Drawing.Size]::new(330, 34)
		$title.TextAlign = 'MiddleCenter'

        $subtitle.Location = [System.Drawing.Point]::new(64, 59)
        $subtitle.Size = [System.Drawing.Size]::new(330, 24)
        $title.TextAlign = 'MiddleCenter'
    }

    $sep = [System.Windows.Forms.Label]::new()
    $sep.BorderStyle = 'Fixed3D'
    $sep.Location = [System.Drawing.Point]::new(24, 99)
    $sep.Size = [System.Drawing.Size]::new($form.ClientSize.Width - 48, 2)
    $form.Controls.Add($sep)

    # INFORMACIÓN
    # Cuatro filas: instalada, paquete local, escritorio y sesión.
    $information = [System.Windows.Forms.Panel]::new()
    $information.Font = [System.Drawing.Font]::new('Tahoma', 11, [System.Drawing.FontStyle]::Regular)
    $information.Size = [System.Drawing.Size]::new(390, 92)
    $information.Location = [System.Drawing.Point]::new(
        [int](($form.ClientSize.Width - $information.Width) / 2), 113)

    $displayVersion = if ($version) { $version }
        elseif ($installed) { Get-WmmText 'Unknown' }
        else { Get-WmmText 'NotInstalled' }
    $displayLocal = if ($localInfo.Version) {
        $localInfo.Version
    } else {
        Get-WmmText 'NotAvailable'
    }

    $infoLabels = [System.Windows.Forms.Label]::new()
    $infoLabels.Text = @(
        (Get-WmmText 'InstalledVersion') + ':'
        (Get-WmmText 'PackageVersion') + ':'
        (Get-WmmText 'Desktop') + ':'
        (Get-WmmText 'Session') + ':'
    ) -join "`r`n"
    $infoLabels.Location = [System.Drawing.Point]::new(0, 0)
    $infoLabels.Size = [System.Drawing.Size]::new(188, 90)
    $infoLabels.TextAlign = 'TopRight'
    $information.Controls.Add($infoLabels)

    $infoValues = [System.Windows.Forms.Label]::new()
    $infoValues.Text = "$displayVersion`r`n$displayLocal`r`nWindows`r`nWin32"
    $infoValues.Location = [System.Drawing.Point]::new(200, 0)
    $infoValues.Size = [System.Drawing.Size]::new(190, 90)
    $infoValues.TextAlign = 'TopLeft'
    $information.Controls.Add($infoValues)
    $form.Controls.Add($information)

    # DIAGNÓSTICO DEL PAQUETE
    # Desde fuentes se muestran los requisitos ausentes.
    # Desde la instalación solo se advierte de la falta del repair,
    # sin confundirla con la ausencia legítima de recursos fuente.
    $missingTip = $null
    $missingText = $null

    if (-not $script:WmmFromInstalled -and $localInfo.MissingFile) {
        $missingText = (Get-WmmText 'LocalPackageMissingFile') -f $localInfo.MissingFile
    }
    elseif ($script:WmmFromInstalled -and $installed -and
            -not (Test-WmmRepairArchive)) {
        $missingText = Get-WmmText 'RepairPackageMissing'
    }

    if ($missingText) {
        $missingLabel = [System.Windows.Forms.Label]::new()
        $missingLabel.Text = $missingText
		$missingLabel.Location = [System.Drawing.Point]::new(24, 195)
		$missingLabel.Size = [System.Drawing.Size]::new(402, 32)
        $missingLabel.TextAlign = 'MiddleCenter'
        $missingLabel.Font = [System.Drawing.Font]::new('Segoe UI', 9)
        $missingLabel.AutoEllipsis = $true

        # Las rutas extensas conservan su texto íntegro en el tooltip.
        $missingTip = [System.Windows.Forms.ToolTip]::new()
        $missingTip.SetToolTip($missingLabel, $missingLabel.Text)
        $form.Controls.Add($missingLabel)
    }

    # Ranuras compartidas: la consulta GitHub solo actualiza su estado.
    $buttons = @()
    $captions = @()
    for ($i = 0; $i -lt 4; $i++) {
        $button = [System.Windows.Forms.Button]::new()
        $button.Visible = $false
        $form.Controls.Add($button)
        $buttons += $button

        $caption = [System.Windows.Forms.Label]::new()
        $caption.TextAlign = 'TopCenter'
        $caption.Font = [System.Drawing.Font]::new('Segoe UI', 8)
        $caption.Visible = $false
        $form.Controls.Add($caption)
        $captions += $caption
    }

    $githubLabel = [System.Windows.Forms.Label]::new()
    $githubLabel.Location = [System.Drawing.Point]::new(24, 335)
    $githubLabel.Size = [System.Drawing.Size]::new(275, 24)
    $githubLabel.TextAlign = 'MiddleLeft'
    $githubLabel.Text = (Get-WmmText 'GitHubVersion') + ': ...'
    $form.Controls.Add($githubLabel)

    $close = [System.Windows.Forms.Button]::new()
    $close.Text = Get-WmmText 'Close'
    $close.Size = [System.Drawing.Size]::new(90, 30)
    $close.Location = [System.Drawing.Point]::new(
        $form.ClientSize.Width - $close.Width - 24,
        $form.ClientSize.Height - $close.Height - 16)
    $close.Anchor = 'Bottom, Right'
    $close.Add_Click({ $form.Close() })
    $form.Controls.Add($close)

    $form.Tag = @{
        Installed = $installed
        InstalledVersion = $version
        LocalVersion = $localVersion
        RecoverableLocalVersion = $recoverableLocalVersion
        GithubVersion = $null
        Buttons = $buttons
        Captions = $captions
    }

    foreach ($button in $buttons) {
        $button.Add_Click({
            param($sender, $eventArgs)
            $choice = $sender.Tag
            if ($null -eq $choice) { return }
            $selected = [string]$choice.Action
            $selectedSource = [string]$choice.Source
            $selectedVersion = [string]$choice.Version
            $questionKey = switch ($selected) {
                'install'   { 'ConfirmInstall' }
                'upgrade'   { 'ConfirmUpgrade' }
                'downgrade' { 'ConfirmDowngrade' }
                'repair'    { 'ConfirmReinstall' }
                'uninstall' { 'ConfirmUninstall' }
            }

            $question = Get-WmmText $questionKey
            if ($selectedVersion) {
                # Confirmar la selección concreta, no solo un verbo genérico.
                $sourceKey = [string]$choice.CaptionKey
                $question += "`r`n`r`n" + (Get-WmmText 'TargetVersion') + ': ' + $selectedVersion +
                    "`r`n" + (Get-WmmText 'PackageSource') + ': ' + (Get-WmmText $sourceKey)
            }

            $desktop = 'Ask'
            $autostart = 'Ask'
            $recoverRuntime = $false

            if ($selected -eq 'install') {
                # La descarga requiere permiso expreso antes de preparar
                # el paquete; las preferencias conservan su diálogo actual.
                if ($selectedSource -eq 'Local' -and $selectedVersion -and
                        $selectedVersion -eq $form.Tag.RecoverableLocalVersion) {
                    $question = (Get-WmmText 'ConfirmRuntimeInstall') -f $selectedVersion
                    $answer = [System.Windows.Forms.MessageBox]::Show(
                        $form, $question, (Get-WmmText 'WindowTitle'), 'YesNo', 'Question')
                    if ($answer -ne [System.Windows.Forms.DialogResult]::Yes) { return }
                    $recoverRuntime = $true
                }

                # La confirmación y las preferencias comparten un diálogo.
                $options = Show-WmmInstallConfirmation -Owner $form

                if ($null -eq $options) { return }

                $desktop = [string]$options.Desktop
                $autostart = [string]$options.Autostart
            }
            else {
                # Reinstalar con runtime ausente solicita permiso para
                # completar la misma fuente antes del mantenimiento.
                $recoverRuntime = $selected -eq 'repair' -and
                    $selectedSource -eq 'Local' -and
                    $selectedVersion -eq $form.Tag.RecoverableLocalVersion

                if ($recoverRuntime) {
                    $question = (Get-WmmText 'ConfirmRuntimeDownload') -f $selectedVersion
                }

                $answer = [System.Windows.Forms.MessageBox]::Show(
                    $form, $question, (Get-WmmText 'WindowTitle'), 'YesNo', 'Question')

                if ($answer -ne [System.Windows.Forms.DialogResult]::Yes) { return }
            }
            try {
                [void](Start-WmmWorker $selected $desktop $autostart `
                    $selectedSource $selectedVersion $recoverRuntime)
                $form.Close()
            }
            catch {
                [System.Windows.Forms.MessageBox]::Show(
                    $form, $_.Exception.Message, (Get-WmmText 'StartFailed'), 'OK', 'Error') | Out-Null
            }
        })
    }

    # Mostrar las operaciones locales sin esperar a la red.
    Update-WmmManagerChoices $form

    # Consulta asíncrona; DownloadStringCompleted se ejecuta en el
    # contexto WinForms. No se bloquea la ventana ni se hace polling.
    $client = [System.Net.WebClient]::new()
    $client.Encoding = [System.Text.Encoding]::UTF8
    $client.Headers.Add('Accept', 'application/vnd.github+json')
    $client.Headers.Add('User-Agent', 'WMM-Install-Manager')
    $client.add_DownloadStringCompleted({
        param($sender, $eventArgs)
        try {
            $latest = $null
            if (-not $eventArgs.Cancelled -and $null -eq $eventArgs.Error) {
                $release = $eventArgs.Result | ConvertFrom-Json
                $tag = [string]$release.tag_name
                if ($tag -match '^v(?<version>\d+\.\d+\.\d+)$') {
                    $candidate = $Matches['version']
                    if ([version]$candidate -ge $script:WmmMinGitHubVersion) {
                        $latest = $candidate
                    }
                }
            }
            if (-not $form.IsDisposed) {
                $form.Tag.GithubVersion = $latest
                $display = if ($latest) { $latest } else { Get-WmmText 'NotAvailable' }
                $githubLabel.Text = (Get-WmmText 'GitHubVersion') + ': ' + $display
                Update-WmmManagerChoices $form
            }
        }
        catch {
            if (-not $form.IsDisposed) {
                $form.Tag.GithubVersion = $null
                $githubLabel.Text = (Get-WmmText 'GitHubVersion') + ': ' + (Get-WmmText 'NotAvailable')
                Update-WmmManagerChoices $form
            }
        }
        finally { $sender.Dispose() }
    })
    $form.Add_Shown({
        try {
            [Net.ServicePointManager]::SecurityProtocol =
                [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
            $client.DownloadStringAsync(
                [uri]'https://api.github.com/repos/makimanson/wmm/releases/latest')
        }
        catch {
            $githubLabel.Text = (Get-WmmText 'GitHubVersion') + ': ' + (Get-WmmText 'NotAvailable')
            $client.Dispose()
        }
    })
    $form.Add_FormClosed({
        if ($client.IsBusy) { $client.CancelAsync() }
    })

    $form.Add_Activated({
        param($sender, $eventArgs)
        Set-WmmFormTheme $sender
    })

    try {
        [void]$form.ShowDialog()
    }
    finally {
        $form.Dispose()

        # Liberar los recursos gráficos cargados en memoria.
        if ($null -ne $brandBitmap) { $brandBitmap.Dispose() }
        if ($null -ne $brandIcon) { $brandIcon.Dispose() }
        if ($null -ne $brandStream) { $brandStream.Dispose() }

        if ($null -ne $missingTip) { $missingTip.Dispose() }
    }
}

# ==========================================================
# Entrada: menú gráfico o consola; el worker nunca usa runtime.
# ==========================================================
function Show-WmmConsoleMenu {
    # Consola y GUI consumen las mismas opciones, aunque la consulta
    # de latest aquí es síncrona porque no existe un bucle WinForms.
    $installed = Test-Path -LiteralPath $InstallDir -PathType Container
    $installedVersion = if ($installed) { Get-WmmInstalledVersion } else { $null }

    # La versión identifica la fuente; la disponibilidad autoriza operaciones.
    $localInfo = Get-WmmLocalPackageInfo $PSScriptRoot
    $localVersion = if ($localInfo.Available) { $localInfo.Version } else { $null }
    $recoverableLocalVersion = if (Test-WmmRuntimeRecovery $localInfo) {
        $localInfo.Version
    } else { $null }
    $githubVersion = $null
    try {
        [Net.ServicePointManager]::SecurityProtocol =
            [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
        $headers = @{ Accept='application/vnd.github+json'; 'User-Agent'='WMM-Install-Manager' }
        $release = Invoke-RestMethod -Uri 'https://api.github.com/repos/makimanson/wmm/releases/latest' `
            -Headers $headers -TimeoutSec 20 -ErrorAction Stop
        if ([string]$release.tag_name -match '^v(?<version>\d+\.\d+\.\d+)$') {
            $candidate = $Matches['version']
            if ([version]$candidate -ge $script:WmmMinGitHubVersion) {
                $githubVersion = $candidate
            }
        }
    }
    catch { }  # Falta de respuesta: N/A, sin afectar las opciones locales.

    $choices = @(Get-WmmOperationChoices -Installed $installed `
        -InstalledVersion $installedVersion -LocalVersion $localVersion `
        -GithubVersion $githubVersion `
        -RecoverableLocalVersion $recoverableLocalVersion)
    Write-Host ''
    Write-Host 'WMM Install Manager (Windows)'
    Write-Host ("Installed: " + $(if ($installedVersion) { $installedVersion } elseif ($installed) { 'Unknown' } else { 'Not installed' }))
    Write-Host ("Local package: " + $(if ($localInfo.Version) { $localInfo.Version } else { 'N/A' }))

    # Advertir solo ante una distribución fuente incompleta.
    # El gestor instalado carece legítimamente de los recursos fuente.
    if (-not $script:WmmFromInstalled -and $localInfo.MissingFile) {
        Warn ((Get-WmmText 'LocalPackageMissingFile') -f $localInfo.MissingFile)
    }

    # El gestor instalado no puede reinstalar sin su repair.
    if ($script:WmmFromInstalled -and $installed -and
            -not (Test-WmmRepairArchive)) {
        Warn (Get-WmmText 'RepairPackageMissing')
    }

    Write-Host ("GitHub: " + $(if ($githubVersion) { $githubVersion } else { 'N/A' }))
    Write-Host ''

    while ($true) {
        for ($i = 0; $i -lt $choices.Count; $i++) {
            $choice = $choices[$i]
            $title = Get-WmmText $choice.TextKey
            if ($choice.Version) { $title += ' ' + $choice.Version }
            $unavailable = if ($choice.Source -eq 'Repair' -and
                    -not (Test-WmmRepairArchive)) {
                ' [' + (Get-WmmText 'NotAvailable') + ']'
            } else { '' }

            Write-Host ("{0}. {1} ({2}){3}" -f
                ($i + 1), $title, (Get-WmmText $choice.CaptionKey), $unavailable)
        }
        Write-Host '0. Exit'
        $answer = Read-Host 'Select an option'
        if ($answer -eq '0') { return }

        $choiceIndex = 0
        if (-not [int]::TryParse($answer, [ref]$choiceIndex) -or
                $choiceIndex -lt 1 -or $choiceIndex -gt $choices.Count) {
            Warn 'This option is not available.'
            continue
        }

        $choice = $choices[$choiceIndex - 1]

        # En consola no existe Enabled: impedir expresamente
        # seleccionar una reinstalación cuyo repair no existe.
        if ($choice.Source -eq 'Repair' -and -not (Test-WmmRepairArchive)) {
            Warn (Get-WmmText 'RepairPackageMissing')
            continue
        }

        $recoverRuntime = $choice.Action -in @('install', 'repair') -and
            $choice.Source -eq 'Local' -and
            $choice.Version -eq $recoverableLocalVersion

        $question = if ($recoverRuntime) {
            $key = if ($choice.Action -eq 'install') {
                'ConfirmRuntimeInstall'
            } else { 'ConfirmRuntimeDownload' }
            (Get-WmmText $key) -f $choice.Version
        } else {
            "Start WMM {0} {1} from {2}?" -f
                $choice.Action, $choice.Version, $choice.Source
        }

        if (-not (Confirm-Wmm $question)) { continue }

        if (-not (Start-WmmWorker $choice.Action 'Ask' 'Ask' `
                $choice.Source $choice.Version $recoverRuntime)) {
            Warn "WMM $($choice.Action) failed."
            continue
        }
        return
    }
}

if ($Worker) {
    if (-not $Operation) { throw 'Internal maintenance operation missing.' }
    if (-not $TempRoot) { throw 'Internal temporary directory missing.' }
    if ($Console) {
        $success = $false
        try { Invoke-WmmSelectedOperation $Operation; $success = $true }
        catch { Warn "Maintenance failed: $($_.Exception.Message)" }
    }
    else { $success = Invoke-WmmWorkerUI $Operation }

    # El propio worker ya ha terminado de leer los recursos temporales.
    # La limpieza es best-effort para no ocultar un resultado operativo.
    try {
        if ($TempRoot -and $TempRoot -match '^.+[\\/]wmm-maint-[a-f0-9]{32}$') {
            Remove-Item -LiteralPath $TempRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
    catch { }
    if ($success) { exit 0 } else { exit 1 }
}

if ($Operation) {
    # Los accesos del menú Inicio / Registro llegan aquí.

    # Una instalación gráfica directa también debe recoger las
    # preferencias antes de lanzar el worker sin consola.
    if ($Operation -eq 'install' -and -not $Console) {
        Add-Type -AssemblyName System.Windows.Forms

        if ($DesktopOption -eq 'Ask') {
            $answer = [System.Windows.Forms.MessageBox]::Show(
                'Create a desktop shortcut?', 'WMM Installation', 'YesNo', 'Question')
            $DesktopOption = if ($answer -eq 'Yes') { 'Yes' } else { 'No' }
        }

        if ($AutostartOption -eq 'Ask') {
            $answer = [System.Windows.Forms.MessageBox]::Show(
                'Start WMM with Windows?', 'WMM Installation', 'YesNo', 'Question')
            $AutostartOption = if ($answer -eq 'Yes') { 'Yes' } else { 'No' }
        }
    }

    # Una desinstalación directa también requiere confirmación: el
    # gestor gráfico ya la pidió al seleccionar su botón.
    if ($Operation -eq 'uninstall') {
        if ($Console) {
            if (-not (Confirm-Wmm 'Uninstall WMM Manager?')) { return }
        }
        else {
            Add-Type -AssemblyName System.Windows.Forms
			$answer = [System.Windows.Forms.MessageBox]::Show(
				(Get-WmmText 'DirectUninstall'),
				(Get-WmmText 'UninstallTitle'), 'YesNo', 'Warning')
            if ($answer -ne [System.Windows.Forms.DialogResult]::Yes) { return }
        }
    }

    # La instalación o reinstalación directa también requieren
    # consentimiento antes de completar un runtime fuente ausente.
    $recoverRuntimeAllowed = $false

    if ($Operation -in @('install', 'repair') -and
            -not $script:WmmFromInstalled -and
            $Source -in @('Auto', 'Local')) {

        $localInfo = Get-WmmLocalPackageInfo $script:WmmOriginRoot

        if (Test-WmmRuntimeRecovery $localInfo) {
            $key = if ($Operation -eq 'install') {
                'ConfirmRuntimeInstall'
            } else { 'ConfirmRuntimeDownload' }
            $question = (Get-WmmText $key) -f $localInfo.Version

            if ($Console) {
                if (-not (Confirm-Wmm $question)) { return }
            }
            else {
                Add-Type -AssemblyName System.Windows.Forms
                $answer = [System.Windows.Forms.MessageBox]::Show(
                    $question, (Get-WmmText 'WindowTitle'), 'YesNo', 'Question')

                if ($answer -ne [System.Windows.Forms.DialogResult]::Yes) { return }
            }

            $recoverRuntimeAllowed = $true
        }
    }

    # Delegar siempre desde fuera del árbol que va a modificarse.
    $successful = Start-WmmWorker $Operation $DesktopOption $AutostartOption `
        $Source $ExpectedVersion $recoverRuntimeAllowed
    if ($Console -and -not $successful) { exit 1 }
}
elseif ($Console) { Show-WmmConsoleMenu }
else { Show-WmmManager }
