"""Safe SOQL construction: no user string ever reaches a query unescaped."""
import re
from datetime import date

_ID_RE = re.compile(r"^[a-zA-Z0-9]{15}([a-zA-Z0-9]{3})?$")
_NAME_RE = re.compile(r"^[A-Za-z0-9\u00C0-\u024F .'\-@+]{1,80}$")  # no % or _ (LIKE wildcards)
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._'+\-]{1,64}@[A-Za-z0-9.\-]{1,190}\.[A-Za-z]{2,}$")


class InvalidInput(ValueError):
    pass


def escape(value: str) -> str:
    """Escape a string for use inside a SOQL single-quoted literal."""
    return (
        value.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')
        .replace("\n", "\\n").replace("\r", "\\r")
    )


def lit(value: str) -> str:
    return f"'{escape(value)}'"


def sf_id(value: str) -> str:
    if not isinstance(value, str) or not _ID_RE.match(value):
        raise InvalidInput("Invalid Salesforce ID (expected 15 or 18 alphanumeric characters).")
    return value


def text(value: str) -> str:
    """Validate a name search term. Rejects control chars and the LIKE wildcards % and _."""
    if not isinstance(value, str) or not _NAME_RE.match(value.strip()):
        raise InvalidInput("Invalid search text (letters, digits, space . ' - @ + only, max 80 chars).")
    return value.strip()


def email(value: str) -> str:
    """Validate an email for an exact-match (`=`) filter. Unlike names, `_` is allowed: it is only a
    wildcard inside LIKE, and emails are never used with LIKE."""
    if not isinstance(value, str) or not _EMAIL_RE.match(value.strip()):
        raise InvalidInput("Invalid email address.")
    return value.strip()


def iso_date(value: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError):
        raise InvalidInput("Dates must be ISO format YYYY-MM-DD.") from None


def clamp_limit(limit: int | None, default: int, maximum: int) -> int:
    if limit is None:
        return default
    return max(1, min(int(limit), maximum))


def build(fields: tuple[str, ...], sobject: str, where: list[str], order: str | None, limit: int) -> str:
    q = f"SELECT {', '.join(fields)} FROM {sobject}"
    if where:
        q += " WHERE " + " AND ".join(where)
    if order:
        q += f" ORDER BY {order}"
    return q + f" LIMIT {limit}"
