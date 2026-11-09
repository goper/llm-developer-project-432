"""Стоимость считается в Decimal по токенам из ответа модели."""

from decimal import Decimal

from app.core.config import Settings
from app.llm.cost import compute_cost, price_for


def test_cost_is_decimal_and_exact() -> None:
    s = Settings(_env_file=None)
    cost = compute_cost(1000, 500, price_for("main", s))
    assert isinstance(cost, Decimal)
    # 1000 * 0.50 / 1e6 + 500 * 1.50 / 1e6 = 0.0005 + 0.00075
    assert cost == Decimal("0.00125000")


def test_cheap_role_uses_cheap_prices() -> None:
    s = Settings(_env_file=None)
    assert compute_cost(1_000_000, 0, price_for("cheap", s)) == Decimal("0.05000000")
