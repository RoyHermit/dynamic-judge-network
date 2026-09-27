"""Typed application settings loaded from environment variables / .env.

See docs/superpowers/specs/2026-09-27-project-foundation-design.md §7.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()


class Settings(BaseModel):
    typesafe_api_key: str = Field(min_length=1)

    @classmethod
    def load(cls) -> Settings:
        """Fail fast (pydantic ValidationError) if TYPESAFE_API_KEY is
        missing or empty, rather than proceeding with a falsy secret."""
        return cls(typesafe_api_key=os.environ.get("TYPESAFE_API_KEY", ""))
