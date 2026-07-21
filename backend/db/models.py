"""AutoBOM ORM models — the 19-table Phase 1 schema.

Cross-referenced to CLAUDE.md's data model and
02_Architecture/AutoBOM_Platform_Architecture.md §2.3 / §6.

Conventions:
- String PKs preserve prototype IDs (u-aaron, BOM-052, terra-voyager, ...).
  Pure child line tables use integer autoincrement PKs.
- List-valued fields are JSON (portability + simple tests), not Postgres ARRAY.
- Document-shaped sub-structures are JSON (JSONB on Postgres).
- Enums are stored as VARCHAR + CHECK (native_enum=False) for portability.
- Every domain table carries created_at/updated_at (TimestampMixin); audit and
  append-only tables carry an explicit ts instead.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Integer, JSON,
    Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base, TimestampMixin

# JSON that becomes JSONB on Postgres but stays portable elsewhere.
JSONType = JSON().with_variant(JSONB(), "postgresql")


# --------------------------------------------------------------------------- #
# Enums (stored as their string .value)
# --------------------------------------------------------------------------- #
def _enum(e):
    """Enum column stored as its string .value.

    `validate_strings=True` is load-bearing, not decoration. SQLAlchemy defaults
    it to False, which means a raw string is written to the column WITHOUT being
    checked against the enum — but it is checked on the way back out. A single
    bad value (e.g. urgency="Standard" instead of "standard") therefore inserts
    happily and then raises LookupError on every subsequent SELECT. Because
    /api/bootstrap reads these tables on login, one bad row bricks the entire
    app for every user with no way back in short of DB surgery.
    Fail loudly at write time instead, where it is recoverable.
    """
    return Enum(e, native_enum=False, validate_strings=True,
                values_callable=lambda x: [m.value for m in x])


class RoleSource(str, enum.Enum):
    seed = "seed"                # local/dev — roles hardcoded from seed
    azure_group = "azure_group"  # production — roles are a read-through cache of Azure AD groups


class ProgramStatus(str, enum.Enum):
    active = "Active"; paused = "Paused"; complete = "Complete"; archived = "Archived"


class ProjectStatus(str, enum.Enum):
    active = "active"; paused = "paused"; complete = "complete"; archived = "archived"


class BomState(str, enum.Enum):
    draft = "draft"; validated = "validated"; sourcing = "sourcing"; results = "results"
    normalised = "normalised"; submitted = "submitted"; exceptions = "exceptions"


class CollectionState(str, enum.Enum):
    draft = "draft"; active = "active"; order_requested = "order-requested"; ordered = "ordered"
    # Development-collection states (deferred; kept so the enum is complete)
    ready = "ready"; recommendation_sent = "recommendation-sent"; closed = "closed"


class RequestKind(str, enum.Enum):
    collection = "collection"; bom = "bom"


class BucketState(str, enum.Enum):
    queued_main = "QUEUED_MAIN"; queued_critical = "QUEUED_CRITICAL"
    written = "WRITTEN"; purchased = "PURCHASED"; processed = "PROCESSED"


class PushbackReason(str, enum.Enum):
    obsolete = "obsolete"; eol = "eol"; unsourceable = "unsourceable"
    zero_stock = "zero-stock"; missing_component = "missing-component"; other = "other"


class PushbackUrgency(str, enum.Enum):
    blocking = "blocking"; standard = "standard"


class PushbackState(str, enum.Enum):
    open = "open"; deferred = "deferred"; resolved = "resolved"; cancelled = "cancelled"


class BatchStream(str, enum.Enum):
    critical = "critical"; main = "main"


class BatchState(str, enum.Enum):
    pending = "pending"; written = "written"


class CpnScope(str, enum.Enum):
    project = "project"; wall = "wall"


class NotificationKind(str, enum.Enum):
    action = "action"; fyi = "fyi"


class CommentThreadLevel(str, enum.Enum):
    overall = "overall"; line = "line"


# Valid role strings anywhere in the system. NO legacy manager/readonly/executive.
VALID_ROLES = ("designer", "production", "admin", "development")


# --------------------------------------------------------------------------- #
# Users + auth/role sourcing
# --------------------------------------------------------------------------- #
class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    # Read-through cache of role truth. Only VALID_ROLES; [] for inert users.
    roles: Mapped[list] = mapped_column(JSONType, default=list)
    primary_role: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    overrides: Mapped[list] = mapped_column(JSONType, default=list)  # additive capability overrides
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    intern: Mapped[bool] = mapped_column(Boolean, default=False)
    title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Soft metadata (who invited them). Not a hard FK — avoids self-referential
    # insert-ordering constraints in batch seeding; it's informational only.
    invited_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_active: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # --- role sourcing (dev seed vs Azure AD groups) ---
    role_source: Mapped[str] = mapped_column(_enum(RoleSource), default=RoleSource.seed.value)
    azure_ad_object_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_role_sync: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


# --------------------------------------------------------------------------- #
# Program -> Project -> BOM -> Build
# --------------------------------------------------------------------------- #
class Program(Base, TimestampMixin):
    __tablename__ = "programs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    code: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    identifier: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    owner_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(_enum(ProgramStatus), default=ProgramStatus.active.value)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    customer: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    started: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    target: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    tags: Mapped[list] = mapped_column(JSONType, default=list)
    notify_on_equivalent_swap: Mapped[bool] = mapped_column(Boolean, default=True)


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    identifier: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    lead_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    # Nullable: a Project may be standalone (no Program). Structure != control.
    program_id: Mapped[Optional[str]] = mapped_column(ForeignKey("programs.id"), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(_enum(ProjectStatus), default=ProjectStatus.active.value)


class Bom(Base, TimestampMixin):
    __tablename__ = "boms"
    # Exactly one master BOM per Project.
    __table_args__ = (UniqueConstraint("project_id", name="one_master_bom_per_project"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    state: Mapped[str] = mapped_column(_enum(BomState), default=BomState.draft.value)
    version: Mapped[int] = mapped_column(Integer, default=1)
    owner_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    role: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    build_qty: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    overage: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_collection_id: Mapped[Optional[str]] = mapped_column(ForeignKey("collections.id"), nullable=True)
    partsbox_ref: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    validation: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)

    lines: Mapped[list["BomLine"]] = relationship(cascade="all, delete-orphan", back_populates="bom")


class BomLine(Base):
    __tablename__ = "bom_lines"
    __table_args__ = (UniqueConstraint("bom_id", "line_no", name="line_no_unique_per_bom"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bom_id: Mapped[str] = mapped_column(ForeignKey("boms.id"), nullable=False)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    mpn: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    mfr: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    qty: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    supplier: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    supplier_pn: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    unit_price: Mapped[Optional[float]] = mapped_column(Numeric(12, 4), nullable=True)
    ext_price: Mapped[Optional[float]] = mapped_column(Numeric(14, 4), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ex_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    source_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    replacement: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    cpn: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    bom: Mapped["Bom"] = relationship(back_populates="lines")


class BomVersion(Base):
    """Version-increment history for a master BOM. When Production applies a
    Push-Back recommendation, a row is written whose `reason` carries the
    recommendation snapshot — see Pushback.resolved_at_version_id."""
    __tablename__ = "bom_versions"
    __table_args__ = (UniqueConstraint("bom_id", "version", name="version_unique_per_bom"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    bom_id: Mapped[str] = mapped_column(ForeignKey("boms.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    reason: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)  # incl. applied recommendation snapshot
    actor_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Build(Base, TimestampMixin):
    __tablename__ = "builds"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    bom_id: Mapped[str] = mapped_column(ForeignKey("boms.id"), nullable=False)
    seq_no: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    build_qty: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Per-line overlay: {line_no: {state: used|skipped|deferred|rework, ...}}
    overlay: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    qr_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    actor_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)


# --------------------------------------------------------------------------- #
# Collections (Designer)
# --------------------------------------------------------------------------- #
class Collection(Base, TimestampMixin):
    __tablename__ = "collections"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    project_id: Mapped[Optional[str]] = mapped_column(ForeignKey("projects.id"), nullable=True)
    # Program is required for Designer Collections (CLAUDE.md). Nullable at the
    # column level to accommodate deferred dev collections; enforced in the app.
    program_id: Mapped[Optional[str]] = mapped_column(ForeignKey("programs.id"), nullable=True)
    state: Mapped[str] = mapped_column(_enum(CollectionState), default=CollectionState.active.value)
    owner_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    role: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    req_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    updated_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    items: Mapped[list["CollectionItem"]] = relationship(cascade="all, delete-orphan", back_populates="collection")


class CollectionItem(Base):
    __tablename__ = "collection_items"
    __table_args__ = (UniqueConstraint("collection_id", "line_no", name="line_no_unique_per_collection"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    collection_id: Mapped[str] = mapped_column(ForeignKey("collections.id"), nullable=False)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    mpn: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    mfr: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    qty: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    supplier: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    supplier_pn: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    unit_price: Mapped[Optional[float]] = mapped_column(Numeric(12, 4), nullable=True)
    ext_price: Mapped[Optional[float]] = mapped_column(Numeric(14, 4), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    collection: Mapped["Collection"] = relationship(back_populates="items")


# --------------------------------------------------------------------------- #
# Purchasing: requests (bucket entries), batches, CPN issuance
# --------------------------------------------------------------------------- #
class Request(Base, TimestampMixin):
    __tablename__ = "requests"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(_enum(RequestKind), nullable=False)
    source_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    source_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    project_id: Mapped[Optional[str]] = mapped_column(ForeignKey("projects.id"), nullable=True)
    from_user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    from_role: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    submitted: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    age: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    critical: Mapped[bool] = mapped_column(Boolean, default=False)
    bucket_state: Mapped[str] = mapped_column(_enum(BucketState), nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resubmit: Mapped[bool] = mapped_column(Boolean, default=False)
    # Items are frozen at submission time.
    items_snapshot: Mapped[Optional[list]] = mapped_column(JSONType, nullable=True)


class Batch(Base, TimestampMixin):
    __tablename__ = "batches"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    stream: Mapped[str] = mapped_column(_enum(BatchStream), nullable=False)
    state: Mapped[str] = mapped_column(_enum(BatchState), default=BatchState.pending.value)
    supplier: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    cart_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Supplier-side identifier for traceability: Mouser CartKey / DigiKey listId.
    # NEVER written to Josh's sheet in API-URL form (that would leak the API key).
    supplier_ref: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    item_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    written_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class CpnIssuance(Base, TimestampMixin):
    """Format-agnostic CPN records. The current format is a continuous-identifier
    chain (program.identifier-project.identifier-line, e.g. TVCA-R2-042);
    `format_version` lets the format evolve under Bounded Admin config."""
    __tablename__ = "cpn_issuance"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    cpn: Mapped[str] = mapped_column(String, nullable=False)
    scope: Mapped[str] = mapped_column(_enum(CpnScope), nullable=False)
    source_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    source_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    line_no: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    program_id: Mapped[Optional[str]] = mapped_column(ForeignKey("programs.id"), nullable=True)
    project_id: Mapped[Optional[str]] = mapped_column(ForeignKey("projects.id"), nullable=True)
    wall_location: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    format_version: Mapped[int] = mapped_column(Integer, default=1)
    fulfillment_state: Mapped[Optional[str]] = mapped_column(String, nullable=True)


# --------------------------------------------------------------------------- #
# Cross-workflow state: Push-Backs, notifications, comments, storage metadata
# --------------------------------------------------------------------------- #
class Pushback(Base, TimestampMixin):
    __tablename__ = "pushbacks"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    bom_id: Mapped[str] = mapped_column(ForeignKey("boms.id"), nullable=False)
    reason: Mapped[str] = mapped_column(_enum(PushbackReason), nullable=False)
    urgency: Mapped[str] = mapped_column(_enum(PushbackUrgency), default=PushbackUrgency.standard.value)
    from_user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    to_user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    state: Mapped[str] = mapped_column(_enum(PushbackState), default=PushbackState.open.value)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    loop: Mapped[Optional[int]] = mapped_column(Integer, default=1)
    flagged_lines: Mapped[Optional[list]] = mapped_column(JSONType, nullable=True)
    added_component_request: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    recommendation: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    # Explicit resolution linkage: the master-BOM version produced by applying
    # this Push-Back's recommendation (Production applies -> version increment).
    resolved_at_version_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("bom_versions.id"), nullable=True
    )


class Notification(Base, TimestampMixin):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    for_roles: Mapped[list] = mapped_column(JSONType, default=list)
    group: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    unread: Mapped[bool] = mapped_column(Boolean, default=True)
    kind: Mapped[str] = mapped_column(_enum(NotificationKind), default=NotificationKind.action.value)
    source_role: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    target_role: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    action_label: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    verb: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    who: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    when: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    entity_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    entity_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    type_label: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    routes: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)
    go: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)


class Comment(Base):
    """Polymorphic comment thread. Push-Back carries two levels (overall + per
    flagged line via line_no). Append-only — comments are never deleted."""
    __tablename__ = "comments"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[str] = mapped_column(String, nullable=False)
    thread_level: Mapped[str] = mapped_column(_enum(CommentThreadLevel), default=CommentThreadLevel.overall.value)
    line_no: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    role: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class StorageLocationMetadata(Base, TimestampMixin):
    """AutoBOM-side annotations on PartsBox storage locations. PartsBox owns the
    physical structure; this table only adds our tags/ownership."""
    __tablename__ = "storage_location_metadata"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    partsbox_location_ref: Mapped[str] = mapped_column(String, nullable=False)
    tags: Mapped[list] = mapped_column(JSONType, default=list)
    ownership: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    autobom_managed: Mapped[bool] = mapped_column(Boolean, default=False)


# --------------------------------------------------------------------------- #
# Admin / observability: audit, force-waivers, configuration, suppliers
# --------------------------------------------------------------------------- #
class Audit(Base):
    """Immutable audit log. Append-only — no update, no delete."""
    __tablename__ = "audit"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    ts: Mapped[Any] = mapped_column(String, nullable=True)  # prototype uses human strings ("Today 14:22")
    actor_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    role: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    action: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    entity_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    before: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    after: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    context: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)


class ForceWaiver(Base):
    __tablename__ = "force_waivers"
    __table_args__ = (
        CheckConstraint("length(reason) >= 10", name="reason_min_length"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    actor_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    target_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    target_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    context: Mapped[Optional[dict]] = mapped_column(JSONType, nullable=True)


class Configuration(Base, TimestampMixin):
    """Bounded-Admin config values, keyed. section groups them for the Admin UI."""
    __tablename__ = "configuration"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    section: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[Any] = mapped_column(JSONType, nullable=True)
    updated_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class Supplier(Base, TimestampMixin):
    """Supplier config (NOT API keys — those live in .env / Key Vault)."""
    __tablename__ = "suppliers"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    api_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    mode: Mapped[Optional[str]] = mapped_column(String, nullable=True)
