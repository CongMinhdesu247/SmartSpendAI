import json
from typing import Any, Dict, List, Literal, Optional

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from backend.database import load_config

# =====================================================================
# BẢNG NEO GIÁ THỰC TẾ TẠI VIỆT NAM (VN_PRICE_ANCHOR)
# Giúp AI định giá sát thực tế chợ truyền thống, siêu thị & dịch vụ VN
# =====================================================================
VN_PRICE_ANCHOR = """
[BẢNG NEO GIÁ THỰC TẾ TẠI VIỆT NAM - ĐƠN VỊ: VNĐ]
1. Thịt, Cá, Trứng, Đậu (Đạm):
   - Thịt heo (ba rọi, nạc vai, thịt xay): 130.000đ - 165.000đ / 1kg (mua lẻ 300g ~ 42.000đ - 50.000đ)
   - Thịt ức gà / đùi gà công nghiệp: 75.000đ - 95.000đ / 1kg (500g ~ 40.000đ - 48.000đ)
   - Thịt bò (thăn/bắp): 250.000đ - 290.000đ / 1kg (200g ~ 52.000đ - 58.000đ)
   - Cá nục / cá rô phi / cá bạc má / cá diêu hồng: 65.000đ - 95.000đ / 1kg
   - Tôm thẻ tươi: 170.000đ - 220.000đ / 1kg (300g ~ 55.000đ - 65.000đ)
   - Trứng gà / trứng vịt: 30.000đ - 35.000đ / chục (10 quả)
   - Đậu hũ (đậu phụ): 3.000đ - 5.000đ / bìa (10 bìa ~ 35.000đ)
   - Giò lụa / chả cá: 35.000đ - 50.000đ / 300g

2. Rau củ quả & Gia vị tươi:
   - Rau muống, cải ngọt, cải thìa, mồng tơi, rau ngót: 10.000đ - 15.000đ / bó lớn
   - Bắp cải, bí xanh, bầu, mướp, su hào, củ cải: 15.000đ - 25.000đ / kg
   - Cà chua, khoai tây, cà rốt, dưa leo: 20.000đ - 30.000đ / kg
   - Nấm kim châm / nấm đùi gà / nấm rơm: 18.000đ - 30.000đ / gói hoặc khay
   - Hành lá, ngò rí, ớt, tỏi, hành tím, gừng, sả, chanh: 15.000đ - 30.000đ (combo dùng cả tuần)
   - Trái cây tráng miệng (chuối, ổi, thanh long, dưa hấu, cam): 20.000đ - 35.000đ / kg

3. Tinh bột & Đồ khô:
   - Gạo tẻ thơm vừa: 20.000đ - 24.000đ / kg
   - Bún tươi / bánh phở / hủ tiếu: 15.000đ - 20.000đ / kg
   - Mì gói / miến / nui: 4.500đ - 8.000đ / gói
   - Bánh mì ổ: 5.000đ / ổ không, 18.000đ - 25.000đ / ổ kẹp thịt trứng

4. Đi chơi, Ăn uống ngoài hàng & Giải trí:
   - Gửi xe máy: 5.000đ - 10.000đ / lượt; Xăng xe di chuyển nội thành: 20.000đ - 40.000đ / buổi
   - Cà phê / Trà sữa bình dân - tầm trung: 25.000đ - 55.000đ / ly
   - Ăn vặt vỉa hè (bánh tráng trộn, cá viên chiên, nem chua rán, chè, ốc bình dân): 25.000đ - 60.000đ / người
   - Quán ăn chính (bún đậu, phở, cơm tấm, mì cay, lẩu/nướng bình dân): 45.000đ - 160.000đ / người
   - Vé xem phim (CGV/Lotte/Beta/Galaxy): 65.000đ - 115.000đ / vé (Beta/U22/Thứ 3 rẻ hơn)
   - Photobooth chụp ảnh Hàn Quốc / Bảo tàng / Workshop / Bowling / Billiards: 50.000đ - 120.000đ / người
"""


# =====================================================================
# PYDANTIC SCHEMAS ĐỊNH DẠNG ĐẦU RA CHUẨN TỪ GEMINI
# =====================================================================
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
        description=(
            "Thời điểm hoặc phân nhóm. "
            "Với 'grocery': ghi nhóm nguyên liệu (VD: 'Đạm & Thịt cá', 'Rau củ & Trái cây', 'Tinh bột & Gia vị'). "
            "Với 'daily_menu': ghi 'Ngày 1', 'Ngày 2'... "
            "Với 'activity': ghi khung giờ cụ thể (VD: '17:30 - 18:30', 'Dự phòng')."
        )
    )
    name: str = Field(
        description=(
            "Tên thực phẩm kèm định lượng rõ ràng (VD: 'Thịt ba rọi heo (500g)') "
            "HOẶC tóm tắt món Sáng - Trưa - Tối của ngày đó "
            "HOẶC tên địa điểm/hoạt động đi chơi."
        )
    )
    details: str = Field(
        description=(
            "Chi tiết hữu ích: "
            "Với 'grocery': cách chọn mua tươi ngon, chia phần & bảo quản tủ lạnh cho những ngày nào. "
            "Với 'daily_menu': chi tiết món Sáng, Trưa, Tối và cách tận dụng nguyên liệu từ giỏ đi chợ gộp. "
            "Với 'activity': địa chỉ gợi ý thực tế tại khu vực, món nên gọi và mẹo trải nghiệm."
        )
    )
    price: int = Field(
        ge=0,
        description=(
            "Chi phí ước tính bằng VNĐ (số nguyên dương, làm tròn nghìn đồng). "
            "LƯU Ý QUAN TRỌNG: Với kế hoạch 'meal', toàn bộ tiền mua nguyên liệu đã tính ở các mục 'grocery', "
            "nên các mục 'daily_menu' PHẢI để price = 0 (hoặc chỉ ghi chi phí phát sinh nhỏ không có trong giỏ đi chợ) "
            "để tránh cộng trùng lặp ngân sách."
        ),
    )


class AIPlanOutput(BaseModel):
    title: str = Field(
        description="Tiêu đề kế hoạch ngắn gọn, hấp dẫn (VD: 'Thực đơn 7 ngày 500k đủ chất' hoặc 'Hẹn hò cuối tuần 300k tại Hà Nội')."
    )
    estimated_cost: int = Field(
        ge=0,
        description="Tổng chi phí dự tính của toàn bộ kế hoạch (VNĐ), phải nhỏ hơn hoặc bằng ngân sách total_budget.",
    )
    advice: str = Field(
        description="Lời khuyên thực tế từ chuyên gia tài chính: mẹo đi chợ/sơ chế/bảo quản hoặc mẹo săn ưu đãi, phương án dự phòng khi thời tiết xấu."
    )
    items: List[AIPlanItemSchema] = Field(
        description="Danh sách đầy đủ các hạng mục của kế hoạch."
    )


# =====================================================================
# HÀM GỌI GEMINI VỚI CƠ CHẾ TỰ ĐỘNG FALLBACK MODEL
# =====================================================================
PREFERRED_MODELS = [
    "gemini-3.5-flash",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
]


def _call_gemini_with_fallback(
    client: genai.Client,
    prompt: str,
    system_instruction: str,
) -> AIPlanOutput:
    """
    Thử gọi lần lượt các model trong danh sách ưu tiên:
    ["gemini-3.5-flash", "gemini-2.5-flash", "gemini-2.0-flash"].
    Nếu gặp lỗi 404 (Not Found), tự động gọi client.models.list() để tìm model có chữ 'flash' khả dụng.
    """
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        response_mime_type="application/json",
        response_schema=AIPlanOutput,
        temperature=0.4,
    )

    last_error: Optional[Exception] = None
    tried_models: List[str] = []

    for model_name in PREFERRED_MODELS:
        tried_models.append(model_name)
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config,
            )
            return _parse_ai_response(response)
        except Exception as err:
            last_error = err
            err_str = str(err).lower()
            # Nếu lỗi xác thực API Key hoặc hết quota thì báo ngay, không cần thử model khác
            if "api_key_invalid" in err_str or "invalid api key" in err_str or "permission_denied" in err_str:
                raise RuntimeError("Gemini API Key không hợp lệ. Vui lòng kiểm tra lại trong phần Cài đặt.") from err
            continue

    # Nếu tất cả các model cố định đều lỗi (404/không tìm thấy), quét danh sách model khả dụng có chữ "flash"
    try:
        available_flash_models: List[str] = []
        for m in client.models.list():
            m_name = getattr(m, "name", "") or ""
            short_name = m_name.replace("models/", "")
            if (
                "flash" in short_name.lower()
                and "tts" not in short_name.lower()
                and "image" not in short_name.lower()
                and "audio" not in short_name.lower()
                and short_name not in tried_models
            ):
                available_flash_models.append(short_name)

        for fallback_model in available_flash_models:
            try:
                response = client.models.generate_content(
                    model=fallback_model,
                    contents=prompt,
                    config=config,
                )
                return _parse_ai_response(response)
            except Exception as err:
                last_error = err
                continue
    except Exception:
        pass

    raise RuntimeError(
        f"Không thể gọi Gemini AI sau khi thử các model {tried_models}. Chi tiết lỗi: {last_error}"
    )


def _parse_ai_response(response: Any) -> AIPlanOutput:
    """Chuyển đổi kết quả trả về từ google-genai sang đối tượng AIPlanOutput."""
    if getattr(response, "parsed", None) is not None and isinstance(response.parsed, AIPlanOutput):
        return response.parsed

    raw_text = (getattr(response, "text", "") or "").strip()
    if not raw_text:
        raise ValueError("AI trả về phản hồi rỗng.")

    # Làm sạch markdown code fence nếu có
    if raw_text.startswith("```"):
        lines = raw_text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        raw_text = "\n".join(lines).strip()

    data = json.loads(raw_text)
    return AIPlanOutput.model_validate(data)


# =====================================================================
# HÀM CHÍNH: TẠO KẾ HOẠCH CHI TIÊU THÔNG MINH
# =====================================================================
def generate_smart_plan(
    plan_type: str,
    total_budget: int,
    region: str = "TP. Hồ Chí Minh",
    days_or_people: str = "7 ngày cho 1-2 người",
    preferences: str = "",
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Tạo kế hoạch thực đơn đi chợ ('meal') hoặc lịch trình đi chơi ('hangout')
    bằng Gemini AI kèm kiểm soát ngân sách nghiêm ngặt theo giá cả Việt Nam.
    """
    cfg = load_config()
    effective_key = (api_key or cfg.get("gemini_api_key", "")).strip()
    if not effective_key:
        raise ValueError(
            "Chưa cấu hình Gemini API Key! Vui lòng mở mục Cài đặt (Settings) và nhập Gemini API Key trước khi tạo kế hoạch."
        )

    plan_type_clean = "meal" if plan_type.lower().strip() == "meal" else "hangout"
    budget_int = max(10000, int(total_budget))

    system_instruction = f"""
Bạn là "SmartSpend Pro AI" - Chuyên gia quản lý tài chính cá nhân, đầu bếp gia đình và thổ địa du lịch hàng đầu tại Việt Nam.
Nhiệm vụ của bạn là lập kế hoạch chi tiêu cực kỳ thực tế, thông minh, tiết kiệm và KHÔNG BAO GIỜ VƯỢT NGÂN SÁCH.

Hãy luôn tham chiếu bảng giá thực tế sau đây để định giá chính xác tới từng nghìn đồng:
{VN_PRICE_ANCHOR}

NGUYÊN TẮC BẮT BUỘC:
1. Tổng chi phí (`estimated_cost` = tổng `price` của tất cả `items`) BẮT BUỘC PHẢI <= {budget_int:,} VNĐ (tối ưu nhất là đạt khoảng 88% - 98% ngân sách).
2. Mọi số tiền `price` đều là số nguyên VNĐ, bội số của 1.000 (ví dụ: 35000, 45000, 120000).
3. Ngôn ngữ: Tiếng Việt tự nhiên, rõ ràng, trình bày khoa học.
"""

    if plan_type_clean == "meal":
        user_prompt = f"""
Hãy lập KẾ HOẠCH ĐI CHỢ GỘP & THỰC ĐƠN NẤU ĂN (`plan_type = "meal"`) với thông số:
- Ngân sách tối đa (`total_budget`): {budget_int:,} VNĐ
- Khu vực giá cả (`region`): {region}
- Quy mô / Thời lượng: {days_or_people}
- Sở thích / Yêu cầu đặc biệt: {preferences or "Đủ dinh dưỡng, dễ nấu, tiết kiệm thời gian, đổi món đa dạng"}

YÊU CẦU CẤU TRÚC `items` CHO KẾ HOẠCH "meal" (BẮT BUỘC CÓ CẢ 2 NHÓM SAU):
1. Nhóm `category = "grocery"` (Danh sách đi chợ gộp thông minh dùng chung cho cả đợt):
   - Liệt kê từ 8 đến 16 mặt hàng thực phẩm cần mua (Đạm/Thịt cá trứng đậu, Rau củ quả, Tinh bột/Đồ khô/Gia vị).
   - `time_or_day`: Ghi nhóm thực phẩm (VD: "Đạm & Thịt cá", "Rau củ tươi", "Tinh bột & Gia vị").
   - `name`: Ghi tên nguyên liệu kèm định lượng cụ thể (VD: "Thịt heo ba rọi & nạc xay (700g)", "Trứng gà ta (10 quả)").
   - `details`: Ghi rõ cách chia phần sơ chế, cách bảo quản ngăn mát/ngăn đông và dùng cho những ngày nào.
   - `price`: Giá tiền thực tế (VNĐ). Tổng tiền của tất cả mục `grocery` phải <= {budget_int:,} VNĐ.

2. Nhóm `category = "daily_menu"` (Thực đơn chi tiết từng ngày chế biến từ giỏ đi chợ trên):
   - Tạo đầy đủ thực đơn cho từng ngày (VD: "Ngày 1", "Ngày 2", ... tương ứng với yêu cầu "{days_or_people}").
   - `time_or_day`: Ghi rõ "Ngày 1", "Ngày 2", "Ngày 3"...
   - `name`: Tóm tắt các món chính trong ngày (VD: "Sáng: Bánh mì ốp la | Trưa: Thịt kho trứng, Canh cải | Tối: Cá chiên sả, Rau luộc").
   - `details`: Hướng dẫn nấu nhanh cho bữa Sáng - Trưa - Tối và cách tận dụng chéo nguyên liệu từ giỏ `grocery`.
   - `price`: BẮT BUỘC ĐẶT `price = 0` (hoặc chỉ tính tiền phát sinh cực nhỏ chưa có trong `grocery`) để KHÔNG BỊ CỘNG TRÙNG LẶP với tiền đi chợ gộp!
"""
    else:
        user_prompt = f"""
Hãy lập KẾ HOẠCH ĐI CHƠI / HẸN HÒ / DÃ NGOẠI (`plan_type = "hangout"`) với thông số:
- Ngân sách tối đa (`total_budget`): {budget_int:,} VNĐ
- Khu vực / Thành phố (`region`): {region}
- Quy mô / Thời lượng / Số người: {days_or_people}
- Sở thích / Yêu cầu đặc biệt: {preferences or "Vui vẻ, có ăn uống ngon, chụp ảnh đẹp, tối ưu quãng đường di chuyển"}

YÊU CẦU CẤU TRÚC `items` CHO KẾ HOẠCH "hangout":
- Tất cả các mục đều có `category = "activity"`.
- Chia thành 4 đến 8 chặng hoạt động theo khung giờ hợp lý (VD: `time_or_day` = "08:30 - 10:00", "10:15 - 12:30", "14:00 - 16:30", "18:00 - 20:30"...).
- `name`: Tên hoạt động + gợi ý địa điểm cụ thể tại {region}.
- `details`: Mô tả trải nghiệm, gợi ý món nên gọi, địa chỉ/khu vực cụ thể và mẹo tiết kiệm.
- BẮT BUỘC có 1 mục cuối cùng có `time_or_day = "Quỹ dự phòng & Gửi xe"` (category="activity") dành cho tiền gửi xe, xăng xe hoặc chi phí phát sinh nhỏ.
- Tổng `price` của tất cả các mục `activity` phải <= {budget_int:,} VNĐ.
"""

    client = genai.Client(api_key=effective_key)
    ai_output: AIPlanOutput = _call_gemini_with_fallback(
        client=client,
        prompt=user_prompt,
        system_instruction=system_instruction,
    )

    # Chuẩn hóa và kiểm tra tổng chi phí để đảm bảo tính chính xác toán học
    cleaned_items: List[Dict[str, Any]] = []
    for item in ai_output.items:
        cat = item.category
        if plan_type_clean == "hangout":
            cat = "activity"
        elif cat not in ("grocery", "daily_menu"):
            cat = "grocery"

        cleaned_items.append(
            {
                "category": cat,
                "time_or_day": item.time_or_day.strip(),
                "name": item.name.strip(),
                "details": item.details.strip(),
                "price": max(0, int(item.price)),
                "is_completed": False,
            }
        )

    # Nếu tổng vượt quá ngân sách do AI sai số nhỏ, tự động cân đối lại hợp lý để đảm bảo <= total_budget
    calculated_total = sum(i["price"] for i in cleaned_items)
    if calculated_total > budget_int and calculated_total > 0:
        ratio = budget_int / calculated_total
        for i in cleaned_items:
            if i["price"] > 0:
                # Làm tròn xuống theo bậc 1.000đ
                i["price"] = max(1000, int((i["price"] * ratio) // 1000) * 1000)
        calculated_total = sum(i["price"] for i in cleaned_items)

    if calculated_total > budget_int:
        raise ValueError("Ngân sách chưa đủ cho số hạng mục được đề xuất. Hãy tăng ngân sách hoặc giảm thời lượng.")

    return {
        "title": ai_output.title.strip(),
        "plan_type": plan_type_clean,
        "total_budget": budget_int,
        "estimated_cost": calculated_total,
        "actual_spent": 0,
        "region": region.strip() or "Việt Nam",
        "advice": ai_output.advice.strip(),
        "items": cleaned_items,
    }


def suggest_replacement(context: Dict[str, Any]) -> Dict[str, Any]:
    """Replace exactly one unpaid item, keeping its category and budget cap."""
    key = load_config().get("gemini_api_key", "").strip()
    if not key:
        raise ValueError("Chưa cấu hình Gemini API Key")
    output = _call_gemini_with_fallback(
        genai.Client(api_key=key),
        "Đề xuất MỘT hạng mục thay thế khác với hạng mục cũ. Trả về items chỉ có 1 mục. "
        "Giữ category và khung thời gian. Không tự thay đổi nguyên liệu của các mục khác. "
        "Giá là ước tính, phải <= budget; với daily_menu ưu tiên giá 0 vì nguyên liệu đã tính riêng. "
        + json.dumps(context, ensure_ascii=False),
        "Bạn là trợ lý lập kế hoạch sinh hoạt tại Việt Nam. Trả về JSON đúng schema, không emoji. " + VN_PRICE_ANCHOR,
    )
    if len(output.items) != 1:
        raise ValueError("AI chưa trả về đúng một phương án. Hãy thử lại.")
    item = output.items[0]
    if item.category != context["category"] or item.price > context["budget"] or not item.name.strip():
        raise ValueError("Phương án AI chưa phù hợp ngân sách. Hãy thử lại.")
    return {"name": item.name.strip()[:255], "details": item.details.strip(), "price": item.price}

