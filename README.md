# AIGov-Sep25
AI Governance - Code
# Fair Sight AI Governance Prototype

This repository tracks the implementation of the Fair Sight AI Governance hackathon prototype.
The first component focuses on converting an Excel governance workbook into the JSON configuration
consumed by the forthcoming Streamlit application.

## Excel Parser

The `generate_config_from_excel.py` script converts the Excel workbook into a configuration
containing gate definitions, artifact schemas, and domain-aware G3 checkpoint mappings.

### Usage

```bash
python generate_config_from_excel.py path/to/governance.xlsx --output governance_config.json
```

### Installation

```bash
pip install -r requirements-dev.txt
```

### Testing

```bash
pytest
```

The parser uses pandas and openpyxl to respect the Excel-first source of truth described in the
product specification.
