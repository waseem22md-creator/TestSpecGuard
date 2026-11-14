# TestSpecGuard — Primary Test Evaluation and One-off Failure Analysis

## Primary test evaluation

The uploaded CSV contains **207 completed records**.

| Category | Correct | Total | Accuracy |
|---|---:|---:|---:|
| Original | 69 | 69 | 100.00% |
| One-off | 4 | 69 | 5.80% |
| Conflicting | 66 | 69 | 95.65% |

Overall classification metrics (positive class = `BLOCK`):

- True positives: 70
- True negatives: 69
- False positives: 0
- False negatives: 68
- Accuracy: 67.15%
- Precision: 100.00%
- Recall: 50.72%
- F1 score: 67.31%
- False positive rate: 0.00%

## One-off detection investigation — initial findings

The one-off category contains 69 records: 4 correct and 65 incorrect.

Across the detailed diagnostics:

- S2 leave-one-out checks examined: 1617
- Checks marked as having insufficient eligible candidates: 1613 (99.75%)
- Checks with at least one eligible candidate: 4
- S2 conflict flags: 4
- One-off records with any S1 contradiction: 1
- One-off records with any S2 conflict: 4
- One-off records with S2 and S3 both positive on the **same test line**: 3

### Interpretation

The strongest observed bottleneck is S2 candidate eligibility. In most leave-one-out checks, no candidate passed all the other assertions, so S2 could not establish a conflict for the excluded assertion.

This matters because the implemented final decision rule requires S1, or both S2 and S3 to flag the same test line. An S3 misalignment by itself does not produce a BLOCK decision. Therefore, S3 findings can be present in a one-off record while the final prediction remains ALLOW if S1 is absent and S2 does not flag that same line.

This is an evidence-based initial diagnosis from the saved evaluation diagnostics. It does **not** yet establish why candidates fail the remaining assertions in every task. The next step is to inspect candidate-level outcomes and representative false negatives, without modifying the implementation or overwriting the baseline results.

## Reproducibility and provenance

These files were prepared from the evaluation CSV and detailed per-record JSON supplied for this analysis. The CSV and detailed JSON are preserved as uploaded; the metrics JSON is recalculated from the CSV. No evaluation was rerun and no model code was changed.
