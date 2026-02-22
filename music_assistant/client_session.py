from __future__ import annotations

import asyncio
import logging
import threading
from typing import Awaitable, Callable, TypeVar

from music_assistant_client import MusicAssistantClient


T = TypeVar("T")


class ClientSession:
    """Run Music Assistant client requests on a shared background loop."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._thread_lock = threading.Lock()
        self._connection_lock: asyncio.Lock | None = None
        self._request_lock: asyncio.Lock | None = None
        self._client: MusicAssistantClient | None = None
        self._client_cm: MusicAssistantClient | None = None
        self._server_url = ""
        self._auth_token: str | None = None
        self._logger = logging.getLogger(__name__)

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._connection_lock = asyncio.Lock()
        self._request_lock = asyncio.Lock()
        self._loop = loop
        self._ready.set()
        loop.run_forever()
        pending = asyncio.all_tasks(loop)
        if pending:
            for task in pending:
                task.cancel()
            loop.run_until_complete(
                asyncio.gather(*pending, return_exceptions=True)
            )
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()

    def _ensure_loop(self) -> None:
        if self._loop and self._loop.is_running():
            return
        with self._thread_lock:
            if self._loop and self._loop.is_running():
                return
            self._ready.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                daemon=True,
            )
            self._thread.start()
        self._ready.wait()

    def run(
        self,
        server_url: str,
        auth_token: str,
        coro_func: Callable[..., Awaitable[T]],
        *args: object,
        **kwargs: object,
    ) -> T:
        self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(
            self._run_with_client(
                server_url,
                auth_token,
                coro_func,
                *args,
                **kwargs,
            ),
            self._loop,
        )
        return future.result()

    def set_server(self, server_url: str, auth_token: str) -> None:
        self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(
            self._set_server_async(server_url, auth_token),
            self._loop,
        )
        future.add_done_callback(self._log_future_error)

    def stop(self) -> None:
        if not self._loop or not self._loop.is_running():
            return
        future = asyncio.run_coroutine_threadsafe(
            self._shutdown(),
            self._loop,
        )
        try:
            future.result(timeout=3)
        except Exception as exc:
            self._logger.debug("Client session shutdown failed: %s", exc)
        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=1)
        self._loop = None
        self._thread = None

    async def _run_with_client(
        self,
        server_url: str,
        auth_token: str,
        coro_func: Callable[..., Awaitable[T]],
        *args: object,
        **kwargs: object,
    ) -> T:
        if self._connection_lock is None:
            self._connection_lock = asyncio.Lock()
        if self._request_lock is None:
            self._request_lock = asyncio.Lock()
        async with self._request_lock:
            async with self._connection_lock:
                client = await self._ensure_client(server_url, auth_token)
            try:
                return await coro_func(client, *args, **kwargs)
            except Exception as exc:
                should_reset = self._is_connection_error(exc)
                if should_reset:
                    self._logger.debug(
                        "Client session disconnected; resetting connection."
                    )
                    async with self._connection_lock:
                        await self._close_client()
                if not self._should_retry_on_disconnect(exc):
                    raise
                try:
                    async with self._connection_lock:
                        client = await self._ensure_client(server_url, auth_token)
                    return await coro_func(client, *args, **kwargs)
                except Exception as retry_exc:
                    if self._is_connection_error(retry_exc):
                        async with self._connection_lock:
                            await self._close_client()
                    raise

    async def _set_server_async(
        self,
        server_url: str,
        auth_token: str,
    ) -> None:
        if self._connection_lock is None:
            self._connection_lock = asyncio.Lock()
        async with self._connection_lock:
            if not server_url:
                await self._close_client()
                return
            await self._ensure_client(server_url, auth_token)

    async def _shutdown(self) -> None:
        if self._connection_lock is None:
            self._connection_lock = asyncio.Lock()
        async with self._connection_lock:
            await self._close_client()

    async def _ensure_client(
        self,
        server_url: str,
        auth_token: str,
    ) -> MusicAssistantClient:
        if not server_url:
            await self._close_client()
            raise RuntimeError("Server URL not configured")
        token = auth_token or None
        if (
            self._client
            and self._server_url == server_url
            and self._auth_token == token
        ):
            if self._client_is_connected():
                return self._client
        await self._close_client()
        client_cm = MusicAssistantClient(server_url, None, token=token)
        client = await client_cm.__aenter__()
        self._client_cm = client_cm
        self._client = client
        self._server_url = server_url
        self._auth_token = token
        return client

    async def _close_client(self) -> None:
        if self._client_cm:
            try:
                await self._client_cm.__aexit__(None, None, None)
            except Exception as exc:
                self._logger.debug("Client session close failed: %s", exc)
        self._client_cm = None
        self._client = None
        self._server_url = ""
        self._auth_token = None

    def _client_is_connected(self) -> bool:
        client = self._client
        if not client:
            return False
        connected = getattr(client, "connected", None)
        if connected is False:
            return False
        connection = getattr(client, "connection", None)
        if connection is None:
            connection = getattr(client, "_connection", None)
        if connection is not None:
            conn_connected = getattr(connection, "connected", None)
            if conn_connected is False:
                return False
        return True

    @staticmethod
    def _is_connection_error(exc: Exception) -> bool:
        if isinstance(exc, ConnectionError):
            return True
        message = str(exc).casefold()
        return any(
            token in message
            for token in (
                "not connected",
                "connection closed",
                "connection lost",
                "disconnected",
                "cannot connect",
            )
        )

    @staticmethod
    def _should_retry_on_disconnect(exc: Exception) -> bool:
        message = str(exc).casefold()
        return "not connected" in message

    def _log_future_error(self, future: object) -> None:
        try:
            future.result()
        except Exception as exc:
            self._logger.debug("Client session task failed: %s", exc)
