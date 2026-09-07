import pytest
import requests

from aardvark_jd import http_retry
from aardvark_jd.craft_client import CraftApiError, CraftClient

_API_URL = "https://connect.craft.do/links/abc123/api/v1"


@pytest.fixture(autouse=True)
def _no_retry_sleep(monkeypatch):
    """*run any retry loop without real backoff sleeps*"""
    monkeypatch.setattr(http_retry, "_sleep", lambda seconds: None)

_CONNECTION_RESPONSE = {
    "space": {"id": "space-1"},
    "urlTemplates": {"app": "craftdocs://open?spaceId=space-1&blockId={blockId}"},
}


class FakeResponse:
    def __init__(self, status_code=200, json_body=None, text=""):
        self.status_code = status_code
        self._json_body = json_body
        self.text = text
        self.content = b"1" if json_body is not None else b""
        self.ok = 200 <= status_code < 300

    def json(self):
        return self._json_body


def _deep_link(itemId):
    return f"craftdocs://open?spaceId=space-1&blockId={itemId}"


def test_create_folder_posts_expected_body(monkeypatch):
    captured = {}

    def fakeRequest(self, method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return FakeResponse(json_body={"id": "folder-1"})

    monkeypatch.setattr(requests.Session, "request", fakeRequest)

    client = CraftClient(apiUrl=_API_URL, apiToken="tok")
    folderId = client.create_folder("03 A.REAS🧭", parentFolderId="parent-1")

    assert folderId == "folder-1"
    assert captured["method"] == "POST"
    assert captured["url"] == f"{_API_URL}/folders"
    # no `icon` field - craft's API has none, so the emoji rides in the name
    assert captured["json"] == {
        "folders": [{"name": "03 A.REAS🧭", "parentFolderId": "parent-1"}]
    }


def test_create_folder_omits_optional_fields_when_unset(monkeypatch):
    captured = {}

    def fakeRequest(self, method, url, **kwargs):
        captured["json"] = kwargs.get("json")
        return FakeResponse(json_body={"id": "folder-1"})

    monkeypatch.setattr(requests.Session, "request", fakeRequest)

    CraftClient(apiUrl=_API_URL, apiToken="tok").create_folder("Inbox")

    assert captured["json"] == {"folders": [{"name": "Inbox"}]}


def test_create_folder_unwraps_a_list_response(monkeypatch):
    def fakeRequest(self, method, url, **kwargs):
        return FakeResponse(json_body=[{"id": "folder-1"}])

    monkeypatch.setattr(requests.Session, "request", fakeRequest)

    folderId = CraftClient(apiUrl=_API_URL, apiToken="tok").create_folder("Areas")

    assert folderId == "folder-1"


def test_list_folders_returns_the_nested_tree(monkeypatch):
    tree = [{"id": "f-1", "name": "03 A.REAS🧭", "folders": [{"id": "f-2", "name": "A.10-19 health", "folders": []}]}]

    def fakeRequest(self, method, url, **kwargs):
        assert method == "GET"
        assert url == f"{_API_URL}/folders"
        return FakeResponse(json_body={"items": tree})

    monkeypatch.setattr(requests.Session, "request", fakeRequest)

    assert CraftClient(apiUrl=_API_URL, apiToken="tok").list_folders() == tree


def test_folder_deep_link_uses_the_openfolder_route(monkeypatch):
    def fakeRequest(self, method, url, **kwargs):
        return FakeResponse(json_body=_CONNECTION_RESPONSE)

    monkeypatch.setattr(requests.Session, "request", fakeRequest)

    url = CraftClient(apiUrl=_API_URL, apiToken="tok").folder_deep_link("folder-1", "03 A.REAS🧭")

    # folders use `openfolder`, not the `urlTemplates` block route, and the
    # title is url-encoded so the emoji survives
    assert url == "craftdocs://openfolder?folderId=folder-1&spaceId=space-1&title=03%20A.REAS%F0%9F%A7%AD"


def test_create_document_fetches_connection_info_only_once(monkeypatch):
    connectionCalls = []

    def fakeRequest(self, method, url, **kwargs):
        if url.endswith("/connection"):
            connectionCalls.append(url)
            return FakeResponse(json_body=_CONNECTION_RESPONSE)
        return FakeResponse(json_body={"id": "doc-1"})

    monkeypatch.setattr(requests.Session, "request", fakeRequest)

    client = CraftClient(apiUrl=_API_URL, apiToken="tok")
    client.create_document("00 Index")
    client.create_document("00 Index")

    assert len(connectionCalls) == 1


def test_create_document_omits_folder_id_when_unfiled(monkeypatch):
    captured = {}

    def fakeRequest(self, method, url, **kwargs):
        if url.endswith("/connection"):
            return FakeResponse(json_body=_CONNECTION_RESPONSE)
        captured["json"] = kwargs.get("json")
        return FakeResponse(json_body={"id": "doc-1"})

    monkeypatch.setattr(requests.Session, "request", fakeRequest)

    client = CraftClient(apiUrl=_API_URL, apiToken="tok")
    documentId, url = client.create_document("00 Index")

    assert documentId == "doc-1"
    assert url == _deep_link("doc-1")
    assert "destination" not in captured["json"]


def test_create_document_includes_folder_id_when_given(monkeypatch):
    captured = {}

    def fakeRequest(self, method, url, **kwargs):
        if url.endswith("/connection"):
            return FakeResponse(json_body=_CONNECTION_RESPONSE)
        captured["json"] = kwargs.get("json")
        return FakeResponse(json_body={"id": "doc-1"})

    monkeypatch.setattr(requests.Session, "request", fakeRequest)

    CraftClient(apiUrl=_API_URL, apiToken="tok").create_document("A.11.01 Cardiologist", folderId="folder-1")

    assert captured["json"] == {
        "documents": [{"title": "A.11.01 Cardiologist"}],
        "destination": {"folderId": "folder-1"},
    }


def test_add_block_posts_to_document_and_returns_block_id(monkeypatch):
    captured = {}

    def fakeRequest(self, method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return FakeResponse(json_body={"id": "block-1"})

    monkeypatch.setattr(requests.Session, "request", fakeRequest)

    blockId = CraftClient(apiUrl=_API_URL, apiToken="tok").add_block("doc-1", "- item")

    assert blockId == "block-1"
    assert captured["method"] == "POST"
    assert captured["url"] == f"{_API_URL}/blocks"
    assert captured["json"] == {
        "blocks": [{"type": "text", "markdown": "- item"}],
        "position": {"pageId": "doc-1", "position": "end"},
    }


def test_add_block_splits_multiline_markdown_into_sibling_blocks(monkeypatch):
    """*confirmed empirically against a real space: one sibling block per line, not one block*"""

    def fakeRequest(self, method, url, **kwargs):
        return FakeResponse(json_body={"items": [
            {"id": "block-1", "markdown": "- line one"},
            {"id": "block-2", "markdown": "- line two"},
        ]})

    monkeypatch.setattr(requests.Session, "request", fakeRequest)

    blockId = CraftClient(apiUrl=_API_URL, apiToken="tok").add_block("doc-1", "- line one\n- line two")

    # only the first resulting sibling's id is returned - callers cannot
    # address "the" block afterwards, because there usually isn't just one
    assert blockId == "block-1"


def test_get_block_fetches_by_id(monkeypatch):
    captured = {}

    def fakeRequest(self, method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured["params"] = kwargs.get("params")
        return FakeResponse(json_body={
            "id": "doc-1", "type": "page", "content": [{"id": "block-1", "markdown": "- item"}],
        })

    monkeypatch.setattr(requests.Session, "request", fakeRequest)

    block = CraftClient(apiUrl=_API_URL, apiToken="tok").get_block("doc-1")

    assert captured["method"] == "GET"
    assert captured["url"] == f"{_API_URL}/blocks"
    assert captured["params"] == {"id": "doc-1"}
    assert block["content"] == [{"id": "block-1", "markdown": "- item"}]


def test_delete_blocks_sends_block_ids(monkeypatch):
    captured = {}

    def fakeRequest(self, method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return FakeResponse(json_body={"items": [{"id": "block-1"}, {"id": "block-2"}]})

    monkeypatch.setattr(requests.Session, "request", fakeRequest)

    CraftClient(apiUrl=_API_URL, apiToken="tok").delete_blocks(["block-1", "block-2"])

    assert captured["method"] == "DELETE"
    assert captured["url"] == f"{_API_URL}/blocks"
    assert captured["json"] == {"blockIds": ["block-1", "block-2"]}


def test_delete_blocks_is_a_noop_for_an_empty_list(monkeypatch):
    calls = []

    def fakeRequest(self, method, url, **kwargs):
        calls.append((method, url))
        return FakeResponse(status_code=204)

    monkeypatch.setattr(requests.Session, "request", fakeRequest)

    CraftClient(apiUrl=_API_URL, apiToken="tok").delete_blocks([])

    assert calls == []


def test_request_failure_raises_craft_api_error(monkeypatch):
    def fakeRequest(self, method, url, **kwargs):
        return FakeResponse(status_code=500, text="boom")

    monkeypatch.setattr(requests.Session, "request", fakeRequest)

    with pytest.raises(CraftApiError) as error:
        CraftClient(apiUrl=_API_URL, apiToken="tok").create_folder("Areas")
    assert error.value.method == "POST"
    assert error.value.path == "/folders"
    assert error.value.statusCode == 500
    assert error.value.responseText == "boom"


def test_a_transient_500_is_retried_then_succeeds(monkeypatch):
    calls = []

    def fakeRequest(self, method, url, **kwargs):
        calls.append(url)
        if len(calls) < 3:
            return FakeResponse(status_code=500, text="transient")
        return FakeResponse(json_body={"id": "folder-1"})

    monkeypatch.setattr(requests.Session, "request", fakeRequest)

    folderId = CraftClient(apiUrl=_API_URL, apiToken="tok").create_folder("Areas")
    assert folderId == "folder-1"
    assert len(calls) == 3


def test_a_persistent_429_is_retried_then_raises(monkeypatch):
    calls = []

    def fakeRequest(self, method, url, **kwargs):
        calls.append(url)
        return FakeResponse(status_code=429, text="slow down")

    monkeypatch.setattr(requests.Session, "request", fakeRequest)

    with pytest.raises(CraftApiError):
        CraftClient(apiUrl=_API_URL, apiToken="tok").create_folder("Areas")
    assert len(calls) == 5


def test_authorization_header_carries_the_api_token():
    client = CraftClient(apiUrl=_API_URL, apiToken="secret-token")
    assert client._session.headers["Authorization"] == "Bearer secret-token"
