# WASP (Watchlist Attack Shield Protocol)

**WASP** is a privacy-preserving routing and shielding protocol designed for Information-Centric Networking (ICN) and Named Data Networking (NDN). It dynamically protects the network from passive adversaries attempting to infer sensitive user content via timing, frequency, and cache-hit observation (Watchlist Attacks).

This repository contains the complete research implementation, including the deterministic network simulator, the mathematical WASP core, a web-based visualization dashboard, and an interactive multi-process terminal security lab.

---

## 🧬 Core Architecture

The architecture strictly adheres to the principle of **"One WASP Core, Multiple Interfaces."**

1. **WASP Engine (`wasp/`)**: The mathematical heart of the project. It calculates Traffic Features ($F, C, T, H$), the Privacy Exposure Score (PES), Sigmoid-based Adaptive Shielding, and Cryptographic parameters.
2. **Deterministic Simulator (`simulator/`)**: A discrete-event network simulator using `NetworkX`. It models Consumers, Producers, Routers, and Watchlist Attackers with perfect scientific reproducibility based on random seeds.
3. **Experiment Runner (`experiments/`)**: Automates ablations (e.g., *Baseline ICN*, *Static Crypto*, *Full WASP*) to generate comparison metrics (PDR, Latency, Privacy Leakage, Crypto Overhead).

---

## 🖥️ Interfaces & How to Run

### 1. The Interactive Network Security Lab (Multi-Terminal TUI)
A highly interactive, "hacker-style" local network lab where each terminal represents a different network node.

**Launch the Lab:**
1. Open PowerShell and activate your environment: `.\venv\Scripts\Activate.ps1`
2. Start the Controller daemon: `wasp network start`
3. Open multiple new terminal windows and attach them to nodes:
   - `wasp node --id R0` (Watch Router 0)
   - `wasp node --id R1` (Watch Router 1)
   - `wasp attacker` (Watch the attacker's live inference)
4. Trigger the live scenario: `wasp scenario --mode wasp`

### 2. The CLI Toolkit
The `wasp` command acts as your primary research toolkit for rapid analysis and graph generation.
- `wasp doctor`: Check system health and dependencies.
- `wasp experiment run --scenario FULL_WASP --seed 42`: Run a fast headless simulation.
- `wasp compare`: Compare the latest ablations in a terminal table.
- `wasp graph all`: Generate publication-ready Matplotlib charts in `/results`.
- `wasp demo`: Run a guided, step-by-step terminal demonstration.

### 3. The Web Dashboard (React + FastAPI)
For comprehensive, real-time visual analysis, you can use the graphical UI.
- Run `.\start_all.ps1` to launch both servers.
- Open `http://localhost:5173`.
- Features a Live Network Topology map, a dedicated Attack Center, and an Interest Inspector.

---

## 🛡️ Scientific Validation

The project enforces a **Zero Mock Data** policy.
- Every metric displayed in the UI or CLI is mathematically traced directly to the simulator.
- Privacy Leakage, Detection Accuracy, Cache Hit Ratio (CHR), and Latency are true reflections of the underlying simulation.
- Running experiments with the same `--seed` guarantees mathematically identical outputs, ensuring defensible research results.

---

## 🚀 What's Next (Upcoming TUI Upgrades)

While the multi-terminal network lab provides a great proof-of-concept for localized state-monitoring, the current `rich.live` implementation is a stepping stone. 

**Planned Upgrades for the Terminal Lab:**
- **Textual Integration:** Migrating from `Rich` to `Textual` to create a true, mouse-interactive TUI (Terminal User Interface) where you can click on packets to inspect them inside the terminal.
- **Unified Command Center:** Instead of opening 5 separate PowerShell windows, launching a single, massive multiplexed dashboard that allows you to tab between routers, consumers, and the attacker instantly.
- **Dynamic Topology View:** A live ASCII node map where the links physically flash red or green as packets traverse them.
- **Packet Injection:** A command-line input box inside the Consumer TUI to manually type and fire specific Interests into the network and watch them trigger the WASP shield in real-time.
