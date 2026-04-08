# Release Checklist

This checklist is for shipping the core Scryer plumbing:
- PM
- vault/secrets
- new orchestrator
- tmuxer/session lifecycle
- hook/runtime contract
- git/worktree primitives

It is intentionally focused on operational confidence, not UI completeness.

## 1. Environment

- [ ] `start-all.sh` reliably brings up the supported runtime
- [ ] `stop-all.sh` reliably tears the supported runtime down
- [ ] `rebuild-all.sh` reliably rebuilds and restarts the supported runtime
- [ ] secrets service, Valkey, tmuxer, and `new_orchestrator` start in the expected order
- [ ] the shipped path does not depend on `.machine-env`
- [ ] required ports are documented and reachable
- [ ] no critical component depends on host-only paths in the release configuration

## 2. Runtime Contract

- [x] every hook gets required runtime values from `state.json`
- [x] no hook hardcodes orchestrator URLs
- [x] no hook hardcodes tmuxer URLs
- [x] no hook hardcodes interaction-service URLs
- [x] no hook hardcodes secrets-service URLs
- [x] no hook hardcodes common-volume paths
- [x] session naming contract is deterministic and documented
- [x] repo/session path contract is deterministic and documented
- [x] workflow state schema matches what hooks actually consume

## 3. Workflow Execution

- [ ] `pre_workflow` succeeds for a linked-repo project
- [ ] `pre_workflow` succeeds for a no-repo project
- [ ] `pre_step`, `step`, and `post_step` sequencing is correct
- [ ] steps in a phase dispatch according to the intended model
- [ ] `POST /processes/notify` is the only workflow advancement path
- [ ] failures move workflows into the correct terminal state
- [ ] timeouts, kills, and failures do not leave workflows in ambiguous state

## 4. Secrets And Identity

- [ ] project-selected identities are passed into runtime correctly
- [ ] project-selected environment variables are passed into runtime correctly
- [ ] unlocked vault resolves runtime secrets successfully
- [ ] locked vault fails early and clearly
- [ ] missing identity produces a clear failure
- [ ] missing variable produces a clear failure

## 5. Tmux And Session Lifecycle

- [ ] step launch creates the expected tmux session
- [ ] UI can attach to the running session
- [ ] session naming is derived from workflow instance, phase, and step
- [ ] completed sessions are handled consistently
- [ ] tmuxer trust/untrust calls work in the shipped runtime
- [ ] internal `orch-*` hook runner sessions do not leak into user-facing attach paths

## 6. Git And Repo Handling

- [ ] linked repo creates a fresh worktree
- [ ] missing repo link falls back to clean repo initialization
- [ ] interactor scaffold is copied into the session repo correctly
- [ ] skills are copied into the session repo correctly
- [ ] agent config files are written correctly
- [ ] transient agent directories are excluded from commit/PR paths
- [ ] worktree preservation/cleanup behavior is intentional and documented

## 7. PM Visibility

- [ ] active runs are visible in the PM UI
- [ ] archived runs are visible in the PM UI
- [ ] active polling is not excessively noisy
- [ ] process detail reflects real current state
- [ ] project-selected identities are visible and editable in the PM UI
- [ ] project-selected environment variables are visible and editable in the PM UI
- [ ] arbitrary task properties work end to end

## 8. Post-Workflow And PR Path

- [ ] missing `pr.md` logs and exits cleanly
- [ ] PR artifact plus configured remote behaves correctly
- [ ] missing remote degrades cleanly
- [ ] missing identity degrades cleanly
- [ ] no-ahead-commits path degrades cleanly
- [ ] no silent post-workflow failures

## 9. Tests

- [ ] shared resolver/helper tests pass
- [ ] hook adapter tests pass
- [ ] step launch tests pass
- [ ] process notification tests pass
- [ ] live dummy workflow test passes
- [ ] live linked-repo workflow test passes
- [ ] locked-vault failure test passes

## 10. Documentation

- [ ] `handoff.md` reflects the actual runtime
- [ ] secrets README reflects actual usage
- [ ] startup commands are documented
- [ ] runtime contract is documented
- [ ] known limitations are documented explicitly

## 11. Pre-Ship Cleanup

- [ ] sample/demo hooks are removed, renamed, or clearly marked non-production
- [ ] sample/demo skills are removed, renamed, or clearly marked non-production
- [ ] old orchestrator references are fully retired or clearly marked legacy
- [ ] dead script paths are not referenced by UI, hooks, or docs
- [ ] workflow execution uses a stable workflow ID rather than `workflow_name` as the primary cross-system identifier

## Signoff

### Must Pass Before Ship

- [ ] Environment
- [ ] Runtime Contract
- [ ] Workflow Execution
- [ ] Secrets And Identity
- [ ] Tmux And Session Lifecycle
- [ ] PM Visibility
- [ ] Documentation

### Should Pass Before Ship

- [ ] Git And Repo Handling
- [ ] Post-Workflow And PR Path
- [ ] Live linked-repo workflow tests

### Can Ship Later

- [ ] alternate UI
- [ ] nicer UX polish
- [ ] richer PR/review actions
- [ ] non-core workflow variants
