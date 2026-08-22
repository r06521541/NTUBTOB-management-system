# TASK-155 Flutter Web-Portal visual-system parity

## Classification

- task_type: work_package
- risk: incubator L1 (presentation/theme/component composition only)
- incubator_delivery_group: `flutter-member-experience-incubator-v1`
- shared_branch: `codex/flutter-incubator-member-experience`
- milestone: one coherent production-shaped Flutter visual language across the main member and officer flows
- requires_independent_pr: false
- owner_authorized: 2026-08-23

## Product outcome

Make the Flutter app feel like the same product as the Web Portal. Treat
`apps/web_portal/static/brand.css` and `production_portal.css` as the primary
art-direction reference, while adapting interaction and density for native
mobile instead of mechanically translating CSS.

1. Extract the Web palette and hierarchy into reusable Flutter tokens/theme:
   navy primary, warm-gold accent/focus, canvas/surface/text/muted/border,
   success/warning/danger soft states, 20px cards, 12px controls, restrained
   shadows, strong headings and consistent 8/16/24 spacing.
2. Establish reusable production components for the repeated Web vocabulary:
   page title/eyebrow, surface/action card, status badge/pill, notice panel,
   metric tile, primary/secondary action and segmented/filter controls. Preserve
   Material semantics, 44px minimum targets, text scaling and visible focus.
3. Apply the system broadly to existing production Flutter surfaces, not only a
   showcase: authenticated home/action dashboard, schedule/calendar and game
   cards/details, notification centre, Officer report/insights/Lineup Lab,
   onboarding/preferences/support, loading/empty/error/offline states and the
   production demo shell. Remove conspicuous one-off styling where a shared
   component or theme now expresses the same purpose.
4. Preserve system/light/dark selection. Light mode should closely match Web;
   dark mode must be a deliberate accessible derivation, not hard-coded light
   colors. Status colors must retain truthful meanings and readable contrast.
5. Keep information architecture and behavior intact. Visual refinement may
   improve grouping, spacing, typography, icons and mobile navigation clarity,
   but may not hide capability/offline warnings, change routes, invent data or
   add transport/storage side effects.
6. Extend the deterministic production demo so Owner can inspect the unified
   visual language across normal, actionable, warning, empty and offline states
   using production widgets.

## Web reference boundary

Read the shared Web brand/production CSS and representative templates for home,
games/detail, notifications, officer reporting and Lineup Lab. Copy the design
principles and recognizable product character. Native Flutter controls may
replace Web-specific hover, sticky-header, print and desktop-grid behavior.
Do not modify Web files.

## Focused evidence

- direct tests for canonical light/dark tokens and component semantics;
- representative widget tests proving shared components are composed by member
  home/schedule, notification, Officer/Lineup and support/preferences surfaces;
- existing focused behavior tests for every materially touched production file;
- production-demo tests covering normal/warning/empty/offline visual states;
- affected `flutter analyze`, canonical Dart format, `git diff --check`, final
  branch/HEAD/status and a concise list of intentional Web-to-mobile adaptations.

No task-local hosted CI, PR, emulator or platform build. Do not add screenshot or
golden infrastructure unless the existing toolchain already supports it without
new dependency/environment cost.

## Incubator exit conditions

Stop and notify Main before changing API/OpenAPI/DTO, auth/session/capability,
durable cache or preference semantics, backend/shared/schema/data, real
notification/provider, device permission behavior, navigation authorization,
deployment/signing/store configuration, dependencies, fonts or external assets.

## File boundary and handoff

Modify only the minimum required `clients/flutter_app/lib/**` and corresponding
tests, plus `docs/coordination/reports/TASK-155-FLUTTER-CODEX.md`. Do not modify
task/HANDOFF/policy, Web Portal, archive, backend or deployment files. Commit and
push one descriptive checkpoint to the shared branch; no PR. Proactively report
completion/blocker to Main with exact base/HEAD, dirty state, changed files,
focused evidence, adaptations and external effects.
