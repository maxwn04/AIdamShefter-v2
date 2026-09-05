from typing import Literal

from backend.resources._contracts import ContractModel, NonBlankStr


class ScheduledReviewCondition(ContractModel):
    kind: Literal["scheduled_review"] = "scheduled_review"
    review_question: NonBlankStr
