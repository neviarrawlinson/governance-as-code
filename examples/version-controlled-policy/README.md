# Version-Controlled Policy Management

## Overview

Governance policies are living documents. Requirements change, regulations evolve, systems are updated, and organizations continuously make decisions that affect how policies should operate.

Traditional policy management often relies on static documents, shared drives, email approvals, and manual version histories. While these approaches can document a policy, they can make it difficult to understand exactly what changed, who changed it, why the change occurred, and how the policy evolved over time.

Version-controlled policy management applies software engineering version-control practices to governance artifacts.

Instead of treating a policy as a static document, the policy becomes a governed artifact with a traceable history.

## The Governance Problem

Consider an organization's Access Control Policy.

Over time, the organization may need to:

* Add requirements for multifactor authentication
* Change access review frequency
* Update privileged access requirements
* Modify control ownership
* Respond to new regulatory or audit requirements

Without strong version control, teams may rely on filenames such as:

`Access_Control_Policy_Final.docx`

`Access_Control_Policy_Final_v2.docx`

`Access_Control_Policy_FINAL_APPROVED.docx`

That approach makes change history difficult to manage at scale.

## Governance as Code Approach

Using a version-control system such as Git, governance teams can manage policy changes through a structured workflow:

**Policy Requirement → Proposed Change → Review → Approval → Version History**

Each change can create a record showing:

* What changed
* Who proposed the change
* When the change occurred
* Why the change was necessary
* Who reviewed or approved it

The result is a governance artifact with an auditable history rather than a collection of disconnected document versions.

## Example

This directory includes a simplified example Access Control Policy:

[View the Access Control Policy](access-control-policy.md)

The example demonstrates how a governance policy can be stored as a version-controlled Markdown document.

## Creating an Auditable Governance Trail

Each policy change can begin with a commit that records a focused revision and explains why it was made. The commit history then provides a chronological record of how the policy evolved, including the contributor, date, and change description.

When configured with appropriate review requirements and authorized approvers, pull requests add a governed review layer before a change becomes part of the controlled policy. A pull request can capture:

* The business, regulatory, audit, or risk-based reason for the change
* The exact policy language added, removed, or revised
* Discussion between policy owners, control owners, subject matter experts, and reviewers
* Requested changes and the responses to them
* Evidence of review and approval before the change is merged

Together, commits and pull requests connect policy decisions to the resulting text. They provide supporting evidence for an auditable governance trail showing what changed, who participated, why the change was accepted, and when it became part of the controlled source of truth. The organization remains responsible for defining approval authority and retaining that evidence according to its governance requirements.

## Completed Governance Change Example

This repository includes a completed, simplified example showing how a policy requirement can move through a version-controlled governance workflow. [Pull Request #1: Policy v1.1: Strengthen Multifactor Authentication Requirements](https://github.com/neviarrawlinson/governance-as-code/pull/1) demonstrates:

**Policy Baseline → Proposed Change → Branch → Reviewable Diff → Governance Review → Approval → Merge → Version History**

Readers can inspect Pull Request #1 to see:

* The business and governance rationale for the change
* The affected control and policy version
* The exact line-by-line policy diff
* Validation and evidence considerations
* The documented governance review outcome
* The final merge into the approved policy baseline

This example illustrates how software engineering practices can make governance artifacts more traceable and reviewable. GitHub provides the version-control workflow for this demonstration, but it does not by itself constitute a complete enterprise governance or approval system.

## Why This Matters for GRC

Version-controlled policy management can support:

* **Traceability** by maintaining a history of policy changes
* **Accountability** by identifying contributors and reviewers
* **Consistency** by maintaining a controlled source of truth
* **Audit readiness** by preserving change history
* **Collaboration** by enabling structured review of proposed changes
* **Resilience** by reducing dependence on institutional knowledge

The objective is not simply to move Word documents into GitHub.

The larger goal is to apply the discipline of software configuration management to governance artifacts so that governance changes become controlled, reviewable, traceable, and reproducible.
