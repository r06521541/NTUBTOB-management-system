param(
    [string]$Action,
    [string]$OperationId,
    [string]$ConfigPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Net.Http

$script:BrokerOperations = @('inspect', 'reset', 'grant', 'restore', 'reconcile')
$script:BrokerProject = 'ntubtob-mobile-staging'
$script:BrokerRegion = 'asia-east1'
$script:BrokerService = 'mobile-staging-broker'
$script:BrokerOperationIdPattern = '^[A-Za-z0-9_-]{16,64}$'
$script:BrokerDigestPattern = '^sha256:[0-9a-f]{64}$'
$script:BrokerIdentityPattern = '^[a-z][a-z0-9-]{4,28}[a-z0-9]@[a-z][a-z0-9-]{4,62}\.iam\.gserviceaccount\.com$'
$script:BrokerAccountPattern = '^[A-Za-z0-9.!#$%&''*+/=?^_`{|}~-]{1,64}@[A-Za-z0-9.-]{3,190}$'
$script:BrokerReasonCodes = @(
    'NONE', 'REQUEST_INVALID', 'LOCK_UNAVAILABLE', 'INTENT_CONFLICT',
    'OPERATION_IN_PROGRESS', 'JOURNAL_CONFLICT', 'OPERATION_NOT_FOUND',
    'CONFIG_INVALID', 'SECRET_UNAVAILABLE', 'SECRET_INVALID', 'INSPECT_DRIFT',
    'OPERATOR_UNKNOWN', 'POSTCHECK_MISMATCH', 'RECONCILE_REQUIRED'
)

function Throw-BrokerClientSafe {
    param([string]$Message)
    throw [InvalidOperationException]::new($Message)
}

function Assert-BrokerClientSafeText {
    param([string]$Text)
    if ($Text -match '(?i)(postgres(?:ql)?://|provider[_ -]?subject|bearer\s|identity[_ -]?token|private\.invalid|https?://|secret[_ -]?version|keystore|raw[_ -]?response|raw[_ -]?exception)') {
        Throw-BrokerClientSafe 'Broker output failed the sensitive-field gate'
    }
}

function Get-BrokerObjectFieldNames {
    param([object]$Value)
    if ($null -eq $Value) { return @() }
    return @($Value.PSObject.Properties.Name)
}

function Assert-BrokerExactProperties {
    param([object]$Value, [string[]]$Expected, [string]$Label)
    if ($null -eq $Value) { Throw-BrokerClientSafe "$Label is malformed" }
    $actual = @(Get-BrokerObjectFieldNames $Value | Sort-Object)
    $wanted = @($Expected | Sort-Object)
    if (($actual -join "`n") -cne ($wanted -join "`n")) { Throw-BrokerClientSafe "$Label is malformed" }
}

function Load-BrokerClientConfig {
    param([string]$Path)
    if (-not $Path -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) { Throw-BrokerClientSafe 'Broker configuration is unavailable' }
    try { $config = Get-Content -LiteralPath $Path -Encoding UTF8 -Raw | ConvertFrom-Json }
    catch { Throw-BrokerClientSafe 'Broker configuration is malformed' }
    $fields = @(
        'schema_version', 'provisioned', 'project', 'region', 'service',
        'operator_account', 'caller_identity', 'runtime_identity', 'image_digest',
        'gcloud_executable', 'gcloud_sha256', 'lock_path'
    )
    Assert-BrokerExactProperties $config $fields 'Broker configuration'
    if (
        $config.schema_version -ne 1 -or
        $config.provisioned -isnot [bool] -or
        $config.project -cne $script:BrokerProject -or
        $config.region -cne $script:BrokerRegion -or
        $config.service -cne $script:BrokerService -or
        [string]$config.operator_account -notmatch $script:BrokerAccountPattern -or
        [string]$config.caller_identity -notmatch $script:BrokerIdentityPattern -or
        [string]$config.runtime_identity -notmatch $script:BrokerIdentityPattern -or
        [string]$config.image_digest -notmatch $script:BrokerDigestPattern -or
        [string]$config.gcloud_sha256 -notmatch '^[0-9a-f]{64}$'
    ) { Throw-BrokerClientSafe 'Broker configuration is not exact' }
    $gcloudPath = [IO.Path]::GetFullPath([string]$config.gcloud_executable)
    $lockPath = [IO.Path]::GetFullPath([string]$config.lock_path)
    if (
        -not [IO.Path]::IsPathRooted($gcloudPath) -or $gcloudPath.StartsWith('\\') -or
        [IO.Path]::GetFileName($gcloudPath) -cne 'gcloud.cmd' -or
        -not $lockPath.StartsWith('E:\codex-evidence\task-134\', [StringComparison]::OrdinalIgnoreCase)
    ) { Throw-BrokerClientSafe 'Broker configuration path is not approved' }
    $approvedGcloudPaths = @(
        [IO.Path]::Combine([Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData), 'Google', 'Cloud SDK', 'google-cloud-sdk', 'bin', 'gcloud.cmd'),
        [IO.Path]::Combine([Environment]::GetFolderPath([Environment+SpecialFolder]::ProgramFiles), 'Google', 'Cloud SDK', 'google-cloud-sdk', 'bin', 'gcloud.cmd'),
        [IO.Path]::Combine([Environment]::GetFolderPath([Environment+SpecialFolder]::ProgramFilesX86), 'Google', 'Cloud SDK', 'google-cloud-sdk', 'bin', 'gcloud.cmd')
    )
    if (@($approvedGcloudPaths | Where-Object { $_ -and $gcloudPath.Equals([IO.Path]::GetFullPath($_), [StringComparison]::OrdinalIgnoreCase) }).Count -ne 1) {
        Throw-BrokerClientSafe 'Broker configuration path is not approved'
    }
    if (-not (Test-Path -LiteralPath ([string]$config.gcloud_executable) -PathType Leaf)) { Throw-BrokerClientSafe 'Broker executable is unavailable' }
    $pathCursor = Get-Item -LiteralPath $gcloudPath -Force
    for ($depth = 0; $depth -lt 4 -and $null -ne $pathCursor; $depth++) {
        if (($pathCursor.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { Throw-BrokerClientSafe 'Broker executable is not exact' }
        $pathCursor = $pathCursor.Parent
    }
    try { $actualGcloudHash = (Get-FileHash -LiteralPath $gcloudPath -Algorithm SHA256).Hash.ToLowerInvariant() }
    catch { Throw-BrokerClientSafe 'Broker executable is unavailable' }
    if ($actualGcloudHash -cne [string]$config.gcloud_sha256) { Throw-BrokerClientSafe 'Broker executable is not exact' }
    return $config
}

function Quote-BrokerArgument {
    param([string]$Value)
    if ($Value -notmatch '[\s"]') { return $Value }
    return '"' + ($Value -replace '(\\*)"', '$1$1\"' -replace '(\\+)$', '$1$1') + '"'
}

function Initialize-BrokerBoundedProcessType {
    if ('Task134BoundedProcess' -as [type]) { return }
    Add-Type -TypeDefinition @'
using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Threading.Tasks;

public sealed class Task134ProcessResult {
    public bool TimedOut { get; set; }
    public bool Overflow { get; set; }
    public int ExitCode { get; set; }
    public string Stdout { get; set; }
    public string Stderr { get; set; }
}

public static class Task134BoundedProcess {
    private static string ReadBounded(Stream stream, int maximumBytes) {
        using (var result = new MemoryStream()) {
        var buffer = new byte[1024];
        int count;
        while ((count = stream.Read(buffer, 0, buffer.Length)) > 0) {
            if (result.Length + count > maximumBytes) {
                throw new InvalidDataException("bounded output exceeded");
            }
            result.Write(buffer, 0, count);
        }
        return new UTF8Encoding(false, true).GetString(result.ToArray());
        }
    }

    public static Task134ProcessResult Run(string file, string arguments, int timeoutMilliseconds, int maximumBytes) {
        using (var process = new Process()) {
            process.StartInfo = new ProcessStartInfo {
                FileName = file,
                Arguments = arguments,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true
            };
            if (!process.Start()) throw new InvalidOperationException("process start failed");
            var stdout = Task.Factory.StartNew(() => ReadBounded(process.StandardOutput.BaseStream, maximumBytes));
            var stderr = Task.Factory.StartNew(() => ReadBounded(process.StandardError.BaseStream, maximumBytes));
            if (!process.WaitForExit(timeoutMilliseconds)) {
                try { process.Kill(); } catch { }
                return new Task134ProcessResult { TimedOut = true, ExitCode = -1, Stdout = "", Stderr = "" };
            }
            try {
                Task.WaitAll(new Task[] { stdout, stderr }, 5000);
                if (!stdout.IsCompleted || !stderr.IsCompleted) throw new InvalidDataException("bounded read incomplete");
                return new Task134ProcessResult {
                    TimedOut = false,
                    Overflow = false,
                    ExitCode = process.ExitCode,
                    Stdout = stdout.Result,
                    Stderr = stderr.Result
                };
            }
            catch {
                try { process.Kill(); } catch { }
                return new Task134ProcessResult { TimedOut = false, Overflow = true, ExitCode = -1, Stdout = "", Stderr = "" };
            }
        }
    }
}
'@
}

function Invoke-BrokerExternalProcess {
    param([string]$File, [string[]]$Arguments, [int]$TimeoutSeconds, [int]$MaximumCharacters = 32768)
    try {
        Initialize-BrokerBoundedProcessType
        $argumentText = (($Arguments | ForEach-Object { Quote-BrokerArgument ([string]$_) }) -join ' ')
        $result = [Task134BoundedProcess]::Run($File, $argumentText, $TimeoutSeconds * 1000, $MaximumCharacters)
        if ($result.Overflow) { Throw-BrokerClientSafe 'Broker external process output is invalid' }
        return $result
    }
    catch {
        if ($_.Exception.Message -ceq 'Broker external process output is invalid') { Throw-BrokerClientSafe 'Broker external process output is invalid' }
        Throw-BrokerClientSafe 'Broker external process failed safely'
    }
    finally { $argumentText = $null }
}

function Enter-BrokerClientLock {
    param([object]$Config)
    $path = [IO.Path]::GetFullPath([string]$Config.lock_path)
    $directory = [IO.Path]::GetDirectoryName($path)
    if (-not (Test-Path -LiteralPath $directory -PathType Container)) { Throw-BrokerClientSafe 'Broker lock directory is unavailable' }
    $stream = $null
    $created = $false
    try {
        $stream = [IO.File]::Open($path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        $created = $true
        Write-BrokerClientLockMarker $stream
        return [pscustomobject]@{ Stream = $stream; Path = $path }
    }
    catch {
        if ($null -ne $stream) { try { $stream.Dispose() } catch {} }
        if ($created -and (Test-Path -LiteralPath $path -PathType Leaf)) { try { Remove-Item -LiteralPath $path -Force } catch {} }
        Throw-BrokerClientSafe 'Broker task lock is unavailable'
    }
}

function Write-BrokerClientLockMarker {
    param([IO.Stream]$Stream)
    $bytes = [Text.Encoding]::ASCII.GetBytes('TASK-134')
    $Stream.Write($bytes, 0, $bytes.Length)
    $Stream.Flush()
}

function Remove-BrokerClientLock {
    param([object]$Config, [object]$Lock)
    if ($null -eq $Lock) { return $true }
    $clean = $true
    try { $Lock.Stream.Dispose() } catch { $clean = $false }
    try {
        if (Test-Path -LiteralPath ([string]$Lock.Path) -PathType Leaf) { Remove-Item -LiteralPath ([string]$Lock.Path) -Force }
    }
    catch { $clean = $false }
    return $clean
}

function ConvertFrom-BrokerBoundedJson {
    param([string]$Raw, [int]$MaximumBytes, [string]$Failure)
    if ([string]::IsNullOrWhiteSpace($Raw) -or [Text.Encoding]::UTF8.GetByteCount($Raw) -gt $MaximumBytes) { Throw-BrokerClientSafe $Failure }
    try { return $Raw | ConvertFrom-Json }
    catch { Throw-BrokerClientSafe $Failure }
}

function Get-BrokerIamState {
    param([object]$Config)
    $result = Invoke-BrokerExternalProcess ([string]$Config.gcloud_executable) @(
        'run', 'services', 'get-iam-policy', [string]$Config.service,
        "--project=$($Config.project)", "--region=$($Config.region)", '--format=json'
    ) 30
    if ($result.TimedOut) { Throw-BrokerClientSafe 'Broker external process timed out' }
    if ($result.ExitCode -ne 0) { Throw-BrokerClientSafe 'Broker IAM inventory failed safely' }
    $policy = ConvertFrom-BrokerBoundedJson ([string]$result.Stdout) 16384 'Broker IAM inventory is malformed'
    $bindings = @($policy.bindings)
    $expectedMember = 'serviceAccount:' + [string]$Config.caller_identity
    $invokerMembers = @()
    foreach ($binding in $bindings) {
        $members = @($binding.members)
        if ($members -contains 'allUsers' -or $members -contains 'allAuthenticatedUsers') { Throw-BrokerClientSafe 'Broker IAM boundary is public' }
        if ([string]$binding.role -ceq 'roles/run.invoker') {
            if ($null -ne $binding.PSObject.Properties['condition']) { Throw-BrokerClientSafe 'Broker caller IAM is not exact' }
            $invokerMembers += $members
        }
    }
    $uniqueInvokerMembers = @($invokerMembers | Sort-Object -Unique)
    if ($invokerMembers.Count -ne 1 -or $uniqueInvokerMembers.Count -ne 1 -or $uniqueInvokerMembers[0] -cne $expectedMember) { Throw-BrokerClientSafe 'Broker caller IAM is not exact' }
    return 'private_exact'
}

function Get-BrokerRuntimeBinding {
    param([object]$Config)
    $account = Invoke-BrokerExternalProcess ([string]$Config.gcloud_executable) @('config', 'get-value', 'account', '--quiet') 20
    if ($account.TimedOut) { Throw-BrokerClientSafe 'Broker external process timed out' }
    if ($account.ExitCode -ne 0 -or $account.Stdout.Trim() -cne [string]$Config.operator_account) { Throw-BrokerClientSafe 'Broker operator account is not exact' }
    $service = Invoke-BrokerExternalProcess ([string]$Config.gcloud_executable) @(
        'run', 'services', 'describe', [string]$Config.service,
        "--project=$($Config.project)", "--region=$($Config.region)", '--format=json'
    ) 30
    if ($service.TimedOut) { Throw-BrokerClientSafe 'Broker external process timed out' }
    if ($service.ExitCode -ne 0) { Throw-BrokerClientSafe 'Broker service inventory failed safely' }
    $metadata = ConvertFrom-BrokerBoundedJson ([string]$service.Stdout) 32768 'Broker service inventory is malformed'

    try {
        $uri = [string]$metadata.status.url
        $runtimeIdentity = [string]$metadata.spec.template.spec.serviceAccountName
        $containers = @($metadata.spec.template.spec.containers)
        $image = if ($containers.Count -eq 1) { [string]$containers[0].image } else { '' }
        $trafficEntries = @($metadata.status.traffic)
        $readyRevision = [string]$metadata.status.latestReadyRevisionName
        $exactTraffic = @($trafficEntries | Where-Object { $_.percent -eq 100 -and [string]$_.revisionName -ceq $readyRevision })
        $traffic = if ($trafficEntries.Count -eq 1 -and $exactTraffic.Count -eq 1) { 100 } else { 0 }
        $ingress = [string]$metadata.metadata.annotations.'run.googleapis.com/ingress'
        $maxInstances = [int]$metadata.spec.template.metadata.annotations.'autoscaling.knative.dev/maxScale'
        $concurrency = [int]$metadata.spec.template.spec.containerConcurrency
        $readyConditions = @($metadata.status.conditions | Where-Object { $_.type -ceq 'Ready' -and [string]$_.status -ceq 'True' })
        $ready = $readyConditions.Count -eq 1
    }
    catch { Throw-BrokerClientSafe 'Broker service inventory is malformed' }
    $parsedUri = $null
    try { $parsedUri = [Uri]::new($uri) } catch { Throw-BrokerClientSafe 'Broker service metadata is not exact' }
    if (
        $parsedUri.Scheme -cne 'https' -or $parsedUri.AbsolutePath -cne '/' -or
        $parsedUri.Query -or $parsedUri.Fragment -or
        -not $parsedUri.Host.StartsWith(([string]$Config.service + '-'), [StringComparison]::OrdinalIgnoreCase) -or
        -not (
            $parsedUri.Host.EndsWith('.asia-east1.run.app', [StringComparison]::OrdinalIgnoreCase) -or
            $parsedUri.Host.EndsWith('-de.a.run.app', [StringComparison]::OrdinalIgnoreCase)
        ) -or
        $runtimeIdentity -cne [string]$Config.runtime_identity -or
        -not $image.EndsWith('@' + [string]$Config.image_digest, [StringComparison]::Ordinal) -or
        $traffic -ne 100 -or $ingress -cne 'all' -or
        $maxInstances -ne 1 -or $concurrency -ne 1 -or -not $ready
    ) { Throw-BrokerClientSafe 'Broker service metadata is not exact' }
    if ((Get-BrokerIamState $Config) -cne 'private_exact') { Throw-BrokerClientSafe 'Broker IAM boundary is not exact' }
    return [pscustomobject]@{ Uri = $uri }
}

function Read-BrokerBoundedHttpBody {
    param([Net.Http.HttpContent]$Content, [int]$MaximumBytes)
    if ($null -eq $Content) { Throw-BrokerClientSafe 'Broker HTTP response is malformed' }
    $contentLength = $Content.Headers.ContentLength
    if ($null -ne $contentLength -and [long]$contentLength -gt $MaximumBytes) { Throw-BrokerClientSafe 'Broker HTTP response is malformed' }
    $stream = $null
    $memory = [IO.MemoryStream]::new()
    try {
        $stream = $Content.ReadAsStreamAsync().GetAwaiter().GetResult()
        $buffer = [byte[]]::new(1024)
        while (($count = $stream.Read($buffer, 0, $buffer.Length)) -gt 0) {
            if ($memory.Length + $count -gt $MaximumBytes) { Throw-BrokerClientSafe 'Broker HTTP response is malformed' }
            $memory.Write($buffer, 0, $count)
        }
        return [Text.Encoding]::UTF8.GetString($memory.ToArray())
    }
    finally {
        if ($null -ne $stream) { $stream.Dispose() }
        $memory.Dispose()
    }
}

function Invoke-BrokerIdentityTokenExchange {
    param([string]$AccessToken, [string]$CallerIdentity, [string]$Audience)
    $handler = [Net.Http.HttpClientHandler]::new()
    $handler.AllowAutoRedirect = $false
    $handler.UseCookies = $false
    $client = [Net.Http.HttpClient]::new($handler)
    $request = $null
    $content = $null
    $response = $null
    try {
        $client.Timeout = [TimeSpan]::FromSeconds(30)
        $encodedIdentity = [Uri]::EscapeDataString($CallerIdentity)
        $request = [Net.Http.HttpRequestMessage]::new(
            [Net.Http.HttpMethod]::Post,
            "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/$encodedIdentity`:generateIdToken"
        )
        $request.Headers.Authorization = [Net.Http.Headers.AuthenticationHeaderValue]::new('Bearer', $AccessToken)
        $json = [ordered]@{ audience = $Audience; includeEmail = $true } | ConvertTo-Json -Compress
        $content = [Net.Http.StringContent]::new($json, [Text.Encoding]::UTF8, 'application/json')
        $request.Content = $content
        $response = $client.SendAsync(
            $request,
            [Net.Http.HttpCompletionOption]::ResponseHeadersRead
        ).GetAwaiter().GetResult()
        if ([int]$response.StatusCode -ne 200) { Throw-BrokerClientSafe 'Broker identity token is unavailable' }
        return Read-BrokerBoundedHttpBody $response.Content 12288
    }
    catch {
        if ($_.Exception.Message -ceq 'Broker identity token is unavailable') { Throw-BrokerClientSafe 'Broker identity token is unavailable' }
        Throw-BrokerClientSafe 'Broker identity token is unavailable'
    }
    finally {
        if ($null -ne $response) { $response.Dispose() }
        if ($null -ne $content) { $content.Dispose() }
        if ($null -ne $request) { $request.Dispose() }
        $client.Dispose()
        $handler.Dispose()
        $json = $null
        $encodedIdentity = $null
    }
}

function Get-BrokerIdentityToken {
    param([object]$Config, [string]$Uri)
    $accessToken = $null
    $rawExchange = $null
    $exchange = $null
    $result = Invoke-BrokerExternalProcess ([string]$Config.gcloud_executable) @('auth', 'print-access-token', '--quiet') 30
    if ($result.TimedOut) { Throw-BrokerClientSafe 'Broker external process timed out' }
    if ($result.ExitCode -ne 0) { Throw-BrokerClientSafe 'Broker identity token is unavailable' }
    try {
        $accessToken = $result.Stdout.Trim()
        if ($accessToken.Length -lt 32 -or $accessToken.Length -gt 8192 -or $accessToken -notmatch '^[A-Za-z0-9._~-]+$') { Throw-BrokerClientSafe 'Broker identity token is invalid' }
        $rawExchange = Invoke-BrokerIdentityTokenExchange $accessToken ([string]$Config.caller_identity) $Uri
        $exchange = ConvertFrom-BrokerBoundedJson $rawExchange 12288 'Broker identity token is invalid'
        Assert-BrokerExactProperties $exchange @('token') 'Broker identity token result'
        $token = [string]$exchange.token
        if ($token.Length -lt 32 -or $token.Length -gt 8192 -or $token -notmatch '^[A-Za-z0-9._~-]+$') { Throw-BrokerClientSafe 'Broker identity token is invalid' }
        return $token
    }
    finally {
        $accessToken = $null
        $rawExchange = $null
        $exchange = $null
        $result = $null
    }
}

function Invoke-BrokerHttp {
    param([string]$Uri, [string]$Token, [string]$Operation, [string]$OpaqueOperationId)
    $handler = [Net.Http.HttpClientHandler]::new()
    $handler.AllowAutoRedirect = $false
    $handler.UseCookies = $false
    $client = [Net.Http.HttpClient]::new($handler)
    $request = $null
    $content = $null
    $response = $null
    try {
        $client.Timeout = [TimeSpan]::FromSeconds(30)
        $request = [Net.Http.HttpRequestMessage]::new([Net.Http.HttpMethod]::Post, ($Uri.TrimEnd('/') + '/v1/operations'))
        $request.Headers.Authorization = [Net.Http.Headers.AuthenticationHeaderValue]::new('Bearer', $Token)
        $json = [ordered]@{ operation = $Operation; operation_id = $OpaqueOperationId } | ConvertTo-Json -Compress
        $content = [Net.Http.StringContent]::new($json, [Text.Encoding]::UTF8, 'application/json')
        $request.Content = $content
        $response = $client.SendAsync(
            $request,
            [Net.Http.HttpCompletionOption]::ResponseHeadersRead
        ).GetAwaiter().GetResult()
        $body = Read-BrokerBoundedHttpBody $response.Content 4096
        return [pscustomobject]@{ StatusCode = [int]$response.StatusCode; Body = $body }
    }
    catch { Throw-BrokerClientSafe 'Broker operation result is unknown' }
    finally {
        if ($null -ne $response) { $response.Dispose() }
        if ($null -ne $content) { $content.Dispose() }
        if ($null -ne $request) { $request.Dispose() }
        $client.Dispose()
        $handler.Dispose()
        $json = $null
        $body = $null
    }
}

function ConvertFrom-BrokerResponse {
    param([object]$Response, [string]$Operation, [string]$OpaqueOperationId)
    if ($null -eq $Response -or $Response.StatusCode -lt 200 -or $Response.StatusCode -gt 599) { Throw-BrokerClientSafe 'Broker operation result is unknown' }
    $value = ConvertFrom-BrokerBoundedJson ([string]$Response.Body) 4096 'Broker operation response is malformed'
    $fields = @('classification', 'lifecycle_state', 'operation', 'operation_id', 'reason_code', 'target_state')
    Assert-BrokerExactProperties $value $fields 'Broker operation response'
    if ([string]$value.reason_code -notin $script:BrokerReasonCodes) { Throw-BrokerClientSafe 'Broker operation response is not exact' }
    if ($Response.StatusCode -ge 200 -and $Response.StatusCode -lt 300) {
        if (
            [string]$value.operation_id -cne $OpaqueOperationId -or
            $value.classification -cne 'PASS' -or $value.reason_code -cne 'NONE' -or
            $value.lifecycle_state -cne 'postcheck_complete' -or
            $value.operation -notin ($script:BrokerOperations | Where-Object { $_ -ne 'reconcile' }) -or
            $value.target_state -notin @('ready_basic', 'ready_officer', 'reset_required')
        ) { Throw-BrokerClientSafe 'Broker operation response is not exact' }
        if ($Operation -ne 'reconcile' -and $value.operation -cne $Operation) { Throw-BrokerClientSafe 'Broker operation response is not exact' }
        return [pscustomobject]@{ Classification = 'PASS'; State = [string]$value.target_state; ReasonCode = 'NONE' }
    }
    if (
        $value.classification -cne 'FAILED' -or $value.lifecycle_state -cne 'unchanged' -or
        $value.operation -cne 'none' -or $value.operation_id -cne 'none' -or
        $value.target_state -cne 'none' -or $value.reason_code -ceq 'NONE'
    ) { Throw-BrokerClientSafe 'Broker operation response is not exact' }
    return [pscustomobject]@{ Classification = 'FAILED'; State = 'unchanged'; ReasonCode = [string]$value.reason_code }
}

function New-BrokerClientEnvelope {
    param([string]$SelectedAction, [string]$Classification, [string]$Result, [string]$State, [string]$ReasonCode)
    return [ordered]@{
        action = $(if ($SelectedAction) { $SelectedAction } else { 'unknown' })
        classification = $Classification
        operator = 'agent'
        owner_gate = $(if ($Classification -eq 'OWNER_ACTION_REQUIRED') { 'BROKER_PROVISIONING' } else { 'none' })
        standing_authorization = 'DEC-098'
        stop_only_on = 'broker-provisioning|identity-or-runtime-drift|unknown-operation-result'
        report_to = 'main-work'
        retention_owner = 'TASK-134'
        details = [ordered]@{ result = $Result; state = $State; reason_code = $ReasonCode }
    }
}

function Get-BrokerClientFailureEnvelope {
    param([string]$SelectedAction, [string]$Message)
    switch -CaseSensitive ($Message) {
        'BROKER_PROVISIONING' { return New-BrokerClientEnvelope $SelectedAction 'OWNER_ACTION_REQUIRED' 'stopped' 'unavailable' 'BROKER_PROVISIONING' }
        'Broker operation result is unknown' { return New-BrokerClientEnvelope $SelectedAction 'FAILED' 'stopped' 'unknown' 'BROKER_RESULT_UNKNOWN' }
        'Broker external process timed out' { return New-BrokerClientEnvelope $SelectedAction 'TIMEOUT' 'stopped' 'unknown' 'BROKER_TIMEOUT' }
    }
    if ($Message -match '(?i)(not exact|malformed|invalid|public|lock)') { return New-BrokerClientEnvelope $SelectedAction 'DRIFT' 'stopped' 'unchanged' 'BROKER_DRIFT' }
    return New-BrokerClientEnvelope $SelectedAction 'FAILED' 'stopped' 'unknown' 'BROKER_UNAVAILABLE'
}

function Invoke-MobileStagingBrokerMain {
    param([string]$SelectedAction, [string]$OpaqueOperationId, [string]$BrokerConfigPath)
    $token = $null
    $binding = $null
    $lock = $null
    $config = $null
    $envelope = $null
    $cleanupSucceeded = $true
    try {
        if ($SelectedAction -notin @('status') + $script:BrokerOperations) { Throw-BrokerClientSafe 'Broker action is invalid' }
        if ($SelectedAction -eq 'status') {
            if ($OpaqueOperationId) { Throw-BrokerClientSafe 'Broker operation ID is invalid' }
        }
        elseif ($OpaqueOperationId -notmatch $script:BrokerOperationIdPattern) { Throw-BrokerClientSafe 'Broker operation ID is invalid' }
        $config = Load-BrokerClientConfig $BrokerConfigPath
        if ($config.provisioned -ne $true) { Throw-BrokerClientSafe 'BROKER_PROVISIONING' }
        $lock = Enter-BrokerClientLock $config
        $binding = Get-BrokerRuntimeBinding $config
        if ($SelectedAction -eq 'status') {
            $envelope = New-BrokerClientEnvelope $SelectedAction 'PASS' 'available' 'private_exact' 'NONE'
        }
        else {
            $token = Get-BrokerIdentityToken $config ([string]$binding.Uri)
            try { $response = Invoke-BrokerHttp ([string]$binding.Uri) $token $SelectedAction $OpaqueOperationId }
            catch {
                if ($_.Exception.Message -ceq 'Broker external process timed out') { Throw-BrokerClientSafe 'Broker external process timed out' }
                Throw-BrokerClientSafe 'Broker operation result is unknown'
            }
            $parsed = ConvertFrom-BrokerResponse $response $SelectedAction $OpaqueOperationId
            $envelope = New-BrokerClientEnvelope $SelectedAction ([string]$parsed.Classification) 'completed' ([string]$parsed.State) ([string]$parsed.ReasonCode)
        }
    }
    catch { $envelope = Get-BrokerClientFailureEnvelope $SelectedAction ([string]$_.Exception.Message) }
    finally {
        $token = $null
        $binding = $null
        $response = $null
        $parsed = $null
        if ($null -ne $lock) {
            try { $cleanupSucceeded = [bool](Remove-BrokerClientLock $config $lock) }
            catch { $cleanupSucceeded = $false }
        }
    }
    if (-not $cleanupSucceeded) { return New-BrokerClientEnvelope $SelectedAction 'FAILED' 'stopped' 'unknown' 'BROKER_LOCK_CLEANUP_FAILED' }
    return $envelope
}

function Write-BrokerClientJson {
    param([object]$Value)
    $json = $Value | ConvertTo-Json -Depth 6 -Compress
    Assert-BrokerClientSafeText $json
    Write-Output $json
}

if ($MyInvocation.InvocationName -ne '.') {
    try { $envelope = Invoke-MobileStagingBrokerMain $Action $OperationId $ConfigPath }
    catch { $envelope = New-BrokerClientEnvelope 'unknown' 'FAILED' 'stopped' 'unknown' 'BROKER_UNAVAILABLE' }
    try { Write-BrokerClientJson $envelope }
    catch {
        $envelope = New-BrokerClientEnvelope 'unknown' 'FAILED' 'stopped' 'unknown' 'OUTPUT_REDACTION_FAILED'
        Write-BrokerClientJson $envelope
    }
    if ($envelope.classification -eq 'PASS') { exit 0 }
    exit 2
}
