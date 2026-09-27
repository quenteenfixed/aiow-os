"""会话管理器 - 持久化到 agent_sessions / agent_messages 表

关键职责：
1. 创建/恢复会话
2. 持久化每条消息（user / assistant / tool_result）
3. 加载历史上下文（最近 N 轮）
4. 关闭会话、更新摘要
"""
import logging
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.types import SessionContext, utcnow_naive
from app.models.agent import AgentSession, AgentMessage

logger = logging.getLogger(__name__)


class SessionManager:
    """会话生命周期管理"""

    # 历史上下文窗口（最近 N 条消息）
    MAX_HISTORY_MESSAGES = 20

    async def get_or_create_session(
        self,
        db: AsyncSession,
        agent_id: int,
        business_id: int,
        session_id: Optional[int],
        title: Optional[str] = None,
    ) -> SessionContext:
        """有 session_id 恢复，无则新建"""
        if session_id:
            sess = await self._load_session(db, session_id, agent_id, business_id)
            if sess is None:
                logger.warning(f"[Session] session_id={session_id} 不存在或越权，新建会话")
            else:
                # 加载历史消息
                messages = await self._load_messages(db, session_id)
                ctx = SessionContext(
                    session_id=sess.id,
                    agent_id=sess.agent_id,
                    business_id=sess.business_id,
                    session_type=sess.session_type,
                    title=sess.title,
                    status=sess.status,
                    messages=messages,
                )
                logger.info(f"[Session] 恢复会话 {sess.id}，历史 {len(messages)} 条消息")
                return ctx

        # 新建会话
        sess = AgentSession(
            agent_id=agent_id,
            business_id=business_id,
            session_type="chat",
            title=title or "新会话",
            status="active",
        )
        db.add(sess)
        await db.flush()
        ctx = SessionContext(
            session_id=sess.id,
            agent_id=sess.agent_id,
            business_id=sess.business_id,
            session_type=sess.session_type,
            title=sess.title,
            status=sess.status,
        )
        logger.info(f"[Session] 新建会话 {sess.id}")
        return ctx

    async def _load_session(
        self, db: AsyncSession, session_id: int, agent_id: int, business_id: int
    ) -> Optional[AgentSession]:
        """加载会话，校验归属"""
        stmt = select(AgentSession).where(
            AgentSession.id == session_id,
            AgentSession.agent_id == agent_id,
            AgentSession.business_id == business_id,
            AgentSession.status == "active",
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def _load_messages(self, db: AsyncSession, session_id: int) -> list:
        """加载历史消息，转换为 Claude API 格式"""
        stmt = select(AgentMessage).where(
            AgentMessage.session_id == session_id
        ).order_by(AgentMessage.created_at.asc()).limit(self.MAX_HISTORY_MESSAGES)
        result = await db.execute(stmt)
        msgs = result.scalars().all()

        messages = []
        for m in msgs:
            if m.role == "tool":
                # tool_result 块
                messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": m.tool_call_id or "",
                        "content": m.content or "",
                        "is_error": False,
                    }],
                })
            elif m.role == "assistant" and m.tool_calls:
                # assistant 消息含 tool_use 块
                content = []
                if m.content:
                    content.append({"type": "text", "text": m.content})
                if isinstance(m.tool_calls, list):
                    for tc in m.tool_calls:
                        content.append({
                            "type": "tool_use",
                            "id": tc.get("id", ""),
                            "name": tc.get("name", ""),
                            "input": tc.get("input", {}),
                        })
                elif isinstance(m.tool_calls, dict) and "blocks" in m.tool_calls:
                    for b in m.tool_calls["blocks"]:
                        content.append({
                            "type": "tool_use",
                            "id": b.get("id", ""),
                            "name": b.get("name", ""),
                            "input": b.get("input", {}),
                        })
                messages.append({"role": "assistant", "content": content})
            else:
                # 普通文本消息
                messages.append({"role": m.role, "content": m.content or ""})
        return messages

    async def add_user_message(
        self, db: AsyncSession, ctx: SessionContext, text: str
    ) -> None:
        """持久化用户消息，并追加到上下文"""
        msg = AgentMessage(
            session_id=ctx.session_id,
            agent_id=ctx.agent_id,
            role="user",
            content=text,
        )
        db.add(msg)
        await db.flush()
        ctx.messages.append({"role": "user", "content": text})

    async def add_assistant_message(
        self,
        db: AsyncSession,
        ctx: SessionContext,
        text: Optional[str],
        tool_calls: Optional[list] = None,
    ) -> None:
        """持久化助手消息（可能含 tool_use 块）"""
        tool_calls_json = None
        if tool_calls:
            tool_calls_json = {"blocks": tool_calls}

        msg = AgentMessage(
            session_id=ctx.session_id,
            agent_id=ctx.agent_id,
            role="assistant",
            content=text,
            tool_calls=tool_calls_json,
        )
        db.add(msg)
        await db.flush()

        # 追加到上下文
        if tool_calls:
            content = []
            if text:
                content.append({"type": "text", "text": text})
            for tc in tool_calls:
                content.append({
                    "type": "tool_use",
                    "id": tc.get("id", ""),
                    "name": tc.get("name", ""),
                    "input": tc.get("input", {}),
                })
            ctx.messages.append({"role": "assistant", "content": content})
        else:
            ctx.messages.append({"role": "assistant", "content": text or ""})

    async def add_tool_result(
        self,
        db: AsyncSession,
        ctx: SessionContext,
        tool_call_id: str,
        tool_name: str,
        content: str,
        is_error: bool = False,
    ) -> None:
        """持久化工具结果消息"""
        msg = AgentMessage(
            session_id=ctx.session_id,
            agent_id=ctx.agent_id,
            role="tool",
            content=content,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
        )
        db.add(msg)
        await db.flush()
        ctx.messages.append({
            "role": "user",
            "content": [{
                "type": "tool_result",
                "tool_use_id": tool_call_id,
                "content": content,
                "is_error": is_error,
            }],
        })

    async def close_session(
        self, db: AsyncSession, ctx: SessionContext, summary: Optional[str] = None
    ) -> None:
        """关闭会话"""
        stmt = (
            update(AgentSession)
            .where(AgentSession.id == ctx.session_id)
            .values(
                status="closed",
                closed_at=utcnow_naive(),
                context_summary=summary,
            )
        )
        await db.execute(stmt)
        await db.flush()
        ctx.status = "closed"

    async def update_summary(
        self, db: AsyncSession, ctx: SessionContext, summary: str
    ) -> None:
        """更新会话摘要（不关闭）"""
        stmt = (
            update(AgentSession)
            .where(AgentSession.id == ctx.session_id)
            .values(context_summary=summary)
        )
        await db.execute(stmt)
        await db.flush()
        ctx.context_summary = summary
