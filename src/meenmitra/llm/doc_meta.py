"""The record we want for every document of MeenMitra.

This class is a contract. The extraction prompt, the database and (from Week 3)
the search filters all rely on it: add a field freely, but rename or remove one
only on purpose.
"""

from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

Short = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=80),
]

Values = Annotated[list[Short], Field(default_factory=list, max_length=8)]

ScientificName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=3,
        max_length=80,
        pattern=r"^[A-Z][a-z]+(?: [a-z][a-z-]+){1,2}$",
    ),
]

ScientificNames = Annotated[
    list[ScientificName],
    Field(default_factory=list, max_length=8),
]

Regulation = Literal[
    "mesh_size",
    "minimum_legal_size",
    "fishing_ban",
    "licensing",
    "gear_restriction",
    "protected_species",
    "other",
]

Regulations = Annotated[
    list[Regulation],
    Field(default_factory=list, max_length=8),
]

Kind = Literal[
    "guideline",
    "rule",
    "notice",
    "list",
    "report",
    "faq",
    "form",
    "tutorial",
    "reference",
    "other",
]


class DocMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doc_kind: Kind
    year: int | None = Field(default=None, ge=1950, le=2027)
    language: Literal["en", "ta", "hi", "other"]
    summary: str = Field(min_length=20, max_length=300)
    topics: Annotated[list[Short], Field(min_length=1, max_length=6)]

    # MeenMitra-specific document metadata
    species_scientific: ScientificNames
    local_name_tamil: Values
    topic: Values
    region: Values
    regulation: Regulations

    @field_validator("topics")
    @classmethod
    def _tidy(cls, value: list[str]) -> list[str]:
        """Lowercase and remove duplicates."""
        return list(dict.fromkeys(topic.lower() for topic in value))
