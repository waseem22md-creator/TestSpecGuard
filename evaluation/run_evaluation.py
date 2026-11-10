import argparse
import csv
import json
import random
import re
import time
from collections import defaultdict
from pathlib import Path

from testspecguard.guard import TestSpecGuard
from testspecguard.benchmark_adapter import BenchmarkAdapter


# --------------------------------------------------
# 1. Project configuration
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = PROJECT_ROOT / "benchmark_raw"
RESULTS_DIR = PROJECT_ROOT / "evaluation" / "results"

CATEGORIES = ["original", "oneoff", "conflicting"]

TUNING_TASK_COUNT = 30
RANDOM_SEED = 42

RESULT_FIELDS = [
    "task_id",
    "category",
    "entry_point",
    "expected_decision",
    "predicted_decision",
    "correct",
    "status",
    "S1_contradiction_count",
    "S2_conflict_count",
    "S3_misaligned_count",
    "evaluation_seconds",
    "error",
]


# --------------------------------------------------
# 2. Safe JSON saving
# --------------------------------------------------

def save_json_atomic(data, path):
    """Write JSON safely using a temporary file."""

    path.parent.mkdir(parents=True, exist_ok=True)

    temporary_path = path.with_suffix(path.suffix + ".tmp")

    with temporary_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)

    temporary_path.replace(path)


# --------------------------------------------------
# 3. Load and validate matched benchmark records
# --------------------------------------------------

def load_dataset():

    adapter = BenchmarkAdapter()
    records_by_task = defaultdict(dict)

    for category in CATEGORIES:

        file_path = DATASET_DIR / category / "records_clean.json"

        if not file_path.exists():
            raise FileNotFoundError(
                f"Benchmark file not found: {file_path}"
            )

        with file_path.open("r", encoding="utf-8") as file:
            category_records = json.load(file)

        for record in category_records:

            task_id = record.get("task_id")

            if not task_id:
                continue

            if category in records_by_task[task_id]:
                raise ValueError(
                    f"Duplicate task ID {task_id} in {category}"
                )

            record["_category"] = category
            records_by_task[task_id][category] = record

    valid_records = []
    excluded_tasks = []

    for task_id, versions in sorted(records_by_task.items()):

        missing_versions = [
            category
            for category in CATEGORIES
            if category not in versions
        ]

        if missing_versions:
            excluded_tasks.append({
                "task_id": task_id,
                "reason": (
                    "Missing benchmark versions: "
                    + ", ".join(missing_versions)
                ),
            })
            continue

        # Check whether all three versions are supported by the parser.
        parse_errors = []

        for category in CATEGORIES:

            try:
                adapter.parse_record(versions[category])

            except Exception as exc:
                parse_errors.append(
                    f"{category}: {str(exc)}"
                )

        if parse_errors:
            excluded_tasks.append({
                "task_id": task_id,
                "reason": " | ".join(parse_errors),
            })
            continue

        # Keep all three versions of a valid task.
        for category in CATEGORIES:
            valid_records.append(versions[category])

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    excluded_path = RESULTS_DIR / "excluded_tasks.json"

    save_json_atomic(excluded_tasks, excluded_path)

    retained_task_count = len(valid_records) // len(CATEGORIES)

    print("\n========== DATASET VALIDATION ==========")
    print(f"Underlying tasks found: {len(records_by_task)}")
    print(f"Underlying tasks retained: {retained_task_count}")
    print(f"Underlying tasks excluded: {len(excluded_tasks)}")

    for category in CATEGORIES:

        count = sum(
            record["_category"] == category
            for record in valid_records
        )

        print(f"{category}: {count} records")

    print(f"Excluded task details saved to: {excluded_path}")
    print("========================================")

    return valid_records, excluded_tasks


# --------------------------------------------------
# 4. Create deterministic tuning/test split
# --------------------------------------------------

def create_task_split(records):

    task_ids = sorted({
        record["task_id"]
        for record in records
    })

    if len(task_ids) <= TUNING_TASK_COUNT:
        raise ValueError(
            f"Expected more than {TUNING_TASK_COUNT} valid tasks "
            f"to create the tuning/test split. Found {len(task_ids)}."
        )

    shuffled_task_ids = task_ids.copy()

    random.Random(RANDOM_SEED).shuffle(shuffled_task_ids)

    tuning_ids = set(
        shuffled_task_ids[:TUNING_TASK_COUNT]
    )

    test_ids = set(
        shuffled_task_ids[TUNING_TASK_COUNT:]
    )

    tuning_records = [
        record for record in records
        if record["task_id"] in tuning_ids
    ]

    test_records = [
        record for record in records
        if record["task_id"] in test_ids
    ]

    if tuning_ids.intersection(test_ids):
        raise RuntimeError(
            "Data leakage detected between tuning and test splits."
        )

    # Verify all three versions remain together.
    for task_id in task_ids:

        versions = [
            record["_category"]
            for record in records
            if record["task_id"] == task_id
        ]

        if sorted(versions) != sorted(CATEGORIES):
            raise RuntimeError(
                f"Incomplete task versions found for {task_id}"
            )

    split_manifest = {
        "random_seed": RANDOM_SEED,
        "tuning_task_count": len(tuning_ids),
        "test_task_count": len(test_ids),
        "tuning_task_ids": sorted(tuning_ids),
        "test_task_ids": sorted(test_ids),
    }

    manifest_path = RESULTS_DIR / "split_manifest.json"

    save_json_atomic(split_manifest, manifest_path)

    print("\n========== DATASET SPLIT ==========")
    print(f"Tuning tasks: {len(tuning_ids)}")
    print(f"Tuning records: {len(tuning_records)}")
    print(f"Primary test tasks: {len(test_ids)}")
    print(f"Primary test records: {len(test_records)}")
    print(f"Random seed: {RANDOM_SEED}")
    print(f"Split manifest: {manifest_path}")
    print("===================================")

    return tuning_records, test_records


# --------------------------------------------------
# 5. Evaluate one benchmark record
# --------------------------------------------------

def evaluate_record(guard, adapter, record):

    category = record["_category"]

    expected_decision = (
        "ALLOW" if category == "original" else "BLOCK"
    )

    start_time = time.perf_counter()

    try:

        test_cases = adapter.parse_record(record)

        # Replace candidate(...) with the actual entry-point name.
        source_code = "\n".join(
            re.sub(
                r"\bcandidate(?=\s*\()",
                record["entry_point"],
                case.source,
            )
            for case in test_cases
        )

        result = guard.run(
            source_code=source_code,
            task_description=record["prompt"],
            enable_s2=True,
            enable_s3=True,
        )

        decision = result.get("decision", {})

        predicted_decision = decision.get(
            "final_decision",
            "UNKNOWN",
        )

        s1 = result.get("S1", {})
        s2 = result.get("S2", {})
        s3 = result.get("S3", {})

        elapsed_seconds = time.perf_counter() - start_time

        return {
            "task_id": record["task_id"],
            "category": category,
            "entry_point": record["entry_point"],
            "expected_decision": expected_decision,
            "predicted_decision": predicted_decision,
            "correct": predicted_decision == expected_decision,
            "status": result.get("status", "unknown"),

            "S1_contradiction_count": s1.get(
                "contradiction_count", 0
            ),

            "S2_conflict_count": sum(
                item.get("is_conflict", False)
                for item in s2.get("flags", [])
            ),

            "S3_misaligned_count": sum(
                item.get("verdict") == "MISALIGNED"
                for item in s3.get("results", [])
            ),

            # Save the decision for every individual test line.
            "line_decisions": decision.get("decisions", []),

            # Save the original component outputs for detailed analysis.
            "component_diagnostics": {
                "S1_contradictions": s1.get(
                    "contradictions", []
                ),

                "S2_flags": s2.get(
                    "flags", []
                ),

                "S2_candidate_diagnostics": s2.get(
                    "candidate_diagnostics", []
                ),

                "S3_results": s3.get(
                    "results", []
                ),
            },

            "evaluation_seconds": round(elapsed_seconds, 4),
            "error": "",
        }

    except Exception as exc:

        elapsed_seconds = time.perf_counter() - start_time

        return {
            "task_id": record.get("task_id", "unknown"),
            "category": category,
            "entry_point": record.get("entry_point", ""),
            "expected_decision": expected_decision,
            "predicted_decision": "ERROR",
            "correct": False,
            "status": "error",
            "S1_contradiction_count": 0,
            "S2_conflict_count": 0,
            "S3_misaligned_count": 0,
            "line_decisions": [],
            "component_diagnostics": {},
            "evaluation_seconds": round(elapsed_seconds, 4),
            "error": str(exc),
        }


# --------------------------------------------------
# 6. Save evaluation results
# --------------------------------------------------

def save_results(results, split):

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    json_path = (
        RESULTS_DIR / f"{split}_evaluation_results.json"
    )

    csv_path = (
        RESULTS_DIR / f"{split}_evaluation_results.csv"
    )

    save_json_atomic(results, json_path)

    temporary_csv = csv_path.with_suffix(".csv.tmp")

    with temporary_csv.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=RESULT_FIELDS,
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(results)

    temporary_csv.replace(csv_path)

    print("\nResults saved:")
    print(json_path)
    print(csv_path)


# --------------------------------------------------
# 7. Load existing results and validate configuration
# --------------------------------------------------

def load_existing_results(split, config):

    json_path = (
        RESULTS_DIR / f"{split}_evaluation_results.json"
    )

    config_path = (
        RESULTS_DIR / f"{split}_evaluation_config.json"
    )

    if not json_path.exists():

        save_json_atomic(config, config_path)
        return []

    if not config_path.exists():
        raise RuntimeError(
            "Existing results have no configuration file. "
            "Back them up and start a fresh evaluation."
        )

    with config_path.open("r", encoding="utf-8") as file:
        old_config = json.load(file)

    if old_config != config:
        raise RuntimeError(
            "Evaluation configuration does not match the saved "
            "results. Do not combine results from different "
            "models or settings. Back up the old results or use "
            "a separate results directory."
        )

    with json_path.open("r", encoding="utf-8") as file:
        results = json.load(file)

    if not isinstance(results, list):
        raise RuntimeError(
            "Existing results file is not a valid list."
        )

    print(f"Loaded {len(results)} existing results.")

    return results


# --------------------------------------------------
# 8. Calculate classification metrics
# --------------------------------------------------

def calculate_metrics(results):

    valid_results = [
        item for item in results
        if item["predicted_decision"] in ("ALLOW", "BLOCK")
    ]

    tp = sum(
        item["expected_decision"] == "BLOCK"
        and item["predicted_decision"] == "BLOCK"
        for item in valid_results
    )

    tn = sum(
        item["expected_decision"] == "ALLOW"
        and item["predicted_decision"] == "ALLOW"
        for item in valid_results
    )

    fp = sum(
        item["expected_decision"] == "ALLOW"
        and item["predicted_decision"] == "BLOCK"
        for item in valid_results
    )

    fn = sum(
        item["expected_decision"] == "BLOCK"
        and item["predicted_decision"] == "ALLOW"
        for item in valid_results
    )

    precision = tp / (tp + fp) if (tp + fp) else 0
    recall = tp / (tp + fn) if (tp + fn) else 0
    fpr = fp / (fp + tn) if (fp + tn) else 0

    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall)
        else 0
    )

    accuracy = (
        (tp + tn) / len(valid_results)
        if valid_results
        else 0
    )

    error_count = len(results) - len(valid_results)

    return {
        "total_records": len(results),
        "valid_predictions": len(valid_results),
        "error_records": error_count,
        "TP": tp,
        "TN": tn,
        "FP": fp,
        "FN": fn,
        "precision": precision,
        "recall": recall,
        "FPR": fpr,
        "F1_score": f1,
        "classification_accuracy": accuracy,
    }


# --------------------------------------------------
# 9. Print and save evaluation summary
# --------------------------------------------------

def print_summary(results, split):

    grouped = defaultdict(list)

    for result in results:
        grouped[result["category"]].append(result)

    print(f"\n========== {split.upper()} SUMMARY ==========")

    for category in CATEGORIES:

        category_results = grouped[category]

        if not category_results:
            continue

        correct = sum(
            item["correct"]
            for item in category_results
        )

        errors = sum(
            item["predicted_decision"] == "ERROR"
            for item in category_results
        )

        valid = [
            item for item in category_results
            if item["predicted_decision"] in ("ALLOW", "BLOCK")
        ]

        valid_correct = sum(
            item["correct"]
            for item in valid
        )

        print(f"\nCategory: {category}")
        print(f"Records evaluated: {len(category_results)}")
        print(f"Correct decisions: {correct}")
        print(f"Errors: {errors}")

        print(
            f"Accuracy including errors: "
            f"{correct / len(category_results) * 100:.2f}%"
        )

        if valid:
            print(
                f"Accuracy among valid predictions: "
                f"{valid_correct / len(valid) * 100:.2f}%"
            )

    metrics = calculate_metrics(results)

    total_runtime = sum(
        item.get("evaluation_seconds", 0)
        for item in results
    )

    print("\n========== CLASSIFICATION METRICS ==========")
    print(f"Total records: {metrics['total_records']}")
    print(f"Valid predictions: {metrics['valid_predictions']}")
    print(f"Error records: {metrics['error_records']}")
    print(f"True Positives (TP): {metrics['TP']}")
    print(f"True Negatives (TN): {metrics['TN']}")
    print(f"False Positives (FP): {metrics['FP']}")
    print(f"False Negatives (FN): {metrics['FN']}")
    print(f"Precision: {metrics['precision'] * 100:.2f}%")
    print(f"Recall: {metrics['recall'] * 100:.2f}%")
    print(f"False Positive Rate: {metrics['FPR'] * 100:.2f}%")
    print(f"F1 Score: {metrics['F1_score'] * 100:.2f}%")

    print(
        f"Classification Accuracy: "
        f"{metrics['classification_accuracy'] * 100:.2f}%"
    )

    print("============================================")

    print(
        f"\nTotal recorded evaluation runtime: "
        f"{total_runtime:.2f} seconds"
    )

    metrics["total_runtime_seconds"] = round(total_runtime, 2)

    metrics_path = (
        RESULTS_DIR / f"{split}_evaluation_metrics.json"
    )

    save_json_atomic(metrics, metrics_path)

    print(f"Metrics saved to: {metrics_path}")


# --------------------------------------------------
# 10. Main evaluation
# --------------------------------------------------

def main():

    parser = argparse.ArgumentParser(
        description="Run TestSpecGuard benchmark evaluation."
    )

    parser.add_argument(
        "--split",
        choices=["tuning", "test"],
        default="test",
        help="Choose tuning or primary test dataset.",
    )

    parser.add_argument(
        "--model",
        default="qwen2.5-coder:3b",
        help="Ollama model used by TestSpecGuard.",
    )

    parser.add_argument(
        "--num-candidates",
        type=int,
        default=5,
        help="Number of candidate solutions generated for S2.",
    )

    parser.add_argument(
        "--min-candidates",
        type=int,
        default=1,
        help="Minimum eligible candidates required by S2.",
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=5,
        help="Candidate execution timeout in seconds.",
    )

    # Optional diagnostic arguments.
    parser.add_argument(
        "--diagnose-tasks",
        nargs="+",
        help=(
            "Evaluate only the specified task IDs and save "
            "results separately."
        ),
    )

    parser.add_argument(
        "--diagnose-category",
        choices=CATEGORIES,
        help="Restrict diagnostic evaluation to one category.",
    )

    args = parser.parse_args()

    if args.num_candidates < 1:
        parser.error("--num-candidates must be at least 1.")

    if args.min_candidates < 1:
        parser.error("--min-candidates must be at least 1.")

    if args.timeout < 1:
        parser.error("--timeout must be at least 1.")

    print("\nLoading TestSpecGuard benchmark dataset...")

    records, excluded_tasks = load_dataset()

    if not records:
        print("No valid matched benchmark records found.")
        return

    tuning_records, test_records = create_task_split(records)

    selected_records = (
        tuning_records
        if args.split == "tuning"
        else test_records
    )

    # --------------------------------------------------
    # Optional diagnostic filtering
    # --------------------------------------------------

    if args.diagnose_tasks:

        requested_ids = set(args.diagnose_tasks)

        selected_records = [
            record for record in selected_records
            if record["task_id"] in requested_ids
            and (
                args.diagnose_category is None
                or record["_category"] == args.diagnose_category
            )
        ]

        found_ids = {
            record["task_id"]
            for record in selected_records
        }

        missing_ids = requested_ids - found_ids

        if missing_ids:
            parser.error(
                "Diagnostic task IDs not found in the selected "
                "split/category: "
                + ", ".join(sorted(missing_ids))
            )

        if not selected_records:
            parser.error(
                "No records matched the diagnostic filters."
            )

    # Diagnostic results use separate filenames.
    result_name = (
        f"diagnostic_{args.split}"
        if args.diagnose_tasks
        else args.split
    )

    print(f"\nSelected split: {args.split}")

    if args.diagnose_tasks:
        print(
            f"Diagnostic task IDs: "
            f"{', '.join(args.diagnose_tasks)}"
        )

        print(
            f"Diagnostic category: "
            f"{args.diagnose_category or 'all'}"
        )

    print(
        f"Records ready for evaluation: "
        f"{len(selected_records)}"
    )

    # --------------------------------------------------
    # Evaluation configuration
    # --------------------------------------------------

    config = {
        "split": args.split,
        "model": args.model,
        "num_candidates": args.num_candidates,
        "min_candidates": args.min_candidates,
        "timeout": args.timeout,
        "random_seed": RANDOM_SEED,
        "tuning_task_count": TUNING_TASK_COUNT,
        "diagnose_tasks": sorted(
            set(args.diagnose_tasks or [])
        ),
        "diagnose_category": args.diagnose_category,
    }

    results = load_existing_results(
        result_name,
        config,
    )

    # Skip completed records.
    completed_keys = {
        (item["task_id"], item["category"])
        for item in results
        if item.get("predicted_decision") in ("ALLOW", "BLOCK")
        and item.get("status") != "error"
    }

    pending_records = [
        record for record in selected_records
        if (
            record["task_id"],
            record["_category"],
        ) not in completed_keys
    ]

    print(f"Already completed: {len(completed_keys)}")
    print(f"Remaining records: {len(pending_records)}")

    if not pending_records:

        print(
            "\nAll records in this split have completed predictions."
        )

        print_summary(
            results,
            result_name,
        )

        return

    # --------------------------------------------------
    # Initialize TestSpecGuard
    # --------------------------------------------------

    guard = TestSpecGuard(
        model=args.model,
        num_candidates=args.num_candidates,
        min_candidates=args.min_candidates,
        timeout=args.timeout,
    )

    adapter = BenchmarkAdapter()

    # --------------------------------------------------
    # Evaluate records
    # --------------------------------------------------

    for index, record in enumerate(
        pending_records,
        start=1,
    ):

        print(
            f"\n[{index}/{len(pending_records)}] "
            f"Evaluating {record['task_id']} "
            f"({record['_category']})..."
        )

        result = evaluate_record(
            guard,
            adapter,
            record,
        )

        # Remove an earlier result for the same record.
        results = [
            item for item in results
            if not (
                item["task_id"] == result["task_id"]
                and item["category"] == result["category"]
            )
        ]

        results.append(result)

        print(
            f"Expected: {result['expected_decision']} | "
            f"Predicted: {result['predicted_decision']} | "
            f"Status: {result['status']}"
        )

        if result["error"]:
            print(f"Error: {result['error']}")

        # Save after every record.
        save_results(
            results,
            result_name,
        )

    # --------------------------------------------------
    # Final summary
    # --------------------------------------------------

    print_summary(
        results,
        result_name,
    )


if __name__ == "__main__":
    main()