from __future__ import annotations

import json
import os
import subprocess
import tempfile
import textwrap
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / "tools" / "Invoke-MobileStagingBroker.ps1"
FULL_SHA = "a" * 40
IMAGE_DIGEST = "sha256:" + "b" * 64


def powershell_available() -> bool:
    return bool(os.environ.get("SystemRoot")) and (
        Path(os.environ["SystemRoot"])
        / "System32"
        / "WindowsPowerShell"
        / "v1.0"
        / "powershell.exe"
    ).is_file()


@unittest.skipUnless(powershell_available(), "Windows PowerShell is unavailable")
class MobileStagingBrokerClientTest(unittest.TestCase):
    maxDiff = None

    def run_script(self, body: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.ps1"
            path.write_text(
                "$ErrorActionPreference='Stop'\n"
                f". '{CLIENT.as_posix()}'\n"
                + textwrap.dedent(body),
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
                    str(path),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )

    def run_http_case(
        self,
        response_code: int,
        response_body: bytes,
        redirect: bool = False,
        include_content_length: bool = True,
        body_delay_seconds: float = 0,
        deadline_milliseconds: int | None = None,
    ):
        calls: list[str] = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802 - standard-library callback name
                calls.append(self.path)
                self.send_response(response_code)
                if redirect:
                    self.send_header("Location", "/redirected")
                if include_content_length:
                    self.send_header("Content-Length", str(len(response_body)))
                else:
                    self.send_header("Connection", "close")
                self.end_headers()
                if body_delay_seconds:
                    time.sleep(body_delay_seconds)
                try:
                    self.wfile.write(response_body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, _format, *_args):
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        deadline_override = ""
        if deadline_milliseconds is not None:
            deadline_override = (
                "function New-BrokerHttpDeadline { "
                "$value=[Threading.CancellationTokenSource]::new();"
                f"$value.CancelAfter({deadline_milliseconds});return $value }}"
            )
        try:
            result = self.run_script(
                f"""
                {deadline_override}
                try {{
                    $value=Invoke-BrokerHttp 'http://127.0.0.1:{server.server_port}' ('t'*64) 'grant' 'operation-123456'
                    [pscustomobject]@{{status=$value.StatusCode}}|ConvertTo-Json -Compress
                }} catch {{ Write-Output 'HTTP_REJECTED' }}
                """
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        return result, calls

    def test_parser_and_source_have_no_private_payload_interface(self):
        parser = subprocess.run(
            [
                "powershell.exe",
                "-NoLogo",
                "-NoProfile",
                "-Command",
                "$e=$null;$t=$null;"
                f"[Management.Automation.Language.Parser]::ParseFile('{CLIENT.as_posix()}',[ref]$t,[ref]$e)|Out-Null;"
                "if($e.Count){$e|%{$_.Message};exit 1}",
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(parser.returncode, 0, parser.stdout + parser.stderr)
        source = CLIENT.read_text(encoding="utf-8")
        for forbidden in (
            "MOBILE_STAGING_DATABASE_URL",
            "MOBILE_STAGING_PROVIDER_SUBJECT",
            "Read-Host",
            "--secret=",
            "access_secret_version",
        ):
            self.assertNotIn(forbidden, source)

    def test_unprovisioned_stops_before_any_external_call(self):
        result = self.run_script(
            """
            function Load-BrokerClientConfig { return [pscustomobject]@{ provisioned=$false } }
            function Invoke-BrokerExternalProcess { throw 'external-sentinel' }
            $value=Invoke-MobileStagingBrokerMain 'status' '' 'E:/broker.json'
            $value|ConvertTo-Json -Depth 5 -Compress
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["classification"], "OWNER_ACTION_REQUIRED")
        self.assertEqual(payload["details"]["reason_code"], "BROKER_PROVISIONING")
        self.assertNotIn("sentinel", result.stdout + result.stderr)

    def test_exact_metadata_then_one_operation_request(self):
        result = self.run_script(
            f"""
            $script:external=0;$script:http=0;$script:token='token-private-sentinel-value-1234567890'
            function Load-BrokerClientConfig {{ return [pscustomobject]@{{
                provisioned=$true;project='ntubtob-mobile-staging';region='asia-east1';service='mobile-staging-broker';operator_account='owner@example.com';
                caller_identity='broker-caller@ntubtob-mobile-staging.iam.gserviceaccount.com';
                runtime_identity='broker-runtime@ntubtob-mobile-staging.iam.gserviceaccount.com';
                image_digest='{IMAGE_DIGEST}';gcloud_executable='E:/safe/gcloud.cmd';lock_path='E:/task-134/broker.lock'
            }} }}
            function Enter-BrokerClientLock {{ return [pscustomobject]@{{owned=$true}} }}
            function Remove-BrokerClientLock {{ param($c,$l) return $true }}
            function Invoke-BrokerExternalProcess {{ param($file,$arguments,$timeout)
                $script:external++
                if($arguments[0] -ceq 'config'){{return [pscustomobject]@{{TimedOut=$false;ExitCode=0;Stdout='owner@example.com';Stderr=''}}}}
                if($arguments[0] -ceq 'run' -and $arguments[1] -ceq 'services'){{return [pscustomobject]@{{TimedOut=$false;ExitCode=0;Stdout='{{"metadata":{{"annotations":{{"run.googleapis.com/ingress":"all"}}}},"spec":{{"template":{{"metadata":{{"annotations":{{"autoscaling.knative.dev/maxScale":"1"}}}},"spec":{{"serviceAccountName":"broker-runtime@ntubtob-mobile-staging.iam.gserviceaccount.com","containerConcurrency":1,"containers":[{{"image":"x@{IMAGE_DIGEST}"}}]}}}}}},"status":{{"url":"https://mobile-staging-broker-abc-de.a.run.app","latestReadyRevisionName":"revision-1","traffic":[{{"revisionName":"revision-1","percent":100}}],"conditions":[{{"type":"Ready","status":"True"}}]}}}}';Stderr=''}}}}
                if($arguments[0] -ceq 'run' -and $arguments[1] -ceq 'services' -and $arguments[2] -ceq 'get-iam-policy'){{throw 'unreachable'}}
                if($arguments[0] -ceq 'auth'){{return [pscustomobject]@{{TimedOut=$false;ExitCode=0;Stdout=$script:token;Stderr=''}}}}
                throw 'unexpected external call'
            }}
            function Get-BrokerIamState {{ param($config) return 'private_exact' }}
            function Invoke-BrokerIdentityTokenExchange {{ param($access,$caller,$audience) return ('{{"token":"'+$script:token+'"}}') }}
            function Invoke-BrokerHttp {{ param($uri,$token,$operation,$operationId)
                $script:http++; if($token -cne $script:token){{throw 'token mismatch'}}
                return [pscustomobject]@{{StatusCode=200;Body='{{"classification":"PASS","lifecycle_state":"postcheck_complete","operation":"grant","operation_id":"operation-123456","reason_code":"NONE","target_state":"ready_officer"}}'
                }}
            }}
            $value=Invoke-MobileStagingBrokerMain 'grant' 'operation-123456' 'E:/broker.json'
            [pscustomobject]@{{value=$value;external=$script:external;http=$script:http}}|ConvertTo-Json -Depth 6 -Compress
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["value"]["classification"], "PASS", payload)
        self.assertEqual(payload["value"]["details"]["state"], "ready_officer")
        self.assertEqual(payload["http"], 1)
        self.assertNotIn("token-private-sentinel", result.stdout + result.stderr)
        self.assertNotIn("private.invalid", result.stdout + result.stderr)

    def test_runtime_identity_image_traffic_readiness_and_shape_drift(self):
        base = {
            "metadata": {"annotations": {"run.googleapis.com/ingress": "all"}},
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {"autoscaling.knative.dev/maxScale": "1"}
                    },
                    "spec": {
                        "serviceAccountName": "broker-runtime@ntubtob-mobile-staging.iam.gserviceaccount.com",
                        "containerConcurrency": 1,
                        "containers": [{"image": "x@" + IMAGE_DIGEST}],
                    },
                }
            },
            "status": {
                "url": "https://mobile-staging-broker-abc-de.a.run.app",
                "latestReadyRevisionName": "revision-1",
                "traffic": [{"revisionName": "revision-1", "percent": 100}],
                "conditions": [{"type": "Ready", "status": "True"}],
            },
        }
        variants = []
        for name in ("runtime", "image", "traffic", "ready"):
            value = json.loads(json.dumps(base))
            if name == "runtime":
                value["spec"]["template"]["spec"]["serviceAccountName"] = (
                    "other-sentinel@ntubtob-mobile-staging.iam.gserviceaccount.com"
                )
            elif name == "image":
                value["spec"]["template"]["spec"]["containers"][0]["image"] = (
                    "x@sha256:" + "d" * 64
                )
            elif name == "traffic":
                value["status"]["traffic"][0]["percent"] = 50
            else:
                value["status"]["conditions"][0]["status"] = "False"
            variants.append((name, json.dumps(value, separators=(",", ":"))))
        variants.append(("malformed", "{}"))
        for name, metadata in variants:
            with self.subTest(name=name):
                escaped = metadata.replace("'", "''")
                result = self.run_script(
                    f"""
                    function Invoke-BrokerExternalProcess {{ param($file,$arguments,$timeout)
                        if($arguments[0] -ceq 'config'){{return [pscustomobject]@{{TimedOut=$false;ExitCode=0;Stdout='owner@example.com';Stderr=''}}}}
                        return [pscustomobject]@{{TimedOut=$false;ExitCode=0;Stdout='{escaped}';Stderr=''}}
                    }}
                    function Get-BrokerIamState {{ return 'private_exact' }}
                    $config=[pscustomobject]@{{gcloud_executable='C:/safe/gcloud.cmd';project='ntubtob-mobile-staging';region='asia-east1';service='mobile-staging-broker';operator_account='owner@example.com';runtime_identity='broker-runtime@ntubtob-mobile-staging.iam.gserviceaccount.com';image_digest='{IMAGE_DIGEST}'}}
                    try {{ Get-BrokerRuntimeBinding $config|Out-Null;exit 9 }}
                    catch {{ Write-Output 'METADATA_REJECTED' }}
                    """
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), "METADATA_REJECTED")
                self.assertNotIn("sentinel", result.stdout + result.stderr)

    def test_unknown_http_result_is_not_retried_or_disclosed(self):
        result = self.run_script(
            f"""
            $script:http=0
            function Load-BrokerClientConfig {{ return [pscustomobject]@{{provisioned=$true;project='ntubtob-mobile-staging';region='asia-east1';service='mobile-staging-broker';operator_account='owner@example.com';caller_identity='broker-caller@ntubtob-mobile-staging.iam.gserviceaccount.com';runtime_identity='broker-runtime@ntubtob-mobile-staging.iam.gserviceaccount.com';image_digest='{IMAGE_DIGEST}';gcloud_executable='E:/safe/gcloud.cmd';lock_path='E:/task-134/broker.lock'}} }}
            function Enter-BrokerClientLock {{ return @{{owned=$true}} }}
            function Remove-BrokerClientLock {{ param($c,$l) return $true }}
            function Get-BrokerRuntimeBinding {{ return @{{uri='https://private-sentinel.invalid'}} }}
            function Get-BrokerIdentityToken {{ return 'token-private-sentinel' }}
            function Invoke-BrokerHttp {{ $script:http++; throw 'raw-network-sentinel' }}
            $value=Invoke-MobileStagingBrokerMain 'grant' 'operation-123456' 'E:/broker.json'
            [pscustomobject]@{{value=$value;http=$script:http}}|ConvertTo-Json -Depth 6 -Compress
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["value"]["classification"], "FAILED")
        self.assertEqual(payload["value"]["details"]["reason_code"], "BROKER_RESULT_UNKNOWN")
        self.assertEqual(payload["http"], 1)
        for sentinel in ("raw-network-sentinel", "token-private-sentinel", "private-sentinel"):
            self.assertNotIn(sentinel, result.stdout + result.stderr)

    def test_identity_token_exchange_keeps_audience_out_of_gcloud_argv(self):
        result = self.run_script(
            """
            $script:captured=@();$script:exchange=@()
            function Invoke-BrokerExternalProcess { param($file,$arguments,$timeout)
                $script:captured=@($arguments)
                return [pscustomobject]@{TimedOut=$false;ExitCode=0;Stdout=('a'*64);Stderr=''}
            }
            function Invoke-BrokerIdentityTokenExchange { param($access,$caller,$audience)
                $script:exchange=@($access.Length,$caller,$audience)
                return ('{"token":"'+('t'*64)+'"}')
            }
            $config=[pscustomobject]@{gcloud_executable='E:/safe/gcloud.cmd';caller_identity='broker-caller@ntubtob-mobile-staging.iam.gserviceaccount.com'}
            $token=Get-BrokerIdentityToken $config 'https://mobile-staging-broker-123.asia-east1.run.app'
            [pscustomobject]@{length=$token.Length;arguments=$script:captured;exchange=@($script:exchange[0],$script:exchange[1])}|ConvertTo-Json -Depth 3 -Compress
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["length"], 64)
        self.assertEqual(payload["arguments"], ["auth", "print-access-token", "--quiet"])
        self.assertEqual(payload["exchange"][0], 64)
        self.assertEqual(payload["exchange"][1], "broker-caller@ntubtob-mobile-staging.iam.gserviceaccount.com")
        self.assertNotIn("t" * 32, result.stdout + result.stderr)
        self.assertNotIn("mobile-staging-broker-123", json.dumps(payload["arguments"]))

    def test_known_broker_failure_is_bounded_without_operation_id_echo(self):
        result = self.run_script(
            """
            $response=[pscustomobject]@{StatusCode=503;Body='{"classification":"FAILED","lifecycle_state":"unchanged","operation":"none","operation_id":"none","reason_code":"RECONCILE_REQUIRED","target_state":"none"}'}
            $value=ConvertFrom-BrokerResponse $response 'reconcile' 'opaque-operation-1234'
            $value|ConvertTo-Json -Compress
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["Classification"], "FAILED")
        self.assertEqual(payload["ReasonCode"], "RECONCILE_REQUIRED")
        self.assertNotIn("opaque-operation", result.stdout + result.stderr)

    def test_lock_failure_precedes_binding_token_and_http(self):
        result = self.run_script(
            f"""
            $script:binding=0;$script:token=0;$script:http=0
            function Load-BrokerClientConfig {{ return [pscustomobject]@{{provisioned=$true;project='ntubtob-mobile-staging';region='asia-east1';service='mobile-staging-broker';operator_account='owner@example.com';caller_identity='broker-caller@ntubtob-mobile-staging.iam.gserviceaccount.com';runtime_identity='broker-runtime@ntubtob-mobile-staging.iam.gserviceaccount.com';image_digest='{IMAGE_DIGEST}';gcloud_executable='E:/safe/gcloud.cmd';lock_path='E:/task-134/broker.lock'}} }}
            function Enter-BrokerClientLock {{ throw 'Broker task lock is unavailable' }}
            function Get-BrokerRuntimeBinding {{ $script:binding++;throw 'binding-sentinel' }}
            function Get-BrokerIdentityToken {{ $script:token++;throw 'token-sentinel' }}
            function Invoke-BrokerHttp {{ $script:http++;throw 'http-sentinel' }}
            $value=Invoke-MobileStagingBrokerMain 'grant' 'operation-123456' 'E:/broker.json'
            [pscustomobject]@{{value=$value;binding=$script:binding;token=$script:token;http=$script:http}}|ConvertTo-Json -Depth 5 -Compress
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["value"]["classification"], "DRIFT")
        self.assertEqual((payload["binding"], payload["token"], payload["http"]), (0, 0, 0))
        self.assertNotIn("sentinel", result.stdout + result.stderr)

    def test_partial_lock_acquisition_removes_created_file_without_disclosure(self):
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / "broker.lock"
            result = self.run_script(
                f"""
                function Write-BrokerClientLockMarker {{ throw 'partial-lock-path-sentinel' }}
                $config=[pscustomobject]@{{lock_path='{lock.as_posix()}'}}
                try {{ Enter-BrokerClientLock $config|Out-Null;exit 9 }}
                catch {{ [pscustomobject]@{{rejected=$true;exists=(Test-Path -LiteralPath '{lock.as_posix()}')}}|ConvertTo-Json -Compress }}
                """
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["rejected"])
        self.assertFalse(payload["exists"])
        self.assertNotIn("sentinel", result.stdout + result.stderr)

    def test_handled_operation_failure_still_cleans_lock(self):
        result = self.run_script(
            f"""
            $script:cleanup=0
            function Load-BrokerClientConfig {{ return [pscustomobject]@{{provisioned=$true;project='ntubtob-mobile-staging';region='asia-east1';service='mobile-staging-broker';operator_account='owner@example.com';caller_identity='broker-caller@ntubtob-mobile-staging.iam.gserviceaccount.com';runtime_identity='broker-runtime@ntubtob-mobile-staging.iam.gserviceaccount.com';image_digest='{IMAGE_DIGEST}';gcloud_executable='E:/safe/gcloud.cmd';gcloud_sha256=('c'*64);lock_path='E:/codex-evidence/task-134/broker.lock'}} }}
            function Enter-BrokerClientLock {{ return @{{owned=$true}} }}
            function Remove-BrokerClientLock {{ $script:cleanup++;return $true }}
            function Get-BrokerRuntimeBinding {{ throw 'operation-failure-sentinel' }}
            $value=Invoke-MobileStagingBrokerMain 'status' '' 'E:/broker.json'
            [pscustomobject]@{{value=$value;cleanup=$script:cleanup}}|ConvertTo-Json -Depth 5 -Compress
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["value"]["classification"], "FAILED")
        self.assertEqual(payload["cleanup"], 1)
        self.assertNotIn("sentinel", result.stdout + result.stderr)

    def test_malformed_response_and_raw_sentinels_fail_closed(self):
        for body in (
            "raw-response-sentinel",
            "{}",
            '{"classification":"PASS","lifecycle_state":"postcheck_complete","operation":"grant","operation_id":"wrong-operation-1234","reason_code":"NONE","target_state":"ready_officer"}',
        ):
            with self.subTest(body=body):
                escaped = body.replace("'", "''")
                result = self.run_script(
                    f"""
                    try {{
                        $response=[pscustomobject]@{{StatusCode=200;Body='{escaped}'}}
                        ConvertFrom-BrokerResponse $response 'grant' 'operation-123456'|Out-Null
                        exit 9
                    }} catch {{ Write-Output 'fixed-failure' }}
                    """
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), "fixed-failure")
                self.assertNotIn("sentinel", result.stdout + result.stderr)

    def test_safe_json_rejects_endpoint_or_token_without_echo(self):
        result = self.run_script(
            """
            try { Write-BrokerClientJson @{result='https://private.invalid';token='token-private-sentinel'};exit 9 }
            catch { Write-Output 'OUTPUT_REDACTION_FAILED' }
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "OUTPUT_REDACTION_FAILED")
        self.assertNotIn("private.invalid", result.stdout + result.stderr)
        self.assertNotIn("token-private", result.stdout + result.stderr)

    def test_token_timeout_is_terminal_and_http_is_not_called(self):
        result = self.run_script(
            f"""
            $script:http=0
            function Load-BrokerClientConfig {{ return [pscustomobject]@{{provisioned=$true;project='ntubtob-mobile-staging';region='asia-east1';service='mobile-staging-broker';operator_account='owner@example.com';caller_identity='broker-caller@ntubtob-mobile-staging.iam.gserviceaccount.com';runtime_identity='broker-runtime@ntubtob-mobile-staging.iam.gserviceaccount.com';image_digest='{IMAGE_DIGEST}';gcloud_executable='E:/safe/gcloud.cmd';lock_path='E:/task-134/broker.lock'}} }}
            function Enter-BrokerClientLock {{ return @{{owned=$true}} }}
            function Remove-BrokerClientLock {{ param($c,$l) return $true }}
            function Get-BrokerRuntimeBinding {{ return @{{uri='https://private-sentinel.invalid'}} }}
            function Get-BrokerIdentityToken {{ throw 'Broker external process timed out' }}
            function Invoke-BrokerHttp {{ $script:http++;throw 'must-not-run-sentinel' }}
            $value=Invoke-MobileStagingBrokerMain 'grant' 'operation-123456' 'E:/broker.json'
            [pscustomobject]@{{value=$value;http=$script:http}}|ConvertTo-Json -Depth 5 -Compress
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["value"]["classification"], "TIMEOUT")
        self.assertEqual(payload["value"]["details"]["reason_code"], "BROKER_TIMEOUT")
        self.assertEqual(payload["http"], 0)
        self.assertNotIn("sentinel", result.stdout + result.stderr)

    def test_config_rejects_extra_secret_reference_field(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "broker.json"
            config.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "provisioned": False,
                        "project": "ntubtob-mobile-staging",
                        "region": "asia-east1",
                        "service": "mobile-staging-broker",
                        "operator_account": "owner@example.com",
                        "caller_identity": "broker-caller@ntubtob-mobile-staging.iam.gserviceaccount.com",
                        "runtime_identity": "broker-runtime@ntubtob-mobile-staging.iam.gserviceaccount.com",
                        "image_digest": IMAGE_DIGEST,
                        "gcloud_executable": "C:/safe/gcloud.cmd",
                        "gcloud_sha256": "c" * 64,
                        "lock_path": "E:/codex-evidence/task-134/broker.lock",
                        "subject_secret_reference": "must-not-be-accepted",
                    }
                ),
                encoding="utf-8",
            )
            result = self.run_script(
                f"""
                function Test-Path {{ return $true }}
                try {{ Load-BrokerClientConfig '{config.as_posix()}'|Out-Null;exit 9 }}
                catch {{ Write-Output 'CONFIG_REJECTED' }}
                """
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "CONFIG_REJECTED")
        self.assertNotIn("must-not-be-accepted", result.stdout + result.stderr)

    def test_config_rejects_same_basename_outside_approved_cloud_sdk_roots(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "broker.json"
            config.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "provisioned": False,
                        "project": "ntubtob-mobile-staging",
                        "region": "asia-east1",
                        "service": "mobile-staging-broker",
                        "operator_account": "owner@example.com",
                        "caller_identity": "broker-caller@ntubtob-mobile-staging.iam.gserviceaccount.com",
                        "runtime_identity": "broker-runtime@ntubtob-mobile-staging.iam.gserviceaccount.com",
                        "image_digest": IMAGE_DIGEST,
                        "gcloud_executable": "C:/attacker/gcloud.cmd",
                        "gcloud_sha256": "c" * 64,
                        "lock_path": "E:/codex-evidence/task-134/broker.lock",
                    }
                ),
                encoding="utf-8",
            )
            result = self.run_script(
                f"""
                function Test-Path {{ return $true }}
                function Get-FileHash {{ return @{{Hash=('c'*64)}} }}
                try {{ Load-BrokerClientConfig '{config.as_posix()}'|Out-Null;exit 9 }}
                catch {{ Write-Output 'CONFIG_REJECTED' }}
                """
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "CONFIG_REJECTED")
        self.assertNotIn("attacker", result.stdout + result.stderr)

    def test_public_iam_is_rejected_without_policy_echo(self):
        result = self.run_script(
            """
            function Invoke-BrokerExternalProcess {
                return [pscustomobject]@{TimedOut=$false;ExitCode=0;Stdout='{"bindings":[{"role":"roles/run.invoker","members":["allUsers","policy-sentinel"]}]}';Stderr=''}
            }
            $config=[pscustomobject]@{gcloud_executable='C:/safe/gcloud.cmd';service='mobile-staging-broker';project='ntubtob-mobile-staging';region='asia-east1';caller_identity='broker-caller@ntubtob-mobile-staging.iam.gserviceaccount.com'}
            try { Get-BrokerIamState $config|Out-Null;exit 9 }
            catch { Write-Output 'IAM_REJECTED' }
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "IAM_REJECTED")
        self.assertNotIn("policy-sentinel", result.stdout + result.stderr)

    def test_additional_invoker_is_rejected(self):
        result = self.run_script(
            """
            function Invoke-BrokerExternalProcess {
                return [pscustomobject]@{TimedOut=$false;ExitCode=0;Stdout='{"bindings":[{"role":"roles/run.invoker","members":["serviceAccount:broker-caller@ntubtob-mobile-staging.iam.gserviceaccount.com","serviceAccount:extra-sentinel@ntubtob-mobile-staging.iam.gserviceaccount.com"]}]}';Stderr=''}
            }
            $config=[pscustomobject]@{gcloud_executable='C:/safe/gcloud.cmd';service='mobile-staging-broker';project='ntubtob-mobile-staging';region='asia-east1';caller_identity='broker-caller@ntubtob-mobile-staging.iam.gserviceaccount.com'}
            try { Get-BrokerIamState $config|Out-Null;exit 9 }
            catch { Write-Output 'IAM_REJECTED' }
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "IAM_REJECTED")
        self.assertNotIn("extra-sentinel", result.stdout + result.stderr)

    def test_conditional_invoker_is_rejected(self):
        result = self.run_script(
            """
            function Invoke-BrokerExternalProcess {
                return [pscustomobject]@{TimedOut=$false;ExitCode=0;Stdout='{"bindings":[{"role":"roles/run.invoker","members":["serviceAccount:broker-caller@ntubtob-mobile-staging.iam.gserviceaccount.com"],"condition":{"title":"conditional-sentinel"}}]}';Stderr=''}
            }
            $config=[pscustomobject]@{gcloud_executable='C:/safe/gcloud.cmd';service='mobile-staging-broker';project='ntubtob-mobile-staging';region='asia-east1';caller_identity='broker-caller@ntubtob-mobile-staging.iam.gserviceaccount.com'}
            try { Get-BrokerIamState $config|Out-Null;exit 9 }
            catch { Write-Output 'IAM_REJECTED' }
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "IAM_REJECTED")
        self.assertNotIn("conditional-sentinel", result.stdout + result.stderr)

    def test_explicit_reconcile_accepts_original_operation_same_id(self):
        result = self.run_script(
            """
            $response=[pscustomobject]@{StatusCode=200;Body='{"classification":"PASS","lifecycle_state":"postcheck_complete","operation":"grant","operation_id":"operation-123456","reason_code":"NONE","target_state":"ready_officer"}'}
            $value=ConvertFrom-BrokerResponse $response 'reconcile' 'operation-123456'
            $value|ConvertTo-Json -Compress
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["Classification"], "PASS")
        self.assertEqual(payload["State"], "ready_officer")
        self.assertNotIn("operation-123456", result.stdout + result.stderr)

    def test_cleanup_failure_replaces_success_with_fixed_failure(self):
        result = self.run_script(
            f"""
            function Load-BrokerClientConfig {{ return [pscustomobject]@{{provisioned=$true;project='ntubtob-mobile-staging';region='asia-east1';service='mobile-staging-broker';operator_account='owner@example.com';caller_identity='broker-caller@ntubtob-mobile-staging.iam.gserviceaccount.com';runtime_identity='broker-runtime@ntubtob-mobile-staging.iam.gserviceaccount.com';image_digest='{IMAGE_DIGEST}';gcloud_executable='E:/safe/gcloud.cmd';gcloud_sha256=('c'*64);lock_path='E:/codex-evidence/task-134/broker.lock'}} }}
            function Enter-BrokerClientLock {{ return @{{owned=$true}} }}
            function Remove-BrokerClientLock {{ throw 'cleanup-path-sentinel' }}
            function Get-BrokerRuntimeBinding {{ return @{{uri='https://private-sentinel.invalid'}} }}
            $value=Invoke-MobileStagingBrokerMain 'status' '' 'E:/broker.json'
            $value|ConvertTo-Json -Depth 5 -Compress
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["classification"], "FAILED")
        self.assertEqual(payload["details"]["reason_code"], "BROKER_LOCK_CLEANUP_FAILED")
        self.assertNotIn("sentinel", result.stdout + result.stderr)

    def test_http_redirect_is_not_followed(self):
        result, calls = self.run_http_case(307, b"redirect", redirect=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual(result.stdout.strip(), "HTTP_REJECTED", result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], 307, result.stdout + result.stderr)
        self.assertEqual(calls, ["/v1/operations"])

    def test_oversized_http_body_is_rejected_without_echo(self):
        result, calls = self.run_http_case(200, b"x" * 5000)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "HTTP_REJECTED")
        self.assertEqual(calls, ["/v1/operations"])
        self.assertNotIn("x" * 100, result.stdout + result.stderr)

    def test_streamed_oversized_http_is_bounded_for_both_transports(self):
        source = CLIENT.read_text(encoding="utf-8")
        for start, end in (
            (
                "function Invoke-BrokerIdentityTokenExchange",
                "function Get-BrokerIdentityToken",
            ),
            ("function Invoke-BrokerHttp", "function ConvertFrom-BrokerResponse"),
        ):
            block = source.split(start, 1)[1].split(end, 1)[0]
            self.assertIn(
                "[Net.Http.HttpCompletionOption]::ResponseHeadersRead",
                block,
            )
            self.assertIn("New-BrokerHttpDeadline", block)
            self.assertGreaterEqual(block.count("$deadline.Token"), 2)
            self.assertEqual(block.count("SendAsync("), 1)
        result, calls = self.run_http_case(
            200,
            b"streamed-sentinel-" * 400,
            include_content_length=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "HTTP_REJECTED")
        self.assertEqual(calls, ["/v1/operations"])
        self.assertNotIn("streamed-sentinel", result.stdout + result.stderr)

    def test_stalled_stream_has_one_deadline_and_no_disclosure(self):
        result, calls = self.run_http_case(
            200,
            b"stalled-body-sentinel",
            include_content_length=False,
            body_delay_seconds=1,
            deadline_milliseconds=150,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "HTTP_REJECTED")
        self.assertEqual(calls, ["/v1/operations"])
        self.assertNotIn("stalled-body-sentinel", result.stdout + result.stderr)

    def test_oversized_external_output_is_rejected_without_echo(self):
        result = self.run_script(
            """
            try {
                Invoke-BrokerExternalProcess (Join-Path $PSHOME 'powershell.exe') @('-NoProfile','-Command','[Console]::Out.Write(([char]0x4E00).ToString()*500)') 15 1024|Out-Null
                exit 9
            } catch { Write-Output 'PROCESS_REJECTED' }
            """
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "PROCESS_REJECTED")
        self.assertNotIn("一" * 20, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
