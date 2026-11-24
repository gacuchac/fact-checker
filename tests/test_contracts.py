import copy

import pytest
from fact_checker.contracts import (
    SCHEMAS,
    ConfirmedStatements,
    FinalAnswer,
    JudgeScores,
    RetrievalResult,
    Verdicts,
)
from pydantic import ValidationError

CLAIM = "Language models use the middle of long contexts poorly."
QUOTE = "performance degrades when relevant information is in the middle"


def statement(id=0, implied_by="middle of long contexts", mark="confirmed"):
    return {
        "id": id,
        "text": "Models use the middle poorly.",
        "load_bearing": True,
        "implied_by": implied_by,
        "query": "middle long contexts",
        "kind": "explicit",
        "mark": mark,
    }


def confirmed(**over):
    base = {
        "claim": CLAIM,
        "statements": [statement()],
        "proposed": [],
        "edits": [{"op": "drop", "id": 1, "value": None}],
        "rounds": 1,
        "source": "chat",
    }
    base.update(over)
    return base


def evidence(quote=QUOTE):
    return {"passage_id": "2307.03172v3#2", "quote": quote, "stance": "supports"}


def sverdict(id=0, quote=QUOTE):
    return {
        "id": id,
        "queries": ["middle long contexts"],
        "evidence": [evidence(quote)],
        "verdict": "supported",
        "reason": "The paper reports it.",
    }


def verdicts(*ids, quote=QUOTE):
    return {"statements": [sverdict(i, quote) for i in ids]}


def retrieval():
    return {
        "query": "middle contexts",
        "k": 5,
        "per_doc": 2,
        "hits": [
            {
                "passage_id": "2307.03172v3#0",
                "doc_id": "2307.03172v3",
                "title": "Lost in the Middle",
                "score": 1.5,
                "text": "Some text.",
            }
        ],
    }


def final():
    return {
        "claim": CLAIM,
        "overall": {"verdict": "supported", "rule": 2},
        "statements": [
            {
                "id": 0,
                "text": "Models use the middle poorly.",
                "load_bearing": True,
                "mark": "confirmed",
                "model_verdict": "supported",
                "verdict": "unknown",
                "downgrade_reason": "quote_failed",
                "evidence": [
                    {
                        "doc_id": "2307.03172v3",
                        "title": "Lost in the Middle",
                        "authors": ["A", "B"],
                        "published": "2023-07-06",
                        "quote": QUOTE,
                        "stance": "supports",
                    }
                ],
                "dropped_quotes": [evidence()],
            }
        ],
        "counts": {"confirmed": 1, "user_edited": 0, "user_added": 0, "dropped": 0},
    }


DIMS = (
    "evidence_relevance",
    "statement_verdicts",
    "overreach",
    "conflict_handling",
    "aggregation",
    "unknown_calibration",
)


def scores(score=3):
    return {
        "model": "some-model",
        "seconds": 1.5,
        "dimensions": {d: {"score": score, "evidence": "because"} for d in DIMS},
        "flagged": [{"statement_id": 0, "dimension": "overreach", "reason": "r"}],
        "needs_attention": False,
    }


BUILDERS = {
    "confirmed": confirmed,
    "retrieval": retrieval,
    "verdicts": lambda: verdicts(0, 1),
    "final": final,
    "scores": scores,
}


@pytest.mark.parametrize("name", sorted(BUILDERS))
def test_us1_roundtrip(name):
    model = SCHEMAS[name]
    obj = model.model_validate(BUILDERS[name]())
    assert model.model_validate_json(obj.model_dump_json()) == obj


def test_us1_schemas_map_names_to_the_five_models():
    assert dict(SCHEMAS) == {
        "confirmed": ConfirmedStatements,
        "retrieval": RetrievalResult,
        "verdicts": Verdicts,
        "final": FinalAnswer,
        "scores": JudgeScores,
    }


def test_us1_schemas_is_read_only():
    with pytest.raises(TypeError):
        SCHEMAS["x"] = Verdicts


def test_us1_verdicts_rejects_missing_id():
    with pytest.raises(ValidationError):
        Verdicts.model_validate(verdicts(0), context={"confirmed_ids": {0, 1}})


def test_us1_verdicts_rejects_extra_id():
    with pytest.raises(ValidationError):
        Verdicts.model_validate(verdicts(0, 1), context={"confirmed_ids": {0}})


def test_us1_verdicts_accepts_exact_ids():
    v = Verdicts.model_validate(verdicts(1, 0), context={"confirmed_ids": {0, 1}})
    assert {s.id for s in v.statements} == {0, 1}


def test_us1_verdicts_rejects_duplicate_id():
    with pytest.raises(ValidationError):
        Verdicts.model_validate(verdicts(0, 0))


def test_us1_verdicts_rejects_quote_under_5_words():
    with pytest.raises(ValidationError):
        Verdicts.model_validate(verdicts(0, quote="only four words here"))


def test_us1_verdicts_accepts_5_word_quote():
    Verdicts.model_validate(verdicts(0, quote="exactly five words are here"))


def test_us1_confirmed_rejects_implied_by_not_in_claim():
    bad = confirmed(statements=[statement(implied_by="not in the claim at all")])
    with pytest.raises(ValidationError):
        ConfirmedStatements.model_validate(bad)


def test_us1_confirmed_accepts_user_added_implied_by_not_in_claim():
    ok = confirmed(statements=[statement(implied_by="not in the claim at all", mark="user_added")])
    ConfirmedStatements.model_validate(ok)


def test_us1_confirmed_does_not_check_implied_by_on_proposed():
    ok = confirmed(proposed=[statement(id=7, implied_by="not in the claim at all")])
    ConfirmedStatements.model_validate(ok)


@pytest.mark.parametrize("n", [0, 6])
def test_us1_confirmed_rejects_statement_count_outside_1_to_5(n):
    bad = confirmed(statements=[statement(id=i) for i in range(n)])
    with pytest.raises(ValidationError):
        ConfirmedStatements.model_validate(bad)


def test_us1_confirmed_accepts_5_statements():
    ConfirmedStatements.model_validate(confirmed(statements=[statement(id=i) for i in range(5)]))


def test_us1_confirmed_rejects_duplicate_statement_ids():
    bad = confirmed(statements=[statement(id=0), statement(id=0)])
    with pytest.raises(ValidationError):
        ConfirmedStatements.model_validate(bad)


@pytest.mark.parametrize("rounds", [-1, 4])
def test_us1_confirmed_rejects_rounds_outside_0_to_3(rounds):
    with pytest.raises(ValidationError):
        ConfirmedStatements.model_validate(confirmed(rounds=rounds))


@pytest.mark.parametrize("rounds", [0, 3])
def test_us1_confirmed_accepts_rounds_0_and_3(rounds):
    ConfirmedStatements.model_validate(confirmed(rounds=rounds))


def test_us1_confirmed_rejects_unknown_source():
    with pytest.raises(ValidationError):
        ConfirmedStatements.model_validate(confirmed(source="web"))


@pytest.mark.parametrize("name", sorted(BUILDERS))
def test_us1_contracts_reject_extra_field(name):
    obj = BUILDERS[name]()
    obj["bogus"] = 1
    with pytest.raises(ValidationError):
        SCHEMAS[name].model_validate(obj)


def test_us1_nested_models_reject_extra_field():
    obj = confirmed()
    obj["statements"][0]["bogus"] = 1
    with pytest.raises(ValidationError):
        ConfirmedStatements.model_validate(obj)


@pytest.mark.parametrize("bad", [0, 6])
def test_us1_judge_scores_rejects_score_outside_1_to_5(bad):
    with pytest.raises(ValidationError):
        JudgeScores.model_validate(scores(bad))


@pytest.mark.parametrize("ok", [1, 5])
def test_us1_judge_scores_accepts_score_1_and_5(ok):
    JudgeScores.model_validate(scores(ok))


def test_us1_judge_scores_rejects_unknown_flagged_dimension():
    obj = scores()
    obj["flagged"][0]["dimension"] = "vibes"
    with pytest.raises(ValidationError):
        JudgeScores.model_validate(obj)


@pytest.mark.parametrize("rule", [-1, 5])
def test_us1_final_rejects_rule_outside_0_to_4(rule):
    obj = final()
    obj["overall"]["rule"] = rule
    with pytest.raises(ValidationError):
        FinalAnswer.model_validate(obj)


def test_us1_final_rejects_unknown_downgrade_reason():
    obj = final()
    obj["statements"][0]["downgrade_reason"] = "because"
    with pytest.raises(ValidationError):
        FinalAnswer.model_validate(obj)


@pytest.mark.parametrize("name", ["confirmed", "verdicts", "final", "scores"])
def test_us1_file_contracts_carry_schema_version_1(name):
    obj = SCHEMAS[name].model_validate(BUILDERS[name]())
    assert obj.schema_version == 1
    assert '"schema_version":1' in obj.model_dump_json()


@pytest.mark.parametrize("name", ["confirmed", "verdicts", "final", "scores"])
def test_us1_file_contracts_reject_schema_version_2(name):
    obj = copy.deepcopy(BUILDERS[name]())
    obj["schema_version"] = 2
    with pytest.raises(ValidationError):
        SCHEMAS[name].model_validate(obj)
