"""Data validation schemas for plans and system configuration."""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class TrimmedInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)


class ConfigUpdateRequest(BaseModel):
    gemini_api_key: Optional[str] = Field(
        default=None, max_length=512, description="Google Gemini API Key"
    )
    database_url: Optional[str] = Field(
        default=None,
        max_length=2048,
        description="Chuỗi kết nối Supabase PostgreSQL (postgresql://... hoặc postgres://...)",
    )
    cloud_url: Optional[str] = Field(
        default=None,
        max_length=512,
        description="Địa chỉ HTTPS ứng dụng đã triển khai cloud",
    )
    allow_lan: Optional[bool] = Field(
        default=None,
        description="Cho phép các thiết bị cùng mạng Wi-Fi truy cập khi mở lại ứng dụng",
    )
    clear_api_key: bool = False
    clear_database_url: bool = False
    clear_cloud_url: bool = False


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


class CreatePlanRequest(TrimmedInput):
    title: str = Field(min_length=1, max_length=255)
    plan_type: Literal["meal", "hangout"] = "meal"
    total_budget: int = Field(default=500000, ge=10000, le=2000000000)
    region: str = Field(default="Hà Nội", min_length=1, max_length=120)
    advice: str = Field(default="", max_length=5000)


class UpdatePlanRequest(TrimmedInput):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    total_budget: Optional[int] = Field(default=None, ge=10000, le=2000000000)
    region: Optional[str] = Field(default=None, min_length=1, max_length=120)
    advice: Optional[str] = Field(default=None, max_length=5000)


class CreatePlanItemRequest(TrimmedInput):
    category: Literal["grocery", "daily_menu", "activity"] = "grocery"
    time_or_day: str = Field(default="", max_length=120)
    name: str = Field(min_length=1, max_length=255)
    details: str = Field(default="", max_length=5000)
    price: int = Field(default=0, ge=0, le=2000000000)


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
    time_or_day: Optional[str] = Field(
        default=None, max_length=120, description="Nhóm nguyên liệu / ngày / khung giờ"
    )


class ReplaceItemRequest(TrimmedInput):
    preferences: str = Field(default="", max_length=2000)
