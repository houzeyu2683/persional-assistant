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

MODEL_CONTEXT=8000 PA_WORKSPACE=/tmp/pa-summarization-test python main.py
