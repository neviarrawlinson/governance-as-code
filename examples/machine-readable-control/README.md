# Machine-Readable Control

## Overview

This example is the second stage of the Governance as Code demonstration. The previous example showed how governance artifacts can be version-controlled and reviewed through an engineering workflow. This stage extends that concept by representing an individual governance control in a structured, machine-readable format.

**Human-Readable Policy → Machine-Readable Control → Automated Validation → Evidence → Continuous Assurance**

The example uses control `ACP-001-03`, Multifactor Authentication, from the existing [Access Control Policy](../version-controlled-policy/access-control-policy.md).

The objective is not to replace human-readable policies. A structured control definition creates a bridge between governance requirements and the technical mechanisms that may eventually validate those requirements.

## First Control Definition

[`ACP-001-03.yaml`](controls/ACP-001-03.yaml) is the first machine-readable control example. It represents the human-readable [`ACP-001-03` requirement](../version-controlled-policy/access-control-policy.md#acp-001-03-multifactor-authentication) in Version 1.1 of the Access Control Policy.

**Control Definition = What governance requires**

**Validation Logic = How the technical environment is evaluated against that requirement**

The YAML defines the governance requirement, not executable validation logic. Its `automation_status: implemented_demo` value indicates that validation exists for this synthetic demonstration; it does not describe production-ready automation. Its `mappings: []` value remains intentionally empty because framework mappings have not yet been defined. The YAML does not itself mean automated compliance or continuous assurance.

## Synthetic Environment Data

[`sample-data/identity-environment.json`](sample-data/identity-environment.json) represents fictional identity-system data used to demonstrate how a machine-readable governance requirement can eventually be evaluated against technical state.

All accounts and identifiers are synthetic. No production, personal, or organizational identity data is included. The dataset represents technical facts, not governance outcomes, so `PASS`, `FAIL`, `APPROVED_EXCEPTION`, and `NOT_APPLICABLE` are intentionally not stored in it.

Those outcomes are determined by validation logic that compares the technical state with [`ACP-001-03.yaml`](controls/ACP-001-03.yaml).

## Automated Validation

The validator reads the control's structured scope, evaluates each synthetic account, and returns one of four governance outcomes:

* `PASS` — The account is in scope and MFA is enabled.
* `FAIL` — The account is in scope, MFA is disabled, and no valid exception applies.
* `APPROVED_EXCEPTION` — The account is in scope and MFA is disabled, but the documented exception is approved, fully reviewed, and unexpired on the evaluation date.
* `NOT_APPLICABLE` — The account does not meet any scope condition, so the MFA requirement does not apply.

`APPROVED_EXCEPTION` is a governance outcome rather than a technical bypass. It records that designated risk, security, and governance conditions have been satisfied for a time-bound exception; it does not make MFA technically enabled.

From this directory, install the YAML dependency and run the tests and validator:

```text
python -m pip install -r requirements.txt
python -m unittest discover -s validation/tests -v
python -m validation.cli --evaluation-date 2026-08-22
```

This implementation evaluates synthetic data only and does not connect to a production identity system. It is an educational demonstration, not production-ready automation or continuous assurance.

## Structured Control Validation Evidence

Phase 4A extends the demonstration through this progression:

**Human-Readable Policy → Machine-Readable Control → Technical State → Governance Validation → Structured Control Validation Evidence**

The evidence layer consumes the existing validator results and produces one structured JSON record per evaluated subject. It does not recalculate governance outcomes. Each record preserves the control and policy context, evaluation date, subject, outcome, human-readable reason, source provenance, and relevant exception traceability.

Generate runtime evidence after validation with:

```text
python -m evidence.cli --evaluation-date 2026-08-22
```

Records are written to the ignored `generated-evidence/` directory and are not committed as source content. These artifacts support governance traceability, but evidence generation is not the same as evidence retention, and the records are not automatically sufficient audit evidence. This demonstration does not constitute continuous assurance.

## Evidence Integrity and Provenance

Phase 4B extends the demonstration through this progression:

**Policy → Machine-Readable Control → Technical State → Governance Validation → Structured Evidence → Integrity Verification**

SHA-256 hashes bind each evidence record to the exact machine-readable control, synthetic environment input, and validator content referenced during generation. A detached `.sha256` checksum is written beside each JSON record so the complete serialized artifact can be checked for later modification. When Git metadata is available, the evidence provenance also records the repository commit associated with generation.

Verify the generated records and current source files with:

```text
python -m evidence.verify_cli
```

Integrity verification reports `VERIFIED` or `MISMATCH` and identifies each mismatched component. Integrity status is separate from the governance outcome: a `PASS` result with `MISMATCH` integrity should not be treated as equivalent to a `PASS` result whose evidence verifies successfully.

Hashing demonstrates integrity checking, not authenticity, trustworthiness, nonrepudiation, or audit sufficiency. A Git commit identifier provides repository-state provenance but does not independently prove artifact authenticity or integrity. This example remains synthetic and educational; evidence retention and continuous assurance have not been implemented.

## Continuous Assurance Decision Model

Phase 5A extends the demonstration through this progression:

**Policy → Machine-Readable Control → Technical State → Governance Validation → Structured Evidence → Integrity Verification → Assurance Decision**

The decision engine consumes existing governance and integrity results and classifies the appropriate assurance action. It does not recalculate control compliance or evidence integrity.

**Governance Outcome** = what the control state is

**Integrity Status** = whether supporting evidence verifies against known provenance

**Assurance Action** = what governance should do with that information

The primary decision matrix is:

| Governance outcome | Integrity status | Assurance action |
| --- | --- | --- |
| `PASS` | `VERIFIED` | `RECORD` |
| `NOT_APPLICABLE` | `VERIFIED` | `RECORD` |
| `APPROVED_EXCEPTION` | `VERIFIED` | `REVIEW` |
| `FAIL` | `VERIFIED` | `ESCALATE` |
| Any governance outcome | `MISMATCH` | `HALT_TRUST` |

When a previous governance outcome is available, the engine also identifies named state transitions such as a new failure, persistent failure, recovery, new approved exception, or stable state. Other valid changes use the generic `<PREVIOUS>_TO_<CURRENT>` form without assigning additional governance significance. A transition never overrides integrity: every `MISMATCH` produces `HALT_TRUST`.

This phase determines an action classification only. It does not send notifications, create tickets or GitHub issues, perform remediation, change technical systems, retain evidence, schedule execution, or constitute a production continuous-assurance platform.

## Automated Governance Execution

Phase 5B extends the demonstration through this progression:

**Policy → Machine-Readable Control → Technical State → Governance Validation → Structured Evidence → Integrity Verification → Assurance Decision → Automated Execution**

The reusable pipeline runner orchestrates the approved validation, evidence, integrity, and assurance components. It produces one structured assurance decision per synthetic subject and a human-readable run summary with subject-level results and aggregate counts.

Run the pipeline locally with a reproducible evaluation date:

```text
python -m automation.cli --evaluation-date 2026-08-22 \
  --state-resolution generated-assurance/trusted-state-resolution.json \
  --previous-state /path/to/trusted-assurance-state.json
```

When `--evaluation-date` is omitted, the pipeline uses the current UTC execution date. The workflow creates the required trusted-history resolution handoff before invoking this command. A prior state path is supplied only when that resolution confirms an eligible, valid authoritative baseline; history is never inferred from artifact absence.

The GitHub Actions workflow supports three triggers:

* Relevant changes to the machine-readable control, validation, evidence, assurance, automation, sample-data, or workflow implementation.
* Manual execution through `workflow_dispatch`.
* Weekly scheduled evaluation every Monday at `06:00 UTC`.

The weekly schedule demonstrates periodic reevaluation of the synthetic environment; it is not production continuous monitoring.

**Governance failure is not pipeline failure.** A verified `FAIL` produces `ESCALATE`, is reported in the summary, and allows execution to complete successfully. A verified approved exception similarly produces `REVIEW` without failing execution.

**Integrity failure is pipeline failure.** Any `MISMATCH` produces `HALT_TRUST`, causes a nonzero pipeline result, and stops reliance on the affected assurance result until the integrity concern is investigated.

Runtime evidence, detached checksums, structured decisions, and summaries are written beneath the ignored `generated-assurance/` directory. GitHub Actions uploads that directory as a clearly named synthetic demonstration artifact with seven-day retention. This bounded artifact storage is not an enterprise evidence-retention system, and no runtime evidence is committed automatically.

This automation is synthetic and educational. It is not production continuous monitoring, automated remediation, a production identity integration, or a deployment mechanism.

## Trusted Assurance State and Historical Comparison

Phase 6 extends the demonstration through this progression:

**Policy → Machine-Readable Control → Technical State → Validation → Evidence → Integrity → Assurance Decision → Automated Execution → Historical Comparison**

Historical comparison gives governance changes meaning that a single point-in-time result cannot provide. The pipeline can load the most recent prior trusted state, match subjects by stable account ID, and pass each prior outcome into the existing assurance decision engine. This enables classifications such as new failures, persistent failures, recoveries, and changes involving approved exceptions without recreating transition logic in the persistence layer.

The trusted-state artifact contains only the control ID, evaluation date, subject IDs, and governance outcomes. It does not contain evidence records or technical environment details. Subjects newly appearing in the current environment have no prior outcome and therefore no transition. Subjects present only in prior state are listed separately in the run summary without being assigned a governance outcome.

Only a run whose evidence integrity remains `VERIFIED` for every subject may produce a candidate `trusted-assurance-state.json`. A dry-run that generates governance events does not promote that candidate, because doing so would consume transitions before an authorized workflow can process them. A verified dry-run with no governance events may advance the baseline. When live issue processing is explicitly authorized, the candidate becomes authoritative only after the live workflow completes successfully. If any result is `MISMATCH`, the pipeline produces `HALT_TRUST`, fails execution, and does not replace the prior trusted baseline.

Runtime state remains separate from source-controlled governance definitions and is never committed automatically. For this educational demonstration, GitHub Actions retrieves the newest unexpired trusted-state artifact for the current branch and retains a successfully promoted replacement for 30 days. This bounded artifact mechanism is not an enterprise assurance database or evidence-retention platform.

## Trusted-State Lineage and Fail-Closed Resolution

Phase 8C-1 adds a source-controlled lineage declaration for `ACP-001-03` so GitHub Actions artifact absence cannot be mistaken for proof that the control has never had authoritative history. The declaration records an `ESTABLISHED` lineage anchored to the production-verified Run #14 state (run `32799613802`, artifact `9546047131`, evaluation date `2026-08-22`). Artifact presence or absence cannot change that declaration.

Retrieval now reports raw conditions separately from their governance interpretation. The resolution layer distinguishes a valid state from absence, detectable expiration, retrieval or download unavailability, invalid state content, ineligible provenance, and a resolution stage that was not reached. The existing version 1 trusted-state structure remains supported; Phase 8C-1 does not require historical artifacts to contain metadata that did not exist when they were published.

For this established lineage, unresolved history fails closed. Current validation, evidence generation, and integrity verification may still produce a point-in-time observation, but the run does not claim historical transitions, does not generate history-dependent governance events, cannot reach GitHub Issue writes, cannot promote a replacement trusted state, and reports that explicit recovery is required. Evidence-integrity failure remains a separate condition from trusted-history resolution failure.

This phase does not provide bootstrap, restoration, re-baselining, retention changes, a version 2 state schema, publication receipts, or cryptographic provenance. The trusted-state artifact retains its existing 30-day retention; recovery execution will be designed separately.

## Structured Governance Events

Phase 7A translates existing assurance decisions into workflow-neutral structured governance events:

**Assurance Decision → Governance Event → Future Workflow Integration**

The event layer consumes the approved governance outcome, integrity status, assurance action, and transition classification without recalculating them. It creates events for meaningful changes such as new or persistent failures, recoveries, lapsed or newly approved exceptions, and integrity incidents. Integrity incidents take priority over transition-based events.

Stable `PASS`, `APPROVED_EXCEPTION`, and `NOT_APPLICABLE` states do not automatically create new events. This avoids producing duplicate workflow signals when an approved or healthy state has not changed. Runtime event JSON files are written beneath the ignored `generated-assurance/events/` directory and are not committed as source content.

The event layer is intentionally decoupled from external workflow platforms. Phase 7A does not create GitHub Issues, Jira tickets, notifications, or remediation actions; those remain possible future integrations rather than behavior of this demonstration.

## Governance Workflow Integration

Phase 7B extends the demonstration through this progression:

**Policy → Machine-Readable Control → Technical State → Validation → Evidence → Integrity → Assurance Decision → Historical Comparison → Governance Event → Workflow Integration**

The integration follows a deliberately separated flow:

**Governance Event → Workflow Integration → Human Review**

GitHub Issues is the first demonstration workflow target. The dedicated integration consumes existing structured governance events and translates them into proposed issue creation, comment, closure, or no-action operations without recalculating governance outcomes, integrity, assurance actions, transitions, event types, or severity.

Deterministic, category-specific correlation markers support idempotency. Persistent conditions can therefore update an existing workflow rather than create duplicate issues, while control failures, approved-exception reviews, and integrity incidents remain distinct for the same control and subject. A verified recovery can comment on and close an existing correlated control-failure issue; it does not invent or close workflow history when no matching open issue exists. Stable states produce no issue activity.

Phase 7B operates in dry-run mode in GitHub Actions. The integration performs read-only lookup and shows the proposed operations in the workflow summary and an ignored runtime JSON artifact, but it does not create labels or issues, add comments, or close issues. Push, scheduled, and manual workflow triggers all use this same dry-run-only path and receive no `issues: write` permission.

GitHub Issue creation represents workflow initiation only. It is not governance approval, risk acceptance, remediation authorization, technical remediation, policy approval, or control-owner attestation. This demonstration does not integrate with other workflow platforms or production systems.

## Controlled Live Governance Workflow

Phase 7C adds an explicitly authorized manual path from the existing dry-run plan to live GitHub Issue operations:

**Automated Assurance → Governance Event → Dry-Run Workflow Plan → Explicit Human Authorization → Live Workflow Action**

Push-triggered and scheduled runs remain dry-run only. A manually dispatched run also defaults to dry-run because the boolean `live_issue_workflow` input defaults to `false`. The separate write-capable job can run only when the event is actually `workflow_dispatch`, the input is explicitly set to `true`, and the assurance job has successfully produced the dry-run workflow plan.

The live job downloads the runtime artifact from that assurance run and passes its existing structured governance events to the Phase 7B integration with `--live`. It does not rerun validation, manufacture a failure, or recalculate governance outcomes, integrity status, assurance actions, transitions, event types, or severity. The pipeline must report an authenticated terminal status of `verified` or `integrity_halt`; unexpected execution failures do not authorize dry-run planning or live action. Existing correlation and event markers preserve idempotency for creation, updates, recovery closure, and partial retries.

Trusted-state publication is a separate lifecycle step. Push, scheduled, and manual dry-runs can calculate and retain a candidate state, but a dry-run with pending governance events does not advance the authoritative baseline. An explicitly authorized live run promotes its candidate only after successful workflow processing. This preserves actionable transitions for the live integration while keeping push and scheduled execution read-only for GitHub Issues.

Permissions remain separated by job. Normal assurance and dry-run processing have `issues: read`; only the explicitly gated live job has `issues: write`. A genuine `INTEGRITY_INCIDENT` can initiate its issue workflow in authorized live mode, while `MISMATCH → HALT_TRUST` still fails assurance execution and prevents trusted-state advancement.

Live issue activity remains workflow initiation, not risk acceptance, remediation authorization, governance approval, policy approval, or control-owner attestation. Enabling the manual input authorizes only the existing bounded `CREATE_ISSUE`, `COMMENT_ISSUE`, `CLOSE_ISSUE`, and `NO_ACTION` behavior.

## Assurance Lifecycle Observability and Diagnostics

Phase 8B adds a descriptive view of the complete assurance lifecycle without changing any governance decision or workflow behavior. A final read-only job runs after assurance, authorized live processing, and trusted-state publication have reached their outcomes. It produces deterministic structured JSON and a concise **Governance Assurance Lifecycle** Markdown summary.

The diagnostic record keeps governance outcomes, integrity status, assurance actions, transitions, governance events, workflow operations, and trusted-state publication separate. It identifies the prior trusted-state source when available, aggregates current results, distinguishes proposed operations from executed operations, records the existing publication decision and reason verbatim, and describes bounded lifecycle failures such as retrieval failure or integrity halt.

Diagnostics are non-authoritative. They do not rerun validation, verify evidence, calculate transitions, generate events, authorize live execution, determine publication eligibility, or change workflow success and failure semantics. A diagnostic rendering or upload problem cannot prevent an otherwise eligible trusted-state publication. Conversely, diagnostics cannot turn a failed assurance lifecycle into a successful one.

The JSON and Markdown files are uploaded as the separate `synthetic-governance-lifecycle-diagnostics-<run-id>` runtime artifact with seven-day retention. They contain lifecycle metadata rather than credentials, environment dumps, evidence payloads, integrity hashes, file contents, or raw GitHub API responses. This bounded runtime artifact is not a long-term observability, evidence-retention, or audit system.

## What We Will Build

1. Define `ACP-001-03` in a structured YAML format.
2. Map the structured control back to the human-readable policy.
3. Define how the control can be validated.
4. Generate evidence from validation results.
5. Demonstrate how those results can support continuous assurance.

The control definition, synthetic validation, Structured Control Validation Evidence generation, integrity verification, assurance decision, automated execution, bounded historical comparison, structured governance events, dry-run GitHub workflow planning, and explicitly authorized live GitHub workflow path are now included. Enterprise state persistence, enterprise evidence retention, other external workflow integrations, and production continuous-assurance capabilities are not implemented.
