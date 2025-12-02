
# FastAPI WebSocket Server (dev notes)

Install:
- `pip install fastapi uvicorn redis`
- Or just use `requirements.txt`


Redis:
- Make sure Redis is running locally (`redis-server` or Memurai on Windows)

Run:
- `uvicorn main:app --reload` (1 worker)
- `uvicorn main:app --workers 4` (multi-worker, don't work graceful shutdown because uvicorn killed children before they can recieve SIGTERM/SIGINT )

Endpoints:
- `/ws` (WebSocket): connect with any client, get a message every 10s. To broadcast, send a message starting with `/BS` (e.g., `/BS your message`). Other messages are not broadcast.
- `/broadcast` (POST): send a message to all clients (try with curl or Postman)
    POST http://localhost:8000/broadcast
    Body (JSON):
    {
        "message": "Your message here"
    }

Testing:
- Use browser JS, Postman, or `websocat` for WebSocket
- Open a couple clients, send a message from one, all should see it
- POST to `/broadcast` to test manual broadcast

Redis Implementation:
- Connection state and broadcasts are shared across all workers using Redis
- Each worker subscribes to a Redis pub/sub channel for broadcasts
- Connections are tracked with unique IDs in Redis

Shutdown:
- Ctrl+C or SIGTERM: server waits for clients to disconnect, or kills after 30 min
- You’ll see logs about connection count and time left

Files:
- `main.py`: everything’s here (app, endpoints, shutdown, connection manager, Redis logic)
