"""
Educational WebSocket Client for Home Assistant

This module demonstrates WebSocket communication patterns and serves as a learning
resource for understanding bidirectional, real-time communication protocols.

WEBSOCKET BASICS:
-----------------
WebSocket is a protocol that provides full-duplex (two-way) communication over a
single TCP connection. Unlike HTTP's request-response pattern, WebSocket allows:
- Server-initiated messages (push)
- Persistent connection (no reconnection overhead)
- Lower latency (no HTTP headers on every message)
- Bidirectional data flow

The protocol starts with an HTTP "upgrade" handshake, then switches to WebSocket
framing for all subsequent communication.
"""

import asyncio
import json
import logging
from typing import Any, Callable, Dict, Optional
from enum import Enum

import websockets
from websockets.client import WebSocketClientProtocol


logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """
    Tracks the WebSocket connection lifecycle.

    DISCONNECTED: No connection established
    CONNECTING: TCP handshake in progress
    AUTHENTICATING: WebSocket connected, waiting for auth success
    CONNECTED: Fully authenticated and ready for commands
    RECONNECTING: Connection lost, attempting to reconnect
    """
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    AUTHENTICATING = "authenticating"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"


class HomeAssistantWebSocket:
    """
    Educational WebSocket client for Home Assistant.

    This client demonstrates:
    1. WebSocket connection management
    2. Authentication flows
    3. Message correlation (matching responses to requests)
    4. Event subscription patterns
    5. Async/await patterns for concurrent operations

    ARCHITECTURE:
    -------------
    - Uses asyncio for non-blocking I/O
    - Separate tasks for sending and receiving
    - Message correlation via unique IDs
    - Event-driven callbacks for state changes
    """

    def __init__(self, url: str, token: str):
        """
        Initialize the WebSocket client.

        Args:
            url: Home Assistant WebSocket URL (e.g., ws://homeassistant.local:8123/api/websocket)
            token: Long-lived access token for authentication
        """
        self.url = url
        self.token = token

        # CONNECTION STATE
        # ----------------
        self.state = ConnectionState.DISCONNECTED
        self._websocket: Optional[WebSocketClientProtocol] = None

        # MESSAGE CORRELATION
        # -------------------
        # WebSocket is asynchronous - we send requests and receive responses
        # independently. We need to match responses to requests using IDs.
        self._message_id = 0  # Counter for generating unique message IDs
        self._pending_requests: Dict[int, asyncio.Future] = {}  # Maps message_id -> Future

        # EVENT HANDLING
        # --------------
        # Subscriptions allow us to receive notifications when Home Assistant
        # state changes (e.g., light turned on, temperature changed)
        self._event_callbacks: Dict[int, Callable] = {}  # Maps subscription_id -> callback

        # ASYNC TASKS
        # -----------
        # We run separate tasks for receiving messages and managing the connection
        self._receive_task: Optional[asyncio.Task] = None

    async def connect(self) -> bool:
        """
        Establish WebSocket connection and authenticate.

        WEBSOCKET HANDSHAKE FLOW:
        -------------------------
        1. TCP connection establishment
        2. HTTP upgrade request (switching protocols)
        3. Server accepts upgrade, connection becomes WebSocket
        4. Home Assistant-specific: auth challenge/response

        Returns:
            True if connection and auth successful
        """
        try:
            self.state = ConnectionState.CONNECTING
            logger.info(f"Connecting to {self.url}")

            # STEP 1: WebSocket Connection
            # ----------------------------
            # The websockets library handles the HTTP upgrade handshake for us.
            # Under the hood:
            # - Client sends: GET /api/websocket HTTP/1.1
            #                 Upgrade: websocket
            #                 Connection: Upgrade
            # - Server responds: HTTP/1.1 101 Switching Protocols
            self._websocket = await websockets.connect(self.url)
            logger.info("WebSocket connection established")

            # STEP 2: Wait for Home Assistant's auth challenge
            # ------------------------------------------------
            # Home Assistant sends an "auth_required" message immediately after connection
            auth_required = await self._websocket.recv()
            auth_msg = json.loads(auth_required)

            if auth_msg.get("type") != "auth_required":
                raise Exception(f"Expected auth_required, got: {auth_msg}")

            logger.info("Received auth challenge")

            # STEP 3: Send authentication token
            # ----------------------------------
            self.state = ConnectionState.AUTHENTICATING
            await self._websocket.send(json.dumps({
                "type": "auth",
                "access_token": self.token
            }))

            # STEP 4: Wait for auth result
            # -----------------------------
            auth_result = await self._websocket.recv()
            auth_response = json.loads(auth_result)

            if auth_response.get("type") != "auth_ok":
                raise Exception(f"Authentication failed: {auth_response}")

            logger.info("Authentication successful")
            self.state = ConnectionState.CONNECTED

            # STEP 5: Start message receiver task
            # ------------------------------------
            # We need a long-running task to continuously receive messages
            # from the server (responses, events, etc.)
            self._receive_task = asyncio.create_task(self._receive_loop())

            return True

        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self.state = ConnectionState.DISCONNECTED
            return False

    async def _receive_loop(self):
        """
        Continuously receive and process messages from the WebSocket.

        MESSAGE PROCESSING:
        -------------------
        This is the heart of bidirectional communication. The server can send us:
        1. Responses to our requests (matched by message ID)
        2. Event notifications (from subscriptions)
        3. Errors or system messages

        We route each message to the appropriate handler based on its type.
        """
        try:
            async for message in self._websocket:
                # WEBSOCKET FRAME TYPES:
                # ----------------------
                # WebSocket supports text and binary frames. Home Assistant uses
                # JSON-encoded text frames for all messages.
                data = json.loads(message)

                logger.debug(f"Received: {data}")

                # MESSAGE ROUTING:
                # ----------------
                # Determine what kind of message this is and handle it appropriately

                msg_type = data.get("type")
                msg_id = data.get("id")

                if msg_type == "result":
                    # RESPONSE TO A REQUEST
                    # ---------------------
                    # This is a response to a command we sent earlier.
                    # Find the Future that's waiting for this response.
                    if msg_id in self._pending_requests:
                        future = self._pending_requests.pop(msg_id)
                        if data.get("success"):
                            future.set_result(data.get("result"))
                        else:
                            future.set_exception(Exception(data.get("error")))

                elif msg_type == "event":
                    # EVENT NOTIFICATION
                    # ------------------
                    # This is a pushed notification from a subscription.
                    # Call the registered callback for this subscription.
                    if msg_id in self._event_callbacks:
                        callback = self._event_callbacks[msg_id]
                        event_data = data.get("event")
                        # Run callback in background to not block message processing
                        asyncio.create_task(self._safe_callback(callback, event_data))

                elif msg_type == "pong":
                    # KEEPALIVE RESPONSE
                    # ------------------
                    # Response to our ping (heartbeat) message
                    pass

                else:
                    logger.warning(f"Unhandled message type: {msg_type}")

        except asyncio.CancelledError:
            # Task was cancelled (normal during shutdown)
            logger.info("Receive loop cancelled")
        except Exception as e:
            logger.error(f"Receive loop error: {e}")
            self.state = ConnectionState.DISCONNECTED

    async def _safe_callback(self, callback: Callable, data: Any):
        """
        Safely execute a callback, catching any exceptions.

        DEFENSIVE PROGRAMMING:
        ----------------------
        User-provided callbacks might raise exceptions. We don't want
        those to crash our message processing loop.
        """
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(data)
            else:
                callback(data)
        except Exception as e:
            logger.error(f"Callback error: {e}")

    def _next_id(self) -> int:
        """
        Generate a unique message ID.

        MESSAGE CORRELATION:
        --------------------
        Since we can have multiple requests in-flight simultaneously,
        we need a way to match responses to requests. Each message
        gets a unique ID that the server echoes back in the response.
        """
        self._message_id += 1
        return self._message_id

    async def send_command(self, command_type: str, **kwargs) -> Any:
        """
        Send a command and wait for the response.

        REQUEST-RESPONSE PATTERN:
        -------------------------
        1. Generate unique message ID
        2. Create a Future to wait for the response
        3. Send the message
        4. Await the Future (blocks until response arrives)
        5. Return the result

        This pattern allows us to have multiple concurrent requests,
        each waiting for its own response independently.

        Args:
            command_type: Home Assistant command (e.g., "get_states", "call_service")
            **kwargs: Additional command parameters

        Returns:
            The result from Home Assistant
        """
        if self.state != ConnectionState.CONNECTED:
            raise Exception("Not connected")

        # STEP 1: Prepare the message
        msg_id = self._next_id()
        message = {
            "id": msg_id,
            "type": command_type,
            **kwargs
        }

        # STEP 2: Create a Future for the response
        # -----------------------------------------
        # A Future is a placeholder for a result that will arrive later.
        # The receive loop will complete this Future when the response arrives.
        future = asyncio.Future()
        self._pending_requests[msg_id] = future

        # STEP 3: Send the message
        # ------------------------
        logger.debug(f"Sending: {message}")
        await self._websocket.send(json.dumps(message))

        # STEP 4: Wait for response
        # -------------------------
        # This will block until the receive loop gets our response
        # and calls future.set_result()
        try:
            result = await asyncio.wait_for(future, timeout=30.0)
            return result
        except asyncio.TimeoutError:
            # Clean up if response never arrives
            self._pending_requests.pop(msg_id, None)
            raise Exception(f"Command {command_type} timed out")

    async def subscribe_events(
        self,
        event_type: Optional[str] = None,
        callback: Optional[Callable] = None
    ) -> int:
        """
        Subscribe to Home Assistant events.

        PUBLISH-SUBSCRIBE PATTERN:
        --------------------------
        Unlike request-response, subscriptions are long-lived. After
        subscribing, the server will push notifications to us whenever
        matching events occur.

        Flow:
        1. Send subscribe_events command
        2. Server confirms subscription with an ID
        3. Server sends event messages whenever events occur
        4. Our receive loop routes events to the callback

        Args:
            event_type: Filter events by type (None = all events)
            callback: Function to call when events arrive

        Returns:
            Subscription ID (used to unsubscribe later)
        """
        command = {"event_type": event_type} if event_type else {}
        result = await self.send_command("subscribe_events", **command)

        # The response contains the subscription ID
        # We'll use this ID to route incoming events to the callback
        subscription_id = self._next_id()

        if callback:
            self._event_callbacks[subscription_id] = callback

        logger.info(f"Subscribed to events (type={event_type}), subscription_id={subscription_id}")
        return subscription_id

    async def ping(self):
        """
        Send a keepalive ping.

        HEARTBEAT/KEEPALIVE:
        --------------------
        Long-lived connections may be closed by intermediaries (proxies,
        firewalls) if idle. Periodic pings keep the connection alive and
        verify the server is still responsive.
        """
        msg_id = self._next_id()
        await self._websocket.send(json.dumps({
            "id": msg_id,
            "type": "ping"
        }))

    async def close(self):
        """
        Gracefully close the WebSocket connection.

        CLEANUP:
        --------
        1. Cancel background tasks
        2. Close WebSocket (sends CLOSE frame)
        3. Clean up pending requests
        """
        logger.info("Closing connection")

        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        if self._websocket:
            await self._websocket.close()

        # Cancel any pending requests
        for future in self._pending_requests.values():
            if not future.done():
                future.cancel()

        self._pending_requests.clear()
        self._event_callbacks.clear()
        self.state = ConnectionState.DISCONNECTED
        logger.info("Connection closed")

    async def __aenter__(self):
        """Enable async context manager usage."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Ensure cleanup on context manager exit."""
        await self.close()
