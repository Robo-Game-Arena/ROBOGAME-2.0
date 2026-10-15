"""The scoreboard panel, drawn from a game state, and the instructor's keys.

draw_panel() draws whatever GameFlow.state() describes, so it works the
same whether the state came straight from GameFlow or over a ROS 2 topic
as JSON. key_command() turns a key press into a GameFlow command.

Keys:
    0 to 9   before round 1, add or remove that team (teams can also join
             by pressing OPTIONS on their controller)
    n        enter the secret roles for the next round
    r g b y  pick a color while entering roles
    space    start the round once the roles are in
    0 to 9   during a round, credit the waiting guess to that team
    x        drop the waiting guess
    e        end the round early
"""
import math

import numpy as np

from arena_game.arena_check import label
from arena_game.game_rules import COLORS
from arena_game.token_zones import (
    CYAN, GRAY, MAGENTA, PANEL_WIDTH, RED, TOKEN_BGR, VIEW_HEIGHT, WHITE)

KEYS_HINT = 'l re-lock   s save   q quit'
COLOR_KEYS = {ord(color[0].lower()): color for color in COLORS}
# Where each team's base is in the camera view on the NUC.
CORNER_NAMES = {1: 'bottom right', 2: 'top right', 3: 'top left',
                4: 'bottom left'}


def key_command(key, phase):
    """Return the GameFlow command for a key, or None."""
    if key == ord('n'):
        return {'cmd': 'roles'}
    if key in COLOR_KEYS:
        return {'cmd': 'pick', 'color': COLOR_KEYS[key]}
    if key == ord(' '):
        return {'cmd': 'start' if phase == 'ready' else 'skip_roles'}
    if key == ord('e'):
        return {'cmd': 'end'}
    if key == ord('x'):
        return {'cmd': 'ignore'}
    if ord('0') <= key <= ord('9'):
        team = key - ord('0')
        if phase == 'playing':
            return {'cmd': 'credit', 'team': team}
        return {'cmd': 'toggle_team', 'team': team}
    return None


def points(value):
    """Format points, which guesses can make fractional, as 6 or 1.8."""
    value = round(value, 1)
    return f'{value:g}' if value else '0'


def signed(value):
    value = round(value, 1)
    return f'{value:+g}' if value else '+0'


def outcome_text(outcome):
    guesser, target = outcome['guesser'], outcome['target']
    color, result = outcome['color'], outcome['result']
    if result == 'regular':
        return (f'Team {guesser} guessed Team {target} {color}: '
                'regular, no change')
    return (f'Team {guesser} guessed Team {target} {color}: '
            f'{result}, Team {guesser} {signed(outcome["moved"])}')


def draw_panel(state):
    panel = np.full((VIEW_HEIGHT, PANEL_WIDTH, 3), 30, np.uint8)
    if state is None:
        label(panel, 'Waiting for the game node', (20, 40), GRAY, 0.8)
    elif state['phase'] == 'roles':
        draw_roles(panel, state)
    elif state['phase'] == 'playing':
        draw_round(panel, state)
    else:
        draw_between(panel, state)
    return panel


def draw_roles(panel, state):
    team, role = state['entering']['team'], state['entering']['role']
    label(panel, f'Round {state["round"]}: secret roles', (20, 40), WHITE,
          0.9)
    label(panel, f'Team {team}', (20, 115), WHITE, 1.4)
    label(panel, f'press your {role.upper()} color', (20, 165), CYAN, 1.0)
    for column, color in enumerate(COLORS):
        label(panel, color[0], (40 + 80 * column, 240), TOKEN_BGR[color], 1.6)
    label(panel, state['message'], (20, 290), RED, 0.65)
    label(panel, 'Everyone else, look away', (20, 340), GRAY, 0.7)
    done = [f'Team {t}' for t in state['roles_done']]
    label(panel, 'Roles set: ' + (', '.join(done) or 'none yet'), (20, 390),
          WHITE, 0.65)
    label(panel, 'n starts the roles over   space skips the rest',
          (20, 770), GRAY, 0.55)


def draw_round(panel, state):
    left = math.ceil(state['time_left'])
    label(panel, f'Round {state["round"]} of {state["rounds"]}', (20, 40),
          WHITE, 0.9)
    label(panel, f'{left // 60}:{left % 60:02d}', (20, 125),
          RED if left <= 10 else WHITE, 2.2)
    y = 185
    for team in state['teams']:
        label(panel, f'Team {team}', (20, y), WHITE, 0.7)
        for column, color in enumerate(COLORS):
            count = state['bases'][str(team)][color]
            label(panel, f'{color[0]} {count}', (150 + 62 * column, y),
                  TOKEN_BGR[color] if count else GRAY, 0.7)
        y += 34
    y += 25
    waiting = state['waiting']
    if waiting:
        label(panel, f'{waiting[0]["color"]} token in Team '
              f'{waiting[0]["team"]} guess zone', (20, y), MAGENTA, 0.8)
        label(panel, 'Which team guessed? Press its number, x ignores',
              (20, y + 36), MAGENTA, 0.7)
        if len(waiting) > 1:
            label(panel, f'{len(waiting) - 1} more waiting', (20, y + 68),
                  GRAY, 0.6)
    y += 115
    label(panel, 'Guesses this round', (20, y), WHITE, 0.7)
    for row, guess in enumerate(state['guesses'][-8:]):
        label(panel, f'Team {guess["guesser"]} on Team {guess["target"]} '
              f'with {guess["color"]}', (20, y + 32 + 26 * row), WHITE, 0.6)
    label(panel, 'e ends the round early', (20, 770), GRAY, 0.55)


def draw_between(panel, state):
    if state['phase'] == 'over':
        title, hint = 'Game over', 'n starts a new game'
    elif state['phase'] == 'ready':
        title = f'Round {state["round"]} of {state["rounds"]}'
        hint = 'Roles are in. Space starts the round'
    else:
        title = f'Round {state["round"]} of {state["rounds"]}'
        hint = 'n enters the secret roles'
    label(panel, title, (20, 40), WHITE, 0.9)
    label(panel, hint, (20, 80), CYAN, 0.7)
    in_bases = sum(sum(state['bases'][str(team)].values())
                   for team in state['teams'])
    if in_bases and state['phase'] != 'over':
        label(panel, f'{in_bases} tokens still in bases, clear them before '
              'starting', (20, 112), RED, 0.6)

    if state['choosing_teams']:
        draw_team_choice(panel, state)
        return

    results = state['results']
    totals = state['totals']
    label(panel, 'Totals', (20, 160), WHITE, 0.75)
    leader = max(totals.values())
    for row, team in enumerate(state['teams']):
        total = totals[str(team)]
        color = CYAN if results and total == leader else WHITE
        label(panel, f'Team {team}   {points(total)}', (40, 195 + 30 * row),
              color, 0.7)

    if not results:
        return
    y = 345
    label(panel, f'Round {results["round"]} results', (20, y), WHITE, 0.75)
    for team in state['teams']:
        roles = results['roles'].get(str(team), {})
        base = results['base'][str(team)]
        swing = results['swing'][str(team)]
        label(panel, f'Team {team}: base {points(base)}, guesses '
              f'{signed(swing)}, round {points(base + swing)}', (20, y + 32),
              WHITE, 0.6)
        label(panel, f'star {roles.get("star", "-")}, '
              f'decoy {roles.get("decoy", "-")}', (60, y + 56), GRAY, 0.55)
        y += 56
    for outcome in results['outcomes'][:7]:
        label(panel, outcome_text(outcome), (20, y + 40), WHITE, 0.5)
        y += 24


def draw_team_choice(panel, state):
    label(panel, 'Who is playing?', (20, 160), WHITE, 0.75)
    corners = state['corners']
    for row, corner in enumerate(sorted(CORNER_NAMES)):
        team = corners.get(str(corner))
        text = f'Team {team}' if team is not None else 'open'
        label(panel, f'{CORNER_NAMES[corner]} corner', (40, 200 + 36 * row),
              WHITE if team is not None else GRAY, 0.7)
        label(panel, text, (330, 200 + 36 * row),
              CYAN if team is not None else GRAY, 0.7)
    label(panel, 'Press OPTIONS on a controller to join,', (20, 370), CYAN,
          0.65)
    label(panel, 'or press a team number here to add or remove it',
          (20, 400), CYAN, 0.65)
    label(panel, 'The first two teams to join play opposite corners',
          (20, 440), GRAY, 0.6)
