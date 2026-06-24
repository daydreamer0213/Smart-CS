"""Prompt templates — multi-tenant, adapted from ShopMind."""

HANDOFF_MESSAGE = "已为您记录问题并转接人工客服，请稍等。"


def build_system_prompt(tenant_name: str, append: str = "") -> str:
    base = (
        f"你是 {tenant_name} 的智能客服。"
        "你只能根据提供的知识库内容回答问题，不要编造信息。"
        "回答要简洁、礼貌、专业。"
        "如果知识库中没有相关信息，请如实告知用户。"
    )
    if append:
        base = f"{base}\n\n{append}"
    return base


def intent_prompt(user_input: str, human_keywords: list[str]) -> str:
    keywords_text = "、".join(human_keywords) if human_keywords else "转人工、人工客服"
    return (
        f"用户输入：{user_input}\n\n"
        f"请判断用户意图。只能返回 faq 或 human。\n"
        f"faq：用户咨询知识库可回答的问题。\n"
        f"human：用户触发以下关键词需要转人工：{keywords_text}；"
        f"或者用户情绪激烈、要求投诉、问题超出知识库范围。\n"
        f'返回格式：{{"intent": "faq或human", "confidence": 0.0到1.0之间的数字}}'
    )


def response_prompt(
    intent: str,
    context_docs: list[dict],
    history: list[dict],
    user_input: str,
) -> str:
    ctx = ""
    if context_docs:
        parts = []
        for i, doc in enumerate(context_docs, 1):
            parts.append(
                f"[{i}] 问题：{doc.get('question', '')}\n"
                f"    答案：{doc.get('answer', '')}"
            )
        ctx = "\n".join(parts)
    else:
        ctx = "未找到相关知识条目。"

    history_text = ""
    for m in history[-10:]:
        role = m.get("role", "user")
        content = m.get("content", "")
        history_text += f"{role}: {content}\n"

    return (
        f"知识库检索结果：\n{ctx}\n\n"
        f"对话历史：\n{history_text}\n"
        f"用户输入：{user_input}\n\n"
        f"请根据检索结果生成简洁、礼貌的中文回复。"
        f"如果检索结果为'未找到'，请告知用户暂时无法回答该问题并建议联系人工客服。"
    )
