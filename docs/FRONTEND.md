# Frontend Documentation

## Architecture
- **Framework:** React 18, TypeScript, Vite
- **Routing:** React Router v6
- **Styling:** TailwindCSS
- **Icons:** Lucide-react
- **Charting:** Recharts

## Pages Implementation (16 Total)
1. **Command Center:** (`Overview.tsx`) - High-level metrics via `/api/metrics/current`.
2. **Live Network:** (`Topology.tsx`) - Network graph via `/api/network/topology`.
3. **Attack Center:** (`AttackCenter.tsx`) - Watchlist metrics via `/api/attack/status`.
4. **Privacy Analysis:** (`PrivacyAnalysis.tsx`) - Risk rendering.
5. **WASP Controller:** (`WaspController.tsx`) - Renders the Sigmoid curve utilizing `kappa` and `tau` from `/api/wasp/status`.
6. **Crypto Protection:** (`CryptoProtection.tsx`) - Shows dynamic scaling delays from `/api/crypto/status`.
7. **Secure Forwarding:** (`SecureForwarding.tsx`) - Shows path dispersion weights via `/api/forwarding/status`.
8. **Scenario Lab:** (`ScenarioLab.tsx`) - Displays experiment controls.
9. **Experiment Config:** (`ExperimentConfig.tsx`) - Payload builder for `/api/simulation/start`.
10. **Experiment Monitor:** (`ExperimentMonitor.tsx`) - Live polling of `/api/simulation/status`.
11. **Results:** (`Results.tsx`) - Lists persistent `.json` logs via `/api/experiments/results`.
12. **Scenario Comparison:** (`ScenarioComparison.tsx`) - Loads tabular metrics via `/api/results/compare`.
13. **Interest Inspector:** (`InterestInspector.tsx`) - Fetches specific lifecycle traces via `/api/network/interest/{id}`.
14. **Event Log:** (`EventLog.tsx`) - Streams WS messages.
15. **System Status:** (`SystemStatus.tsx`) - Queries `/api/health`.
16. **Presentation Mode:** (`PresentationMode.tsx`) - State-driven guided narrative.

## State Management
- Components utilize functional `useState` and `useEffect` with strict `fetch` boundaries.
- Graceful degradation ensures empty datasets show explicit error/loading banners rather than crashing or faking data.
