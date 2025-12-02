
import asyncio
import sys
import signal
import time
import redis.asyncio as redis
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

app = FastAPI()


class ConnectionManager:
    def __init__(self, redis_url="redis://localhost:6379/0"):
        self.active_connections = {}
        self.redis_url = redis_url
        self.redis = None
        self.pubsub_task = None

    async def setup(self):
        self.redis = redis.from_url(self.redis_url, decode_responses=True)
        self.pubsub_task = asyncio.create_task(self.listen_pubsub())

    async def get_connection_count(self) -> int:
        return await self.redis.scard("ws_clients")

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        client_id = str(id(websocket))
        self.active_connections[client_id] = websocket
        await self.redis.sadd("ws_clients", client_id)
        count = await self.get_connection_count()
        websocket.client_id = client_id
        print(f"[Connect] Client {client_id} connected. Total: {count}", flush=True)

    async def disconnect(self, websocket: WebSocket):
        client_id = getattr(websocket, "client_id", None)
        if client_id and client_id in self.active_connections:
            del self.active_connections[client_id]
            await self.redis.srem("ws_clients", client_id)
            count = await self.get_connection_count()
            print(f"[Disconnect] Client {client_id} disconnected. Total: {count}", flush=True)

    async def broadcast(self, message: str):
        await self.redis.publish("ws_broadcast", message)

    async def listen_pubsub(self):
        pubsub = self.redis.pubsub()
        await pubsub.subscribe("ws_broadcast")
        async for msg in pubsub.listen():
            if msg["type"] == "message":
                for ws in self.active_connections.values():
                    await ws.send_text(msg["data"])
        await pubsub.unsubscribe("ws_broadcast")\
        
manager = ConnectionManager()


shutdown_initiated = False
shutdown_start_time = None
SHUTDOWN_TIMEOUT = 1800  # seconds


async def log_shutdown_progress():
    remaining = SHUTDOWN_TIMEOUT - (time.time() - shutdown_start_time)
    count = await manager.get_connection_count()
    print(f"[Shutdown] Active connections: {count}, Remaining time: {int(remaining)}s", flush=True)


async def graceful_shutdown():
    global shutdown_initiated, shutdown_start_time
    shutdown_initiated = True
    shutdown_start_time = time.time()
    print("[Shutdown] SIGTERM/SIGINT received. Waiting for clients to disconnect or timeout...", flush=True)
    while await manager.get_connection_count() > 0:
        await log_shutdown_progress()
        if time.time() - shutdown_start_time > SHUTDOWN_TIMEOUT:
            print("[Shutdown] Timeout reached. Forcing shutdown.", flush=True)
            break
        await asyncio.sleep(5)
    print("[Shutdown] No active connections. Shutting down.", flush=True)
    sys.exit(0)

def handle_signal(sig, frame):
    if not shutdown_initiated:
        loop = asyncio.get_event_loop()
        loop.create_task(graceful_shutdown())

signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)



class BroadcastRequest(BaseModel):
    message: str


async def periodic_notifications():
    while True:
        await asyncio.sleep(10)
        await manager.broadcast("Test notification: 10 seconds elapsed")


@app.on_event("startup")
async def startup_event():
    await manager.setup()
    asyncio.create_task(periodic_notifications())

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            print(f"Received message from client: {data}", flush=True)
    except WebSocketDisconnect:
        await manager.disconnect(websocket)

@app.post("/broadcast")
async def broadcast_message(request: BroadcastRequest):
    await manager.broadcast(f"Manual broadcast: {request.message}")
    return {"status": "sent"}