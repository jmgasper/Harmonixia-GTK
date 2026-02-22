from __future__ import annotations

import logging
import os
import inspect

from music_assistant_client import MusicAssistantClient
from music_assistant_client.exceptions import MusicAssistantClientException
from music_assistant_models.enums import QueueOption


def build_media_uri_list(tracks: list[dict]) -> list[str]:
    if not tracks:
        return []
    uris = []
    for item in tracks:
        if isinstance(item, dict):
            uri = item.get("source_uri")
            if not uri:
                source = item.get("source")
                if isinstance(source, dict):
                    uri = source.get("uri") or source.get("source_uri")
                elif source is not None:
                    uri = getattr(source, "uri", None) or getattr(
                        source, "source_uri", None
                    )
        else:
            uri = getattr(item, "source_uri", None)
            if not uri:
                source = getattr(item, "source", None)
                if isinstance(source, dict):
                    uri = source.get("uri") or source.get("source_uri")
                elif source is not None:
                    uri = getattr(source, "uri", None) or getattr(
                        source, "source_uri", None
                    )
        if isinstance(uri, str):
            uri = uri.strip()
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


def _get_media_attr(item: object | None, key: str) -> object | None:
    if item is None:
        return None
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key, None)


def _normalize_player_id(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text


def _extract_group_member_ids(player: object | None) -> set[str]:
    if player is None:
        return set()
    members: set[str] = set()
    raw_members = (
        _get_media_attr(player, "group_members")
        or _get_media_attr(player, "members")
        or _get_media_attr(player, "child_player_ids")
        or []
    )
    for member in raw_members:
        member_id = _normalize_player_id(
            _get_media_attr(member, "player_id") if member is not None else None
        ) or _normalize_player_id(member)
        if member_id:
            members.add(member_id)
    player_id = _normalize_player_id(_get_media_attr(player, "player_id"))
    if player_id:
        members.discard(player_id)
    return members


def _extract_queue_media_item(item: object) -> object:
    for key in ("media_item", "item", "track", "media"):
        candidate = _get_media_attr(item, key)
        if candidate:
            return candidate
    return item


def _normalize_queue_artist(media_item: object) -> str:
    artist = _get_media_attr(media_item, "artist_str") or _get_media_attr(
        media_item, "artist"
    )
    if artist:
        return str(artist)
    artists = _get_media_attr(media_item, "artists") or []
    names: list[str] = []
    for entry in artists:
        name = _get_media_attr(entry, "name") or _get_media_attr(
            entry, "sort_name"
        )
        if name:
            names.append(str(name))
    return ", ".join(names)


def _iter_image_candidates(value: object):
    if isinstance(value, str):
        candidate = value.strip()
        if candidate:
            yield candidate
        return
    if isinstance(value, dict):
        for key in ("url", "path", "uri"):
            candidate = value.get(key)
            if isinstance(candidate, str):
                normalized = candidate.strip()
                if normalized:
                    yield normalized
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_image_candidates(item)
        return
    for key in ("url", "path", "uri"):
        candidate = getattr(value, key, None)
        if isinstance(candidate, str):
            normalized = candidate.strip()
            if normalized:
                yield normalized


def _extract_queue_image_url(media_item: object) -> str | None:
    to_scan = [media_item]
    visited: set[int] = set()
    while to_scan:
        candidate_item = to_scan.pop(0)
        marker = id(candidate_item)
        if marker in visited:
            continue
        visited.add(marker)
        for key in (
            "image_url",
            "cover_image_url",
            "image",
            "artwork",
            "cover",
            "thumbnail",
        ):
            for image_url in _iter_image_candidates(
                _get_media_attr(candidate_item, key)
            ):
                return image_url
        metadata = _get_media_attr(candidate_item, "metadata")
        if metadata is not None:
            for key in ("image", "images"):
                for image_url in _iter_image_candidates(
                    _get_media_attr(metadata, key)
                ):
                    return image_url
        album = _get_media_attr(candidate_item, "album")
        if album is not None and album is not candidate_item:
            to_scan.append(album)
    return None


def _serialize_queue_item(item: object, index: int) -> dict:
    media_item = _extract_queue_media_item(item)
    title = _get_media_attr(media_item, "name") or _get_media_attr(
        media_item, "title"
    )
    if not title:
        title = "Unknown Track"
    duration = (
        _get_media_attr(media_item, "duration")
        or _get_media_attr(media_item, "length_seconds")
        or _get_media_attr(media_item, "length")
        or 0
    )
    try:
        duration_seconds = int(duration)
    except (TypeError, ValueError):
        duration_seconds = 0
    uri = _get_media_attr(media_item, "uri") or _get_media_attr(item, "uri")
    queue_item_id = (
        _get_media_attr(item, "queue_item_id")
        or _get_media_attr(item, "item_id")
        or _get_media_attr(item, "id")
    )
    image_url = _extract_queue_image_url(media_item)
    return {
        "index": index,
        "item_id": queue_item_id,
        "title": str(title),
        "artist": _normalize_queue_artist(media_item),
        "duration": duration_seconds,
        "uri": str(uri) if uri is not None else "",
        "image_url": image_url or "",
    }


async def resolve_player_and_queue(
    client: MusicAssistantClient, preferred_player_id: str | None
) -> tuple[str, str]:
    if preferred_player_id:
        cached_players = list(client.players.players)
        if cached_players:
            player = next(
                (
                    candidate
                    for candidate in cached_players
                    if candidate.player_id == preferred_player_id
                    and candidate.available
                    and candidate.enabled
                ),
                None,
            )
            if player:
                queue = await client.player_queues.get_active_queue(
                    player.player_id
                )
                queue_id = queue.queue_id if queue else player.player_id
                if os.getenv("SENDSPIN_DEBUG"):
                    logging.getLogger(__name__).info(
                        "Resolved playback target: player=%s queue=%s",
                        player.player_id,
                        queue_id,
                    )
                return player.player_id, queue_id

    # Fall back to full state refresh.
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


async def _add_to_queue_async(
    client: MusicAssistantClient,
    media: object,
    preferred_player_id: str | None,
) -> None:
    _player_id, queue_id = await resolve_player_and_queue(
        client, preferred_player_id
    )
    await client.player_queues.play_media(
        queue_id,
        media,
        option=QueueOption.ADD,
    )


async def _play_next_async(
    client: MusicAssistantClient,
    media: object,
    preferred_player_id: str | None,
) -> None:
    _player_id, queue_id = await resolve_player_and_queue(
        client, preferred_player_id
    )
    await client.player_queues.play_media(
        queue_id,
        media,
        option=QueueOption.NEXT,
    )


async def _play_radio_async(
    client: MusicAssistantClient,
    media: object,
    preferred_player_id: str | None,
) -> None:
    _player_id, queue_id = await resolve_player_and_queue(
        client, preferred_player_id
    )
    await client.player_queues.play_media(
        queue_id,
        media,
        option=QueueOption.REPLACE,
        radio_mode=True,
    )


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


def add_to_queue(
    client_session,
    server_url: str,
    auth_token: str,
    media: object,
    preferred_player_id: str | None,
) -> None:
    client_session.run(
        server_url,
        auth_token,
        _add_to_queue_async,
        media,
        preferred_player_id,
    )


def play_next(
    client_session,
    server_url: str,
    auth_token: str,
    media: object,
    preferred_player_id: str | None,
) -> None:
    client_session.run(
        server_url,
        auth_token,
        _play_next_async,
        media,
        preferred_player_id,
    )


def play_radio(
    client_session,
    server_url: str,
    auth_token: str,
    media: object,
    preferred_player_id: str | None,
) -> None:
    client_session.run(
        server_url,
        auth_token,
        _play_radio_async,
        media,
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


async def _get_queue_items(
    client: MusicAssistantClient, queue_id: str
) -> list[object]:
    def _coerce_queue_items_result(result: object) -> list[object]:
        if not result:
            return []
        if isinstance(result, dict):
            nested_items = result.get("items")
            if nested_items is not None:
                result = nested_items
            else:
                return []
        if isinstance(result, list):
            return result
        try:
            return list(result)
        except TypeError:
            return []

    for method_name in ("get_queue_items", "items", "queue_items"):
        fetch_method = getattr(client.player_queues, method_name, None)
        if not callable(fetch_method):
            continue
        try:
            result = fetch_method(queue_id)
        except TypeError:
            try:
                result = fetch_method(queue_id=queue_id)
            except TypeError:
                continue
        if inspect.isawaitable(result):
            result = await result
        return _coerce_queue_items_result(result)

    send_command = getattr(client, "send_command", None)
    if callable(send_command):
        result = send_command(
            "player_queues/items",
            queue_id=queue_id,
            limit=500,
            offset=0,
        )
        if inspect.isawaitable(result):
            result = await result
        return _coerce_queue_items_result(result)

    raise MusicAssistantClientException(
        "Queue item retrieval is unavailable in this Music Assistant client version"
    )


async def _fetch_queue_items_async(
    client: MusicAssistantClient,
    preferred_player_id: str | None,
) -> list[dict]:
    _player_id, queue_id = await resolve_player_and_queue(
        client, preferred_player_id
    )
    queue_items = await _get_queue_items(client, queue_id)
    return [
        _serialize_queue_item(item, index)
        for index, item in enumerate(queue_items)
    ]


async def _delete_queue_item_async(
    client: MusicAssistantClient,
    preferred_player_id: str | None,
    item_id: str,
) -> None:
    _player_id, queue_id = await resolve_player_and_queue(
        client, preferred_player_id
    )
    await client.player_queues.delete_item(queue_id, item_id)


async def _clear_queue_async(
    client: MusicAssistantClient,
    preferred_player_id: str | None,
) -> None:
    _player_id, queue_id = await resolve_player_and_queue(
        client, preferred_player_id
    )
    clear_method = getattr(client.player_queues, "clear", None)
    if callable(clear_method):
        result = clear_method(queue_id)
        if inspect.isawaitable(result):
            await result
        return
    clear_method = getattr(client.player_queues, "queue_command_clear", None)
    if callable(clear_method):
        result = clear_method(queue_id)
        if inspect.isawaitable(result):
            await result
        return
    queue_items = await _get_queue_items(client, queue_id)
    for item in queue_items:
        item_id = (
            _get_media_attr(item, "queue_item_id")
            or _get_media_attr(item, "item_id")
            or _get_media_attr(item, "id")
        )
        if item_id is None:
            continue
        await client.player_queues.delete_item(queue_id, str(item_id))


async def _move_queue_item_async(
    client: MusicAssistantClient,
    preferred_player_id: str | None,
    queue_item_id: str,
    pos_before: int,
) -> None:
    pos_shift = int(pos_before)
    if pos_shift == 0:
        return
    _player_id, queue_id = await resolve_player_and_queue(
        client, preferred_player_id
    )
    if pos_shift < 0 and hasattr(client.player_queues, "move_up"):
        await client.player_queues.move_up(queue_id, queue_item_id)
        return
    if pos_shift > 0 and hasattr(client.player_queues, "move_down"):
        await client.player_queues.move_down(queue_id, queue_item_id)
        return
    await client.player_queues.move_item(queue_id, queue_item_id, pos_shift)


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


async def _group_players_async(
    client: MusicAssistantClient,
    player_id: str,
    group_member_ids: list[str],
) -> None:
    normalized_player_id = _normalize_player_id(player_id)
    if not normalized_player_id:
        raise MusicAssistantClientException("Invalid player id")
    normalized_group_members = sorted(
        {
            candidate
            for candidate in (
                _normalize_player_id(member_id)
                for member_id in group_member_ids
            )
            if candidate and candidate != normalized_player_id
        }
    )
    if hasattr(client.players, "set_members"):
        await client.players.fetch_state()
        current_player = client.players.get(normalized_player_id)
        current_members = _extract_group_member_ids(current_player)
        members_to_add = sorted(
            set(normalized_group_members) - set(current_members)
        )
        members_to_remove = sorted(
            set(current_members) - set(normalized_group_members)
        )
        result = client.players.set_members(
            normalized_player_id,
            members_to_add or None,
            members_to_remove or None,
        )
        if inspect.isawaitable(result):
            await result
        return
    if hasattr(client.players, "group_players"):
        await client.players.group_players(
            normalized_player_id, normalized_group_members
        )
        return
    if hasattr(client.players, "group_many"):
        await client.players.group_many(
            normalized_player_id, normalized_group_members
        )
        return
    if hasattr(client.players, "group"):
        await client.players.fetch_state()
        current_player = client.players.get(normalized_player_id)
        current_members = _extract_group_member_ids(current_player)
        for member_id in sorted(
            set(normalized_group_members) - set(current_members)
        ):
            await client.players.group(member_id, normalized_player_id)
        return
    raise MusicAssistantClientException("Player grouping is not supported")


async def _ungroup_player_async(
    client: MusicAssistantClient,
    player_id: str,
) -> None:
    if hasattr(client.players, "ungroup_player"):
        await client.players.ungroup_player(player_id)
        return
    if hasattr(client.players, "ungroup"):
        await client.players.ungroup(player_id)
        return
    if hasattr(client.players, "player_command_ungroup"):
        await client.players.player_command_ungroup(player_id)
        return
    raise MusicAssistantClientException("Player ungrouping is not supported")


async def _fetch_group_member_ids_async(
    client: MusicAssistantClient,
    preferred_player_id: str | None,
) -> list[str]:
    player_id = _normalize_player_id(preferred_player_id)
    if not player_id:
        return []
    await client.players.fetch_state()
    players = list(getattr(client.players, "players", []) or [])
    players_by_id = {
        candidate_id: player
        for player in players
        for candidate_id in [
            _normalize_player_id(_get_media_attr(player, "player_id"))
        ]
        if candidate_id
    }
    selected_player = players_by_id.get(player_id)
    if selected_player is None:
        return []

    member_ids = _extract_group_member_ids(selected_player)
    active_group_id = _normalize_player_id(
        _get_media_attr(selected_player, "active_group")
    )
    synced_to_id = _normalize_player_id(
        _get_media_attr(selected_player, "synced_to")
    )
    for group_owner_id in (active_group_id, synced_to_id):
        if not group_owner_id or group_owner_id == player_id:
            continue
        member_ids.add(group_owner_id)
        member_ids.update(_extract_group_member_ids(players_by_id.get(group_owner_id)))

    for player in players:
        candidate_id = _normalize_player_id(
            _get_media_attr(player, "player_id")
        )
        if not candidate_id or candidate_id == player_id:
            continue
        if (
            _normalize_player_id(_get_media_attr(player, "active_group"))
            == player_id
        ):
            member_ids.add(candidate_id)
        if _normalize_player_id(_get_media_attr(player, "synced_to")) == player_id:
            member_ids.add(candidate_id)
    member_ids.discard(player_id)
    return sorted(member_ids)


async def _update_player_settings_async(
    client: MusicAssistantClient,
    player_id: str,
    crossfade_duration: int,
    flow_mode: bool,
) -> None:
    payload = {
        "crossfade_duration": int(max(0, min(10, crossfade_duration))),
        "flow_mode": bool(flow_mode),
    }
    if not hasattr(client.players, "update_player_config"):
        raise MusicAssistantClientException(
            "Player playback settings are not supported"
        )
    updater = client.players.update_player_config
    try:
        result = updater(player_id, payload)
    except TypeError:
        result = updater(player_id, **payload)
    if inspect.isawaitable(result):
        await result


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


def group_players(
    client_session,
    server_url: str,
    auth_token: str,
    player_id: str,
    group_member_ids: list[str],
) -> None:
    client_session.run(
        server_url,
        auth_token,
        _group_players_async,
        player_id,
        group_member_ids,
    )


def ungroup_player(
    client_session,
    server_url: str,
    auth_token: str,
    player_id: str,
) -> None:
    client_session.run(
        server_url,
        auth_token,
        _ungroup_player_async,
        player_id,
    )


def update_player_settings(
    client_session,
    server_url: str,
    auth_token: str,
    player_id: str,
    crossfade_duration: int,
    flow_mode: bool,
) -> None:
    client_session.run(
        server_url,
        auth_token,
        _update_player_settings_async,
        player_id,
        crossfade_duration,
        flow_mode,
    )


def fetch_queue_items(
    client_session,
    server_url: str,
    auth_token: str,
    preferred_player_id: str | None,
) -> list[dict]:
    return client_session.run(
        server_url,
        auth_token,
        _fetch_queue_items_async,
        preferred_player_id,
    )


def delete_queue_item(
    client_session,
    server_url: str,
    auth_token: str,
    preferred_player_id: str | None,
    item_id: str,
) -> None:
    client_session.run(
        server_url,
        auth_token,
        _delete_queue_item_async,
        preferred_player_id,
        item_id,
    )


def clear_queue(
    client_session,
    server_url: str,
    auth_token: str,
    preferred_player_id: str | None,
) -> None:
    client_session.run(
        server_url,
        auth_token,
        _clear_queue_async,
        preferred_player_id,
    )


def move_queue_item(
    client_session,
    server_url: str,
    auth_token: str,
    preferred_player_id: str | None,
    queue_item_id: str,
    pos_before: int,
) -> None:
    client_session.run(
        server_url,
        auth_token,
        _move_queue_item_async,
        preferred_player_id,
        queue_item_id,
        pos_before,
    )


def fetch_group_member_ids(
    client_session,
    server_url: str,
    auth_token: str,
    preferred_player_id: str | None,
) -> list[str]:
    return client_session.run(
        server_url,
        auth_token,
        _fetch_group_member_ids_async,
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
    "add_to_queue",
    "play_next",
    "play_radio",
    "play_index",
    "group_players",
    "ungroup_player",
    "update_player_settings",
    "fetch_queue_items",
    "delete_queue_item",
    "clear_queue",
    "move_queue_item",
    "fetch_group_member_ids",
    "send_playback_command",
    "set_queue_repeat_mode",
    "set_queue_shuffle",
    "transfer_queue",
    "set_player_volume",
    "step_player_volume",
    "resolve_player_and_queue",
    "build_media_uri_list",
]
