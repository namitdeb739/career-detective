"""Entry point for career-detective."""

from __future__ import annotations

import logging

from career_detective.logging_config import configure_logging

logger = logging.getLogger(__name__)


def main() -> None:
    """Run the main application.

    This is the CLI entry point configured in ``pyproject.toml``
    under ``[project.scripts]``.
    """
    configure_logging()
    logger.info("Starting career-detective")
    print("Hello from career-detective!")


if __name__ == "__main__":
    main()
