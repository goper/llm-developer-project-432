"""Стоимость вызова. Деньги считаем в Decimal, округляем до 1e-8 доллара."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.core.config import Settings

MILLION = Decimal(1_000_000)
QUANT = Decimal("0.00000001")


@dataclass(frozen=True)
class Price:
    input_per_mtok: Decimal
    output_per_mtok: Decimal


def price_for(role: str, settings: Settings) -> Price:
    if role == "cheap":
        return Price(settings.price_cheap_input_per_mtok, settings.price_cheap_output_per_mtok)
    return Price(settings.price_main_input_per_mtok, settings.price_main_output_per_mtok)


def compute_cost(prompt_tokens: int, completion_tokens: int, price: Price) -> Decimal:
    """Стоимость = токены на входе * цена входа + токены на выходе * цена выхода, всё в Decimal."""
    total = (
        Decimal(prompt_tokens) * price.input_per_mtok + Decimal(completion_tokens) * price.output_per_mtok
    ) / MILLION
    return total.quantize(QUANT, rounding=ROUND_HALF_UP)
