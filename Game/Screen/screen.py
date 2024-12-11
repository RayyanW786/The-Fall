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
from inspect import iscoroutinefunction
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional, Tuple, Union

import pygame

from .constants import FONT, FPS, backgrounds, colours
from .handler import Handler
from .utils import Button, DynamicText, InputBox, Text

if TYPE_CHECKING:
    from logging import Logger

    from Game.Networking.client import Client as NetworkClient
    from launcher.launcher import Launcher

    from .game import Game


class UIManager:
    def __init__(self, screen: pygame.Surface):
        self.screen = screen
        self.elements: Dict[
            str, Dict[str, Union[Button, InputBox, Text, DynamicText, List]]
        ] = {"buttons": {}, "inputboxes": {}, "text": {}, "functions": {}}

    def get_size(self):
        return self.screen.get_size()

    def scale_pos(self, x_factor: float, y_factor: float) -> Tuple[int, int]:
        w, h = self.get_size()
        return int(x_factor * w), int(y_factor * h)

    def scale_size(self, w_factor: float, h_factor: float) -> Tuple[int, int]:
        w, h = self.get_size()
        return int(w_factor * w), int(h_factor * h)

    def ensure_no_collision(self, new_element, allowed_overlap=5):
        # Only proceed if element has a rect attribute
        if not hasattr(new_element, "rect"):
            return

        moved = True
        while moved:
            moved = False
            for cat in self.elements:
                for el_name, el in self.elements[cat].items():
                    if el is not new_element and hasattr(el, "rect"):
                        if el.rect.colliderect(new_element.rect):
                            intersection = el.rect.clip(new_element.rect)
                            if (
                                intersection.width > allowed_overlap
                                and intersection.height > allowed_overlap
                            ):
                                new_element.rect.y += 10
                                moved = True
                                break
                if moved:
                    break

    def add_element(
        self,
        category: Literal["buttons", "inputboxes", "text", "functions"],
        name: str,
        element,
    ):
        if category in ["buttons", "inputboxes", "text"]:
            self.ensure_no_collision(element)
        self.elements[category][name] = element

    def remove_element(
        self, category: Literal["buttons", "inputboxes", "text", "functions"], name: str
    ):
        try:
            del self.elements[category][name]
        except KeyError:
            pass

    def get_element(
        self, category: Literal["buttons", "inputboxes", "text", "functions"], name: str
    ):
        return self.elements[category].get(name)

    def get_elements(
        self, category: Literal["buttons", "inputboxes", "text", "functions"]
    ):
        return self.elements[category]

    def get_task_keys(
        self, category: Literal["buttons", "inputboxes", "text", "functions"]
    ):
        return self.elements[category].keys()

    async def handle_events(self, events: List[pygame.event.Event]):
        # Focus and tabbing logic
        for event in events:
            for cat in self.elements:
                for el_name, el in self.elements[cat].copy().items():
                    if hasattr(el, "handle_event"):
                        if iscoroutinefunction(el.handle_event):
                            await el.handle_event(event)
                        else:
                            el.handle_event(event)

    async def run_tasks(self):
        # Draw all elements
        for cat in ["buttons", "inputboxes", "text"]:
            for name, el in self.elements[cat].copy().items():
                if hasattr(el, "draw"):
                    if cat == "text":
                        el.draw(self.screen)
                    else:
                        el.draw(self.screen)

        # Call functions
        for name, func_list in self.elements["functions"].copy().items():
            if iscoroutinefunction(func_list[0]):
                await func_list[0](*func_list[1:])
            else:
                await asyncio.to_thread(func_list[0], *func_list[1:])

    def clear_tasks(self):
        self.elements = {"buttons": {}, "inputboxes": {}, "functions": {}, "text": {}}


class Screen:
    def __init__(self, launcher: Launcher):
        self.__launcher: Launcher = launcher
        self.__client: NetworkClient = launcher.client
        pygame.init()
        pygame.display.set_caption("The Fall")
        displayinfo = pygame.display.Info()
        self.win_size: Tuple[int, int] = (
            displayinfo.current_w - 5,
            displayinfo.current_h - 100,
        )
        self.window: pygame.Surface = pygame.display.set_mode(
            self.win_size, pygame.RESIZABLE
        )
        pygame.scrap.init()
        self.FONT: pygame.font.SysFont = FONT
        self.colours: Dict[str, Tuple[int, int, int]] = colours
        self.backgrounds: Dict[str, str] = backgrounds
        self.screen_config: Dict[str, Any] = {
            "background": None,
            "fps": FPS,
            "clock": pygame.time.Clock(),
            "bgcolour": self.colours["TURQUOISE"],
            "parent": None,
            "minor": None,
            "loading": False,
        }
        self.__logger: Logger = self.__launcher.logger
        self.__handler: Handler = Handler(self)
        self.tab_current_index: Optional[int] = None
        self.ui_manager = UIManager(self.window)

    def set_screen_minor(
        self, minor: Literal["Login", "Register", "ForgotPassword", "MainUi"] | None
    ) -> None:
        self.screen_config["minor"] = minor
        self.__handler.registered_views = False

    def set_parent(self, parent: Literal["Launcher", "MainUI", "Game"]) -> None:
        self.screen_config["parent"] = parent

    @property
    def logger(self) -> Logger:
        return self.__logger

    @property
    def runner(self) -> bool:
        return self.__launcher.runner

    @property
    def client(self) -> NetworkClient:
        return self.__client

    @property
    def handler(self) -> Handler:
        return self.__handler

    @property
    def loading(self) -> bool:
        return True if self.screen_config.get("loading", False) else False

    @loading.setter
    def loading(self, value: bool) -> None:
        self.screen_config["loading"] = value

    @property
    def game(self) -> Optional[Game]:
        return self.__launcher.game

    @game.setter
    def game(self, payload: Optional[Game]) -> None:
        self.__launcher.game = payload

    def add_task(
        self,
        _type: Literal["buttons", "inputboxes", "text", "functions"],
        name: str,
        value,
    ):
        if _type in ["buttons", "inputboxes", "text"]:
            self.ui_manager.add_element(_type, name, value)
        else:
            self.ui_manager.elements[_type][name] = value

    def get_tasks(self, _type: Literal["buttons", "inputboxes", "text", "functions"]):
        return self.ui_manager.get_elements(_type)

    def get_task(
        self, _type: Literal["buttons", "inputboxes", "text", "functions"], name: str
    ):
        return self.ui_manager.get_element(_type, name)

    def get_task_keys(
        self, _type: Literal["buttons", "inputboxes", "text", "functions"]
    ):
        return self.ui_manager.get_task_keys(_type)

    def remove_task(
        self, _type: Literal["buttons", "inputboxes", "text", "functions"], name: str
    ) -> None:
        self.ui_manager.remove_element(_type, name)

    async def run_tasks(self) -> None:
        await self.ui_manager.run_tasks()

    def clear_tasks(self) -> None:
        self.ui_manager.clear_tasks()

    def display_loading_screen(self) -> None:
        win_cx, win_cy = self.window.get_rect().center
        # Just show a simple loading text:
        font = pygame.font.Font(None, 50)
        txt_surface = font.render("Loading...", True, self.colours["WHITE"])
        rect = txt_surface.get_rect(center=(win_cx, win_cy))
        self.window.blit(txt_surface, rect)

    def get_focusable_elements(self) -> List[Union[InputBox, Button]]:
        # Combine inputboxes and buttons
        return list(self.get_tasks("inputboxes").values()) + list(
            self.get_tasks("buttons").values()
        )

    def cycle_focus(self, forward: bool = True) -> None:
        elements = self.get_focusable_elements()
        if not elements:
            self.tab_current_index = None
            return
        if self.tab_current_index is None:
            self.tab_current_index = 0
        else:
            self.tab_current_index = (
                self.tab_current_index + (1 if forward else -1)
            ) % len(elements)
        # Unfocus all
        for e in elements:
            if isinstance(e, InputBox):
                e.active = False
                e.colour = e.colour_INACTIVE
            elif isinstance(e, Button):
                e.focused = False
        current = elements[self.tab_current_index]
        if isinstance(current, InputBox):
            current.active = True
            current.colour = current.colour_ACTIVE
        elif isinstance(current, Button):
            current.focused = True

    async def handle_events(self) -> None:
        if self.__launcher.game:
            await self.__launcher.game.handle(self.window)

        await self.__handler.check()
        events = pygame.event.get()

        # Focus and Tab logic
        for event in events:
            self.handle_exit(event)
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_TAB:
                    self.cycle_focus(True)
                elif event.key == pygame.K_RETURN:
                    buttons = list(self.get_tasks("buttons").values())
                    one_button = len(buttons) == 1
                    if one_button and buttons:
                        buttons[0].click()
                    else:
                        # If something is focused:
                        if self.tab_current_index is not None:
                            try:
                                el = self.get_focusable_elements()[self.tab_current_index]
                                if isinstance(el, Button):
                                    el.click()
                            except IndexError:
                                self.tab_current_index = None
        # Now pass events to UI elements
        await self.ui_manager.handle_events(events)

    def handle_exit(self, event) -> None:
        if event.type == pygame.QUIT:
            asyncio.create_task(self.__launcher.close())

    def handle_background(self) -> bool:
        background = self.screen_config.get("background")
        if not background:
            bgcolour = self.screen_config.get("bgcolour")
            self.window.fill(bgcolour)
        else:
            background = self.backgrounds[background]
            img = pygame.image.load(f"{background}")
            img = pygame.transform.scale(img, (self.win_size[0], self.win_size[1]))
            self.window.blit(img, [0, 0])
        if self.loading:
            self.display_loading_screen()
            return True
        return False

    async def run(self) -> None:
        while self.__launcher.runner:
            await asyncio.sleep(0)
            clock = self.screen_config["clock"]
            fps = self.screen_config["fps"]
            try:
                loading = self.handle_background()
                if loading:
                    pygame.display.flip()
                    continue
                await self.run_tasks()
                await self.handle_events()
                pygame.display.flip()
                clock.tick(fps)
            except pygame.error:
                pass
