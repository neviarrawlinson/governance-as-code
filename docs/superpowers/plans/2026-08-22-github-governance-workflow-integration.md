# GitHub Governance Workflow Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Translate existing structured governance events into idempotent GitHub Issue workflow operations with a safe dry-run Actions integration.

**Architecture:** A dedicated GitHub integration package plans operations from immutable Phase 7A events through an injected issue gateway. GitHub API behavior, operation execution, and CLI presentation remain separate from event and assurance logic.

**Tech Stack:** Python 3.12 standard library, `unittest`, GitHub REST API, GitHub Actions YAML.

**Spec:** `docs/superpowers/specs/2026-08-22-github-governance-workflow-integration-design.md`

## Global Constraints

- Consume existing Phase 7A events without recalculating governance semantics.
- Push and scheduled workflows remain dry-run only and receive no `issues: write` permission.
- Tests and verification must not create, modify, comment on, or close live GitHub issues.
- Runtime operation plans remain beneath ignored `generated-assurance/` storage.

---

### Task 1: Structured Issue Operation Planner

**Files:**
- Create: `examples/machine-readable-control/integrations/__init__.py`
- Create: `examples/machine-readable-control/integrations/github/__init__.py`
- Create: `examples/machine-readable-control/integrations/github/issues.py`
- Create: `examples/machine-readable-control/integrations/github/tests/test_issues.py`

**Interfaces:**
- Consumes: `events.generator.GovernanceEvent` and an `IssueGateway` implementation.
- Produces: `IssueOperation`, deterministic `correlation_id()`, `plan_event_operations()`, and `process_events()`.

- [ ] Write tests with literal expected mappings, correlation IDs, labels, issue content, idempotent matches, missing-history behavior, and dry-run zero writes.
- [ ] Run the focused suite and confirm failure because the integration package is absent.
- [ ] Implement the minimal models, gateway protocol, planner, and executor required by the tests.
- [ ] Run the focused suite until all integration behavior passes.

### Task 2: GitHub API Gateway and Dry-Run CLI

**Files:**
- Create: `examples/machine-readable-control/integrations/github/client.py`
- Create: `examples/machine-readable-control/integrations/github/cli.py`
- Create: `examples/machine-readable-control/integrations/github/tests/test_cli.py`

**Interfaces:**
- Consumes: runtime event JSON, repository name, token, and optional GitHub summary path.
- Produces: `generated-assurance/github-issue-operations.json` and a Markdown dry-run summary.

- [ ] Write tests proving event JSON loading, structured JSON serialization, summary rendering, default dry-run, and zero GitHub writes.
- [ ] Run the focused tests and confirm failure for the missing client and CLI behavior.
- [ ] Implement paginated read lookup plus bounded write methods behind the gateway, and a dry-run-default CLI.
- [ ] Run all GitHub integration tests until green.

### Task 3: Pipeline Workflow and Documentation Integration

**Files:**
- Modify: `.github/workflows/governance-assurance.yml`
- Modify: `examples/machine-readable-control/automation/tests/test_pipeline.py`
- Modify: `examples/machine-readable-control/README.md`

**Interfaces:**
- Consumes: runtime event files produced by the existing pipeline.
- Produces: dry-run operation plans and GitHub Actions summary content.

- [ ] Add failing workflow tests for integration path coverage, integration tests, `issues: read`, absence of `issues: write`, and explicit `--dry-run` execution.
- [ ] Run automation tests and confirm the new expectations fail.
- [ ] Add the dry-run workflow step and concise Phase 7B documentation without changing existing triggers or governance behavior.
- [ ] Run automation and integration suites until green.

### Task 4: Regression, Demonstration, Review, and Delivery

**Files:**
- Verify all files above; add no runtime artifacts.

**Interfaces:**
- Consumes: complete repository changes.
- Produces: verified commit on `origin/main`.

- [ ] Run all Phase 3 through Phase 7B tests and validate workflow YAML.
- [ ] Demonstrate all six event workflows, idempotent matching, category separation, and zero dry-run writes with controlled fakes.
- [ ] Confirm runtime operation plans are ignored, run `git diff --check`, and review the exact diff.
- [ ] Obtain independent code review and resolve findings with regression tests.
- [ ] Commit as `Add GitHub governance workflow integration`, push `main`, and verify local and remote SHAs match.
