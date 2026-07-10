"""One-time scraper: export the TUM Student Representation group directory to CSV.

Kept in the repo as the provenance record for `data/raw/tum_student_groups.csv` —
how the dataset was produced. Run once:

    uv run python scripts/scrape_tum_groups.py

The source is the accredited-groups directory maintained by the Student
Representation (SV); a single GET of a server-rendered TYPO3 page returns all
groups. This is a curation distinct from the TUM CST student-clubs gallery
(see scrape_tum_clubs.py) — dedupe on `name` when combining the two datasets.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

SOURCE_URL = "https://www.sv.tum.de/en/sv/student-groups/"
BASE_URL = "https://www.sv.tum.de"
OUTPUT = Path("data/raw/tum_student_groups.csv")

USER_AGENT = (
    "career-detective/0.1 (hackathon student project; "
    "one-time student-groups dataset export)"
)


def fetch_html(url: str = SOURCE_URL) -> str:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    return resp.text


def _normalize_website(href: str | None) -> str:
    if not href:
        return ""
    href = href.strip()
    if href.startswith("//"):  # protocol-relative
        return "https:" + href
    if href.startswith("/"):  # internal SV link
        return BASE_URL + href
    return href


def parse_groups(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    rows: dict[str, dict[str, str]] = {}

    for card in soup.select(".c-card"):
        classes = card.get("class", [])
        # Group cards carry a logo; skip layout/intro cards (no image) and the
        # contact-person cards (committee members) marked c-card--contact.
        img = card.select_one("figure.image img")
        if not img or "c-card--contact" in classes:
            continue

        name_el = card.find(["h1", "h2", "h3", "h4", "h5", "h6"])
        name = name_el.get_text(strip=True) if name_el else ""
        if not name:
            continue

        desc_el = card.select_one(".ce-bodytext")
        description = desc_el.get_text(" ", strip=True) if desc_el else ""

        link_el = name_el.find("a", class_="external-link") if name_el else None
        if not (link_el and link_el.get("href")):
            link_el = card.select_one("figure.image a[href]")
        website = _normalize_website(link_el.get("href") if link_el else None)

        logo_url = _normalize_website(img.get("src"))

        rows[name] = {
            "name": name,
            "description": description,
            "website": website,
            "logo_url": logo_url,
        }

    return [rows[name] for name in sorted(rows)]


def main() -> None:
    groups = parse_groups(fetch_html())
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(
        groups,
        columns=["name", "description", "website", "logo_url"],
    )
    df.to_csv(OUTPUT, index=False)
    print(f"Wrote {len(df)} groups to {OUTPUT}")


if __name__ == "__main__":
    main()
