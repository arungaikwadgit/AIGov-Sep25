"""Utilities for transforming governance Excel workbooks into JSON config."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import re
from typing import Dict, Iterable, List, Sequence

import pandas as pd

# Regular expression to detect gate sheets such as ``G0_Initiation`` or ``G1-Design``
_GATE_SHEET_PATTERN = re.compile(r"^(G\d+)\s*[-_]\s*(.+)$", re.IGNORECASE)

# Candidate sheet names that encode domain-to-checkpoint mappings for G3.
_DOMAIN_MAPPING_SHEETS = {
    "G3_DOMAIN_MAP",
    "G3_DOMAIN_MAPPING",
    "DOMAIN_CHECKLIST_MAP",
}


@dataclass
class FieldSchema:
    """Structured representation of a field inside an artifact schema."""

    name: str
    label: str
    input_type: str
    required: bool

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "label": self.label,
            "input_type": self.input_type,
            "required": self.required,
        }


def _normalize_identifier(value: str) -> str:
    """Normalize a string for case-insensitive sheet lookups."""

    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _normalize_sheet_name(sheet_name: str) -> str:
    """Normalize sheet names for comparisons."""

    return sheet_name.strip().upper().replace(" ", "_")


def _split_artifact_cell(value) -> List[str]:
    """Split an artifact cell into a list of artifact names."""

    if pd.isna(value):
        return []
    if isinstance(value, str):
        parts = re.split(r"[,\n;/]+", value)
        return [part.strip() for part in parts if part and part.strip()]
    # Fall back to a string representation for unexpected types
    text = str(value).strip()
    return [text] if text else []


def _append_unique(target: List[str], items: Iterable[str]) -> None:
    """Append items to the target list while preserving order and uniqueness."""

    seen = set(target)
    for item in items:
        if item not in seen:
            target.append(item)
            seen.add(item)


def infer_widget_type(label: str) -> str:
    """Infer the input widget type for a field based on naming conventions."""

    text = label.lower()
    if "date" in text:
        return "date"
    if any(keyword in text for keyword in ("count", "number", "num", "%", "ratio")):
        return "number"
    if re.search(r"\b(is|has)\b", text) or "flag" in text:
        return "checkbox"
    if any(keyword in text for keyword in ("type", "status", "method")):
        return "single_select"
    if any(keyword in text for keyword in ("tags", "labels", "stakeholder")):
        return "multi_select"
    if any(keyword in text for keyword in ("description", "objective")):
        return "textarea"
    return "text"


def _slugify_field_name(label: str) -> str:
    """Transform a human-readable field label into a machine-friendly key."""

    slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    return slug or re.sub(r"[^a-z0-9]+", "", label.lower()) or "field"


def _parse_artifact_sheet(df: pd.DataFrame, artifact_name: str) -> List[FieldSchema]:
    """Parse a sheet describing an artifact schema."""

    if "Fields" not in df.columns:
        raise ValueError(f"Artifact sheet '{artifact_name}' must include a 'Fields' column.")

    fields: List[FieldSchema] = []
    for raw_field in df["Fields"].dropna():
        label = str(raw_field).strip()
        if not label:
            continue
        required = label.endswith("*")
        if required:
            label = label[:-1].strip()
        field_schema = FieldSchema(
            name=_slugify_field_name(label),
            label=label,
            input_type=infer_widget_type(label),
            required=required,
        )
        fields.append(field_schema)

    if not fields:
        raise ValueError(f"Artifact sheet '{artifact_name}' does not define any fields.")

    return fields


def _parse_gate_sheet(df: pd.DataFrame, sheet_name: str, gate_id: str, gate_name: str) -> Dict[str, object]:
    """Parse a gate sheet into its checkpoints and artifacts."""

    expected_columns = {"Checkpoint", "Artifacts Produced"}
    missing = expected_columns - set(df.columns)
    if missing:
        raise ValueError(
            f"Gate sheet '{sheet_name}' is missing required columns: {', '.join(sorted(missing))}"
        )

    checkpoints: List[str] = []
    artifacts: List[str] = []
    for _, row in df.iterrows():
        checkpoint_val = row.get("Checkpoint")
        artifact_val = row.get("Artifacts Produced")

        checkpoint = str(checkpoint_val).strip() if not pd.isna(checkpoint_val) else ""
        if checkpoint:
            checkpoints.append(checkpoint)

        artifact_entries = _split_artifact_cell(artifact_val)
        _append_unique(artifacts, artifact_entries)

    if not checkpoints:
        raise ValueError(f"Gate sheet '{sheet_name}' does not include any checkpoints.")

    return {
        "gate_id": gate_id.upper(),
        "gate_name": gate_name.strip(),
        "checkpoints": checkpoints,
        "artifacts": artifacts,
    }


def _parse_domain_mapping(df: pd.DataFrame) -> Dict[str, List[str]]:
    """Parse the domain mapping sheet into a dictionary."""

    required_columns = {"Domain", "Checkpoint"}
    if not required_columns.issubset(df.columns):
        raise ValueError(
            "Domain mapping sheet must include 'Domain' and 'Checkpoint' columns."
        )

    mapping: Dict[str, List[str]] = {}
    for _, row in df.iterrows():
        domain_raw = row.get("Domain")
        checkpoint_raw = row.get("Checkpoint")

        domain = str(domain_raw).strip() if not pd.isna(domain_raw) else ""
        checkpoint = str(checkpoint_raw).strip() if not pd.isna(checkpoint_raw) else ""
        if not domain or not checkpoint:
            continue

        key = "_default" if domain.lower() in {"default", "fallback"} else domain
        mapping.setdefault(key, [])
        if checkpoint not in mapping[key]:
            mapping[key].append(checkpoint)

    return mapping


def generate_config_from_excel(excel_path: Path | str) -> Dict[str, object]:
    """Generate the governance configuration dictionary from an Excel workbook."""

    excel_path = Path(excel_path)
    if not excel_path.exists():
        raise FileNotFoundError(f"Excel file not found: {excel_path}")

    workbook = pd.ExcelFile(excel_path)
    sheet_lookup = {_normalize_identifier(name): name for name in workbook.sheet_names}

    gates: List[Dict[str, object]] = []
    referenced_artifacts: List[str] = []

    for sheet_name in workbook.sheet_names:
        normalized_sheet = _normalize_sheet_name(sheet_name)
        if normalized_sheet in _DOMAIN_MAPPING_SHEETS:
            continue

        match = _GATE_SHEET_PATTERN.match(sheet_name.strip())
        if not match:
            continue
        gate_id, gate_name = match.groups()
        gate_df = workbook.parse(sheet_name)
        gate_config = _parse_gate_sheet(gate_df, sheet_name, gate_id, gate_name)
        gates.append(gate_config)
        _append_unique(referenced_artifacts, gate_config["artifacts"])

    if not gates:
        raise ValueError("No gate sheets were discovered in the workbook.")

    artifacts_config: Dict[str, List[Dict[str, object]]] = {}
    for artifact in referenced_artifacts:
        normalized = _normalize_identifier(artifact)
        sheet_name = sheet_lookup.get(normalized)
        if not sheet_name:
            raise ValueError(
                f"Artifact '{artifact}' is referenced by a gate but no matching sheet was found."
            )
        artifact_df = workbook.parse(sheet_name)
        fields = _parse_artifact_sheet(artifact_df, artifact)
        artifacts_config[artifact] = [field.to_dict() for field in fields]

    domain_mapping: Dict[str, List[str]] = {}
    for sheet_name in workbook.sheet_names:
        if _normalize_sheet_name(sheet_name) in _DOMAIN_MAPPING_SHEETS:
            df = workbook.parse(sheet_name)
            parsed = _parse_domain_mapping(df)
            for domain, checkpoints in parsed.items():
                domain_mapping.setdefault(domain, [])
                for checkpoint in checkpoints:
                    if checkpoint not in domain_mapping[domain]:
                        domain_mapping[domain].append(checkpoint)

    if not domain_mapping:
        # Fall back to using the first G3 gate definition as the default mapping.
        g3_gate = next((gate for gate in gates if gate["gate_id"].upper() == "G3"), None)
        if g3_gate:
            domain_mapping["_default"] = list(g3_gate["checkpoints"])

    return {
        "gates": gates,
        "artifacts": artifacts_config,
        "domain_checklist_map": domain_mapping,
    }


def main(args: Sequence[str] | None = None) -> None:
    """CLI entrypoint used by the standalone script."""

    import argparse

    parser = argparse.ArgumentParser(
        description="Generate Fair Sight governance configuration from an Excel workbook.",
    )
    parser.add_argument("excel", type=Path, help="Path to the Excel workbook input")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("governance_config.json"),
        help="Destination path for the generated JSON configuration",
    )
    parsed_args = parser.parse_args(args)

    config = generate_config_from_excel(parsed_args.excel)
    parsed_args.output.write_text(json.dumps(config, indent=2))
    print(f"Configuration generated at {parsed_args.output}")


if __name__ == "__main__":
    main()