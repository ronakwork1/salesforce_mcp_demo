import asyncio

from .. import audit, mapping, soql
from ..client import SalesforceClient


async def search_contacts(client: SalesforceClient, name: str | None = None, email: str | None = None,
                          limit: int | None = None) -> dict:
    """Find Contacts by name and/or email. Returns allowlisted fields only."""
    params = {"name": name, "email": email, "limit": limit}
    try:
        if not name and not email:
            raise soql.InvalidInput("Provide at least one of: name, email.")
        where = []
        if name:
            n = soql.text(name)
            where.append(f"Name LIKE '%{soql.escape(n)}%'")
        if email:
            where.append(f"Email = {soql.lit(soql.email(email))}")
        cfg = mapping.CONTACT
        result = await client.query_limited(cfg.fields, cfg.sobject, where, "LastName, FirstName",
                                            soql.clamp_limit(limit, mapping.DEFAULT_LIMIT, mapping.MAX_LIMIT))
        audit.record("search_contacts", params, result["returned"])
        return result
    except Exception as e:
        audit.record("search_contacts", params, None, ok=False, error=type(e).__name__)
        raise


async def get_contact_summary(client: SalesforceClient, contact_id: str) -> dict:
    """One Contact plus counts of their Cases (total, open, closed), open Tasks and upcoming Events."""
    params = {"contact_id": contact_id}
    try:
        pid = soql.sf_id(contact_id)
        cfg = mapping.CONTACT
        contact_q = soql.build(cfg.fields, cfg.sobject, [f"Id = '{pid}'"], None, 1)
        counts = [
            f"SELECT COUNT() FROM Case WHERE ContactId = '{pid}'",
            f"SELECT COUNT() FROM Case WHERE ContactId = '{pid}' AND IsClosed = false",
            f"SELECT COUNT() FROM Task WHERE WhoId = '{pid}' AND IsClosed = false",
            f"SELECT COUNT() FROM Event WHERE WhoId = '{pid}' AND StartDateTime >= TODAY",
        ]
        contact, all_cases, open_cases, tasks, events = await asyncio.gather(
            client.query(contact_q), *(client.query(c) for c in counts))
        if not contact["records"]:
            raise soql.InvalidInput("No contact found with that ID.")
        audit.record("get_contact_summary", params, 1)
        return {
            "contact": contact["records"][0],
            "total_cases": all_cases["total_size"],
            "open_cases": open_cases["total_size"],
            "closed_cases": all_cases["total_size"] - open_cases["total_size"],
            "open_tasks": tasks["total_size"],
            "upcoming_events": events["total_size"],
        }
    except Exception as e:
        audit.record("get_contact_summary", params, None, ok=False, error=type(e).__name__)
        raise
