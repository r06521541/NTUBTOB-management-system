# TASK-148: Flutter support, privacy and app information

- Task type: delivery
- Delivery group: `mobile-support-app-information`
- Risk level: L1 presentation／static configuration
- Repository authority: `9b1c52eeb9445887ad2ff9ab3b37b650e6fe8dd1`
- Owner gate: none for repository work; external contact publication, OS
  permission prompts, stores, signing and deployment remain excluded

## Goal

Give signed-in Flutter users one understandable place to learn how to contact
the team administrator, how the app uses their data and notifications, and
which app build they are viewing.

## Writer claim

- claim_id: `task-148-flutter-support-app-info-writer`
- lease_version: 1
- actor_id: `01a02907-0f8e-7fd3-a2a5-faad4beef47b`
- role: `codex-writer`
- write: true, limited to the task's Flutter implementation, affected tests and
  `docs/coordination/reports/TASK-148-FLUTTER-CODEX.md`
- report_to: `main-work`
- implementation branch: `codex/task-148-support-app-info-writer`

## Scope

- Add a `支援與 App 資訊` entry to the real account/home experience and use
  the same production widget in the fictional demo.
- Explain that account correction or deletion requests go through the team
  administrator and provide truthful in-app contact guidance without embedding
  a private account, credential or unapproved external URL.
- Add concise Traditional Chinese privacy/data-use disclosure covering account
  identity, games, attendance and notification content, plus the no-secret and
  no-advertising/third-party-sale boundaries supported by this product.
- Explain what notification permission would be used for and that in-app
  notifications still work independently. Do not request or infer OS
  permission in this task.
- Display app version/build metadata from an explicit compile-time/runtime
  source. Missing metadata must render as unavailable, never as a fabricated
  installed version.
- Add focused widget/configuration tests and production-shaped fake demo
  coverage.

## Invariants and non-goals

- Static information must not expose Person IDs, capabilities, tokens,
  notification bodies, secrets or private administrator contact data.
- No network request, external URL launch, clipboard write, OS permission
  prompt or analytics event occurs merely by opening the page.
- No backend, OpenAPI, schema, migration, provider, device registration,
  notification preference, deep-link, deployment, emulator, signing or store
  work.
- Do not refactor TASK-146/147 session, notification, game or navigation
  lifecycle behaviour.

## Verification budget

Writer runs only focused account/basic/demo/config tests affected by the change,
affected analyze/format checks, `git diff --check` and `git status --short`.
Main Work reviews copy truthfulness, zero-I/O behaviour and production-widget
composition. No Domain reviewer, local full suite, backend, PostgreSQL,
emulator or runtime matrix. Hosted CI is the independent full Flutter gate.

One batched correction round is available. A correction reruns only its affected
widget/config slice. Evidence reuse requires exact HEAD and unchanged command
and toolchain.

## Acceptance

- A signed-in user can open one support/app-information page from the real home
  and understand how to request account help.
- Privacy/data-use and notification-purpose language is readable, truthful and
  does not claim an OS permission state.
- Version/build values are sourced explicitly and missing values fail visibly
  to `未提供` or equivalent wording.
- Opening and reading the page performs zero transport, permission, storage
  mutation or other external action.
- The fictional demo renders the same production page without credentials or
  network access.

## Status

- 2026-08-22: planned by Main Work and authorized for repository execution.
- Current: ready for Writer claim.
