# Handoff

## Current Architecture

The active orchestration path is `new_orchestrator`.

- `new_orchestrator` is the only orchestration target that matters now.
- The legacy `orchestrator` folder has been moved to:
  - `apps/_local_backups/orchestrator`
- `new_orchestrator` runs in Docker from the existing infra compose stack on port `8101`.
- It mounts `common-volume` at `/workspace/common-volume`.
- It owns:
  - workflow, skill, and hook asset APIs
  - live workflow state in Valkey
  - event history
  - hook firing
  - runtime artifact creation under `common-volume/hook-fires`
- It does not embed PM, secrets, Git forge, or tmuxer business logic beyond the explicit hook and runtime contracts.

The core contract is:

- orchestrator maintains workflow state
- orchestrator materializes `state.json`
- orchestrator fires hooks in order
- scripts do external work
- workflow advancement happens through `POST /processes/notify`

## Lifecycle

Current hook set:

- `pre_workflow`
- `post_workflow`
- `pre_phase`
- `post_phase`
- `pre_step`
- `step`
- `post_step`
- `on_workflow_pause`
- `on_workflow_continue`
- `on_step_timeout`
- `on_step_user_kill`

Current advancement model:

- workflow advancement is no longer driven by the Valkey notifications stream
- workflow advancement is driven only by `POST /processes/notify`
- hook order is notification-gated rather than dispatch-gated
- missing lifecycle hooks are treated as contract errors, not silent backend fast paths

## Runtime Layout

Hook fire folders live under:

- `common-volume/hook-fires/<workflow_uuid>/pre_workflow`
- `common-volume/hook-fires/<workflow_uuid>/post_workflow`
- `common-volume/hook-fires/<workflow_uuid>/phases/phase-<n>/pre_phase`
- `common-volume/hook-fires/<workflow_uuid>/phases/phase-<n>/post_phase`
- `common-volume/hook-fires/<workflow_uuid>/phases/phase-<n>/<step-name>/pre_step`
- `common-volume/hook-fires/<workflow_uuid>/phases/phase-<n>/<step-name>/step`
- `common-volume/hook-fires/<workflow_uuid>/phases/phase-<n>/<step-name>/post_step`

Each fire writes:

- `state.json`
- copied hook script(s)

Each workflow also writes:

- `common-volume/hook-fires/<workflow_uuid>/logs.log`

The UI can watch that file through the orchestrator logs endpoint.

## State Dict

`state.json` is the hook runtime contract.

Important fields:

- `workflow_uuid`
- `hook_event_name`
- `common_volume_root`
- `orchestrator_url`
- `tmuxer_url`
- `interaction_service_url`
- `secrets_service_url`
- `phase_number` when applicable
- `step_details` when applicable
- `project_identities_associated`
- `project_environment_variables_associated`
- `workflow_definition`
- `additional_caller_info`

`additional_caller_info` currently includes:

- `project_name`
- `ticket_name`
- `task_description`
- `task_id`
- `project_base_repo_path_relative_to_common_volume`
- `project_identities_associated`
- `project_environment_variables_associated`
- `project_properties`

For step-scoped hooks it is also augmented with:

- `selected_agent`
- `selected_model`

Hooks must:

- resolve environment-sensitive paths and service URLs from `state.json`
- not hardcode orchestrator, tmuxer, interaction-service, secrets-service, or common-volume locations

## Current Hook Scripts

Under `common-volume/hooks`:

### `scryer-pre-workflow.py`

This currently:

- reads `state.json`
- resolves the base repo from `additional_caller_info`
- creates `common-volume/agent-sessions/<workflow_uuid>`
- creates a worktree there if a base repo exists
- otherwise initializes a new git repo and renames the default branch to `main`
- copies the full skill library into local agent folders
- writes local agent config files
- updates `.gitignore` for transient local agent folders
- copies the `interactor/` scaffold into the session root
- resolves selected runtime environment variables through `scryer_resolver.py`
- calls tmuxer trust endpoints
- logs heavily
- posts `done`

Important design choice:

- the session folder path is exactly `agent-sessions/<workflow_uuid>`

### `scryer-pre-step.py`

This currently:

- writes `task.md`
- writes `agents-<step>.md`
- writes `prompt-<step>.txt`
- includes project, task, agent, and model context
- posts `done`

### `scryer-step.py`

This currently:

- reads `state.json`
- resolves the session repo
- validates expected step assets
- writes `.env.<step>`
- derives a deterministic tmux session name from:
  - `workflow_uuid`
  - `phase_number`
  - `step_name`
- starts the per-step tmux session via tmuxer
- posts `start` to `new_orchestrator` with `detail.session_name`

Important:

- it does not post `done`
- `done`, `pass`, or `fail` are expected to come later from the launched agent via `interactor.sh`

### `scryer-post-step.py`

This currently:

- derives the canonical step tmux session name from runtime state
- deletes that tmux session through tmuxer
- posts `done`

### `scryer-noop.py`

This is the canonical explicit no-op lifecycle hook.

It currently:

- reads `state.json`
- logs that the lifecycle hook ran
- posts `done`

### `scryer-step-fail.py`

This is the canonical explicit failing step lifecycle hook for:

- `on_step_timeout`
- `on_step_user_kill`

It currently:

- derives the canonical step tmux session id from runtime state
- attempts tmux session cleanup through tmuxer
- posts `fail`

### `scryer-post-workflow.py`

This currently:

- removes transient agent folders first
- inspects the session repo and derives git metadata
- looks for `pr.md`
- no-ops if `pr.md` is absent
- if `pr.md` is present and preconditions are satisfied:
  - resolves the selected runtime git identity
  - pushes the workflow branch with identity-backed auth
  - creates a remote PR for supported providers
- calls tmuxer untrust endpoints
- preserves the workflow worktree
- posts explicit `done` or `fail`

## Secrets Runtime

The workflow runtime carries enough information for hook-side secrets resolution.

- `state.json` includes `secrets_service_url`
- current host URL: `http://127.0.0.1:8211`
- current container or hook URL: `http://host.docker.internal:8211`

Projects no longer define freeform runtime identities or variables locally. Instead:

- identities are defined centrally in the secrets service
- environment variables are defined centrally in the secrets service
- projects select which of those names are exposed to runtime
- only the checked names are injected into `state.json`

Shared hook-side resolver:

- `common-volume/hooks/scryer_resolver.py`
  - `resolve_identity(name)`
  - `resolve_variable(name)`

## Interactor

`common-volume/interactor/interactor.sh` now participates in the new contract.

It posts to:

- `http://new-orchestrator:8101/processes/notify`

using:

- `workflow_uuid`
- `phase_number`
- `step_name`

Expected step-side commands now include:

- `task-start`
- `task-done`
- `task-pass`
- `task-fail`
- `task-progress`
- `task-summon`
- `task-ask-mcq`

## Tmuxer

Tmuxer is being reduced to a session utility.

Current tmuxer state:

- old `/start/{agent}` endpoints are no longer exposed
- old `/orchestrated/start` endpoint is no longer exposed
- new endpoint exists:
  - `POST /start/with-command-in-path`
- trust endpoints exist:
  - `POST /trust-path`
  - `POST /untrust-path`

`/start/with-command-in-path` currently:

- accepts a common-volume-relative path
- resolves that internally to tmuxer’s mounted path
- creates a tmux session
- runs the provided command there
- returns:
  - `session`
  - `session_name`

## Testing

Focused automated coverage exists under:

- `new_orchestrator/tests`

Covered areas include:

- pre-workflow bootstrap behavior
- shared secrets resolution
- `pre_step -> step` integration
- deterministic per-step tmux session startup
- process notification behavior
- phase dispatch behavior
- post-workflow PR behavior

## Phase Architecture Extension

This is the next required design change. The old anonymous `steps: list[list[str]]` workflow schema is no longer the target shape.

This is a breaking change by design.

### New First-Class Phase Model

Workflow definitions should move to first-class phase objects.

Each phase will carry:

- `type`
- `completionMode`
- `maxTimes`
- `steps`

Supported phase `type` values:

- `ExecParallel`
- `ExecSerial`

Supported `completionMode` values:

- `execCount`
- `allPass`

Defaults:

- default `completionMode` is `execCount`
- default `maxTimes` is `1`

`maxTimes` applies only when `completionMode` is `execCount`.

### Phase Semantics

`ExecParallel`:

- dispatch all pending steps in the phase iteration together
- wait for the entire phase batch to finish before evaluating iteration completion

`ExecSerial`:

- dispatch exactly one step at a time in listed order
- wait for that step to reach `done` or `pass`
- then move to the next step

For both phase types:

- `pre_phase` and `post_phase` are part of the repeated phase iteration contract
- if the phase repeats, `pre_phase` fires again before the next iteration
- this imposes an idempotency requirement on downstream scripts

### `execCount`

For `completionMode: execCount`:

- a phase iteration means:
  - `pre_phase`
  - full step execution for that phase according to phase type
  - `post_phase`
- `maxTimes` counts the number of successful `post_phase` completions
- once `post_phase` has completed successfully `maxTimes` times, the phase advances
- any step `fail` is still a real failure and fails the workflow

### `allPass`

For `completionMode: allPass`:

- every step in the phase must emit `pass`
- `done` is not `pass`
- `maxTimes` does not apply

`ExecSerial + allPass`:

- if a step emits `done`, the phase iteration restarts from the beginning
- the whole iteration restarts, not just that single step

`ExecParallel + allPass`:

- dispatch the full batch
- wait until all steps reach completion for that iteration
- if every step emitted `pass`, advance
- otherwise restart the whole iteration

### New `pass` Notification

A new notification event must exist:

- `pass`

Rules:

- `pass` is only valid for step-scoped notifications
- if any workflow-scoped or phase-scoped hook emits `pass`, that is an error and should fail the workflow
- `pass` should behave like a completed step in control flow
- the stored step status should still be distinct:
  - `pass`

### Step Runtime History

Steps can now run across multiple phase iterations.

Because of that:

- `started_at` and `completed_at` should become first-class histories
- replace them with:
  - `started_ats`
  - `completed_ats`

For a new phase iteration:

- reset step status and transient runtime fields needed for a fresh run
- preserve start and completion history
- use the most recent `started_ats` entry for timeout checks

### Phase Iteration Tracking

Phases should persist and expose a cycle counter.

This should exist on the runtime phase object and be included in `state.json`.

Expected field:

- `phase_iteration`

Behavior:

- it starts at `0` for the first phase run
- it increments after each successful `post_phase` completion

This is useful both for orchestrator logic and for weaker downstream hook implementations.

## Immediate Implementation Target

The next implementation slice is:

1. replace the old workflow endpoint contract with first-class phase objects
2. extend runtime phase and step schemas for:
   - `type`
   - `completionMode`
   - `maxTimes`
   - `phase_iteration`
   - `started_ats`
   - `completed_ats`
   - step status `pass`
3. add notification support for:
   - `pass`
4. change advancement logic to support:
   - repeated phase iterations
   - `ExecParallel`
   - `ExecSerial`
   - `execCount`
   - `allPass`
5. fail the workflow if any non-step hook emits `pass`

## Notes

- downstream scripts are expected to be idempotent across repeated phase iterations
- this is intentionally not being hardcoded away in the orchestrator
- the user is an adult
