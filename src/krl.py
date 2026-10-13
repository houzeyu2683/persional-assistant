import asyncio
import uuid
from typing import Optional
from pathlib import Path
from collections.abc import AsyncIterator
from deepagents import create_deep_agent
from deepagents.backends.local_shell import LocalShellBackend
from dotenv import dotenv_values
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from deepagents.middleware.summarization import SummarizationMiddleware

from cfg import Profile

profile = Profile()
chat_model = ChatOpenAI(
    model=profile.secret["MODEL_NAME"],
    base_url=profile.secret["MODEL_URL"],
    api_key=profile.secret["API_KEY"],
)
shell_backend = LocalShellBackend(
    root_dir=profile.workspace,
    virtual_mode=True,
    inherit_env=True,
)
system_prompt = (
    "你是使用者的個人助理，預設使用繁體中文回答。"
    f"系統是 {profile.os} 環境，請使用這個系統的指令語法。"

    # 檔案工具：只看得到工作資料夾，路徑用 / 開頭。
    "read_file、write_file、edit_file、ls 等檔案工具只能存取工作資料夾，"
    "路徑一律用 / 開頭，路徑 / 就代表工作資料夾，例如 /result.txt, /sample.py 等。"
    "不要在檔案工具的路徑裡寫 C: 這種磁碟代號。"

    # execute：可以碰到整台電腦，目前位置就是工作資料夾。
    "execute 工具執行 shell 指令時，目前所在位置就是工作資料夾，"
    "可以用完整路徑存取電腦上的其他檔案。"

    # 使用者給的檔案：先複製進來，不動原檔。
    "當使用者提供工作資料夾以外的檔案時，"
    "先用 execute 把它複製到工作資料夾，再用檔案工具讀取。"
    "**只能複製**原本的檔案。"
    "**禁止移動或修改**原本的檔案。"

    # 圖片和聲音：用 read_file 讀。
    "要看圖片或聽聲音時，用 read_file 讀取，如果你有能力，你可以看到圖片、聽到聲音。"

    "你產生的暫存檔和分析結果，都存在工作資料夾裡。"

    # 回報位置：給使用者看實際路徑，不要給 / 開頭的虛擬路徑。
    f"工作資料夾在電腦上的實際位置是 {profile.workspace}。"
    "告訴使用者檔案存在哪裡時，要給實際位置，"
    f"例如 /content.txt 要說成 {profile.workspace / 'content.txt'} 等。"
)
default_agent = create_deep_agent(
    model=chat_model,
    system_prompt=system_prompt,
    backend=shell_backend,
    middleware=[
        SummarizationMiddleware(
            model=chat_model,
            backend=shell_backend,
            # 對話觸碰條件就開始壓縮。
            trigger=[("tokens", 20000), ("messages", 50)],
            # 壓縮後保留最後 20 則訊息原文，其餘變成摘要。
            keep=("messages", 20),
        )  
    ],
    interrupt_on={
        "execute": {"allowed_decisions": ["approve", "reject"]},
    },
    checkpointer=InMemorySaver(),
)


class Assistant:

    def __init__(self, thread_id: str) -> None:
        """使用預設的 deep agent，並開一段新的對話"""

        self.thread_id = thread_id
        return
    
    async def get_feedback(
        self, 
        question_content: Optional[str], 
        approval_decisions: Optional[list[bool]]
    ) -> AsyncIterator[str | list | dict]:
        """問 agent 問題或回答核准，回答一邊產生一邊回傳文字片段"""

        # 如果有審核，彙整審核結果。
        if approval_decisions is not None and question_content is None:

            # 把 TUI 給的 True/False，翻成 agent 看得懂的 approve/reject。
            decision_contents = []
            for approved_item in approval_decisions:

                decision_type = "approve" if approved_item else "reject"
                decision_contents.append({"type": decision_type})
                continue

            stream_payload = Command(resume={"decisions": decision_contents})
            pass

        elif approval_decisions is None and question_content is not None:

            # 沒有審核，就是使用者問了新問題。
            stream_payload = {
                "messages": [{"role": "user", "content": question_content}]
            }

        elif approval_decisions is not None and question_content is not None:

            raise ValueError("問題和審核結果只能給一個，不能兩個都給")

        elif approval_decisions is None and question_content is None:

            raise ValueError("問題和審核結果至少要給一個")

        # 用 thread_id 讓 agent 知道這是哪一段對話。
        stream_config = {"configurable": {"thread_id": self.thread_id}}

        # 一邊收 agent 的輸出，一邊把文字交給 TUI。
        async for stream_part in default_agent.astream(
            stream_payload,
            config=stream_config,
            stream_mode=["messages", "updates"],
            version="v2"
        ):
            # 狀態更新裡只挑出工具資訊，一筆一筆交給 TUI。
            part_type = stream_part["type"]
            if part_type == "updates":
                tool_events = self.get_tool_events(stream_part["data"])
                for tool_event in tool_events:
                    yield tool_event
                    continue

                continue

            # 剩下只處理對話文字，其他類型略過。
            if part_type != "messages":
                continue

            # 不是 AI 的回答、空字串、上下文壓縮時產生的摘要，都不顯示。
            message_chunk, message_metadata = stream_part["data"]
            if (
                not isinstance(message_chunk, AIMessageChunk) or
                not message_chunk.text or
                dict(message_metadata).get("lc_source") == "summarization"
            ):
                continue

            yield message_chunk.text
            continue

        # stream 停下來後，如果 agent 在等審批，把請求清單交給 TUI。
        agent_state = await default_agent.aget_state(stream_config)
        approval_requests = []
        for agent_interrupt in agent_state.interrupts:
            action_requests = agent_interrupt.value["action_requests"]
            approval_requests.extend(action_requests)
            continue

        # 沒有要審批的就結束；有的話把整份清單交給 TUI。
        if approval_requests==[]: return
        yield approval_requests

    def get_tool_events(self, update_data: dict) -> list[dict]:
        """從一次狀態更新裡，挑出工具呼叫和工具結果"""

        tool_events = []

        # 更新的格式是 {步驟名稱: 這一步改了什麼}。
        for node_name, node_update in update_data.items():

            # 同一步寫了好幾次時會是 list，統一變成 list 來處理。
            update_items = node_update
            if not isinstance(node_update, list):
                update_items = [node_update]

            for update_item in update_items:

                # 這一步沒有改任何東西（None），或不是一般的更新，略過。
                if not isinstance(update_item, dict):
                    continue

                update_messages = update_item.get("messages")
                if not isinstance(update_messages, list):
                    continue

                for update_message in update_messages:

                    # AI 決定要呼叫工具：記下名稱和參數。
                    # 只看 model 這一步，因為審批的步驟會把同一個呼叫再送一次。
                    if (
                        node_name == "model" and
                        isinstance(update_message, AIMessage)
                    ):
                        for tool_call in update_message.tool_calls:
                            tool_events.append({
                                "type": "tool_call",
                                "name": tool_call["name"],
                                "args": tool_call["args"],
                            })
                            continue

                    # 工具執行完：記下成功或失敗，以及結果。
                    # 圖片、聲音這類不是文字的結果，只寫一句說明。
                    if isinstance(update_message, ToolMessage):
                        result_content = update_message.content
                        if not isinstance(result_content, str):
                            result_content = "（非文字內容）"

                        tool_events.append({
                            "type": "tool_result",
                            "name": update_message.name,
                            "status": update_message.status,
                            "content": result_content,
                        })

                    continue

                continue

            continue

        return tool_events

    pass


if __name__ == "__main__":

    pass
