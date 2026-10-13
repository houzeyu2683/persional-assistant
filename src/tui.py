import json
import uuid
from typing import Optional
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, Static
from textual.widget import Widget

from krl import Assistant


class Approval(ModalScreen[bool]):

    def __init__(self, function_name: str, function_variables: dict) -> None:
        """記下要核准的工具名稱和參數"""

        super().__init__()
        self.function_name = function_name
        self.function_variables = function_variables
        return

    def compose(self) -> ComposeResult:
        """對話框：標題、參數、核准與拒絕按鈕"""

        title = f"[b]Agent 想要執行[/b] [cyan]{self.function_name}[/cyan]"
        function_variables_text = json.dumps(
            self.function_variables, ensure_ascii=False, indent=2
        )
        with Vertical(id="dialog"):
            yield Static(title)
            yield Static(
                function_variables_text, classes="variables", markup=False
            )
            with Horizontal(id="buttons"):
                yield Button("核准 (y)", variant="success", id="approve", compact=True)
                yield Button("拒絕 (n)", variant="error", id="reject", compact=True)

    def action_decide(self, approved: bool) -> None:
        """按 y 或 n 時關閉視窗，並回傳結果"""

        self.dismiss(approved)
        return

    @on(Button.Pressed)
    def _pressed(self, event: Button.Pressed) -> None:
        """按下按鈕時關閉視窗，並回傳結果"""

        self.dismiss(event.button.id == "approve")
        return

    BINDINGS = [
        Binding("y", "decide(True)", "核准"),
        Binding("n", "decide(False)", "拒絕"),
    ]
    pass


assistant = Assistant(
    thread_id=str(uuid.uuid4())
)


class Screen(App):

    def __init__(self) -> None:
        """初始化主畫面，並開一段新的對話"""

        super().__init__()
        return

    def compose(self) -> ComposeResult:
        """版面：標題列、聊天區、輸入框、快捷鍵列"""

        yield Header()
        yield VerticalScroll(id="chat")
        yield Input(placeholder="輸入訊息，Enter 送出", id="prompt")
        yield Footer()

    def on_mount(self) -> None:
        """畫面建立完成後，讓游標停在輸入框"""

        self.query_one("#prompt", Input).focus()
        return

    async def _add(self, widget: Widget) -> None:
        """把元件加到聊天區最下面，並捲到底"""

        chat = self.query_one("#chat", VerticalScroll)
        await chat.mount(widget)
        chat.scroll_end(animate=False)
        return

    @on(Input.Submitted, "#prompt")
    async def _submit(self, event: Input.Submitted) -> None:
        """使用者在輸入框按 Enter 時，顯示訊息並交給 agent"""

        text = event.value.strip()
        if not text:
            return
        
        event.input.value = ""
        event.input.disabled = True
        await self._add(Static(text, classes="user", markup=False))
        _ = self._converse(text)
        return

    def get_tool_widget(self, tool_event: dict) -> Static:
        """把工具資訊變成聊天區裡的一行，失敗的用紅色顯示"""

        tool_name = tool_event["name"]

        # AI 決定呼叫工具：顯示工具名稱和參數。
        if tool_event["type"] == "tool_call":
            tool_args_text = json.dumps(tool_event["args"], ensure_ascii=False)
            tool_content = f"▶ {tool_name}: {tool_args_text[:300]}"
            return Static(tool_content, classes="tool", markup=False)

        # 工具執行完：顯示成功或失敗，以及結果的前 300 個字。
        result_text = tool_event["content"][:300]
        if tool_event["status"] == "error":
            tool_content = f"✗ {tool_name} 失敗\n{result_text}"
            return Static(tool_content, classes="error", markup=False)

        tool_content = f"✓ {tool_name} 成功\n{result_text}"
        return Static(tool_content, classes="tool", markup=False)

    @work(exclusive=True)
    async def _converse(self, question_content: Optional[str]) -> None:
        """把問題交給 agent 並顯示回答，需要審核時逐一跳出核准視窗"""

        chat = self.query_one("#chat", VerticalScroll)

        # 每一次對話，按下 Enter 就是問問題，所以不會有審批結果。
        approval_decisions = None

        # agent 可能停下來好幾次等審批，所以用迴圈一直重複，
        # 直到它不再停下來為止。
        while True:

            # 目前還沒有回答框，等 AI 開始說話才建立。
            answer_widget = None
            answer_content = ""

            # 這一輪 agent 想執行的指令，先當作沒有。
            approval_requests = []

            # 一邊收 agent 的回答，一邊顯示。
            # 收到的是文字就顯示；收到的是 list，代表 agent 停下來等審批；
            # 收到的是 dict，代表 agent 做完了一步。
            async for answer_piece in assistant.get_feedback(
                question_content, approval_decisions
            ):
                if isinstance(answer_piece, list):
                    approval_requests = answer_piece
                    continue

                # 收到 dict，是工具資訊，顯示一行到聊天區。
                # 然後忘掉目前的回答框，AI 接下來的話會寫在新的框裡。
                if isinstance(answer_piece, dict):
                    await self._add(self.get_tool_widget(answer_piece))
                    answer_widget = None
                    continue

                # 收到文字，但目前沒有回答框，就在最下面開一個新的。
                if answer_widget is None:
                    answer_widget = Static(
                        "", classes="assistant", markup=False
                    )
                    await self._add(answer_widget)
                    answer_content = ""

                answer_content += answer_piece
                answer_widget.update(answer_content)
                chat.scroll_end(animate=False)
                continue

            # 沒有要審批的指令，代表 agent 已經回答完，結束這次對話。
            if not approval_requests:
                break

            # 一個一個跳出核准視窗，把使用者的回答照順序記下來。
            approval_decisions = []
            for approval_request in approval_requests:
                approval = Approval(
                    approval_request["name"], approval_request["args"]
                )
                approved = await self.push_screen_wait(approval)
                approval_decisions.append(approved)
                continue

            # 下一輪只送審批結果給 agent，不再送問題。
            question_content = None
            continue

        # 對話結束，讓使用者可以再輸入。
        prompt = self.query_one("#prompt", Input)
        prompt.disabled = False
        prompt.focus()
        return

    TITLE = "Personal Assistant"
    CSS = """
    #chat {
        padding: 0 1;
    }
    .user {
        background: $boost;
        border-left: thick $accent;
        padding: 0 1;
        margin: 1 0 0 0;
    }
    .assistant {
        margin: 1 0 0 0;
    }
    .tool {
        color: $text-muted;
        border-left: thick $warning;
        padding: 0 1;
        margin: 1 0 0 0;
    }
    .error {
        color: $error;
        border-left: thick $error;
        padding: 0 1;
        margin: 1 0 0 0;
    }
    Approval {
        align: center middle;
    }
    #dialog {
        width: 80%;
        max-height: 80%;
        height: auto;
        border: thick $warning;
        background: $surface;
        padding: 1 2;
    }
    #dialog .variables {
        margin: 1 0;
        max-height: 20;
        overflow-y: auto;
    }
    #buttons {
        height: auto;
        align-horizontal: right;
    }
    #buttons Button {
        margin-left: 2;
    }
    """
    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
    ]
    pass

def activate() -> None:
    """啟動 TUI"""

    Screen().run()
    return

if __name__ == "__main__":

    activate()
    pass