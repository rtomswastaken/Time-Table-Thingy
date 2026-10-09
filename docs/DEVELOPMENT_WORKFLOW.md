# Timetable Thingy - Multi-Agent Development Workflow

This document establishes the collaboration rules, module ownership, interface change governance, and quality gates for the 8-agent development team.

---

## 1. Agent Responsibilities & Explicit File Ownership

To prevent merge conflicts and overwriting working code, each agent has exclusive write ownership over designated directories and files.

| Agent | Core Responsibility | Exclusive Write Directory / Files | Primary Dependencies |
|---|---|---|---|
| **Agent 1** | System Architect | `docs/`, `core/` (interfaces, models, base exceptions) | None |
| **Agent 2** | Database Architect | `database/`, SQLite schema migrations, DB tests | `core/` |
| **Agent 3** | Academic Management | `academic/` (services & views for departments, subjects, classes, rooms) | `core/`, `database/` |
| **Agent 4** | Preferences & Workload | `workload/` (faculty availability, preferences, workload analytics) | `core/`, `academic/` |
| **Agent 5** | Scheduling Engine | `solver/` (CP-SAT solver, constraint formulation, validator) | `core/` |
| **Agent 6** | Timetable Workspace | `gui/timetable/` (grid view, manual move/swap, locked session pins) | `core/`, `solver/` (validator), `academic/` |
| **Agent 7** | Import, Export & Reports | `exchange/` (CSV/Excel import, PDF/Excel export, report generators) | `core/`, `academic/`, `workload/` |
| **Agent 8** | Application Shell & Integration | `gui/shell/`, `gui/common/`, `app.py`, `main.py` entry point | All modules |

### Rules of File Ownership:
1. **Never edit another agent's primary directory** without documented alignment.
2. **`core/` is immutable to Agents 2–8**: Any addition to `core/models.py`, `core/interfaces.py`, or `core/exceptions.py` must follow the Interface Change Procedure (Section 2).
3. If an agent needs helper utilities specific to their domain, create them within their owned package (e.g. `solver/utils.py`, `database/helpers.py`), NOT in `core/`.

---

## 2. Shared Interface Change Procedure

If an agent discovers that a model or interface contract in `core/` is missing a field or requires modification:

1. **Do not modify `core/` silently.**
2. Propose the addition with justification:
   - Identify the exact interface/model.
   - Describe the new field/method, type signature, and default value (to preserve backwards compatibility).
   - Verify that existing tests in `tests/test_core.py` will not break.
3. Update `docs/INTEGRATION_CONTRACTS.md` and `docs/DATA_MODEL.md` simultaneously.

---

## 3. Git Safety Rules

1. **No Destructive Commands**: Never run `git reset --hard`, `git checkout .`, `git clean -fd`, or `git push --force`.
2. **Preserve Untracked / Modified Files**: Verify status with `git status` before executing any file operations.
3. **Commit Rules**:
   - Each agent should commit only files within their designated ownership.
   - Commit messages must follow Conventional Commits:
     - `feat(solver): implement teacher consecutive period constraint`
     - `feat(db): add sqlite migration for subject session requirements`
     - `test(core): add duration validation tests`

---

## 4. Testing & Quality Requirements

Every agent must provide unit and integration tests for their module:

```bash
# To run all project tests:
.venv/bin/pytest tests/ -v

# To run tests for a specific module:
.venv/bin/pytest tests/test_core.py -v
.venv/bin/pytest tests/test_solver.py -v
.venv/bin/pytest tests/test_database.py -v
```

### Mandatory Verification Gates:
- **No Mocking the Universe**: Repositories must be tested against real SQLite in-memory databases (`:memory:`).
- **Solver Invariant**: Any schedule returned with `SchedulingStatus.OPTIMAL` or `FEASIBLE` must produce zero violations when evaluated by `ScheduleValidator`.
- **Zero GUI in Core/Solver**: Running `import solver` or `import core` in a headless environment must never trigger Tkinter or GUI initialization.

---

## 5. Agent Reporting Template

When an agent completes their task, they must provide a standardized completion summary:

```markdown
### Agent Completion Report: Agent [N] - [Role]

1. **Responsibilities Executed**:
   - [Bullet list of implemented capabilities]

2. **Files Created or Modified**:
   - [List of paths]

3. **Interfaces Implemented or Consumed**:
   - Implemented: [e.g., TimetableSolver, ScheduleValidator]
   - Consumed: [e.g., TimetableRepository]

4. **Verification & Test Results**:
   - Command run: `.venv/bin/pytest tests/...`
   - Test count and pass/fail summary.

5. **Notes & Handoff for Subsequent Agents**:
   - [Important nuances, performance notes, or dependencies for downstream agents]
```
