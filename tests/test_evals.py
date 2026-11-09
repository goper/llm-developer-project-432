"""Метрики: нормализация значений, цитирование, разбор вердикта судьи, промпт судьи на подмене."""

from evals.metrics import characteristic_match, citation_match, judge_support, normalize_value, parse_judge


class FakeJudge:
    def __init__(self, text: str) -> None:
        self.text = text
        self.messages = None

    def chat(self, messages, *, purpose, job_id=None, cheap=False, json_schema=None):
        self.messages = messages
        assert purpose == "judge" and cheap is True
        return type("R", (), {"text": self.text})()


def test_values_are_normalized() -> None:
    assert normalize_value("800 Вт") == normalize_value("800 вт") == normalize_value("800 Вт.") == "800вт"
    assert normalize_value("1,5 л") == normalize_value("1.5 л")


def test_characteristic_match_ignores_format() -> None:
    golden = {"Мощность": "800 Вт", "Объём мерного стакана": "1,5 л"}
    card = {"мощность": "800 вт.", "Объём мерного стакана": "1.5 л"}
    assert characteristic_match(golden, card) == (2, 2)


def test_citation_checks_probe_text_and_page() -> None:
    probes = {"Мощность": {"page": 1, "text_contains": "800 Вт"}}
    chunks = {"c1": {"text": "Мощность 800 Вт", "page": 1}, "c2": {"text": "Мощность 800 Вт", "page": 2}}
    assert citation_match(probes, {"Мощность": "c1"}, chunks) == (1, 1)
    assert citation_match(probes, {"Мощность": "c2"}, chunks) == (0, 1)


def test_judge_verdict_is_parsed_and_prompt_has_fragments() -> None:
    assert parse_judge('{"supported_share": 0.75}') == 0.75
    assert (
        parse_judge('{"claims": [{"claim": "a", "supported": true}, {"claim": "b", "supported": false}]}')
        == 0.5
    )
    assert parse_judge("не json") is None
    fake = FakeJudge('{"supported_share": 1}')
    share = judge_support(fake, "[chunk_id=c1]\n800 Вт", {"title": "t"}, job_id=None)
    assert share == 1.0
    assert "chunk_id=c1" in fake.messages[1]["content"]
