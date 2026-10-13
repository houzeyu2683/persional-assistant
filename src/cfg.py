import platform
import os
from dotenv import dotenv_values
from pathlib import Path


class Profile:

    def __init__(self) -> None:
        """"""

        return

    @property
    def workspace(self) -> Path:
        """
        在指定的路徑啟用應用程式的時候，
        在該路徑底下新增一個 workspace 資料夾，
        將該資料夾作為工作目錄，保存執行過程中儲存檔案的位置。
        """

        workspace = Path.cwd() / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        return workspace

    @property
    def os(self) -> str:
        """
        獲得作業系統名稱，可以是 "Linux", "Windows", "Darwin"等。 
        """

        return platform.system()

    @property
    def secret(self) -> dict:
        """
        獲得模型訪問的設定，
        從啟用應用程式時所在路徑的 .env 讀取。
        """

        path = Path.cwd() / '.env'
        if not path.exists():
            raise FileNotFoundError(f"找不到設定檔，請在 {path} 建立 .env")

        secret = dict(dotenv_values(path))
        return secret

    pass
