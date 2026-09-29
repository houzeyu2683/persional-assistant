"""Build the deep agent. Add tools / memory / skills here later."""

import os

from deepagents import create_deep_agent
from deepagents.backends.local_shell import LocalShellBackend
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver

from pa.config import Settings

SYSTEM_PROMPT = """你是使用者的個人助理，預設使用繁體中文回答。
你的工作目錄是一個 workspace，可以在裡面讀寫檔案，也可以用 execute 工具執行 shell 指令（例如 python 程式）。
執行指令前使用者會逐一審核。回答要簡潔、直接。"""


def build_agent(settings: Settings):
    model = ChatOpenAI(
        model=settings.model_name,
        base_url=settings.model_url,
        api_key=settings.model_key,
    )
    # Shell commands run in the workspace; pass only a minimal env so API keys
    # loaded from .env never leak into agent-run commands.
    backend = LocalShellBackend(
        root_dir=settings.workspace,
        virtual_mode=True,
        env={k: os.environ[k] for k in ("PATH", "HOME", "LANG", "TERM") if k in os.environ},
    )
    return create_deep_agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        backend=backend,
        interrupt_on={"execute": {"allowed_decisions": ["approve", "reject"]}},
        checkpointer=InMemorySaver(),
    )
