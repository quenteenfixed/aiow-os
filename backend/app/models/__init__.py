"""所有 ORM 模型导入 - Alembic 自动检测用"""
from app.models.base import TimestampMixin, SoftDeleteMixin, UUIDMixin
from app.models.user import User, UserBusinessRole
from app.models.business import Business
from app.models.product import Product, SKU
from app.models.inventory import InventoryLog, InventoryBatch
from app.models.order import Order, OrderItem
from app.models.customer import Customer
from app.models.agent import Agent, AgentSession, AgentMessage, AgentMemory, AgentSkill
from app.models.work_order import WorkOrder, ApprovalAction, ExecutionJob
from app.models.operations import Alert, AuditLog, CircuitBreak
from app.models.a2a import A2AAgent, A2ASession, A2AMessage, A2AGatewayLog
from app.models.loop import AgentLoop, AgentLoopRun

__all__ = [
    # 基类
    "TimestampMixin", "SoftDeleteMixin", "UUIDMixin",
    # 业务
    "Business", "Product", "SKU", "InventoryLog", "InventoryBatch",
    "Order", "OrderItem", "Customer",
    # Agent
    "Agent", "AgentSession", "AgentMessage", "AgentMemory", "AgentSkill",
    # 运营
    "WorkOrder", "ApprovalAction", "ExecutionJob",
    "Alert", "AuditLog", "CircuitBreak",
    # OUPDEL 循环
    "AgentLoop", "AgentLoopRun",
    # A2A
    "A2AAgent", "A2ASession", "A2AMessage", "A2AGatewayLog",
    # IAM
    "User", "UserBusinessRole",
]
