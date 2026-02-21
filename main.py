import re

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

from .client import TrelloApiError, TrelloAuthError, TrelloClient


@register(
    "astrbot_plugin_trello_control",
    "Potatoworkshop",
    "Control Trello boards and cards with AstrBot commands.",
    "0.1.1",
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

    @filter.command_group("trello")
    def trello(self):
        """Trello integration commands."""

    @filter.permission_type(filter.PermissionType.ADMIN)
    @trello.command("use-board")
    async def use_board(self, event: AstrMessageEvent, board_id: str = ""):
        """Set default board for current session. Admin only."""
        if not board_id:
            yield event.plain_result("Usage: /trello use-board <board_id>")
            return
        await self.put_kv_data(self._session_key(event, "board_id"), board_id)
        yield event.plain_result(f"Default board set for this session: {board_id}")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @trello.command("use-list")
    async def use_list(self, event: AstrMessageEvent, list_id: str = ""):
        """Set default list for current session. Admin only."""
        if not list_id:
            yield event.plain_result("Usage: /trello use-list <list_id>")
            return
        await self.put_kv_data(self._session_key(event, "list_id"), list_id)
        yield event.plain_result(f"Default list set for this session: {list_id}")

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
        yield event.plain_result(
            f"session={event.unified_msg_origin}\nchat_type={chat_type}"
        )

    @trello.command("help")
    async def help(self, event: AstrMessageEvent):
        """Show Trello command help."""
        lines = [
            "Trello commands:",
            "scope | boards | board-create <name> | <desc> | board-info [board_id] | board-archive [board_id]",
            "use-board <board_id> | lists [board_id] | list-create <name> or <board_id> | <name>",
            "list-rename <list_id> | <new_name> | list-archive [list_id] | use-list <list_id> | use-done <list_id>",
            "cards [list_id] | add <title> | <desc> | card <card_id> | edit <card_id> <name|desc|due|list> <value>",
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

        if not board_id:
            board_id = await self._get_session_board_id(event)
        if not board_id:
            yield event.plain_result(
                "Usage: /trello board-info <board_id> (or set /trello use-board first)"
            )
            return

        try:
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

        if not board_id:
            board_id = await self._get_session_board_id(event)
        if not board_id:
            yield event.plain_result(
                "No board selected. Use /trello use-board <board_id> or pass board_id."
            )
            return

        try:
            lists = await self.client.get_lists(
                api_key=api_key, token=token, board_id=board_id
            )
        except TrelloAuthError:
            yield event.plain_result("Trello authentication failed. Check key/token.")
            return
        except TrelloApiError as exc:
            yield event.plain_result(f"Trello error: {exc}")
            return

        if not lists:
            yield event.plain_result("No lists found on this board.")
            return

        lines = [f"Lists on board {board_id}:"]
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

        if not list_id:
            list_id = await self._get_session_list_id(event)
        if not list_id:
            yield event.plain_result(
                "No list selected. Use /trello use-list <list_id> or pass list_id."
            )
            return

        try:
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

        if not cards:
            yield event.plain_result("No cards found on this list.")
            return

        lines = [f"Cards on list {list_id}:"]
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

        if not card_id:
            yield event.plain_result("Usage: /trello card <card_id>")
            return

        try:
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
