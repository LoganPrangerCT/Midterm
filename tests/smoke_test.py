"""Exercise the real local/Azure HTTP host; keep API keys out of output/files."""
import argparse
import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base_url', help='https://<host>/api or http://127.0.0.1:7071/api')
    parser.add_argument('--league-id', default='1391859959213359104')
    parser.add_argument('--team-name', default='loganpranger')
    parser.add_argument('--update-team', default='danjgrady28', help='Second team to grade from the saved league')
    args = parser.parse_args()
    base = args.base_url.rstrip('/')
    if not (base.startswith('https://') or base.startswith('http://127.0.0.1:')
            or base.startswith('http://localhost:')):
        parser.error('Use HTTPS for hosted testing, or loopback HTTP for local testing')
    key = os.environ.get('APP_API_KEY')
    if not key:
        parser.error('Set APP_API_KEY in this process before testing')
    count = 0

    def call(method, path, expected, body=None, auth=key, accept='application/json'):
        nonlocal count
        headers = {'Accept': accept, 'Content-Type': 'application/json'}
        if auth is not None:
            headers['x-api-key'] = auth
        raw = body if isinstance(body, bytes) else json.dumps(body).encode() if body is not None else None
        req = Request(base + path, data=raw, method=method, headers=headers)
        try:
            response = urlopen(req, timeout=120)
        except HTTPError as exc:
            response = exc
        with response:
            content = response.read().decode('utf-8')
            assert response.code == expected, f'{method} {path}: expected {expected}, got {response.code}'
            assert response.headers.get('Cache-Control') == 'no-store'
            result = json.loads(content) if 'application/json' in response.headers.get('Content-Type', '') else content
            if expected >= 400:
                assert isinstance(result.get('error', {}).get('message'), str)
            count += 1
            print(f'PASS {method} {path} -> {expected}')
            return result, response.headers

    missing = '/leagues/00000000-0000-0000-0000-000000000000'
    for method, path in [('GET', '/leagues'), ('POST', '/leagues'), ('PUT', missing),
                         ('DELETE', missing), ('POST', '/reports')]:
        call(method, path, 401, auth=None)
    call('GET', '/leagues', 401, auth=key + '-wrong')
    existing, _ = call('GET', '/leagues', 200)
    if existing:
        parser.error('A league is already saved. Use an empty test instance; no data was changed.')
    call('POST', '/reports', 404, {'teamName': args.team_name})
    call('POST', '/leagues', 400, {})
    call('POST', '/leagues', 400, {'leagueId': 'invalid'})
    call('POST', '/leagues', 400, {'leagueId': args.league_id, 'teamName': args.team_name})
    call('POST', '/leagues', 400, b'{broken')
    call('POST', '/leagues', 400, b'{"leagueId":"a","leagueId":"b"}')
    call('PUT', missing, 404, {})
    call('DELETE', missing, 404)
    body = {'leagueId': args.league_id}
    created, headers = call('POST', '/leagues', 201, body)
    path = '/leagues/' + created['id']
    try:
        assert headers['Location'] == '/api' + path
        assert len(created['teams']) > 1, 'Expected the whole league'
        assert all(len(team['picks']) > 1 for team in created['teams'])
        call('POST', '/leagues', 409, body)
        listed, _ = call('GET', '/leagues', 200)
        assert listed == [created]
        reports = []
        for team_name in [args.team_name, args.update_team]:
            report, _ = call('POST', '/reports', 200, {'teamName': team_name})
            assert report['source']['leagueId'] == args.league_id
            assert report['evaluation']['scoringVersion'] == '2026-softer-misses-v15'
            assert report['evaluation']['pickCount'] == len(report['picks']) > 1
            reports.append(report)
        if args.team_name != args.update_team:
            assert reports[0]['source']['rosterId'] != reports[1]['source']['rosterId']
        text, _ = call('POST', '/reports', 200, {'teamName': args.team_name}, accept='text/plain')
        assert 'DRAFT GRADE' in text and 'FULL DRAFT BOARD' in text
        call('POST', '/reports', 400, {})
        call('POST', '/reports', 400, {'teamName': ''})
        demo_body = {'teamName': args.team_name, 'leagueId': args.league_id}
        demo, _ = call('POST', '/reports', 200, demo_body)
        assert demo['source']['leagueId'] == args.league_id
        assert demo['source']['rosterId'] == reports[0]['source']['rosterId']
        assert demo['evaluation'] == reports[0]['evaluation']
        demo_text, _ = call('POST', '/reports', 200, demo_body, accept='text/plain')
        assert demo_text == text
        listed, _ = call('GET', '/leagues', 200)
        assert listed == [created], 'Report generation must not change the saved league'
        updated, _ = call('PUT', path, 200, body)
        assert updated['id'] == created['id'] and updated['createdAt'] == created['createdAt']
        assert updated['updatedAt'] != created['updatedAt']
        call('PUT', path, 400, {})
        listed, _ = call('GET', '/leagues', 200)
        assert listed == [updated], 'Failed refresh must preserve the saved league'
        print(f"Whole league verified: {len(created['teams'])} teams; reports for two managers.")
    finally:
        call('DELETE', path, 200)
    listed, _ = call('GET', '/leagues', 200)
    assert listed == []
    call('DELETE', path, 404)
    call('POST', '/reports', 404, {'teamName': args.team_name})
    print(f'{count} HTTP checks passed against {base}. Test-created league removed.')


if __name__ == '__main__':
    main()
