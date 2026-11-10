
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = PROJECT_ROOT / "dataset"


def load_records(category):
    folder = DATASET_DIR / category
    records = []

    for file_path in sorted(folder.glob("*.json")):
        with file_path.open("r", encoding="utf-8") as file:
            records.append(json.load(file))

    return records


def test_dataset_categories_exist():
    for category in ["original", "one_off", "conflicting"]:
        assert (DATASET_DIR / category).is_dir()


def test_each_category_has_three_tasks():
    for category in ["original", "one_off", "conflicting"]:
        records = load_records(category)
        assert len(records) == 3


def test_dataset_records_have_required_fields():
    required_fields = {
        "task_id",
        "task_description",
        "category",
        "test_code",
        "mutation_details",
    }

    for category in ["original", "one_off", "conflicting"]:
        for record in load_records(category):
            assert required_fields.issubset(record.keys())
            assert record["category"] == category
            assert record["test_code"].strip()


def test_task_ids_match_across_categories():
    categories = ["original", "one_off", "conflicting"]

    task_ids = [
        {record["task_id"] for record in load_records(category)}
        for category in categories
    ]

    assert task_ids[0] == task_ids[1] == task_ids[2]
