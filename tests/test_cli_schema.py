import json

import pytest
from fact_checker.cli import main
from fact_checker.contracts import SCHEMAS, Verdicts


def test_us6_schema_verdicts_prints_model_json_schema(capsys):
    assert main(["schema", "verdicts"]) == 0
    assert json.loads(capsys.readouterr().out) == Verdicts.model_json_schema()


@pytest.mark.parametrize("name", ["confirmed", "retrieval", "verdicts", "final", "scores"])
def test_us6_schema_each_name_prints_its_schema(name, capsys):
    assert main(["schema", name]) == 0
    assert json.loads(capsys.readouterr().out) == SCHEMAS[name].model_json_schema()


def test_us6_schema_unknown_name_exits_2():
    with pytest.raises(SystemExit) as exc:
        main(["schema", "nope"])
    assert exc.value.code == 2
