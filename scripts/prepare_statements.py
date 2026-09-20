"""Download FOMC press-conference PDFs and extract chair opening statements.

Reuses logic from keltokhy/jsort bench/fed.py (public domain Fed transcripts).
Writes data/clean/statements.jsonl with doc_id, date, text, source, raw_text.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from strip_meta import strip_meta  # noqa: E402

RAW_PDF = ROOT / "data" / "raw" / "jsort" / "pdfs"
OUT_JSONL = ROOT / "data" / "clean" / "statements.jsonl"
OUT_TXT = ROOT / "data" / "clean" / "statements_txt"
CALENDAR = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
TRANSCRIPT = "https://www.federalreserve.gov/mediacenter/files/FOMCpresconf{}.pdf"

FURNITURE = re.compile(
    r"^(Page \d+ of \d+|PRELIMINARY|FINAL|[A-Z][a-z]+ \d{1,2}, \d{4}|"
    r"(Transcript of )?Chair\w* \w+[’']s Press Conference)$"
)
SPEAKER = re.compile(r"^((?:[A-Z][A-Z’'\-]+\.? ){1,3}[A-Z][A-Z’'\-]+)[.:] ")


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (fedjev-bench)"})
    with urllib.request.urlopen(request, timeout=90) as r:
        return r.read()


def opening_statement(raw: str) -> tuple[str, str]:
    lines = [l.strip() for l in raw.splitlines()]
    lines = [l for l in lines if l and not FURNITURE.match(l)]
    start = next(
        i
        for i, l in enumerate(lines)
        if (m := SPEAKER.match(l)) and m.group(1).startswith("CHAIR")
    )
    chair = SPEAKER.match(lines[start]).group(1)
    end = next((i for i in range(start + 1, len(lines)) if SPEAKER.match(lines[i])), len(lines))
    text = " ".join(lines[start:end])[len(chair) + 2 :]
    return re.sub(r"\s+", " ", text).strip(), chair.title()


def pressconf_days() -> list[str]:
    page = fetch(CALENDAR).decode("utf-8", "replace")
    days = sorted(
        set(re.findall(r"fomcpress?conf(\d{8})\.htm", page))
        | {"20110427", "20110622", "20111102"}
    )
    return days


def main() -> None:
    RAW_PDF.mkdir(parents=True, exist_ok=True)
    OUT_TXT.mkdir(parents=True, exist_ok=True)
    days = pressconf_days()
    records = []
    for day in days:
        pdf = RAW_PDF / f"{day}.pdf"
        if not pdf.exists() or pdf.stat().st_size < 1000:
            try:
                pdf.write_bytes(fetch(TRANSCRIPT.format(day)))
                print(f"downloaded {day}")
            except Exception as e:
                print(f"{day}: no transcript ({e})")
                continue
            time.sleep(0.4)
        try:
            raw = subprocess.run(
                ["pdftotext", str(pdf), "-"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
        except subprocess.CalledProcessError as e:
            print(f"{day}: pdftotext failed ({e})")
            continue
        try:
            text, chair = opening_statement(raw)
        except StopIteration:
            print(f"{day}: could not find CHAIR opening")
            continue
        iso = f"{day[:4]}-{day[4:6]}-{day[6:]}"
        doc_id = f"stmt-{iso}"
        cleaned = strip_meta(text)
        (OUT_TXT / f"{iso}.txt").write_text(text + "\n")
        records.append(
            {
                "doc_id": doc_id,
                "date": iso,
                "text": cleaned,
                "source": "statement",
                "raw_text": text,
                "chair": chair,
                "words": len(text.split()),
            }
        )
        print(f"{iso}  {chair:16s} {len(text.split()):5d} words")

    OUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    with OUT_JSONL.open("w") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    index_path = ROOT / "data" / "clean" / "statements_index.json"
    index_path.write_text(
        json.dumps(
            [{"doc_id": r["doc_id"], "date": r["date"], "chair": r["chair"], "words": r["words"]} for r in records],
            indent=2,
        )
    )
    print(f"Wrote {len(records)} statements -> {OUT_JSONL}")


if __name__ == "__main__":
    main()
