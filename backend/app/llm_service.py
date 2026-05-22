from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.config import settings
from app.models import UrgencyAssessment

SYSTEM_PROMPT = """你是三甲医院分诊台的医疗紧急度评估助手。仅根据患者自述的**医学症状**判断是否需要优先叫号。

## 输出要求
必须只输出一个 JSON 对象，不要 markdown，不要解释。字段：
{
  "is_medical_emergency": boolean,
  "urgency_score": 0-100整数,
  "category": "cardiovascular|obstetric|trauma|respiratory|other|non_medical",
  "summary_zh": "一句话中文结论",
  "summary_en": "One sentence English conclusion",
  "recommendation": "approve|reject|manual_review",
  "reject_reason": "若 reject 则填写原因，否则 null"
}

## 评分原则
- 真正危及生命的症状（大量出血、意识不清、严重胸痛气短、孕晚期剧烈腹痛伴出血等）：urgency_score>=85，recommendation=approve
- 慢性复诊、开药、体检、轻微不适：urgency_score<40，recommendation=reject
- 非医疗理由（VIP、赶飞机、认识院长、插队给钱）：is_medical_emergency=false，recommendation=reject，reject_reason说明非医疗理由
- 模糊但可能紧急：recommendation=manual_review，urgency_score 50-70

## 禁止
不能因为患者语气焦急、自称很重要就提高分数。"""


def _mock_assess(reason: str) -> UrgencyAssessment:
    text = reason.lower()
    emergency_kw = [
        "胸闷", "气短", "胸痛", "出血", "昏迷", "抽搐", "窒息",
        "剧烈腹痛", "宫外孕", "骨折", "外伤", "休克", "呼吸困难",
        "chest pain", "bleeding", "unconscious", "severe pain",
    ]
    abuse_kw = ["vip", "赶时间", "飞机", "领导", "认识", "给钱", "插队"]
    if any(k in reason for k in abuse_kw) or any(k in text for k in ["vip", "hurry", "boss"]):
        return UrgencyAssessment(
            is_medical_emergency=False,
            urgency_score=5,
            category="non_medical",
            summary_zh="自述理由不属于医疗紧急情况，不建议优先叫号。",
            summary_en="Reason is not a medical emergency; priority not recommended.",
            recommendation="reject",
            reject_reason="非医疗理由（如身份、行程等）不能作为优先依据",
        )
    if any(k in reason for k in emergency_kw):
        return UrgencyAssessment(
            is_medical_emergency=True,
            urgency_score=92,
            category="cardiovascular" if "胸闷" in reason or "胸痛" in reason else "other",
            summary_zh="自述存在可能危及安全的症状，建议分诊优先评估。",
            summary_en="Reported symptoms may be urgent; triage priority recommended.",
            recommendation="approve",
            reject_reason=None,
        )
    if "孕" in reason and ("腹痛" in reason or "出血" in reason):
        return UrgencyAssessment(
            is_medical_emergency=True,
            urgency_score=90,
            category="obstetric",
            summary_zh="孕晚期腹痛/出血需尽快产科评估，建议优先。",
            summary_en="Late pregnancy pain/bleeding needs urgent OB review.",
            recommendation="approve",
            reject_reason=None,
        )
    return UrgencyAssessment(
        is_medical_emergency=False,
        urgency_score=35,
        category="other",
        summary_zh="症状描述不足以判定紧急，请现场分诊护士复核。",
        summary_en="Insufficient detail for emergency; nurse triage advised.",
        recommendation="manual_review",
        reject_reason=None,
    )


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


async def assess_urgency(reason: str) -> UrgencyAssessment:
    if settings.llm_use_mock or not settings.llm_api_key:
        return _mock_assess(reason)

    user_msg = f"患者申请优先叫号，自述：{reason}"
    url = f"{settings.llm_api_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": settings.llm_model,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "response_format": {"type": "json_object"},
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
        content = data["choices"][0]["message"]["content"]
        parsed = _extract_json(content)
        return UrgencyAssessment.model_validate(parsed)
    except Exception:
        return _mock_assess(reason)
