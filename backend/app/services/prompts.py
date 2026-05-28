from functools import lru_cache
from pathlib import Path


PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"


@lru_cache
def load_prompt(name: str) -> str:
    path = PROMPT_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")
