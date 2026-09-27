"""种子数据脚本 - 初始化默认角色、行业模板、测试商户"""
import asyncio
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import async_session_factory, engine, Base
from app.models import User, Business, UserBusinessRole, Agent
from app.core.security import hash_password


async def seed():
    """生成种子数据"""
    async with async_session_factory() as session:
        # 1. 创建测试用户
        test_user = User(
            email="admin@aiow.test",
            phone="13800000000",
            password_hash=hash_password("admin123"),
            name="测试管理员",
            status="active",
        )
        session.add(test_user)
        await session.flush()

        # 2. 创建测试商户
        test_business = Business(
            name="AIOW 测试零售店",
            slug="aiow-test-retail",
            category="retail",
            sub_category="convenience",
            business_model="b2c",
            city="武汉",
            province="湖北",
            country="中国",
            timezone="Asia/Shanghai",
            currency="CNY",
            status="active",
            owner_id=test_user.id,
        )
        session.add(test_business)
        await session.flush()

        # 3. 绑定用户-商户-角色
        role = UserBusinessRole(
            user_id=test_user.id,
            business_id=test_business.id,
            role="owner",
            status="active",
        )
        session.add(role)

        # 4. 创建 Store Manager Agent
        agent = Agent(
            business_id=test_business.id,
            name="Store Manager",
            role="store_manager",
            autonomy_level="L2",
            status="ready",
            model="claude-3-5-sonnet-20240620",
            system_prompt_text="你是一家零售店的智能店长助手，负责商品、库存、订单和客户服务。",
        )
        session.add(agent)
        await session.flush()

        # 回写 agent_id 到 business
        test_business.agent_id = agent.id

        await session.commit()

        print(f"✓ 测试用户: admin@aiow.test / admin123 (ID={test_user.id})")
        print(f"✓ 测试商户: AIOW 测试零售店 (ID={test_business.id}, slug=aiow-test-retail)")
        print(f"✓ 角色绑定: owner")
        print(f"✓ Store Manager Agent (ID={agent.id})")
        print("\n种子数据生成完成！")


if __name__ == "__main__":
    asyncio.run(seed())
