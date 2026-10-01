import httpx
import pytest
import respx
from sf_mcp.client import SalesforceClient, SalesforceError
from sf_mcp.tools import cases, contacts, generic, tasks

BASE = "https://x.my.salesforce.com/services/data/v62.0"


class FakeAuth:
    instance_url = "https://x.my.salesforce.com"
    refreshes = 0

    async def token(self, force_refresh=False):
        if force_refresh:
            self.refreshes += 1
        return "tok"


@pytest.fixture
def auth():
    return FakeAuth()


@pytest.fixture
def client(auth):
    return SalesforceClient(auth)


def ok(records, done=True):
    return httpx.Response(200, json={"totalSize": len(records), "done": done,
                                     "records": [{"attributes": {}, **r} for r in records]})


@respx.mock
async def test_search_contacts_builds_safe_query_and_strips_attributes(client):
    route = respx.get(f"{BASE}/query").mock(return_value=ok([{"Id": "003", "LastName": "O'Brien"}]))
    res = await contacts.search_contacts(client, name="O'Brien", limit=999)
    q = route.calls[0].request.url.params["q"]
    assert "Name LIKE '%O\\'Brien%'" in q and q.endswith("LIMIT 26")  # limit+1 probe
    assert "attributes" not in res["records"][0]
    assert res["returned"] == 1 and res["truncated"] is False


@respx.mock
async def test_search_rejects_injection_without_calling_salesforce(client):
    route = respx.get(f"{BASE}/query").mock(return_value=ok([]))
    with pytest.raises(ValueError):
        await contacts.search_contacts(client, name="' OR Id != null --")
    assert not route.called


async def test_search_requires_a_filter(client):
    with pytest.raises(ValueError):
        await contacts.search_contacts(client)


@respx.mock
async def test_summary_counts(client):
    def handler(request):
        q = request.url.params["q"]
        if q.startswith("SELECT COUNT()"):
            if "FROM Case" in q and "IsClosed" not in q:
                n = 4  # all cases
            elif "FROM Case" in q:
                n = 1  # open cases
            else:
                n = 2
            return httpx.Response(200, json={"totalSize": n, "done": True, "records": []})
        return ok([{"Id": "0035g00000AbCdE", "LastName": "Lopez"}])
    respx.get(f"{BASE}/query").mock(side_effect=handler)
    res = await contacts.get_contact_summary(client, "0035g00000AbCdE")
    assert (res["total_cases"], res["open_cases"], res["closed_cases"]) == (4, 1, 3)
    assert res["open_tasks"] == res["upcoming_events"] == 2


@respx.mock
async def test_cases_include_closed_by_default_and_filters(client):
    route = respx.get(f"{BASE}/query").mock(return_value=ok([]))
    await cases.list_cases(client)  # default: open AND closed
    assert "IsClosed" not in route.calls[0].request.url.params["q"]
    await cases.list_cases(client, open_only=True)
    assert "IsClosed = false" in route.calls[1].request.url.params["q"]
    await cases.list_cases(client, status="Escalated", open_only=True)  # explicit status wins
    q = route.calls[2].request.url.params["q"]
    assert "Status = 'Escalated'" in q and "IsClosed" not in q


@respx.mock
async def test_tasks_overdue_and_date(client):
    route = respx.get(f"{BASE}/query").mock(return_value=ok([]))
    await tasks.list_tasks(client, overdue_only=True, due_before="2026-10-01")
    q = route.calls[0].request.url.params["q"]
    assert "ActivityDate < TODAY" in q and "ActivityDate <= 2026-10-01" in q
    with pytest.raises(ValueError):
        await tasks.list_tasks(client, due_before="tomorrow")


@respx.mock
async def test_401_refreshes_once(client, auth):
    respx.get(f"{BASE}/query").mock(side_effect=[httpx.Response(401), ok([])])
    await client.query("SELECT Id FROM Contact")
    assert auth.refreshes == 1


@respx.mock
async def test_error_hides_body(client):
    respx.get(f"{BASE}/query").mock(return_value=httpx.Response(400, text="secret org detail"))
    with pytest.raises(SalesforceError) as e:
        await client.query("bad")
    assert "secret" not in str(e.value)


def test_describe_lists_no_sensitive_fields():
    data = generic.describe_available_data()
    assert data["read_only"] and "SSN" not in str([c["fields"] for c in data["concepts"].values()])
    assert data["note"] == "Only the fields listed here can be read; all other fields are intentionally not exposed."


@respx.mock
async def test_truncated_flag_and_trimming(client):
    rows = [{"Id": str(i)} for i in range(4)]  # server "has" 4 rows, we ask for 3
    respx.get(f"{BASE}/query").mock(return_value=ok(rows))
    res = await client.query_limited(("Id",), "Contact", [], None, 3)
    assert res["truncated"] is True and res["returned"] == 3 and len(res["records"]) == 3


@respx.mock
async def test_nested_attributes_stripped(client):
    rec = {"Id": "1", "Account": {"attributes": {"url": "/x"}, "Name": "Acme"}}
    respx.get(f"{BASE}/query").mock(return_value=ok([rec]))
    res = await client.query("SELECT Id FROM Contact")
    assert res["records"][0] == {"Id": "1", "Account": {"Name": "Acme"}}


def test_audit_hash_is_keyed_not_plain_sha256():
    import hashlib
    from sf_mcp import audit
    assert audit._h("a") != hashlib.sha256(b"a").hexdigest()[:10]


async def test_expected_errors_reach_the_model():
    from mcp.server.mcpserver.exceptions import ToolError
    from sf_mcp import server
    with pytest.raises(ToolError, match="at least one"):
        await server.search_contacts()


def test_http_client_logging_is_quiet():
    import logging
    from sf_mcp import server  # noqa: F401  (import applies the logging config)
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
