# AIOW (AI Operating World)

> 让现实世界商业拥有 AI 自主经营能力的操作系统

## 项目简介

AIOW 是一个 Business Agent Operating System + Agent Commerce Network，将实体商业映射为可被 AI Agent 理解、管理、运营和交易的 Business Agent，并连接未来个人 AI Agent 的 A2A 商业网络。

> **v1.0 已通过六方评审**：[查看最终需求设计文档 v1.0](docs/aiow-requirements-v1.0.md)
> （商户CEO / 商户员工 / 平台运营 / 个人AI Agent / 技术研发 / 后台审计 六方合议通过）

## 文档索引

### 📌 最终需求（评审通过）

| 文档 | 说明 |
|------|------|
| [🎯 需求设计 v1.0（评审版）](docs/aiow-requirements-v1.0.md) | **最终交付文档**：13项P0功能、进化机制、A2A被动模式、安全三底线、开发计划 |

### 架构设计

| 文档 | 说明 |
|------|------|
| [系统概述与核心架构](docs/architecture/01-system-overview.md) | 系统定位、设计原则、总体架构、核心概念 |

### 五层架构

| 文档 | 说明 |
|------|------|
| [Layer 1: 商业数字孪生](docs/layers/01-business-digital-twin.md) | 数据模型、同步机制、接入适配器、状态机 |
| [Layer 2: Business Agent 运行时](docs/layers/02-agent-runtime.md) | 六大 Agent 角色、Skill 系统、Memory 系统、自主级别 |
| [Layer 3: 自主运营引擎](docs/layers/03-autonomous-engine.md) | OUPDEL 循环、感知/理解/规划/执行/评估/学习 |
| [Layer 4: A2A 商业网络](docs/layers/04-a2a-commerce.md) | A2A 协议、发现/协商/交易、Commerce Gateway |
| [Layer 5: 人类管理控制层](docs/layers/05-human-control-plane.md) | 审批、风控、权限、审计、监控、人工介入 |

### 安全架构

| 文档 | 说明 |
|------|------|
| [安全架构总览](docs/security/01-security-architecture.md) | 威胁模型、七层安全、代码层强制规则、测试方法 |

### 数据与 API

| 文档 | 说明 |
|------|------|
| [核心数据模型](docs/api/01-data-model.md) | 9 张核心表结构、ER 关系、状态机 |
| [API 接口规格](docs/api/02-api-spec.md) | 7 大接口组、REST API、事件流 |

### MVP 与路线图

| 文档 | 说明 |
|------|------|
| [MVP 范围定义](docs/mvp/01-mvp-scope.md) | 无人零售店场景、P0/P1/P2 功能、成功指标 |
| [开发路线图](docs/mvp/02-roadmap.md) | 6 个 Phase、里程碑、团队配置 |

### 详细设计（开发参考）

| 文档 | 说明 |
|------|------|
| [功能清单与模块总览](docs/design/01-function-catalog.md) | 33 个子模块功能清单、优先级矩阵、权限矩阵、安全门禁映射 |
| [核心功能详细设计](docs/design/02-core-function-design.md) | 数字孪生 / Agent / 自主运营 三大模块的实现机制与交互流程 |
| [用户操作流程手册](docs/design/03-user-operation-flows.md) | 6 种角色端到端操作流程、步骤说明、界面元素、预期结果 |
| [关键技术实现方案](docs/design/04-technical-implementation.md) | 6 大核心架构模式、伪代码、数据层设计、部署架构 |

## 目录结构

```
aiow-os/
├── docs/                    # 需求与设计文档
│   ├── architecture/        # 系统架构总览
│   ├── layers/              # 五层架构详细需求
│   ├── security/            # 安全架构设计
│   ├── api/                 # 数据模型与 API 规格
│   ├── mvp/                 # MVP 范围与开发路线图
│   ├── design/              # 详细设计文档（开发参考）
│   └── aiow-overview/       # HTML 总览报告
├── src/                     # 源代码（待开发）
├── tests/                   # 测试代码（待开发）
├── scripts/                 # 运维脚本（待开发）
└── data/                    # 示例数据（待补充）
```

## 设计借鉴

本系统深度借鉴 [Anthropic Commerce Agents](https://github.com/anthropics/commerce-agents/) 的工程实践，包括但不限于：

- **Fencing 文本隔离** — 所有外部数据在进入 LLM 前经过消毒和围栏包裹
- **Provenance Gates 来源证明** — 写入操作的对象必须来自会话内读取的记录
- **Stage-Approval-Apply 流程** — 高风险操作走暂存-审批-应用三级流程
- **Delegate 委托模式** — 分析委托给只读 Agent，不接触写入能力
- **Skill 按需加载** — 索引常驻，详细内容按需加载
- **Memory 生命周期** — 完整的记忆写入过滤、保留期、删除管理
- **服务端身份持有** — 身份在服务端绑定，工具参数从不携带主体 ID

## 版本

- **v1.0** — 六方评审通过，最终需求设计文档（2026-09-26）
- v0.2.0 — 补充详细设计文档：功能清单、核心功能设计、操作流程、技术实现方案（2026-09-26）
- v0.1.0 — 初始需求规格（2026-09-26）
