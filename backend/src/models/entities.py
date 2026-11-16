from sqlalchemy import (
    Column, Integer, String, Float, JSON, Text, ForeignKey, Date, UniqueConstraint, Index,
)
from src.config.database import Base


class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    email = Column(String(100), unique=True)
    password = Column(String(200))
    role = Column(String(20))


class Reader(Base):
    __tablename__ = 'readers'
    id = Column(Integer, primary_key=True)
    code = Column(String(60), unique=True, nullable=False)
    weekly_reading = Column(Float)
    completion = Column(Float)
    night_share = Column(Float)
    note = Column(Text, default='')


class Segment(Base):
    __tablename__ = 'segments'
    id = Column(Integer, primary_key=True)
    name = Column(String(100))
    k = Column(Integer)
    features = Column(JSON)
    state = Column(String(20), default='queued')
    result = Column(JSON)
    error = Column(Text, default='')
    # 资格依据在创建分群时冻结：所选自然周、完整权益版本、纳入/排除名单。
    week_start = Column(Date)
    week_end = Column(Date)
    entitlement_version = Column(Integer)
    qualification = Column(JSON)


class Outreach(Base):
    __tablename__ = 'outreaches'
    id = Column(Integer, primary_key=True)
    segment_id = Column(Integer, ForeignKey('segments.id'))
    cluster_id = Column(Integer)
    title = Column(String(100))
    note = Column(Text)
    members = Column(JSON)
    status = Column(String(20), default='draft')
    # 发送日决定可达名单；签核时按同一完整权益版本重算并冻结。
    send_date = Column(Date)
    entitlement_version = Column(Integer)
    entitlement_basis = Column(JSON)
    approved_by = Column(String(100))
    approved_at = Column(String(40))


class Audit(Base):
    __tablename__ = 'audits'
    id = Column(Integer, primary_key=True)
    actor = Column(String(100))
    action = Column(String(200))
    created = Column(String(40))


class SubscriptionBatch(Base):
    """一次订阅订单修订导入，待核验(pending) -> 生效(effective)。

    import_key 让同一次导入的重试直接取回原批次，不重复记账。
    坏行写入 rejected，不阻塞同批次的正常行。
    """
    __tablename__ = 'subscription_batches'
    id = Column(Integer, primary_key=True)
    name = Column(String(120), default='')
    import_key = Column(String(120), unique=True)
    state = Column(String(20), default='pending')
    submitted_by = Column(String(100))
    created = Column(String(40))
    verified_by = Column(String(100))
    verified_at = Column(String(40))
    total_rows = Column(Integer, default=0)
    accepted_rows = Column(Integer, default=0)
    duplicate_rows = Column(Integer, default=0)
    rejected_rows = Column(Integer, default=0)
    superseded_rows = Column(Integer, default=0)
    problem_rows = Column(Integer, default=0)
    rejected = Column(JSON)
    entitlement_version = Column(Integer)
    version_checksum = Column(String(64))


class SubscriptionEvent(Base):
    """订阅订单修订明细。

    (order_no, revision) 唯一：同一订单的同一修订只记一次账，内容不可变；
    (batch_id, line_no) 唯一：同一批次的同一行只记一次账。
    """
    __tablename__ = 'subscription_events'
    __table_args__ = (
        UniqueConstraint('order_no', 'revision', name='uq_event_order_revision'),
        UniqueConstraint('batch_id', 'line_no', name='uq_event_batch_line'),
        Index('ix_event_member', 'member_code'),
    )
    id = Column(Integer, primary_key=True)
    batch_id = Column(Integer, ForeignKey('subscription_batches.id'), nullable=False)
    line_no = Column(Integer, nullable=False)
    order_no = Column(String(80), nullable=False)
    member_code = Column(String(60), nullable=False)
    revision = Column(Integer, nullable=False)
    effective_start = Column(Date, nullable=False)
    effective_end = Column(Date, nullable=False)
    refunded_on = Column(Date)
    raw = Column(JSON)


class EntitlementVersion(Base):
    """权益版本台账。每次批次生效生成或复用一个完整快照版本。"""
    __tablename__ = 'entitlement_versions'
    id = Column(Integer, primary_key=True)
    version = Column(Integer, unique=True, nullable=False)
    batch_id = Column(Integer, ForeignKey('subscription_batches.id'))
    created = Column(String(40))
    checksum = Column(String(64))
    members = Column(Integer, default=0)
    ranges = Column(Integer, default=0)


class EntitlementSnapshot(Base):
    """某个权益版本下的合并后有效区间（退款截断、重叠合并之后）。"""
    __tablename__ = 'entitlement_snapshots'
    __table_args__ = (
        UniqueConstraint('version', 'member_code', 'start_date', name='uq_snapshot_version_member_start'),
        Index('ix_snapshot_member_range', 'member_code', 'start_date', 'end_date'),
    )
    id = Column(Integer, primary_key=True)
    version = Column(Integer, nullable=False, index=True)
    member_code = Column(String(60), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    days = Column(Integer, nullable=False)
    source_orders = Column(JSON)
