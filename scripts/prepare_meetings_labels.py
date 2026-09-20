"""Build meetings.csv and labels (parquet+csv) from Fed calendars + FRED.

Label definitions (aligned with jsort/bench/fed.py where applicable):
  d_same  = DFEDTARU[day+1] - DFEDTARU[day-1]  (pp; new range effective next day)
  y_action = sign(d_same) in {+1,0,-1}
  d_90    = DFEDTARU[t+90] - DFEDTARU[t] (nearest available on/before)
  d_2y    = DGS2[t] - DGS2[t-1] (last available on/before each date)
"""
from __future__ import annotations

import csv
import json
import re
import time
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FRED_DIR = ROOT / "data" / "raw" / "fred"
CLEAN = ROOT / "data" / "clean"
LABELS = ROOT / "data" / "labels"
CALENDAR = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
HIST = "https://www.federalreserve.gov/monetarypolicy/fomchistorical{}.htm"
PRESSER = "https://www.federalreserve.gov/mediacenter/files/FOMCpresconf{}.pdf"
STATEMENT_TMPL = "https://www.federalreserve.gov/newsevents/pressreleases/monetary{}a.htm"

# Pre-registered extraordinary exclusions (unscheduled / intermeeting)
EXCLUDE_MAIN = {"2020-03-03", "2020-03-15"}
FLAG_SVB = {"2023-03-22"}

START = date(2011, 1, 1)
END = date(2026, 9, 20)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (fedjev-bench)"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read().decode("utf-8", "replace")


def load_fred(series: str) -> dict[date, float]:
    path = FRED_DIR / f"{series}.csv"
    out: dict[date, float] = {}
    with path.open() as f:
        reader = csv.DictReader(f)
        # column may be series id
        for row in reader:
            d = date.fromisoformat(row["observation_date"])
            v = row.get(series) or row.get(list(row.keys())[1])
            if v in ("", ".", None):
                continue
            out[d] = float(v)
    return out


def last_on_or_before(series: dict[date, float], day: date) -> tuple[date, float] | None:
    d = day
    for _ in range(14):
        if d in series:
            return d, series[d]
        d -= timedelta(days=1)
    return None


def value_on_or_before(series: dict[date, float], day: date) -> float | None:
    hit = last_on_or_before(series, day)
    return hit[1] if hit else None


def chair_for(day: date) -> str:
    if day < date(2014, 2, 3):
        return "Bernanke"
    if day < date(2018, 2, 5):
        return "Yellen"
    return "Powell"


def parse_calendar_meetings() -> list[dict]:
    """Parse current calendars page + historical year pages for meeting end dates."""
    meetings: dict[str, dict] = {}

    # Primary: press conference / statement dates from current calendars (covers recent years)
    page = fetch(CALENDAR)
    for yyyymmdd in set(re.findall(r"monetary(\d{8})a\.htm", page)):
        iso = f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:]}"
        d = date.fromisoformat(iso)
        if d < START or d > END:
            continue
        meetings[iso] = {
            "date": iso,
            "statement_url": STATEMENT_TMPL.format(yyyymmdd),
            "presser_pdf": PRESSER.format(yyyymmdd),
            "is_scheduled": iso not in EXCLUDE_MAIN,
            "is_sep": False,  # filled later from SEP mentions / known SEP meetings
            "chair": chair_for(d),
        }

    # Also pressconf links (may include days without separate monetary link pattern)
    for yyyymmdd in set(re.findall(r"fomcpress?conf(\d{8})\.htm", page)) | {
        "20110427",
        "20110622",
        "20111102",
    }:
        iso = f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:]}"
        d = date.fromisoformat(iso)
        if d < START or d > END:
            continue
        if iso not in meetings:
            meetings[iso] = {
                "date": iso,
                "statement_url": STATEMENT_TMPL.format(yyyymmdd),
                "presser_pdf": PRESSER.format(yyyymmdd),
                "is_scheduled": iso not in EXCLUDE_MAIN,
                "is_sep": False,
                "chair": chair_for(d),
            }
        else:
            meetings[iso]["presser_pdf"] = PRESSER.format(yyyymmdd)

    # Historical pages for 2011–2017 style listings (supplement)
    for year in range(2011, 2018):
        try:
            hist = fetch(HIST.format(year))
            time.sleep(0.2)
        except Exception as e:
            print(f"hist {year} failed: {e}")
            continue
        # monetaryYYYYMMDDa.htm or fomcstatementYYYYMMDD.htm
        for yyyymmdd in set(
            re.findall(r"monetary(\d{8})a\.htm", hist)
            + re.findall(r"fomcstatement(\d{8})\.htm", hist)
            + re.findall(r"fomcpress?conf(\d{8})", hist)
        ):
            iso = f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:]}"
            d = date.fromisoformat(iso)
            if d < START or d > END:
                continue
            if iso not in meetings:
                stmt = STATEMENT_TMPL.format(yyyymmdd)
                if "fomcstatement" in hist and year < 2016:
                    # older statements sometimes under different path; keep monetary URL as best effort
                    pass
                meetings[iso] = {
                    "date": iso,
                    "statement_url": stmt,
                    "presser_pdf": PRESSER.format(yyyymmdd),
                    "is_scheduled": iso not in EXCLUDE_MAIN,
                    "is_sep": False,
                    "chair": chair_for(d),
                }

    # Mark known SEP (Summary of Economic Projections) meeting months: typically Mar, Jun, Sep, Dec
    # More precisely: meetings with SEPs — quarterly projection meetings.
    # Use heuristic: month in {3,6,9,12} for scheduled meetings (Fed SEP cadence).
    for iso, m in meetings.items():
        d = date.fromisoformat(iso)
        m["is_sep"] = d.month in (3, 6, 9, 12) and m["is_scheduled"]

    # Force exclusions
    for iso in EXCLUDE_MAIN:
        if iso in meetings:
            meetings[iso]["is_scheduled"] = False

    return [meetings[k] for k in sorted(meetings)]


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


def sign(x: float) -> int:
    if x > 0:
        return 1
    if x < 0:
        return -1
    return 0


def main() -> None:
    CLEAN.mkdir(parents=True, exist_ok=True)
    LABELS.mkdir(parents=True, exist_ok=True)

    dfed = load_fred("DFEDTARU")
    dgs2 = load_fred("DGS2")
    last_fred = max(dfed)

    meetings = parse_calendar_meetings()
    print(f"parsed {len(meetings)} meetings")

    # Match to statement corpus dates
    stmt_dates = set()
    stmt_path = CLEAN / "statements.jsonl"
    if stmt_path.exists():
        with stmt_path.open() as f:
            for line in f:
                stmt_dates.add(json.loads(line)["date"])

    rows = []
    for m in meetings:
        d = date.fromisoformat(m["date"])
        # d_same per jsort: (day+1) - (day-1)
        v_after = value_on_or_before(dfed, min(d + timedelta(days=1), last_fred))
        v_before = value_on_or_before(dfed, d - timedelta(days=1))
        d_same = None
        if v_after is not None and v_before is not None:
            d_same = round(v_after - v_before, 4)

        # d_90: DFEDTARU[t+90] - DFEDTARU[t]
        v_t = value_on_or_before(dfed, d)
        v_90 = value_on_or_before(dfed, d + timedelta(days=90))
        d_90 = None
        if v_t is not None and v_90 is not None and (d + timedelta(days=90)) <= last_fred + timedelta(days=5):
            # only if we have ~90 days of data after
            if last_fred >= d + timedelta(days=80):
                d_90 = round(v_90 - v_t, 4)

        v2_t = value_on_or_before(dgs2, d)
        v2_prev = value_on_or_before(dgs2, d - timedelta(days=1))
        d_2y = None
        if v2_t is not None and v2_prev is not None:
            d_2y = round(v2_t - v2_prev, 4)

        n_hawk, n_dove, dissent_note = scrape_dissents(m["statement_url"])
        time.sleep(0.25)

        # Blank presser if we know there's no PDF in corpus and HEAD fails — leave URL; note later
        presser = m["presser_pdf"]
        if m["date"] not in stmt_dates and m["date"] in EXCLUDE_MAIN:
            # still keep URL pattern
            pass

        rows.append(
            {
                "date": m["date"],
                "statement_url": m["statement_url"],
                "presser_pdf": presser,
                "is_scheduled": bool(m["is_scheduled"]),
                "is_sep": bool(m["is_sep"]),
                "chair": m["chair"],
                "flag_svb": m["date"] in FLAG_SVB,
                "exclude_main": m["date"] in EXCLUDE_MAIN,
                "has_opening_statement": m["date"] in stmt_dates,
                "d_same": d_same,
                "y_action": sign(d_same) if d_same is not None else None,
                "d_90": d_90,
                "d_2y": d_2y,
                "n_hawk_dissent": n_hawk,
                "n_dove_dissent": n_dove,
                "dissent_note": dissent_note,
            }
        )
        print(
            f"{m['date']} sched={m['is_scheduled']} d_same={d_same} y={sign(d_same) if d_same is not None else None} "
            f"dissents={n_hawk}/{n_dove} ({dissent_note})"
        )

    # meetings.csv (requested columns + flags)
    meet_cols = ["date", "statement_url", "presser_pdf", "is_scheduled", "is_sep", "chair", "flag_svb", "exclude_main"]
    pd.DataFrame(rows)[meet_cols].to_csv(CLEAN / "meetings.csv", index=False)

    label_df = pd.DataFrame(rows)
    label_df.to_csv(LABELS / "meetings.csv", index=False)
    label_df.to_parquet(LABELS / "meetings.parquet", index=False)
    print(f"Wrote {len(rows)} meetings -> {CLEAN / 'meetings.csv'} and labels")


if __name__ == "__main__":
    main()
