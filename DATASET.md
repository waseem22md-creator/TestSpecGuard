# TestSpecGuard Dataset Documentation

## 1. Dataset Source

The benchmark used in TestSpecGuard is based on **Impossible-LiveCodeBench**, obtained from the Hugging Face dataset:

`fjzzq2002/impossible_livecodebench`

The benchmark contains programming problems paired with three test-suite variants:

- Original
- One-off
- Conflicting

Each variant represents a different test condition used to evaluate the system's ability to identify inconsistencies between problem descriptions and test specifications.

## 2. Dataset Collection

The benchmark records were downloaded and organized into the following directories:

- `benchmark_raw/original/`
- `benchmark_raw/oneoff/`
- `benchmark_raw/conflicting/`

Each directory contains the corresponding benchmark records in JSON format.

The original downloaded dataset contained 103 records in each category, giving 309 records in total.
## 3. Dataset Cleaning and Validation

The downloaded records were checked for consistency and compatibility with the TestSpecGuard assertion parser.

The cleaning process was performed in two stages:

**Stage 1: Initial Cleaning**

The initially downloaded dataset contained 103 records in each category (309 records total).

The task `lcbhard_77` was removed from all three categories because its mutated One-off and Conflicting variants contained malformed test cases.

After this stage, 102 underlying tasks remained, with 102 records in each category (306 records total).

**Stage 2: Parser Validation**

The remaining records were checked for compatibility with the implemented assertion parser.

Three underlying tasks were excluded consistently across all three categories because they did not contain supported assertions:

- `lcbhard_4`
- `lcbhard_5`
- `lcbhard_26`

The exclusions were recorded in `evaluation/results/excluded_tasks.json`.

The final cleaned dataset contains 99 underlying tasks and 297 records.

The cleaning process also included:
1. Checking task identifiers and required record fields.
2. Checking whether test assertions could be parsed.
3. Ensuring that the same underlying tasks were retained across all three variants.
4. Excluding malformed or unsupported tasks consistently across categories.

The cleaned records are stored in:

- `benchmark_raw/original/records_clean.json`
- `benchmark_raw/oneoff/records_clean.json`
- `benchmark_raw/conflicting/records_clean.json`

## 4. Final Dataset Statistics

After cleaning and validation, the dataset contains:

| Category | Records |
|---|---:|
| Original | 99 |
| One-off | 99 |
| Conflicting | 99 |
| **Total** | **297** |

The final dataset contains 99 underlying programming tasks, with three corresponding variants for each task.

## 5. Dataset Record Structure

Each benchmark record contains the following fields:

| Field | Description |
|---|---|
| `task_id` | Unique identifier for the programming task |
| `prompt` | Original programming problem description |
| `test` | Test suite used for evaluation |
| `original_test` | Original test suite associated with the task |
| `impossible_type` | Test-suite category |
| `entry_point` | Expected function name |

The test suites contain Python assertions that are processed by the TestSpecGuard benchmark adapter and assertion parser.

## 6. Training and Evaluation Split

The dataset is divided at the underlying task level to prevent variants of the same task from appearing in different splits.

The split uses a fixed random seed of 42 to ensure reproducibility.

| Split | Underlying Tasks | Records |
|---|---:|---:|
| Tuning | 30 | 90 |
| Primary Test | 69 | 207 |
| **Total** | **99** | **297** |

All three variants of an underlying task remain in the same split.

The split information is saved in `evaluation/results/split_manifest.json`.

## 7. Dataset Creation Code

The repository also includes:

`dataset_creation/generate_dataset.py`

This script generates a separate small synthetic dataset containing nine examples across the three categories. It is intended for basic testing and demonstration.

It is separate from the 297-record Impossible-LiveCodeBench benchmark used for the main evaluation.

## 8. Reproducibility

The evaluation dataset is loaded and validated by:

`evaluation/run_evaluation.py`

The script loads the cleaned benchmark files, checks the three variants, excludes unsupported tasks, creates the reproducible tuning and primary test splits, and saves evaluation results.

To run the evaluation:

```bash
PYTHONPATH=. python evaluation/run_evaluation.py --split tuning
```

```bash
PYTHONPATH=. python evaluation/run_evaluation.py --split test
```

## 9. Limitations

- The implemented assertion parser supports a subset of Python equality assertions rather than every possible Python test structure.
- Tasks without supported assertions are excluded from the benchmark.
- The evaluation results apply to the retained benchmark tasks and should not automatically be generalized to all programming problems.
- The synthetic dataset is intended for basic testing and is not a replacement for the main benchmark.
