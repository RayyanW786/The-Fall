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

from typing import Dict, List, Any, Literal, TYPE_CHECKING, Tuple, Callable, Optional, NoReturn

from .utils import InputBox, Button, Text, DynamicText
from fuzzywuzzy import fuzz
from .constants import colours
import re
import datetime
from Game.utils import human_timedelta, chunked
import asyncio
from ..Networking.client import User, Lobby, GameInfo
from .game import Game

if TYPE_CHECKING:
    from screen import Screen

# Email Regex Taken from https://stackabuse.com/python-validate-email-address-with-regular-expressions-regex/
EMAIL_RE = re.compile(r'([A-Za-z0-9]+[.-_])*[A-Za-z0-9]+@[A-Za-z0-9-]+(\.[A-Z|a-z]{2,})+')


class Handler(object):
    """This class handles many of the pygame event loop for the buttons and inputboxes (views)"""

    def __init__(self, screen: Screen):
        self.__screen: Screen = screen
        self.__registered_views: bool = False
        self.__register_submit: bool = False
        self.__data: Dict[str, Any] = {}
        self.__started_game_check: bool = False

    def dynamic(self, factor: float, _type: Literal['w', 'h']) -> int:
        """ Allows for scaling to the specific screen size """
        ret = factor * 100  # by default
        if _type == 'w':
            ret = factor * self.__screen.win_size[0]
        elif _type == 'h':
            ret = factor * self.__screen.win_size[1]
        return int(ret)

    @property
    def registered_views(self) -> bool:
        return self.__registered_views

    @registered_views.setter
    def registered_views(self, value: bool) -> None:
        self.__registered_views = value

    async def delete_alert(self, _insts: Dict[str, Text | DynamicText], sleep_until: int = 5) -> None:
        await asyncio.sleep(sleep_until)
        for key in _insts:
            if key not in self.__screen.get_task_keys('text'):
                continue
            if self.__screen.get_task('text', key) is _insts[key]:
                self.__screen.remove_task('text', key)

    async def register_step1_checks(self) -> bool | Dict:
        """ Handles the first step to for register """
        inputbxs: Dict[str, InputBox] = self.__screen.get_tasks('inputboxes')
        displayname = inputbxs.get('displayname', None)
        username = inputbxs.get('username', None)
        password = inputbxs.get('password', None)
        confpass = inputbxs.get('confirm_password', None)
        email = inputbxs.get('email', None)
        flags: List[bool, ...] = [False, False, False, False, False]
        # one for each attribute in order of definition
        total_feedback: Dict[str, List] = {'dpn': [], 'usn': [], 'pwd': [], 'em': []}

        if displayname is not None:
            if not displayname.text:
                total_feedback['dpn'].append("displayname is a required field and is missing!")

            elif len(displayname.text) < 2 or len(displayname) > 10:
                total_feedback['dpn'].append('displayname must be bigger than 2 and lower than 10')

            elif displayname.text:
                flags[0] = True

        if username is not None:
            if username.text:
                res = await self.__screen.client.username_lookup(str(username))
                if res:
                    total_feedback['usn'].append("Username Taken!")
                else:
                    flags[1] = True
            else:
                total_feedback['usn'].append("Username is a required field and is missing!")

        if password is not None and confpass is not None:
            pwd_feedback: List[str] = []
            if not password.text or not confpass.text:
                total_feedback['pwd'].append('Password is a required field and is missing!')

            elif confpass.text == password.text:

                password_flags = [False, False, False, False, False]
                # should be True, True, True, True, True
                # order being digit check, uppercase check, lowercase check, ratio check, length check
                if len(password) >= 8:
                    password_flags[4] = True
                if fuzz.ratio(username.text.lower(), password.text.lower()) < 70:
                    password_flags[3] = True
                for chr in password:  # NOQA: ignore shadow of chr
                    if all(password_flags):  # if all the flags are True it breaks out of the loop
                        break
                    if chr.isdigit():  # checks for digits
                        password_flags[0] = True
                    if chr.isupper():  # checks for uppercase letter
                        password_flags[1] = True
                    if chr.islower():  # checks for lowercase letter
                        password_flags[2] = True
                if not all(password_flags):  # means they are missing something in their password
                    for index, val in enumerate(password_flags):  # we want the index and so we use enumerate
                        if not val:
                            if index == 0:
                                pwd_feedback.append("Password must have at least one digit!")
                            elif index == 1:
                                pwd_feedback.append("Password must have at least one uppercase!")
                            elif index == 2:
                                pwd_feedback.append("Password must have at least one lowercase!")
                            elif index == 3:
                                pwd_feedback.append("Your username cannot be in your password!")
                            elif index == 4:
                                pwd_feedback.append("Your password must be a length of 8 characters or more!")
                    total_feedback['pwd'].extend(pwd_feedback)
                else:
                    flags[2], flags[3] = True, True
            else:
                total_feedback['pwd'].append("Passwords do not match!")

        if email is not None:
            length = len(email.text.lower().strip())
            if not email.text:
                total_feedback['em'].append("Email is a required field and is missing!")
            elif not 5 < length < 30:
                total_feedback['em'].append('Email length should be more than 5 and less than 30')

            elif not re.fullmatch(EMAIL_RE, email.text):
                total_feedback['em'].append('Invalid Email')

            elif len(total_feedback['em']) == 0:
                flags[4] = True

        if not all(flags):
            if total_feedback:
                return total_feedback
            return False
        return True

    async def check(self) -> List | None:
        """ Checks if the screen_config has been initialized """
        if self.__screen.loading:
            return

        screen_conf = self.__screen.screen_config.get('parent', None)

        minor_conf = self.__screen.screen_config.get('minor', None)

        if not self.registered_views:
            self.register_views(screen_conf, minor_conf)
            self.registered_views = True

    async def register_step1_continue(self) -> None:
        """ Called via button, allows the user to continue with registration """
        res = await self.register_step1_checks()
        if res is True:
            await self.init_register_step2()
        else:
            friendly: Dict[str, str] = {
                'dpn': 'displayname',
                'usn': 'username',
                'pwd': 'password',
                'em': 'email'
            }

            # need to copy otherwise error dict changed size error will occur

            for potential in self.__screen.get_tasks('text').copy():
                if potential + 'main' in [friendly.values()]:
                    self.__screen.remove_task('text', potential)
                elif 'fb_' in potential:
                    self.__screen.remove_task('text', potential)

            y_inc: int = 0
            x_inc: int = self.dynamic(0.7, 'w')

            for field in res:
                if res[field]:
                    for idx, fb in enumerate(res[field]):
                        y_inc += 50
                        self.__screen.add_task(
                            'text',
                            friendly[field] + f'fb_{idx}',
                            Text(x_inc, y_inc, 50, 50, colours['BLACK'], fb)
                        )

    async def init_register_step2(self) -> None:
        """ initializes step 2 for registration """
        ipbx = self.__screen.get_tasks('inputboxes')

        self.__data['register'] = {
            'displayname': ipbx['displayname'],
            'username': ipbx['username'],
            'password': ipbx['password'],
            'email': ipbx['email']
        }
        self.__screen.clear_tasks()
        _temp = {k: str(v) for k, v in self.__data['register'].items()}
        await self.__screen.client.register(**_temp)  # This will send an OTP code
        self.__data['register']['otp_expdt'] = self.__screen.client.notifs.get(
            'register_s2', {}
        ).get(
            'exp', (datetime.datetime.now() + datetime.timedelta(minutes=5))
        )

        class OTPTimer(DynamicText):
            def __init__(self, x: int, y: int, width: int, height: int, colour: Tuple, text: str, fmt_dict: dict,
                         size: int = 28):
                super().__init__(x, y, width, height, colour, text, fmt_dict, size)

            def fmt_text(self, text: str) -> str:
                return text.format(dt=self._fmt_dict['func'](self._fmt_dict['dt'].get(
                    'register_s2', {}
                ).get(
                    'exp', datetime.datetime.now())
                ))

        self.__screen.add_task('text', 'otp_info', OTPTimer(
            self.dynamic(0.45, 'w'), self.dynamic(0.1, 'h'),
            100, 100,
            colours['BLACK'],
            "A One Time Password Code was sent to your email, the code will expire in {dt}",
            {"dt": self.__screen.client.notifs, 'func': human_timedelta})
                               )
        self.__screen.add_task('text', 'enter_code', Text(
            self.dynamic(0.025, 'w'), self.dynamic(0.45, 'h'),
            250, 250,
            colours['BLACK'],
            f"Enter Code:", size=40)
                               )
        self.__screen.add_task('buttons', 'create', Button(
            self.dynamic(0.7, 'w'), self.dynamic(0.45, 'h'),
            250, 250,
            "Create Account",
            colours['BLURPLE'], colours['BLACK'],
            action=self.submit_register)
                               )
        self.__screen.add_task('inputboxes', 'otp_inp', InputBox(
            self.dynamic(0.25, 'w'), self.dynamic(0.57, 'h'),
            250, 100,
            'otp_code',
            max_length=6)
                               )

    async def submit_register(self) -> None:
        """ this is the action for the final submit button to register an account and
        makes sure the otp code is valid and not expired.
        """

        try:
            self.__data['register']['otp'] = int(str(self.__screen.get_task('inputboxes', 'otp_inp')))
        except ValueError as e:
            self.__screen.logger.warning(f"suppressing error {e.__class__.__name__}: {e}")
            inst = Text(
                self.dynamic(0.4, 'w'), self.dynamic(0.3, 'h'),
                100, 100,
                colours['BLACK'],
                f"Account Creation Unsuccessful: Invalid OTP code"
            )
            self.__screen.add_task('text', 'inform_err', inst)
            asyncio.create_task(self.delete_alert({'inform_err': inst}))

        _temp = {k: str(v) if type(v) not in [int, str] else v for k, v in self.__data['register'].items()}
        del _temp['otp_expdt']
        response = await self.__screen.client.register(**_temp)
        if type(response) == dict:
            class CountDown(DynamicText):
                def __init__(self, x: int, y: int, width: int, height: int, colour: Tuple, text: str,
                             fmt_dict: dict,
                             size: int = 28):
                    super().__init__(x, y, width, height, colour, text, fmt_dict, size)

                def fmt_text(self: DynamicText, text: str) -> str:
                    return text.format(dt=self._fmt_dict['func'](self._fmt_dict['dt']), msg=self._fmt_dict['msg'])

            if response['code'] in [1, 4]:
                self.__screen.clear_tasks()

                self.__screen.add_task('text', 'go_back', CountDown(
                    self.dynamic(0.45, 'w'), self.dynamic(0.4, 'h'),
                    100, 100,
                    colours['BLACK'],
                    "Account Creation Unsuccessful: {msg}. You will be redirected to the main menu automatically "
                    "in {dt}",
                    {
                        "dt": datetime.datetime.now() + datetime.timedelta(seconds=5),
                        'func': human_timedelta,
                        'msg': response['message']
                    }
                ))
                await asyncio.sleep(5)
                # go back to the main menu after 10 seconds
                self.__data = {}
                self.__screen.clear_tasks()
                self.__screen.set_screen_minor(None)
                self.registered_views = False
            elif response['code'] in [2, 3, 5]:
                inst = Text(
                    self.dynamic(0.4, 'w'), self.dynamic(0.3, 'h'),
                    100, 100,
                    colours['BLACK'],
                    f"Account Creation Unsuccessful: {response['message']}"
                )
                self.__screen.add_task('text', 'inform_err', inst)

                asyncio.create_task(self.delete_alert({'inform_err': inst}, sleep_until=7))

            elif response['code'] in [6]:
                # ratelimited
                data = self.__screen.client.notifs.get('ratelimit')
                if not data:
                    return

                inst = CountDown(
                    self.dynamic(0.4, 'w'), self.dynamic(0.3, 'h'),
                    100, 100,
                    colours['BLACK'],
                    "Account Creation Unsuccessful: {msg} Retry in {dt}",
                    {
                        "dt": datetime.datetime.fromtimestamp(data['dt']),
                        'func': human_timedelta,
                        'msg': data['message']
                    }

                )
                self.__screen.add_task('text', 'inform_err', inst)

                asyncio.create_task(self.delete_alert({'inform_err': inst}, sleep_until=15))

        else:

            class CountDown(DynamicText):
                def __init__(self, x: int, y: int, width: int, height: int, colour: Tuple, text: str,
                             fmt_dict: dict,
                             size: int = 28):
                    super().__init__(x, y, width, height, colour, text, fmt_dict, size)

                def fmt_text(self, text: str) -> str:
                    return text.format(dt=self._fmt_dict['func'](self._fmt_dict['dt']))

            if response is False:
                inst = Text(
                    self.dynamic(0.45, 'w'), self.dynamic(0.3, 'h'),
                    100, 100,
                    colours['BLACK'],
                    "Account Creation Unsuccessful: Unable to establish a connection to onboarding"
                    " service. See your console for more information", size=22)

                self.__screen.add_task('text', 'inform_err', inst)
                asyncio.create_task(self.delete_alert({'inform_err': inst}, sleep_until=15))
                return

            self.__screen.clear_tasks()
            inst = CountDown(
                self.dynamic(0.4, 'w'), self.dynamic(0.3, 'h'),
                100, 100,
                colours['BLACK'],
                "Account Creation successful! You will be placed into the main menu in {dt}",
                {
                    'dt': datetime.datetime.now() + datetime.timedelta(seconds=10),
                    'func': human_timedelta
                }
            )

            self.__screen.add_task('text', 'created', inst)
            asyncio.create_task(self.delete_alert({'inform_err': inst}, sleep_until=10))
            await self.MainUI()

    async def submit_login(self) -> None:
        """ Called by button click, handles login """
        ipbx = self.__screen.get_tasks('inputboxes')

        self.__data['login'] = {
            'username': ipbx['username'],
            'password': ipbx['password'],
        }

        _temp = {k: str(v) for k, v in self.__data['login'].items()}
        response = await self.__screen.client.login(**_temp)

        if not response:
            rl_data = self.__screen.client.notifs.get('ratelimit')
            if rl_data and rl_data['dt'] > datetime.datetime.now().timestamp():
                class CountDown(DynamicText):
                    def __init__(self, x: int, y: int, width: int, height: int, colour: Tuple, text: str,
                                 fmt_dict: dict,
                                 size: int = 28):
                        super().__init__(x, y, width, height, colour, text, fmt_dict, size)

                    def fmt_text(self, text: str) -> str:
                        return text.format(dt=self._fmt_dict['func'](self._fmt_dict['dt']), msg=self._fmt_dict['msg'])

                inst = CountDown(
                    self.dynamic(0.6, 'w'), self.dynamic(0.25, 'h'),
                    100, 100,
                    colours['BLACK'],
                    "Login Failed: {msg} Retry in {dt}",
                    {
                        "dt": datetime.datetime.fromtimestamp(rl_data['dt']),
                        'func': human_timedelta,
                        'msg': rl_data['message']
                    }

                )

                self.__screen.add_task('text', 'login_failure', inst)

                asyncio.create_task(self.delete_alert({'login_failure': inst}))
            else:

                inst = Text(
                    self.dynamic(0.6, 'w'), self.dynamic(0.25, 'h'),
                    100, 100,
                    colours['BLACK'],
                    f"Login Error: Incorrect Username or Password!"
                )
                self.__screen.add_task('text', 'login_failure', inst)

                asyncio.create_task(self.delete_alert({'login_failure': inst}))

        else:
            self.__screen.clear_tasks()
            inst = Text(
                self.dynamic(0.4, 'w'), self.dynamic(0.3, 'h'),
                100, 100,
                colours['BLACK'],
                f"You have logged in successfully"
            )
            self.__screen.add_task('text', 'greet', inst)
            await asyncio.sleep(2)
            self.__screen.clear_tasks()
            await self.MainUI()

    async def add_friend(self, user: User) -> None:
        """ Allows the user to send / accept friend requests """
        response = await self.__screen.client.add_friend(user)
        if response.get('error'):
            if response.get('code', 0) == 2:
                response['message'] = response['message'] + ' Try again in ' + human_timedelta(
                    datetime.datetime.fromtimestamp(
                        self.__screen.client.notifs.get('ratelimit', {}).get('dt', datetime.datetime.now().timestamp()))
                )

            _inst = Text(
                self.dynamic(0.4, 'w'), self.dynamic(0.25, 'h'), 100, 100,
                colours['BLACK'], response['message']
            )
            self.__screen.add_task('text', 'output', _inst)
            asyncio.create_task(self.delete_alert({'output': _inst}))
        else:
            _with_user = response.get('with')
            if _with_user:
                text = f'You are now friends with "{_with_user}"'
            else:
                text = f'Send a friend request to "{user.username}"'
            _inst = Text(
                self.dynamic(0.4, 'w'), self.dynamic(0.25, 'h'), 100, 100,
                colours['BLACK'], text
            )
            self.__screen.add_task('text', 'output', _inst)
            asyncio.create_task(self.delete_alert({'output': _inst}, sleep_until=10))

    async def remove_friend(self, user: User) -> None:
        """ Allows a user to remove a friend or deny a friend request """
        response = await self.__screen.client.remove_friend(user)
        if response.get('error'):
            if response.get('code', 0) == 2:
                response['message'] = response['message'] + ' Try again in ' + human_timedelta(
                    datetime.datetime.fromtimestamp(
                        self.__screen.client.notifs.get('ratelimit', {}).get('dt', datetime.datetime.now().timestamp()))
                )

            _inst = Text(
                self.dynamic(0.4, 'w'), self.dynamic(0.25, 'h'), 100, 100,
                colours['BLACK'], response['message']
            )
            self.__screen.add_task('text', 'output', _inst)
            asyncio.create_task(self.delete_alert({'output': _inst}))
        else:
            _with_user = response.get('with')
            if _with_user:
                text = f'You are no longer friends with "{_with_user}"'
            else:
                text = f'You are not Friends with "{_with_user}"'
            _inst = Text(
                self.dynamic(0.4, 'w'), self.dynamic(0.25, 'h'), 100, 100,
                colours['BLACK'], text
            )
            self.__screen.add_task('text', 'output', _inst)
            asyncio.create_task(self.delete_alert({'output': _inst}, sleep_until=10))

    async def view_profile(self, align_left: Optional[bool] = False) -> None:
        """ handles the viewing profile functionality
            align_left: bool = False -> weather the profile should be displaced in the centre or on the left side
        """
        self.__screen.loading = True

        user_box = self.__screen.get_task('inputboxes', 'query_user')
        if not user_box:
            self.__screen.screen_config['loading'] = False
            _inst = Text(
                self.dynamic(0.4 if not align_left else 0.15, 'w'), self.dynamic(0.25 if not align_left else 0.25, 'h'),
                100, 100, colours['BLACK'], 'User is a required field and is missing!'
            )
            self.__screen.add_task('text', 'output', _inst)
            asyncio.create_task(self.delete_alert({'output': _inst}))

        else:
            user = await self.__screen.client.get_or_fetch_user(str(user_box))
            if not user:
                self.__screen.screen_config['loading'] = False
                _inst = Text(
                    self.dynamic(0.4 if not align_left else 0.15, 'w'),
                    self.dynamic(0.25 if not align_left else 0.25, 'h'),
                    100, 100, colours['BLACK'], f'User "{user_box}" not found!'
                )
                self.__screen.add_task('text', 'output', _inst)
                asyncio.create_task(self.delete_alert({'output': _inst}))
            else:
                # display stats, and show add, remove, close button, invite [if friend]
                user_stats = [
                    f'Username: {user.username}, Displayname: {user.displayname}',
                    f'KD: {user.kd} | Hours Played: {user.hours_played:,} ',
                    f'Games Played: {user.games_played:,} | Games Won: {user.games_won:,}',
                    f'Total Kills: {user.total_kills:,} | Total Deaths: {user.total_deaths}'
                ]
                if user.username == self.__screen.client.root.username:
                    user_stats.insert(0, '      (YOU)       ')
                elif user.username in self.__screen.client.root.friends:
                    user_stats.insert(0, '      (FRIEND)      ')

                y_inc: int = self.dynamic(0.32 if not align_left else 0.3, 'h')
                x_inc: int = self.dynamic(0.4 if not align_left else 0.1, 'w')
                total_idx = len(user_stats)
                for idx, ln in enumerate(user_stats):
                    y_inc += 50
                    ln_txt = Text(
                        x_inc, y_inc, 50, 50, colours['BLACK'], ln, size=22
                    )
                    self.__screen.add_task('text', f'user_stats_{idx}', ln_txt)

                # buttons
                _add_inst = None
                _remove_inst = None  # workaround to not define the buttons twice

                async def _action(user: User, _type: Literal['add', 'remove', 'close']) -> None:
                    nonlocal total_idx
                    nonlocal self
                    nonlocal _add_inst
                    nonlocal _remove_inst

                    if _type == 'add':
                        _add_inst.disabled = True
                        await self.add_friend(user)
                        if user not in outbound_requests:
                            outbound_requests.append(user.username)
                        if user.username != self.__screen.client.root.username \
                                and any([user.username in outbound_requests, user.username in inbound_requests,
                                         user.username in self.__screen.client.root.friends]):
                            _remove_inst.disabled = False
                            if not self.__screen.get_task('buttons', 'remove'):
                                self.__screen.add_task('buttons', 'remove', _remove_inst)

                    elif _type == 'remove':
                        _remove_inst.disabled = True
                        await self.remove_friend(user)
                        if user in outbound_requests:
                            outbound_requests.remove(user.username)
                        if user.username != self.__screen.client.root.username and any([
                            user.username not in self.__screen.client.root.friends,
                            user.username not in outbound_requests]):
                            _add_inst.disabled = False
                            if not self.__screen.get_task('buttons', 'add'):
                                self.__screen.add_task('buttons', 'add', _add_inst)

                    elif _type == 'close':
                        self.__screen.remove_task('buttons', 'close')
                        self.__screen.remove_task('buttons', 'add')
                        self.__screen.remove_task('buttons', 'remove')
                        for idx in range(total_idx + 1):
                            self.__screen.remove_task('text', f'user_stats_{idx}')

                outbound_requests = await self.__screen.client.get_outbound_requests()
                inbound_requests = await self.__screen.client.get_inbound_requests()
                if outbound_requests.get('error'):
                    outbound_requests = {'result': []}
                if inbound_requests.get('error'):
                    inbound_requests = {'result': []}
                outbound_requests = outbound_requests['result']
                inbound_requests = inbound_requests['result']
                self.__screen.loading = False

                add: Button = Button(
                    self.dynamic(0.25 if not align_left else 0.001, 'w'), self.dynamic(0.82, 'h'), 100, 100,
                    'Add', colours['BLURPLE'], colours['WHITE'], user, 'add', action=_action
                )
                _add_inst = add

                close: Button = Button(
                    self.dynamic(0.35 if not align_left else 0.1, 'w'), self.dynamic(0.82, 'h'), 100, 100,
                    'Close', colours['RED'], colours['WHITE'], user, 'close', action=_action
                )
                self.__screen.add_task('buttons', 'close', close)

                remove: Button = Button(
                    self.dynamic(0.45 if not align_left else 0.2, 'w'), self.dynamic(0.82, 'h'), 100, 100,
                    'Remove', colours['BLURPLE'], colours['WHITE'], user, 'remove', action=_action
                )
                _remove_inst = remove

                if user.username != self.__screen.client.root.username and (
                        user.username not in self.__screen.client.root.friends and
                        user.username not in outbound_requests):
                    self.__screen.add_task('buttons', 'add', add)

                elif user.username != self.__screen.client.root.username and any([
                    user.username in outbound_requests, user.username in inbound_requests,
                    user.username in self.__screen.client.root.friends]):
                    self.__screen.add_task('buttons', 'remove', remove)

    def create_paginator(self, entries: List[Any], *, name: str, per_page: int = 5, dy_w: float = 0.35,
                         dy_h: float = 0.65, inc_y: int = 40, entry_size: int = 22) -> NoReturn | Callable:
        """ Creates a paginator which will allow the user to go through the entries with a nice GUI """
        if not entries:
            raise RuntimeError('entries cannot be empty')
        if not self.__data.get('paginator'):
            self.__data['paginator'] = {}
        self.__data['paginator'][name] = {
            "per_page": per_page,
            "total": len(entries),
            "pages": list(chunked(entries, per_page)),
            "current_page": 0,
        }

        def _paginator():
            nonlocal self
            nonlocal dy_w
            nonlocal dy_h
            nonlocal inc_y
            nonlocal entry_size

            data = self.__data['paginator'][name]
            per_page = data['per_page']
            total = data['total']
            pages = data['pages']
            current_page = data['current_page']
            _page = current_page + 1

            if _page == len(pages):
                next_btn: Button = self.__screen.get_task('buttons', f'next_page_{name}')
                next_btn.disabled = True

            if _page == 1:
                previous_btn: Button = self.__screen.get_task('buttons', f'previous_page_{name}')
                previous_btn.disabled = True

            elif _page not in [len(pages), 1]:
                previous_btn: Button = self.__screen.get_task('buttons', f'previous_page_{name}')
                next_btn: Button = self.__screen.get_task('buttons', f'next_page_{name}')
                if previous_btn.disabled:
                    previous_btn.disabled = False
                if next_btn.disabled:
                    next_btn.disabled = False

            _chunk = pages[current_page]
            if len(_chunk) != per_page:
                difference = per_page - len(_chunk)
                _chunk.extend(['' for _ in range(0, difference)])

            y_inc: int = self.dynamic(dy_w, 'h')
            x_inc: int = self.dynamic(dy_h, 'w')
            for idx, entry in enumerate(_chunk):
                y_inc += inc_y
                if entry:
                    ln_txt = Text(
                        x_inc, y_inc, 50, 50, colours['BLACK'], entry, size=entry_size
                    )
                    self.__screen.add_task('text', f'entry_{idx}', ln_txt)
                else:
                    self.__screen.remove_task('text', f'entry_{idx}')

            page_info = Text(
                self.dynamic(0.9, 'w'), self.dynamic(0.85, 'h'), 1, 1,
                colours['BLACK'], f'page {current_page + 1:,}/{len(pages)}'
            )

            self.__screen.add_task('text', f'page_info_{name}', page_info)

            total_entries = Text(
                self.dynamic(0.9, 'w'), self.dynamic(0.9, 'h'), 1, 1,
                colours['BLACK'], f'total entries: {total:,}'
            )
            self.__screen.add_task('text', f'total_entries_{name}', total_entries)

        def increment_page():
            nonlocal self
            data = self.__data['paginator'][name]
            data['current_page'] += 1

        def decrement_page():
            nonlocal self
            data = self.__data['paginator'][name]
            data['current_page'] -= 1

        # Buttons
        previous_button: Button = Button(
            self.dynamic(0.55, 'w'), self.dynamic(0.82, 'h'), 100, 100,
            'previous', colours['BLURPLE'], colours['WHITE'],
             disabled=True, action=decrement_page
        )

        self.__screen.add_task('buttons', f'previous_page_{name}', previous_button)

        def close():
            nonlocal self

            data = self.__data['paginator'][name]
            self.__screen.remove_task('functions', name)
            for idx, _ in enumerate(data['pages'][data['current_page']]):
                self.__screen.remove_task('text', f'entry_{idx}')
            self.__screen.remove_task('text', f'page_info_{name}')
            self.__screen.remove_task('text', f'total_entries_{name}')
            btns = [f'previous_page_{name}', f'close_{name}', f'next_page_{name}']
            for btn in btns:
                self.__screen.remove_task('buttons', btn)

        close_paginator: Button = Button(
            self.dynamic(0.65, 'w'), self.dynamic(0.82, 'h'), 100, 100,
            'close', colours['RED'], colours['WHITE'],
            action=close,
        )
        self.__screen.add_task('buttons', f'close_{name}', close_paginator)

        next_button: Button = Button(
            self.dynamic(0.75, 'w'), self.dynamic(0.82, 'h'), 100, 100,
            'next', colours['BLURPLE'], colours['WHITE'], action=increment_page
        )

        self.__screen.add_task('buttons', f'next_page_{name}', next_button)
        return _paginator

    def remove_paginators(self, names: Optional[List[str]] = None) -> None:
        """ removes all paginators if none specified, otherwise removes requested paginators """
        for k_paginator in self.__data.get('paginator', {}).copy():
            if names and k_paginator not in names:
                continue
            _close_btn: Button = self.__screen.get_task('buttons', f'close_{k_paginator}')
            if _close_btn:
                _close_btn.action()
            del self.__data['paginator'][k_paginator]

    async def friends_paginator(self) -> None:
        """
        Paginates though the list of friends.
        allowing the user to go to the previous, next page or close the paginator
        """
        self.remove_paginators()
        friends = self.__screen.client.root.friends
        if not friends:
            text = Text(
                self.dynamic(0.7, 'w'), self.dynamic(0.45, 'h'), 100, 100,
                colours['BLACK'], 'You don\'t have any friend\'s yet!'
            )
            self.__screen.add_task('text', 'friend_lst', text)
            asyncio.create_task(self.delete_alert({'friend_lst': text}))
        else:

            _paginator = self.create_paginator(friends, name='friends')
            self.__screen.add_task('functions', 'friends', [_paginator])

    async def inbound_paginator(self) -> None:
        """ paginates though list of inbound requests sent to the user """
        self.remove_paginators()
        inbound_requests = await self.__screen.client.get_inbound_requests()
        if inbound_requests.get('error'):
            inbound_requests = {'result': []}
        inbound_requests = inbound_requests['result']
        if inbound_requests:
            _paginator = self.create_paginator(inbound_requests, name='inbound')
            self.__screen.add_task('functions', 'inbound', [_paginator])
        else:
            _inst = Text(
                self.dynamic(0.4, 'w'), self.dynamic(0.25, 'h'), 100, 100,
                colours['BLACK'], 'You have no inbound requests!'
            )
            self.__screen.add_task('text', 'output', _inst)
            asyncio.create_task(self.delete_alert({'output': _inst}))

    async def outbound_paginator(self) -> None:
        """ List of outbound requests sent by the user """
        self.remove_paginators()
        outbound_requests = await self.__screen.client.get_outbound_requests()
        if outbound_requests.get('error'):
            outbound_requests = {'result': []}
        outbound_requests = outbound_requests['result']
        if outbound_requests:
            _paginator = self.create_paginator(outbound_requests, name='outbound')
            self.__screen.add_task('functions', 'outbound', [_paginator])
        else:
            _inst = Text(
                self.dynamic(0.4, 'w'), self.dynamic(0.25, 'h'), 100, 100,
                colours['BLACK'], 'You have no outbound requests!'
            )
            self.__screen.add_task('text', 'output', _inst)
            asyncio.create_task(self.delete_alert({'output': _inst}))

    async def requests(self, redirect: Optional[List] = None) -> None:
        """ Handles the request button functionality and provides a back button to exit """
        self.__screen.remove_task('buttons', 'friends_list')
        self.__screen.remove_task('buttons', 'requests')

        self.remove_paginators()

        inbound: Button = Button(
            self.dynamic(0.05, 'w'), self.dynamic(0.5, 'h'), 100, 47, 'Inbound',
            colours['FAWN'], colours['WHITE'], action=self.inbound_paginator
        )
        self.__screen.add_task('buttons', 'inbound_list', inbound)

        outbound: Button = Button(
            self.dynamic(0.05, 'w'), self.dynamic(0.575, 'h'), 100, 47, 'Outbound',
            colours['JADE'], colours['WHITE'], action=self.outbound_paginator
        )

        self.__screen.add_task('buttons', 'outbound_list', outbound)

        back: Button = Button(
            self.dynamic(0.05, 'w'), self.dynamic(0.65, 'h'), 100, 100, 'Back',
            colours['PUCE'], colours['WHITE'], redirect, action=self.friends_view
        )
        self.__screen.add_task('buttons', 'back', back)

    async def friends_view(self, redirect: Optional[List] = None) -> None:
        """" handles all friend functionality:
            - Add Friends
            - add Friends
            - Remove Friends
            - view Friends
            - view Requests
            - view profile
        """
        self.__screen.clear_tasks()
        # Input
        search_name_bx: InputBox = InputBox(
            self.dynamic(0.15, 'w'), self.dynamic(0.05, 'h'), 100, 100, 'query_user'
        )
        self.__screen.add_task('inputboxes', 'query_user', search_name_bx)

        search_text: Text = Text(
            self.dynamic(0.05, 'w'), self.dynamic(0.05, 'h'), 100, 100, colours['BLACK'], 'User: '
        )
        self.__screen.add_task('text', 'search', search_text)

        redirect_btn: Button = Button(
            self.dynamic(0.05, 'w'), self.dynamic(0.2, 'h'), 100, 100, 'Main Menu' if not redirect else redirect[0],
            colours['ORANGE'], colours['WHITE'],
            *redirect[2] if redirect else (), action=self.MainUI if not redirect else redirect[1]
        )
        self.__screen.add_task('buttons', 'redirect', redirect_btn)

        view_person: Button = Button(
            self.dynamic(0.05, 'w'), self.dynamic(0.35, 'h'), 100, 100, 'Profile',
            colours['PURPLE'], colours['WHITE'], action=self.view_profile
        )
        self.__screen.add_task('buttons', 'view_person', view_person)

        friends_list: Button = Button(
            self.dynamic(0.05, 'w'), self.dynamic(0.50, 'h'), 100, 100, 'List',
            colours['BLURPLE'], colours['WHITE'], action=self.friends_paginator
        )
        self.__screen.add_task('buttons', 'friends_list', friends_list)

        requests: Button = Button(
            self.dynamic(0.05, 'w'), self.dynamic(0.65, 'h'), 100, 100, 'Requests',
            colours['GREEN'], colours['WHITE'], redirect, action=self.requests
        )
        self.__screen.add_task('buttons', 'requests', requests)


    async def invites_view(self) -> None:
        """
        creates a paginator where you can join a game via a btn
        """
        self.remove_paginators()
        invites = await self.__screen.client.get_invites()
        if not invites:
            text = Text(
                self.dynamic(0.7, 'w'), self.dynamic(0.45, 'h'), 100, 100,
                colours['BLACK'], 'You don\'t have any invites\'s!'
            )
            self.__screen.add_task('text', 'output', text)
            asyncio.create_task(self.delete_alert({'output': text}))

        elif invites.get('error'):
            text = Text(
                self.dynamic(0.7, 'w'), self.dynamic(0.45, 'h'), 100, 100,
                colours['BLACK'], invites['message']
            )
            self.__screen.add_task('text', 'output', text)
            asyncio.create_task(self.delete_alert({'output': text}))

        else:
            entries = []
            for k, v in invites.items():
                entries.append(f"{k}: {v:,}")
            _pag = self.create_paginator(entries, name="invites", entry_size=26)
            self.__screen.add_task('functions', 'invites', [_pag])

    async def join_lobby(self) -> None:
        """ handles the join_lobby view """
        self.__screen.clear_tasks()
        main_menu: Button = Button(
            self.dynamic(0.05, 'w'), self.dynamic(0.2, 'h'), 200, 100, 'Main Menu',
            colours['PUCE'], colours['WHITE'], action=self.MainUI
        )
        self.__screen.add_task('buttons', 'main_menu', main_menu)
        # means they can view invites sent to them by friends
        invites_btn = Button(
            self.dynamic(0.05, 'w'), self.dynamic(0.4, 'h'), 200, 100,
            'Invites', colours['LIGHTBLUE'], colours['WHITE'], action=self.invites_view
        )
        self.__screen.add_task('buttons', 'invites', invites_btn)

        code_bx: InputBox = InputBox(
            self.dynamic(0.35, 'w'), self.dynamic(0.1, 'h'), 100, 100,
            'invite_code', max_length=6
        )
        self.__screen.add_task('inputboxes', 'invite_code', code_bx)
        code_txt: Text = Text(
            self.dynamic(0.25, 'w'), self.dynamic(0.1, 'h'), 100, 100,
            colours['BLACK'], 'Invite Code: '
        )
        self.__screen.add_task('text', 'code_text', code_txt)

        async def _forwarder():
            nonlocal self

            code: InputBox = self.__screen.get_task('inputboxes', 'invite_code')
            _output = None
            if not str(code):
                _output = 'Invite Code is a required argument and is missing!'
            if not _output and len(code) != 6:
                _output = 'Invalid Invite Code!'
            try:
                if not _output:
                    code: int = int(code)
            except ValueError:
                _output = 'Invalid Invite Code!'
            if _output:
                err_txt: Text = Text(
                    self.dynamic(0.4, 'w'), self.dynamic(0.3, 'h'), 100, 100,
                    colours['BLACK'], _output
                )
                self.__screen.add_task('text', 'output', err_txt)
                await self.delete_alert({'output': err_txt})
            else:
                self.__screen.remove_task('text', 'output')
                await self.lobby_view(code)

        join_lobby_btn = Button(
            self.dynamic(0.05, 'w'), self.dynamic(0.6, 'h'), 200, 100,
            'Join Lobby', colours['YELLOW'], colours['WHITE'], action=_forwarder
        )
        self.__screen.add_task('buttons', 'join_lobby', join_lobby_btn)

    async def leave_lobby(self) -> None:
        """ Leaves a game lobby and returns to the main UI"""
        if not self.__screen.client.game_info:
            asyncio.create_task(self.__screen.client.leave_lobby())
            await self.MainUI()

    async def lobby_check_game_started(self):
        """ checks if a game has been started by the game host """
        if self.__started_game_check:
            return
        while self.__screen.client.lobby and self.__screen.runner and not self.__started_game_check:
            if self.__screen.client.game_info:
                self.__started_game_check = True
                asyncio.create_task(self.start_game('join'))
                break
            await asyncio.sleep(1)
        self.__started_game_check = False

    async def lobby_invite(self) -> None:
        """ Invites a user to the lobby"""
        self.__screen.loading = True
        user_box = self.__screen.get_task('inputboxes', 'query_user')
        if not user_box:
            self.__screen.loading = False
            _inst = Text(
                self.dynamic(0.15, 'w'), self.dynamic(0.25, 'h'), 100, 100, colours['BLACK'],
                'User is a required field and is missing!'
            )
            self.__screen.add_task('text', 'output', _inst)
            asyncio.create_task(self.delete_alert({'output': _inst}))
        else:
            user = await self.__screen.client.get_or_fetch_user(str(user_box))
            if not user:
                self.__screen.loading = False
                _inst = Text(
                    self.dynamic(0.15, 'w'), self.dynamic(0.25, 'h'), 100, 100, colours['BLACK'],
                    f'User "{user_box}" not found!'
                )
                self.__screen.add_task('text', 'output', _inst)
                asyncio.create_task(self.delete_alert({'output': _inst}))
            else:
                resp = await self.__screen.client.invite(user.username)
                self.__screen.loading = False
                if resp.get('error'):
                    _inst = Text(
                        self.dynamic(0.15, 'w'), self.dynamic(0.25, 'h'), 100, 100, colours['BLACK'],
                        resp['message']
                    )
                    self.__screen.add_task('text', 'output', _inst)
                    asyncio.create_task(self.delete_alert({'output': _inst}))
                else:
                    _inst = Text(
                        self.dynamic(0.15, 'w'), self.dynamic(0.25, 'h'), 100, 100, colours['BLACK'],
                        f'{user.username} has been invited to the lobby'
                    )
                    self.__screen.add_task('text', 'output', _inst)
                    asyncio.create_task(self.delete_alert({'output': _inst}))

    async def settings_view(self) -> None:
        """ Displays the game settings

            if user is the host they will be able to edit the settings and have a view such as:
            Button(Lobby)

            total rounds: InputBox(default=3)
            round duration: InputBox(default=180)

            Button(submit changes)


            if user is not the host they will only be given a read only view such as:
            Button(Lobby)

            total rounds: {var}
            total duration: {var2}
        """
        self.__screen.clear_tasks()
        back_btn: Button = Button(
            self.dynamic(0.05, 'w'), self.dynamic(0.1, 'h'), 100, 100, 'Lobby',
            colours['ORANGE'], colours['WHITE'],
            None, True, action=self.lobby_view
        )
        self.__screen.add_task('buttons', 'back', back_btn)
        settings_dict = self.__screen.client.lobby.game_settings
        if self.__screen.client.root.username == self.__screen.client.lobby.host:
            total_rounds_bx: InputBox = InputBox(
                self.dynamic(0.28, 'w'), self.dynamic(0.4, 'h'), 100, 100, 'total_rounds',
                text=str(settings_dict['total_rounds']), max_length=2
            )
            self.__screen.add_task('inputboxes', 'total_rounds', total_rounds_bx)
            total_duration_bx: InputBox = InputBox(
                self.dynamic(0.28, 'w'), self.dynamic(0.6, 'h'), 100, 100, 'round_duration',
                text=str(settings_dict['round_duration']), max_length=3
            )
            self.__screen.add_task('inputboxes', 'total_duration', total_duration_bx)

            async def update_game_settings() -> None:
                nonlocal self
                output = None
                total_rounds_bx: InputBox = self.__screen.get_task('inputboxes', 'total_rounds')
                total_duration_bx: InputBox = self.__screen.get_task('inputboxes', 'total_duration')
                try:
                    total_rounds_bx: int = int(total_rounds_bx)
                    total_duration_bx: int = int(total_duration_bx)
                except ValueError:
                    output = 'Setting values should be integers'

                if not output:
                    if total_rounds_bx > 20 or total_rounds_bx < 1:
                        output = 'Total Rounds must be less than 21 and higher than 0'

                if not output:
                    if total_duration_bx > 600 or total_duration_bx < 60:
                        output = 'Round Duration must be less than to 601 seconds and higher than 59'

                if not output:
                    if total_duration_bx == self.__screen.client.lobby.game_settings['round_duration'] and \
                            total_rounds_bx == self.__screen.client.lobby.game_settings['total_rounds']:
                        output = 'No change to the game settings was made!'

                if not output:
                    self.__screen.client.lobby.game_settings['total_rounds'] = total_rounds_bx
                    self.__screen.client.lobby.game_settings['round_duration'] = total_duration_bx
                    resp = await self.__screen.client.update_game_settings()
                    if resp.get('error'):
                        output = resp['message']
                    else:
                        output = 'Saved Changes!'

                txt: Text = Text(
                    self.dynamic(0.45, 'w'), self.dynamic(0.15, 'h'), 100, 100,
                    colours['BLACK'], output
                )
                self.__screen.add_task('text', 'output', txt)
                await self.delete_alert({'output': txt})

            submit_changes: Button = Button(
                self.dynamic(0.05, 'w'), self.dynamic(0.82, 'h'), 200, 100, 'Submit Changes',
                colours['GREEN'], colours['WHITE'], action=update_game_settings
            )
            self.__screen.add_task('buttons', 'submit_changes', submit_changes)
            totalroundsfmt = 'Total Rounds: '
            totaldurationfmt = 'Round Duration (seconds): '

        else:
            totalroundsfmt = f'Total Rounds: {settings_dict["total_rounds"]}'
            totaldurationfmt = f'Round Duration (seconds): {settings_dict["round_duration"]}'

        total_rounds_txt: Text = Text(
            self.dynamic(0.1, 'w'), self.dynamic(0.4, 'h'), 100, 100,
            colours['BLACK'], totalroundsfmt
        )
        self.__screen.add_task('text', 'total_rounds', total_rounds_txt)
        total_duration_txt: Text = Text(
            self.dynamic(0.1, 'w'), self.dynamic(0.6, 'h'), 100, 100,
            colours['BLACK'], totaldurationfmt
        )
        self.__screen.add_task('text', 'round_duration', total_duration_txt)

    async def reconnect_to_game(self) -> None:
        """ Allows a user to reconnect to a game if they have disconnected """
        self.__screen.loading = True
        await self.start_game('join')
        self.__screen.loading = False

    async def start_game(self, _type: Literal['create', 'join']) -> None:
        """ Starts a game by either created one as the host or joining one """
        self.__screen.clear_tasks()
        self.__screen.loading = True
        if _type == 'create':
            resp = await self.__screen.client.create_game()
            if not isinstance(resp, GameInfo):
                self.__screen.loading = False
                _inst = Text(
                    self.dynamic(0.15, 'w'), self.dynamic(0.25, 'h'), 100, 100, colours['BLACK'],
                    resp['message']
                )
                self.__screen.add_task('text', 'output', _inst)
                await self.delete_alert({'output': _inst})
                await self.lobby_view(None, True)
        else:
            resp = self.__screen.client.game_info
        if isinstance(resp, GameInfo):
            self.__screen.loading = False
            if not self.__screen.game:
                self.__screen.game = Game(self.__screen)

    async def on_game_finish(self) -> None:
        """ Called when a game has ended """
        self.__screen.game = None
        self.__screen.client.game_info = None
        self.__screen.client.game_data = None
        await self.__screen.client.recache_users()
        if self.__screen.client.lobby:
            await self.lobby_view(None, True)
        else:
            await self.MainUI()

    async def lobby_view(self, invite_code: Optional[int] = None, redirect: bool = False) -> None:
        """ manages the lobby view

            if invite_code passed, then the user joins a lobby otherwise it creates a lobby
            if redirect passed, then it simply means user is already in a lobby
         """

        self.__screen.clear_tasks()
        lobby: Lobby = self.__screen.client.lobby
        if not redirect:
            if not invite_code:
                resp = await self.__screen.client.create_lobby()
            else:
                resp = await self.__screen.client.join_lobby(invite_code)
            if resp.get('error'):
                _inst = Text(
                    self.dynamic(0.4, 'w'), self.dynamic(0.25, 'h'), 100, 100,
                    colours['BLACK'], resp['message']
                )
                self.__screen.add_task('text', 'output', _inst)
                await self.delete_alert({'output': _inst}, sleep_until=1)
                # not using asyncio.create_task as we want that time delay
                await self.join_lobby()
            else:
                resp['lobby']['players'] = {
                    k: datetime.datetime.fromtimestamp(v) for k, v in resp['lobby']['players'].items()
                }
                lobby: Lobby = Lobby(resp['lobby_id'], **resp['lobby'])
                self.__screen.client.lobby = lobby

        if lobby:

            # [START GAME] [GAME SETTINGS] [FRIENDS] [PROFILES] [LEAVE] (search) Invite CODE: <DISPLAY CODE>
            start: Button = Button(
                self.dynamic(0.001, 'w'), self.dynamic(0.05, 'h'), 100, 100,
                'Start', colours['GREEN'], colours['WHITE'], 'create', disabled=True, action=self.start_game
            )
            if lobby.host == self.__screen.client.root.username:
                start.disabled = False
            self.__screen.add_task('buttons', 'start', start)
            settings: Button = Button(
                self.dynamic(0.1, 'w'), self.dynamic(0.05, 'h'), 100, 100,
                'settings', colours['PUCE'], colours['WHITE'], action=self.settings_view
            )
            self.__screen.add_task('buttons', 'settings', settings)

            friends: Button = Button(
                self.dynamic(0.2, 'w'), self.dynamic(0.05, 'h'), 100, 100,
                'friends', colours['FAWN'], colours['WHITE'], ['Lobby', self.lobby_view, [None, True]],
                action=self.friends_view
            )
            self.__screen.add_task('buttons', 'friends', friends)

            profile: Button = Button(
                self.dynamic(0.3, 'w'), self.dynamic(0.05, 'h'), 100, 100,
                'profile', colours['JADE'], colours['WHITE'], True, action=self.view_profile
            )
            self.__screen.add_task('buttons', 'profile', profile)

            leave: Button = Button(
                self.dynamic(0.4, 'w'), self.dynamic(0.05, 'h'), 100, 100,
                'leave', colours['PURPLE'], colours['WHITE'], action=self.leave_lobby
            )
            self.__screen.add_task('buttons', 'leave', leave)

            invite: Button = Button(
                self.dynamic(0.5, 'w'), self.dynamic(0.05, 'h'), 100, 100,
                'invite', colours['BLURPLE'], colours['WHITE'], action=self.lobby_invite
            )
            self.__screen.add_task('buttons', 'invite', invite)

            search: Text = Text(
                self.dynamic(0.61, 'w'), self.dynamic(0.018, 'h'), 1, 1,
                colours['BLACK'], f'search: ', size=24
            )
            self.__screen.add_task('text', 'search', search)

            prompt: InputBox = InputBox(
                self.dynamic(0.6, 'w'), self.dynamic(0.05, 'h'), 100, 100,
                'prompt'
            )
            self.__screen.add_task('inputboxes', 'query_user', prompt)

            display_code: Text = Text(
                self.dynamic(0.8, 'w'), self.dynamic(0.001, 'h'), 100, 100,
                colours['BLACK'], f'Invite Code: {lobby.invite_code:,}'
            )
            self.__screen.add_task('text', 'display_code', display_code)

            # Team shower
            def output_team(start_w: float, start_h: float, team: List):
                x_inc: int = self.dynamic(start_w, 'w')
                y_inc: int = self.dynamic(start_h, 'h')
                for idx, ln in enumerate(team):
                    if ln == lobby.host:
                        ln = '[HOST] ' + ln
                    y_inc += 50
                    ln_txt = Text(
                        x_inc, y_inc, 50, 50, colours['BLACK'], ln, size=22
                    )
                    self.__screen.add_task('text', f'team_out_{team[idx]}', ln_txt)

            async def join_red() -> None:
                nonlocal self
                nonlocal lobby
                if len(lobby.red_team) < 5:
                    await self.__screen.client.join_team('red')

            async def join_switcher() -> None:
                nonlocal self
                nonlocal lobby
                if len(lobby.switcher) < 5:
                    await self.__screen.client.join_team('switcher')

            async def join_blue() -> None:
                nonlocal self
                nonlocal lobby
                if len(lobby.blue_team) < 5:
                    await self.__screen.client.join_team('blue')

            def show_teams() -> None:
                nonlocal self
                nonlocal join_red
                nonlocal join_switcher
                nonlocal join_blue
                lobby = self.__screen.client.lobby

                for task in self.__screen.get_tasks('text').copy():
                    if task.startswith('team_out_'):
                        self.__screen.remove_task('text', task)

                output_team(0.515, 0.32, lobby.red_team)
                output_team(0.69, 0.32, lobby.switcher)
                output_team(0.865, 0.32, lobby.blue_team)

                # red side
                if not self.__screen.get_task('text', 'red_header'):
                    red_header: Text = Text(
                        self.dynamic(0.5, 'w'), self.dynamic(0.27, 'h'), 100, 100,
                        colours['RED'], 'RED TEAM'
                    )
                    self.__screen.add_task('text', 'red_header', red_header)

                # slider
                if not self.__screen.get_task('text', 'slider_header'):
                    slider_header: Text = Text(
                        self.dynamic(0.675, 'w'), self.dynamic(0.27, 'h'), 100, 100,
                        colours['BLACK'], 'SWITCHER'
                    )
                    self.__screen.add_task('text', 'slider_header', slider_header)

                # blue side
                if not self.__screen.get_task('text', 'blue_header'):
                    blue_header: Text = Text(
                        self.dynamic(0.85, 'w'), self.dynamic(0.27, 'h'), 100, 100,
                        colours['BLURPLE'], 'BLUE TEAM'
                    )
                    self.__screen.add_task('text', 'blue_header', blue_header)

                me = self.__screen.client.root.username
                if not self.__screen.get_task('buttons', 'join_red'):
                    # join buttons
                    join_red_btn: Button = Button(
                        self.dynamic(0.5, 'w'), self.dynamic(0.82, 'h'), 100, 100,
                        'RED', colours['RED'], colours['WHITE'], action=join_red
                    )
                    join_switcher_btn: Button = Button(
                        self.dynamic(0.675, 'w'), self.dynamic(0.82, 'h'), 100, 100,
                        'SWITCHER', colours['PUCE'], colours['WHITE'], action=join_switcher
                    )
                    join_blue_btn: Button = Button(
                        self.dynamic(0.85, 'w'), self.dynamic(0.82, 'h'), 100, 100,
                        'BLUE', colours['BLURPLE'], colours['WHITE'], action=join_blue
                    )
                    for btn in [join_red_btn, join_switcher_btn, join_blue_btn]:
                        self.__screen.add_task('buttons', "join_" + btn.text.lower(), btn)

            self.__screen.add_task('functions', 'show_teams', [show_teams])
            asyncio.create_task(self.lobby_check_game_started())

    async def MainUI(self) -> None:
        """ Places the logged-in user into the main ui
        FRIENDS:
            - Add Friends
            - Remove Friends
            - view Friends
            - view Requests
        Reconnect:
            -> shows this if the user joined a game and had left and the game is still on going,
            they cannot join or create lobbies during this period, otherwise the button is disabled
        Create Lobby:
            -> places the user into the lobby ui and as game host
        Join Lobby:
            -> allows the user to join a lobby
        Invites:
            -> Lets the person view invites from friends and join lobbies
        """
        self.__screen.clear_tasks()
        res = await self.__screen.client.root_in_game()
        friends_btn = Button(
            self.dynamic(0.2, 'w'), self.dynamic(0.15, 'h'), 200, 100,
            'Friends', colours['BLURPLE'], colours['WHITE'], action=self.friends_view
        )
        self.__screen.add_task('buttons', 'friends', friends_btn)
        reconnect_btn = Button(
            self.dynamic(0.4, 'w'), self.dynamic(0.15, 'h'), 200, 100,
            'Reconnect  To Game', colours['RED'], colours['WHITE'], disabled=True, action=self.reconnect_to_game
        )
        self.__screen.add_task('buttons', 'reconnect', reconnect_btn)
        if res:
            # they must reconnect to the game and cannot join or create lobbies until the game has ended.
            reconnect_btn.disabled = False
        else:
            join_lobby_btn = Button(
                self.dynamic(0.2, 'w'), self.dynamic(0.45, 'h'), 200, 100,
                'Join Lobby', colours['YELLOW'], colours['WHITE'], action=self.join_lobby
            )
            self.__screen.add_task('buttons', 'join_lobby', join_lobby_btn)

            create_lobby_btn = Button(
                self.dynamic(0.4, 'w'), self.dynamic(0.45, 'h'), 200, 100,
                'Create Lobby', colours['PURPLE'], colours['WHITE'], action=self.lobby_view
            )
            self.__screen.add_task('buttons', 'create_lobby', create_lobby_btn)

    async def send_fpwd_code(self) -> None:
        """ Handles the forgotten password logic """
        username = self.__screen.get_task('inputboxes', 'username')
        email = self.__screen.get_task('inputboxes', 'email')
        total_feedback = {'svr': [], 'em': [], 'usn': []}
        if email is not None:
            length = len(email.text.lower().strip())
            if not email.text:
                total_feedback['em'].append("Email is a required field and is missing!")
            elif not 5 < length < 30:
                total_feedback['em'].append('Email length should be more than 5 and less than 30')
            elif not re.fullmatch(EMAIL_RE, email.text):
                total_feedback['em'].append('Invalid Email')

        if username is not None:
            if str(username) == '':
                total_feedback['usn'].append("Username is a required field and is missing!")
        if not any([total_feedback[k] for k in total_feedback.keys()]):
            if self.__screen.client.notifs.get(
                    'sent_fpwd_otp', {}).get('exp', datetime.datetime.now()) <= datetime.datetime.now():
                result = await self.__screen.client.send_fpwd_code(str(username), str(email))
                if result.get('error'):
                    total_feedback['svr'].append(result['result']['message'])

        if any([total_feedback[k] for k in total_feedback.keys()]):
            friendly: Dict[str, str] = {
                'svr': 'server',
                'em': 'email',
                'usn': 'username'
            }

            for potential in self.__screen.get_tasks('text').copy():
                if potential + 'main' in [friendly.values()]:
                    self.__screen.remove_task('text', potential)
                elif 'fb_' in potential:
                    self.__screen.remove_task('text', potential)

            y_inc: int = self.dynamic(0.2, 'h')
            x_inc: int = self.dynamic(0.7, 'w')

            _insts: Dict[str, Text] = {}

            for field in total_feedback:
                if total_feedback[field]:
                    for idx, fb in enumerate(total_feedback[field]):
                        y_inc += 50
                        fb_txt = Text(
                            x_inc, y_inc, 50, 50, colours['BLACK'], fb
                        )
                        self.__screen.add_task('text', friendly[field] + f'fb_{idx}', fb_txt)
                        _insts[friendly[field] + f'fb_{idx}'] = fb_txt
            asyncio.create_task(self.delete_alert(_insts, sleep_until=10))
        else:
            class OTPTimer(DynamicText):
                def __init__(self, x: int, y: int, width: int, height: int, colour: Tuple, text: str,
                             fmt_dict: dict,
                             size: int = 28):
                    super().__init__(x, y, width, height, colour, text, fmt_dict, size)

                def fmt_text(self, text: str) -> str:
                    return text.format(dt=self._fmt_dict['func'](self._fmt_dict['dt'].get(
                        'sent_fpwd_otp', {}
                    ).get(
                        'exp', datetime.datetime.now())
                    ))

            dy_txt = OTPTimer(
                self.dynamic(0.65, 'w'), self.dynamic(0.1, 'h'),
                100, 100,
                colours['BLACK'],
                "A One Time Password Code was sent to your email, the code will expire in {dt}",
                {"dt": self.__screen.client.notifs, 'func': human_timedelta},
                size=22
            )
            self.__screen.add_task('text', 'otp_info', dy_txt)
            asyncio.create_task(self.delete_alert({'otp_info': dy_txt}))

    async def update_password(self) -> None:
        """ Updates the password when a user has forgotten it. """
        username: InputBox = self.__screen.get_task('inputboxes', 'username')
        email: InputBox = self.__screen.get_task('inputboxes', 'email')
        otp_code: InputBox = self.__screen.get_task('inputboxes', 'otp_code')
        password: InputBox = self.__screen.get_task('inputboxes', 'new_pwd')

        total_feedback: Dict[str, List] = {'svr': [], 'em': [], 'usn': [], 'pwd': [], 'otp': []}

        if password is not None:
            pwd_feedback: List[str] = []
            if not password.text:
                total_feedback['pwd'].append('Password is a required field and is missing!')
            else:
                password_flags = [False, False, False, False, False]
                # should be True, True, True, True, True
                # order being digit check, uppercase check, lowercase check, ratio check, length check
                if len(password) >= 8:
                    password_flags[4] = True
                if fuzz.ratio(username.text.lower(), password.text.lower()) < 70:
                    password_flags[3] = True
                for chr in password:  # NOQA: ignore shadow of chr
                    if all(password_flags):  # if all the flags are True it breaks out of the loop
                        break
                    if chr.isdigit():  # checks for digits
                        password_flags[0] = True
                    if chr.isupper():  # checks for uppercase letter
                        password_flags[1] = True
                    if chr.islower():  # checks for lowercase letter
                        password_flags[2] = True
                if not all(password_flags):  # means they are missing something in their password
                    for index, val in enumerate(password_flags):  # we want the index and so we use enumerate
                        if not val:
                            if index == 0:
                                pwd_feedback.append("Password must have at least one digit!")
                            elif index == 1:
                                pwd_feedback.append("Password must have at least one uppercase!")
                            elif index == 2:
                                pwd_feedback.append("Password must have at least one lowercase!")
                            elif index == 3:
                                pwd_feedback.append("Your username cannot be in your password!")
                            elif index == 4:
                                pwd_feedback.append("Your password must be a length of 8 characters or more!")
                    total_feedback['pwd'].extend(pwd_feedback)

        if email is not None:
            length = len(email.text.lower().strip())
            if not email.text:
                total_feedback['em'].append("Email is a required field and is missing!")
            elif not 5 < length < 30:
                total_feedback['em'].append('Email length should be more than 5 and less than 30')
            elif not re.fullmatch(EMAIL_RE, email.text):
                total_feedback['em'].append('Invalid Email')

        if username is not None:
            if str(username) == '':
                total_feedback['usn'].append("Username is a required field and is missing!")

        if otp_code is not None:
            if not str(otp_code):
                total_feedback['otp'].append('OTP Code is a required field and is missing.')
            try:
                otp_code: int = int(otp_code)
            except ValueError:
                total_feedback['otp'].append('Invalid OTP code')

        if not any([total_feedback[k] for k in total_feedback.keys()]):
            result = await self.__screen.client.update_password(
                *[bx.__str__() if type(bx) != int else bx for bx in [username, email, password, otp_code]]
            )
            if result.get('error'):
                total_feedback['svr'].append(result['result']['message'])

        if any([total_feedback[k] for k in total_feedback.keys()]):
            friendly: Dict[str, str] = {
                'svr': 'server',
                'em': 'email',
                'usn': 'username',
                'pwd': 'password',
                'otp': 'otp'
            }

            y_inc: int = self.dynamic(0.2, 'h')
            x_inc: int = self.dynamic(0.7, 'w')

            _insts: Dict[str, Text] = {}

            for field in total_feedback:
                if total_feedback[field]:
                    for idx, fb in enumerate(total_feedback[field]):
                        y_inc += 50
                        fb_txt = Text(
                            x_inc, y_inc, 50, 50, colours['BLACK'], fb
                        )
                        self.__screen.add_task('text', friendly[field] + f'fb_{idx}', fb_txt)
                        _insts[friendly[field] + f'fb_{idx}'] = fb_txt

            asyncio.create_task(self.delete_alert(_insts, sleep_until=10))
        else:
            self.__screen.add_task('text', 'success', Text(
                self.dynamic(0.5, 'w'), self.dynamic(0.6, 'h'), 100, 100,
                colours['BLACK'], 'You have updated your account successfully'
                                  ', you will be returned to the main menu shortly'
            ))
            await asyncio.sleep(5)
            self.__data = {}
            self.__screen.clear_tasks()
            self.__screen.set_screen_minor(None)
            self.registered_views = False

    def register_views(self, screen_conf: str, minor_conf: str | None) -> None:
        """ Registers the initial views """
        if screen_conf and not minor_conf:
            if screen_conf == 'Launcher':
                login_button = Button(
                    self.dynamic(0.1, 'w'), self.dynamic(0.45, 'h'), 170, 100, 'Login',
                    colours['GREEN'], colours['WHITE'], 'Login', action=self.__screen.set_screen_minor
                )
                register_button = Button(
                    self.dynamic(0.7, 'w'), self.dynamic(0.45, 'h'), 175, 100, 'Register', colours['BLURPLE'],
                    colours['WHITE'], 'Register', action=self.__screen.set_screen_minor
                )

                self.__screen.add_task('buttons', 'login', login_button)
                self.__screen.add_task('buttons', 'register', register_button)
        else:

            if minor_conf == 'Login':
                self.__screen.clear_tasks()
                username_bx = InputBox(
                    self.dynamic(0.17, 'w'), self.dynamic(0.15, 'h'), 100, 100, 'Username',
                )
                username_txt = Text(
                    self.dynamic(0.04, 'w'), self.dynamic(0.15, 'h'), 100, 100, colours['BLACK'], 'Username: '
                )
                password_bx = InputBox(
                    self.dynamic(0.17, 'w'), self.dynamic(0.40, 'h'), 100, 100, 'Password',
                )
                password_txt = Text(
                    self.dynamic(0.04, 'w'), self.dynamic(0.40, 'h'), 100, 100, colours['BLACK'], 'Password: '
                )
                forgot_btn = Button(
                    self.dynamic(0.04, 'w'), self.dynamic(0.7, 'h'), 175, 100, 'Forgot Password', colours['RED'],
                    colours['WHITE'], 'ForgotPassword', action=self.__screen.set_screen_minor
                )
                submit_btn = Button(
                    self.dynamic(0.3, 'w'), self.dynamic(0.7, 'h'), 100, 100, 'Submit', colours['BLURPLE'],
                    colours['WHITE'], action=self.submit_login
                )
                self.__screen.add_task('buttons', 'submit', submit_btn)
                self.__screen.add_task('buttons', 'forgot', forgot_btn)
                self.__screen.add_task('inputboxes', 'username', username_bx)
                self.__screen.add_task('inputboxes', 'password', password_bx)
                self.__screen.add_task('text', 'username', username_txt)
                self.__screen.add_task('text', 'password', password_txt)

            elif minor_conf == 'Register':
                self.__screen.clear_tasks()
                # create views
                views: Dict[str, InputBox | Text] = {}
                y_counter: int = 0
                y_inc: int = 115
                bx_x: int = 225
                txt_x: int = 75
                to_cr: List[str] = ['displayname', 'username', 'password', 'confirm_password', 'email']
                friendly: List[str] = ['Display name: ', 'Username: ', 'password: ',
                                       'Confirm Password: ', 'Email: ', 'Authentication Code: ']

                for idx, view in enumerate(to_cr):  # type: int, str
                    if y_counter == 0:
                        y_counter += 25
                    else:
                        y_counter += y_inc
                    if view == 'email':
                        views[view + "_bx"] = InputBox(bx_x, y_counter, 100, 100, view, max_length=30)
                    else:
                        views[view + "_bx"] = InputBox(bx_x, y_counter, 100, 100, view)
                    views[view + "_txt"] = Text(txt_x, y_counter, 100, 100, colours['BLACK'], friendly[idx])

                # Persistent
                for view in views:  # type: str
                    if view.endswith('_bx'):
                        self.__screen.add_task('inputboxes', view[:-3], views[view])
                    elif view.endswith('_txt'):
                        self.__screen.add_task('text', view[:-4], views[view])

                # Send OTP + Submit Form button

                self.__screen.add_task('buttons', 'submit', Button(
                    self.dynamic(0.38, 'w'), self.dynamic(0.1, 'h'), 175, 100, 'Submit', colours['BLURPLE'],
                    colours['WHITE'], action=self.register_step1_continue
                ))

            elif minor_conf == 'ForgotPassword':
                self.__screen.clear_tasks()
                self.__screen.add_task('inputboxes', 'username', InputBox(
                    self.dynamic(0.2, 'w'), self.dynamic(0.12, 'h'), 100, 100,
                    'username'
                ))
                self.__screen.add_task('text', 'username', Text(
                    self.dynamic(0.1, 'w'), self.dynamic(0.12, 'h'), 100, 100,
                    colours['BLACK'], 'Username: '
                ))
                self.__screen.add_task('inputboxes', 'email', InputBox(
                    self.dynamic(0.2, 'w'), self.dynamic(0.3, 'h'), 100, 100,
                    'email', max_length=30
                ))
                self.__screen.add_task('text', 'email', Text(
                    self.dynamic(0.1, 'w'), self.dynamic(0.3, 'h'), 100, 100,
                    colours['BLACK'], 'Email: '
                ))
                self.__screen.add_task("inputboxes", "otp_code", InputBox(
                    self.dynamic(0.2, 'w'), self.dynamic(0.5, 'h'), 100, 100,
                    'otp_code', max_length=6
                ))
                self.__screen.add_task('text', 'otp_code', Text(
                    self.dynamic(0.1, 'w'), self.dynamic(0.5, 'h'), 100, 100,
                    colours['BLACK'], 'OTP Code: '
                ))
                self.__screen.add_task('inputboxes', 'new_pwd', InputBox(
                    self.dynamic(0.55, 'w'), self.dynamic(0.76, 'h'), 100, 100,
                    'new_password'
                ))
                self.__screen.add_task('text', 'new_pwd', Text(
                    self.dynamic(0.43, 'w'), self.dynamic(0.76, 'h'), 100, 100,
                    colours['BLACK'], 'New Password: '
                ))
                self.__screen.add_task('buttons', 'send_otp', Button(
                    self.dynamic(0.25, 'w'), self.dynamic(0.7, 'h'), 175, 175,
                    'Send Code', colours['BLURPLE'], colours['BLACK'], action=self.send_fpwd_code
                ))
                self.__screen.add_task('buttons', 'update_pwd', Button(
                    self.dynamic(0.1, 'w'), self.dynamic(0.7, 'h'), 175, 175,
                    'Update Password', colours['BLURPLE'], colours['BLACK'], action=self.update_password
                ))
