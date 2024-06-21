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
from typing import Tuple, Dict, Any, Literal, Optional, Union, TYPE_CHECKING, KeysView, Callable, List
from .constants import colours, FPS, FONT, backgrounds
from .utils import InputBox, create_input_box, Button, create_text_surface, Text, DynamicText
from .handler import Handler
import asyncio
from inspect import iscoroutinefunction

if TYPE_CHECKING:
    from launcher.launcher import Launcher
    from Game.Networking.client import Client as NetworkClient
    from .game import Game
    from logging import Logger

class Screen(object):
    """ Handles the screen functionality via pygame """
    def __init__(self, launcher: Launcher):
        self.__launcher: Launcher = launcher
        self.__client: NetworkClient = launcher.client
        pygame.init()
        pygame.display.set_caption("The Fall")
        displayinfo = pygame.display.Info()
        self.win_size: Tuple[int, int] = (displayinfo.current_w - 5, displayinfo.current_h - 100)
        self.window: pygame.Surface | pygame.SurfaceType = pygame.display.set_mode(
            self.win_size, pygame.RESIZABLE | pygame.DOUBLEBUF
        )
        self.FONT: pygame.font.SysFont = FONT
        self.colours: Dict[str, Tuple[int, int, int]] = colours
        self.backgrounds: Dict[str, str] = backgrounds
        self.__persistent: Dict[str, Dict[
            str, Union[Button, InputBox, Text, DynamicText, List[Callable[..., Any], Tuple[Any, ...]]]]] = {
            'buttons': {},
            'inputboxes': {},
            'text': {},
            'functions': {}
        }

        self.screen_config: Dict[str, Any] = {
            'background': None,
            'fps': FPS,
            'clock': pygame.time.Clock(),
            'bgcolour': self.colours['TURQUOISE'],
            'parent': None,
            'minor': None,
            'loading': False
        }
        self.__logger: Logger = self.__launcher.logger
        self.__handler: Handler = Handler(self)


    def set_screen_minor(self, minor: Literal['Login', 'Register', 'ForgotPassword', 'MainUi'] | None) -> None:
        self.screen_config['minor'] = minor
        self.__handler.registered_views = False

    def set_parent(self, parent: Literal['Launcher', 'MainUI', 'Game']) -> None:
        self.screen_config['parent'] = parent

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
        return True if self.screen_config.get('loading', False) else False

    @loading.setter
    def loading(self, value: bool) -> None:
        self.screen_config['loading'] = value

    @property
    def game(self) -> Optional[Game]:
        return self.__launcher.game

    @game.setter
    def game(self, payload: Optional[Game]) -> None:
        self.__launcher.game = payload

    def add_task(self, _type: Literal['buttons', 'inputboxes', 'text', 'functions'],
                 name: str,
                 value: Union[
                     Button,
                     InputBox,
                     Text,
                     DynamicText,
                     List[Callable[..., Any], Optional[Tuple[Any, ...]]]
                 ]) -> None:
        self.__persistent[_type][name] = value

    def get_tasks(
            self,
            _type: Literal['buttons', 'inputboxes', 'text', 'functions']) -> Dict[
            str, Union[Button, InputBox, Text, DynamicText, List[Callable[..., Any], Tuple[Any, ...]]]]:
        return self.__persistent[_type]

    def get_task(self,
                 _type: Literal['buttons', 'inputboxes', 'text', 'functions'], name: str) \
            -> Union[Button, InputBox, Text, DynamicText, List[Callable[..., Any], Tuple[Any, ...]], None]:
        return self.__persistent[_type].get(name)

    def get_task_keys(self, _type: Literal['buttons', 'inputboxes', 'text', 'functions']) -> KeysView[str]:
        return self.__persistent[_type].keys()

    def remove_task(self, _type: Literal['buttons', 'inputboxes', 'text', 'functions'],
                    name: str) -> None:
        try:
            del self.__persistent[_type][name]
        except KeyError:
            pass
        except Exception as e:
            self.__logger.warning(f"error in remove task when deleting task [{e.__class__.__name__}]: {e}")

    async def run_tasks(self) -> None:
        for p_btns in self.__persistent['buttons'].copy():
            try:
                btn: Button = self.__persistent['buttons'][p_btns]
                btn.draw(self.window)
            except KeyError:
                pass

        for p_inputbx in self.__persistent['inputboxes'].copy():
            try:
                bx: InputBox = self.__persistent['inputboxes'][p_inputbx]
                bx.update()
                bx.draw(self.window)
            except KeyError:
                pass
        for p_text in self.__persistent['text'].copy():
            try:
                txt: Text = self.__persistent['text'][p_text]
                txt.draw(self.window, self.screen_config['bgcolour'])
            except KeyError:
                pass
        for p_funcs in self.__persistent['functions'].copy():
            try:
                func: List[Callable[..., Any], Tuple[Any, ...]] = self.__persistent['functions'][p_funcs]
                if iscoroutinefunction(func):
                    await func[0](*func[1:])
                else:
                    func[0](*func[1:])
            except KeyError:
                pass

    def clear_tasks(self) -> None:
        """clears persistent"""
        self.__persistent['buttons'] = {}
        self.__persistent['inputboxes'] = {}
        self.__persistent['functions'] = {}
        self.__persistent['timed_text'] = {}
        self.__persistent['text'] = {}

    def display_loading_screen(self) -> None:
        win_cx, win_cy = self.window.get_rect().center
        create_text_surface(
            self.window, "Loading...", self.colours['WHITE'],
            create_input_box(
                self.window, self.screen_config['bgcolour'],
                win_cx - 100, win_cy - 100, 200, 200
            )
        )

    async def handle_events(self) -> None:
        """ Handles the pygame events and views (buttons and inputboxes) """
        if self.__launcher.game:
            await self.__launcher.game.handle(self.window)

        await self.__handler.check()
        for event in pygame.event.get():
            self.handle_exit(event)
            if event.type in (pygame.MOUSEBUTTONDOWN,):
                for p_btns in self.__persistent['buttons'].copy():
                    try:
                        btn: Button = self.__persistent['buttons'][p_btns]
                        await btn.handle_event(event)
                    except KeyError:
                        pass
            if event.type in (pygame.MOUSEBUTTONDOWN, pygame.KEYDOWN):
                for p_inputbx in self.__persistent['inputboxes'].copy():
                    try:
                        bx: InputBox = self.__persistent['inputboxes'][p_inputbx]
                        bx.handle_event(event)
                    except KeyError:
                        pass

    def handle_exit(self, event) -> None:
        """ Provides a clean way to exit the code """
        if event.type == pygame.QUIT:
            asyncio.create_task(self.__launcher.close())

    def handle_background(self) -> bool:
        """
        Manages the background
        """
        background = self.screen_config.get('background')
        if not background:
            bgcolour = self.screen_config.get('bgcolour')
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
        """
        :return: None
        This function is the main loop for the pygame screen
        It renders and handles all events
        """
        while self.__launcher.runner:
            await asyncio.sleep(0.02)
            clock = self.screen_config['clock']
            fps = self.screen_config['fps']
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

