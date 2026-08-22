# Access Control Policy

> **Example Governance as Code Artifact**
> This policy is a simplified demonstration of how a governance artifact can be maintained through version control. It is intended for educational purposes and is not a production-ready organizational policy.

## Policy Metadata

| Attribute        | Value                |
| ---------------- | -------------------- |
| Policy ID        | ACP-001              |
| Policy Owner     | Information Security |
| Governance Owner | GRC                  |
| Version          | 1.1                  |
| Status           | Approved             |
| Review Frequency | Annual               |
| Last Reviewed    | 2026-08-22           |
| Next Review      | 2027-08-22           |

## 1. Purpose

The purpose of this policy is to establish requirements for managing access to organizational systems, applications, and information resources.

Access controls should ensure that users receive only the level of access necessary to perform authorized responsibilities.

## 2. Scope

This policy applies to:

* Employees
* Contractors
* Third-party users
* Privileged administrators
* Applications and systems that process organizational information
* Cloud and infrastructure environments

## 3. Policy Requirements

### ACP-001-01: Unique User Identification

Each user must be assigned a unique account or identifier.

Shared accounts should be prohibited unless a documented business or technical requirement exists and appropriate compensating controls are implemented.

**Control Type:** Preventive
**Validation Method:** Account configuration review
**Evidence:** User account inventory

### ACP-001-02: Least Privilege

Access must be granted according to the principle of least privilege.

Users should receive only the permissions necessary to perform their authorized responsibilities.

**Control Type:** Preventive
**Validation Method:** Access entitlement review
**Evidence:** Role and permission assignments

### ACP-001-03: Multifactor Authentication

Multifactor authentication must be enabled for privileged accounts, remote access, and access to systems containing sensitive or regulated information.

Exceptions to the multifactor authentication requirement must follow the exception process documented in this policy and include appropriate risk review and approval.

**Control Type:** Preventive
**Validation Method:** Configuration validation
**Evidence:** Authentication configuration

### ACP-001-04: Periodic Access Reviews

User access must be reviewed periodically to identify inappropriate, unnecessary, or outdated permissions.

**Review Frequency:** Quarterly
**Control Type:** Detective
**Validation Method:** Access review
**Evidence:** Completed access review records

### ACP-001-05: Access Removal

Access must be removed or modified promptly when a user's employment, contractual relationship, role, or business need changes.

**Control Type:** Preventive
**Validation Method:** Termination and role-change review
**Evidence:** Access removal records and related service tickets

## 4. Exceptions

Exceptions to this policy must:

1. Document the business or technical justification.
2. Identify the associated risk.
3. Define appropriate compensating controls when applicable.
4. Receive approval from the designated governance and security authorities.
5. Include an expiration or review date.

## 5. Monitoring and Evidence

Evidence supporting these requirements should be retained according to applicable organizational retention requirements.

Where technically feasible, control validation and evidence collection should be automated to support continuous assurance.

## 6. Governance as Code Implementation

When managed through version control, modifications to this policy should follow a controlled workflow:

**Proposed Change → Review → Approval → Merge → Version History**

Changes should include documentation explaining:

* What changed
* Why the change was necessary
* Who proposed the change
* Who reviewed or approved the change

Git commit history and pull requests can provide supporting traceability for the evolution of the policy.

## 7. Future Automation Opportunities

Requirements within this policy may eventually be mapped to automated validation.

Examples include:

* Checking whether multifactor authentication is enabled
* Identifying inactive accounts
* Detecting privileged accounts outside approved groups
* Identifying accounts that have not completed required access reviews
* Detecting access that remains active after termination

These validations can connect policy requirements to technical controls and continuous monitoring.

## Change History

| Version | Date       | Description                               |
| ------- | ---------- | ----------------------------------------- |
| 1.1     | 2026-08-22 | Strengthened multifactor authentication requirements |
| 1.0     | 2026-08-22 | Initial version-controlled policy example |
