"""LLM service — DeepSeek official OpenAI-compatible API."""
from openai import AsyncOpenAI
from app.config import settings


class LLMService:
    def __init__(self):
        api_key = (
            settings.deepseek_api_key
            if "api.deepseek.com" in settings.llm_base_url
            else settings.siliconflow_api_key
        )
        if not api_key:
            api_key = settings.siliconflow_api_key or settings.deepseek_api_key
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=settings.llm_base_url,
        )
        self.model = settings.llm_model
        self.provider = (
            "deepseek" if "api.deepseek.com" in settings.llm_base_url else "siliconflow"
        )

    async def chat(
        self, messages: list[dict], temperature: float = 0.3, max_tokens: int = 2048
    ) -> str:
        """Send chat request, return text response."""
        response = await self.create_chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content

    async def create_chat_completion(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 2048,
        response_format: dict | None = None,
    ):
        """Send chat request and return raw OpenAI-compatible response."""
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            kwargs["response_format"] = response_format
        return await self.client.chat.completions.create(**kwargs)

    async def chat_json(
        self, messages: list[dict], temperature: float = 0.1
    ) -> dict:
        """Send chat request, parse JSON response."""
        import json
        response = await self.create_chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=1024,
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content)

    async def _legacy_chat_json(
        self, messages: list[dict], temperature: float = 0.1
    ) -> dict:
        """Deprecated compatibility method."""
        import json
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=1024,
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content)


llm_service = LLMService()
