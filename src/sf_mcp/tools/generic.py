from .. import audit, mapping


def describe_available_data() -> dict:
    """Tell the model which concepts/objects/fields it may query (the allowlist)."""
    audit.record("describe_available_data", {}, None)
    return {
        "read_only": True,
        "max_limit": mapping.MAX_LIMIT,
        "concepts": {k: {"salesforce_object": v.sobject, "fields": list(v.fields)} for k, v in mapping.OBJECTS.items()},
        "note": "Only the fields listed here can be read; all other fields are intentionally not exposed.",
    }
