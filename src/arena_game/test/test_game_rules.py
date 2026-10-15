"""Checks of the game rules, which need no camera.

    python3 -m pytest src/arena_game/test
"""
import pytest

from arena_game.game_rules import GameRules


def test_each_team_values_tokens_by_its_own_roles():
    rules = GameRules()
    rules.set_roles(1, star='Red', decoy='Blue')
    rules.set_roles(2, star='Blue', decoy='Red')
    bases = {1: {'Red': 1, 'Blue': 1, 'Green': 1},
             2: {'Red': 1, 'Blue': 1, 'Green': 1}}
    results = rules.end_round(bases)
    assert results['base'][1] == 5 + 1 + 3
    assert results['base'][2] == 1 + 5 + 3


def test_guessing_the_star_takes_60_percent_of_its_points():
    rules = GameRules()
    rules.set_roles(2, star='Yellow', decoy='Green')
    assert rules.guess(1, 2, 'Yellow') is None
    results = rules.end_round({2: {'Yellow': 2}})
    assert results['swing'][1] == pytest.approx(6)
    assert results['swing'][2] == pytest.approx(-6)
    assert rules.totals[2] == pytest.approx(4)


def test_guessing_the_decoy_gives_60_percent_of_your_own_points():
    rules = GameRules()
    rules.set_roles(1, star='Red', decoy='Blue')
    rules.set_roles(3, star='Blue', decoy='Red')
    rules.guess(3, 1, 'Blue')
    results = rules.end_round({3: {'Blue': 1}})
    assert results['swing'][3] == pytest.approx(-3)
    assert results['swing'][1] == pytest.approx(3)


def test_guessing_a_regular_color_moves_nothing():
    rules = GameRules()
    rules.set_roles(2, star='Yellow', decoy='Green')
    rules.guess(1, 2, 'Red')
    results = rules.end_round({1: {'Red': 2}, 2: {'Red': 2}})
    assert results['swing'] == {1: 0, 2: 0, 3: 0, 4: 0}


def test_only_the_first_guess_at_each_opponent_counts():
    rules = GameRules()
    assert rules.guess(1, 2, 'Red') is None
    assert rules.guess(1, 2, 'Blue') is not None
    assert rules.guess(1, 1, 'Blue') is not None
    assert rules.guess(1, 3, 'Blue') is None
    assert rules.guesses == {(1, 2): 'Red', (1, 3): 'Blue'}


def test_a_two_team_game_leaves_the_other_corners_out():
    rules = GameRules(teams=(1, 3))
    rules.set_roles(1, star='Red', decoy='Blue')
    assert rules.guess(1, 2, 'Red') is not None
    assert rules.guess(3, 1, 'Red') is None
    results = rules.end_round({1: {'Red': 1}, 2: {'Red': 5}})
    assert set(results['base']) == {1, 3}
    assert rules.totals == {1: pytest.approx(2), 3: pytest.approx(3)}


def test_star_and_decoy_must_differ():
    with pytest.raises(ValueError):
        GameRules().set_roles(1, star='Red', decoy='Red')


def test_roles_are_chosen_again_each_round_and_the_game_ends():
    rules = GameRules(rounds=2)
    rules.set_roles(1, star='Red', decoy='Blue')
    rules.end_round({1: {'Red': 1}})
    assert rules.roles == {} and rules.round == 2 and not rules.over
    rules.end_round({1: {'Red': 1}})
    assert rules.over
    assert rules.totals[1] == 5 + 3
