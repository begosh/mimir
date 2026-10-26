# Deterministic computation for supported formulas and explicit tool need routing — 2026-10-25

Durable qualification for backlog item **P2.3** from [tasks/todo.md](../tasks/todo.md).

## Problem and historical failure mode

In previous evaluations ([execution conclusions](../docs/EXECUTION_CONCLUSIONS_2026-10-23.md) and [self-hardening assessment](../docs/SELF_HARDENING_ASSESSMENT_2026-10-23.md)):
1. Calculations were delegated to LLM calls, risking arithmetic hallucinations, approximation errors, and wasting model calls and tokens on simple math (such as hydration percentages or scaling ratios).
2. The result gate lacked deterministic arithmetic verification, relying on another model check to evaluate whether numbers were calculated correctly.
3. Workers were dispatched to native tool-using runtimes based on role conventions or indiscriminately, rather than checking an explicit tool need. In particular, the supplied-input critic (`Red-Team-Critic`) was routed through native tools in review mode even though it only consumes text findings from specialists.

## Implemented contract

1. **Deterministic Formula Engine (`scripts/formula_engine.py`)**:
   - **Quantity Extraction (`extract_quantities`)**: Deterministically parses named numbers, weights, and yields from text with unit normalizations (e.g. `kg` $\to$ `g`, `l` $\to$ `ml`).
   - **Safe AST Evaluation (`safe_eval_expression`)**: Restricts expression parsing strictly to arithmetic AST nodes (`BinOp`, `UnaryOp`, `Constant`, `Name`), forbidding arbitrary code execution, imports, or attributes.
   - **Supported Formula Registry**:
     - *Baker's hydration percentage*: `(water / flour) * 100`
     - *Baker's percentage for ingredients*: `(ingredient / flour) * 100`
     - *Batch scaling*: `amount * (target_yield / base_yield)`
     - *Total dough weight*: `sum(ingredients)`
     - *Explicit arithmetic expressions*: in task contracts or objectives.
   - **Direct Deterministic Execution (`execute_deterministic_calculation`)**: When a `calculate` task matches a supported formula with resolved operands, the engine computes the exact result with 0 model calls and 0 tokens, returning a structured result envelope with rationale.
   - **Truthful Missing Operand Handling**: If required operands are absent, the calculation records the missing inputs in `gaps` without guessing or fabricating numbers.
   - **Deterministic Result Gate Check (`check_calculation`)**: Deterministically validates that calculation claims match expected values within $\pm 0.15$ tolerance. Contradictory calculations are immediately rejected with `FAIL` (`check_type="deterministic_calculation"`).

2. **Explicit Tool Need Routing (`scripts/task_graph.py`, `scripts/scheduler.py`, `scripts/research_program.py`)**:
   - `TaskNode` includes an explicit `needs_tools: bool` contract.
   - In review mode, `critique` (`Red-Team-Critic`) sets `needs_tools = False` and routes to `spawn_restricted` (direct Responses text API), eliminating unnecessary tool runtime process boots.
   - Specialist workers investigating evidence (`evidence`, `alternatives`) maintain `needs_tools = True` and route to `spawn` (native tools).
   - In atomic decomposition, `retrieve` sets `needs_tools = True`, while text-only operations (`extract`, `calculate`, `compare`, `check`, `clarify`) set `needs_tools = False` and route to `spawn_restricted`.

## Verification

Qualified in `.venv-research` (Python 3.14.7 on Windows) via `tests/test_formula_and_tool_routing.py`:
- **Quantity extraction & safe AST evaluation**: Verified extraction of flour (600g), water (390g), salt (18g), yeast (1g), and yield (4 balls), and exact calculation of hydration (65.0%), salt percentage (3.0%), total weight (1009g), and scaled flour (900g).
- **Deterministic execution (0 tokens)**: `calculate` task executed deterministically, returning 65.0% hydration with `tokens_used=0` and 0 model calls.
- **Truthful missing operand handling**: Calculation with missing water operand properly returned missing operand notice in `gaps` without hallucinating a value.
- **Result gate verification**: `check_calculation` verified correct arithmetic and rejected contradictory calculation (72.5% vs 65.0%) with `FAIL`.
- **Review mode routing**: Verified that in review mode, `Domain-Analyst` and `Code-Architect` route to `spawn` (native tools), while `Red-Team-Critic` routes to `spawn_restricted` (text API).
- **Atomic tool need routing**: Verified that `retrieve` routes to `spawn`, while `extract` and `calculate` route to `spawn_restricted`.
- **Regression suites**:
  - `tests/test_formula_and_tool_routing.py`: 6 passed in 4.60s.
  - `tests/test_blocker_qualification.py`: 6 passed.
  - `tests/test_bounded_extraction.py`: 5 passed.
  - `tests/test_atomic_worker.py`: 2 passed.
  - `tests/test_extraction_checks.py`: 4 passed.
  - Core planner/scheduler regressions: 62 passed, 42 subtests.
  - Engine policy suite: 13 passed in 29.75s.

## Limitations and remaining gaps

- Supported formula registry currently covers core baking and batch calculations (hydration, baker's percentages, scaling ratios, sums, and explicit arithmetic expressions). Arbitrary domain-specific equations not expressible as arithmetic expressions require model execution.
- Comparison of the minimal checked baseline with recursive plans across frozen real-source case sets remains open under **P2.5**.
