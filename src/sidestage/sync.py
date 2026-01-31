import logging
from typing import List, Dict, Any, Optional
from fastapi import WebSocket

logger = logging.getLogger(__name__)

class SyncManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Sync: Client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"Sync: Client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: Dict[str, Any], exclude: Optional[WebSocket] = None):
        """
        Broadcasts a message to all connected clients, optionally excluding one (the sender).
        """
        msg_type = message.get("type", "unknown")
        # Don't log content-heavy sync messages to keep logs clean
        if msg_type != "entity_content_sync":
            logger.info(f"Sync: Broadcasting {msg_type}")
            
        for connection in self.active_connections:
            if connection == exclude:
                continue
            try:
                await connection.send_json(message)
            except Exception as e:
                # Disconnect will handle cleanup eventually, but log if it's unusual
                pass

    async def handle_message(self, websocket: WebSocket, data: str):
        """
        Handles incoming messages from clients and routes them accordingly.
        """
        try:
            message = json.loads(data)
            msg_type = message.get("type")

            if msg_type == "entity_content_sync":
                # Broadcast the keystroke update to all OTHER clients
                await self.broadcast(message, exclude=websocket)
            
            # Future message types (like cursor position) can be added here
            
        except Exception as e:
            logger.error(f"Sync: Error handling message: {e}")

# Global instance for easy access if needed, though Orchestrator should own it.
import json
