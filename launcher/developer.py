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
from multiprocessing import Process
from typing import List, Tuple

from launcher.launcher import Launcher

""" This file was coded for the purpose of QOL for the testing video  """


async def run_client(username: str, password: str) -> None:
    await Launcher().run(username, password)


def create_launcher_process(username: str, password: str) -> None:
    asyncio.run(run_client(username, password))


if __name__ == "__main__":
    clients: List[Tuple[str, str]] = [
        ("RAY", "Password1"),
        ("test", "Password1"),
        # ("test1", "Password1")
    ]

    for username, password in clients:
        Process(target=create_launcher_process, args=(username, password)).start()
