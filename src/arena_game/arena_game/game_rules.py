"""Rules of the star and decoy token game, with no camera or screen code.

These are the old game's rules. Before each round, every team secretly makes
one token color its star (5 points), one its decoy (1 point) and the other
two regular (3 points). Teams score by delivering tokens of any color to
their own base, each token valued by the team's own roles. A team guesses an
opponent's star by putting a token of that color in the opponent's guess
zone. Only its first guess at each opponent in a round counts, and guesses
settle when the round ends:

- the target's star: the guesser takes 60% of the target's points in it
- the target's decoy: the guesser gives 60% of its own points in that color
  to the target
- a regular color: nothing moves

This file only keeps the score. Whatever runs the game tells it the roles,
the guesses and the tokens in each base, and reads the results back. Here
that is game_flow.py, which runs the rounds for both the ROS 2 game node
and the standalone game.
"""

COLORS = ('Red', 'Green', 'Blue', 'Yellow')
TEAMS = (1, 2, 3, 4)
ROUNDS = 3
ROUND_SECONDS = 180

STAR, DECOY, REGULAR = 'star', 'decoy', 'regular'
VALUES = {STAR: 5, REGULAR: 3, DECOY: 1}
TRANSFER = 0.6  # Share of the points that a settled guess moves


class GameRules:
    """The roles, guesses and scores of one game.

    teams lists the teams playing, which can be any of the four corners.
    """

    def __init__(self, rounds=ROUNDS, round_seconds=ROUND_SECONDS,
                 teams=TEAMS):
        self.rounds = rounds
        self.round_seconds = round_seconds
        self.teams = tuple(teams)
        self.round = 1  # The round being set up or played
        self.playing = False
        self.ends_at = None
        self.totals = {team: 0.0 for team in self.teams}
        self.roles = {}  # Team to {STAR: color, DECOY: color}
        self.guesses = {}  # (guesser, target) to color, this round
        self.results = []  # One entry per finished round

    @property
    def over(self):
        return len(self.results) >= self.rounds

    def clear_roles(self):
        self.roles = {}

    def set_roles(self, team, star, decoy):
        """Set a team's secret roles. Its other two colors are regular."""
        if star == decoy:
            raise ValueError('The decoy must differ from the star')
        self.roles[team] = {STAR: star, DECOY: decoy}

    def value(self, team, color):
        """Points for one token of this color in this team's base."""
        roles = self.roles.get(team, {})
        for role in (STAR, DECOY):
            if roles.get(role) == color:
                return VALUES[role]
        return VALUES[REGULAR]

    def start_round(self, now):
        self.guesses = {}
        self.playing = True
        self.ends_at = now + self.round_seconds

    def time_left(self, now):
        return max(0.0, self.ends_at - now) if self.playing else 0.0

    def guess(self, guesser, target, color):
        """Record a guess. Return why it does not count, or None if it does."""
        for team in (guesser, target):
            if team not in self.teams:
                return f'Team {team} is not playing'
        if guesser == target:
            return f'Team {guesser} cannot guess its own zone'
        if (guesser, target) in self.guesses:
            return f'Team {guesser} already guessed Team {target} this round'
        self.guesses[(guesser, target)] = color
        return None

    def end_round(self, base_counts):
        """Score the round and settle its guesses.

        base_counts maps each team to {color: tokens of it in the team's
        base} when the round ends. Returns the round's results, which are
        also kept in self.results.
        """
        def count(team, color):
            return base_counts.get(team, {}).get(color, 0)

        base = {team: sum(count(team, color) * self.value(team, color)
                          for color in COLORS)
                for team in self.teams}

        # `moved` is what the guesser gains, and negative when it loses.
        swing = {team: 0.0 for team in self.teams}
        outcomes = []
        for (guesser, target), color in self.guesses.items():
            target_roles = self.roles.get(target, {})
            if target_roles.get(STAR) == color:
                moved = TRANSFER * count(target, color) * VALUES[STAR]
                result = STAR
            elif target_roles.get(DECOY) == color:
                moved = -TRANSFER * (count(guesser, color)
                                     * self.value(guesser, color))
                result = DECOY
            else:
                moved, result = 0.0, REGULAR
            swing[guesser] += moved
            swing[target] -= moved
            outcomes.append((guesser, target, color, result, moved))

        for team in self.teams:
            self.totals[team] += base[team] + swing[team]
        results = {'round': self.round, 'base': base, 'swing': swing,
                   'roles': self.roles, 'outcomes': outcomes}
        self.results.append(results)

        self.playing = False
        self.roles = {}
        if not self.over:
            self.round += 1
        return results
