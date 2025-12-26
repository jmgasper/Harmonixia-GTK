from __future__ import annotations

import logging
import os

from music_assistant_client import MusicAssistantClient
from music_assistant_client.exceptions import MusicAssistantClientException
from music_assistant_models.enums import QueueOption


def build_media_uri_list(tracks: list[dict]) -> list[str]:
    if not tracks:
        return []
    uris = []
    for item in tracks:
        uri = item.get("source_uri")
        if not uri:
            return []
        uris.append(uri)
    return uris


def _normalize_queue_state(state: object) -> str:
    if state is None:
        return ""
    value = getattr(state, "value", state)
    text = str(value).casefold()
    if text.startswith("playbackstate."):
        return text.split(".", 1)[1]
    return text


async def resolve_player_and_queue(
    client: MusicAssistantClient, preferred_player_id: str | None
) -> tuple[str, str]:
    await client.players.fetch_state()
    await client.player_queues.fetch_state()
    players = [
        player
        for player in client.players.players
        if player.available and player.enabled
    ]
    if not players:
        raise MusicAssistantClientException("No available players")
    if preferred_player_id:
        player = next(
            (
                candidate
                for candidate in players
                if candidate.player_id == preferred_player_id
            ),
            players[0],
        )
        if os.getenv("SENDSPIN_DEBUG") and player.player_id != preferred_player_id:
            logging.getLogger(__name__).info(
                "Preferred output unavailable; using %s instead.",
                player.player_id,
            )
    else:
        player = players[0]
    queue = await client.player_queues.get_active_queue(player.player_id)
    queue_id = queue.queue_id if queue else player.player_id
    if os.getenv("SENDSPIN_DEBUG"):
        logging.getLogger(__name__).info(
            "Resolved playback target: player=%s queue=%s",
            player.player_id,
            queue_id,
        )
    return player.player_id, queue_id


async def _play_album_async(
    client: MusicAssistantClient,
    track_uri: str,
    album_media: list[str],
    start_index: int,
    preferred_player_id: str | None,
) -> str:
    player_id, queue_id = await resolve_player_and_queue(
        client, preferred_player_id
    )
    if os.getenv("SENDSPIN_DEBUG"):
        logging.getLogger(__name__).info(
            "Sending play_media to queue=%s (player=%s).",
            queue_id,
            player_id,
        )
    if album_media:
        if start_index:
            await client.player_queues.clear(queue_id)
            await client.player_queues.play_media(
                queue_id,
                album_media,
                option=QueueOption.ADD,
            )
            await client.player_queues.play_index(queue_id, start_index)
        else:
            await client.player_queues.play_media(
                queue_id,
                album_media,
                option=QueueOption.REPLACE,
            )
    else:
        await client.player_queues.play_media(
            queue_id,
            track_uri,
            option=QueueOption.REPLACE,
        )
    if os.getenv("SENDSPIN_DEBUG"):
        queue = None
        try:
            queue = await client.player_queues.get_active_queue(player_id)
        except Exception:
            queue = None
        logging.getLogger(__name__).info(
            "Queue state after play_media: state=%s elapsed=%s current_item=%s",
            getattr(queue, "state", None) if queue else None,
            getattr(queue, "elapsed_time", None) if queue else None,
            getattr(queue, "current_item", None) if queue else None,
        )
    return player_id


def play_album(
    client_session,
    server_url: str,
    auth_token: str,
    track_uri: str,
    album_media: list[str],
    start_index: int,
    preferred_player_id: str | None,
) -> str:
    return client_session.run(
        server_url,
        auth_token,
        _play_album_async,
        track_uri,
        album_media,
        start_index,
        preferred_player_id,
    )


async def _playback_command_async(
    client: MusicAssistantClient,
    command: str,
    preferred_player_id: str | None,
    position: int | None,
) -> None:
    _player_id, queue_id = await resolve_player_and_queue(
        client, preferred_player_id
    )
    if command == "pause":
        await client.player_queues.pause(queue_id)
    elif command == "resume":
        await client.player_queues.resume(queue_id)
    elif command == "next":
        await client.player_queues.next(queue_id)
    elif command == "previous":
        await client.player_queues.previous(queue_id)
    elif command == "seek" and position is not None:
        await client.player_queues.seek(queue_id, position)


async def _play_index_async(
    client: MusicAssistantClient,
    index: int,
    preferred_player_id: str | None,
) -> None:
    _player_id, queue_id = await resolve_player_and_queue(
        client, preferred_player_id
    )
    await client.player_queues.play_index(queue_id, int(index))


def send_playback_command(
    client_session,
    server_url: str,
    auth_token: str,
    command: str,
    preferred_player_id: str | None,
    position: int | None = None,
) -> None:
    client_session.run(
        server_url,
        auth_token,
        _playback_command_async,
        command,
        preferred_player_id,
        position,
    )


def play_index(
    client_session,
    server_url: str,
    auth_token: str,
    index: int,
    preferred_player_id: str | None,
) -> None:
    client_session.run(
        server_url,
        auth_token,
        _play_index_async,
        index,
        preferred_player_id,
    )


async def _volume_command_async(
    client: MusicAssistantClient,
    player_id: str,
    volume: int,
) -> None:
    await client.players.volume_set(player_id, volume)


def set_player_volume(
    client_session,
    server_url: str,
    auth_token: str,
    player_id: str,
    volume: int,
) -> None:
    client_session.run(
        server_url,
        auth_token,
        _volume_command_async,
        player_id,
        volume,
    )


__all__ = [
    "play_album",
    "play_index",
    "send_playback_command",
    "set_player_volume",
    "resolve_player_and_queue",
    "build_media_uri_list",
]
