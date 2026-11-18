"""SQLAlchemy database models for documents and pages."""

from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"

    __table_args__ = (
        Index("ix_documents_doc_type", "doc_type"),
        # GIN index: makes metadata containment filters fast on big tables.
        Index(
            "ix_documents_metadata_gin",
            "metadata",
            postgresql_using="gin",
            postgresql_ops={"metadata": "jsonb_path_ops"},
        ),
    )

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    species_scientific: Mapped[str | None] = mapped_column(String(255))
    local_name_tamil: Mapped[str | None] = mapped_column(String(255))
    english_name: Mapped[str | None] = mapped_column(String(255))
    topic: Mapped[str | None] = mapped_column(String(255))
    region: Mapped[str | None] = mapped_column(String(255))
    regulation: Mapped[str | None] = mapped_column(Text)

    source_url: Mapped[str | None] = mapped_column(Text)

    doc_type: Mapped[str | None] = mapped_column(String(100))

    document_metadata: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
    )

    pages: Mapped[list["Page"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )


class Page(Base):
    __tablename__ = "pages"
    __table_args__ = (UniqueConstraint("document_id", "page_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    document: Mapped["Document"] = relationship(back_populates="pages")
