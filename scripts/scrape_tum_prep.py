"""One-time scraper: export TUM PREP research projects to a CSV.

Kept in the repo as the provenance record for `data/raw/tum_prep_projects.csv` —
how the dataset was produced. Run once:

    uv run python scripts/scrape_tum_prep.py

The source is a Confluence (BayernCollab) space. The project list is a ConfiForm
table on the overview page; each row links to a per-project description page. Both
are readable anonymously via Confluence's REST API using `body.export_view`, which
renders the ConfiForm macros into real values (unlike `body.storage`).

robots.txt sets `crawl-delay: 60` for crawlers; this is a one-time export of ~83
pages, so REQUEST_DELAY keeps it polite without the full 60s between requests.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://collab.dvb.bayern"
OVERVIEW_PAGE_ID = "69901187"  # "TUM PREP Projects" — the ConfiForm project table
OUTPUT = Path("data/raw/tum_prep_projects.csv")

REQUEST_DELAY_SECONDS = 1.0

USER_AGENT = (
    "career-detective/0.1 (hackathon student project; "
    "one-time PREP-projects dataset export)"
)

# Field keys as rendered by ConfiForm (`cf-field` / `id="i_sel_<key>"`).
OVERVIEW_FIELDS = {
    "dep": "department",
    "pn": "project_name",
    "keyword": "keyword",
    "pl": "location",
    "group": "student_background",
    "fd": "further_disciplines",
    "pc": "project_code",
}

COLUMNS = [
    "project_code",
    "project_name",
    "department",
    "keyword",
    "research_area",
    "chair_institute",
    "student_background",
    "further_disciplines",
    "location",
    "supervisor",
    "supervisor_email",
    "description",
    "page_url",
]


def fetch_export_view(page_id: str) -> str:
    """Return the rendered (macros-expanded) body of a Confluence page."""
    url = f"{BASE_URL}/rest/api/content/{page_id}"
    resp = requests.get(
        url,
        params={"expand": "body.export_view"},
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["body"]["export_view"]["value"]


def _text(el: object) -> str:
    if el is None:
        return ""
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()


def _page_id(url: str) -> str | None:
    match = re.search(r"/pages/(\d+)/", url)
    return match.group(1) if match else None


def parse_overview(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    projects: list[dict[str, str]] = []

    for entry in soup.select("tr.cf-entry-container"):
        row = {col: "" for col in COLUMNS}
        for td in entry.select("td[cf-field]"):
            key = td.get("cf-field")
            if key == "mylink":
                link = td.find("a")
                row["page_url"] = link.get("href", "").strip() if link else ""
            elif key in OVERVIEW_FIELDS:
                row[OVERVIEW_FIELDS[key]] = _text(td)
        if row["project_name"]:
            projects.append(row)

    return projects


def enrich_from_detail(row: dict[str, str]) -> None:
    """Add research area, chair, supervisor, and full description in place."""
    page_id = _page_id(row["page_url"])
    if not page_id:
        return

    try:
        html = fetch_export_view(page_id)
    except requests.HTTPError as err:
        print(f"  skipping {row['project_name']!r}: {err.response.status_code}")
        return

    soup = BeautifulSoup(html, "html.parser")

    def sel(field: str) -> str:
        return _text(soup.find(id=f"i_sel_{field}"))

    row["research_area"] = sel("research")
    row["chair_institute"] = sel("chair")
    row["description"] = sel("pd")
    row["supervisor"] = " ".join(
        part for part in (sel("st"), sel("fn"), sel("sn")) if part
    )
    row["supervisor_email"] = sel("mail")
    if not row["further_disciplines"]:
        row["further_disciplines"] = sel("fd")


def main() -> None:
    projects = parse_overview(fetch_export_view(OVERVIEW_PAGE_ID))
    print(f"Found {len(projects)} projects; fetching descriptions...")

    for i, row in enumerate(projects):
        enrich_from_detail(row)
        if i < len(projects) - 1:
            time.sleep(REQUEST_DELAY_SECONDS)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(projects, columns=COLUMNS)
    df.to_csv(OUTPUT, index=False)
    print(f"Wrote {len(df)} projects to {OUTPUT}")


if __name__ == "__main__":
    main()
