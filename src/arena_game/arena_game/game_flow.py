"""Round flow of the token game: teams, phases, secret roles and guesses.

GameFlow sits between whatever drives the game and the rules in
game_rules.py. It takes commands, such as starting a round or crediting a
guess, and describes the game as a dictionary of plain values that a screen
can draw and a ROS 2 node can send as JSON. It knows nothing of cameras,
windows or ROS, so the same flow runs the ROS 2 game node and the
standalone game.

Teams are numbered like their robots and controllers, so Team 6 drives
robot 6. The arena has four corners, numbered 1 to 4 as in token_zones.py,
and each team that joins takes the next free corner in CORNER_ORDER.

A command is a dictionary with a 'cmd' key, and is ignored unless it fits
the current phase:

    {'cmd': 'join', 'team': 6}         a team joins, before round 1
    {'cmd': 'toggle_team', 'team': 6}  a team joins or leaves, before round 1
    {'cmd': 'roles'}                   teams enter their secret roles in turn
    {'cmd': 'pick', 'color': 'Red'}    the entering team's star, then decoy
    {'cmd': 'skip_roles'}              the teams left play every color regular
    {'cmd': 'start'}                   start the round once the roles are in
    {'cmd': 'credit', 'team': 6}       credit the waiting guess to a team
    {'cmd': 'ignore'}                  drop the waiting guess
    {'cmd': 'end'}                     end the round early
"""
from collections import deque

from arena_game.game_rules import COLORS, DECOY, STAR, GameRules

# Corners in the order joining teams take them. Corners 1 and 3 face each
# other across the board, so the first two teams to join play opposite.
CORNER_ORDER = (1, 3, 2, 4)
MAX_TEAM = 9  # Teams 0 to 9, numbered like their robots


class GameFlow:
    """Runs the rounds of one game from commands and zone changes."""

    def __init__(self, rounds, round_seconds, teams=(), log=print):
        self.rounds = rounds
        self.round_seconds = round_seconds
        self.log = log
        self.corners = {}  # Corner to the team playing from it
        for team in teams:
            self.join(team)
        self.new_game()

    @property
    def teams(self):
        return sorted(self.corners.values())

    def new_game(self):
        self.rules = GameRules(self.rounds, self.round_seconds, self.teams)
        # Tokens in each team's base, kept up to date from the camera.
        self.bases = {team: {color: 0 for color in COLORS}
                      for team in self.teams}
        self.phase = 'between'  # between, roles, ready, playing or over
        self.entering = []  # Teams still to enter their roles
        self.star = None  # Star picked by the team entering its roles
        self.message = ''
        self.waiting = deque()  # (target, color) guesses not yet credited

    @property
    def choosing_teams(self):
        """Teams can join or leave until the first round of a game."""
        return self.phase == 'between' and not self.rules.results

    def join(self, team):
        """Give a team the next free corner, if it can join."""
        if not 0 <= team <= MAX_TEAM or team in self.corners.values():
            return
        free = [corner for corner in CORNER_ORDER if corner not in self.corners]
        if not free:
            self.log(f'Team {team} cannot join: all four corners are taken')
            return
        self.corners[free[0]] = team
        self.log(f'Team {team} joined, playing from corner {free[0]}')

    def leave(self, team):
        for corner, other in list(self.corners.items()):
            if other == team:
                del self.corners[corner]
                self.log(f'Team {team} left')

    def set_bases(self, counts):
        """Take {corner: {color: count}} for the tokens in each base."""
        self.bases = {team: {color: int(counts.get(corner, {}).get(color, 0))
                             for color in COLORS}
                      for corner, team in self.corners.items()}

    def command(self, command, now):
        name = command.get('cmd')
        try:
            team = int(command.get('team', -1))
        except (TypeError, ValueError):
            team = -1  # No such team, so the command is ignored
        if name in ('join', 'toggle_team') and self.choosing_teams:
            if name == 'toggle_team' and team in self.teams:
                self.leave(team)
            else:
                self.join(team)
            self.new_game()
        elif name == 'roles' and self.phase == 'over':
            # Back to choosing the teams for a new game.
            self.new_game()
        elif name == 'roles' and self.phase != 'playing' and self.teams:
            self.rules.clear_roles()
            self.entering = list(self.teams)
            self.star = None
            self.message = ''
            self.phase = 'roles'
        elif name == 'pick' and self.phase == 'roles':
            if command.get('color') in COLORS:
                self.pick(command['color'])
        elif name == 'skip_roles' and self.phase == 'roles':
            self.entering = []
            self.phase = 'ready'
        elif name == 'start' and self.phase == 'ready':
            self.waiting.clear()
            self.rules.start_round(now)
            self.phase = 'playing'
            self.log(f'Round {self.rules.round} started')
        elif name == 'end' and self.phase == 'playing':
            self.end_round()
        elif name == 'credit' and self.phase == 'playing' and self.waiting:
            self.credit(team)
        elif name == 'ignore' and self.phase == 'playing' and self.waiting:
            target, color = self.waiting.popleft()
            self.log(f'Ignored {color} in Team {target} guess zone')

    def pick(self, color):
        """Take a team's star, then its decoy."""
        if self.star is None:
            self.star = color
            return
        team = self.entering[0]
        try:
            self.rules.set_roles(team, self.star, color)
        except ValueError as error:
            self.message = str(error)
            return
        self.log(f'Team {team} roles set')
        self.entering.pop(0)
        self.star = None
        self.message = ''
        if not self.entering:
            self.phase = 'ready'

    def tick(self, now):
        if self.phase == 'playing' and self.rules.time_left(now) <= 0:
            self.end_round()

    def on_zone_change(self, zone, corner, color, old_count, new_count):
        """A token arriving in a guess zone during a round is a guess."""
        target = self.corners.get(corner)
        if (self.phase == 'playing' and zone == 'guess'
                and new_count > old_count and target is not None):
            self.waiting.append((target, color))

    def credit(self, guesser):
        target, color = self.waiting.popleft()
        problem = self.rules.guess(guesser, target, color)
        if problem:
            self.log(f'{problem}, ignored')
        else:
            self.log(f'Guess: Team {guesser} on Team {target} with {color}')

    def end_round(self):
        results = self.rules.end_round(self.bases)
        self.waiting.clear()
        self.phase = 'over' if self.rules.over else 'between'
        self.log(f'Round {results["round"]} results')
        for team in self.rules.teams:
            roles = results['roles'].get(team, {})
            self.log(f'  Team {team}: star {roles.get(STAR, "-")}, '
                     f'decoy {roles.get(DECOY, "-")}; '
                     f'base {results["base"][team]:g}, '
                     f'guesses {results["swing"][team]:+.1f}, '
                     f'total {self.rules.totals[team]:.1f}')

    def state(self, now):
        """Describe the game in plain values, with numbers as dictionary
        keys written as text, the way it reads after a trip through JSON."""
        rules = self.rules
        entering = None
        if self.phase == 'roles' and self.entering:
            entering = {'team': self.entering[0],
                        'role': STAR if self.star is None else DECOY}
        results = None
        if rules.results:
            last = rules.results[-1]
            results = {
                'round': last['round'],
                'base': {str(t): v for t, v in last['base'].items()},
                'swing': {str(t): v for t, v in last['swing'].items()},
                'roles': {str(t): r for t, r in last['roles'].items()},
                'outcomes': [
                    {'guesser': g, 'target': t, 'color': c, 'result': r,
                     'moved': moved}
                    for g, t, c, r, moved in last['outcomes']],
            }
        return {
            'phase': self.phase,
            'teams': list(rules.teams),
            'corners': {str(c): t for c, t in sorted(self.corners.items())},
            'choosing_teams': self.choosing_teams,
            'round': rules.round,
            'rounds': rules.rounds,
            'time_left': rules.time_left(now),
            'totals': {str(t): rules.totals[t] for t in rules.teams},
            'bases': {str(t): dict(counts)
                      for t, counts in self.bases.items()},
            'entering': entering,
            'roles_done': [t for t in rules.teams if t in rules.roles],
            'message': self.message,
            'waiting': [{'team': t, 'color': c} for t, c in self.waiting],
            'guesses': [{'guesser': g, 'target': t, 'color': c}
                        for (g, t), c in rules.guesses.items()],
            'results': results,
        }
