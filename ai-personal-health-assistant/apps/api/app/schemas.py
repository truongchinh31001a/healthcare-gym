from datetime import date, datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from health_core.body_progress.schema import FIELDS


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Register(Input):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    adult_attestation: Literal[True]


class Login(Input):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    client: Literal["mobile", "web"] = "mobile"


class Reauthenticate(Input):
    password: str = Field(min_length=1, max_length=128)


Purpose = Literal["health_data_processing", "document_processing", "body_image_processing", "admin_support", "research_training"]


class ConsentInput(Input):
    purpose: Purpose
    granted: bool


class Profile(Input):
    version: int = Field(default=0, ge=0)
    display_name: str = Field(min_length=1, max_length=100)
    birth_date: date
    height_cm: float = Field(ge=80, le=250)
    gender: Literal["male", "female", "unspecified"] = "unspecified"
    timezone: str = "Asia/Bangkok"

    @field_validator("birth_date")
    @classmethod
    def adult_only(cls, value):
        today = datetime.now(timezone.utc).date()
        age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
        if age < 18 or age > 120:
            raise ValueError("This module supports self-declared adults aged 18–120")
        return value

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Use an IANA timezone")
        return value


TriState = Literal["unknown", "no", "yes"]


class HealthContext(Input):
    version: int = Field(default=0, ge=0)
    pregnancy: TriState = "unknown"
    eating_disorder_risk: TriState = "unknown"
    clinician_restrictions: TriState = "unknown"
    acute_red_flags: TriState = "unknown"
    notes: str = Field(default="", max_length=2000)


class Value(Input):
    field: str
    value: float = Field(strict=True, ge=-1_000_000, le=1_000_000)
    unit: str

    @field_validator("value", mode="before")
    @classmethod
    def not_boolean(cls, value):
        if isinstance(value, bool):
            raise ValueError("Expected a measurement number")
        return value

    @field_validator("field")
    @classmethod
    def known_field(cls, value):
        if value not in FIELDS:
            raise ValueError("Unknown measurement field")
        return value


class MeasurementInput(Input):
    measured_at: datetime
    values: list[Value] = Field(min_length=1, max_length=14)
    device_id: str = Field(min_length=1, max_length=80)
    device_model: str = Field(min_length=1, max_length=80)
    protocol_id: str = Field(min_length=1, max_length=80)
    measurement_method: Literal["scale", "tape", "device_report"]

    @field_validator("measured_at")
    @classmethod
    def timestamp_with_offset(cls, value):
        if value.tzinfo is None or value > datetime.now(timezone.utc):
            raise ValueError("Measurement time needs an offset and must not be in the future")
        return value


class Revision(Input):
    value: float = Field(strict=True, ge=-1_000_000, le=1_000_000)
    unit: str
    reason: str = Field(min_length=5, max_length=500)


class Transcription(Input):
    values: list[Value] = Field(min_length=1, max_length=9)
    measured_on: date | None = None
    device_id: str = Field(min_length=1, max_length=80)
    device_model: str = Field(min_length=1, max_length=80)
    protocol_id: str = Field(min_length=1, max_length=80)

    @field_validator("measured_on")
    @classmethod
    def past_date(cls, value):
        if value and value > datetime.now(timezone.utc).date():
            raise ValueError("Report date must not be in the future")
        return value


class ConfirmDraft(Input):
    version: int = Field(ge=1)
    selected_fields: list[str] = Field(min_length=1, max_length=9)
    corrections: dict[str, float] = Field(default_factory=dict)
    acknowledged_flags: list[str] = Field(default_factory=list, max_length=100)
    checked_original: Literal[True]

    @field_validator("corrections")
    @classmethod
    def bounded_corrections(cls, values):
        if any(abs(value) > 1_000_000 for value in values.values()):
            raise ValueError("Correction exceeds the numeric storage limit")
        return values


class GoalInput(Input):
    target_weight_kg: float = Field(ge=20, le=400)
    weeks: int = Field(ge=1, le=104)
    approved_by_user: Literal[True]
    weight_stream_id: str | None = Field(default=None, min_length=20, max_length=20)


class GoalRevision(GoalInput):
    version: int = Field(ge=1)
    reason: str = Field(min_length=5, max_length=500)
