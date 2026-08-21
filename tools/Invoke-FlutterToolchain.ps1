[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet('status', 'dart', 'flutter')]
    [string]$Action,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CommandArgs
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$flutterRoot = 'E:\codex-toolchains\task-113\flutter-clean'
$dart = Join-Path $flutterRoot 'bin\cache\dart-sdk\bin\dart.exe'
$flutterSnapshot = Join-Path $flutterRoot 'bin\cache\flutter_tools.snapshot'

if (-not (Test-Path -LiteralPath $dart -PathType Leaf) -or
    -not (Test-Path -LiteralPath $flutterSnapshot -PathType Leaf)) {
    [ordered]@{
        classification = 'FAILED'
        result = 'unavailable'
        reason_code = 'TOOLCHAIN_UNAVAILABLE'
    } | ConvertTo-Json -Compress
    exit 2
}

if ($Action -ceq 'status') {
    [ordered]@{
        classification = 'PASS'
        result = 'ready'
        toolchain = 'flutter-3.47.0-dart-3.13.0'
    } | ConvertTo-Json -Compress
    exit 0
}

if ($Action -ceq 'dart') {
    & $dart @CommandArgs
    exit $LASTEXITCODE
}

$env:FLUTTER_ROOT = $flutterRoot
& $dart $flutterSnapshot @CommandArgs
exit $LASTEXITCODE
