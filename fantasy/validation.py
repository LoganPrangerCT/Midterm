"""Validate team selections and normalized picks imported from Sleeper."""
from .grading import normalize_name, SUPPORTED_SEASON
import unicodedata


class ValidationError(ValueError):
    pass


def fail(message):
    raise ValidationError(message)


def fields(value, required, label):
    if not isinstance(value, dict):
        fail(f'{label} must be a JSON object')
    missing = required - value.keys()
    extra = value.keys() - required
    if missing:
        fail(f'{label} missing fields: {", ".join(sorted(missing))}')
    if extra:
        fail(f'{label} contains unknown or server-owned fields: {", ".join(sorted(extra))}')


def name(value, label, maximum):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        fail(f'{label} must be a nonempty string of at most {maximum} characters')
    if any(unicodedata.category(c) in ('Cc', 'Cs') for c in value):
        fail(f'{label} cannot contain control characters or invalid Unicode')
    return value.strip()


def integer(value, label, maximum):
    if type(value) is not int or not 1 <= value <= maximum:
        fail(f'{label} must be an integer from 1 to {maximum}')
    return value


def validate(body):
    fields(body, {'teamName', 'season', 'picks'}, 'body')
    team = name(body['teamName'], 'teamName', 100)
    if type(body['season']) is not int or body['season'] != SUPPORTED_SEASON:
        fail(f'season must be {SUPPORTED_SEASON}, the snapshot season')
    if not isinstance(body['picks'], list) or not 1 <= len(body['picks']) <= 30:
        fail('picks must contain 1 to 30 picks')
    picks, numbers, players = [], set(), set()
    for i, pick in enumerate(body['picks']):
        label = f'picks[{i}]'
        fields(pick, {'overallPick', 'round', 'playerName', 'position'}, label)
        number = integer(pick['overallPick'], f'{label}.overallPick', 1000)
        rnd = integer(pick['round'], f'{label}.round', 30)
        player = name(pick['playerName'], f'{label}.playerName', 120)
        position = pick['position']
        if not isinstance(position, str) or position not in ('QB', 'RB', 'WR', 'TE', 'K', 'D/ST'):
            fail(f'{label}.position must be QB, RB, WR, TE, K, or D/ST')
        normalized = normalize_name(player)
        if not normalized:
            fail(f'{label}.playerName must contain a player name')
        if number in numbers or normalized in players:
            fail(f'{label} duplicates an overall pick or normalized player name')
        numbers.add(number)
        players.add(normalized)
        picks.append(dict(overallPick=number, round=rnd, playerName=player, position=position))
    return dict(teamName=team, season=SUPPORTED_SEASON, picks=picks)
