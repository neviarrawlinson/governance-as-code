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

The YAML defines the governance requirement, not executable validation logic. Its `automation_status: planned` value is intentional because automated validation has not yet been implemented. Its `mappings: []` value is also intentionally empty because framework mappings have not yet been defined. The YAML does not itself mean automated compliance or continuous assurance.

## Synthetic Environment Data

[`sample-data/identity-environment.json`](sample-data/identity-environment.json) represents fictional identity-system data used to demonstrate how a machine-readable governance requirement can eventually be evaluated against technical state.

All accounts and identifiers are synthetic. No production, personal, or organizational identity data is included. The dataset represents technical facts, not governance outcomes, so `PASS`, `FAIL`, and `APPROVED_EXCEPTION` are intentionally not stored in it.

Those outcomes will later be determined by validation logic that compares the technical state with [`ACP-001-03.yaml`](controls/ACP-001-03.yaml). Automated validation has not yet been implemented.

## What We Will Build

1. Define `ACP-001-03` in a structured YAML format.
2. Map the structured control back to the human-readable policy.
3. Define how the control can be validated.
4. Generate evidence from validation results.
5. Demonstrate how those results can support continuous assurance.

The control definition is now included. The later validation, evidence, and continuous assurance capabilities are planned but are not implemented yet.
