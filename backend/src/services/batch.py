"""订阅订单修订导入：坏行隔离、按批次记账、待核验到生效。"""
from datetime import datetime, timezone

from pydantic import ValidationError
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from src.models.entities import SubscriptionBatch, SubscriptionEvent
from src.schemas.business import SubscriptionRow
from src.services.entitlement import create_version, entitlement_lock, key_lock

MAX_REPORTED_BAD_ROWS = 200


class BatchConflict(Exception):
    """批次或幂等键状态冲突，映射为 409。"""


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def _event_payload(event):
    return {
        'order_no': event.order_no,
        'member_code': event.member_code,
        'revision': event.revision,
        'effective_start': event.effective_start.isoformat(),
        'effective_end': event.effective_end.isoformat(),
        'refunded_on': event.refunded_on.isoformat() if event.refunded_on else None,
    }


def _reason(error):
    if isinstance(error, ValidationError):
        parts = []
        for item in error.errors():
            field = '.'.join(str(x) for x in item.get('loc', ())) or '记录'
            parts.append(f'{field}: {item.get("msg")}')
        return '；'.join(parts)
    return str(error)


def import_batch(s, data, actor):
    """写入一个待核验批次。返回 (batch, created)。

    import_key 相同且批次已存在时取回原批次：已生效则不再处理，
    仍待核验时按同一份行重放，已记账的行不会重复记账。
    计数每次从库内实况重建，因此中途失败后重试仍得到相同结果。

    同一 import_key 的并发提交按幂等键串行化：后到者在前者提交后
    看到完整批次，不会各自基于半成品返回不同计数。
    """
    if not data.import_key:
        return _import_batch(s, data, actor)
    with key_lock(s, data.import_key):
        return _import_batch(s, data, actor)


def _import_batch(s, data, actor):
    created = False
    existing = None
    if data.import_key:
        existing = s.query(SubscriptionBatch).filter_by(import_key=data.import_key).first()
        if existing and existing.state != 'pending':
            return existing, False

    if existing is None:
        batch = SubscriptionBatch(
            name=data.name,
            import_key=data.import_key,
            state='pending',
            submitted_by=actor,
            created=now_iso(),
            total_rows=len(data.rows),
            rejected=[],
        )
        s.add(batch)
        try:
            s.flush()
        except IntegrityError:
            # 未走幂等键锁时的兜底：并发已写入同一 import_key，取回对方批次。
            s.rollback()
            existing = s.query(SubscriptionBatch).filter_by(import_key=data.import_key).first()
            if existing:
                return existing, False
            raise
        created = True
    else:
        batch = existing
        if batch.total_rows != len(data.rows):
            raise BatchConflict(
                f'导入幂等键 {batch.import_key} 首次提交 {batch.total_rows} 行，本次 {len(data.rows)} 行；'
                '同一幂等键只能重放同一份行'
            )
        _assert_replay_matches(s, batch, data.rows)
        created = False

    # 从零重建本批次的解析结果，让重放/重试幂等。
    batch.accepted_rows = 0
    batch.duplicate_rows = 0
    batch.rejected_rows = 0
    batch.rejected = []
    recorded = {
        event.line_no
        for event in s.query(SubscriptionEvent).filter_by(batch_id=batch.id).all()
    }

    for line_no, raw in enumerate(data.rows, start=1):
        if not isinstance(raw, dict):
            _reject(batch, line_no, '每一行必须是包含订单号、会员编号、修订号与有效起止日的对象', raw)
            continue
        try:
            row = SubscriptionRow.model_validate(raw)
        except ValidationError as error:
            _reject(batch, line_no, _reason(error), raw)
            continue

        if line_no in recorded:
            # 该行已在同一批次的早前尝试中写入。重放必须是同一份内容，
            # 否则视为换了输入却复用幂等键；已记账行本身不重复记账。
            stored_line = s.query(SubscriptionEvent).filter_by(
                batch_id=batch.id, line_no=line_no
            ).one()
            if _event_payload(stored_line) != _row_payload(row):
                raise BatchConflict(f'第 {line_no} 行与幂等键首次提交的内容不一致')
            continue

        stored = s.query(SubscriptionEvent).filter_by(
            order_no=row.order_no, revision=row.revision
        ).first()
        if stored:
            if _event_payload(stored) == _row_payload(row):
                batch.duplicate_rows += 1
            else:
                _reject(
                    batch, line_no,
                    f'订单 {row.order_no} 的修订 {row.revision} 已记账且内容不同，修订不可变',
                    raw,
                )
            continue

        event = SubscriptionEvent(
            batch_id=batch.id,
            line_no=line_no,
            order_no=row.order_no,
            member_code=row.member_code,
            revision=row.revision,
            effective_start=row.effective_start,
            effective_end=row.effective_end,
            refunded_on=row.refunded_on,
            raw=raw,
        )
        try:
            with s.begin_nested():
                s.add(event)
                s.flush()
        except IntegrityError:
            # 唯一键冲突：同订单同修订已由并发导入写入，按重复处理，不重复记账。
            batch.duplicate_rows += 1
            continue

    batch.accepted_rows = s.query(SubscriptionEvent).filter_by(batch_id=batch.id).count()
    _count_problems(s, batch)
    s.commit()
    s.refresh(batch)
    return batch, created


def _assert_replay_matches(s, batch, rows):
    """重放前先整体核对已记账行，避免部分写入后才在循环中途报冲突。"""
    recorded = {
        event.line_no: event
        for event in s.query(SubscriptionEvent).filter_by(batch_id=batch.id).all()
    }
    for line_no, raw in enumerate(rows, start=1):
        stored = recorded.get(line_no)
        if not stored or not isinstance(raw, dict):
            continue
        try:
            row = SubscriptionRow.model_validate(raw)
        except ValidationError:
            # 首次提交时该行就是坏行，重放仍按坏行处理。
            continue
        if _event_payload(stored) != _row_payload(row):
            raise BatchConflict(f'第 {line_no} 行与幂等键首次提交的内容不一致')


def _row_payload(row):
    return {
        'order_no': row.order_no,
        'member_code': row.member_code,
        'revision': row.revision,
        'effective_start': row.effective_start.isoformat(),
        'effective_end': row.effective_end.isoformat(),
        'refunded_on': row.refunded_on.isoformat() if row.refunded_on else None,
    }


def _reject(batch, line_no, reason, raw):
    batch.rejected_rows += 1
    rejected = list(batch.rejected or [])
    if len(rejected) < MAX_REPORTED_BAD_ROWS:
        rejected.append({'line': line_no, 'reason': reason, 'raw': raw})
    batch.rejected = rejected


def _count_problems(s, batch):
    """problem_rows：坏行 + 已被更高修订取代的行，供页面展示。"""
    events = s.query(SubscriptionEvent).filter_by(batch_id=batch.id).all()
    latest = {}
    for event in events:
        current = latest.get(event.order_no)
        if current is None or event.revision > current.revision:
            latest[event.order_no] = event
    batch.superseded_rows = len(events) - len(latest)
    batch.problem_rows = batch.rejected_rows + batch.superseded_rows


def verify_batch(s, batch, actor):
    """待核验 -> 生效，生成或复用完整权益版本。

    条件更新保证并发核验只有一次生效；已生效批次直接返回，不重新记账。
    """
    with entitlement_lock(s):
        s.refresh(batch)
        if batch.state == 'effective':
            return batch
        if batch.state != 'pending':
            raise ValueError('只有待核验批次可以生效')

        if not s.query(SubscriptionEvent).filter_by(batch_id=batch.id).count():
            raise ValueError('批次没有可生效的有效行')

        stamp = now_iso()
        transitioned = s.execute(
            update(SubscriptionBatch)
            .where(SubscriptionBatch.id == batch.id, SubscriptionBatch.state == 'pending')
            .values(state='effective', verified_by=actor, verified_at=stamp)
        )
        if transitioned.rowcount != 1:
            s.rollback()
            raise BatchConflict('批次已被其他请求核验，请刷新后查看')
        s.flush()

        version = create_version(s, batch.id, stamp)
        s.execute(
            update(SubscriptionBatch)
            .where(SubscriptionBatch.id == batch.id)
            .values(entitlement_version=version.version, version_checksum=version.checksum)
        )
        s.flush()
        s.refresh(batch)
        _count_problems(s, batch)
        s.commit()
        return batch


def batch_detail(s, batch):
    events = (
        s.query(SubscriptionEvent)
        .filter_by(batch_id=batch.id)
        .order_by(SubscriptionEvent.line_no)
        .all()
    )
    latest = {}
    for event in events:
        current = latest.get(event.order_no)
        if current is None or event.revision > current.revision:
            latest[event.order_no] = event
    return {
        'id': batch.id,
        'name': batch.name,
        'import_key': batch.import_key,
        'state': batch.state,
        'submitted_by': batch.submitted_by,
        'created': batch.created,
        'verified_by': batch.verified_by,
        'verified_at': batch.verified_at,
        'total_rows': batch.total_rows,
        'accepted_rows': batch.accepted_rows,
        'duplicate_rows': batch.duplicate_rows,
        'rejected_rows': batch.rejected_rows,
        'superseded_rows': batch.superseded_rows,
        'problem_rows': batch.problem_rows,
        'rejected': batch.rejected or [],
        'entitlement_version': batch.entitlement_version,
        'version_checksum': batch.version_checksum,
        'events': [
            {
                'line': event.line_no,
                'order_no': event.order_no,
                'member_code': event.member_code,
                'revision': event.revision,
                'effective_start': event.effective_start.isoformat(),
                'effective_end': event.effective_end.isoformat(),
                'refunded_on': event.refunded_on.isoformat() if event.refunded_on else None,
                'is_latest': latest[event.order_no].id == event.id,
            }
            for event in events
        ],
    }
