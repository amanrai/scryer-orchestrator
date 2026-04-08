# scryer-orchestrator

Note: this project includes vibe-coded elements produced with Codex and Claude.

Orchestration backbone for Scryer.

## What This Is

`Scryer Orchestrator` is designed to provide a small, explicit orchestration core that can adapt to many different workflow shapes.

It is doing something more opinionated:

- keep the runtime model small
- keep orchestration state explicit
- make side effects happen in hooks
- let callers define behavior by composing scripts rather than by asking the orchestrator to own every domain concern

That is the “opinionated way of being unopinionated” here.

The orchestrator is opinionated about:

- workflow structure
- lifecycle boundaries
- notification-gated advancement
- runtime state materialization
- hook execution order

It is intentionally unopinionated about:

- what a workflow actually does
- which external systems it touches
- how git, secrets, tmux, PRs, or other integrations behave
- what business logic belongs in each step

Those are pushed into hook scripts and runtime assets.

## Core Contract

The core contract is:

- orchestrator maintains workflow state
- orchestrator materializes `state.json`
- orchestrator fires hooks in order
- scripts do external work
- workflow advancement happens through `POST /processes/notify`

That means the orchestrator is not supposed to silently “help” by completing lifecycle boundaries on its own when the contract is missing. If a lifecycle hook is required, the workflow should have that hook.

## Workflow Model

The structural model is:

- workflow
- phase
- step

Current scheduling model:

- phases are serial
- all pending steps in a phase dispatch together
- each running step owns its own tmux session lifecycle
- phase completion waits for every step in that phase to settle

## Runtime Model

Every hook fire gets a materialized runtime folder under `common-volume/hook-fires`.

Each fire writes:

- `state.json`
- the copied hook script

Each workflow also writes:

- `common-volume/hook-fires/<workflow_uuid>/logs.log`

The important thing is not just that hooks run. It is that hooks run with a clear, inspectable runtime envelope.

## state.json

`state.json` is the runtime contract between the orchestrator and hook code.

Important fields include:

- `workflow_uuid`
- `hook_event_name`
- `common_volume_root`
- `orchestrator_url`
- `tmuxer_url`
- `interaction_service_url`
- `secrets_service_url`
- `phase_number`
- `step_details`
- `project_identities_associated`
- `project_environment_variables_associated`
- `additional_caller_info`
- `workflow_definition`

The rule is simple:

- hooks must resolve environment-sensitive paths and service URLs from `state.json`
- hooks must not hardcode runtime locations

For skills, the orchestrator supports multiple ordered skill roots through `SKILLS_PATHS`.

- each root is scanned independently
- something only counts as a skill if it is a subfolder containing `SKILL.md`
- the first matching root wins when the same skill name exists in multiple roots
- create/edit/delete operations write to the first configured root

This makes it possible to keep downloaded skills separate from your own local skills while exposing both through one API surface.

## Hook Lifecycle

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

- workflow advancement is driven only by `POST /processes/notify`
- hook order is notification-gated rather than dispatch-gated
- missing lifecycle hooks are treated as contract errors, not silent backend fast paths
- the default operational stance is `OnError = Fail`
- where that is not fully imposed yet, it should be treated as the intended direction and will be imposed

## Why This Shape

This design gives you a useful split:

- the orchestrator owns the skeleton
- runtime scripts own the flesh

That is valuable because orchestration tends to become a mess when the engine tries to absorb every integration directly. By forcing git behavior, secrets behavior, tmux behavior, PR behavior, and step semantics out into hooks, the orchestrator stays smaller and more legible.

At the same time, it is not “anything goes.” The lifecycle, state model, and notification contract are strict. That is the opinionated part.

## What This Is Good At

- running structured multi-step workflows
- giving hooks a stable runtime contract
- coordinating hook execution without absorbing every integration detail
- exposing workflow, hook, and skill assets over API
- keeping enough event history and logs to debug runs

## What This Is Not Trying To Be

- a full built-in business workflow platform
- a giant integrations hub
- a hidden black-box agent runner
- a system where side effects are implicit and hard to inspect

## Environment

Primary runtime:

- Docker / infra stack
- port `8101`

For host-native runs, env-backed path and URL settings are supported through:

- `.env`
- `.machine-env`

## API Surface

High-level API groups include:

- workflows
- hooks
- skills
- processes
- events
- messaging

The most important runtime endpoint is:

- `POST /processes/notify`

That is the advancement path the hook contract is built around.

## Tests

There is now meaningful automated coverage around:

- shared runtime helper behavior
- hook adapter behavior
- `pre_step -> step` integration
- process notification behavior
- phase dispatch behavior
- live startup verification for the testing project
