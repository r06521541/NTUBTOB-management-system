# Phase C identity maintenance closeout runbook

This is a repository-only execution contract, not production authorization.
The operator must stop unless Stage B and the exact Stage C Owner package are
approved. Do not record target IDs, names, LINE subjects, Member IDs, Person
IDs, Secret values, full environment output, or request bodies in this file.

## Prepared read-only commands (do not run without Stage B approval)

```powershell
gcloud run services describe web-portal --project ntubtob-schedule-405614 --region asia-east1 --format="json(status.latestCreatedRevisionName,status.latestReadyRevisionName,status.traffic)"
gcloud run revisions describe <owner-approved-candidate> --project ntubtob-schedule-405614 --region asia-east1 --format="json(status.imageDigest,status.conditions,spec.serviceAccountName)"
gcloud run services get-iam-policy web-portal --project ntubtob-schedule-405614 --region asia-east1 --format="json(bindings.role,bindings.members)"
```

The operator must separately project only the approved non-secret Phase C,
freeze and maintenance booleans plus Secret *binding name/version metadata*.
If that cannot be obtained without printing an environment payload, stop rather
than widening the command. Execute the checksummed SQL through the approved
read-only database channel and pass only its six sanitized columns plus the
aggregate metadata to `tools.phase_c_closeout.build_manifest`.

1. Run fresh account/project/region guards, the checksummed read-only SQL, the
   TASK-068 drift inventory, and the closeout verifier with aggregate evidence.
   Require schema 0004, all-on/unfrozen Phase C, at least one classified active
   allowlisted admin, zero drift, and zero duplicate request IDs.
2. Lock the current Web Portal revision/digest as rollback. Create only the
   Owner-approved maintenance=true candidate. Before 100% promotion, require
   Ready, unchanged image digest, exact public IAM, approved Secret binding
   metadata, Phase C=true, freeze=false, maintenance=true, and every other
   service unchanged. Any unknown candidate or metadata is a stop.
3. Promote only the verified candidate. If promotion/verification fails, return
   traffic to the locked maintenance-off revision. Do not change other services.
4. Use the Owner-provided, repository-external safe candidate classification and
   two opaque request IDs. Execute one supported domain action with a reason;
   retry the same request ID and require no new audit/state delta. Recover only
   through the approved domain action with the second request ID; never delete
   audit data or repair with SQL.
5. Re-run both inventories and compare only aggregate before/after evidence.
   Require all protected drift counts unchanged, exact expected audit deltas,
   and the original business-state classification restored. On recovery or
   audit mismatch, set maintenance=false or return to the locked revision,
   retain Phase C, stop, and escalate to Owner.

The admin pre-check is an aggregate classification only: an active Person with
a linked identity and a Member ID present in the runtime allowlist. The operator
must confirm its count is at least one without printing the allowlist or any
principal identifier. The action operator obtains CSRF, target and opaque
request ID only from the authenticated browser/session at execution time; it
replays the exact same POST body once before following its redirect, then uses
a distinct opaque request ID only for recovery. No special endpoint, CSRF bypass
or shell argument may be used for retry.
