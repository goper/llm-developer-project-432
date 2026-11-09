"""Маскирование персональных данных (ПДн) в тексте документа.

Маскирование идёт до вызова модели и до записи в лог. В findings попадают
только вид и метка, исходные значения туда не пишутся.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

# Разделители внутри номера: пробел, перенос строки, дефис, скобки, точка.
_PHONE_SEP = r"[\s\-().]"


@dataclass(frozen=True)
class PiiFinding:
    kind: str  # "phone" | "email" | "inn" | "card"
    label: str  # например "телефон номер один"


@dataclass(frozen=True)
class MaskResult:
    text: str
    findings: tuple[PiiFinding, ...]

    def __iter__(self):
        # Распаковка `cleaned, entities = mask_pii(text)`.
        yield self.text
        yield list(self.findings)


_KIND_WORDS = {"phone": "телефон", "email": "почта", "card": "карта", "inn": "инн"}

_PHONE_RE = re.compile(rf"(?<!\d)(?:\+7|8)(?:{_PHONE_SEP}*\d){{10}}(?!\d)")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
_CARD_RE = re.compile(r"(?<!\d)\d(?:[ -]?\d){12,18}(?!\d)")
_INN_RE = re.compile(r"(?<!\d)(?:\d{10}|\d{12})(?!\d)")

_ONES = (
    "ноль",
    "один",
    "два",
    "три",
    "четыре",
    "пять",
    "шесть",
    "семь",
    "восемь",
    "девять",
    "десять",
    "одиннадцать",
    "двенадцать",
    "тринадцать",
    "четырнадцать",
    "пятнадцать",
    "шестнадцать",
    "семнадцать",
    "восемнадцать",
    "девятнадцать",
)
_TENS = (
    "",
    "",
    "двадцать",
    "тридцать",
    "сорок",
    "пятьдесят",
    "шестьдесят",
    "семьдесят",
    "восемьдесят",
    "девяносто",
)
_HUNDREDS = (
    "",
    "сто",
    "двести",
    "триста",
    "четыреста",
    "пятьсот",
    "шестьсот",
    "семьсот",
    "восемьсот",
    "девятьсот",
)


def _ru_number(n: int) -> str:
    """Число словами (до 999), для меток вида «номер два»."""
    if n >= 1000:
        return str(n)
    if n < 20:
        return _ONES[n]
    if n < 100:
        tens, ones = divmod(n, 10)
        return _TENS[tens] + (f" {_ONES[ones]}" if ones else "")
    hundreds, rest = divmod(n, 100)
    return _HUNDREDS[hundreds] + (f" {_ru_number(rest)}" if rest else "")


def _luhn_ok(value: str) -> bool:
    digits = [int(c) for c in re.sub(r"\D", "", value)]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _checksum(digits: list[int], coefficients: list[int]) -> int:
    return (sum(d * c for d, c in zip(digits, coefficients, strict=False)) % 11) % 10


def _inn_ok(value: str) -> bool:
    """Проверка контрольной суммы ИНН (10 или 12 цифр)."""
    digits = [int(c) for c in value]
    if len(digits) == 10:
        return _checksum(digits[:9], [2, 4, 10, 3, 5, 9, 4, 6, 8]) == digits[9]
    if len(digits) == 12:
        first = _checksum(digits[:11], [7, 2, 4, 10, 3, 5, 9, 4, 6, 8, 0]) == digits[10]
        second = _checksum(digits[:11], [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) == digits[11]
        return first and second
    return False


def _always(_value: str) -> bool:
    return True


def _mask_kind(
    text: str,
    pattern: re.Pattern[str],
    kind: str,
    is_valid: Callable[[str], bool],
    findings: list[PiiFinding],
) -> str:
    """Заменяет все подходящие совпадения одного вида меткой. Нумерация идёт по порядку."""
    counter = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal counter
        value = match.group(0)
        if not is_valid(value):
            return value
        counter += 1
        label = f"{_KIND_WORDS[kind]} номер {_ru_number(counter)}"
        findings.append(PiiFinding(kind=kind, label=label))
        return label

    return pattern.sub(replace, text)


def mask_pii(text: str) -> MaskResult:
    """Заменяет телефоны, почту, номера карт и ИНН на метки.

    Порядок важен: телефоны до карт (11-значный номер не должен стать картой),
    карты до ИНН. Метки не содержат цифр, поэтому повторно их не заменят.
    """
    findings: list[PiiFinding] = []
    text = _mask_kind(text, _PHONE_RE, "phone", _always, findings)
    text = _mask_kind(text, _EMAIL_RE, "email", _always, findings)
    text = _mask_kind(text, _CARD_RE, "card", _luhn_ok, findings)
    text = _mask_kind(text, _INN_RE, "inn", _inn_ok, findings)
    return MaskResult(text=text, findings=tuple(findings))


def _inn_checksum(value: str) -> bool:
    """Проверка контрольной суммы ИНН (10 или 12 цифр). Имя из практики темы."""
    return _inn_ok(value)


def contains_pii(text: str) -> bool:
    """Есть ли в тексте персональные данные (телефон, почта, ИНН, карта)."""
    return bool(mask_pii(text).findings)
