"""
MIT License

Copyright (c) 2024-present Rayyan Warraich

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

# Candidate No: 7168
# Centre No: 20570

from typing import AnyStr, Dict, Tuple
import string
import pygame
from os import listdir, path

pygame.font.init()

IS_PRINTABLE: AnyStr = ''.join([string.ascii_letters, string.punctuation, string.digits])

FONT: pygame.font.Font = pygame.font.SysFont("comiscans", 28)

FPS: int = 60

colours: Dict[str, Tuple[int, int, int]] = {
    'BLACK': (0, 0, 0), 'WHITE': (255, 255, 255),
    'TURQUOISE': (48, 213, 200), 'BLURPLE': (88, 101, 242),
    'GREEN': (127, 255, 0), 'LIGHTBLUE': (135, 206, 250),
    'RED': (255, 0, 0), 'DISABLED': (128, 128, 128),
    'YELLOW': (255, 192, 0), 'ORANGE': (255, 165, 0),
    'PURPLE': (148, 68, 119), 'JADE': (0, 163, 108),
    'FAWN': (229, 170, 112), 'PUCE': (169, 92, 104)
}

backgrounds: Dict[str, str] = {}

for filename in listdir(path.join(path.dirname(__file__), 'Backgrounds')):
    backgrounds[filename.split('.')[0]] = filename

