from .. import audit, mapping, soql
from ..client import SalesforceClient


async def list_cases(client: SalesforceClient, contact_id: str | None = None, status: str | None = None,
                     open_only: bool = False, limit: int | None = None) -> dict:
    """List Cases (open and closed), newest first. Filter by contact, exact status, or open-only."""
    params = {"contact_id": contact_id, "status": status, "open_only": open_only, "limit": limit}
    try:
        where = []
        if contact_id:
            where.append(f"ContactId = '{soql.sf_id(contact_id)}'")
        if status:
            where.append(f"Status = {soql.lit(soql.text(status))}")
        elif open_only:
            where.append("IsClosed = false")
        cfg = mapping.CASE
        result = await client.query_limited(cfg.fields, cfg.sobject, where, "CreatedDate DESC",
                                            soql.clamp_limit(limit, mapping.DEFAULT_LIMIT, mapping.MAX_LIMIT))
        audit.record("list_cases", params, result["returned"])
        return result
    except Exception as e:
        audit.record("list_cases", params, None, ok=False, error=type(e).__name__)
        raise
