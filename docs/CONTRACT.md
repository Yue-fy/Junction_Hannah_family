# CONTRACT

> The interface between parts of the system. Frontend and backend build against this file in parallel.
> Change it only through a PR labeled `contract` (see "Change the contract" in AGENTS.md).
> If we switch to an OpenAPI file or shared types, link them here and keep this as the summary.

## Base URLs

| Environment | Frontend | Backend |
|---|---|---|
| Local | TBD | TBD |
| Demo | TBD | TBD |

## Endpoints

### `GET /api/example` (placeholder, replace)
Request: none
Response `200`:
```json
{ "items": [{ "id": "string", "name": "string" }] }
```

## Shared data types
TBD

## Env vars (names only; values live in `.env`)

| Name | Used by | Where to get it |
|---|---|---|
| TBD | TBD | TBD |
