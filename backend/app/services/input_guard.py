"""Input guard — prompt injection detection and sensitive info filtering."""
import re


class InputGuard:
    MAX_QUESTION_LENGTH = 500

    INJECTION_PATTERNS = [
        r"(?i)ignore\s+(all\s+)?(previous|above|prior)\s+instructions?",
        r"(?i)you\s+are\s+now\s+(a\s+)?(different|new|other)",
        r"(?i)(tell|show|reveal)\s+(me\s+)?(your\s+)?(system\s*)?(prompt|message|instruction)",
        r"(?i)forget\s+(everything|all|your\s+training)",
        r"(?i)DAN\s+(mode|prompt|jailbreak)",
        r"(?i)不要.*(参考|使用|根据).*知识库",
        r"(?i)扮演.*角色",
    ]

    SENSITIVE_PATTERNS = [
        (r"\d{17}[\dXx]", "身份证号"),
        (r"1[3-9]\d{9}", "手机号"),
        (r"\d{16,19}", "银行卡号"),
    ]

    @classmethod
    def sanitize(cls, text: str) -> tuple[str, bool, str]:
        """Returns (cleaned_text, passed, reason)."""
        if not text or not text.strip():
            return "", False, "输入不能为空"
        if len(text) > cls.MAX_QUESTION_LENGTH:
            return (
                text[: cls.MAX_QUESTION_LENGTH],
                False,
                "输入内容过长，请精简后重新提问",
            )
        for pattern in cls.INJECTION_PATTERNS:
            if re.search(pattern, text):
                return "", False, "检测到异常输入，已被安全拦截"
        for pattern, label in cls.SENSITIVE_PATTERNS:
            if re.search(pattern, text):
                return "", False, f"请勿在对话中包含{label}等个人敏感信息"
        return text.strip(), True, ""
