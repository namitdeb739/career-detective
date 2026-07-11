"""Streamlit dashboard for career-detective.

Run with:  just app   (or: uv run streamlit run src/career_detective/app.py)
"""

from __future__ import annotations

import streamlit as st


def main() -> None:
    """Render the dashboard."""
    st.title("career-detective")
    st.write("AI powered job search tool for German tech industry")


if __name__ == "__main__":
    main()
