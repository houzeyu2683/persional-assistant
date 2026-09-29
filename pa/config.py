"""Load settings from .env."""

from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    model_name: str
    model_url: str
    model_key: str
    model_context: int | None  # max input tokens; drives when summarization kicks in
    workspace: Path


def load_settings() -> Settings:
    missing = [k for k in ("MODEL_NAME", "MODEL_URL", "MODEL_KEY") if not os.getenv(k)]
    if missing:
        raise RuntimeError(f"Missing in .env: {', '.join(missing)}")
    workspace = Path(os.getenv("PA_WORKSPACE", PROJECT_ROOT / "workspace")).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    return Settings(
        model_name=os.environ["MODEL_NAME"],
        model_url=os.environ["MODEL_URL"],
        model_key=os.environ["MODEL_KEY"],
        model_context=int(os.environ["MODEL_CONTEXT"]) if os.getenv("MODEL_CONTEXT") else None,
        workspace=workspace,
    )
