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
from typing import TYPE_CHECKING, Optional, Literal, Tuple, Dict, List, Union
from .constants import colours, FONT
import datetime as dt
from .utils import Text, DynamicText
from ..utils import generate_snowflake, human_timedelta
import asyncio

if TYPE_CHECKING:
    from ..Networking.client import GameInfo
    from ..Networking.client import Client as NetworkClient
    from ..Networking.client import GameData
    from .screen import Screen


class ServerBullet(pygame.sprite.Sprite):
    """ This class is made by the server """

    def __init__(self, shooter: ServerCharacter, x: int, y: int, speed: int) -> None:
        super().__init__()
        self.__shooter: ServerCharacter = shooter
        self.__x: int = x
        self.__y: int = y
        self.__speed: int = speed
        self.__max_y = int(shooter.win_size[1] * 0.9) - 10
        self.__bullet_surface = pygame.Surface((10, 10))
        self.__bullet_surface.fill(shooter.colour)
        if self.__shooter.team == 'red':
            self.__rect: pygame.Rect = self.__bullet_surface.get_rect(midright=(self.__x, self.__y))
        else:
            self.__rect: pygame.Rect = self.__bullet_surface.get_rect(midleft=(self.__x, self.__y))

    @property
    def rect(self):
        return self.__rect

    def update(self) -> None:
        """ Updates the bullets position """
        self.__x += self.__speed
        if self.__shooter.team == 'red':
            self.__rect.midright = (self.__x, self.__y)
        else:
            self.__rect.midleft = (self.__x, self.__y)

        for enemy in pygame.sprite.spritecollide(self, self.__shooter.enemy_group, False):
            self.__shooter.hit_enemy(enemy)
            self.kill()

        if not (0 <= self.__x <= self.__shooter.win_size[0] and 0 <= self.__y <= self.__shooter.win_size[1]):
            self.kill()

    def draw(self, window: pygame.Surface | pygame.SurfaceType) -> None:
        """Draw the Server Bullet"""
        window.blit(self.__bullet_surface, (self.__x, self.__y))


class Bullet(pygame.sprite.Sprite):
    """ This class is for bullets made by the client """

    def __init__(self, game_data: GameData, shooter: Character) -> None:
        super().__init__()
        self.__game_data: GameData = game_data
        self.__shooter: Character = shooter
        self.__x: int = shooter.x
        self.__y: int = shooter.y
        self.__speed: int = 10
        self.__max_y = int(shooter.win_size[1] * 0.9) - 10
        self.__bullet_surface = pygame.Surface((10, 10))
        self.__bullet_surface.fill(shooter.colour)
        if self.__shooter.team == 'red':
            self.__rect: pygame.Rect = self.__bullet_surface.get_rect(midright=(self.__x, self.__y))
        else:
            self.__rect: pygame.Rect = self.__bullet_surface.get_rect(midleft=(self.__x, self.__y))
        self.broadcast(init=True)

    @property
    def rect(self):
        return self.__rect

    def update(self) -> None:
        """ Updates the bullets position """
        if self.__shooter.team == "red":
            self.__x += self.__speed
            self.__rect.midright = (self.__x, self.__y)
        else:
            self.__x -= self.__speed
            self.__rect.midleft = (self.__x, self.__y)

        for enemy in pygame.sprite.spritecollide(self, self.__shooter.enemy_group, False):
            self.__shooter.hit_enemy(enemy)
            self.kill()

        if not (0 <= self.__x <= self.__shooter.win_size[0] and 0 <= self.__y <= self.__shooter.win_size[1]):
            self.kill()

    def broadcast(self, *, init: bool = False) -> None:
        """ broadcasts the changes to the server"""
        if init:
            self.__game_data.to_send['bullets'][generate_snowflake()] = {
                'COMMAND': 'CREATED',
                'X': self.__x,
                'Y': self.__y,
                'SPEED': -self.__speed if self.__shooter.team == 'blue' else self.__speed,
            }

    def draw(self, window: pygame.Surface | pygame.SurfaceType) -> None:
        """Draw the Bullet"""
        window.blit(self.__bullet_surface, (self.__x, self.__y))


class ServerCharacter(pygame.sprite.Sprite):
    """ This class is for characters made by the server """

    def __init__(self, name: str, team: Literal['red', 'blue'], idx: int,
                 enemy_group: pygame.sprite.Group, win_size: Tuple[int, int]) -> None:
        super().__init__()
        self.__name: str = name
        self.__x: int = 0 if team == 'red' else win_size[0] - 50
        self.__y: int = max((int(win_size[1] * 0.9) - 50 // 5) * (idx - 1), 0)
        self.__team: Literal['red', 'blue'] = team
        self.__idx: int = idx + 1
        self.__hp: int = 100
        self.__enemy_group: pygame.sprite.Group = enemy_group
        self.__win_size: Tuple[int, int] = win_size
        self.__surface: pygame.Surface | pygame.SurfaceType = pygame.Surface((50, 50))
        self.__colour: Tuple[int, int, int] = colours['RED'] if team == 'red' else colours['BLURPLE']
        self.__surface.fill(self.__colour)
        self.__rect: pygame.Rect = self.__surface.get_rect()
        self.__x: int = 0 if team == 'red' else win_size[0] - 50
        self.__min_y = int((0.1 * win_size[1]) + 50)
        self.__y: int = max(int((win_size[1] - 50) // 6) * self.__idx, self.__min_y)
        self.__rect.topleft = (self.x, self.y)

    @property
    def name(self) -> str:
        return self.__name

    @property
    def team(self) -> Literal['red', 'blue']:
        return self.__team

    @property
    def enemy_group(self) -> pygame.sprite.Group:
        return self.__enemy_group

    @property
    def win_size(self) -> Tuple[int, int]:
        return self.__win_size

    @property
    def rect(self) -> pygame.Rect:
        return self.__rect

    @property
    def x(self) -> int:
        return self.__x

    @property
    def y(self) -> int:
        return self.__y

    @property
    def colour(self) -> Tuple[int, int, int]:
        return self.__colour

    def update(self, x, y) -> None:
        """ Updates players position """
        self.__x = x
        self.__y = max(self.__min_y, y)
        self.__rect.topleft = (self.__x, self.__y)

    def hit_enemy(self, enemy: ServerCharacter | Character) -> None:
        enemy.receive_damage(5, self)

    def receive_damage(self, damage: int, _: ServerCharacter | Character) -> None:
        self.__hp -= damage
        if self.__hp <= 0:
            self.kill()

    def on_kill(self) -> None:
        self.kill()

    def draw(self, window: pygame.Surface | pygame.SurfaceType) -> None:
        """Draw the Server Character."""
        window.blit(self.__surface, self.__rect.topleft)
        text_surface = FONT.render(str(self.__idx), True, colours['BLACK'])
        text_rect = text_surface.get_rect(center=self.__rect.center)
        window.blit(text_surface, text_rect)


class Character(pygame.sprite.Sprite):
    """ This class is for the character made by the client """

    def __init__(self, name, game_data: GameData, team: Literal['red', 'blue'], idx: int,
                 enemy_group: pygame.sprite.Group, bullet_group: pygame.sprite.Group,
                 win_size: Tuple[int, int]) -> None:
        super().__init__()
        self.__name: str = name
        self.__game_data: GameData = game_data
        self.__team: Literal['red', 'blue'] = team
        self.__idx: int = idx + 1
        # self.__my_group: pygame.sprite.Group = my_group
        self.__enemy_group: pygame.sprite.Group = enemy_group
        self.__bullet_group: pygame.sprite.Group = bullet_group
        self.__win_size: Tuple[int, int] = win_size
        self.__hp: int = 100
        self.__last_shot_time: dt.datetime = dt.datetime.now()
        self.__surface: pygame.Surface | pygame.SurfaceType = pygame.Surface((50, 50))
        self.__colour: Tuple[int, int, int] = colours['RED'] if team == 'red' else colours['BLURPLE']
        self.__surface.fill(self.__colour)
        self.__rect: pygame.Rect = self.__surface.get_rect()
        self.__max_y: int = int(win_size[1] * 0.9) - 50
        self.__x: int = 0 if team == 'red' else win_size[0] - 50
        self.__min_y = int((0.1 * win_size[1]) + 50)
        self.__y: int = max(int((win_size[1] - 50) // 6) * self.__idx, self.__min_y)
        self.__rect.topleft = (self.__x, self.__y)
        self.__last_move_broadcast: dt.datetime = dt.datetime.now()
        self.__killed: bool = False
        self.broadcast(init=True)

    @property
    def name(self) -> str:
        return self.__name

    @property
    def team(self) -> Literal['red', 'blue']:
        return self.__team

    @property
    def enemy_group(self) -> pygame.sprite.Group:
        return self.__enemy_group

    @property
    def win_size(self) -> Tuple[int, int]:
        return self.__win_size

    @property
    def rect(self) -> pygame.Rect:
        return self.__rect

    @property
    def x(self) -> int:
        return self.__x

    @property
    def y(self) -> int:
        return self.__y

    @property
    def colour(self) -> Tuple[int, int, int]:
        return self.__colour

    def broadcast(self, *, init: bool = False, move: bool = False, kill: bool = False,
                  killed_by: Optional[ServerCharacter] = None) -> None:
        """ Transmits data about itself to the server """
        current_time = dt.datetime.now()
        if kill:
            self.__killed = True
        if self.__killed:
            self.__game_data.to_send['character'] = {
                'COMMAND': 'DEATH',
                'BY': killed_by.name
            }
            return
        if init:
            self.__game_data.to_send['character'] = {
                'COMMAND': 'INIT',
                'X': self.__x,
                'Y': self.__y,
            }
        elif move and \
                (current_time - self.__last_move_broadcast) >= dt.timedelta(milliseconds=2):
            self.__game_data.to_send['character'] = {
                'COMMAND': 'MOVE',
                'X': self.__x,
                'Y': self.__y,
            }

    def shoot(self) -> None:
        current_time = dt.datetime.now()
        if current_time - self.__last_shot_time >= dt.timedelta(seconds=0.2):
            bullet = Bullet(self.__game_data, self)
            self.__bullet_group.add(bullet)  # NOQA
            self.__last_shot_time = current_time

    def hit_enemy(self, enemy: ServerCharacter) -> None:
        enemy.receive_damage(5, self)

    def receive_damage(self, damage: int, hitby: ServerCharacter) -> None:
        self.__hp -= damage
        if self.__hp <= 0:
            self.broadcast(kill=True, killed_by=hitby)
            self.kill()

    def move_right(self) -> None:
        self.__x = min(self.__x + 5, self.win_size[0] - 50)
        self.__rect.topleft = (self.__x, self.__y)
        self.broadcast(move=True)

    def move_left(self) -> None:
        self.__x = max(self.__x - 5, 0)
        self.__rect.topleft = (self.__x, self.__y)
        self.broadcast(move=True)

    def move_down(self) -> None:
        self.__y = min(self.__y + 5, self.win_size[1] - 50)
        self.__rect.topleft = (self.__x, self.__y)
        self.broadcast(move=True)

    def move_up(self) -> None:
        self.__y = max(self.__y - 5, self.__min_y)
        self.__rect.topleft = (self.__x, self.__y)
        self.broadcast(move=True)

    def draw(self, window: pygame.Surface | pygame.SurfaceType) -> None:
        """Draw the character"""
        window.blit(self.__surface, self.__rect.topleft)
        text_surface = FONT.render(str(self.__idx), True, colours['BLACK'])
        text_rect = text_surface.get_rect(center=self.rect.center)
        window.blit(text_surface, text_rect)


class Game(object):
    """ Handles the Game logic """

    def __init__(self, screen: Screen):
        self.__screen: Screen = screen
        self.__client: NetworkClient = screen.client
        self.__game_info: GameInfo = self.__client.game_info
        self.__game_data: GameData = self.__client.GameData
        self.__networking_data: Dict = {}
        self.__red_team: pygame.sprite.Group = pygame.sprite.Group()
        self.__blue_team: pygame.sprite.Group = pygame.sprite.Group()
        self.__bullet_group: pygame.sprite.Group = pygame.sprite.Group()
        self.__lookup_table: Dict[str, List] = {}
        try:
            self.__game_starts_at: dt.datetime = self.__client.lobby.game_starting_at
            self.__game_started: bool = False
        except Exception:
            self.__game_starts_at: dt.datetime = dt.datetime.now()
            self.__game_started: bool = True
        self.__game_finished: bool = False
        self.__next_round_init: bool = False
        self.__score: Dict[str, int] = {'red': 0, 'blue': 0}
        _team_lookup, self.__team = (self.__game_info.red_team, 'red') if self.__client.root.username in \
                                                                          self.__game_info.red_team else (
        self.__game_info.blue_team, 'blue')
        self.__team: Literal['red', 'blue']
        my_group, enemy_group = (self.__red_team, self.__blue_team) if self.__team == 'red' else \
            (self.__blue_team, self.__red_team)
        self.__idx: int = _team_lookup.index(self.__client.root.username)
        self.__character: Character = Character(
            self.__client.root.username, self.__game_data, self.__team, self.__idx, enemy_group,
            self.__bullet_group, self.__screen.win_size
        )
        if self.__team == 'red':
            self.__red_team.add(self.__character)  # NOQA
        else:
            self.__blue_team.add(self.__character)  # NOQA

        for idx, player in enumerate(self.__game_info.red_team):
            if player == self.__client.root.username:
                continue
            else:
                character = ServerCharacter(player, 'red', idx, self.__blue_team, self.__screen.win_size)
                self.__red_team.add(character)  # NOQA
                self.__lookup_table[player] = ['red', idx, character]

        for idx, player in enumerate(self.__game_info.blue_team):
            if player == self.__client.root.username:
                continue
            else:
                character = ServerCharacter(player, 'blue', idx, self.__red_team, self.__screen.win_size)  # NOQA
                self.__blue_team.add(character)  # NOQA
                self.__lookup_table[player] = ['blue', idx, character]

        asyncio.create_task(self.start_countdown(dt.datetime.now(), 'start'))
        asyncio.create_task(self.__screen.client.send_game())

    @property
    def lookup_table(self) -> Dict[str, List]:
        return self.__lookup_table

    def update(self) -> None:
        """ Updates the character class when the specific key bind is pressed for a specific action """
        keys = pygame.key.get_pressed()
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            self.__character.move_right()
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            self.__character.move_left()
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            self.__character.move_down()
        if keys[pygame.K_w] or keys[pygame.K_UP]:
            self.__character.move_up()
        if keys[pygame.K_SPACE]:
            self.__character.shoot()

    def display_headers(self) -> None:
        """ Displays information about the current game round """
        current_round: int = self.__game_info.round
        total_rounds = self.__game_info.total_rounds
        current_round_info: Text = Text(
            self.__screen.handler.dynamic(0.1, 'w'), self.__screen.handler.dynamic(0.05, 'h'), 1, 1,
            colours['BLACK'], f"ROUND: {current_round} / {total_rounds}", size=40
        )

        self.__screen.add_task('text', 'current_round', current_round_info)

        score_board: Text = Text(
            self.__screen.handler.dynamic(0.5, 'w'), self.__screen.handler.dynamic(0.05, 'h'), 1, 1,
            colours['BLACK'], f"RED SCORE: {self.__score['red']} | BLUE SCORE: {self.__score['blue']}", size=30
        )
        self.__screen.add_task('text', 'score_board', score_board)

        class RemainingTime(DynamicText):
            def __init__(self, x: int, y: int, width: int, height: int, colour: Tuple, text: str,
                         fmt_dict: dict,
                         size: int = 28):
                super().__init__(x, y, width, height, colour, text, fmt_dict, size)
                self._fmt_dict = fmt_dict

            def fmt_text(self, text: str) -> str:
                return text.format(time=self._fmt_dict['func'](self._fmt_dict['time']))

        time_left = RemainingTime(
            self.__screen.handler.dynamic(0.5, 'w'), self.__screen.handler.dynamic(0.09, 'h'),
            1, 1, colours['BLACK'], "{time}",
            {"time": self.__game_info.round_end_at, 'func': human_timedelta},
            size=20
        )
        self.__screen.add_task('text', 'time_left', time_left)

    async def start_countdown(self, current: dt.datetime, _for: Literal['start', 'next_round', 'end']) -> None:
        """ Creates a countdown and handles Game logic for the start, next round and the end """
        self.__screen.clear_tasks()
        comparable: dt.datetime = None  # type: ignore
        if _for == 'start':
            comparable = self.__game_starts_at
        elif _for == 'next_round':
            comparable = self.__game_info.round_starts_at
        elif _for == 'end':
            comparable = dt.datetime.now() + dt.timedelta(seconds=15)
        assert comparable is not None
        seconds_left = int((comparable - current).total_seconds())
        if _for == 'start':
            for x in range(seconds_left, 0, -1):
                to_output: Text = Text(
                    self.__screen.handler.dynamic(0.5, 'w'), self.__screen.handler.dynamic(0.5, 'h'), 1, 1,
                    colours['BLACK'], f"Starting in {x:,}", size=30

                )
                self.__screen.add_task('text', 'timed_output', to_output)
                await asyncio.sleep(1)
            self.__screen.remove_task('text', 'timed_output')
            self.display_headers()
            self.__game_started = True

        elif _for == 'next_round':
            winning: str = self.__game_data.from_server['metadata']['won']
            red_lb: List[str] = self.__game_data.from_server['metadata']['red_leaderboard']
            blue_lb: List[str] = self.__game_data.from_server['metadata']['blue_leaderboard']
            out_win: Text = Text(
                self.__screen.handler.dynamic(0.5, 'w'), self.__screen.handler.dynamic(0.5, 'h'), 1, 1,
                colours['BLACK'], winning.upper() + ' WON THE ROUND' if winning != 'draw' else winning.upper(), size=30
            )
            self.__screen.add_task('text', 'out_winners', out_win)

            red, blue = self.__score['red'], self.__score['blue']
            if winning == 'draw':
                red += 1
                blue += 1
            elif winning == 'red':
                red += 1
            else:
                blue += 1
            self.__score['red'], self.__score['blue'] = red, blue

            def output_lb(name: str, lb: List[str], start_w: float, start_h: float):
                x_inc: int = self.__screen.handler.dynamic(start_w, 'w')
                y_inc: int = self.__screen.handler.dynamic(start_h, 'h')
                for idx, ln in enumerate(lb):
                    y_inc += 50
                    ln_txt = Text(
                        x_inc, y_inc, 50, 50, colours['BLACK'], ln
                    )
                    self.__screen.add_task('text', f'{name}_lb_{idx}', ln_txt)

            output_lb('red', red_lb, 0.2, 0.1)
            output_lb('blue', blue_lb, 0.8, 0.1)

            for x in range(seconds_left, 0, -1):
                to_output = Text(
                    self.__screen.handler.dynamic(0.5, 'w'), self.__screen.handler.dynamic(0.1, 'h'), 1, 1,
                    colours['BLACK'], f"Next round starting in {x:,}", size=30

                )
                self.__screen.add_task('text', 'timed_output', to_output)
                await asyncio.sleep(1)

            self.__screen.clear_tasks()
            self.init_next()
            self.display_headers()
            self.__next_round_init = False

        elif _for == 'end':
            winning: str = self.__game_data.from_server['metadata']['won']
            red_lb: List[str] = self.__game_data.from_server['metadata']['red_leaderboard']
            blue_lb: List[str] = self.__game_data.from_server['metadata']['blue_leaderboard']
            out_win: Text = Text(
                self.__screen.handler.dynamic(0.5, 'w'), self.__screen.handler.dynamic(0.5, 'h'), 1, 1,
                colours['BLACK'], winning.upper() + ' WON' if winning != 'draw' else winning.upper(), size=70
            )
            self.__screen.add_task('text', 'out_winners', out_win)

            def output_lb(name: str, lb: List[str], start_w: float, start_h: float):
                x_inc: int = self.__screen.handler.dynamic(start_w, 'w')
                y_inc: int = self.__screen.handler.dynamic(start_h, 'h')
                for idx, ln in enumerate(lb):
                    y_inc += 50
                    ln_txt = Text(
                        x_inc, y_inc, 50, 50, colours['BLACK'], ln
                    )
                    self.__screen.add_task('text', f'{name}_lb_{idx}', ln_txt)

            output_lb('red', red_lb, 0.2, 0.1)
            output_lb('blue', blue_lb, 0.8, 0.1)

            for x in range(seconds_left, 0, -1):
                to_output = Text(
                    self.__screen.handler.dynamic(0.5, 'w'), self.__screen.handler.dynamic(0.1, 'h'), 1, 1,
                    colours['BLACK'],
                    f"Back to lobby in {x:,}" if self.__screen.client.lobby else f"Back to main menu in {x:,}", size=30

                )
                self.__screen.add_task('text', 'timed_output', to_output)
                await asyncio.sleep(1)

            self.__screen.clear_tasks()
            self.__game_finished = True
            asyncio.create_task(self.__screen.handler.on_game_finish())

    def init_next(self) -> None:
        """initializes the next round."""
        self.__red_team: pygame.sprite.Group = pygame.sprite.Group()
        self.__blue_team: pygame.sprite.Group = pygame.sprite.Group()
        self.__bullet_group: pygame.sprite.Group = pygame.sprite.Group()
        my_group, enemy_group = (self.__red_team, self.__blue_team) if self.__team == 'red' else \
            (self.__blue_team, self.__red_team)
        self.__character: Character = Character(
            self.__client.root.username, self.__client.GameData, self.__team, self.__idx, enemy_group,
            self.__bullet_group, self.__screen.win_size
        )
        if self.__team == 'red':
            self.__red_team.add(self.__character)  # NOQA
        else:
            self.__blue_team.add(self.__character)  # NOQA

        for player in self.__lookup_table:
            data = self.__lookup_table[player]
            my_group, enemy_group = (self.__red_team, self.__blue_team) if data[0] == 'red' else \
                (self.__blue_team, self.__red_team)
            character = ServerCharacter(player, data[0], data[1], enemy_group, self.__screen.win_size)
            data[2] = character
            if data[0] == 'red':
                self.__red_team.add(character)  # NOQA
            else:
                self.__blue_team.add(character)  # NOQA
        self.__next_round_init = False

    def create_bullet(self, payload: Dict):
        """ Allows the server to represent bullets made by other clients """
        bullet = ServerBullet(self.__lookup_table[payload['OWNER']][2], payload['X'], payload['Y'], payload['SPEED'])
        self.__bullet_group.add(bullet)  # NOQA

    async def handle(self, window: pygame.Surface | pygame.SurfaceType):
        """ Handles the logic for the Game """
        if self.__game_finished:
            return

        current_time = dt.datetime.now()
        if not self.__game_started:
            return
        elif self.__next_round_init:
            return

        elif current_time >= self.__game_info.round_end_at or len(self.__red_team) == 0 or len(self.__blue_team) == 0:
            if self.__game_data.from_server['next_check']:  # server acknowledgement
                self.__game_data.from_server['next_check'] = False
                self.__next_round_init = True
                if self.__game_info.total_rounds < self.__game_info.round + 1:
                    asyncio.create_task(self.start_countdown(current_time, 'end'))
                else:
                    self.__game_info.round += 1
                    self.__game_info.round_starts_at = current_time + dt.timedelta(seconds=15)
                    self.__game_info.round_end_at = current_time + dt.timedelta(
                        seconds=self.__game_info.round_length + 15
                    )
                    asyncio.create_task(self.start_countdown(current_time, 'next_round'))
        else:
            self.update()

            for spri in self.__red_team:  # type: Union[ServerCharacter, Character]
                spri.draw(window)

            for spri in self.__blue_team:  # type: Union[ServerCharacter, Character]
                spri.draw(window)

            for bul in self.__bullet_group:  # type: Union[ServerBullet, Bullet]
                bul.update()
                bul.draw(window)
