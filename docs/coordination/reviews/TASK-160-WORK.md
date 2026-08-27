# TASK-160 Main Work review

## Verdict

`accepted_pending_hosted_ci`

Main reviewed the actual diff at implementation commit
`29ae8e2d064ed823af479e82e59f657a1916364d` against TASK-160. The change remains
inside the declared Web Portal repository boundary and introduces no provider,
cloud, runtime, Secret, schema, notification or production-data mutation.

## Accepted invariants

- Desktop `mode=browser` clears the prior Portal session before creating a new
  signed state／nonce pair; normal LINE in-app login remains unchanged.
- Callback state expiry and browser-session nonce binding remain fail closed.
- Dashboard reply forms receive CSRF without changing reply or notification
  domain behavior.
- Pending identity selection exposes only active／inactive Member-linked People;
  disabled／blocked／unlinked and forged targets are rejected before mutation.
- Independent Member matching no longer blocks non-member／ignore／reject actions;
  maintenance-off presentation disables every mutation form consistently.
- Same-day games retain independent links, reply state and CSRF-protected forms.

## Evidence

- Writer focused regressions: 7 passed; correction regressions: 4 passed.
- Writer Web Portal affected complete: 212 passed, 2 platform skips.
- Independent Auth／Identity review: ACCEPT after one bounded correction.
- Main supported discovery invocation for `test_admin_security.py`: 116 passed.
- Main's first two package-qualified unittest attempts failed at harness import
  setup (`config`, then `shared_lib`); the repository-supported discover command
  from root passed and no source correction was needed.
- `py_compile`, Black formatter API and `git diff --check`: passed per writer.

## Remaining gate

One final PR hosted CI must pass before merge. Production deployment and enabling
identity maintenance remain separate Owner-exact gates and are not authorized by
this review.
