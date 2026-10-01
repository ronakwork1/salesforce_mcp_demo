"""Read-only Salesforce MCP server for looking up Contacts, Cases, Tasks and Events."""
from dotenv import load_dotenv

# Load .env first: audit.py reads SF_AUDIT_LOG / SF_AUDIT_KEY when it is imported.
load_dotenv()
