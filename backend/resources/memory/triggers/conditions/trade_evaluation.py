from typing import Literal

from backend.resources._contracts import ContractModel


class TradeEvaluationCondition(ContractModel):
    kind: Literal["trade_evaluation"] = "trade_evaluation"
