# 安裝教學

這份文件說明如何在自己的電腦上安裝並啟動個人助理。

## 需要準備

- **Python 3.12 以上**（目前在 3.14 上測試過）
- **git**
- **OpenRouter 的 API 金鑰**：到 <https://openrouter.ai/keys> 申請。也可以用其他相容 OpenAI 格式的 API。
- （建議）**conda**，用來建立獨立的 Python 環境

## 1. 下載專案

```bash
git clone -b fresh https://github.com/houzeyu2683/persional-assistant.git
cd persional-assistant
```

## 2. 建立 Python 環境

建議用獨立的環境，避免跟電腦上其他專案的套件互相影響：

```bash
conda create -n pa python=3.14
conda activate pa
```

沒有 conda 的話，也可以用 venv：

```bash
python -m venv .venv
source .venv/bin/activate
```

## 3. 安裝

在專案資料夾（有 `pyproject.toml` 的那一層）執行：

```bash
pip install -e .
```

> **一定要加 `-e`。** 程式會從專案資料夾讀取 `.env` 和 `workspace/`，不加 `-e` 的話會找不到設定。

裝好後會多一個 `pa` 指令。

## 4. 設定金鑰

複製範本，再填入自己的金鑰：

```bash
cp .env.sample .env
```

打開 `.env`，把 `MODEL_KEY` 改成你的金鑰：

```bash
MODEL_NAME=google/gemma-4-31b-it
MODEL_URL=https://openrouter.ai/api/v1
MODEL_KEY=sk-or-你的金鑰
MODEL_CONTEXT=262144
```

| 設定 | 說明 |
|---|---|
| `MODEL_NAME` | 要用的模型，名稱照 OpenRouter 上的寫法 |
| `MODEL_URL` | API 位址 |
| `MODEL_KEY` | 你的 API 金鑰。**不要分享給別人，也不要 commit** |
| `MODEL_CONTEXT` | 模型一次最多能讀多少 token。換模型時要跟著改，數字可以在 OpenRouter 的模型頁面查到 |
| `PA_WORKSPACE` | （選填）助理讀寫檔案的資料夾，預設是專案裡的 `workspace/` |

## 5. 啟動

```bash
pa
```

在最下面輸入訊息，按 Enter 送出。

| 按鍵 / 指令 | 功能 |
|---|---|
| `Enter` | 送出訊息 |
| `/compact` | 手動濃縮對話（對話夠長時才有作用） |
| `Ctrl+N` | 開新對話 |
| `Ctrl+Q` | 離開 |
| `y` / `n` | 同意 / 拒絕助理執行指令 |

## 使用前請注意

助理可以**在你的電腦上執行指令**（例如跑 Python 程式）。每次執行前都會跳出視窗問你，**按 `y` 之前請看清楚它要做什麼**：

- 指令是用**你的身分**執行的，能讀、改、刪你電腦上的檔案
- 看到 `rm`、`sudo`、不認識的網址，或是 `workspace` 以外的路徑，不確定就按 `n`

助理寫的檔案預設放在 `workspace/` 裡。對話內容只存在記憶體裡，關掉程式就會消失。

## 常見問題

**打 `pa` 說找不到指令**
確認已經啟動環境（`conda activate pa`），並且在第 3 步有成功執行 `pip install -e .`。

**啟動時出現 `Missing in .env: ...`**
`.env` 不存在或少了設定。確認第 4 步有做，而且 `.env` 放在專案資料夾的最上層。

**助理一直回錯誤，或沒有回應**
檢查 `MODEL_KEY` 是否正確，以及 OpenRouter 帳戶還有沒有額度。

**更新到最新版**

```bash
git pull
pip install -e .
```

只改程式碼時不需要重裝；`pyproject.toml` 有變動（例如新增套件）時才需要重跑 `pip install -e .`。
