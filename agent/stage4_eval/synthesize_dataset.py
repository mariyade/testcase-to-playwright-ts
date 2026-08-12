from __future__ import annotations

import argparse
from pathlib import Path


# Optional CLI for creating portfolio-safe DeepEval goldens from sanitized docs.
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate synthetic DeepEval goldens from local documentation."
    )
    parser.add_argument(
        "documents",
        nargs="+",
        help="Sanitized .txt/.md/.pdf/.docx files used as Synthesizer source material.",
    )
    parser.add_argument(
        "--output-dir",
        default="agent/stage4_eval/datasets/synthetic",
        help="Directory where DeepEval save_as() writes the JSONL dataset.",
    )
    parser.add_argument(
        "--include-test-cases",
        action="store_true",
        help="Also save generated DeepEval test cases when supported by your DeepEval version.",
    )
    args = parser.parse_args()

    from deepeval.dataset import EvaluationDataset
    from deepeval.synthesizer import Synthesizer

    document_paths = [str(Path(document)) for document in args.documents]
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    goldens = Synthesizer().generate_goldens_from_docs(document_paths=document_paths)
    dataset = EvaluationDataset(goldens=goldens)

    save_options = {
        "file_type": "jsonl",
        "directory": str(output_dir),
    }
    if args.include_test_cases:
        save_options["include_test_cases"] = True

    dataset.save_as(**save_options)
    print(f"Saved {len(goldens)} synthetic goldens to {output_dir}")


if __name__ == "__main__":
    main()
