from __future__ import annotations

import json
import shutil


ASCII_LOGO = r"""
   ______          __        ___   __  __
  / ____/___  ____/ /__     /   | / /_/ /___ ______
 / /   / __ \/ __  / _ \   / /| |/ __/ / __ `/ ___/
/ /___/ /_/ / /_/ /  __/  / ___ / /_/ / /_/ (__  )
\____/\____/\__,_/\___/  /_/  |_\__/_/\__,_/____/
"""


class UI:
    RESET = "\033[0m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"

    def __init__(self) -> None:
        self.use_color = bool(shutil.which("tput"))

    def c(self, text: str, color: str) -> str:
        return f"{color}{text}{self.RESET}" if self.use_color else text

    def header(self, text: str) -> None:
        print(self.c(text, self.BOLD + self.CYAN))

    def info(self, text: str) -> None:
        print(self.c(text, self.BLUE))

    def success(self, text: str) -> None:
        print(self.c(text, self.GREEN))

    def warn(self, text: str) -> None:
        print(self.c(text, self.YELLOW))

    def error(self, text: str) -> None:
        print(self.c(text, self.RED))

    def muted(self, text: str) -> None:
        print(self.c(text, self.DIM))


def print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def clear_screen() -> None:
    print("\033[2J\033[H", end="")
