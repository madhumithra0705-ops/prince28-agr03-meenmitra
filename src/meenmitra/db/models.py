"""SQLAlchemy database models for documents and pages."""

from datetime import date, datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    synonym,
)


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"

    __table_args__ = (
        Index("ix_documents_doc_type", "doc_type"),
        Index(
            "ix_documents_metadata_gin",
            "metadata",
            postgresql_using="gin",
            postgresql_ops={"metadata": "jsonb_path_ops"},
        ),
    )

    # Existing MeenMitra primary key.
    id: Mapped[str] = mapped_column(String(50), primary_key=True)

    # Alias for the existing ID; no duplicate database column.
    external_id = synonym("id")

    # Existing MeenMitra fields.
    species_scientific: Mapped[str | None] = mapped_column(String(255))
    local_name_tamil: Mapped[str | None] = mapped_column(String(255))
    english_name: Mapped[str | None] = mapped_column(String(255))
    topic: Mapped[str | None] = mapped_column(String(255))
    region: Mapped[str | None] = mapped_column(String(255))
    regulation: Mapped[str | None] = mapped_column(Text)

    # Additional document fields.
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text)
    licence: Mapped[str | None] = mapped_column(String(200))
    doc_type: Mapped[str | None] = mapped_column(String(100))
    published_on: Mapped[date | None]

    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)

    document_metadata: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    pages: Mapped[list["Page"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )


class Page(Base):
    __tablename__ = "pages"

    __table_args__ = (UniqueConstraint("document_id", "page_number"),)

    # Existing page structure is preserved.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )

    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # The section path this page starts in, e.g. ["Fever", "Dengue"]: used for citations.
    headings: Mapped[list[str]] = mapped_column(JSONB, server_default="[]")

    document: Mapped["Document"] = relationship(back_populates="pages")


class ParseFailure(Base):
    """The dead-letter table: one row per raw file we could not parse, with the reason."""

    __tablename__ = "parse_failures"

    id: Mapped[int] = mapped_column(primary_key=True)
    path: Mapped[str] = mapped_column(Text, unique=True)  # data/raw/<source>/<file>
    sha256: Mapped[str] = mapped_column(String(64))
    source_url: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(String(40), index=True)  # no_text_layer, corrupt, ...
    detail: Mapped[str] = mapped_column(Text, server_default="")
    attempts: Mapped[int] = mapped_column(server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
