"""
Parse downloaded PYQ PDFs (in pyqs/raw/) into structured JSON (pyqs.json),
one entry per question, tagged with year and paper (prelims_gs1, mains_gs1,
mains_gs2, mains_gs3, mains_gs4).

Expected filenames: <year>_<paper>.pdf, e.g. 2024_mains_gs2.pdf,
2019_prelims_gs1.pdf - matching what fetch_pyqs.py produces (auto or manual).

Question numbering/format differs between Prelims (numbered MCQs, no marks
shown) and Mains (numbered, often with marks/word-limit like "(10 marks,
150 words)") - both are handled by the same numbered-line split, since
UPSC's Mains papers also start each question with "1.", "2." etc. Marks/word
limits, if present, are captured separately when the pattern is found.
"""

import json
import re
from pathlib import Path

import pdfplumber

RAW_DIR = Path(__file__).parent / "pyqs" / "raw"
OUT_FILE = Path(__file__).parent / "pyqs.json"

FILENAME_PATTERN = re.compile(r"(\d{4})_(prelims_gs1|mains_gs1|mains_gs2|mains_gs3|mains_gs4)\.pdf")
QUESTION_START = re.compile(r"^\s*(\d{1,3})\.\s+")
MARKS_PATTERN = re.compile(r"\((\d{1,3})\s*marks?[,;]?\s*(\d{2,4})?\s*words?\)?", re.IGNORECASE)


def extract_text(pdf_path: Path) -> str:
    text_parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text_parts.append(page.extract_text() or "")
    return "\n".join(text_parts)


def split_questions(text: str, year: int, paper: str) -> list[dict]:
    lines = text.split("\n")
    questions = []
    current = []

    def flush():
        if current:
            q_text = " ".join(current).strip()
            if len(q_text) > 15:  # skip noise/header fragments
                marks_match = MARKS_PATTERN.search(q_text)
                questions.append({
                    "year": year,
                    "paper": paper,          # prelims_gs1 | mains_gs1 | mains_gs2 | mains_gs3 | mains_gs4
                    "question": q_text,
                    "marks": int(marks_match.group(1)) if marks_match else None,
                    "topics": []              # fill in manually or via LLM tagging later
                })

    for line in lines:
        if QUESTION_START.match(line):
            flush()
            current = [line]
        else:
            current.append(line)
    flush()
    return questions


def main():
    all_questions = []
    pdfs = sorted(RAW_DIR.glob("*.pdf"))

    if not pdfs:
        print(f"No PDFs found in {RAW_DIR}. Run fetch_pyqs.py first, "
              f"or drop PDFs in manually (name them <year>_<paper>.pdf, "
              f"paper = prelims_gs1 | mains_gs1 | mains_gs2 | mains_gs3 | mains_gs4).")
        return

    skipped = []
    for pdf_path in pdfs:
        match = FILENAME_PATTERN.match(pdf_path.name)
        if not match:
            skipped.append(pdf_path.name)
            continue

        year, paper = int(match.group(1)), match.group(2)
        print(f"Parsing {pdf_path.name}...")
        text = extract_text(pdf_path)
        questions = split_questions(text, year, paper)
        print(f"  -> extracted {len(questions)} questions")
        all_questions.extend(questions)

    OUT_FILE.write_text(json.dumps(all_questions, indent=2, ensure_ascii=False))
    print(f"\nWrote {len(all_questions)} total questions to {OUT_FILE}")

    if skipped:
        print(f"\n[warn] skipped {len(skipped)} file(s) with unrecognized naming: {skipped}")
        print("Rename to <year>_<paper>.pdf (e.g. 2023_mains_gs2.pdf) and re-run.")

    print("\nTip: spot-check a few entries - PDF text extraction sometimes "
          "merges or splits lines oddly, especially for Mains questions with "
          "sub-parts (a)/(b) or embedded marks/word-limit annotations.")


if __name__ == "__main__":
    main()
