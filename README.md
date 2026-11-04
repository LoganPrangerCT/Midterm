# Fantasy Lab Draft Grader

A Python Azure Functions API for reviewing a Sleeper league's draft against the 2026 rankings. Save a league once, then request any manager's report by name. The API stores one complete league in memory and calculates report cards on demand.

Azure API base URL: https://fantasy-midterm-lpranger-degda0fabcbehhch.northcentralus-01.azurewebsites.net/api

Append the route to this base URL and send the private `APP_API_KEY` in the `x-api-key` header. For PUT and DELETE, use the saved UUID returned by your POST request; the UUIDs in the writeup are example values.

## Run locally

Install Python 3.12 and Azure Functions Core Tools v4. From the project root:

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
Copy-Item local.settings.example.json local.settings.json
```

The `-r` option tells pip to install every Python package listed in `requirements.txt`. Azure Functions Core Tools is a separate prerequisite and is not installed by pip.

Set a private `APP_API_KEY` in `local.settings.json`, then start the host:

```powershell
./scripts/start-local.ps1
```

Keep an existing environment and settings file when rerunning setup. The local base URL is `http://127.0.0.1:7071/api`.

## Quick demo: one request

Send both fields to fetch the league and receive a report card immediately:

```http
POST /api/reports
x-api-key: <APP_API_KEY>
Content-Type: application/json
Accept: text/plain
```

```json
{"leagueId":"1391859959213359104","teamName":"loganpranger"}
```

This demo shortcut fetches fresh Sleeper data on each request and returns **200 OK**. It does not save or replace a league. Omit `Accept: text/plain` for JSON. The separate league CRUD flow below remains available for the rubric and for grading several teams from one saved snapshot.

## Use the saved-league API

Send `x-api-key: <APP_API_KEY>` on every request and `Content-Type: application/json` with JSON bodies.

Save the complete league:

```http
POST /api/leagues
```

```json
{"leagueId":"1391859959213359104"}
```

Request a report without resending the league ID:

```http
POST /api/reports
Accept: text/plain
```

```json
{"teamName":"loganpranger"}
```

Change the name to grade another saved manager. JSON is the default; `Accept: text/plain` returns a readable report card. Team-name-only report requests make no additional Sleeper calls. Picks whose names match multiple ranked players are excluded from grading with an `ambiguous` warning; the API does not guess which player was drafted.

| Method | Route | Purpose |
| --- | --- | --- |
| POST | `/api/leagues` | Save the complete league; 201 |
| GET | `/api/leagues` | List the current league; 200 |
| PUT | `/api/leagues/{id}` | Refresh or replace the league; 200 |
| DELETE | `/api/leagues/{id}` | Remove the league; 200 |
| POST | `/api/reports` | Calculate a saved team's report, or fetch and grade with both fields; 200 |

League create/update bodies contain only `leagueId`. Report bodies contain `teamName`, with optional `leagueId` for the demo shortcut. PUT/DELETE use the saved UUID returned by POST, not the numeric Sleeper ID. A second create returns 409; update or delete the current league first.

## Project structure

```text
function_app.py          Azure app, HTTP routes and request/response helpers
repository.py            One current league, locking and resource identity
fantasy/                 Import, validation, grading and report formatting
  data/                  The rankings CSV the grading engine reads
scripts/                 Local startup and Azure configuration/publication
tests/                   API tests, scoring tests and HTTP smoke test
docs/                    Writeup PDF, walkthroughs and hosted evidence
  architecture_visualizer.html        Application walkthrough
  azure_architecture_visualizer.html  Azure resource walkthrough
host.json                Azure Functions host configuration
local.settings.example.json
requirements.txt
```

## Tests

```powershell
.venv/Scripts/python -m unittest discover -s tests -v
# With the host running and APP_API_KEY set to the local key:
.venv/Scripts/python tests/smoke_test.py http://127.0.0.1:7071/api
```

The smoke test requires an empty instance, creates its own league and deletes it afterward. It refuses to overwrite an existing saved league.

## Documentation

- [Project writeup](docs/project.pdf) — overview, API reference, deployment and full hosted test records
- [Application walkthrough](docs/architecture_visualizer.html) · [Azure walkthrough](docs/azure_architecture_visualizer.html)
