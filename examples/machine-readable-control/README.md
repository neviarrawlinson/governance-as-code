# Machine-Readable Control

## Overview

This example is the second stage of the Governance as Code demonstration. The previous example showed how governance artifacts can be version-controlled and reviewed through an engineering workflow. This stage extends that concept by representing an individual governance control in a structured, machine-readable format.

**Human-Readable Policy → Machine-Readable Control → Automated Validation → Evidence → Continuous Assurance**

The example will use control `ACP-001-03`, Multifactor Authentication, from the existing [Access Control Policy](../version-controlled-policy/access-control-policy.md).

The objective is not to replace human-readable policies. A structured control definition creates a bridge between governance requirements and the technical mechanisms that may eventually validate those requirements.

## What We Will Build

1. Define `ACP-001-03` in a structured YAML format.
2. Map the structured control back to the human-readable policy.
3. Define how the control can be validated.
4. Generate evidence from validation results.
5. Demonstrate how those results can support continuous assurance.

These later capabilities are planned but are not implemented yet.
