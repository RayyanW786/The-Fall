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
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from json import dumps, loads
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional

import websockets
from pygame import display

from Game.utils import encrypt, generate_snowflake

if TYPE_CHECKING:
    from logging import Logger

    from websockets.asyncio.client import ClientConnection

    from launcher.launcher import Launcher

    from ..Screen.game import ServerCharacter


@dataclass
class User:
    """User's that are not Root"""

    username: str
    displayname: str
    hours_played: int
    games_played: int
    games_won: int
    total_kills: int
    total_deaths: int
    friends: List[str]
    kd: float


@dataclass
class Root:
    """The logged-in User"""

    username: str
    displayname: str
    authentication: str
    email: str
    last_game_id: str
    hours_played: float
    games_played: int
    games_won: int
    total_kills: int
    total_deaths: int
    friends: list[str]
    kd: float


@dataclass
class Lobby:
    """Represents the lobby data"""

    lobby_id: str
    host: str
    red_team: List[str]
    blue_team: List[str]
    switcher: List[str]
    players: Dict[str, datetime]
    invite_code: int
    game_settings: Dict
    game_starting_at: Optional[datetime] = None


@dataclass
class GameInfo:
    """Represents the data required to start a game"""

    game_id: str
    host: str
    round: int
    total_rounds: int
    round_length: int
    round_starts_at: datetime
    round_end_at: datetime
    red_team: List[str]
    blue_team: List[str]
    players: Dict[str, Dict]
    stats: Dict[str, Any]


@dataclass
class GameData:
    """Represents data that is required within a game"""

    to_send: Dict[str, Any] = field(
        default_factory=lambda: {"bullets": {}, "character": {}}
    )
    from_server: Dict[str, Any] = field(
        default_factory=lambda: {
            "bullets": {},
            "characters": {},
            "metadata": {},
            "next_check": False,
        }
    )


CONNECT_PATH: str = "ws://localhost:50000"


class Client:
    """Handles all the client networking side"""

    def __init__(self, launcher: Launcher):
        self.__launcher: Launcher = launcher
        self.__websocket: Optional[ClientConnection] = None
        self.__data: Dict = {}  # data from the websocket
        self.__notif_data: Dict = {}  # data sent from server marked as a notification / event
        self.__result_available: Dict = {}
        self.__user_cache: List[User] = []
        self.__root: Optional[Root] = None
        self.__reconnect_attempts: List[int | datetime] = [0, datetime.now(), 0]
        self.__Lobby: Optional[Lobby] = None
        self.__GameInfo: Optional[GameInfo] = None
        self.__GameData: Optional[GameData] = None
        self.__logger: Logger = self.__launcher.logger

    @property
    def ws(self) -> Optional[ClientConnection]:
        return self.__websocket

    @property
    def notifs(self) -> Dict:
        return self.__notif_data

    @property
    def root(self) -> Optional[Root]:
        return self.__root

    @property
    def game_data(self) -> GameData:
        return self.__GameData

    @game_data.setter
    def game_data(self, payload: GameData) -> None:
        self.__GameData = payload

    @property
    def game_info(self) -> GameInfo:
        return self.__GameInfo

    @game_info.setter
    def game_info(self, payload: GameInfo) -> None:
        self.__GameInfo = payload

    @property
    def lobby(self) -> Lobby:
        return self.__Lobby

    @lobby.setter
    def lobby(self, payload: Optional[Lobby]) -> None:
        self.__Lobby = payload

    async def recache_users(self) -> None:
        """Replaces self.__user_cache with freshly fetched users"""
        new = []
        for user in self.__user_cache:
            new_user = await self.fetch_user(user.username)
            if new_user:
                new.append(new_user)
        self.__user_cache = new

    async def run(self, websocket: ClientConnection) -> None:
        """Runs the client"""
        self.__websocket: ClientConnection = websocket
        print(199, type(self.__websocket))
        await asyncio.gather(
            self.send_heartbeat(),
            self.recv_from_server(),
        )

    async def send_heartbeat(self) -> None:
        """This sends heartbeats to the server so that the websocket does not time out."""
        try:
            while self.__launcher.runner:
                await asyncio.sleep(15)
                await self.__websocket.send(
                    dumps({"command": "HEARTBEAT", "id": 0}).encode()
                )
        except websockets.ConnectionClosedError as e:
            self.__logger.error(f"WebSocket connection closed unexpectedly: {e}")
        except Exception as e:
            self.__logger.error(f"Error in send_heartbeat: {e}")

    async def recv_game(self, data: Dict) -> None:
        """All game data from the server is sent to this function"""
        if not self.__launcher.game:
            return
        payload = data["data"]
        event = data["event"]
        if event == "next_check":
            self.GameData.from_server["metadata"] = payload["metadata"]
            self.GameData.from_server["next_check"] = True

        elif event == "bullet":
            self.__launcher.game.create_bullet(payload)

        elif event == "character":
            name = data["owner"]
            if name in self.__launcher.game.lookup_table:
                character: ServerCharacter = self.__launcher.game.lookup_table[name][2]
                character.update(payload["X"], payload["Y"])

    async def send_game(self) -> None:
        while self.__launcher.game and self.__launcher.runner:
            if self.GameData.to_send["bullets"]:
                for bullet in self.GameData.to_send["bullets"].copy():
                    await self.request(
                        command="bullet_fired",
                        data=self.GameData.to_send["bullets"][bullet],
                        game_id=self.__GameInfo.game_id,
                        root=self.__root.username,
                        authentication=self.__root.authentication,
                    )
                    del self.GameData.to_send["bullets"][bullet]
            if self.GameData.to_send["character"]:
                await self.request(
                    command="broadcast_self",
                    data=self.GameData.to_send["character"],
                    game_id=self.__GameInfo.game_id,
                    root=self.__root.username,
                    authentication=self.__root.authentication,
                )
                self.GameData.to_send["character"] = {}

            await asyncio.sleep(0)

    async def recv_from_server(self) -> None:
        """Handles / Redirects all the data from the servers"""
        self.__logger.info(f"CONNECTED {self.__websocket}")
        try:
            async for data in self.__websocket:
                if isinstance(data, str):
                    data: str = data.decode()

                if not data:
                    continue

                command_list = data.split("#")
                for command in command_list:
                    if command == "":
                        continue

                    data: dict = loads(command)
                    _id = data.get("id", None)
                    if _id == 0:
                        # ON CONNECT OR HEARTBEAT.
                        continue

                    elif _id == -1:
                        # error commands
                        if data.get("error") == "ratelimit":
                            self.__notif_data["ratelimit"] = {
                                "message": data["message"],
                                "dt": data["dt"],
                            }

                    elif _id == -2:
                        # notifying commands (server wants to make the client aware of something)
                        if data.get("notify") == "sent_register_otp":
                            self.__notif_data["register_s2"] = {
                                "exp": datetime.fromtimestamp(data.get("exp"))
                            }

                        elif data.get("notify") == "sent_fpwd_otp":
                            self.__notif_data["sent_fpwd_otp"] = {
                                "exp": datetime.fromtimestamp(data.get("exp"))
                            }

                        elif data.get("notify") == "on_friends_update":
                            if data["event"] == "added":
                                self.root.friends.append(data["friend"])
                            elif data["event"] == "removed":
                                if data["friend"] in self.root.friends:
                                    self.root.friends.remove(data["friend"])

                        elif data.get("notify") == "on_lobby_update" and self.__Lobby:
                            event = data["event"]
                            if event == "join":
                                member = data["member"]
                                self.__Lobby.switcher.append(member)
                            elif event == "leave":
                                lobby_data = data["lobby"]
                                for attr in lobby_data:
                                    self.__Lobby.__setattr__(attr, lobby_data[attr])
                            elif event == "team_update":
                                lobby = self.__Lobby
                                member = data["member"]
                                team = data["team"]
                                if member in lobby.switcher:
                                    lobby.switcher.remove(member)
                                elif member in lobby.blue_team:
                                    lobby.blue_team.remove(member)
                                elif member in lobby.red_team:
                                    lobby.red_team.remove(member)

                                if team == "red":
                                    lobby.red_team.append(member)
                                elif team == "blue":
                                    lobby.blue_team.append(member)
                                else:
                                    lobby.switcher.append(member)

                            elif event == "settings_update":
                                lobby = self.__Lobby
                                payload = data["settings_dict"]
                                lobby.game_settings = payload

                            elif event == "on_game_start":
                                self.__Lobby.game_starting_at = datetime.fromtimestamp(
                                    data["when"]
                                )

                        elif data.get("notify") == "on_game_update":
                            await self.recv_game(data)

                        elif data.get("notify") == "game_started":
                            for player in data["game_info"]["players"]:
                                dt = data["game_info"]["players"][player]["joined"]
                                data["game_info"]["players"][player]["joined"] = (
                                    datetime.fromtimestamp(dt)
                                )

                            data["game_info"]["round_starts_at"] = (
                                datetime.fromtimestamp(
                                    data["game_info"]["round_starts_at"]
                                )
                            )
                            data["game_info"]["round_end_at"] = datetime.fromtimestamp(
                                data["game_info"]["round_end_at"]
                            )
                            game_info = GameInfo(data["game_id"], **data["game_info"])
                            self.__GameInfo = game_info
                            self.GameData = GameData()

                    elif data.get("return", "") == "userdata":
                        self.__data[_id] = {
                            "result": data["result"],
                            "ret_type": data["ret_type"],
                        }
                        if _id in self.__result_available:
                            self.__result_available[_id].set()

                    elif data.get("return", "") in [
                        "login",
                        "register",
                        "sent_fpwd_code",
                        "updated_password",
                        "added_friend",
                        "removed_friend",
                        "outbound_requests",
                        "inbound_requests",
                        "invites",
                        "created_lobby",
                        "joined_lobby",
                        "invited",
                        "team_joined",
                        "left_lobby",
                        "updated_game_settings",
                        "created_game",
                        "root_in_game",
                    ]:
                        self.__data[_id] = data
                        if _id in self.__result_available:
                            self.__result_available[_id].set()

        except websockets.ConnectionClosedError as e:
            self.__logger.warning(f"WebSocket connection closed unexpectedly: {e}")
            await self.reconnect_and_recv()

    async def reconnect_and_recv(self) -> None:
        """Attempts to reconnect to the server 5 times in case of a disconnect"""
        self.__logger.warning("retrying....")
        try:
            if self.__reconnect_attempts[0] >= 5:
                raise ConnectionAbortedError
            elif self.__reconnect_attempts[1] <= datetime.now():
                self.__reconnect_attempts[0] = 0
                self.__reconnect_attempts[1] = datetime.now() + timedelta(minutes=5)
                self.__reconnect_attempts[2] = 0
            self.__reconnect_attempts[0] += 1

            self.__logger.warning(
                f"Reconnecting to the server...\nAttempt {self.__reconnect_attempts[0]} / 5"
            )

            if self.__websocket and self.__websocket.open:
                await self.__websocket.close()

            self.__websocket = await websockets.connect(CONNECT_PATH)

            asyncio.create_task(self.recv_from_server())

            self.__logger.info(
                f"Reconnected successfully on attempt {self.__reconnect_attempts[0]}"
            )
            self.__reconnect_attempts[0] = 0
        except Exception as e:
            if self.__reconnect_attempts[0] < 5:
                self.__reconnect_attempts[2] += 10
                self.__logger.warning(
                    f"Error reconnecting to the server: retrying in {self.__reconnect_attempts[2]} seconds."
                )
                await asyncio.sleep(self.__reconnect_attempts[2])
                asyncio.create_task(self.reconnect_and_recv())
            else:
                self.__logger.error(f"Error reconnecting to the server: {e}.Attempt(s) {self.__reconnect_attempts[0]} / 5  made! \
                \nexiting...")

    async def request(self, *, command, gen_id: bool = True, **kwargs) -> str:
        """Sends a command with kwargs to the websocket with a snowflake id"""
        try:
            _id = generate_snowflake() if gen_id else None
            data = {"command": command, "kwargs": kwargs, "id": _id}
            await self.__websocket.send(dumps(data).encode())
            return _id
        except websockets.ConnectionClosedError:
            return ""

    async def handle_request(
        self, _id: str, *, ret: Any, timeout: int = 1, success: bool = None
    ) -> Any:
        """
        handles requests made to the server
        _id: str -> the id from calling request
        ret: Any -> what should be returned on timeout or invalid id
        timeout: int ->  the maximum time the client should wait for a response from the server [default = 1]
        return: Any
        """

        if not _id:
            return ret

        if _id not in self.__result_available:
            self.__result_available[_id] = asyncio.Event()

        try:
            await asyncio.wait_for(self.__result_available[_id].wait(), timeout=timeout)
        except asyncio.TimeoutError:
            return ret

        return success

    @staticmethod
    def extract_user_data(data: Dict) -> Dict:
        """Formats the user data to match the User dataclass"""
        if data["friends"]:
            data["friends"] = data["friends"].split(", ")
        else:
            data["friends"] = []
        data["hours_played"] = round(data.pop("total_minutes") / 60, 1)
        data["games_played"] = data.pop("games_played")
        try:
            data["kd"] = round(data["total_kills"] / data["total_deaths"], 2)
        except ZeroDivisionError:
            data["kd"] = 0
        return data

    def get_user(self, username: str) -> Optional[User]:
        """Gets a user from cache state"""

        def check(u: User):
            return u.username == username

        try:
            return next(
                filter(check, self.__user_cache)
            )  # without calling next, a filter object is returned
        except StopIteration:
            return None

    async def fetch_user(self, username: str) -> Optional[User]:
        """Makes a call to the server to get a user.
        :returns:  Optional[User]
        """
        _id = await self.request(command="get_user", username=username, ret_type="dict")
        ret = None
        handle_res = await self.handle_request(_id, ret=ret, success=True)
        if handle_res is ret:
            return handle_res

        result = self.__data.get(_id, None)
        if result["ret_type"] == "NoneType":
            return  # User does not exist

        result = self.extract_user_data(result["result"])
        user = User(**result)
        if user not in self.__user_cache:
            self.__user_cache.append(user)
        return user

    async def get_or_fetch_user(self, username: str) -> Optional[User]:
        """Gets the user from cache state if exists else fetches the user"""
        res = self.get_user(username)
        if not res:
            return await self.fetch_user(username)
        return res

    async def username_lookup(self, username: str, **kwargs) -> bool:
        """Checks if a username exists
        KWARGS:
            use_cache: bool = True -> to check client cache before making a call to the server
        :returns: True if user does exist, False if User not found.
        """

        try:
            use_cache = kwargs.pop("use_cache")
        except KeyError:
            use_cache = True

        if use_cache and username in [u.username for u in self.__user_cache]:
            return True

        result = await self.get_or_fetch_user(username)
        if not result:
            return False
        return True

    async def login(self, username: str, password: str) -> Literal[False] | Root:
        """This function logins in a User

        Root -> successful login
        False -> Failure when  in
        :returns: Literal[False] | Root

        """

        if self.__root:
            return self.__root
        password = encrypt(password)

        _id = await self.request(command="login", username=username, password=password)
        ret = False
        handle_res = await self.handle_request(_id, ret=ret)
        if handle_res is ret:
            return handle_res

        data = self.__data.get(_id)["result"]
        if not data["status"]:
            return False
        result = self.extract_user_data(data["data"])
        root = Root(**result, authentication=data["authentication"])
        self.__root = root
        display.set_caption(f"The Fall: Logged in @ {self.__root.username}")
        return root

    async def register(
        self,
        displayname: str,
        username: str,
        email: str,
        password: str,
        otp: Optional[int] = None,
    ) -> False | str | dict | Root:
        """Called when registering in a user"""

        password = encrypt(password)
        _id = await self.request(
            command="register",
            displayname=displayname,
            username=username,
            email=email,
            password=password,
            otp=otp,
        )
        ret = False
        handle_res = await self.handle_request(_id, ret=ret)
        if handle_res is ret:
            return handle_res

        data = self.__data.get(_id)
        if data["result"] == "sent_register_otp":
            return data
        else:
            error = data.get("error")
            if error:
                return data["result"]
            else:
                if not data["result"].get("status", False):
                    return False
                else:
                    result = self.extract_user_data(data["result"]["data"])
                    root = Root(
                        **result, authentication=data["result"]["authentication"]
                    )
                    self.__root = root
                    display.set_caption(f"The Fall: Logged in @ {self.__root.username}")
                    return root

    async def root_in_game(self) -> bool:
        """
        Checks if root users last_game_id is still a running game
        if it is then the user is prompted to reconnect to the game and cannot join / create other lobbies
        """

        if not self.root or (self.root and self.root.last_game_id == 0):
            return False
        else:
            _id = await self.request(
                command="game_is_running",
                notify_on_finish=True,
                authentication=self.root.authentication,
            )
            ret = False
            handle_res = await self.handle_request(_id, ret=ret)
            if handle_res is ret:
                return handle_res
            result = self.__data[_id]
            return result["status"]

    async def send_fpwd_code(self, username: str, email: str) -> Dict:
        """asks the server to send a forgotten password OTP code for the specified username and email"""
        _id = await self.request(
            command="send_fpwd_code", **{"username": username, "email": email}
        )
        ret = {
            "error": True,
            "result": {"message": "Could not establish a connection to game server."},
        }
        handle_res = await self.handle_request(_id, ret=ret)
        if handle_res is ret:
            return handle_res

        result = self.__data[_id]
        return result

    async def update_password(
        self, username: str, email: str, new_password: str, otp_code: str
    ) -> Dict:
        """Updates the password for a user who has forgotten it and provided the valid OTP code"""
        _id = await self.request(
            command="update_password",
            **{
                "username": username,
                "email": email,
                "password": encrypt(new_password),
                "otp_code": otp_code,
            },
        )
        if not _id:
            return {
                "error": True,
                "result": {
                    "message": "Could not establish a connection to game server."
                },
            }

        if _id not in self.__result_available:
            self.__result_available[_id] = asyncio.Event()

        try:
            await asyncio.wait_for(self.__result_available[_id].wait(), timeout=1)
        except asyncio.TimeoutError:
            return {
                "error": True,
                "result": {
                    "message": "Could not establish a connection to game server."
                },
            }

        result = self.__data[_id]
        return result

    async def add_friend(self, to_user: User) -> Dict:
        """Allows a user to accept / send a friend request"""
        if not self.root:
            return {"error": "authorisation", "message": "Invalid Token"}
        else:
            _id = await self.request(
                command="add_friend",
                **{
                    "from_user": self.root.username,
                    "authentication": self.root.authentication,
                    "to_user": to_user.username,
                },
            )
            ret = {
                "error": True,
                "message": "Could not establish a connection to game server.",
            }
            handle_res = await self.handle_request(_id, ret=ret)
            if handle_res is ret:
                return handle_res
            data = self.__data[_id]["result"]
            if data.get("result") == "accepted":
                self.root.friends.append(data["with"])
            return data

    async def remove_friend(self, with_user: User) -> Dict:
        """Allows a user to remove a friend / deny a friend request"""
        if not self.root:
            return {"error": "authorisation", "message": "Invalid Token"}
        else:
            _id = await self.request(
                command="remove_friend",
                **{
                    "from_user": self.root.username,
                    "authentication": self.root.authentication,
                    "with_user": with_user.username,
                },
            )
            ret = {
                "error": True,
                "message": "Could not establish a connection to game server.",
            }
            handle_res = await self.handle_request(_id, ret=ret)
            if handle_res is ret:
                return handle_res
            data = self.__data[_id]["result"]
            if data.get("result") == "removed":
                if data["with"] in self.__root.friends:
                    self.root.friends.remove(data["with"])
            return data

    async def get_outbound_requests(self) -> Dict:
        """Shows all friend requests send by the user"""
        if not self.root:
            return {"error": "authorisation", "message": "Invalid Token"}
        else:
            _id = await self.request(
                command="get_outbound_requests",
                **{
                    "root": self.root.username,
                    "authentication": self.root.authentication,
                },
            )
            ret = {
                "error": True,
                "message": "Could not establish a connection to game server.",
            }
            handle_res = await self.handle_request(_id, ret=ret)
            if handle_res is ret:
                return handle_res

            return self.__data[_id]["result"]

    async def get_inbound_requests(self) -> Dict:
        """Shows all friend requests sent to the user"""
        if not self.root:
            return {"error": "authorisation", "message": "Invalid Token"}
        else:
            _id = await self.request(
                command="get_inbound_requests",
                **{
                    "root": self.root.username,
                    "authentication": self.root.authentication,
                },
            )
            ret = {
                "error": True,
                "message": "Could not establish a connection to game server.",
            }
            handle_res = await self.handle_request(_id, ret=ret)
            if handle_res is ret:
                return handle_res

            return self.__data[_id]["result"]

    async def get_invites(self) -> Dict:
        """Provides all the lobby invites sent to the user"""
        if not self.root:
            return {"error": "authorisation", "message": "Invalid Token"}
        else:
            _id = await self.request(
                command="get_invites",
                **{
                    "root": self.root.username,
                    "authentication": self.root.authentication,
                },
            )
            ret = {
                "error": True,
                "message": "Could not establish a connection to game server.",
            }
            handle_res = await self.handle_request(_id, ret=ret)
            if handle_res is ret:
                return handle_res

            return self.__data[_id]["result"]

    async def create_game(self) -> Dict | GameInfo:
        """Games a game"""
        if not self.root or not self.__Lobby:
            return {"error": "authorisation", "message": "Invalid Token"}
        else:
            _id = await self.request(
                command="create_game",
                **{
                    "root": self.root.username,
                    "authentication": self.root.authentication,
                    "lobby_id": self.__Lobby.lobby_id,
                },
            )
            ret = {
                "error": True,
                "message": "Could not establish a connection to game server.",
            }
            handle_res = await self.handle_request(_id, ret=ret)
            if handle_res is ret:
                return handle_res

            result = self.__data[_id]["result"]
            if result.get("error"):
                return result

            for player in result["game_info"]["players"]:
                dt = result["game_info"]["players"][player]["joined"]
                result["game_info"]["players"][player]["joined"] = (
                    datetime.fromtimestamp(dt)
                )

            result["game_info"]["round_starts_at"] = datetime.fromtimestamp(
                result["game_info"]["round_starts_at"]
            )
            result["game_info"]["round_end_at"] = datetime.fromtimestamp(
                result["game_info"]["round_end_at"]
            )

            game_info = GameInfo(result["game_id"], **result["game_info"])
            self.__GameInfo = game_info
            self.GameData = GameData()
            return game_info

    async def create_lobby(self) -> Dict:
        """Creates a lobby"""
        if not self.root:
            return {"error": "authorisation", "message": "Invalid Token"}
        else:
            _id = await self.request(
                command="create_lobby",
                **{
                    "root": self.root.username,
                    "authentication": self.root.authentication,
                },
            )
            ret = {
                "error": True,
                "message": "Could not establish a connection to game server.",
            }
            handle_res = await self.handle_request(_id, ret=ret)
            if handle_res is ret:
                return handle_res

            return self.__data[_id]["result"]

    async def join_lobby(self, invite_code: int) -> Dict:
        """Allows the user to join a valid lobby"""
        if not self.root:
            return {"error": "authorisation", "message": "Invalid Token"}
        else:
            _id = await self.request(
                command="join_lobby",
                **{
                    "root": self.root.username,
                    "authentication": self.root.authentication,
                    "invite_code": invite_code,
                },
            )
            ret = {
                "error": True,
                "message": "Could not establish a connection to game server.",
            }
            handle_res = await self.handle_request(_id, ret=ret)
            if handle_res is ret:
                return handle_res

            return self.__data[_id]["result"]

    async def leave_lobby(self) -> Optional[Dict]:
        """Allows the user to leave a lobby"""
        assert self.__Lobby is not None
        _id = await self.request(
            command="leave_lobby",
            **{
                "root": self.root.username,
                "authentication": self.root.authentication,
                "lobby_id": self.__Lobby.lobby_id,
            },
        )
        ret = {
            "error": True,
            "message": "Could not establish a connection to game server.",
        }
        handle_res = await self.handle_request(_id, ret=ret)
        if handle_res is ret:
            return handle_res

        self.__Lobby = None

    async def invite(self, user: str) -> Dict:
        """Allows a user to invite another to a lobby"""
        assert self.__Lobby is not None
        _id = await self.request(
            command="invite",
            **{
                "root": self.root.username,
                "authentication": self.root.authentication,
                "lobby_id": self.__Lobby.lobby_id,
                "user": user,
            },
        )
        ret = {
            "error": True,
            "message": "Could not establish a connection to game server.",
        }
        handle_res = await self.handle_request(_id, ret=ret)
        if handle_res is ret:
            return handle_res

        return self.__data[_id]["result"]

    async def join_team(self, team: Literal["red", "switcher", "blue"]) -> None:
        """Allows users to switch teams within the lobby and broadcasts the change to other clients"""
        assert self.__Lobby is not None
        lobby = self.__Lobby
        _id = await self.request(
            command="join_team",
            **{
                "root": self.root.username,
                "authentication": self.root.authentication,
                "lobby_id": self.__Lobby.lobby_id,
                "team": team,
            },
        )
        handle = await self.handle_request(_id, ret=False)
        if handle is not False:
            if self.__data[_id]["result"]["status"]:
                me = self.__root.username
                if me in lobby.switcher:
                    lobby.switcher.remove(me)
                elif me in lobby.blue_team:
                    lobby.blue_team.remove(me)
                elif me in lobby.red_team:
                    lobby.red_team.remove(me)

                if team == "red":
                    lobby.red_team.append(me)
                elif team == "blue":
                    lobby.blue_team.append(me)
                else:
                    lobby.switcher.append(me)

    async def update_game_settings(self) -> Dict:
        """Allows the host to change the game settings and broadcast the changes to other players present"""
        assert self.__Lobby is not None
        _id = await self.request(
            command="update_game_settings",
            **{
                "root": self.root.username,
                "authentication": self.root.authentication,
                "lobby_id": self.__Lobby.lobby_id,
                "settings_dict": self.__Lobby.game_settings,
            },
        )
        ret = {
            "error": True,
            "message": "Could not establish a connection to game server.",
        }
        handle_res = await self.handle_request(_id, ret=ret)
        if handle_res is ret:
            return handle_res

        return self.__data[_id]["result"]
