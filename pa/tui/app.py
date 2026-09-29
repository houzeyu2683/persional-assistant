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
        self.run_agent({"messages": [{"role": "user", "content": text}]})

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
                chunk, _meta = data
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
