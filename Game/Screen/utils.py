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

from __future__ import annotations

import pygame
from .constants import IS_PRINTABLE, FONT, colours
from typing import Tuple, Literal, Any, Optional, Iterator, NoReturn, Callable
from inspect import iscoroutinefunction
import asyncio
from abc import abstractmethod


class InputBox:
    """ Creates an inputbox """
    def __init__(self, x: int, y: int, w: int, h: int, name: str,
                 text: str = '', max_length: int = 16):
        self.colour_INACTIVE: pygame.Color = pygame.Color('lightskyblue3')
        self.colour_ACTIVE: pygame.Color = pygame.Color('dodgerblue2')
        self.FONT: pygame.font.Font = pygame.font.Font(None, 32)
        self.rect: pygame.Rect = pygame.Rect(x, y, w, h)
        self.colour: pygame.Color = self.colour_INACTIVE
        self.text: str = text
        self.txt_surface: pygame.Surface | pygame.SurfaceType = self.FONT.render(text, True, (0, 0, 0))
        self.active: bool = False
        self.name: str = name
        self.max_length: int = max_length
        self.index: int = 0

    def __str__(self) -> str:
        return self.text

    def __int__(self) -> int | NoReturn:
        return int(str(self))

    def __repr__(self) -> str:
        pos_params = [self.rect.x, self.rect.y, self.rect.w, self.rect.h]
        pos_params = map(str, pos_params)

        def get_attribute_name(obj, attribute_value) -> str:
            for name, value in obj.__dict__.items():
                if value == attribute_value:
                    return name
            return 'None'

        kw_params = [f'{get_attribute_name(self, p)}={p}' for p in [self.name, self.text]]

        return f'InputBox({", ".join(pos_params)}, {", ".join(kw_params)})'

    def __len__(self) -> int:
        return len(self.text)

    def __iter__(self) -> Iterator:
        return iter(self.text)

    def handle_event(self, event) -> None:
        """ Handles events for the inputbox via pygame events """
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                self.active = not self.active
            else:
                self.active = False
            self.colour = self.colour_ACTIVE if self.active else self.colour_INACTIVE
        if event.type == pygame.KEYDOWN:
            if self.active:
                if event.key == pygame.K_BACKSPACE and self.text:
                    self.text = self.text[:-1]
                elif event.unicode in IS_PRINTABLE and len(self.text) < self.max_length:
                    self.text += event.unicode
                self.txt_surface = self.FONT.render(self.text, True, self.colour)

    def update_text(self) -> None:
        self.txt_surface = self.FONT.render(self.text, True, self.colour)

    def update(self) -> None:
        width = max(200, self.txt_surface.get_width() + 10)
        self.rect.w = width

    def draw(self, screen: pygame.Surface | pygame.SurfaceType) -> None:
        screen.blit(self.txt_surface, (self.rect.x + 5, self.rect.y + 5))
        pygame.draw.rect(screen, self.colour, self.rect, 2)


def create_input_box(window: pygame.Surface | pygame.SurfaceType, colour: Tuple, x: int, y: int, width: int,
                     height: int) -> pygame.Rect:
    input_box = pygame.Rect(x, y, width, height)
    pygame.draw.rect(window, colour, input_box)
    return input_box


def create_text_surface(window: pygame.Surface | pygame.SurfaceType, text: str,
                        colour: Tuple, rect: pygame.Rect, font: Optional[pygame.font.Font] = None) -> None:
    text_surface = FONT.render(text, True, colour) if not font else font.render(text, True, colour)
    text_rect = text_surface.get_rect()
    text_rect.center = rect.center
    window.blit(text_surface, text_rect)


class Button(object):
    """ Creates a button which can cause an action """
    def __init__(self, x: int, y: int, width: int, height: int, text: str, bg_colour: Tuple, text_colour: Tuple,
                 *args, disabled: bool = False, action: Any = None):
        self.__text = text
        self.__bg_colour = bg_colour
        self.__text_colour = text_colour
        self.__button = pygame.Rect(x, y, width, height)
        self.__disabled = disabled
        self.__action = action
        self.__args = args

    @property
    def text(self) -> str:
        return self.__text

    @property
    def action(self) -> Callable:
        return self.__action

    @property
    def disabled(self) -> bool:
        return self.__disabled

    @disabled.setter
    def disabled(self, value: bool | Literal[0, 1]) -> None:
        if value in [0, 1]:
            value = not not value  # cast to type bool without using bool

        if value in [True, False]:
            self.__disabled = value
        else:
            raise TypeError(f'{value} is type {type(value)} not boolean!')

    async def handle_event(self, event: pygame.event.Event) -> None:
        """ Handles the button events though the pygame event"""
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.__button.collidepoint(event.pos):
                if not self.__disabled and self.__action is not None:
                    if iscoroutinefunction(self.__action):
                        asyncio.create_task(self.__action(*self.__args))
                    else:
                        self.__action(*self.__args)

    def draw(self, window: pygame.Surface | pygame.SurfaceType) -> None:
        colour = colours['DISABLED'] if self.__disabled else self.__bg_colour
        pygame.draw.rect(window, colour, self.__button)
        create_text_surface(window, self.__text, self.__text_colour, self.__button)


class Text(object):
    """ Creates a static Text """
    def __init__(self, x: int, y: int, width: int, height: int, colour: Tuple, text: str,
                 size: int = 28):
        self.__text = text
        self.__rect = pygame.Rect(x, y, width, height)
        self.__colour = colour
        self.__font: pygame.font.Font = FONT if size == 28 else pygame.font.SysFont("comiscans", size)

    def __len__(self) -> int:
        return len(self.__text)

    @property
    def get_text(self) -> str:
        return self.__text

    def draw(self, window: pygame.Surface | pygame.SurfaceType, bg_colour: Tuple[int, int, int] | None) -> None:
        if bg_colour is None:
            bg_colour = colours['TURQUOISE']
        pygame.draw.rect(window, bg_colour, self.__rect)
        create_text_surface(window, self.__text, self.__colour, self.__rect, font=self.__font)


class DynamicText(Text):
    """ Creates a text that is formatted on every draw """
    def __init__(self, x: int, y: int, width: int, height: int, colour: Tuple, text: str, fmt_dict: dict,
                 size: int = 28):
        super().__init__(x, y, width, height, colour, text, size=size)
        self._fmt_dict = fmt_dict

    def __len__(self) -> int:
        return len(self.get_text)

    @abstractmethod
    def fmt_text(self, text: str) -> str:
        """ this function has to be specifically implemented for use case.
        fmt_dict should be used for implementation """
        raise NotImplemented

    @property
    def get_text(self) -> str:
        return self.fmt_text(super().get_text)

    def draw(self, window: pygame.Surface | pygame.SurfaceType, bg_colour: Tuple[int, int, int] | None) -> None:
        if bg_colour is None:
            bg_colour = colours['TURQUOISE']
        pygame.draw.rect(window, bg_colour, self._Text__rect)  # type: ignore
        create_text_surface(
            window,
            self.get_text,
            self._Text__colour,  # type: ignore
            self._Text__rect,  # type: ignore
            font=self._Text__font  # type: ignore
        )
