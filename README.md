# Fantasy Lab Draft Grader

A Python Azure Functions API for reviewing a Sleeper league's draft against the 2026 rankings. Save a league once, then request any manager's report by name. The API stores one complete league in memory and calculates report cards on demand.

## Run locally

Install Python 3.12 and Azure Functions Core Tools v4. From the project root:

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
Copy-Item local.settings.example.json local.settings.json
```

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

## Deployment

**Deployment status:** This application was deployed to Azure and tested successfully on October 30, 2026, as documented in the hosted test records and screenshots. I have since taken down the deployment because I was worried I'd forget about it and eat through all my credits. If you would like me to redeploy for your own verification just let me know.

The application was published from this folder as the Azure Functions root. Its former base URL was `https://fantasy-midterm-lpranger.azurewebsites.net/api`. Redeployment requires recreating the Azure resources, setting a private `APP_API_KEY`, and publishing the folder with Azure Functions Core Tools.

The deployment used a Linux Basic B1 plan in North Central US with one instance, one Python worker and Always On. This provided warm availability and predictable compute cost of about $0.43/day or $13.14 per 730-hour month, before storage and other charges (USD retail estimate checked October 28, 2026). Scale-to-zero hosting is an alternative if future usage and costs justify a change. B1 is a project choice, not a rubric requirement.

The in-memory league is shared by callers using the application key and clears on restart/deployment. Host storage does not persist league data. Use one instance and one Python worker for this temporary repository. Always On prevents idle unloading; it does not guarantee process lifetime or preserve memory across recycling, and stopping the Function App still leaves the B1 plan billable. The October 30 clean rebuild passed all 33 hosted smoke checks; see the [completed writeup](docs/project.pdf).

## Documentation

- [Project writeup](docs/project.pdf) — overview, API reference, deployment and full hosted test records
- [Application walkthrough](docs/architecture_visualizer.html) · [Azure walkthrough](docs/azure_architecture_visualizer.html)
