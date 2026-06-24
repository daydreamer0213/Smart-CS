"""Analytics schemas — request/response models for the analytics API.

Covers query parameter models (date range, group-by, filters) and
response models for conversation stats, satisfaction ratings,
trend data, and exported report formats.
"""

from pydantic import BaseModel


class DashboardStats(BaseModel):
    """Placeholder for dashboard overview statistics."""
    pass
