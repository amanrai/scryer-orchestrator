# Scryer Hook Helper Architecture

## Purpose

This document defines the target internal architecture for native Scryer hook helper libraries.

The goal is to divide native Scryer hook-side logic into three abstraction layers:

- helper methods
- functionalities
- commands

This is an internal implementation standard.

It is not enforced in code.
It is enforced by us.

## Scope

This document applies only to the native Scryer hook-helper library surface.

It does not apply to all native Scryer system boundaries globally.

This distinction matters.

There are two separate concepts:

- native Scryer libraries
  The shared hook-side helper surface we are designing here
- native Scryer systems
  Other systems Scryer is composed of, such as orchestrator, tmuxer, secrets service, PM, interactor, and related services

A helper may call another native Scryer system.
That is not, by itself, a violation of the abstraction rules in this document.

## Goals

The layer split exists to improve all of the following equally:

- maintainability
- clarity of abstraction
- testability
- reuse
- safety

None of these goals is secondary.

## The Three Layers

### Helper Methods

Helper methods are the lowest-level native Scryer hook helpers.

They are:

- atomic
- narrow
- technical
- close to external systems or primitive local operations

Examples:

- talk to the secrets service
- talk to tmuxer
- execute a single git command
- read `state.json`
- write a file
- parse one remote URL
- send one process notification

Preferred implementation style:

- plain functions

Helpers may know about `state.json`.
That is allowed.

Even so, the preferred style is still to keep helpers reusable and avoid excessive workflow-specific interpretation there when practical.

### Functionalities

Functionalities are one level above helpers.

They represent bounded domain capabilities assembled from lower-level primitives.

Examples:

- make a worktree
- resolve identities
- resolve environment variables
- get all secrets
- derive a step session name
- discover PR metadata

Preferred implementation style:

- typed internal models may be used where contract clarity helps
- composition should read more clearly than a pile of raw helper calls

Functionalities may still contain direct operational code when needed.
That is allowed.

The preferred style, though, is for them to read as compositions of helpers.

### Commands

Commands are the highest abstraction layer inside the native Scryer hook-helper library surface.

They are reusable high-level operational units.

A command is a unit of work.

Examples:

- prepare agent session in filesystem
- provision local agent runtime config
- launch step execution session
- finalize workflow git flow

Important clarification:

- a command is not defined as “everything one hook script does”
- a single hook script may call multiple commands

Preferred implementation style:

- typed internal models may be used where contract clarity helps
- commands should read like high-level coordinators

Commands may still contain direct operational code when needed.
That is allowed.

The preferred style, though, is for them to read as higher-level coordinators over lower abstractions.

## Architectural Dependency Goal

Within the native Scryer hook-helper library surface, the target dependency graph is:

- hooks -> commands
- commands -> functionalities
- functionalities -> helpers
- helpers -> non-native libraries and external systems

This is the architectural goal.

This is the intended interaction pattern inside native Scryer hook helpers.

## Critical Rule

The most important rule is:

- lower layers should not depend upward

Concretely:

- helpers should not depend on functionalities or commands
- functionalities should not depend on commands
- commands should not depend on hooks

This is the core rule because once upward dependencies appear, the abstraction stack collapses.

We may not be able to enforce this mechanically in every case.
But we should treat it as a critical implementation rule in our own code.

## Working Rules

The intended rules are:

- hooks may call commands
- commands should not call commands
- functionalities should not call functionalities
- helpers should not call helpers
- lower layers should not depend upward

These rules are the target shape.

They are not enforced in code.
They are enforced by us.

## Pragmatism

We should not make the perfect the enemy of the good.

That means:

- speed of development matters
- temporary deviations may happen while building quickly
- direct implementation code may sometimes live at a higher layer than ideal
- `state.json` access is allowed in any layer

But the long-term target remains the same:

- hooks sequence commands
- commands read as command-scale operations
- functionalities read as bounded domain capabilities
- helpers remain the atomic technical layer

This document defines the target architecture, not a reason to block forward motion unnecessarily.

## Preferred Versus Allowed

The preferred style is:

- hooks sequence commands
- commands compose functionalities
- functionalities compose helpers
- helpers remain fully atomic

What is allowed in practice:

- commands may contain direct operational code
- functionalities may contain direct low-level work
- helpers may access `state.json`

The fact that something is allowed does not make it the preferred shape.

## Models and Contracts

Internal typed models are encouraged at higher layers when they improve clarity and safety.

Preferred guidance:

- helpers: plain functions by default
- functionalities: may use models for internal contracts
- commands: may use models for internal contracts

These are internal Python models.

They are not the same thing as the hook runtime `state.json` contract.

We explicitly do not want `state.json` to become overly restrictive.
Hook authors should still be able to pass what they need to.

## Naming Guidance

Naming conventions by layer are recommended.

They are not enforced in code.

The goal is that a file or function should ideally read as obviously one of:

- a helper
- a functionality
- a command

This improves readability and maintenance, but it is guidance rather than a code-enforced rule.

## Notifications As A Good Example Of Layering

The same concern may exist at multiple abstraction levels as long as it is expressed correctly at each layer.

Example:

- helper: `notify_process(workflow_uuid, event, ...)`
- higher abstraction: `mark_done()`

This is good design.

It is not duplication.

It is the same concern expressed at different abstraction levels.

## Hook Scripts

Hook scripts remain the top-level orchestration surface for the hook runtime.

Their normal shape should be:

1. load runtime state
2. call one or more commands
3. log
4. notify success or failure

A single hook script may require multiple command-scale operations.
That is expected.

The hook script is the normal place where multiple command units are sequenced.

## Migration View

Current libraries such as:

- `scryer_resolver.py`
- `scryer_git.py`

should be treated as current pragmatic helper-heavy libraries, not as the final architectural shape.

They are likely to be decomposed over time across the three abstraction layers described here.

Likewise, existing hook scripts may still be somewhat pragmatic during active development.

But before release:

- this layered model should be established in the implementation
- we should refactor the native Scryer hook helper surface toward this target architecture

## Filesystem Layout

This document does not lock the final filesystem or package layout yet.

We may eventually choose:

- one package-style area
- separate files by layer
- some other structure that still preserves the abstractions

That decision can be made later.

For now, the abstraction boundaries matter more than the final directory layout.

## Summary

The intended internal architecture for native Scryer hook helpers is:

- helper methods for atomic technical operations
- functionalities for bounded domain capabilities
- commands for reusable high-level units of work

The critical rule is:

- no upward dependencies from lower layers

The target interaction graph is:

- hooks -> commands
- commands -> functionalities
- functionalities -> helpers
- helpers -> non-native libraries and external systems

This architecture is not code-enforced.
It is an internal implementation standard enforced by us.

It exists to improve:

- maintainability
- clarity of abstraction
- testability
- reuse
- safety
