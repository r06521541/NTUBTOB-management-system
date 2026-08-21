[CmdletBinding()]
param(
    [string]$Scenario,
    [string]$Mode,
    [string]$Commit,
    [string]$ConfigPath,
    [string]$BrokerConfigPath,
    [string]$CheckpointPath,
    [switch]$Resume
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:HarnessScenarios = @('basic-authorization', 'officer-authorization-roundtrip')
$script:HarnessVocabularyVersion = 'task124-package4-v1'
$script:HarnessPackage = 'tw.org.ntubtob.portal'
$script:HarnessShaPattern = '^[0-9a-f]{40}$'
$script:HarnessFingerprintPattern = '^[A-F0-9]{64}$'
$script:HarnessBrokerOperationIdPattern = '^[A-Za-z0-9_-]{16,64}$'
$script:HarnessColdLaunchResults = @('running', 'timeout_but_running')
$script:HarnessTerminalStatusReasons = @(
    'ADB_UNAVAILABLE', 'ADB_INVALID',
    'PACKAGE_UNAVAILABLE', 'PACKAGE_INVALID',
    'ACTIVITY_UNAVAILABLE', 'ACTIVITY_INVALID',
    'STATUS_HOST_UNAVAILABLE', 'STATUS_CHILD_TIMEOUT', 'STATUS_CHILD_STDERR',
    'STATUS_CHILD_OUTPUT_INVALID', 'STATUS_CHILD_ENVELOPE_INVALID',
    'STATUS_CHILD_RESULT_INVALID'
)
$script:HarnessSteps = @(
    'await_observation', 'await_login', 'broker_gate', 'grant_intent', 'grant_result',
    'grant_reconcile', 'officer_online', 'offline_observed',
    'restore_intent', 'restore_result', 'restore_reconcile',
    'basic_restored', 'logout_intent', 'logout_result', 'logout_reconcile',
    'completed', 'stopped'
)

function Throw-HarnessSafe {
    param([string]$Message)
    throw [System.InvalidOperationException]::new($Message)
}

function Assert-HarnessSafeText {
    param([string]$Text)
    if ($Text -match '(?i)(postgres(?:ql)?://|provider[_ -]?subject|bearer\s|id[_ -]?token|refresh[_ -]?token|assertion|api[_ -]?base[_ -]?url|line[_ -]?channel[_ -]?id|raw\s+xml|logcat|screenshot|endpoint)') {
        Throw-HarnessSafe 'Harness output failed the sensitive-field gate'
    }
}

function Write-HarnessJson {
    param([object]$Value)
    $json = $Value | ConvertTo-Json -Depth 8 -Compress
    Assert-HarnessSafeText $json
    Write-Output $json
}

function New-HarnessEnvelope {
    param([string]$SelectedScenario, [string]$Classification, [string]$OwnerGate, [string]$Step, [string]$Result, [string]$ReasonCode)
    return [ordered]@{
        scenario = $(if ($SelectedScenario) { $SelectedScenario } else { 'unknown' })
        classification = $Classification
        operator = 'agent'
        owner_gate = $OwnerGate
        standing_authorization = 'DEC-098'
        stop_only_on = 'producer-vocabulary-drift|owner-line-login-consent|broker-provisioning|runtime-ambiguity'
        report_to = 'main-work'
        retention_owner = 'TASK-129'
        details = [ordered]@{ step = $Step; result = $Result; reason_code = $ReasonCode }
    }
}

function Get-HarnessFailureClassification {
    param([string]$Message)
    if ($Message -ceq 'STATUS_CHILD_TIMEOUT') { return 'TIMEOUT' }
    if ($Message -cin @(
        'STATUS_HOST_UNAVAILABLE', 'STATUS_CHILD_STDERR',
        'STATUS_CHILD_OUTPUT_INVALID', 'STATUS_CHILD_ENVELOPE_INVALID',
        'STATUS_CHILD_RESULT_INVALID'
    )) { return 'EVIDENCE_GAP' }
    if ($Message -cin @('ADB_UNAVAILABLE', 'PACKAGE_UNAVAILABLE', 'ACTIVITY_UNAVAILABLE')) { return 'EVIDENCE_GAP' }
    if ($Message -cin @('ADB_INVALID', 'PACKAGE_INVALID', 'ACTIVITY_INVALID')) { return 'DRIFT' }
    if ($Message -ceq 'Accessibility inventory failed safely') { return 'EVIDENCE_GAP' }
    if ($Message -ceq 'Accessibility inventory is malformed') { return 'EVIDENCE_GAP' }
    if ($Message -ceq 'Accessibility foreground state is not exact') { return 'DRIFT' }
    if ($Message -match 'Harness status is unavailable') { return 'EVIDENCE_GAP' }
    if ($Message -ceq 'Harness broker provisioning is required') { return 'OWNER_ACTION_REQUIRED' }
    if ($Message -cin @('Harness broker timed out')) { return 'TIMEOUT' }
    if ($Message -cin @('Harness broker is unavailable', 'Harness broker operation result is unknown')) { return 'EVIDENCE_GAP' }
    if ($Message -match 'Harness broker') { return 'DRIFT' }
    if ($Message -match '(?i)(timeout|timed out|bounded window)') { return 'TIMEOUT' }
    if ($Message -match '(?i)(drift|mismatch|malformed|missing|stale|lock|ambiguous|unknown|not exact|invalid|reconcile)') { return 'DRIFT' }
    return 'FAILED'
}

function Get-HarnessFailureReasonCode {
    param([string]$Message)
    if ($Message -cin $script:HarnessTerminalStatusReasons) { return $Message }
    if ($Message -ceq 'Accessibility inventory failed safely') { return 'ACCESSIBILITY_UNAVAILABLE' }
    if ($Message -ceq 'Accessibility inventory is malformed') { return 'ACCESSIBILITY_INVALID' }
    if ($Message -ceq 'Accessibility foreground state is not exact') { return 'SEMANTIC_DRIFT' }
    if ($Message -match 'Harness status is unavailable') { return 'STATUS_UNAVAILABLE' }
    if ($Message -ceq 'Harness broker provisioning is required') { return 'BROKER_PROVISIONING' }
    if ($Message -ceq 'Harness broker timed out') { return 'BROKER_TIMEOUT' }
    if ($Message -ceq 'Harness broker is unavailable') { return 'BROKER_UNAVAILABLE' }
    if ($Message -ceq 'Harness broker operation result is unknown') { return 'BROKER_RESULT_UNKNOWN' }
    if ($Message -ceq 'Harness broker private state is invalid') { return 'BROKER_PRIVATE_STATE_INVALID' }
    if ($Message -match 'Harness broker') { return 'BROKER_DRIFT' }
    if ($Message -match 'Harness action result is invalid') { return 'ACTION_RESULT_INVALID' }
    if ($Message -match 'Harness artifact inspection is unavailable') { return 'ARTIFACT_UNAVAILABLE' }
    if ($Message -match 'Harness artifact provenance is invalid') { return 'ARTIFACT_INVALID' }
    if ($Message -match 'checkpoint binding') { return 'CHECKPOINT_BINDING_DRIFT' }
    if ($Message -match 'checkpoint lock') { return 'LOCK_UNAVAILABLE' }
    if ($Message -match 'checkpoint') { return 'CHECKPOINT_INVALID' }
    if ($Message -match 'producer') { return 'PRODUCER_GAP' }
    if ($Message -match '(?i)(timeout|timed out|bounded window)') { return 'RUNTIME_TIMEOUT' }
    return 'RUNTIME_FAILED'
}

function Get-HarnessFieldNames {
    param([object]$Value)
    if ($Value -is [System.Collections.IDictionary]) { return @($Value.Keys | ForEach-Object { [string]$_ }) }
    return @($Value.PSObject.Properties.Name)
}

function Get-HarnessFunctionScriptBlock {
    param([string]$Name)
    $command = Get-Command $Name -CommandType Function -ErrorAction SilentlyContinue
    if ($null -eq $command) { return $null }
    return $command.ScriptBlock
}

function Assert-HarnessArguments {
    param([string]$SelectedScenario, [string]$SelectedMode, [string]$ExpectedCommit, [string]$LauncherConfigPath, [string]$StatePath)
    if ($SelectedScenario -notin $script:HarnessScenarios) { Throw-HarnessSafe 'Scenario is explicit and required' }
    if ($SelectedMode -ne 'staging') { Throw-HarnessSafe 'Harness requires explicit staging mode' }
    if ($ExpectedCommit -notmatch $script:HarnessShaPattern) { Throw-HarnessSafe 'Harness requires a full accepted commit SHA' }
    if (-not $LauncherConfigPath -or -not $StatePath -or -not [IO.Path]::IsPathRooted($StatePath)) { Throw-HarnessSafe 'Harness config and absolute checkpoint are required' }
}

function Assert-HarnessBinding {
    param([object]$Binding, [string]$ExpectedCommit)
    $expected = @('accepted_sha', 'artifact_sha256', 'signer_sha256', 'package', 'version', 'avd', 'serial', 'vocabulary_version')
    $actual = @(Get-HarnessFieldNames $Binding | Sort-Object)
    if (($actual -join "`n") -cne (($expected | Sort-Object) -join "`n")) { Throw-HarnessSafe 'Harness binding is malformed' }
    if (
        [string]$Binding.accepted_sha -cne $ExpectedCommit -or
        [string]$Binding.artifact_sha256 -notmatch $script:HarnessFingerprintPattern -or
        [string]$Binding.signer_sha256 -notmatch $script:HarnessFingerprintPattern -or
        [string]$Binding.package -cne $script:HarnessPackage -or
        [string]$Binding.version -notmatch '^[0-9A-Za-z._+-]{1,64}$' -or
        [string]$Binding.avd -notmatch '^[A-Za-z0-9._-]{3,64}$' -or
        [string]$Binding.serial -notmatch '^emulator-[0-9]{4,5}$' -or
        [string]$Binding.vocabulary_version -cne $script:HarnessVocabularyVersion
    ) { Throw-HarnessSafe 'Harness binding is malformed' }
}

function Test-HarnessBindingEqual {
    param([object]$Left, [object]$Right)
    foreach ($field in @('accepted_sha', 'artifact_sha256', 'signer_sha256', 'package', 'version', 'avd', 'serial', 'vocabulary_version')) {
        if ([string]$Left.$field -cne [string]$Right.$field) { return $false }
    }
    return $true
}

function Enter-HarnessLock {
    param([string]$StatePath)
    try { return [IO.File]::Open($StatePath + '.lock', 'CreateNew', 'Write', 'None') }
    catch { Throw-HarnessSafe 'Harness checkpoint lock is unavailable' }
}

function Remove-HarnessLock {
    param([string]$StatePath, [IO.FileStream]$Lock)
    if ($null -ne $Lock) { $Lock.Dispose() }
    $lockPath = $StatePath + '.lock'
    if (Test-Path -LiteralPath $lockPath -PathType Leaf) { Remove-Item -LiteralPath $lockPath -Force }
}

function Read-HarnessCheckpoint {
    param([string]$StatePath)
    if (-not (Test-Path -LiteralPath $StatePath -PathType Leaf)) { return $null }
    try { $state = Get-Content -LiteralPath $StatePath -Encoding UTF8 -Raw | ConvertFrom-Json }
    catch { Throw-HarnessSafe 'Harness checkpoint is malformed' }
    $expected = @('schema_version', 'scenario', 'step', 'binding', 'prior_result')
    $actual = @(Get-HarnessFieldNames $state | Sort-Object)
    if (($actual -join "`n") -cne (($expected | Sort-Object) -join "`n") -or $state.schema_version -ne 2 -or $state.scenario -notin $script:HarnessScenarios -or $state.step -notin $script:HarnessSteps -or [string]$state.prior_result -notmatch '^[a-z_]{1,64}$') {
        Throw-HarnessSafe 'Harness checkpoint is malformed'
    }
    Assert-HarnessBinding $state.binding ([string]$state.binding.accepted_sha)
    return $state
}

function Save-HarnessCheckpoint {
    param([string]$StatePath, [string]$SelectedScenario, [string]$Step, [object]$Binding, [string]$PriorResult)
    if ($Step -notin $script:HarnessSteps -or $PriorResult -notmatch '^[a-z_]{1,64}$') { Throw-HarnessSafe 'Harness checkpoint is malformed' }
    $directory = [IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($StatePath))
    if (-not (Test-Path -LiteralPath $directory -PathType Container)) { Throw-HarnessSafe 'Harness checkpoint directory is unavailable' }
    $state = [ordered]@{
        schema_version = 2
        scenario = $SelectedScenario
        step = $Step
        binding = [ordered]@{
            accepted_sha = [string]$Binding.accepted_sha; artifact_sha256 = [string]$Binding.artifact_sha256
            signer_sha256 = [string]$Binding.signer_sha256; package = [string]$Binding.package
            version = [string]$Binding.version; avd = [string]$Binding.avd; serial = [string]$Binding.serial
            vocabulary_version = [string]$Binding.vocabulary_version
        }
        prior_result = $PriorResult
    }
    $temporaryPath = $StatePath + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
    $backupPath = $StatePath + '.' + [Guid]::NewGuid().ToString('N') + '.bak'
    try {
        $json = $state | ConvertTo-Json -Depth 4 -Compress
        Assert-HarnessSafeText $json
        [IO.File]::WriteAllText($temporaryPath, $json, [Text.UTF8Encoding]::new($false))
        if (Test-Path -LiteralPath $StatePath -PathType Leaf) { [IO.File]::Replace($temporaryPath, $StatePath, $backupPath) }
        else { [IO.File]::Move($temporaryPath, $StatePath) }
    }
    finally {
        if (Test-Path -LiteralPath $temporaryPath -PathType Leaf) { Remove-Item -LiteralPath $temporaryPath -Force }
        if (Test-Path -LiteralPath $backupPath -PathType Leaf) { Remove-Item -LiteralPath $backupPath -Force }
    }
}

function Initialize-HarnessExactFileType {
    if ('Task138ExactFile' -as [type]) { return }
    Add-Type -TypeDefinition @'
using Microsoft.Win32.SafeHandles;
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;

public sealed class Task138ExactFileSnapshot {
    public string Text { get; set; }
    public string Identity { get; set; }
    public string FinalPath { get; set; }
}

public static class Task138ExactFile {
    [StructLayout(LayoutKind.Sequential)]
    private struct ByHandleFileInformation {
        public uint FileAttributes;
        public System.Runtime.InteropServices.ComTypes.FILETIME CreationTime;
        public System.Runtime.InteropServices.ComTypes.FILETIME LastAccessTime;
        public System.Runtime.InteropServices.ComTypes.FILETIME LastWriteTime;
        public uint VolumeSerialNumber;
        public uint FileSizeHigh;
        public uint FileSizeLow;
        public uint NumberOfLinks;
        public uint FileIndexHigh;
        public uint FileIndexLow;
    }

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool GetFileInformationByHandle(
        SafeFileHandle handle,
        out ByHandleFileInformation information
    );

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern uint GetFinalPathNameByHandle(
        SafeFileHandle handle,
        StringBuilder path,
        uint pathLength,
        uint flags
    );

    public static Task138ExactFileSnapshot Read(string path, int maximumBytes) {
        using (var stream = new FileStream(
            path,
            FileMode.Open,
            FileAccess.Read,
            FileShare.Read,
            4096,
            FileOptions.SequentialScan
        )) {
            ByHandleFileInformation information;
            if (!GetFileInformationByHandle(stream.SafeFileHandle, out information)) {
                throw new IOException("file identity unavailable");
            }
            if (information.NumberOfLinks != 1) {
                throw new IOException("file link count invalid");
            }
            var finalPath = new StringBuilder(32768);
            var finalLength = GetFinalPathNameByHandle(
                stream.SafeFileHandle,
                finalPath,
                (uint)finalPath.Capacity,
                0
            );
            if (finalLength == 0 || finalLength >= finalPath.Capacity) {
                throw new IOException("final path unavailable");
            }
            using (var memory = new MemoryStream()) {
                var buffer = new byte[1024];
                int count;
                while ((count = stream.Read(buffer, 0, buffer.Length)) > 0) {
                    if (memory.Length + count > maximumBytes) {
                        throw new IOException("file is oversized");
                    }
                    memory.Write(buffer, 0, count);
                }
                return new Task138ExactFileSnapshot {
                    Text = new UTF8Encoding(false, true).GetString(memory.ToArray()),
                    Identity = information.VolumeSerialNumber.ToString("X8") + ":" +
                        information.FileIndexHigh.ToString("X8") +
                        information.FileIndexLow.ToString("X8"),
                    FinalPath = finalPath.ToString()
                };
            }
        }
    }
}
'@
}

function Read-HarnessExactFile {
    param(
        [string]$Path,
        [int]$MaximumBytes,
        [scriptblock]$ReadSnapshot = { param($ExactPath, $Limit) [Task138ExactFile]::Read($ExactPath, $Limit) }
    )
    try {
        $full = [IO.Path]::GetFullPath($Path)
        $cursor = Get-Item -LiteralPath $full -Force
        while ($null -ne $cursor) {
            if (($cursor.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { Throw-HarnessSafe 'Harness private file is invalid' }
            $parentPath = [IO.Path]::GetDirectoryName([string]$cursor.FullName)
            if (-not $parentPath -or $parentPath -ceq [string]$cursor.FullName) { break }
            $cursor = Get-Item -LiteralPath $parentPath -Force
        }
        Initialize-HarnessExactFileType
        $first = & $ReadSnapshot $full $MaximumBytes
        $second = & $ReadSnapshot $full $MaximumBytes
        $expectedFinal = $full
        $actualFinal = [string]$first.FinalPath
        if ($actualFinal.StartsWith('\\?\', [StringComparison]::Ordinal)) { $actualFinal = $actualFinal.Substring(4) }
        if (
            -not $actualFinal.Equals($expectedFinal, [StringComparison]::OrdinalIgnoreCase) -or
            [string]$first.Identity -cne [string]$second.Identity -or
            [string]$first.FinalPath -cne [string]$second.FinalPath -or
            [string]$first.Text -cne [string]$second.Text
        ) { Throw-HarnessSafe 'Harness private file is invalid' }
        return [string]$first.Text
    }
    catch {
        if ($_.Exception.Message -ceq 'Harness private file is invalid') { Throw-HarnessSafe 'Harness private file is invalid' }
        Throw-HarnessSafe 'Harness private file is invalid'
    }
    finally { $cursor = $null; $first = $null; $second = $null; $actualFinal = $null }
}

function Get-HarnessBrokerConfigFingerprint {
    param([string]$BrokerConfigPath)
    if (-not $BrokerConfigPath -or -not [IO.Path]::IsPathRooted($BrokerConfigPath)) { Throw-HarnessSafe 'Harness broker provisioning is required' }
    $raw = Read-HarnessExactFile $BrokerConfigPath 16384
    $normalized = $raw.Replace("`r`n", "`n").Replace("`r", "`n")
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($normalized)))).Replace('-', '') }
    finally { $sha.Dispose(); $raw = $null; $normalized = $null }
}

function Get-HarnessBindingFingerprint {
    param([object]$Binding)
    $canonical = @(
        [string]$Binding.accepted_sha,
        [string]$Binding.artifact_sha256,
        [string]$Binding.signer_sha256,
        [string]$Binding.package,
        [string]$Binding.version,
        [string]$Binding.avd,
        [string]$Binding.serial,
        [string]$Binding.vocabulary_version
    ) -join "`n"
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($canonical)))).Replace('-', '') }
    finally { $sha.Dispose(); $canonical = $null }
}

function Get-HarnessBrokerPrivatePath {
    param([string]$StatePath, [string]$BrokerAction)
    if ($BrokerAction -notin @('grant', 'restore')) { Throw-HarnessSafe 'Harness broker private state is invalid' }
    return $StatePath + ".broker-$BrokerAction.private.json"
}

function Assert-HarnessDirectoryChainNoReparse {
    param([string]$DirectoryPath)
    try {
        $currentPath = [IO.Path]::GetFullPath($DirectoryPath)
        while ($currentPath) {
            $item = Get-Item -LiteralPath $currentPath -Force
            if (
                -not $item.PSIsContainer -or
                ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0
            ) { Throw-HarnessSafe 'Harness broker private state is invalid' }
            $parentPath = [IO.Path]::GetDirectoryName($currentPath)
            if (-not $parentPath -or $parentPath -ceq $currentPath) { break }
            $currentPath = $parentPath
        }
    }
    catch {
        Throw-HarnessSafe 'Harness broker private state is invalid'
    }
    finally { $currentPath = $null; $item = $null; $parentPath = $null }
}

function Save-HarnessBrokerPrivateState {
    param([string]$StatePath, [string]$BrokerAction, [object]$Binding, [string]$BrokerConfigFingerprint)
    if ($BrokerConfigFingerprint -notmatch $script:HarnessFingerprintPattern) { Throw-HarnessSafe 'Harness broker private state is invalid' }
    $path = Get-HarnessBrokerPrivatePath $StatePath $BrokerAction
    $directory = [IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($path))
    Assert-HarnessDirectoryChainNoReparse $directory
    if (Test-Path -LiteralPath $path) { Throw-HarnessSafe 'Harness broker private state is invalid' }
    if (@(Get-ChildItem -LiteralPath $directory -Filter ([IO.Path]::GetFileName($path) + '.*.tmp') -Force).Count -ne 0) { Throw-HarnessSafe 'Harness broker private state is invalid' }
    $operationId = [Guid]::NewGuid().ToString('N')
    $value = [ordered]@{
        schema_version = 1
        scenario = 'officer-authorization-roundtrip'
        broker_action = $BrokerAction
        operation_id = $operationId
        binding_sha256 = Get-HarnessBindingFingerprint $Binding
        broker_config_sha256 = $BrokerConfigFingerprint
    }
    $temporaryPath = $path + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
    try {
        $json = $value | ConvertTo-Json -Depth 3 -Compress
        Assert-HarnessSafeText $json
        $bytes = [Text.UTF8Encoding]::new($false).GetBytes($json)
        $stream = [IO.FileStream]::new($temporaryPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None, 4096, [IO.FileOptions]::WriteThrough)
        try { $stream.Write($bytes, 0, $bytes.Length); $stream.Flush($true) }
        finally { $stream.Dispose() }
        [IO.File]::Move($temporaryPath, $path)
        if ((Read-HarnessExactFile $path 4096) -cne $json) { Throw-HarnessSafe 'Harness broker private state is invalid' }
    }
    finally {
        if (Test-Path -LiteralPath $temporaryPath -PathType Leaf) { Remove-Item -LiteralPath $temporaryPath -Force }
        $json = $null; $bytes = $null; $stream = $null
    }
    return $operationId
}

function Read-HarnessBrokerPrivateState {
    param([string]$StatePath, [string]$BrokerAction, [object]$Binding, [string]$BrokerConfigFingerprint)
    $path = Get-HarnessBrokerPrivatePath $StatePath $BrokerAction
    $directory = [IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($path))
    $directoryItem = Get-Item -LiteralPath $directory -Force
    if (($directoryItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { Throw-HarnessSafe 'Harness broker private state is invalid' }
    if (@(Get-ChildItem -LiteralPath $directory -Filter ([IO.Path]::GetFileName($path) + '.*.tmp') -Force).Count -ne 0) { Throw-HarnessSafe 'Harness broker private state is invalid' }
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { Throw-HarnessSafe 'Harness broker private state is invalid' }
    try { $value = (Read-HarnessExactFile $path 4096) | ConvertFrom-Json }
    catch { Throw-HarnessSafe 'Harness broker private state is invalid' }
    $expected = @('schema_version', 'scenario', 'broker_action', 'operation_id', 'binding_sha256', 'broker_config_sha256')
    $actual = @(Get-HarnessFieldNames $value | Sort-Object)
    if (
        ($actual -join "`n") -cne (($expected | Sort-Object) -join "`n") -or
        $value.schema_version -ne 1 -or
        [string]$value.scenario -cne 'officer-authorization-roundtrip' -or
        [string]$value.broker_action -cne $BrokerAction -or
        [string]$value.operation_id -notmatch $script:HarnessBrokerOperationIdPattern -or
        [string]$value.binding_sha256 -cne (Get-HarnessBindingFingerprint $Binding) -or
        [string]$value.broker_config_sha256 -cne $BrokerConfigFingerprint -or
        $BrokerConfigFingerprint -notmatch $script:HarnessFingerprintPattern
    ) { Throw-HarnessSafe 'Harness broker private state is invalid' }
    return [string]$value.operation_id
}

function Test-BasicAcceptanceObservation {
    param([object]$Observation, [switch]$Terminal)
    if ($Terminal) { return $Observation.principal -eq 'logged_out' -and $Observation.provenance -eq 'none' -and $Observation.aggregate -eq 'terminal_absent' -and $Observation.report_entry -eq 'absent' }
    return $Observation.principal -eq 'basic' -and $Observation.provenance -eq 'fresh_server' -and $Observation.aggregate -eq 'basic_valid' -and $Observation.report_entry -eq 'absent'
}

function Get-HarnessObservationFailure {
    param([object]$Observation)
    if ($Observation.provenance -in @('offline_cache', 'unknown')) { return 'NON_AUTHORITATIVE_PROJECTION' }
    if ($Observation.producer_gap -eq $true) { return 'PRODUCER_GAP' }
    return 'OBSERVATION_MISMATCH'
}

function Assert-HarnessActionResult {
    param([object]$Value, [string[]]$AllowedResults)
    if ($null -eq $Value -or [string]$Value.result -notin $AllowedResults -or ($null -ne $Value.classification -and [string]$Value.classification -ne 'PASS')) { Throw-HarnessSafe 'Harness action result is invalid' }
}

function Invoke-HarnessAction {
    param([hashtable]$Dependencies, [string]$ActionName, [string[]]$AllowedResults)
    $result = & $Dependencies.Action $ActionName
    Assert-HarnessActionResult $result $AllowedResults
    return $result
}

function New-MobileAcceptanceTestDependencies {
    param(
        [Parameter(Mandatory = $true)][scriptblock]$Action,
        [Parameter(Mandatory = $true)][scriptblock]$Artifact,
        [Parameter(Mandatory = $true)][scriptblock]$Observation,
        [scriptblock]$BrokerStatus = { [pscustomobject]@{ classification = 'OWNER_ACTION_REQUIRED'; result = 'stopped'; state = 'unavailable'; reason_code = 'BROKER_PROVISIONING' } },
        [scriptblock]$BrokerOperation = { param($Action, $OperationId) [pscustomobject]@{ classification = 'FAILED'; result = 'stopped'; state = 'unknown'; reason_code = 'BROKER_UNAVAILABLE' } },
        [scriptblock]$BrokerBinding = { 'CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC' },
        [scriptblock]$NetworkGet = { 'on' },
        [scriptblock]$NetworkSet = { param($State) },
        [scriptblock]$CheckpointPolicy = { param($Path) $true }
    )
    return [ordered]@{
        Action = $Action; Artifact = $Artifact; Observation = $Observation; BrokerStatus = $BrokerStatus
        BrokerOperation = $BrokerOperation; BrokerBinding = $BrokerBinding; NetworkGet = $NetworkGet; NetworkSet = $NetworkSet; CheckpointPolicy = $CheckpointPolicy
    }
}

function New-IsolatedBrokerClientAction {
    param(
        [string]$BrokerPath,
        [string]$BrokerConfigPath,
        [string]$BrokerConfigFingerprint,
        [scriptblock]$InvokeBounded,
        [string]$HostExecutable
    )
    return {
        param([string]$BrokerAction, [string]$OperationId)
        if (-not $BrokerConfigPath) {
            return [pscustomobject]@{ classification = 'OWNER_ACTION_REQUIRED'; result = 'stopped'; state = 'unavailable'; reason_code = 'BROKER_PROVISIONING' }
        }
        $childLaunched = $false
        $failureMessage = $null
        $postCheckFailed = $false
        $resultEnvelope = $null
        try {
            if ((Get-HarnessBrokerConfigFingerprint $BrokerConfigPath) -cne $BrokerConfigFingerprint) { Throw-HarnessSafe 'Harness broker result is invalid' }
            $arguments = @(
                '-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                '-File', $BrokerPath, '-Action', $BrokerAction, '-ConfigPath', $BrokerConfigPath
            )
            if ($BrokerAction -ne 'status') { $arguments += @('-OperationId', $OperationId) }
            $childLaunched = $true
            $child = & $InvokeBounded $HostExecutable $arguments 120
            if ($child.TimedOut) { Throw-HarnessSafe 'Harness broker timed out' }
            if ([string]$child.Stderr -match '\S') { Throw-HarnessSafe 'Harness broker operation result is unknown' }
            $raw = [string]$child.Stdout
            if ($raw.Length -lt 1 -or $raw.Length -gt 4096) { Throw-HarnessSafe 'Harness broker result is invalid' }
            $lines = @($raw -split "`r?`n" | Where-Object { $_.Trim().Length -gt 0 })
            if ($lines.Count -ne 1) { Throw-HarnessSafe 'Harness broker result is invalid' }
            try { $envelope = $lines[0] | ConvertFrom-Json }
            catch { Throw-HarnessSafe 'Harness broker result is invalid' }
            $expectedEnvelope = @('action', 'classification', 'operator', 'owner_gate', 'standing_authorization', 'stop_only_on', 'report_to', 'retention_owner', 'details')
            if (
                $null -eq $envelope -or $envelope -isnot [System.Management.Automation.PSCustomObject] -or
                ((@(Get-HarnessFieldNames $envelope | Sort-Object) -join "`n") -cne (($expectedEnvelope | Sort-Object) -join "`n")) -or
                [string]$envelope.action -cne $BrokerAction -or
                [string]$envelope.operator -cne 'agent' -or
                [string]$envelope.standing_authorization -cne 'DEC-098' -or
                [string]$envelope.report_to -cne 'main-work' -or
                [string]$envelope.retention_owner -cne 'TASK-134' -or
                [string]$envelope.stop_only_on -cne 'broker-provisioning|identity-or-runtime-drift|unknown-operation-result' -or
                ([string]$envelope.owner_gate -cne $(if ([string]$envelope.classification -ceq 'OWNER_ACTION_REQUIRED') { 'BROKER_PROVISIONING' } else { 'none' }))
            ) { Throw-HarnessSafe 'Harness broker result is invalid' }
            $expectedDetails = @('result', 'state', 'reason_code')
            if ($null -eq $envelope.details -or $envelope.details -isnot [System.Management.Automation.PSCustomObject] -or (@(Get-HarnessFieldNames $envelope.details | Sort-Object) -join "`n") -cne (($expectedDetails | Sort-Object) -join "`n")) { Throw-HarnessSafe 'Harness broker result is invalid' }
            $classification = [string]$envelope.classification
            $resultValue = [string]$envelope.details.result
            $state = [string]$envelope.details.state
            $reason = [string]$envelope.details.reason_code
            if (
                $classification -notin @('PASS', 'OWNER_ACTION_REQUIRED', 'DRIFT', 'TIMEOUT', 'FAILED') -or
                $resultValue -notin @('available', 'completed', 'stopped') -or
                $state -notin @('private_exact', 'ready_basic', 'ready_officer', 'reset_required', 'unavailable', 'unchanged', 'unknown') -or
                $reason -notmatch '^[A-Z][A-Z0-9_]{0,63}$' -or
                (($classification -eq 'PASS') -ne ($child.ExitCode -eq 0)) -or
                ($classification -ne 'PASS' -and $child.ExitCode -ne 2)
            ) { Throw-HarnessSafe 'Harness broker result is invalid' }
            $resultEnvelope = [pscustomobject]@{ classification = $classification; result = $resultValue; state = $state; reason_code = $reason }
        }
        catch {
            $failureMessage = if ($_.Exception.Message -cin @('Harness broker timed out', 'Harness broker operation result is unknown', 'Harness broker result is invalid')) { $_.Exception.Message } else { 'Harness broker operation result is unknown' }
        }
        finally {
            if ($childLaunched) {
                try {
                    if ((Get-HarnessBrokerConfigFingerprint $BrokerConfigPath) -cne $BrokerConfigFingerprint) { $postCheckFailed = $true }
                }
                catch { $postCheckFailed = $true }
            }
            $arguments = $null; $child = $null; $raw = $null; $lines = $null; $envelope = $null
        }
        if ($postCheckFailed) { Throw-HarnessSafe 'Harness broker result is invalid' }
        if ($failureMessage) { Throw-HarnessSafe $failureMessage }
        return $resultEnvelope
    }.GetNewClosure()
}

function Get-AdditionalAcceptanceProducerObservation {
    param([object]$Status, [scriptblock]$UiDump)
    $isOfflineOfficer = $Status.semantic_state -eq 'officer_report_enabled_non_authoritative' -and $Status.provenance -eq 'offline_cache'
    if ($Status.semantic_state -notin @('logged_out', 'basic', 'officer_report_enabled') -and -not $isOfflineOfficer) {
        return [pscustomobject]@{ principal = 'non_foreground'; provenance = 'none'; aggregate = 'absent'; report = 'absent'; report_entry = 'absent'; producer_gap = $false }
    }
    $raw = & $UiDump
    if ($raw.Length -lt 1 -or $raw.Length -gt 65536) { Throw-HarnessSafe 'Harness producer observation is malformed' }
    $start = $raw.IndexOf('<hierarchy', [StringComparison]::Ordinal)
    $endMarker = '</hierarchy>'
    $end = $raw.IndexOf($endMarker, [StringComparison]::Ordinal)
    if ($start -lt 0 -or $end -lt $start -or $raw.IndexOf('<hierarchy', $start + 1, [StringComparison]::Ordinal) -ge 0 -or $raw.IndexOf($endMarker, $end + $endMarker.Length, [StringComparison]::Ordinal) -ge 0) { Throw-HarnessSafe 'Harness producer observation is malformed' }
    $settings = [Xml.XmlReaderSettings]::new(); $settings.DtdProcessing = [Xml.DtdProcessing]::Prohibit; $settings.XmlResolver = $null; $settings.MaxCharactersInDocument = 65536
    $reader = $null; $document = [Xml.XmlDocument]::new(); $document.XmlResolver = $null
    try { $reader = [Xml.XmlReader]::Create([IO.StringReader]::new($raw.Substring($start, $end - $start + $endMarker.Length)), $settings); $document.Load($reader) }
    catch { Throw-HarnessSafe 'Harness producer observation is malformed' }
    finally { if ($null -ne $reader) { $reader.Dispose() } }
    $nodes = @($document.SelectNodes('//node') | Where-Object { [string]$_.GetAttribute('package') -ceq $script:HarnessPackage })
    $labels = @($nodes | ForEach-Object { [string]$_.GetAttribute('content-desc') } | Where-Object { $_ })
    $aggregatePattern = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('5YG16Yyv5pys5qmf54uA5oWL77yac2Vzc2lvbiAoPzxzZXNzaW9uPnByZXNlbnR8YWJzZW50Ke+8m2Jhc2ljX2NhY2hlICg/PGJhc2ljPnByZXNlbnR8YWJzZW50Ke+8m29mZmljZXJfcmVwb3J0X2NhY2hlICg/PG9mZmljZXI+cHJlc2VudHxhYnNlbnQp77ybcGVuZGluZ19hdHRlbmRhbmNlX2ludGVudCAoPzxwZW5kaW5nPnByZXNlbnR8YWJzZW50KSQ='))
    $aggregateLabels = @($labels | Where-Object { $_ -match $aggregatePattern })
    if ($aggregateLabels.Count -ne 1) { Throw-HarnessSafe 'Harness aggregate producer is not exact' }
    $null = $aggregateLabels[0] -match $aggregatePattern
    $aggregate = if ($Matches['session'] -eq 'present' -and $Matches['basic'] -eq 'present' -and $Matches['officer'] -eq 'absent' -and $Matches['pending'] -eq 'absent') { 'basic_valid' }
    elseif ($Matches['session'] -eq 'present' -and $Matches['basic'] -eq 'present' -and $Matches['officer'] -eq 'present' -and $Matches['pending'] -eq 'absent') { 'officer_valid' }
    elseif ($Matches['session'] -eq 'absent' -and $Matches['basic'] -eq 'absent' -and $Matches['officer'] -eq 'absent' -and $Matches['pending'] -eq 'absent') { 'terminal_absent' }
    else { 'invalid' }
    $reportPattern = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('5YG16Yyv5aCx6KGo5oqV5b2x77yaKD88cmVwb3J0PnJlYWR5fGVtcHR5fG9mZmxpbmVfY2FjaGVkX3JlYWRvbmx5Ke+8m+W3suWVn+eUqOWvq+WFpeaOp+WItu+8mjAk'))
    $reportLabels = @($labels | Where-Object { $_ -match $reportPattern })
    if ($reportLabels.Count -gt 1) { Throw-HarnessSafe 'Harness report producer is not exact' }
    $report = if ($reportLabels.Count -eq 1) { $null = $reportLabels[0] -match $reportPattern; $Matches['report'] } else { 'absent' }
    $reportEntryLabel = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('5Ye65bit5aCx6KGoCk9mZmljZXLvvI9BZG1pbiDllK/oroA='))
    $reportEntryNodes = @($nodes | Where-Object { [string]$_.GetAttribute('class') -ceq 'android.view.View' -and [string]$_.GetAttribute('content-desc') -ceq $reportEntryLabel -and [string]$_.GetAttribute('enabled') -ceq 'true' -and [string]$_.GetAttribute('clickable') -ceq 'true' })
    if ($reportEntryNodes.Count -gt 1) { Throw-HarnessSafe 'Harness report entry is not exact' }
    $reportEntry = if ($reportEntryNodes.Count -eq 1) { 'present' } else { 'absent' }
    $principal = if ($Status.semantic_state -eq 'logged_out') { 'logged_out' } elseif ($Status.semantic_state -eq 'basic') { 'basic' } else { 'officer' }
    return [pscustomobject]@{ principal = $principal; provenance = [string]$Status.provenance; aggregate = $aggregate; report = $report; report_entry = $reportEntry; producer_gap = $false }
}

function Get-MobileAcceptanceStatus {
    param(
        [scriptblock]$InvokeStatus,
        [scriptblock]$Wait = { Start-Sleep -Seconds 3 }
    )
    $maxAttempts = 5
    $retryableMessages = @(
        'Accessibility inventory failed safely',
        'Accessibility inventory is malformed',
        'Accessibility foreground state is not exact'
    )
    for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
        try {
            $status = & $InvokeStatus
            if ($null -ne $status -and [string]$status.result -eq 'observed') { return $status }
            Throw-HarnessSafe 'Harness status is unavailable'
        }
        catch {
            $readinessMessage = [string]$_.Exception.Message
            if ($readinessMessage -cin $retryableMessages) {
                if ($attempt -lt $maxAttempts) {
                    & $Wait
                    continue
                }
                Throw-HarnessSafe $readinessMessage
            }
            if ($readinessMessage -cin $script:HarnessTerminalStatusReasons) {
                Throw-HarnessSafe $readinessMessage
            }
            Throw-HarnessSafe 'Harness status is unavailable'
        }
    }
    Throw-HarnessSafe 'Harness status is unavailable'
}

function Get-MobileAcceptanceArtifact {
    param([object]$Config, [string]$ExpectedCommit, [hashtable]$LauncherCommands)
    if ($null -eq $LauncherCommands) {
        $LauncherCommands = @{
            GetArtifactPath = Get-HarnessFunctionScriptBlock 'Get-ArtifactPath'
            InvokeApkTool = Get-HarnessFunctionScriptBlock 'Invoke-ApkToolWithApprovedJava'
            GetSigner = Get-HarnessFunctionScriptBlock 'Get-ApkSignerFingerprint'
            GetPackage = Get-HarnessFunctionScriptBlock 'Get-ApkPackageIdentity'
        }
    }
    $getArtifactPath = $LauncherCommands.GetArtifactPath
    $artifact = & $getArtifactPath $Config
    if (-not (Test-Path -LiteralPath $artifact -PathType Leaf)) { return [ordered]@{ state = 'missing' } }
    $manifestPath = Join-Path ([string]$Config.evidence_root) 'artifact-manifest.json'
    try { $manifest = Get-Content -LiteralPath $manifestPath -Encoding UTF8 -Raw | ConvertFrom-Json } catch { return [ordered]@{ state = 'drift' } }
    $expectedManifestFields = @('accepted_commit', 'artifact_sha256', 'classification', 'mode', 'package', 'retention_owner', 'signer_sha256')
    $actualManifestFields = @(Get-HarnessFieldNames $manifest | Sort-Object)
    if (
        ($actualManifestFields -join "`n") -cne (($expectedManifestFields | Sort-Object) -join "`n") -or
        $manifest.accepted_commit -cne $ExpectedCommit -or
        $manifest.mode -cne 'staging' -or
        $manifest.package -cne $script:HarnessPackage -or
        $manifest.classification -cne 'PASS' -or
        $manifest.retention_owner -cne 'TASK-123' -or
        [string]$manifest.artifact_sha256 -notmatch $script:HarnessFingerprintPattern -or
        [string]$manifest.signer_sha256 -notmatch $script:HarnessFingerprintPattern
    ) { return [ordered]@{ state = 'drift' } }
    try {
        $invokeApkTool = $LauncherCommands.InvokeApkTool
        $versionResult = & $invokeApkTool $Config ([string]$Config.apkanalyzer_executable) @('manifest', 'version-name', $artifact)
        $versionLines = @($versionResult.Stdout -split "`r?`n" | Where-Object { $_.Trim().Length -gt 0 })
        if ($versionResult.TimedOut -or $versionResult.ExitCode -ne 0 -or $versionLines.Count -ne 1) { return [ordered]@{ state = 'unavailable' } }
        $binding = [pscustomobject]@{
            accepted_sha = $ExpectedCommit; artifact_sha256 = (Get-FileHash -LiteralPath $artifact -Algorithm SHA256).Hash
            signer_sha256 = & $LauncherCommands.GetSigner $Config $artifact; package = & $LauncherCommands.GetPackage $Config $artifact
            version = $versionLines[0].Trim(); avd = [string]$Config.avd_name; serial = [string]$Config.serial
            vocabulary_version = $script:HarnessVocabularyVersion
        }
    }
    catch { return [ordered]@{ state = 'unavailable' } }
    if ($manifest.package -cne $binding.package -or $manifest.artifact_sha256 -cne $binding.artifact_sha256 -or $manifest.signer_sha256 -cne $binding.signer_sha256) { return [ordered]@{ state = 'drift' } }
    Assert-HarnessBinding $binding $ExpectedCommit
    return [ordered]@{ state = 'matched'; binding = $binding }
}

function New-MobileAcceptanceDependenciesFromConfig {
    param(
        [string]$SelectedMode,
        [string]$ExpectedCommit,
        [string]$LauncherConfigPath,
        [object]$Config,
        [hashtable]$LauncherCommands,
        [scriptblock]$StatusAction
    )
    if ($null -eq $LauncherCommands) {
        $LauncherCommands = @{
            InvokeMain = Get-HarnessFunctionScriptBlock 'Invoke-MobileStagingMain'
            InvokeBounded = Get-HarnessFunctionScriptBlock 'Invoke-BoundedProcess'
        }
    }
    $invokeMain = $LauncherCommands.InvokeMain
    $invokeBounded = $LauncherCommands.InvokeBounded
    $inspectArtifact = (Get-Command Get-MobileAcceptanceArtifact -CommandType Function).ScriptBlock
    $produceObservation = (Get-Command Get-AdditionalAcceptanceProducerObservation -CommandType Function).ScriptBlock
    $readStatus = (Get-Command Get-MobileAcceptanceStatus -CommandType Function).ScriptBlock
    if ($null -eq $StatusAction) {
        $StatusAction = { & $invokeMain 'status' $SelectedMode $ExpectedCommit $LauncherConfigPath '' $false $false $false }.GetNewClosure()
    }
    $action = {
        param($Name)
        switch ($Name) {
            'preflight' { $value = & $invokeMain 'preflight' $SelectedMode $ExpectedCommit $LauncherConfigPath '' $false $false $false }
            'avd-start' { $value = & $invokeMain 'avd-start' $SelectedMode $ExpectedCommit $LauncherConfigPath '' $false $false $false }
            'cleanup-artifact' { $value = & $invokeMain 'cleanup-artifact' $SelectedMode $ExpectedCommit $LauncherConfigPath '' $false $false $false }
            'build' { $value = & $invokeMain 'build' $SelectedMode $ExpectedCommit $LauncherConfigPath '' $false $false $false }
            'signer-check' { $value = & $invokeMain 'signer-check' $SelectedMode $ExpectedCommit $LauncherConfigPath '' $false $false $false }
            'install' { $value = & $invokeMain 'install' $SelectedMode $ExpectedCommit $LauncherConfigPath '' $true $false $false }
            'cold-launch' { $value = & $invokeMain 'cold-launch' $SelectedMode $ExpectedCommit $LauncherConfigPath '' $false $false $false }
            default { Throw-HarnessSafe 'Harness action is unavailable' }
        }
        return [pscustomobject]@{ classification = 'PASS'; result = [string]$value.result }
    }.GetNewClosure()
    $artifact = { & $inspectArtifact $Config $ExpectedCommit $LauncherCommands }.GetNewClosure()
    $observation = {
        $status = & $readStatus $StatusAction
        return & $produceObservation $status {
            $result = & $invokeBounded ([string]$Config.adb_executable) @('-s', [string]$Config.serial, 'exec-out', 'uiautomator', 'dump', '/dev/tty') 15
            if ($result.TimedOut -or $result.ExitCode -ne 0) { Throw-HarnessSafe 'Harness producer observation is unavailable' }
            return [string]$result.Stdout
        }
    }.GetNewClosure()
    $checkpointPolicy = {
        param($Path)
        $root = [IO.Path]::GetFullPath((Join-Path ([string]$Config.evidence_root) 'task-129')).TrimEnd('\')
        $full = [IO.Path]::GetFullPath($Path)
        if (-not $full.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)) { return $false }
        [IO.Directory]::CreateDirectory($root) | Out-Null
        return $true
    }.GetNewClosure()
    return New-MobileAcceptanceTestDependencies -Action $action -Artifact $artifact -Observation $observation -CheckpointPolicy $checkpointPolicy
}

function New-IsolatedLauncherStatusAction {
    param(
        [string]$LauncherPath,
        [string]$SelectedMode,
        [string]$ExpectedCommit,
        [string]$LauncherConfigPath,
        [scriptblock]$InvokeBounded,
        [string]$HostExecutable
    )
    $terminalStatusReasons = @($script:HarnessTerminalStatusReasons)
    return {
        try {
            $arguments = @(
                '-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                '-File', $LauncherPath, '-Action', 'status', '-Mode', $SelectedMode,
                '-Commit', $ExpectedCommit, '-ConfigPath', $LauncherConfigPath
            )
            $result = & $InvokeBounded $HostExecutable $arguments 45
            if ($result.TimedOut) { Throw-HarnessSafe 'STATUS_CHILD_TIMEOUT' }
            if ([string]$result.Stderr -match '\S') { Throw-HarnessSafe 'STATUS_CHILD_STDERR' }
            $raw = [string]$result.Stdout
            if ($raw.Length -lt 1 -or $raw.Length -gt 4096) { Throw-HarnessSafe 'STATUS_CHILD_OUTPUT_INVALID' }
            $lines = @($raw -split "`r?`n" | Where-Object { $_.Trim().Length -gt 0 })
            if ($lines.Count -ne 1) { Throw-HarnessSafe 'STATUS_CHILD_OUTPUT_INVALID' }
            try { $envelope = $lines[0] | ConvertFrom-Json }
            catch { Throw-HarnessSafe 'STATUS_CHILD_ENVELOPE_INVALID' }
            if ($null -eq $envelope -or $envelope -isnot [System.Management.Automation.PSCustomObject]) {
                Throw-HarnessSafe 'STATUS_CHILD_ENVELOPE_INVALID'
            }
            $classificationProperty = $envelope.PSObject.Properties['classification']
            $detailsProperty = $envelope.PSObject.Properties['details']
            if ($null -eq $classificationProperty -or $null -eq $detailsProperty) {
                Throw-HarnessSafe 'STATUS_CHILD_ENVELOPE_INVALID'
            }
            $details = $detailsProperty.Value
            if ($null -eq $details -or $details -isnot [System.Management.Automation.PSCustomObject]) {
                Throw-HarnessSafe 'STATUS_CHILD_ENVELOPE_INVALID'
            }
            $classification = [string]$classificationProperty.Value
            $actionProperty = $details.PSObject.Properties['action']
            $resultProperty = $details.PSObject.Properties['result']
            $reasonProperty = $details.PSObject.Properties['reason_code']
            $action = $(if ($null -eq $actionProperty) { '' } else { [string]$actionProperty.Value })
            $actionResult = $(if ($null -eq $resultProperty) { '' } else { [string]$resultProperty.Value })
            $reason = $(if ($null -eq $reasonProperty) { '' } else { [string]$reasonProperty.Value })
            if (
                $result.ExitCode -eq 0 -and
                $classification -ceq 'PASS' -and
                $action -ceq 'status' -and
                $actionResult -ceq 'observed'
            ) { return $details }
            if ($result.ExitCode -eq 2 -and $classification -ceq 'FAILED') {
                if ($reason -ceq 'ACCESSIBILITY_UNAVAILABLE') { Throw-HarnessSafe 'Accessibility inventory failed safely' }
                if ($reason -ceq 'ACCESSIBILITY_INVALID') { Throw-HarnessSafe 'Accessibility inventory is malformed' }
                if ($reason -cin $terminalStatusReasons) { Throw-HarnessSafe $reason }
            }
            if ($result.ExitCode -eq 2 -and $classification -ceq 'DRIFT' -and $reason -ceq 'SEMANTIC_DRIFT') {
                Throw-HarnessSafe 'Accessibility foreground state is not exact'
            }
            Throw-HarnessSafe 'STATUS_CHILD_RESULT_INVALID'
        }
        catch {
            if ($_.Exception.Message -cin @(
                'Accessibility inventory failed safely',
                'Accessibility inventory is malformed',
                'Accessibility foreground state is not exact'
            )) { Throw-HarnessSafe $_.Exception.Message }
            if ($_.Exception.Message -cin $terminalStatusReasons) {
                Throw-HarnessSafe $_.Exception.Message
            }
            Throw-HarnessSafe 'Harness status is unavailable'
        }
        finally {
            $raw = $null
            $lines = $null
            $envelope = $null
            $details = $null
            $arguments = $null
        }
    }.GetNewClosure()
}

function New-MobileAcceptanceDependencies {
    param([string]$SelectedMode, [string]$ExpectedCommit, [string]$LauncherConfigPath, [string]$BrokerConfigPath)
    $launcherPath = Join-Path $PSScriptRoot 'Invoke-MobileStaging.ps1'
    $brokerPath = Join-Path $PSScriptRoot 'Invoke-MobileStagingBroker.ps1'
    $launcherModule = New-Module -ArgumentList $launcherPath -ScriptBlock {
        param($Path)
        . $Path
    }
    if ($null -eq $launcherModule) { Throw-HarnessSafe 'Harness launcher composition is unavailable' }
    $loadConfig = $launcherModule.NewBoundScriptBlock({ param($Path) Load-LauncherConfig $Path })
    $config = & $loadConfig $LauncherConfigPath
    $launcherCommands = @{
        InvokeMain = $launcherModule.NewBoundScriptBlock({
            param($Action, $Mode, $Commit, $ConfigPath, $ApprovalPath, $PreserveSession, $PublicHealth, $PurgeEvidence)
            Invoke-MobileStagingMain $Action $Mode $Commit $ConfigPath $ApprovalPath $PreserveSession $PublicHealth $PurgeEvidence
        })
        InvokeBounded = $launcherModule.NewBoundScriptBlock({ param($File, $Arguments, $Timeout, [hashtable]$Environment = @{}) Invoke-BoundedProcess $File $Arguments $Timeout $Environment })
        GetArtifactPath = $launcherModule.NewBoundScriptBlock({ param($Config) Get-ArtifactPath $Config })
        InvokeApkTool = $launcherModule.NewBoundScriptBlock({ param($Config, $Tool, $Arguments) Invoke-ApkToolWithApprovedJava $Config $Tool $Arguments })
        GetSigner = $launcherModule.NewBoundScriptBlock({ param($Config, $Artifact) Get-ApkSignerFingerprint $Config $Artifact })
        GetPackage = $launcherModule.NewBoundScriptBlock({ param($Config, $Artifact) Get-ApkPackageIdentity $Config $Artifact })
    }
    $hostExecutable = Join-Path $PSHOME 'powershell.exe'
    if (-not (Test-Path -LiteralPath $hostExecutable -PathType Leaf)) {
        $hostExecutable = Join-Path $PSHOME 'pwsh.exe'
    }
    if (-not (Test-Path -LiteralPath $hostExecutable -PathType Leaf)) { Throw-HarnessSafe 'STATUS_HOST_UNAVAILABLE' }
    $statusAction = New-IsolatedLauncherStatusAction $launcherPath $SelectedMode $ExpectedCommit $LauncherConfigPath $launcherCommands.InvokeBounded $hostExecutable
    $dependencies = New-MobileAcceptanceDependenciesFromConfig $SelectedMode $ExpectedCommit $LauncherConfigPath $config $launcherCommands $statusAction
    $brokerConfigFingerprint = ''
    if ($BrokerConfigPath) {
        try { $brokerConfigFingerprint = Get-HarnessBrokerConfigFingerprint $BrokerConfigPath }
        catch { Throw-HarnessSafe 'Harness broker result is invalid' }
    }
    $brokerAction = New-IsolatedBrokerClientAction $brokerPath $BrokerConfigPath $brokerConfigFingerprint $launcherCommands.InvokeBounded $hostExecutable
    $dependencies.BrokerStatus = { & $brokerAction 'status' '' }.GetNewClosure()
    $dependencies.BrokerOperation = { param($Action, $OperationId) & $brokerAction $Action $OperationId }.GetNewClosure()
    $dependencies.BrokerBinding = { $brokerConfigFingerprint }.GetNewClosure()
    return $dependencies
}

function Invoke-HarnessPreparation {
    param([hashtable]$Dependencies, [object]$Checkpoint)
    Invoke-HarnessAction $Dependencies 'preflight' @('ready') | Out-Null
    Invoke-HarnessAction $Dependencies 'avd-start' @('started', 'reused') | Out-Null
    $artifact = & $Dependencies.Artifact
    if ($artifact.state -eq 'matched') {
        if ($null -eq $Checkpoint) {
            # Artifact provenance does not prove the installed package identity.
            Invoke-HarnessAction $Dependencies 'signer-check' @('matched') | Out-Null
            Invoke-HarnessAction $Dependencies 'install' @('replaced') | Out-Null
            Invoke-HarnessAction $Dependencies 'cold-launch' $script:HarnessColdLaunchResults | Out-Null
        }
        return $artifact.binding
    }
    if ($null -ne $Checkpoint) { Throw-HarnessSafe 'Harness checkpoint binding is missing' }
    if ($artifact.state -eq 'unavailable') { Throw-HarnessSafe 'Harness artifact inspection is unavailable' }
    if ($artifact.state -eq 'drift') { Invoke-HarnessAction $Dependencies 'cleanup-artifact' @('removed_artifact') | Out-Null }
    if ($artifact.state -notin @('missing', 'drift')) { Throw-HarnessSafe 'Harness artifact provenance is invalid' }
    Invoke-HarnessAction $Dependencies 'build' @('built') | Out-Null
    Invoke-HarnessAction $Dependencies 'signer-check' @('matched') | Out-Null
    Invoke-HarnessAction $Dependencies 'install' @('replaced') | Out-Null
    Invoke-HarnessAction $Dependencies 'cold-launch' $script:HarnessColdLaunchResults | Out-Null
    $rebuilt = & $Dependencies.Artifact
    if ($rebuilt.state -ne 'matched') { Throw-HarnessSafe 'Harness artifact provenance is invalid' }
    return $rebuilt.binding
}

function Invoke-BasicScenario {
    param([string]$SelectedScenario, [string]$StatePath, [object]$Binding, [object]$Checkpoint, [hashtable]$Dependencies)
    $observation = & $Dependencies.Observation
    if ($observation.principal -eq 'logged_out') {
        Save-HarnessCheckpoint $StatePath $SelectedScenario 'await_login' $Binding 'owner_action_required'
        return New-HarnessEnvelope $SelectedScenario 'OWNER_ACTION_REQUIRED' 'LINE_LOGIN_CONSENT' 'await_login' 'stopped' 'LINE_LOGIN_CONSENT'
    }
    if (-not (Test-BasicAcceptanceObservation $observation)) {
        $classification = if ($observation.provenance -in @('offline_cache', 'unknown') -or $observation.producer_gap) { 'EVIDENCE_GAP' } else { 'DRIFT' }
        Save-HarnessCheckpoint $StatePath $SelectedScenario 'stopped' $Binding 'evidence_gap'
        return New-HarnessEnvelope $SelectedScenario $classification 'none' 'basic_authorization' 'stopped' (Get-HarnessObservationFailure $observation)
    }
    Save-HarnessCheckpoint $StatePath $SelectedScenario 'completed' $Binding 'accepted'
    return New-HarnessEnvelope $SelectedScenario 'PASS' 'none' 'completed' 'accepted' 'NONE'
}

function Assert-HarnessBrokerResult {
    param([object]$Value, [string]$ExpectedState)
    if ($null -ne $Value -and [string]$Value.classification -cne 'PASS') { Throw-HarnessBrokerFailure $Value }
    if (
        $null -eq $Value -or
        [string]$Value.classification -cne 'PASS' -or
        [string]$Value.result -cne 'completed' -or
        [string]$Value.state -cne $ExpectedState -or
        [string]$Value.reason_code -cne 'NONE'
    ) { Throw-HarnessSafe 'Harness broker result is invalid' }
}

function Throw-HarnessBrokerFailure {
    param([object]$Value)
    if ($null -eq $Value) { Throw-HarnessSafe 'Harness broker is unavailable' }
    if ([string]$Value.reason_code -ceq 'BROKER_PROVISIONING') { Throw-HarnessSafe 'Harness broker provisioning is required' }
    if ([string]$Value.reason_code -ceq 'BROKER_TIMEOUT' -or [string]$Value.classification -ceq 'TIMEOUT') { Throw-HarnessSafe 'Harness broker timed out' }
    if ([string]$Value.reason_code -ceq 'BROKER_RESULT_UNKNOWN') { Throw-HarnessSafe 'Harness broker operation result is unknown' }
    if ([string]$Value.classification -ceq 'DRIFT') { Throw-HarnessSafe 'Harness broker result is invalid' }
    Throw-HarnessSafe 'Harness broker is unavailable'
}

function Invoke-HarnessBrokerReconcile {
    param([string]$StatePath, [object]$Binding, [hashtable]$Dependencies, [string]$BrokerAction, [string]$ExpectedState)
    $brokerConfigFingerprint = & $Dependencies.BrokerBinding
    $operationId = Read-HarnessBrokerPrivateState $StatePath $BrokerAction $Binding $brokerConfigFingerprint
    $value = & $Dependencies.BrokerOperation 'reconcile' $operationId
    Assert-HarnessBrokerResult $value $ExpectedState
}

function Resume-OfficerMutation {
    param([string]$SelectedScenario, [string]$StatePath, [object]$Binding, [object]$Checkpoint, [hashtable]$Dependencies)
    if ($Checkpoint.step -in @('grant_intent', 'grant_result')) {
        Invoke-HarnessBrokerReconcile $StatePath $Binding $Dependencies 'grant' 'ready_officer'
        Save-HarnessCheckpoint $StatePath $SelectedScenario 'grant_reconcile' $Binding 'reconciled'
        return 'grant_reconcile'
    }
    if ($Checkpoint.step -in @('restore_intent', 'restore_result')) {
        Invoke-HarnessBrokerReconcile $StatePath $Binding $Dependencies 'restore' 'ready_basic'
        Save-HarnessCheckpoint $StatePath $SelectedScenario 'restore_reconcile' $Binding 'reconciled'
        return 'restore_reconcile'
    }
    if ($Checkpoint.step -in @('logout_intent', 'logout_result')) {
        if (-not (Test-BasicAcceptanceObservation (& $Dependencies.Observation) -Terminal)) { Throw-HarnessSafe 'Harness mutation reconcile is required' }
        Save-HarnessCheckpoint $StatePath $SelectedScenario 'logout_reconcile' $Binding 'reconciled'
        return 'logout_reconcile'
    }
    return [string]$Checkpoint.step
}

function Invoke-OfficerBrokerMutation {
    param([string]$SelectedScenario, [string]$StatePath, [object]$Binding, [hashtable]$Dependencies, [string]$BrokerAction, [string]$Intent, [string]$ResultStep, [string]$ExpectedState)
    $brokerConfigFingerprint = & $Dependencies.BrokerBinding
    $operationId = Save-HarnessBrokerPrivateState $StatePath $BrokerAction $Binding $brokerConfigFingerprint
    Save-HarnessCheckpoint $StatePath $SelectedScenario $Intent $Binding 'intent'
    $value = & $Dependencies.BrokerOperation $BrokerAction $operationId
    Assert-HarnessBrokerResult $value $ExpectedState
    Save-HarnessCheckpoint $StatePath $SelectedScenario $ResultStep $Binding 'mutation_returned'
    Invoke-HarnessBrokerReconcile $StatePath $Binding $Dependencies $BrokerAction $ExpectedState
}

function Invoke-OfficerLogoutMutation {
    param([string]$SelectedScenario, [string]$StatePath, [object]$Binding, [hashtable]$Dependencies)
    Save-HarnessCheckpoint $StatePath $SelectedScenario 'logout_intent' $Binding 'intent'
    Invoke-HarnessAction $Dependencies 'logout' @('logged_out') | Out-Null
    Save-HarnessCheckpoint $StatePath $SelectedScenario 'logout_result' $Binding 'mutation_returned'
    if (-not (Test-BasicAcceptanceObservation (& $Dependencies.Observation) -Terminal)) { Throw-HarnessSafe 'Harness mutation reconcile is required' }
}

function Invoke-OfficerScenario {
    param([string]$SelectedScenario, [string]$StatePath, [object]$Binding, [object]$Checkpoint, [hashtable]$Dependencies)
    $step = if ($null -eq $Checkpoint) { 'start' } else { Resume-OfficerMutation $SelectedScenario $StatePath $Binding $Checkpoint $Dependencies }
    if ($step -eq 'completed') {
        $terminal = & $Dependencies.Observation
        if (Test-BasicAcceptanceObservation $terminal -Terminal) { return New-HarnessEnvelope $SelectedScenario 'PASS' 'none' 'completed' 'accepted' 'NONE' }
        return New-HarnessEnvelope $SelectedScenario 'DRIFT' 'none' 'completed' 'stopped' 'LOGOUT_PURGE_INVALID'
    }
    if ($step -in @('start', 'broker_gate')) {
        $baseline = & $Dependencies.Observation
        if (-not (Test-BasicAcceptanceObservation $baseline)) { Save-HarnessCheckpoint $StatePath $SelectedScenario 'stopped' $Binding 'evidence_gap'; return New-HarnessEnvelope $SelectedScenario 'EVIDENCE_GAP' 'none' 'basic_baseline' 'stopped' (Get-HarnessObservationFailure $baseline) }
        $brokerStatus = & $Dependencies.BrokerStatus
        if ([string]$brokerStatus.classification -ceq 'OWNER_ACTION_REQUIRED' -and [string]$brokerStatus.reason_code -ceq 'BROKER_PROVISIONING') { Save-HarnessCheckpoint $StatePath $SelectedScenario 'broker_gate' $Binding 'owner_action_required'; return New-HarnessEnvelope $SelectedScenario 'OWNER_ACTION_REQUIRED' 'BROKER_PROVISIONING' 'broker_gate' 'stopped' 'BROKER_PROVISIONING' }
        if ([string]$brokerStatus.classification -cne 'PASS') { Throw-HarnessBrokerFailure $brokerStatus }
        if ([string]$brokerStatus.result -cne 'available' -or [string]$brokerStatus.state -cne 'private_exact' -or [string]$brokerStatus.reason_code -cne 'NONE') { Throw-HarnessSafe 'Harness broker result is invalid' }
        Invoke-OfficerBrokerMutation $SelectedScenario $StatePath $Binding $Dependencies 'grant' 'grant_intent' 'grant_result' 'ready_officer'
        Save-HarnessCheckpoint $StatePath $SelectedScenario 'grant_reconcile' $Binding 'reconciled'; $step = 'grant_reconcile'
    }
    if ($step -eq 'grant_reconcile') {
        Invoke-HarnessAction $Dependencies 'cold-launch' $script:HarnessColdLaunchResults | Out-Null
        $online = & $Dependencies.Observation
        if ($online.principal -ne 'officer' -or $online.provenance -ne 'fresh_server' -or $online.aggregate -ne 'officer_valid' -or $online.report_entry -ne 'present' -or $online.report -notin @('ready', 'empty')) { Throw-HarnessSafe 'Officer online producer observation is invalid' }
        Save-HarnessCheckpoint $StatePath $SelectedScenario 'officer_online' $Binding 'observed'; $step = 'officer_online'
    }
    if ($step -eq 'officer_online') {
        $originalNetwork = & $Dependencies.NetworkGet; $networkChanged = $false
        try {
            & $Dependencies.NetworkSet 'off'; $networkChanged = $true
            $offline = & $Dependencies.Observation
            if ($offline.principal -ne 'officer' -or $offline.provenance -ne 'offline_cache' -or $offline.report_entry -ne 'present' -or $offline.report -ne 'offline_cached_readonly') { Throw-HarnessSafe 'Officer offline producer observation is invalid' }
            Save-HarnessCheckpoint $StatePath $SelectedScenario 'offline_observed' $Binding 'observed'
        }
        finally { if ($networkChanged) { & $Dependencies.NetworkSet $originalNetwork } }
        $step = 'offline_observed'
    }
    if ($step -eq 'offline_observed') {
        Invoke-OfficerBrokerMutation $SelectedScenario $StatePath $Binding $Dependencies 'restore' 'restore_intent' 'restore_result' 'ready_basic'
        Save-HarnessCheckpoint $StatePath $SelectedScenario 'restore_reconcile' $Binding 'reconciled'; $step = 'restore_reconcile'
    }
    if ($step -eq 'restore_reconcile') {
        Invoke-HarnessAction $Dependencies 'cold-launch' $script:HarnessColdLaunchResults | Out-Null
        $restored = & $Dependencies.Observation
        if (-not (Test-BasicAcceptanceObservation $restored)) { Throw-HarnessSafe 'Officer restore purge observation is invalid' }
        Save-HarnessCheckpoint $StatePath $SelectedScenario 'basic_restored' $Binding 'observed'; $step = 'basic_restored'
    }
    if ($step -eq 'basic_restored') {
        Invoke-OfficerLogoutMutation $SelectedScenario $StatePath $Binding $Dependencies
        Save-HarnessCheckpoint $StatePath $SelectedScenario 'logout_reconcile' $Binding 'reconciled'; $step = 'logout_reconcile'
    }
    if ($step -eq 'logout_reconcile') {
        Invoke-HarnessAction $Dependencies 'cold-launch' $script:HarnessColdLaunchResults | Out-Null
        $terminal = & $Dependencies.Observation
        if (-not (Test-BasicAcceptanceObservation $terminal -Terminal)) { Throw-HarnessSafe 'Officer logout purge observation is invalid' }
        Save-HarnessCheckpoint $StatePath $SelectedScenario 'completed' $Binding 'accepted'
        return New-HarnessEnvelope $SelectedScenario 'PASS' 'none' 'completed' 'accepted' 'NONE'
    }
    Throw-HarnessSafe 'Harness checkpoint is malformed'
}

function Invoke-MobileStagingAcceptanceMain {
    param([string]$SelectedScenario, [string]$SelectedMode, [string]$ExpectedCommit, [string]$LauncherConfigPath, [string]$StatePath, [bool]$IsResume, [hashtable]$Dependencies, [string]$PrivateBrokerConfigPath = '')
    Assert-HarnessArguments $SelectedScenario $SelectedMode $ExpectedCommit $LauncherConfigPath $StatePath
    if ($null -eq $Dependencies) { $Dependencies = New-MobileAcceptanceDependencies $SelectedMode $ExpectedCommit $LauncherConfigPath $PrivateBrokerConfigPath }
    if (-not (& $Dependencies.CheckpointPolicy $StatePath)) { return New-HarnessEnvelope $SelectedScenario 'DRIFT' 'none' 'start' 'stopped' 'CHECKPOINT_PATH_INVALID' }
    $lock = $null
    try {
        $lock = Enter-HarnessLock $StatePath
        $checkpoint = Read-HarnessCheckpoint $StatePath
        if ($null -eq $checkpoint -and $IsResume) { return New-HarnessEnvelope $SelectedScenario 'DRIFT' 'none' 'start' 'stopped' 'CHECKPOINT_MISSING' }
        if ($null -ne $checkpoint -and -not $IsResume) { return New-HarnessEnvelope $SelectedScenario 'DRIFT' 'none' 'start' 'stopped' 'CHECKPOINT_RESUME_REQUIRED' }
        if ($null -ne $checkpoint -and $checkpoint.scenario -cne $SelectedScenario) { return New-HarnessEnvelope $SelectedScenario 'DRIFT' 'none' 'start' 'stopped' 'CHECKPOINT_SCENARIO_DRIFT' }
        $binding = Invoke-HarnessPreparation $Dependencies $checkpoint
        Assert-HarnessBinding $binding $ExpectedCommit
        if ($null -ne $checkpoint -and -not (Test-HarnessBindingEqual $checkpoint.binding $binding)) { return New-HarnessEnvelope $SelectedScenario 'DRIFT' 'none' 'start' 'stopped' 'CHECKPOINT_BINDING_DRIFT' }
        if ($SelectedScenario -eq 'basic-authorization') {
            if ($null -eq $checkpoint) {
                Save-HarnessCheckpoint $StatePath $SelectedScenario 'await_observation' $binding 'prepared'
            }
            return Invoke-BasicScenario $SelectedScenario $StatePath $binding $checkpoint $Dependencies
        }
        return Invoke-OfficerScenario $SelectedScenario $StatePath $binding $checkpoint $Dependencies
    }
    catch {
        return New-HarnessEnvelope $SelectedScenario (Get-HarnessFailureClassification $_.Exception.Message) 'none' 'stopped' 'stopped' (Get-HarnessFailureReasonCode $_.Exception.Message)
    }
    finally { if ($null -ne $lock) { Remove-HarnessLock $StatePath $lock } }
}

if ($MyInvocation.InvocationName -ne '.') {
    try { $envelope = Invoke-MobileStagingAcceptanceMain $Scenario $Mode $Commit $ConfigPath $CheckpointPath ([bool]$Resume) $null $BrokerConfigPath }
    catch { $envelope = New-HarnessEnvelope $Scenario (Get-HarnessFailureClassification $_.Exception.Message) 'none' 'start' 'stopped' (Get-HarnessFailureReasonCode $_.Exception.Message) }
    try { Write-HarnessJson $envelope }
    catch {
        $envelope = New-HarnessEnvelope 'unknown' 'FAILED' 'none' 'start' 'stopped' 'OUTPUT_REDACTION_FAILED'
        Write-HarnessJson $envelope
    }
    if ($envelope.classification -eq 'PASS') { exit 0 }
    exit 2
}
