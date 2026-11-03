"""Sleeper API HTTP client with bounded responses and error mapping."""
import json
import socket
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SLEEPER_BASE_URL = 'https://api.sleeper.app/v1/'
MAX_RESPONSE_BYTES = 2 * 1024 * 1024  # 2 MiB
DEFAULT_TIMEOUT_SECONDS = 10.0


class UpstreamError(Exception):
    def __init__(self, message, status_code=502):
        super().__init__(message)
        self.status_code = status_code


class UpstreamNotFoundError(UpstreamError):
    def __init__(self, message='Resource not found on Sleeper'):
        super().__init__(message, status_code=404)


def fetch(path, timeout=DEFAULT_TIMEOUT_SECONDS):
    url = SLEEPER_BASE_URL + path.lstrip('/')
    req = Request(url, headers={'User-Agent': 'FantasyLabDraftGrader/1.0'})
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise UpstreamError('Sleeper response exceeded size limit', status_code=502)
            if raw.strip() == b'null':
                return None
            try:
                return json.loads(raw)
            except (ValueError, UnicodeError, RecursionError) as exc:
                raise UpstreamError('Invalid JSON from Sleeper API', status_code=502) from exc
    except HTTPError as exc:
        if exc.code == 404:
            return None
        if exc.code == 429:
            raise UpstreamError('Sleeper rate limit exceeded', status_code=503) from exc
        if exc.code >= 500:
            raise UpstreamError(f'Sleeper server error ({exc.code})', status_code=502) from exc
        raise UpstreamError(f'Sleeper returned HTTP {exc.code}', status_code=502) from exc
    except (socket.timeout, TimeoutError) as exc:
        raise UpstreamError('Sleeper request timed out', status_code=504) from exc
    except URLError as exc:
        if isinstance(exc.reason, (socket.timeout, TimeoutError)):
            raise UpstreamError('Sleeper request timed out', status_code=504) from exc
        raise UpstreamError('Failed to connect to Sleeper', status_code=502) from exc
    except (OSError, HTTPException) as exc:
        raise UpstreamError('Sleeper connection closed or returned an invalid response') from exc


def fetch_object(path):
    data = fetch(path)
    if data is not None and not isinstance(data, dict):
        raise UpstreamError('Expected an object from Sleeper')
    return data


def fetch_list(path):
    data = fetch(path)
    if data is None:
        return []
    if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
        raise UpstreamError('Expected a list of objects from Sleeper')
    return data


def get_league(league_id):
    return fetch_object(f'league/{league_id}')


def get_league_drafts(league_id):
    return fetch_list(f'league/{league_id}/drafts')


def get_league_rosters(league_id):
    rosters = fetch_list(f'league/{league_id}/rosters')
    ids = []
    for roster in rosters:
        roster_id = roster.get('roster_id')
        if type(roster_id) is not int or roster_id < 1:
            raise UpstreamError('Sleeper roster is missing a valid roster ID')
        ids.append(roster_id)
        owner = roster.get('owner_id')
        co_owners = roster.get('co_owners') or []
        if (owner is not None and not isinstance(owner, str)
                or not isinstance(co_owners, list)
                or any(not isinstance(user_id, str) for user_id in co_owners)):
            raise UpstreamError('Sleeper roster has invalid owner data')
    if len(ids) != len(set(ids)):
        raise UpstreamError('Sleeper returned duplicate roster IDs')
    return rosters


def get_league_users(league_id):
    users = fetch_list(f'league/{league_id}/users')
    for user in users:
        metadata = user.get('metadata') or {}
        if not isinstance(metadata, dict):
            raise UpstreamError('Sleeper user has invalid metadata')
        names = [user.get('user_id'), user.get('display_name'),
                 user.get('username'), metadata.get('team_name')]
        if any(value is not None and not isinstance(value, str) for value in names):
            raise UpstreamError('Sleeper user has invalid names or ID')
        if not user.get('user_id'):
            raise UpstreamError('Sleeper user is missing its user ID')
    return users


def get_draft_picks(draft_id):
    return fetch_list(f'draft/{draft_id}/picks')
