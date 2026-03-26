# Anagram Quest Backend Production Tuning

This guide is for the current architecture:
- FastAPI + Uvicorn
- In-memory `active_matches` state
- SSE streams for AI events

## 1) Keep Uvicorn at 1 worker (current architecture)

Use:
```bash
uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1 --timeout-keep-alive 75
```

Why:
- Match state is stored in memory per process.
- Multiple workers can route requests to different processes and cause `match not found` / inconsistent state.

If you want multiple workers or multiple droplets:
- Move match state to Redis/Postgres first.

## 2) Nginx SSE settings (critical)

For SSE endpoints:
- `proxy_buffering off`
- `proxy_set_header X-Accel-Buffering no`
- `proxy_read_timeout 3600s`
- `proxy_send_timeout 3600s`
- `proxy_http_version 1.1`

These are now included in `deploy_do.sh` for:
- `/stream-ai-play`
- `/match/{id}/ai-stream`

## 3) Add swap on 2GB droplet

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h
```

## 4) Backend improvements already implemented

- Oracle HTTP client connection pooling
- Oracle response cache (TTL + bounded size)
- Stale-level guard for late guesses
- Extended active-match TTL while game is playing

## 5) Quick runtime checks

```bash
curl -sS https://anagram-quest.mooo.com/health
journalctl -u anagram-quest -f
```

Health should show:
- `"game_master":"ok"`
- `"oracle":"ok"` (or transient unreachable during oracle outages)
- `"oracle_cache_size"` present on updated backend

## 6) Load test target (10-20 concurrent users)

With current architecture and tuning:
- 10 concurrent users should be stable.
- 20 concurrent users can be okay but depends on oracle latency and network quality.

If you see sustained instability at 20+:
- Move match state + oracle cache to Redis
- Keep API stateless across workers/instances
- Then scale workers/instances horizontally
