import platform
from pathlib import Path


class Profile:

    def __init__(self) -> None:
        """"""

        return

    def get_workspace_path(self) -> Path:
        """"""

        # 工作資料夾建在使用者打 lpa 時所在的資料夾裡。
        workspace_path = Path.cwd() / "workspace"
        workspace_path.mkdir(parents=True, exist_ok=True)
        return workspace_path

    PATH = Path(__file__).resolve()
    SYSTEM = platform.system()
    pass
