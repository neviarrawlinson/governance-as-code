# Explicit synthetic history recovery

This procedure establishes a new **current-state** baseline after unavailable historical state. It does not reconstruct missing events, accept risk, enable MFA, or close issue #3. The original established lineage remains intact. Ordinary missing history continues to fail closed.

## Before recovery

Name the remediation coordinator and accountable reviewer. A maintainer can conduct a disclosed self-review for this educational demonstration; record that choice. Preserve current evidence and investigate external backups first. A surviving authoritative backup should be assessed separately; this workflow is an explicit rebaseline, not backup restoration.

## Preview

After this implementation is reviewed and merged, use GitHub Actions → **Explicit Governance History Recovery** → **Run workflow**, choose branch **main**, and leave mode **preview**. Download `synthetic-history-recovery-preview-<run-id>`.

Review the candidate state, every subject's evidence and checksums, `assurance-decisions.json`, and `recovery-manifest.json`. USR-004 must remain FAIL, evidence must verify, and no historical transitions or events should appear. The preview prints SHA-256 values for the candidate and manifest. Use the Actions API or artifact details to obtain the exact artifact ID; never substitute a similarly named artifact.

## Candidate-specific authorization

The named approver records the following JSON in a reviewed commit on main, under this directory. Replace every example value with the reviewed candidate's actual identifiers and dates. **This example is not an approval.** No authorization is committed by the implementation itself.

```json
{
  "schema_version": "1.0",
  "recovery_id": "YOUR-RECOVERY-ID",
  "repository": "neviarrawlinson/governance-as-code",
  "branch": "main",
  "control_id": "ACP-001-03",
  "preview_run_id": "ACTUAL-NUMERIC-RUN-ID",
  "preview_artifact_id": "ACTUAL-NUMERIC-ARTIFACT-ID",
  "source_commit": "ACTUAL-40-CHARACTER-PREVIEW-COMMIT",
  "evaluation_date": "YYYY-MM-DD",
  "candidate_sha256": "ACTUAL-CANDIDATE-SHA256",
  "manifest_sha256": "ACTUAL-MANIFEST-SHA256",
  "approver": "ACTUAL-GITHUB-LOGIN",
  "approved_at": "YYYY-MM-DD",
  "valid_until": "YYYY-MM-DD",
  "reason": "Reviewed evidence, reason for recovery, scope and known history gap",
  "history_gap_acknowledged": true,
  "review_mode": "disclosed_self_review",
  "related_issue": 3
}
```

Use `independent` only if an independent review actually occurred; otherwise explicitly use `disclosed_self_review`. Link the review decision in issue #3. Approval must postdate or equal evaluation, remain valid on promotion, and match the triggering actor. Never backdate approval.

The approval commit differs from the evaluated preview commit. Promotion reads authorization from the current default-branch commit and verifies evidence against a separate checkout of the exact preview commit. It does not regenerate a different candidate after approval.

## Promotion

Run the recovery workflow on main with mode **promote**, the approved preview run/artifact IDs, and the authorization path (for example `examples/machine-readable-control/recovery/recovery-001.json`). The named approver must initiate it. It validates API source identity, archive digest, pinned-source evidence, candidate-specific authorization and baseline freshness under concurrency shared with normal assurance.

Only a valid, nonconflicting candidate can publish `trusted-assurance-state.json` plus `recovery-receipt.json`. The receipt labels the boundary EXPLICIT_REBASELINE and the missing historical interval UNKNOWN. Matching prior uploads are idempotent; conflicts block. A newer baseline requires a new preview and approval.

Neither preview nor promotion has issues-write permission. Issue #3 remains open. After promotion succeeds, run normal assurance in dry-run mode and inspect its history resolution and USR-004 failure. Enabling MFA is a separate reviewed change; verified recovery and closure rationale must be recorded before authorizing live issue closure.

## Retention and limits

Preview artifacts last seven days. Authoritative state lasts 30 days. Preserve the recovery receipt and evidence externally before expiry, and monitor baseline renewal: persistent failure events in dry-run mode can prevent normal state advancement. This does not provide permanent state persistence or enterprise evidence retention. Recovery does not create production attestations or cryptographic approval signatures; authorization relies on reviewed repository state and GitHub execution provenance.
