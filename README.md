# Salesforce MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io) server that lets Claude look up Contacts, Cases, Tasks and Events in Salesforce. It is read-only, stores no data of its own, and fetches everything live from Salesforce at the moment you ask.

## How it works

```
You ask Claude a question
   │
   ▼
Claude picks a tool and fills in its arguments          (MCP, JSON-RPC over stdin/stdout)
   │
   ▼
sf-mcp (this server, a local Python process started by Claude Code)
   1. validates the arguments                            soql.py
   2. builds a SOQL query from an allowlist of fields    mapping.py
   3. gets an OAuth access token (cached)                auth.py
   4. sends an HTTPS GET to the Salesforce REST API      client.py
   5. cleans the response and writes an audit line       client.py, audit.py
   │
   ▼
Salesforce checks the token's user, permissions and sharing rules, then returns JSON
   │
   ▼
Claude reads the result and answers you
```

- **Transport.** Claude Code launches `sf-mcp` as a child process and talks to it over stdio. Nothing listens on a network port.
- **Tool discovery.** On startup the server tells Claude which tools exist. The name, description and parameters of each tool are generated from the Python function signature and docstring in `server.py`. That description is the only guidance Claude has about when to use a tool.
- **Data access.** Every lookup is a `GET /services/data/v62.0/query?q=<SOQL>` request. The only other request is the OAuth token request. The client has no method for creating, updating or deleting records.
- **Authentication.** OAuth 2.0 Client Credentials. The server exchanges a client ID and secret for a bearer token, and Salesforce issues it for a dedicated integration user. The token is cached in memory and refreshed once if Salesforce answers 401. Claude never sees the ID, secret or token.
- **No stored data.** Nothing is cached or written to disk except the optional audit log.

## Tools

| Tool | Purpose |
|---|---|
| `search_contacts` | Find Contacts by partial name and/or exact email |
| `get_contact_summary` | One Contact plus counts of their Cases (total, open, closed), open Tasks and upcoming Events |
| `list_cases` | List Cases (open and closed by default), newest first |
| `list_tasks` | List open Tasks, soonest due first |
| `describe_available_data` | Show which objects and fields the server can read |

Each tool reads one standard Salesforce object: Contact, Case, Task or Event.

### `search_contacts(name?, email?, limit=10)`
At least one of `name` or `email` is required. `limit` is capped at 25. The name is matched anywhere in the contact's full name (case-insensitive); the email must match exactly. If both are given, both must match.

```sql
SELECT Id, FirstName, LastName, Email, Phone, Birthdate, Account.Name
FROM Contact
WHERE Name LIKE '%<name>%' AND Email = '<email>'    -- only the filters you supplied
ORDER BY LastName, FirstName
LIMIT <limit + 1>
```

### `get_contact_summary(contact_id)`
Takes a Salesforce Contact ID (from `search_contacts`). Runs five queries at the same time and combines them:

```sql
SELECT <contact fields> FROM Contact WHERE Id = '<id>' LIMIT 1
SELECT COUNT() FROM Case  WHERE ContactId = '<id>'
SELECT COUNT() FROM Case  WHERE ContactId = '<id>' AND IsClosed = false
SELECT COUNT() FROM Task  WHERE WhoId     = '<id>' AND IsClosed = false
SELECT COUNT() FROM Event WHERE WhoId     = '<id>' AND StartDateTime >= TODAY
```

Returns `{ contact, total_cases, open_cases, closed_cases, open_tasks, upcoming_events }`. Closed cases are the total minus the open ones.

### `list_cases(contact_id?, status?, open_only=false, limit=10)`
Returns open and closed Cases unless `open_only` is true.

```sql
SELECT Id, CaseNumber, Subject, Status, Priority, CreatedDate, ContactId, Owner.Name
FROM Case
WHERE ContactId = '<contact_id>'       -- if given
  AND Status = '<status>'              -- if given (replaces the open-only filter)
  AND IsClosed = false                 -- only when open_only is true and no status is given
ORDER BY CreatedDate DESC
LIMIT <limit + 1>
```

### `list_tasks(overdue_only=false, due_before?, contact_id?, limit=10)`
`due_before` is a date in `YYYY-MM-DD` format. Only open Tasks are returned, and `contact_id` matches Tasks whose "Name" (WhoId) field is that Contact.

```sql
SELECT Id, Subject, Status, Priority, ActivityDate, WhoId, Owner.Name
FROM Task
WHERE IsClosed = false
  AND ActivityDate < TODAY             -- when overdue_only is true
  AND ActivityDate <= <due_before>     -- if given
  AND WhoId = '<contact_id>'           -- if given
ORDER BY ActivityDate ASC
LIMIT <limit + 1>
```

### `describe_available_data()`
Returns the server's own list of readable objects and fields, the maximum result size and a `read_only: true` flag. It does not call Salesforce.

## What a tool returns

List tools return:

```json
{ "records": [ ... ], "returned": 3, "truncated": false }
```

The server asks Salesforce for one row more than `limit`, then trims the result. If that extra row exists, `truncated` is `true`, which means more matching records exist than were returned. Records contain only the fields shown above, with Salesforce's internal metadata removed.

## Input checks and errors

All input is checked before any request is sent to Salesforce:

- **Names** may contain letters, digits, spaces and `. ' - @ +`, up to 80 characters. Wildcards (`%`, `_`) are rejected.
- **Emails** must look like an address (`local@domain.tld`); they are matched exactly.
- **IDs** must be 15 or 18 alphanumeric characters.
- **Dates** must be real `YYYY-MM-DD` dates.
- **`limit`** is clamped to 1 to 25.

Rejected input and Salesforce or setup failures come back to Claude as readable error messages (for example "Provide at least one of: name, email."), so it can correct itself. Raw Salesforce error bodies are never passed through.

## Audit log

Each tool call writes one JSON line to stderr, or to the file named in `SF_AUDIT_LOG`:

```json
{"ts": 1790791623.1, "tool": "search_contacts", "params": {"name": "29c4fccbfa"}, "rows": 1, "ok": true, "error": null}
```

Parameter values are replaced with keyed hashes, so names, emails and IDs never appear in the log. The hash key is random each time the server starts; set `SF_AUDIT_KEY` to keep hashes comparable across restarts.

## Requirements

- Python 3.10 or newer (developed and tested on 3.14)
- [Claude Code](https://claude.com/claude-code)
- A Salesforce org (a free Developer Edition org works)

## Setup

### 1. Salesforce

1. Create a free Developer Edition org at developer.salesforce.com/signup.
2. Create a permission set (for example `MCP Read Only`) with **API Enabled**, and **Read** on Account, Contact, Case, Task and Event plus Read on the fields listed above.
3. Create an integration user with a full **Salesforce** license and the **Salesforce API Only System Integration** profile, and assign the permission set to it.
4. Create an **External Client App** with OAuth enabled, the scope **Manage user data via APIs (api)**, and the **Client Credentials Flow** turned on. On its Policies tab, set **Run As** to the integration user.
5. Copy the app's Consumer Key and Consumer Secret, and your My Domain URL (Setup > My Domain).

### 2. Local install

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env      # then fill in the values below
.venv/bin/pytest          # runs with mocked HTTP, no Salesforce needed
```

### 3. Configuration (`.env`)

| Variable | Required | Meaning |
|---|---|---|
| `SF_INSTANCE_URL` | yes | Your My Domain URL, e.g. `https://yourname-dev-ed.develop.my.salesforce.com` |
| `SF_CLIENT_ID` | yes | Consumer Key |
| `SF_CLIENT_SECRET` | yes | Consumer Secret |
| `SF_API_VERSION` | no | REST API version (default `v62.0`) |
| `SF_AUDIT_LOG` | no | File for audit lines (default: stderr) |
| `SF_AUDIT_KEY` | no | Fixed key for audit hashes |

`.env` is git-ignored. Never commit it.

### 4. Connect to Claude Code

```bash
claude mcp add salesforce -- "$PWD/.venv/bin/sf-mcp"
claude mcp list          # salesforce should show as connected
claude                   # start a session, then type /mcp to see the five tools
```

After changing the server code, restart `claude` or reconnect the server from `/mcp`.

## Example prompts

- "What Salesforce data can you access?"
- "Find contacts with the last name Smith."
- "Give me a summary of Stella Pavlova: how many cases does she have, and which are open?"
- "Show all cases for Stella Pavlova."
- "Show only the open cases."
- "Which cases have status New?"
- "Which tasks are overdue?"

The task and event figures are zero until Tasks and Events exist in the org. In a Developer Edition org, create a few by hand (for example, log a call on a Contact with a past due date).

The example names come from the sample data that ships with a Developer Edition org. Your org's records will differ.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Tool errors with "Missing environment variables" | `.env` is missing or incomplete. Check that it sits in the project folder and has the three required values. |
| "Salesforce token request failed (HTTP 400/401)" | Wrong consumer key or secret, Client Credentials Flow not enabled, or no Run As user set on the app's Policies tab. |
| "Salesforce API error (HTTP 403)" | The integration user lacks API access or Read permission on an object or field. Recheck the permission set and its assignment. |
| Searches return nothing but records exist | Sharing rules hide them from the integration user, or its permission set lacks Read on the object. |
| A field is missing from results | It is not in `mapping.py`, or the integration user has no Read access to it. |
| Code changes have no effect | Restart `claude`, or reconnect the server from `/mcp`. |
| Server missing from `/mcp` | Re-run `claude mcp add` with the absolute path to `.venv/bin/sf-mcp`. |

## Project layout

```
src/sf_mcp/
  server.py        MCP entry point; registers the tools; turns expected failures into readable errors
  tools/           contacts.py, cases.py, tasks.py, generic.py - one function per tool
  soql.py          input validation, escaping and SOQL assembly
  mapping.py       the allowlist: which objects and fields can be read, and the result cap
  client.py        read-only Salesforce REST client (GET only), retries, truncation, cleanup
  auth.py          OAuth Client Credentials token handling
  audit.py         keyed-hash audit logging
tests/             unit tests using mocked Salesforce responses
```

## Customizing

- **Expose another field:** add it to the object in `mapping.py` and grant Read on it in the permission set.
- **Use different Salesforce objects** (for example custom objects): edit the object and field definitions in `mapping.py`.
- **Add a tool:** write a function in `tools/` that builds its query with `soql.py` and `client.query_limited`, then register it in `server.py`.
