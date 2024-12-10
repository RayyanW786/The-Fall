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

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from inspect import iscoroutinefunction
from typing import Any, Callable, Iterator, Literal, NoReturn, Tuple

import pygame

from .constants import FONT, IS_PRINTABLE, colours


class UIElement(ABC):
    """Base UI Element class that all UI elements inherit from."""

    def __init__(
        self,
        ui_manager,
        x_factor: float,
        y_factor: float,
        w_factor: float = 0,
        h_factor: float = 0,
    ):
        self.ui_manager = ui_manager
        self.x_factor = x_factor
        self.y_factor = y_factor
        self.w_factor = w_factor
        self.h_factor = h_factor
        self.rect = pygame.Rect(0, 0, 1, 1)
        self.active = False
        self.update_rect()  # Sets self.rect based on factors.

    def update_rect(self):
        w, h = self.ui_manager.screen.get_size()
        self.rect.x = int(self.x_factor * w)
        self.rect.y = int(self.y_factor * h)
        if self.w_factor > 0 and self.h_factor > 0:
            self.rect.width = int(self.w_factor * w)
            self.rect.height = int(self.h_factor * h)
        # dynamic font scaling, handled in subclasses.

    @abstractmethod
    def handle_event(self, event: pygame.event.Event):
        pass

    @abstractmethod
    def draw(self, surface: pygame.Surface):
        pass


class InputBox(UIElement):
    def __init__(
        self,
        ui_manager,
        name: str,
        x_factor: float,
        y_factor: float,
        w_factor: float,
        h_factor: float,
        text: str = "",
        max_length: int = 16,
    ):
        super().__init__(ui_manager, x_factor, y_factor, w_factor, h_factor)
        self.colour_INACTIVE: pygame.Color = pygame.Color("lightskyblue3")
        self.colour_ACTIVE: pygame.Color = pygame.Color("dodgerblue2")

        approx_font_size = int(self.rect.height * 0.7)
        self.FONT: pygame.font.Font = pygame.font.Font(None, approx_font_size)

        self.colour: pygame.Color = self.colour_INACTIVE
        self.text: str = text
        self.name: str = name
        self.max_length: int = max_length
        self.cursor_pos: int = len(self.text)
        self.update()

        # Enable key repeat so holding backspace or arrow keys works continuously
        pygame.key.set_repeat(200, 50)

    def __str__(self) -> str:
        return self.text

    def __int__(self) -> int | NoReturn:
        return int(str(self))

    def __repr__(self) -> str:
        pos_params = [
            str(self.rect.x),
            str(self.rect.y),
            str(self.rect.w),
            str(self.rect.h),
        ]
        return f'InputBox({", ".join(pos_params)}, name={self.name}, text={self.text})'

    def __len__(self) -> int:
        return len(self.text)

    def __iter__(self) -> Iterator:
        return iter(self.text)

    def update(self):
        approx_font_size = int(self.rect.height * 0.7)
        self.FONT: pygame.font.Font = pygame.font.Font(None, approx_font_size)
        self.txt_surface = self.FONT.render(self.text, True, (0, 0, 0))
        # Dynamically resize width if text exceeds current box width
        text_width = self.txt_surface.get_width() + 10
        if text_width > self.rect.width:
            self.rect.width = text_width

    def handle_event(self, event) -> None:
        self.update_rect()
        self.update()
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                self.active = True
                self.colour = self.colour_ACTIVE
                # cursor placement for single line
                x_rel = event.pos[0] - (self.rect.x + 5)
                char_widths = [
                    self.FONT.size(self.text[:i])[0] for i in range(len(self.text) + 1)
                ]
                closest_i = 0
                closest_diff = float("inf")
                for i, cw in enumerate(char_widths):
                    diff = abs(cw - x_rel)
                    if diff < closest_diff:
                        closest_diff = diff
                        closest_i = i
                self.cursor_pos = closest_i
            else:
                self.active = False
                self.colour = self.colour_INACTIVE

        if event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_v and (pygame.key.get_mods() & pygame.KMOD_CTRL):
                # Paste text if available
                clip = pygame.scrap.get(pygame.SCRAP_TEXT)
                if clip:
                    clip = clip.decode("utf-8", "ignore").replace("\r", "")
                    for c in clip:
                        if c in IS_PRINTABLE and len(self.text) < self.max_length:
                            self.text = (
                                self.text[: self.cursor_pos]
                                + c
                                + self.text[self.cursor_pos :]
                            )
                            self.cursor_pos += 1
            elif event.key == pygame.K_BACKSPACE and self.cursor_pos > 0:
                self.text = (
                    self.text[: self.cursor_pos - 1] + self.text[self.cursor_pos :]
                )
                self.cursor_pos -= 1
            elif event.key == pygame.K_LEFT and self.cursor_pos > 0:
                self.cursor_pos -= 1
            elif event.key == pygame.K_RIGHT and self.cursor_pos < len(self.text):
                self.cursor_pos += 1
            else:
                # Typed a character
                if event.unicode in IS_PRINTABLE and len(self.text) < self.max_length:
                    self.text = (
                        self.text[: self.cursor_pos]
                        + event.unicode
                        + self.text[self.cursor_pos :]
                    )
                    self.cursor_pos += 1
            self.update()

    def draw(self, screen: pygame.Surface) -> None:
        pygame.draw.rect(screen, self.colour, self.rect, 2)
        txt_surface = self.FONT.render(self.text, True, (0, 0, 0))
        screen.blit(txt_surface, (self.rect.x + 5, self.rect.y + 5))
        if self.active:
            cursor_x = self.rect.x + 5 + self.FONT.size(self.text[: self.cursor_pos])[0]
            pygame.draw.line(
                screen,
                (0, 0, 0),
                (cursor_x, self.rect.y + 5),
                (cursor_x, self.rect.y + self.rect.height - 5),
                2,
            )


class Button(UIElement):
    def __init__(
        self,
        ui_manager,
        label: str,
        bg_colour: Tuple[int, int, int],
        text_colour: Tuple[int, int, int],
        x_factor: float,
        y_factor: float,
        w_factor: float,
        h_factor: float,
        *args,
        disabled: bool = False,
        action: Any = None,
    ):
        super().__init__(ui_manager, x_factor, y_factor, w_factor, h_factor)
        self.__text = label
        self.__bg_colour = bg_colour
        self.__text_colour = text_colour
        self.__disabled = disabled
        self.__action = action
        self.__args = args
        self.focused = False
        # font size based on rect
        approx_font_size = int(self.rect.height * 0.5)
        self.font = pygame.font.Font(None, approx_font_size)
        self.update()

    def update(self):
        approx_font_size = int(self.rect.height * 0.5)
        self.font = pygame.font.Font(None, approx_font_size)
        self.text_surface = self.font.render(self.__text, True, self.__text_colour)

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
            value = bool(value)
        if isinstance(value, bool):
            self.__disabled = value
        else:
            raise TypeError(f"{value} is type {type(value)} not boolean!")

    async def handle_event(self, event: pygame.event.Event) -> None:
        self.update_rect()
        self.update()
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                if not self.__disabled and self.__action is not None:
                    if iscoroutinefunction(self.__action):
                        asyncio.create_task(self.__action(*self.__args))
                    else:
                        self.__action(*self.__args)

    def click(self) -> None:
        if not self.__disabled and self.__action is not None:
            if iscoroutinefunction(self.__action):
                asyncio.create_task(self.__action(*self.__args))
            else:
                self.__action(*self.__args)

    def draw(self, window: pygame.Surface) -> None:
        colour = colours["DISABLED"] if self.__disabled else self.__bg_colour
        pygame.draw.rect(window, colour, self.rect)
        text_rect = self.text_surface.get_rect(center=self.rect.center)
        window.blit(self.text_surface, text_rect)
        if self.focused:
            pygame.draw.rect(window, (0, 0, 0), self.rect, 2)


class Text(UIElement):
    def __init__(
        self,
        ui_manager,
        x_factor: float,
        y_factor: float,
        w_factor: float,
        h_factor: float,
        colour: Tuple,
        text: str,
        size: int = 28,
    ):
        super().__init__(ui_manager, x_factor, y_factor, w_factor, h_factor)
        w, h = self.ui_manager.screen.get_size()
        scaled_font_size = int(size * (w / 1920))
        self.__size = size
        self.__text = text
        self.__colour = colour
        self.__font: pygame.font.Font = (
            FONT if size == 28 else pygame.font.SysFont("comicsans", scaled_font_size)
        )

    def __len__(self) -> int:
        return len(self.__text)

    @property
    def get_text(self) -> str:
        return self.__text

    async def handle_event(self, event: pygame.event.Event) -> None:
        self.update_rect()
        w, h = self.ui_manager.screen.get_size()
        scaled_font_size = int(self.__size * (w / 1920))
        self.__font: pygame.font.Font = (
            FONT
            if self.__size == 28
            else pygame.font.SysFont("comicsans", scaled_font_size)
        )

    def draw(
        self, window: pygame.Surface, bg_colour: Tuple[int, int, int] | None = None
    ) -> None:
        if bg_colour is None:
            bg_colour = colours["TURQUOISE"]
        # Draw bg if needed:
        pygame.draw.rect(window, bg_colour, self.rect)
        text_surface = self.__font.render(self.__text, True, self.__colour)
        text_rect = text_surface.get_rect(center=self.rect.center)
        window.blit(text_surface, text_rect)


class DynamicText(Text):
    def __init__(
        self,
        ui_manager,
        x_factor: float,
        y_factor: float,
        w_factor: float,
        h_factor: float,
        colour: Tuple,
        text: str,
        fmt_dict: dict,
        size: int = 28,
    ):
        super().__init__(
            ui_manager, x_factor, y_factor, w_factor, h_factor, colour, text, size=size
        )
        self._fmt_dict = fmt_dict

    def __len__(self) -> int:
        return len(self.get_text)

    @abstractmethod
    def fmt_text(self, text: str) -> str:
        raise NotImplementedError

    @property
    def get_text(self) -> str:
        return self.fmt_text(super().get_text)
