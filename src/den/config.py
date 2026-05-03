from pathlib import Path
from .utils.platform import Platform, get_current_platform
import configparser
from dataclasses import dataclass, field


@dataclass
class Config:
    THEME: str = ""
    CONFIG_FILE_PATH: Path = field(init=False)
    DATA_DIR_PATH: Path = field(init=False)

    def __post_init__(self):
        platform = get_current_platform()

        if platform in (Platform.LINUX, Platform.ANDROID):
            self.CONFIG_FILE_PATH = Path.home() / ".config" / "den" / "config.ini"
            self.DATA_DIR_PATH = Path.home() / ".local" / "share" / "den"
        else:
            raise RuntimeError(f"Unsupported platform: {platform}")

        self.CONFIG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.DATA_DIR_PATH.mkdir(parents=True, exist_ok=True)

        config = configparser.ConfigParser()

        if not self.CONFIG_FILE_PATH.exists():
            self.THEME = "gruvbox"
            config["DEFAULT"] = {"Theme": self.THEME}
            with open(self.CONFIG_FILE_PATH, "w") as f:
                config.write(f)
        else:
            config.read(self.CONFIG_FILE_PATH)
            self.THEME = config["DEFAULT"].get("Theme", "gruvbox")


config = Config()
