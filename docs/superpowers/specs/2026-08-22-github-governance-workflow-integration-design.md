# GitHub Governance Workflow Integration Design

## Scope

Phase 7B translates existing Phase 7A structured governance events into GitHub Issue operation plans. It does not recalculate validation, evidence integrity, assurance decisions, transitions, event types, or severity. Push and scheduled GitHub Actions runs operate in dry-run mode and cannot modify issues.

## Architecture

The integration lives in `examples/machine-readable-control/integrations/github/`. A workflow planner consumes `GovernanceEvent` values and queries an injected issue gateway for an existing open issue with an exact correlation marker. It returns structured `CREATE_ISSUE`, `COMMENT_ISSUE`, `CLOSE_ISSUE`, or `NO_ACTION` operations. A separate executor performs operations only when explicitly invoked outside dry-run mode.

The production gateway contains GitHub API behavior. Tests use an in-memory fake, keeping the event generator and assurance pipeline platform-neutral:

`Assurance Decision → Structured Governance Event → GitHub Issues Integration`

## Correlation and Idempotency

Correlation identifiers use the stable form `gac-v1:<category>:<control-id>:<subject-id>` and appear in issue bodies as an HTML comment marker. Categories are `control-failure`, `exception-review`, and `integrity-incident`, so workflows for the same control and subject cannot collide. Matching scans open issues carrying the `governance-as-code` label and compares the exact marker rather than relying on titles.

Control-failure opened events create a missing workflow and do nothing when one is already open. Persistent failures comment on an existing workflow. When no correlated issue exists, they create a recovery issue whose structured operation and body explicitly state that the current failure is persistent but the original opening event was not observed. Recovery events comment and close only a matching open control-failure issue. Exception lapse shares the control-failure workflow; new exception reviews and integrity incidents use independent workflows.

## Issue Content and Labels

Every created issue includes the event's control, subject, outcome, integrity status, assurance action, transition, event type, severity, evaluation date, reason, human-review requirement, correlation identifier, and a synthetic-demonstration notice. All created issues use `governance-as-code` plus exactly one category label. Live execution may safely ensure these bounded labels exist before creation; dry-run performs no label or issue writes.

## Dry-Run and Workflow Behavior

The CLI loads the real runtime event JSON files, performs read-only correlation lookup, writes a structured operation-plan artifact, and appends proposed operations to the GitHub Actions summary. Dry-run is the default and performs no create, comment, close, or label operations. The workflow grants only `issues: read` in addition to its existing permissions and invokes dry-run for push, schedule, and manual triggers. No live workflow path is enabled in Phase 7B.

## Testing and Boundaries

Tests exercise the planner and executor through an in-memory gateway, including mappings, missing-history behavior, recovery closure ordering, idempotency, category separation, required content and labels, and zero-write dry-run behavior. Workflow tests verify read-only permissions and dry-run invocation. Existing Phase 3 through Phase 7A suites remain regression coverage.

This phase does not add other workflow platforms, notifications, approvals, risk acceptance, remediation, dashboards, production integrations, controls, or framework mappings. Workflow initiation is not governance approval.
