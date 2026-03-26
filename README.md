# Anagram Quest — Game Master Server

FastAPI backend for Anagram Quest with real-time streaming, competitive match logic, and production hardening.

## Live API

- Health: [anagram-quest.mooo.com/health](https://anagram-quest.mooo.com/health)

## Project Family

- Master repo (architecture + journey): [divyanshailani/anagram-quest](https://github.com/divyanshailani/anagram-quest)
- Frontend: [divyanshailani/anagram-quest-frontend](https://github.com/divyanshailani/anagram-quest-frontend)
- OpenEnv foundation: [divyanshailani/anagram-quest-openenv](https://github.com/divyanshailani/anagram-quest-openenv)

## Core Responsibilities

- Match lifecycle management (create, guess, level progression, game over)
- Real-time SSE streams for AI thinking + guesses
- Human/AI scoring with completion bonuses
- PvAI banking actions (boost/recover)
- Oracle integration for anagram candidate generation
- Resilience controls: cache, reconnect safety, stale-level handling

## Architecture

```text
[Frontend] -- HTTPS/SSE --> [FastAPI Game Master]
                                 |
                                 +--> [Oracle Service]
```

## Key Endpoints

### Watch Mode

| Endpoint | Method | Description |
|---|---|---|
| `/stream-ai-play` | GET | End-to-end AI gameplay SSE stream |
| `/game/{id}` | GET | Watch-mode game status |

### Player vs AI

| Endpoint | Method | Description |
|---|---|---|
| `/match/create` | POST | Create match and return level 1 |
| `/match/{id}/guess` | POST | Validate human guess |
| `/match/{id}/ai-stream` | GET | AI SSE stream for active level |
| `/match/{id}/next-level` | POST | Advance level / finalize match |
| `/match/{id}/status` | GET | Match status + diagnostics |
| `/match/{id}/bank/boost` | POST | Spend bank for current score boost |
| `/match/{id}/bank/recover` | POST | Spend bank to attempt missed-word recovery |

### Service

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Service metadata |
| `/health` | GET | Health + oracle connectivity + cache size |

## Local Run

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

## Docker

```bash
docker build -t anagram-quest-server .
docker run -p 8000:8000 anagram-quest-server
```

## Production Notes

- Current deployment is aligned to in-memory match state consistency (`workers=1`)
- SSE routes are tuned at Nginx for long-lived streaming
- See [PROD_TUNING.md](PROD_TUNING.md) for operational guidance
