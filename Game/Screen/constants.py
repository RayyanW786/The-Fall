"""
MIT License

Copyright (c) 2024-present Rayyan

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import logging
import re
import string
from os import listdir, path
from typing import AnyStr, Dict, Tuple

import pygame

logging.basicConfig(
    level=logging.INFO,
    format="[{asctime}] [{levelname:<7}] {name}: {message}",
    style="{",
    datefmt="%Y-%m-%d %H:%M:%S",
)

log = logging.getLogger(__name__)
EMAIL_RE = re.compile(
    r"([A-Za-z0-9]+[.-_])*[A-Za-z0-9]+@[A-Za-z0-9-]+(\.[A-Z|a-z]{2,})+"
)
pygame.font.init()

IS_PRINTABLE: AnyStr = "".join(
    [string.ascii_letters, string.punctuation, string.digits]
)

FONT: pygame.font.Font = pygame.font.SysFont("comiscans", 28)

FPS: int = 60

colours: Dict[str, Tuple[int, int, int]] = {
    "BLACK": (0, 0, 0),
    "WHITE": (255, 255, 255),
    "TURQUOISE": (48, 213, 200),
    "BLURPLE": (88, 101, 242),
    "GREEN": (127, 255, 0),
    "LIGHTBLUE": (135, 206, 250),
    "RED": (255, 0, 0),
    "DISABLED": (128, 128, 128),
    "YELLOW": (255, 192, 0),
    "ORANGE": (255, 165, 0),
    "PURPLE": (148, 68, 119),
    "JADE": (0, 163, 108),
    "FAWN": (229, 170, 112),
    "PUCE": (169, 92, 104),
}

# RED = "\033[31m"
# RESET = "\033[0m"

backgrounds: Dict[str, str] = {}
try:
    backgrounds_dir = path.join(path.dirname(__file__), "Backgrounds")
    for filename in listdir(backgrounds_dir):
        if path.isfile(path.join(backgrounds_dir, filename)):
            key = path.splitext(filename)[0]
            backgrounds[key] = filename
except FileNotFoundError:
    log.warning(
        "\033[31mBackground directory not found. Background features may not work as expected.\033[0m"
    )
