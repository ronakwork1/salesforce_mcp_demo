"""MCP server entrypoint (stdio). All tools are read-only."""
import functools
import logging
import os

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from .auth import AuthError, ClientCredentialsAuth
from .client import SalesforceClient, SalesforceError
from .soql import InvalidInput
from .tools import cases, contacts, generic, tasks

# httpx logs every request URL at INFO. Our URLs contain the SOQL text (names, record IDs), so keep
# it quiet or personal data lands in stderr/Claude Code's MCP logs despite the audit design.
for _name in ("httpx", "httpcore"):
    logging.getLogger(_name).setLevel(logging.WARNING)
mcp = MCPServer("salesforce-crm")


def expected_errors(fn):
    """Surface anticipated failures to the model. The SDK hides every non-ToolError exception, so
    without this Claude sees only 'Error executing tool' and can't correct its input. Messages here
    are ours (validation text, generic HTTP status), never raw Salesforce output."""
    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except (InvalidInput, SalesforceError, AuthError) as e:
            raise ToolError(str(e)) from e
    return wrapper


_client: SalesforceClient | None = None


def client() -> SalesforceClient:
    global _client
    if _client is None:
        _client = SalesforceClient(ClientCredentialsAuth.from_env(), os.environ.get("SF_API_VERSION", "v62.0"))
    return _client


@mcp.tool()
@expected_errors
async def search_contacts(name: str | None = None, email: str | None = None, limit: int = 10) -> dict:
    """Search Salesforce Contacts by (partial) name and/or exact email. At least one is required (there is no list-all). Max 25 results; check `truncated`. Returns id, name, contact info, account."""
    return await contacts.search_contacts(client(), name, email, limit)


@mcp.tool()
@expected_errors
async def get_contact_summary(contact_id: str) -> dict:
    """One Contact plus counts of their Cases (total, open, closed), open Tasks and upcoming Events. Needs a Contact ID from search_contacts. For the cases themselves, call list_cases with the same contact_id."""
    return await contacts.get_contact_summary(client(), contact_id)


@mcp.tool()
@expected_errors
async def list_cases(contact_id: str | None = None, status: str | None = None, open_only: bool = False, limit: int = 10) -> dict:
    """List Salesforce Cases, newest first. Cases are support tickets, requests or issues. By default returns BOTH open and closed cases, each with its Status; set open_only=true only when the user explicitly asks for open cases only. Optional filters: contact_id, exact status."""
    return await cases.list_cases(client(), contact_id, status, open_only, limit)


@mcp.tool()
@expected_errors
async def list_tasks(overdue_only: bool = False, due_before: str | None = None, contact_id: str | None = None, limit: int = 10) -> dict:
    """List open Salesforce Tasks by due date. overdue_only=true for past-due; due_before is YYYY-MM-DD."""
    return await tasks.list_tasks(client(), overdue_only, due_before, contact_id, limit)


@mcp.tool()
def describe_available_data() -> dict:
    """Describe which objects and fields this server can read. Call first to plan queries."""
    return generic.describe_available_data()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
