# Anagram Quest — Game Master Server

FastAPI backend for the Anagram Quest AI game with:
- **GameEngine**: 5-level anagram game state machine
- **BankingEngine**: MDP-based Expected Value optimizer
- **Oracle Client**: Async HTTP calls to HF Spaces LLM (Qwen3-0.6B GRPO)
- **SSE Streaming**: Real-time "Watch AI Play" events

## Architecture
```
[HF Oracle (Qwen3-0.6B)] ← httpx → [Game Master :8000] ← SSE → [Frontend]
```

## Quick Start
```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

## Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Service info |
| `/health` | GET | Health check (pings Oracle) |
| `/stream-ai-play` | GET | SSE stream — watch the AI play |
| `/game/{id}` | GET | Game status |

## Docker
```bash
docker build -t anagram-quest-server .
docker run -p 8000:8000 anagram-quest-server
```

## SSE Event Types
`game_start` → `level_start` → `thinking` → `ai_guess` → `bank_decision` → `recovery_start` → `recovery_result` → `level_end` → `game_over`
