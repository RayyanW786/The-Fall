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
import datetime
import re
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Literal, Optional

from fuzzywuzzy import fuzz

from ..Networking.client import GameInfo, Lobby, User
from ..utils import chunked, human_timedelta
from .constants import EMAIL_RE
from .utils import Button, DynamicText, InputBox, Text, colours

if TYPE_CHECKING:
    from .screen import Screen


class OTPTimer(DynamicText):
    def fmt_text(self, text: str) -> str:
        return text.format(
            dt=self._fmt_dict["func"](
                self._fmt_dict["dt"]
                .get("register_s2", {})
                .get("exp", datetime.datetime.now())
            )
        )


class CountDown(DynamicText):
    def fmt_text(self, text: str) -> str:
        return text.format(
            dt=self._fmt_dict["func"](self._fmt_dict["dt"]),
            msg=self._fmt_dict.get("msg", ""),
        )


class Handler:
    """This class handles many of the pygame event loop for the buttons and inputboxes (views)"""

    def __init__(self, screen: Screen):
        self.__screen: Screen = screen
        self.__registered_views: bool = False
        self.__register_submit: bool = False
        self.__data: Dict[str, Any] = {}
        self.__started_game_check: bool = False

    def dynamic(self, factor: float, _type: Literal["w", "h"]) -> int:
        w, h = self.__screen.window.get_size()
        if _type == "w":
            return int(w * factor)
        else:
            return int(h * factor)

    @property
    def registered_views(self) -> bool:
        return self.__registered_views

    @registered_views.setter
    def registered_views(self, value: bool) -> None:
        self.__registered_views = value

    async def delete_alert(
        self, _insts: Dict[str, Text | DynamicText], sleep_until: int = 5
    ) -> None:
        await asyncio.sleep(sleep_until)
        for key in _insts:
            if key in self.__screen.get_task_keys("text"):
                if self.__screen.get_task("text", key) is _insts[key]:
                    self.__screen.remove_task("text", key)

    async def register_step1_checks(self) -> bool | Dict:
        inputbxs: Dict[str, InputBox] = self.__screen.get_tasks("inputboxes")
        displayname = inputbxs.get("displayname", None)
        username = inputbxs.get("username", None)
        password = inputbxs.get("password", None)
        confpass = inputbxs.get("confirm_password", None)
        email = inputbxs.get("email", None)
        flags: List[bool] = [False, False, False, False, False]
        total_feedback: Dict[str, List] = {"dpn": [], "usn": [], "pwd": [], "em": []}

        if displayname is not None:
            if not displayname.text:
                total_feedback["dpn"].append(
                    "displayname is a required field and is missing!"
                )
            elif len(displayname.text) < 2 or len(displayname) > 10:
                total_feedback["dpn"].append(
                    "displayname must be bigger than 2 and lower than 10"
                )
            else:
                flags[0] = True

        if username is not None:
            if username.text:
                res = await self.__screen.client.username_lookup(str(username))
                if res:
                    total_feedback["usn"].append("Username Taken!")
                else:
                    flags[1] = True
            else:
                total_feedback["usn"].append(
                    "Username is a required field and is missing!"
                )

        if password is not None and confpass is not None:
            pwd_feedback: List[str] = []
            if not password.text or not confpass.text:
                total_feedback["pwd"].append(
                    "Password is a required field and is missing!"
                )
            elif confpass.text == password.text:
                password_flags = [False, False, False, False, False]
                if len(password) >= 8:
                    password_flags[4] = True
                if fuzz.ratio(username.text.lower(), password.text.lower()) < 70:
                    password_flags[3] = True
                for chr_ in password:
                    if all(password_flags):
                        break
                    if chr_.isdigit():
                        password_flags[0] = True
                    if chr_.isupper():
                        password_flags[1] = True
                    if chr_.islower():
                        password_flags[2] = True
                if not all(password_flags):
                    for index, val in enumerate(password_flags):
                        if not val:
                            if index == 0:
                                pwd_feedback.append(
                                    "Password must have at least one digit!"
                                )
                            elif index == 1:
                                pwd_feedback.append(
                                    "Password must have at least one uppercase!"
                                )
                            elif index == 2:
                                pwd_feedback.append(
                                    "Password must have at least one lowercase!"
                                )
                            elif index == 3:
                                pwd_feedback.append(
                                    "Your username cannot be in your password!"
                                )
                            elif index == 4:
                                pwd_feedback.append(
                                    "Your password must be a length of 8 characters or more!"
                                )
                    total_feedback["pwd"].extend(pwd_feedback)
                else:
                    flags[2], flags[3] = True, True
            else:
                total_feedback["pwd"].append("Passwords do not match!")

        if email is not None:
            length = len(email.text.lower().strip())
            if not email.text:
                total_feedback["em"].append("Email is a required field and is missing!")
            elif not 5 < length < 30:
                total_feedback["em"].append(
                    "Email length should be more than 5 and less than 30"
                )
            elif not re.fullmatch(EMAIL_RE, email.text):
                total_feedback["em"].append("Invalid Email")
            else:
                flags[4] = True

        if not all(flags):
            if total_feedback:
                return total_feedback
            return False
        return True

    async def register_step1_continue(self) -> None:
        res = await self.register_step1_checks()
        if res is True:
            await self.init_register_step2()
        else:
            friendly: Dict[str, str] = {
                "dpn": "displayname",
                "usn": "username",
                "pwd": "password",
                "em": "email",
            }

            for potential in self.__screen.get_tasks("text").copy():
                if "fb_" in potential:
                    self.__screen.remove_task("text", potential)

            y_inc: int = 0
            x_inc: int = self.dynamic(0.7, "w")

            if isinstance(res, dict):
                for field in res:
                    if res[field]:
                        for idx, fb in enumerate(res[field]):
                            y_inc += 50
                            self.__screen.add_task(
                                "text",
                                friendly[field] + f"fb_{idx}",
                                Text(
                                    self.__screen.ui_manager,
                                    x_inc / self.__screen.window.get_width(),
                                    (y_inc / self.__screen.window.get_height()),
                                    0.05,
                                    0.05,
                                    colours["BLACK"],
                                    fb,
                                ),
                            )

    async def init_register_step2(self) -> None:
        ipbx = self.__screen.get_tasks("inputboxes")
        self.__data["register"] = {
            "displayname": ipbx["displayname"],
            "username": ipbx["username"],
            "password": ipbx["password"],
            "email": ipbx["email"],
        }
        self.__screen.clear_tasks()
        _temp = {k: str(v) for k, v in self.__data["register"].items()}
        await self.__screen.client.register(**_temp)
        self.__data["register"]["otp_expdt"] = self.__screen.client.notifs.get(
            "register_s2", {}
        ).get("exp", (datetime.datetime.now() + datetime.timedelta(minutes=5)))

        self.__screen.add_task(
            "text",
            "otp_info",
            OTPTimer(
                self.__screen.ui_manager,
                0.45,
                0.1,
                0.1,
                0.1,
                colours["BLACK"],
                "A One Time Password Code was sent to your email, the code will expire in {dt}",
                {"dt": self.__screen.client.notifs, "func": human_timedelta},
            ),
        )
        self.__screen.add_task(
            "text",
            "enter_code",
            Text(
                self.__screen.ui_manager,
                0.025,
                0.45,
                0.1,
                0.1,
                colours["BLACK"],
                "Enter Code:",
                size=40,
            ),
        )
        self.__screen.add_task(
            "buttons",
            "create",
            Button(
                self.__screen.ui_manager,
                "Create Account",
                colours["BLURPLE"],
                colours["BLACK"],
                0.7,
                0.45,
                0.1,
                0.1,
                action=self.submit_register,
            ),
        )
        self.__screen.add_task(
            "inputboxes",
            "otp_inp",
            InputBox(
                self.__screen.ui_manager,
                "otp_code",
                0.25,
                0.57,
                0.1,
                0.05,
                max_length=6,
            ),
        )

    async def submit_register(self) -> None:
        try:
            self.__data["register"]["otp"] = int(
                str(self.__screen.get_task("inputboxes", "otp_inp"))
            )
        except ValueError as e:
            self.__screen.logger.warning(
                f"suppressing error {e.__class__.__name__}: {e}"
            )
            inst = Text(
                self.__screen.ui_manager,
                0.4,
                0.3,
                0.1,
                0.1,
                colours["BLACK"],
                "Account Creation Unsuccessful: Invalid OTP code",
            )
            self.__screen.add_task("text", "inform_err", inst)
            asyncio.create_task(self.delete_alert({"inform_err": inst}))

        _temp = {
            k: (str(v) if type(v) not in [int, str] else v)
            for k, v in self.__data["register"].items()
        }
        del _temp["otp_expdt"]
        response = await self.__screen.client.register(**_temp)
        if isinstance(type(response), dict):
            if response["code"] in [1, 4]:
                self.__screen.clear_tasks()
                cd = CountDown(
                    self.__screen.ui_manager,
                    0.45,
                    0.4,
                    0.1,
                    0.1,
                    colours["BLACK"],
                    "Account Creation Unsuccessful: {msg}. You will be redirected to the main menu automatically in {dt}",
                    {
                        "dt": datetime.datetime.now() + datetime.timedelta(seconds=5),
                        "func": human_timedelta,
                        "msg": response["message"],
                    },
                )
                self.__screen.add_task("text", "go_back", cd)
                await asyncio.sleep(5)
                self.__data = {}
                self.__screen.clear_tasks()
                self.__screen.set_screen_minor(None)
                self.registered_views = False
            elif response["code"] in [2, 3, 5]:
                inst = Text(
                    self.__screen.ui_manager,
                    0.4,
                    0.3,
                    0.1,
                    0.1,
                    colours["BLACK"],
                    f"Account Creation Unsuccessful: {response['message']}",
                )
                self.__screen.add_task("text", "inform_err", inst)
                asyncio.create_task(
                    self.delete_alert({"inform_err": inst}, sleep_until=7)
                )
            elif response["code"] in [6]:
                data = self.__screen.client.notifs.get("ratelimit")
                if not data:
                    return
                cd = CountDown(
                    self.__screen.ui_manager,
                    0.4,
                    0.3,
                    0.1,
                    0.1,
                    colours["BLACK"],
                    "Account Creation Unsuccessful: {msg} Retry in {dt}",
                    {
                        "dt": datetime.datetime.fromtimestamp(data["dt"]),
                        "func": human_timedelta,
                        "msg": data["message"],
                    },
                )
                self.__screen.add_task("text", "inform_err", cd)
                asyncio.create_task(
                    self.delete_alert({"inform_err": cd}, sleep_until=15)
                )
        else:
            if response is False:
                inst = Text(
                    self.__screen.ui_manager,
                    0.45,
                    0.3,
                    0.1,
                    0.1,
                    colours["BLACK"],
                    "Account Creation Unsuccessful: Unable to establish a connection"
                    "See console",
                )
                self.__screen.add_task("text", "inform_err", inst)
                asyncio.create_task(
                    self.delete_alert({"inform_err": inst}, sleep_until=15)
                )
                return
            self.__screen.clear_tasks()
            cd = CountDown(
                self.__screen.ui_manager,
                0.4,
                0.3,
                0.1,
                0.1,
                colours["BLACK"],
                "Account Creation successful! You will be placed into the main menu in {dt}",
                {
                    "dt": datetime.datetime.now() + datetime.timedelta(seconds=10),
                    "func": human_timedelta,
                },
            )
            self.__screen.add_task("text", "created", cd)
            asyncio.create_task(self.delete_alert({"inform_err": cd}, sleep_until=10))
            await self.MainUI()

    async def submit_login(self) -> None:
        """Called by button click, handles login"""
        ipbx = self.__screen.get_tasks("inputboxes")
        self.__data["login"] = {
            "username": ipbx["username"],
            "password": ipbx["password"],
        }

        _temp = {k: str(v) for k, v in self.__data["login"].items()}
        response = await self.__screen.client.login(**_temp)

        if not response:
            rl_data = self.__screen.client.notifs.get("ratelimit")
            if rl_data and rl_data["dt"] > datetime.datetime.now().timestamp():
                # Use CountDown dynamic text
                inst = CountDown(
                    self.__screen.ui_manager,
                    0.6,
                    0.25,
                    0.1,
                    0.05,
                    colours["BLACK"],
                    "Login Failed: {msg} Retry in {dt}",
                    {
                        "dt": datetime.datetime.fromtimestamp(rl_data["dt"]),
                        "func": human_timedelta,
                        "msg": rl_data["message"],
                    },
                )
                self.__screen.add_task("text", "login_failure", inst)
                asyncio.create_task(self.delete_alert({"login_failure": inst}))
            else:
                inst = Text(
                    self.__screen.ui_manager,
                    0.6,
                    0.25,
                    0.1,
                    0.05,
                    colours["BLACK"],
                    "Login Error: Incorrect Username or Password!",
                )
                self.__screen.add_task("text", "login_failure", inst)
                asyncio.create_task(self.delete_alert({"login_failure": inst}))
        else:
            self.__screen.clear_tasks()
            inst = Text(
                self.__screen.ui_manager,
                0.4,
                0.3,
                0.1,
                0.05,
                colours["BLACK"],
                "You have logged in successfully",
            )
            self.__screen.add_task("text", "greet", inst)
            await asyncio.sleep(2)
            self.__screen.clear_tasks()
            await self.MainUI()

    async def add_friend(self, user: User) -> None:
        response = await self.__screen.client.add_friend(user)
        if response.get("error"):
            if response.get("code", 0) == 2:
                response["message"] = (
                    response["message"]
                    + " Try again in "
                    + human_timedelta(
                        datetime.datetime.fromtimestamp(
                            self.__screen.client.notifs.get("ratelimit", {}).get(
                                "dt", datetime.datetime.now().timestamp()
                            )
                        )
                    )
                )
            _inst = Text(
                self.__screen.ui_manager,
                0.4,
                0.25,
                0.2,
                0.05,
                colours["BLACK"],
                response["message"],
            )
            self.__screen.add_task("text", "output", _inst)
            asyncio.create_task(self.delete_alert({"output": _inst}))
        else:
            _with_user = response.get("with")
            if _with_user:
                text = f'You are now friends with "{_with_user}"'
            else:
                text = f'Send a friend request to "{user.username}"'
            _inst = Text(
                self.__screen.ui_manager, 0.4, 0.25, 0.2, 0.05, colours["BLACK"], text
            )
            self.__screen.add_task("text", "output", _inst)
            asyncio.create_task(self.delete_alert({"output": _inst}, sleep_until=10))

    async def remove_friend(self, user: User) -> None:
        response = await self.__screen.client.remove_friend(user)
        if response.get("error"):
            if response.get("code", 0) == 2:
                response["message"] = (
                    response["message"]
                    + " Try again in "
                    + human_timedelta(
                        datetime.datetime.fromtimestamp(
                            self.__screen.client.notifs.get("ratelimit", {}).get(
                                "dt", datetime.datetime.now().timestamp()
                            )
                        )
                    )
                )
            _inst = Text(
                self.__screen.ui_manager,
                0.4,
                0.25,
                0.2,
                0.05,
                colours["BLACK"],
                response["message"],
            )
            self.__screen.add_task("text", "output", _inst)
            asyncio.create_task(self.delete_alert({"output": _inst}))
        else:
            _with_user = response.get("with")
            if _with_user:
                text = f'You are no longer friends with "{_with_user}"'
            else:
                text = f'You are not Friends with "{_with_user}"'
            _inst = Text(
                self.__screen.ui_manager, 0.4, 0.25, 0.2, 0.05, colours["BLACK"], text
            )
            self.__screen.add_task("text", "output", _inst)
            asyncio.create_task(self.delete_alert({"output": _inst}, sleep_until=10))

    async def view_profile(self, align_left: Optional[bool] = False) -> None:
        """View user profile."""
        self.__screen.loading = True
        user_box = self.__screen.get_task("inputboxes", "query_user")
        if not user_box:
            self.__screen.loading = False
            x_factor = 0.4 if not align_left else 0.15
            y_factor = 0.25
            _inst = Text(
                self.__screen.ui_manager,
                x_factor,
                y_factor,
                0.2,
                0.05,
                colours["BLACK"],
                "User is a required field and is missing!",
            )
            self.__screen.add_task("text", "output", _inst)
            asyncio.create_task(self.delete_alert({"output": _inst}))
        else:
            user = await self.__screen.client.get_or_fetch_user(str(user_box))
            if not user:
                self.__screen.loading = False
                x_factor = 0.4 if not align_left else 0.15
                y_factor = 0.25
                _inst = Text(
                    self.__screen.ui_manager,
                    x_factor,
                    y_factor,
                    0.2,
                    0.05,
                    colours["BLACK"],
                    f'User "{user_box}" not found!',
                )
                self.__screen.add_task("text", "output", _inst)
                asyncio.create_task(self.delete_alert({"output": _inst}))
            else:
                user_stats = [
                    f"Username: {user.username}, Displayname: {user.displayname}",
                    f"KD: {user.kd} | Hours Played: {user.hours_played:,}",
                    f"Games Played: {user.games_played:,} | Games Won: {user.games_won:,}",
                    f"Total Kills: {user.total_kills:,} | Total Deaths: {user.total_deaths}",
                ]
                if user.username == self.__screen.client.root.username:
                    user_stats.insert(0, "      (YOU)       ")
                elif user.username in self.__screen.client.root.friends:
                    user_stats.insert(0, "      (FRIEND)      ")

                y_start = 0.32 if not align_left else 0.3
                x_start = 0.4 if not align_left else 0.1
                self.__screen.loading = False

                for idx, ln in enumerate(user_stats):
                    self.__screen.add_task(
                        "text",
                        f"user_stats_{idx}",
                        Text(
                            self.__screen.ui_manager,
                            x_start,
                            y_start + (0.05 * idx),
                            0.2,
                            0.05,
                            colours["BLACK"],
                            ln,
                            size=22,
                        ),
                    )

                outbound_requests = await self.__screen.client.get_outbound_requests()
                inbound_requests = await self.__screen.client.get_inbound_requests()
                if outbound_requests.get("error"):
                    outbound_requests = {"result": []}
                if inbound_requests.get("error"):
                    inbound_requests = {"result": []}
                outbound_requests = outbound_requests["result"]
                inbound_requests = inbound_requests["result"]

                async def _action(
                    user: User, _type: Literal["add", "remove", "close"]
                ) -> None:
                    if _type == "add":
                        await self.add_friend(user)
                    elif _type == "remove":
                        await self.remove_friend(user)
                    elif _type == "close":
                        for idx in range(len(user_stats)):
                            self.__screen.remove_task("text", f"user_stats_{idx}")
                        self.__screen.remove_task("buttons", "close")
                        self.__screen.remove_task("buttons", "add")
                        self.__screen.remove_task("buttons", "remove")

                # Buttons
                # position them relatively
                # Add friend
                if (
                    user.username != self.__screen.client.root.username
                    and user.username not in self.__screen.client.root.friends
                    and user.username not in outbound_requests
                ):
                    self.__screen.add_task(
                        "buttons",
                        "add",
                        Button(
                            self.__screen.ui_manager,
                            "Add",
                            colours["BLURPLE"],
                            colours["WHITE"],
                            0.001 if align_left else 0.25,
                            0.82,
                            0.1,
                            0.05,
                            user,
                            "add",
                            action=_action,
                        ),
                    )
                # Remove if friend or request pending
                if user.username != self.__screen.client.root.username and (
                    user.username in self.__screen.client.root.friends
                    or user.username in outbound_requests
                    or user.username in inbound_requests
                ):
                    self.__screen.add_task(
                        "buttons",
                        "remove",
                        Button(
                            self.__screen.ui_manager,
                            "Remove",
                            colours["BLURPLE"],
                            colours["WHITE"],
                            0.2 if align_left else 0.45,
                            0.82,
                            0.1,
                            0.05,
                            user,
                            "remove",
                            action=_action,
                        ),
                    )

                # Close
                self.__screen.add_task(
                    "buttons",
                    "close",
                    Button(
                        self.__screen.ui_manager,
                        "Close",
                        colours["RED"],
                        colours["WHITE"],
                        0.1 if align_left else 0.35,
                        0.82,
                        0.1,
                        0.05,
                        user,
                        "close",
                        action=_action,
                    ),
                )

    def create_paginator(
        self,
        entries: List[Any],
        *,
        name: str,
        per_page: int = 5,
        dy_w: float = 0.35,
        dy_h: float = 0.65,
        inc_y: int = 40,
        entry_size: int = 22,
    ) -> Callable:
        if not entries:
            raise RuntimeError("entries cannot be empty")
        if not self.__data.get("paginator"):
            self.__data["paginator"] = {}
        self.__data["paginator"][name] = {
            "per_page": per_page,
            "total": len(entries),
            "pages": list(chunked(entries, per_page)),
            "current_page": 0,
        }

        def _paginator():
            data = self.__data["paginator"][name]
            per_page = data["per_page"]
            pages = data["pages"]
            current_page = data["current_page"]

            # clear old entries
            for idx in range(per_page):
                self.__screen.remove_task("text", f"entry_{idx}")
            self.__screen.remove_task("text", f"page_info_{name}")
            self.__screen.remove_task("text", f"total_entries_{name}")

            _chunk = pages[current_page]
            if len(_chunk) != per_page:
                difference = per_page - len(_chunk)
                _chunk.extend(["" for _ in range(difference)])

            # Draw entries
            y_start = dy_w
            x_start = dy_h

            for idx, entry in enumerate(_chunk):
                if entry:
                    self.__screen.add_task(
                        "text",
                        f"entry_{idx}",
                        Text(
                            self.__screen.ui_manager,
                            x_start,
                            y_start + (0.05 * idx),
                            0.2,
                            0.05,
                            colours["BLACK"],
                            entry,
                            size=entry_size,
                        ),
                    )

            page_info = Text(
                self.__screen.ui_manager,
                0.9,
                0.85,
                0.05,
                0.05,
                colours["BLACK"],
                f"page {current_page + 1:,}/{len(pages)}",
            )
            self.__screen.add_task("text", f"page_info_{name}", page_info)
            total_entries = Text(
                self.__screen.ui_manager,
                0.9,
                0.9,
                0.05,
                0.05,
                colours["BLACK"],
                f'total entries: {data["total"]:,}',
            )
            self.__screen.add_task("text", f"total_entries_{name}", total_entries)

        def increment_page():
            data = self.__data["paginator"][name]
            if data["current_page"] < len(data["pages"]) - 1:
                data["current_page"] += 1

        def decrement_page():
            data = self.__data["paginator"][name]
            if data["current_page"] > 0:
                data["current_page"] -= 1

        def close():
            data = self.__data["paginator"][name]
            for idx, _ in enumerate(data["pages"][data["current_page"]]):
                self.__screen.remove_task("text", f"entry_{idx}")
            self.__screen.remove_task("text", f"page_info_{name}")
            self.__screen.remove_task("text", f"total_entries_{name}")
            self.__screen.remove_task("buttons", f"previous_page_{name}")
            self.__screen.remove_task("buttons", f"close_{name}")
            self.__screen.remove_task("buttons", f"next_page_{name}")
            del self.__data["paginator"][name]

        # Buttons
        self.__screen.add_task(
            "buttons",
            f"previous_page_{name}",
            Button(
                self.__screen.ui_manager,
                "previous",
                colours["BLURPLE"],
                colours["WHITE"],
                0.55,
                0.82,
                0.1,
                0.05,
                disabled=True,
                action=decrement_page,
            ),
        )
        self.__screen.add_task(
            "buttons",
            f"close_{name}",
            Button(
                self.__screen.ui_manager,
                "close",
                colours["RED"],
                colours["WHITE"],
                0.65,
                0.82,
                0.1,
                0.05,
                action=close,
            ),
        )
        self.__screen.add_task(
            "buttons",
            f"next_page_{name}",
            Button(
                self.__screen.ui_manager,
                "next",
                colours["BLURPLE"],
                colours["WHITE"],
                0.75,
                0.82,
                0.1,
                0.05,
                action=increment_page,
            ),
        )

        return _paginator

    def remove_paginators(self, names: Optional[List[str]] = None) -> None:
        if not self.__data.get("paginator"):
            return
        for k_paginator in list(self.__data["paginator"].keys()):
            if names and k_paginator not in names:
                continue
            # close the paginator properly
            # simulate pressing close
            paginator = self.__data["paginator"][k_paginator]
            current_page = paginator["current_page"]
            for idx, _ in enumerate(paginator["pages"][current_page]):
                self.__screen.remove_task("text", f"entry_{idx}")
            self.__screen.remove_task("text", f"page_info_{k_paginator}")
            self.__screen.remove_task("text", f"total_entries_{k_paginator}")
            btns = [
                f"previous_page_{k_paginator}",
                f"close_{k_paginator}",
                f"next_page_{k_paginator}",
            ]
            for b in btns:
                self.__screen.remove_task("buttons", b)
            del self.__data["paginator"][k_paginator]

    async def friends_paginator(self) -> None:
        self.remove_paginators()
        friends = self.__screen.client.root.friends
        if not friends:
            text = Text(
                self.__screen.ui_manager,
                0.7,
                0.45,
                0.1,
                0.05,
                colours["BLACK"],
                "You don't have any friends yet!",
            )
            self.__screen.add_task("text", "friend_lst", text)
            asyncio.create_task(self.delete_alert({"friend_lst": text}))
        else:
            _paginator = self.create_paginator(friends, name="friends")
            self.__screen.add_task("functions", "friends", [_paginator])

    async def inbound_paginator(self) -> None:
        self.remove_paginators()
        inbound_requests = await self.__screen.client.get_inbound_requests()
        if inbound_requests.get("error"):
            inbound_requests = {"result": []}
        inbound_requests = inbound_requests["result"]
        if inbound_requests:
            _paginator = self.create_paginator(inbound_requests, name="inbound")
            self.__screen.add_task("functions", "inbound", [_paginator])
        else:
            _inst = Text(
                self.__screen.ui_manager,
                0.4,
                0.25,
                0.1,
                0.05,
                colours["BLACK"],
                "You have no inbound requests!",
            )
            self.__screen.add_task("text", "output", _inst)
            asyncio.create_task(self.delete_alert({"output": _inst}))

    async def outbound_paginator(self) -> None:
        self.remove_paginators()
        outbound_requests = await self.__screen.client.get_outbound_requests()
        if outbound_requests.get("error"):
            outbound_requests = {"result": []}
        outbound_requests = outbound_requests["result"]
        if outbound_requests:
            _paginator = self.create_paginator(outbound_requests, name="outbound")
            self.__screen.add_task("functions", "outbound", [_paginator])
        else:
            _inst = Text(
                self.__screen.ui_manager,
                0.4,
                0.25,
                0.1,
                0.05,
                colours["BLACK"],
                "You have no outbound requests!",
            )
            self.__screen.add_task("text", "output", _inst)
            asyncio.create_task(self.delete_alert({"output": _inst}))

    async def requests(self, redirect: Optional[List] = None) -> None:
        self.__screen.remove_task("buttons", "friends_list")
        self.__screen.remove_task("buttons", "requests")

        self.remove_paginators()

        inbound = Button(
            self.__screen.ui_manager,
            "Inbound",
            colours["FAWN"],
            colours["WHITE"],
            0.05,
            0.5,
            0.1,
            0.05,
            action=self.inbound_paginator,
        )
        self.__screen.add_task("buttons", "inbound_list", inbound)

        outbound = Button(
            self.__screen.ui_manager,
            "Outbound",
            colours["JADE"],
            colours["WHITE"],
            0.05,
            0.575,
            0.1,
            0.05,
            action=self.outbound_paginator,
        )
        self.__screen.add_task("buttons", "outbound_list", outbound)

        back = Button(
            self.__screen.ui_manager,
            "Back",
            colours["PUCE"],
            colours["WHITE"],
            0.05,
            0.65,
            0.1,
            0.05,
            redirect,
            action=self.friends_view,
        )
        self.__screen.add_task("buttons", "back", back)

    async def friends_view(self, redirect: Optional[List] = None) -> None:
        self.__screen.clear_tasks()

        # Input user
        self.__screen.add_task(
            "inputboxes",
            "query_user",
            InputBox(self.__screen.ui_manager, "query_user", 0.15, 0.05, 0.1, 0.05),
        )
        self.__screen.add_task(
            "text",
            "search",
            Text(
                self.__screen.ui_manager,
                0.05,
                0.05,
                0.1,
                0.05,
                colours["BLACK"],
                "User: ",
            ),
        )

        label = "Main Menu" if not redirect else redirect[0]
        action = self.MainUI if not redirect else redirect[1]
        args = redirect[2] if redirect else ()
        self.__screen.add_task(
            "buttons",
            "redirect",
            Button(
                self.__screen.ui_manager,
                label,
                colours["ORANGE"],
                colours["WHITE"],
                0.05,
                0.2,
                0.1,
                0.05,
                *args,
                action=action,
            ),
        )

        self.__screen.add_task(
            "buttons",
            "view_person",
            Button(
                self.__screen.ui_manager,
                "Profile",
                colours["PURPLE"],
                colours["WHITE"],
                0.05,
                0.35,
                0.1,
                0.05,
                action=self.view_profile,
            ),
        )

        self.__screen.add_task(
            "buttons",
            "friends_list",
            Button(
                self.__screen.ui_manager,
                "List",
                colours["BLURPLE"],
                colours["WHITE"],
                0.05,
                0.50,
                0.1,
                0.05,
                action=self.friends_paginator,
            ),
        )

        self.__screen.add_task(
            "buttons",
            "requests",
            Button(
                self.__screen.ui_manager,
                "Requests",
                colours["GREEN"],
                colours["WHITE"],
                0.05,
                0.65,
                0.1,
                0.05,
                redirect,
                action=self.requests,
            ),
        )

    async def invites_view(self) -> None:
        self.remove_paginators()
        invites = await self.__screen.client.get_invites()
        if not invites:
            text = Text(
                self.__screen.ui_manager,
                0.7,
                0.45,
                0.1,
                0.05,
                colours["BLACK"],
                "You don't have any invites!",
            )
            self.__screen.add_task("text", "output", text)
            asyncio.create_task(self.delete_alert({"output": text}))
        elif invites.get("error"):
            text = Text(
                self.__screen.ui_manager,
                0.7,
                0.45,
                0.1,
                0.05,
                colours["BLACK"],
                invites["message"],
            )
            self.__screen.add_task("text", "output", text)
            asyncio.create_task(self.delete_alert({"output": text}))
        else:
            entries = []
            for k, v in invites.items():
                entries.append(f"{k}: {v:,}")
            _pag = self.create_paginator(entries, name="invites", entry_size=26)
            self.__screen.add_task("functions", "invites", [_pag])

    async def join_lobby(self) -> None:
        self.__screen.clear_tasks()
        self.__screen.add_task(
            "buttons",
            "main_menu",
            Button(
                self.__screen.ui_manager,
                "Main Menu",
                colours["PUCE"],
                colours["WHITE"],
                0.05,
                0.2,
                0.1,
                0.05,
                action=self.MainUI,
            ),
        )
        self.__screen.add_task(
            "buttons",
            "invites",
            Button(
                self.__screen.ui_manager,
                "Invites",
                colours["LIGHTBLUE"],
                colours["WHITE"],
                0.05,
                0.4,
                0.1,
                0.05,
                action=self.invites_view,
            ),
        )

        self.__screen.add_task(
            "inputboxes",
            "invite_code",
            InputBox(
                self.__screen.ui_manager,
                "invite_code",
                0.35,
                0.1,
                0.1,
                0.05,
                max_length=6,
            ),
        )
        self.__screen.add_task(
            "text",
            "code_text",
            Text(
                self.__screen.ui_manager,
                0.25,
                0.1,
                0.1,
                0.05,
                colours["BLACK"],
                "Invite Code: ",
            ),
        )

        async def _forwarder():
            code_box = self.__screen.get_task("inputboxes", "invite_code")
            _output = None
            if not str(code_box):
                _output = "Invite Code is required"
            elif len(code_box) != 6:
                _output = "Invalid Invite Code!"
            else:
                try:
                    code = int(code_box)
                except ValueError:
                    _output = "Invalid Invite Code!"

            if _output:
                err_txt = Text(
                    self.__screen.ui_manager,
                    0.4,
                    0.3,
                    0.2,
                    0.05,
                    colours["BLACK"],
                    _output,
                )
                self.__screen.add_task("text", "output", err_txt)
                await self.delete_alert({"output": err_txt})
            else:
                code = int(code_box)
                await self.lobby_view(code)

        self.__screen.add_task(
            "buttons",
            "join_lobby",
            Button(
                self.__screen.ui_manager,
                "Join Lobby",
                colours["YELLOW"],
                colours["WHITE"],
                0.05,
                0.6,
                0.1,
                0.05,
                action=_forwarder,
            ),
        )

    async def leave_lobby(self) -> None:
        if not self.__screen.client.game_info:
            asyncio.create_task(self.__screen.client.leave_lobby())
            await self.MainUI()

    async def lobby_check_game_started(self):
        if self.__started_game_check:
            return
        self.__started_game_check = True
        while self.__screen.client.lobby and self.__screen.runner:
            if self.__screen.client.game_info:
                await self.start_game("join")
                break
            await asyncio.sleep(0)
        self.__started_game_check = False

    async def lobby_invite(self) -> None:
        self.__screen.loading = True
        user_box = self.__screen.get_task("inputboxes", "query_user")
        if not user_box:
            self.__screen.loading = False
            _inst = Text(
                self.__screen.ui_manager,
                0.15,
                0.25,
                0.2,
                0.05,
                colours["BLACK"],
                "User is required!",
            )
            self.__screen.add_task("text", "output", _inst)
            asyncio.create_task(self.delete_alert({"output": _inst}))
        else:
            user = await self.__screen.client.get_or_fetch_user(str(user_box))
            if not user:
                self.__screen.loading = False
                _inst = Text(
                    self.__screen.ui_manager,
                    0.15,
                    0.25,
                    0.2,
                    0.05,
                    colours["BLACK"],
                    f'User "{user_box}" not found!',
                )
                self.__screen.add_task("text", "output", _inst)
                asyncio.create_task(self.delete_alert({"output": _inst}))
            else:
                resp = await self.__screen.client.invite(user.username)
                self.__screen.loading = False
                if resp.get("error"):
                    _inst = Text(
                        self.__screen.ui_manager,
                        0.15,
                        0.25,
                        0.2,
                        0.05,
                        colours["BLACK"],
                        resp["message"],
                    )
                    self.__screen.add_task("text", "output", _inst)
                    asyncio.create_task(self.delete_alert({"output": _inst}))
                else:
                    _inst = Text(
                        self.__screen.ui_manager,
                        0.15,
                        0.25,
                        0.2,
                        0.05,
                        colours["BLACK"],
                        f"{user.username} has been invited",
                    )
                    self.__screen.add_task("text", "output", _inst)
                    asyncio.create_task(
                        self.delete_alert({"output": _inst}, sleep_until=10)
                    )

    async def settings_view(self) -> None:
        self.__screen.clear_tasks()
        back_btn = Button(
            self.__screen.ui_manager,
            "Lobby",
            colours["ORANGE"],
            colours["WHITE"],
            0.05,
            0.1,
            0.1,
            0.05,
            None,
            True,
            action=self.lobby_view,
        )
        self.__screen.add_task("buttons", "back", back_btn)

        settings_dict = self.__screen.client.lobby.game_settings
        if self.__screen.client.root.username == self.__screen.client.lobby.host:
            self.__screen.add_task(
                "inputboxes",
                "total_rounds",
                InputBox(
                    self.__screen.ui_manager,
                    "total_rounds",
                    0.28,
                    0.4,
                    0.05,
                    0.05,
                    text=str(settings_dict["total_rounds"]),
                    max_length=2,
                ),
            )
            self.__screen.add_task(
                "inputboxes",
                "total_duration",
                InputBox(
                    self.__screen.ui_manager,
                    "round_duration",
                    0.28,
                    0.6,
                    0.05,
                    0.05,
                    text=str(settings_dict["round_duration"]),
                    max_length=3,
                ),
            )

            async def update_game_settings():
                total_rounds_bx = self.__screen.get_task("inputboxes", "total_rounds")
                total_duration_bx = self.__screen.get_task(
                    "inputboxes", "total_duration"
                )
                output = None
                try:
                    total_rounds_val = int(total_rounds_bx)
                    total_duration_val = int(total_duration_bx)
                except ValueError:
                    output = "Settings must be integers"
                if not output:
                    if total_rounds_val > 20 or total_rounds_val < 1:
                        output = "Total Rounds must be <21 and >0"
                if not output:
                    if total_duration_val > 600 or total_duration_val < 60:
                        output = "Round Duration must be 60-600 seconds"
                if not output:
                    if (
                        total_duration_val == settings_dict["round_duration"]
                        and total_rounds_val == settings_dict["total_rounds"]
                    ):
                        output = "No change made!"
                if not output:
                    self.__screen.client.lobby.game_settings["total_rounds"] = (
                        total_rounds_val
                    )
                    self.__screen.client.lobby.game_settings["round_duration"] = (
                        total_duration_val
                    )
                    resp = await self.__screen.client.update_game_settings()
                    if resp.get("error"):
                        output = resp["message"]
                    else:
                        output = "Saved Changes!"

                txt = Text(
                    self.__screen.ui_manager,
                    0.45,
                    0.15,
                    0.1,
                    0.05,
                    colours["BLACK"],
                    output,
                )
                self.__screen.add_task("text", "output", txt)
                await self.delete_alert({"output": txt})

            self.__screen.add_task(
                "buttons",
                "submit_changes",
                Button(
                    self.__screen.ui_manager,
                    "Submit Changes",
                    colours["GREEN"],
                    colours["WHITE"],
                    0.05,
                    0.82,
                    0.15,
                    0.05,
                    action=update_game_settings,
                ),
            )
            totalroundsfmt = "Total Rounds: "
            totaldurationfmt = "Round Duration (seconds): "
        else:
            totalroundsfmt = f"Total Rounds: {settings_dict['total_rounds']}"
            totaldurationfmt = (
                f"Round Duration (seconds): {settings_dict['round_duration']}"
            )

        self.__screen.add_task(
            "text",
            "total_rounds",
            Text(
                self.__screen.ui_manager,
                0.1,
                0.4,
                0.1,
                0.05,
                colours["BLACK"],
                totalroundsfmt,
            ),
        )
        self.__screen.add_task(
            "text",
            "round_duration",
            Text(
                self.__screen.ui_manager,
                0.1,
                0.6,
                0.1,
                0.05,
                colours["BLACK"],
                totaldurationfmt,
            ),
        )

    async def reconnect_to_game(self) -> None:
        self.__screen.loading = True
        await self.start_game("join")
        self.__screen.loading = False

    async def start_game(self, _type: Literal["create", "join"]) -> None:
        self.__screen.clear_tasks()
        self.__screen.loading = True
        if _type == "create":
            resp = await self.__screen.client.create_game()
            if not isinstance(resp, GameInfo):
                self.__screen.loading = False
                _inst = Text(
                    self.__screen.ui_manager,
                    0.15,
                    0.25,
                    0.2,
                    0.05,
                    colours["BLACK"],
                    resp["message"],
                )
                self.__screen.add_task("text", "output", _inst)
                await self.delete_alert({"output": _inst})
                await self.lobby_view(None, True)
                return
        else:
            resp = self.__screen.client.game_info

        if isinstance(resp, GameInfo):
            self.__screen.loading = False
            if not self.__screen.game:
                from .game import Game

                self.__screen.game = Game(self.__screen)

    async def on_game_finish(self) -> None:
        self.__screen.game = None
        self.__screen.client.game_info = None
        self.__screen.client.game_data = None
        await self.__screen.client.recache_users()
        if self.__screen.client.lobby:
            await self.lobby_view(None, True)
        else:
            await self.MainUI()

    async def check(self) -> List | None:
        """Checks if the screen_config has been initialized"""
        if self.__screen.loading:
            return

        screen_conf = self.__screen.screen_config.get("parent", None)
        minor_conf = self.__screen.screen_config.get("minor", None)

        if not self.registered_views:
            self.register_views(screen_conf, minor_conf)
            self.registered_views = True

    def register_views(self, screen_conf: str, minor_conf: str | None) -> None:
        """Registers the initial views"""
        if screen_conf and not minor_conf:
            if screen_conf == "Launcher":
                login_button = Button(
                    self.__screen.ui_manager,
                    "Login",
                    self.__screen.colours["GREEN"],
                    self.__screen.colours["WHITE"],
                    0.1,
                    0.45,
                    0.1,
                    0.1,
                    "Login",
                    action=self.__screen.set_screen_minor,
                )
                register_button = Button(
                    self.__screen.ui_manager,
                    "Register",
                    self.__screen.colours["BLURPLE"],
                    self.__screen.colours["WHITE"],
                    0.7,
                    0.45,
                    0.1,
                    0.1,
                    "Register",
                    action=self.__screen.set_screen_minor,
                )

                self.__screen.add_task("buttons", "login", login_button)
                self.__screen.add_task("buttons", "register", register_button)
        else:
            if minor_conf == "Login":
                self.__screen.clear_tasks()
                username_bx = InputBox(
                    self.__screen.ui_manager,
                    "username",
                    0.17,
                    0.15,
                    0.1,
                    0.05,
                )
                username_txt = Text(
                    self.__screen.ui_manager,
                    0.04,
                    0.15,
                    0.1,
                    0.05,
                    self.__screen.colours["BLACK"],
                    "Username: ",
                )
                password_bx = InputBox(
                    self.__screen.ui_manager, "password", 0.17, 0.40, 0.1, 0.05
                )
                password_txt = Text(
                    self.__screen.ui_manager,
                    0.04,
                    0.40,
                    0.1,
                    0.05,
                    self.__screen.colours["BLACK"],
                    "Password: ",
                )
                forgot_btn = Button(
                    self.__screen.ui_manager,
                    "Forgot Password",
                    self.__screen.colours["RED"],
                    self.__screen.colours["WHITE"],
                    0.04,
                    0.7,
                    0.1,
                    0.05,
                    "ForgotPassword",
                    action=self.__screen.set_screen_minor,
                )
                submit_btn = Button(
                    self.__screen.ui_manager,
                    "Submit",
                    self.__screen.colours["BLURPLE"],
                    self.__screen.colours["WHITE"],
                    0.3,
                    0.7,
                    0.1,
                    0.05,
                    action=self.submit_login,
                )
                self.__screen.add_task("buttons", "submit", submit_btn)
                self.__screen.add_task("buttons", "forgot", forgot_btn)
                self.__screen.add_task("inputboxes", "username", username_bx)
                self.__screen.add_task("inputboxes", "password", password_bx)
                self.__screen.add_task("text", "username", username_txt)
                self.__screen.add_task("text", "password", password_txt)

            elif minor_conf == "Register":
                self.__screen.clear_tasks()
                # create views
                to_cr = [
                    "displayname",
                    "username",
                    "password",
                    "confirm_password",
                    "email",
                ]
                friendly = [
                    "Display name: ",
                    "Username: ",
                    "password: ",
                    "Confirm Password: ",
                    "Email: ",
                ]
                y_counter = 0
                y_inc = 0.115
                bx_x = 0.225
                txt_x = 0.075
                # We'll just map them inline
                for idx, view in enumerate(to_cr):
                    if y_counter == 0:
                        y_counter = 0.25
                    else:
                        y_counter += y_inc
                    self.__screen.add_task(
                        "inputboxes",
                        view,
                        InputBox(
                            self.__screen.ui_manager,
                            view,
                            bx_x,
                            y_counter,
                            0.1,
                            0.05,
                            max_length=30 if view == "email" else 16,
                        ),
                    )
                    self.__screen.add_task(
                        "text",
                        view,
                        Text(
                            self.__screen.ui_manager,
                            txt_x,
                            y_counter,
                            0.1,
                            0.05,
                            self.__screen.colours["BLACK"],
                            friendly[idx],
                        ),
                    )

                self.__screen.add_task(
                    "buttons",
                    "submit",
                    Button(
                        self.__screen.ui_manager,
                        "Submit",
                        self.__screen.colours["BLURPLE"],
                        self.__screen.colours["WHITE"],
                        0.38,
                        0.1,
                        0.1,
                        0.05,
                        action=self.register_step1_continue,
                    ),
                )

            elif minor_conf == "ForgotPassword":
                self.__screen.clear_tasks()
                self.__screen.add_task(
                    "inputboxes",
                    "username",
                    InputBox(
                        self.__screen.ui_manager, "username", 0.2, 0.12, 0.1, 0.05
                    ),
                )
                self.__screen.add_task(
                    "text",
                    "username",
                    Text(
                        self.__screen.ui_manager,
                        0.1,
                        0.12,
                        0.1,
                        0.05,
                        self.__screen.colours["BLACK"],
                        "Username: ",
                    ),
                )
                self.__screen.add_task(
                    "inputboxes",
                    "email",
                    InputBox(
                        self.__screen.ui_manager,
                        "email",
                        0.2,
                        0.3,
                        0.1,
                        0.05,
                        max_length=30,
                    ),
                )
                self.__screen.add_task(
                    "text",
                    "email",
                    Text(
                        self.__screen.ui_manager,
                        0.1,
                        0.3,
                        0.1,
                        0.05,
                        self.__screen.colours["BLACK"],
                        "Email: ",
                    ),
                )
                self.__screen.add_task(
                    "inputboxes",
                    "otp_code",
                    InputBox(
                        self.__screen.ui_manager,
                        "otp_code",
                        0.2,
                        0.5,
                        0.1,
                        0.05,
                        max_length=6,
                    ),
                )
                self.__screen.add_task(
                    "text",
                    "otp_code",
                    Text(
                        self.__screen.ui_manager,
                        0.1,
                        0.5,
                        0.1,
                        0.05,
                        self.__screen.colours["BLACK"],
                        "OTP Code: ",
                    ),
                )
                self.__screen.add_task(
                    "inputboxes",
                    "new_pwd",
                    InputBox(
                        self.__screen.ui_manager, "new_password", 0.55, 0.76, 0.1, 0.05
                    ),
                )
                self.__screen.add_task(
                    "text",
                    "new_pwd",
                    Text(
                        self.__screen.ui_manager,
                        0.43,
                        0.76,
                        0.1,
                        0.05,
                        self.__screen.colours["BLACK"],
                        "New Password: ",
                    ),
                )
                self.__screen.add_task(
                    "buttons",
                    "send_otp",
                    Button(
                        self.__screen.ui_manager,
                        "Send Code",
                        self.__screen.colours["BLURPLE"],
                        self.__screen.colours["BLACK"],
                        0.25,
                        0.7,
                        0.1,
                        0.1,
                        action=self.send_fpwd_code,
                    ),
                )
                self.__screen.add_task(
                    "buttons",
                    "update_pwd",
                    Button(
                        self.__screen.ui_manager,
                        "Update Password",
                        self.__screen.colours["BLURPLE"],
                        self.__screen.colours["BLACK"],
                        0.1,
                        0.7,
                        0.1,
                        0.1,
                        action=self.update_password,
                    ),
                )

    async def send_fpwd_code(self) -> None:
        """Handles the forgotten password logic for sending the OTP code"""
        username = self.__screen.get_task("inputboxes", "username")
        email = self.__screen.get_task("inputboxes", "email")
        total_feedback = {"svr": [], "em": [], "usn": []}

        if email is not None:
            length = len(email.text.lower().strip())
            if not email.text:
                total_feedback["em"].append("Email is a required field and is missing!")
            elif not 5 < length < 30:
                total_feedback["em"].append(
                    "Email length should be more than 5 and less than 30"
                )
            elif not re.fullmatch(EMAIL_RE, email.text):
                total_feedback["em"].append("Invalid Email")

        if username is not None:
            if str(username) == "":
                total_feedback["usn"].append(
                    "Username is a required field and is missing!"
                )

        # If we have no errors so far, attempt to send code
        if not any([total_feedback[k] for k in total_feedback.keys()]):
            # Check if rate limit has expired
            if (
                self.__screen.client.notifs.get("sent_fpwd_otp", {}).get(
                    "exp", datetime.datetime.now()
                )
                <= datetime.datetime.now()
            ):
                result = await self.__screen.client.send_fpwd_code(
                    str(username), str(email)
                )
                if result.get("error"):
                    total_feedback["svr"].append(result["result"]["message"])

        if any([total_feedback[k] for k in total_feedback.keys()]):
            friendly: Dict[str, str] = {
                "svr": "server",
                "em": "email",
                "usn": "username",
            }

            y_inc: int = self.dynamic(0.2, "h")
            x_inc: int = self.dynamic(0.7, "w")
            _insts: Dict[str, Text] = {}

            for field in total_feedback:
                if total_feedback[field]:
                    for idx, fb in enumerate(total_feedback[field]):
                        y_inc += 50
                        fb_txt = Text(
                            self.__screen.ui_manager,
                            x_inc / self.__screen.window.get_width(),
                            (y_inc / self.__screen.window.get_height()),
                            0.05,
                            0.05,
                            self.__screen.colours["BLACK"],
                            fb,
                        )
                        self.__screen.add_task(
                            "text", friendly[field] + f"fb_{idx}", fb_txt
                        )
                        _insts[friendly[field] + f"fb_{idx}"] = fb_txt
            asyncio.create_task(self.delete_alert(_insts, sleep_until=10))
        else:
            # Code sent successfully
            class OTPTimer(DynamicText):
                def fmt_text(self, text: str) -> str:
                    return text.format(
                        dt=self._fmt_dict["func"](
                            self._fmt_dict["dt"]
                            .get("sent_fpwd_otp", {})
                            .get("exp", datetime.datetime.now())
                        )
                    )

            dy_txt = OTPTimer(
                self.__screen.ui_manager,
                0.65,
                0.1,
                0.1,
                0.1,
                self.__screen.colours["BLACK"],
                "A One Time Password Code was sent to your email, the code will expire in {dt}",
                {"dt": self.__screen.client.notifs, "func": human_timedelta},
                size=22,
            )
            self.__screen.add_task("text", "otp_info", dy_txt)
            asyncio.create_task(self.delete_alert({"otp_info": dy_txt}))

    async def update_password(self) -> None:
        """Updates the password when a user has forgotten it."""
        username: InputBox = self.__screen.get_task("inputboxes", "username")
        email: InputBox = self.__screen.get_task("inputboxes", "email")
        otp_code: InputBox = self.__screen.get_task("inputboxes", "otp_code")
        password: InputBox = self.__screen.get_task("inputboxes", "new_password")

        total_feedback: Dict[str, List] = {
            "svr": [],
            "em": [],
            "usn": [],
            "pwd": [],
            "otp": [],
        }

        if password is not None:
            pwd_feedback: List[str] = []
            if not password.text:
                total_feedback["pwd"].append(
                    "Password is a required field and is missing!"
                )
            else:
                password_flags = [False, False, False, False, False]
                # Digit, uppercase, lowercase, ratio check, length check
                if len(password) >= 8:
                    password_flags[4] = True
                if fuzz.ratio(username.text.lower(), password.text.lower()) < 70:
                    password_flags[3] = True
                for chr_ in password:
                    if all(password_flags):
                        break
                    if chr_.isdigit():
                        password_flags[0] = True
                    if chr_.isupper():
                        password_flags[1] = True
                    if chr_.islower():
                        password_flags[2] = True
                if not all(password_flags):
                    for index, val in enumerate(password_flags):
                        if not val:
                            if index == 0:
                                pwd_feedback.append(
                                    "Password must have at least one digit!"
                                )
                            elif index == 1:
                                pwd_feedback.append(
                                    "Password must have at least one uppercase!"
                                )
                            elif index == 2:
                                pwd_feedback.append(
                                    "Password must have at least one lowercase!"
                                )
                            elif index == 3:
                                pwd_feedback.append(
                                    "Your username cannot be in your password!"
                                )
                            elif index == 4:
                                pwd_feedback.append(
                                    "Your password must be a length of 8 characters or more!"
                                )
                    total_feedback["pwd"].extend(pwd_feedback)

        if email is not None:
            length = len(email.text.lower().strip())
            if not email.text:
                total_feedback["em"].append("Email is a required field and is missing!")
            elif not 5 < length < 30:
                total_feedback["em"].append(
                    "Email length should be more than 5 and less than 30"
                )
            elif not re.fullmatch(EMAIL_RE, email.text):
                total_feedback["em"].append("Invalid Email")

        if username is not None:
            if str(username) == "":
                total_feedback["usn"].append(
                    "Username is a required field and is missing!"
                )

        if otp_code is not None:
            if not str(otp_code):
                total_feedback["otp"].append(
                    "OTP Code is a required field and is missing."
                )
            try:
                int(otp_code)
            except ValueError:
                total_feedback["otp"].append("Invalid OTP code")

        # If no errors, attempt to update password
        if not any([total_feedback[k] for k in total_feedback.keys()]):
            result = await self.__screen.client.update_password(
                str(username), str(email), str(password), int(str(otp_code))
            )
            if result.get("error"):
                total_feedback["svr"].append(result["result"]["message"])

        if any([total_feedback[k] for k in total_feedback.keys()]):
            friendly: Dict[str, str] = {
                "svr": "server",
                "em": "email",
                "usn": "username",
                "pwd": "password",
                "otp": "otp",
            }

            y_inc: int = self.dynamic(0.2, "h")
            x_inc: int = self.dynamic(0.7, "w")

            _insts: Dict[str, Text] = {}

            for field in total_feedback:
                if total_feedback[field]:
                    for idx, fb in enumerate(total_feedback[field]):
                        y_inc += 50
                        fb_txt = Text(
                            self.__screen.ui_manager,
                            x_inc / self.__screen.window.get_width(),
                            (y_inc / self.__screen.window.get_height()),
                            0.05,
                            0.05,
                            self.__screen.colours["BLACK"],
                            fb,
                        )
                        self.__screen.add_task(
                            "text", friendly[field] + f"fb_{idx}", fb_txt
                        )
                        _insts[friendly[field] + f"fb_{idx}"] = fb_txt

            asyncio.create_task(self.delete_alert(_insts, sleep_until=10))
        else:
            self.__screen.add_task(
                "text",
                "success",
                Text(
                    self.__screen.ui_manager,
                    0.5,
                    0.6,
                    0.1,
                    0.05,
                    self.__screen.colours["BLACK"],
                    "You have updated your account successfully"
                    ", you will be returned to the main menu shortly",
                ),
            )
            await asyncio.sleep(3)
            self.__data = {}
            self.__screen.clear_tasks()
            self.__screen.set_screen_minor(None)
            self.registered_views = False

    async def MainUI(self) -> None:
        """Places the logged-in user into the main UI."""
        self.__screen.clear_tasks()
        res = await self.__screen.client.root_in_game()

        friends_btn = Button(
            self.__screen.ui_manager,
            "Friends",
            self.__screen.colours["BLURPLE"],
            self.__screen.colours["WHITE"],
            0.2,
            0.15,
            0.1,
            0.05,
            action=self.friends_view,
        )
        self.__screen.add_task("buttons", "friends", friends_btn)

        reconnect_btn = Button(
            self.__screen.ui_manager,
            "Reconnect To Game",
            self.__screen.colours["RED"],
            self.__screen.colours["WHITE"],
            0.4,
            0.15,
            0.1,
            0.05,
            disabled=True,
            action=self.reconnect_to_game,
        )
        self.__screen.add_task("buttons", "reconnect", reconnect_btn)

        if res:
            reconnect_btn.disabled = False
        else:
            join_lobby_btn = Button(
                self.__screen.ui_manager,
                "Join Lobby",
                self.__screen.colours["YELLOW"],
                self.__screen.colours["WHITE"],
                0.2,
                0.45,
                0.1,
                0.05,
                action=self.join_lobby,
            )
            self.__screen.add_task("buttons", "join_lobby", join_lobby_btn)

            create_lobby_btn = Button(
                self.__screen.ui_manager,
                "Create Lobby",
                self.__screen.colours["PURPLE"],
                self.__screen.colours["WHITE"],
                0.4,
                0.45,
                0.1,
                0.05,
                action=self.lobby_view,
            )
            self.__screen.add_task("buttons", "create_lobby", create_lobby_btn)

    async def lobby_view(
        self, invite_code: Optional[int] = None, redirect: bool = False
    ) -> None:
        """Manages the lobby UI.
        - If invite_code is provided, tries to join that lobby; if not provided, creates a lobby.
        - If redirect is True, it means the user is already in a lobby and we just refresh the UI.
        - Shows UI elements for starting game, settings, friends, profile, leaving, inviting, and team selection.
        """

        self.__screen.clear_tasks()
        lobby = self.__screen.client.lobby

        if not redirect:
            if not invite_code:
                resp = await self.__screen.client.create_lobby()
            else:
                resp = await self.__screen.client.join_lobby(invite_code)

            if resp.get("error"):
                # Show error message and return to MainUI
                _inst = Text(
                    self.__screen.ui_manager,
                    0.4,
                    0.25,
                    0.1,
                    0.05,
                    self.__screen.colours["BLACK"],
                    resp["message"],
                )
                self.__screen.add_task("text", "output", _inst)
                await asyncio.sleep(1)
                await self.MainUI()
                return
            else:
                # Convert player timestamps to datetime
                resp["lobby"]["players"] = {
                    k: datetime.datetime.fromtimestamp(v)
                    for k, v in resp["lobby"]["players"].items()
                }
                lobby = Lobby(resp["lobby_id"], **resp["lobby"])
                self.__screen.client.lobby = lobby

        if lobby:
            # Add UI Elements for Lobby
            start = Button(
                self.__screen.ui_manager,
                "Start",
                self.__screen.colours["GREEN"],
                self.__screen.colours["WHITE"],
                0,
                0.05,
                0.1,
                0.05,
                "create",
                disabled=True,
                action=self.start_game,
            )
            if lobby.host == self.__screen.client.root.username:
                start.disabled = False
            self.__screen.add_task("buttons", "start", start)

            settings = Button(
                self.__screen.ui_manager,
                "settings",
                self.__screen.colours["PUCE"],
                self.__screen.colours["WHITE"],
                0.1,
                0.05,
                0.1,
                0.05,
                action=self.settings_view,
            )
            self.__screen.add_task("buttons", "settings", settings)

            friends = Button(
                self.__screen.ui_manager,
                "friends",
                self.__screen.colours["FAWN"],
                self.__screen.colours["WHITE"],
                0.2,
                0.05,
                0.1,
                0.05,
                ["Lobby", self.lobby_view, [None, True]],
                action=self.friends_view,
            )
            self.__screen.add_task("buttons", "friends", friends)

            profile = Button(
                self.__screen.ui_manager,
                "profile",
                self.__screen.colours["JADE"],
                self.__screen.colours["WHITE"],
                0.3,
                0.05,
                0.1,
                0.05,
                True,
                action=self.view_profile,
            )
            self.__screen.add_task("buttons", "profile", profile)

            leave = Button(
                self.__screen.ui_manager,
                "leave",
                self.__screen.colours["PURPLE"],
                self.__screen.colours["WHITE"],
                0.4,
                0.05,
                0.1,
                0.05,
                action=self.leave_lobby,
            )
            self.__screen.add_task("buttons", "leave", leave)

            invite = Button(
                self.__screen.ui_manager,
                "invite",
                self.__screen.colours["BLURPLE"],
                self.__screen.colours["WHITE"],
                0.5,
                0.05,
                0.1,
                0.05,
                action=self.lobby_invite,
            )
            self.__screen.add_task("buttons", "invite", invite)

            search = Text(
                self.__screen.ui_manager,
                0.61,
                0.018,
                0.1,
                0.05,
                self.__screen.colours["BLACK"],
                "search: ",
                size=24,
            )
            self.__screen.add_task("text", "search", search)

            prompt = InputBox(
                self.__screen.ui_manager, "query_user", 0.6, 0.05, 0.1, 0.05
            )
            self.__screen.add_task("inputboxes", "query_user", prompt)

            display_code = Text(
                self.__screen.ui_manager,
                0.8,
                0.001,
                0.1,
                0.05,
                self.__screen.colours["BLACK"],
                f"Invite Code: {lobby.invite_code:,}",
            )
            self.__screen.add_task("text", "display_code", display_code)

            # Team display logic
            def output_team(start_w: float, start_h: float, team: List[str]):
                x_inc = self.__screen.handler.dynamic(start_w, "w")
                y_inc = self.__screen.handler.dynamic(start_h, "h")
                for _, ln in enumerate(team):
                    line_text = ln
                    if ln == lobby.host:
                        line_text = "[HOST] " + ln
                    y_inc += 50
                    ln_txt = Text(
                        self.__screen.ui_manager,
                        x_inc / self.__screen.window.get_width(),
                        y_inc / self.__screen.window.get_height(),
                        0.05,
                        0.05,
                        self.__screen.colours["BLACK"],
                        line_text,
                        size=22,
                    )
                    self.__screen.add_task("text", f"team_out_{line_text}", ln_txt)

            async def join_red() -> None:
                if len(lobby.red_team) < 5:
                    await self.__screen.client.join_team("red")

            async def join_switcher() -> None:
                if len(lobby.switcher) < 5:
                    await self.__screen.client.join_team("switcher")

            async def join_blue() -> None:
                if len(lobby.blue_team) < 5:
                    await self.__screen.client.join_team("blue")

            def show_teams():
                # Remove old team outputs
                for t_key in self.__screen.get_tasks("text").copy():
                    if t_key.startswith("team_out_"):
                        self.__screen.remove_task("text", t_key)

                output_team(0.515, 0.32, lobby.red_team)
                output_team(0.69, 0.32, lobby.switcher)
                output_team(0.865, 0.32, lobby.blue_team)

                # Headers for teams
                if not self.__screen.get_task("text", "red_header"):
                    red_header = Text(
                        self.__screen.ui_manager,
                        0.5,
                        0.27,
                        0.1,
                        0.05,
                        self.__screen.colours["RED"],
                        "RED TEAM",
                    )
                    self.__screen.add_task("text", "red_header", red_header)

                if not self.__screen.get_task("text", "slider_header"):
                    slider_header = Text(
                        self.__screen.ui_manager,
                        0.675,
                        0.27,
                        0.1,
                        0.05,
                        self.__screen.colours["BLACK"],
                        "SWITCHER",
                    )
                    self.__screen.add_task("text", "slider_header", slider_header)

                if not self.__screen.get_task("text", "blue_header"):
                    blue_header = Text(
                        self.__screen.ui_manager,
                        0.85,
                        0.27,
                        0.1,
                        0.05,
                        self.__screen.colours["BLURPLE"],
                        "BLUE TEAM",
                    )
                    self.__screen.add_task("text", "blue_header", blue_header)

                # Join team buttons if not present
                if not self.__screen.get_task("buttons", "join_red"):
                    join_red_btn = Button(
                        self.__screen.ui_manager,
                        "RED",
                        self.__screen.colours["RED"],
                        self.__screen.colours["WHITE"],
                        0.5,
                        0.82,
                        0.1,
                        0.05,
                        action=join_red,
                    )
                    self.__screen.add_task("buttons", "join_red", join_red_btn)

                    join_switcher_btn = Button(
                        self.__screen.ui_manager,
                        "SWITCHER",
                        self.__screen.colours["PUCE"],
                        self.__screen.colours["WHITE"],
                        0.675,
                        0.82,
                        0.1,
                        0.05,
                        action=join_switcher,
                    )
                    self.__screen.add_task(
                        "buttons", "join_switcher", join_switcher_btn
                    )

                    join_blue_btn = Button(
                        self.__screen.ui_manager,
                        "BLUE",
                        self.__screen.colours["BLURPLE"],
                        self.__screen.colours["WHITE"],
                        0.85,
                        0.82,
                        0.1,
                        0.05,
                        action=join_blue,
                    )
                    self.__screen.add_task("buttons", "join_blue", join_blue_btn)

            self.__screen.add_task("functions", "show_teams", [show_teams])
            # Check if game started
            asyncio.create_task(self.lobby_check_game_started())
