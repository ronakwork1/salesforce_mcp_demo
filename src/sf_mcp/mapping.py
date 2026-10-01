"""Salesforce object/field allowlists.

Only fields listed here can ever be selected. To expose another field or use
different objects, edit this file, not the tools. Anything not listed is
deliberately unreadable. Birthdate is included so users can tell apart contacts
with the same name; remove it from CONTACT if your policy forbids it.
"""
from dataclasses import dataclass

MAX_LIMIT = 25
DEFAULT_LIMIT = 10


@dataclass(frozen=True)
class ObjectConfig:
    sobject: str
    fields: tuple[str, ...]


CONTACT = ObjectConfig("Contact", ("Id", "FirstName", "LastName", "Email", "Phone", "Birthdate", "Account.Name"))
CASE = ObjectConfig("Case", ("Id", "CaseNumber", "Subject", "Status", "Priority", "CreatedDate", "ContactId", "Owner.Name"))
TASK = ObjectConfig("Task", ("Id", "Subject", "Status", "Priority", "ActivityDate", "WhoId", "Owner.Name"))
EVENT = ObjectConfig("Event", ("Id", "Subject", "StartDateTime", "EndDateTime", "WhoId"))

OBJECTS = {"contact": CONTACT, "case": CASE, "task": TASK, "event": EVENT}

