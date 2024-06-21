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

from typing import TYPE_CHECKING, Optional, Union, Literal, List, Dict, TypedDict, overload
import asyncio
import asqlite
from sqlite3 import Row
import datetime
import random
import string
import aiosmtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv
from os import getenv
from utils import generate_snowflake, encrypt
from json import dumps
from copy import deepcopy
from dataclasses import dataclass
from itertools import chain

load_dotenv()

if TYPE_CHECKING:
    from server import Server, Game
    import websockets


@dataclass
class Root:
    """ Represent's authenticated clients """
    username: str
    displayname: str
    token: str
    email: str
    last_game_id: str  # snowflake
    friends: list[str]
    lobby_id: Optional[str] = None


class OTPCacheDict(TypedDict):
    """ One Time password Cache"""
    datetime: datetime.datetime
    displayname: str
    username: str
    email: str
    password: str


class RateLimitCacheDict(TypedDict):
    """ RateLimit Cache """
    times: int
    limit: int
    clear_after: Optional[datetime.datetime]
    retry_after: Optional[datetime.datetime]


class DBManager:
    """ Manages all the database interactions """
    def __init__(self, server: Server = None) -> None:
        # self.__pool: Optional[asqlite.Pool] = None
        self.__server: Server = server
        self.__register_cache: Dict[int, OTPCacheDict] = {}
        self.__fpwd_otp_cache: Dict[int, OTPCacheDict] = {}
        self.__pool: Optional[asqlite.Pool] = None
        # fpwd is shorthanded for "forgot password" 
        self.__ratelimit_cache: Dict[websockets.WebSocketClientProtocol, RateLimitCacheDict] = {}
        self.__mail_server = aiosmtplib.SMTP(
            hostname='smtp.gmail.com',
            port=587,
            start_tls=True
        )
        # port number 587 -> https://www.cloudflare.com/learning/email-security/smtp-port-25-587/
        # self.__mail_server.starttls()
        self.__sender_email: str = getenv('EMAIL')
        self.__sender_password: str = getenv('APP_PASSWORD')


    """ boot up functions """

    async def clear_cache(self) -> None:
        """ This function clears the OTP and ratelimit cache every 5 seconds"""
        while True:
            await asyncio.sleep(5)
            now = datetime.datetime.now()
            # _c stands for _copy
            _c = deepcopy(self.__register_cache)
            for _code in _c:  # type: int
                _c[_code]: OTPCacheDict
                if _c[_code]['datetime'] <= now:
                    del self.__register_cache[_code]

            _c = deepcopy(self.__fpwd_otp_cache)
            now = datetime.datetime.now()
            for _code in _c:  # type: int
                _c[_code]: OTPCacheDict
                if _c[_code]['datetime'] <= now:
                    del self.__fpwd_otp_cache[_code]

            # hack implementation due to pickle error:
            # TypeError: cannot pickle '_asyncio.Future' object

            _pickle_friendly = {}
            _book = {}
            _identifier = 0
            for _websocket in self.__ratelimit_cache:
                _pickle_friendly[_identifier] = self.__ratelimit_cache[_websocket]
                _book[_identifier] = _websocket
                _identifier += 1

            for _id in _pickle_friendly:  # type: int
                _pickle_friendly[_id]: RateLimitCacheDict
                r_after = _pickle_friendly[_id]['retry_after']
                c_after = _pickle_friendly[_id]['clear_after']
                if r_after and (r_after - now) > datetime.timedelta(hours=1):
                    del self.__ratelimit_cache[_book[_id]]
                if c_after and _pickle_friendly[_id]['limit'] <= _pickle_friendly[_id]['times'] and c_after <= now:
                    del self.__ratelimit_cache[_book[_id]]

    async def on_load(self):
        """ The server calls this function; this ensures that an asyncio loop is running. """
        # loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()

        # self.__conn: asqlite.Connection = await asqlite.connect('data.db')
        await self.__mail_server.connect()
        await self.__mail_server.login(self.__sender_email, self.__sender_password)
        self.__pool: asqlite.Pool = await asqlite.create_pool('data.db')
        await self.init_tables()
        asyncio.create_task(self.clear_cache())

    """
    Ratelimit related functions
    """

    async def maybe_rlimit(self, websocket: websockets.WebSocketClientProtocol) -> None:
        """" potentially rate-limits a websocket """
        current = self.__ratelimit_cache.get(websocket)
        if not current:
            self.__ratelimit_cache[websocket] = {
                "times": 1,
                "limit": 50,
                "clear_after": datetime.datetime.now() + datetime.timedelta(minutes=5),
                "retry_after": None
            }
            return
        current['times'] += 1
        if current['limit'] > current['times']:
            # no ratelimit
            if current['retry_after']:
                current['retry_after'] = None
            current['clear_after'] = datetime.datetime.now() + datetime.timedelta(minutes=1)
            self.__ratelimit_cache[websocket] = current
        else:
            _duration = current['times'] * 5
            if _duration > 3600:
                _duration = 3600
            current['retry_after'] = datetime.datetime.now() + datetime.timedelta(seconds=_duration)
            current['clear_after'] = datetime.datetime.now() + datetime.timedelta(seconds=_duration + 150)
            self.__ratelimit_cache[websocket] = current
            await websocket.send(dumps({
                "error": "ratelimit",
                "id": -1,
                "message": f"You are being ratelimited!",
                "dt": current['retry_after'].timestamp()
            }).encode())

    def is_rlimited(self, websocket: websockets.WebSocketClientProtocol) -> bool:
        """ checks if a websocket is ratelimited
            :returns: True if ratelimited else False
        """
        current = self.__ratelimit_cache.get(websocket)
        if not current:
            return False

        return True if current['retry_after'] and current['retry_after'] > datetime.datetime.now() else False

    async def notify_rlimit(self, websocket: websockets.WebSocketClientProtocol) -> bool:
        """ notifies a client of their ratelimit [retry_after]
            :returns: False if websocket has no ratelimit else True
        """

        current = self.__ratelimit_cache.get(websocket)
        if not current:
            return False

        if current['retry_after'] and current['retry_after'] > datetime.datetime.now():
            await websocket.send(dumps({
                "error": "ratelimit",
                "id": -1,
                "message": f"You are being ratelimited!",
                "dt": current['retry_after'].timestamp()
            }).encode())
            return True

    """ sql / database related functions"""

    async def run_sql(self, sql, *args, **kwargs) -> Optional[Union[List, Dict]]:
        """ Runs the sql statement given with the args and kwargs and executes them asynchronously

        ----- FUNCTION RELATED KWARGS -----
            - ret: Union[int, Literal['one', 'all']] = None
            # int [n > 0] -> n number of items returned (fetchmany)
            # str:
                -> 'all' -> maximum number of items returned (fetchall)
                -> 'one' -> one item returned (fetchone)

        ---- REST OF THE ARGS AND KWARGS ARE PASSED INTO .EXECUTE -----
        :return: Optional[Union[List, Dict]]
        """

        ret: Union[int, Literal['one', 'all'], None]
        try:
            ret = kwargs.pop('ret')
        except KeyError:
            ret = None

        ret_type: Literal['list', 'dict']
        try:
            ret_type = kwargs.pop('ret_type')
        except KeyError:
            ret_type = 'list'

        @overload
        def fmt_type(r: List[Row]) -> List[Dict | List]:
            ...

        @overload
        def fmt_type(r: Row) -> Dict | List:
            ...

        def fmt_type(r: Row | List[Row]) -> List | Dict | List[Dict | List]:
            if not r:
                return r
            if type(r) != list:
                return dict(r) if ret_type == 'dict' else list(r)
            else:
                d = []
                for _r in r:
                    d.append(dict(_r) if ret_type == 'dict' else list(_r))
                return d

        cursor: asqlite.Cursor
        async with self.__pool.acquire() as conn:
            async with conn.cursor() as cursor:
                res = await cursor.execute(sql, *args, **kwargs)  # type: ignore
                if ret:
                    if type(ret) == int and ret > 0:
                        return fmt_type(await res.fetchmany(ret))
                    elif ret == 'one':
                        return fmt_type(await res.fetchone())
                    elif ret == 'all':
                        _all = await res.fetchall()
                        return fmt_type(_all)

    async def init_tables(self) -> None:
        """ Creates tables needed if they don't already exist """

        user_table = """ CREATE TABLE IF NOT EXISTS USER (
            USERNAME CHARACTER,
            DISPLAYNAME CHARACTER,
            EMAIL CHARACTER COLLATE NOCASE,
            PASSWORD CHARACTER,
            FRIENDS CHARACTER,
            LAST_GAME_ID INTEGER,
            PRIMARY KEY (USERNAME)

        )"""

        # IF the LAST GAME ID IS A RUNNING GAME, WE CAN ALLOW THEM TO RECONNECT
        await self.run_sql(user_table)

        stats_table = """ CREATE TABLE IF NOT EXISTS STATS (
            USERNAME CHARACTER,
            TOTAL_MINUTES INTEGER,
            GAMES_PLAYED INTEGER,
            GAMES_WON INTEGER,
            TOTAL_KILLS INTEGER,
            TOTAL_DEATHS INTEGER,
            PRIMARY KEY (USERNAME),
            FOREIGN KEY (USERNAME) REFERENCES USER(USERNAME) ON DELETE CASCADE
            )"""

        # stats query example: FROM USER JOIN Stats ON User.UserID = Stats.UserID WHERE User.UserID = 1
        await self.run_sql(stats_table)

        friend_request_table = """ CREATE TABLE IF NOT EXISTS FRIEND_REQUEST (
            FROM_USER CHARACTER,
            TO_USER CHARACTER,
            PRIMARY KEY (FROM_USER, TO_USER)
        )"""
        await self.run_sql(friend_request_table)

    """ User related functions
        Login
        Get_User
        Register
        Outbound_fnd_requests
        Inbound_fnd_requests
     """

    async def login(self, username: str, password: str, websocket: websockets.WebSocketClientProtocol) -> Dict:
        """ authenticates a user's login

            :returns: Dict

            Dict:
                - Failure: Dict['status': False] # indicates username or password is incorrect

                - Success: Dict['status': True,
                    'authentication': encrypted(snowflake + Server.__salt), 'data': Dict]
                    # indicates the correct username and password were passed in
        """

        _ = self.is_rlimited(websocket)
        if _:
            _ = await self.notify_rlimit(websocket)
            if _:
                return {
                    'status': False,
                    'authentication': None,
                    'data': {}
                }
        else:
            await self.maybe_rlimit(websocket)

        query = """
            SELECT USER.USERNAME, USER.DISPLAYNAME, USER.EMAIL, USER.FRIENDS, USER.LAST_GAME_ID,
            STATS.TOTAL_MINUTES, STATS.GAMES_PLAYED, STATS.GAMES_WON, STATS.TOTAL_KILLS, STATS.TOTAL_DEATHS
            
            FROM USER JOIN STATS ON USER.USERNAME = STATS.USERNAME WHERE USER.USERNAME = ? AND USER.PASSWORD = ?
            """
        res = await self.run_sql(query, username, password, ret='one', ret_type='dict')
        if not res:
            return {'status': False, 'authentication': None, 'data': {}}
        return {
            'status': True,
            'authentication': encrypt(generate_snowflake() + self.__server.salt),
            'data': {k.lower(): v for k, v in res.items()}
        }

    async def get_user(self, username: str, ret_type: Literal['dict', 'lst']) -> Dict | List | None:
        """ returns a user from the sqlite database if none found return's None
            ret_type: Literal['dict', 'lst'] -> the type that the returned value should be
        """

        query = """
            SELECT USER.USERNAME, USER.DISPLAYNAME, USER.FRIENDS, 
            STATS.TOTAL_MINUTES, STATS.GAMES_PLAYED, STATS.GAMES_WON, STATS.TOTAL_KILLS, STATS.TOTAL_DEATHS  
            FROM USER JOIN STATS ON USER.USERNAME = STATS.USERNAME WHERE USER.USERNAME = ?
            """
        data = await self.run_sql(query, username, ret='one', ret_type=ret_type)
        if not data:
            return data
        elif ret_type == 'dict':
            # format the data first
            return {k.lower(): v for k, v in data.items()}
        else:
            return data

    def register_collision(self, displayname: str, username: str, email: str, password: str) -> bool:
        """ Checks if username is taken (collision) by someone who needs to enter an otp code.

            True -> there is a collision
            False -> no collision
            :returns: bool
        """

        for otp in self.__register_cache:  # type: int
            data: OTPCacheDict = self.__register_cache[otp]
            if any([data['email'] != email, data['password'] != password, data['displayname'] != displayname]) \
                    and data['username'] == username:
                # this makes sure that the data isn't from the user validating their otp
                return True

        return False

    async def register(self, displayname: str, username: str, email: str,
                       password: str, websocket: websockets.WebSocketClientProtocol, otp: Optional[int] = None) \
            -> Dict | str:
        """ Handles the creation of the user
            What this does (in order):
                - Makes sure username is available in the pool
                - if not raises error code 1 (username taken)
                - otherwise sends an OTP CODE to the email
                - sends the OTP code to the client
                - waits until the client sends a confirmation of the OTP
                - them creates the account into the database.

            to prevent collision on registration, when a user gets OTP code, is marked as taken until
            self.__register_cache is cleared for that otp code

            error codes: [all have an id of -1]
            1 -> username taken
            2 -> invalid otp token
            3 -> data for otp doesn't match (otp code doesn't match for its data)
            4 -> username being held by another party during otp
            5 -> expired otp token / otp token doesn't exist for that account (sends a new otp code to email)
            6 -> ratelimited

        """

        _ = self.is_rlimited(websocket)
        if _:
            _ = await self.notify_rlimit(websocket)
            if _:
                return {
                    "id": -1,
                    "error": True,
                    "code": 6,
                }
        else:
            await self.maybe_rlimit(websocket)

        res = await self.run_sql("SELECT USERNAME FROM USER WHERE USERNAME = ?", username, ret='one')

        if res:
            return {
                "id": -1,
                "error": "register",
                "code": 1,
                "message": "username taken"
            }

        # check if the username is held
        res = self.register_collision(displayname, username, email, password)
        if res:
            return {
                "id": -1,
                "error": "register",
                "code": 4,
                "message": "username held by another party"
            }

        if not otp:
            await self.send_register_otp(displayname, username, email, password, websocket)
            return 'sent_register_otp'
        else:
            FLAG_AHOTP = False

            async def resend_otp(d, u, e, p, w):
                await asyncio.sleep(5)
                # sleep ensures invalid otp has been removed from cache
                await self.send_register_otp(d, u, e, p, w)

            for code in self.__register_cache:
                _shrt: OTPCacheDict = self.__register_cache[code]

                if _shrt['email'] == email and _shrt['displayname'] == displayname and _shrt['username'] == username \
                        and _shrt['password'] == password:
                    FLAG_AHOTP = True
                    # check if there even is any otp code for the user
                    # check if otp is expired
                    if datetime.datetime.now() >= _shrt['datetime']:
                        # expired

                        asyncio.create_task(resend_otp(displayname, username, email, password, websocket))

                        return {
                            "id": -1,
                            "error": "register",
                            "code": 5,
                            "message": "OTP code Expired, a new code has been sent!"
                        }

            if not FLAG_AHOTP:
                # send an otp code to user as previous has expired.
                asyncio.create_task(resend_otp(displayname, username, email, password, websocket))

                return {
                    "id": -1,
                    "error": "register",
                    "code": 5,
                    "message": "OTP code Expired, a new code has been sent!"
                }

            data = self.__register_cache.get(otp, None)
            # first check if any of the otp codes in the data match the email
            if not data:
                return {
                    "id": -1,
                    "error": "register",
                    "code": 2,
                    "message": "Invalid OTP code"
                }

            if username != data['username'] or displayname != data['displayname'] \
                    or password != data['password'] or email != data['email']:
                return {
                    "id": -1,
                    "error": "register",
                    "code": 3,
                    "message": "invalid otp code"
                }
                # this is to make sure another user didn't just guess an OTP which they didn't validate for

            # CREATE USER
            query = "INSERT INTO USER VALUES (?, ?, ?, ?, ?, ?)"
            # display name, username, email, password, friends, last_game_id
            await self.run_sql(query, username, displayname, email, password, '', 0)
            # CREATE STATS
            query = "INSERT INTO STATS VALUES (?, ?, ?, ?, ?, ?)"
            await self.run_sql(query, username, 0, 0, 0, 0, 0)

            query = """
                SELECT USER.USERNAME, USER.DISPLAYNAME, USER.EMAIL, USER.FRIENDS, USER.LAST_GAME_ID,
                STATS.TOTAL_MINUTES, STATS.GAMES_PLAYED, STATS.GAMES_WON, STATS.TOTAL_KILLS, STATS.TOTAL_DEATHS
                FROM USER JOIN STATS ON USER.USERNAME = STATS.USERNAME WHERE USER.USERNAME = ? AND USER.PASSWORD = ?
                """
            res = await self.run_sql(query, username, password, ret='one', ret_type='dict')
            if not res:
                return {'status': False, 'authentication': None, 'data': {}}
            return {
                'status': True,
                'authentication': encrypt(generate_snowflake() + self.__server.salt),
                'data': {k.lower(): v for k, v in res.items()}
            }



    async def update_password(self, username: str, email: str, new_password: str, otp_code: int,
                              websocket: websockets.WebSocketClientProtocol) -> Dict:
        """
        updates a password if the correct OTP code is provided, an otp code is sent when a user clicks forgot password
        Notifies the server that the password has been reset!
        :returns: None
        """

        _ = self.is_rlimited(websocket)
        if _:
            _ = await self.notify_rlimit(websocket)
            if _:
                return {
                    "status": False,
                    "error": "ratelimit",
                    "id": -1,
                    "message": "You are being RateLimited."
                }
        else:
            await self.maybe_rlimit(websocket)

        details: OTPCacheDict = self.__fpwd_otp_cache.get(otp_code)
        if not details:
            # invalid OTP code
            return {
                "status": False,
                "error": "update_password",
                "id": -1,
                "message": "Invalid OTP code"
            }
        if details['username'] == username and details['email'] == email:
            query = "UPDATE USER SET PASSWORD = ? WHERE USERNAME = ? AND EMAIL = ?"
            await self.run_sql(query, new_password, username, email)
            return {
                "status": True,
            }  # this prompts the server to go back to the login menu
        else:
            return {
                "status": False,
                "error": "update_password",
                "id": -1,
                "message": "Invalid Username, Password or OTP code"
            }

    """ OTP related functions """

    def find_otp_for(self, _for: Literal['register', 'forgot_password'], username: str, email: str,
                     displayname: Optional[str] = None, password: Optional[str] = None) -> None | int:
        """ Finds the OTP code for a user with that email with optional arguments for displayname and password """
        if _for == 'register':
            for code in self.__register_cache:
                _shrt: OTPCacheDict = self.__register_cache[code]

                if _shrt['email'] == email and _shrt['displayname'] == displayname and _shrt['username'] == username \
                        and _shrt['password'] == password:
                    return code
        elif _for == 'forgot_password':
            for code in self.__fpwd_otp_cache:
                _shrt: OTPCacheDict = self.__fpwd_otp_cache[code]

                if _shrt['email'] == email and _shrt['username'] == username:
                    return code

    async def send_register_otp(self, displayname: str, username: str, email: str,
                                password: str, websocket: websockets.WebSocketClientProtocol) -> None:
        """Generates and sends a unique 6-digit OTP to the client and email for registration"""

        _ = self.find_otp_for('register', username, email, displayname, password)
        if _:
            del self.__register_cache[_]  # invalidate the old code, as they requested for a new one
        iterations = 0
        while True:
            otp_code: int = int(''.join(random.SystemRandom().choices(string.digits, k=6)))
            iterations += 1
            if iterations > 99_000:
                break
            if otp_code not in self.__register_cache.values():
                break

        future_5m = datetime.datetime.now() + datetime.timedelta(minutes=5)
        self.__register_cache[otp_code]: OTPCacheDict = {
            'datetime': future_5m,
            'displayname': displayname,
            'username': username,
            'email': email,
            'password': password,
        }
        await self.send_otp_email(username, email, otp_code)
        await websocket.send(dumps({"notify": "sent_register_otp", "id": -2, "exp": future_5m.timestamp()}))

    async def send_fpwd_otp(self, username: str, email: str, websocket: websockets.WebSocketClientProtocol) -> Dict:
        """Generates and sends a unique 6-digit OTP to the client and email to reset a password"""

        _ = self.is_rlimited(websocket)
        if _:
            _ = await self.notify_rlimit(websocket)
            if _:
                return {
                    "status": False,
                    "error": "ratelimit",
                    "id": -1,
                    "message": "You are being RateLimited."
                }
        else:
            await self.maybe_rlimit(websocket)

        _ = self.find_otp_for('forgot_password', username, email)
        if _:
            del self.__fpwd_otp_cache[_]  # invalidate the old code, as they requested for a new one

        query = "SELECT USER.USERNAME, USER.EMAIL FROM USER WHERE USER.USERNAME = ? AND USER.EMAIL = ?"
        res = await self.run_sql(query, *[username, email], ret='one', ret_type='dict')
        if not res:
            return {
                "status": False,
                "error": "sent_fpwd_code",
                "id": -1,
                "message": "Invalid account credentials"
            }
        iterations = 0
        while True:
            otp_code: int = random.SystemRandom().randint(100_000, 999_999)
            iterations += 1
            if iterations > 99_000:
                break
            if otp_code not in self.__register_cache.values():
                break

        future_5m = datetime.datetime.now() + datetime.timedelta(minutes=5)
        self.__fpwd_otp_cache[otp_code]: OTPCacheDict = {
            'datetime': future_5m,
            'username': username,
            'email': email,
        }
        await self.send_otp_email(username, email, otp_code)
        await websocket.send(dumps({"notify": "sent_fpwd_otp", "id": -2, "exp": future_5m.timestamp()}))
        return {
            "status": True,
        }

    async def send_otp_email(self, username: str, email: str, otp_code: int) -> None:
        """Sends the OTP code to the provided email address using Gmail's SMTP server."""
        subject = 'Authentication Code [TheFall]'
        body = f"Hello {username}\nYour One Time Password is: {otp_code}\nThis code will expire in 5 minutes."
        message = MIMEText(body)
        message['Subject'] = subject
        message['From'] = self.__sender_email
        message['To'] = email

        try:
            if not self.__mail_server.is_connected:
                if self.__mail_server._connect_lock and self.__mail_server._connect_lock.locked():
                    self.__mail_server.close()
                await self.__mail_server.connect()
            await self.__mail_server.send_message(message)
        except aiosmtplib.SMTPException as e:
            if not self.__mail_server.is_connected:
                if self.__mail_server._connect_lock and self.__mail_server._connect_lock.locked():
                    self.__mail_server.close()
                await self.__mail_server.connect()
            await self.__mail_server.login(self.__sender_email, self.__sender_password)

            # Retry sending the email
            try:
                await self.__mail_server.send_message(message)
            except Exception:
                pass

    """ FRIENDS """

    async def get_friends_for(self, user: str, token: Optional[str] = None, check_token: bool = True) -> Dict:
        """ Returns the friends for a user """
        if check_token:
            if not token:
                return {
                    "id": -1,
                    "error": "authentication",
                    "code": 1,
                    "message": "Invalid token"
                }
            else:
                response = self.__server.validate_authentication(user, token)
                if not isinstance(response, Root):
                    return response

        query = "SELECT FRIENDS FROM USER WHERE USERNAME = ?", user
        result = await self.run_sql(*query, ret='one', ret_type='dict')
        if result:
            if result['FRIENDS']:
                result['FRIENDS'] = result['FRIENDS'].split(', ')
                return result
        return {'FRIENDS': []}

    async def get_inbound_requests(self, to_username: str, token: str,
                                   websocket: websockets.WebSocketClientProtocol) -> Dict:
        """ returns all friend requests sent to the user
            errors:
                invalid token
                ratelimited
        """
        # check if authentication token matches user
        _ = self.is_rlimited(websocket)
        if _:
            _ = await self.notify_rlimit(websocket)
            if _:
                return {
                    'error': 'ratelimit',
                    'id': -1,
                    'message': 'You are being ratelimited!',
                }
        else:
            await self.maybe_rlimit(websocket)

        response = self.__server.validate_authentication(to_username, token, websocket)
        if not isinstance(response, Root):
            return response

        query = "SELECT FROM_USER FROM FRIEND_REQUEST WHERE TO_USER == ?", to_username
        result = await self.run_sql(*query, ret='all', ret_type='list')
        if result:
            result = list(chain.from_iterable(result))
        return {'result': result}

    async def get_outbound_requests(self, from_username: str, token: str,
                                    websocket: websockets.WebSocketClientProtocol) -> Dict:
        """ returns all friend requests sent by user error codes:
                1 -> invalid token
                2 -> ratelimited
        """

        _ = self.is_rlimited(websocket)
        if _:
            _ = await self.notify_rlimit(websocket)
            if _:
                return {
                    'error': 'ratelimit',
                    'id': -1,
                    'message': 'You are being ratelimited!',
                }
        else:
            await self.maybe_rlimit(websocket)

        # check if authentication token matches user
        response = self.__server.validate_authentication(from_username, token, websocket)
        if not isinstance(response, Root):
            return response

        query = "SELECT TO_USER FROM FRIEND_REQUEST WHERE FROM_USER = ?", from_username
        result = await self.run_sql(*query, ret='all', ret_type='list')
        if result:
            result = list(chain.from_iterable(result))
        return {'result': result}

    async def notify_friends_update(self, username: str, with_user: str, *, event: Literal['added', 'removed']):
        filtered = dict(
            filter(lambda item: item[1].username == username, self.__server.clients_auth.items())
        )
        """ Sends a notification when a new friend event occurs"""
        for ws in filtered:  # type: websockets.WebSocketClientProtocol
            # add the data to the client auth
            if event == 'added':
                if with_user not in filtered[ws].friends:
                    filtered[ws].friends.append(with_user)
            elif event == 'removed':
                if with_user in self.__server.clients_auth[ws].friends:
                    filtered[ws].friends.remove(with_user)
            await ws.send(dumps({
                "notify": "on_friends_update",
                "id": -2,
                "friend": with_user,
                "event": event
            }).encode())

    async def add_friend(self, from_user: str, to_user: str, from_user_token: str,
                         websocket: websockets.WebSocketClientProtocol) -> Dict:
        """ This function is used to send requests and accept requests.
        error codes:
                1 -> Invalid Authorisation
                2 -> Ratelimited
                3 -> Conflict
        """
        # first check if from_user token is correct

        _ = self.is_rlimited(websocket)
        if _:
            _ = await self.notify_rlimit(websocket)
            if _:
                return {
                    'error': 'ratelimit',
                    'message': 'You are being ratelimited!',
                    'id': -1,
                }
        else:
            await self.maybe_rlimit(websocket)

        _root: Dict | Root = self.__server.validate_authentication(from_user, from_user_token, websocket)
        if not isinstance(_root, Root):
            return _root
        _root: Root

        # check if they are already friends
        if to_user in _root.friends:
            return {
                "id": -1,
                "error": "add_friend",
                "code": 3,
                "message": f"You\'r already friends with \"{to_user}\""
            }

        # check if from_user has already sent them a request
        query = "SELECT * FROM FRIEND_REQUEST WHERE FROM_USER = ? AND TO_USER =? ", from_user, to_user
        result = await self.run_sql(*query, ret='one', ret_type='list')
        if result:
            return {'result': 'sent'}

        # check if to_user has already sent them a request
        query = "SELECT * FROM FRIEND_REQUEST WHERE FROM_USER = ? AND TO_USER = ?", to_user, from_user
        result = await self.run_sql(*query, ret='one', ret_type='list')
        if result:
            # accept this request.
            to_user_frnds = (await self.get_friends_for(to_user, check_token=False))['FRIENDS']
            to_user_frnds.append(from_user)
            from_user_frnds = _root.friends
            from_user_frnds.append(to_user)
            delete_query = "DELETE FROM FRIEND_REQUEST WHERE FROM_USER = ? and TO_USER = ?", to_user, from_user
            update_query = "UPDATE USER SET FRIENDS = ? WHERE USERNAME = ?"
            await asyncio.gather(
                self.run_sql(update_query, *[", ".join(to_user_frnds), to_user]),
                self.run_sql(update_query, *[", ".join(from_user_frnds), from_user])
            )

            await self.run_sql(*delete_query)
            await self.notify_friends_update(to_user, from_user, event='added')

            return {'result': 'accepted', 'with': to_user}

        else:
            # we are going to send the request.
            insert_query = "INSERT INTO FRIEND_REQUEST (FROM_USER, TO_USER) VALUES (?, ?)"
            await self.run_sql(insert_query, from_user, to_user)
            return {'result': 'sent'}

    async def remove_friend(self, from_user: str, with_user: str, from_user_token: str,
                            websocket: websockets.WebSocketClientProtocol) -> Dict:
        """ This function is used to remove friend requests and users as friends
        errors:
            Invalid Authorization
            Ratelimited
            Conflict
        """

        _ = self.is_rlimited(websocket)
        if _:
            _ = await self.notify_rlimit(websocket)
            if _:
                return {
                    'error': 'ratelimit',
                    'message': 'You are being ratelimited!',
                    'id': -1,
                }
        else:
            await self.maybe_rlimit(websocket)

        _root: Dict | Root = self.__server.validate_authentication(from_user, from_user_token, websocket)
        if not isinstance(_root, Root):
            return _root
        _root: Root

        # check if it is a request

        query = "SELECT * FROM FRIEND_REQUEST WHERE FROM_USER = ? AND TO_USER = ? ", from_user, with_user
        result = await self.run_sql(*query, ret='one', ret_type='list')

        if result:
            delete_query = "DELETE FROM FRIEND_REQUEST WHERE FROM_USER = ? and TO_USER = ?", from_user, with_user
            await self.run_sql(*delete_query)

            return {'result': 'removed', 'with': with_user}

        else:
            # check if they are friends.
            to_user_frnds = (await self.get_friends_for(with_user, check_token=False))['FRIENDS']
            if from_user in to_user_frnds:
                to_user_frnds.remove(from_user)
                from_user_frnds = _root.friends
                from_user_frnds.remove(with_user)
                update_query = "UPDATE USER SET FRIENDS = ? WHERE USERNAME = ?"
                await asyncio.gather(
                    self.run_sql(update_query, *[", ".join(to_user_frnds), with_user]),
                    self.run_sql(update_query, *[", ".join(from_user_frnds), from_user])
                )
                await self.notify_friends_update(with_user, from_user, event='removed')
                return {'result': 'removed', 'with': with_user}
            else:
                return {
                    'error': 'remove_request',
                    'id': -1,
                    'message': f'You\'re not friends with "{with_user}"'
                }

    async def add_game_id(self, user: str, game_id: str) -> None:
        """ Sets the last_game_id to a user when they leave a game, so they can be prompted to rejoin the game """
        query = "UPDATE USER SET LAST_GAME_ID = ? WHERE USERNAME = ?", game_id, user
        await self.run_sql(*query)

    async def save_stats(self, game: Game) -> None:
        """ Saves the stats from a game and updates all the player's stats accordingly"""
        winnings = ', '.join(game.stats['winnings'])
        _rc, _bc = winnings.count('red'), winnings.count('blue')
        final_winner = ['red', 'blue']  # draw
        if _rc > _bc:
            final_winner = ['red']
        elif _bc > _rc:
            final_winner = ['blue']

        for player in game.stats['players']:
            query = "SELECT * FROM STATS WHERE USERNAME = ?", player
            result = await self.run_sql(*query, ret='one', ret_type='dict')
            _shrt = game.stats['players'][player]
            if game.players[player]['team'] in final_winner:
                result['GAMES_WON'] += 1
            result['TOTAL_KILLS'] += _shrt['kills']
            result['TOTAL_DEATHS'] += _shrt['deaths']
            result['TOTAL_MINUTES'] += _shrt['playtime']
            update_query = """
                UPDATE STATS SET GAMES_WON = ?, TOTAL_KILLS = ?, TOTAL_DEATHS = ?, TOTAL_MINUTES = ? WHERE USERNAME = ?
                """
            await self.run_sql(
                update_query, result['GAMES_WON'], result['TOTAL_KILLS'], result['TOTAL_DEATHS'],
                result['TOTAL_MINUTES'], player
            )
