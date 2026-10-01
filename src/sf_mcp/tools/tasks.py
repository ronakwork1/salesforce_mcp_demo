from .. import audit, mapping, soql
from ..client import SalesforceClient


async def list_tasks(client: SalesforceClient, overdue_only: bool = False, due_before: str | None = None,
                     contact_id: str | None = None, limit: int | None = None) -> dict:
    """List open Tasks ordered by due date. `overdue_only` = due before today."""
    params = {"overdue_only": overdue_only, "due_before": due_before, "contact_id": contact_id, "limit": limit}
    try:
        where = ["IsClosed = false"]
        if overdue_only:
            where.append("ActivityDate < TODAY")
        if due_before:
            where.append(f"ActivityDate <= {soql.iso_date(due_before)}")  # date literal, validated
        if contact_id:
            where.append(f"WhoId = '{soql.sf_id(contact_id)}'")
        cfg = mapping.TASK
        result = await client.query_limited(cfg.fields, cfg.sobject, where, "ActivityDate ASC",
                                            soql.clamp_limit(limit, mapping.DEFAULT_LIMIT, mapping.MAX_LIMIT))
        audit.record("list_tasks", params, result["returned"])
        return result
    except Exception as e:
        audit.record("list_tasks", params, None, ok=False, error=type(e).__name__)
        raise
