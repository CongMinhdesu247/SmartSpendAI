"""Data validation schemas for ai."""

from typing import List, Literal

from pydantic import BaseModel, Field


class AIPlanItemSchema(BaseModel):
    category: Literal["grocery", "daily_menu", "activity"] = Field(
        description=(
            "Phân loại mục: "
            "'grocery' (nguyên liệu trong giỏ đi chợ gộp), "
            "'daily_menu' (thực đơn Sáng-Trưa-Tối của từng ngày), "
            "hoặc 'activity' (hoạt động trong lịch trình đi chơi)."
        )
    )
    time_or_day: str = Field(
        max_length=120,
        description=(
            "Thời điểm hoặc phân nhóm. "
            "Với 'grocery': ghi nhóm nguyên liệu (VD: 'Đạm & Thịt cá', 'Rau củ & Trái cây', 'Tinh bột & Gia vị'). "
            "Với 'daily_menu': ghi 'Ngày 1', 'Ngày 2'... "
            "Với 'activity': ghi khung giờ cụ thể (VD: '17:30 - 18:30', 'Dự phòng')."
        ),
    )
    name: str = Field(
        min_length=1,
        max_length=255,
        description=(
            "Tên thực phẩm kèm định lượng rõ ràng (VD: 'Thịt ba rọi heo (500g)') "
            "HOẶC tóm tắt món Sáng - Trưa - Tối của ngày đó "
            "HOẶC tên địa điểm/hoạt động đi chơi."
        ),
    )
    details: str = Field(
        max_length=5000,
        description=(
            "Chi tiết hữu ích: "
            "Với 'grocery': cách chọn mua tươi ngon, chia phần & bảo quản tủ lạnh cho những ngày nào. "
            "Với 'daily_menu': chi tiết món Sáng, Trưa, Tối và cách tận dụng nguyên liệu từ giỏ đi chợ gộp. "
            "Với 'activity': địa chỉ gợi ý thực tế tại khu vực, món nên gọi và mẹo trải nghiệm."
        ),
    )
    price: int = Field(
        ge=0,
        le=2000000000,
        description=(
            "Chi phí ước tính bằng VNĐ (số nguyên dương, làm tròn nghìn đồng). "
            "LƯU Ý QUAN TRỌNG: Với kế hoạch 'meal', toàn bộ tiền mua nguyên liệu đã tính ở các mục 'grocery', "
            "nên các mục 'daily_menu' PHẢI để price = 0 (hoặc chỉ ghi chi phí phát sinh nhỏ không có trong giỏ đi chợ) "
            "để tránh cộng trùng lặp ngân sách."
        ),
    )


class AIPlanOutput(BaseModel):
    title: str = Field(
        min_length=1,
        max_length=255,
        description="Tiêu đề kế hoạch ngắn gọn, hấp dẫn (VD: 'Thực đơn 7 ngày 500k đủ chất' hoặc 'Hẹn hò cuối tuần 300k tại Hà Nội').",
    )
    estimated_cost: int = Field(
        ge=0,
        description="Tổng chi phí dự tính của toàn bộ kế hoạch (VNĐ), phải nhỏ hơn hoặc bằng ngân sách total_budget.",
    )
    advice: str = Field(
        description="Lời khuyên thực tế từ chuyên gia tài chính: mẹo đi chợ/sơ chế/bảo quản hoặc mẹo săn ưu đãi, phương án dự phòng khi thời tiết xấu."
    )
    items: List[AIPlanItemSchema] = Field(
        min_length=1, max_length=200, description="Danh sách đầy đủ các hạng mục của kế hoạch."
    )


class AIMonthlyCoachingOutput(BaseModel):
    headline: str = Field(
        min_length=1,
        max_length=180,
        description="Nhận định ngắn gọn, sắc sảo về tình hình tài chính tháng này.",
    )
    summary: str = Field(
        min_length=1,
        max_length=1200,
        description="Đánh giá tổng quan dòng tiền thu - chi - tiết kiệm và nhịp độ ngân sách.",
    )
    strengths: List[str] = Field(
        default_factory=list,
        max_length=5,
        description="Các điểm sáng tài chính người dùng đang làm tốt (1-3 ý ngắn gọn).",
    )
    warnings: List[str] = Field(
        default_factory=list,
        max_length=5,
        description="Các điểm rò rỉ chi tiêu hoặc rủi ro vượt hạn mức cần lưu ý (0-3 ý).",
    )
    action_items: List[str] = Field(
        min_length=1,
        max_length=5,
        description="3 hành động thực tế, cụ thể bằng VNĐ để tối ưu chi tiêu những ngày còn lại.",
    )
    suggested_daily_cap: int = Field(
        ge=0,
        le=2000000000,
        description="Hạn mức chi tiêu khuyến nghị mỗi ngày cho phần còn lại của tháng (VNĐ).",
    )

