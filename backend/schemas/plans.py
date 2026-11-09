"""Data validation schemas for plans."""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class TrimmedInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)


class ConfigUpdateRequest(BaseModel):
    gemini_api_key: Optional[str] = Field(default=None, description="Google Gemini API Key")
    database_url: Optional[str] = Field(
        default=None,
        description="Chuỗi kết nối Supabase PostgreSQL (postgresql://... hoặc postgres://...)",
    )
    clear_api_key: bool = False
    clear_database_url: bool = False


class GeneratePlanRequest(TrimmedInput):
    title: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Tên kế hoạch tùy chọn do người dùng đặt (nếu để trống AI sẽ tự đặt)",
    )
    plan_type: Literal["meal", "hangout"] = Field(
        default="meal",
        description="Loại kế hoạch: 'meal' (Thực đơn & đi chợ) hoặc 'hangout' (Đi chơi & hẹn hò)",
    )
    total_budget: int = Field(
        default=500000,
        ge=10000,
        le=2000000000,
        description="Ngân sách tối đa (VNĐ)",
    )
    region: str = Field(
        default="Hà Nội", min_length=1, max_length=120, description="Khu vực / Thành phố"
    )
    days_or_people: str = Field(
        default="7 ngày cho 1-2 người",
        min_length=1,
        max_length=120,
        description="Thời lượng hoặc số lượng người tham gia",
    )
    preferences: str = Field(
        default="",
        max_length=2000,
        description="Sở thích, khẩu vị, hình thức hoặc yêu cầu đặc biệt",
    )
    pantry: str = Field(default="", max_length=2000)


class PatchItemRequest(TrimmedInput):
    is_completed: Optional[bool] = Field(
        default=None,
        description="Trạng thái đã mua / đã chi tiêu",
    )
    price: Optional[int] = Field(
        default=None,
        ge=0,
        le=2000000000,
        description="Giá tiền thực tế chỉnh sửa (VNĐ)",
    )
    name: Optional[str] = Field(
        default=None, min_length=1, max_length=255, description="Tên mục (tùy chọn chỉnh sửa)"
    )
    details: Optional[str] = Field(
        default=None, max_length=5000, description="Chi tiết mục (tùy chọn chỉnh sửa)"
    )


class ReplaceItemRequest(TrimmedInput):
    preferences: str = Field(default="", max_length=2000)
