# Snapshotting — Design Notes and Key Findings

## What this project demonstrates

Snapshotting solves a different problem than Project 3's SCD Type 2.
SCD2 assumes the source system tells you when a change happened. 
Snapshotting infers history by polling that current state repeatedly 
and diffing successive polls. The change detection resolution is 
bounded by poll frequency: a nightly poll can only ever say "this
changed sometime between last night and tonight," never the exact moment.

---

## Storage finding

Periodic snapshotting stores a full copy every night regardless of
whether anything changed: ~10,000 rows × 29 successful nights ≈ 290,000
rows. Incremental stores one base copy plus only the rows that actually
changed: ~10,000 + ~45 ≈ 10,045 rows. At this change rate, incremental
achieves roughly a 29x storage reduction — proportional to how rarely
the dimension actually changes, the same principle behind Project 2's
propagation multiplier finding, applied to storage instead of maintenance.

---

## The core finding: periodic and incremental fail differently under a gap

**Periodic under a missing night:** the failure is contained. Night 12's
snapshot simply doesn't exist. Every other night stands alone — Night 13
onward are completely unaffected, because periodic re-derives full state
independently each time. The cost of the gap is narrow: you permanently
lose the ability to say exactly what the dimension looked like on Night
12 specifically, and nothing else.

**Incremental under a missing night — if built defensively:** the
failure is absorbed. Because the diff baseline is "whatever was last
successfully captured" rather than "the calendar night before this
one," Night 13's delta naturally bundles in anything that changed during
Night 12 as well. Final state remains correct. The cost is narrower than
it first appears: you lose the ability to say whether a given change
happened specifically on Night 12 or Night 13, but you don't lose the
change itself.

**Incremental under a missing night — if built naively:** the failure
corrupts. A process that rigidly diffs against "night_number - 1" by
direct lookup, rather than "last successful capture," finds nothing to
compare against when that lookup is empty. Every customer appears to
have no prior state, so every customer appears changed. The delta for
Night 13 balloons from ~2-3 rows to ~10,000 rows — a full-table-sized
delta masquerading as an incremental one. A lost checkpoint or offset
produces a spurious full reload disguised as an incremental update,
often silently, because the process "succeeds" and writes the wrong data.

The practical implication: incremental snapshotting requires the diff 
logic to be resilient to gaps by design — diffing against last known 
good state, not against an assumed prior period.
Getting this wrong doesn't just lose history, it actively corrupts the
delta with false positives.

---

## Gap detection is robust to silent failures by design

The gap detection query (calendar spine anti-joined against
`status = 'success'` entries in `snapshot_log`) works identically
whether a failure is logged explicitly (`status = 'failed'`) or not
logged at all (no row exists for that night). It only checks for the
*absence* of a success record — it never assumes failures announce
themselves. This matters because a query that only checked
`WHERE status = 'failed'` would miss a job that crashed before it even
reached its own logging step, which is a common real-world failure mode.

---

## Reconstruction: exact-match vs as-of

`WHERE night_number = 12` on the periodic table silently returns zero
rows — indistinguishable, on the surface, from "zero customers existed."
The safer pattern is an explicit "as of" query that finds the latest
*available* night at or before the target and surfaces which night it
actually used (`reconstructed_as_of_night` in the query output). This
is a small change in query shape with a large difference in honesty:
one silently returns nothing, the other explicitly tells you it fell
back and to which night.

---

## Connection to adjacent projects

**Project 3:** Both projects answer "what was true at a point in time,"
but from opposite starting conditions. Project 3 assumes you know
exactly when a change happened (told via `valid_from`). Project 5
assumes you don't know and must infer it from polling frequency —
the resolution of "when" is only ever as fine as the snapshot interval.

**Project 2:** The storage ratio finding here (29x) is structurally the
same kind of result as Project 2's propagation multiplier (10,000x) —
both quantify how much a design choice costs by measuring rows rather
than asserting an opinion.

**Project 4:** The naive incremental bug (a lost checkpoint producing a
full-table-sized delta) is a distinct species of the same underlying
lesson as Project 4's join inflation — an operation that's supposed to
be small silently becomes large because of an unhandled edge case, and
the fix in both cases is a row-count sanity check before trusting the
output.