import re
import unicodedata
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class PhoneRequest(RequestModel):
    phone: str = Field(min_length=8, max_length=20)

    @field_validator("phone")
    @classmethod
    def phone_format(cls, value: str):
        value = value.strip()
        if re.fullmatch(r"1[0-9]{10}", value):
            value = "+86" + value
        if not re.fullmatch(r"\+[1-9][0-9]{7,14}", value):
            raise ValueError("使用国际区号手机号，例如 +8613800000000")
        return value


class OTPVerify(PhoneRequest):
    code: str = Field(pattern=r"^[0-9]{6}$")
    challenge_id: UUID | None = None
    device_label: str = Field(default="", max_length=100)


class RefreshRequest(RequestModel):
    refresh_token: str = Field(min_length=30, max_length=300)


class PersonaStyle(RequestModel):
    address_user: str = Field(default="您", min_length=1, max_length=40)
    sentence_length: Literal["short", "medium"] = "short"
    warmth: Literal["low", "medium", "high"] = "high"
    humor: Literal["none", "light"] = "light"
    preferred_phrases: list[str] = Field(default_factory=list, max_length=10)
    avoided_phrases: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("preferred_phrases", "avoided_phrases")
    @classmethod
    def phrase_lengths(cls, values):
        if any(not value.strip() or len(value) > 100 for value in values):
            raise ValueError("短语须为1—100字")
        return values


class PersonaCreate(RequestModel):
    display_name: str = Field(min_length=1, max_length=40)
    avatar_asset_id: UUID | None = None
    relationship_reference: str = Field(default="", max_length=200)
    style: PersonaStyle = Field(default_factory=PersonaStyle)
    examples: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("display_name")
    @classmethod
    def name_not_blank(cls, value):
        if not value.strip():
            raise ValueError("人物名称不能为空")
        return value

    @field_validator("examples")
    @classmethod
    def example_lengths(cls, values):
        if any(not value.strip() or len(value) > 500 for value in values):
            raise ValueError("例句须为1—500字")
        return values


class PersonaPatch(RequestModel):
    style_version: int = Field(gt=0)
    display_name: str | None = Field(default=None, min_length=1, max_length=40)
    avatar_asset_id: UUID | None = None
    relationship_reference: str | None = Field(default=None, max_length=200)
    style: PersonaStyle | None = None
    examples: list[str] | None = Field(default=None, max_length=30)

    @field_validator("display_name")
    @classmethod
    def name_not_blank(cls, value):
        if value is not None and not value.strip():
            raise ValueError("人物名称不能为空")
        return value

    @field_validator("examples")
    @classmethod
    def example_lengths(cls, values):
        if values is not None and any(not value.strip() or len(value) > 500 for value in values):
            raise ValueError("例句须为1—500字")
        return values


class ConversationCreate(RequestModel):
    persona_id: UUID


def normalize_text(value: str):
    value = unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))
    if not value.strip():
        raise ValueError("消息不能为空")
    return value


class RunCreate(RequestModel):
    client_message_id: UUID
    text: str = Field(min_length=1, max_length=2000)

    _normalize = field_validator("text")(normalize_text)


class PreviewCreate(RequestModel):
    client_message_id: UUID
    sample_question: str = Field(min_length=1, max_length=2000)

    _normalize = field_validator("sample_question")(normalize_text)


class RetryRequest(RequestModel):
    client_message_id: UUID


class RevisionRequest(RequestModel):
    revision: int = Field(gt=0)


class MemoryEdit(RevisionRequest):
    content: str = Field(min_length=1, max_length=500)

    _normalize = field_validator("content")(normalize_text)


class ResetRequest(RequestModel):
    confirm: Literal[True]
