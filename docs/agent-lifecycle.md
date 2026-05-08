# The Lifecycle of an AI Agent using Saurix

This walkthrough illustrates how an AI Agent (like Claude or Antigravity) uses Saurix to solve a real-world task: **"Modify the data persistence layer to support PostgreSQL."**

---

### Phase 0: Triggering a Smart Workflow (Optional)
Before the agent even looks at the code, the user can jumpstart the process using a pre-defined **MCP Prompt**.
- **User Action**: Selects the `repo_onboarding` prompt.
- **Agent Instruction**: "You are an expert architect. Index the repo, get stats, and explain the entry points."
- **Benefit**: The agent is immediately put into a "High-Level Architecture" mindset without manual prompting.

### Phase 1: Environmental Awareness (The Bird's Eye View)
The agent is dropped into a 50,000-line repository it has never seen.
- **Agent Action**: Calls `saurix.stats()`.
- **Knowledge Gained**: "Okay, this is 80% Python with 450 nodes. It's a medium-sized OO project."
- **Next Step**: The agent uses `find_symbol(query="persistence")` to locate the `DatabaseStore` class in `core/db.py`.
- **Benefit**: The agent doesn't have to guess where the "important" files are.

### Phase 2: Navigation (Finding the Entry Point)
The agent needs to find where the database logic is actually used.
- **Agent Action**: Calls `saurix.find_symbol(query="Database")`.
- **Knowledge Gained**: It finds `core.persistence:SQLiteStore` and `core.persistence:BaseStore`.
- **Benefit**: Instant pinpointing of relevant classes without reading irrelevant "database" mentions in documentation or logs.

### Phase 3: Relationship Mapping (Connecting the Dots)
The agent needs to know how the rest of the app interacts with the database.
- **Agent Action**: Calls `saurix.path_between(source="cli.app:main", target="core.persistence:SQLiteStore")`.
- **Knowledge Gained**: "The flow is: `main` -> `CommandDispatcher` -> `RepositoryIndexer` -> `GraphStore` -> `SQLiteStore`."
- **Benefit**: The agent now understands the **Data Flow** of the entire application across 5 different files.

### Phase 4: Risk Assessment (The "Blast Radius")
The agent is about to change the `BaseStore` interface to support PostgreSQL.
- **Agent Action**: Calls `saurix.impact_of_symbol(symbol="core.persistence:BaseStore")`.
- **Knowledge Gained**: "Wait, if I change this interface, I will break 12 different tests and 3 exporters I didn't know existed."
- **Benefit**: The agent identifies potential regressions **before** it even starts writing code.

### Phase 5: Implementation & Verification
The agent writes the new `PostgresStore` class.
- **Agent Action**: Calls `saurix.index_repo(source=".")`.
- **Knowledge Gained**: The agent verifies that the new class is correctly "seen" by the graph and that its inheritance edges to `BaseStore` are active.
- **Benefit**: Final structural verification that the new code is correctly integrated into the system.

---

### Comparison: With vs. Without Saurix

| Feature | Without Saurix | With Saurix |
| :--- | :--- | :--- |
| **Discovery** | Reads 20 files (Slow, Expensive) | `stats()` + `find()` (Instant, Cheap) |
| **Data Flow** | Manually traces imports (Error-prone) | `path_between()` (Absolute precision) |
| **Safety** | "Guess" what might break | `impact()` (Transitive dependencies) |
| **Confidence** | Low (Missing context) | High (Full architectural map) |
