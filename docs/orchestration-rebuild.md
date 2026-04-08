# Orchestration Rebuild Inventory

This document inventories what the current orchestrator actually does today so we can decide, deliberately, what the new orchestrator should keep, change, or delete.

## Current Service Shape

The current orchestrator is a FastAPI service in `apps/orchestrator`.

It is not just a workflow-definition service. It currently owns:

- skill registry and file editing APIs
- workflow registry APIs
- hook asset registry APIs
- live process orchestration
- tmuxer dispatch for step execution
- notification ingestion from agents
- pending-message tracking and response routing
- process event logging
- PM-system task/comment integration
- hook-runner invocation

On startup it also ensures local git-backed asset repos exist for:

- `common-volume/skills`
- `common-volume/workflows`
- `common-volume/hooks`

and it starts background tasks for:

- agent-to-UI message stream consumption
- agent notification stream consumption
- periodic step timeout checking

## External Dependencies

The current orchestrator assumes these external services exist:

- Valkey at `settings.valkey_url`
- tmuxer at `settings.tmuxer_url`
- hook-runner at `settings.hook_runner_url`
- PM system at `settings.pm_url`

It also assumes filesystem roots under common-volume:

- skills
- workflows
- hooks
- hook-runs

It stores process event logs locally in SQLite under:

- `orchestrator/data/event_log.db`

Process state itself is not stored in SQLite. It lives in Valkey.

## API Surface

### Skills API

Routes under `/skills`:

- `GET /skills`
- `POST /skills`
- `GET /skills/{name}`
- `DELETE /skills/{name}`
- `GET /skills/{name}/files/{path}/versions`
- `GET /skills/{name}/files/{path}`
- `PUT /skills/{name}/files/{path}`
- `DELETE /skills/{name}/files/{path}`
- `POST /skills/{name}/upload`

Current functionality:

- create/delete skill folders
- parse `SKILL.md` frontmatter for metadata
- list all files in a skill
- read/write/delete arbitrary skill files
- upload files into a skill
- show git history for a skill file
- commit every change to git

### Workflows API

Routes under `/workflows`:

- `GET /workflows`
- `POST /workflows`
- `GET /workflows/{name}`
- `PUT /workflows/{name}`
- `DELETE /workflows/{name}`

Current functionality:

- store workflows as JSON files
- list workflow summaries
- validate that all referenced skill names exist
- create/update/delete workflow definitions
- store workflow-level hook configuration
- commit every workflow asset change to git

### Hooks API

Routes under `/hooks`:

- `GET /hooks`
- `POST /hooks`
- `GET /hooks/{name}`
- `PUT /hooks/{name}`
- `DELETE /hooks/{name}`

Current functionality:

- treat hook assets as Python files under `common-volume/hooks`
- CRUD those files
- commit all hook asset changes to git

### Processes API

Routes under `/processes`:

- `POST /processes`
- `GET /processes`
- `GET /processes/{process_id}`
- `GET /processes/{process_id}/notifications`
- `POST /processes/{process_id}/pause`
- `POST /processes/{process_id}/resume`
- `DELETE /processes/{process_id}`
- `POST /processes/{process_id}/steps/kill`
- `PATCH /processes/{process_id}/steps/config`
- `POST /processes/{process_id}/phases`
- `DELETE /processes/{process_id}/phases/{phase_index}`
- `POST /processes/{process_id}/steps/run`
- `DELETE /processes/{process_id}/steps`
- `POST /processes/{process_id}/steps`
- `POST /processes/{process_id}/steps/move`
- `POST /processes/notify`
- `GET /processes/by-task/{task_id}`

This is the real orchestration API.

### Messaging API

Routes under `/messaging`:

- `GET /messaging/pending`
- `GET /messaging/{message_id}`
- `POST /messaging/{message_id}/respond`

Current functionality:

- expose pending agent questions/messages
- retrieve previously seen messages by ID
- route human responses back into the correct tmux session

### Events API

Routes under `/events`:

- `GET /events/process/{process_id}`

Current functionality:

- return process event history from SQLite

## Current Data Model

### Workflow Model

A workflow currently contains:

- `name`
- `description`
- `steps: list[list[str]]`
- `hooks`

Important detail:

- `steps` is phase-oriented
- each inner list is a phase
- each string inside a phase is a skill name

So the current model is:

- workflow
- phases
- skills inside phases

This is the place where a future internal `step` abstraction would replace the current hardcoded `skill` execution unit.

### Process Model

A process currently contains:

- process metadata
- task/project linkage
- workflow name
- current phase index
- process status
- per-phase statuses
- per-step statuses
- copied workflow hooks
- accumulated hook run records
- timestamps

Process status values currently used:

- `pending`
- `running`
- `paused`
- `completed`
- `failed`

Phase status values currently used:

- `pending`
- `running`
- `done`
- `failed`

Step status values currently used:

- `pending`
- `dispatched`
- `running`
- `done`
- `failed`
- `rfi`

Each step currently stores:

- `skill`
- `agent`
- `model`
- `tmux_session`
- status/timestamps
- optional `detail`

### Hook Model

Workflow and process hooks currently support these event types:

- `pre_workflow`
- `post_workflow_finish`
- `pre_phase`
- `post_phase_finish`
- `pre_skill`
- `post_skill_finish`

Each hook entry stores:

- `asset_name`
- `failure_policy`

Failure policies:

- `fail`
- `warn_and_continue`

This is where the new hidden `step` hook should logically fit in the rebuild.

## Current Process Lifecycle

### Process Creation

`POST /processes` currently does two things:

1. create a process object from PM task + workflow definition
2. immediately start it

During creation the orchestrator:

- fetches the task from PM
- fetches the task’s project from PM
- loads the named workflow
- expands workflow phases/skills into concrete step records
- requires agent/model configuration for every workflow skill
- copies workflow hook definitions into the process
- stores the process in Valkey

### Process Start

`start_process()` currently:

1. runs `pre_workflow` hooks
2. marks process `running`
3. updates PM task status to `in_execution`
4. finds the earliest unfinished phase
5. dispatches that phase

If hook execution or PM update fails, the process is marked failed.

### Phase Dispatch

`_dispatch_phase()` currently:

- stops immediately if process is paused
- completes the process if `current_phase >= len(phases)`
- skips empty/completed phases and advances recursively
- runs `pre_phase` hooks before dispatching a phase
- dispatches all unfinished steps in the phase in parallel

Important current behavior:

- phases are serial
- steps inside a phase are parallel

For each unfinished step:

1. run `pre_skill` hooks
2. kill any lingering tmux session if step still has one
3. dispatch the step to tmuxer
4. mark step `dispatched`
5. stamp `started_at`

### Step Dispatch

`_dispatch_step()` currently calls tmuxer:

- `POST {tmuxer_url}/orchestrated/start`

Payload includes:

- `process_id`
- `phase`
- `step`
- `agent`
- `model`
- `task_title`
- `task_description`
- `workflow_name`
- `project_name`
- notification channel name

Returned value used by orchestrator:

- `session_name`

That session name is stored as `tmux_session` on the step.

### Notifications and Step Completion

The orchestrator consumes the Valkey notifications stream and converts each stream item into a `NotificationEvent`.

Supported notification event names currently handled:

- `start`
- `done`
- `fail`
- `rfi`
- `progress`

Behavior by event:

#### `start`

- step becomes `running`
- `started_at` is updated

#### `done`

- step becomes `done`
- `completed_at` is set
- tmux session is killed and cleared
- `post_skill_finish` hooks run
- if every step in the phase is now done:
  - `post_phase_finish` hooks run
  - phase becomes `done`
  - process advances to next phase
  - next phase dispatch starts immediately if process is still running

#### `fail`

- step becomes `failed`
- `completed_at` is set
- failure detail is stored
- tmux session is killed and cleared
- phase becomes failed
- process becomes failed
- PM comment is added

#### `rfi`

- step becomes `rfi`
- detail is stored

#### `progress`

- currently only logged into the event log
- no process-state mutation beyond general save path

### Process Completion

When all phases are complete, orchestrator currently:

1. runs `post_workflow_finish` hooks
2. marks process `completed`
3. records a `process_completed` event
4. updates PM task status to `ready_for_human_review`
5. adds a PM comment

## Current Hook Execution Model

Hook support is already live.

### Hook Asset Storage

Hook assets live under:

- `common-volume/hooks/<name>.py`

### Per-Process Hook Workspace

For each process, hook execution artifacts live under:

- `common-volume/hook-runs/<process_id>/scripts`
- `common-volume/hook-runs/<process_id>/payloads`
- `common-volume/hook-runs/<process_id>/logs`

### Hook Execution Flow

For every hook invocation, orchestrator currently:

1. ensures process hook workspace exists
2. copies the hook asset into the process `scripts` directory
3. materializes a JSON payload file
4. computes stdout/stderr log file paths
5. calls the hook-runner over HTTP
6. records the result into `proc.hook_runs`

The hook-runner request currently includes:

- `script_path`
- `payload_path`
- `stdout_log_path`
- `stderr_log_path`
- `timeout_seconds`

The payload currently contains:

- event name
- timestamp
- process metadata
- optional phase metadata
- optional skill metadata

### Hook Ordering and Failure Semantics

Within a given event group:

- hooks execute serially
- first failure stops the group if policy is `fail`
- failures may be recorded and continued if policy is `warn_and_continue`

Important distinction in the current implementation:

- serial execution is enforced within a process’s hook group
- nothing prevents different processes from invoking hooks concurrently

## Current Pause / Resume / Manual Control Behavior

### Pause

Pausing a running process currently:

- kills all live tmux sessions for non-completed steps
- resets non-done steps back to `pending`
- recomputes phase statuses
- moves `current_phase` to earliest unfinished phase
- marks process `paused`

This is not a “freeze exactly where execution was” pause.

It is effectively:

- kill active work
- reset unfinished work for rerun

### Resume

Resuming a paused process currently:

- finds earliest unfinished phase
- if nothing remains, marks completed
- otherwise marks `running`
- dispatches that phase again

### Kill Step

Manual step kill currently:

- only works on running/paused processes
- only works on non-completed live steps with a tmux session
- kills that tmux session
- resets that step to pending
- marks process paused

So user kill is also implemented as:

- abort specific live step
- pause orchestration

### Manual Single-Step Run

`run_step()` currently allows:

- only when process is paused
- only for the earliest runnable phase
- only for a pending, never-started step

It dispatches just that step to tmuxer and marks the phase running.

### Runtime Process Editing

The current orchestrator allows editing future process structure:

- add phase
- delete phase
- add step
- delete step
- move step between phases
- update agent/model for a future step

These edits are only allowed on phases that have not started yet.

That means the current system already supports in-flight process mutation for future work, even though the workflow definition itself is static.

## Timeout Handling

There is a background timeout checker that runs every 60 seconds.

Current timeout behavior:

- only checks running processes
- only checks current phase
- only checks steps in `dispatched` or `running`
- skips skills whose mode is `interactive`
- uses global timeout `process_timeout_seconds`

If a timeout is detected:

- step becomes `failed`
- timeout detail is stored
- tmux session is killed
- phase/process may be marked failed if phase is terminal with failures
- PM comment is added on failure

## Messaging Functionality

The orchestrator also acts as a lightweight conversation-response router.

### Agent-to-UI Stream Consumption

Background task `consume_stream()` reads from Valkey stream:

- `agent:to:ui`

For each message it:

- parses content JSON
- stores all messages in `_messages`
- stores response-required messages in `_pending`
- timestamps messages from stream IDs

### Pending Message Listing

`list_pending()`:

- fetches live tmux sessions from tmuxer
- prunes pending messages whose sessions no longer exist
- returns remaining pending messages oldest-first

### Response Routing

`respond(message_id, response)`:

- removes message from `_pending`
- routes text back into the tmux session through tmuxer input API
- marks stored message as resolved

This functionality is separate from process lifecycle, but the current orchestrator owns it.

## Event Logging

The orchestrator persists process lifecycle events in SQLite.

It records:

- notification events
- explicit `process_completed`

Each row includes:

- process id
- phase
- step
- event
- detail
- timestamp
- workflow name
- task title
- project name

Current uses:

- process history API
- operational introspection

## PM-System Integration

The current orchestrator is tightly coupled to the PM system.

It currently depends on PM for:

- fetching task metadata
- fetching project metadata
- updating task status
- adding comments to tasks
- listing task comments
- deleting its own orchestration comments

Current task status transitions used:

- `in_execution` on start
- `ready_for_human_review` on success
- `unopened` when deleting a non-terminal process

Comments are also used as user-visible orchestration audit markers.

## Git-Backed Asset Management

Skills, workflows, and hook assets are all git-backed.

Current behavior:

- initialize repo if missing
- stage/commit on every asset change
- expose skill file history via git log

This means the current orchestrator owns not only execution but also authoring storage for orchestration assets.

## Filesystem / Safety Behavior

Current safety helpers include:

- path traversal protection for skill file access via `safe_resolve()`
- separate repo roots for skills/workflows/hooks

Current process runtime artifacts are written to common-volume and are not isolated per worktree or sandbox.

## Implicit Design Decisions in the Current System

These are not just implementation details; they are actual design choices in the current orchestrator:

- workflow phases are serial
- steps inside a phase are parallel
- step execution primitive is hardcoded as a skill
- execution backend is tmuxer
- orchestration state lives in Valkey
- event history lives in SQLite
- hook assets and authoring assets live in git-backed filesystem repos
- process edits are allowed for future phases/steps
- pause means kill and reset unfinished work
- notifications are authoritative for step lifecycle
- PM task/comment integration is part of the orchestrator core

## Functionality Buckets to Evaluate During Rebuild

When rebuilding, we should decide explicitly which of these buckets belong in the new orchestrator:

### 1. Asset Authoring

- skill CRUD
- workflow CRUD
- hook asset CRUD
- git-backed asset commits

### 2. Execution Engine

- process creation
- lifecycle state machine
- phase/step scheduling
- pause/resume/manual run/manual kill
- timeout handling

### 3. Hook System

- workflow/phase/skill hook lifecycle
- per-process hook artifacts
- hook-runner integration
- failure-policy semantics

### 4. Agent Interaction

- notifications stream
- pending message stream
- human response routing

### 5. PM Integration

- task fetch/update
- project fetch
- comment creation/deletion

### 6. Observability

- event log
- notification history
- process history APIs

## Rebuild Notes

The current orchestrator already contains a meaningful hook pipeline, but it is still organized around:

- workflow
- phase
- skill

If the rebuild is going to become hook-first and configuration-first, the main internal shift should be:

- make the engine’s atomic executable unit a `step`
- treat current `skill` execution as one kind of step behavior
- eventually introduce hidden step lifecycle hooks internally

That would let the new orchestrator preserve the useful parts of the current system:

- explicit lifecycle
- process mutation
- event logging
- external execution adapters

without carrying forward the current hardcoded assumption that “a step is always a skill.”
