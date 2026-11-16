import random
from datetime import date,timedelta
from src.config.database import Base,engine,Session
from src.models.entities import (
 User,Reader,SubscriptionBatch,SubscriptionEvent,EntitlementSnapshot,EntitlementVersion,
)
from src.utils.security import hash_password
from src.services.entitlement import build_snapshot

SEED_WEEK=date(2026,11,9)

def _ensure_entitlements(s):
 """自然键幂等：已有生效批次则不重复导入或生成版本。"""
 if s.query(EntitlementVersion).first():return
 start=SEED_WEEK-timedelta(days=60);end=SEED_WEEK+timedelta(days=60)
 batch=SubscriptionBatch(name='演示订阅订单基线',import_key='seed-entitlements-v1',state='pending',submitted_by='seed',created='2026-11-09T00:00:00+00:00',total_rows=0,rejected=[])
 s.add(batch);s.flush()
 rows=[]
 for i in range(240):
  code=f'SL-{i+1:03}'
  rows.append(dict(order_no=f'ORD-{i+1:03}',member_code=code,revision=1,effective_start=start,effective_end=end,refunded_on=None))
 # 覆盖退款截断、重叠订阅、迟到修订三类样本。
 rows.append(dict(order_no='ORD-003',member_code='SL-003',revision=2,effective_start=start,effective_end=end,refunded_on=SEED_WEEK+timedelta(days=10)))
 rows.append(dict(order_no='ORD-004B',member_code='SL-004',revision=1,effective_start=SEED_WEEK+timedelta(days=30),effective_end=SEED_WEEK+timedelta(days=100),refunded_on=None))
 rows.append(dict(order_no='ORD-005',member_code='SL-005',revision=3,effective_start=SEED_WEEK+timedelta(days=3),effective_end=SEED_WEEK+timedelta(days=20),refunded_on=None))
 rows.append(dict(order_no='ORD-006',member_code='SL-006',revision=2,effective_start=SEED_WEEK+timedelta(days=2),effective_end=SEED_WEEK+timedelta(days=9),refunded_on=None))
 rows.append(dict(order_no='ORD-007',member_code='SL-007',revision=2,effective_start=SEED_WEEK,effective_end=SEED_WEEK+timedelta(days=3),refunded_on=None))
 batch.total_rows=len(rows)
 for line_no,row in enumerate(rows,start=1):
  s.add(SubscriptionEvent(batch_id=batch.id,line_no=line_no,order_no=row['order_no'],member_code=row['member_code'],revision=row['revision'],effective_start=row['effective_start'],effective_end=row['effective_end'],refunded_on=row['refunded_on'],raw={**row,'effective_start':row['effective_start'].isoformat(),'effective_end':row['effective_end'].isoformat(),'refunded_on':row['refunded_on'].isoformat() if row['refunded_on'] else None}))
 batch.accepted_rows=len(rows);batch.state='effective';batch.verified_by='seed';batch.verified_at='2026-11-09T00:00:00+00:00'
 s.flush()
 snapshot,checksum=build_snapshot(s.query(SubscriptionEvent).all())
 version=EntitlementVersion(version=1,batch_id=batch.id,created=batch.verified_at,checksum=checksum,members=len({r['member_code'] for r in snapshot}),ranges=len(snapshot))
 s.add(version);s.flush()
 for r in snapshot:
  s.add(EntitlementSnapshot(version=1,member_code=r['member_code'],start_date=r['start_date'],end_date=r['end_date'],days=r['days'],source_orders=r['source_orders']))
 batch.entitlement_version=1;batch.version_checksum=checksum

def seed():
 Base.metadata.create_all(engine);rng=random.Random(3107)
 with Session() as s:
  for role in ('admin','analyst','viewer'):
   email=role+'@demo.local'
   if not s.query(User).filter_by(email=email).first():s.add(User(email=email,role=role,password=hash_password('Demo123!')))
  for i in range(240):
   code=f'SL-{i+1:03}';mode=i//80
   reading=round(max(0,rng.gauss([4,14,26][mode],[1.1,3,4][mode])),2)
   completion=round(max(0,min(1,rng.gauss([.32,.81,.61][mode],.06))),4)
   night=round(max(0,min(1,rng.gauss([.18,.23,.77][mode],.08))),4)
   if not s.query(Reader).filter_by(code=code).first():s.add(Reader(code=code,weekly_reading=reading,completion=completion,night_share=night,note='最近完整自然周行为聚合；模拟会员，不含个人联系方式'))
  _ensure_entitlements(s)
  s.commit();print({'users':s.query(User).count(),'readers':s.query(Reader).count(),'versions':s.query(EntitlementVersion).count()})
if __name__=='__main__':seed()
