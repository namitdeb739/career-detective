"""One-time scraper: export TUM's student club gallery to a CSV.

Kept in the repo as the provenance record for `data/raw/tum_clubs.csv` — how the
dataset was produced. Run once:

    uv run python scripts/scrape_tum_clubs.py

The source is a server-rendered TYPO3 page; a single GET returns all ~200 clubs.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

SOURCE_URL = "https://www.tum.de/en/community/campus-life/student-clubs-gallery"
BASE_URL = "https://www.tum.de"
OUTPUT = Path("data/raw/tum_clubs.csv")

USER_AGENT = (
    "career-detective/0.1 (hackathon student project; "
    "one-time student-club dataset export)"
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
    if href.startswith("/"):  # internal TUM link
        return BASE_URL + href
    return href


def parse_clubs(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    rows: dict[str, dict[str, str]] = {}

    for card in soup.select("div.c-club"):
        name_el = card.select_one(".c-club__content h4")
        name = name_el.get_text(strip=True) if name_el else ""
        if not name:
            continue

        desc_el = card.select_one(".c-club__content p")
        description = desc_el.get_text(strip=True) if desc_el else ""

        focus_areas = [
            a.get_text(strip=True) for a in card.select(".c-club__category a")
        ]

        link_el = card.select_one(".c-club__link a")
        website = _normalize_website(link_el.get("href") if link_el else None)

        img_el = card.select_one(".c-club__image img")
        logo_url = _normalize_website(img_el.get("src") if img_el else None)

        rows[name] = {
            "name": name,
            "description": description,
            "focus_areas": "|".join(focus_areas),
            "website": website,
            "logo_url": logo_url,
        }

    return [rows[name] for name in sorted(rows)]


def main() -> None:
    clubs = parse_clubs(fetch_html())
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(
        clubs,
        columns=["name", "description", "focus_areas", "website", "logo_url"],
    )
    df.to_csv(OUTPUT, index=False)
    print(f"Wrote {len(df)} clubs to {OUTPUT}")


if __name__ == "__main__":
    main()
