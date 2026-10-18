# WASP Frontend Data Provenance Report

This document maps all frontend metrics to their underlying simulation or WASP engine components, ensuring end-to-end trace verification with zero mock data.

## 1. Network & Cache Metrics

### Packet Delivery Ratio (PDR) & Interest Satisfaction Rate (ISR)
- **Source Module**: `simulator.network.topology` and `experiments.runner`
- **Calculation**: `satisfied_interests / total_interests` computed natively in the simulation loop.
- **API Source**: REST `/api/results/compare`
- **Frontend Component**: `ScenarioLab.tsx` (Delivery & Cache Performance Chart)

### Cache Hit Ratio (CHR)
- **Source Module**: `simulator.cache.cs` and `simulator.router`
- **Calculation**: `total_hits / (total_hits + total_misses)` iterating over actual router Content Store states.
- **API Source**: REST `/api/results/compare` and `/api/metrics/current`
- **Frontend Component**: `ScenarioLab.tsx`

### Latency & Hops
- **Source Module**: `simulator.network.topology`
- **Calculation**: Time elapsed for Interest-Data cycle in the scheduler. Incremented per edge traversal.
- **API Source**: REST `/api/results/compare`
- **Frontend Component**: `ScenarioLab.tsx`

## 2. Privacy & Attack Metrics

### Privacy Leakage & Inference Confidence
- **Source Module**: `simulator.attacker.watchlist.WatchlistAttacker`
- **Calculation**: Confidence tracks observed request frequency matching a pre-defined array of watchlist strings. Leakage is the normalized aggregate of confidence values.
- **API Source**: REST `/api/attack/status` (live) and `/api/results/compare` (experiment)
- **Frontend Component**: `AttackCenter.tsx` and `ScenarioLab.tsx`

## 3. WASP Engine Core Decisions

### Feature Vector ($F, T, C, H$)
- **Source Module**: `wasp.monitor.sliding_window`
- **Calculation**: Empirically derived over an actual array of historical `Interest` packets.
- **WebSocket Source**: `WASP_DECISION` payload (`msg.data.decision.features.F` etc.)
- **Frontend Component**: `InterestInspector.tsx`

### Privacy Exposure Score (PES) & Risk
- **Source Module**: `wasp.privacy.pes`
- **Calculation**: Feature vectors normalized against bounds and summed using $\alpha, \beta, \gamma, \delta$.
- **WebSocket Source**: `WASP_DECISION` payload
- **Frontend Component**: `InterestInspector.tsx` and `PrivacyAnalysis.tsx`

### Adaptive Shielding (Sigmoid)
- **Source Module**: `wasp.shielding.controller`
- **Calculation**: $S = 1 / (1 + \exp(-\kappa(P - \tau)))$ (where $\kappa = 10, \tau = 0.5$)
- **Frontend Verification**: `PrivacyAnalysis.tsx` draws the exact geometric curve using $\kappa = 10, \tau = 0.5$ and plots the empirical `WASP_DECISION` operating points on top of it.
- **Frontend Component**: `PrivacyAnalysis.tsx`, `InterestInspector.tsx`

### Cryptography & Forwarding (Overhead, Diversity, Probability)
- **Source Module**: `wasp.crypto.dynamic_crypto` and `wasp.forwarding.secure_route`
- **Calculation**: Linear mappings derived purely from the Shielding Intensity metric $S$.
- **WebSocket Source**: `WASP_DECISION` payload (`encryption_time`, `entropy`, `forwarding_probability`, etc.)
- **Frontend Component**: `InterestInspector.tsx`

## Audit Summary
- **Verified real-data paths**: All calculations are 1-to-1 verified between Python and React UI.
- **Fabricated/Mock data found**: **None**. Complete codebase audit confirmed no `Math.random()` or hardcoded metric structures outside of deterministic JSON serialization.
- **Experiments Executed**: Verified `NORMAL_ICN`, `WATCHLIST_ATTACK`, and `FULL_WASP` execution flows outputting real API results.
- **Discrepancies Fixed**: The Sigmoid visualization in `PrivacyAnalysis.tsx` was enhanced to plot the exact theoretical curve and map the actual simulated points upon it, rather than just showing a general area chart.
- **Limitations**: The frontend must gracefully degrade with "Data unavailable" when the backend is offline. Real-time topology uses fixed coordinate projection rather than D3 force layout for performance, but node relationships correctly track the physical Python `NetworkTopology` graph matrix.
