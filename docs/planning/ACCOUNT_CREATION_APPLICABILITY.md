# Account creation applicability audit — NOT SUBMITTED

Date: 2026-09-17. TASK-202 planning only; no product or runtime changes.
Source: `2b8e93e9029ac9be924967696b9be544f377c456`.

Subsequent Owner decision: DEC-112 selects Apple first-login with pending approval
and genuine account deletion. The exemption choice gate below is historical, not
a prerequisite for implementation. See [approved delivery direction](APPLE_ONBOARDING_DELIVERY.md).

## Decision and boundaries

Existing-account linking is supported by source evidence. A blanket claim that
the entire product only provides login and never supports account creation is
not established. A Person table name, an existing roster entry, or administrator
approval does not itself resolve Apple's account-creation requirement.

Do not change the product merely to manufacture an exemption. Keep normal login,
linking and team operations unchanged. The [deletion design](ACCOUNT_DELETION_DESIGN.md)
remains a conservative conditional option, not proof that all its implementation
is mandatory. Retention periods and identifiable-roster exceptions remain undecided.

## Evidence levels

- SOURCE: inspected repository behavior, not a claim of live availability.
- RECORDED BUILD: [TASK-198 report](../coordination/reports/TASK-198.md) binds
  installed TestFlight 1.0.0(2) to source
  `283c9c9e3de8f395728851d28039a7b2c46a1f24`, run35048625677.
- RECORDED RUNTIME: last sanitized staging record names
  `mobile-api-staging-task157-47ccfb5f`; this is not a fresh inventory or an
  immutable backend source/image binding. Never substitute the iOS SHA for it.
- UNKNOWN: current deployed provider/config/schema exposure and the eventual
  public release's complete onboarding behavior have not been verified here.

Build2 and current source have identical `identity_link.dart`, `pending_review.dart`,
`identity_linking.py` and `apps/mobile_api/bootstrap.py` in the inspected Git diff.
`basic_app.dart` changed support/deletion injection and terminal cache cleanup;
`identity_lifecycle.py` changed revision handling. `mobile_repository.py` also
changed schema readiness/notification handling. These are not a whole-app
equivalence claim; neither build proves the backend deployed matching code.
The last recorded Apple lifecycle configuration-name check found required names
absent. Do not ask the Owner to exercise Apple login on that basis or declare it ready.

## Source flow findings

| Path | Observed behavior | Applicability implication |
| --- | --- | --- |
| Ordinary provider exchange | Resolves linked identity and active Person; unknown subject cannot obtain a normal session or automatically create Person | Evidence for existing-account authentication, not proof about all other paths |
| Candidate entry from recovery/linking UI | Verified provider can create pending AuthIdentity and review thread/audit before existing-account proof; LINE also creates legacy line_users | New persistent personal data can exist even without a new Person |
| Self-link / recovery-link | Requires fresh different-provider proof bound to linked active Person; confirmation binds candidate, proof and installation/attempt | Strong evidence for adding/recovering access to an existing service account |
| Existing pending identity retry | Can receive bounded review credentials instead of normal session | Pending workflow must be explained; not full membership and not necessarily no account |
| Admin LINE approve_member | Links pending LINE identity to existing Member/Person | Distinguish existing service user from first activation of a roster-only person |
| Admin LINE approve_non_member | Can create new active basic Person and link identity; transaction also requires legacy LINE record | Source can support new service participation; not generic Apple/Google approval |
| Admin create_member | Can create Member and Person outside mobile self-service | Administrative roster creation alone does not prove in-app account creation or exemption |

Evidence entry points:

- [MobileRepository](../../shared_lib/shared_module/portal_data/mobile_repository.py):
  `exchange`, `ensure_google_link_candidate`, `ensure_apple_link_candidate`,
  `ensure_line_link_candidate`, `confirm_identity_link`.
- [IdentityLinkService](../../shared_lib/shared_module/identity_linking.py):
  `begin_candidate`, `issue_fresh_proof`, `_confirm`.
- [Identity lifecycle](../../shared_lib/shared_module/portal_data/identity_lifecycle.py):
  `ensure_pending_line_identity`, `create_member`, `approve_member`, `approve_non_member`.
- [Flutter entry](../../clients/flutter_app/lib/basic_app.dart),
  [link flow](../../clients/flutter_app/lib/identity_link.dart),
  [pending review](../../clients/flutter_app/lib/pending_review.dart),
  [Mobile routes](../../apps/mobile_api/app.py),
  [bootstrap](../../apps/mobile_api/bootstrap.py).

Do not conflate AuthIdentity creation with Person creation, or assume neither
could count as account creation under review. Candidate cancellation does not
establish erasure of the pending server record. Backend review routes with LINE
in their name must not be assumed provider-exclusive; admin approval paths must
not conversely be assumed provider-generic.

## Apple rules and defensible statements

[Apple account deletion guidance](https://developer.apple.com/support/offering-account-deletion-in-your-app/)
requires an in-app deletion initiation option where an app supports account
creation, including automatically created accounts. Removing one login method
or merely deactivating an account is not an equivalent deletion implementation.

[Review Guidelines](https://developer.apple.com/app-store/review/guidelines/)
5.1.1(v) supplies the account rule. Section4.8's existing education/enterprise
login exceptions address alternative login services, not an account-deletion
exemption. No explicit roster-only exemption was established by this research.

The published review preparation asks for full app access/test credentials or a
full-featured demo, working backend and explanations of non-obvious features.
It does not establish routine submission of backend SQL/schema. This does not
guarantee Apple will never request technical clarification. Describe behavior
truthfully and supply test access through the reviewed release process; do not
rely on reviewers being unable to inspect a database.

Safe now: “The system supports linking an additional verified login provider to
an existing active service identity. It also contains pending identity review
and LINE administrator onboarding paths; release exposure must be confirmed.”

Unsafe now: “There is no account creation anywhere”; “all Person data is exempt
because it is a roster”; “removing Apple alone satisfies account deletion”; or
“Apple has approved this interpretation.”

## Draft clarification to Apple — UNSENT, NOT FINAL REVIEW NOTES

> Our app serves an existing amateur sports team and its roster. We would like
> to clarify the application of Guideline5.1.1(v) before finalizing onboarding
> and account deletion. Our implementation can link an additional login provider
> only after fresh authentication with a different provider already linked to an
> active service identity. This linking does not create a new Person record.
>
> However, a verified but unlinked provider identity may first create a pending
> identity/review record. Our LINE administration workflow can link that identity
> to an existing member, or approve a non-member by creating a new service Person.
> We are still verifying which of these paths are exposed by the release candidate;
> this is not a claim that all are currently enabled or that the app is login-only.
>
> Would the pending/request-and-administrator-approval flow constitute support
> for account creation under5.1.1(v)? Would your assessment differ for a release
> genuinely restricted to already active service accounts with no onboarding
> request path? We are not proposing to treat removal of one provider as deletion
> of an entire service account, and can supply precise candidate flow evidence.

Do not submit this draft without a current candidate flow inventory and explicit
authorization. A support answer would inform scope, not guarantee App Review.

## Recommended next step

Keep the existing product scope intact. Before implementing destructive fulfillment
or claiming an exemption, bind the intended release to exact client and backend
versions/configuration and list who can first obtain service access through it.
Use sanitized metadata and isolated fixtures first; real provider login/new-user
creation and review submission require their own explicit scope.

If the release retains in-app onboarding/request-for-new-service-access, plan on
providing proper deletion rather than relying on the word “roster.” If a genuinely
existing-active-account-only release is desired, that is a product-scope decision,
not an unapproved cleanup. Either way, assess pending personal-data deletion and
retention separately. No Owner input or credential is required to complete this audit.
