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

import asyncio
import websockets
from typing import Dict, List, Set, Literal, Any, Optional, NoReturn
from database import DBManager, Root
from json import dumps, loads
import random
import string
from utils import encrypt, generate_snowflake
from dataclasses import dataclass, asdict, field
import datetime as dt
import logging

logging.basicConfig(
    level=logging.INFO,
    format='[{asctime}] [{levelname:<7}] {name}: {message}',
    style='{',
    datefmt='%Y-%m-%d %H:%M:%S'
)
# logging format, style and datefmt taken from https://github.com/Rapptz/RoboDanny/blob/rewrite/launcher.py#L182


@dataclass
class Invite:
    audit_log: Dict[str, str]  # invited, inviter
    invited_users: List[str]
    lobby_id: str


@dataclass
class Lobby:
    host: str
    red_team: List[str]
    blue_team: List[str]
    switcher: List[str]
    players: Dict[str, dt.datetime]
    invite_code: int
    game_settings: Dict[str, Any]
    game_starting_at: Optional[dt.datetime] = None
    # banned_players: List[str] = field(default_factory=list)


@dataclass
class Game:
    host: str
    round: int
    total_rounds: int
    round_length: int
    round_starts_at: dt.datetime
    round_end_at: dt.datetime
    red_team: List[str]
    blue_team: List[str]
    players: Dict[str, Dict]  # Keys(join_time, team)
    stats: Dict[str, Any] = field(default_factory=lambda: {
        'teams': {'red': {'remaining_players': 0}, 'blue': {'remaining_players': 0}},
        'players': {},
        'winnings': [],
    })
    game_table: Dict[str, Any] = field(default_factory=lambda: {
        'bullets': {},
        'characters': {}
    })


class Server(object):
    """ Handles all the server side networking """
    def __init__(self):
        self.__clients: Set[websockets.WebSocketServerProtocol, ...] = set()
        self.__clients_auth: Dict[websockets.WebSocketServerProtocol, Root] = {}
        self.__lobbies: Dict[str, Lobby] = {}  # Lobby id
        self.__games: Dict[str, Game] = {}  # Game id
        self.__invites: Dict[int, Invite] = {}  # invite_code
        self.__db: DBManager = DBManager(self)
        characters: str = ''.join([string.ascii_letters, string.digits, string.punctuation])
        self.__salt: str = ''.join(
            random.SystemRandom().choices(characters, k=8))  # creates a new salt on each server boot up
        self.__notify: Dict[str, List[str]] = {'track_game_finish': []}  # List of client tokens.
        self.__player_stats: Dict[str, Dict] = {}
        self.__logger: logging.Logger = logging.Logger('Server')
        # this salt is only used to create an authentication token after logging in

    @property
    def salt(self) -> str:
        return self.__salt

    @property
    def clients_auth(self) -> Dict[websockets.WebSocketServerProtocol, Root]:
        return self.__clients_auth

    @property
    def logger(self) -> logging.Logger:
        return self.__logger

    async def on_connect(self, websocket: websockets.WebSocketServerProtocol) -> None:
        """Called when a WebSocket connection is accepted."""
        self.__logger.info("New connection from", websocket.remote_address)
        self.__clients.add(websocket)
        await websocket.send(dumps({"command": "ON_CONNECT", "id": 0}).encode())

    async def on_remove(self, websocket: websockets.WebSocketServerProtocol) -> None:
        """Called when a WebSocket connection is removed."""
        self.__logger.info("Connection closed from", websocket.remote_address)
        if websocket in self.__clients:
            self.__clients.remove(websocket)
            if websocket in self.__clients_auth:
                _root = self.__clients_auth[websocket]
                lobby = self.__lobbies.get(_root.lobby_id)
                game = self.__games.get(_root.last_game_id)
                if lobby:
                    del lobby.players[_root.username]
                    if len(lobby.players.keys()) == 0:
                        if self.__lobbies.get(_root.lobby_id) and \
                                self.__invites.get(self.__lobbies[_root.lobby_id].invite_code):
                            del self.__invites[self.__lobbies[_root.lobby_id].invite_code]
                        del self.__lobbies[_root.lobby_id]

                    elif _root.username == lobby.host:
                        oldest: Optional[str] = None
                        for player in lobby.players:
                            current = lobby.players[player]
                            if not oldest:
                                oldest = player
                            else:
                                if current < lobby.players[oldest]:
                                    oldest = player
                        assert oldest is not None
                        lobby.host = oldest
                    member = _root.username
                    if member in lobby.switcher:
                        lobby.switcher.remove(member)
                    elif member in lobby.blue_team:
                        lobby.blue_team.remove(member)
                    elif member in lobby.red_team:
                        lobby.red_team.remove(member)

                    if len(lobby.players.keys()) != 0:
                        try:
                            await self.on_lobby_gateway(_root.lobby_id, _root.username, 'leave')
                        except Exception as e:
                            self.__logger.warning(e)

                if game:
                    await self.__db.add_game_id(_root.username, _root.last_game_id)
                del self.__clients_auth[websocket]

    def validate_authentication(self, user: str, token: str,
                                websocket: Optional[websockets.WebSocketClientProtocol] = None) -> Dict | Root:
        """ Checks if a user has the correct credentials """
        if not websocket:
            for ws in self.clients_auth:  # type: websockets.WebSocketClientProtocol
                root: Root = self.clients_auth[ws]
                if root.username == user and root.token == token:
                    return root
            return {
                "id": -1,
                "error": "authentication",
                "code": 1,
                "message": "Invalid token"
            }
        else:
            if websocket in self.clients_auth:  # type: websockets.WebSocketClientProtocol
                root: Root = self.clients_auth[websocket]
                if root.username == user and root.token == token:
                    return root

            return {
                "id": -1,
                "error": "authentication",
                "code": 1,
                "message": "Invalid token"
            }

    async def track_game_finish(self) -> NoReturn:
        """ Tracks when a game has finished in order to notify clients that
        they can now join / create games if they didn't reconnect """
        while True:
            for token in self.__notify['track_game_finish']:
                for websocket in self.__clients_auth:
                    if token == self.__clients_auth[websocket].token:
                        if self.__clients_auth[websocket].last_game_id not in self.__games.keys():
                            await websocket.send(dumps({
                                'notify': 'on_game_finish',
                                'id': -2,
                                'game_id': self.__clients_auth[websocket].last_game_id,
                            }))
                            self.__notify['track_game_finish'].remove(token)
            await asyncio.sleep(20)

    async def check_round_ended(self) -> NoReturn:
        """ Checks when a game's round ends and pushes an event """
        while True:
            current = dt.datetime.now()
            for _id in self.__games:
                game = self.__games[_id]
                if game.round_end_at < current:
                    await self.on_round_end(_id, game)
            await asyncio.sleep(1)

    def send_invite(self, username: str, send_to: str, lobby_id: str) -> Dict:
        """ Send a lobby invite to a user """
        lobby = self.__lobbies.get(lobby_id, None)
        if not lobby:
            return {'error': 'Lobby', 'code': 2, 'message': 'Lobby not found!'}
        if username == send_to or send_to in lobby.players:
            return {'error': 'invite', 'message': 'Person already in lobby'}
        invite = self.__invites.get(lobby.invite_code)
        assert invite is not None
        if send_to not in invite.invited_users:
            invite.invited_users.append(send_to)
            invite.audit_log[send_to] = username
            return {'invited': send_to}
        else:
            return {'error': 'send_invite', 'message': f'User is already invited by {invite.audit_log[send_to]}!'}

    async def create_lobby(self, host: str, ws: websockets.WebSocketClientProtocol) -> Dict:
        """ Creates a lobby """
        _ = self.__db.is_rlimited(ws)
        if _:
            _ = await self.__db.notify_rlimit(ws)
            if _:
                return {
                    "status": False,
                    "error": "ratelimit",
                    "id": -1,
                    "message": "You are being RateLimited."
                }
        else:
            await self.__db.maybe_rlimit(ws)

        iterations = 0
        while True:
            invite_code: int = random.SystemRandom().randint(100_000, 999_999)
            iterations += 1
            if iterations > 99_000:
                return {
                    'error': 'ConcurrencyLimit',
                    'id': -1,
                    'message': 'The maximum number of concurrent lobbies created has been reached!'
                }
            if invite_code not in self.__invites.values():
                break

        lobby_id = generate_snowflake()
        lobby = Lobby(
            host, [], [], [host], {host: dt.datetime.now()}, invite_code, {'total_rounds': 3, 'round_duration': 150}
        )
        self.__clients_auth[ws].lobby_id = lobby_id
        self.__lobbies[lobby_id] = lobby
        self.__invites[invite_code] = Invite({}, [], lobby_id)
        json_fmt = asdict(lobby)
        json_fmt['players'] = {k: v.timestamp() for k, v in json_fmt['players'].items()}
        return {'lobby_id': lobby_id, 'lobby': json_fmt}

    async def on_lobby_gateway(self, lobby_id: str, user: str, _type: Literal['join', 'leave']) -> None:
        """ Allows the user to join or leave the lobby and broadcasts that to other clients"""
        lobby = self.__lobbies.get(lobby_id)
        if not lobby_id:
            return

        targets = lobby.players.copy()
        if _type == 'join':
            lobby.players[user] = dt.datetime.now()

        filtered = dict(
            filter(lambda item: item[1].username in targets.keys(), self.__clients_auth.items())
        )
        for ws in filtered:
            to_send = {
                "id": -2,
                "notify": "on_lobby_update",
                "event": "join" if _type == 'join' else 'leave',
                "member": user
            }
            if _type == 'leave':
                json_fmt = asdict(lobby)
                json_fmt['players'] = {k: v.timestamp() for k, v in json_fmt['players'].items()}
                to_send.update({'lobby': json_fmt})
            await ws.send(dumps(to_send).encode())

    async def on_team_change(self, user: str, team: str, lobby_id: str) -> None:
        """ sends an event when an update within the team occurs"""
        lobby = self.__lobbies.get(lobby_id)
        if not lobby:
            return
        targets = lobby.players.copy()
        del targets[user]
        filtered = dict(
            filter(lambda item: item[1].username in targets.keys(), self.__clients_auth.items())
        )
        for ws in filtered:
            await ws.send(dumps({
                "id": -2,
                "notify": "on_lobby_update",
                "event": "team_update",
                "team": team,
                "member": user
            }).encode())

    async def on_settings_update(self, user: str, lobby_id) -> Dict:
        """ sends an event when an update within the settings occurs"""
        lobby = self.__lobbies.get(lobby_id)
        if not lobby:
            return {'error': 'lobby', 'message': 'lobby not found!'}
        targets = lobby.players.copy()
        del targets[user]
        filtered = dict(
            filter(lambda item: item[1].username in targets.keys(), self.__clients_auth.items())
        )
        for ws in filtered:
            await ws.send(dumps({
                "id": -2,
                "notify": "on_lobby_update",
                "event": "settings_update",
                "settings_dict": lobby.game_settings
            }).encode())

    async def on_game_start(self, lobby: Lobby) -> None:
        """ sends an event when a game starts"""
        targets = lobby.players.copy()
        filtered = dict(
            filter(lambda item: item[1].username in targets.keys(), self.__clients_auth.items())
        )
        for ws in filtered:
            await ws.send(dumps({
                "id": -2,
                "notify": "on_lobby_update",
                "event": "on_game_start",
                "when": (dt.datetime.now() + dt.timedelta(seconds=15)).timestamp(),
            }).encode())

    async def join_lobby(self, user: str, invite_code: int, ws: websockets.WebSocketClientProtocol) -> Dict:
        """ Joins a lobby """
        _ = self.__db.is_rlimited(ws)
        if _:
            _ = await self.__db.notify_rlimit(ws)
            if _:
                return {
                    "status": False,
                    "error": "ratelimit",
                    "id": -1,
                    "message": "You are being RateLimited."
                }
        else:
            await self.__db.maybe_rlimit(ws)

        lobby_id = None
        for lid in self.__lobbies:  # type: str
            if self.__lobbies[lid].invite_code == invite_code and not self.__lobbies[lid].game_starting_at:
                lobby_id = lid
                break

        if not lobby_id:
            return {'error': 'join_lobby', 'id': -1, 'code': 1, 'message': 'lobby not found!'}
        else:
            lobby = self.__lobbies[lobby_id]
        if lobby.players == 10:
            return {'error': 'join_lobby', 'id': -1, 'code': 2, 'message': 'lobby is full!'}
        else:
            self.__clients_auth[ws].lobby_id = lobby_id
            lobby.switcher.append(user)
            await self.on_lobby_gateway(lobby_id, user, 'join')
            json_fmt = asdict(self.__lobbies[lobby_id])
            json_fmt['players'] = {k: v.timestamp() for k, v in json_fmt['players'].items()}
            return {'lobby_id': lobby_id, 'lobby': json_fmt}

    async def create_game(self, host: str, *, lobby: Lobby, ws: websockets.WebSocketClientProtocol) -> Dict:
        """ Creates a game """
        _ = self.__db.is_rlimited(ws)
        if _:
            _ = await self.__db.notify_rlimit(ws)
            if _:
                return {
                    "status": False,
                    "error": "ratelimit",
                    "id": -1,
                    "message": "You are being RateLimited."
                }
        else:
            await self.__db.maybe_rlimit(ws)

        red_team = lobby.red_team
        blue_team = lobby.blue_team
        total_rounds = lobby.game_settings['total_rounds']
        round_duration = lobby.game_settings['round_duration']

        game_id = generate_snowflake()
        game = Game(
            host=host, round=1, total_rounds=total_rounds, round_length=round_duration,
            round_starts_at=dt.datetime.now() + dt.timedelta(seconds=15),
            round_end_at=dt.datetime.now() + dt.timedelta(seconds=round_duration + 15),
            red_team=red_team[:], blue_team=blue_team[:],
            players={k: {'joined': v.timestamp()} for k, v in lobby.players.items()},
        )
        game.stats['teams']['red']['remaining_players'] = len(game.red_team)
        game.stats['teams']['blue']['remaining_players'] = len(game.blue_team)
        for player in game.players:
            game.stats['players'][player] = {}
            game.stats['players'][player]['kills'] = 0
            game.stats['players'][player]['deaths'] = 0
            game.stats['players'][player]['playtime'] = 0
            game.players[player]['team'] = 'red' if player in game.red_team else 'blue'

        self.__games[game_id] = game
        json_fmt = asdict(game)
        del json_fmt['game_table']
        json_fmt['round_starts_at'] = json_fmt['round_starts_at'].timestamp()
        json_fmt['round_end_at'] = json_fmt['round_end_at'].timestamp()
        await self.on_game_start(lobby)
        async def do():
            nonlocal host
            nonlocal self
            nonlocal game
            nonlocal json_fmt
            targets = list(game.players.keys()).copy()
            filtered = dict(
                filter(lambda item: item[1].username in targets, self.__clients_auth.items())
            )
            for webs in filtered:  # type: websockets.WebSocketClientProtocol
                self.__clients_auth[webs].last_game_id = game_id
                if self.__clients_auth[webs].username == host:
                    continue
                await webs.send(dumps({
                    'notify': 'game_started',
                    'id': -2,
                    'game_id': game_id,
                    'game_info': json_fmt
                }).encode())

        asyncio.create_task(do())
        return {'game_id': game_id, 'game_info': json_fmt}

    async def on_round_end(self, game_id: str, game: Game) -> None:
        """ Handles the logic when a round ends and send's an event to inform the clients that the round has ended """
        filtered = dict(
            filter(lambda item: item[1].username in game.players.keys(), self.__clients_auth.items())
        )

        red_rem = game.stats['teams']['red']['remaining_players']
        blue_rem = game.stats['teams']['blue']['remaining_players']
        if red_rem == blue_rem:
            winning = 'draw'
        elif red_rem > 0 and blue_rem <= 0:
            winning = 'red'
        else:
            winning = 'blue'
        game.stats['winnings'].append(winning)
        game.round_starts_at = dt.datetime.now() + dt.timedelta(seconds=15)
        game.round_end_at = dt.datetime.now() + dt.timedelta(seconds=game.round_length + 15)
        game.stats['teams']['red']['remaining_players'] = len(game.red_team)
        game.stats['teams']['blue']['remaining_players'] = len(game.blue_team)
        game.round += 1

        to_send = {
            "id": -2,
            "notify": "on_game_update",
            "event": "next_check",
            "data": {
                "metadata": {
                    "won": winning,
                    "red_leaderboard": ["RED TEAM"],
                    "blue_leaderboard": ["BLUE TEAM"]
                }
            }
        }
        red_lb = []
        blue_lb = []
        lb_data = sorted(game.stats['players'].items(), key=lambda x: x[1]['kills'], reverse=True)
        for player, player_data in lb_data:
            game.stats['players'][player]['playtime'] += (game.round_length // 60)
            _team = game.players[player]['team']
            idx = game.red_team.index(player) if _team == 'red' else game.blue_team.index(player)
            sts = f"[{idx + 1}] {player}: ({player_data['kills']:,})k ({player_data['deaths']})d"
            if _team == 'red':
                red_lb.append(sts)
            else:
                blue_lb.append(sts)

        _shrt: Dict[str, List | str] = to_send['data']['metadata']
        _shrt['red_leaderboard'].extend(red_lb)
        _shrt['blue_leaderboard'].extend(blue_lb)

        for ws in filtered:
            await ws.send(dumps(to_send).encode())

        if game.round > game.total_rounds:
            await self.__db.save_stats(game)
            del self.__games[game_id]

    async def on_game_broadcast(self, character: bool, data: Dict, game_id: str, user: str) -> None:
        """ Used to transmit game data to other clients """
        game = self.__games[game_id]
        targets = list(game.players.keys()).copy()
        filtered = dict(
            filter(lambda item: item[1].username in targets, self.__clients_auth.items())
        )
        if character:
            if data['COMMAND'] == 'MOVE':
                del data['COMMAND']
                to_send = {
                    "id": -2,
                    "notify": "on_game_update",
                    "event": "character",
                    "owner": user,
                    "data": data
                }
                game.game_table[user] = data
                for ws in filtered:
                    if self.__clients_auth[ws].username == user:
                        continue
                    await ws.send(dumps(to_send).encode())
            elif data['COMMAND'] == 'INIT':
                del data['COMMAND']
                game.game_table[user] = data

            elif data['COMMAND'] == 'DEATH':
                by = data['BY']
                game.stats['players'][by]['kills'] += 1
                game.stats['players'][user]['deaths'] += 1
                _team = game.players[user]['team']
                game.stats['teams'][_team]['remaining_players'] -= 1
                if game.stats['teams'][_team]['remaining_players'] == 0:
                    await self.on_round_end(game_id, game)

        else:
            # Bullet
            del data['COMMAND']
            to_send = {
                "id": -2,
                "notify": "on_game_update",
                "event": "bullet",
                "data": data
            }
            to_send['data'].update({"OWNER": user})
            for ws in filtered:
                if self.__clients_auth[ws].username == user:
                    continue
                await ws.send(dumps(to_send).encode())

    async def accept(self, websocket: websockets.WebSocketServerProtocol) -> None:
        """Accepts and handles WebSocket connections from clients.
            """
        await self.on_connect(websocket)
        while True:
            try:
                data: bytes = await websocket.recv()
            except (websockets.ConnectionClosedError, websockets.ConnectionClosedOK):
                self.__logger.info("Client", websocket.remote_address, "has disconnected!")
                await self.on_remove(websocket)
                break
            data: str = data.decode()

            if not data:
                continue

            data: List[str] = data.split('#')
            for instruction in data:
                if instruction == "":
                    continue
                instruction = loads(instruction)
                command = instruction.get("command")
                _id = instruction.get("id")
                kwargs = instruction.get("kwargs", {})
                if _id == 0:
                    # Heartbeat ws from client
                    continue
                if command == 'get_user':
                    username = kwargs.get('username')
                    if not username:
                        data: Dict = {"return": "userdata", "id": _id, "result": None, 'ret_type': 'NoneType'}
                        await websocket.send(dumps(data).encode())
                        continue

                    ret_type: Literal['list', 'dict']
                    try:
                        ret_type = kwargs.pop('ret_type')
                    except KeyError:
                        ret_type = 'dict'
                    res = await self.__db.get_user(username, ret_type=ret_type)
                    if not res:
                        data: Dict = {"return": "userdata", "id": _id, "result": None, 'ret_type': 'NoneType'}
                        await websocket.send(dumps(data).encode())
                        continue

                    data: Dict = {"return": "userdata", "id": _id, "result": res, 'ret_type': ret_type}
                    await websocket.send(dumps(data).encode())

                elif command == 'login':
                    username = kwargs.get('username')
                    password = kwargs.get('password')
                    if not username or not password:
                        continue
                    password = encrypt(password)
                    res = await self.__db.login(username, password, websocket)
                    if res['status']:
                        self.__clients_auth[websocket] = Root(
                            username=res['data']['username'],
                            displayname=res['data']['displayname'],
                            token=res['authentication'],
                            email=res['data']['email'],
                            last_game_id=res['data']['last_game_id'],
                            friends=res['data']['friends'].split(", ") if res['data']['friends'] else []
                        )
                    data: Dict = {'return': 'login', 'id': _id, 'result': res}
                    await websocket.send(dumps(data).encode())

                elif command == 'register':
                    displayname = kwargs.get('displayname')
                    username = kwargs.get('username')
                    email = kwargs.get('email')
                    password = kwargs.get('password')
                    otp = kwargs.get('otp')
                    if displayname and username and email and password:
                        password: str = encrypt(password)
                        result = await self.__db.register(displayname, username, email, password, websocket, otp)
                        if type(result) == dict and result.get('error'):
                            await websocket.send(dumps({
                                'return': 'register',
                                'id': _id,
                                'error': True,
                                'result': result
                            }).encode())
                        else:
                            if type(result) == dict and result.get('status'):
                                result: Dict[str, Any]
                                if result['data']['friends']:
                                    result['data']['friends'] = data['friends'].split(", ")
                                else:
                                    result['data']['friends'] = []
                                self.__clients_auth[websocket] = Root(
                                    username=result['data']['username'],
                                    displayname=result['data']['displayname'],
                                    token=result['authentication'],
                                    email=result['data']['email'],
                                    last_game_id=result['data']['last_game_id'],
                                    friends=result['data']['friends'].split(", ") if result['data']['friends'] else []
                                )
                            await websocket.send(dumps({
                                'return': 'register',
                                'id': _id,
                                'result': result
                            }).encode())

                elif command == 'send_fpwd_code':
                    username = kwargs.get('username')
                    email = kwargs.get('email')
                    result = await self.__db.send_fpwd_otp(username, email, websocket)
                    if result.get('error'):
                        await websocket.send(dumps({
                            'return': 'sent_fpwd_code',
                            'id': _id,
                            'error': True,
                            'result': result
                        }).encode())
                    else:
                        await websocket.send(dumps({
                            'return': 'sent_fpwd_code',
                            'id': _id,
                            'result': result
                        }).encode())

                elif command == 'update_password':
                    username = kwargs.get('username')
                    email = kwargs.get('email')
                    password = encrypt(kwargs.get('password'))
                    otp_code = kwargs.get('otp_code')
                    result = await self.__db.update_password(username, email, password, otp_code, websocket)
                    if result.get('error'):
                        await websocket.send(dumps({
                            'return': 'updated_password',
                            'id': _id,
                            'error': True,
                            'result': result
                        }).encode())
                    else:
                        await websocket.send(dumps({
                            'return': 'updated_password',
                            'id': _id,
                            'result': result
                        }).encode())

                elif command == 'add_friend':
                    from_user = kwargs.get('from_user')
                    to_user = kwargs.get('to_user')
                    from_user_token = kwargs.get('authentication')
                    result = await self.__db.add_friend(from_user, to_user, from_user_token, websocket)
                    if result.get('error'):
                        await websocket.send(dumps({
                            'return': 'added_friend',
                            'id': _id,
                            'error': True,
                            'result': result
                        }).encode())
                    else:
                        await websocket.send(dumps({
                            'return': 'added_friend',
                            'id': _id,
                            'result': result
                        }).encode())

                elif command == 'remove_friend':
                    from_user = kwargs.get('from_user')
                    with_user = kwargs.get('with_user')
                    from_user_token = kwargs.get('authentication')
                    result = await self.__db.remove_friend(from_user, with_user, from_user_token, websocket)
                    if result.get('error'):
                        await websocket.send(dumps({
                            'return': 'removed_friend',
                            'id': _id,
                            'error': True,
                            'result': result
                        }).encode())
                    else:
                        await websocket.send(dumps({
                            'return': 'removed_friend',
                            'id': _id,
                            'result': result
                        }).encode())

                elif command == 'get_outbound_requests':
                    from_username = kwargs.get('root')
                    token = kwargs.get('authentication')
                    result = await self.__db.get_outbound_requests(from_username, token, websocket)
                    if result.get('error'):
                        await websocket.send(dumps({
                            'return': 'outbound_requests',
                            'id': _id,
                            'error': True,
                            'result': result
                        }).encode())
                    else:
                        await websocket.send(dumps({
                            'return': 'outbound_requests',
                            'id': _id,
                            'result': result
                        }).encode())

                elif command == 'get_inbound_requests':
                    to_username = kwargs.get('root')
                    token = kwargs.get('authentication')
                    result = await self.__db.get_inbound_requests(to_username, token, websocket)
                    if result.get('error'):
                        await websocket.send(dumps({
                            'return': 'inbound_requests',
                            'id': _id,
                            'error': True,
                            'result': result
                        }).encode())
                    else:
                        await websocket.send(dumps({
                            'return': 'inbound_requests',
                            'id': _id,
                            'result': result
                        }).encode())

                elif command == 'game_is_running':
                    notify_on_finish = kwargs.get('notify_on_finish')
                    token = kwargs.get('authentication')
                    if websocket in self.__clients_auth:
                        if token == self.__clients_auth[websocket].token:
                            if self.__clients_auth[websocket].last_game_id in self.__games.keys():
                                await websocket.send(dumps({
                                    'return': 'root_in_game',
                                    'status': True,
                                    'id': _id
                                }).encode())
                                json_fmt = asdict(self.__games[self.__clients_auth[websocket].last_game_id])
                                del json_fmt['game_table']
                                json_fmt['round_starts_at'] = json_fmt['round_starts_at'].timestamp()
                                json_fmt['round_end_at'] = json_fmt['round_end_at'].timestamp()

                                await websocket.send(dumps({
                                    'notify': 'game_started',
                                    'id': -2,
                                    'game_id': self.__clients_auth[websocket].last_game_id,
                                    'game_info': json_fmt
                                }).encode())

                                if notify_on_finish:
                                    self.__notify['track_game_finish'].append(token)
                    else:
                        await websocket.send(dumps({
                            'status': False,
                            'id': _id
                        }).encode())

                elif command == 'get_invites':
                    _ = self.__db.is_rlimited(websocket)
                    if _:
                        _ = await self.__db.notify_rlimit(websocket)
                        if _:
                            await websocket.send(dumps({
                                'return': 'invites',
                                'error': True,
                                'id': _id,
                                'result': {
                                    "id": -1,
                                    "error": "ratelimit",
                                    "code": 1,
                                }
                            }).encode())
                    else:
                        await self.__db.maybe_rlimit(websocket)

                    user = kwargs.get('root')
                    token = kwargs.get('authentication')
                    resp = self.validate_authentication(user, token, websocket)
                    if not isinstance(resp, Root):
                        await websocket.send(dumps({
                            'return': 'invites',
                            'error': True,
                            'id': _id,
                            'result': resp
                        }).encode())
                    else:
                        _dict: Dict[str, int] = {}
                        for inv in self.__invites:
                            if user in self.__invites[inv].invited_users:
                                invited_by = self.__invites[inv].audit_log[user]
                                _dict[invited_by] = inv
                        await websocket.send(dumps({
                            'return': 'invites',
                            'id': _id,
                            'result': _dict
                        }).encode())

                elif command == 'create_lobby':
                    host = kwargs.get('root')
                    token = kwargs.get('authentication')
                    resp = self.validate_authentication(host, token, websocket)
                    to_send = {'return': 'created_lobby', 'id': _id}
                    if not isinstance(resp, Root):
                        to_send.update({'error': True, 'result': resp})
                    else:
                        resp = await self.create_lobby(host, websocket)
                        to_send.update({'result': resp})
                        if resp.get('error'):
                            to_send.update({'error': True})
                    await websocket.send(dumps(to_send).encode())

                elif command == 'join_lobby':
                    user = kwargs.get('root')
                    invite_code = kwargs.get('invite_code')
                    token = kwargs.get('authentication')
                    resp = self.validate_authentication(user, token, websocket)
                    to_send = {'return': 'joined_lobby', 'id': _id}
                    if not isinstance(resp, Root):
                        to_send.update({'error': True, 'result': resp})
                    else:
                        resp = await self.join_lobby(user, invite_code, websocket)
                        to_send.update({'result': resp})
                        if resp.get('error'):
                            to_send.update({'error': True})
                    await websocket.send(dumps(to_send).encode())

                elif command == 'leave_lobby':
                    user = kwargs.get('root')
                    token = kwargs.get('authentication')
                    lobby_id = kwargs.get('lobby_id')
                    resp = self.validate_authentication(user, token, websocket)
                    to_send = {'return': 'left_lobby', 'id': _id}
                    if not isinstance(resp, Root):
                        to_send.update({'error': True, 'result': resp})
                    else:
                        lobby = self.__lobbies.get(lobby_id)
                        if lobby:
                            del lobby.players[user]
                            if len(lobby.players.keys()) == 0:
                                del self.__lobbies[lobby_id]
                                if self.__invites.get(lobby.invite_code):
                                    del self.__invites[lobby.invite_code]

                            elif user == lobby.host:
                                oldest: Optional[str] = None
                                for player in lobby.players:
                                    current = lobby.players[player]
                                    if not oldest:
                                        oldest = player
                                    else:
                                        if current < lobby.players[oldest]:
                                            oldest = player
                                assert oldest is not None
                                lobby.host = oldest
                            if user in lobby.switcher:
                                lobby.switcher.remove(user)
                            elif user in lobby.blue_team:
                                lobby.blue_team.remove(user)
                            elif user in lobby.red_team:
                                lobby.red_team.remove(user)

                            if len(lobby.players.keys()) != 0:
                                await self.on_lobby_gateway(lobby_id, user, 'leave')

                        to_send.update({'result': 'handled'})
                    await websocket.send(dumps(to_send).encode())

                elif command == 'invite':
                    user = kwargs.get('root')
                    token = kwargs.get('authentication')
                    to_invite = kwargs.get('user')
                    lobby_id = kwargs.get('lobby_id')
                    resp = self.validate_authentication(user, token, websocket)
                    to_send = {'return': 'invited', 'id': _id}
                    if not isinstance(resp, Root):
                        to_send.update({'error': True, 'result': resp})
                    else:
                        resp = self.send_invite(user, to_invite, lobby_id)
                        to_send.update({'result': resp})
                    await websocket.send(dumps(to_send).encode())

                elif command == 'join_team':
                    user = kwargs.get('root')
                    token = kwargs.get('authentication')
                    lobby_id = kwargs.get('lobby_id')
                    team = kwargs.get('team')
                    resp = self.validate_authentication(user, token, websocket)
                    to_send = {'return': 'team_joined', 'id': _id}
                    if not isinstance(resp, Root):
                        to_send.update({'result': {'status': False}})
                    else:
                        lobby = self.__lobbies.get(lobby_id)
                        if lobby:
                            if user in lobby.switcher:
                                lobby.switcher.remove(user)
                            elif user in lobby.blue_team:
                                lobby.blue_team.remove(user)
                            elif user in lobby.red_team:
                                lobby.red_team.remove(user)

                            if team == 'red':
                                lobby.red_team.append(user)
                            elif team == 'blue':
                                lobby.blue_team.append(user)
                            else:
                                lobby.switcher.append(user)
                            to_send.update({'result': {'status': True}})
                            asyncio.create_task(self.on_team_change(user, team, lobby_id))
                        else:
                            to_send.update({'result': {'status': False}})

                    await websocket.send(dumps(to_send).encode())

                elif command == 'update_game_settings':
                    user = kwargs.get('root')
                    token = kwargs.get('authentication')
                    lobby_id = kwargs.get('lobby_id')
                    settings_dict = kwargs.get('settings_dict')
                    resp = self.validate_authentication(user, token, websocket)
                    to_send = {'return': 'updated_game_settings', 'id': _id}
                    if not isinstance(resp, Root):
                        to_send.update({'error': True, 'result': {'status': False}})
                    else:
                        lobby = self.__lobbies.get(lobby_id)
                        if lobby:
                            total_rounds = settings_dict.get('total_rounds')
                            round_duration = settings_dict.get('round_duration')
                            if type(total_rounds) == int and type(round_duration) == int:
                                if round_duration > 600 or round_duration < 60:
                                    to_send.update({
                                        'result': {
                                            'error': True,
                                            'message': 'Round Duration must be less than to 601 seconds and'
                                                       ' higher than 59'
                                        },
                                        'error': True
                                    })
                                elif total_rounds > 20 or total_rounds < 1:
                                    to_send.update({
                                        'result': {
                                            'error': True,
                                            'message': 'Total Rounds must be less than 21 and higher than 0'
                                        },
                                        'error': True
                                    })
                                else:
                                    lobby.game_settings['total_rounds'] = total_rounds
                                    lobby.game_settings['round_duration'] = round_duration
                                    asyncio.create_task(self.on_settings_update(user, lobby_id))
                                    to_send.update({'result': {'status': True}})
                            else:
                                to_send.update({'error': True, 'result': {
                                    'error': True, 'message': 'Setting values should be integers'
                                }})
                        else:
                            to_send.update({'error': True, 'result': {'error': True, 'message': 'lobby not found!'}})
                        await websocket.send(dumps(to_send).encode())

                elif command == 'create_game':
                    host = kwargs.get('root')
                    token = kwargs.get('authentication')
                    lobby_id = kwargs.get('lobby_id')
                    resp = self.validate_authentication(host, token, websocket)
                    to_send = {'return': 'created_game', 'id': _id}
                    if not isinstance(resp, Root):
                        to_send.update({'error': True, 'result': resp})
                    else:
                        lobby = self.__lobbies[lobby_id]
                        if len(lobby.red_team) < 1 or len(lobby.blue_team) < 1:
                            to_send.update({'result': {
                                'error': True,
                                'message': 'There needs to be at least 1 player in each team!'
                            }})
                        else:
                            resp = await self.create_game(
                                host, lobby=lobby, ws=websocket)
                            to_send.update({'result': resp})
                            if resp.get('error'):
                                to_send.update({'error': True})
                    await websocket.send(dumps(to_send).encode())

                elif command == 'bullet_fired':
                    data: Dict = kwargs.get('data')
                    game_id: str = kwargs.get('game_id')
                    user = kwargs.get('root')
                    token = kwargs.get('authentication')
                    resp = self.validate_authentication(user, token, websocket)
                    if isinstance(resp, Root):
                        await self.on_game_broadcast(character=False, data=data, game_id=game_id, user=user)

                elif command == 'broadcast_self':
                    data: Dict = kwargs.get('data')
                    game_id: str = kwargs.get('game_id')
                    user = kwargs.get('root')
                    token = kwargs.get('authentication')
                    resp = self.validate_authentication(user, token, websocket)
                    if isinstance(resp, Root):
                        await self.on_game_broadcast(character=True, data=data, game_id=game_id, user=user)

    async def run(self) -> None:
        """Called to start the WebSocket server."""
        await self.__db.on_load()
        asyncio.create_task(self.check_round_ended())
        asyncio.create_task(self.track_game_finish())
        self.__logger.info("STARTED SERVER")
        server = await websockets.serve(
            self.accept,
            "localhost",
            50000  # Port 50,000
        )

        await server.wait_closed()


if __name__ == '__main__':
    asyncio.run(Server().run())
