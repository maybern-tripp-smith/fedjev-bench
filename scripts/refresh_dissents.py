"""Re-scrape n_hawk_dissent / n_dove_dissent into existing meetings labels."""
from __future__ import annotations

import re
import time
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
LABELS = ROOT / "data" / "labels"


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (fedjev-bench)"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read().decode("utf-8", "replace")


def scrape_dissents(statement_url: str):
    try:
        html = fetch(statement_url)
    except Exception as e:
        return None, None, f"fetch_failed:{e}"
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    # Protect middle initials so sentence-end "." is real
    protected = re.sub(r"\b([A-Z])\.", r"\1·", text)

    m = re.search(r"Voting against.{0,1200}?\.(?:\s|$)", protected, re.I)
    if not m:
        if re.search(
            r"unanimous|Voting against the action:?\s*None|there were no dissenting",
            text,
            re.I,
        ):
            return 0, 0, "unanimous_or_none"
        return 0, 0, "no_against_paragraph"
    para = m.group(0).replace("·", ".")
    if re.search(r"Voting against[^:]*:\s*None\b", para, re.I):
        return 0, 0, "none"

    against = re.search(r"Voting against[^:]*:?\s*(.+?)(?:,?\s*who\b|\.\s|$)", para, re.I)
    names_blob = against.group(1) if against else ""
    if re.search(r"^\s*None\b", names_blob, re.I):
        return 0, 0, "none"

    name_re = re.compile(
        r"[A-Z][a-zA-Z\-']+(?:\s+[A-Z]\.)?(?:\s+[A-Z][a-zA-Z\-']+)+"
    )
    names = name_re.findall(names_blob)
    if not names:
        parts = re.split(r",| and ", names_blob)
        names = [p.strip() for p in parts if p and re.search(r"[A-Z][a-z]+", p)]
    n = len(names)

    hawk = bool(
        re.search(
            r"prefer\w*(?:\s+\w+){0,8}\s+to\s+(?:raise|increase|tighten)|"
            r"opposed (?:additional )?(?:easing|accommodation|asset purchases)|"
            r"concerned that (?:the )?continued high level of monetary accommod|"
            r"preferred (?:a )?(?:larger|higher|more aggressive)|"
            r"should signal more strongly|"
            r"objected to the guidance",
            para,
            re.I,
        )
    )
    dove = bool(
        re.search(
            r"prefer\w*(?:\s+\w+){0,8}\s+to\s+(?:lower|cut|reduce|ease|maintain|leave|keep)|"
            r"supported additional (?:policy )?accommodation|"
            r"preferred (?:at this meeting )?to maintain|"
            r"preferred (?:no change|to leave)|"
            r"supported no change|"
            r"preferred (?:a )?smaller|"
            r"who preferred to omit|"
            r"sluggishness in the inflat|"
            r"unemployment rate still elevated",
            para,
            re.I,
        )
    )

    if hawk and not dove:
        return max(n, 1), 0, "hawk_dissent"
    if dove and not hawk:
        return 0, max(n, 1), "dove_dissent"
    if hawk and dove:
        return None, None, "mixed_dissent_language"
    return None, None, f"against_unclear:{para[:160]}"


def main() -> None:
    df = pd.read_csv(LABELS / "meetings.csv")
    for i, row in df.iterrows():
        nh, nd, note = scrape_dissents(row["statement_url"])
        df.at[i, "n_hawk_dissent"] = nh if nh is not None else pd.NA
        df.at[i, "n_dove_dissent"] = nd if nd is not None else pd.NA
        df.at[i, "dissent_note"] = note
        print(f"{row['date']} hawk={nh} dove={nd} {note[:100]}")
        time.sleep(0.15)
    df.to_csv(LABELS / "meetings.csv", index=False)
    df.to_parquet(LABELS / "meetings.parquet", index=False)
    unclear = df["dissent_note"].astype(str).str.startswith("against_unclear").sum()
    print(f"done; against_unclear={unclear}/{len(df)}")
    print("hawk non-null", df["n_hawk_dissent"].notna().sum(), "dove non-null", df["n_dove_dissent"].notna().sum())
    print("rows with hawk>0", (df["n_hawk_dissent"].fillna(0) > 0).sum())
    print("rows with dove>0", (df["n_dove_dissent"].fillna(0) > 0).sum())


if __name__ == "__main__":
    main()
