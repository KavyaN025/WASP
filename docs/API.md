# WASP API Documentation

The backend exposes a FastAPI REST service to drive the React frontend.

## Endpoints

### Health & Status
- `GET /api/health` -> Returns `{"status": "ok", "version": "1.0"}`

### Simulation & Network
- `POST /api/simulation/start` -> Triggers `ExperimentRunner` execution. Payload: `{"scenario": "...", "seed": 42}`.
- `POST /api/simulation/stop` -> Cancels the current `asyncio` network task.
- `GET /api/simulation/status` -> Returns running status and current scenario.
- `GET /api/network/topology` -> Returns nodes and edges from the NetworkX graph.
- `GET /api/metrics/current` -> Returns global PDR, CHR, and Privacy Leakage.

### WASP Metrics
- `GET /api/attack/status` -> Returns Watchlist items and inference probabilities.
- `GET /api/wasp/status` -> Returns Adaptive Controller parameters (κ, τ, α, β, γ, δ).
- `GET /api/crypto/status` -> Returns Dynamic Crypto bounds ($K_{min}, K_{max}, t_b$).
- `GET /api/forwarding/status` -> Returns Secure Routing thresholds ($\Delta, \rho, w_1, w_2, w_3$).
- `GET /api/network/interest/{id}` -> Returns the complete WASP decision history for a specific Interest packet.

### Experiments
- `GET /api/experiments/scenarios` -> Returns list of configurable ablations.
- `GET /api/experiments/results` -> Returns list of persisted JSON files on disk.
- `GET /api/results/compare` -> Returns the most recently completed experiment payload for comparative graphing.

### WebSocket
- `WS /ws/live` -> Broadcasts `TOPOLOGY`, `WASP_DECISION`, and other real-time network states.
