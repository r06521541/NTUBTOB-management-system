from __future__ import annotations

import json
import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "tools" / "Invoke-MobileStagingAcceptance.ps1"
FULL_SHA = "20f393778a9010ac52ad9c8935f3992d72ce06a0"
ARTIFACT_SHA = "B" * 64
SIGNER_SHA = "A" * 64


def powershell_available() -> bool:
    return bool(os.environ.get("SystemRoot")) and (
        Path(os.environ["SystemRoot"])
        / "System32"
        / "WindowsPowerShell"
        / "v1.0"
        / "powershell.exe"
    ).is_file()


@unittest.skipUnless(powershell_available(), "Windows PowerShell is unavailable")
class MobileStagingAcceptanceHarnessTest(unittest.TestCase):
    maxDiff = None

    def run_harness(self, body: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "harness.ps1"
            script.write_text(
                "$ErrorActionPreference = 'Stop'\n"
                f". '{HARNESS.as_posix()}'\n" + textwrap.dedent(body),
                encoding="utf-8-sig",
            )
            return subprocess.run(
                [
                    "powershell.exe",
                    "-NoLogo",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )

    @staticmethod
    def binding_ps() -> str:
        return (
            "@{ accepted_sha = '"
            + FULL_SHA
            + "'; artifact_sha256 = '"
            + ARTIFACT_SHA
            + "'; signer_sha256 = '"
            + SIGNER_SHA
            + "'; package = 'tw.org.ntubtob.portal'; version = '1'; "
            "avd = 'Pixel_API'; serial = 'emulator-5554'; "
            "vocabulary_version = 'task124-package4-v1' }"
        )

    def test_parser_explicit_scope_and_no_private_broker_access(self):
        parser = subprocess.run(
            [
                "powershell.exe",
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "$e=$null;$t=$null;"
                f"[System.Management.Automation.Language.Parser]::ParseFile('{HARNESS.as_posix()}',[ref]$t,[ref]$e)|Out-Null;"
                "if($e.Count){$e|ForEach-Object{$_.Message};exit 1}",
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(parser.returncode, 0, parser.stdout + parser.stderr)
        source = HARNESS.read_text(encoding="utf-8")
        self.assertIn("basic-authorization", source)
        self.assertIn("officer-authorization-roundtrip", source)
        self.assertIn("grant_intent", source)
        self.assertIn("restore_intent", source)
        self.assertIn("logout_intent", source)
        self.assertNotIn("MOBILE_STAGING_DATABASE_URL", source)
        self.assertNotIn("MOBILE_STAGING_PROVIDER_SUBJECT", source)
        self.assertNotIn("tools.mobile_staging_data", source)
        basic_source = (ROOT / "clients" / "flutter_app" / "lib" / "basic_app.dart").read_text(
            encoding="utf-8"
        )
        report_source = (
            ROOT / "clients" / "flutter_app" / "lib" / "officer_prereview.dart"
        ).read_text(encoding="utf-8")
        self.assertIn("偵錯本機狀態：session", basic_source)
        self.assertIn("const Text('出席報表')", basic_source)
        self.assertIn("const Text('Officer／Admin 唯讀')", basic_source)
        self.assertIn("偵錯報表投影：", report_source)

    def test_production_dependency_factory_retains_delayed_bindings(self):
        result = self.run_harness(
            f"""
            function Invoke-MobileStagingMain {{
                param($action,$mode,$commit,$configPath,$approval,$preserve,$public,$purge)
                $script:captured = @($action,$mode,$commit,$configPath)
                return @{{result='ready'}}
            }}
            function Get-MobileAcceptanceArtifact {{
                param($config,$commit)
                return @{{state='drift';root=[string]$config.evidence_root;commit=$commit}}
            }}
            $config=[pscustomobject]@{{evidence_root='E:/task-owned';adb_executable='E:/safe/adb.exe';serial='emulator-5554'}}
            $deps=New-MobileAcceptanceDependenciesFromConfig 'staging' '{FULL_SHA}' 'C:/value-free.json' $config
            $artifact=& $deps.Artifact
            $action=& $deps.Action 'preflight'
            [pscustomobject]@{{artifact=$artifact;action=$action;captured=$script:captured}}|ConvertTo-Json -Depth 4 -Compress
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["artifact"]["state"], "drift")
        self.assertEqual(payload["artifact"]["root"], "E:/task-owned")
        self.assertEqual(payload["artifact"]["commit"], FULL_SHA)
        self.assertEqual(payload["action"]["result"], "ready")
        self.assertEqual(
            payload["captured"],
            ["preflight", "staging", FULL_SHA, "C:/value-free.json"],
        )

    def test_scoped_launcher_commands_survive_factory_return(self):
        result = self.run_harness(
            """
            function New-ScopedDependencies {
                function Invoke-MobileStagingMain { param($action) return @{result='ready';action=$action} }
                function Invoke-BoundedProcess { throw 'must not run' }
                function Get-ArtifactPath { param($config) return 'E:/missing-app-debug.apk' }
                function Invoke-ApkToolWithApprovedJava { throw 'must not run' }
                function Get-ApkSignerFingerprint { throw 'must not run' }
                function Get-ApkPackageIdentity { throw 'must not run' }
                $commands=@{
                    InvokeMain=(Get-Command Invoke-MobileStagingMain -CommandType Function).ScriptBlock
                    InvokeBounded=(Get-Command Invoke-BoundedProcess -CommandType Function).ScriptBlock
                    GetArtifactPath=(Get-Command Get-ArtifactPath -CommandType Function).ScriptBlock
                    InvokeApkTool=(Get-Command Invoke-ApkToolWithApprovedJava -CommandType Function).ScriptBlock
                    GetSigner=(Get-Command Get-ApkSignerFingerprint -CommandType Function).ScriptBlock
                    GetPackage=(Get-Command Get-ApkPackageIdentity -CommandType Function).ScriptBlock
                }
                $config=[pscustomobject]@{evidence_root='E:/task-owned';adb_executable='E:/safe/adb.exe';serial='emulator-5554'}
                return New-MobileAcceptanceDependenciesFromConfig 'staging' '20f393778a9010ac52ad9c8935f3992d72ce06a0' 'C:/value-free.json' $config $commands
            }
            $deps=New-ScopedDependencies
            $artifact=& $deps.Artifact
            $action=& $deps.Action 'preflight'
            [pscustomobject]@{artifact=$artifact.state;action=$action.result}|ConvertTo-Json -Compress
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"artifact": "missing", "action": "ready"})

    def test_status_action_uses_an_isolated_governed_launcher_process(self):
        result = self.run_harness(
            f"""
            $script:calls=0;$script:captured=@()
            $invoke={{param($file,$arguments,$timeout)
                $script:calls++;$script:captured=@($file)+@($arguments)+@([string]$timeout)
                $config=$arguments[$arguments.IndexOf('-ConfigPath')+1]
                if($config -ceq 'C:/recoverable.json'){{return [pscustomobject]@{{TimedOut=$false;ExitCode=2;Stdout='{{"classification":"FAILED","details":{{"reason_code":"ACCESSIBILITY_INVALID"}}}}';Stderr=''}}}}
                if($config -ceq 'C:/unknown.json'){{return [pscustomobject]@{{TimedOut=$false;ExitCode=2;Stdout='private-provider-subject-sentinel';Stderr='private-provider-subject-sentinel'}}}}
                return [pscustomobject]@{{TimedOut=$false;ExitCode=0;Stdout='{{"classification":"PASS","details":{{"action":"status","result":"observed","semantic_state":"logged_out"}}}}';Stderr=''}}
            }}
            $status=New-IsolatedLauncherStatusAction 'C:/launcher.ps1' 'staging' '{FULL_SHA}' 'C:/value-free.json' $invoke 'C:/powershell.exe'
            $first=& $status;$second=& $status
            $recoverable=New-IsolatedLauncherStatusAction 'C:/launcher.ps1' 'staging' '{FULL_SHA}' 'C:/recoverable.json' $invoke 'C:/powershell.exe'
            try {{& $recoverable|Out-Null;$recoverableError='unexpected'}}catch{{$recoverableError=$_.Exception.Message}}
            $unknown=New-IsolatedLauncherStatusAction 'C:/launcher.ps1' 'staging' '{FULL_SHA}' 'C:/unknown.json' $invoke 'C:/powershell.exe'
            try {{& $unknown|Out-Null;$unknownError='unexpected'}}catch{{$unknownError=$_.Exception.Message}}
            [pscustomobject]@{{first=$first.result;second=$second.result;recoverable=$recoverableError;unknown=$unknownError;calls=$script:calls;argv=($script:captured -join '|')}}|ConvertTo-Json -Compress
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["first"], "observed")
        self.assertEqual(payload["second"], "observed")
        self.assertEqual(payload["recoverable"], "Accessibility inventory is malformed")
        self.assertEqual(payload["unknown"], "STATUS_CHILD_STDERR")
        self.assertEqual(payload["calls"], 4)
        self.assertIn("C:/powershell.exe|-NoLogo|-NoProfile|-NonInteractive", payload["argv"])
        self.assertIn(f"-File|C:/launcher.ps1|-Action|status|-Mode|staging|-Commit|{FULL_SHA}", payload["argv"])
        self.assertNotIn("private-provider-subject-sentinel", result.stdout + result.stderr)

    def test_broker_action_isolated_envelope_and_no_disclosure(self):
        result = self.run_harness(
            """
            $script:calls=0;$script:statusArgv=$false;$script:grantArgv=$false
            $invoke={param($file,$arguments,$timeout)
                $script:calls++
                $action=$arguments[$arguments.IndexOf('-Action')+1]
                $hasId=$arguments.Contains('-OperationId')
                if($action -eq 'status'){$script:statusArgv=(-not $hasId);$details='{"result":"available","state":"private_exact","reason_code":"NONE"}'}
                elseif($action -eq 'grant'){$script:grantArgv=$hasId;$details='{"result":"completed","state":"ready_officer","reason_code":"NONE"}'}
                elseif($action -eq 'inspect'){$details='{"result":"completed","state":"ready_basic","reason_code":"NONE"}'}
                else{return [pscustomobject]@{TimedOut=$false;ExitCode=2;Stdout='private-provider-subject-sentinel';Stderr='private-provider-subject-sentinel'}}
                $ownerGate=$(if($action -eq 'inspect'){'BROKER_PROVISIONING'}else{'none'})
                $body='{"action":"'+$action+'","classification":"PASS","operator":"agent","owner_gate":"'+$ownerGate+'","standing_authorization":"DEC-098","stop_only_on":"broker-provisioning|identity-or-runtime-drift|unknown-operation-result","report_to":"main-work","retention_owner":"TASK-134","details":'+$details+'}'
                return [pscustomobject]@{TimedOut=$false;ExitCode=0;Stdout=$body;Stderr=''}
            }
            function Get-HarnessBrokerConfigFingerprint {param($path)'CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC'}
            $broker=New-IsolatedBrokerClientAction 'C:/broker.ps1' 'E:/value-free.json' 'CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC' $invoke 'C:/powershell.exe'
            $status=& $broker 'status' ''
            $grant=& $broker 'grant' '0123456789abcdef'
            try{& $broker 'inspect' '0011223344556677'|Out-Null;$governance='unexpected'}catch{$governance=$_.Exception.Message}
            try{& $broker 'restore' 'fedcba9876543210'|Out-Null;$failure='unexpected'}catch{$failure=$_.Exception.Message}
            [pscustomobject]@{status=$status.state;grant=$grant.state;calls=$script:calls;statusArgv=$script:statusArgv;grantArgv=$script:grantArgv;governance=$governance;failure=$failure}|ConvertTo-Json -Compress
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "private_exact")
        self.assertEqual(payload["grant"], "ready_officer")
        self.assertEqual(payload["calls"], 4)
        self.assertTrue(payload["statusArgv"])
        self.assertTrue(payload["grantArgv"])
        self.assertEqual(payload["governance"], "Harness broker result is invalid")
        self.assertEqual(payload["failure"], "Harness broker operation result is unknown")
        self.assertNotIn("private-provider-subject-sentinel", result.stdout + result.stderr)

    def test_broker_private_sidecar_is_atomic_bound_and_not_in_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "checkpoint.json"
            result = self.run_harness(
                f"""
                $binding={self.binding_ps()}
                $id=Save-HarnessBrokerPrivateState '{checkpoint.as_posix()}' 'grant' $binding 'CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC'
                Save-HarnessCheckpoint '{checkpoint.as_posix()}' 'officer-authorization-roundtrip' 'grant_intent' $binding 'intent'
                $read=Read-HarnessBrokerPrivateState '{checkpoint.as_posix()}' 'grant' $binding 'CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC'
                $checkpointRaw=Get-Content -LiteralPath '{checkpoint.as_posix()}' -Raw
                $privateRaw=Get-Content -LiteralPath ('{checkpoint.as_posix()}'+'.broker-grant.private.json') -Raw
                $drift=@{{}}+$binding;$drift.version='2'
                try{{Read-HarnessBrokerPrivateState '{checkpoint.as_posix()}' 'grant' $drift 'CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC'|Out-Null;$bindingFailure='unexpected'}}catch{{$bindingFailure=$_.Exception.Message}}
                $orphan='{checkpoint.as_posix()}'+'.broker-restore.private.json.deadbeef.tmp'
                Set-Content -LiteralPath $orphan -Value 'sentinel' -Encoding UTF8
                try{{Save-HarnessBrokerPrivateState '{checkpoint.as_posix()}' 'restore' $binding 'CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC'|Out-Null;$orphanFailure='unexpected'}}catch{{$orphanFailure=$_.Exception.Message}}
                [pscustomobject]@{{same=($id -ceq $read);idInCheckpoint=$checkpointRaw.Contains($id);idInPrivate=$privateRaw.Contains($id);bindingFailure=$bindingFailure;orphanFailure=$orphanFailure;successTemps=@(Get-ChildItem -LiteralPath '{directory}' -Filter '*.tmp'|Where-Object{{$_.Name -notlike '*deadbeef*'}}).Count}}|ConvertTo-Json -Compress
                """
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["same"])
            self.assertFalse(payload["idInCheckpoint"])
            self.assertTrue(payload["idInPrivate"])
            self.assertEqual(payload["bindingFailure"], "Harness broker private state is invalid")
            self.assertEqual(payload["orphanFailure"], "Harness broker private state is invalid")
            self.assertEqual(payload["successTemps"], 0)

    def test_private_file_identity_rejects_hardlink_reparse_and_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            real = root / "real"
            real.mkdir()
            source = real / "state.json"
            source.write_text("safe", encoding="utf-8")
            hardlink = root / "hardlink.json"
            os.link(source, hardlink)
            junction = root / "junction"
            linked = subprocess.run(
                ["cmd.exe", "/c", "mklink", "/J", str(junction), str(real)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(linked.returncode, 0, linked.stdout + linked.stderr)
            try:
                result = self.run_harness(
                    f"""
                    try{{Read-HarnessExactFile '{hardlink.as_posix()}' 64|Out-Null;$hardlink='unexpected'}}catch{{$hardlink=$_.Exception.Message}}
                    try{{Read-HarnessExactFile '{(junction / 'state.json').as_posix()}' 64|Out-Null;$reparse='unexpected'}}catch{{$reparse=$_.Exception.Message}}
                    $script:index=0
                    $reader={{param($path,$limit)$script:index++;[pscustomobject]@{{Text='safe';Identity=$(if($script:index -eq 1){{'A'}}else{{'B'}});FinalPath=[IO.Path]::GetFullPath($path)}}}}
                    try{{Read-HarnessExactFile '{source.as_posix()}' 64 $reader|Out-Null;$replacement='unexpected'}}catch{{$replacement=$_.Exception.Message}}
                    [pscustomobject]@{{hardlink=$hardlink;reparse=$reparse;replacement=$replacement}}|ConvertTo-Json -Compress
                    """
                )
            finally:
                junction.rmdir()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                json.loads(result.stdout),
                {
                    "hardlink": "Harness private file is invalid",
                    "reparse": "Harness private file is invalid",
                    "replacement": "Harness private file is invalid",
                },
            )

    def test_broker_config_drift_stops_before_same_id_reconcile(self):
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "checkpoint.json"
            result = self.run_harness(
                f"""
                $script:role='basic';$script:fingerprint='CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC';$script:brokerCalls=0
                $deps=New-MobileAcceptanceTestDependencies -Action {{param($name)$result=@{{preflight='ready';'avd-start'='started';'signer-check'='matched';install='replaced';'cold-launch'='running'}}[$name];@{{classification='PASS';result=$result}}}} -Artifact {{@{{state='matched';binding={self.binding_ps()}}}}} -Observation {{if($script:role -eq 'basic'){{@{{principal='basic';provenance='fresh_server';aggregate='basic_valid';report='absent';report_entry='absent';producer_gap=$false}}}}else{{@{{principal='officer';provenance='fresh_server';aggregate='officer_valid';report='ready';report_entry='present';producer_gap=$false}}}}}} -BrokerStatus {{[pscustomobject]@{{classification='PASS';result='available';state='private_exact';reason_code='NONE'}}}} -BrokerBinding {{$script:fingerprint}} -BrokerOperation {{param($action,$id)$script:brokerCalls++;$script:role='officer';throw 'Harness broker operation result is unknown'}} -CheckpointPolicy {{param($path)$true}}
                $first=Invoke-MobileStagingAcceptanceMain 'officer-authorization-roundtrip' 'staging' '{FULL_SHA}' 'C:/config.json' '{checkpoint.as_posix()}' $false $deps
                $script:fingerprint='DDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD'
                $second=Invoke-MobileStagingAcceptanceMain 'officer-authorization-roundtrip' 'staging' '{FULL_SHA}' 'C:/config.json' '{checkpoint.as_posix()}' $true $deps
                [pscustomobject]@{{first=$first.classification;second=$second.classification;reason=$second.details.reason_code;brokerCalls=$script:brokerCalls}}|ConvertTo-Json -Compress
                """
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                json.loads(result.stdout),
                {
                    "first": "EVIDENCE_GAP",
                    "second": "DRIFT",
                    "reason": "BROKER_PRIVATE_STATE_INVALID",
                    "brokerCalls": 1,
                },
            )

    def test_preaccessibility_status_reasons_are_preserved_without_retry(self):
        reasons = (
            "ADB_UNAVAILABLE",
            "ADB_INVALID",
            "PACKAGE_UNAVAILABLE",
            "PACKAGE_INVALID",
            "ACTIVITY_UNAVAILABLE",
            "ACTIVITY_INVALID",
        )
        for reason in reasons:
            with self.subTest(reason=reason):
                result = self.run_harness(
                    f"""
                    $script:attempts=0
                    $invoke={{param($file,$arguments,$timeout)
                        $script:attempts++
                        return [pscustomobject]@{{
                            TimedOut=$false;ExitCode=2
                            Stdout='{{"classification":"FAILED","details":{{"reason_code":"{reason}"}}}}'
                            Stderr=''
                        }}
                    }}
                    $status=New-IsolatedLauncherStatusAction 'C:/launcher.ps1' 'staging' '{FULL_SHA}' 'C:/value-free.json' $invoke 'C:/powershell.exe'
                    try {{
                        Get-MobileAcceptanceStatus -InvokeStatus {{& $status}} -Wait {{throw 'must not wait'}} | Out-Null
                        $message='unexpected'
                    }} catch {{$message=$_.Exception.Message}}
                    [pscustomobject]@{{
                        message=$message
                        classification=Get-HarnessFailureClassification $message
                        reason=Get-HarnessFailureReasonCode $message
                        attempts=$script:attempts
                    }}|ConvertTo-Json -Compress
                    """
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    json.loads(result.stdout),
                    {
                        "message": reason,
                        "classification": (
                            "EVIDENCE_GAP" if reason.endswith("UNAVAILABLE") else "DRIFT"
                        ),
                        "reason": reason,
                        "attempts": 1,
                    },
                )
                self.assertNotIn("must not wait", result.stdout + result.stderr)

    def test_status_child_transport_reasons_are_bounded_without_disclosure(self):
        sentinel = "private-provider-subject-sentinel"
        cases = (
            ("$true", "0", "''", "''", "STATUS_CHILD_TIMEOUT", "TIMEOUT"),
            ("$false", "0", "'{}'", f"'{sentinel}'", "STATUS_CHILD_STDERR", "EVIDENCE_GAP"),
            ("$false", "0", "''", "''", "STATUS_CHILD_OUTPUT_INVALID", "EVIDENCE_GAP"),
            ("$false", "0", "'not-json'", "''", "STATUS_CHILD_ENVELOPE_INVALID", "EVIDENCE_GAP"),
            (
                "$false",
                "2",
                "'{\"classification\":\"FAILED\",\"details\":{\"reason_code\":\"RUNTIME_FAILED\"}}'",
                "''",
                "STATUS_CHILD_RESULT_INVALID",
                "EVIDENCE_GAP",
            ),
        )
        for timed_out, exit_code, stdout, stderr, reason, classification in cases:
            with self.subTest(reason=reason):
                result = self.run_harness(
                    f"""
                    $script:attempts=0
                    $invoke={{param($file,$arguments,$timeout)
                        $script:attempts++
                        return [pscustomobject]@{{TimedOut={timed_out};ExitCode={exit_code};Stdout={stdout};Stderr={stderr}}}
                    }}
                    $status=New-IsolatedLauncherStatusAction 'C:/launcher.ps1' 'staging' '{FULL_SHA}' 'C:/value-free.json' $invoke 'C:/powershell.exe'
                    try {{Get-MobileAcceptanceStatus -InvokeStatus {{& $status}} -Wait {{throw 'must not wait'}}|Out-Null;$message='unexpected'}}
                    catch {{$message=$_.Exception.Message}}
                    [pscustomobject]@{{message=$message;classification=Get-HarnessFailureClassification $message;reason=Get-HarnessFailureReasonCode $message;attempts=$script:attempts}}|ConvertTo-Json -Compress
                    """
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    json.loads(result.stdout),
                    {"message": reason, "classification": classification, "reason": reason, "attempts": 1},
                )
                self.assertNotIn(sentinel, result.stdout + result.stderr)
        malformed_envelopes = (
            "'{}'",
            "'null'",
            "'42'",
            "'[]'",
            "'{\"classification\":\"FAILED\"}'",
            f"'{{\"classification\":\"FAILED\",\"details\":\"{sentinel}\"}}'",
        )
        for stdout in malformed_envelopes:
            with self.subTest(malformed_envelope=stdout):
                result = self.run_harness(
                    f"""
                    $script:attempts=0
                    $invoke={{param($file,$arguments,$timeout)
                        $script:attempts++
                        return [pscustomobject]@{{TimedOut=$false;ExitCode=2;Stdout={stdout};Stderr=''}}
                    }}
                    $status=New-IsolatedLauncherStatusAction 'C:/launcher.ps1' 'staging' '{FULL_SHA}' 'C:/value-free.json' $invoke 'C:/powershell.exe'
                    try {{Get-MobileAcceptanceStatus -InvokeStatus {{& $status}} -Wait {{throw 'must not wait'}}|Out-Null;$message='unexpected'}}
                    catch {{$message=$_.Exception.Message}}
                    $classification=Get-HarnessFailureClassification $message
                    $reason=Get-HarnessFailureReasonCode $message
                    Write-HarnessJson (New-HarnessEnvelope 'basic-authorization' $classification 'none' 'await_observation' 'failed' $reason)
                    exit 2
                    """
                )
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stderr, "")
                self.assertEqual(len(result.stdout.splitlines()), 1)
                envelope = json.loads(result.stdout)
                self.assertEqual(envelope["classification"], "EVIDENCE_GAP")
                self.assertEqual(envelope["details"]["reason_code"], "STATUS_CHILD_ENVELOPE_INVALID")
                self.assertNotIn(sentinel, result.stdout + result.stderr)
        source = HARNESS.read_text(encoding="utf-8")
        self.assertEqual(
            source.count(
                "if (-not (Test-Path -LiteralPath $hostExecutable -PathType Leaf)) { "
                "Throw-HarnessSafe 'STATUS_HOST_UNAVAILABLE' }"
            ),
            1,
        )
        self.assertEqual(
            "EVIDENCE_GAP",
            json.loads(
                self.run_harness(
                    "[pscustomobject]@{classification=Get-HarnessFailureClassification "
                    "'STATUS_HOST_UNAVAILABLE';reason=Get-HarnessFailureReasonCode "
                    "'STATUS_HOST_UNAVAILABLE'}|ConvertTo-Json -Compress"
                ).stdout
            )["classification"],
        )

    def test_basic_owner_gate_resume_and_artifact_preparation_matrix(self):
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "checkpoint.json"
            result = self.run_harness(
                f"""
                $script:actions = @(); $script:artifactState = 'matched'; $script:loggedOut = $true
                $deps = New-MobileAcceptanceTestDependencies -Action {{ param($name)
                    $script:actions += $name
                    $result = @{{ preflight='ready'; 'avd-start'='reused'; 'cleanup-artifact'='removed_artifact'; build='built'; 'signer-check'='matched'; install='replaced'; 'cold-launch'='timeout_but_running' }}[$name]
                    @{{ classification='PASS'; result=$result }}
                }} -Artifact {{
                    if ($script:artifactState -eq 'missing') {{ $script:artifactState='matched'; return @{{ state='missing' }} }}
                    if ($script:artifactState -eq 'drift') {{ $script:artifactState='matched'; return @{{ state='drift' }} }}
                    @{{ state='matched'; binding={self.binding_ps()} }}
                }} -Observation {{
                    if ($script:loggedOut) {{ $script:loggedOut=$false; return @{{ principal='logged_out'; provenance='none'; aggregate='absent'; report='absent'; report_entry='absent'; producer_gap=$false }} }}
                    @{{ principal='basic'; provenance='fresh_server'; aggregate='basic_valid'; report='absent'; report_entry='absent'; producer_gap=$false }}
                }} -CheckpointPolicy {{ param($path) $true }}
                $owner = Invoke-MobileStagingAcceptanceMain 'basic-authorization' 'staging' '{FULL_SHA}' 'C:/config.json' '{checkpoint.as_posix()}' $false $deps
                $matchedActions = @($script:actions)
                $resumed = Invoke-MobileStagingAcceptanceMain 'basic-authorization' 'staging' '{FULL_SHA}' 'C:/config.json' '{checkpoint.as_posix()}' $true $deps
                Remove-Item -LiteralPath '{checkpoint.as_posix()}' -Force
                $script:actions=@(); $script:artifactState='missing'; $script:loggedOut=$false
                $missing = Invoke-MobileStagingAcceptanceMain 'basic-authorization' 'staging' '{FULL_SHA}' 'C:/config.json' '{checkpoint.as_posix()}' $false $deps
                Remove-Item -LiteralPath '{checkpoint.as_posix()}' -Force
                $script:actions=@(); $script:artifactState='drift'
                $drift = Invoke-MobileStagingAcceptanceMain 'basic-authorization' 'staging' '{FULL_SHA}' 'C:/config.json' '{checkpoint.as_posix()}' $false $deps
                [pscustomobject]@{{ owner=$owner; resumed=$resumed; matchedActions=$matchedActions; missing=$missing; drift=$drift; actions=$script:actions }} | ConvertTo-Json -Depth 6 -Compress
                """
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["owner"]["owner_gate"], "LINE_LOGIN_CONSENT")
            self.assertEqual(payload["resumed"]["classification"], "PASS")
            self.assertEqual(payload["matchedActions"], ["preflight", "avd-start", "signer-check", "install", "cold-launch"])
            self.assertEqual(payload["missing"]["classification"], "PASS")
            self.assertEqual(payload["drift"]["classification"], "PASS")
            self.assertEqual(
                payload["actions"],
                [
                    "preflight",
                    "avd-start",
                    "cleanup-artifact",
                    "build",
                    "signer-check",
                    "install",
                    "cold-launch",
                ],
            )

    def test_invalid_launcher_action_result_is_bounded_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "checkpoint.json"
            result = self.run_harness(
                f"""
                $deps=New-MobileAcceptanceTestDependencies -Action {{param($name)
                    $value=if($name -eq 'avd-start'){{'unexpected-sentinel-result'}}else{{'ready'}}
                    @{{classification='PASS';result=$value}}
                }} -Artifact {{@{{state='matched';binding={self.binding_ps()}}}}} -Observation {{throw 'must not run'}} -CheckpointPolicy {{param($path)$true}}
                $value=Invoke-MobileStagingAcceptanceMain 'basic-authorization' 'staging' '{FULL_SHA}' 'C:/config.json' '{checkpoint.as_posix()}' $false $deps
                Write-HarnessJson $value
                """
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(result.stdout.splitlines()), 1)
            envelope = json.loads(result.stdout)
            self.assertEqual(envelope["classification"], "DRIFT")
            self.assertEqual(
                envelope["details"]["reason_code"], "ACTION_RESULT_INVALID"
            )
            self.assertNotIn("unexpected-sentinel-result", result.stdout + result.stderr)

    def test_cold_launch_timeout_unknown_is_rejected_without_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "checkpoint.json"
            result = self.run_harness(
                f"""
                $script:cold=0
                $deps=New-MobileAcceptanceTestDependencies -Action {{param($name)
                    if($name -eq 'cold-launch'){{$script:cold++;return @{{classification='PASS';result='timeout_unknown'}}}}
                    @{{classification='PASS';result=@{{preflight='ready';'avd-start'='reused';'signer-check'='matched';install='replaced'}}[$name]}}
                }} -Artifact {{@{{state='matched';binding={self.binding_ps()}}}}} -Observation {{throw 'must not run'}} -CheckpointPolicy {{param($path)$true}}
                $value=Invoke-MobileStagingAcceptanceMain 'basic-authorization' 'staging' '{FULL_SHA}' 'C:/config.json' '{checkpoint.as_posix()}' $false $deps
                [pscustomobject]@{{value=$value;cold=$script:cold}}|ConvertTo-Json -Depth 5 -Compress
                """
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["value"]["details"]["reason_code"], "ACTION_RESULT_INVALID")
            self.assertEqual(payload["cold"], 1)

    def test_basic_observation_gap_resumes_without_reinstall_or_cold_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "checkpoint.json"
            result = self.run_harness(
                f"""
                $script:phase='first';$script:actions=@()
                $binding={self.binding_ps()}
                $deps=New-MobileAcceptanceTestDependencies -Action {{param($name)
                    $script:actions+=$name
                    return @{{classification='PASS';result=@{{preflight='ready';'avd-start'='reused';'signer-check'='matched';install='replaced';'cold-launch'='running'}}[$name]}}
                }} -Artifact {{@{{state='matched';binding=$binding}}}} -Observation {{
                    if($script:phase -eq 'first'){{throw 'Harness status is unavailable'}}
                    return [pscustomobject]@{{principal='logged_out';provenance='none';aggregate='terminal_absent';report='absent';report_entry='absent';producer_gap=$false}}
                }} -CheckpointPolicy {{param($path)$true}}
                $first=Invoke-MobileStagingAcceptanceMain 'basic-authorization' 'staging' '{FULL_SHA}' 'C:/config.json' '{checkpoint.as_posix()}' $false $deps
                $firstCheckpoint=Get-Content -LiteralPath '{checkpoint.as_posix()}' -Raw|ConvertFrom-Json
                $firstActions=@($script:actions);$script:actions=@();$script:phase='resume'
                $second=Invoke-MobileStagingAcceptanceMain 'basic-authorization' 'staging' '{FULL_SHA}' 'C:/config.json' '{checkpoint.as_posix()}' $true $deps
                $secondCheckpoint=Get-Content -LiteralPath '{checkpoint.as_posix()}' -Raw|ConvertFrom-Json
                [pscustomobject]@{{first=$first;firstStep=$firstCheckpoint.step;firstActions=$firstActions;second=$second;secondStep=$secondCheckpoint.step;secondActions=$script:actions}}|ConvertTo-Json -Depth 6 -Compress
                """
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["first"]["classification"], "EVIDENCE_GAP")
        self.assertEqual(payload["firstStep"], "await_observation")
        self.assertEqual(
            payload["firstActions"],
            ["preflight", "avd-start", "signer-check", "install", "cold-launch"],
        )
        self.assertEqual(payload["second"]["classification"], "OWNER_ACTION_REQUIRED")
        self.assertEqual(payload["secondStep"], "await_login")
        self.assertEqual(payload["secondActions"], ["preflight", "avd-start"])

    def test_status_readiness_retries_only_exact_recoverable_accessibility_states(self):
        result = self.run_harness(
            """
            $script:attempts=0;$script:waits=0
            $ready=Get-MobileAcceptanceStatus -InvokeStatus {
                $script:attempts++
                if($script:attempts -eq 1){throw 'Accessibility inventory failed safely'}
                if($script:attempts -eq 2){throw 'Accessibility inventory is malformed'}
                if($script:attempts -lt 5){throw 'Accessibility foreground state is not exact'}
                return @{result='observed';semantic_state='logged_out'}
            } -Wait {$script:waits++}
            $script:unknownAttempts=0
            try {
                Get-MobileAcceptanceStatus -InvokeStatus {$script:unknownAttempts++;throw 'private-provider-subject-sentinel'} -Wait {throw 'must not wait'} | Out-Null
                $unknown='unexpected'
            } catch {$unknown=$_.Exception.Message}
            $script:persistentAttempts=0;$script:persistentWaits=0
            try {
                Get-MobileAcceptanceStatus -InvokeStatus {$script:persistentAttempts++;throw 'Accessibility foreground state is not exact'} -Wait {$script:persistentWaits++} | Out-Null
                $persistent='unexpected'
            } catch {$persistent=$_.Exception.Message}
            [pscustomobject]@{result=$ready.result;attempts=$script:attempts;waits=$script:waits;unknown=$unknown;unknownAttempts=$script:unknownAttempts;persistent=$persistent;persistentAttempts=$script:persistentAttempts;persistentWaits=$script:persistentWaits}|ConvertTo-Json -Compress
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["result"], "observed")
        self.assertEqual(payload["attempts"], 5)
        self.assertEqual(payload["waits"], 4)
        self.assertEqual(payload["unknown"], "Harness status is unavailable")
        self.assertEqual(payload["unknownAttempts"], 1)
        self.assertEqual(
            payload["persistent"], "Accessibility foreground state is not exact"
        )
        self.assertEqual(payload["persistentAttempts"], 5)
        self.assertEqual(payload["persistentWaits"], 4)
        self.assertNotIn("private-provider-subject-sentinel", result.stdout + result.stderr)

    def test_exhausted_status_reasons_are_bounded_and_distinct(self):
        result = self.run_harness(
            """
            $messages=@(
                'Accessibility inventory failed safely',
                'Accessibility inventory is malformed',
                'Accessibility foreground state is not exact',
                'Harness status is unavailable'
            )
            $values=@($messages|ForEach-Object{
                [ordered]@{
                    classification=Get-HarnessFailureClassification $_
                    reason=Get-HarnessFailureReasonCode $_
                }
            })
            $values|ConvertTo-Json -Compress
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            [
                {"classification": "EVIDENCE_GAP", "reason": "ACCESSIBILITY_UNAVAILABLE"},
                {"classification": "EVIDENCE_GAP", "reason": "ACCESSIBILITY_INVALID"},
                {"classification": "DRIFT", "reason": "SEMANTIC_DRIFT"},
                {"classification": "EVIDENCE_GAP", "reason": "STATUS_UNAVAILABLE"},
            ],
        )

    def test_artifact_manifest_drift_short_circuits_tools_and_unknown_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "app-debug.apk"
            artifact.write_bytes(b"fictional-apk")
            manifest = root / "artifact-manifest.json"
            old_manifest = {
                "accepted_commit": "1" * 40,
                "artifact_sha256": ARTIFACT_SHA,
                "classification": "PASS",
                "mode": "staging",
                "package": "tw.org.ntubtob.portal",
                "retention_owner": "TASK-123",
                "signer_sha256": SIGNER_SHA,
            }
            manifest.write_text(json.dumps(old_manifest), encoding="utf-8")
            result = self.run_harness(
                f"""
                $script:toolCalls=0
                function Get-ArtifactPath {{param($config)'{artifact.as_posix()}'}}
                function Invoke-ApkToolWithApprovedJava {{$script:toolCalls++;throw 'private-provider-subject-sentinel'}}
                $config=[pscustomobject]@{{evidence_root='{root.as_posix()}';apkanalyzer_executable='E:/safe/apkanalyzer.bat';avd_name='Pixel_API';serial='emulator-5554'}}
                $drift=Get-MobileAcceptanceArtifact $config '{FULL_SHA}'
                $manifest=Get-Content -LiteralPath '{manifest.as_posix()}' -Raw|ConvertFrom-Json
                $manifest.accepted_commit='{FULL_SHA}'
                $manifest|ConvertTo-Json -Compress|Set-Content -LiteralPath '{manifest.as_posix()}' -Encoding UTF8
                $unavailable=Get-MobileAcceptanceArtifact $config '{FULL_SHA}'
                [pscustomobject]@{{drift=$drift.state;unavailable=$unavailable.state;calls=$script:toolCalls}}|ConvertTo-Json -Compress
                """
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload, {"drift": "drift", "unavailable": "unavailable", "calls": 1})
            self.assertNotIn("private-provider-subject-sentinel", result.stdout + result.stderr)

    def test_officer_crash_unknown_resume_never_replays_each_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.run_harness(
                f"""
                $script:results=@()
                foreach ($crashAt in @('grant','restore','logout')) {{
                    $checkpoint=Join-Path '{root.as_posix()}' ($crashAt+'.json')
                    $script:role='basic'; $script:network='on'; $script:crash=$true; $script:counts=@{{ grant=0; restore=0; logout=0 }}; $script:ids=@{{}}; $script:sameIds=$true
                    $deps=New-MobileAcceptanceTestDependencies -Action {{ param($name)
                        if ($name -eq 'logout') {{ $script:counts[$name]++; $script:role='logged_out'; if($script:crash -and $crashAt -eq $name) {{ throw 'unknown mutation result' }}; return @{{classification='PASS';result='logged_out'}} }}
                        $result=@{{preflight='ready';'avd-start'='started';'signer-check'='matched';install='replaced';'cold-launch'='running'}}[$name]; return @{{classification='PASS';result=$result}}
                    }} -Artifact {{ @{{state='matched';binding={self.binding_ps()}}} }} -Observation {{
                        if($script:role -eq 'basic') {{ return @{{principal='basic';provenance='fresh_server';aggregate='basic_valid';report='absent';report_entry='absent';producer_gap=$false}} }}
                        if($script:role -eq 'officer') {{ return @{{principal='officer';provenance=$(if($script:network -eq 'off'){{'offline_cache'}}else{{'fresh_server'}});aggregate='officer_valid';report=$(if($script:network -eq 'off'){{'offline_cached_readonly'}}else{{'ready'}});report_entry='present';producer_gap=$false}} }}
                        return @{{principal='logged_out';provenance='none';aggregate='terminal_absent';report='absent';report_entry='absent';producer_gap=$false}}
                    }} -BrokerStatus {{[pscustomobject]@{{classification='PASS';result='available';state='private_exact';reason_code='NONE'}}}} -BrokerOperation {{param($action,$operationId)
                        if($action -eq 'grant'){{$script:counts.grant++;$script:ids.grant=$operationId;$script:role='officer';if($script:crash -and $crashAt -eq 'grant'){{throw 'unknown mutation result'}};return [pscustomobject]@{{classification='PASS';result='completed';state='ready_officer';reason_code='NONE'}}}}
                        if($action -eq 'restore'){{$script:counts.restore++;$script:ids.restore=$operationId;$script:role='basic';if($script:crash -and $crashAt -eq 'restore'){{throw 'unknown mutation result'}};return [pscustomobject]@{{classification='PASS';result='completed';state='ready_basic';reason_code='NONE'}}}}
                        if($action -eq 'reconcile'){{if($script:role -eq 'officer'){{$script:sameIds=$script:sameIds -and ($operationId -ceq $script:ids.grant);$state='ready_officer'}}else{{$script:sameIds=$script:sameIds -and ($operationId -ceq $script:ids.restore);$state='ready_basic'}};return [pscustomobject]@{{classification='PASS';result='completed';state=$state;reason_code='NONE'}}}}
                    }} -NetworkGet {{$script:network}} -NetworkSet {{param($state)$script:network=$state}} -CheckpointPolicy {{param($path)$true}}
                    $first=Invoke-MobileStagingAcceptanceMain 'officer-authorization-roundtrip' 'staging' '{FULL_SHA}' 'C:/config.json' $checkpoint $false $deps
                    $saved=Get-Content -LiteralPath $checkpoint -Encoding UTF8 -Raw|ConvertFrom-Json
                    $script:crash=$false
                    $second=Invoke-MobileStagingAcceptanceMain 'officer-authorization-roundtrip' 'staging' '{FULL_SHA}' 'C:/config.json' $checkpoint $true $deps
                    $script:results += [pscustomobject]@{{crash=$crashAt;first=$first.classification;intent=$saved.step;second=$second.classification;grant=$script:counts.grant;restore=$script:counts.restore;logout=$script:counts.logout;network=$script:network;sameIds=$script:sameIds}}
                }}
                $script:results|ConvertTo-Json -Compress
                """
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            for item in json.loads(result.stdout):
                self.assertEqual(item["first"], "DRIFT")
                self.assertTrue(item["intent"].endswith("intent"))
                self.assertEqual(item["second"], "PASS")
                self.assertEqual(item["grant"], 1)
                self.assertEqual(item["restore"], 1)
                self.assertEqual(item["logout"], 1)
                self.assertEqual(item["network"], "on")
                self.assertTrue(item["sameIds"])

    def test_unprovisioned_broker_stops_before_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "checkpoint.json"
            result = self.run_harness(
                f"""
                $script:actions=@()
                $deps=New-MobileAcceptanceTestDependencies -Action {{param($name)$script:actions+=$name;@{{classification='PASS';result=@{{preflight='ready';'avd-start'='started';'signer-check'='matched';install='replaced';'cold-launch'='running'}}[$name]}}}} -Artifact {{@{{state='matched';binding={self.binding_ps()}}}}} -Observation {{@{{principal='basic';provenance='fresh_server';aggregate='basic_valid';report='absent';report_entry='absent';producer_gap=$false}}}} -BrokerStatus {{[pscustomobject]@{{classification='OWNER_ACTION_REQUIRED';result='stopped';state='unavailable';reason_code='BROKER_PROVISIONING'}}}} -CheckpointPolicy {{param($path)$true}}
                $value=Invoke-MobileStagingAcceptanceMain 'officer-authorization-roundtrip' 'staging' '{FULL_SHA}' 'C:/config.json' '{checkpoint.as_posix()}' $false $deps
                [pscustomobject]@{{value=$value;actions=$script:actions}}|ConvertTo-Json -Depth 5 -Compress
                """
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["value"]["owner_gate"], "BROKER_PROVISIONING")
            self.assertEqual(payload["actions"], ["preflight", "avd-start", "signer-check", "install", "cold-launch"])

    def test_nonforeground_status_never_requests_accessibility(self):
        result = self.run_harness(
            """
            $script:calls=0
            $values=@()
            foreach($state in @('package_absent','portal_background','portal_stopped','basic_non_authoritative')) {
                $status=[pscustomobject]@{semantic_state=$state;provenance='none'}
                $values += Get-AdditionalAcceptanceProducerObservation $status { $script:calls++; '<hierarchy />' }
            }
            [pscustomobject]@{calls=$script:calls;states=@($values|ForEach-Object{$_.principal})}|ConvertTo-Json -Compress
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["calls"], 0)
        self.assertEqual(payload["states"], ["non_foreground"] * 4)

    def test_task124_xml_transport_offline_and_report_entry_contract(self):
        result = self.run_harness(
            """
            $basic='<hierarchy><node package="tw.org.ntubtob.portal" class="android.view.View" content-desc="偵錯本機狀態：session present；basic_cache present；officer_report_cache absent；pending_attendance_intent absent" /></hierarchy>'
            $officer='<hierarchy><node package="tw.org.ntubtob.portal" class="android.view.View" content-desc="偵錯本機狀態：session present；basic_cache present；officer_report_cache present；pending_attendance_intent absent" /><node package="tw.org.ntubtob.portal" class="android.view.View" content-desc="出席報表&#xA;Officer／Admin 唯讀" enabled="true" clickable="true" /><node package="tw.org.ntubtob.portal" class="android.view.View" content-desc="偵錯報表投影：ready；已啟用寫入控制：0" /></hierarchy>'
            $offline=$officer -replace 'ready','offline_cached_readonly'
            $basicValue=Get-AdditionalAcceptanceProducerObservation ([pscustomobject]@{semantic_state='basic';provenance='fresh_server'}) {$basic}
            $officerValue=Get-AdditionalAcceptanceProducerObservation ([pscustomobject]@{semantic_state='officer_report_enabled';provenance='fresh_server'}) {"INFO transport`n$officer`nINFO complete"}
            $offlineValue=Get-AdditionalAcceptanceProducerObservation ([pscustomobject]@{semantic_state='officer_report_enabled_non_authoritative';provenance='offline_cache'}) {$offline}
            $duplicate=$officer -replace '</hierarchy>','<node package="tw.org.ntubtob.portal" class="android.view.View" content-desc="出席報表&#xA;Officer／Admin 唯讀" enabled="true" clickable="true" /></hierarchy>'
            try { Get-AdditionalAcceptanceProducerObservation ([pscustomobject]@{semantic_state='officer_report_enabled';provenance='fresh_server'}) {$duplicate}|Out-Null; $duplicateResult='unexpected' } catch { $duplicateResult=$_.Exception.Message }
            [pscustomobject]@{basic=$basicValue;officer=$officerValue;offline=$offlineValue;duplicate=$duplicateResult}|ConvertTo-Json -Depth 5 -Compress
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["basic"]["report_entry"], "absent")
        self.assertEqual(payload["officer"]["report_entry"], "present")
        self.assertEqual(payload["offline"]["report"], "offline_cached_readonly")
        self.assertIn("report entry", payload["duplicate"])

    def test_mutation_requires_its_exact_bounded_result(self):
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "checkpoint.json"
            result = self.run_harness(
                f"""
                $script:actions=@();$script:brokerCalls=@()
                $deps=New-MobileAcceptanceTestDependencies -Action {{param($name)
                    $script:actions+=$name
                    $result=@{{preflight='ready';'avd-start'='started';'signer-check'='matched';install='replaced';'cold-launch'='running'}}[$name]
                    @{{classification='PASS';result=$result}}
                }} -Artifact {{@{{state='matched';binding={self.binding_ps()}}}}} -Observation {{@{{principal='basic';provenance='fresh_server';aggregate='basic_valid';report='absent';report_entry='absent';producer_gap=$false}}}} -BrokerStatus {{[pscustomobject]@{{classification='PASS';result='available';state='private_exact';reason_code='NONE'}}}} -BrokerOperation {{param($action,$id)$script:brokerCalls+=$action;[pscustomobject]@{{classification='PASS';result='completed';state='ready_basic';reason_code='NONE'}}}} -CheckpointPolicy {{param($path)$true}}
                $value=Invoke-MobileStagingAcceptanceMain 'officer-authorization-roundtrip' 'staging' '{FULL_SHA}' 'C:/config.json' '{checkpoint.as_posix()}' $false $deps
                $saved=Get-Content -LiteralPath '{checkpoint.as_posix()}' -Raw|ConvertFrom-Json
                [pscustomobject]@{{value=$value;step=$saved.step;actions=$script:actions;brokerCalls=$script:brokerCalls}}|ConvertTo-Json -Depth 5 -Compress
                """
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["value"]["classification"], "DRIFT")
            self.assertEqual(payload["step"], "grant_intent")
            self.assertEqual(
                payload["actions"],
                [
                    "preflight",
                    "avd-start",
                    "signer-check",
                    "install",
                    "cold-launch",
                ],
            )
            self.assertEqual(payload["brokerCalls"], ["grant"])

    def test_checkpoint_path_policy_and_atomic_write(self):
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "checkpoint.json"
            result = self.run_harness(
                f"""
                $binding={self.binding_ps()}
                Save-HarnessCheckpoint '{checkpoint.as_posix()}' 'basic-authorization' 'await_login' $binding 'owner_action_required'
                $temporary=@(Get-ChildItem -LiteralPath '{directory}' -Filter '*.tmp')
                $deps=New-MobileAcceptanceTestDependencies -Action {{param($name)@{{classification='PASS';result='ready'}}}} -Artifact {{@{{state='matched';binding=$binding}}}} -Observation {{throw 'must not run'}} -CheckpointPolicy {{param($path)$false}}
                $value=Invoke-MobileStagingAcceptanceMain 'basic-authorization' 'staging' '{FULL_SHA}' 'C:/config.json' '{checkpoint.as_posix()}' $false $deps
                [pscustomobject]@{{temporary=$temporary.Count;value=$value}}|ConvertTo-Json -Depth 5 -Compress
                """
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["temporary"], 0)
            self.assertEqual(payload["value"]["classification"], "DRIFT")

    def test_output_redaction_fallback_is_one_line_and_exit_two(self):
        source = HARNESS.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as directory:
            copy = Path(directory) / "harness.ps1"
            copy.write_text(
                source.replace(
                    "try { Write-HarnessJson $envelope }",
                    "try { $envelope.details.reason_code='private-provider-subject-sentinel'; Write-HarnessJson $envelope }",
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoLogo",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(copy),
                    "-Scenario",
                    "basic-authorization",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
                check=False,
            )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(len(result.stdout.splitlines()), 1)
        envelope = json.loads(result.stdout)
        self.assertEqual(envelope["classification"], "FAILED")
        self.assertEqual(envelope["details"]["reason_code"], "OUTPUT_REDACTION_FAILED")
        self.assertNotIn("private-provider-subject-sentinel", result.stdout + result.stderr)
