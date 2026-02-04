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
    media: object,
    start_item: object | None,
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
    await client.player_queues.play_media(
        queue_id,
        media,
        option=QueueOption.REPLACE,
        start_item=start_item,
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
    media: object,
    start_item: object | None,
    preferred_player_id: str | None,
) -> str:
    return client_session.run(
        server_url,
        auth_token,
        _play_album_async,
        media,
        start_item,
        preferred_player_id,
    )


async def _playback_command_async(
    client: MusicAssistantClient,
    command: str,
    preferred_player_id: str | None,
    position: int | None,
) -> None:
    if preferred_player_id:
        try:
            await _send_player_command(
                client,
                command,
                preferred_player_id,
                position,
            )
            return
        except MusicAssistantClientException as exc:
            if os.getenv("SENDSPIN_DEBUG"):
                logging.getLogger(__name__).info(
                    "Playback command fast-path failed for %s: %s",
                    preferred_player_id,
                    exc,
                )
    player_id, _queue_id = await resolve_player_and_queue(
        client, preferred_player_id
    )
    await _send_player_command(client, command, player_id, position)


async def _send_player_command(
    client: MusicAssistantClient,
    command: str,
    player_id: str,
    position: int | None,
) -> None:
    if command == "pause":
        await client.players.pause(player_id)
    elif command in ("play", "resume"):
        await client.players.play(player_id)
    elif command == "next":
        await client.players.next_track(player_id)
    elif command == "previous":
        await client.players.previous_track(player_id)
    elif command == "stop":
        await client.players.stop(player_id)
    elif command == "seek" and position is not None:
        await client.players.seek(player_id, position)


def _coerce_repeat_mode(value: object):
    try:
        from music_assistant_models.enums import RepeatMode
    except Exception:
        return value
    if isinstance(value, RepeatMode):
        return value
    if isinstance(value, str):
        text = value.casefold()
        if text in ("off", "none", "disabled"):
            return RepeatMode.OFF
        if text in ("one", "track", "single"):
            return RepeatMode.ONE
        if text in ("all", "playlist"):
            return RepeatMode.ALL
    return value


async def _set_repeat_mode_async(
    client: MusicAssistantClient,
    repeat_mode: object,
    preferred_player_id: str | None,
) -> None:
    _player_id, queue_id = await resolve_player_and_queue(
        client, preferred_player_id
    )
    await client.player_queues.repeat(queue_id, _coerce_repeat_mode(repeat_mode))


async def _set_shuffle_async(
    client: MusicAssistantClient,
    enabled: bool,
    preferred_player_id: str | None,
) -> None:
    _player_id, queue_id = await resolve_player_and_queue(
        client, preferred_player_id
    )
    await client.player_queues.shuffle(queue_id, bool(enabled))


async def _play_index_async(
    client: MusicAssistantClient,
    index: int,
    preferred_player_id: str | None,
) -> None:
    _player_id, queue_id = await resolve_player_and_queue(
        client, preferred_player_id
    )
    await client.player_queues.play_index(queue_id, int(index))


async def _transfer_queue_async(
    client: MusicAssistantClient,
    source_player_id: str,
    target_player_id: str,
    auto_play: bool | None,
) -> None:
    await client.players.fetch_state()
    await client.player_queues.fetch_state()
    source_player = client.players.get(source_player_id)
    target_player = client.players.get(target_player_id)
    if not source_player:
        raise MusicAssistantClientException(
            f"Source output unavailable: {source_player_id}"
        )
    if not target_player:
        raise MusicAssistantClientException(
            f"Target output unavailable: {target_player_id}"
        )
    source_queue = await client.player_queues.get_active_queue(
        source_player_id
    )
    target_queue = await client.player_queues.get_active_queue(
        target_player_id
    )
    source_queue_id = (
        source_queue.queue_id if source_queue else source_player_id
    )
    target_queue_id = (
        target_queue.queue_id if target_queue else target_player_id
    )
    if source_queue_id == target_queue_id:
        return
    await client.player_queues.transfer(
        source_queue_id,
        target_queue_id,
        auto_play=auto_play,
    )


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


def set_queue_repeat_mode(
    client_session,
    server_url: str,
    auth_token: str,
    repeat_mode: object,
    preferred_player_id: str | None,
) -> None:
    client_session.run(
        server_url,
        auth_token,
        _set_repeat_mode_async,
        repeat_mode,
        preferred_player_id,
    )


def set_queue_shuffle(
    client_session,
    server_url: str,
    auth_token: str,
    enabled: bool,
    preferred_player_id: str | None,
) -> None:
    client_session.run(
        server_url,
        auth_token,
        _set_shuffle_async,
        enabled,
        preferred_player_id,
    )


def transfer_queue(
    client_session,
    server_url: str,
    auth_token: str,
    source_player_id: str,
    target_player_id: str,
    auto_play: bool | None = None,
) -> None:
    client_session.run(
        server_url,
        auth_token,
        _transfer_queue_async,
        source_player_id,
        target_player_id,
        auto_play,
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


async def _volume_step_async(
    client: MusicAssistantClient,
    player_id: str,
    direction: int,
    steps: int,
) -> None:
    if direction == 0 or steps <= 0:
        return
    if direction > 0:
        for _ in range(steps):
            await client.players.volume_up(player_id)
    else:
        for _ in range(steps):
            await client.players.volume_down(player_id)


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


def step_player_volume(
    client_session,
    server_url: str,
    auth_token: str,
    player_id: str,
    direction: int,
    steps: int,
) -> None:
    if direction == 0 or steps <= 0:
        return
    client_session.run(
        server_url,
        auth_token,
        _volume_step_async,
        player_id,
        direction,
        steps,
    )


__all__ = [
    "play_album",
    "play_index",
    "send_playback_command",
    "set_queue_repeat_mode",
    "set_queue_shuffle",
    "transfer_queue",
    "set_player_volume",
    "step_player_volume",
    "resolve_player_and_queue",
    "build_media_uri_list",
]
