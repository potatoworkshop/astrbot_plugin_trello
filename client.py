from __future__ import annotations

import asyncio
from typing import Any

import aiohttp


class TrelloApiError(Exception):
    pass


class TrelloAuthError(TrelloApiError):
    pass


class TrelloClient:
    def __init__(self, base_url: str = "https://api.trello.com/1", timeout: int = 20):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(timeout=timeout, trust_env=True)
        return self._session

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()

    @staticmethod
    def _ensure_dict(data: Any, endpoint: str) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise TrelloApiError(
                f"Unexpected response type for {endpoint}: {type(data).__name__}"
            )
        return data

    @staticmethod
    def _ensure_list_of_dict(data: Any, endpoint: str) -> list[dict[str, Any]]:
        if not isinstance(data, list):
            raise TrelloApiError(
                f"Unexpected response type for {endpoint}: {type(data).__name__}"
            )
        if not all(isinstance(item, dict) for item in data):
            raise TrelloApiError(
                f"Unexpected item type in response for {endpoint}: list contains non-object entries."
            )
        return data

    async def _request(
        self,
        method: str,
        path: str,
        *,
        api_key: str,
        token: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        query = params.copy() if params else {}
        query["key"] = api_key
        query["token"] = token
        url = f"{self.base_url}/{path.lstrip('/')}"

        session = await self._get_session()
        try:
            async with session.request(method=method, url=url, params=query) as resp:
                if resp.status in (401, 403):
                    raise TrelloAuthError("Authentication failed.")
                if resp.status >= 400:
                    body = await resp.text()
                    raise TrelloApiError(f"HTTP {resp.status}: {body[:300]}")
                if resp.content_length == 0:
                    return {}
                try:
                    return await resp.json()
                except aiohttp.ContentTypeError:
                    return {"text": await resp.text()}
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise TrelloApiError(f"Network error: {exc}") from exc

    async def get_boards(self, *, api_key: str, token: str) -> list[dict[str, Any]]:
        data = await self._request(
            "GET",
            "/members/me/boards",
            api_key=api_key,
            token=token,
            params={"fields": "id,name,url,closed"},
        )
        data = self._ensure_list_of_dict(data, "/members/me/boards")
        return [item for item in data if not item.get("closed")]

    async def get_lists(
        self,
        *,
        api_key: str,
        token: str,
        board_id: str,
    ) -> list[dict[str, Any]]:
        data = await self._request(
            "GET",
            f"/boards/{board_id}/lists",
            api_key=api_key,
            token=token,
            params={"fields": "id,name,closed"},
        )
        data = self._ensure_list_of_dict(data, f"/boards/{board_id}/lists")
        return [item for item in data if not item.get("closed")]

    async def create_card(
        self,
        *,
        api_key: str,
        token: str,
        list_id: str,
        title: str,
        description: str = "",
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/cards",
            api_key=api_key,
            token=token,
            params={
                "idList": list_id,
                "name": title,
                "desc": description,
                "pos": "bottom",
            },
        )

    async def move_card(
        self,
        *,
        api_key: str,
        token: str,
        card_id: str,
        list_id: str,
    ) -> dict[str, Any]:
        return await self._request(
            "PUT",
            f"/cards/{card_id}",
            api_key=api_key,
            token=token,
            params={"idList": list_id},
        )

    async def search_cards(
        self,
        *,
        api_key: str,
        token: str,
        board_id: str,
        keyword: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        data = await self._request(
            "GET",
            "/search",
            api_key=api_key,
            token=token,
            params={
                "query": keyword,
                "idBoards": board_id,
                "modelTypes": "cards",
                "card_fields": "id,name,url,idList,closed",
                "cards_limit": max(1, min(limit, 50)),
            },
        )
        data = self._ensure_dict(data, "/search")
        cards = data.get("cards", [])
        cards = self._ensure_list_of_dict(cards, "/search.cards")
        return [item for item in cards if not item.get("closed")]

    async def create_board(
        self,
        *,
        api_key: str,
        token: str,
        name: str,
        description: str = "",
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/boards",
            api_key=api_key,
            token=token,
            params={"name": name, "desc": description},
        )

    async def update_board(
        self,
        *,
        api_key: str,
        token: str,
        board_id: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        return await self._request(
            "PUT",
            f"/boards/{board_id}",
            api_key=api_key,
            token=token,
            params=params,
        )

    async def get_board(
        self,
        *,
        api_key: str,
        token: str,
        board_id: str,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"/boards/{board_id}",
            api_key=api_key,
            token=token,
            params={"fields": "id,name,desc,url,closed,dateLastActivity"},
        )

    async def archive_board(
        self,
        *,
        api_key: str,
        token: str,
        board_id: str,
    ) -> dict[str, Any]:
        return await self._request(
            "PUT",
            f"/boards/{board_id}/closed",
            api_key=api_key,
            token=token,
            params={"value": "true"},
        )

    async def create_list(
        self,
        *,
        api_key: str,
        token: str,
        board_id: str,
        name: str,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/lists",
            api_key=api_key,
            token=token,
            params={"idBoard": board_id, "name": name, "pos": "bottom"},
        )

    async def get_list(
        self,
        *,
        api_key: str,
        token: str,
        list_id: str,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"/lists/{list_id}",
            api_key=api_key,
            token=token,
            params={"fields": "id,name,closed,idBoard,pos"},
        )

    async def rename_list(
        self,
        *,
        api_key: str,
        token: str,
        list_id: str,
        name: str,
    ) -> dict[str, Any]:
        return await self._request(
            "PUT",
            f"/lists/{list_id}",
            api_key=api_key,
            token=token,
            params={"name": name},
        )

    async def archive_list(
        self,
        *,
        api_key: str,
        token: str,
        list_id: str,
    ) -> dict[str, Any]:
        return await self._request(
            "PUT",
            f"/lists/{list_id}/closed",
            api_key=api_key,
            token=token,
            params={"value": "true"},
        )

    async def get_list_cards(
        self,
        *,
        api_key: str,
        token: str,
        list_id: str,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        data = await self._request(
            "GET",
            f"/lists/{list_id}/cards",
            api_key=api_key,
            token=token,
            params={
                "fields": "id,name,url,closed,idList,due,dueComplete",
                "limit": max(1, min(limit, 100)),
            },
        )
        data = self._ensure_list_of_dict(data, f"/lists/{list_id}/cards")
        return [item for item in data if not item.get("closed")]

    async def get_card(
        self,
        *,
        api_key: str,
        token: str,
        card_id: str,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"/cards/{card_id}",
            api_key=api_key,
            token=token,
            params={
                "fields": "id,name,desc,url,idBoard,idList,closed,due,dueComplete,dateLastActivity,idChecklists"
            },
        )

    async def update_card(
        self,
        *,
        api_key: str,
        token: str,
        card_id: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        return await self._request(
            "PUT",
            f"/cards/{card_id}",
            api_key=api_key,
            token=token,
            params=params,
        )

    async def archive_card(
        self,
        *,
        api_key: str,
        token: str,
        card_id: str,
    ) -> dict[str, Any]:
        return await self.update_card(
            api_key=api_key,
            token=token,
            card_id=card_id,
            params={"closed": "true"},
        )

    async def delete_card(
        self,
        *,
        api_key: str,
        token: str,
        card_id: str,
    ) -> dict[str, Any]:
        return await self._request(
            "DELETE",
            f"/cards/{card_id}",
            api_key=api_key,
            token=token,
        )

    async def add_comment(
        self,
        *,
        api_key: str,
        token: str,
        card_id: str,
        text: str,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"/cards/{card_id}/actions/comments",
            api_key=api_key,
            token=token,
            params={"text": text},
        )

    async def get_card_checklists(
        self,
        *,
        api_key: str,
        token: str,
        card_id: str,
    ) -> list[dict[str, Any]]:
        data = await self._request(
            "GET",
            f"/cards/{card_id}/checklists",
            api_key=api_key,
            token=token,
        )
        return self._ensure_list_of_dict(data, f"/cards/{card_id}/checklists")

    async def create_checklist(
        self,
        *,
        api_key: str,
        token: str,
        card_id: str,
        name: str,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/checklists",
            api_key=api_key,
            token=token,
            params={"idCard": card_id, "name": name},
        )

    async def delete_checklist(
        self,
        *,
        api_key: str,
        token: str,
        checklist_id: str,
    ) -> dict[str, Any]:
        return await self._request(
            "DELETE",
            f"/checklists/{checklist_id}",
            api_key=api_key,
            token=token,
        )

    async def get_checklist(
        self,
        *,
        api_key: str,
        token: str,
        checklist_id: str,
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"/checklists/{checklist_id}",
            api_key=api_key,
            token=token,
        )

    async def update_checklist(
        self,
        *,
        api_key: str,
        token: str,
        checklist_id: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        return await self._request(
            "PUT",
            f"/checklists/{checklist_id}",
            api_key=api_key,
            token=token,
            params=params,
        )

    async def add_check_item(
        self,
        *,
        api_key: str,
        token: str,
        checklist_id: str,
        name: str,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"/checklists/{checklist_id}/checkItems",
            api_key=api_key,
            token=token,
            params={"name": name, "pos": "bottom"},
        )

    async def set_check_item_state(
        self,
        *,
        api_key: str,
        token: str,
        card_id: str,
        check_item_id: str,
        checked: bool,
    ) -> dict[str, Any]:
        return await self._request(
            "PUT",
            f"/cards/{card_id}/checkItem/{check_item_id}",
            api_key=api_key,
            token=token,
            params={"state": "complete" if checked else "incomplete"},
        )

    async def update_check_item(
        self,
        *,
        api_key: str,
        token: str,
        card_id: str,
        check_item_id: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        return await self._request(
            "PUT",
            f"/cards/{card_id}/checkItem/{check_item_id}",
            api_key=api_key,
            token=token,
            params=params,
        )

    async def delete_check_item(
        self,
        *,
        api_key: str,
        token: str,
        checklist_id: str,
        check_item_id: str,
    ) -> dict[str, Any]:
        return await self._request(
            "DELETE",
            f"/checklists/{checklist_id}/checkItems/{check_item_id}",
            api_key=api_key,
            token=token,
        )
