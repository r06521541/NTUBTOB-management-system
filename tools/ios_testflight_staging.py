"""Metadata-only retained TASK-157 ownership, not runtime/data acceptance.

The injected CLI must bound time/output and decode JSON without duplicate keys.
Only describe operations are constructed; no Secret payload or database access.
Cloud Run revisions and Secret version payloads are immutable (Google Cloud
Run v1 Revision and Secret Manager Add a secret version documentation). Server
creation times reject post-receipt resource recreation. This does not establish
current IAM, DNS, database contents, schema or Apple configuration readiness.
Baseline name/digest: archived TASK-157 Gate B; exact server creation timestamp:
Main's TASK-198 read-only metadata observation, not caller-supplied authority.
References: https://docs.cloud.google.com/run/docs/reference/rest/v1/namespaces.revisions
https://docs.cloud.google.com/secret-manager/docs/add-secret-version
https://docs.cloud.google.com/run/docs/reference/rest/v1/Container
"""

import json
import re
from datetime import datetime, timezone

PROJECT = "ntubtob-mobile-staging"
SERVICE = "mobile-api-staging"
REGION = "asia-east1"
BASELINE = "mobile-api-staging-task157-bd8137b4"
DIGEST = "sha256:a536d41b880f2abd3ac7fd58f2c01ea4e07e7c49bb3a2d6a71d469c5623dbc76"
BASELINE_CREATED = datetime(2026, 8, 26, 5, 35, 31, 15912, tzinfo=timezone.utc)
DB = "PORTAL_DATA_DATABASE_URL"


def _require(condition):
    if not condition:
        raise ValueError()


def _timestamp(value):
    _require(
        type(value) is str
        and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,9})?Z", value)
    )
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _ready(document):
    conditions = document["status"]["conditions"]
    _require(type(conditions) is list and len(conditions) <= 32)
    ready = [c for c in conditions if c.get("type") == "Ready"]
    _require(len(ready) == 1 and ready[0].get("status") == "True")
    generation = document["metadata"]["generation"]
    observed = document["status"]["observedGeneration"]
    _require(
        type(generation) is int
        and generation > 0
        and type(observed) is int
        and observed == generation
    )


def _binding(template, number):
    spec, metadata = template["spec"], template.get("metadata", {})
    account = spec["serviceAccountName"]
    _require(
        type(account) is str
        and re.fullmatch(
            r"[a-z][a-z0-9-]{4,28}[a-z0-9]@"
            + re.escape(PROJECT)
            + r"\.iam\.gserviceaccount\.com",
            account,
        )
    )
    containers = spec["containers"]
    _require(
        type(containers) is list and len(containers) == 1 and not spec.get("volumes")
    )
    container = containers[0]
    if "name" in container:
        _require(
            type(container["name"]) is str
            and re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", container["name"])
        )
    _require(not container.get("volumeMounts") and not container.get("envFrom"))
    image = container["image"]
    _require(
        type(image) is str
        and re.fullmatch(
            r"[a-z0-9-]+-docker\.pkg\.dev/"
            + PROJECT
            + r"/[a-z0-9._/-]+@sha256:[0-9a-f]{64}",
            image,
        )
    )
    _require(
        len(image) <= 2048
        and all(part not in {"", ".", ".."} for part in image.split("/"))
    )
    aliases = {}
    annotation = metadata.get("annotations", {}).get("run.googleapis.com/secrets", "")
    _require(type(annotation) is str and len(annotation) <= 16384)
    for item in annotation.split(",") if annotation else []:
        alias, qualified = item.split(":", 1)
        _require(re.fullmatch(r"[A-Za-z0-9_-]{1,255}", alias) and alias not in aliases)
        match = re.fullmatch(
            r"projects/([^/]+)/secrets/([A-Za-z0-9_-]{1,255})", qualified
        )
        _require(match is not None and match[1] in {PROJECT, number})
        aliases[alias] = match[2]
    environment = container.get("env", [])
    _require(type(environment) is list and len(environment) <= 64)
    env, secrets, used = {}, {}, set()
    for item in environment:
        name = item["name"]
        _require(
            type(name) is str
            and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", name)
            and name not in env
        )
        if set(item) == {"name", "value"}:
            _require(type(item["value"]) is str and len(item["value"]) <= 8192)
            env[name] = ("plain", item["value"])
        else:
            _require(
                set(item) == {"name", "valueFrom"}
                and set(item["valueFrom"]) == {"secretKeyRef"}
            )
            ref = item["valueFrom"]["secretKeyRef"]
            _require(set(ref) == {"name", "key"})
            alias, version = ref["name"], ref["key"]
            _require(
                type(alias) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,255}", alias)
            )
            _require(
                type(version) is str and re.fullmatch(r"[1-9][0-9]{0,18}", version)
            )
            secret = aliases.get(alias, alias)
            if alias in aliases:
                used.add(alias)
            secrets[name] = (secret, version)
            env[name] = ("secret", secret, version)
    _require(used == set(aliases) and DB in secrets and len(secrets) <= 32)
    # A single container's generated display name follows the image name, not
    # its runtime/data ownership. All executable/configuration fields still bind.
    other_container = {
        k: v for k, v in container.items() if k not in {"image", "env", "name"}
    }
    other_spec = {k: v for k, v in spec.items() if k != "containers"}
    network = {
        k: v
        for k, v in metadata.get("annotations", {}).items()
        if k.startswith("run.googleapis.com/")
        and k
        in {
            "run.googleapis.com/vpc-access-connector",
            "run.googleapis.com/vpc-access-egress",
            "run.googleapis.com/network-interfaces",
            "run.googleapis.com/cloudsql-instances",
        }
    }
    return (account, env, other_container, other_spec, network), secrets


def verify(project, service, *, cli_json):
    """Fixed public result; no metadata values or exceptions escape."""
    success = False
    try:
        _require(project == PROJECT and service == SERVICE)
        calls = 0

        def read(command):
            nonlocal calls
            calls += 1
            _require(calls <= 48)
            value = cli_json(command)
            _require(type(value) is dict and len(json.dumps(value).encode()) <= 1048576)
            return value

        def describe(kind, name):
            return read(
                [
                    "gcloud",
                    "run",
                    kind,
                    "describe",
                    name,
                    "--project=" + PROJECT,
                    "--region=" + REGION,
                    "--format=json",
                ]
            )

        info = read(["gcloud", "projects", "describe", PROJECT, "--format=json"])
        _require(
            info.get("projectId") == PROJECT and info.get("lifecycleState") == "ACTIVE"
        )
        number = str(info["projectNumber"])
        _require(re.fullmatch(r"[1-9][0-9]{0,19}", number))

        def revision(name):
            _require(
                type(name) is str
                and re.fullmatch(re.escape(SERVICE) + r"-[a-z0-9-]{1,42}", name)
            )
            document = describe("revisions", name)
            metadata = document["metadata"]
            _require(
                metadata["name"] == name
                and str(metadata["namespace"]) == number
                and metadata.get("labels", {}).get("serving.knative.dev/service")
                == SERVICE
            )
            _ready(document)
            return document

        baseline = revision(BASELINE)
        created = _timestamp(baseline["metadata"]["creationTimestamp"])
        _require(created == BASELINE_CREATED)
        image = baseline["status"]["imageDigest"]
        _require(
            type(image) is str and (image == DIGEST or image.endswith("@" + DIGEST))
        )
        expected, secrets = _binding(baseline, number)
        _require(baseline["spec"]["containers"][0]["image"].endswith("@" + DIGEST))
        current = describe("services", SERVICE)
        _require(
            current["metadata"]["name"] == SERVICE
            and str(current["metadata"]["namespace"]) == number
        )
        _ready(current)
        _require(_binding(current["spec"]["template"], number)[0] == expected)
        traffic = current["status"]["traffic"]
        _require(type(traffic) is list and 0 < len(traffic) <= 10)
        names, tags, total = set(), set(), 0
        for item in traffic:
            _require(
                set(item) <= {"revisionName", "percent", "tag", "url", "latestRevision"}
            )
            percent = item.get("percent", 0)
            _require(type(percent) is int and 0 <= percent <= 100)
            total += percent
            tag = item.get("tag")
            if tag is not None:
                _require(
                    type(tag) is str
                    and re.fullmatch(r"[a-z][a-z0-9-]{0,62}", tag)
                    and tag not in tags
                )
                tags.add(tag)
            _require(percent > 0 or tag is not None)
            name = item["revisionName"]
            _require(name not in names)
            names.add(name)
        _require(total == 100)
        for name in names:
            observed = baseline if name == BASELINE else revision(name)
            _require(_binding(observed, number)[0] == expected)
        for secret, version in sorted(set(secrets.values())):
            metadata = read(
                [
                    "gcloud",
                    "secrets",
                    "versions",
                    "describe",
                    version,
                    "--secret=" + secret,
                    "--project=" + PROJECT,
                    "--format=json",
                ]
            )
            _require(
                metadata.get("name")
                == f"projects/{number}/secrets/{secret}/versions/{version}"
                and metadata.get("state") == "ENABLED"
                and _timestamp(metadata["createTime"]) <= created
            )
        # Reject service/template/traffic changes during the metadata snapshot.
        _require(describe("services", SERVICE) == current)
        success = True
    except Exception:
        pass
    return {
        "classification": (
            "STAGING_OWNERSHIP_RETAINED" if success else "STAGING_OWNERSHIP_UNVERIFIED"
        ),
        "ownership_verified": success,
        "runtime_postcheck_verified": False,
        "schema_verified": False,
        "release_authorized": False,
    }
