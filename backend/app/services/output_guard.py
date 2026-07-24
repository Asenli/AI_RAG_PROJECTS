"""Output guard — response safety filter."""
import re


class OutputGuard:
    LEAK_PATTERNS = [
        r"(?i)system\s*prompt",
        r"(?i)system\s*message",
        r"(?i)系统指令",
        r"(?i)系统提示",
    ]

    @classmethod
    def sanitize(cls, text: str) -> str:
        """Filter dangerous output patterns."""
        if not text:
            return ""
        # XSS filter
        text = text.replace("<script>", "&lt;script&gt;")
        text = text.replace("</script>", "&lt;/script&gt;")
        # System prompt leak detection
        for pattern in cls.LEAK_PATTERNS:
            if re.search(pattern, text):
                return "抱歉，无法处理该请求。"
        return text
