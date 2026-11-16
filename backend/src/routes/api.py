import json,os
import redis
from fastapi import APIRouter,Depends,HTTPException,Response
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from src.config.database import db
from src.models.entities import (
    User,Reader,Segment,Outreach,Audit,SubscriptionBatch,EntitlementVersion,EntitlementSnapshot,
)
from src.schemas.business import Login,ReaderInput,SegmentInput,OutreachInput,BatchInput
from src.middlewares.auth import current,editor,admin
from src.utils.security import verify,token
from src.services.business import audit,dump
from src.controllers.business import ensure_segment
from src.services.entitlement import default_week,week_bounds,week_start_of,snapshot_for_version
from src.services.batch import import_batch,verify_batch,batch_detail,now_iso,BatchConflict
from src.services.qualification import qualify,resolve_version,build_reachability,default_send_date
router=APIRouter()
@router.post('/auth/login')
def login(data:Login,s=Depends(db)):
 u=s.query(User).filter_by(email=data.email).first()
 if not u or not verify(data.password,u.password):raise HTTPException(401,'账号或密码错误')
 return {'token':token(u),'user':dump(u)}
@router.get('/me')
def me(u=Depends(current)):return dump(u)
@router.get('/readers')
def readers(u=Depends(current),s=Depends(db)):return [dump(r) for r in s.query(Reader).order_by(Reader.id).all()]
@router.post('/readers')
def create(data:ReaderInput,u=Depends(editor),s=Depends(db)):
 r=Reader(**data.model_dump());s.add(r)
 try:s.commit()
 except IntegrityError:s.rollback();raise HTTPException(409,'会员编号重复')
 audit(s,u,'录入阅读档案 '+r.code);return dump(r)
@router.put('/readers/{i}')
def edit(i:int,data:ReaderInput,u=Depends(editor),s=Depends(db)):
 r=s.get(Reader,i)
 if not r:raise HTTPException(404,'会员档案不存在')
 for k,v in data.model_dump().items():setattr(r,k,v)
 try:s.commit()
 except IntegrityError:s.rollback();raise HTTPException(409,'会员编号重复')
 audit(s,u,'修订档案 '+str(i));return dump(r)

# ---------- 订阅订单修订与权益版本 ----------
@router.get('/batches')
def batches(u=Depends(current),s=Depends(db)):
 return [batch_detail(s,b) for b in s.query(SubscriptionBatch).order_by(SubscriptionBatch.id.desc()).all()]
@router.get('/batches/{i}')
def batch_one(i:int,u=Depends(current),s=Depends(db)):
 b=s.get(SubscriptionBatch,i)
 if not b:raise HTTPException(404,'批次不存在')
 return batch_detail(s,b)
@router.post('/batches')
def create_batch(data:BatchInput,u=Depends(editor),s=Depends(db)):
 try:b,created=import_batch(s,data,u.email)
 except BatchConflict as e:raise HTTPException(409,str(e))
 audit(s,u,('导入订阅批次 ' if created else '重复提交订阅批次 ')+str(b.id))
 return batch_detail(s,b)
@router.post('/batches/{i}/verify')
def verify_batch_route(i:int,u=Depends(admin),s=Depends(db)):
 b=s.get(SubscriptionBatch,i)
 if not b:raise HTTPException(404,'批次不存在')
 if b.state=='effective':raise HTTPException(409,'批次已生效，不能重复核验')
 if b.state!='pending':raise HTTPException(409,'只有待核验批次可以生效')
 try:verify_batch(s,b,u.email)
 except BatchConflict as e:raise HTTPException(409,str(e))
 except ValueError as e:raise HTTPException(422,str(e))
 audit(s,u,'核验订阅批次生效 '+str(i)+' → 权益版本 v'+str(b.entitlement_version))
 return batch_detail(s,b)

@router.get('/entitlements')
def entitlements(u=Depends(current),s=Depends(db)):
 return [dump(v) for v in s.query(EntitlementVersion).order_by(EntitlementVersion.version.desc()).all()]
@router.get('/entitlements/{version}')
def entitlement_one(version:int,u=Depends(current),s=Depends(db)):
 v=s.query(EntitlementVersion).filter_by(version=version).first()
 if not v:raise HTTPException(404,'权益版本不存在')
 rows=s.query(EntitlementSnapshot).filter_by(version=version).order_by(EntitlementSnapshot.member_code,EntitlementSnapshot.start_date).all()
 return {**dump(v),'ranges':[{'member_code':r.member_code,'start':r.start_date.isoformat(),'end':r.end_date.isoformat(),'days':r.days,'orders':r.source_orders} for r in rows]}
@router.get('/entitlements/{version}/members/{code}')
def entitlement_member(version:int,code:str,u=Depends(current),s=Depends(db)):
 v=s.query(EntitlementVersion).filter_by(version=version).first()
 if not v:raise HTTPException(404,'权益版本不存在')
 ranges=snapshot_for_version(s,version).get(code,[])
 return {'member_code':code,'version':version,'ranges':[{'start':r['start'].isoformat(),'end':r['end'].isoformat(),'days':r['days'],'orders':r['orders']} for r in ranges]}

# ---------- 分群 ----------
@router.get('/segments')
def segments(u=Depends(current),s=Depends(db)):return [dump(r) for r in s.query(Segment).order_by(Segment.id.desc()).all()]
@router.post('/segments')
def train(data:SegmentInput,u=Depends(editor),s=Depends(db)):
 week_start=week_start_of(data.week_start or default_week());week_end=week_bounds(week_start)[1]
 version=resolve_version(s,data.entitlement_version)
 included,excluded,basis=qualify(s,week_start,version)
 codes={row['code'] for row in included}
 rows=[dump(r) for r in s.query(Reader).order_by(Reader.id).all() if r.code in codes]
 if len(rows)<=data.k:raise HTTPException(422,f'该自然周整周有权益的会员仅{len(rows)}位，不足以形成k={data.k}个群组')
 payload={k:v for k,v in data.model_dump().items() if k not in ('week_start','entitlement_version')}
 r=Segment(**payload,week_start=week_start,week_end=week_end,entitlement_version=version.version,qualification=basis,result={'snapshot':rows})
 s.add(r);s.commit()
 try:redis.Redis.from_url(os.environ['REDIS_URL']).rpush('reader:segments',r.id)
 except redis.RedisError:r.state='failed';r.error='队列暂不可用，请稍后重试';s.commit();raise HTTPException(503,r.error)
 audit(s,u,'提交分群 '+str(r.id)+'（周'+week_start.isoformat()+'，权益版本 v'+str(version.version)+'）');return dump(r)
@router.get('/segments/{i}')
def detail(i:int,u=Depends(current),s=Depends(db)):return dump(ensure_segment(s,i))
@router.get('/segments/{i}/qualification')
def qualification(i:int,u=Depends(current),s=Depends(db)):
 r=ensure_segment(s,i)
 return r.qualification or {'included':[],'excluded':[],'counts':{'included':0,'excluded':0}}
@router.get('/segments/{i}/export')
def export(i:int,u=Depends(current),s=Depends(db)):
 r=ensure_segment(s,i)
 if r.state!='done':raise HTTPException(409,'仅成功分群可导出')
 body={**dump(r),'qualification':r.qualification}
 return Response(json.dumps(body,ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="reader-segments-{i}.json"'})

# ---------- 触达 ----------
@router.get('/outreaches')
def outreaches(u=Depends(current),s=Depends(db)):return [dump(r) for r in s.query(Outreach).order_by(Outreach.id.desc()).all()]
@router.post('/outreaches')
def outreach(data:OutreachInput,u=Depends(editor),s=Depends(db)):
 r=ensure_segment(s,data.segment_id)
 if r.state!='done':raise HTTPException(409,'分群完成后才能制定触达方案')
 if not any(m['cluster_id']==data.cluster_id for m in r.result.get('members',[])):raise HTTPException(422,'该版本没有所选群组')
 send=data.send_date or default_send_date()
 version=resolve_version(s,None)
 members,excluded,basis=build_reachability(s,r,data.cluster_id,send,version)
 payload={k:v for k,v in data.model_dump().items() if k!='send_date'}
 o=Outreach(**payload,send_date=send,entitlement_version=version.version,entitlement_basis=basis,members=members)
 s.add(o);s.commit();audit(s,u,'起草触达方案 '+str(o.id)+'（发送日'+send.isoformat()+'，权益版本 v'+str(version.version)+'）');return dump(o)
@router.post('/outreaches/{i}/refresh')
def refresh(i:int,u=Depends(editor),s=Depends(db)):
 o=s.get(Outreach,i)
 if not o:raise HTTPException(404,'触达方案不存在')
 if o.status!='draft':raise HTTPException(409,'已签核名单不可重算')
 send=o.send_date or default_send_date();version=resolve_version(s,None)
 members,excluded,basis=build_reachability(s,ensure_segment(s,o.segment_id),o.cluster_id,send,version)
 changed=s.execute(update(Outreach).where(Outreach.id==i,Outreach.status=='draft').values(members=members,entitlement_version=version.version,entitlement_basis=basis))
 if changed.rowcount!=1:
  s.rollback();raise HTTPException(409,'方案已签核，名单不可重算')
 s.commit();audit(s,u,'重算触达可达名单 '+str(i));return dump(s.get(Outreach,i))
@router.post('/outreaches/{i}/approve')
def approve(i:int,u=Depends(admin),s=Depends(db)):
 o=s.get(Outreach,i)
 if not o:raise HTTPException(404,'触达方案不存在')
 if o.status!='draft':raise HTTPException(409,'已签核方案不可重复签核')
 send=o.send_date or default_send_date()
 version=resolve_version(s,None)
 members,excluded,basis=build_reachability(s,ensure_segment(s,o.segment_id),o.cluster_id,send,version)
 stamp=now_iso()
 changed=s.execute(update(Outreach).where(Outreach.id==i,Outreach.status=='draft').values(
  members=members,entitlement_version=version.version,entitlement_basis=basis,
  status='approved',approved_by=u.email,approved_at=stamp))
 if changed.rowcount!=1:
  s.rollback();raise HTTPException(409,'方案已被其他请求签核，请刷新后查看')
 s.commit();audit(s,u,'签核触达方案 '+str(i)+'（冻结'+str(len(members))+'位，权益版本 v'+str(version.version)+'）')
 return dump(s.get(Outreach,i))
@router.get('/outreaches/{i}/export')
def export_outreach(i:int,u=Depends(current),s=Depends(db)):
 r=s.get(Outreach,i)
 if not r:raise HTTPException(404,'触达方案不存在')
 body={**dump(r),'entitlement_basis':r.entitlement_basis}
 return Response(json.dumps(body,ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="reader-outreach-{i}.json"'})
@router.get('/audits')
def audits(u=Depends(admin),s=Depends(db)):return [dump(r) for r in s.query(Audit).order_by(Audit.id.desc()).limit(100)]
