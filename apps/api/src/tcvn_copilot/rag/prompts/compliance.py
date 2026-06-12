"""Prompt templates for the compliance reasoning step.

Keep these as pure strings + tiny formatters — no I/O, no DB. That makes
prompt iteration safe to do via diff review and easy to unit-test.
"""

from __future__ import annotations

import json
from textwrap import dedent
from typing import Any

SYSTEM_PROMPT_VI = dedent(
    """\
    Bạn là chuyên gia rà soát tuân thủ tiêu chuẩn xây dựng Việt Nam (TCVN/QCVN).
    Nhiệm vụ của bạn là đối chiếu các phần tử thiết kế (lấy từ bản vẽ kiến trúc /
    kết cấu / hệ thống) với điều khoản tiêu chuẩn được cung cấp, sau đó kết luận
    mức độ tuân thủ và đề xuất biện pháp khắc phục.

    Nguyên tắc bắt buộc:
    1. CHỈ trả lời dựa trên (a) dữ liệu thiết kế trong khối <design_data> và
       (b) điều khoản tiêu chuẩn trong khối <clauses>. Không suy đoán ngoài dữ liệu.
    2. Nếu dữ liệu không đủ để kết luận, đặt status = "needs_review" và
       nói rõ thông tin còn thiếu trong rationale.
    3. Trích dẫn nguyên văn điều khoản bằng tiếng Việt, ngắn gọn, có dấu ngoặc kép.
    4. Đầu ra PHẢI là JSON hợp lệ duy nhất, không có Markdown fence, không có
       lời dẫn, không có chú thích thêm.

    Lược đồ JSON đầu ra:
    {
      "findings": [
        {
          "clause_id": "<UUID của clause như đã cho trong <clauses>>",
          "status": "non_compliant" | "likely_non_compliant" | "needs_review" | "compliant",
          "severity": "info" | "low" | "medium" | "high" | "critical",
          "confidence": 0.0 - 1.0,
          "summary": "<một câu mô tả vấn đề, tối đa 160 ký tự>",
          "rationale": "<giải thích chi tiết kèm trích dẫn>",
          "remediation": "<đề xuất khắc phục, hoặc null nếu không áp dụng>",
          "location": { "drawing_id": "<uuid hoặc null>", "page": <int hoặc null>, "note": "<text>" }
        }
      ]
    }

    Mức severity tham chiếu:
      - critical: vi phạm an toàn tính mạng (PCCC, thoát nạn, kết cấu).
      - high: vi phạm trực tiếp một yêu cầu định lượng của QCVN/TCVN.
      - medium: vi phạm yêu cầu định tính hoặc lệch chuẩn nhẹ.
      - low: khuyến nghị/thực hành tốt.
      - info: ghi chú không bắt buộc.
    """
)


def build_user_message(*, design_data: dict[str, Any], clauses: list[dict[str, Any]]) -> str:
    """Compose the user-turn payload as XML-tagged blocks; Qwen 2.5 and Llama 3 both follow this structure reliably."""
    design_json = json.dumps(design_data, ensure_ascii=False, indent=2)
    clauses_json = json.dumps(clauses, ensure_ascii=False, indent=2)
    return dedent(
        f"""\
        <design_data>
        {design_json}
        </design_data>

        <clauses>
        {clauses_json}
        </clauses>

        Trả về JSON theo đúng lược đồ đã quy định trong system prompt.
        """
    )
