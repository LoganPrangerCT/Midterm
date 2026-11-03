"""Import draft history from Sleeper API and normalize for grading."""
import re
from .grading import SUPPORTED_SEASON
from .sleeper_client import (
    UpstreamError,
    UpstreamNotFoundError,
    get_draft_picks,
    get_league,
    get_league_drafts,
    get_league_rosters,
    get_league_users,
)
from .validation import ValidationError, validate


def clean_id(value, label):
    if type(value) is int:
        value = str(value)
    if not isinstance(value, str) or re.fullmatch(r'[0-9]{15,22}', value) is None:
        raise ValidationError(f'{label} must be a 15-22 digit string')
    return value


def import_sleeper_league(league_id):
    """Read and validate a complete league draft before saving any of it."""
    league_id = clean_id(league_id, 'leagueId')

    try:
        league = get_league(league_id)
        if league is None:
            raise UpstreamNotFoundError(f'Sleeper league {league_id} not found')
        drafts = get_league_drafts(league_id)
        if not drafts:
            raise UpstreamNotFoundError(f'No drafts found for league {league_id}')
        draft = select_draft(league, drafts)

        rosters = get_league_rosters(league_id)
        if not rosters:
            raise UpstreamNotFoundError(f'No rosters found for league {league_id}')
        users = get_league_users(league_id)
        teams = read_league_teams(draft, rosters, users)
        return league_snapshot(league_id, league, draft, rosters, users, teams)
    except (ValidationError, UpstreamError):
        raise
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise UpstreamError('Sleeper returned incomplete or invalid draft data') from exc


def read_league_teams(draft, rosters, users):
    picks = get_draft_picks(draft['draft_id'])
    if not picks:
        raise UpstreamNotFoundError(f'No picks found for draft {draft["draft_id"]}')
    normalize_roster_ids(picks)
    check_picks(draft, picks, {r['roster_id'] for r in rosters})
    return [read_team_picks(draft, picks, r['roster_id'], roster_name(r, users))
            for r in rosters if any(p['roster_id'] == r['roster_id'] for p in picks)]


def league_snapshot(league_id, league, draft, rosters, users, teams):
    return {
        'leagueId': league_id, 'leagueName': league.get('name') or league_id,
        'draftId': draft['draft_id'], 'season': int(draft['season']),
        'rosters': [{'roster_id': r['roster_id'], 'owner_id': r.get('owner_id'),
                     'co_owners': r.get('co_owners') or []} for r in rosters],
        'users': [{'user_id': u['user_id'], 'display_name': u.get('display_name'),
                   'username': u.get('username'),
                   'metadata': {'team_name': (u.get('metadata') or {}).get('team_name')}}
                  for u in users],
        'teams': teams,
    }


def select_draft(league, drafts):
    """Use the league-linked completed draft, or its only completed draft."""
    complete_drafts = [d for d in drafts if d.get('status') == 'complete']
    if not complete_drafts:
        raise ValidationError('No completed draft found for this league')
    selected_draft = next(
        (d for d in complete_drafts if d.get('draft_id') == league.get('draft_id')), None
    )
    if selected_draft is None:
        if len(complete_drafts) != 1:
            raise ValidationError('League has multiple completed drafts without a matching linked draft')
        selected_draft = complete_drafts[0]
    draft_id = selected_draft['draft_id']

    if selected_draft.get('status') != 'complete':
        raise ValidationError('Selected draft is not complete')
    try:
        draft_id = clean_id(draft_id, 'draftId')
    except ValidationError as exc:
        raise UpstreamError('Sleeper returned an invalid draft ID') from exc

    draft_season = selected_draft.get('season')
    if str(draft_season) != str(SUPPORTED_SEASON):
        raise ValidationError(
            f'Draft season {draft_season} is not supported; only season {SUPPORTED_SEASON} is supported'
        )

    return {**selected_draft, 'draft_id': draft_id}


def roster_name(roster, users):
    owner = next((u for u in users if u.get('user_id') == roster.get('owner_id')), {})
    return ((owner.get('metadata') or {}).get('team_name')
            or owner.get('display_name') or owner.get('username')
            or f'Team {roster["roster_id"]}')


def select_team(rosters, users, selector, league_id):
    """Find a team by its name, manager display name, username or user ID."""
    matching_users = [
        u for u in users if (
            (u.get('display_name') or '').lower() == selector.lower()
            or (u.get('username') or '').lower() == selector.lower()
            or u.get('user_id') == selector
            or ((u.get('metadata') or {}).get('team_name') or '').lower() == selector.lower()
        )
    ]
    if len(matching_users) > 1:
        raise ValidationError('Team name is ambiguous; use a unique manager username or user ID as teamName')
    user = matching_users[0] if matching_users else None
    if not user:
        raise UpstreamNotFoundError(f'Team or manager "{selector}" not found')
    user_id = user.get('user_id')
    if not user_id:
        raise UpstreamError('Sleeper user is missing its user ID')
    matching_rosters = [r for r in rosters if (
        r.get('owner_id') == user_id or user_id in (r.get('co_owners') or [])
    )]
    if not matching_rosters:
        raise ValidationError(f'Team or manager "{selector}" has no roster in league {league_id}')
    if len(matching_rosters) > 1:
        raise ValidationError('Team name selects multiple rosters; use a manager unique to the requested team')
    roster_id = matching_rosters[0]['roster_id']
    team_name = ((user.get('metadata') or {}).get('team_name')
                 or user.get('display_name') or selector)
    return roster_id, team_name


def normalize_roster_ids(picks):
    for pick in picks:
        roster = pick.get('roster_id')
        if isinstance(roster, str) and re.fullmatch(r'[0-9]+', roster):
            pick['roster_id'] = int(roster)


def read_team_picks(draft, picks, roster_id, team_name):
    """Normalize and validate one team's picks from the already checked full draft."""
    team_picks = [p for p in picks if p['roster_id'] == roster_id]
    if not team_picks:
        raise ValidationError(f'No picks found for roster {roster_id} in draft {draft["draft_id"]}')

    team_picks.sort(key=lambda p: p.get('pick_no', 0))

    try:
        validated = validate({
            'teamName': team_name,
            'season': int(draft['season']),
            'picks': [normalize_pick(p) for p in team_picks]
        })
    except ValidationError as exc:
        raise UpstreamError(f'Sleeper draft cannot be graded: {exc}') from exc

    return {'rosterId': roster_id, **validated}


def normalize_pick(pick):
    metadata = pick.get('metadata') or {}
    first = str(metadata.get('first_name') or '').strip()
    last = str(metadata.get('last_name') or '').strip()
    player = f'{first} {last}'.strip()
    if not player:
        player = str(metadata.get('player_name') or metadata.get('name') or '').strip()
    if not player:
        raise UpstreamError('Sleeper pick is missing a player name')
    position = metadata.get('position')
    return {'overallPick': pick['pick_no'], 'round': pick['round'],
            'playerName': player, 'position': 'D/ST' if position == 'DEF' else position}


def check_picks(draft, picks, roster_ids):
    """Check the full draft before selecting a team; traded picks may change team counts."""
    settings = draft.get('settings') or {}
    teams, rounds = settings.get('teams'), settings.get('rounds')
    if type(teams) is not int or type(rounds) is not int or teams < 1 or rounds < 1:
        raise UpstreamError('Sleeper draft is missing valid team and round counts')
    if len(picks) != teams * rounds:
        raise UpstreamError('Sleeper returned an incomplete draft; pick count does not match draft settings')
    numbers = []
    for pick in picks:
        number = pick.get('pick_no')
        if type(number) is not int or number < 1:
            raise UpstreamError('Sleeper pick is missing a valid pick number')
        if type(pick.get('round')) is not int or pick['round'] != (number - 1) // teams + 1:
            raise UpstreamError('Sleeper pick round does not match its pick number')
        if type(pick.get('roster_id')) is not int or pick['roster_id'] not in roster_ids:
            raise UpstreamError('Sleeper pick has an unknown roster ID')
        if pick.get('draft_id') != draft['draft_id']:
            raise UpstreamError('Sleeper pick belongs to a different draft')
        numbers.append(number)
    if set(numbers) != set(range(1, len(picks) + 1)):
        raise UpstreamError('Sleeper draft contains duplicate or missing pick numbers')
