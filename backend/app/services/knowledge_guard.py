"""Knowledge guard — validate documents before ingestion."""
import re
import hashlib


class KnowledgeGuard:
    SENSITIVE_CHECKS = [
        (r"\d{17}[\dXx]", "身份证号"),
        (r"1[3-9]\d{9}", "手机号"),
        (r"\d{16,19}", "银行卡号"),
        (r"(?i)password|密码|secret|密钥", "敏感凭证"),
    ]

    @classmethod
    def validate(cls, content: str, filename: str) -> dict:
        """Validate document content. Returns {valid, reason, md5?, review?}."""
        stripped = content.strip()

        # Empty / too short
        if len(stripped) < 10:
            return {"valid": False, "reason": "文档内容过短（<10字符），拒绝入库"}

        # Garbled text check
        valid_chars = sum(
            1
            for c in stripped
            if "一" <= c <= "鿿"
            or "A" <= c <= "z"
            or c.isdigit()
            or c in "，。；：、？！""''（）【】《》…—·～/-+#\n\r "
        )
        garbled_ratio = 1 - valid_chars / max(len(stripped), 1)
        if garbled_ratio > 0.5:
            return {
                "valid": False,
                "reason": "文档乱码字符占比过高，拒绝入库",
            }

        # Sensitive info scan
        for pattern, label in cls.SENSITIVE_CHECKS:
            if re.search(pattern, stripped):
                return {
                    "valid": False,
                    "reason": f"文档包含{label}，需人工审核后入库",
                    "review": True,
                }

        md5_hash = hashlib.md5(stripped.encode()).hexdigest()
        return {"valid": True, "md5": md5_hash}
