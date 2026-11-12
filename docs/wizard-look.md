# Wizard View for the Pipeline Steps

The existing `RunDetailPage` (`/tasks/:domain/:runId`) shows all 18 pipeline
steps on one screen: a left sidebar lists every step and a free click on any
of them swaps the right-hand content panel. That page stays exactly as it is.

This plan adds a second, parallel way to look at the same run: a **wizard
view** that walks through the 18 steps one at a time, linearly, and only lets
the user move forward once the current step is fully done. The user can
always go back to review or edit an earlier step. This is purely a frontend
addition — no backend/API changes, no new step-status semantics, no
downstream-invalidation logic. The wizard is just a different lens on the
same `RunStatus`/`StepDetail` data the classic page already fetches.

## UI samples

These are rough text mockups of the key wizard states, to anchor the
decisions above before implementation.

### Entry point — link on the classic `RunDetailPage` header

```
┌────────────────────────────────────────────────────────────────────────┐
│ ← Back to runs    acme-corp / run-2026-11-10-001      [ 🧭 Wizard View ]│
├────────────────┬─────────────────────────────────────────────────────-─┤
│ ✓ Research      │                                                      │
│ ✓ Story         │              (existing content panel,                │
│ ✓ Scenes        │               unchanged)                             │
│ ▸ Assets (run)  │                                                      │
│ ○ Fetch Assets  │                                                      │
│ ○ ...           │                                                      │
└────────────────┴──────────────────────────────────────────────────────┘
```

Close-up of the new control itself — a single secondary/outline button
(same button style as other header actions on the page, e.g. `Settings`),
placed at the far right of the header, next to (not replacing) anything
already there:

```
  ┌───────────────────┐
  │ 🧭  Wizard View    │
  └───────────────────┘
```

- **Label:** "Wizard View" with a small compass/steps icon — distinguishes
  it from action buttons like "Rerun" that act on a single step.
- **Placement:** far right of `RunDetailPage`'s header row, so it reads as a
  page-level navigation action rather than a per-step action.
- **Style:** secondary/outline button (not the primary CTA color), since
  it's a mode switch, not the main action on the page.
- **Always visible and enabled** once a run has loaded — no disabled state;
  even a run with zero completed steps still opens the wizard at step 1.
- **Tooltip on hover:** "Open this run as a step-by-step wizard" — a short
  explainer, since "Wizard View" is a new concept on the page.

Clicking it opens the wizard at the first non-`done` step — in this
example, "Assets" (step 4). On the wizard page itself, the inverse link
("← Back to run" / "View in classic") returns to this page.

### Wizard — normal step, done, Next enabled

```
/tasks/acme-corp/run-2026-11-10-001/wizard/step-4

┌──────────────────────────────────────────────────────────────────────┐
│  ← Back to run            Wizard · acme-corp / run-2026-11-10-001     │
├──────────────────────────────────────────────────────────────────────┤
│   ✓──✓──✓──●──○──○──○──○──○──○──○──○──○──○──○──○──○──○               │
│                  ┌─────────────┐                                      │
│                  │ Asset       │  ← tooltip on hover, dot itself      │
│                  │ Manifest    │    carries no number/label           │
│                  └─────────────┘                                      │
├──────────────────────────────────────────────────────────────────────┤
│  Step 4 — Asset Manifest                              status: done ✓ │
│                                                                        │
│   (StepContentPanel renders AssetPlanEditor here, same editor         │
│    as the classic page — fully editable)                              │
│                                                                        │
├──────────────────────────────────────────────────────────────────────┤
│  [ ◂ Back ]                                              [ Next ▸ ]  │
└──────────────────────────────────────────────────────────────────────┘
```

### Wizard — step still running, Next locked

```
┌──────────────────────────────────────────────────────────────────────┐
│   ✓──✓──✓──✓──●──○──○──○──○──○──○──○──○──○──○──○──○──○               │
│                ┌──────────────────────┐                               │
│                │ Asset Acquisition    │  ← hover tooltip               │
│                │ Instructions         │                                │
│                └──────────────────────┘                               │
├──────────────────────────────────────────────────────────────────────┤
│  Step 5 — Asset Acquisition Instructions          status: running ⟳  │
│                                                                        │
│   (content panel shows in-progress output / spinner, same as          │
│    classic page while a step is active; polling every 3s)             │
│                                                                        │
├──────────────────────────────────────────────────────────────────────┤
│  [ ◂ Back ]                                    [ Next ▸ ]  (disabled)│
└──────────────────────────────────────────────────────────────────────┘
```

### Wizard — step failed, retry in place

```
┌──────────────────────────────────────────────────────────────────────┐
│   ✓──✓──✓──✓──✗──○──○──○──○──○──○──○──○──○──○──○──○──○               │
│                ┌──────────────────────┐                               │
│                │ Asset Acquisition    │  ← hover tooltip               │
│                │ Instructions         │                                │
│                └──────────────────────┘                               │
├──────────────────────────────────────────────────────────────────────┤
│  Step 5 — Asset Acquisition Instructions           status: failed ✗  │
│                                                                        │
│   ⚠ This step failed. See error details below.                       │
│   ------------------------------------------------------------       │
│   RuntimeError: timed out contacting asset source                    │
│                                                                        │
│                                            [ ⟲ Rerun this step ]      │
├──────────────────────────────────────────────────────────────────────┤
│  [ ◂ Back ]                                    [ Next ▸ ]  (disabled)│
└──────────────────────────────────────────────────────────────────────┘
```

### Wizard — final step done, pipeline complete

```
┌──────────────────────────────────────────────────────────────────────┐
│   ✓──✓──✓──✓──✓──✓──✓──✓──✓──✓──✓──✓──✓──✓──✓──✓──✓──●               │
│                                            ┌──────────────────┐       │
│                                            │ Platform Metadata │  ← hover│
│                                            └──────────────────┘       │
├──────────────────────────────────────────────────────────────────────┤
│  Step 18 — Platform Metadata                          status: done ✓ │
│                                                                        │
│   (StepContentPanel renders the final step's content)                │
│                                                                        │
│   ✓ Pipeline complete — all 18 steps done.                           │
├──────────────────────────────────────────────────────────────────────┤
│  [ ◂ Back ]                                   [ View in classic ▸ ]  │
└──────────────────────────────────────────────────────────────────────┘
```

Legend: `✓` done, `●` current, `○` locked/pending, `✗` failed, `⟳` running.
The dots themselves carry no step number or visible label — hovering any dot
shows that step's name in a tooltip, as sketched above.

## Key decisions from planning

- **New route, not a toggle.** A dedicated `RunWizardPage.tsx` is added
  alongside `RunDetailPage.tsx`; the classic page is untouched.
- **All 18 steps** are included, in the existing pipeline order
  (`backend/tasks.py` `STEPS`), none skipped or special-cased.
- **Per-step URL**, e.g. `/tasks/:domain/:runId/wizard/:stepId`. Each step is
  a real route — supports refresh, deep-linking, and browser back/forward —
  and makes forward-gating a straightforward route guard.
- **Gate definition:** a step is "fully done" only when
  `StepDetail.status === 'done'`. `pending`, `running`, and `failed` all
  block navigating past that step.
- **Failed steps are retried in-wizard:** a failed step's page shows the
  failure and a Rerun action (reusing the existing rerun call), rather than
  punting the user to the classic page.
- **No auto-advance.** When polling detects a `running` step flip to `done`,
  the wizard unlocks the Next button but does not navigate automatically —
  the user reviews/edits the output, then clicks Next deliberately.
- **Entry point:** a "Wizard View" link in `RunDetailPage`'s header. Opening
  it jumps straight to the first non-`done` step (Back is still available to
  revisit earlier done steps).
- **Locked URL guard:** navigating directly to a step URL that isn't yet
  reachable silently redirects to the furthest step the user is actually
  allowed to be on. No dead-end "locked" page.
- **Content reuse:** step output rendering/editing reuses the existing
  content-viewer components unchanged (`ResearchEditor`, `ScenePlanEditor`,
  `AssetPlanEditor`, etc.) — no divergent or simplified wizard-only content
  rendering.
- **No downstream invalidation.** Editing or rerunning an earlier step from
  the wizard does not reset later steps' status. This matches current
  backend behavior exactly (the backend has no such logic today) and keeps
  this entire change frontend-only.
- **Progress UI:** a horizontal stepper across the top of the wizard page
  (done = check, current = highlighted, locked = grayed/disabled), with
  Back/Next controls below the step content. Deliberately distinct from the
  classic page's left sidebar, so the two views read as genuinely different
  experiences.
- **No step numbers/labels on the stepper itself.** Each dot shows only its
  status icon — the step's name appears solely as a hover tooltip, keeping
  the stepper compact at 18 steps wide.

## Extract the shared content-viewer panel

`RunDetailPage.tsx:52-188` currently defines `ContentPanel` inline, including
the `content.kind === …` switch that dispatches to the step-specific viewer
components. Both the classic page and the new wizard page need this exact
dispatch logic, so it must be pulled out before the wizard is built.

### Move `ContentPanel` into its own component file

Extract the function as-is (no behavior change) into
`frontend/src/components/StepContentPanel.tsx`, taking whatever props it
currently closes over (`content`, step metadata, edit/save handlers, rerun
handler) as explicit props instead of relying on `RunDetailPage` closure
state.

#### Acceptance criteria

- `RunDetailPage.tsx` imports and renders `StepContentPanel` and behaves
  identically to before (manually verify: viewing/editing each represented
  `content.kind` still renders the right viewer and edits still save).
- No new behavior is introduced in this step — it is a pure move/refactor.

### Update `RunDetailPage.tsx` to use the extracted component

Replace the inline `ContentPanel` definition and its call site with the
import from `StepContentPanel.tsx`.

#### Acceptance criteria

- `RunDetailPage.tsx` no longer contains the `content.kind` switch directly.
- Existing classic-page tests/manual flows (step selection, rerun, content
  editing) are unaffected.

## Build the wizard route and step-gating logic

Add the new page, its route, and the core state machine that decides which
steps are reachable.

### Add the wizard route and page shell

Add `frontend/src/pages/RunWizardPage.tsx` and register
`/tasks/:domain/:runId/wizard/:stepId` in `frontend/src/App.tsx`. The page
fetches `RunStatus` the same way `RunDetailPage` does (same API client,
`frontend/src/api/tasks.ts`) and polls on the same 3s cadence while the run
is active.

#### Acceptance criteria

- Visiting `/tasks/:domain/:runId/wizard/:stepId` with a valid `stepId`
  renders a page shell with the top stepper and a content area.
- Polling behavior matches `RunDetailPage`'s existing 3s interval while
  `run.active` is true, and stops when the run is no longer active.

### Implement the reachability/gating logic

Compute, from `RunStatus.steps`, the furthest step the user is allowed to be
on: the first step in the ordered list whose `status !== 'done'`, plus every
step before it (always reachable) — the current "active frontier" plus all
done steps behind it. A step is reachable if its index is `<=` the frontier
index.

#### Acceptance criteria

- Back navigation is always enabled for any step with index less than the
  current step.
- Next is disabled unless the current step's status is `done`.
- Navigating (via typed URL, bookmark, or browser history) to a step whose
  index is greater than the frontier redirects to the frontier step.
- When a `running` step's polled status flips to `done`, Next becomes
  enabled without any navigation happening on its own.

### Build the top stepper component

Add a horizontal stepper (e.g. `frontend/src/components/WizardStepper.tsx`)
showing all 18 steps as plain status dots — no step number or name printed
on the dot itself. Each dot is checked for `done`, highlighted for the
current step, grayed/disabled for anything beyond the reachable frontier.
Wrap each dot in a tooltip (reuse the existing Radix/shadcn tooltip
primitive if one exists under `components/ui/`, otherwise add one) that
shows the step's real `name` (from `StepDetail.name`) on hover/focus.
Clicking a reachable step's dot navigates to it directly (this is just
another form of "going back" when the dot is behind the frontier, or
staying put when it's the current step); clicking a locked dot does nothing.

#### Acceptance criteria

- All 18 steps render in pipeline order, as unlabeled dots.
- Hovering (or focusing, for keyboard users) any dot shows that step's name
  in a tooltip; no number or name is visible without hovering.
- Only steps at or before the frontier are clickable; clicking a locked dot
  is a no-op (no navigation, no error).
- Visual states (done/current/locked) are visually distinct at a glance,
  independent of the tooltip.

### Wire up the step content area with Back/Next controls

Render `StepContentPanel` (from the extraction task) for the current step's
content, with Back/Next buttons below it. Back always navigates to
`stepId` of the previous step in order (disabled on the first step). Next
navigates to the following step's URL and is disabled per the gating logic
above (disabled on the last step once done, with a clear "pipeline complete"
state instead of a dangling Next).

#### Acceptance criteria

- Editing content via `StepContentPanel` on an earlier (already-done) step
  works exactly as it does on the classic page, including after the user
  has already moved forward past it — no downstream step status changes as
  a result (per the no-invalidation decision).
- Last step, once done, shows a completed/finished state rather than an
  enabled Next pointing nowhere.

## Handle failed steps in the wizard

A step with `status === 'failed'` must block Next and offer an in-place fix.

### Add a failure state view with Rerun

When the current step's status is `failed`, `RunWizardPage` (or
`StepContentPanel`) shows the failure clearly and a "Rerun" action that
calls the existing rerun API (`runStep(domain, runId, stepId, force=true)`,
the same call `RunDetailPage.tsx:251-260` already makes), then refetches
status.

#### Acceptance criteria

- A failed step's wizard page shows a visible failure indicator and a Rerun
  button, not a blank/broken content panel.
- Clicking Rerun triggers the same backend call the classic page's Rerun
  button uses, and the step's status updates via the existing polling once
  the rerun completes (no new polling mechanism).
- Next remains disabled until the rerun succeeds and status becomes `done`.

## Add the wizard entry point

### Add a "Wizard View" link to `RunDetailPage`'s header

Add a button in `RunDetailPage.tsx`'s header area, at the far right of the
existing header row, labeled "Wizard View" with a steps/compass icon, using
the same secondary/outline button style as other header-level actions on
the page. Give it a tooltip ("Open this run as a step-by-step wizard").
Clicking it navigates to `/tasks/:domain/:runId/wizard/:stepId`, where
`:stepId` is computed as the first non-`done` step in `run.steps` (or the
last step if everything is already done). See the "Entry point" mockup
under UI samples above for the exact look and placement.

#### Acceptance criteria

- The button is visible and enabled on `RunDetailPage` whenever a run is
  loaded, regardless of how many steps are done (including zero).
- Hovering/focusing it shows the explanatory tooltip.
- Clicking it lands the user on the correct frontier step per the "first
  incomplete step" rule, not always step 1.
- The classic page itself requires no other changes beyond adding this
  button.
