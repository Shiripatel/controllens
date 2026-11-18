# Journal entry testing

This module scores every journal in a general ledger extract, so the auditor can pick the riskiest entries to test. It supports the audit work on management override of controls.

## How it works

1. **Upload the ledger** (CSV or Excel) on the engagement's *Journal entry testing* tab. The file is hashed and stored.
2. **Columns are matched by header name.** Needed: journal ID, date, account, and amount (or debit and credit). Optional: posted time, user, approver, source, description, account name. Checks that need a missing column are skipped, and the screen says which.
3. **Lines are grouped into journals** and each journal is scored by code.
4. **You review** the list, sorted by score. Open a journal to see its lines and why it scored.
5. **AI explains the riskiest journals** when you click *Explain riskiest journals*: why the entry stands out and what to check. It works on the top 30 unexplained journals with a score of 20 or more.
6. **You decide** for each journal: select for testing, checked with no issue, or exception. A note is required to clear a journal or raise an exception. Every decision goes into the audit trail.
7. **Export** the results as CSV.

## The checks

Each check adds points. The score is the total, capped at 100. **40 or more is high risk, 20 to 39 is medium.**

| Check | Points | Fires when |
|---|---|---|
| Posted on a weekend | 10 | Posted time (or date) falls on Saturday or Sunday |
| Posted outside working hours | 8 | Posted before 06:00 or from 20:00 |
| Round amount | 8 | Total is 1,000 or more and a multiple of 1,000 |
| Just below an approval limit | 12 | Total is within 5% under 5k, 10k, 25k, 50k, 100k, 250k, 500k or 1m |
| Large entry at period end | 10 | Top 5% by value and dated in the last 3 or first 2 days of a month |
| Manual entry | 6 | Source says manual, spreadsheet, adjustment, upload or topside |
| Missing or vague description | 8 | Empty, under 5 characters, or words like "misc" |
| Sensitive words in description | 8 | For example plug, adjust, reclass, per CFO, true-up, write off |
| Not independently approved | 12 | No approver, or approver is the creator |
| User who rarely posts | 8 | User posted 2 or fewer journals in the file |
| Unusual account combination | 10 | This debit and credit pairing appears only once |
| Amount far from normal for the account | 15 | Far above the account's usual line amount (robust z-score over 6) |
| Possible duplicate | 10 | Same date, amount and accounts as another journal |
| Debits and credits do not balance | 15 | Totals differ |
| Recorded long after its date | 8 | Posted more than 30 days after the journal date |

The limits, words and points are in `backend/app/journals.py`. Change them to match your methodology.

## What is code and what is AI

| Step | Done by |
|---|---|
| Reading the file, matching columns, grouping lines | Code |
| All 15 checks, the score and the risk level | Code |
| "Why it stands out" and "What to check" text | AI (or a template in offline mode) |
| Selecting, clearing, raising exceptions | A person |

The same file always gives the same scores. The AI can't change a score.

## Limits

- Up to 300,000 lines and 60 MB per file. Split larger ledgers by period.
- The statistics need enough data: the rare-user and unusual-combination checks only run on files with 50 or more journals.
- A high score means "look at this", not "this is wrong".
- Checking that the ledger extract is complete (ties to the trial balance) is still the auditor's job.
