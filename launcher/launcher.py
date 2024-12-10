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

import asyncio
import logging
from typing import Optional

import pygame
import websockets
import websockets.protocol

from Game import Client, Game, Screen

logging.basicConfig(
    level=logging.INFO,
    format="[{asctime}] [{levelname:<7}] {name}: {message}",
    style="{",
    datefmt="%Y-%m-%d %H:%M:%S",
)
# logging format, style and datefmt taken from https://github.com/Rapptz/RoboDanny/blob/rewrite/launcher.py#L182

CONNECT_PATH: str = "ws://localhost:50000"


class Launcher:
    """Combines the whole game into a single class which can be run"""

    def __init__(self) -> None:
        self.__logger = logging.getLogger("Launcher")
        self.__client: Client = Client(self)
        self.__screen: Screen = None  # type: ignore
        self.__runner: bool = True
        self.__Game: Optional[Game] = None

    @property
    def logger(self) -> logging.Logger:
        return self.__logger

    @property
    def client(self) -> Client:
        return self.__client

    @property
    def runner(self) -> bool:
        return self.__runner

    @property
    def game(self) -> Optional[Game]:
        return self.__Game

    @game.setter
    def game(self, payload: Optional[Game]) -> None:
        self.__Game = payload

    def setup_screen(
        self, username: Optional[str] = None, password: Optional[str] = None
    ) -> None:
        if username and password:
            asyncio.create_task(self.skip_login(username, password))
        else:
            self.__screen.set_parent("Launcher")

    async def skip_login(self, username: str, password: str) -> None:
        """
        Allows me (the developer) to login without having to actually log in
        its purpose is a QOL for the testing video and when debugging.
        """
        self.__screen.set_parent("MainUI")
        await self.__client.login(username, password)
        await self.__screen.handler.MainUI()

    async def run(
        self, username: Optional[str] = None, password: Optional[str] = None
    ) -> None:
        try:
            async with websockets.connect(CONNECT_PATH) as websocket:
                asyncio.create_task(self.__client.run(websocket))
                self.__screen = Screen(self)
                # if True:
                #     username, password = ("RAY", "Password1")
                # else:
                # username, password = ("test1", "Password1")
                #     # username, password = ("test", "Password1")
                # ^^ above code was used for development + testing video
                self.setup_screen(username, password)
                asyncio.create_task(self.__screen.run())
                while self.__runner:
                    await asyncio.sleep(0)
        except ConnectionRefusedError:
            self.__logger.error("Cannot connect to game servers, exiting....")

    async def close(self) -> None:
        if (
            self.__client.ws
            and self.__client.ws.state == websockets.protocol.State.OPEN
        ):
            self.__logger.info("CLOSING CONNECTION...")
            await self.__client.ws.close()
            await self.__client.ws.wait_closed()
        self.__runner = False
        pygame.quit()
        self.__logger.info("CLOSED GAME!")


if __name__ == "__main__":
    asyncio.run(Launcher().run())
