from pathlib import Path

import pandas as pd
import pytest

from fairsight.excel_parser import generate_config_from_excel, infer_widget_type


@pytest.fixture()
def sample_workbook(tmp_path: Path) -> Path:
    path = tmp_path / "governance.xlsx"

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame(
            [
                {
                    "Checkpoint": "Define AI Objective",
                    "Artifacts Produced": "AI Charter",
                },
                {
                    "Checkpoint": "Identify Stakeholders",
                    "Artifacts Produced": "Stakeholder Register; Risk Assessment",
                },
            ]
        ).to_excel(writer, sheet_name="G0_Ideation", index=False)

        pd.DataFrame(
            [
                {
                    "Checkpoint": "Design Experiment",
                    "Artifacts Produced": "Experiment Plan",
                },
                {
                    "Checkpoint": "Assess Ethics",
                    "Artifacts Produced": "Ethics Checklist",
                },
            ]
        ).to_excel(writer, sheet_name="G1_Design", index=False)

        pd.DataFrame({"Fields": ["Objective*", "Start Date", "Success Metrics"]}).to_excel(
            writer, sheet_name="AI Charter", index=False
        )

        pd.DataFrame(
            {"Fields": ["Stakeholder Name*", "Role", "Engagement Level"]}
        ).to_excel(writer, sheet_name="Stakeholder Register", index=False)

        pd.DataFrame({"Fields": ["Risk Description*", "Severity", "Mitigation Plan"]}).to_excel(
            writer, sheet_name="Risk Assessment", index=False
        )

        pd.DataFrame({"Fields": ["Experiment Name*", "Method", "Date"]}).to_excel(
            writer, sheet_name="Experiment Plan", index=False
        )

        pd.DataFrame({"Fields": ["Ethics Principle", "Status", "Reviewer"]}).to_excel(
            writer, sheet_name="Ethics Checklist", index=False
        )

        pd.DataFrame(
            {
                "Domain": ["Default", "Healthcare", "Finance"],
                "Checkpoint": [
                    "Design Experiment",
                    "Assess Ethics",
                    "Assess Ethics",
                ],
            }
        ).to_excel(writer, sheet_name="G3_Domain_Map", index=False)

    return path


def test_generate_config_from_excel_parses_sections(sample_workbook: Path):
    config = generate_config_from_excel(sample_workbook)

    assert {gate["gate_id"] for gate in config["gates"]} == {"G0", "G1"}
    ideation_gate = next(g for g in config["gates"] if g["gate_id"] == "G0")
    assert ideation_gate["gate_name"] == "Ideation"
    assert ideation_gate["checkpoints"] == [
        "Define AI Objective",
        "Identify Stakeholders",
    ]
    assert ideation_gate["artifacts"] == [
        "AI Charter",
        "Stakeholder Register",
        "Risk Assessment",
    ]

    artifacts = config["artifacts"]
    assert "AI Charter" in artifacts
    objective_field = next(field for field in artifacts["AI Charter"] if field["name"] == "objective")
    assert objective_field == {
        "name": "objective",
        "label": "Objective",
        "input_type": "textarea",
        "required": True,
    }

    assert config["domain_checklist_map"] == {
        "_default": ["Design Experiment"],
        "Healthcare": ["Assess Ethics"],
        "Finance": ["Assess Ethics"],
    }


def test_infer_widget_type_heuristics():
    assert infer_widget_type("Launch Date") == "date"
    assert infer_widget_type("Success %") == "number"
    assert infer_widget_type("Has Bias") == "checkbox"
    assert infer_widget_type("Review Status") == "single_select"
    assert infer_widget_type("Stakeholder Tags") == "multi_select"
    assert infer_widget_type("Risk Description") == "textarea"
    assert infer_widget_type("Notes") == "text"