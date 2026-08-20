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

    def test_basic_owner_gate_resume_and_artifact_preparation_matrix(self):
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "checkpoint.json"
            result = self.run_harness(
                f"""
                $script:actions = @(); $script:artifactState = 'matched'; $script:loggedOut = $true
                $deps = New-MobileAcceptanceTestDependencies -Action {{ param($name)
                    $script:actions += $name
                    $result = @{{ preflight='ready'; 'avd-start'='reused'; 'cleanup-evidence'='removed_task_owned'; build='built'; 'signer-check'='signer_matched'; install='replaced'; 'cold-launch'='running' }}[$name]
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
                    "cleanup-evidence",
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

    def test_officer_crash_unknown_resume_never_replays_each_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.run_harness(
                f"""
                $script:results=@()
                foreach ($crashAt in @('broker-grant','broker-restore','logout')) {{
                    $checkpoint=Join-Path '{root.as_posix()}' ($crashAt+'.json')
                    $script:role='basic'; $script:network='on'; $script:crash=$true; $script:counts=@{{ 'broker-grant'=0; 'broker-restore'=0; logout=0 }}
                    $deps=New-MobileAcceptanceTestDependencies -Action {{ param($name)
                        if ($name -eq 'broker-grant') {{ $script:counts[$name]++; $script:role='officer'; if($script:crash -and $crashAt -eq $name) {{ throw 'unknown mutation result' }}; return @{{classification='PASS';result='granted'}} }}
                        if ($name -eq 'broker-restore') {{ $script:counts[$name]++; $script:role='basic'; if($script:crash -and $crashAt -eq $name) {{ throw 'unknown mutation result' }}; return @{{classification='PASS';result='restored'}} }}
                        if ($name -eq 'logout') {{ $script:counts[$name]++; $script:role='logged_out'; if($script:crash -and $crashAt -eq $name) {{ throw 'unknown mutation result' }}; return @{{classification='PASS';result='logged_out'}} }}
                        $result=@{{preflight='ready';'avd-start'='started';'signer-check'='signer_matched';install='replaced';'cold-launch'='running'}}[$name]; return @{{classification='PASS';result=$result}}
                    }} -Artifact {{ @{{state='matched';binding={self.binding_ps()}}} }} -Observation {{
                        if($script:role -eq 'basic') {{ return @{{principal='basic';provenance='fresh_server';aggregate='basic_valid';report='absent';report_entry='absent';producer_gap=$false}} }}
                        if($script:role -eq 'officer') {{ return @{{principal='officer';provenance=$(if($script:network -eq 'off'){{'offline_cache'}}else{{'fresh_server'}});aggregate='officer_valid';report=$(if($script:network -eq 'off'){{'offline_cached_readonly'}}else{{'ready'}});report_entry='present';producer_gap=$false}} }}
                        return @{{principal='logged_out';provenance='none';aggregate='terminal_absent';report='absent';report_entry='absent';producer_gap=$false}}
                    }} -BrokerReady {{$true}} -BrokerState {{if($script:role -eq 'officer'){{'granted'}}elseif($script:role -eq 'basic'){{'restored'}}else{{'logged_out'}}}} -NetworkGet {{$script:network}} -NetworkSet {{param($state)$script:network=$state}} -CheckpointPolicy {{param($path)$true}}
                    $first=Invoke-MobileStagingAcceptanceMain 'officer-authorization-roundtrip' 'staging' '{FULL_SHA}' 'C:/config.json' $checkpoint $false $deps
                    $saved=Get-Content -LiteralPath $checkpoint -Encoding UTF8 -Raw|ConvertFrom-Json
                    $script:crash=$false
                    $second=Invoke-MobileStagingAcceptanceMain 'officer-authorization-roundtrip' 'staging' '{FULL_SHA}' 'C:/config.json' $checkpoint $true $deps
                    $script:results += [pscustomobject]@{{crash=$crashAt;first=$first.classification;intent=$saved.step;second=$second.classification;grant=$script:counts['broker-grant'];restore=$script:counts['broker-restore'];logout=$script:counts['logout'];network=$script:network}}
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

    def test_unprovisioned_broker_stops_before_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "checkpoint.json"
            result = self.run_harness(
                f"""
                $script:actions=@()
                $deps=New-MobileAcceptanceTestDependencies -Action {{param($name)$script:actions+=$name;@{{classification='PASS';result=@{{preflight='ready';'avd-start'='started';'signer-check'='signer_matched';install='replaced';'cold-launch'='running'}}[$name]}}}} -Artifact {{@{{state='matched';binding={self.binding_ps()}}}}} -Observation {{@{{principal='basic';provenance='fresh_server';aggregate='basic_valid';report='absent';report_entry='absent';producer_gap=$false}}}} -BrokerReady {{$false}} -CheckpointPolicy {{param($path)$true}}
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
                $script:actions=@()
                $deps=New-MobileAcceptanceTestDependencies -Action {{param($name)
                    $script:actions+=$name
                    if($name -eq 'broker-grant'){{return @{{classification='PASS';result='restored'}}}}
                    $result=@{{preflight='ready';'avd-start'='started';'signer-check'='signer_matched';install='replaced';'cold-launch'='running'}}[$name]
                    @{{classification='PASS';result=$result}}
                }} -Artifact {{@{{state='matched';binding={self.binding_ps()}}}}} -Observation {{@{{principal='basic';provenance='fresh_server';aggregate='basic_valid';report='absent';report_entry='absent';producer_gap=$false}}}} -BrokerReady {{$true}} -BrokerState {{'granted'}} -CheckpointPolicy {{param($path)$true}}
                $value=Invoke-MobileStagingAcceptanceMain 'officer-authorization-roundtrip' 'staging' '{FULL_SHA}' 'C:/config.json' '{checkpoint.as_posix()}' $false $deps
                $saved=Get-Content -LiteralPath '{checkpoint.as_posix()}' -Raw|ConvertFrom-Json
                [pscustomobject]@{{value=$value;step=$saved.step;actions=$script:actions}}|ConvertTo-Json -Depth 5 -Compress
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
                    "broker-grant",
                ],
            )

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
