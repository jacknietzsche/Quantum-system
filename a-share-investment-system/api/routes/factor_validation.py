"""因子验证 API — IC分析 + 相关性矩阵 + 样本外测试"""

from fastapi import APIRouter

from services.factor_validator import get_factor_validator
from shared.logging import emit_log

router = APIRouter()


@router.get("/report")
def get_validation_report():
    """获取最新因子验证报告 (从缓存或实时计算)"""
    try:
        return {
            "status": "ok",
            "message": "Use POST /api/factor-validation/run to trigger validation",
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.post("/run")
def run_validation(payload: dict | None = None):
    """运行因子验证

    body: {
        "price_data": {stock_code: [{date, close, ...}]},
        "factor_data": {date: {factor_name: value}},
        "forward_period": 5,
        "train_ratio": 0.7
    }
    """
    try:
        validator = get_factor_validator()
        data = payload or {}
        result = validator.validate_all(
            price_data=data.get("price_data", {}),
            factor_data=data.get("factor_data", {}),
            forward_period=data.get("forward_period", 5),
            train_ratio=data.get("train_ratio", 0.7),
        )
        return {"status": result.status, **result.data, "errors": result.errors}
    except Exception as e:
        emit_log("ERROR", "factor_validation", f"run: {e}")
        return {"status": "error", "error": str(e)}
