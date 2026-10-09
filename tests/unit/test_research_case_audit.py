import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from ledgerquant.research.artifacts import publish_audit
from ledgerquant.research.audit import audit_cases
from ledgerquant.research.contracts import ContractError, load_frozen_contract


BASE_CONTRACT = json.loads(
    (
        Path(__file__).parents[2]
        / "documents/research/hypotheses/eurusd_four_hour_direction_2020_v1.json"
    ).read_text(encoding="utf-8")
)


def frozen_fixture(tmp_path: Path, csv_rows: list[str], *, alter=None):
    source = tmp_path / "ticks.csv"
    source.write_text("\n".join(csv_rows) + "\n", encoding="ascii")
    contract = deepcopy(BASE_CONTRACT)
    contract["feature_contract"]["source_file"] = "ticks.csv"
    contract["feature_contract"]["source_sha256"] = hashlib.sha256(
        source.read_bytes()
    ).hexdigest()
    contract["development_window"].update(
        start_inclusive_utc="2020-01-02T00:00:00Z",
        end_exclusive_utc="2020-01-03T00:00:00Z",
    )
    contract["validation_windows"][0].update(
        start_inclusive_utc="2020-01-03T00:00:00Z",
        end_exclusive_utc="2020-01-04T00:00:00Z",
    )
    if alter:
        alter(contract)
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")
    freeze = {
        "schema_version": 1,
        "event_type": "CONTRACT_FROZEN",
        "hypothesis_id": contract["hypothesis_id"],
        "contract_path": "contract.json",
        "contract_sha256": hashlib.sha256(contract_path.read_bytes()).hexdigest(),
    }
    freeze_path = tmp_path / "freeze.json"
    freeze_path.write_text(json.dumps(freeze), encoding="utf-8")
    return source, freeze_path


def test_case_audit_respects_quote_direction_staleness_and_holdout(tmp_path):
    _, freeze_path = frozen_fixture(
        tmp_path,
        [
            "2020-01-02,07:00:00.000,1.10000,1.10010",
            "2020-01-02,08:00:00.000,1.10020,1.10030",
            "2020-01-02,08:00:00.000,1.10021,1.10031",
            "2020-01-02,12:00:00.000,1.10040,1.10050",
            "2020-01-02,15:00:00.000,1.10060,1.10070",
            "2020-01-02,16:00:00.000,1.10080,1.10090",
            "2020-01-02,20:02:00.000,1.10100,1.10110",
        ],
    )
    contract = load_frozen_contract(tmp_path, freeze_path)
    audit = audit_cases(contract, tmp_path)
    dev = [case for case in audit.cases if case["window"] == "development"]
    validation = [case for case in audit.cases if case["window"] == "validation"]

    assert [case["status"] for case in dev] == [
        "MEASURABLE",
        "INPUT_MISSING",
        "OUTCOME_MISSING",
    ]
    assert dev[0]["inputs"]["anchor"]["source_line"] == 3
    assert dev[0]["inputs"]["anchor"]["midquote"] == "1.10026"
    assert dev[0]["settlement"]["event_at_utc"] == "2020-01-02T12:00:00Z"
    assert dev[1]["inputs"]["lookback"]["age_ms"] == 10_800_000
    assert dev[1]["inputs"]["lookback"]["midquote"] is None
    assert dev[2]["settlement"]["delay_ms"] == 120_000
    assert len(validation) == 3
    assert all(case["status"] == "INPUT_MISSING" for case in validation)

    manifest = publish_audit(audit, tmp_path / "out")
    inputs = [
        json.loads(line)
        for line in (tmp_path / "out" / manifest["decision_inputs_file"]).read_text().splitlines()
    ]
    eligibility = [
        json.loads(line)
        for line in (tmp_path / "out" / manifest["case_eligibility_file"]).read_text().splitlines()
    ]
    assert len(inputs) == len(eligibility) == 6
    assert manifest["counts_by_window"]["development"] == {
        "MEASURABLE": 1,
        "INPUT_MISSING": 1,
        "OUTCOME_MISSING": 1,
    }
    assert all("settlement" not in row and "status" not in row for row in inputs)
    assert inputs[0]["inputs"]["anchor"]["midquote"] == "1.10026"
    assert all("inputs" not in row and "midquote" not in json.dumps(row) for row in eligibility)
    assert all("source_line" not in row["settlement"] for row in eligibility)
    assert all("bid" not in json.dumps(row) and "ask" not in json.dumps(row) for row in eligibility)
    with pytest.raises(ContractError, match="already exists"):
        publish_audit(audit, tmp_path / "out")


def test_modified_source_fails_before_publication(tmp_path):
    source, freeze_path = frozen_fixture(
        tmp_path, ["2020-01-02,08:00:00.000,1.10000,1.10010"]
    )
    source.write_text("2020-01-02,08:00:00.000,1.10001,1.10010\n", encoding="ascii")
    contract = load_frozen_contract(tmp_path, freeze_path)

    with pytest.raises(ContractError, match="source SHA-256"):
        audit_cases(contract, tmp_path)
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize(
    "rows,error",
    [
        (["2020-01-02,08:00:00.000,1.10020,1.10010"], "crossed quote"),
        (
            [
                "2020-01-02,08:00:00.000,1.10000,1.10010",
                "2020-01-02,07:00:00.000,1.10000,1.10010",
            ],
            "timestamp reversal",
        ),
        (["2020-01-02,08:00:00.000,broken,1.10010"], "malformed row"),
    ],
)
def test_invalid_source_rows_fail_closed(tmp_path, rows, error):
    _, freeze_path = frozen_fixture(tmp_path, rows)
    contract = load_frozen_contract(tmp_path, freeze_path)
    with pytest.raises(ContractError, match=error):
        audit_cases(contract, tmp_path)


def test_contract_hash_and_unsupported_policy_fail_closed(tmp_path):
    _, freeze_path = frozen_fixture(
        tmp_path, ["2020-01-02,08:00:00.000,1.10000,1.10010"]
    )
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(contract_path.read_text() + " ", encoding="utf-8")
    with pytest.raises(ContractError, match="contract SHA-256"):
        load_frozen_contract(tmp_path, freeze_path)

    _, freeze_path = frozen_fixture(
        tmp_path,
        ["2020-01-02,08:00:00.000,1.10000,1.10010"],
        alter=lambda contract: contract["payoff_contract"].update(path_dependent=True),
    )
    with pytest.raises(ContractError, match="path-dependent"):
        load_frozen_contract(tmp_path, freeze_path)

    _, freeze_path = frozen_fixture(
        tmp_path,
        ["2020-01-02,08:00:00.000,1.10000,1.10010"],
        alter=lambda contract: contract["feature_contract"].update(
            quote_calculation="bid only"
        ),
    )
    with pytest.raises(ContractError, match="quote calculation"):
        load_frozen_contract(tmp_path, freeze_path)
