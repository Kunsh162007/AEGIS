"""Casework — the department layer: persistent casebook, priority/SLA model,
and the shared Department state that makes AEGIS learn across investigations."""
from .department import Department, get_department, reset_department
from .store import CaseStore

__all__ = ["CaseStore", "Department", "get_department", "reset_department"]
