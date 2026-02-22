import re
from typing import Any

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

from .client import TrelloApiError, TrelloAuthError, TrelloClient


@register(
    "astrbot_plugin_trello_control",
    "Potatoworkshop",
    "Control Trello boards and cards with AstrBot commands.",
    "0.2.0",
)
class TrelloPlugin(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context, config)
        self.context = context
        self.config = config or {}
        timeout = int(self.config.get("request_timeout_sec", 20) or 20)
        self.client = TrelloClient(timeout=timeout)

    def _session_key(self, event: AstrMessageEvent, key: str) -> str:
        return f"session:{event.unified_msg_origin}:{key}"

    async def terminate(self):
        await self.client.close()

    def _tail(self, event: AstrMessageEvent, command: str) -> str:
        text = event.message_str.strip()
        pattern = rf"^[^\w]*trello\s+{re.escape(command)}\b\s*(.*)$"
        match = re.match(pattern, text, flags=re.IGNORECASE)
        if not match:
            return ""
        return match.group(1).strip()

    def _split_pipe(self, value: str) -> tuple[str, str]:
        if "|" not in value:
            return value.strip(), ""
        left, right = value.split("|", 1)
        return left.strip(), right.strip()

    def _tail_pipe(self, event: AstrMessageEvent, command: str) -> tuple[str, str]:
        return self._split_pipe(self._tail(event, command))

    async def _get_credentials(self) -> tuple[str, str]:
        api_key = str(self.config.get("trello_api_key", "") or "")
        token = str(self.config.get("trello_token", "") or "")
        return str(api_key or ""), str(token or "")

    async def _get_session_board_id(self, event: AstrMessageEvent) -> str:
        return str(
            await self.get_kv_data(self._session_key(event, "board_id"), "") or ""
        )

    async def _get_session_list_id(self, event: AstrMessageEvent) -> str:
        return str(
            await self.get_kv_data(self._session_key(event, "list_id"), "") or ""
        )

    async def _get_session_done_list_id(self, event: AstrMessageEvent) -> str:
        return str(
            await self.get_kv_data(self._session_key(event, "done_list_id"), "") or ""
        )

    async def _get_session_card_id(self, event: AstrMessageEvent) -> str:
        return str(
            await self.get_kv_data(self._session_key(event, "card_id"), "") or ""
        )

    @staticmethod
    def _looks_like_trello_id(value: str) -> bool:
        return bool(re.fullmatch(r"[A-Fa-f0-9]{24}", value or ""))

    @staticmethod
    def _match_named_item(
        items: list[dict],
        query: str,
        *,
        id_key: str = "id",
        name_key: str = "name",
    ) -> tuple[dict | None, str | None]:
        q = (query or "").strip()
        if not q:
            return None, "Empty query."

        lowered = q.casefold()
        exact = [
            item
            for item in items
            if str(item.get(name_key, "")).strip().casefold() == lowered
        ]
        if len(exact) == 1:
            return exact[0], None
        if len(exact) > 1:
            names = ", ".join(
                f"{item.get(name_key)} ({item.get(id_key)})" for item in exact[:5]
            )
            return None, f"Ambiguous name: {q}. Matches: {names}"

        partial = [
            item
            for item in items
            if lowered in str(item.get(name_key, "")).strip().casefold()
        ]
        if len(partial) == 1:
            return partial[0], None
        if len(partial) > 1:
            names = ", ".join(
                f"{item.get(name_key)} ({item.get(id_key)})" for item in partial[:5]
            )
            return None, f"Ambiguous name: {q}. Matches: {names}"

        return None, f"No item matched name: {q}"

    async def _resolve_board_ref(
        self, event: AstrMessageEvent, api_key: str, token: str, board_ref: str
    ) -> tuple[str, dict | None, str | None]:
        ref = (board_ref or "").strip()
        if not ref:
            ref = await self._get_session_board_id(event)
            if not ref:
                return (
                    "",
                    None,
                    "No board selected. Use /trello use-board <board_id|name> first.",
                )

        if self._looks_like_trello_id(ref):
            return ref, None, None

        boards = await self.client.get_boards(api_key=api_key, token=token)
        item, err = self._match_named_item(boards, ref)
        if err:
            return "", None, err
        return str(item.get("id") or ""), item, None

    async def _resolve_list_ref(
        self, event: AstrMessageEvent, api_key: str, token: str, list_ref: str
    ) -> tuple[str, dict | None, str | None]:
        ref = (list_ref or "").strip()
        if not ref:
            ref = await self._get_session_list_id(event)
            if not ref:
                return (
                    "",
                    None,
                    "No list selected. Use /trello use-list <list_id|name> first.",
                )

        if self._looks_like_trello_id(ref):
            return ref, None, None

        board_id = await self._get_session_board_id(event)
        if not board_id:
            return (
                "",
                None,
                "List name lookup requires a selected board. Use /trello use-board <board_id|name> first.",
            )

        lists = await self.client.get_lists(
            api_key=api_key, token=token, board_id=board_id
        )
        item, err = self._match_named_item(lists, ref)
        if err:
            return "", None, err
        return str(item.get("id") or ""), item, None

    async def _resolve_card_ref(
        self, event: AstrMessageEvent, api_key: str, token: str, card_ref: str
    ) -> tuple[str, dict | None, str | None]:
        ref = (card_ref or "").strip()
        if not ref:
            ref = await self._get_session_card_id(event)
            if not ref:
                return "", None, "Usage: /trello card <card_id|name>"

        if self._looks_like_trello_id(ref):
            return ref, None, None

        list_id = await self._get_session_list_id(event)
        if list_id:
            cards = await self.client.get_list_cards(
                api_key=api_key,
                token=token,
                list_id=list_id,
                limit=100,
            )
            item, err = self._match_named_item(cards, ref)
            if not err:
                return str(item.get("id") or ""), item, None

        board_id = await self._get_session_board_id(event)
        if not board_id:
            return (
                "",
                None,
                "Card name lookup requires a selected list or board. Use /trello use-list or /trello use-board first.",
            )

        cards = await self.client.search_cards(
            api_key=api_key,
            token=token,
            board_id=board_id,
            keyword=ref,
            limit=20,
        )
        item, err = self._match_named_item(cards, ref)
        if err:
            return "", None, err
        return str(item.get("id") or ""), item, None

    async def _set_current_board(self, event: AstrMessageEvent, board_id: str) -> None:
        await self.put_kv_data(self._session_key(event, "board_id"), board_id)

    async def _set_current_list(self, event: AstrMessageEvent, list_id: str) -> None:
        await self.put_kv_data(self._session_key(event, "list_id"), list_id)

    async def _set_current_card(self, event: AstrMessageEvent, card_id: str) -> None:
        await self.put_kv_data(self._session_key(event, "card_id"), card_id)

    @staticmethod
    def _normalize_resource(resource: str) -> str:
        value = (resource or "").strip().lower().replace("-", "_")
        aliases = {
            "boards": "board",
            "lists": "list",
            "cards": "card",
            "checklists": "checklist",
            "items": "checklist_item",
            "check_items": "checklist_item",
            "checkitem": "checklist_item",
            "check_item": "checklist_item",
        }
        return aliases.get(value, value)

    @staticmethod
    def _normalize_mode(mode: str) -> str:
        return (mode or "").strip().lower()

    async def _ensure_tool_credentials(
        self, event: AstrMessageEvent
    ) -> tuple[str, str, str | None]:
        api_key, token = await self._get_credentials()
        if not api_key or not token:
            return "", "", "Trello credentials are not configured."
        return api_key, token, None

    async def _sync_context_from_card(
        self,
        event: AstrMessageEvent,
        card: dict[str, Any],
    ) -> None:
        card_id = str(card.get("id") or "")
        board_id = str(card.get("idBoard") or "")
        list_id = str(card.get("idList") or "")
        if board_id:
            await self._set_current_board(event, board_id)
        if list_id:
            await self._set_current_list(event, list_id)
        if card_id:
            await self._set_current_card(event, card_id)

    async def _resolve_card_with_optional_parent(
        self,
        event: AstrMessageEvent,
        api_key: str,
        token: str,
        card_ref: str,
        *,
        parent_resource: str = "",
        parent_id_or_name: str = "",
    ) -> tuple[str, dict | None, str | None]:
        parent_resource = self._normalize_resource(parent_resource)
        parent_ref = (parent_id_or_name or "").strip()

        if (
            parent_resource == "list"
            and parent_ref
            and not self._looks_like_trello_id(card_ref)
        ):
            list_id, _, err = await self._resolve_list_ref(
                event, api_key, token, parent_ref
            )
            if err or not list_id:
                return "", None, err or "List not found."
            cards = await self.client.get_list_cards(
                api_key=api_key, token=token, list_id=list_id, limit=100
            )
            item, match_err = self._match_named_item(cards, card_ref)
            if match_err:
                return "", None, match_err
            return str(item.get("id") or ""), item, None

        if (
            parent_resource == "board"
            and parent_ref
            and not self._looks_like_trello_id(card_ref)
        ):
            board_id, _, err = await self._resolve_board_ref(
                event, api_key, token, parent_ref
            )
            if err or not board_id:
                return "", None, err or "Board not found."
            cards = await self.client.search_cards(
                api_key=api_key,
                token=token,
                board_id=board_id,
                keyword=card_ref,
                limit=20,
            )
            item, match_err = self._match_named_item(cards, card_ref)
            if match_err:
                return "", None, match_err
            return str(item.get("id") or ""), item, None

        return await self._resolve_card_ref(event, api_key, token, card_ref)

    async def _resolve_checklist_ref(
        self,
        event: AstrMessageEvent,
        api_key: str,
        token: str,
        checklist_ref: str,
        *,
        card_ref: str = "",
        parent_resource: str = "",
        parent_id_or_name: str = "",
    ) -> tuple[str, str, dict | None, str | None]:
        ref = (checklist_ref or "").strip()
        if not ref:
            return "", "", None, "Checklist id or name is required."

        card_id_for_lookup = ""
        if parent_resource and self._normalize_resource(parent_resource) == "card":
            card_id_for_lookup, _, err = await self._resolve_card_with_optional_parent(
                event,
                api_key,
                token,
                parent_id_or_name,
            )
            if err or not card_id_for_lookup:
                return "", "", None, err or "Card not found."
        elif card_ref:
            card_id_for_lookup, _, err = await self._resolve_card_with_optional_parent(
                event,
                api_key,
                token,
                card_ref,
            )
            if err or not card_id_for_lookup:
                return "", "", None, err or "Card not found."

        if self._looks_like_trello_id(ref):
            if card_id_for_lookup:
                checklists = await self.client.get_card_checklists(
                    api_key=api_key, token=token, card_id=card_id_for_lookup
                )
                for item in checklists:
                    if str(item.get("id") or "") == ref:
                        return ref, card_id_for_lookup, item, None
            return ref, card_id_for_lookup, None, None

        if not card_id_for_lookup:
            return "", "", None, "Checklist name lookup requires a card context."

        checklists = await self.client.get_card_checklists(
            api_key=api_key, token=token, card_id=card_id_for_lookup
        )
        item, err = self._match_named_item(checklists, ref)
        if err:
            return "", "", None, err
        return str(item.get("id") or ""), card_id_for_lookup, item, None

    async def _resolve_checklist_item_ref(
        self,
        event: AstrMessageEvent,
        api_key: str,
        token: str,
        item_ref: str,
        *,
        checklist_ref: str = "",
        card_ref: str = "",
        parent_resource: str = "",
        parent_id_or_name: str = "",
    ) -> tuple[str, str, str, dict | None, str | None]:
        ref = (item_ref or "").strip()
        if not ref:
            return "", "", "", None, "Checklist item id or name is required."

        norm_parent = self._normalize_resource(parent_resource)
        checklist_id = ""
        checklist = None
        card_id = ""

        if norm_parent == "checklist" and parent_id_or_name:
            checklist_id, card_id, checklist, err = await self._resolve_checklist_ref(
                event,
                api_key,
                token,
                parent_id_or_name,
                card_ref=card_ref,
            )
            if err or not checklist_id:
                return "", "", "", None, err or "Checklist not found."
        elif checklist_ref:
            checklist_id, card_id, checklist, err = await self._resolve_checklist_ref(
                event,
                api_key,
                token,
                checklist_ref,
                card_ref=card_ref,
            )
            if err or not checklist_id:
                return "", "", "", None, err or "Checklist not found."
        else:
            return (
                "",
                "",
                "",
                None,
                "Checklist item operations require checklist_id_or_name (via parent or fields).",
            )

        if checklist is None and checklist_id:
            checklist = await self.client.get_checklist(
                api_key=api_key, token=token, checklist_id=checklist_id
            )
        if not card_id and checklist:
            card_id = str(checklist.get("idCard") or "")

        if self._looks_like_trello_id(ref):
            items = checklist.get("checkItems") or []
            for item in items:
                if str(item.get("id") or "") == ref:
                    return ref, checklist_id, card_id, item, None
            return ref, checklist_id, card_id, None, None

        items = checklist.get("checkItems") or []
        item, err = self._match_named_item(items, ref)
        if err:
            return "", "", "", None, err
        return str(item.get("id") or ""), checklist_id, card_id, item, None

    async def _resolve_parent_ids(
        self,
        event: AstrMessageEvent,
        api_key: str,
        token: str,
        *,
        parent_resource: str,
        parent_id_or_name: str,
    ) -> tuple[dict[str, str], str | None]:
        resource = self._normalize_resource(parent_resource)
        ref = (parent_id_or_name or "").strip()
        ids = {"board_id": "", "list_id": "", "card_id": "", "checklist_id": ""}
        if not resource and not ref:
            return ids, None
        if not resource:
            return (
                ids,
                "parent_resource is required when parent_id_or_name is provided.",
            )

        if resource == "board":
            board_id, _, err = await self._resolve_board_ref(event, api_key, token, ref)
            if err or not board_id:
                return ids, err or "Board not found."
            ids["board_id"] = board_id
            return ids, None
        if resource == "list":
            list_id, _, err = await self._resolve_list_ref(event, api_key, token, ref)
            if err or not list_id:
                return ids, err or "List not found."
            ids["list_id"] = list_id
            return ids, None
        if resource == "card":
            card_id, _, err = await self._resolve_card_with_optional_parent(
                event, api_key, token, ref
            )
            if err or not card_id:
                return ids, err or "Card not found."
            ids["card_id"] = card_id
            return ids, None
        if resource == "checklist":
            checklist_id, card_id, _, err = await self._resolve_checklist_ref(
                event, api_key, token, ref
            )
            if err or not checklist_id:
                return ids, err or "Checklist not found."
            ids["checklist_id"] = checklist_id
            ids["card_id"] = card_id
            return ids, None
        return ids, f"Unsupported parent_resource: {parent_resource}"

    @staticmethod
    def _bool_field(value: Any, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return bool(value)
        return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}

    @filter.command_group("trello")
    def trello(self):
        """Trello integration commands."""

    @filter.permission_type(filter.PermissionType.ADMIN)
    @trello.command("use-board")
    async def use_board(self, event: AstrMessageEvent, board_id: str = ""):
        """Set default board for current session. Admin only."""
        if not board_id:
            yield event.plain_result("Usage: /trello use-board <board_id|name>")
            return
        api_key, token = await self._get_credentials()
        if not api_key or not token:
            yield event.plain_result(
                "Trello credentials are not configured. Set trello_api_key and trello_token in plugin config."
            )
            return
        try:
            resolved_board_id, board, err = await self._resolve_board_ref(
                event, api_key, token, board_id
            )
        except TrelloAuthError:
            yield event.plain_result("Trello authentication failed. Check key/token.")
            return
        except TrelloApiError as exc:
            yield event.plain_result(f"Trello error: {exc}")
            return
        if err or not resolved_board_id:
            yield event.plain_result(err or "Board not found.")
            return

        await self._set_current_board(event, resolved_board_id)
        await self.put_kv_data(self._session_key(event, "card_id"), "")
        display = board.get("name") if board else resolved_board_id
        yield event.plain_result(
            f"Default board set for this session: {display} ({resolved_board_id})"
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @trello.command("use-list")
    async def use_list(self, event: AstrMessageEvent, list_id: str = ""):
        """Set default list for current session. Admin only."""
        if not list_id:
            yield event.plain_result("Usage: /trello use-list <list_id|name>")
            return
        api_key, token = await self._get_credentials()
        if not api_key or not token:
            yield event.plain_result(
                "Trello credentials are not configured. Set trello_api_key and trello_token in plugin config."
            )
            return
        try:
            resolved_list_id, list_item, err = await self._resolve_list_ref(
                event, api_key, token, list_id
            )
        except TrelloAuthError:
            yield event.plain_result("Trello authentication failed. Check key/token.")
            return
        except TrelloApiError as exc:
            yield event.plain_result(f"Trello error: {exc}")
            return
        if err or not resolved_list_id:
            yield event.plain_result(err or "List not found.")
            return

        await self._set_current_list(event, resolved_list_id)
        await self.put_kv_data(self._session_key(event, "card_id"), "")
        display = list_item.get("name") if list_item else resolved_list_id
        yield event.plain_result(
            f"Default list set for this session: {display} ({resolved_list_id})"
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @trello.command("use-done")
    async def use_done(self, event: AstrMessageEvent, list_id: str = ""):
        """Set default done list for current session. Admin only."""
        if not list_id:
            yield event.plain_result("Usage: /trello use-done <list_id>")
            return
        await self.put_kv_data(self._session_key(event, "done_list_id"), list_id)
        yield event.plain_result(f"Done list set for this session: {list_id}")

    @trello.command("scope")
    async def scope(self, event: AstrMessageEvent):
        """Show session scope for permission and board/list mapping."""
        chat_type = "private" if event.is_private_chat() else "group"
        board_id = await self._get_session_board_id(event)
        list_id = await self._get_session_list_id(event)
        card_id = await self._get_session_card_id(event)
        yield event.plain_result(
            f"session={event.unified_msg_origin}\nchat_type={chat_type}\nboard_id={board_id or '-'}\nlist_id={list_id or '-'}\ncard_id={card_id or '-'}"
        )

    @trello.command("help")
    async def help(self, event: AstrMessageEvent):
        """Show Trello command help."""
        lines = [
            "Trello commands:",
            "scope | boards | board-create <name> | <desc> | board-info [board_id|name] | board-archive [board_id]",
            "use-board <board_id|name> | lists [board_id|name] | list-create <name> or <board_id> | <name>",
            "list-rename <list_id> | <new_name> | list-archive [list_id] | use-list <list_id|name> | use-done <list_id>",
            "cards [list_id|name] | add <title> | <desc> | card <card_id|name> | edit <card_id> <name|desc|due|list> <value>",
            "move <card_id> <list_id> | archive <card_id> | delete <card_id> | comment <card_id> | <text>",
            "done <card_id> | find <keyword>",
            "checklists <card_id> | checklist-create <card_id> | <name> | checklist-add <checklist_id> | <item_name>",
            "checklist-check <card_id> <check_item_id> | checklist-uncheck <card_id> <check_item_id> | checklist-delete <checklist_id>",
        ]
        yield event.plain_result("\n".join(lines))

    @trello.command("boards")
    async def boards(self, event: AstrMessageEvent):
        """List boards available to the current token."""
        api_key, token = await self._get_credentials()
        if not api_key or not token:
            yield event.plain_result(
                "Trello credentials are not configured. Set trello_api_key and trello_token in plugin config."
            )
            return

        try:
            boards = await self.client.get_boards(api_key=api_key, token=token)
        except TrelloAuthError:
            yield event.plain_result("Trello authentication failed. Check key/token.")
            return
        except TrelloApiError as exc:
            yield event.plain_result(f"Trello error: {exc}")
            return

        if not boards:
            yield event.plain_result("No boards found.")
            return

        lines = ["Boards:"]
        for idx, board in enumerate(boards[:20], start=1):
            lines.append(f"{idx}. {board.get('name')} ({board.get('id')})")
        yield event.plain_result("\n".join(lines))

    @trello.command("board-create")
    async def board_create(self, event: AstrMessageEvent):
        """Create board. Usage: /trello board-create <name> | <description>"""
        api_key, token = await self._get_credentials()
        if not api_key or not token:
            yield event.plain_result(
                "Trello credentials are not configured. Set trello_api_key and trello_token in plugin config."
            )
            return

        name, desc = self._tail_pipe(event, "board-create")
        if not name and not desc:
            yield event.plain_result(
                "Usage: /trello board-create <name> | <description>"
            )
            return
        if not name:
            yield event.plain_result("Board name is required.")
            return

        try:
            board = await self.client.create_board(
                api_key=api_key,
                token=token,
                name=name,
                description=desc,
            )
        except TrelloAuthError:
            yield event.plain_result("Trello authentication failed. Check key/token.")
            return
        except TrelloApiError as exc:
            yield event.plain_result(f"Trello error: {exc}")
            return

        yield event.plain_result(
            f"Created board: {board.get('name')} ({board.get('id')})\n{board.get('url', '')}"
        )

    @trello.command("board-info")
    async def board_info(self, event: AstrMessageEvent, board_id: str = ""):
        """Show board details."""
        api_key, token = await self._get_credentials()
        if not api_key or not token:
            yield event.plain_result(
                "Trello credentials are not configured. Set trello_api_key and trello_token in plugin config."
            )
            return

        try:
            board_id, board_preview, err = await self._resolve_board_ref(
                event, api_key, token, board_id
            )
            if err or not board_id:
                yield event.plain_result(
                    err
                    or "Usage: /trello board-info <board_id|name> (or set /trello use-board first)"
                )
                return
            board = await self.client.get_board(
                api_key=api_key,
                token=token,
                board_id=board_id,
            )
        except TrelloAuthError:
            yield event.plain_result("Trello authentication failed. Check key/token.")
            return
        except TrelloApiError as exc:
            yield event.plain_result(f"Trello error: {exc}")
            return

        await self._set_current_board(event, board_id)
        if board_preview is None:
            await self.put_kv_data(self._session_key(event, "card_id"), "")

        lines = [
            f"Board: {board.get('name')} ({board.get('id')})",
            f"Closed: {board.get('closed')}",
            f"Last Activity: {board.get('dateLastActivity')}",
            f"URL: {board.get('url')}",
            f"Desc: {board.get('desc') or '-'}",
        ]
        yield event.plain_result("\n".join(lines))

    @trello.command("board-archive")
    async def board_archive(self, event: AstrMessageEvent, board_id: str = ""):
        """Archive board."""
        api_key, token = await self._get_credentials()
        if not api_key or not token:
            yield event.plain_result(
                "Trello credentials are not configured. Set trello_api_key and trello_token in plugin config."
            )
            return

        if not board_id:
            board_id = await self._get_session_board_id(event)
        if not board_id:
            yield event.plain_result(
                "Usage: /trello board-archive <board_id> (or set /trello use-board first)"
            )
            return

        try:
            board = await self.client.archive_board(
                api_key=api_key,
                token=token,
                board_id=board_id,
            )
        except TrelloAuthError:
            yield event.plain_result("Trello authentication failed. Check key/token.")
            return
        except TrelloApiError as exc:
            yield event.plain_result(f"Trello error: {exc}")
            return

        yield event.plain_result(
            f"Archived board: {board.get('name')} ({board.get('id')})"
        )

    @trello.command("lists")
    async def lists(self, event: AstrMessageEvent, board_id: str = ""):
        """List lists on a board."""
        api_key, token = await self._get_credentials()
        if not api_key or not token:
            yield event.plain_result(
                "Trello credentials are not configured. Set trello_api_key and trello_token in plugin config."
            )
            return

        try:
            board_id, board_item, err = await self._resolve_board_ref(
                event, api_key, token, board_id
            )
            if err or not board_id:
                yield event.plain_result(err or "Board not found.")
                return
            lists = await self.client.get_lists(
                api_key=api_key, token=token, board_id=board_id
            )
        except TrelloAuthError:
            yield event.plain_result("Trello authentication failed. Check key/token.")
            return
        except TrelloApiError as exc:
            yield event.plain_result(f"Trello error: {exc}")
            return

        await self._set_current_board(event, board_id)
        await self.put_kv_data(self._session_key(event, "card_id"), "")

        if not lists:
            yield event.plain_result("No lists found on this board.")
            return

        board_name = board_item.get("name") if board_item else board_id
        lines = [f"Lists on board {board_name} ({board_id}):"]
        for idx, list_item in enumerate(lists[:30], start=1):
            lines.append(f"{idx}. {list_item.get('name')} ({list_item.get('id')})")
        yield event.plain_result("\n".join(lines))

    @trello.command("list-create")
    async def list_create(self, event: AstrMessageEvent):
        """Create list. Usage: /trello list-create <name> or <board_id> | <name>"""
        api_key, token = await self._get_credentials()
        if not api_key or not token:
            yield event.plain_result(
                "Trello credentials are not configured. Set trello_api_key and trello_token in plugin config."
            )
            return

        content = self._tail(event, "list-create")
        if not content:
            yield event.plain_result(
                "Usage: /trello list-create <name> or /trello list-create <board_id> | <name>"
            )
            return

        board_id = ""
        list_name = ""
        if "|" in content:
            board_id, list_name = self._split_pipe(content)
        else:
            board_id = await self._get_session_board_id(event)
            list_name = content.strip()

        if not board_id:
            yield event.plain_result(
                "No board selected. Use /trello use-board <board_id> or provide <board_id> | <name>."
            )
            return
        if not list_name:
            yield event.plain_result("List name is required.")
            return

        try:
            list_item = await self.client.create_list(
                api_key=api_key,
                token=token,
                board_id=board_id,
                name=list_name,
            )
        except TrelloAuthError:
            yield event.plain_result("Trello authentication failed. Check key/token.")
            return
        except TrelloApiError as exc:
            yield event.plain_result(f"Trello error: {exc}")
            return

        yield event.plain_result(
            f"Created list: {list_item.get('name')} ({list_item.get('id')})"
        )

    @trello.command("list-rename")
    async def list_rename(self, event: AstrMessageEvent):
        """Rename list. Usage: /trello list-rename <list_id> | <new_name>"""
        api_key, token = await self._get_credentials()
        if not api_key or not token:
            yield event.plain_result(
                "Trello credentials are not configured. Set trello_api_key and trello_token in plugin config."
            )
            return

        list_id, new_name = self._tail_pipe(event, "list-rename")
        if not list_id or not new_name:
            yield event.plain_result(
                "Usage: /trello list-rename <list_id> | <new_name>"
            )
            return

        try:
            list_item = await self.client.rename_list(
                api_key=api_key,
                token=token,
                list_id=list_id,
                name=new_name,
            )
        except TrelloAuthError:
            yield event.plain_result("Trello authentication failed. Check key/token.")
            return
        except TrelloApiError as exc:
            yield event.plain_result(f"Trello error: {exc}")
            return

        yield event.plain_result(
            f"Renamed list: {list_item.get('name')} ({list_item.get('id')})"
        )

    @trello.command("list-archive")
    async def list_archive(self, event: AstrMessageEvent, list_id: str = ""):
        """Archive list."""
        api_key, token = await self._get_credentials()
        if not api_key or not token:
            yield event.plain_result(
                "Trello credentials are not configured. Set trello_api_key and trello_token in plugin config."
            )
            return

        if not list_id:
            list_id = await self._get_session_list_id(event)
        if not list_id:
            yield event.plain_result(
                "Usage: /trello list-archive <list_id> (or set /trello use-list first)"
            )
            return

        try:
            list_item = await self.client.archive_list(
                api_key=api_key,
                token=token,
                list_id=list_id,
            )
        except TrelloAuthError:
            yield event.plain_result("Trello authentication failed. Check key/token.")
            return
        except TrelloApiError as exc:
            yield event.plain_result(f"Trello error: {exc}")
            return

        yield event.plain_result(
            f"Archived list: {list_item.get('name')} ({list_item.get('id')})"
        )

    @trello.command("cards")
    async def cards(self, event: AstrMessageEvent, list_id: str = ""):
        """List cards on a list."""
        api_key, token = await self._get_credentials()
        if not api_key or not token:
            yield event.plain_result(
                "Trello credentials are not configured. Set trello_api_key and trello_token in plugin config."
            )
            return

        try:
            list_id, list_item, err = await self._resolve_list_ref(
                event, api_key, token, list_id
            )
            if err or not list_id:
                yield event.plain_result(err or "List not found.")
                return
            cards = await self.client.get_list_cards(
                api_key=api_key,
                token=token,
                list_id=list_id,
                limit=30,
            )
        except TrelloAuthError:
            yield event.plain_result("Trello authentication failed. Check key/token.")
            return
        except TrelloApiError as exc:
            yield event.plain_result(f"Trello error: {exc}")
            return

        await self._set_current_list(event, list_id)
        await self.put_kv_data(self._session_key(event, "card_id"), "")

        if not cards:
            yield event.plain_result("No cards found on this list.")
            return

        list_name = list_item.get("name") if list_item else list_id
        lines = [f"Cards on list {list_name} ({list_id}):"]
        for idx, card in enumerate(cards, start=1):
            lines.append(f"{idx}. {card.get('name')} ({card.get('id')})")
            if card.get("due"):
                lines.append(
                    f"   due={card.get('due')} complete={bool(card.get('dueComplete'))}"
                )
        yield event.plain_result("\n".join(lines))

    @trello.command("add")
    async def add(self, event: AstrMessageEvent):
        """Create card in default list. Format: /trello add <title> | <description>"""
        api_key, token = await self._get_credentials()
        if not api_key or not token:
            yield event.plain_result(
                "Trello credentials are not configured. Set trello_api_key and trello_token in plugin config."
            )
            return

        list_id = await self._get_session_list_id(event)
        if not list_id:
            yield event.plain_result(
                "No default list selected. Use /trello use-list <list_id> first."
            )
            return

        title, desc = self._tail_pipe(event, "add")
        if not title and not desc:
            yield event.plain_result("Usage: /trello add <title> | <description>")
            return

        if not title:
            yield event.plain_result("Card title is required.")
            return

        try:
            card = await self.client.create_card(
                api_key=api_key,
                token=token,
                list_id=list_id,
                title=title,
                description=desc,
            )
        except TrelloAuthError:
            yield event.plain_result("Trello authentication failed. Check key/token.")
            return
        except TrelloApiError as exc:
            yield event.plain_result(f"Trello error: {exc}")
            return

        yield event.plain_result(
            f"Created card: {card.get('name')} ({card.get('id')})\n{card.get('url', '')}"
        )

    @trello.command("card")
    async def card(self, event: AstrMessageEvent, card_id: str = ""):
        """Show card details."""
        api_key, token = await self._get_credentials()
        if not api_key or not token:
            yield event.plain_result(
                "Trello credentials are not configured. Set trello_api_key and trello_token in plugin config."
            )
            return

        try:
            card_id, card_preview, err = await self._resolve_card_ref(
                event, api_key, token, card_id
            )
            if err or not card_id:
                yield event.plain_result(err or "Usage: /trello card <card_id|name>")
                return
            card = await self.client.get_card(
                api_key=api_key,
                token=token,
                card_id=card_id,
            )
        except TrelloAuthError:
            yield event.plain_result("Trello authentication failed. Check key/token.")
            return
        except TrelloApiError as exc:
            yield event.plain_result(f"Trello error: {exc}")
            return

        await self._set_current_card(event, card_id)
        if card.get("idBoard"):
            await self._set_current_board(event, str(card.get("idBoard")))
        if card.get("idList"):
            await self._set_current_list(event, str(card.get("idList")))

        lines = [
            f"Card: {card.get('name')} ({card.get('id')})",
            f"Board: {card.get('idBoard')}",
            f"List: {card.get('idList')}",
            f"Closed: {card.get('closed')}",
            f"Due: {card.get('due') or '-'} complete={bool(card.get('dueComplete'))}",
            f"Checklists: {len(card.get('idChecklists') or [])}",
            f"URL: {card.get('url')}",
            f"Desc: {card.get('desc') or '-'}",
        ]
        if card_preview and card_preview.get("name"):
            lines.append(f"Matched by name: {card_preview.get('name')}")
        yield event.plain_result("\n".join(lines))

    @trello.command("edit")
    async def edit(self, event: AstrMessageEvent):
        """Edit card. Usage: /trello edit <card_id> <name|desc|due|list> <value>"""
        api_key, token = await self._get_credentials()
        if not api_key or not token:
            yield event.plain_result(
                "Trello credentials are not configured. Set trello_api_key and trello_token in plugin config."
            )
            return

        content = self._tail(event, "edit")
        parts = content.split(maxsplit=2)
        if len(parts) < 3:
            yield event.plain_result(
                "Usage: /trello edit <card_id> <name|desc|due|list> <value>"
            )
            return

        card_id, field_name, field_value = parts[0], parts[1].lower(), parts[2]
        params: dict[str, str] = {}

        if field_name == "name":
            params["name"] = field_value
        elif field_name == "desc":
            params["desc"] = field_value
        elif field_name == "due":
            params["due"] = (
                "" if field_value.lower() in ("none", "null", "clear") else field_value
            )
        elif field_name == "list":
            params["idList"] = field_value
        else:
            yield event.plain_result(
                "Unknown field. Use one of: name, desc, due, list."
            )
            return

        try:
            card = await self.client.update_card(
                api_key=api_key,
                token=token,
                card_id=card_id,
                params=params,
            )
        except TrelloAuthError:
            yield event.plain_result("Trello authentication failed. Check key/token.")
            return
        except TrelloApiError as exc:
            yield event.plain_result(f"Trello error: {exc}")
            return

        yield event.plain_result(
            f"Updated card: {card.get('name')} ({card.get('id')})\n{card.get('url', '')}"
        )

    @trello.command("move")
    async def move(self, event: AstrMessageEvent, card_id: str = "", list_id: str = ""):
        """Move card to target list."""
        if not card_id or not list_id:
            yield event.plain_result("Usage: /trello move <card_id> <list_id>")
            return

        api_key, token = await self._get_credentials()
        if not api_key or not token:
            yield event.plain_result(
                "Trello credentials are not configured. Set trello_api_key and trello_token in plugin config."
            )
            return

        try:
            card = await self.client.move_card(
                api_key=api_key, token=token, card_id=card_id, list_id=list_id
            )
        except TrelloAuthError:
            yield event.plain_result("Trello authentication failed. Check key/token.")
            return
        except TrelloApiError as exc:
            yield event.plain_result(f"Trello error: {exc}")
            return

        yield event.plain_result(
            f"Moved card: {card.get('name')} -> {list_id}\n{card.get('url', '')}"
        )

    @trello.command("archive")
    async def archive(self, event: AstrMessageEvent, card_id: str = ""):
        """Archive card."""
        if not card_id:
            yield event.plain_result("Usage: /trello archive <card_id>")
            return

        api_key, token = await self._get_credentials()
        if not api_key or not token:
            yield event.plain_result(
                "Trello credentials are not configured. Set trello_api_key and trello_token in plugin config."
            )
            return

        try:
            card = await self.client.archive_card(
                api_key=api_key,
                token=token,
                card_id=card_id,
            )
        except TrelloAuthError:
            yield event.plain_result("Trello authentication failed. Check key/token.")
            return
        except TrelloApiError as exc:
            yield event.plain_result(f"Trello error: {exc}")
            return

        yield event.plain_result(
            f"Archived card: {card.get('name')} ({card.get('id')})"
        )

    @trello.command("delete")
    async def delete(self, event: AstrMessageEvent, card_id: str = ""):
        """Delete card."""
        if not card_id:
            yield event.plain_result("Usage: /trello delete <card_id>")
            return

        api_key, token = await self._get_credentials()
        if not api_key or not token:
            yield event.plain_result(
                "Trello credentials are not configured. Set trello_api_key and trello_token in plugin config."
            )
            return

        try:
            await self.client.delete_card(
                api_key=api_key,
                token=token,
                card_id=card_id,
            )
        except TrelloAuthError:
            yield event.plain_result("Trello authentication failed. Check key/token.")
            return
        except TrelloApiError as exc:
            yield event.plain_result(f"Trello error: {exc}")
            return

        yield event.plain_result(f"Deleted card: {card_id}")

    @trello.command("comment")
    async def comment(self, event: AstrMessageEvent):
        """Add comment. Usage: /trello comment <card_id> | <text>"""
        api_key, token = await self._get_credentials()
        if not api_key or not token:
            yield event.plain_result(
                "Trello credentials are not configured. Set trello_api_key and trello_token in plugin config."
            )
            return

        card_id, text = self._tail_pipe(event, "comment")
        if not card_id or not text:
            yield event.plain_result("Usage: /trello comment <card_id> | <text>")
            return

        try:
            action = await self.client.add_comment(
                api_key=api_key,
                token=token,
                card_id=card_id,
                text=text,
            )
        except TrelloAuthError:
            yield event.plain_result("Trello authentication failed. Check key/token.")
            return
        except TrelloApiError as exc:
            yield event.plain_result(f"Trello error: {exc}")
            return

        yield event.plain_result(
            f"Comment added. action_id={action.get('id')} card_id={card_id}"
        )

    @trello.command("done")
    async def done(self, event: AstrMessageEvent, card_id: str = ""):
        """Move card to configured done list."""
        if not card_id:
            yield event.plain_result("Usage: /trello done <card_id>")
            return

        done_list_id = await self._get_session_done_list_id(event)
        if not done_list_id:
            yield event.plain_result(
                "No done list configured. Use /trello use-done <list_id> first."
            )
            return

        api_key, token = await self._get_credentials()
        if not api_key or not token:
            yield event.plain_result(
                "Trello credentials are not configured. Set trello_api_key and trello_token in plugin config."
            )
            return

        try:
            card = await self.client.move_card(
                api_key=api_key,
                token=token,
                card_id=card_id,
                list_id=done_list_id,
            )
        except TrelloAuthError:
            yield event.plain_result("Trello authentication failed. Check key/token.")
            return
        except TrelloApiError as exc:
            yield event.plain_result(f"Trello error: {exc}")
            return

        yield event.plain_result(
            f"Moved card to done: {card.get('name')} ({card.get('id')})"
        )

    @trello.command("find")
    async def find(self, event: AstrMessageEvent):
        """Search cards. Usage: /trello find <keyword>"""
        api_key, token = await self._get_credentials()
        if not api_key or not token:
            yield event.plain_result(
                "Trello credentials are not configured. Set trello_api_key and trello_token in plugin config."
            )
            return

        board_id = await self._get_session_board_id(event)
        if not board_id:
            yield event.plain_result(
                "No default board selected. Use /trello use-board <board_id> first."
            )
            return

        keyword = self._tail(event, "find")
        if not keyword:
            yield event.plain_result("Usage: /trello find <keyword>")
            return

        try:
            cards = await self.client.search_cards(
                api_key=api_key,
                token=token,
                board_id=board_id,
                keyword=keyword,
                limit=10,
            )
        except TrelloAuthError:
            yield event.plain_result("Trello authentication failed. Check key/token.")
            return
        except TrelloApiError as exc:
            yield event.plain_result(f"Trello error: {exc}")
            return

        if not cards:
            yield event.plain_result("No cards matched this keyword.")
            return

        lines = [f"Search results for '{keyword}':"]
        for idx, card in enumerate(cards, start=1):
            lines.append(f"{idx}. {card.get('name')} ({card.get('id')})")
            if card.get("url"):
                lines.append(f"   {card.get('url')}")
        yield event.plain_result("\n".join(lines))

    @trello.command("checklists")
    async def checklists(self, event: AstrMessageEvent, card_id: str = ""):
        """List checklists on a card."""
        api_key, token = await self._get_credentials()
        if not api_key or not token:
            yield event.plain_result(
                "Trello credentials are not configured. Set trello_api_key and trello_token in plugin config."
            )
            return

        if not card_id:
            yield event.plain_result("Usage: /trello checklists <card_id>")
            return

        try:
            checklists = await self.client.get_card_checklists(
                api_key=api_key,
                token=token,
                card_id=card_id,
            )
        except TrelloAuthError:
            yield event.plain_result("Trello authentication failed. Check key/token.")
            return
        except TrelloApiError as exc:
            yield event.plain_result(f"Trello error: {exc}")
            return

        if not checklists:
            yield event.plain_result("No checklists found on this card.")
            return

        lines = [f"Checklists on card {card_id}:"]
        for idx, checklist in enumerate(checklists, start=1):
            lines.append(
                f"{idx}. {checklist.get('name')} ({checklist.get('id')}) items={len(checklist.get('checkItems') or [])}"
            )
            for item in (checklist.get("checkItems") or [])[:20]:
                mark = "[x]" if item.get("state") == "complete" else "[ ]"
                lines.append(f"   {mark} {item.get('name')} ({item.get('id')})")
        yield event.plain_result("\n".join(lines))

    @trello.command("checklist-create")
    async def checklist_create(self, event: AstrMessageEvent):
        """Create checklist. Usage: /trello checklist-create <card_id> | <name>"""
        api_key, token = await self._get_credentials()
        if not api_key or not token:
            yield event.plain_result(
                "Trello credentials are not configured. Set trello_api_key and trello_token in plugin config."
            )
            return

        card_id, checklist_name = self._tail_pipe(event, "checklist-create")
        if not card_id or not checklist_name:
            yield event.plain_result(
                "Usage: /trello checklist-create <card_id> | <name>"
            )
            return

        try:
            checklist = await self.client.create_checklist(
                api_key=api_key,
                token=token,
                card_id=card_id,
                name=checklist_name,
            )
        except TrelloAuthError:
            yield event.plain_result("Trello authentication failed. Check key/token.")
            return
        except TrelloApiError as exc:
            yield event.plain_result(f"Trello error: {exc}")
            return

        yield event.plain_result(
            f"Created checklist: {checklist.get('name')} ({checklist.get('id')})"
        )

    @trello.command("checklist-add")
    async def checklist_add(self, event: AstrMessageEvent):
        """Add check item. Usage: /trello checklist-add <checklist_id> | <item_name>"""
        api_key, token = await self._get_credentials()
        if not api_key or not token:
            yield event.plain_result(
                "Trello credentials are not configured. Set trello_api_key and trello_token in plugin config."
            )
            return

        checklist_id, item_name = self._tail_pipe(event, "checklist-add")
        if not checklist_id or not item_name:
            yield event.plain_result(
                "Usage: /trello checklist-add <checklist_id> | <item_name>"
            )
            return

        try:
            check_item = await self.client.add_check_item(
                api_key=api_key,
                token=token,
                checklist_id=checklist_id,
                name=item_name,
            )
        except TrelloAuthError:
            yield event.plain_result("Trello authentication failed. Check key/token.")
            return
        except TrelloApiError as exc:
            yield event.plain_result(f"Trello error: {exc}")
            return

        yield event.plain_result(
            f"Added checklist item: {check_item.get('name')} ({check_item.get('id')})"
        )

    @trello.command("checklist-check")
    async def checklist_check(
        self,
        event: AstrMessageEvent,
        card_id: str = "",
        check_item_id: str = "",
    ):
        """Mark check item complete."""
        if not card_id or not check_item_id:
            yield event.plain_result(
                "Usage: /trello checklist-check <card_id> <check_item_id>"
            )
            return

        api_key, token = await self._get_credentials()
        if not api_key or not token:
            yield event.plain_result(
                "Trello credentials are not configured. Set trello_api_key and trello_token in plugin config."
            )
            return

        try:
            await self.client.set_check_item_state(
                api_key=api_key,
                token=token,
                card_id=card_id,
                check_item_id=check_item_id,
                checked=True,
            )
        except TrelloAuthError:
            yield event.plain_result("Trello authentication failed. Check key/token.")
            return
        except TrelloApiError as exc:
            yield event.plain_result(f"Trello error: {exc}")
            return

        yield event.plain_result(f"Checklist item checked: {check_item_id}")

    @trello.command("checklist-uncheck")
    async def checklist_uncheck(
        self,
        event: AstrMessageEvent,
        card_id: str = "",
        check_item_id: str = "",
    ):
        """Mark check item incomplete."""
        if not card_id or not check_item_id:
            yield event.plain_result(
                "Usage: /trello checklist-uncheck <card_id> <check_item_id>"
            )
            return

        api_key, token = await self._get_credentials()
        if not api_key or not token:
            yield event.plain_result(
                "Trello credentials are not configured. Set trello_api_key and trello_token in plugin config."
            )
            return

        try:
            await self.client.set_check_item_state(
                api_key=api_key,
                token=token,
                card_id=card_id,
                check_item_id=check_item_id,
                checked=False,
            )
        except TrelloAuthError:
            yield event.plain_result("Trello authentication failed. Check key/token.")
            return
        except TrelloApiError as exc:
            yield event.plain_result(f"Trello error: {exc}")
            return

        yield event.plain_result(f"Checklist item unchecked: {check_item_id}")

    @trello.command("checklist-delete")
    async def checklist_delete(self, event: AstrMessageEvent, checklist_id: str = ""):
        """Delete checklist."""
        if not checklist_id:
            yield event.plain_result("Usage: /trello checklist-delete <checklist_id>")
            return

        api_key, token = await self._get_credentials()
        if not api_key or not token:
            yield event.plain_result(
                "Trello credentials are not configured. Set trello_api_key and trello_token in plugin config."
            )
            return

        try:
            await self.client.delete_checklist(
                api_key=api_key,
                token=token,
                checklist_id=checklist_id,
            )
        except TrelloAuthError:
            yield event.plain_result("Trello authentication failed. Check key/token.")
            return
        except TrelloApiError as exc:
            yield event.plain_result(f"Trello error: {exc}")
            return

        yield event.plain_result(f"Deleted checklist: {checklist_id}")

    @filter.llm_tool("trello_select")
    async def trello_select_tool(
        self,
        event: AstrMessageEvent,
        resource: str,
        id_or_name: str,
        parent_resource: str = "",
        parent_id_or_name: str = "",
    ) -> str:
        """Resolve a Trello resource by id or name and switch current session context.

        Args:
            resource(string): Resource type. One of board, list, card, checklist.
            id_or_name(string): Target resource id or name.
            parent_resource(string): Optional parent resource type for name resolution scope.
            parent_id_or_name(string): Optional parent resource id or name.
        """
        api_key, token, cred_err = await self._ensure_tool_credentials(event)
        if cred_err:
            return cred_err

        resource = self._normalize_resource(resource)
        try:
            if resource == "board":
                board_id, board, err = await self._resolve_board_ref(
                    event, api_key, token, id_or_name
                )
                if err or not board_id:
                    return err or "Board not found."
                await self._set_current_board(event, board_id)
                await self.put_kv_data(self._session_key(event, "card_id"), "")
                name = board.get("name") if board else ""
                return f"Selected board: {name or board_id} ({board_id})"

            if resource == "list":
                list_id, list_item, err = await self._resolve_list_ref(
                    event, api_key, token, id_or_name
                )
                if err or not list_id:
                    return err or "List not found."
                await self._set_current_list(event, list_id)
                await self.put_kv_data(self._session_key(event, "card_id"), "")
                name = list_item.get("name") if list_item else ""
                return f"Selected list: {name or list_id} ({list_id})"

            if resource == "card":
                card_id, _preview, err = await self._resolve_card_with_optional_parent(
                    event,
                    api_key,
                    token,
                    id_or_name,
                    parent_resource=parent_resource,
                    parent_id_or_name=parent_id_or_name,
                )
                if err or not card_id:
                    return err or "Card not found."
                card = await self.client.get_card(
                    api_key=api_key, token=token, card_id=card_id
                )
                await self._sync_context_from_card(event, card)
                return f"Selected card: {card.get('name')} ({card_id})"

            if resource == "checklist":
                (
                    checklist_id,
                    card_id,
                    checklist,
                    err,
                ) = await self._resolve_checklist_ref(
                    event,
                    api_key,
                    token,
                    id_or_name,
                    parent_resource=parent_resource,
                    parent_id_or_name=parent_id_or_name,
                )
                if err or not checklist_id:
                    return err or "Checklist not found."
                if checklist is None:
                    checklist = await self.client.get_checklist(
                        api_key=api_key, token=token, checklist_id=checklist_id
                    )
                if card_id:
                    card = await self.client.get_card(
                        api_key=api_key, token=token, card_id=card_id
                    )
                    await self._sync_context_from_card(event, card)
                return f"Selected checklist: {checklist.get('name')} ({checklist_id})"

            return "Unsupported resource for trello_select. Use board, list, card, checklist."
        except TrelloAuthError:
            return "Trello authentication failed. Check key/token."
        except TrelloApiError as exc:
            return f"Trello error: {exc}"

    @filter.llm_tool("trello_read")
    async def trello_read_tool(
        self,
        event: AstrMessageEvent,
        resource: str,
        mode: str,
        id_or_name: str = "",
        parent_resource: str = "",
        parent_id_or_name: str = "",
        limit: int = 20,
        switch_context: bool = True,
    ) -> str:
        """Read Trello resources (list or get) with id/name support and optional context switching.

        Args:
            resource(string): Resource type. One of board, list, card, checklist, checklist_item.
            mode(string): Read mode. One of list, get.
            id_or_name(string): Target resource id or name for get mode.
            parent_resource(string): Optional parent resource type for list mode or name resolution.
            parent_id_or_name(string): Optional parent resource id or name.
            limit(number): Max rows in list mode.
            switch_context(boolean): Whether to switch current session context after successful resolution.
        """
        api_key, token, cred_err = await self._ensure_tool_credentials(event)
        if cred_err:
            return cred_err

        resource = self._normalize_resource(resource)
        mode = self._normalize_mode(mode)
        limit = max(1, min(int(limit or 20), 100))

        try:
            if resource == "board" and mode == "list":
                boards = await self.client.get_boards(api_key=api_key, token=token)
                rows = [f"{b.get('name')} ({b.get('id')})" for b in boards[:limit]]
                return "Boards:\n" + ("\n".join(rows) if rows else "(empty)")

            if resource == "board" and mode == "get":
                board_id, _, err = await self._resolve_board_ref(
                    event, api_key, token, id_or_name
                )
                if err or not board_id:
                    return err or "Board not found."
                board = await self.client.get_board(
                    api_key=api_key, token=token, board_id=board_id
                )
                if switch_context:
                    await self._set_current_board(event, board_id)
                return (
                    f"Board: {board.get('name')} ({board.get('id')})\n"
                    f"Closed: {board.get('closed')}\n"
                    f"Last Activity: {board.get('dateLastActivity')}\n"
                    f"URL: {board.get('url')}\n"
                    f"Desc: {board.get('desc') or '-'}"
                )

            if resource == "list" and mode == "list":
                board_ref = (
                    parent_id_or_name
                    if self._normalize_resource(parent_resource) == "board"
                    else ""
                )
                board_id, board_item, err = await self._resolve_board_ref(
                    event, api_key, token, board_ref
                )
                if err or not board_id:
                    return (
                        err
                        or "Board not found. Set board context or pass parent_resource=board."
                    )
                lists = await self.client.get_lists(
                    api_key=api_key, token=token, board_id=board_id
                )
                if switch_context:
                    await self._set_current_board(event, board_id)
                rows = [f"{x.get('name')} ({x.get('id')})" for x in lists[:limit]]
                board_name = board_item.get("name") if board_item else board_id
                return f"Lists on {board_name} ({board_id}):\n" + (
                    "\n".join(rows) if rows else "(empty)"
                )

            if resource == "list" and mode == "get":
                list_id, _, err = await self._resolve_list_ref(
                    event, api_key, token, id_or_name
                )
                if err or not list_id:
                    return err or "List not found."
                list_data = await self.client.get_list(
                    api_key=api_key, token=token, list_id=list_id
                )
                if switch_context:
                    await self._set_current_list(event, list_id)
                    if list_data.get("idBoard"):
                        await self._set_current_board(
                            event, str(list_data.get("idBoard"))
                        )
                return (
                    f"List: {list_data.get('name')} ({list_data.get('id')})\n"
                    f"Board: {list_data.get('idBoard')}\n"
                    f"Closed: {list_data.get('closed')}\n"
                    f"Pos: {list_data.get('pos')}"
                )

            if resource == "card" and mode == "list":
                list_ref = (
                    parent_id_or_name
                    if self._normalize_resource(parent_resource) == "list"
                    else ""
                )
                list_id, list_item, err = await self._resolve_list_ref(
                    event, api_key, token, list_ref
                )
                if err or not list_id:
                    return (
                        err
                        or "List not found. Set list context or pass parent_resource=list."
                    )
                cards = await self.client.get_list_cards(
                    api_key=api_key, token=token, list_id=list_id, limit=limit
                )
                if switch_context:
                    await self._set_current_list(event, list_id)
                list_name = list_item.get("name") if list_item else list_id
                rows = []
                for c in cards:
                    line = f"{c.get('name')} ({c.get('id')})"
                    if c.get("due"):
                        line += f" due={c.get('due')}"
                    rows.append(line)
                return f"Cards on {list_name} ({list_id}):\n" + (
                    "\n".join(rows) if rows else "(empty)"
                )

            if resource == "card" and mode == "get":
                card_id, _, err = await self._resolve_card_with_optional_parent(
                    event,
                    api_key,
                    token,
                    id_or_name,
                    parent_resource=parent_resource,
                    parent_id_or_name=parent_id_or_name,
                )
                if err or not card_id:
                    return err or "Card not found."
                card = await self.client.get_card(
                    api_key=api_key, token=token, card_id=card_id
                )
                if switch_context:
                    await self._sync_context_from_card(event, card)
                return (
                    f"Card: {card.get('name')} ({card.get('id')})\n"
                    f"Board: {card.get('idBoard')}\n"
                    f"List: {card.get('idList')}\n"
                    f"Closed: {card.get('closed')}\n"
                    f"Due: {card.get('due') or '-'} complete={bool(card.get('dueComplete'))}\n"
                    f"URL: {card.get('url')}\n"
                    f"Desc: {card.get('desc') or '-'}"
                )

            if resource == "checklist" and mode == "list":
                card_ref = (
                    parent_id_or_name
                    if self._normalize_resource(parent_resource) == "card"
                    else ""
                )
                card_id, _, err = await self._resolve_card_with_optional_parent(
                    event, api_key, token, card_ref
                )
                if err or not card_id:
                    return (
                        err
                        or "Card not found. Set card context or pass parent_resource=card."
                    )
                checklists = await self.client.get_card_checklists(
                    api_key=api_key, token=token, card_id=card_id
                )
                if switch_context:
                    card = await self.client.get_card(
                        api_key=api_key, token=token, card_id=card_id
                    )
                    await self._sync_context_from_card(event, card)
                rows = [
                    f"{cl.get('name')} ({cl.get('id')}) items={len(cl.get('checkItems') or [])}"
                    for cl in checklists[:limit]
                ]
                return f"Checklists on card {card_id}:\n" + (
                    "\n".join(rows) if rows else "(empty)"
                )

            if resource == "checklist" and mode == "get":
                (
                    checklist_id,
                    card_id,
                    checklist,
                    err,
                ) = await self._resolve_checklist_ref(
                    event,
                    api_key,
                    token,
                    id_or_name,
                    parent_resource=parent_resource,
                    parent_id_or_name=parent_id_or_name,
                )
                if err or not checklist_id:
                    return err or "Checklist not found."
                if checklist is None:
                    checklist = await self.client.get_checklist(
                        api_key=api_key, token=token, checklist_id=checklist_id
                    )
                if switch_context and card_id:
                    card = await self.client.get_card(
                        api_key=api_key, token=token, card_id=card_id
                    )
                    await self._sync_context_from_card(event, card)
                rows = []
                for item in (checklist.get("checkItems") or [])[:limit]:
                    mark = "[x]" if item.get("state") == "complete" else "[ ]"
                    rows.append(f"{mark} {item.get('name')} ({item.get('id')})")
                return (
                    f"Checklist: {checklist.get('name')} ({checklist_id})\n"
                    f"Card: {card_id or checklist.get('idCard') or '-'}\n"
                    f"Items:\n" + ("\n".join(rows) if rows else "(empty)")
                )

            if resource == "checklist_item" and mode == "list":
                checklist_ref = (
                    parent_id_or_name
                    if self._normalize_resource(parent_resource) == "checklist"
                    else ""
                )
                if not checklist_ref:
                    return "Checklist item list requires parent_resource=checklist and parent_id_or_name."
                (
                    checklist_id,
                    _card_id,
                    checklist,
                    err,
                ) = await self._resolve_checklist_ref(
                    event, api_key, token, checklist_ref
                )
                if err or not checklist_id:
                    return err or "Checklist not found."
                if checklist is None:
                    checklist = await self.client.get_checklist(
                        api_key=api_key, token=token, checklist_id=checklist_id
                    )
                rows = []
                for item in (checklist.get("checkItems") or [])[:limit]:
                    rows.append(
                        f"{item.get('name')} ({item.get('id')}) state={item.get('state')}"
                    )
                return (
                    f"Checklist items in {checklist.get('name')} ({checklist_id}):\n"
                    + ("\n".join(rows) if rows else "(empty)")
                )

            if resource == "checklist_item" and mode == "get":
                checklist_ref = (
                    parent_id_or_name
                    if self._normalize_resource(parent_resource) == "checklist"
                    else ""
                )
                (
                    item_id,
                    checklist_id,
                    card_id,
                    item,
                    err,
                ) = await self._resolve_checklist_item_ref(
                    event,
                    api_key,
                    token,
                    id_or_name,
                    checklist_ref=checklist_ref,
                )
                if err or not item_id:
                    return err or "Checklist item not found."
                return (
                    f"Checklist Item: {(item or {}).get('name') or id_or_name} ({item_id})\n"
                    f"Checklist: {checklist_id}\n"
                    f"Card: {card_id or '-'}\n"
                    f"State: {(item or {}).get('state') or '-'}"
                )

            return "Unsupported trello_read combination. Use resource in {board,list,card,checklist,checklist_item} and mode in {list,get}."
        except TrelloAuthError:
            return "Trello authentication failed. Check key/token."
        except TrelloApiError as exc:
            return f"Trello error: {exc}"
        except Exception as exc:
            return f"trello_read input error: {exc}"

    @filter.llm_tool("trello_write")
    async def trello_write_tool(
        self,
        event: AstrMessageEvent,
        resource: str,
        action: str,
        id_or_name: str = "",
        parent_resource: str = "",
        parent_id_or_name: str = "",
        fields: dict | None = None,
        confirm: bool = False,
        switch_context: bool = True,
    ) -> str:
        """Create, update, or delete Trello resources with id/name support.

        Args:
            resource(string): Resource type. One of board, list, card, checklist, checklist_item.
            action(string): Mutation action. One of create, update, delete.
            id_or_name(string): Target resource id or name for update/delete.
            parent_resource(string): Optional parent resource type for create or name resolution.
            parent_id_or_name(string): Optional parent resource id or name.
            fields(object): Mutation fields. Example keys: name, desc, due, list_id, checked, checklist_id, card_id.
            confirm(boolean): Must be true for delete operations.
            switch_context(boolean): Whether to switch current session context after success.
        """
        api_key, token, cred_err = await self._ensure_tool_credentials(event)
        if cred_err:
            return cred_err

        resource = self._normalize_resource(resource)
        action = self._normalize_mode(action)
        fields = fields or {}

        try:
            if action not in {"create", "update", "delete"}:
                return "Unsupported action. Use create, update, or delete."

            if action == "delete" and not confirm:
                return "Delete operations require confirm=true."

            if resource == "board":
                if action == "create":
                    name = str(fields.get("name") or "").strip()
                    desc = str(
                        fields.get("desc") or fields.get("description") or ""
                    ).strip()
                    if not name:
                        return "board.create requires fields.name."
                    board = await self.client.create_board(
                        api_key=api_key, token=token, name=name, description=desc
                    )
                    if switch_context:
                        await self._set_current_board(event, str(board.get("id") or ""))
                    return f"Created board: {board.get('name')} ({board.get('id')})"
                board_id, _, err = await self._resolve_board_ref(
                    event, api_key, token, id_or_name
                )
                if err or not board_id:
                    return err or "Board not found."
                if action == "update":
                    params: dict[str, Any] = {}
                    if "name" in fields:
                        params["name"] = str(fields.get("name") or "")
                    if "desc" in fields or "description" in fields:
                        params["desc"] = str(
                            fields.get("desc") or fields.get("description") or ""
                        )
                    if "closed" in fields:
                        params["closed"] = (
                            "true"
                            if self._bool_field(fields.get("closed"))
                            else "false"
                        )
                    if not params:
                        return "board.update requires at least one field in {name, desc, closed}."
                    board = await self.client.update_board(
                        api_key=api_key, token=token, board_id=board_id, params=params
                    )
                    if switch_context:
                        await self._set_current_board(event, board_id)
                    return f"Updated board: {board.get('name')} ({board.get('id')})"
                board = await self.client.archive_board(
                    api_key=api_key, token=token, board_id=board_id
                )
                return f"Archived board: {board.get('name')} ({board.get('id')})"

            if resource == "list":
                if action == "create":
                    name = str(fields.get("name") or "").strip()
                    if not name:
                        return "list.create requires fields.name."
                    board_ref = (
                        parent_id_or_name
                        if self._normalize_resource(parent_resource) == "board"
                        else str(fields.get("board_id") or "")
                    )
                    board_id, _, err = await self._resolve_board_ref(
                        event, api_key, token, board_ref
                    )
                    if err or not board_id:
                        return err or "Board not found for list.create."
                    list_item = await self.client.create_list(
                        api_key=api_key, token=token, board_id=board_id, name=name
                    )
                    if switch_context:
                        await self._set_current_board(event, board_id)
                        await self._set_current_list(
                            event, str(list_item.get("id") or "")
                        )
                    return (
                        f"Created list: {list_item.get('name')} ({list_item.get('id')})"
                    )
                list_id, _, err = await self._resolve_list_ref(
                    event, api_key, token, id_or_name
                )
                if err or not list_id:
                    return err or "List not found."
                if action == "update":
                    name = str(fields.get("name") or "").strip()
                    if not name:
                        return "list.update currently supports fields.name."
                    list_item = await self.client.rename_list(
                        api_key=api_key, token=token, list_id=list_id, name=name
                    )
                    if switch_context:
                        await self._set_current_list(event, list_id)
                    return (
                        f"Updated list: {list_item.get('name')} ({list_item.get('id')})"
                    )
                list_item = await self.client.archive_list(
                    api_key=api_key, token=token, list_id=list_id
                )
                return f"Archived list: {list_item.get('name')} ({list_item.get('id')})"

            if resource == "card":
                if action == "create":
                    title = str(fields.get("name") or fields.get("title") or "").strip()
                    desc = str(
                        fields.get("desc") or fields.get("description") or ""
                    ).strip()
                    if not title:
                        return "card.create requires fields.name (or fields.title)."
                    list_ref = (
                        parent_id_or_name
                        if self._normalize_resource(parent_resource) == "list"
                        else str(fields.get("list_id") or "")
                    )
                    list_id, _, err = await self._resolve_list_ref(
                        event, api_key, token, list_ref
                    )
                    if err or not list_id:
                        return err or "List not found for card.create."
                    card = await self.client.create_card(
                        api_key=api_key,
                        token=token,
                        list_id=list_id,
                        title=title,
                        description=desc,
                    )
                    if switch_context:
                        await self._set_current_list(event, list_id)
                        await self._set_current_card(event, str(card.get("id") or ""))
                    return f"Created card: {card.get('name')} ({card.get('id')})"
                card_id, _, err = await self._resolve_card_with_optional_parent(
                    event,
                    api_key,
                    token,
                    id_or_name,
                    parent_resource=parent_resource,
                    parent_id_or_name=parent_id_or_name,
                )
                if err or not card_id:
                    return err or "Card not found."
                if action == "update":
                    params: dict[str, Any] = {}
                    if "name" in fields:
                        params["name"] = str(fields.get("name") or "")
                    if "desc" in fields or "description" in fields:
                        params["desc"] = str(
                            fields.get("desc") or fields.get("description") or ""
                        )
                    if "due" in fields:
                        due = fields.get("due")
                        params["due"] = "" if due is None else str(due)
                    if "list_id" in fields:
                        params["idList"] = str(fields.get("list_id") or "")
                    if "closed" in fields:
                        params["closed"] = (
                            "true"
                            if self._bool_field(fields.get("closed"))
                            else "false"
                        )
                    if not params:
                        return "card.update requires one of fields {name, desc, due, list_id, closed}."
                    card = await self.client.update_card(
                        api_key=api_key, token=token, card_id=card_id, params=params
                    )
                    if switch_context:
                        await self._sync_context_from_card(event, card)
                    return f"Updated card: {card.get('name')} ({card.get('id')})"
                await self.client.delete_card(
                    api_key=api_key, token=token, card_id=card_id
                )
                return f"Deleted card: {card_id}"

            if resource == "checklist":
                if action == "create":
                    name = str(fields.get("name") or "").strip()
                    if not name:
                        return "checklist.create requires fields.name."
                    card_ref = (
                        parent_id_or_name
                        if self._normalize_resource(parent_resource) == "card"
                        else str(fields.get("card_id") or "")
                    )
                    card_id, _, err = await self._resolve_card_with_optional_parent(
                        event, api_key, token, card_ref
                    )
                    if err or not card_id:
                        return err or "Card not found for checklist.create."
                    checklist = await self.client.create_checklist(
                        api_key=api_key, token=token, card_id=card_id, name=name
                    )
                    if switch_context:
                        card = await self.client.get_card(
                            api_key=api_key, token=token, card_id=card_id
                        )
                        await self._sync_context_from_card(event, card)
                    return f"Created checklist: {checklist.get('name')} ({checklist.get('id')})"
                checklist_id, card_id, _, err = await self._resolve_checklist_ref(
                    event,
                    api_key,
                    token,
                    id_or_name,
                    parent_resource=parent_resource,
                    parent_id_or_name=parent_id_or_name,
                )
                if err or not checklist_id:
                    return err or "Checklist not found."
                if action == "update":
                    name = str(fields.get("name") or "").strip()
                    if not name:
                        return "checklist.update currently supports fields.name."
                    checklist = await self.client.update_checklist(
                        api_key=api_key,
                        token=token,
                        checklist_id=checklist_id,
                        params={"name": name},
                    )
                    return f"Updated checklist: {checklist.get('name')} ({checklist.get('id')})"
                await self.client.delete_checklist(
                    api_key=api_key, token=token, checklist_id=checklist_id
                )
                return f"Deleted checklist: {checklist_id}"

            if resource == "checklist_item":
                checklist_ref = (
                    parent_id_or_name
                    if self._normalize_resource(parent_resource) == "checklist"
                    else str(fields.get("checklist_id") or "")
                )
                card_ref = str(fields.get("card_id") or "")
                if action == "create":
                    name = str(fields.get("name") or "").strip()
                    if not name:
                        return "checklist_item.create requires fields.name."
                    checklist_id, _card_id, _, err = await self._resolve_checklist_ref(
                        event, api_key, token, checklist_ref, card_ref=card_ref
                    )
                    if err or not checklist_id:
                        return err or "Checklist not found for checklist_item.create."
                    item = await self.client.add_check_item(
                        api_key=api_key,
                        token=token,
                        checklist_id=checklist_id,
                        name=name,
                    )
                    return (
                        f"Created checklist item: {item.get('name')} ({item.get('id')})"
                    )

                (
                    item_id,
                    checklist_id,
                    card_id,
                    _,
                    err,
                ) = await self._resolve_checklist_item_ref(
                    event,
                    api_key,
                    token,
                    id_or_name,
                    checklist_ref=checklist_ref,
                    card_ref=card_ref,
                    parent_resource=parent_resource,
                    parent_id_or_name=parent_id_or_name,
                )
                if err or not item_id:
                    return err or "Checklist item not found."

                if action == "update":
                    params: dict[str, Any] = {}
                    if "name" in fields:
                        params["name"] = str(fields.get("name") or "")
                    if "checked" in fields:
                        params["state"] = (
                            "complete"
                            if self._bool_field(fields.get("checked"))
                            else "incomplete"
                        )
                    if not params:
                        return "checklist_item.update requires fields.name or fields.checked."
                    if not card_id:
                        return "checklist_item.update requires card context (fields.card_id or resolvable checklist idCard)."
                    await self.client.update_check_item(
                        api_key=api_key,
                        token=token,
                        card_id=card_id,
                        check_item_id=item_id,
                        params=params,
                    )
                    return f"Updated checklist item: {item_id}"

                await self.client.delete_check_item(
                    api_key=api_key,
                    token=token,
                    checklist_id=checklist_id,
                    check_item_id=item_id,
                )
                return f"Deleted checklist item: {item_id}"

            return "Unsupported resource. Use board, list, card, checklist, or checklist_item."
        except TrelloAuthError:
            return "Trello authentication failed. Check key/token."
        except TrelloApiError as exc:
            return f"Trello error: {exc}"
        except Exception as exc:
            return f"trello_write input error: {exc}"
