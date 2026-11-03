"""Grade a team using the saved league's validated draft picks."""
from copy import deepcopy

from .grading import evaluate, RANKINGS_VERSION
from .sleeper_import import select_team
from .validation import fields, name, ValidationError


def build_report(league, selection):
    """Select and grade a saved team without contacting Sleeper or saving a report."""
    fields(selection, {'teamName'}, 'body')
    selector = name(selection['teamName'], 'teamName', 100)
    roster_id, _ = select_team(league['rosters'], league['users'], selector, league['leagueId'])
    team = next((t for t in league['teams'] if t['rosterId'] == roster_id), None)
    if team is None:
        raise ValidationError(f'No picks found for roster {roster_id} in the saved draft')
    report = deepcopy(team)
    report['source'] = {
        'provider': 'sleeper', 'leagueId': league['leagueId'],
        'draftId': league['draftId'], 'rosterId': roster_id, 'teamName': selector,
    }
    report['evaluation'] = evaluate(report['picks'])
    report['draftGrade'] = report['evaluation']['letterGrade']
    report['rankingsVersion'] = RANKINGS_VERSION
    return report
