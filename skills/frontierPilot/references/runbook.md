# FrontierPilot runbook

## Serving the HTML knowledge base

### Preferred: `chat_server.py` (interactive assistant, SSE)

- Start (inside container):
  - `python3 /home/node/.openclaw/workspace/skills/frontierPilot/scripts/chat_server.py --data ... --html ... --port 7779`
- Host access requires Docker publish:
  - `127.0.0.1:7779:7779`
- `chat_server.py` must bind `0.0.0.0` inside container to accept published connections.

### Simple static serving (no assistant)

Inside container:
```bash
nohup python3 -m http.server 7779 --bind 0.0.0.0 --directory /home/node/.openclaw/workspace/output > /tmp/fp_http.log 2>&1 &
```

## Common failures

### `ERR_CONNECTION_REFUSED` / `ERR_CONNECTION_RESET`
- Container port not published to host
- Server bound to `localhost` inside container
- Background process killed when `exec` session ends (use `nohup`)

### Semantic Scholar rate limit + exec timeout
- Add `SS_API_KEY` or reduce call volume / rely on cache

