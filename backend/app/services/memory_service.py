"""记忆服务 - 写入、检索、CRUD、过期清理

设计要点：
1. 多租户隔离：所有查询带 business_id + agent_id
2. 记忆类型：fact/preference/action/feedback
3. 重要程度 1-5：importance=1 的记忆自动设置 expires_at（默认 7 天）
4. 检索降级方案：pgvector 不可用时，用关键词匹配 + 重要度 + 最近使用排序
5. 过期记忆自动清理（每次查询时惰性清理 + 定时任务）
6. 检索相关度计算：词频重合度 × importance 权重 × 新鲜度衰减
"""
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.types import utcnow_naive
from app.models.agent import AgentMemory

logger = logging.getLogger(__name__)

# 中文停用词
_STOPWORDS = {"的", "了", "是", "在", "有", "我", "你", "他", "她", "它", "和", "与", "或", "也", "都", "就", "不", "没", "这", "那"}


# ===== 序列化 =====

def _memory_dict(m: AgentMemory, relevance_score: Optional[float] = None) -> dict:
    data = {
        "id": m.id,
        "agent_id": m.agent_id,
        "business_id": m.business_id,
        "memory_type": m.memory_type,
        "title": m.title,
        "content": m.content,
        "tags": m.tags or [],
        "importance": m.importance,
        "source": m.source,
        "source_id": m.source_id,
        "metadata_": m.metadata_ or {},
        "expires_at": m.expires_at.isoformat() if m.expires_at else None,
        "created_at": m.created_at.isoformat() if m.created_at else None,
        "updated_at": m.updated_at.isoformat() if m.updated_at else None,
    }
    if relevance_score is not None:
        data["relevance_score"] = round(relevance_score, 4)
    return data


# ===== 分词工具 =====

def _tokenize(text: str) -> set:
    """简单分词：中文按单字 + 英文按单词"""
    if not text:
        return set()
    # 提取英文单词（>=2 字符）
    words = set(re.findall(r'[a-zA-Z0-9]{2,}', text.lower()))
    # 提取中文字符（单字）
    chinese_chars = set(re.findall(r'[\u4e00-\u9fff]', text))
    # 过滤停用词
    tokens = words | {c for c in chinese_chars if c not in _STOPWORDS}
    return tokens


def _compute_relevance(query: str, title: str, content: str, tags: list, importance: int, created_at) -> float:
    """计算相关度分数（0-1）

    公式：词频重合度 × importance权重 × 新鲜度衰减
    """
    query_tokens = _tokenize(query)
    if not query_tokens:
        return 0.0

    text_tokens = _tokenize((title or "") + " " + (content or "") + " " + " ".join(tags or []))
    if not text_tokens:
        return 0.0

    # 词频重合度
    overlap = query_tokens & text_tokens
    overlap_ratio = len(overlap) / len(query_tokens) if query_tokens else 0.0

    # importance 权重：1→0.6, 3→1.0, 5→1.4
    importance_weight = 0.6 + (importance - 1) * 0.2

    # 新鲜度衰减：30 天内满分，之后线性衰减到 0.5
    if created_at:
        # 统一为 naive datetime 避免时区减法错误
        if created_at.tzinfo is not None:
            created_at_naive = created_at.replace(tzinfo=None)
        else:
            created_at_naive = created_at
        days_old = (datetime.now(timezone.utc).replace(tzinfo=None) - created_at_naive).days
        freshness = max(0.5, 1.0 - max(0, days_old - 30) / 365)
    else:
        freshness = 1.0

    score = overlap_ratio * importance_weight * freshness
    return min(1.0, score)


# ===== 创建 =====

async def create_memory(
    db: AsyncSession,
    business_id: int,
    agent_id: int,
    memory_type: str,
    title: str,
    content: str,
    tags: Optional[list] = None,
    importance: int = 3,
    source: str = "manual",
    source_id: Optional[int] = None,
    metadata_: Optional[dict] = None,
    ttl_hours: Optional[int] = None,
) -> AgentMemory:
    """创建记忆

    - importance=1 或 ttl_hours 不为空时，设置 expires_at
    - 默认临时记忆 7 天过期
    """
    valid_types = {"fact", "preference", "action", "feedback"}
    if memory_type not in valid_types:
        raise ValueError(f"非法记忆类型：{memory_type}（应为 {valid_types}）")

    # 计算过期时间
    expires_at = None
    if ttl_hours is not None:
        expires_at = utcnow_naive() + timedelta(hours=ttl_hours)
    elif importance == 1:
        # importance=1 的临时记忆默认 7 天过期
        expires_at = utcnow_naive() + timedelta(days=7)

    memory = AgentMemory(
        business_id=business_id,
        agent_id=agent_id,
        memory_type=memory_type,
        title=title,
        content=content,
        tags=tags or [],
        importance=importance,
        source=source,
        source_id=source_id,
        metadata_=metadata_ or {},
        expires_at=expires_at,
    )
    db.add(memory)
    await db.commit()
    await db.refresh(memory)
    logger.info(
        f"[MemoryService] 创建记忆 {memory.id}（type={memory_type}, importance={importance}, agent={agent_id}）"
    )
    return memory


# ===== 查询 CRUD =====

async def list_memories(
    db: AsyncSession,
    business_id: int,
    agent_id: int,
    memory_type: Optional[str] = None,
    tags: Optional[list] = None,
    source: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> Tuple[list, int]:
    """记忆列表（不含过期记忆）"""
    now = utcnow_naive()
    stmt = select(AgentMemory).where(
        AgentMemory.business_id == business_id,
        AgentMemory.agent_id == agent_id,
        or_(AgentMemory.expires_at.is_(None), AgentMemory.expires_at > now),
    )
    if memory_type:
        stmt = stmt.where(AgentMemory.memory_type == memory_type)
    if source:
        stmt = stmt.where(AgentMemory.source == source)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = stmt.order_by(AgentMemory.importance.desc(), AgentMemory.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    items = [_memory_dict(m) for m in (await db.execute(stmt)).scalars().all()]
    return items, total


async def get_memory(
    db: AsyncSession, business_id: int, agent_id: int, memory_id: int
) -> Optional[AgentMemory]:
    stmt = select(AgentMemory).where(
        AgentMemory.id == memory_id,
        AgentMemory.business_id == business_id,
        AgentMemory.agent_id == agent_id,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def update_memory(
    db: AsyncSession,
    business_id: int,
    agent_id: int,
    memory_id: int,
    *,
    title: Optional[str] = None,
    content: Optional[str] = None,
    tags: Optional[list] = None,
    importance: Optional[int] = None,
) -> Tuple[Optional[AgentMemory], Optional[str]]:
    """更新记忆"""
    memory = await get_memory(db, business_id, agent_id, memory_id)
    if memory is None:
        return None, "记忆不存在或无权访问"

    if title is not None:
        memory.title = title
    if content is not None:
        memory.content = content
    if tags is not None:
        memory.tags = tags
    if importance is not None:
        memory.importance = importance
        # importance=1 时设置过期时间为 7 天
        if importance == 1 and memory.expires_at is None:
            memory.expires_at = utcnow_naive() + timedelta(days=7)
        elif importance > 1:
            memory.expires_at = None  # 重要度提高后变为永久记忆

    await db.commit()
    await db.refresh(memory)
    return memory, None


async def delete_memory(
    db: AsyncSession,
    business_id: int,
    agent_id: int,
    memory_id: int,
) -> Tuple[bool, Optional[str]]:
    """删除记忆（物理删除，记忆不软删）"""
    memory = await get_memory(db, business_id, agent_id, memory_id)
    if memory is None:
        return False, "记忆不存在或无权访问"
    await db.delete(memory)
    await db.commit()
    return True, None


# ===== 检索 =====

async def search_memories(
    db: AsyncSession,
    business_id: int,
    agent_id: int,
    query: str,
    memory_type: Optional[str] = None,
    tags: Optional[list] = None,
    top_k: int = 5,
) -> list:
    """记忆检索（关键词匹配 + 重要度 + 新鲜度排序）

    Returns:
        [memory_dict with relevance_score, ...]，按相关度降序
    """
    now = utcnow_naive()
    stmt = select(AgentMemory).where(
        AgentMemory.business_id == business_id,
        AgentMemory.agent_id == agent_id,
        or_(AgentMemory.expires_at.is_(None), AgentMemory.expires_at > now),
    )
    if memory_type:
        stmt = stmt.where(AgentMemory.memory_type == memory_type)

    # 候选集取最近 200 条（性能优化，避免全表扫描）
    stmt = stmt.order_by(AgentMemory.created_at.desc()).limit(200)
    candidates = (await db.execute(stmt)).scalars().all()

    # 计算每条的相关度
    scored = []
    for m in candidates:
        # tags 过滤
        if tags:
            mem_tags = set(m.tags or [])
            if not any(t in mem_tags for t in tags):
                continue
        score = _compute_relevance(query, m.title, m.content, m.tags, m.importance, m.created_at)
        if score > 0:
            scored.append((m, score))

    # 按分数降序
    scored.sort(key=lambda x: x[1], reverse=True)
    return [_memory_dict(m, relevance_score=s) for m, s in scored[:top_k]]


# ===== 过期清理 =====

async def cleanup_expired(db: AsyncSession) -> int:
    """清理过期记忆，返回清理条数"""
    now = utcnow_naive()
    stmt = select(AgentMemory).where(
        AgentMemory.expires_at.is_not(None),
        AgentMemory.expires_at <= now,
    )
    expired = (await db.execute(stmt)).scalars().all()
    count = len(expired)
    for m in expired:
        await db.delete(m)
    if count > 0:
        await db.commit()
        logger.info(f"[MemoryService] 清理过期记忆 {count} 条")
    return count


# ===== 统计 =====

async def get_memory_stats(
    db: AsyncSession, business_id: int, agent_id: int
) -> dict:
    """记忆统计：按 type 和 importance 聚合"""
    now = utcnow_naive()
    base_stmt = select(AgentMemory).where(
        AgentMemory.business_id == business_id,
        AgentMemory.agent_id == agent_id,
        or_(AgentMemory.expires_at.is_(None), AgentMemory.expires_at > now),
    )

    # 按类型统计
    type_stmt = (
        select(AgentMemory.memory_type, func.count(AgentMemory.id))
        .where(
            AgentMemory.business_id == business_id,
            AgentMemory.agent_id == agent_id,
            or_(AgentMemory.expires_at.is_(None), AgentMemory.expires_at > now),
        )
        .group_by(AgentMemory.memory_type)
    )
    type_rows = (await db.execute(type_stmt)).all()
    type_dist = {row[0]: row[1] for row in type_rows}
    for t in ("fact", "preference", "action", "feedback"):
        type_dist.setdefault(t, 0)

    # 按重要度统计
    imp_stmt = (
        select(AgentMemory.importance, func.count(AgentMemory.id))
        .where(
            AgentMemory.business_id == business_id,
            AgentMemory.agent_id == agent_id,
            or_(AgentMemory.expires_at.is_(None), AgentMemory.expires_at > now),
        )
        .group_by(AgentMemory.importance)
    )
    imp_rows = (await db.execute(imp_stmt)).all()
    imp_dist = {str(row[0]): row[1] for row in imp_rows}
    for i in range(1, 6):
        imp_dist.setdefault(str(i), 0)

    total = sum(type_dist.values())
    return {
        "total": total,
        "type_distribution": type_dist,
        "importance_distribution": imp_dist,
    }
