from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "tools" / "Invoke-MobileStaging.ps1"
FULL_SHA = "20f393778a9010ac52ad9c8935f3992d72ce06a0"
FINGERPRINT = "A" * 64
SENSITIVE_SENTINELS = (
    "postgresql://private-user:private-password@private.invalid/staging",
    "private-provider-subject-sentinel",
    "https://private-staging.invalid",
    "9876543210123456789",
)


def powershell_available() -> bool:
    return (
        bool(os.environ.get("SystemRoot"))
        and (
            Path(os.environ["SystemRoot"])
            / "System32"
            / "WindowsPowerShell"
            / "v1.0"
            / "powershell.exe"
        ).is_file()
    )


@unittest.skipUnless(powershell_available(), "Windows PowerShell is unavailable")
class PowerShellContractTest(unittest.TestCase):
    maxDiff = None

    def test_launcher_requires_current_mobile_api_database_revision(self):
        source = LAUNCHER.read_text(encoding="utf-8")
        self.assertIn(
            "$script:ExpectedRevision = '0008_mobile_notification_delivery'",
            source,
        )
        self.assertNotIn(
            "$script:ExpectedRevision = '0005_mobile_auth_api_foundation'",
            source,
        )

    def run_harness(self, body: str, *, input_text: str | None = None):
        with tempfile.TemporaryDirectory() as directory:
            harness = Path(directory) / "harness.ps1"
            harness.write_text(
                "$ErrorActionPreference = 'Stop'\n"
                f". '{LAUNCHER.as_posix()}'\n" + textwrap.dedent(body),
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
                    str(harness),
                ],
                cwd=ROOT,
                input=input_text,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )

    def assert_safe_output(self, result):
        combined = (result.stdout + result.stderr).lower()
        for sentinel in SENSITIVE_SENTINELS:
            self.assertNotIn(sentinel.lower(), combined)
        for field in (
            "provider_subject",
            "database_url",
            "api_base_url",
            "line_channel_id",
            "keystore",
            "raw ui",
            "logcat",
        ):
            self.assertNotIn(field, combined)

    def test_parser_and_complete_action_matrix(self):
        parser = subprocess.run(
            [
                "powershell.exe",
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "$e=$null;$t=$null;"
                f"[System.Management.Automation.Language.Parser]::ParseFile('{LAUNCHER.as_posix()}',[ref]$t,[ref]$e)|Out-Null;"
                "if($e.Count){$e|ForEach-Object{$_.Message};exit 1}",
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(parser.returncode, 0, parser.stdout + parser.stderr)
        source = LAUNCHER.read_text(encoding="utf-8")
        expected = {
            "help",
            "preflight",
            "avd-start",
            "status",
            "cleanup-artifact",
            "build",
            "signer-check",
            "install",
            "cold-launch",
            "health",
            "stop",
            "cleanup",
            "private-inspect",
            "grant-officer",
            "restore-basic",
        }
        action_sets = re.findall(
            r"\$script:(?:Routine|Private)Actions\s*=\s*@\((.*?)\)", source, re.S
        )
        self.assertEqual(
            {
                value
                for group in action_sets
                for value in re.findall(r"'([^']+)'", group)
            },
            expected,
        )
        for action in expected:
            self.assertIn(f"'{action}'", source)

    def test_artifact_cleanup_preserves_harness_checkpoint_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "evidence"
            harness = evidence / "task-129"
            harness.mkdir(parents=True)
            artifact = evidence / "app-debug.apk"
            manifest = evidence / "artifact-manifest.json"
            checkpoint = harness / "basic.json"
            artifact.write_bytes(b"artifact")
            manifest.write_text("{}", encoding="utf-8")
            checkpoint.write_text("{}", encoding="utf-8")
            result = self.run_harness(
                f"""
                $script:TaskEvidenceRoot='{evidence.as_posix()}'
                $config=[pscustomobject]@{{evidence_root='{evidence.as_posix()}';artifact_relative_path='app-debug.apk'}}
                $value=Invoke-ArtifactCleanup $config
                Write-Output ($value.result+','+(Test-Path -LiteralPath '{artifact.as_posix()}')+','+(Test-Path -LiteralPath '{manifest.as_posix()}')+','+(Test-Path -LiteralPath '{checkpoint.as_posix()}'))
                """
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("removed_artifact,False,False,True", result.stdout)

    def test_missing_action_mode_commit_and_config_fail_before_any_command(self):
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(LAUNCHER),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        envelope = json.loads(result.stdout)
        self.assertEqual(envelope["classification"], "DRIFT")
        self.assertEqual(envelope["details"]["reason_code"], "CONFIG_INVALID")
        self.assertEqual(envelope["standing_authorization"], "DEC-098")
        self.assertEqual(envelope["report_to"], "main-work")
        self.assertNotIn("Action is unknown", result.stdout + result.stderr)
        self.assert_safe_output(result)

    def test_real_complete_config_loads_and_exact_invalid_variants_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            valid_path = root / "valid.json"
            valid_path.write_text(json.dumps(launcher_config()), encoding="utf-8")
            result = self.run_harness(
                f"""
                $value=Load-LauncherConfig '{valid_path.as_posix()}'
                Write-Output ($value.schema_version.ToString()+','+$value.package_id+','+$value.android_user_homes.Count)
                """
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("1,tw.org.ntubtob.portal,1", result.stdout)

            invalid_cases = (
                ({"unexpected": "field"}, "fields are not exact"),
                ({"package_id": "tw.org.ntubtob.wrong"}, "identity is not exact"),
                (
                    {"android_user_homes": [r"C:\not-approved"]},
                    "outside the approved signer homes",
                ),
            )
            for index, (updates, expected) in enumerate(invalid_cases):
                with self.subTest(expected=expected):
                    config = launcher_config()
                    config.update(updates)
                    invalid_path = root / f"invalid-{index}.json"
                    invalid_path.write_text(json.dumps(config), encoding="utf-8")
                    result = self.run_harness(
                        f"""
                        try {{ Load-LauncherConfig '{invalid_path.as_posix()}';exit 9 }} catch {{ Write-Output $_.Exception.Message }}
                        """
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn(expected, result.stdout)

            governed = subprocess.run(
                [
                    "powershell.exe",
                    "-NoLogo",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(LAUNCHER),
                    "-Action",
                    "preflight",
                    "-Mode",
                    "fake",
                    "-Commit",
                    FULL_SHA,
                    "-ConfigPath",
                    str(root / "invalid-0.json"),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            self.assertEqual(governed.returncode, 2, governed.stderr)
            self.assertEqual(len(governed.stdout.splitlines()), 1)
            envelope = json.loads(governed.stdout)
            self.assertEqual(envelope["details"]["reason_code"], "CONFIG_INVALID")
            self.assertNotIn(str(root), governed.stdout + governed.stderr)
            self.assert_safe_output(governed)

    def test_config_allows_only_the_canonical_registered_android_user_home(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registered_home = Path(os.environ["USERPROFILE"]) / ".android"
            valid = launcher_config()
            valid["android_user_homes"] = [str(registered_home)]
            valid_path = root / "registered.json"
            valid_path.write_text(json.dumps(valid), encoding="utf-8")
            result = self.run_harness(
                f"""
                $value=Load-LauncherConfig '{valid_path.as_posix()}'
                Write-Output ('homes='+$value.android_user_homes.Count)
                """
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("homes=1", result.stdout)

            for index, external_home in enumerate(
                (
                    str(registered_home.parent / "other-android-home"),
                    str(registered_home.parent / "nested" / ".." / ".android"),
                    r"E:\task-123\nested\..\android-user",
                )
            ):
                with self.subTest(external_home=external_home):
                    invalid = launcher_config()
                    invalid["android_user_homes"] = [external_home]
                    invalid_path = root / f"external-{index}.json"
                    invalid_path.write_text(json.dumps(invalid), encoding="utf-8")
                    result = self.run_harness(
                        f"""
                        try {{ Load-LauncherConfig '{invalid_path.as_posix()}';exit 9 }} catch {{ Write-Output $_.Exception.Message }}
                        """
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn("outside the approved signer homes", result.stdout)

    def test_config_requires_apkanalyzer_under_the_same_android_sdk(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            valid = launcher_config()
            valid_path = root / "same-sdk.json"
            valid_path.write_text(json.dumps(valid), encoding="utf-8")
            cross = launcher_config()
            cross["apkanalyzer_executable"] = (
                r"E:\other-sdk\cmdline-tools\latest\bin\apkanalyzer.bat"
            )
            cross_path = root / "cross-sdk.json"
            cross_path.write_text(json.dumps(cross), encoding="utf-8")
            result = self.run_harness(
                f"""
                $script:childStarted=$false
                function Invoke-BoundedProcess {{ $script:childStarted=$true;throw 'must not start' }}
                $valid=Load-LauncherConfig '{valid_path.as_posix()}'
                Write-Output ('valid='+$valid.schema_version)
                try {{ Load-LauncherConfig '{cross_path.as_posix()}';exit 9 }} catch {{ Write-Output ($_.Exception.Message+',child='+$script:childStarted) }}
                """
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("valid=1", result.stdout)
            self.assertIn(
                "APK analyzer is outside the approved Android SDK,child=False",
                result.stdout,
            )
            self.assertNotIn("other-sdk", result.stdout + result.stderr)

    def test_snapshot_rejects_wrong_sha_dirty_or_attached_head(self):
        cases = (
            ("wrong", "", 1, "Snapshot commit does not match"),
            (FULL_SHA, "", 0, "Snapshot must be detached"),
            (FULL_SHA, " M changed.txt", 1, "Snapshot must be clean"),
        )
        for head, dirty, symbolic_exit, message in cases:
            with self.subTest(message=message):
                result = self.run_harness(
                    f"""
                    function Invoke-BoundedProcess {{
                        param($Executable, $Arguments, $TimeoutSeconds, $ChildEnvironment, $WorkingDirectory)
                        $joined = $Arguments -join ' '
                        if ($joined -match 'rev-parse') {{ return [pscustomobject]@{{TimedOut=$false;ExitCode=0;Stdout='{head}';Stderr=''}} }}
                        if ($joined -match 'symbolic-ref') {{ return [pscustomobject]@{{TimedOut=$false;ExitCode={symbolic_exit};Stdout='';Stderr=''}} }}
                        return [pscustomobject]@{{TimedOut=$false;ExitCode=0;Stdout='{dirty}';Stderr=''}}
                    }}
                    $config=[pscustomobject]@{{snapshot_root='{ROOT.as_posix()}';git_executable='{LAUNCHER.as_posix()}'}}
                    try {{ Assert-Snapshot $config '{FULL_SHA}'; exit 9 }} catch {{ Write-Output $_.Exception.Message }}
                    """
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(message, result.stdout)

    def test_preflight_and_status_are_zero_mutation_and_secret_free(self):
        result = self.run_harness(
            f"""
            $script:calls=@()
            function Assert-Snapshot {{ param($Config,$ExpectedCommit) }}
            function Assert-DiskAndLock {{ param($Config) }}
            function Test-Path {{ param($LiteralPath,$PathType) return $true }}
            function Assert-OnlyApprovedSerial {{ param($Config) }}
            function Get-PackageState {{ param($Config) return 'installed' }}
            function Get-CurrentActivity {{ param($Config) return 'portal' }}
            function Get-AllowlistedUiCounts {{ param($Config) return [ordered]@{{semantic_state='officer_report_enabled';provenance='fresh_server';login=0;basic=0;officer=1;report_enabled=1;report_disabled=0}} }}
            $config=[pscustomobject]@{{
                flutter_executable='{LAUNCHER.as_posix()}';adb_executable='{LAUNCHER.as_posix()}';
                emulator_executable='{LAUNCHER.as_posix()}';apksigner_executable='{LAUNCHER.as_posix()}';
                apkanalyzer_executable='{LAUNCHER.as_posix()}';keytool_executable='{LAUNCHER.as_posix()}'
            }}
            $a=Invoke-Preflight $config '{FULL_SHA}' 'staging'
            $b=Invoke-Status $config
            Write-Output (($a.result)+','+($b.package)+','+($b.activity))
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ready,installed,portal", result.stdout)
        self.assertNotIn("secrets versions access", result.stdout + result.stderr)
        self.assert_safe_output(result)

    def test_status_classifies_only_allowlisted_accessibility_counts(self):
        cases = (
            (
                "偵錯權限投影：一般使用者；報表讀取：停用；來源：fresh_server（伺服器最新驗證）",
                "state=basic,login=0,basic=1,officer=0,enabled=0,disabled=1",
            ),
            (
                "偵錯權限投影：一般使用者；報表讀取：停用；來源：fresh_server（伺服器最新驗證）"
                "&#10;一般使用者&#10;報表讀取：停用；來源：fresh_server（伺服器最新驗證）",
                "state=basic,login=0,basic=1,officer=0,enabled=0,disabled=1",
            ),
            (
                "偵錯權限投影：幹部；報表讀取：啟用；來源：fresh_server（伺服器最新驗證）",
                "state=officer_report_enabled,login=0,basic=0,officer=1,enabled=1,disabled=0",
            ),
            (
                "偵錯權限投影：幹部；報表讀取：停用；來源：fresh_server（伺服器最新驗證）",
                "state=officer_report_disabled,login=0,basic=0,officer=1,enabled=0,disabled=1",
            ),
        )
        sentinel = "private-provider-subject-sentinel"
        for label, expected in cases:
            with self.subTest(label=label):
                xml = (
                    '<hierarchy><node content-desc="'
                    + label
                    + '"/><node content-desc="'
                    + sentinel
                    + '"/></hierarchy>'
                )
                result = self.run_harness(
                    f"""
                    function Invoke-BoundedProcess {{
                        param($Executable,$Arguments,$TimeoutSeconds)
                        $script:capturedArgs=@($Arguments)
                        return [pscustomobject]@{{TimedOut=$false;ExitCode=0;Stdout='{xml}';Stderr=''}}
                    }}
                    $config=[pscustomobject]@{{adb_executable='E:/mock/adb.exe';serial='emulator-5556'}}
                    $value=Get-AllowlistedUiCounts $config
                    Write-Output ('state='+$value.semantic_state+',login='+$value.login+',basic='+$value.basic+',officer='+$value.officer+',enabled='+$value.report_enabled+',disabled='+$value.report_disabled)
                    Write-Output ('argv='+($script:capturedArgs -join '|'))
                    """
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(expected, result.stdout)
                self.assertIn(
                    "argv=-s|emulator-5556|exec-out|uiautomator|dump|/dev/tty",
                    result.stdout,
                )
                self.assertNotIn("|shell|", result.stdout)
                self.assertNotIn(sentinel, result.stdout + result.stderr)

        rejected = (
            (
                '<hierarchy><node package="tw.org.ntubtob.portal" class="android.widget.Button" '
                'content-desc="LINE 登入" enabled="true" clickable="true"/>'
                '<node content-desc="偵錯權限投影：幹部；報表讀取：啟用；來源：fresh_server（伺服器最新驗證）"/></hierarchy>',
                "Accessibility foreground state is not exact",
            ),
            (
                '<hierarchy><node content-desc="請使用 LINE 安全登入"/>'
                '<node content-desc="請使用 LINE 安全登入"/></hierarchy>',
                "Accessibility foreground state is not exact",
            ),
            (
                '<hierarchy><node content-desc="unapproved"/></hierarchy>',
                "Accessibility foreground state is not exact",
            ),
            ("not-xml", "Accessibility inventory is malformed"),
            ("", "Accessibility inventory size is not bounded"),
        )
        for raw, expected_error in rejected:
            with self.subTest(expected_error=expected_error):
                result = self.run_harness(
                    f"""
                    function Invoke-BoundedProcess {{ return [pscustomobject]@{{TimedOut=$false;ExitCode=0;Stdout='{raw}';Stderr=''}} }}
                    $config=[pscustomobject]@{{adb_executable='E:/mock/adb.exe';serial='emulator-5556'}}
                    try {{ Get-AllowlistedUiCounts $config;exit 9 }} catch {{ Write-Output $_.Exception.Message }}
                    """
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(expected_error, result.stdout)

        result = self.run_harness(
            """
            function Invoke-BoundedProcess { return [pscustomobject]@{TimedOut=$false;ExitCode=0;Stdout=('x' * 65537);Stderr=''} }
            $config=[pscustomobject]@{adb_executable='E:/mock/adb.exe';serial='emulator-5556'}
            try { Get-AllowlistedUiCounts $config;exit 9 } catch { Write-Output $_.Exception.Message }
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Accessibility inventory size is not bounded", result.stdout)

    def test_logged_out_requires_one_exact_portal_login_button(self):
        prompt = "請使用 LINE 安全登入 請使用 LINE 安全登入"
        sentinel = "private-provider-subject-sentinel"
        exact_button = (
            '<node package="tw.org.ntubtob.portal" class="android.widget.Button" '
            'content-desc="LINE 登入" enabled="true" clickable="true"/>'
        )
        valid = (
            '<hierarchy><node package="tw.org.ntubtob.portal" '
            f'class="android.view.View" content-desc="{prompt}"/>{exact_button}'
            f'<node content-desc="{sentinel}"/></hierarchy>'
        )
        result = self.run_harness(
            f"""
            function Invoke-BoundedProcess {{
                return [pscustomobject]@{{TimedOut=$false;ExitCode=0;Stdout='{valid}';Stderr=''}}
            }}
            $config=[pscustomobject]@{{adb_executable='E:/mock/adb.exe';serial='emulator-5556'}}
            $value=Get-AllowlistedUiCounts $config
            Write-Output ('state='+$value.semantic_state+',login='+$value.login+',basic='+$value.basic+',officer='+$value.officer)
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("state=logged_out,login=1,basic=0,officer=0", result.stdout)
        self.assertNotIn(prompt, result.stdout + result.stderr)
        self.assertNotIn(sentinel, result.stdout + result.stderr)

        invalid_nodes = (
            exact_button + exact_button,
            exact_button
            + '<node content-desc="偵錯權限投影：幹部；報表讀取：啟用；來源：fresh_server（伺服器最新驗證）"/>',
            exact_button.replace("tw.org.ntubtob.portal", "com.example.other"),
            exact_button.replace("android.widget.Button", "android.view.View"),
            exact_button.replace('enabled="true"', 'enabled="false"'),
            exact_button.replace('clickable="true"', 'clickable="false"'),
        )
        for nodes in invalid_nodes:
            with self.subTest(nodes=nodes):
                hierarchy = (
                    f'<hierarchy>{nodes}<node content-desc="{sentinel}"/></hierarchy>'
                )
                result = self.run_harness(
                    f"""
                    function Invoke-BoundedProcess {{
                        return [pscustomobject]@{{TimedOut=$false;ExitCode=0;Stdout='{hierarchy}';Stderr=''}}
                    }}
                    $config=[pscustomobject]@{{adb_executable='E:/mock/adb.exe';serial='emulator-5556'}}
                    try {{ Get-AllowlistedUiCounts $config;exit 9 }} catch {{ Write-Output $_.Exception.Message }}
                    """
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(
                    "Accessibility foreground state is not exact", result.stdout
                )
                self.assertNotIn(sentinel, result.stdout + result.stderr)

    def test_principal_provenance_matrix_is_bounded_and_non_authoritative(self):
        sentinel = "private-provider-subject-sentinel"
        cases = (
            (
                "一般使用者",
                "停用",
                "fresh_server",
                "伺服器最新驗證",
                "basic",
                "fresh_server",
            ),
            (
                "幹部",
                "啟用",
                "fresh_server",
                "伺服器最新驗證",
                "officer_report_enabled",
                "fresh_server",
            ),
            (
                "幹部",
                "停用",
                "fresh_server",
                "伺服器最新驗證",
                "officer_report_disabled",
                "fresh_server",
            ),
            (
                "一般使用者",
                "停用",
                "offline_cache",
                "離線快取，非權威",
                "basic_non_authoritative",
                "offline_cache",
            ),
            (
                "幹部",
                "啟用",
                "unknown",
                "來源未確認，非權威",
                "officer_report_enabled_non_authoritative",
                "unknown",
            ),
        )
        for role, report, token, label, expected_state, expected_provenance in cases:
            with self.subTest(token=token, role=role, report=report):
                projection = (
                    f"偵錯權限投影：{role}；報表讀取：{report}；來源："
                    f"{token}（{label}）"
                )
                xml = f'<hierarchy><node content-desc="{projection}"/><node content-desc="{sentinel}"/></hierarchy>'
                result = self.run_harness(
                    f"""
                    function Invoke-BoundedProcess {{
                        return [pscustomobject]@{{TimedOut=$false;ExitCode=0;Stdout='{xml}';Stderr=''}}
                    }}
                    $config=[pscustomobject]@{{adb_executable='E:/mock/adb.exe';serial='emulator-5556'}}
                    $value=Get-AllowlistedUiCounts $config
                    Write-Output ('state='+$value.semantic_state+',provenance='+$value.provenance)
                    """
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(
                    f"state={expected_state},provenance={expected_provenance}",
                    result.stdout,
                )
                self.assertNotIn(sentinel, result.stdout + result.stderr)

    def test_principal_provenance_rejects_legacy_ambiguous_and_malformed_projection(
        self,
    ):
        sentinel = "private-provider-subject-sentinel"
        exact = (
            "偵錯權限投影：幹部；報表讀取：啟用；來源：fresh_server（伺服器最新驗證）"
        )
        login = (
            '<node package="tw.org.ntubtob.portal" class="android.widget.Button" '
            'content-desc="LINE 登入" enabled="true" clickable="true"/>'
        )
        cases = (
            (
                f'<node content-desc="{exact}"/><node content-desc="{exact}"/>',
                "duplicate",
            ),
            (f'{login}<node content-desc="{exact}"/>', "coexisting"),
            ('<node content-desc="偵錯權限投影：幹部；報表讀取：啟用"/>', "legacy"),
            (
                '<node content-desc="偵錯權限投影：一般使用者；報表讀取：啟用；來源：fresh_server（伺服器最新驗證）"/>',
                "inconsistent",
            ),
            (
                '<node content-desc="偵錯權限投影：一般使用者；報表讀取：停用；來源：fresh_server（伺服器最新驗證）'
                '&#10;幹部&#10;報表讀取：停用；來源：fresh_server（伺服器最新驗證）"/>',
                "mismatched merged semantics",
            ),
            (
                '<node content-desc="偵錯權限投影：幹部；報表讀取：啟用；來源：fresh_server（離線快取，非權威）"/>',
                "mismatched provenance label",
            ),
        )
        for nodes, case_name in cases:
            with self.subTest(case=case_name):
                xml = f'<hierarchy>{nodes}<node content-desc="{sentinel}"/></hierarchy>'
                result = self.run_harness(
                    f"""
                    function Invoke-BoundedProcess {{
                        return [pscustomobject]@{{TimedOut=$false;ExitCode=0;Stdout='{xml}';Stderr=''}}
                    }}
                    $config=[pscustomobject]@{{adb_executable='E:/mock/adb.exe';serial='emulator-5556'}}
                    try {{ Get-AllowlistedUiCounts $config; exit 9 }} catch {{ Write-Output $_.Exception.Message }}
                    """
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(
                    "Accessibility foreground state is not exact", result.stdout
                )
                self.assertNotIn(sentinel, result.stdout + result.stderr)

    def test_principal_consumer_keeps_deferred_vocabulary_out_of_parser(self):
        source = LAUNCHER.read_text(encoding="utf-8")
        body = re.search(
            r"function Get-AllowlistedUiCounts \{(.*?)\n\}", source, re.S
        ).group(1)
        for token in ("fresh_server", "offline_cache", "unknown"):
            self.assertIn(token, body)
        for deferred in (
            "cold_reconstructed",
            "terminal_local",
            "offline_report_readonly",
            "ownReply",
        ):
            self.assertNotIn(deferred, body)

    def test_accessibility_transport_rejects_unsafe_results_without_disclosure(self):
        source = LAUNCHER.read_text(encoding="utf-8")
        body = re.search(
            r"function Get-AllowlistedUiCounts \{(.*?)\n\}", source, re.S
        ).group(1)
        self.assertIn("'exec-out', 'uiautomator', 'dump', '/dev/tty'", body)
        for forbidden in ("'shell'", "'cat'", "'pull'", "'rm'", "/data/"):
            self.assertNotIn(forbidden, body)

        sentinel = "private-provider-subject-sentinel"
        for timed_out, exit_code, expected_error in (
            ("$true", 0, "Accessibility inventory failed safely"),
            ("$false", 1, "Accessibility inventory failed safely"),
        ):
            with self.subTest(timed_out=timed_out, exit_code=exit_code):
                result = self.run_harness(
                    f"""
                    function Invoke-BoundedProcess {{
                        param($Executable,$Arguments,$TimeoutSeconds)
                        return [pscustomobject]@{{TimedOut={timed_out};ExitCode={exit_code};Stdout='{sentinel}';Stderr='{sentinel}'}}
                    }}
                    $config=[pscustomobject]@{{adb_executable='E:/mock/adb.exe';serial='emulator-5556'}}
                    try {{ Get-AllowlistedUiCounts $config;exit 9 }} catch {{ Write-Output $_.Exception.Message }}
                    """
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(expected_error, result.stdout)
                self.assertNotIn(sentinel, result.stdout + result.stderr)

    def test_status_skips_accessibility_for_absent_background_and_stopped(self):
        cases = (
            ("absent", "none", "package_absent"),
            ("installed", "other", "portal_background"),
            ("installed", "none", "portal_stopped"),
        )
        for package, activity, semantic_state in cases:
            with self.subTest(semantic_state=semantic_state):
                result = self.run_harness(
                    f"""
                    $script:uiCalls=0
                    function Assert-OnlyApprovedSerial {{ param($Config) }}
                    function Get-PackageState {{ param($Config) return '{package}' }}
                    function Get-CurrentActivity {{ param($Config) return '{activity}' }}
                    function Get-AllowlistedUiCounts {{ $script:uiCalls++;throw 'must not inspect accessibility' }}
                    $config=[pscustomobject]@{{}}
                    $value=Invoke-Status $config
                    Write-Output ($value.semantic_state+',login='+$value.login+',basic='+$value.basic+',officer='+$value.officer+',uiCalls='+$script:uiCalls)
                    """
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(
                    f"{semantic_state},login=0,basic=0,officer=0,uiCalls=0",
                    result.stdout,
                )
                self.assertNotIn(
                    "secrets versions access", result.stdout + result.stderr
                )

    def test_current_activity_uses_only_one_exact_foreground_record(self):
        cases = (
            (
                "background",
                """ACTIVITY MANAGER ACTIVITIES
  * Hist #0: ActivityRecord{111 u0 tw.org.ntubtob.portal/.MainActivity t42}
mResumedActivity: ActivityRecord{222 u0 com.android.chrome/com.google.android.apps.chrome.Main t88}""",
                "other,portal_background,uiCalls=0",
            ),
            (
                "stopped",
                """ACTIVITY MANAGER ACTIVITIES
  * Hist #0: ActivityRecord{111 u0 tw.org.ntubtob.portal/.MainActivity t42}""",
                "none,portal_stopped,uiCalls=0",
            ),
            (
                "portal",
                """ACTIVITY MANAGER ACTIVITIES
topResumedActivity=ActivityRecord{111 u0 tw.org.ntubtob.portal/.MainActivity t42}""",
                "portal,logged_out,uiCalls=1",
            ),
        )
        for _, inventory, expected in cases:
            with self.subTest(expected=expected):
                escaped = inventory.replace("'", "''")
                result = self.run_harness(
                    f"""
                    $script:uiCalls=0
                    function Assert-OnlyApprovedSerial {{ param($Config) }}
                    function Get-PackageState {{ param($Config) return 'installed' }}
                    function Invoke-BoundedProcess {{
                        return [pscustomobject]@{{TimedOut=$false;ExitCode=0;Stdout=@'
{escaped}
'@;Stderr=''}}
                    }}
                    function Get-AllowlistedUiCounts {{
                        param($Config)
                        $script:uiCalls++
                        return [ordered]@{{semantic_state='logged_out';provenance='none';login=1;basic=0;officer=0;report_enabled=0;report_disabled=0}}
                    }}
                    $config=[pscustomobject]@{{adb_executable='E:/mock/adb.exe';serial='emulator-5556'}}
                    $activity=Get-CurrentActivity $config
                    $value=Invoke-Status $config
                    Write-Output ($activity+','+$value.semantic_state+',uiCalls='+$script:uiCalls)
                    """
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(expected, result.stdout)
                self.assert_safe_output(result)

    def test_current_activity_rejects_ambiguous_malformed_and_unsafe_output(self):
        sentinel = "private-provider-subject-sentinel"
        cases = (
            (
                "duplicate",
                """mResumedActivity: ActivityRecord{111 u0 tw.org.ntubtob.portal/.MainActivity t42}
mFocusedActivity: ActivityRecord{222 u0 com.android.chrome/.Main t88}""",
                False,
                "Current activity inventory is ambiguous",
            ),
            (
                "malformed",
                f"mResumedActivity: {sentinel}",
                False,
                "Current activity inventory is malformed",
            ),
            (
                "oversized",
                "x" * 65537,
                False,
                "Activity inventory size is not bounded",
            ),
            (
                "timeout",
                sentinel,
                True,
                "Activity inventory failed safely",
            ),
        )
        for _, inventory, timed_out, expected_error in cases:
            with self.subTest(expected_error=expected_error):
                escaped = inventory.replace("'", "''")
                timed_out_literal = "$true" if timed_out else "$false"
                result = self.run_harness(
                    f"""
                    $script:uiCalls=0
                    function Assert-OnlyApprovedSerial {{ param($Config) }}
                    function Get-PackageState {{ param($Config) return 'installed' }}
                    function Invoke-BoundedProcess {{
                        return [pscustomobject]@{{TimedOut={timed_out_literal};ExitCode=0;Stdout=@'
{escaped}
'@;Stderr=''}}
                    }}
                    function Get-AllowlistedUiCounts {{ $script:uiCalls++;throw 'must not inspect accessibility' }}
                    $config=[pscustomobject]@{{adb_executable='E:/mock/adb.exe';serial='emulator-5556'}}
                    try {{ Invoke-Status $config;exit 9 }} catch {{ Write-Output ($_.Exception.Message+',uiCalls='+$script:uiCalls) }}
                    """
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(expected_error + ",uiCalls=0", result.stdout)
                self.assertNotIn(sentinel, result.stdout + result.stderr)

    def test_disk_lock_avd_and_serial_fail_closed(self):
        result = self.run_harness(
            """
            function Get-PSDrive { return $null }
            $config=[pscustomobject]@{min_free_bytes=1073741824;temp_root='E:/codex-temp/task-123'}
            try { Assert-DiskAndLock $config; exit 9 } catch { Write-Output $_.Exception.Message }
            function Invoke-BoundedProcess { return [pscustomobject]@{TimedOut=$false;ExitCode=0;Stdout="emulator-5556`toffline";Stderr=''} }
            $config=[pscustomobject]@{adb_executable='E:/mock/adb.exe'}
            try { Get-AdbSerials $config; exit 8 } catch { Write-Output $_.Exception.Message }
            function Get-AdbSerials { param($Config) return @('emulator-5556','emulator-5558') }
            $config=[pscustomobject]@{serial='emulator-5556'}
            try { Assert-OnlyApprovedSerial $config; exit 7 } catch { Write-Output $_.Exception.Message }
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("insufficient or unknown", result.stdout)
        self.assertIn("ADB serial state is not ready", result.stdout)
        self.assertIn("ADB serial inventory is not exact", result.stdout)

    def test_avd_reuses_only_the_exact_configured_serial(self):
        result = self.run_harness(
            """
            function Invoke-BoundedProcess { return [pscustomobject]@{TimedOut=$false;ExitCode=0;Stdout="task123_avd`n";Stderr=''} }
            function Get-AdbSerials { param($Config) return @('emulator-5556') }
            $config=[pscustomobject]@{serial='emulator-5556';avd_name='task123_avd';emulator_executable='E:/mock/emulator.exe';android_sdk_root='E:/mock/sdk';android_avd_home='E:/mock/avd'}
            $value=Invoke-AvdStart $config
            Write-Output ($value.result+','+$value.serial)
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("reused,approved", result.stdout)

    def test_signer_zero_multiple_mismatch_and_exact_success(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            homes = [base / "one", base / "two"]
            for home in homes:
                home.mkdir(parents=True)
            config = (
                "[pscustomobject]@{android_user_homes=@('"
                + homes[0].as_posix()
                + "','"
                + homes[1].as_posix()
                + f"');keytool_executable='{LAUNCHER.as_posix()}';signer_allowlist=@('{FINGERPRINT}')}}"
            )
            cases = (
                ((), FINGERPRINT, False),
                ((0, 1), FINGERPRINT, False),
                ((0,), "B" * 64, False),
                ((0,), FINGERPRINT, True),
            )
            for existing, reported, success in cases:
                for home in homes:
                    key = home / "debug.keystore"
                    if key.exists():
                        key.unlink()
                for index in existing:
                    (homes[index] / "debug.keystore").write_bytes(b"fake")
                result = self.run_harness(
                    f"""
                    function Invoke-BoundedProcess {{ return [pscustomobject]@{{TimedOut=$false;ExitCode=0;Stdout='SHA256: {reported}';Stderr=''}} }}
                    $config={config}
                    try {{
                        $value=Get-AllowlistedDebugSigner $config
                        Write-Output ('matched='+([string]$value.Fingerprint -ceq [string]$config.signer_allowlist[0]))
                        $value.Stream.Dispose()
                    }} catch {{ Write-Output ('ERROR='+$_.Exception.Message) }}
                    """
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                if success:
                    self.assertIn("matched=True", result.stdout)
                else:
                    self.assertIn("Exactly one allowlisted debug signer", result.stdout)
                for home in homes:
                    self.assertNotIn(str(home), result.stdout + result.stderr)
                self.assertNotIn("androiddebugkey", result.stdout + result.stderr)
                self.assertNotIn("storepass", result.stdout + result.stderr)

            nested_key = homes[0] / ".android" / "debug.keystore"
            for home in homes:
                root_key = home / "debug.keystore"
                if root_key.exists():
                    root_key.unlink()
            nested_key.parent.mkdir()
            nested_key.write_bytes(b"nested-must-not-match")
            result = self.run_harness(
                f"""
                function Invoke-BoundedProcess {{ throw 'nested signer must not be inspected' }}
                $config={config}
                try {{ Get-AllowlistedDebugSigner $config; exit 9 }} catch {{ Write-Output $_.Exception.Message }}
                """
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Exactly one allowlisted debug signer", result.stdout)
            self.assertNotIn("nested signer", result.stdout)
            self.assertNotIn(str(nested_key), result.stdout + result.stderr)

    def test_signer_rejects_reparse_home_or_keystore_before_keytool(self):
        with tempfile.TemporaryDirectory() as directory:
            android_home = Path(directory) / "android-home"
            android_home.mkdir()
            (android_home / "debug.keystore").write_bytes(b"fake")
            for reparse_target in ("home", "file"):
                with self.subTest(reparse_target=reparse_target):
                    result = self.run_harness(
                        f"""
                        $script:keytoolStarted=$false
                        function Get-Item {{
                            param([string]$LiteralPath,[switch]$Force)
                            $isFile=$LiteralPath.EndsWith('debug.keystore',[StringComparison]::OrdinalIgnoreCase)
                            $isReparse=$(if('{reparse_target}' -eq 'file'){{$isFile}}else{{-not $isFile}})
                            $attributes=$(if($isReparse){{[IO.FileAttributes]::ReparsePoint}}elseif($isFile){{[IO.FileAttributes]::Normal}}else{{[IO.FileAttributes]::Directory}})
                            return [pscustomobject]@{{PSIsContainer=(-not $isFile);Attributes=$attributes}}
                        }}
                        function Invoke-BoundedProcess {{ $script:keytoolStarted=$true;throw 'must not start' }}
                        $config=[pscustomobject]@{{android_user_homes=@('{android_home.as_posix()}');keytool_executable='E:/mock/keytool.exe';signer_allowlist=@('{FINGERPRINT}')}}
                        try {{ Get-AllowlistedDebugSigner $config;exit 9 }} catch {{ Write-Output ($_.Exception.Message+',started='+$script:keytoolStarted) }}
                        """
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn(
                        "Debug signer path contains a reparse point,started=False",
                        result.stdout,
                    )
                    self.assertNotIn(str(android_home), result.stdout + result.stderr)

    def test_signer_rejects_hardlink_count_before_keytool(self):
        with tempfile.TemporaryDirectory() as directory:
            android_home = Path(directory) / "android-home"
            android_home.mkdir()
            (android_home / "debug.keystore").write_bytes(b"fake")
            result = self.run_harness(
                f"""
                $script:keytoolStarted=$false
                function Get-WindowsFileIdentity {{
                    return [pscustomobject]@{{FileIdentity='fixed';FileSize=4;LastWriteHigh=1;LastWriteLow=2;NumberOfLinks=2}}
                }}
                function Get-DebugSignerFingerprint {{ $script:keytoolStarted=$true;return '{FINGERPRINT}' }}
                $config=[pscustomobject]@{{android_user_homes=@('{android_home.as_posix()}');keytool_executable='E:/mock/keytool.exe';signer_allowlist=@('{FINGERPRINT}')}}
                try {{ Get-AllowlistedDebugSigner $config;exit 9 }} catch {{ Write-Output ($_.Exception.Message+',started='+$script:keytoolStarted) }}
                """
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(
                "Debug signer hardlink count is not exact,started=False",
                result.stdout,
            )
            self.assertNotIn(str(android_home), result.stdout + result.stderr)

    def test_signer_handle_blocks_write_and_revalidation_detects_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            android_home = Path(directory) / "android-home"
            android_home.mkdir()
            keystore = android_home / "debug.keystore"
            keystore.write_bytes(b"fake")
            result = self.run_harness(
                f"""
                function Invoke-BoundedProcess {{ return [pscustomobject]@{{TimedOut=$false;ExitCode=0;Stdout='SHA256: {FINGERPRINT}';Stderr=''}} }}
                $config=[pscustomobject]@{{android_user_homes=@('{android_home.as_posix()}');keytool_executable='E:/mock/keytool.exe';signer_allowlist=@('{FINGERPRINT}')}}
                $value=Get-AllowlistedDebugSigner $config
                try {{
                    $writer=[IO.FileStream]::new('{keystore.as_posix()}',[IO.FileMode]::Open,[IO.FileAccess]::Write,[IO.FileShare]::ReadWrite)
                    $writer.Dispose();$blocked=$false
                }} catch {{ $blocked=$true }}
                $value.Stream.Dispose()
                Write-Output ('writeBlocked='+$blocked)

                $script:identityCall=0
                function Get-WindowsFileIdentity {{
                    $script:identityCall++
                    $size=$(if($script:identityCall -eq 3){{5}}else{{4}})
                    return [pscustomobject]@{{FileIdentity='fixed';FileSize=$size;LastWriteHigh=1;LastWriteLow=2;NumberOfLinks=1}}
                }}
                function Get-DebugSignerFingerprint {{ return '{FINGERPRINT}' }}
                $held=[IO.FileStream]::new('{keystore.as_posix()}',[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
                $signer=[pscustomobject]@{{KeystorePath='{keystore.as_posix()}';Stream=$held;Fingerprint='{FINGERPRINT}';Identity=[pscustomobject]@{{FileIdentity='fixed';FileSize=4;LastWriteHigh=1;LastWriteLow=2;NumberOfLinks=1}}}}
                try {{ Assert-DebugSignerStable $config $signer;exit 8 }} catch {{ Write-Output $_.Exception.Message }} finally {{ $held.Dispose() }}

                function Get-WindowsFileIdentity {{ return [pscustomobject]@{{FileIdentity='fixed';FileSize=4;LastWriteHigh=1;LastWriteLow=2;NumberOfLinks=1}} }}
                function Get-DebugSignerFingerprint {{ return ('B' * 64) }}
                $held=[IO.FileStream]::new('{keystore.as_posix()}',[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
                $signer.Stream=$held
                try {{ Assert-DebugSignerStable $config $signer;exit 7 }} catch {{ Write-Output $_.Exception.Message }} finally {{ $held.Dispose() }}
                """
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("writeBlocked=True", result.stdout)
            self.assertEqual(
                result.stdout.count("Debug signer changed during verification"), 2
            )
            self.assertNotIn(str(android_home), result.stdout + result.stderr)

    def test_install_is_session_preserving_and_uses_only_install_r(self):
        result = self.run_harness(
            """
            $script:args=''
            function Assert-OnlyApprovedSerial { param($Config) }
            function Invoke-SignerCheck { param($Config) return @{} }
            function Get-ArtifactPath { param($Config) return 'E:/codex-evidence/task-123/app-debug.apk' }
            function Invoke-BoundedProcess {
                param($Executable,$Arguments,$TimeoutSeconds,$ChildEnvironment,$WorkingDirectory)
                $script:args=$Arguments -join '|'
                return [pscustomobject]@{TimedOut=$false;ExitCode=0;Stdout="Success`n";Stderr=''}
            }
            $config=[pscustomobject]@{adb_executable='E:/mock/adb.exe';serial='emulator-5556'}
            $result=Invoke-Install $config $true
            Write-Output ($script:args+','+$result.session)
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("-s|emulator-5556|install|-r|", result.stdout)
        self.assertIn("preserved", result.stdout)
        lowered = result.stdout.lower()
        self.assertNotIn("uninstall", lowered)
        self.assertNotIn("|clear|", lowered)
        self.assertNotIn("|-d|", lowered)

    def test_apk_package_identity_is_exact_and_wrong_package_never_installs(self):
        cases = (
            ("", "malformed or ambiguous"),
            ("tw.org.ntubtob.portal`nsecond.package", "malformed or ambiguous"),
            ("not a package", "malformed or ambiguous"),
            ("tw.org.ntubtob.other", "does not match"),
            ("tw.org.ntubtob.portal", "tw.org.ntubtob.portal"),
        )
        for output, expected in cases:
            with self.subTest(output=output):
                result = self.run_harness(
                    f"""
                    function Invoke-BoundedProcess {{ return [pscustomobject]@{{TimedOut=$false;ExitCode=0;Stdout=\"{output}\";Stderr=''}} }}
                    $config=[pscustomobject]@{{apkanalyzer_executable='E:/mock/apkanalyzer.bat';java_home='E:/mock/jdk';android_sdk_root='E:/mock/android-sdk'}}
                    try {{ Write-Output (Get-ApkPackageIdentity $config 'E:/task/app-debug.apk') }} catch {{ Write-Output $_.Exception.Message }}
                    """
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(expected, result.stdout)

        result = self.run_harness(
            """
            $script:adbInstall=$false
            function Invoke-SignerCheck { throw 'APK package identity does not match' }
            function Invoke-BoundedProcess { $script:adbInstall=$true;throw 'must not install' }
            $config=[pscustomobject]@{adb_executable='E:/mock/adb.exe';serial='emulator-5556'}
            try { Invoke-Install $config $true;exit 9 } catch { Write-Output ($_.Exception.Message+',install='+$script:adbInstall) }
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "APK package identity does not match,install=False", result.stdout
        )

    def test_apk_tools_use_exact_child_java_and_reject_unapproved_home(self):
        stale_java = "C:/stale-java-sentinel"
        result = self.run_harness(
            f"""
            $env:JAVA_HOME='{stale_java}'
            $env:PATH='C:/stale-path-sentinel'
            $env:ANDROID_HOME='C:/stale-android-home-sentinel'
            $env:ANDROID_SDK_ROOT='C:/stale-android-sdk-root-sentinel'
            $env:SystemRoot='C:\\Windows'
            $script:calls=0
            function Invoke-BoundedProcess {{
                param($Executable,$Arguments,$TimeoutSeconds,$ChildEnvironment,$WorkingDirectory)
                $script:calls++
                $script:lastChildEnvironment=$ChildEnvironment
                if ($ChildEnvironment.Count -ne 4) {{ throw 'APK tool environment is not closed' }}
                if (-not [string]::Equals([IO.Path]::GetFullPath([string]$ChildEnvironment.JAVA_HOME),[IO.Path]::GetFullPath('E:/approved-jdk'),[StringComparison]::OrdinalIgnoreCase)) {{ throw 'APK Java home is not exact' }}
                $expectedPath=[IO.Path]::GetFullPath('E:/approved-jdk/bin')+[IO.Path]::PathSeparator+[IO.Path]::GetFullPath('C:/Windows/System32')
                if (-not [string]::Equals([string]$ChildEnvironment.PATH,$expectedPath,[StringComparison]::OrdinalIgnoreCase)) {{ throw 'APK Java path is not exact' }}
                if (-not [string]::Equals([IO.Path]::GetFullPath([string]$ChildEnvironment.ANDROID_HOME),[IO.Path]::GetFullPath('E:/approved-sdk'),[StringComparison]::OrdinalIgnoreCase)) {{ throw 'APK Android home is not exact' }}
                if (-not [string]::Equals([IO.Path]::GetFullPath([string]$ChildEnvironment.ANDROID_SDK_ROOT),[IO.Path]::GetFullPath('E:/approved-sdk'),[StringComparison]::OrdinalIgnoreCase)) {{ throw 'APK Android SDK root is not exact' }}
                if ([string]$Executable -like '*apkanalyzer*') {{ return [pscustomobject]@{{TimedOut=$false;ExitCode=0;Stdout='tw.org.ntubtob.portal';Stderr=''}} }}
                return [pscustomobject]@{{TimedOut=$false;ExitCode=0;Stdout='Signer #1 certificate SHA-256 digest: {FINGERPRINT}';Stderr=''}}
            }}
            $config=[pscustomobject]@{{java_home='E:/approved-jdk';android_sdk_root='E:/approved-sdk';apkanalyzer_executable='E:/mock/apkanalyzer.bat';apksigner_executable='E:/mock/apksigner.bat'}}
            $package=Get-ApkPackageIdentity $config 'E:/task/app-debug.apk'
            $fingerprint=Get-ApkSignerFingerprint $config 'E:/task/app-debug.apk'
            if ($env:JAVA_HOME -cne '{stale_java}' -or $env:PATH -cne 'C:/stale-path-sentinel' -or $env:ANDROID_HOME -cne 'C:/stale-android-home-sentinel' -or $env:ANDROID_SDK_ROOT -cne 'C:/stale-android-sdk-root-sentinel') {{ throw 'Parent tool environment changed' }}
            if ($script:lastChildEnvironment.Count -ne 0) {{ throw 'APK Java environment was retained' }}
            Write-Output ('package='+$package+',signerMatch='+($fingerprint -ceq '{FINGERPRINT}')+',calls='+$script:calls)
            foreach ($invalid in @('relative-jdk','C:/unapproved-jdk')) {{
                $script:started=$false
                function Invoke-BoundedProcess {{ $script:started=$true;throw 'must not start' }}
                $invalidConfig=[pscustomobject]@{{java_home=$invalid;android_sdk_root='E:/approved-sdk';apkanalyzer_executable='E:/mock/apkanalyzer.bat';apksigner_executable='E:/mock/apksigner.bat'}}
                try {{ Get-ApkPackageIdentity $invalidConfig 'E:/task/app-debug.apk';exit 9 }} catch {{ Write-Output ($_.Exception.Message+',started='+$script:started) }}
            }}
            foreach ($invalidSdk in @('relative-sdk','C:/unapproved-sdk')) {{
                $script:started=$false
                function Invoke-BoundedProcess {{ $script:started=$true;throw 'must not start' }}
                $invalidConfig=[pscustomobject]@{{java_home='E:/approved-jdk';android_sdk_root=$invalidSdk;apkanalyzer_executable='E:/mock/apkanalyzer.bat';apksigner_executable='E:/mock/apksigner.bat'}}
                try {{ Get-ApkPackageIdentity $invalidConfig 'E:/task/app-debug.apk';exit 9 }} catch {{ Write-Output ($_.Exception.Message+',started='+$script:started) }}
            }}
            foreach ($invalidRoot in @('relative-root','C:\\Windows\\..\\Temp','C:/Windows')) {{
                $script:started=$false
                $env:SystemRoot=$invalidRoot
                function Invoke-BoundedProcess {{ $script:started=$true;throw 'must not start' }}
                try {{ Get-ApkPackageIdentity $config 'E:/task/app-debug.apk';exit 9 }} catch {{ Write-Output ($_.Exception.Message+',started='+$script:started) }}
            }}
            $env:SystemRoot='C:\\Windows'
            function Invoke-BoundedProcess {{
                return [pscustomobject]@{{TimedOut=$false;ExitCode=1;Stdout='apk-stdout-sentinel';Stderr='apk-stderr-sentinel'}}
            }}
            try {{ Get-ApkSignerFingerprint $config 'E:/task/app-debug.apk';exit 9 }} catch {{ Write-Output $_.Exception.Message }}
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "package=tw.org.ntubtob.portal,signerMatch=True,calls=2",
            result.stdout,
        )
        self.assertEqual(
            result.stdout.count("Approved Java home is invalid,started=False"), 2
        )
        self.assertEqual(
            result.stdout.count("Approved Android SDK root is invalid,started=False"), 2
        )
        self.assertEqual(
            result.stdout.count("Approved Windows root is invalid,started=False"), 3
        )
        self.assertIn("APK signer verification failed safely", result.stdout)
        self.assertNotIn(stale_java, result.stdout + result.stderr)
        self.assertNotIn("stale-path-sentinel", result.stdout + result.stderr)
        self.assertNotIn("stale-android-home-sentinel", result.stdout + result.stderr)
        self.assertNotIn(
            "stale-android-sdk-root-sentinel", result.stdout + result.stderr
        )
        self.assertNotIn("apk-stdout-sentinel", result.stdout + result.stderr)
        self.assertNotIn("apk-stderr-sentinel", result.stdout + result.stderr)

    def test_cold_launch_timeout_is_not_retried_and_network_is_restored(self):
        result = self.run_harness(
            """
            $script:startCount=0;$script:network=@()
            function Assert-OnlyApprovedSerial { param($Config) }
            function Get-AirplaneState { param($Config) return '1' }
            function Set-AirplaneState { param($Config,$State) $script:network += $State }
            function Get-CurrentActivity { param($Config) return 'portal' }
            function Invoke-BoundedProcess {
                param($Executable,$Arguments,$TimeoutSeconds,$ChildEnvironment,$WorkingDirectory)
                $joined=$Arguments -join ' '
                if($joined -match 'am start'){$script:startCount++;return [pscustomobject]@{TimedOut=$true;ExitCode=$null;Stdout='';Stderr=''}}
                if($joined -match 'pidof'){return [pscustomobject]@{TimedOut=$false;ExitCode=0;Stdout='1234';Stderr=''}}
                return [pscustomobject]@{TimedOut=$false;ExitCode=0;Stdout='';Stderr=''}
            }
            $config=[pscustomobject]@{adb_executable='E:/mock/adb.exe';serial='emulator-5556'}
            $value=Invoke-ColdLaunch $config
            Write-Output ($value.result+','+$value.retry+',starts='+$script:startCount+',network='+($script:network -join ':'))
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "timeout_but_running,forbidden,starts=1,network=0:1", result.stdout
        )

    def test_launcher_anomaly_still_restores_network(self):
        result = self.run_harness(
            """
            $script:network=@()
            function Assert-OnlyApprovedSerial { param($Config) }
            function Get-AirplaneState { param($Config) return '1' }
            function Set-AirplaneState { param($Config,$State) $script:network += $State }
            function Get-CurrentActivity { param($Config) return 'other' }
            function Invoke-BoundedProcess { return [pscustomobject]@{TimedOut=$false;ExitCode=0;Stdout='';Stderr=''} }
            $config=[pscustomobject]@{adb_executable='E:/mock/adb.exe';serial='emulator-5556'}
            try { Invoke-ColdLaunch $config; exit 9 } catch { Write-Output ($_.Exception.Message+',network='+($script:network -join ':')) }
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Launcher activity is anomalous,network=0:1", result.stdout)

    def test_build_rejects_stale_artifact_before_flutter(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "stale.apk"
            artifact.write_bytes(b"stale")
            result = self.run_harness(
                f"""
                $script:called=$false
                function Assert-Snapshot {{ param($Config,$ExpectedCommit) }}
                function Get-ArtifactPath {{ param($Config) return '{artifact.as_posix()}' }}
                function Invoke-BoundedProcess {{ $script:called=$true; throw 'should-not-run' }}
                $config=[pscustomobject]@{{snapshot_root='{Path(directory).as_posix()}'}}
                try {{ Invoke-Build $config 'fake' '{FULL_SHA}'; exit 9 }} catch {{ Write-Output ($_.Exception.Message+',called='+$script:called) }}
                """
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Stale APK artifact", result.stdout)
            self.assertIn("called=False", result.stdout)

    def test_failed_partial_build_is_removed_without_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot = root / "snapshot"
            output = (
                snapshot
                / "clients"
                / "flutter_app"
                / "build"
                / "app"
                / "outputs"
                / "flutter-apk"
                / "app-debug.apk"
            )
            artifact = root / "evidence" / "app-debug.apk"
            (snapshot / "clients" / "flutter_app").mkdir(parents=True)
            result = self.run_harness(
                f"""
                function Assert-Snapshot {{ param($Config,$ExpectedCommit) }}
                function Assert-TaskPath {{ param($Path,$ExactRoot,[switch]$AllowRoot) return $Path }}
                function Get-ArtifactPath {{ param($Config) return '{artifact.as_posix()}' }}
                function Get-AllowlistedDebugSigner {{ return [pscustomobject]@{{Fingerprint='{FINGERPRINT}';AndroidUserHome='{root.as_posix()}';Stream=$null}} }}
                function Assert-DebugSignerStable {{ param($Config,$Signer) }}
                function Invoke-BoundedProcess {{
                    param($Executable,$Arguments,$TimeoutSeconds,$ChildEnvironment,$WorkingDirectory)
                    [IO.Directory]::CreateDirectory('{output.parent.as_posix()}')|Out-Null
                    [IO.File]::WriteAllBytes('{output.as_posix()}',[byte[]](1,2))
                    return [pscustomobject]@{{TimedOut=$false;ExitCode=1;Stdout='';Stderr=''}}
                }}
                $config=[pscustomobject]@{{snapshot_root='{snapshot.as_posix()}';temp_root='{(root / 'temp').as_posix()}';evidence_root='{(root / 'evidence').as_posix()}';flutter_executable='E:/mock/flutter.cmd';android_sdk_root='E:/mock/android';java_home='E:/mock/jdk';pub_cache='E:/mock/pub';gradle_user_home='E:/mock/gradle'}}
                try {{ Invoke-Build $config 'fake' '{FULL_SHA}';exit 9 }} catch {{ Write-Output ($_.Exception.Message+',output='+(Test-Path '{output.as_posix()}')+',artifact='+(Test-Path '{artifact.as_posix()}')) }}
                """
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(
                "Flutter build failed safely,output=False,artifact=False", result.stdout
            )

    def test_timed_out_partial_build_is_removed_without_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot = root / "snapshot"
            output = (
                snapshot
                / "clients"
                / "flutter_app"
                / "build"
                / "app"
                / "outputs"
                / "flutter-apk"
                / "app-debug.apk"
            )
            artifact = root / "evidence" / "app-debug.apk"
            (snapshot / "clients" / "flutter_app").mkdir(parents=True)
            result = self.run_harness(
                f"""
                function Assert-Snapshot {{ param($Config,$ExpectedCommit) }}
                function Assert-TaskPath {{ param($Path,$ExactRoot,[switch]$AllowRoot) return $Path }}
                function Get-ArtifactPath {{ param($Config) return '{artifact.as_posix()}' }}
                function Get-AllowlistedDebugSigner {{ return [pscustomobject]@{{Fingerprint='{FINGERPRINT}';AndroidUserHome='{root.as_posix()}';Stream=$null}} }}
                function Assert-DebugSignerStable {{ param($Config,$Signer) }}
                function Invoke-BoundedProcess {{
                    param($Executable,$Arguments,$TimeoutSeconds,$ChildEnvironment,$WorkingDirectory)
                    [IO.Directory]::CreateDirectory('{output.parent.as_posix()}')|Out-Null
                    [IO.File]::WriteAllBytes('{output.as_posix()}',[byte[]](1,2))
                    return [pscustomobject]@{{TimedOut=$true;ExitCode=$null;Stdout='';Stderr=''}}
                }}
                $config=[pscustomobject]@{{snapshot_root='{snapshot.as_posix()}';temp_root='{(root / 'temp').as_posix()}';evidence_root='{(root / 'evidence').as_posix()}';flutter_executable='E:/mock/flutter.cmd';android_sdk_root='E:/mock/android';java_home='E:/mock/jdk';pub_cache='E:/mock/pub';gradle_user_home='E:/mock/gradle'}}
                try {{ Invoke-Build $config 'fake' '{FULL_SHA}';exit 9 }} catch {{ Write-Output ($_.Exception.Message+',output='+(Test-Path '{output.as_posix()}')+',artifact='+(Test-Path '{artifact.as_posix()}')) }}
                """
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(
                "Flutter build failed safely,output=False,artifact=False", result.stdout
            )

    def test_build_uses_exact_public_defines_and_redacts_bounded_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot = root / "snapshot"
            temp_root = root / "temp"
            evidence = root / "evidence"
            android_user_home = root / "android-home"
            build_output = (
                snapshot
                / "clients"
                / "flutter_app"
                / "build"
                / "app"
                / "outputs"
                / "flutter-apk"
                / "app-debug.apk"
            )
            (snapshot / "clients" / "flutter_app").mkdir(parents=True)
            android_user_home.mkdir()
            (android_user_home / "debug.keystore").write_bytes(b"fake")
            result = self.run_harness(
                f"""
                $env:MOBILE_STAGING_PUBLIC_ORIGIN='{SENSITIVE_SENTINELS[2]}'
                $env:MOBILE_STAGING_LINE_CHANNEL_ID='{SENSITIVE_SENTINELS[3]}'
                $env:MOBILE_STAGING_GOOGLE_CLIENT_ID='android-client.apps.googleusercontent.com'
                $env:MOBILE_STAGING_GOOGLE_SERVER_CLIENT_ID='web-server.apps.googleusercontent.com'
                function Assert-Snapshot {{ param($Config,$ExpectedCommit) }}
                function Assert-TaskPath {{ param($Path,$ExactRoot,[switch]$AllowRoot) return $Path }}
                function Get-ArtifactPath {{ param($Config) return '{(evidence / 'app-debug.apk').as_posix()}' }}
                function Invoke-BoundedProcess {{
                    param($Executable,$Arguments,$TimeoutSeconds,$ChildEnvironment,$WorkingDirectory)
                    if (@($Arguments) -contains '-list') {{
                        return [pscustomobject]@{{TimedOut=$false;ExitCode=0;Stdout='SHA256: {FINGERPRINT}';Stderr=''}}
                    }}
                    $expected=@(
                        '--dart-define=APP_FLAVOR=staging',
                        '--dart-define=CLIENT_MODE=real',
                        ('--dart-define=API_BASE_URL='+$env:MOBILE_STAGING_PUBLIC_ORIGIN),
                        ('--dart-define=LINE_CHANNEL_ID='+$env:MOBILE_STAGING_LINE_CHANNEL_ID),
                        ('--dart-define=GOOGLE_CLIENT_ID='+$env:MOBILE_STAGING_GOOGLE_CLIENT_ID),
                        ('--dart-define=GOOGLE_SERVER_CLIENT_ID='+$env:MOBILE_STAGING_GOOGLE_SERVER_CLIENT_ID)
                    )
                    $actual=@($Arguments | Where-Object {{ $_ -like '--dart-define=*' }})
                    if ($actual.Count -ne 6) {{ throw 'Build define arguments are not exact' }}
                    for ($index=0;$index -lt 6;$index++) {{
                        if ([string]$actual[$index] -cne [string]$expected[$index]) {{ throw 'Build define arguments are not exact' }}
                    }}
                    if (@($Arguments | Where-Object {{ $_ -like '--dart-define-from-file=*' }}).Count -ne 0) {{ throw 'Build transport is not direct' }}
                    if ([string]$ChildEnvironment.ANDROID_USER_HOME -cne '{android_user_home.as_posix()}') {{ throw 'Build child Android user home is not exact' }}
                    if (-not [string]::Equals([IO.Path]::GetFullPath([string]$ChildEnvironment.APPDATA),[IO.Path]::GetFullPath('{(temp_root / 'flutter-appdata').as_posix()}'),[StringComparison]::OrdinalIgnoreCase)) {{ throw 'Build child APPDATA is not exact' }}
                    if ($ChildEnvironment.ContainsKey('HOME') -or $ChildEnvironment.ContainsKey('USERPROFILE')) {{ throw 'Build child home variables were altered' }}
                    [System.IO.Directory]::CreateDirectory('{build_output.parent.as_posix()}')|Out-Null
                    [System.IO.File]::WriteAllBytes('{build_output.as_posix()}',[byte[]](1,2,3,4))
                    return [pscustomobject]@{{TimedOut=$false;ExitCode=0;Stdout='build complete';Stderr=''}}
                }}
                function Get-ApkSignerFingerprint {{ param($Config,$ApkPath) return '{FINGERPRINT}' }}
                function Get-ApkPackageIdentity {{ param($Config,$ApkPath) return 'tw.org.ntubtob.portal' }}
                $config=[pscustomobject]@{{
                    snapshot_root='{snapshot.as_posix()}';temp_root='{temp_root.as_posix()}';
                    evidence_root='{evidence.as_posix()}';flutter_executable='E:/mock/flutter.cmd';
                    android_sdk_root='E:/mock/android';java_home='E:/mock/jdk';
                    pub_cache='E:/mock/pub';gradle_user_home='E:/mock/gradle';
                    android_user_homes=@('{android_user_home.as_posix()}');keytool_executable='E:/mock/keytool.exe';
                    signer_allowlist=@('{FINGERPRINT}')
                }}
                $value=Invoke-Build $config 'staging' '{FULL_SHA}'
                $manifest=Get-Content -LiteralPath '{(evidence / 'artifact-manifest.json').as_posix()}' -Raw
                Write-Output ($value.result+',definesExists='+(Test-Path '{(temp_root / 'dart-defines.json').as_posix()}')+',manifest='+$manifest)
                """
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("built,definesExists=False", result.stdout)
            self.assertTrue((evidence / "app-debug.apk").is_file())
            self.assertFalse(build_output.exists())
            self.assert_safe_output(result)
            manifest = (evidence / "artifact-manifest.json").read_text(encoding="utf-8")
            self.assertEqual(
                set(json.loads(manifest)),
                {
                    "accepted_commit",
                    "mode",
                    "package",
                    "artifact_sha256",
                    "signer_match",
                    "classification",
                    "retention_owner",
                },
            )
            for sentinel in SENSITIVE_SENTINELS:
                self.assertNotIn(sentinel, manifest)
            self.assertNotIn(FINGERPRINT, manifest)

    def test_build_revalidates_held_signer_before_and_after_flutter(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot = root / "snapshot"
            app_root = snapshot / "clients" / "flutter_app"
            build_output = (
                app_root
                / "build"
                / "app"
                / "outputs"
                / "flutter-apk"
                / "app-debug.apk"
            )
            app_root.mkdir(parents=True)
            artifact = root / "evidence" / "app-debug.apk"
            result = self.run_harness(
                f"""
                $script:stableCalls=0
                function Assert-Snapshot {{ param($Config,$ExpectedCommit) }}
                function Assert-TaskPath {{ param($Path,$ExactRoot,[switch]$AllowRoot) return $Path }}
                function Get-ArtifactPath {{ param($Config) return '{artifact.as_posix()}' }}
                function Get-AllowlistedDebugSigner {{ return [pscustomobject]@{{Fingerprint='{FINGERPRINT}';AndroidUserHome='E:/approved-home';Stream=$null}} }}
                function Assert-DebugSignerStable {{
                    param($Config,$Signer)
                    $script:stableCalls++
                    if($script:stableCalls -eq 2){{throw 'Debug signer changed during verification'}}
                }}
                function Invoke-FlutterBuildProcess {{
                    [IO.Directory]::CreateDirectory('{build_output.parent.as_posix()}')|Out-Null
                    [IO.File]::WriteAllBytes('{build_output.as_posix()}',[byte[]](1,2))
                    return [pscustomobject]@{{TimedOut=$false;ExitCode=0;Stdout='';Stderr=''}}
                }}
                $config=[pscustomobject]@{{snapshot_root='{snapshot.as_posix()}';temp_root='{(root / 'temp').as_posix()}';evidence_root='{(root / 'evidence').as_posix()}'}}
                try {{ Invoke-Build $config 'fake' '{FULL_SHA}';exit 9 }} catch {{ Write-Output ($_.Exception.Message+',calls='+$script:stableCalls+',output='+(Test-Path '{build_output.as_posix()}')+',artifact='+(Test-Path '{artifact.as_posix()}')) }}
                """
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(
                "Debug signer changed during verification,calls=2,output=False,artifact=False",
                result.stdout,
            )

    def test_flutter_define_transport_separates_modes_and_rejects_secret_keys(self):
        sentinel = SENSITIVE_SENTINELS[0]
        with tempfile.TemporaryDirectory() as directory:
            task_temp = Path(directory) / "task-temp"
            result = self.run_harness(
                f"""
                $script:TaskTempRoot='{task_temp.as_posix()}'
                $script:started=$false
                function Invoke-BoundedProcess {{
                    param($Executable,$Arguments,$TimeoutSeconds,$ChildEnvironment,$WorkingDirectory)
                    $script:started=$true
                    $expected=@('--dart-define=APP_FLAVOR=development','--dart-define=CLIENT_MODE=fake')
                    $actual=@($Arguments | Where-Object {{ $_ -like '--dart-define=*' }})
                    if ($actual.Count -ne 2) {{ throw 'Fake define arguments are not exact' }}
                    for ($index=0;$index -lt 2;$index++) {{
                        if ([string]$actual[$index] -cne [string]$expected[$index]) {{ throw 'Fake define arguments are not exact' }}
                    }}
                    return [pscustomobject]@{{TimedOut=$false;ExitCode=0;Stdout='';Stderr=''}}
                }}
                $config=[pscustomobject]@{{temp_root='{task_temp.as_posix()}';flutter_executable='E:/mock/flutter.cmd';android_sdk_root='E:/mock/android';java_home='E:/mock/jdk';pub_cache='E:/mock/pub';gradle_user_home='E:/mock/gradle'}}
                $fake=[ordered]@{{APP_FLAVOR='development';CLIENT_MODE='fake'}}
                [void](Invoke-FlutterBuildProcess $config $fake 'fake' 'E:/mock/app' 'E:/mock/android-home')
                Write-Output ('fakeStarted='+$script:started)
                $script:started=$false
                $adversarial=[ordered]@{{APP_FLAVOR='staging';CLIENT_MODE='real';API_BASE_URL='https://public.invalid';LINE_CHANNEL_ID='2011164500';SECRET_TOKEN='{sentinel}'}}
                try {{ Invoke-FlutterBuildProcess $config $adversarial 'staging' 'E:/mock/app' 'E:/mock/android-home';exit 9 }} catch {{ Write-Output ($_.Exception.Message+',secretStarted='+$script:started) }}
                """
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("fakeStarted=True", result.stdout)
            self.assertIn(
                "Flutter define set is invalid,secretStarted=False", result.stdout
            )
            self.assertNotIn(sentinel, result.stdout + result.stderr)

    def test_help_and_owner_gate_emit_one_governed_json_result(self):
        cases = (
            (["-Action", "help"], "PASS", "agent", "none", 0, None),
            (
                ["-Action", "unknown-action"],
                "DRIFT",
                "agent",
                "none",
                2,
                "CONFIG_INVALID",
            ),
            (
                ["-Action", "private-inspect", "-Mode", "staging", "-Commit", FULL_SHA],
                "OWNER_ACTION_REQUIRED",
                "owner",
                "private-console",
                2,
                "OWNER_ACTION_REQUIRED",
            ),
        )
        for (
            arguments,
            classification,
            operator,
            owner_gate,
            returncode,
            reason_code,
        ) in cases:
            with self.subTest(classification=classification):
                result = subprocess.run(
                    [
                        "powershell.exe",
                        "-NoLogo",
                        "-NoProfile",
                        "-NonInteractive",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-File",
                        str(LAUNCHER),
                        *arguments,
                    ],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=False,
                )
                self.assertEqual(result.returncode, returncode, result.stderr)
                self.assertEqual(len(result.stdout.splitlines()), 1)
                envelope = json.loads(result.stdout)
                self.assertEqual(envelope["classification"], classification)
                self.assertEqual(envelope["operator"], operator)
                self.assertEqual(envelope["owner_gate"], owner_gate)
                self.assertEqual(envelope["standing_authorization"], "DEC-098")
                self.assertEqual(envelope["report_to"], "main-work")
                self.assertEqual(envelope["retention_owner"], "TASK-123")
                if reason_code is not None:
                    self.assertEqual(envelope["details"]["reason_code"], reason_code)
                self.assert_safe_output(result)

    def test_failure_reason_codes_are_bounded_and_never_echo_raw_errors(self):
        result = self.run_harness(
            """
            $messages=@(
              'Launcher config is unavailable or malformed',
              'Snapshot commit does not match',
              'Approved E drive has insufficient or unknown free space',
              'Approved toolchain is incomplete',
              'Task launcher lock already exists',
              'OWNER_ACTION_REQUIRED',
              'ADB inventory failed safely',
              'ADB serial state is not ready',
              'Package inventory failed safely',
              'Package inventory is malformed',
              'Activity inventory failed safely',
              'Activity inventory size is not bounded',
              'Current activity inventory is ambiguous',
              'Accessibility inventory failed safely',
              'Accessibility inventory is malformed',
              'Accessibility foreground state is not exact',
              'private-provider-subject-sentinel'
            )
            foreach($diagnosticMessage in $messages){ Write-Output (Get-FailureReasonCode $diagnosticMessage) }
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.splitlines(),
            [
                "CONFIG_INVALID",
                "SNAPSHOT_INVALID",
                "DISK_UNAVAILABLE",
                "TOOLCHAIN_UNAVAILABLE",
                "LOCK_UNAVAILABLE",
                "OWNER_ACTION_REQUIRED",
                "ADB_UNAVAILABLE",
                "ADB_INVALID",
                "PACKAGE_UNAVAILABLE",
                "PACKAGE_INVALID",
                "ACTIVITY_UNAVAILABLE",
                "ACTIVITY_INVALID",
                "ACTIVITY_INVALID",
                "ACCESSIBILITY_UNAVAILABLE",
                "ACCESSIBILITY_INVALID",
                "SEMANTIC_DRIFT",
                "RUNTIME_FAILED",
            ],
        )
        self.assertNotIn(
            "private-provider-subject-sentinel", result.stdout + result.stderr
        )

    def test_governed_status_failures_emit_exact_safe_reason_codes(self):
        cases = (
            ("ADB inventory failed safely", "FAILED", "ADB_UNAVAILABLE"),
            ("ADB serial inventory is not exact", "FAILED", "ADB_INVALID"),
            ("Package inventory failed safely", "FAILED", "PACKAGE_UNAVAILABLE"),
            ("Package inventory is malformed", "FAILED", "PACKAGE_INVALID"),
            ("Activity inventory failed safely", "FAILED", "ACTIVITY_UNAVAILABLE"),
            ("Activity inventory size is not bounded", "FAILED", "ACTIVITY_INVALID"),
            (
                "Accessibility inventory failed safely",
                "FAILED",
                "ACCESSIBILITY_UNAVAILABLE",
            ),
            (
                "Accessibility inventory is malformed",
                "FAILED",
                "ACCESSIBILITY_INVALID",
            ),
            (
                "Accessibility foreground state is not exact",
                "DRIFT",
                "SEMANTIC_DRIFT",
            ),
        )
        source = LAUNCHER.read_text(encoding="utf-8")
        dispatch = (
            "$details = Invoke-MobileStagingMain $Action $Mode $Commit $ConfigPath "
            "$ApprovalPath ([bool]$PreserveSession) ([bool]$PublicHealth) "
            "([bool]$PurgeEvidence)"
        )
        self.assertEqual(source.count(dispatch), 1)
        with tempfile.TemporaryDirectory() as directory:
            for index, (message, classification, reason_code) in enumerate(cases):
                with self.subTest(reason_code=reason_code):
                    launcher_copy = Path(directory) / f"launcher-{index}.ps1"
                    launcher_copy.write_text(
                        source.replace(dispatch, f"Throw-Safe '{message}'"),
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
                            str(launcher_copy),
                            "-Action",
                            "status",
                        ],
                        cwd=ROOT,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=20,
                        check=False,
                    )
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertEqual(len(result.stdout.splitlines()), 1)
                    envelope = json.loads(result.stdout)
                    self.assertEqual(envelope["classification"], classification)
                    self.assertEqual(envelope["details"]["reason_code"], reason_code)
                    self.assertNotIn(message, result.stdout + result.stderr)
                    self.assert_safe_output(result)

            sentinel = "private-provider-subject-sentinel"
            launcher_copy = Path(directory) / "launcher-raw.ps1"
            launcher_copy.write_text(
                source.replace(dispatch, f"throw '{sentinel}'"), encoding="utf-8"
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
                    str(launcher_copy),
                    "-Action",
                    "status",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
                check=False,
            )
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(len(result.stdout.splitlines()), 1)
            envelope = json.loads(result.stdout)
            self.assertEqual(envelope["classification"], "FAILED")
            self.assertEqual(envelope["details"]["reason_code"], "RUNTIME_FAILED")
            self.assertNotIn(sentinel, result.stdout + result.stderr)

    def test_flutter_appdata_is_task_owned_and_outside_root_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            task_temp = Path(directory) / "task-temp"
            inherited = "C:/global-flutter-config-sentinel"
            evidence_root = Path(directory) / "task-evidence"
            result = self.run_harness(
                f"""
                $env:APPDATA='{inherited}'
                $script:TaskTempRoot='{task_temp.as_posix()}'
                $script:TaskEvidenceRoot='{evidence_root.as_posix()}'
                $script:started=$false
                function Invoke-BoundedProcess {{
                    param($Executable,$Arguments,$TimeoutSeconds,$ChildEnvironment,$WorkingDirectory)
                    $script:started=$true
                    if (-not [string]::Equals([IO.Path]::GetFullPath([string]$ChildEnvironment.APPDATA),[IO.Path]::GetFullPath('{(task_temp / 'flutter-appdata').as_posix()}'),[StringComparison]::OrdinalIgnoreCase)) {{ throw 'Child APPDATA is not exact' }}
                    if ($ChildEnvironment.ContainsKey('HOME') -or $ChildEnvironment.ContainsKey('USERPROFILE')) {{ throw 'Child home variables were altered' }}
                    return [pscustomobject]@{{TimedOut=$false;ExitCode=0;Stdout='';Stderr=''}}
                }}
                $config=[pscustomobject]@{{temp_root='{task_temp.as_posix()}';evidence_root='{evidence_root.as_posix()}';flutter_executable='E:/mock/flutter.cmd';android_sdk_root='E:/mock/android';java_home='E:/mock/jdk';pub_cache='E:/mock/pub';gradle_user_home='E:/mock/gradle'}}
                $values=[ordered]@{{APP_FLAVOR='development';CLIENT_MODE='fake'}}
                [void](Invoke-FlutterBuildProcess $config $values 'fake' 'E:/mock/app' 'E:/mock/android-home')
                Write-Output ('isolated='+$script:started+',created='+(Test-Path -LiteralPath '{(task_temp / 'flutter-appdata').as_posix()}' -PathType Container))
                [void](Invoke-Cleanup $config $false)
                Write-Output ('cleaned='+(-not (Test-Path -LiteralPath '{(task_temp / 'flutter-appdata').as_posix()}')))
                $script:TaskTempRoot='E:/codex-temp/task-123'
                $script:started=$false
                $outside=[ordered]@{{APP_FLAVOR='development';CLIENT_MODE='fake'}}
                try {{ Invoke-FlutterBuildProcess $config $outside 'fake' 'E:/mock/app' 'E:/mock/android-home';exit 9 }} catch {{ Write-Output ($_.Exception.Message+',outsideStarted='+$script:started) }}
                """
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("isolated=True,created=True", result.stdout)
            self.assertIn("cleaned=True", result.stdout)
            self.assertIn(
                "Path escapes the task-owned root,outsideStarted=False", result.stdout
            )
            self.assertNotIn(inherited, result.stdout + result.stderr)

    def test_real_package_state_emits_exact_governed_contract(self):
        sentinel = "private-provider-subject-sentinel"
        installed_path = "package:/data/app/exact/base.apk"
        cases = (
            (True, 0, sentinel, "FAILED", "PACKAGE_UNAVAILABLE", None, 2),
            (False, 1, sentinel, "FAILED", "PACKAGE_UNAVAILABLE", None, 2),
            (False, 0, "", "PASS", None, "absent", 0),
            (False, 0, installed_path, "PASS", None, "installed", 0),
            (
                False,
                0,
                installed_path + "\npackage:/data/app/" + sentinel + "/base.apk",
                "FAILED",
                "PACKAGE_INVALID",
                None,
                2,
            ),
        )
        source = LAUNCHER.read_text(encoding="utf-8")
        dispatch = (
            "$details = Invoke-MobileStagingMain $Action $Mode $Commit $ConfigPath "
            "$ApprovalPath ([bool]$PreserveSession) ([bool]$PublicHealth) "
            "([bool]$PurgeEvidence)"
        )
        entry = "if ($MyInvocation.InvocationName -ne '.') {"
        self.assertEqual(source.count(dispatch), 1)
        self.assertEqual(source.count(entry), 1)
        with tempfile.TemporaryDirectory() as directory:
            for index, (
                timed_out,
                exit_code,
                stdout,
                classification,
                reason_code,
                state,
                expected_exit,
            ) in enumerate(cases):
                with self.subTest(index=index, classification=classification):
                    escaped_stdout = (
                        stdout.replace("`", "``").replace('"', '`"').replace("\n", "`n")
                    )
                    mock = (
                        "function Invoke-BoundedProcess { "
                        "return [pscustomobject]@{"
                        f"TimedOut=${str(timed_out).lower()};ExitCode={exit_code};"
                        f'Stdout="{escaped_stdout}";Stderr="{sentinel}"'
                        "} }\n"
                    )
                    real_package_dispatch = (
                        "$packageState = Get-PackageState "
                        "([pscustomobject]@{adb_executable='E:/mock/adb.exe';"
                        "serial='emulator-5556'}); "
                        "$details = [ordered]@{result=$packageState}"
                    )
                    launcher_copy = Path(directory) / f"package-{index}.ps1"
                    launcher_copy.write_text(
                        source.replace(entry, mock + entry).replace(
                            dispatch, real_package_dispatch
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
                            str(launcher_copy),
                            "-Action",
                            "status",
                        ],
                        cwd=ROOT,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=20,
                        check=False,
                    )
                    self.assertEqual(result.returncode, expected_exit, result.stderr)
                    self.assertEqual(len(result.stdout.splitlines()), 1)
                    envelope = json.loads(result.stdout)
                    self.assertEqual(envelope["classification"], classification)
                    if reason_code:
                        self.assertEqual(
                            envelope["details"]["reason_code"], reason_code
                        )
                    else:
                        self.assertEqual(envelope["details"]["result"], state)
                    self.assertNotIn(installed_path, result.stdout + result.stderr)
                    self.assertNotIn(sentinel, result.stdout + result.stderr)
                    self.assert_safe_output(result)

    def test_real_status_stage_boundaries_sanitize_unknown_exceptions(self):
        sentinel = "private-provider-subject-sentinel"
        cases = (
            (
                f"function Assert-OnlyApprovedSerial {{ throw '{sentinel}' }}",
                "FAILED",
                "ADB_UNAVAILABLE",
            ),
            (
                "function Assert-OnlyApprovedSerial {}\n"
                f"function Get-PackageState {{ throw '{sentinel}' }}",
                "FAILED",
                "PACKAGE_UNAVAILABLE",
            ),
            (
                "function Assert-OnlyApprovedSerial {}\n"
                "function Get-PackageState { return 'installed' }\n"
                f"function Get-CurrentActivity {{ throw '{sentinel}' }}",
                "FAILED",
                "ACTIVITY_UNAVAILABLE",
            ),
            (
                "function Assert-OnlyApprovedSerial {}\n"
                "function Get-PackageState { return 'installed' }\n"
                "function Get-CurrentActivity { return 'portal' }\n"
                f"function Get-AllowlistedUiCounts {{ throw '{sentinel}' }}",
                "FAILED",
                "ACCESSIBILITY_UNAVAILABLE",
            ),
            (
                "function Assert-OnlyApprovedSerial {}\n"
                "function Get-PackageState { return 'installed' }\n"
                "function Get-CurrentActivity { return 'portal' }\n"
                "function Get-AllowlistedUiCounts { "
                "Throw-Safe 'Accessibility foreground state is not exact' }",
                "DRIFT",
                "SEMANTIC_DRIFT",
            ),
        )
        source = LAUNCHER.read_text(encoding="utf-8")
        dispatch = (
            "$details = Invoke-MobileStagingMain $Action $Mode $Commit $ConfigPath "
            "$ApprovalPath ([bool]$PreserveSession) ([bool]$PublicHealth) "
            "([bool]$PurgeEvidence)"
        )
        entry = "if ($MyInvocation.InvocationName -ne '.') {"
        self.assertEqual(source.count(dispatch), 1)
        self.assertEqual(source.count(entry), 1)
        with tempfile.TemporaryDirectory() as directory:
            for index, (overrides, classification, reason_code) in enumerate(cases):
                with self.subTest(reason_code=reason_code):
                    launcher_copy = Path(directory) / f"status-stage-{index}.ps1"
                    launcher_copy.write_text(
                        source.replace(entry, overrides + "\n" + entry).replace(
                            dispatch,
                            "$details = Invoke-Status ([pscustomobject]@{})",
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
                            str(launcher_copy),
                            "-Action",
                            "status",
                        ],
                        cwd=ROOT,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=20,
                        check=False,
                    )
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertEqual(len(result.stdout.splitlines()), 1)
                    envelope = json.loads(result.stdout)
                    self.assertEqual(envelope["classification"], classification)
                    self.assertEqual(envelope["details"]["reason_code"], reason_code)
                    self.assertNotIn(sentinel, result.stdout + result.stderr)
                    self.assert_safe_output(result)

    def test_accessibility_readiness_retries_only_transient_inventory_states(self):
        cases = (
            (
                "@('Accessibility inventory failed safely',"
                "'Accessibility inventory is malformed','success')",
                "success",
                3,
                2,
            ),
            (
                "@('Accessibility inventory is malformed',"
                "'Accessibility inventory is malformed',"
                "'Accessibility inventory is malformed')",
                "Accessibility inventory is malformed",
                3,
                2,
            ),
            (
                "@('Accessibility foreground state is not exact')",
                "Accessibility foreground state is not exact",
                1,
                0,
            ),
            (
                "@('private-provider-subject-sentinel')",
                "unknown",
                1,
                0,
            ),
        )
        for sequence, expected, attempts, waits in cases:
            with self.subTest(expected=expected):
                result = self.run_harness(
                    f"""
                    $script:attempts=0
                    $script:waits=0
                    $script:sequence={sequence}
                    function Start-Sleep {{ param([int]$Seconds) $script:waits++ }}
                    function Get-AllowlistedUiCounts {{
                        $value=$script:sequence[$script:attempts]
                        $script:attempts++
                        if ($value -eq 'success') {{ return 'success' }}
                        throw $value
                    }}
                    try {{
                        $value=Get-ReadyAllowlistedUiCounts ([pscustomobject]@{{}})
                    }} catch {{
                        $value=if ($_.Exception.Message -eq 'private-provider-subject-sentinel') {{
                            'unknown'
                        }} else {{
                            $_.Exception.Message
                        }}
                    }}
                    Write-Output ($value+',attempts='+$script:attempts+',waits='+$script:waits)
                    """
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    result.stdout.strip(),
                    f"{expected},attempts={attempts},waits={waits}",
                )
                self.assertNotIn(
                    "private-provider-subject-sentinel",
                    result.stdout + result.stderr,
                )

    def test_status_uses_local_accessibility_readiness_and_sanitizes_unknown(self):
        sentinel = "private-provider-subject-sentinel"
        result = self.run_harness(
            f"""
            function Assert-OnlyApprovedSerial {{}}
            function Get-PackageState {{ return 'installed' }}
            function Get-CurrentActivity {{ return 'portal' }}
            function Get-ReadyAllowlistedUiCounts {{ throw '{sentinel}' }}
            try {{ Invoke-Status ([pscustomobject]@{{}}); exit 9 }}
            catch {{ Write-Output $_.Exception.Message }}
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "Accessibility inventory failed safely")
        self.assertNotIn(sentinel, result.stdout + result.stderr)

    def test_full_entrypoint_status_success_states_are_governed_passes(self):
        cases = (
            (
                "function Assert-OnlyApprovedSerial {}\n"
                "function Get-PackageState { return 'absent' }\n"
                "function Get-CurrentActivity { return 'none' }",
                "package_absent",
            ),
            (
                "function Assert-OnlyApprovedSerial {}\n"
                "function Get-PackageState { return 'installed' }\n"
                "function Get-CurrentActivity { return 'other' }",
                "portal_background",
            ),
            (
                "function Assert-OnlyApprovedSerial {}\n"
                "function Get-PackageState { return 'installed' }\n"
                "function Get-CurrentActivity { return 'none' }",
                "portal_stopped",
            ),
            (
                "function Assert-OnlyApprovedSerial {}\n"
                "function Get-PackageState { return 'installed' }\n"
                "function Get-CurrentActivity { return 'portal' }\n"
                "function Get-AllowlistedUiCounts { return [ordered]@{"
                "semantic_state='logged_out';provenance='none';login=1;basic=0;officer=0;"
                "report_enabled=0;report_disabled=0} }",
                "logged_out",
            ),
            (
                "function Assert-OnlyApprovedSerial {}\n"
                "function Get-PackageState { return 'installed' }\n"
                "function Get-CurrentActivity { return 'portal' }\n"
                "function Get-AllowlistedUiCounts { return [ordered]@{"
                "semantic_state='officer_report_enabled';provenance='fresh_server';login=0;basic=0;officer=1;"
                "report_enabled=1;report_disabled=0} }",
                "officer_report_enabled",
            ),
        )
        source = LAUNCHER.read_text(encoding="utf-8")
        dispatch = (
            "$details = Invoke-MobileStagingMain $Action $Mode $Commit $ConfigPath "
            "$ApprovalPath ([bool]$PreserveSession) ([bool]$PublicHealth) "
            "([bool]$PurgeEvidence)"
        )
        entry = "if ($MyInvocation.InvocationName -ne '.') {"
        self.assertEqual(source.count(dispatch), 1)
        self.assertEqual(source.count(entry), 1)
        with tempfile.TemporaryDirectory() as directory:
            for index, (overrides, semantic_state) in enumerate(cases):
                with self.subTest(semantic_state=semantic_state):
                    launcher_copy = Path(directory) / f"status-pass-{index}.ps1"
                    launcher_copy.write_text(
                        source.replace(entry, overrides + "\n" + entry).replace(
                            dispatch,
                            "$details = Invoke-Status ([pscustomobject]@{})",
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
                            str(launcher_copy),
                            "-Action",
                            "status",
                        ],
                        cwd=ROOT,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=20,
                        check=False,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(len(result.stdout.splitlines()), 1)
                    envelope = json.loads(result.stdout)
                    self.assertEqual(envelope["classification"], "PASS")
                    self.assertEqual(envelope["details"]["result"], "observed")
                    self.assertEqual(
                        envelope["details"]["semantic_state"], semantic_state
                    )
                    self.assert_safe_output(result)

    def test_common_entrypoint_rejects_missing_or_malformed_action_result(self):
        sentinel = "private-provider-subject-sentinel"
        replacements = (
            "$details = [ordered]@{action='status'}",
            f"$details = [ordered]@{{result='{sentinel}'}}",
        )
        source = LAUNCHER.read_text(encoding="utf-8")
        dispatch = (
            "$details = Invoke-MobileStagingMain $Action $Mode $Commit $ConfigPath "
            "$ApprovalPath ([bool]$PreserveSession) ([bool]$PublicHealth) "
            "([bool]$PurgeEvidence)"
        )
        self.assertEqual(source.count(dispatch), 1)
        with tempfile.TemporaryDirectory() as directory:
            for index, replacement in enumerate(replacements):
                launcher_copy = Path(directory) / f"invalid-result-{index}.ps1"
                launcher_copy.write_text(
                    source.replace(dispatch, replacement), encoding="utf-8"
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
                        str(launcher_copy),
                        "-Action",
                        "status",
                    ],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=20,
                    check=False,
                )
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(len(result.stdout.splitlines()), 1)
                envelope = json.loads(result.stdout)
                self.assertEqual(envelope["classification"], "FAILED")
                self.assertEqual(
                    envelope["details"]["reason_code"], "ACTION_RESULT_INVALID"
                )
                self.assertNotIn(sentinel, result.stdout + result.stderr)
                self.assert_safe_output(result)

    def test_output_redaction_fallback_is_one_failed_json_and_exit_two(self):
        sentinel = "postgresql://private-user:private-password@private.invalid/staging"
        with tempfile.TemporaryDirectory() as directory:
            launcher_copy = Path(directory) / "Invoke-MobileStaging.ps1"
            source = LAUNCHER.read_text(encoding="utf-8")
            original = "return [ordered]@{ result = 'available'; actions = @($script:RoutineActions + $script:PrivateActions) }"
            injected = f"return [ordered]@{{ result = 'available'; actions = @($script:RoutineActions + $script:PrivateActions); diagnostic = '{sentinel}' }}"
            self.assertEqual(source.count(original), 1)
            launcher_copy.write_text(
                source.replace(original, injected), encoding="utf-8"
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
                    str(launcher_copy),
                    "-Action",
                    "help",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(len(result.stdout.splitlines()), 1)
            envelope = json.loads(result.stdout)
            self.assertEqual(envelope["classification"], "FAILED")
            self.assertEqual(
                envelope["details"]["reason_code"], "OUTPUT_REDACTION_FAILED"
            )
            self.assertNotIn(sentinel, result.stdout + result.stderr)
            self.assertNotIn("Launcher output failed", result.stdout + result.stderr)
            self.assertEqual(result.stderr, "")

    def test_safe_json_rejects_raw_signer_fingerprint_fields(self):
        result = self.run_harness(
            f"""
            try {{
                Write-SafeJson ([ordered]@{{result='matched';signer_sha256='{FINGERPRINT}'}})
                exit 9
            }} catch {{ Write-Output $_.Exception.Message }}
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Launcher output failed the sensitive-field gate", result.stdout)
        self.assertNotIn(FINGERPRINT, result.stdout + result.stderr)

    def test_source_avoids_automatic_and_readonly_variable_collisions(self):
        source = LAUNCHER.read_text(encoding="utf-8")
        blocked = {
            "args",
            "error",
            "executioncontext",
            "foreach",
            "home",
            "host",
            "input",
            "lastexitcode",
            "matches",
            "myinvocation",
            "ofs",
            "pid",
            "profile",
            "psboundparameters",
            "pscmdlet",
            "pshome",
            "pwd",
            "shellid",
            "stacktrace",
            "switch",
            "this",
        }
        assigned = {
            name.casefold()
            for name in re.findall(
                r"(?im)(?:^|[;{])\s*\$([A-Za-z][A-Za-z0-9_]*)\s*=", source
            )
        }
        iterators = {
            name.casefold()
            for name in re.findall(
                r"(?i)foreach\s*\(\s*\$([A-Za-z][A-Za-z0-9_]*)", source
            )
        }
        self.assertFalse((assigned | iterators) & blocked)

    def test_routine_dispatch_does_not_load_private_tools_or_environment(self):
        source = LAUNCHER.read_text(encoding="utf-8")
        routine_body = re.search(
            r"function Invoke-MobileStagingMain \{(.*?)\n\}", source, re.S
        ).group(1)
        pre_private = routine_body.split(
            "if ($SelectedAction -in @('private-inspect'", maxsplit=1
        )[0]
        for forbidden in (
            "Resolve-PrivateExecutable",
            "MOBILE_STAGING_DATABASE_URL",
            "MOBILE_STAGING_PROVIDER_SUBJECT",
            "secrets",
            "tools.mobile_staging_data",
        ):
            self.assertNotIn(forbidden, pre_private)
        config_body = re.search(
            r"function Load-LauncherConfig \{(.*?)\n\}", source, re.S
        ).group(1)
        self.assertNotIn("gcloud", config_body.lower())
        self.assertNotIn("python_executable", config_body)

    def test_bounded_process_timeout_leaves_no_child_process(self):
        with tempfile.TemporaryDirectory() as directory:
            pid_file = Path(directory) / "child.pid"
            command = (
                f"[IO.File]::WriteAllText('{pid_file.as_posix()}',"
                "[string][Diagnostics.Process]::GetCurrentProcess().Id);Start-Sleep 20"
            )
            result = self.run_harness(
                f"""
                $exe=[Diagnostics.Process]::GetCurrentProcess().MainModule.FileName
                $value=Invoke-BoundedProcess $exe @('-NoProfile','-Command',\"{command}\") 1
                Start-Sleep -Milliseconds 250
                $childPid=[int](Get-Content -LiteralPath '{pid_file.as_posix()}')
                try {{ [void][Diagnostics.Process]::GetProcessById($childPid);$alive=$true }} catch {{ $alive=$false }}
                Write-Output ('timedOut='+$value.TimedOut+',alive='+$alive)
                """
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("timedOut=True,alive=False", result.stdout)

    def test_task_lock_rejects_concurrent_and_stale_ownership(self):
        with tempfile.TemporaryDirectory() as directory:
            temp_root = Path(directory) / "task-temp"
            lock_path = Path(str(temp_root) + ".lock")
            result = self.run_harness(
                f"""
                $script:TaskTempRoot='{temp_root.as_posix()}'
                $config=[pscustomobject]@{{temp_root='{temp_root.as_posix()}'}}
                $first=Enter-TaskLock $config
                try {{ Enter-TaskLock $config;exit 9 }} catch {{ $collision=$_.Exception.Message }}
                Remove-TaskLock $config $first
                [IO.File]::WriteAllText('{lock_path.as_posix()}','stale')
                try {{ Enter-TaskLock $config;exit 8 }} catch {{ $stale=$_.Exception.Message }}
                Remove-Item -LiteralPath '{lock_path.as_posix()}' -Force
                Write-Output ($collision+','+$stale)
                """
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                result.stdout.count("Task launcher lock already exists"), 2
            )

    def test_conflicting_options_fail_before_action_dispatch(self):
        source = LAUNCHER.read_text(encoding="utf-8")
        for contract in (
            "Read-only action received conflicting options",
            "Routine action cannot receive private approval",
            "Session preservation applies only to install",
            "Public health applies only to health",
            "Evidence retention applies only to cleanup",
            "Owner-private action received conflicting options",
        ):
            self.assertIn(contract, source)

    def test_private_agent_path_stops_before_secret_retrieval(self):
        result = self.run_harness(
            """
            $script:called=$false
            function Invoke-BoundedProcess { $script:called=$true; throw 'secret retrieval must not run' }
            $config=[pscustomobject]@{gcloud_executable='E:/mock/gcloud.cmd';python_executable='E:/mock/python.exe'}
            try { Invoke-PrivateAction $config 'private-inspect' 'C:/private/approval.json' '20f393778a9010ac52ad9c8935f3992d72ce06a0'; exit 9 } catch { Write-Output ($_.Exception.Message+',called='+$script:called) }
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("OWNER_ACTION_REQUIRED,called=False", result.stdout)
        self.assert_safe_output(result)

    def test_private_confirmation_child_environment_redaction_and_finally_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            approval = Path(directory) / "approval.json"
            approval.write_text(json.dumps(candidate_approval()), encoding="utf-8")
            result = self.run_harness(
                f"""
                $script:prompt=0;$script:captured=$null;$script:gcloudCalls=0;$script:operatorCalls=@()
                function Test-OwnerInteractiveConsole {{ return $true }}
                function Read-Host {{
                    param([string]$Prompt,[switch]$AsSecureString)
                    $script:prompt++
                    if($AsSecureString){{return (ConvertTo-SecureString '{SENSITIVE_SENTINELS[1]}' -AsPlainText -Force)}}
                    return 'GRANT-OFFICER'
                }}
                function Invoke-BoundedProcess {{
                    param($Executable,$Arguments,$TimeoutSeconds,$ChildEnvironment,$WorkingDirectory)
                    if(($Arguments -join ' ') -match 'secrets versions access'){{
                        $script:gcloudCalls++;return [pscustomobject]@{{TimedOut=$false;ExitCode=0;Stdout='{SENSITIVE_SENTINELS[0]}';Stderr=''}}
                    }}
                    $flag=$Arguments[-1];$script:operatorCalls += $flag;$script:captured=$ChildEnvironment
                    $state=if($flag -eq '--inspect-officer' -and $script:operatorCalls.Count -eq 1){{'baseline'}}else{{'granted'}}
                    return [pscustomobject]@{{TimedOut=$false;ExitCode=0;Stdout=('{{"state":"'+$state+'"}}');Stderr=''}}
                }}
                function Resolve-PrivateExecutable {{ param($Name) return '{LAUNCHER.as_posix()}' }}
                $config=[pscustomobject]@{{snapshot_root='{ROOT.as_posix()}'}}
                $value=Invoke-PrivateAction $config 'grant-officer' '{approval.as_posix()}' '{FULL_SHA}'
                Write-Output ($value.action+','+$value.state+',changed='+$value.changed+',gcloud='+$script:gcloudCalls+',childCleared='+($script:captured.Count -eq 0)+',calls='+($script:operatorCalls -join '|'))
                Write-Output ('parentDsn='+[string]::IsNullOrEmpty($env:MOBILE_STAGING_DATABASE_URL)+',parentSubject='+[string]::IsNullOrEmpty($env:MOBILE_STAGING_PROVIDER_SUBJECT))
                """
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(
                "grant-officer,granted,changed=True,gcloud=1,childCleared=True",
                result.stdout,
            )
            self.assertIn(
                "calls=--inspect-officer|--grant-officer|--inspect-officer",
                result.stdout,
            )
            self.assertIn("parentDsn=True,parentSubject=True", result.stdout)
            self.assert_safe_output(result)

    def test_wrong_private_confirmation_never_retrieves_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            approval = Path(directory) / "approval.json"
            approval.write_text(json.dumps(candidate_approval()), encoding="utf-8")
            result = self.run_harness(
                f"""
                $script:mutationCalled=$false
                function Test-OwnerInteractiveConsole {{ return $true }}
                function Read-Host {{ param($Prompt,[switch]$AsSecureString); if($AsSecureString){{return ConvertTo-SecureString 'fake-subject' -AsPlainText -Force}}; return 'wrong-confirmation' }}
                function Resolve-PrivateExecutable {{ param($Name) return '{LAUNCHER.as_posix()}' }}
                function Invoke-BoundedProcess {{
                    param($Executable,$Arguments,$TimeoutSeconds,$ChildEnvironment,$WorkingDirectory)
                    $flag=$Arguments[-1]
                    if(($Arguments -join ' ') -match 'secrets versions access'){{return [pscustomobject]@{{TimedOut=$false;ExitCode=0;Stdout='fake-dsn';Stderr=''}}}}
                    if($flag -ne '--inspect-officer'){{$script:mutationCalled=$true}}
                    return [pscustomobject]@{{TimedOut=$false;ExitCode=0;Stdout='{{"state":"granted"}}';Stderr=''}}
                }}
                $config=[pscustomobject]@{{snapshot_root='{ROOT.as_posix()}'}}
                try {{ Invoke-PrivateAction $config 'restore-basic' '{approval.as_posix()}' '{FULL_SHA}'; exit 9 }} catch {{ Write-Output ($_.Exception.Message+',mutationCalled='+$script:mutationCalled) }}
                """
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(
                "Owner confirmation did not match,mutationCalled=False", result.stdout
            )
            self.assert_safe_output(result)

    def test_private_mutation_interruption_only_reconciles_read_only_once(self):
        with tempfile.TemporaryDirectory() as directory:
            approval = Path(directory) / "approval.json"
            approval.write_text(json.dumps(candidate_approval()), encoding="utf-8")
            result = self.run_harness(
                f"""
                $script:calls=@();$script:captured=$null
                function Test-OwnerInteractiveConsole {{ return $true }}
                function Read-Host {{ param($Prompt,[switch]$AsSecureString);if($AsSecureString){{return ConvertTo-SecureString 'fake-subject' -AsPlainText -Force}};return 'GRANT-OFFICER' }}
                function Resolve-PrivateExecutable {{ param($Name) return '{LAUNCHER.as_posix()}' }}
                function Invoke-BoundedProcess {{
                    param($Executable,$Arguments,$TimeoutSeconds,$ChildEnvironment,$WorkingDirectory)
                    if(($Arguments -join ' ') -match 'secrets versions access'){{return [pscustomobject]@{{TimedOut=$false;ExitCode=0;Stdout='fake-dsn';Stderr=''}}}}
                    $flag=$Arguments[-1];$script:calls += $flag;$script:captured=$ChildEnvironment
                    if($flag -eq '--grant-officer'){{throw 'simulated interruption'}}
                    $state=if($script:calls.Count -eq 1){{'baseline'}}else{{'granted'}}
                    return [pscustomobject]@{{TimedOut=$false;ExitCode=0;Stdout=('{{"state":"'+$state+'"}}');Stderr=''}}
                }}
                $config=[pscustomobject]@{{snapshot_root='{ROOT.as_posix()}'}}
                $value=Invoke-PrivateAction $config 'grant-officer' '{approval.as_posix()}' '{FULL_SHA}'
                Write-Output ($value.result+',attempts='+$value.mutation_attempts+',calls='+($script:calls -join '|')+',cleared='+($script:captured.Count -eq 0))
                """
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("reconciled,attempts=1", result.stdout)
            self.assertIn(
                "calls=--inspect-officer|--grant-officer|--inspect-officer|--inspect-officer",
                result.stdout,
            )
            self.assertIn("cleared=True", result.stdout)
            self.assert_safe_output(result)

    def test_private_dispatcher_lock_blocks_before_secret_and_cleans_on_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            temp_root = Path(directory) / "task-temp"
            lock_path = Path(str(temp_root) + ".lock")
            result = self.run_harness(
                f"""
                $script:TaskTempRoot='{temp_root.as_posix()}'
                $script:privateCalls=0
                function Test-OwnerInteractiveConsole {{ return $true }}
                function Load-LauncherConfig {{ return [pscustomobject]@{{temp_root='{temp_root.as_posix()}';snapshot_root='{ROOT.as_posix()}'}} }}
                function Assert-Snapshot {{ param($Config,$ExpectedCommit) }}
                function Invoke-PrivateAction {{ $script:privateCalls++;throw 'private child interruption' }}
                $config=[pscustomobject]@{{temp_root='{temp_root.as_posix()}'}}
                $held=Enter-TaskLock $config
                try {{ Invoke-MobileStagingMain 'private-inspect' 'staging' '{FULL_SHA}' 'E:/config.json' 'C:/private/approval.json' $false $false $false;exit 9 }} catch {{ $blocked=$_.Exception.Message }}
                $during=$script:privateCalls
                Remove-TaskLock $config $held
                [IO.File]::WriteAllText('{lock_path.as_posix()}','stale')
                try {{ Invoke-MobileStagingMain 'private-inspect' 'staging' '{FULL_SHA}' 'E:/config.json' 'C:/private/approval.json' $false $false $false;exit 7 }} catch {{ $stale=$_.Exception.Message }}
                $duringStale=$script:privateCalls
                Remove-Item -LiteralPath '{lock_path.as_posix()}' -Force
                try {{ Invoke-MobileStagingMain 'private-inspect' 'staging' '{FULL_SHA}' 'E:/config.json' 'C:/private/approval.json' $false $false $false;exit 8 }} catch {{ $failed=$_.Exception.Message }}
                Write-Output ($blocked+',privateCallsDuringLock='+$during+',stale='+$stale+',privateCallsDuringStale='+$duringStale+',failure='+$failed+',lockAfterFailure='+(Test-Path '{lock_path.as_posix()}'))
                """
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Task launcher lock already exists", result.stdout)
            self.assertIn("privateCallsDuringLock=0", result.stdout)
            self.assertIn("stale=Task launcher lock already exists", result.stdout)
            self.assertIn("privateCallsDuringStale=0", result.stdout)
            self.assertIn("failure=private child interruption", result.stdout)
            self.assertIn("lockAfterFailure=False", result.stdout)

    def test_source_forbids_destructive_or_global_cleanup_commands(self):
        source = LAUNCHER.read_text(encoding="utf-8").lower()
        for forbidden in (
            "adb uninstall",
            "pm clear",
            "install -d",
            "avdmanager create",
            "-wipe-data",
            "keytool -genkey",
            "copy-item",
            "mklink",
            "-itemtype junction",
            "-itemtype symboliclink",
            "get-process",
            "stop-process",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("'install', '-r'", source)
        self.assertNotRegex(source, r"remove-item[^\n]*(gradle_user_home|pub_cache)")
        self.assertIn("finally", source)


def candidate_approval():
    return {
        "owner_approved": True,
        "project": "ntubtob-mobile-stage",
        "region": "asia-east1",
        "service": "mobile-api-staging",
        "approved_commit": FULL_SHA,
        "approval_phase": "candidate",
        "build_id": "build-task123",
        "image_uri": "asia-east1-docker.pkg.dev/ntubtob-mobile-stage/mobile/mobile-api",
        "image_digest": "sha256:" + "a" * 64,
        "mode": "update",
        "candidate_revision": "mobile-api-staging-task123",
        "rollback_revision": "mobile-api-staging-task122",
        "database_identity_sha256": "b" * 64,
        "production_database_identity_sha256": "c" * 64,
        "database_provider": "supabase",
        "database_resource_id": "project/task123-staging",
        "database_alias": "task123",
        "max_instances": 1,
        "service_account": "mobile-runtime@ntubtob-mobile-stage.iam.gserviceaccount.com",
        "build_service_account": "mobile-build@ntubtob-mobile-stage.iam.gserviceaccount.com",
        "runtime_secret_refs": {
            "PORTAL_DATA_DATABASE_URL": "mobile-api-staging-db:4",
            "MOBILE_ACCESS_SIGNING_KEY": "mobile-api-staging-access:1",
            "MOBILE_REFRESH_REPLAY_KEY": "mobile-api-staging-refresh:1",
        },
        "mobile_api_audience": "1234567890123456789",
        "mobile_api_google_audiences": "staging-web.apps.googleusercontent.com",
    }


def launcher_config():
    return {
        "schema_version": 1,
        "snapshot_root": r"E:\task-123\snapshot",
        "flutter_executable": r"E:\flutter\bin\flutter.bat",
        "git_executable": r"C:\Program Files\Git\cmd\git.exe",
        "adb_executable": r"E:\android\platform-tools\adb.exe",
        "emulator_executable": r"E:\android\emulator\emulator.exe",
        "apksigner_executable": r"E:\android\build-tools\apksigner.bat",
        "apkanalyzer_executable": r"E:\android\cmdline-tools\latest\bin\apkanalyzer.bat",
        "keytool_executable": r"E:\jdk\bin\keytool.exe",
        "android_sdk_root": r"E:\android",
        "java_home": r"E:\jdk",
        "android_user_homes": [r"E:\task-123\android-user"],
        "android_avd_home": r"E:\task-123\avd",
        "pub_cache": r"E:\task-123\pub-cache",
        "gradle_user_home": r"E:\task-123\gradle",
        "avd_name": "task123_avd",
        "serial": "emulator-5556",
        "package_id": "tw.org.ntubtob.portal",
        "main_activity": "tw.org.ntubtob.portal/.MainActivity",
        "evidence_root": r"E:\codex-evidence\task-123",
        "temp_root": r"E:\codex-temp\task-123",
        "min_free_bytes": 1073741824,
        "signer_allowlist": [FINGERPRINT],
        "artifact_relative_path": "app-debug.apk",
    }


if __name__ == "__main__":
    unittest.main()
