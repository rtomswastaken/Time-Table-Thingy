# Timetable Thingy 🗓️

An offline, local-first academic timetable generation and management desktop application built with **Python**, **CustomTkinter**, **SQLite**, and **Google OR-Tools CP-SAT**.

---

## 🚀 Overview

**Timetable Thingy** automates the complex combinatorial optimization task of generating institution-wide academic schedules. It accounts for:
- **Academic Structure:** Multiple departments, academic years, semesters, class cohorts, and practical student groups.
- **Faculty Management:** Teachers, qualifications, weekly/daily workload caps, max consecutive periods, and soft scheduling preferences.
- **Curricular Breakdown:** Theory lectures, multi-period laboratory blocks, tutorials, seminars, and projects with distinct credit vs. contact hour accounting.
- **Physical Resources:** Classrooms, lecture halls, computer labs, hardware labs, and room seating capacities.
- **Constraint Scheduling:** Google OR-Tools CP-SAT formulation ensuring zero double-booking (teacher, class, room), adherence to availability, and soft penalty optimization.
- **Interactive Workspace:** Multi-perspective timetable grid (Class, Faculty, Room), drag-and-drop / manual moves with real-time collision validation, session locking/pinning, undo/redo, and partial regeneration.
- **Import & Export:** Batch CSV / Excel curriculum import, publication-quality printable PDF timetable grid export, styled multi-tab Excel export, and analytical workload/room utilization reports.

---

## 📐 Architecture & Documentation

The architecture follows a strict decoupled design:
**Presentation (CustomTkinter) → Application Services → Domain Core & Protocols ← Infrastructure (SQLite) & Solver (OR-Tools)**

* **[System Architecture](docs/ARCHITECTURE.md)**: Layered design, dependency rules, threading model, and background execution.
* **[Domain Data Model](docs/DATA_MODEL.md)**: Entity specifications, identifier types, validation invariants, and domain definitions.
* **[Integration Contracts](docs/INTEGRATION_CONTRACTS.md)**: Concrete Python typing protocols (`Protocol`), input/output bundles, and service signatures.
* **[Development Workflow & Ownership](docs/DEVELOPMENT_WORKFLOW.md)**: Agent module ownership matrix, interface change governance, and quality gates.
* **[Database Persistence Specification](docs/DATABASE_PERSISTENCE.md)**: SQLite schema, WAL mode, foreign keys, and migration runner.

---

## 👥 8-Agent Subsystems & Directory Mapping

| Subsystem | Primary Package | Role & Deliverables |
|---|---|---|
| **Architecture** | `core/`, `docs/` | Shared domain models, protocols, exceptions, configuration defaults |
| **Database** | `database/` | SQLite connection manager, migrations runner, repository implementations |
| **Academic Management** | `academic/` | Services and CustomTkinter screens for institutions, departments, classes, subjects, rooms |
| **Faculty & Workload** | `workload/` | Availability matrices, soft preference weights, workload rules & analytics |
| **Scheduling Engine** | `solver/` (`engine/`) | Google OR-Tools CP-SAT model, constraint encoders, deterministic validator |
| **Timetable Workspace** | `gui/timetable/` | Multi-perspective timetable grid, manual move/swap editor, locked slot pins |
| **Import, Export & Reports** | `exchange/` (`reports/`) | CSV/Excel batch importers, styled Excel workbooks, printable PDF grids, reports |
| **Application Shell** | `app.py`, `main.py` | Unified application shell, responsive navigation sidebar, background solver thread |

---

## 🛠️ Quick Start & Setup

### Requirements
- Python 3.11+
- SQLite 3.35+ (standard library)

### 1. Initialize Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Launch the Application
```bash
python3 main.py
# or
python3 app.py
```

### 3. Run Automated Tests
```bash
pytest tests/ -v
```

---

## 📁 Repository Structure

```
├── app.py                         # Unified CustomTkinter desktop application shell
├── main.py                        # Application entry point
├── pyproject.toml                 # Build system & pytest configuration
├── requirements.txt               # Pinned Python dependencies
├── data.py                        # Legacy seed prototype data (preserved)
├── docs/                          # Architecture & contract specifications
│   ├── ARCHITECTURE.md
│   ├── DATA_MODEL.md
│   ├── DATABASE_PERSISTENCE.md
│   ├── DEVELOPMENT_WORKFLOW.md
│   └── INTEGRATION_CONTRACTS.md
├── core/                          # Shared domain foundation & protocols
│   ├── __init__.py
│   ├── config.py
│   ├── exceptions.py
│   ├── interfaces.py
│   └── models.py
├── database/                      # SQLite persistence & migrations
│   ├── connection.py
│   ├── schema.py
│   ├── backup.py
│   ├── migrations/
│   └── repositories/
├── academic/                      # Academic curriculum & management
│   ├── academic_service.py
│   ├── class_service.py
│   ├── institution_service.py
│   ├── period_service.py
│   ├── room_service.py
│   ├── subject_service.py
│   ├── teacher_service.py
│   └── ui/
├── workload/                      # Teacher preferences & workload rules
│   ├── calculator.py
│   ├── preferences.py
│   ├── rules.py
│   ├── service.py
│   └── ui/
├── solver/                        # OR-Tools CP-SAT scheduling engine
│   ├── cp_sat_solver.py
│   ├── constraints.py
│   ├── optimizer.py
│   ├── results.py
│   ├── session_builder.py
│   └── validator.py
├── gui/timetable/                 # Timetable grid & interactive editor
│   ├── session_card.py
│   ├── timetable_editor.py
│   ├── timetable_grid.py
│   └── timetable_views.py
├── exchange/                      # Tabular import, PDF/Excel export, reports
│   ├── service.py
│   ├── exporters/
│   ├── importers/
│   ├── reports/
│   └── ui/
├── templates/                     # CSV & Excel import templates
└── tests/                         # Complete test suite (184 tests)
    ├── database/
    ├── services/
    ├── ui/
    └── test_*.py
```
