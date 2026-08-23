import logging
import sys

CATEGORIES = [
    "game",
    "db",
    "simulation",
    "llm",
    "narration",
    "context",
    "api",
    "visual",
]


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    )

    root = logging.getLogger("everreach")
    root.setLevel(level)
    root.addHandler(handler)
    root.propagate = False


def get_logger(category: str) -> logging.Logger:
    if category not in CATEGORIES:
        raise ValueError(f"Unknown logging category: {category}")
    return logging.getLogger(f"everreach.{category}")
