"""RBAC 角色权限定义"""
from enum import Enum


class Role(str, Enum):
    """用户角色"""

    SUPER_ADMIN = "super_admin"  # 超级管理员
    OWNER = "owner"  # 商户所有者
    MANAGER = "manager"  # 商户管理员
    EMPLOYEE = "employee"  # 员工
    VIEWER = "viewer"  # 只读查看者
    AGENT = "agent"  # Agent 服务账号


# 角色权限矩阵
ROLE_PERMISSIONS = {
    Role.SUPER_ADMIN: {"*"},  # 所有权限
    Role.OWNER: {
        "business:*", "product:*", "sku:*", "inventory:*",
        "order:*", "customer:*", "agent:*", "user:read",
        "work_order:*", "approval:*", "alert:*", "dashboard:*",
        "loop:*", "memory:*", "feedback:*", "dashboard:*", "circuit:*", "audit:*",
    },
    Role.MANAGER: {
        "business:read", "business:update",
        "product:*", "sku:*", "inventory:*",
        "order:*", "customer:*", "agent:read",
        "user:read", "work_order:*", "approval:*",
        "alert:*", "dashboard:*", "loop:*", "memory:*",
    },
    Role.EMPLOYEE: {
        "business:read", "product:read", "sku:read", "inventory:read",
        "inventory:write", "order:read", "order:write",
        "customer:read", "agent:read", "work_order:read",
        "work_order:write", "dashboard:read", "loop:read", "memory:read",
    },
    Role.VIEWER: {
        "business:read", "product:read", "sku:read", "inventory:read",
        "order:read", "customer:read", "agent:read",
        "work_order:read", "dashboard:read", "loop:read", "memory:read",
    },
    Role.AGENT: {
        "business:read", "product:read", "sku:read", "inventory:read",
        "order:read", "customer:read", "agent:read",
        "work_order:read", "work_order:write", "dashboard:read",
        "loop:read", "loop:write", "memory:read", "memory:write", "feedback:read", "feedback:write",
    },
}


def has_permission(role: str, permission: str) -> bool:
    """检查角色是否拥有权限"""
    try:
        r = Role(role)
    except ValueError:
        return False

    perms = ROLE_PERMISSIONS.get(r, set())
    if "*" in perms:
        return True

    # 模块通配：product:* 匹配 product:read
    module = permission.split(":")[0]
    if f"{module}:*" in perms:
        return True

    return permission in perms
