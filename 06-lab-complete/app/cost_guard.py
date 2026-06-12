"""
Cost Guard — Bảo vệ budget LLM

Track chi phí token theo ngày. Block khi vượt budget.

Pricing reference (GPT-4o-mini, thay đổi theo model):
  Input:  $0.15 / 1M tokens  →  $0.00015 / 1K tokens
  Output: $0.60 / 1M tokens  →  $0.00060 / 1K tokens

Limitation: in-memory, reset khi restart.
Production: persist vào Redis với TTL 24h.
"""
import time
import logging
from fastapi import HTTPException

from app.config import settings

logger = logging.getLogger(__name__)

# Giá GPT-4o-mini (update khi đổi model)
_PRICE_INPUT_PER_1K = 0.00015
_PRICE_OUTPUT_PER_1K = 0.00060


def _estimate_cost(input_tokens: int, output_tokens: int) -> float:
    """Tính chi phí cho 1 request dựa trên số tokens ước tính."""
    return (
        (input_tokens / 1000) * _PRICE_INPUT_PER_1K
        + (output_tokens / 1000) * _PRICE_OUTPUT_PER_1K
    )


class DailyBudgetGuard:
    """
    Global daily budget guard.

    Đơn giản hoá cho lab: track tổng cost của toàn service trong ngày.
    Reset tự động khi sang ngày mới.
    """

    def __init__(self, daily_budget_usd: float):
        self.daily_budget_usd = daily_budget_usd
        self._today: str = time.strftime("%Y-%m-%d")
        self._spent: float = 0.0
        self._request_count: int = 0

    def _maybe_reset(self) -> None:
        """Reset counter nếu đã sang ngày mới."""
        today = time.strftime("%Y-%m-%d")
        if today != self._today:
            logger.info(
                f"Daily reset: spent=${self._spent:.4f} over {self._request_count} requests"
            )
            self._today = today
            self._spent = 0.0
            self._request_count = 0

    def check(self) -> None:
        """
        Kiểm tra budget trước khi gọi LLM.
        Raise HTTP 503 nếu đã hết budget trong ngày.
        """
        self._maybe_reset()
        if self._spent >= self.daily_budget_usd:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "Daily budget exhausted",
                    "spent_usd": round(self._spent, 4),
                    "budget_usd": self.daily_budget_usd,
                    "resets_at": "midnight UTC",
                },
            )
        # Cảnh báo khi dùng >= 80%
        if self._spent >= self.daily_budget_usd * 0.8:
            logger.warning(
                f"Budget warning: ${self._spent:.4f} / ${self.daily_budget_usd} "
                f"({self._spent/self.daily_budget_usd*100:.0f}%)"
            )

    def record(self, input_tokens: int, output_tokens: int) -> float:
        """
        Ghi nhận chi phí sau khi request hoàn thành.
        Returns: cost của request này (USD).
        """
        self._maybe_reset()
        cost = _estimate_cost(input_tokens, output_tokens)
        self._spent += cost
        self._request_count += 1
        logger.info(
            f"Cost recorded: +${cost:.6f} | "
            f"daily total=${self._spent:.4f}/{self.daily_budget_usd}"
        )
        return cost

    @property
    def stats(self) -> dict:
        self._maybe_reset()
        return {
            "date": self._today,
            "spent_usd": round(self._spent, 4),
            "budget_usd": self.daily_budget_usd,
            "remaining_usd": round(max(0, self.daily_budget_usd - self._spent), 4),
            "used_pct": round(self._spent / self.daily_budget_usd * 100, 1),
            "request_count": self._request_count,
        }


# Singleton
cost_guard = DailyBudgetGuard(daily_budget_usd=settings.daily_budget_usd)
