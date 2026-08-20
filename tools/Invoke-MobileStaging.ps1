[CmdletBinding()]
param(
    [string]$Action,
    [string]$Mode,
    [string]$Commit,
    [string]$ConfigPath,
    [string]$ApprovalPath,
    [switch]$PreserveSession,
    [switch]$PublicHealth,
    [switch]$PurgeEvidence
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:PackageId = 'tw.org.ntubtob.portal'
$script:MainActivity = 'tw.org.ntubtob.portal/.MainActivity'
$script:ExpectedRevision = '0005_mobile_auth_api_foundation'
$script:ProductionProject = 'ntubtob-schedule-405614'
$script:FullShaPattern = '^[0-9a-f]{40}$'
$script:FingerprintPattern = '^[0-9A-F]{64}$'
$script:TaskEvidenceRoot = 'E:\codex-evidence\task-123'
$script:TaskTempRoot = 'E:\codex-temp\task-123'
$script:RoutineActions = @('help', 'preflight', 'avd-start', 'status', 'build', 'signer-check', 'install', 'cold-launch', 'health', 'stop', 'cleanup')
$script:PrivateActions = @('private-inspect', 'grant-officer', 'restore-basic')

function Throw-Safe {
    param([string]$Message)
    throw [System.InvalidOperationException]::new($Message)
}

function ConvertTo-SafeArgument {
    param([string]$Value)
    if ($null -eq $Value) { return '""' }
    if ($Value -notmatch '[\s"]') { return $Value }
    return '"' + ($Value -replace '(\\*)"', '$1$1\"' -replace '(\\+)$', '$1$1') + '"'
}

function Invoke-BoundedProcess {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [string[]]$Arguments = @(),
        [int]$TimeoutSeconds = 30,
        [hashtable]$ChildEnvironment = @{},
        [string]$WorkingDirectory = ''
    )
    if (-not [System.IO.Path]::IsPathRooted($Executable) -or -not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
        Throw-Safe 'Approved executable is unavailable'
    }
    if ($TimeoutSeconds -lt 1 -or $TimeoutSeconds -gt 600) {
        Throw-Safe 'Process timeout is outside the bounded range'
    }
    $start = [System.Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $Executable
    $start.Arguments = (($Arguments | ForEach-Object { ConvertTo-SafeArgument ([string]$_) }) -join ' ')
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    if ($WorkingDirectory) { $start.WorkingDirectory = $WorkingDirectory }
    foreach ($name in $ChildEnvironment.Keys) {
        $start.EnvironmentVariables[[string]$name] = [string]$ChildEnvironment[$name]
    }
    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $start
    $started = $false
    try {
        if (-not $process.Start()) { Throw-Safe 'Approved process did not start' }
        $started = $true
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        $completed = $process.WaitForExit($TimeoutSeconds * 1000)
        if (-not $completed) {
            try { $process.Kill() } catch { }
            return [pscustomobject]@{ ExitCode = $null; TimedOut = $true; Stdout = ''; Stderr = '' }
        }
        $stdoutTask.Wait()
        $stderrTask.Wait()
        return [pscustomobject]@{
            ExitCode = $process.ExitCode
            TimedOut = $false
            Stdout = $stdoutTask.Result
            Stderr = $stderrTask.Result
        }
    }
    finally {
        if ($started -and -not $process.HasExited) { try { $process.Kill() } catch { } }
        $start.Arguments = ''
        $Arguments = $null
        $ChildEnvironment = $null
        $process.Dispose()
    }
}

function Assert-NoSensitiveText {
    param([string]$Text)
    if ($Text -match '(?i)(postgres(?:ql)?://|provider[_ -]?subject|bearer\s|id[_ -]?token|refresh[_ -]?token|assertion|keystore|storepass|keypass|api[_ -]?base[_ -]?url|line[_ -]?channel[_ -]?id)') {
        Throw-Safe 'Launcher output failed the sensitive-field gate'
    }
}

function Write-SafeJson {
    param([object]$Value)
    $json = $Value | ConvertTo-Json -Depth 8 -Compress
    Assert-NoSensitiveText $json
    Write-Output $json
}

function Assert-ExactProperties {
    param([object]$Value, [string[]]$Expected, [string]$Label)
    $actual = @($Value.PSObject.Properties.Name | Sort-Object)
    $wanted = @($Expected | Sort-Object)
    if (($actual -join "`n") -cne ($wanted -join "`n")) {
        Throw-Safe "$Label fields are not exact"
    }
}

function Assert-TaskPath {
    param([string]$Path, [string]$ExactRoot, [switch]$AllowRoot)
    if (-not [System.IO.Path]::IsPathRooted($Path)) { Throw-Safe 'Task path must be absolute' }
    $full = [System.IO.Path]::GetFullPath($Path).TrimEnd('\')
    $root = [System.IO.Path]::GetFullPath($ExactRoot).TrimEnd('\')
    if (($full -cne $root -or -not $AllowRoot) -and -not $full.StartsWith($root + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
        Throw-Safe 'Path escapes the task-owned root'
    }
    return $full
}

function Load-LauncherConfig {
    param([string]$Path)
    if (-not $Path -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        Throw-Safe 'Launcher config is required'
    }
    try { $config = Get-Content -LiteralPath $Path -Encoding UTF8 -Raw | ConvertFrom-Json }
    catch { Throw-Safe 'Launcher config is unavailable or malformed' }
    $fields = @(
        'schema_version', 'snapshot_root', 'flutter_executable', 'git_executable',
        'adb_executable', 'emulator_executable', 'apksigner_executable',
        'apkanalyzer_executable', 'keytool_executable',
        'android_sdk_root', 'java_home', 'android_user_homes', 'android_avd_home',
        'pub_cache', 'gradle_user_home', 'avd_name',
        'serial', 'package_id', 'main_activity', 'evidence_root', 'temp_root',
        'min_free_bytes', 'signer_allowlist', 'artifact_relative_path'
    )
    Assert-ExactProperties $config $fields 'Launcher config'
    if ($config.schema_version -ne 1 -or $config.package_id -cne $script:PackageId -or $config.main_activity -cne $script:MainActivity) {
        Throw-Safe 'Launcher config identity is not exact'
    }
    foreach ($pathField in @('snapshot_root', 'flutter_executable', 'adb_executable', 'emulator_executable', 'apksigner_executable', 'apkanalyzer_executable', 'keytool_executable', 'android_sdk_root', 'java_home', 'android_avd_home', 'pub_cache', 'gradle_user_home')) {
        $value = [string]$config.$pathField
        if (-not [System.IO.Path]::IsPathRooted($value) -or -not $value.StartsWith('E:\', [System.StringComparison]::OrdinalIgnoreCase)) {
            Throw-Safe 'Approved toolchain must remain on the E drive'
        }
    }
    foreach ($pathField in @('git_executable')) {
        if (-not [System.IO.Path]::IsPathRooted([string]$config.$pathField)) { Throw-Safe 'System executable path must be absolute' }
    }
    if ([string]$config.evidence_root -cne $script:TaskEvidenceRoot -or [string]$config.temp_root -cne $script:TaskTempRoot) {
        Throw-Safe 'Evidence and temp roots are not task-owned'
    }
    if (-not ([string]$config.avd_name -match '^[A-Za-z0-9._-]{3,64}$') -or -not ([string]$config.serial -match '^emulator-[0-9]{4,5}$')) {
        Throw-Safe 'AVD or serial is invalid'
    }
    if ([long]$config.min_free_bytes -lt 1073741824 -or [long]$config.min_free_bytes -gt 1099511627776) {
        Throw-Safe 'Disk threshold is invalid'
    }
    $homes = @($config.android_user_homes)
    $signers = @($config.signer_allowlist)
    if ($homes.Count -lt 1 -or $homes.Count -gt 4 -or $signers.Count -ne 1) {
        Throw-Safe 'Signer inventory is not exact'
    }
    foreach ($androidUserHomeCandidate in $homes) {
        if (-not [System.IO.Path]::IsPathRooted([string]$androidUserHomeCandidate) -or -not ([string]$androidUserHomeCandidate).StartsWith('E:\', [System.StringComparison]::OrdinalIgnoreCase)) {
            Throw-Safe 'Android user home is outside the E drive allowlist'
        }
    }
    foreach ($signer in $signers) {
        if (-not ([string]$signer -cmatch $script:FingerprintPattern)) { Throw-Safe 'Signer allowlist is invalid' }
    }
    if ([string]$config.artifact_relative_path -cne 'app-debug.apk') {
        Throw-Safe 'Artifact path is not exact'
    }
    return $config
}

function Assert-Snapshot {
    param([object]$Config, [string]$ExpectedCommit)
    if ($ExpectedCommit -notmatch $script:FullShaPattern) { Throw-Safe 'A full accepted commit SHA is required' }
    $root = [string]$Config.snapshot_root
    if (-not (Test-Path -LiteralPath $root -PathType Container)) { Throw-Safe 'Detached snapshot is unavailable' }
    $head = Invoke-BoundedProcess ([string]$Config.git_executable) @('-C', $root, 'rev-parse', 'HEAD') 15
    if ($head.TimedOut -or $head.ExitCode -ne 0 -or $head.Stdout.Trim() -cne $ExpectedCommit) { Throw-Safe 'Snapshot commit does not match' }
    $branch = Invoke-BoundedProcess ([string]$Config.git_executable) @('-C', $root, 'symbolic-ref', '-q', 'HEAD') 15
    if ($branch.TimedOut -or $branch.ExitCode -eq 0) { Throw-Safe 'Snapshot must be detached' }
    $status = Invoke-BoundedProcess ([string]$Config.git_executable) @('-C', $root, 'status', '--porcelain', '--untracked-files=all') 15
    if ($status.TimedOut -or $status.ExitCode -ne 0 -or $status.Stdout.Trim().Length -ne 0) { Throw-Safe 'Snapshot must be clean' }
}

function Assert-DiskAndLock {
    param([object]$Config)
    $drive = Get-PSDrive -Name E -ErrorAction SilentlyContinue
    if ($null -eq $drive -or $null -eq $drive.Free -or [long]$drive.Free -lt [long]$Config.min_free_bytes) {
        Throw-Safe 'Approved E drive has insufficient or unknown free space'
    }
    $lock = ([string]$Config.temp_root).TrimEnd('\') + '.lock'
    if (Test-Path -LiteralPath $lock) { Throw-Safe 'Task launcher lock already exists' }
}

function Get-AdbSerials {
    param([object]$Config)
    $result = Invoke-BoundedProcess ([string]$Config.adb_executable) @('devices') 15
    if ($result.TimedOut -or $result.ExitCode -ne 0) { Throw-Safe 'ADB inventory failed safely' }
    $serials = @()
    foreach ($line in ($result.Stdout -split "`r?`n")) {
        if ($line -match '^([^\s]+)\s+device$') { $serials += $Matches[1] }
        elseif ($line -match '^([^\s]+)\s+(offline|unauthorized)$') { Throw-Safe 'ADB serial state is not ready' }
    }
    return @($serials)
}

function Assert-OnlyApprovedSerial {
    param([object]$Config)
    $serials = @(Get-AdbSerials $Config)
    if ($serials.Count -ne 1 -or $serials[0] -cne [string]$Config.serial) {
        Throw-Safe 'ADB serial inventory is not exact'
    }
}

function Invoke-Preflight {
    param([object]$Config, [string]$ExpectedCommit, [string]$SelectedMode)
    Assert-Snapshot $Config $ExpectedCommit
    Assert-DiskAndLock $Config
    foreach ($field in @('flutter_executable', 'adb_executable', 'emulator_executable', 'apksigner_executable', 'apkanalyzer_executable', 'keytool_executable')) {
        if (-not (Test-Path -LiteralPath ([string]$Config.$field) -PathType Leaf)) { Throw-Safe 'Approved toolchain is incomplete' }
    }
    return [ordered]@{ action = 'preflight'; result = 'ready'; commit = $ExpectedCommit; mode = $SelectedMode }
}

function Invoke-AvdStart {
    param([object]$Config)
    $inventory = Invoke-BoundedProcess ([string]$Config.emulator_executable) @('-list-avds') 15 @{
        ANDROID_SDK_ROOT = [string]$Config.android_sdk_root
        ANDROID_HOME = [string]$Config.android_sdk_root
        ANDROID_AVD_HOME = [string]$Config.android_avd_home
    }
    if ($inventory.TimedOut -or $inventory.ExitCode -ne 0 -or @($inventory.Stdout -split "`r?`n" | Where-Object { $_ -ceq [string]$Config.avd_name }).Count -ne 1) {
        Throw-Safe 'Approved AVD inventory is not exact'
    }
    $serials = @(Get-AdbSerials $Config)
    if ($serials.Count -eq 1 -and $serials[0] -ceq [string]$Config.serial) {
        return [ordered]@{ action = 'avd-start'; result = 'reused'; serial = 'approved' }
    }
    if ($serials.Count -ne 0) { Throw-Safe 'Unknown ADB serial prevents AVD start' }
    $start = [System.Diagnostics.ProcessStartInfo]::new()
    $start.FileName = [string]$Config.emulator_executable
    $start.Arguments = "-avd $($Config.avd_name) -no-snapshot-load -no-boot-anim"
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.EnvironmentVariables['ANDROID_SDK_ROOT'] = [string]$Config.android_sdk_root
    $start.EnvironmentVariables['ANDROID_HOME'] = [string]$Config.android_sdk_root
    $start.EnvironmentVariables['ANDROID_AVD_HOME'] = [string]$Config.android_avd_home
    $process = [System.Diagnostics.Process]::Start($start)
    if ($null -eq $process) { Throw-Safe 'Approved AVD did not start' }
    $deadline = [DateTime]::UtcNow.AddSeconds(120)
    try {
        do {
            Start-Sleep -Milliseconds 500
            $serials = @(Get-AdbSerials $Config)
            if ($serials.Count -eq 1 -and $serials[0] -ceq [string]$Config.serial) {
                return [ordered]@{ action = 'avd-start'; result = 'started'; serial = 'approved' }
            }
            if ($serials.Count -gt 0) { Throw-Safe 'Unknown ADB serial appeared during AVD start' }
        } while ([DateTime]::UtcNow -lt $deadline -and -not $process.HasExited)
        Throw-Safe 'Approved AVD did not become ready within the bounded window'
    }
    catch {
        if (-not $process.HasExited) { try { $process.Kill() } catch { } }
        throw
    }
    finally { $process.Dispose() }
}

function Get-CurrentActivity {
    param([object]$Config)
    $result = Invoke-BoundedProcess ([string]$Config.adb_executable) @('-s', [string]$Config.serial, 'shell', 'dumpsys', 'activity', 'activities') 15
    if ($result.TimedOut -or $result.ExitCode -ne 0) { Throw-Safe 'Activity inventory failed safely' }
    $activityInventory = [string]$result.Stdout
    if ($activityInventory.Length -gt 65536) { Throw-Safe 'Activity inventory size is not bounded' }
    $currentMarker = '^\s*(?:mResumedActivity|topResumedActivity|mFocusedActivity)\s*[:=]'
    $currentRecords = @(
        $activityInventory -split "`r?`n" | Where-Object { $_ -match $currentMarker }
    )
    if ($currentRecords.Count -eq 0) { return 'none' }
    if ($currentRecords.Count -ne 1) { Throw-Safe 'Current activity inventory is ambiguous' }
    $currentRecord = [regex]::Match(
        [string]$currentRecords[0],
        '^\s*(?:mResumedActivity|topResumedActivity|mFocusedActivity)\s*[:=]\s*ActivityRecord\{[^}\r\n]*\s(?:u\d+\s+)?(?<component>[A-Za-z][A-Za-z0-9_.]*\/[A-Za-z0-9_.$]+)(?:\s|\})'
    )
    if (-not $currentRecord.Success) { Throw-Safe 'Current activity inventory is malformed' }
    $foregroundComponent = $currentRecord.Groups['component'].Value
    if ($foregroundComponent -ceq $script:MainActivity) { return 'portal' }
    return 'other'
}

function Get-PackageState {
    param([object]$Config)
    $result = Invoke-BoundedProcess ([string]$Config.adb_executable) @('-s', [string]$Config.serial, 'shell', 'pm', 'path', $script:PackageId) 15
    if ($result.TimedOut -or $result.ExitCode -ne 0) { Throw-Safe 'Package inventory failed safely' }
    $packageInventory = [string]$result.Stdout
    if ($packageInventory.Length -gt 4096) { Throw-Safe 'Package inventory is malformed' }
    if ([string]::IsNullOrWhiteSpace($packageInventory)) { return 'absent' }
    $packageLines = @(
        $packageInventory -split "`r?`n" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    )
    if ($packageLines.Count -ne 1 -or [string]$packageLines[0] -notmatch '^package:\S+$') {
        Throw-Safe 'Package inventory is malformed'
    }
    return 'installed'
}

function Invoke-BoundedStatusStage {
    param(
        [scriptblock]$Operation,
        [string[]]$KnownMessages,
        [string]$UnavailableMessage
    )
    try { return & $Operation }
    catch {
        $stageMessage = [string]$_.Exception.Message
        if ($stageMessage -cin $KnownMessages) { throw }
        Throw-Safe $UnavailableMessage
    }
}

function Invoke-Status {
    param([object]$Config)
    $null = Invoke-BoundedStatusStage {
        Assert-OnlyApprovedSerial $Config
    } @(
        'ADB inventory failed safely',
        'ADB serial state is not ready',
        'ADB serial inventory is not exact'
    ) 'ADB inventory failed safely'
    $package = Invoke-BoundedStatusStage {
        Get-PackageState $Config
    } @(
        'Package inventory failed safely',
        'Package inventory is malformed'
    ) 'Package inventory failed safely'
    $activity = Invoke-BoundedStatusStage {
        Get-CurrentActivity $Config
    } @(
        'Activity inventory failed safely',
        'Activity inventory size is not bounded',
        'Current activity inventory is ambiguous',
        'Current activity inventory is malformed'
    ) 'Activity inventory failed safely'
    if ($package -eq 'absent' -or $activity -ne 'portal') {
        $boundedState = if ($package -eq 'absent') {
            'package_absent'
        }
        elseif ($activity -eq 'other') {
            'portal_background'
        }
        else {
            'portal_stopped'
        }
        return [ordered]@{
            action = 'status'
            result = 'observed'
            package = $package
            activity = $activity
            semantic_state = $boundedState
            login = 0
            basic = 0
            officer = 0
            report_enabled = 0
            report_disabled = 0
        }
    }
    $ui = Invoke-BoundedStatusStage {
        Get-AllowlistedUiCounts $Config
    } @(
        'Accessibility inventory failed safely',
        'Accessibility inventory size is not bounded',
        'Accessibility inventory is malformed',
        'Accessibility foreground state is not exact'
    ) 'Accessibility inventory failed safely'
    return [ordered]@{
        action = 'status'
        result = 'observed'
        package = $package
        activity = $activity
        semantic_state = $ui.semantic_state
        login = $ui.login
        basic = $ui.basic
        officer = $ui.officer
        report_enabled = $ui.report_enabled
        report_disabled = $ui.report_disabled
    }
}

function Get-AllowlistedUiCounts {
    param([object]$Config)
    $result = Invoke-BoundedProcess ([string]$Config.adb_executable) @('-s', [string]$Config.serial, 'exec-out', 'uiautomator', 'dump', '/dev/tty') 15
    if ($result.TimedOut -or $result.ExitCode -ne 0) { Throw-Safe 'Accessibility inventory failed safely' }
    $raw = [string]$result.Stdout
    if ($raw.Length -lt 1 -or $raw.Length -gt 65536) { Throw-Safe 'Accessibility inventory size is not bounded' }
    $start = $raw.IndexOf('<hierarchy', [System.StringComparison]::Ordinal)
    $endMarker = '</hierarchy>'
    $end = $raw.IndexOf($endMarker, [System.StringComparison]::Ordinal)
    if ($start -lt 0 -or $end -lt $start -or $raw.IndexOf('<hierarchy', $start + 1, [System.StringComparison]::Ordinal) -ge 0) {
        Throw-Safe 'Accessibility inventory is malformed'
    }
    $settings = [System.Xml.XmlReaderSettings]::new()
    $settings.DtdProcessing = [System.Xml.DtdProcessing]::Prohibit
    $settings.XmlResolver = $null
    $settings.MaxCharactersInDocument = 65536
    $reader = $null
    try {
        $reader = [System.Xml.XmlReader]::Create(
            [System.IO.StringReader]::new($raw.Substring($start, $end - $start + $endMarker.Length)),
            $settings
        )
        $document = [System.Xml.XmlDocument]::new()
        $document.XmlResolver = $null
        $document.Load($reader)
    }
    catch { Throw-Safe 'Accessibility inventory is malformed' }
    finally { if ($null -ne $reader) { $reader.Dispose() } }
    $nodes = @($document.SelectNodes('//node'))
    $labels = @(
        $nodes |
            ForEach-Object { [string]$_.GetAttribute('content-desc') } |
            Where-Object { $_ }
    )
    $basicDisabledLabel = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('5YG16Yyv5qyK6ZmQ5oqV5b2x77ya5LiA6Iis5L2/55So6ICF77yb5aCx6KGo6K6A5Y+W77ya5YGc55So'))
    $officerEnabledLabel = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('5YG16Yyv5qyK6ZmQ5oqV5b2x77ya5bm56YOo77yb5aCx6KGo6K6A5Y+W77ya5ZWf55So'))
    $officerDisabledLabel = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('5YG16Yyv5qyK6ZmQ5oqV5b2x77ya5bm56YOo77yb5aCx6KGo6K6A5Y+W77ya5YGc55So'))
    $loginLabel = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('TElORSDnmbvlhaU='))
    $basicDisabled = @($labels | Where-Object { $_ -ceq $basicDisabledLabel }).Count
    $officerEnabled = @($labels | Where-Object { $_ -ceq $officerEnabledLabel }).Count
    $officerDisabled = @($labels | Where-Object { $_ -ceq $officerDisabledLabel }).Count
    $login = @(
        $nodes | Where-Object {
            [string]$_.GetAttribute('package') -ceq $script:PackageId -and
            [string]$_.GetAttribute('class') -ceq 'android.widget.Button' -and
            [string]$_.GetAttribute('content-desc') -ceq $loginLabel -and
            [string]$_.GetAttribute('enabled') -ceq 'true' -and
            [string]$_.GetAttribute('clickable') -ceq 'true'
        }
    ).Count
    if (($login + $basicDisabled + $officerEnabled + $officerDisabled) -ne 1) {
        Throw-Safe 'Accessibility foreground state is not exact'
    }
    $semanticState = if ($login -eq 1) {
        'logged_out'
    }
    elseif ($basicDisabled -eq 1) {
        'basic'
    }
    elseif ($officerEnabled -eq 1) {
        'officer_report_enabled'
    }
    else {
        'officer_report_disabled'
    }
    return [ordered]@{
        semantic_state = $semanticState
        login = $login
        basic = $basicDisabled
        officer = $officerEnabled + $officerDisabled
        report_enabled = $officerEnabled
        report_disabled = $basicDisabled + $officerDisabled
    }
}

function Enter-TaskLock {
    param([object]$Config)
    $root = Assert-TaskPath ([string]$Config.temp_root) $script:TaskTempRoot -AllowRoot
    [System.IO.Directory]::CreateDirectory($root) | Out-Null
    $lock = $root.TrimEnd('\') + '.lock'
    try { return [System.IO.File]::Open($lock, 'CreateNew', 'Write', 'None') }
    catch { Throw-Safe 'Task launcher lock already exists' }
}

function Remove-TaskLock {
    param([object]$Config, [System.IO.FileStream]$Lock)
    if ($null -ne $Lock) { $Lock.Dispose() }
    $path = ([string]$Config.temp_root).TrimEnd('\') + '.lock'
    if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force }
}

function Invoke-ApkToolWithApprovedJava {
    param(
        [object]$Config,
        [string]$Executable,
        [string[]]$Arguments
    )
    $childEnvironment = $null
    $configuredJavaHome = $null
    $configuredSystemRoot = $null
    $javaHome = $null
    $javaBin = $null
    $systemRoot = $null
    $system32 = $null
    $trustedSystemRoot = $null
    try {
        $configuredJavaHome = [string]$Config.java_home
        if (-not [System.IO.Path]::IsPathRooted($configuredJavaHome)) {
            Throw-Safe 'Approved Java home is invalid'
        }
        try { $javaHome = [System.IO.Path]::GetFullPath($configuredJavaHome).TrimEnd('\') }
        catch { Throw-Safe 'Approved Java home is invalid' }
        if (-not $javaHome.StartsWith('E:\', [System.StringComparison]::OrdinalIgnoreCase)) {
            Throw-Safe 'Approved Java home is invalid'
        }
        $javaBin = [System.IO.Path]::GetFullPath((Join-Path $javaHome 'bin'))
        $configuredSystemRoot = [string]$env:SystemRoot
        if ($configuredSystemRoot -notmatch '^[A-Za-z]:\\Windows$') {
            Throw-Safe 'Approved Windows root is invalid'
        }
        try {
            $systemRoot = [System.IO.Path]::GetFullPath($configuredSystemRoot).TrimEnd('\')
            $trustedSystemRoot = [System.IO.Path]::GetFullPath(
                [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Windows)
            ).TrimEnd('\')
        }
        catch { Throw-Safe 'Approved Windows root is invalid' }
        if (-not [string]::Equals($systemRoot, $trustedSystemRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            Throw-Safe 'Approved Windows root is invalid'
        }
        $system32 = [System.IO.Path]::GetFullPath((Join-Path $systemRoot 'System32'))
        $childEnvironment = @{
            JAVA_HOME = $javaHome
            PATH = $javaBin + [System.IO.Path]::PathSeparator + $system32
        }
        return Invoke-BoundedProcess $Executable $Arguments 30 $childEnvironment
    }
    finally {
        if ($null -ne $childEnvironment) { $childEnvironment.Clear() }
        $childEnvironment = $null
        $Arguments = $null
        $configuredJavaHome = $null
        $configuredSystemRoot = $null
        $javaHome = $null
        $javaBin = $null
        $systemRoot = $null
        $system32 = $null
        $trustedSystemRoot = $null
    }
}

function Get-ApkSignerFingerprint {
    param([object]$Config, [string]$ApkPath)
    $result = Invoke-ApkToolWithApprovedJava $Config ([string]$Config.apksigner_executable) @('verify', '--print-certs', $ApkPath)
    if ($result.TimedOut -or $result.ExitCode -ne 0) { Throw-Safe 'APK signer verification failed safely' }
    $certificateMatches = [regex]::Matches($result.Stdout, '(?im)certificate SHA-256 digest:\s*([0-9a-f:]{64,95})')
    if ($certificateMatches.Count -ne 1) { Throw-Safe 'APK signer result is not exact' }
    return ($certificateMatches[0].Groups[1].Value -replace ':', '').ToUpperInvariant()
}

function Get-ApkPackageIdentity {
    param([object]$Config, [string]$ApkPath)
    $result = Invoke-ApkToolWithApprovedJava $Config ([string]$Config.apkanalyzer_executable) @('manifest', 'application-id', $ApkPath)
    if ($result.TimedOut -or $result.ExitCode -ne 0) { Throw-Safe 'APK package inspection failed safely' }
    $lines = @($result.Stdout -split "`r?`n" | Where-Object { $_.Trim().Length -gt 0 })
    if ($lines.Count -ne 1 -or $lines[0].Trim() -notmatch '^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+$') {
        Throw-Safe 'APK package identity is malformed or ambiguous'
    }
    $package = $lines[0].Trim()
    if ($package -cne $script:PackageId) { Throw-Safe 'APK package identity does not match' }
    return $package
}

function Get-AllowlistedDebugSigner {
    param([object]$Config)
    $found = @()
    foreach ($androidHome in @($Config.android_user_homes)) {
        $keystore = Join-Path ([string]$androidHome) 'debug.keystore'
        if (-not (Test-Path -LiteralPath $keystore -PathType Leaf)) { continue }
        $result = Invoke-BoundedProcess ([string]$Config.keytool_executable) @('-list', '-v', '-keystore', $keystore, '-alias', 'androiddebugkey', '-storepass', 'android', '-keypass', 'android') 30
        if ($result.TimedOut -or $result.ExitCode -ne 0) { Throw-Safe 'Debug signer inventory failed safely' }
        $certificateMatches = [regex]::Matches($result.Stdout, '(?im)SHA256:\s*([0-9A-F:]{64,95})')
        if ($certificateMatches.Count -ne 1) { Throw-Safe 'Debug signer inventory is not exact' }
        $found += [pscustomobject]@{
            Fingerprint = (($certificateMatches[0].Groups[1].Value -replace ':', '').ToUpperInvariant())
            AndroidUserHome = [string]$androidHome
        }
    }
    if ($found.Count -ne 1 -or @($Config.signer_allowlist).Count -ne 1 -or [string]$found[0].Fingerprint -cne [string]$Config.signer_allowlist[0]) {
        Throw-Safe 'Exactly one allowlisted debug signer is required'
    }
    return $found[0]
}

function Get-ArtifactPath {
    param([object]$Config)
    $root = Assert-TaskPath ([string]$Config.evidence_root) $script:TaskEvidenceRoot -AllowRoot
    $artifact = [System.IO.Path]::GetFullPath((Join-Path $root ([string]$Config.artifact_relative_path)))
    if (-not $artifact.StartsWith($root + '\', [System.StringComparison]::OrdinalIgnoreCase)) { Throw-Safe 'Artifact path escapes the task-owned evidence root' }
    return $artifact
}

function Get-FlutterDefineArguments {
    param(
        [System.Collections.IDictionary]$Values,
        [string]$SelectedMode
    )
    if ($null -eq $Values) { Throw-Safe 'Flutter define set is invalid' }
    if ($SelectedMode -eq 'fake') {
        $expectedKeys = @('APP_FLAVOR', 'CLIENT_MODE')
        $validValues = (
            [string]$Values['APP_FLAVOR'] -ceq 'development' -and
            [string]$Values['CLIENT_MODE'] -ceq 'fake'
        )
    }
    elseif ($SelectedMode -eq 'staging') {
        $expectedKeys = @('APP_FLAVOR', 'CLIENT_MODE', 'API_BASE_URL', 'LINE_CHANNEL_ID')
        $validValues = (
            [string]$Values['APP_FLAVOR'] -ceq 'staging' -and
            [string]$Values['CLIENT_MODE'] -ceq 'real' -and
            [string]$Values['API_BASE_URL'] -cmatch '^https://[A-Za-z0-9.-]+$' -and
            [string]$Values['LINE_CHANNEL_ID'] -cmatch '^[1-9][0-9]{4,19}$'
        )
    }
    else {
        Throw-Safe 'Flutter define set is invalid'
    }
    $actualKeys = @($Values.Keys | ForEach-Object { [string]$_ })
    if ($actualKeys.Count -ne $expectedKeys.Count) { Throw-Safe 'Flutter define set is invalid' }
    for ($index = 0; $index -lt $expectedKeys.Count; $index++) {
        if ([string]$actualKeys[$index] -cne [string]$expectedKeys[$index]) { Throw-Safe 'Flutter define set is invalid' }
    }
    if (-not $validValues) { Throw-Safe 'Flutter define set is invalid' }
    return [string[]]@($expectedKeys | ForEach-Object { '--dart-define=' + $_ + '=' + [string]$Values[$_] })
}

function Invoke-FlutterBuildProcess {
    param(
        [object]$Config,
        [System.Collections.IDictionary]$Values,
        [string]$SelectedMode,
        [string]$WorkingDirectory,
        [string]$AndroidUserHome
    )
    $defineArguments = $null
    $buildArguments = $null
    $tempRoot = $null
    $appDataRoot = $null
    try {
        $defineArguments = @(Get-FlutterDefineArguments $Values $SelectedMode)
        $tempRoot = Assert-TaskPath ([string]$Config.temp_root) $script:TaskTempRoot -AllowRoot
        $appDataRoot = Assert-TaskPath (Join-Path $tempRoot 'flutter-appdata') $tempRoot
        [System.IO.Directory]::CreateDirectory($appDataRoot) | Out-Null
        $buildArguments = @('--suppress-analytics', 'build', 'apk', '--debug', '--target-platform', 'android-x64') + $defineArguments
        return Invoke-BoundedProcess ([string]$Config.flutter_executable) $buildArguments 600 @{
            APPDATA = $appDataRoot
            ANDROID_SDK_ROOT = [string]$Config.android_sdk_root
            ANDROID_HOME = [string]$Config.android_sdk_root
            JAVA_HOME = [string]$Config.java_home
            ANDROID_USER_HOME = $AndroidUserHome
            PUB_CACHE = [string]$Config.pub_cache
            GRADLE_USER_HOME = [string]$Config.gradle_user_home
        } $WorkingDirectory
    }
    finally {
        if ($null -ne $defineArguments) { [System.Array]::Clear($defineArguments, 0, $defineArguments.Length) }
        if ($null -ne $buildArguments) { [System.Array]::Clear($buildArguments, 0, $buildArguments.Length) }
        if ($null -ne $Values) { $Values.Clear() }
        $defineArguments = $null
        $buildArguments = $null
        $tempRoot = $null
        $appDataRoot = $null
    }
}

function Invoke-SignerCheck {
    param([object]$Config)
    Assert-OnlyApprovedSerial $Config
    $artifact = Get-ArtifactPath $Config
    if (-not (Test-Path -LiteralPath $artifact -PathType Leaf)) { Throw-Safe 'Fresh APK artifact is unavailable' }
    [void](Get-ApkPackageIdentity $Config $artifact)
    $approvedSigner = Get-AllowlistedDebugSigner $Config
    $allowed = [string]$approvedSigner.Fingerprint
    $artifactSigner = Get-ApkSignerFingerprint $Config $artifact
    if ($artifactSigner -cne $allowed) { Throw-Safe 'Artifact signer does not match the allowlist' }
    $tempRoot = Assert-TaskPath ([string]$Config.temp_root) $script:TaskTempRoot -AllowRoot
    [System.IO.Directory]::CreateDirectory($tempRoot) | Out-Null
    $installed = Join-Path $tempRoot 'installed.apk'
    if (Test-Path -LiteralPath $installed) { Throw-Safe 'Stale installed APK evidence exists' }
    try {
        $path = Invoke-BoundedProcess ([string]$Config.adb_executable) @('-s', [string]$Config.serial, 'shell', 'pm', 'path', $script:PackageId) 15
        if ($path.TimedOut -or $path.ExitCode -ne 0 -or $path.Stdout.Trim() -notmatch '^package:(/[^\r\n]+)$') { Throw-Safe 'Installed package path is unavailable' }
        $pull = Invoke-BoundedProcess ([string]$Config.adb_executable) @('-s', [string]$Config.serial, 'pull', $Matches[1], $installed) 60
        if ($pull.TimedOut -or $pull.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $installed -PathType Leaf)) { Throw-Safe 'Installed APK could not be inspected' }
        $installedSigner = Get-ApkSignerFingerprint $Config $installed
        if ($installedSigner -cne $allowed) { Throw-Safe 'Installed package signer does not match the allowlist' }
        return [ordered]@{ action = 'signer-check'; result = 'matched'; signer_sha256 = $allowed }
    }
    finally {
        if (Test-Path -LiteralPath $installed) { Remove-Item -LiteralPath $installed -Force }
    }
}

function Invoke-Build {
    param([object]$Config, [string]$SelectedMode, [string]$ExpectedCommit)
    Assert-Snapshot $Config $ExpectedCommit
    $artifact = Get-ArtifactPath $Config
    $buildOutput = Join-Path ([string]$Config.snapshot_root) 'clients\flutter_app\build\app\outputs\flutter-apk\app-debug.apk'
    if ((Test-Path -LiteralPath $artifact) -or (Test-Path -LiteralPath $buildOutput)) { Throw-Safe 'Stale APK artifact must be removed by bounded cleanup first' }
    $approvedSigner = Get-AllowlistedDebugSigner $Config
    $tempRoot = Assert-TaskPath ([string]$Config.temp_root) $script:TaskTempRoot -AllowRoot
    $evidenceRoot = Assert-TaskPath ([string]$Config.evidence_root) $script:TaskEvidenceRoot -AllowRoot
    [System.IO.Directory]::CreateDirectory($tempRoot) | Out-Null
    [System.IO.Directory]::CreateDirectory($evidenceRoot) | Out-Null
    $manifest = Join-Path $evidenceRoot 'artifact-manifest.json'
    try {
        if ($SelectedMode -eq 'fake') {
            $values = [ordered]@{ APP_FLAVOR = 'development'; CLIENT_MODE = 'fake' }
        }
        else {
            $origin = [Environment]::GetEnvironmentVariable('MOBILE_STAGING_PUBLIC_ORIGIN', 'Process')
            $channel = [Environment]::GetEnvironmentVariable('MOBILE_STAGING_LINE_CHANNEL_ID', 'Process')
            if ($origin -notmatch '^https://[A-Za-z0-9.-]+$' -or $channel -notmatch '^[1-9][0-9]{4,19}$') { Throw-Safe 'Private staging build inputs are unavailable or malformed' }
            $values = [ordered]@{ APP_FLAVOR = 'staging'; CLIENT_MODE = 'real'; API_BASE_URL = $origin; LINE_CHANNEL_ID = $channel }
        }
        $appRoot = Join-Path ([string]$Config.snapshot_root) 'clients\flutter_app'
        $result = Invoke-FlutterBuildProcess $Config $values $SelectedMode $appRoot ([string]$approvedSigner.AndroidUserHome)
        if ($result.TimedOut -or $result.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $buildOutput -PathType Leaf)) { Throw-Safe 'Flutter build failed safely' }
        Move-Item -LiteralPath $buildOutput -Destination $artifact
        $package = Get-ApkPackageIdentity $Config $artifact
        $fingerprint = Get-ApkSignerFingerprint $Config $artifact
        if ($fingerprint -cne [string]$approvedSigner.Fingerprint) { Throw-Safe 'Fresh artifact signer is not allowlisted' }
        $hash = (Get-FileHash -LiteralPath $artifact -Algorithm SHA256).Hash
        $evidence = [ordered]@{
            accepted_commit = $ExpectedCommit
            mode = $SelectedMode
            package = $package
            artifact_sha256 = $hash
            signer_sha256 = $fingerprint
            classification = 'PASS'
            retention_owner = 'TASK-123'
        }
        [System.IO.File]::WriteAllText($manifest, ($evidence | ConvertTo-Json -Compress), [System.Text.UTF8Encoding]::new($false))
        return [ordered]@{ action = 'build'; result = 'built'; commit = $ExpectedCommit; mode = $SelectedMode; package = $package; artifact_sha256 = $hash; signer_sha256 = $fingerprint }
    }
    catch {
        if (Test-Path -LiteralPath $artifact) { Remove-Item -LiteralPath $artifact -Force }
        throw
    }
    finally {
        $origin = $null
        $channel = $null
        $values = $null
        $result = $null
        if (Test-Path -LiteralPath $buildOutput) { Remove-Item -LiteralPath $buildOutput -Force }
    }
}

function Invoke-Install {
    param([object]$Config, [bool]$KeepSession)
    if (-not $KeepSession) { Throw-Safe 'Install requires explicit session preservation' }
    [void](Invoke-SignerCheck $Config)
    $artifact = Get-ArtifactPath $Config
    $result = Invoke-BoundedProcess ([string]$Config.adb_executable) @('-s', [string]$Config.serial, 'install', '-r', $artifact) 120
    if ($result.TimedOut -or $result.ExitCode -ne 0 -or $result.Stdout -notmatch '(?m)^Success\s*$') { Throw-Safe 'Session-preserving install failed safely' }
    return [ordered]@{ action = 'install'; result = 'replaced'; session = 'preserved' }
}

function Get-AirplaneState {
    param([object]$Config)
    $result = Invoke-BoundedProcess ([string]$Config.adb_executable) @('-s', [string]$Config.serial, 'shell', 'settings', 'get', 'global', 'airplane_mode_on') 10
    if ($result.TimedOut -or $result.ExitCode -ne 0 -or $result.Stdout.Trim() -notmatch '^[01]$') { Throw-Safe 'Network state is unknown' }
    return $result.Stdout.Trim()
}

function Set-AirplaneState {
    param([object]$Config, [string]$State)
    $verb = if ($State -eq '1') { 'enable' } else { 'disable' }
    $result = Invoke-BoundedProcess ([string]$Config.adb_executable) @('-s', [string]$Config.serial, 'shell', 'cmd', 'connectivity', 'airplane-mode', $verb) 15
    if ($result.TimedOut -or $result.ExitCode -ne 0) { Throw-Safe 'Network state change failed safely' }
}

function Invoke-ColdLaunch {
    param([object]$Config)
    Assert-OnlyApprovedSerial $Config
    $original = Get-AirplaneState $Config
    $changed = $false
    try {
        if ($original -eq '1') { Set-AirplaneState $Config '0'; $changed = $true }
        $stop = Invoke-BoundedProcess ([string]$Config.adb_executable) @('-s', [string]$Config.serial, 'shell', 'am', 'force-stop', $script:PackageId) 15
        if ($stop.TimedOut -or $stop.ExitCode -ne 0) { Throw-Safe 'Package stop failed safely' }
        $launch = Invoke-BoundedProcess ([string]$Config.adb_executable) @('-s', [string]$Config.serial, 'shell', 'am', 'start', '-W', '-a', 'android.intent.action.MAIN', '-c', 'android.intent.category.LAUNCHER', '-n', $script:MainActivity) 30
        $activity = Get-CurrentActivity $Config
        $pidResult = Invoke-BoundedProcess ([string]$Config.adb_executable) @('-s', [string]$Config.serial, 'shell', 'pidof', $script:PackageId) 10
        $running = (-not $pidResult.TimedOut -and $pidResult.ExitCode -eq 0 -and $pidResult.Stdout.Trim() -match '^[0-9]+$')
        if ($activity -eq 'other') { Throw-Safe 'Launcher activity is anomalous' }
        if ($launch.TimedOut) {
            return [ordered]@{ action = 'cold-launch'; result = $(if ($running -and $activity -eq 'portal') { 'timeout_but_running' } else { 'timeout_unknown' }); retry = 'forbidden' }
        }
        if ($launch.ExitCode -ne 0 -or -not $running -or $activity -ne 'portal') { Throw-Safe 'Cold launch did not reach the approved activity' }
        return [ordered]@{ action = 'cold-launch'; result = 'running'; retry = 'not_needed' }
    }
    finally {
        if ($changed) { Set-AirplaneState $Config $original }
    }
}

function Invoke-Health {
    param([object]$Config, [bool]$AllowPublic)
    Assert-OnlyApprovedSerial $Config
    if (-not $AllowPublic) { return [ordered]@{ action = 'health'; result = 'local_ready'; public_request = 'none' } }
    $origin = [Environment]::GetEnvironmentVariable('MOBILE_STAGING_PUBLIC_ORIGIN', 'Process')
    if ($origin -notmatch '^https://[A-Za-z0-9.-]+$') { Throw-Safe 'Public health origin is unavailable or malformed' }
    $client = [System.Net.Http.HttpClient]::new()
    $client.Timeout = [TimeSpan]::FromSeconds(10)
    try {
        $request = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::Get, "$origin/health")
        $response = $client.SendAsync($request, [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead).GetAwaiter().GetResult()
        $status = [int]$response.StatusCode
        $response.Dispose()
        if ($status -lt 200 -or $status -ge 300) { Throw-Safe 'Public health status is not successful' }
        return [ordered]@{ action = 'health'; result = 'public_ready'; status_class = '2xx' }
    }
    catch [System.InvalidOperationException] { throw }
    catch { Throw-Safe 'Public health request failed safely' }
    finally { $client.Dispose() }
}

function Invoke-Stop {
    param([object]$Config)
    Assert-OnlyApprovedSerial $Config
    $result = Invoke-BoundedProcess ([string]$Config.adb_executable) @('-s', [string]$Config.serial, 'shell', 'am', 'force-stop', $script:PackageId) 15
    if ($result.TimedOut -or $result.ExitCode -ne 0) { Throw-Safe 'Package stop failed safely' }
    return [ordered]@{ action = 'stop'; result = 'stopped'; package = $script:PackageId }
}

function Invoke-Cleanup {
    param([object]$Config, [bool]$RemoveEvidence)
    $temp = Assert-TaskPath ([string]$Config.temp_root) $script:TaskTempRoot -AllowRoot
    $evidence = Assert-TaskPath ([string]$Config.evidence_root) $script:TaskEvidenceRoot -AllowRoot
    if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Recurse -Force }
    if ($RemoveEvidence -and (Test-Path -LiteralPath $evidence)) { Remove-Item -LiteralPath $evidence -Recurse -Force }
    return [ordered]@{ action = 'cleanup'; result = 'removed_task_owned'; evidence = $(if ($RemoveEvidence) { 'removed' } else { 'retained' }) }
}

function ConvertFrom-PrivateSecureString {
    param([Security.SecureString]$Value)
    $pointer = [IntPtr]::Zero
    try {
        $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    finally {
        if ($pointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
    }
}

function Load-PrivateApproval {
    param([string]$Path, [string]$ExpectedCommit)
    if (-not $Path -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) { Throw-Safe 'Private candidate approval is required' }
    try { $approval = Get-Content -LiteralPath $Path -Encoding UTF8 -Raw | ConvertFrom-Json }
    catch { Throw-Safe 'Private candidate approval is unavailable or malformed' }
    $required = @(
        'owner_approved', 'project', 'region', 'service', 'approved_commit',
        'approval_phase', 'build_id', 'image_uri', 'image_digest', 'mode',
        'candidate_revision', 'rollback_revision', 'database_identity_sha256',
        'production_database_identity_sha256', 'database_provider',
        'database_resource_id', 'database_alias', 'max_instances',
        'service_account', 'build_service_account', 'runtime_secret_refs',
        'mobile_api_audience'
    )
    Assert-ExactProperties $approval $required 'Private candidate approval'
    if (
        $approval.approval_phase -cne 'candidate' -or
        $approval.owner_approved -ne $true -or
        $approval.project -ceq $script:ProductionProject -or
        [string]$approval.project -notmatch '^[a-z][a-z0-9-]{4,28}[a-z0-9]$' -or
        $approval.region -cne 'asia-east1' -or
        $approval.service -cne 'mobile-api-staging' -or
        $approval.approved_commit -cne $ExpectedCommit -or
        [string]$approval.approved_commit -notmatch $script:FullShaPattern
    ) {
        Throw-Safe 'Private candidate approval is not exact'
    }
    $secretNames = @($approval.runtime_secret_refs.PSObject.Properties.Name | Sort-Object)
    $expectedSecretNames = @('MOBILE_ACCESS_SIGNING_KEY', 'MOBILE_REFRESH_REPLAY_KEY', 'PORTAL_DATA_DATABASE_URL' | Sort-Object)
    if (($secretNames -join "`n") -cne ($expectedSecretNames -join "`n")) { Throw-Safe 'Private candidate Secret references are not exact' }
    foreach ($property in $approval.runtime_secret_refs.PSObject.Properties) {
        if ([string]$property.Value -notmatch '^[a-z][a-z0-9_-]{2,126}:[1-9][0-9]*$') { Throw-Safe 'Private candidate Secret reference is invalid' }
    }
    if (
        [string]$approval.database_identity_sha256 -notmatch '^[0-9a-f]{64}$' -or
        [string]$approval.production_database_identity_sha256 -notmatch '^[0-9a-f]{64}$' -or
        $approval.database_identity_sha256 -ceq $approval.production_database_identity_sha256 -or
        [string]$approval.mobile_api_audience -notmatch '^[1-9][0-9]{4,19}$'
    ) { Throw-Safe 'Private candidate identity metadata is invalid' }
    $reference = [string]$approval.runtime_secret_refs.PORTAL_DATA_DATABASE_URL
    if ($reference -notmatch '^([a-z][a-z0-9_-]{2,126}):([1-9][0-9]*)$') { Throw-Safe 'Approved database Secret reference is invalid' }
    return [pscustomobject]@{ Project = [string]$approval.project; SecretName = $Matches[1]; SecretVersion = $Matches[2] }
}

function Test-OwnerInteractiveConsole {
    try { return [Environment]::UserInteractive -and -not [Console]::IsInputRedirected -and -not [Console]::IsOutputRedirected }
    catch { return $false }
}

function Resolve-PrivateExecutable {
    param([string]$Name)
    $commands = @(Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue)
    if ($commands.Count -ne 1 -or -not [System.IO.Path]::IsPathRooted([string]$commands[0].Source)) {
        Throw-Safe 'Owner-private executable is unavailable or ambiguous'
    }
    return [string]$commands[0].Source
}

function Invoke-PrivateOperator {
    param(
        [string]$PythonExecutable,
        [string]$PrivateApprovalPath,
        [string]$OperatorFlag,
        [hashtable]$ChildEnvironment,
        [string]$WorkingDirectory
    )
    $result = Invoke-BoundedProcess $PythonExecutable @('-m', 'tools.mobile_staging_data', '--approval', $PrivateApprovalPath, $OperatorFlag) 120 $ChildEnvironment $WorkingDirectory
    if ($result.TimedOut) { Throw-Safe 'Private staging data action timed out' }
    if ($result.ExitCode -ne 0) { Throw-Safe 'Private staging data action failed safely' }
    try { $parsed = $result.Stdout.Trim() | ConvertFrom-Json }
    catch { Throw-Safe 'Private staging data result is malformed' }
    if ([string]$parsed.state -notin @('baseline', 'granted', 'restored')) { Throw-Safe 'Private staging data state is not allowlisted' }
    return $parsed
}

function Invoke-PrivateAction {
    param([object]$Config, [string]$PrivateAction, [string]$PrivateApprovalPath, [string]$ExpectedCommit)
    if (-not (Test-OwnerInteractiveConsole)) { Throw-Safe 'OWNER_ACTION_REQUIRED' }
    $approval = Load-PrivateApproval $PrivateApprovalPath $ExpectedCommit
    $secureSubject = Read-Host 'Private tester subject' -AsSecureString
    $subject = $null
    $dsn = $null
    $secret = $null
    $confirmation = $null
    $child = @{}
    try {
        $subject = ConvertFrom-PrivateSecureString $secureSubject
        if ([string]::IsNullOrWhiteSpace($subject)) { Throw-Safe 'Private tester subject is required' }
        $gcloudExecutable = Resolve-PrivateExecutable 'gcloud.cmd'
        $pythonExecutable = Resolve-PrivateExecutable 'python.exe'
        $secret = Invoke-BoundedProcess $gcloudExecutable @('secrets', 'versions', 'access', $approval.SecretVersion, "--secret=$($approval.SecretName)", "--project=$($approval.Project)") 30
        if ($secret.TimedOut -or $secret.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($secret.Stdout)) { Throw-Safe 'Approved database Secret retrieval failed safely' }
        $dsn = $secret.Stdout.Trim()
        $child['MOBILE_STAGING_DATABASE_URL'] = $dsn
        $child['MOBILE_STAGING_PROVIDER_SUBJECT'] = $subject
        $workingDirectory = [string]$Config.snapshot_root
        $before = Invoke-PrivateOperator $pythonExecutable $PrivateApprovalPath '--inspect-officer' $child $workingDirectory
        if ($PrivateAction -eq 'private-inspect') {
            return [ordered]@{ action = $PrivateAction; result = 'inspected'; state = [string]$before.state }
        }
        $terminalState = if ($PrivateAction -eq 'grant-officer') { 'granted' } else { 'restored' }
        $allowedState = if ($PrivateAction -eq 'grant-officer') { 'baseline' } else { 'granted' }
        if ([string]$before.state -notin @($allowedState, $terminalState)) { Throw-Safe 'Private staging mutation prestate is not exact' }
        $expectedConfirmation = if ($PrivateAction -eq 'grant-officer') { 'GRANT-OFFICER' } else { 'RESTORE-BASIC' }
        $confirmation = Read-Host "Type $expectedConfirmation to continue"
        if ($confirmation -cne $expectedConfirmation) { Throw-Safe 'Owner confirmation did not match' }
        $mutationAttempted = $false
        $reconciled = $false
        if ([string]$before.state -ne $terminalState) {
            $mutationAttempted = $true
            $mutationFlag = if ($PrivateAction -eq 'grant-officer') { '--grant-officer' } else { '--restore-basic' }
            try {
                [void](Invoke-PrivateOperator $pythonExecutable $PrivateApprovalPath $mutationFlag $child $workingDirectory)
            }
            catch {
                $reconciled = $true
                $afterUnknown = Invoke-PrivateOperator $pythonExecutable $PrivateApprovalPath '--inspect-officer' $child $workingDirectory
                if ([string]$afterUnknown.state -ne $terminalState) { Throw-Safe 'Private mutation result requires read-only reconciliation' }
            }
        }
        $after = Invoke-PrivateOperator $pythonExecutable $PrivateApprovalPath '--inspect-officer' $child $workingDirectory
        if ([string]$after.state -ne $terminalState) { Throw-Safe 'Private staging mutation postcheck is not exact' }
        return [ordered]@{
            action = $PrivateAction
            result = $(if ($reconciled) { 'reconciled' } else { 'completed' })
            state = [string]$after.state
            changed = $mutationAttempted
            mutation_attempts = $(if ($mutationAttempted) { 1 } else { 0 })
        }
    }
    finally {
        $child.Clear()
        $dsn = $null
        $subject = $null
        $secret = $null
        $confirmation = $null
        $gcloudExecutable = $null
        $pythonExecutable = $null
        if ($secureSubject -is [System.IDisposable]) { $secureSubject.Dispose() }
    }
}

function Get-FailureClassification {
    param([string]$Message)
    if ($Message -eq 'OWNER_ACTION_REQUIRED') { return 'OWNER_ACTION_REQUIRED' }
    if ($Message -ceq 'Action result is invalid') { return 'FAILED' }
    if ($Message -ceq 'Accessibility foreground state is not exact') { return 'DRIFT' }
    if ($Message -cin @(
        'ADB inventory failed safely',
        'ADB serial state is not ready',
        'ADB serial inventory is not exact',
        'Package inventory failed safely',
        'Package inventory is malformed',
        'Activity inventory failed safely',
        'Activity inventory size is not bounded',
        'Current activity inventory is ambiguous',
        'Current activity inventory is malformed',
        'Accessibility inventory failed safely',
        'Accessibility inventory size is not bounded',
        'Accessibility inventory is malformed'
    )) { return 'FAILED' }
    if ($Message -match '(?i)(timed out|bounded window|timeout)') { return 'TIMEOUT' }
    if ($Message -match '(?i)(drift|not exact|does not match|unknown|stale|dirty|ambiguous|conflicting|escapes|collision)') { return 'DRIFT' }
    return 'FAILED'
}

function Get-FailureReasonCode {
    param([string]$Message)
    if ($Message -eq 'OWNER_ACTION_REQUIRED') { return 'OWNER_ACTION_REQUIRED' }
    if ($Message -ceq 'Action result is invalid') { return 'ACTION_RESULT_INVALID' }
    if ($Message -ceq 'ADB inventory failed safely') { return 'ADB_UNAVAILABLE' }
    if ($Message -cin @(
        'ADB serial state is not ready',
        'ADB serial inventory is not exact'
    )) { return 'ADB_INVALID' }
    if ($Message -ceq 'Package inventory failed safely') { return 'PACKAGE_UNAVAILABLE' }
    if ($Message -ceq 'Package inventory is malformed') { return 'PACKAGE_INVALID' }
    if ($Message -ceq 'Activity inventory failed safely') { return 'ACTIVITY_UNAVAILABLE' }
    if ($Message -cin @(
        'Activity inventory size is not bounded',
        'Current activity inventory is ambiguous',
        'Current activity inventory is malformed'
    )) { return 'ACTIVITY_INVALID' }
    if ($Message -ceq 'Accessibility inventory failed safely') { return 'ACCESSIBILITY_UNAVAILABLE' }
    if ($Message -cin @(
        'Accessibility inventory size is not bounded',
        'Accessibility inventory is malformed'
    )) { return 'ACCESSIBILITY_INVALID' }
    if ($Message -ceq 'Accessibility foreground state is not exact') { return 'SEMANTIC_DRIFT' }
    if ($Message -match '(?i)(launcher config|action is unknown|exact action, mode|conflicting options|full accepted commit|config identity|config fields|artifact path is not exact)') {
        return 'CONFIG_INVALID'
    }
    if ($Message -match '(?i)(snapshot)') { return 'SNAPSHOT_INVALID' }
    if ($Message -match '(?i)(approved E drive|disk threshold)') { return 'DISK_UNAVAILABLE' }
    if ($Message -match '(?i)(task launcher lock)') { return 'LOCK_UNAVAILABLE' }
    if ($Message -match '(?i)(toolchain|approved executable|APK package|APK signer|debug signer|artifact signer)') {
        return 'TOOLCHAIN_UNAVAILABLE'
    }
    if ($Message -match '(?i)(timed out|bounded window|timeout)') { return 'RUNTIME_TIMEOUT' }
    return 'RUNTIME_FAILED'
}

function New-LauncherEnvelope {
    param([string]$SelectedAction, [string]$Classification, [object]$Details)
    $isPrivate = $SelectedAction -in $script:PrivateActions
    return [ordered]@{
        action = $(if ($SelectedAction) { $SelectedAction } else { 'unknown' })
        classification = $Classification
        operator = $(if ($isPrivate) { 'owner' } else { 'agent' })
        owner_gate = $(if ($isPrivate) { 'private-console' } else { 'none' })
        standing_authorization = 'DEC-098'
        stop_only_on = 'wire-or-schema-need|unbounded-fixture-ambiguity|production-secret-external-need'
        report_to = 'main-work'
        retention_owner = 'TASK-123'
        details = $Details
    }
}

function Invoke-MobileStagingMain {
    param(
        [string]$SelectedAction, [string]$SelectedMode, [string]$ExpectedCommit,
        [string]$LauncherConfigPath, [string]$PrivateApprovalPath,
        [bool]$KeepSession, [bool]$AllowPublicHealth, [bool]$RemoveEvidence
    )
    if ($SelectedAction -eq 'help') {
        return [ordered]@{ result = 'available'; actions = @($script:RoutineActions + $script:PrivateActions) }
    }
    if ($SelectedAction -notin @($script:RoutineActions + $script:PrivateActions)) { Throw-Safe 'Action is unknown' }
    if ($SelectedAction -in $script:PrivateActions -and -not (Test-OwnerInteractiveConsole)) { Throw-Safe 'OWNER_ACTION_REQUIRED' }
    if (-not $SelectedMode -or $SelectedMode -notin @('fake', 'staging') -or -not $ExpectedCommit -or -not $LauncherConfigPath) {
        Throw-Safe 'Exact action, mode, full commit and config are required'
    }
    if ($ExpectedCommit -notmatch $script:FullShaPattern) { Throw-Safe 'A full accepted commit SHA is required' }
    $config = Load-LauncherConfig $LauncherConfigPath
    if ($SelectedAction -in @('private-inspect', 'grant-officer', 'restore-basic')) {
        if ($SelectedMode -ne 'staging' -or $KeepSession -or $AllowPublicHealth -or $RemoveEvidence) { Throw-Safe 'Owner-private action received conflicting options' }
        Assert-Snapshot $config $ExpectedCommit
        $privateLock = $null
        try {
            $privateLock = Enter-TaskLock $config
            return Invoke-PrivateAction $config $SelectedAction $PrivateApprovalPath $ExpectedCommit
        }
        finally { if ($null -ne $privateLock) { Remove-TaskLock $config $privateLock } }
    }
    Assert-Snapshot $config $ExpectedCommit
    if ($SelectedAction -in @('preflight', 'status')) {
        if ($KeepSession -or $AllowPublicHealth -or $RemoveEvidence -or $PrivateApprovalPath) { Throw-Safe 'Read-only action received conflicting options' }
        if ($SelectedAction -eq 'preflight') { return Invoke-Preflight $config $ExpectedCommit $SelectedMode }
        return Invoke-Status $config
    }
    if ($PrivateApprovalPath) { Throw-Safe 'Routine action cannot receive private approval' }
    if ($SelectedAction -ne 'install' -and $KeepSession) { Throw-Safe 'Session preservation applies only to install' }
    if ($SelectedAction -ne 'health' -and $AllowPublicHealth) { Throw-Safe 'Public health applies only to health' }
    if ($SelectedAction -eq 'health' -and $AllowPublicHealth -and $SelectedMode -ne 'staging') { Throw-Safe 'Public health requires staging mode' }
    if ($SelectedAction -ne 'cleanup' -and $RemoveEvidence) { Throw-Safe 'Evidence retention applies only to cleanup' }
    $lock = $null
    try {
        if ($SelectedAction -notin @('health')) { $lock = Enter-TaskLock $config }
        switch ($SelectedAction) {
            'avd-start' { return Invoke-AvdStart $config }
            'build' { return Invoke-Build $config $SelectedMode $ExpectedCommit }
            'signer-check' { return Invoke-SignerCheck $config }
            'install' { return Invoke-Install $config $KeepSession }
            'cold-launch' { return Invoke-ColdLaunch $config }
            'health' { return Invoke-Health $config $AllowPublicHealth }
            'stop' { return Invoke-Stop $config }
            'cleanup' { return Invoke-Cleanup $config $RemoveEvidence }
            default { Throw-Safe 'Action is not implemented' }
        }
    }
    finally { if ($null -ne $lock) { Remove-TaskLock $config $lock } }
}

if ($MyInvocation.InvocationName -ne '.') {
    $classification = 'PASS'
    $details = $null
    try {
        $details = Invoke-MobileStagingMain $Action $Mode $Commit $ConfigPath $ApprovalPath ([bool]$PreserveSession) ([bool]$PublicHealth) ([bool]$PurgeEvidence)
        if (
            $null -eq $details -or
            $details -isnot [System.Collections.IDictionary] -or
            -not $details.Contains('result')
        ) { Throw-Safe 'Action result is invalid' }
        $actionResult = [string]$details['result']
        if (
            [string]::IsNullOrWhiteSpace($actionResult) -or
            $actionResult.Length -gt 64 -or
            $actionResult -notmatch '^[a-z][a-z0-9_]*$'
        ) { Throw-Safe 'Action result is invalid' }
        if ($actionResult -match '^timeout') {
            $classification = 'TIMEOUT'
            $details['reason_code'] = 'RUNTIME_TIMEOUT'
        }
    }
    catch {
        $classification = Get-FailureClassification $_.Exception.Message
        $details = [ordered]@{
            result = $classification.ToLowerInvariant()
            reason_code = Get-FailureReasonCode $_.Exception.Message
        }
    }
    $envelope = New-LauncherEnvelope $Action $classification $details
    try { Write-SafeJson $envelope }
    catch {
        $classification = 'FAILED'
        Write-Output '{"action":"unknown","classification":"FAILED","operator":"agent","owner_gate":"none","standing_authorization":"DEC-098","stop_only_on":"wire-or-schema-need|unbounded-fixture-ambiguity|production-secret-external-need","report_to":"main-work","retention_owner":"TASK-123","details":{"result":"failed","reason_code":"OUTPUT_REDACTION_FAILED"}}'
    }
    if ($classification -eq 'PASS') { exit 0 }
    exit 2
}
