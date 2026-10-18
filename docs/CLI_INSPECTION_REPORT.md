# Repository Inspection Report

1. **Current architecture**: FastAPI (`backend/main.py`) running a WebSockets server, connecting to the network simulator in `simulator/network/topology.py`, and serving a React frontend in `frontend/`. The WASP engine lives in `wasp/` (controller, privacy, shielding, crypto, forwarding, monitor). The experiment engine lives in `experiments/runner.py`.
2. **Working components**: `simulator` (caching, routing, timing), `wasp` core mathematics (PES, sigmoid, etc.), `experiments`, backend API, and React frontend.
3. **Broken components**: None identified in the baseline.
4. **Stubbed components**: Advanced attack extensions (timing, cache-probing) are likely stubbed/not fully implemented.
5. **Mock data**: We already purged all mock data in previous phases. `Math.random()` and fakers do not exist in the production codebase.
6. **Core logic**: Exists in `wasp/` directory. It is mostly decoupled from the UI, but we must ensure it is cleanly invokable by a CLI.
7. **UI coupling**: The experiment runner is currently triggered via FastAPI (`/api/simulation/start`), but it uses the independent `experiments/runner.py`.
8. **Recommended migration plan**: Create a `cli` module utilizing `typer` and `rich`. Wrap `experiments/runner.py` with CLI commands. Implement `wasp monitor` and `wasp demo` using `rich.live` or `textual`. Build packaging via `pyproject.toml`.
9. **Files to modify**: `experiments/runner.py` (to ensure it returns clean data objects for the CLI), `simulator/network/topology.py` (to ensure event callbacks can be routed to the CLI TUI).
10. **Files to create**: `cli.py`, `pyproject.toml`, `Dockerfile`, `docker-compose.yml`, `docs/CLI_INSPECTION_REPORT.md`.
11. **Files that should NOT be touched**: `frontend/*`, `wasp/*` (unless strictly necessary for CLI).
12. **Risks**: Modifying the callback system in `topology.py` might break the WebSocket streaming for the React app if not done carefully.
13. **Test plan**: Run existing `math_validation.py`. Add new tests for CLI commands. Test Docker build.
