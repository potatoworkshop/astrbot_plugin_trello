import asyncio
import unittest

import aiohttp

from client import TrelloApiError, TrelloClient


class _ResponseCtx:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _RaiseOnEnterCtx:
    def __init__(self, exc):
        self._exc = exc

    async def __aenter__(self):
        raise self._exc

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeResponse:
    def __init__(self, *, status=200, json_data=None, text_data="", content_length=1):
        self.status = status
        self._json_data = json_data
        self._text_data = text_data
        self.content_length = content_length

    async def json(self):
        return self._json_data

    async def text(self):
        return self._text_data


class _FakeSession:
    def __init__(self, ctx):
        self._ctx = ctx
        self.closed = False
        self.last_request = None

    def request(self, *, method, url, params):
        self.last_request = {
            "method": method,
            "url": url,
            "params": params,
        }
        return self._ctx

    async def close(self):
        self.closed = True


class TrelloClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_boards_filters_closed_items(self):
        client = TrelloClient()
        session = _FakeSession(
            _ResponseCtx(
                _FakeResponse(
                    status=200,
                    json_data=[
                        {"id": "1", "name": "Open Board", "closed": False},
                        {"id": "2", "name": "Closed Board", "closed": True},
                    ],
                )
            )
        )
        client._session = session

        boards = await client.get_boards(api_key="k", token="t")

        self.assertEqual(1, len(boards))
        self.assertEqual("1", boards[0]["id"])
        self.assertEqual(
            "https://api.trello.com/1/members/me/boards", session.last_request["url"]
        )
        self.assertIn("key", session.last_request["params"])
        self.assertIn("token", session.last_request["params"])

    async def test_get_boards_raises_when_response_is_not_list(self):
        client = TrelloClient()
        client._session = _FakeSession(
            _ResponseCtx(_FakeResponse(status=200, json_data={"unexpected": "shape"}))
        )

        with self.assertRaises(TrelloApiError):
            await client.get_boards(api_key="k", token="t")

    async def test_search_cards_raises_when_cards_field_is_not_list(self):
        client = TrelloClient()
        client._session = _FakeSession(
            _ResponseCtx(_FakeResponse(status=200, json_data={"cards": "bad-shape"}))
        )

        with self.assertRaises(TrelloApiError):
            await client.search_cards(
                api_key="k",
                token="t",
                board_id="b1",
                keyword="kw",
            )

    async def test_request_wraps_timeout_error(self):
        client = TrelloClient()
        client._session = _FakeSession(_RaiseOnEnterCtx(asyncio.TimeoutError()))

        with self.assertRaises(TrelloApiError) as ctx:
            await client._request(
                "GET",
                "/members/me/boards",
                api_key="k",
                token="t",
            )
        self.assertIn("Network error", str(ctx.exception))

    async def test_request_wraps_client_error(self):
        client = TrelloClient()
        client._session = _FakeSession(_RaiseOnEnterCtx(aiohttp.ClientError("boom")))

        with self.assertRaises(TrelloApiError) as ctx:
            await client._request(
                "GET",
                "/members/me/boards",
                api_key="k",
                token="t",
            )
        self.assertIn("Network error", str(ctx.exception))

    async def test_close_closes_reused_session(self):
        client = TrelloClient()
        session = _FakeSession(
            _ResponseCtx(_FakeResponse(status=200, json_data=[], content_length=1))
        )
        client._session = session

        await client.close()

        self.assertTrue(session.closed)

