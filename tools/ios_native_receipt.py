"""Read a completed native signing receipt; GET only, no raw job log output.

gh's escape override is scoped to captured pipes. Only an exact known receipt
can escape this reader. It is not a general log viewer or upload-result parser.
"""

import argparse
import json
import re

from tools import ios_native_secret_setup as setup
from tools.ios_native_upload import unique

SUCCESS = {
    "classification": "SIGNED_BASELINE_VERIFIED",
    "failure": None,
    "cleanup_failures": [],
    "signature_verified": True,
    "cleanup_verified": True,
    "upload_attempted": False,
    "device_verified": False,
    "release_authorized": False,
    "next_action": "REVIEW_UPLOAD_STAGE",
}
AUDIT = {"stage": "cleanup_audit", "classification": "ABSENT"}


class Rejected(Exception):
    def __init__(self, stage, reason):
        super().__init__("native receipt unavailable")
        self.stage, self.reason = stage, reason


def check(ok, stage, reason):
    if not ok:
        raise Rejected(stage, reason)


def exact(value, expected):
    # Python True == 1 must not make wrong JSON types look like a verified fact.
    return type(value) is dict and json.dumps(value, sort_keys=True) == json.dumps(
        expected, sort_keys=True
    )


def parse(raw):
    check(
        type(raw) is bytes and 0 < len(raw) <= 1048576, "receipt", "LOG_SIZE_REJECTED"
    )
    success = audit = 0
    for line in raw.splitlines():
        line = re.sub(rb"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+Z ", b"", line)
        if not line.startswith(b"{"):
            continue
        check(len(line) <= 4096, "receipt", "JSON_RECORD_TOO_LARGE")
        try:
            value = json.loads(line, object_pairs_hook=unique)
        except (ValueError, UnicodeError):
            raise Rejected("receipt", "MALFORMED_RECEIPT") from None
        if type(value) is dict and (
            "signature_verified" in value
            or value.get("classification") in {"STOP", SUCCESS["classification"]}
            or ("classification" in value and "stage" not in value)
        ):
            check(exact(value, SUCCESS), "receipt", "CONTRADICTORY_RECEIPT")
        if type(value) is dict and value.get("stage") == "cleanup_audit":
            check(exact(value, AUDIT), "receipt", "CONTRADICTORY_AUDIT")
        success += exact(value, SUCCESS)
        audit += exact(value, AUDIT)
    check(success == 1 and audit == 1, "receipt", "EXACT_RECEIPT_NOT_FOUND")
    return dict(SUCCESS)


def read(run_id, job_id, sha, *, run=setup.command):
    result = {
        "classification": "STOP",
        "failure": None,
        "cleanup_failure": None,
        "next_action": "READ_ONLY_REVIEW",
        "mutation_count": 0,
    }
    stage = "input"
    try:
        check(
            type(run_id) is int
            and type(job_id) is int
            and run_id > 0
            and job_id > 0
            and type(sha) is str
            and re.fullmatch(r"[a-f0-9]{40}", sha),
            stage,
            "INPUT_REJECTED",
        )
        api = f"repos/{setup.REPO}/actions"
        stage = "run_binding"
        value = setup.api(run, stage, f"{api}/runs/{run_id}")
        check(
            type(value) is dict
            and type(value.get("id")) is int
            and value.get("id") == run_id
            and value.get("head_sha") == sha
            and value.get("head_branch") == "main"
            and value.get("event") == "workflow_dispatch"
            and type(value.get("run_attempt")) is int
            and value["run_attempt"] == 1
            and value.get("path") == ".github/workflows/ios-native-signing.yml"
            and value.get("status") == "completed"
            and value.get("conclusion") == "success"
            and value.get("repository", {}).get("full_name") == setup.REPO,
            stage,
            "COMPLETED_RUN_MISMATCH",
        )
        stage = "job_binding"
        job = setup.api(run, stage, f"{api}/jobs/{job_id}")
        check(
            type(job) is dict
            and type(job.get("id")) is int
            and type(job.get("run_id")) is int
            and job.get("id") == job_id
            and job.get("run_id") == run_id
            and job.get("head_sha") == sha
            and type(job.get("run_attempt")) is int
            and job["run_attempt"] == 1
            and job.get("name") == "native_signing"
            and job.get("status") == "completed"
            and job.get("conclusion") == "success",
            stage,
            "COMPLETED_JOB_MISMATCH",
        )
        stage = "artifacts"
        artifacts = setup.api(run, stage, f"{api}/runs/{run_id}/artifacts?per_page=100")
        check(
            exact(artifacts, {"total_count": 0, "artifacts": []}),
            stage,
            "ARTIFACT_ABSENCE_UNCONFIRMED",
        )
        stage = "job_log"
        # gh 2.97 rejects ANSI in non-JSON responses even when stdout is a pipe.
        # Never display this override's raw response or use gh run view --log.
        raw = run(
            stage,
            [
                setup.GH,
                "api",
                "--hostname",
                "github.com",
                "--allow-escape-sequences",
                f"{api}/jobs/{job_id}/logs",
            ],
        )
        receipt = parse(raw)
        result.update(
            classification="SIGNED_RECEIPT_VERIFIED",
            receipt=receipt,
            artifact_count=0,
            next_action="REVIEW_UPLOAD_STAGE",
        )
    except setup.Failure as failure:
        result["failure"] = failure.public()
        result["cleanup_failure"] = failure.cleanup
    except Rejected as failure:
        result["failure"] = {"stage": failure.stage, "reason": failure.reason}
    except (Exception, KeyboardInterrupt):
        result["failure"] = {"stage": stage, "reason": "RECEIPT_READ_UNRESOLVED"}
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--job-id", required=True, type=int)
    parser.add_argument("--expected-commit", required=True)
    args = parser.parse_args(argv)
    result = read(args.run_id, args.job_id, args.expected_commit)
    print(json.dumps(result, sort_keys=True))
    return 1 if result["classification"] == "STOP" else 0


if __name__ == "__main__":
    raise SystemExit(main())
