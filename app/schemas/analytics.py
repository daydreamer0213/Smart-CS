"""Analytics schemas — request/response models for the analytics API.

Covers query parameter models (date range, group-by, filters) and
response models for conversation stats, satisfaction ratings,
trend data, and exported report formats.
"""

from pydantic import BaseModel


class AnalyticsPlaceholder(BaseModel):
    """Placeholder — remove once real analytics schemas are defined."""
    pass
