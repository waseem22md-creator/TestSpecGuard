# TestSpecGuard

**Pre-Execution Verification for Detecting Conflicts Between Task Specifications and Unit Tests**

TestSpecGuard is a pre-execution verification system designed to identify inconsistencies between programming task descriptions and their associated test suites before a coding agent executes a solution.

The system combines static assertion analysis, candidate-based execution analysis, and LLM-assisted semantic verification to detect potentially incorrect or conflicting test specifications.

## 1. Project Overview

Coding agents rely on task descriptions and unit tests to generate and validate program solutions. However, test suites may contain duplicate inputs with contradictory expected outputs, incorrect expected results, or requirements that do not align with the task description.

TestSpecGuard addresses this problem by analyzing test specifications before execution.

The system uses three verification components:

- **S1 – Static Conflict Detection:** Identifies identical inputs associated with different expected outputs.
- **S2 – Candidate-Based Execution Analysis:** Uses multiple candidate solutions and leave-one-out evaluation to identify suspicious test cases.
- **S3 – LLM-Based Semantic Verification:** Evaluates whether an expected output is consistent with the task description.

The final decision combines these components to determine whether a test specification should be flagged.

## 2. System Architecture

### S1 – Static Conflict Detection

The static checker analyzes parsed assertions and groups test cases by their function inputs.

If identical inputs are associated with different expected outputs, the corresponding test cases are flagged as conflicts.

### S2 – Candidate-Based Execution Analysis

The execution checker generates multiple candidate solutions using an Ollama-hosted language model.

Each candidate is evaluated against the test suite. The system applies leave-one-out analysis by checking whether candidates that pass all other test cases fail the excluded test case.

Candidate eligibility is controlled by a configurable minimum candidate threshold.

### S3 – LLM-Based Semantic Verification

The semantic checker compares the task description with the expected output of a test case.

It uses deterministic checks for supported cases and an LLM-based judge for cases requiring semantic analysis.

Uncertain judgments are treated as abstentions rather than automatically classified as conflicts.

### Final Decision

The decision engine combines the three components using:

`F_i = S1_i OR (S2_i AND S3_i)`

Where:

- `S1_i` represents a static conflict.
- `S2_i` represents a candidate-based execution conflict.
- `S3_i` represents semantic confirmation.

A test case is flagged when the static checker identifies a conflict or when both execution analysis and semantic verification identify a conflict.

## 3. Technology Stack

| Component | Technology |
|---|---|
| Programming language | Python 3.11 |
| LLM runtime | Ollama |
| Candidate generation model | Qwen2.5-Coder 3B |
| Semantic judge model | Qwen2.5-Coder 7B |
| Testing framework | Pytest |
| Data format | JSON and CSV |

## 4. Repository Structure

```text
TestSpecGuard/
│
├── testspecguard/
│   ├── __init__.py
│   ├── benchmark_adapter.py
│   ├── decision_engine.py
│   ├── execution_checker.py
│   ├── guard.py
│   ├── llm_judge.py
│   ├── parser.py
│   └── static_checker.py
│
├── dataset/
│   ├── original/
│   ├── one_off/
│   └── conflicting/
│
├── dataset_creation/
│   └── generate_dataset.py
│
├── ├── benchmark_raw/          # Local benchmark data (not included in GitHub)
│   ├── original/
│   ├── oneoff/
│   └── conflicting/
│
├── evaluation/
│   ├── results/
│   └── run_evaluation.py
│
├── tests/
│   ├── test_dataset.py
│   ├── test_execution_checker.py
│   ├── test_guard_integration.py
│   ├── test_parser.py
│   └── test_static_checker.py
│
├── DATASET.md
├── README.md
├── requirements.txt
├── .env.example
└── .gitignore
```

## 5. Installation and Setup

### Prerequisites

- Python 3.11
- Ollama
- Git
- Sufficient system memory and compute resources to run the selected language models

### Step 1: Clone the Repository

```bash
git clone https://github.com/waseem22md-creator/TestSpecGuard.git
cd TestSpecGuard
```

### Step 2: Create a Virtual Environment

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

### Step 3: Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 4: Install and Configure Ollama

Install Ollama from:

https://ollama.com/download

Download the required models:

```bash
ollama pull qwen2.5-coder:3b
ollama pull qwen2.5-coder:7b
```

Ensure that the Ollama service is running before starting the evaluation.

To check available models:

```bash
ollama list
```

## 6. Running TestSpecGuard

The evaluation script supports the tuning and primary test splits.

To view the available arguments:

```bash
PYTHONPATH=. python evaluation/run_evaluation.py --help
```

### Run the Tuning Evaluation

```bash
PYTHONPATH=. python evaluation/run_evaluation.py --split tuning
```

### Run the Primary Test Evaluation

```bash
PYTHONPATH=. python evaluation/run_evaluation.py --split test
```

The evaluation script loads the cleaned benchmark, validates task variants, creates the reproducible split, and executes the verification pipeline.

Evaluation results are saved in:

`evaluation/results/`

The script supports saving intermediate results to facilitate recovery and continuation of evaluation runs.

## 7. Dataset

TestSpecGuard uses the Impossible-LiveCodeBench benchmark obtained from Hugging Face:

https://huggingface.co/datasets/fjzzq2002/impossible_livecodebench

The benchmark contains three test-suite variants:

- Original
- One-off
- Conflicting

After cleaning and parser validation, the retained benchmark contains:

| Category | Records |
|---|---:|
| Original | 99 |
| One-off | 99 |
| Conflicting | 99 |
| **Total** | **297** |

The 99 underlying tasks are divided into:

- Tuning: 30 tasks (90 records).
- Primary test: 69 tasks (207 records).

All three variants of each underlying task remain in the same split.

For detailed information about data collection, cleaning, validation, exclusions, and dataset organization, see [DATASET.md](DATASET.md).

The repository also contains a separate synthetic dataset generator in `dataset_creation/generate_dataset.py`.

## 8. Evaluation Methodology

The evaluation measures the ability of TestSpecGuard to identify inconsistent test specifications while avoiding incorrect conflict classifications.

The evaluation considers:

- **Precision:** Proportion of flagged cases that are actual conflicts.
- **Recall:** Proportion of actual conflicts correctly identified.
- **False Positive Rate (FPR):** Proportion of legitimate cases incorrectly flagged.
- **F1 Score:** Harmonic mean of precision and recall.
- **Accuracy:** Overall proportion of correct classifications.

Additional measures include cheating rate, residual cheating rate, legitimate completion rate, and evaluation overhead where applicable.

The tuning split is used for configuration analysis, while the primary test split is reserved for evaluating performance on the held-out tasks.

Final performance figures should be taken from the completed primary test evaluation rather than the tuning results.

## 9. Running Tests

Run the project's automated test suite using:

```bash
python -m pytest -q
```

To check Python syntax:

```bash
python -m py_compile testspecguard/*.py
```

## 10. Limitations

- The assertion parser currently supports a subset of Python equality assertions rather than all possible Python test structures.
- Candidate generation and semantic verification depend on the selected local language models.
- Candidate execution uses subprocess-based isolation and should not be considered a fully secure sandbox for untrusted code.
- Model-generated candidates may contain syntax errors, execution errors, or timeouts.
- LLM-based semantic judgments may be uncertain or incorrect.
- Evaluation findings are based on the retained benchmark and should not automatically be generalized to every programming task.

## 11. Reproducibility

The repository includes the implementation, tests, benchmark organization, dataset documentation, and evaluation scripts required to reproduce the experiments.

For reproducible evaluation:

1. Use the specified Python environment.
2. Install the dependencies.
3. Download the required Ollama models.
4. Ensure the cleaned benchmark files are available.
5. Run the evaluation using the documented commands.
6. Inspect the generated results in `evaluation/results/`.

The task split uses a fixed random seed of 42.

## 12. Author

**TestSpecGuard**

Research implementation project.

GitHub Repository:

https://github.com/waseem22md-creator/TestSpecGuard
