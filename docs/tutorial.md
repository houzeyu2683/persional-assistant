# 用 deepagents + Textual 打造一個會寫程式的終端機個人助理

這篇文章會一步一步帶你做出一個在終端機裡運作的個人助理。它可以：

- 跟你聊天，回答會像打字一樣**即時串流**出來
- 在一個專屬資料夾（`workspace/`）裡**讀寫檔案**
- **寫程式並執行**，而且每次執行前都會先問你「可以嗎？」
- 對話太長時**自動濃縮**舊對話，也可以輸入 `/compact` 手動濃縮

我們會用到：

| 工具 | 用途 |
|---|---|
| deepagents | Agent 核心，內建檔案工具、執行指令、子代理、對話濃縮 |
| LangChain / LangGraph | deepagents 底層，負責模型串接與對話狀態 |
| Textual | 在終端機裡做出有按鈕、對話框的介面 |
| OpenRouter | 模型 API（相容 OpenAI 格式，本文用 `google/gemma-4-31b-it`） |

## 完成後的專案結構

```
persional-assistant/
├── src/
│   └── pa/
│       ├── __init__.py
│       ├── config.py        # 讀取 .env 設定
│       ├── agent.py         # 建立 deep agent
│       └── tui/
│           ├── __init__.py
│           └── app.py       # Textual 聊天介面
├── scripts/
│   └── try_summarization.sh # 測試對話濃縮用
├── workspace/               # 助理讀寫檔案、執行指令的地方
├── pyproject.toml
├── .env.sample
├── .env                     # 你的金鑰（不要 commit）
└── .gitignore
```

整個程式的流程很單純：

```
你在 TUI 輸入訊息
   → app.py 把訊息交給 agent
   → agent（deepagents）呼叫模型、使用工具
   → app.py 把串流回來的文字和工具呼叫顯示在畫面上
   → 遇到「執行指令」時暫停，跳出視窗問你 y / n
```

---

## 步驟 0：準備環境

建立一個獨立的 Python 環境（本文使用 Python 3.14）：

```bash
conda create -n pa python=3.14
conda activate pa
```

建立專案資料夾：

```bash
mkdir persional-assistant && cd persional-assistant
git init
mkdir -p src/pa/tui scripts workspace
touch workspace/.gitkeep
```

到 OpenRouter 網站申請一把 API 金鑰，等一下會用到。

---

## 步驟 1：專案設定檔

### `pyproject.toml`

這個檔案告訴 Python：專案叫什麼、需要哪些套件，以及要產生一個叫 `pa` 的指令。

**檔案位置：`pyproject.toml`**

```toml
[project]
name = "personal-assistant"
version = "0.1.0"
description = "Personal assistant built on deepagents with a Textual TUI"
requires-python = ">=3.12"
dependencies = [
    "deepagents>=0.7.19",
    "langchain-openai>=1.6.6",
    "langchain-core>=1.6.5",
    "langgraph>=1.2.12",
    "textual>=8.2.8",
    "python-dotenv>=1.2.3",
]

[project.scripts]
pa = "pa.tui.app:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/pa"]
```

重點：

- `dependencies` 只列程式裡**直接 import** 的套件，`langchain`、`rich` 等會被自動帶進來。
- `[project.scripts]` 的 `pa = "pa.tui.app:main"` 代表：在終端機打 `pa`，就會執行 `src/pa/tui/app.py` 裡的 `main()`。
- 我們用 **src 結構**（程式碼放在 `src/pa/`），這是 Python 官方打包指南推薦的做法。

### `.env.sample` 與 `.env`

把設定放在 `.env`，金鑰就不會寫死在程式碼裡。`.env.sample` 是給別人參考的範本，**不含真正的金鑰**。

**檔案位置：`.env.sample`**

```bash
# Copy to .env and fill in: cp .env.sample .env

# Model (any OpenAI-compatible API, e.g. OpenRouter)
MODEL_NAME=google/gemma-4-31b-it
MODEL_URL=https://openrouter.ai/api/v1
MODEL_KEY=your-api-key-here

# Model context window in tokens; auto-summarization triggers at 85% of it.
# Lower it (e.g. 8000) to test summarization.
MODEL_CONTEXT=262144

# Optional: where the agent reads/writes files and runs commands (default: ./workspace)
# PA_WORKSPACE=/path/to/workspace
```

複製一份成 `.env`，填入你的金鑰：

```bash
cp .env.sample .env
```

`MODEL_CONTEXT` 是模型一次最多能讀多少 token，後面做「對話濃縮」時會用到。

### `.gitignore`

確保 `.env`（金鑰）和 `workspace/`（助理產生的檔案）不會被 commit。

**檔案位置：`.gitignore`**

```gitignore
# Secrets
.env
.env.*
!.env.example
!.env.sample

# Python
__pycache__/
*.py[cod]
*.egg-info/
.eggs/
build/
dist/

# Tooling caches
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/

# Virtual envs
.venv/
venv/

# Editors / OS
.vscode/
.idea/
.DS_Store

# LangGraph
.langgraph_api/

# Agent workspace
workspace/*
!workspace/.gitkeep
```

---

## 步驟 2：讀取設定 — `config.py`

先建立兩個 `__init__.py`，讓 Python 把資料夾當成套件：

**檔案位置：`src/pa/__init__.py`**

```python
"""Personal assistant built on deepagents."""
```

**檔案位置：`src/pa/tui/__init__.py`**（空檔案即可）

```bash
touch src/pa/tui/__init__.py
```

接著是讀取 `.env` 的模組。

**檔案位置：`src/pa/config.py`**

```python
"""Load settings from .env."""

from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # src/pa/config.py -> project root
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
```

重點：

- **`PROJECT_ROOT`**：`config.py` 位在 `src/pa/config.py`，往上三層（`parents[2]`）就是專案根目錄。這樣不管你在哪個資料夾執行 `pa`，都能找到 `.env` 和 `workspace/`。
- **`Settings`**：用 dataclass 把設定集中在一起，其他模組只要拿這個物件就好。
- **缺少必要設定時直接報錯**，比執行到一半才莫名失敗好除錯。
- **`MODEL_CONTEXT` 是選填**，沒填就是 `None`。

---

## 步驟 3：建立 Agent — `agent.py`

這是整個助理的核心，只有一個函式 `build_agent()`。

**檔案位置：`src/pa/agent.py`**

```python
"""Build the deep agent. Add tools / memory / skills here later."""

import os

from deepagents import create_deep_agent
from deepagents.backends.local_shell import LocalShellBackend
from deepagents.middleware.summarization import create_summarization_tool_middleware
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
        profile={"max_input_tokens": settings.model_context} if settings.model_context else None,
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
        # Adds the compact_conversation tool; auto-summarization stays the built-in one.
        middleware=[create_summarization_tool_middleware(model, backend)],
        interrupt_on={"execute": {"allowed_decisions": ["approve", "reject"]}},
        checkpointer=InMemorySaver(),
    )
```

我們一段一段看：

### 3-1. 模型

```python
model = ChatOpenAI(
    model=settings.model_name,
    base_url=settings.model_url,
    api_key=settings.model_key,
    profile={"max_input_tokens": settings.model_context} if settings.model_context else None,
)
```

OpenRouter 相容 OpenAI 的 API 格式，所以直接用 `ChatOpenAI`，把 `base_url` 換成 OpenRouter 就好。

`profile={"max_input_tokens": ...}` 是告訴 deepagents「這個模型最多讀多少 token」。deepagents 預設就會**自動濃縮對話**，有了這個數字，它會在用到 **85%** 時濃縮、保留最近 **10%** 的原文。沒給的話，它會退回保守的固定規則。

### 3-2. Backend：助理的「手」

```python
backend = LocalShellBackend(
    root_dir=settings.workspace,
    virtual_mode=True,
    env={k: os.environ[k] for k in ("PATH", "HOME", "LANG", "TERM") if k in os.environ},
)
```

deepagents 內建 `ls`、`read_file`、`write_file`、`edit_file`、`glob`、`grep`、`execute` 等工具，**backend 決定這些工具實際作用在哪裡**。

- `LocalShellBackend`：檔案工具作用在 `workspace/`，`execute` 在你的電腦上執行 shell 指令。
- `virtual_mode=True`：檔案工具只能碰 `workspace/` 裡的檔案。
- `env={...}`：只傳最基本的環境變數給執行的指令。因為 `.env` 被讀進了環境變數，這樣做可以**避免 API 金鑰被助理執行的程式讀到**。

> ⚠️ **安全提醒**：`virtual_mode` 只限制「檔案工具」，**`execute` 執行的 shell 指令沒有任何限制**，能做到你在這台電腦上能做的任何事。deepagents 官方也建議，使用 `LocalShellBackend` 時一定要開啟下面的「執行前確認」。

### 3-3. 組裝 Agent

```python
return create_deep_agent(
    model=model,
    system_prompt=SYSTEM_PROMPT,
    backend=backend,
    middleware=[create_summarization_tool_middleware(model, backend)],
    interrupt_on={"execute": {"allowed_decisions": ["approve", "reject"]}},
    checkpointer=InMemorySaver(),
)
```

- **`middleware=[create_summarization_tool_middleware(...)]`**：多給助理一個 `compact_conversation` 工具，讓我們可以手動濃縮對話。自動濃縮仍由 deepagents 內建的那一個負責，兩者共用狀態，**不會重複濃縮**。
- **`interrupt_on={"execute": ...}`**：每次要執行指令前**暫停**，等使用者同意或拒絕。這就是 Human-in-the-Loop（HITL）。
- **`checkpointer=InMemorySaver()`**：把對話記在記憶體裡，助理才記得前面聊過什麼。關掉程式就會消失。

---

## 步驟 4：聊天介面 — `app.py`

這是最長的檔案，先看完整程式碼，再拆解重點。

**檔案位置：`src/pa/tui/app.py`**

```python
"""Textual chat UI for the assistant."""

import json
import uuid

from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from langgraph.types import Command
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, Markdown, Static

from pa.agent import build_agent
from pa.config import load_settings

TOOL_RESULT_PREVIEW = 800
COMPACT_REQUEST = "請立刻呼叫 compact_conversation 工具來濃縮對話，不需要做其他事。"


def _short(value, limit: int = TOOL_RESULT_PREVIEW) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
    return text if len(text) <= limit else text[:limit] + f"\n… ({len(text) - limit} more chars)"


class ApprovalScreen(ModalScreen[bool]):
    """Ask the user to approve or reject a tool call."""

    BINDINGS = [("y", "decide(True)", "Approve"), ("n", "decide(False)", "Reject")]

    def __init__(self, name: str, args: dict) -> None:
        super().__init__()
        self.tool_name = name
        self.tool_args = args

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(f"[b]Agent wants to run[/b] [cyan]{self.tool_name}[/cyan]")
            yield Static(_short(self.tool_args), classes="args", markup=False)
            with Horizontal(id="buttons"):
                yield Button("Approve (y)", variant="success", id="approve")
                yield Button("Reject (n)", variant="error", id="reject")

    def action_decide(self, approved: bool) -> None:
        self.dismiss(approved)

    @on(Button.Pressed)
    def _pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "approve")


class AssistantApp(App):
    TITLE = "Personal Assistant"
    CSS = """
    #chat { padding: 0 1; }
    .user { background: $boost; border-left: thick $accent; padding: 0 1; margin: 1 0 0 0; }
    .assistant { margin: 1 0 0 0; }
    .tool { color: $text-muted; border-left: thick $warning; padding: 0 1; margin: 1 0 0 0; }
    .error { color: $error; border-left: thick $error; padding: 0 1; margin: 1 0 0 0; }
    ApprovalScreen { align: center middle; }
    #dialog { width: 80%; max-height: 80%; height: auto; border: thick $warning; background: $surface; padding: 1 2; }
    #dialog .args { margin: 1 0; max-height: 20; overflow-y: auto; }
    #buttons { height: auto; align-horizontal: right; }
    #buttons Button { margin-left: 2; }
    """
    BINDINGS = [
        Binding("ctrl+n", "new_chat", "New chat"),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.settings = load_settings()
        self.agent = build_agent(self.settings)
        self.thread_id = str(uuid.uuid4())
        self._shown_calls: set[str] = set()

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(id="chat")
        yield Input(placeholder="輸入訊息，Enter 送出", id="prompt")
        yield Footer()

    def on_mount(self) -> None:
        self.sub_title = f"{self.settings.model_name} · workspace: {self.settings.workspace}"
        self.query_one("#prompt", Input).focus()

    async def _add(self, widget) -> None:
        chat = self.query_one("#chat", VerticalScroll)
        await chat.mount(widget)
        chat.scroll_end(animate=False)

    def action_new_chat(self) -> None:
        self.thread_id = str(uuid.uuid4())
        self.query_one("#chat", VerticalScroll).remove_children()
        self.notify("Started a new conversation")

    @on(Input.Submitted, "#prompt")
    async def _submit(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        event.input.value = ""
        event.input.disabled = True
        await self._add(Static(text, classes="user", markup=False))
        content = COMPACT_REQUEST if text == "/compact" else text
        self.run_agent({"messages": [{"role": "user", "content": content}]})

    @work(exclusive=True)
    async def run_agent(self, payload) -> None:
        config = {"configurable": {"thread_id": self.thread_id}, "recursion_limit": 200}
        prompt = self.query_one("#prompt", Input)
        try:
            while payload is not None:
                interrupt = await self._stream(payload, config)
                payload = None
                if interrupt:
                    decisions = []
                    for action in interrupt.value["action_requests"]:
                        approved = await self.push_screen_wait(ApprovalScreen(action["name"], action["args"]))
                        decisions.append({"type": "approve"} if approved else
                                         {"type": "reject", "message": "User rejected this command."})
                        await self._add(Static(
                            f"{'✔ approved' if approved else '✘ rejected'}: {action['name']}", classes="tool"))
                    payload = Command(resume={"decisions": decisions})
        except Exception as exc:  # show errors in the chat instead of crashing the UI
            await self._add(Static(f"Error: {exc!r}", classes="error", markup=False))
        finally:
            prompt.disabled = False
            prompt.focus()

    async def _stream(self, payload, config):
        """Stream one agent run; return a pending interrupt, if any."""
        md: Markdown | None = None
        stream = None
        interrupt = None
        summary_note: Static | None = None

        async def close_text():
            nonlocal md, stream
            if stream is not None:
                await stream.stop()
            md, stream = None, None

        async for namespace, mode, data in self.agent.astream(
            payload, config, stream_mode=["messages", "updates"], subgraphs=True
        ):
            if namespace:  # skip subagent internals for now
                continue
            if mode == "messages":
                chunk, meta = data
                if meta.get("lc_source") == "summarization":  # hide the summary LLM's own output
                    if summary_note is None:
                        await close_text()
                        summary_note = Static("📝 對話太長，正在濃縮…", classes="tool")
                        await self._add(summary_note)
                    continue
                if isinstance(chunk, AIMessageChunk) and isinstance(chunk.content, str) and chunk.content:
                    if stream is None:
                        md = Markdown(classes="assistant")
                        await self._add(md)
                        stream = Markdown.get_stream(md)
                    await stream.write(chunk.content)
                    self.query_one("#chat", VerticalScroll).scroll_end(animate=False)
                continue

            # mode == "updates"
            for node, update in data.items():
                if node == "__interrupt__":
                    interrupt = update[0]
                    continue
                event = update.get("_summarization_event") if isinstance(update, dict) else None
                if event:
                    path = event.get("file_path")
                    text = "📝 對話已濃縮" + (f"，完整舊對話存在 workspace{path}" if path else "")
                    if summary_note is None:
                        await self._add(Static(text, classes="tool", markup=False))
                    else:
                        summary_note.update(text)
                    summary_note = None
                messages = update.get("messages") if isinstance(update, dict) else None
                if not isinstance(messages, list):
                    continue
                for msg in messages:
                    if isinstance(msg, AIMessage) and msg.tool_calls:
                        await close_text()
                        for call in msg.tool_calls:
                            if call["id"] in self._shown_calls:  # HITL re-emits approved calls
                                continue
                            self._shown_calls.add(call["id"])
                            await self._add(Static(f"🔧 {call['name']}\n{_short(call['args'], 400)}",
                                                   classes="tool", markup=False))
                    elif isinstance(msg, ToolMessage):
                        await close_text()
                        await self._add(Static(f"↳ {msg.name}\n{_short(msg.content)}",
                                               classes="tool", markup=False))
        await close_text()
        return interrupt


def main() -> None:
    AssistantApp().run()
```

### 4-1. 畫面結構

```python
def compose(self) -> ComposeResult:
    yield Header()
    yield VerticalScroll(id="chat")   # 對話內容
    yield Input(placeholder="輸入訊息，Enter 送出", id="prompt")
    yield Footer()
```

Textual 用 `compose()` 描述畫面：上面標題、中間可捲動的對話區、下面輸入框、最下面按鍵提示。樣式寫在 `CSS` 字串裡，寫法跟網頁 CSS 很像。

### 4-2. 送出訊息

`_submit()` 在按下 Enter 時觸發：把你的訊息顯示在畫面上，再交給 `run_agent()`。如果輸入的是 `/compact`，就改送一句「請呼叫 compact_conversation 工具」給助理。

`run_agent()` 加了 `@work(exclusive=True)`，代表它在**背景**執行，介面不會卡住。

### 4-3. 串流顯示

```python
async for namespace, mode, data in self.agent.astream(
    payload, config, stream_mode=["messages", "updates"], subgraphs=True
):
```

同時訂閱兩種串流：

| 模式 | 收到什麼 | 用來做什麼 |
|---|---|---|
| `messages` | 模型一個字一個字吐出來的片段 | 即時顯示回答（寫進 `Markdown` 串流） |
| `updates` | 每個步驟完成後的結果 | 顯示工具呼叫 🔧、工具結果 ↳、執行前確認、濃縮提示 📝 |

`subgraphs=True` 會把子代理的輸出也送過來，目前用 `if namespace: continue` 先略過，畫面比較乾淨。

### 4-4. 執行前確認（HITL）

當助理想呼叫 `execute`，agent 會暫停，`updates` 串流裡出現 `__interrupt__`。`run_agent()` 收到後：

1. 用 `push_screen_wait(ApprovalScreen(...))` 跳出確認視窗，等你按 `y` 或 `n`
2. 把決定包成 `Command(resume={"decisions": [...]})`
3. 用這個 `Command` 再呼叫一次 agent，它就會從暫停的地方繼續

有個小細節：核准之後，HITL 會把同一個工具呼叫**再送一次**，所以用 `self._shown_calls` 記下已顯示過的呼叫 id，避免畫面重複。

### 4-5. 對話濃縮的顯示

deepagents 濃縮對話時，會**再呼叫一次模型**寫摘要。這段摘要文字也會出現在 `messages` 串流裡，如果不處理，畫面上會突然冒出一大段英文摘要。

還好 deepagents 會在這次呼叫的 metadata 標上 `lc_source: "summarization"`，我們就能認出來：

```python
if meta.get("lc_source") == "summarization":
    # 不顯示摘要文字，改顯示「📝 對話太長，正在濃縮…」
```

濃縮完成時，`updates` 裡會出現 `_summarization_event`，裡面有舊對話存檔的路徑，我們把提示改成「📝 對話已濃縮，完整舊對話存在 …」。

---

## 步驟 5：安裝並啟動

在專案根目錄執行：

```bash
pip install -e .
```

`-e`（editable）代表用「連結」的方式安裝，之後改程式碼**不用重裝**。這裡**一定要加 `-e`**，因為 `config.py` 是從原始碼的位置去找 `.env` 和 `workspace/`。

啟動：

```bash
pa
```

| 按鍵 / 指令 | 功能 |
|---|---|
| `Enter` | 送出訊息 |
| `/compact` | 手動濃縮對話 |
| `Ctrl+N` | 開新對話 |
| `Ctrl+Q` | 離開 |
| `y` / `n` | 同意 / 拒絕執行指令 |

試試看這些：

1. `你好，介紹一下你能做什麼` — 看回答串流出來
2. `在 workspace 建一個 notes.md，寫三個今天的待辦` — 看到 🔧 `write_file`
3. `寫一個 python 程式算 1 到 100 的質數並執行` — 會跳出確認視窗，按 `y`
4. `剛剛有幾個質數？` — 確認它記得前面的對話

---

## 步驟 6：測試對話濃縮

正常情況下，要聊到二十幾萬 token 才會觸發濃縮。為了測試，我們寫一個腳本，把 `MODEL_CONTEXT` 暫時調成 8000，並使用另一個 workspace，不影響平常的設定。

**檔案位置：`scripts/try_summarization.sh`**

```bash
#!/usr/bin/env bash
# Launch the TUI with a tiny context window so summarization triggers after a few turns.
# Uses a separate workspace so test files don't mix with your real one.
cd "$(dirname "$0")/.."

cat <<'MSG'
測試模式：模型上限假裝成 8000 token，聊大約 5~6 輪就會觸發濃縮。
依序貼上這些問題：
  1. 用大約 800 字詳細介紹台灣的歷史
  2. 用大約 800 字詳細介紹日本的歷史
  3. 用大約 800 字詳細介紹韓國的歷史
  4. 用大約 800 字詳細介紹越南的歷史
  5. 用大約 800 字詳細介紹泰國的歷史
  6. 用大約 800 字詳細介紹菲律賓的歷史
看到「📝 對話已濃縮」後，再問：我們剛剛聊了哪些國家？
想手動濃縮：聊 2~3 輪後輸入 /compact
按 Enter 開始...
MSG
read -r

MODEL_CONTEXT=8000 PA_WORKSPACE=/tmp/pa-summarization-test pa
```

```bash
chmod +x scripts/try_summarization.sh
./scripts/try_summarization.sh
```

依序貼上腳本列出的問題，大約第 5～6 輪會看到「📝 對話已濃縮」。濃縮後問「我們剛剛聊了哪些國家？」，它仍然答得出來，因為模型讀到的是摘要。

> 為什麼 `MODEL_CONTEXT` 不能設太小？因為 system prompt 和工具說明本身就要佔幾千 token，設到 2000 左右會直接報錯。8000 是測試時比較好用的數字。

`/compact` 也有一道門檻：對話至少要到自動濃縮門檻的一半，才允許手動濃縮，太早按會回「Nothing to compact yet」。這是 deepagents 刻意設計的，避免在對話還很短時浪費一次模型呼叫。

---

## 回顧

我們用大約 300 行程式碼做出了：

- ✅ 終端機聊天介面，回答即時串流
- ✅ 讀寫檔案、寫程式並執行
- ✅ 執行前確認，守住安全底線
- ✅ 自動與手動的對話濃縮，並在畫面上清楚提示

deepagents 幫我們處理了最麻煩的部分：工具、子代理、對話濃縮都是內建的。我們主要做的是**選好 backend、開啟 HITL，再把串流接到介面上**。

## 下一步可以做什麼

- **長期記憶**：用 `create_deep_agent(memory=[...], store=...)` 讓助理跨對話記住事情
- **Skills**：用 `skills=[...]` 讓助理學會特定工作流程
- **對話持久化**：把 `InMemorySaver` 換成 SQLite 的 checkpointer，關掉程式也不會忘記
- **沙盒**：用 Docker 實作 `BaseSandbox`，讓執行指令真正與你的電腦隔離
- **看圖片**：deepagents 的 `read_file` 讀圖片時會交給模型看，搭配支援圖片的模型就能做多模態理解
