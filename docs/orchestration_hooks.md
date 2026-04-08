# Orchestration Hooks Design

## Purpose

Hooks are the central orchestration extension mechanism.

The goal is to remove hardcoded orchestration behavior wherever hooks can express the same behavior more cleanly.

This document defines the current design direction. It is not a claim that every part below is already implemented.

---

## Supported Hook Events

The first version supports only these fixed lifecycle events:

- `pre_workflow`
- `post_workflow_finish`
- `pre_phase`
- `post_phase_finish`
- `pre_skill`
- `post_skill_finish`

No arbitrary conditional triggers are included in v1.

---

## Hook Definition Model

Hooks exist in two layers:

- workflow definition level
- process instance level

This follows the same model as workflows themselves:

- workflow definition is the class
- executing workflow is the instance

A process instance begins with a copied hook set derived from the workflow definition.

For v1:

- workflow definitions can define hooks
- process instances receive a copied hook set at execution start
- live editing of hooks during execution is not required yet

Longer term:

- process-instance hooks should eventually be editable during execution for future hook events

---

## Hook Asset Model

Reusable workflow-level hooks are named Python script assets.

For v1, each hook asset has only:

- `name`
- `python source`

These reusable hook assets live at:

- `common-volume/hooks/<name>.py`

Examples:

- `common-volume/hooks/notify_slack.py`
- `common-volume/hooks/update_dashboard.py`

---

## Hook Ordering

Each hook event maps to an ordered list of scripts.

Example:

```json
{
  "hooks": {
    "pre_workflow": ["scr_1.py", "scr_2.py", "scr_3.py"],
    "post_workflow_finish": ["scr_4.py"]
  }
}
```

Execution order is exactly the list order.

There is no separate integer priority field in v1.

---

## Execution Semantics

Hooks are blocking.

This means:

- orchestration waits for a hook to finish before continuing
- `pre_*` hooks must finish before the corresponding workflow, phase, or skill begins
- `post_*` hooks must finish before orchestration proceeds past that completion point

If multiple scripts are attached to a single hook event:

- they run serially
- never in parallel
- in exact list order

No two hook scripts run at once.

No two hook events run at once.

The runner stops immediately on the first non-zero exit code and returns that failure to orchestrator.

The orchestrator then applies the hook failure policy.

---

## Failure Policy

Each hook has a failure policy.

Supported policies in v1:

- `fail`
- `warn_and_continue`

Default:

- `fail`

If a hook cannot resolve required scope values before execution:

- the hook does not run
- this counts as hook failure
- the hook failure policy decides whether orchestration fails or continues with warning

---

## Script Language

Hooks are Python only.

V1 does not support bash hooks.

All hook scripts are executed with Python inside a dedicated hook-runner container.

---

## Execution Location

Hooks do not run:

- in tmux sessions
- in the tmuxer container
- in the orchestrator container

Hooks run in a separate shared hook-runner container.

The hook-runner container:

- mounts the same common volume as the rest of the system
- has one centrally managed Python environment
- uses one centrally managed `requirements.txt`
- is reused for all hook executions
- is not created per hook
- is not created per process

This is one shared execution environment for hooks.

---

## Execution Folder Layout

Hooks execute from deterministic folders in the common volume.

The root is:

- `<common_volume>/hook_executions/<agent_id>/`

Where `<agent_id>` is the same canonical id already used for the corresponding agent execution root.

Under that root, each fired hook event gets one folder.

Examples:

- `pre_workflow`
- `post_workflow_finish`
- `pre_phase_2`
- `post_phase_finish_2`
- `pre_skill_writer`
- `post_skill_finish_writer`

Rules:

- phases use phase index
- skills use skill name
- if a collision still occurs, append a unique suffix

All scripts attached to the same fired hook event run inside the same event folder.

That folder contains:

- copied script files with their original filenames
- `scope_vars.json`

Scripts are executed in exact list order inside that same working directory.

---

## Scope Model

Hook inputs are provided through a JSON file.

The standardized filename is:

- `scope_vars.json`

The file is written into the hook execution folder before the runner is called.

Hook scripts should assume this file exists in the current working directory:

- `./scope_vars.json`

There is no dedicated env var for the scope file path in v1.

There is no materialized script templating step in v1.

The script remains the script.

The orchestrator only materializes the scope dictionary.

---

## Orchestrator / Runner Responsibility Split

The orchestrator is responsible for preparing hook execution.

The orchestrator must:

- determine the correct hook execution folder path
- create that folder in common volume
- copy the ordered hook scripts into it
- write `scope_vars.json`
- call the hook-runner

The hook-runner is intentionally dumb.

The hook-runner is responsible only for:

- resolving the deterministic execution folder
- executing the copied Python scripts in exact list order
- stopping on first non-zero exit code
- returning logs and exit status to orchestrator

The runner should not own orchestration logic.

---

## Output Capture

Every hook run must record:

- stdout
- stderr
- exit code

Stdout and stderr should be stored with per-line timestamps.

This means:

- every stdout line gets a timestamp
- every stderr line gets a timestamp
- users can inspect hook execution history later

---

## Data That Must Be Preserved Per Hook Run

Each executed hook should eventually have a persisted run record containing at least:

- hook event name
- process id / agent-session id
- phase context if applicable
- skill context if applicable
- execution folder path
- exit code
- timestamped stdout log
- timestamped stderr log
- effective failure policy
- final result
  - success
  - failed
  - warned and continued

Exact schema can be refined later.

---

## Security / Trust Model

This hook system assumes the same trust boundary as the rest of the current platform:

- local machine
- or tailnet-reachable trusted environment

Hook scripts are arbitrary user-authored Python.

Therefore:

- they are trusted automation
- they are not sandboxed against the user
- they should not be treated as safe for hostile multi-tenant execution

This is acceptable for the current system model.

---

## Non-Goals For V1

The following are out of scope for the first version:

- arbitrary conditional hook triggers
- live process-instance hook editing during execution
- bash hooks
- per-hook dependency environments
- per-hook containers
- parallel hook execution
- execution inside tmux sessions
- materialized script source with substituted variables
- env-var-driven hook parameter passing as the primary contract

---

## Summary Of Current Decisions

- fixed lifecycle events only
- both workflow-level and process-instance hook sets exist
- process instances get copied hook definitions
- hooks are blocking
- multiple scripts on one event run serially in exact list order
- Python only
- reusable workflow-level hook assets live in `common-volume/hooks/<name>.py`
- hooks execute in a separate shared hook-runner container
- runner uses one central Python environment and one central `requirements.txt`
- execution folders live under `common-volume/hook_executions/<agent_id>/...`
- each fired hook event gets one deterministic execution folder
- all scripts for that event run in that one folder
- `scope_vars.json` is the standardized scope file
- orchestrator prepares folders, copies scripts, and writes scope
- runner only executes prepared folders and returns results
- unresolved scope values prevent execution
- failure policy is per hook, defaulting to `fail`
- supported failure policies are `fail` and `warn_and_continue`
- stdout and stderr are captured with per-line timestamps and retained for later inspection

---

## Open Items For Next Discussion

These still need concrete design decisions:

- exact `scope_vars.json` schema per event type
- exact identifier contract runner should receive from orchestrator
- exact persistence schema for hook run history
- UI model for creating and sequencing reusable hook assets beyond the current first pass
- UI model for attaching hook assets to workflow definitions beyond the current first pass
- UI model for showing hook execution logs and outcomes
- exact hook-runner container image contents and dependency policy
