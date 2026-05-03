import sys
from enum import Enum, auto


class Platform(Enum):
    LINUX = auto()
    ANDROID = auto()
    DARWIN = auto()
    WIN32 = auto()
    UNKNOWN = auto()


_current_platform = Platform.UNKNOWN

match sys.platform:
    case "linux":
        _current_platform = Platform.LINUX
    case "android":
        _current_platform = Platform.ANDROID
    case "darwin":
        _current_platform = Platform.DARWIN
    case "win32":
        _current_platform = Platform.WIN32
    case _:
        _current_platform = Platform.UNKNOWN

_supported_platforms = frozenset({Platform.LINUX, Platform.ANDROID})


def get_current_platform() -> Platform:
    return _current_platform


def get_supported_platforms() -> frozenset[Platform]:
    return _supported_platforms


def check_platform_support():
    if _current_platform not in _supported_platforms:
        raise RuntimeError(f"Platform '{sys.platform}' is not supported by Den.")
