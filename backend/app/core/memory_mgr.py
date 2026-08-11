"""Memory manager — 3-tier memory: short-term(Redis), medium-term(Redis+PG), long-term(PG)."""
import json
import time
from datetime import datetime
import redis.asyncio as aioredis
from app.config import settings
from app.models.memory import (
    SessionMediumMemory, ChatSession, ChatMessage,
    UserProfile, UserFact, UserFrequentQuestion,
)
from app.models.base import async_session
from sqlalchemy import select, func


class MemoryManager:
    def __init__(self):
        self.redis = None

    async def connect(self):
        try:
            self.redis = await aioredis.from_url(
                f"redis://:{settings.redis_password}@{settings.redis_host}:{settings.redis_port}/0",
                decode_responses=True,
            )
            await self.redis.ping()
        except Exception:
            self.redis = None  # Redis optional in dev

    # ========== Short-term Memory (Redis) ==========

    @staticmethod
    def _session_key(company_id: str, session_id: str, memory_type: str) -> str:
        cid = str(company_id or settings.default_company_id)
        return f"company:{cid}:session:{session_id}:{memory_type}"

    @staticmethod
    def _session_meta_key(company_id: str, session_id: str) -> str:
        cid = str(company_id or settings.default_company_id)
        return f"company:{cid}:session:{session_id}:meta"

    @staticmethod
    def _user_sessions_key(company_id: str, user_id: str) -> str:
        cid = str(company_id or settings.default_company_id)
        uid = str(user_id or "dev_user")
        return f"company:{cid}:user:{uid}:sessions"

    @staticmethod
    def _now_iso() -> str:
        return datetime.utcnow().isoformat(timespec="seconds") + "Z"

    @staticmethod
    def _message_to_dict(message: ChatMessage) -> dict:
        metadata = message.message_metadata or {}
        return {
            "id": message.id,
            "company_id": message.company_id,
            "session_id": message.session_id,
            "user_id": message.user_id,
            "user_role": message.user_role,
            "role": message.role,
            "content": message.content,
            "metadata": metadata,
            "trace_id": message.trace_id,
            "answer_id": message.answer_id,
            "timestamp": message.created_at.isoformat(timespec="seconds") + "Z"
            if message.created_at else "",
        }

    async def register_session(
        self,
        session_id: str,
        user_id: str = "dev_user",
        user_role: str = "school",
        school_id: str = "",
        company_id: str = settings.default_company_id,
        title: str = "",
    ) -> dict:
        """Create or refresh lightweight session metadata for history list."""
        company_id = str(company_id or settings.default_company_id)
        user_id = str(user_id or "dev_user")
        now_score = time.time()
        now_text = self._now_iso()
        title = (title or "新会话").strip()[:128]
        meta = {
            "company_id": company_id,
            "session_id": session_id,
            "user_id": user_id,
            "user_role": user_role or "school",
            "school_id": school_id or "",
            "title": title,
            "message_count": 0,
            "created_at": now_text,
            "updated_at": now_text,
        }
        try:
            async with async_session() as session:
                result = await session.execute(
                    select(ChatSession).where(
                        ChatSession.company_id == company_id,
                        ChatSession.session_id == session_id,
                    )
                )
                chat_session = result.scalar_one_or_none()
                if chat_session:
                    chat_session.user_id = user_id
                    chat_session.user_role = user_role or chat_session.user_role or "school"
                    chat_session.school_id = school_id or chat_session.school_id
                    if title and (not chat_session.title or chat_session.title == "新会话"):
                        chat_session.title = title[:128]
                    chat_session.is_active = True
                    chat_session.updated_at = datetime.utcnow()
                    meta["title"] = chat_session.title or meta["title"]
                    meta["message_count"] = chat_session.message_count or 0
                    meta["created_at"] = (
                        chat_session.created_at.isoformat(timespec="seconds") + "Z"
                        if chat_session.created_at else now_text
                    )
                else:
                    chat_session = ChatSession(
                        company_id=company_id,
                        session_id=session_id,
                        user_id=user_id,
                        user_role=user_role or "school",
                        school_id=school_id or "",
                        title=title[:128],
                        preview="",
                        message_count=0,
                        is_active=True,
                    )
                    session.add(chat_session)
                await session.commit()
        except Exception:
            pass
        if not self.redis:
            return meta
        try:
            existing_raw = await self.redis.get(self._session_meta_key(company_id, session_id))
            if existing_raw:
                existing = json.loads(existing_raw)
                meta = {**existing, **{k: v for k, v in meta.items() if v not in ("", None)}}
                meta["updated_at"] = existing.get("updated_at") or now_text
                meta["created_at"] = existing.get("created_at") or now_text
                if existing.get("title") and existing.get("title") != "新会话":
                    meta["title"] = existing["title"]
            await self.redis.setex(
                self._session_meta_key(company_id, session_id),
                settings.session_ttl,
                json.dumps(meta, ensure_ascii=False),
            )
            await self.redis.zadd(
                self._user_sessions_key(company_id, user_id),
                {session_id: now_score},
            )
            await self.redis.expire(self._user_sessions_key(company_id, user_id), settings.session_ttl)
        except Exception:
            pass
        return meta

    async def persist_message(
        self,
        session_id: str,
        role: str,
        content: str,
        user_id: str = "dev_user",
        user_role: str = "school",
        company_id: str = settings.default_company_id,
        metadata: dict | None = None,
        trace_id: str | None = None,
        answer_id: str | None = None,
        school_id: str = "",
        title: str = "",
    ) -> dict:
        company_id = str(company_id or settings.default_company_id)
        user_id = str(user_id or "dev_user")
        metadata = metadata or {}
        await self.register_session(
            session_id,
            user_id=user_id,
            user_role=user_role,
            school_id=school_id,
            company_id=company_id,
            title=title or content,
        )
        message_dict = {
            "company_id": company_id,
            "session_id": session_id,
            "user_id": user_id,
            "user_role": user_role,
            "role": role,
            "content": content,
            "metadata": metadata,
            "trace_id": trace_id,
            "answer_id": answer_id,
            "timestamp": self._now_iso(),
        }
        try:
            async with async_session() as session:
                message = ChatMessage(
                    company_id=company_id,
                    session_id=session_id,
                    user_id=user_id,
                    user_role=user_role,
                    role=role,
                    content=content,
                    trace_id=trace_id,
                    answer_id=answer_id,
                    message_metadata=metadata,
                )
                session.add(message)
                await session.flush()
                count_result = await session.execute(
                    select(func.count(ChatMessage.id)).where(
                        ChatMessage.company_id == company_id,
                        ChatMessage.session_id == session_id,
                    )
                )
                message_count = count_result.scalar_one() or 0
                result = await session.execute(
                    select(ChatSession).where(
                        ChatSession.company_id == company_id,
                        ChatSession.session_id == session_id,
                    )
                )
                chat_session = result.scalar_one_or_none()
                if chat_session:
                    if title and (not chat_session.title or chat_session.title == "新会话"):
                        chat_session.title = title[:128]
                    chat_session.preview = content[:500]
                    chat_session.message_count = int(message_count)
                    chat_session.is_active = True
                    chat_session.updated_at = datetime.utcnow()
                await session.commit()
                await session.refresh(message)
                message_dict["id"] = message.id
        except Exception:
            pass
        return message_dict

    async def touch_session(
        self,
        session_id: str,
        user_id: str = "dev_user",
        user_role: str = "school",
        school_id: str = "",
        company_id: str = settings.default_company_id,
        title: str = "",
        message_count: int | None = None,
    ) -> dict:
        company_id = str(company_id or settings.default_company_id)
        user_id = str(user_id or "dev_user")
        meta = await self.register_session(
            session_id,
            user_id=user_id,
            user_role=user_role,
            school_id=school_id,
            company_id=company_id,
            title=title,
        )
        if not self.redis:
            return meta
        try:
            existing_raw = await self.redis.get(self._session_meta_key(company_id, session_id))
            if existing_raw:
                meta = json.loads(existing_raw)
            if title and (not meta.get("title") or meta.get("title") == "新会话"):
                meta["title"] = title.strip()[:80]
            if message_count is not None:
                meta["message_count"] = message_count
            meta["updated_at"] = self._now_iso()
            await self.redis.setex(
                self._session_meta_key(company_id, session_id),
                settings.session_ttl,
                json.dumps(meta, ensure_ascii=False),
            )
            await self.redis.zadd(
                self._user_sessions_key(company_id, user_id),
                {session_id: time.time()},
            )
            await self.redis.expire(self._user_sessions_key(company_id, user_id), settings.session_ttl)
        except Exception:
            pass
        return meta

    async def list_sessions(
        self,
        user_id: str = "dev_user",
        company_id: str = settings.default_company_id,
        limit: int = 30,
    ) -> list[dict]:
        company_id = str(company_id or settings.default_company_id)
        user_id = str(user_id or "dev_user")
        try:
            async with async_session() as session:
                result = await session.execute(
                    select(ChatSession)
                    .where(
                        ChatSession.company_id == company_id,
                        ChatSession.user_id == user_id,
                        ChatSession.is_active == True,
                    )
                    .order_by(ChatSession.updated_at.desc().nulls_last())
                    .limit(limit)
                )
                rows = result.scalars().all()
                if rows:
                    return [
                        {
                            "company_id": row.company_id,
                            "session_id": row.session_id,
                            "user_id": row.user_id,
                            "user_role": row.user_role or "",
                            "school_id": row.school_id or "",
                            "title": row.title or "新会话",
                            "preview": row.preview or "",
                            "message_count": row.message_count or 0,
                            "created_at": row.created_at.isoformat(timespec="seconds") + "Z"
                            if row.created_at else "",
                            "updated_at": row.updated_at.isoformat(timespec="seconds") + "Z"
                            if row.updated_at else "",
                        }
                        for row in rows
                    ]
        except Exception:
            pass

        if not self.redis:
            return []
        session_ids: list[str] = []
        scores: dict[str, float] = {}
        try:
            raw_items = await self.redis.zrevrange(
                self._user_sessions_key(company_id, user_id),
                0,
                max(limit - 1, 0),
                withscores=True,
            )
            for sid, score in raw_items:
                session_ids.append(str(sid))
                scores[str(sid)] = float(score)

            # Backfill older sessions created before the session index existed.
            async for key in self.redis.scan_iter(match=f"company:{company_id}:session:*:short_term"):
                sid = str(key).split(":session:", 1)[1].rsplit(":", 1)[0]
                if sid not in session_ids:
                    session_ids.append(sid)
        except Exception:
            return []

        sessions = []
        for sid in session_ids:
            try:
                meta_raw = await self.redis.get(self._session_meta_key(company_id, sid))
                meta = json.loads(meta_raw) if meta_raw else {}
                if meta.get("user_id") and meta.get("user_id") != user_id:
                    continue
                history = await self.get_short_term(sid, company_id=company_id)
                first_user = next(
                    (m.get("content", "") for m in history if m.get("role") == "user"),
                    "",
                )
                last_msg = history[-1].get("content", "") if history else ""
                title = meta.get("title") or first_user or "新会话"
                sessions.append({
                    "company_id": company_id,
                    "session_id": sid,
                    "user_id": meta.get("user_id") or user_id,
                    "user_role": meta.get("user_role") or "",
                    "school_id": meta.get("school_id") or "",
                    "title": str(title).strip()[:80],
                    "preview": str(last_msg).strip()[:120],
                    "message_count": meta.get("message_count") or len(history),
                    "created_at": meta.get("created_at") or "",
                    "updated_at": meta.get("updated_at") or "",
                    "last_active_ts": scores.get(sid, 0),
                })
            except Exception:
                continue
        sessions.sort(key=lambda item: item.get("last_active_ts") or 0, reverse=True)
        return sessions[:limit]

    async def get_persistent_history(
        self,
        session_id: str,
        company_id: str = settings.default_company_id,
        limit: int = 500,
    ) -> list[dict]:
        company_id = str(company_id or settings.default_company_id)
        try:
            async with async_session() as session:
                result = await session.execute(
                    select(ChatMessage)
                    .where(
                        ChatMessage.company_id == company_id,
                        ChatMessage.session_id == session_id,
                    )
                    .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
                    .limit(limit)
                )
                rows = result.scalars().all()
                if rows:
                    return [self._message_to_dict(row) for row in rows]
        except Exception:
            pass
        return await self.get_short_term(session_id, company_id=company_id)

    async def delete_session(
        self,
        session_id: str,
        company_id: str = settings.default_company_id,
        user_id: str | None = None,
    ):
        if not self.redis:
            try:
                async with async_session() as session:
                    result = await session.execute(
                        select(ChatSession).where(
                            ChatSession.company_id == str(company_id or settings.default_company_id),
                            ChatSession.session_id == session_id,
                        )
                    )
                    chat_session = result.scalar_one_or_none()
                    if chat_session:
                        chat_session.is_active = False
                        chat_session.updated_at = datetime.utcnow()
                        await session.commit()
            except Exception:
                pass
            return
        company_id = str(company_id or settings.default_company_id)
        try:
            async with async_session() as session:
                result = await session.execute(
                    select(ChatSession).where(
                        ChatSession.company_id == company_id,
                        ChatSession.session_id == session_id,
                    )
                )
                chat_session = result.scalar_one_or_none()
                if chat_session:
                    chat_session.is_active = False
                    chat_session.updated_at = datetime.utcnow()
                    await session.commit()
            meta_raw = await self.redis.get(self._session_meta_key(company_id, session_id))
            meta = json.loads(meta_raw) if meta_raw else {}
            uid = user_id or meta.get("user_id")
            await self.redis.delete(
                self._session_key(company_id, session_id, "short_term")
            )
            await self.redis.delete(
                self._session_key(company_id, session_id, "medium_term")
            )
            await self.redis.delete(self._session_meta_key(company_id, session_id))
            if uid:
                await self.redis.zrem(self._user_sessions_key(company_id, uid), session_id)
        except Exception:
            pass

    async def get_short_term(
        self,
        session_id: str,
        company_id: str = settings.default_company_id,
    ) -> list:
        if not self.redis:
            return []
        try:
            data = await self.redis.get(
                self._session_key(company_id, session_id, "short_term")
            )
            return json.loads(data) if data else []
        except Exception:
            return []

    async def append_short_term(
        self,
        session_id: str,
        message: dict,
        company_id: str = settings.default_company_id,
    ) -> list:
        if not self.redis:
            return []
        key = self._session_key(company_id, session_id, "short_term")
        history = await self.get_short_term(session_id, company_id=company_id)
        history.append(message)
        if len(history) > 10:  # 5 rounds
            evicted = history.pop(0)
            if evicted.get("role") == "user":
                await self._compress_to_medium(
                    session_id,
                    evicted,
                    company_id=company_id,
                )
        try:
            await self.redis.setex(
                key, settings.session_ttl,
                json.dumps(history, ensure_ascii=False),
            )
        except Exception:
            pass
        return history

    async def _compress_to_medium(
        self,
        session_id: str,
        evicted_message: dict,
        company_id: str = settings.default_company_id,
    ):
        key = self._session_key(company_id, session_id, "medium_term")
        current = {}
        try:
            raw = await self.redis.get(key)
            current = json.loads(raw) if raw else {}
        except Exception:
            pass
        summary = current.get("summary", "")
        new_line = f"Q: {evicted_message.get('content', '')}"
        if len(summary) + len(new_line) > settings.summary_max_length:
            summary = summary[: settings.summary_max_length // 2] + "..."
        summary = (summary + "\n" + new_line).strip()
        current["summary"] = summary
        current["version"] = current.get("version", 0) + 1
        try:
            await self.redis.setex(
                key, settings.session_ttl,
                json.dumps(current, ensure_ascii=False),
            )
        except Exception:
            pass

    # ========== Medium-term Memory ==========

    async def get_medium_term(
        self,
        session_id: str,
        company_id: str = settings.default_company_id,
    ) -> dict:
        if not self.redis:
            return {}
        try:
            raw = await self.redis.get(
                self._session_key(company_id, session_id, "medium_term")
            )
            return json.loads(raw) if raw else {}
        except Exception:
            return {}

    # ========== Long-term Memory (PostgreSQL) ==========

    async def get_user_profile(
        self,
        user_id: str,
        company_id: str = settings.default_company_id,
    ) -> dict:
        try:
            async with async_session() as session:
                result = await session.execute(
                    select(UserProfile).where(
                        UserProfile.user_id == user_id,
                        UserProfile.company_id == str(company_id or settings.default_company_id),
                    )
                )
                profile = result.scalar_one_or_none()
                if not profile:
                    return {}
                return {
                    "user_id": profile.user_id,
                    "company_id": profile.company_id,
                    "role": profile.role,
                    "school_name": profile.school_name or "",
                    "preferred_response_style": profile.preferred_response_style or "normal",
                    "total_sessions": profile.total_sessions or 0,
                    "total_questions": profile.total_questions or 0,
                    "avg_satisfaction": profile.avg_satisfaction,
                    "needs_human_priority": profile.needs_human_priority or False,
                }
        except Exception:
            return {}

    async def get_user_facts(
        self,
        user_id: str,
        limit: int = 10,
        company_id: str = settings.default_company_id,
    ) -> list:
        try:
            async with async_session() as session:
                result = await session.execute(
                    select(UserFact)
                    .where(
                        UserFact.user_id == user_id,
                        UserFact.company_id == str(company_id or settings.default_company_id),
                        UserFact.is_active == True,
                    )
                    .order_by(UserFact.last_mentioned_at.desc().nulls_last())
                    .limit(limit)
                )
                facts = result.scalars().all()
                return [
                    {"type": f.fact_type, "content": f.fact_content, "confidence": f.confidence}
                    for f in facts
                ]
        except Exception:
            return []

    async def get_frequent_questions(
        self,
        user_id: str,
        limit: int = 5,
        company_id: str = settings.default_company_id,
    ) -> list:
        try:
            async with async_session() as session:
                result = await session.execute(
                    select(UserFrequentQuestion)
                    .where(
                        UserFrequentQuestion.user_id == user_id,
                        UserFrequentQuestion.company_id == str(company_id or settings.default_company_id),
                    )
                    .order_by(UserFrequentQuestion.frequency.desc())
                    .limit(limit)
                )
                qs = result.scalars().all()
                return [
                    {"question": q.question_text, "answer": q.answer_text, "frequency": q.frequency}
                    for q in qs
                ]
        except Exception:
            return []

    async def update_user_profile(
        self,
        user_id: str,
        data: dict,
        company_id: str = settings.default_company_id,
    ):
        try:
            company_id = str(company_id or settings.default_company_id)
            async with async_session() as session:
                result = await session.execute(
                    select(UserProfile).where(
                        UserProfile.user_id == user_id,
                        UserProfile.company_id == company_id,
                    )
                )
                profile = result.scalar_one_or_none()
                if not profile:
                    profile = UserProfile(
                        company_id=company_id,
                        user_id=user_id,
                        role=data.get("role", "school"),
                    )
                    session.add(profile)
                for key, value in data.items():
                    if hasattr(profile, key):
                        setattr(profile, key, value)
                await session.commit()
        except Exception:
            pass

    async def get_context_snapshot(
        self,
        session_id: str,
        user_id: str,
        user_role: str = "school",
        school_name: str = "",
        company_id: str | None = None,
    ) -> dict:
        """一次性获取三层记忆的快照，返回适合填充模板的 dict.

        替代原 ContextAssembler.assemble() 中的记忆查询逻辑。
        """
        company_id = str(company_id or settings.default_company_id)

        # 短期记忆
        short_term = await self.get_short_term(session_id, company_id=company_id)
        recent_dialog = ""
        for msg in (short_term or [])[-10:]:
            role_label = "用户" if msg.get("role") == "user" else "助手"
            recent_dialog += f"{role_label}：{msg.get('content', '')}\n"

        # 中期记忆
        medium = await self.get_medium_term(session_id, company_id=company_id)
        session_summary = (medium or {}).get("summary", "无历史摘要")

        # 长期记忆
        profile = await self.get_user_profile(user_id, company_id=company_id)
        facts = await self.get_user_facts(user_id, limit=5, company_id=company_id)
        freq_qs = await self.get_frequent_questions(user_id, limit=3, company_id=company_id)

        user_facts_text = ""
        if facts:
            user_facts_text = "; ".join(
                [f"{f['type']}:{f['content']}" for f in facts]
            )

        freq_q_text = ""
        if freq_qs:
            freq_q_text = "; ".join([q["question"] for q in freq_qs])

        return {
            "role": user_role,
            "school_name": school_name or "",
            "preferred_style": profile.get("preferred_response_style", "标准专业"),
            "user_facts": user_facts_text,
            "frequent_questions": freq_q_text,
            "session_summary": session_summary,
            "recent_dialog": recent_dialog or "无",
        }


memory_manager = MemoryManager()
