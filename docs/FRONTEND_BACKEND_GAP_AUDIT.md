# Frontend/Backend Gap Audit

| Frontend Feature | Required Data | Existing Backend Source | Missing Capability | Required Endpoint/Event | Implementation (files) | Frontend Integration (files) | Test(s) | Status |
|---|---|---|---|---|---|---|---|---|
| Command Center | Simulation state, metrics, attacker status | `main.py` | Need detailed active Interests/Data count | `/api/metrics/current` (update) | `backend/main.py` | `Overview.tsx` | - | Complete |
| Live Network | Graph topology, node state | - | Topology structure, route data | `/api/network/topology` | `backend/main.py`, `topology.py` | `Topology.tsx` | - | Complete |
| Attack Center | Watchlist, inference events, leakage | `main.py` | Attack timeline, inference stats | `/api/attack/status` (update) | `backend/main.py`, `watchlist.py` | `AttackCenter.tsx` | - | Complete |
| Privacy Analysis | F/T/C/H, PES, risk history | - | Historic risk trends | `/api/privacy/status` | `backend/main.py` | `PrivacyAnalysis.tsx` | - | Complete |
| WASP Shield Controller | Sigmoid parameters (tau, kappa), operating points | - | Controller parameters | `/api/wasp/status` | `backend/main.py`, `controller.py` | `WaspController.tsx` (new) | - | Complete |
| Cryptographic Protection | Encryption time, overhead, protected traffic % | - | Crypto metrics | `/api/crypto/status` | `backend/main.py` | `CryptoProtection.tsx` (new) | - | Complete |
| Secure Forwarding | Candidate routes, delay, diversity | - | Route decision metrics | `/api/forwarding/status` | `backend/main.py` | `SecureForwarding.tsx` (new) | - | Complete |
| Scenario Lab | Scenarios list | `runner.py` | Scenario metadata | `/api/experiments/scenarios` | `backend/main.py` | `ScenarioLab.tsx` | - | Complete |
| Experiment Config | Config params, start run | - | Trigger experiment | `/api/experiments/run` (POST) | `backend/main.py` | `ExperimentConfig.tsx` (new) | - | Complete |
| Experiment Monitor | Run progress, status | - | Active experiment progress | `/api/experiments/status` | `backend/main.py` | `ExperimentMonitor.tsx` (new) | - | Complete |
| Results | List of results | `results/` dir | Fetch past results | `/api/experiments/results` | `backend/main.py` | `Results.tsx` (new) | - | Complete |
| Scenario Comparison | Side-by-side metrics | `/api/results/compare` | Fine | `/api/results/compare` | `backend/main.py` | `ScenarioComparison.tsx` (new) | - | Complete |
| Interest Inspector | Full lifecycle per packet | WebSocket `WASP_DECISION` | Need lookup by ID | `/api/network/interest/{id}` | `backend/main.py` | `InterestInspector.tsx` | - | Complete |
| Event Log | Raw event stream | WebSocket `ws/live` | Fine | `ws/live` | `backend/main.py` | `EventLog.tsx` | - | Complete |
| System Status | Health of components | `/api/health` | WS status, memory | `/api/health` (update) | `backend/main.py` | `SystemStatus.tsx` (new) | - | Complete |
| Presentation Mode | Driven narrative | - | Guided steps API/state | Frontend State | `PresentationMode.tsx` (new)| `PresentationMode.tsx` | - | Complete |

