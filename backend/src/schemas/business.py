from datetime import date
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class Login(BaseModel):
    email: str
    password: str


class ReaderInput(BaseModel):
    code: str = Field(min_length=1, max_length=60)
    weekly_reading: float = Field(ge=0, le=1000, allow_inf_nan=False)
    completion: float = Field(ge=0, le=1, allow_inf_nan=False)
    night_share: float = Field(ge=0, le=1, allow_inf_nan=False)
    note: str = Field(default='', max_length=1000)


class SegmentInput(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    k: int = Field(default=3, ge=2, le=6)
    features: list[Literal['weekly_reading', 'completion', 'night_share']] = Field(
        default=['weekly_reading', 'completion', 'night_share'], min_length=2, max_length=3
    )
    week_start: Optional[date] = None
    entitlement_version: Optional[int] = Field(default=None, gt=0)

    @field_validator('features')
    @classmethod
    def unique(cls, v):
        if len(set(v)) != len(v):
            raise ValueError('特征不能重复')
        return v


class OutreachInput(BaseModel):
    segment_id: int = Field(gt=0)
    cluster_id: int = Field(ge=0, le=5)
    title: str = Field(min_length=2, max_length=100)
    note: str = Field(min_length=8, max_length=2000)
    send_date: Optional[date] = None


class SubscriptionRow(BaseModel):
    """订阅订单修订的单行契约；坏行由此模型的校验结果隔离。"""
    order_no: str = Field(min_length=1, max_length=80)
    member_code: str = Field(min_length=1, max_length=60)
    revision: int = Field(ge=1, le=1_000_000)
    effective_start: date
    effective_end: date
    refunded_on: Optional[date] = None

    @model_validator(mode='after')
    def ordered(self):
        if self.effective_end < self.effective_start:
            raise ValueError('有效结束日早于开始日')
        return self


class BatchInput(BaseModel):
    name: str = Field(default='', max_length=120)
    import_key: Optional[str] = Field(default=None, min_length=1, max_length=120)
    # 行先按任意值接收，非对象/字段不合法的行在导入时逐行隔离，而不是整批失败。
    rows: list[Any] = Field(min_length=1, max_length=5000)
