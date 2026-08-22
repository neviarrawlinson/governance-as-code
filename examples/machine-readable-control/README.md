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

## What We Will Build

1. Define `ACP-001-03` in a structured YAML format.
2. Map the structured control back to the human-readable policy.
3. Define how the control can be validated.
4. Generate evidence from validation results.
5. Demonstrate how those results can support continuous assurance.

The control definition, synthetic validation, Structured Control Validation Evidence generation, and integrity verification demonstration are now included. Evidence retention and continuous assurance capabilities are not implemented.
