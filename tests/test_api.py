"""Offline checks for league CRUD and reports generated without another import."""
from contextlib import ExitStack
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import azure.functions as func
import function_app as api
from repository import LeagueRepository
from fantasy import sleeper_import
from fantasy.sleeper_client import UpstreamError, UpstreamNotFoundError
from fantasy.validation import ValidationError

FUNCTIONS = {f.get_function_name(): f for f in api.app.get_functions()}
LEAGUE_ID = '1391859959213359104'
DRAFT_ID = '1391859959213359105'
MISSING_ID = '00000000-0000-0000-0000-000000000000'
SELECTION = {'leagueId': LEAGUE_ID}
DRAFT = {'draft_id': DRAFT_ID, 'season': '2026', 'status': 'complete',
         'settings': {'teams': 2, 'rounds': 2}}
ROSTERS = [{'roster_id': 1, 'owner_id': 'user1'}, {'roster_id': 2, 'owner_id': 'user2'}]
USERS = [{'user_id': 'user1', 'display_name': 'Alice', 'metadata': {'team_name': 'Aces'}},
         {'user_id': 'user2', 'display_name': 'Bob', 'username': 'bobby'}]
PICKS = [{'draft_id': DRAFT_ID, 'roster_id': str(roster), 'pick_no': number,
          'round': (number - 1) // 2 + 1,
          'metadata': {'player_name': player, 'position': 'WR'}}
         for number, roster, player in [(1, 1, 'Ja’Marr Chase'), (2, 2, 'Justin Jefferson'),
                                        (3, 2, 'CeeDee Lamb'), (4, 1, 'Amon-Ra St. Brown')]]


class ApiChecks(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(os.environ, APP_API_KEY='offline-test-key'))
        self.stack.enter_context(patch.object(api, 'repository', LeagueRepository()))
        fixtures = {'get_league': {'name': 'Example League', 'draft_id': DRAFT_ID},
                    'get_league_drafts': [DRAFT], 'get_league_rosters': ROSTERS,
                    'get_league_users': USERS, 'get_draft_picks': PICKS}
        self.remote = {name: self.stack.enter_context(patch.object(
            sleeper_import, name, side_effect=lambda *args, value=value: deepcopy(value)))
            for name, value in fixtures.items()}

    def call(self, method, path, expected, body=None, key='offline-test-key',
             accept='application/json'):
        resource_id = path.split('/')[-1] if path.startswith('/leagues/') else None
        raw = body if isinstance(body, bytes) else json.dumps(body).encode() if body is not None else b''
        req = func.HttpRequest(method=method, url='http://localhost/api' + path,
            headers={'x-api-key': key, 'Accept': accept}, params={}, body=raw,
            route_params={} if resource_id is None else {'league_id': resource_id})
        name = 'league' if resource_id is not None else path.lstrip('/')
        response = FUNCTIONS[name].get_user_function()(req)
        self.assertEqual(response.status_code, expected)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        return response

    def create(self):
        response = self.call('POST', '/leagues', 201, SELECTION)
        saved = json.loads(response.get_body())
        self.assertEqual(response.headers['Location'], '/api/leagues/' + saved['id'])
        return saved

    def test_sdk_registration(self):
        self.assertEqual(set(FUNCTIONS), {'leagues', 'league', 'reports'})
        for name, route, methods in [('leagues', 'leagues', {'GET', 'POST'}),
                ('league', 'leagues/{league_id}', {'PUT', 'DELETE'}),
                ('reports', 'reports', {'POST'})]:
            trigger = FUNCTIONS[name].get_bindings_dict()['bindings'][0]
            self.assertEqual(trigger['route'], route)
            self.assertEqual({m.value for m in trigger['methods']}, methods)
            self.assertEqual(trigger['authLevel'], func.AuthLevel.ANONYMOUS)

    def test_authentication_before_input_or_import(self):
        for method, path in [('GET', '/leagues'), ('POST', '/leagues'),
                ('PUT', '/leagues/invalid'), ('DELETE', '/leagues/invalid'), ('POST', '/reports')]:
            self.call(method, path, 401, b'{broken', key='wrong')
        for key in ['', '   ', 'REPLACE_WITH_A_RANDOM_LOCAL_KEY']:
            with patch.dict(os.environ, APP_API_KEY=key):
                self.call('GET', '/leagues', 503)
        for remote in self.remote.values():
            remote.assert_not_called()

    def test_league_crud(self):
        self.assertEqual(json.loads(self.call('GET', '/leagues', 200).get_body()), [])
        created = self.create()
        self.assertEqual(len(created['teams']), 2)
        self.assertEqual(sum(len(t['picks']) for t in created['teams']), 4)
        self.assertEqual(json.loads(self.call('GET', '/leagues', 200).get_body()), [created])
        path = '/leagues/' + created['id']
        updated = json.loads(self.call('PUT', path, 200, SELECTION).get_body())
        self.assertEqual(updated['id'], created['id'])
        self.assertEqual(updated['createdAt'], created['createdAt'])
        deleted = json.loads(self.call('DELETE', path, 200).get_body())
        self.assertEqual(deleted, {'id': created['id'], 'deleted': True})
        self.call('DELETE', path, 404)
        self.call('POST', '/reports', 404, {'teamName': 'Alice'})
        self.assertEqual(api.repository.all(), [])

    def test_unchanged_example_key_cannot_authenticate(self):
        settings = Path(__file__).resolve().parents[1] / 'local.settings.example.json'
        example_key = json.loads(settings.read_text())['Values']['APP_API_KEY']
        with patch.dict(os.environ, APP_API_KEY=example_key):
            self.call('GET', '/leagues', 503, key=example_key)

    def test_reports_use_saved_league_without_fetching_again(self):
        saved = self.create()
        for name, roster in [('Alice', 1), ('aces', 1), ('Bob', 2), ('BOBBY', 2), ('user2', 2)]:
            response = self.call('POST', '/reports', 200, {'teamName': name})
            report = json.loads(response.get_body())
            self.assertEqual(report['source']['rosterId'], roster)
            self.assertEqual(report['evaluation']['pickCount'], 2)
            self.assertEqual(len(report['picks']), 2)
        text = self.call('POST', '/reports', 200, {'teamName': 'Bob'}, accept='text/plain')
        self.assertEqual(text.mimetype, 'text/plain')
        self.assertEqual(text.headers['Vary'], 'Accept')
        self.assertIn(b'DRAFT GRADE', text.get_body())
        self.assertIn(b'FULL DRAFT BOARD', text.get_body())
        self.assertEqual(api.repository.all(), [saved])
        for remote in self.remote.values():
            remote.assert_called_once()

    def test_only_one_current_league(self):
        saved = self.create()
        self.call('POST', '/leagues', 409, SELECTION)
        self.assertEqual(api.repository.all(), [saved])
        self.remote['get_league'].assert_called_once()

    def test_demo_report_fetches_without_saving(self):
        selection = {'leagueId': LEAGUE_ID, 'teamName': 'Alice'}
        response = self.call('POST', '/reports', 200, selection)
        report = json.loads(response.get_body())
        self.assertEqual(report['source']['leagueId'], LEAGUE_ID)
        self.assertEqual(report['source']['rosterId'], 1)
        self.assertEqual(report['evaluation']['pickCount'], 2)
        self.assertEqual(response.headers['Vary'], 'Accept')
        text = self.call('POST', '/reports', 200, selection, accept='text/plain')
        self.assertEqual(text.mimetype, 'text/plain')
        self.assertIn(b'DRAFT GRADE', text.get_body())
        self.assertIn(b'FULL DRAFT BOARD', text.get_body())
        self.assertEqual(api.repository.all(), [])
        for remote in self.remote.values():
            self.assertEqual(remote.call_count, 2)  # Each demo request fetches fresh data.

    def test_demo_can_grade_another_league_without_replacing_saved_state(self):
        saved = self.create()
        other_id = '1391859959213359106'
        response = self.call('POST', '/reports', 200, {'leagueId': other_id, 'teamName': 'Bob'})
        report = json.loads(response.get_body())
        self.assertEqual(report['source']['leagueId'], other_id)
        self.assertEqual(report['source']['rosterId'], 2)
        self.remote['get_league'].assert_called_with(other_id)
        self.assertEqual(api.repository.all(), [saved])

    def test_demo_authentication_and_validation_before_fetch(self):
        self.call('POST', '/reports', 401,
                  {'leagueId': LEAGUE_ID, 'teamName': 'Alice'}, key='wrong')
        for body in [b'{broken', b'{"leagueId":1,"leagueId":2}',
                     {'leagueId': LEAGUE_ID}, {'leagueId': LEAGUE_ID, 'teamName': ''},
                     {'leagueId': LEAGUE_ID, 'teamName': ['Alice']},
                     {'leagueId': 'invalid', 'teamName': 'Alice'},
                     {'leagueId': LEAGUE_ID, 'teamName': 'Alice', 'extra': True}]:
            self.call('POST', '/reports', 400, body)
        for remote in self.remote.values():
            remote.assert_not_called()
        self.assertEqual(api.repository.all(), [])

    def test_failed_demo_preserves_saved_league(self):
        saved = self.create()
        selection = {'leagueId': LEAGUE_ID, 'teamName': 'Nobody'}
        self.call('POST', '/reports', 404, selection)
        with patch.object(api, 'import_sleeper_league', side_effect=UpstreamError('Timed out', 504)):
            self.call('POST', '/reports', 504, {**selection, 'teamName': 'Alice'})
        self.assertEqual(api.repository.all(), [saved])

    def test_ids_missing_targets_and_json_validation(self):
        for method in ['PUT', 'DELETE']:
            self.call(method, '/leagues/invalid', 400)
            self.call(method, '/leagues/' + MISSING_ID, 404, b'{broken')
        for body in [b'{broken', b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}',
                     b'\xff', b' ' * 65537, {}, {'leagueId': LEAGUE_ID, 'teamName': 'Alice'},
                     {'leagueId': 'invalid'}]:
            self.call('POST', '/leagues', 400, body)
        self.remote['get_league'].assert_not_called()

    def test_invalid_or_unknown_team(self):
        self.call('POST', '/reports', 404, {'teamName': 'Alice'})
        self.create()
        for body in [{}, {'teamName': ''}, {'teamName': 'Alice', 'extra': True}]:
            self.call('POST', '/reports', 400, body)
        self.call('POST', '/reports', 404, {'teamName': 'Nobody'})

    def test_failed_refresh_preserves_saved_league(self):
        saved = self.create()
        errors = [(ValidationError('Invalid selection'), 400, 'validation_error'),
                  (UpstreamNotFoundError(), 404, 'not_found'),
                  (UpstreamError('Timed out', 504), 504, 'upstream_error'),
                  (RuntimeError('private detail'), 500, 'internal_error')]
        for exc, status, code in errors:
            with patch.object(api, 'import_sleeper_league', side_effect=exc), \
                    patch.object(api.logging, 'exception'):
                response = self.call('PUT', '/leagues/' + saved['id'], status, SELECTION)
                self.assertEqual(json.loads(response.get_body())['error']['code'], code)
                self.assertNotIn(b'private detail', response.get_body())
                self.assertEqual(api.repository.all(), [saved])

    def test_incomplete_or_invalid_other_team_prevents_save(self):
        for picks in [PICKS[:-1], [*PICKS[:-1], {**PICKS[-1], 'metadata': {}}]]:
            with patch.object(sleeper_import, 'get_draft_picks', return_value=deepcopy(picks)):
                self.call('POST', '/leagues', 502, SELECTION)
                self.assertEqual(api.repository.all(), [])

    def test_concurrent_create_and_delete_during_refresh(self):
        snapshot = sleeper_import.import_sleeper_league(LEAGUE_ID)

        def other_create(league_id):
            api.repository.create(snapshot)
            return snapshot

        with patch.object(api, 'import_sleeper_league', side_effect=other_create):
            self.call('POST', '/leagues', 409, SELECTION)
        saved = api.repository.current()

        def other_delete(league_id):
            api.repository.delete(saved['id'])
            return snapshot

        with patch.object(api, 'import_sleeper_league', side_effect=other_delete):
            self.call('PUT', '/leagues/' + saved['id'], 404, SELECTION)
        self.assertEqual(api.repository.all(), [])


if __name__ == '__main__':
    unittest.main()
