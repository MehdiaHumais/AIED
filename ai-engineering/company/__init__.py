"""Layer 0 - Company Information Layer (Britsync AIED).

Stores company profile and project registry. The CEO agent reads from
this layer to introduce the company and answer questions about projects.
"""

from company.models import CompanyData, CompanyProfile, Project
from company.store import CompanyStore

__all__ = [
    "CompanyData",
    "CompanyProfile",
    "CompanyStore",
    "Project",
]
