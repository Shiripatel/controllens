# Testing methodology

This page explains the audit logic behind ControlLens. Firms should review it and swap in their own methodology where it differs.

## ITGC domains

| Domain | Risk it covers |
|---|---|
| **APD**: Access to Programs & Data | Only the right people can access systems and data |
| **PC**: Program Change | Changes to systems are approved, tested and moved to production properly |
| **CO**: Computer Operations | Jobs, backups, interfaces and incidents run and are handled correctly |
| **PD**: Program Development | New systems and data migrations are controlled |

The full list of 20 controls, with attributes and procedures, is in `backend/app/library.py` and on the **Control library** page.

## Two stages of testing

| Stage | Question | Typical evidence |
|---|---|---|
| **Design & Implementation (D&I)** | If the control works as described, does it address the risk? Was it actually in place at least once? | Policy, procedure, walkthrough notes, one example |
| **Test of Operating Effectiveness (TOE)** | Did the control work for every sampled item through the period? | Population, sample tickets, approvals, logs, system reports |

TOE should start after D&I is reviewed. The TOE agent flags it if D&I isn't reviewed yet.

## Attributes

An **attribute** is one thing that must be true for the control to work. For example, for user provisioning:

- A1: A documented access request exists
- A2: The request is approved before access is granted
- A3: Access granted matches what was approved
- A4: The approver is independent of the person granting access

D&I checks each attribute once. TOE checks every attribute for every sample item.

## Test type

| Control nature / frequency | Test type | Why |
|---|---|---|
| Automated, or "Continuous (automated)" | **Test of one** | An automated control works the same way every time. Rely on the change and access ITGCs for consistency over the period. |
| Manual or IT-dependent manual | **Random sample** | Each time a person does it is a separate event that can fail |

## Sample sizes

From `backend/app/sampling.py`:

| Frequency | Lower risk | Higher risk |
|---|---|---|
| Annual | 1 | 1 |
| Quarterly | 2 | 2 |
| Monthly | 2 | 3 |
| Weekly | 5 | 10 |
| Daily | 20 | 30 |
| Multiple times per day | 25 | 40 |
| Event-driven | 25 | 40 |

- "Higher risk" is used when the control's risk rating is **High**. Low and Moderate use the lower size.
- If the population is no bigger than the sample size, **all items** are tested.
- An empty population gives a sample of 0, with a note to confirm the population is complete.
- Selection is random using a saved **seed**. The same file with the same seed always gives the same sample.
- **Override:** a bigger sample is always allowed. A smaller one needs reviewer role and a written reason. Both are logged.

## Population completeness

The population file must be uploaded as evidence with purpose **Population**, so it's hashed and kept. The reviewer agent flags a sample that isn't linked to a population file. Testers should still document how the population was produced (report name, parameters, record count), because the system can't check that by itself.

## Conclusion rules

These are calculated by code from the attribute or item results:

**D&I: design**

| If any attribute is... | Proposed conclusion |
|---|---|
| inadequate | Not effective |
| unable to assess (and none inadequate) | Needs more evidence |
| all adequate | Effective |

**D&I: implementation.** Same logic, using implemented: yes / no / unable.

**TOE**

| If... | Proposed conclusion |
|---|---|
| any sample item has a fail | Not operating effectively |
| any check is unable to assess, or an item wasn't tested | Needs more evidence |
| everything passed | Operating effectively |

The preparer can choose a different conclusion (for example, if an exception is explained and accepted under the firm's methodology), but must write the reason.

## Exceptions

Each failed item × attribute becomes an exception record with a severity, set by the team:

- **Deficiency**
- **Significant deficiency**
- **Material weakness**

Status: open → accepted / remediated. Changing an exception revokes TOE sign-offs, so the reviewer sees the latest position.
