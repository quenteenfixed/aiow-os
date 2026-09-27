"""统一响应格式 + 异常体系 + request_id 中间件"""
import uuid as uuid_lib
from typing import Any, Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


def generate_request_id() -> str:
    """生成 request_id"""
    return str(uuid_lib.uuid4())


class RequestContextMiddleware(BaseHTTPMiddleware):
    """为每个请求注入 request_id 到响应头"""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or generate_request_id()
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


def success_response(
    data: Any = None,
    message: str = "success",
    request_id: Optional[str] = None,
) -> dict:
    """成功响应"""
    return {
        "code": 0,
        "message": message,
        "data": data,
        "request_id": request_id or generate_request_id(),
    }


def error_response(
    code: int,
    message: str,
    request_id: Optional[str] = None,
    details: Any = None,
) -> dict:
    """错误响应"""
    resp = {
        "code": code,
        "message": message,
        "data": None,
        "request_id": request_id or generate_request_id(),
    }
    if details is not None:
        resp["data"] = details
    return resp


# ===== 业务异常体系 =====
class BizException(Exception):
    """业务异常基类"""

    def __init__(
        self,
        code: int = 50000,
        message: str = "Internal Server Error",
        details: Any = None,
        status_code: int = 200,
    ):
        self.code = code
        self.message = message
        self.details = details
        self.status_code = status_code
        super().__init__(message)


class AuthException(BizException):
    """认证异常"""

    def __init__(self, message: str = "Unauthorized", code: int = 40100):
        super().__init__(code=code, message=message, status_code=401)


class PermissionException(BizException):
    """权限异常"""

    def __init__(self, message: str = "Forbidden", code: int = 40300):
        super().__init__(code=code, message=message, status_code=403)


class NotFoundException(BizException):
    """资源不存在"""

    def __init__(self, message: str = "Not Found", code: int = 40400):
        super().__init__(code=code, message=message, status_code=404)


class ValidationException(BizException):
    """参数校验异常"""

    def __init__(self, message: str = "Validation Error", code: int = 40001, details: Any = None):
        super().__init__(code=code, message=message, details=details, status_code=422)


class ConflictException(BizException):
    """资源冲突"""

    def __init__(self, message: str = "Conflict", code: int = 40900):
        super().__init__(code=code, message=message, status_code=409)


class RateLimitException(BizException):
    """限流异常"""

    def __init__(self, message: str = "Rate Limit Exceeded", code: int = 42900):
        super().__init__(code=code, message=message, status_code=429)


async def biz_exception_handler(request: Request, exc: BizException) -> JSONResponse:
    """业务异常处理器"""
    request_id = getattr(request.state, "request_id", None) or generate_request_id()
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response(exc.code, exc.message, request_id, exc.details),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """参数校验异常处理器"""
    request_id = getattr(request.state, "request_id", None) or generate_request_id()
    return JSONResponse(
        status_code=422,
        content=error_response(40001, "参数校验失败", request_id, exc.errors()),
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """通用异常处理器"""
    request_id = getattr(request.state, "request_id", None) or generate_request_id()
    return JSONResponse(
        status_code=500,
        content=error_response(50000, "Internal Server Error", request_id),
    )


class PaginatedData:
    """分页数据封装"""

    def __init__(self, items: list, total: int, page: int, page_size: int):
        self.items = items
        self.total = total
        self.page = page
        self.page_size = page_size
        self.total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0

    def to_dict(self) -> dict:
        return {
            "items": self.items,
            "total": self.total,
            "page": self.page,
            "page_size": self.page_size,
            "total_pages": self.total_pages,
        }
