"""安全门禁管线 - 5 道门禁 + Pipeline 编排

门禁执行顺序：
1. Fencing    - 围栏标记检测（防 prompt injection）
2. Provenance - 来源校验（防越权 ID，仅 write）
3. Guardrail  - 参数护栏（防危险参数）
4. RateLimit  - 频率限制
5. Approval   - 审批门禁（仅 write，高风险需审批）
"""
from app.agent.gates.fencing import FencingGate
from app.agent.gates.provenance import ProvenanceGate
from app.agent.gates.guardrail import GuardrailGate
from app.agent.gates.rate_limit import RateLimitGate, get_rate_limit_gate
from app.agent.gates.approval import ApprovalGate
from app.agent.gates.pipeline import GatePipeline, get_gate_pipeline

__all__ = [
    "FencingGate",
    "ProvenanceGate",
    "GuardrailGate",
    "RateLimitGate",
    "ApprovalGate",
    "GatePipeline",
    "get_rate_limit_gate",
    "get_gate_pipeline",
]
