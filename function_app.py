"""HTTP API for the saved league and its draft report cards."""
import hmac
import json
import logging
import os
from uuid import UUID

import azure.functions as func
from werkzeug.datastructures import MIMEAccept
from werkzeug.http import parse_accept_header

from repository import repository
from fantasy.drafts import build_report
from fantasy.sleeper_import import import_sleeper_league
from fantasy.report import format_reports
from fantasy.sleeper_client import UpstreamError, UpstreamNotFoundError
from fantasy.validation import ValidationError, fields, name

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)
MAX_BODY_BYTES = 65536


# Routes

@app.route(route='leagues', methods=['GET', 'POST'])
def leagues(req: func.HttpRequest) -> func.HttpResponse:
    action = list_leagues if req.method.upper() == 'GET' else create_league
    return run_request(req, action)


@app.route(route='leagues/{league_id}', methods=['PUT', 'DELETE'])
def league(req: func.HttpRequest) -> func.HttpResponse:
    action = replace_league if req.method.upper() == 'PUT' else delete_league
    return run_request(req, action)


@app.route(route='reports', methods=['POST'])
def reports(req: func.HttpRequest) -> func.HttpResponse:
    return run_request(req, make_report)


# Authentication and request errors

def run_request(req, action):
    """Authenticate a request and translate failures into HTTP responses."""
    try:
        failure = check_api_key(req)
        if failure is not None:
            return failure
        return action(req)
    except ValidationError as exc:
        return error_response('validation_error', str(exc), 400)
    except UpstreamNotFoundError as exc:
        return error_response('not_found', str(exc), 404)
    except UpstreamError as exc:
        return error_response('upstream_error', str(exc), exc.status_code)
    except Exception:
        logging.exception('API request failed unexpectedly')
        return error_response('internal_error', 'An unexpected error occurred', 500)


def check_api_key(req):
    key = os.environ.get('APP_API_KEY', '')
    if not key.strip() or key.strip() == 'REPLACE_WITH_A_RANDOM_LOCAL_KEY':
        return error_response('configuration_error', 'API authentication is not configured', 503)
    supplied = req.headers.get('x-api-key', '')
    if not hmac.compare_digest(supplied.encode('utf-8'), key.encode('utf-8')):
        return error_response('unauthorized', 'A valid x-api-key header is required', 401)
    return None


# League operations

def list_leagues(req):
    return json_response(repository.all())


def create_league(req):
    if repository.current() is not None:
        return league_conflict()
    saved = repository.create(import_requested_league(req))
    if saved is None:  # Another request may have saved a league during the import.
        return league_conflict()
    return json_response(saved, 201, {'Location': f'/api/leagues/{saved["id"]}'})


def replace_league(req):
    league_id = read_league_id(req)
    if not repository.exists(league_id):
        return error_response('not_found', 'League not found', 404)
    saved = repository.replace(league_id, import_requested_league(req))
    if saved is None:  # Another request may have deleted it during the import.
        return error_response('not_found', 'League not found', 404)
    return json_response(saved)


def delete_league(req):
    league_id = read_league_id(req)
    if not repository.delete(league_id):
        return error_response('not_found', 'League not found', 404)
    return json_response({'id': league_id, 'deleted': True})


def import_requested_league(req):
    selection = read_json(req)
    fields(selection, {'leagueId'}, 'body')
    return import_sleeper_league(selection['leagueId'])


def league_conflict():
    return error_response('conflict', 'A league is already saved; update or delete it first', 409)


# Report requests

def make_report(req):
    selection = read_json(req)
    if isinstance(selection, dict) and 'leagueId' in selection:
        # Demo shortcut: send both fields to fetch and grade in one call without changing saved league state.
        fields(selection, {'leagueId', 'teamName'}, 'body')
        team_name = name(selection['teamName'], 'teamName', 100)
        league = import_sleeper_league(selection['leagueId'])
        selection = {'teamName': team_name}
    else:
        league = repository.current()
        if league is None:
            return error_response('not_found', 'No league saved; POST a leagueId to /api/leagues first', 404)
    report = build_report(league, selection)
    return report_response(req, report)


# Reading and checking request data

def read_json(req):
    raw = req.get_body()
    if len(raw) > MAX_BODY_BYTES:
        raise ValidationError('body must be at most 65536 bytes')
    try:
        return json.loads(raw, parse_constant=reject_json_constant, object_pairs_hook=unique_json_object)
    except (ValueError, UnicodeError, RecursionError):
        raise ValidationError('body must be valid JSON with unique keys and finite numbers') from None


def read_league_id(req):
    try:
        return str(UUID(req.route_params.get('league_id')))
    except (ValueError, AttributeError, TypeError):
        raise ValidationError('id must be a valid UUID') from None


def reject_json_constant(value):
    raise ValueError('Non-finite JSON number')


def unique_json_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError('Duplicate JSON key')
        obj[key] = value
    return obj


# HTTP responses

def json_response(body, status=200, headers=None):
    return func.HttpResponse(json.dumps(body, allow_nan=False), status_code=status,
                             mimetype='application/json',
                             headers={'Cache-Control': 'no-store', **(headers or {})})


def error_response(code, message, status):
    return json_response({'error': {'code': code, 'message': message}}, status)


def report_response(req, body, status=200, headers=None):
    headers = {'Vary': 'Accept', **(headers or {})}
    accept = parse_accept_header(req.headers.get('Accept', ''), MIMEAccept)
    if accept.best_match(['application/json', 'text/plain']) == 'text/plain':
        return func.HttpResponse(format_reports(body), status_code=status, mimetype='text/plain',
                                 headers={'Cache-Control': 'no-store', **headers})
    return json_response(body, status, headers)
