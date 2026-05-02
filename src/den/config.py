import sys
from pathlib import Path
from .utils.platform import Platform, platform
import configparser
from dataclasses import dataclass

CONFIG_FILE_PATH: Path = Path()
DATA_DIR_PATH: Path = Path()


def resolve_paths():
    global CONFIG_FILE_PATH, DATA_DIR_PATH
    if platform == Platform.LINUX or platform == Platform.ANDROID:
        CONFIG_FILE_PATH = Path.home() / ".config" / "den" / "config.ini"
        DATA_DIR_PATH = Path.home() / ".local" / "share" / "den"
    elif platform == Platform.WIN32:
        DATA_DIR_PATH = Path.home()
        CONFIG_FILE_PATH = DATA_DIR_PATH / "config.ini"
    else:
        raise OSError(
            f"Current platform ({platform if platform else sys.platform}) is not supported."
        )


THEME = ""


def apply_config():
    global THEME

    config = configparser.ConfigParser()
    if not Path.exists(CONFIG_FILE_PATH):
        config["DEFAULT"] = {"Theme": "gruvbox"}
        try:
            with open(CONFIG_FILE_PATH, "w") as config_file:
                config.write(config_file)
        except OSError as e:
            print(f"Unable to write to config file {e}")
    else:
        try:
            config.read(CONFIG_FILE_PATH)
            THEME = config["DEFAULT"]["Theme"]
        except OSError as e:
            print(f"Unable to read config file {e}")


resolve_paths()
apply_config()
