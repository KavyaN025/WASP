# Implementation Plan: WASP Multi-Terminal Network Security Lab

## 1. Repository Audit Summary
- **WASP Core**: Resides in `wasp/` (controller, crypto, forwarding, monitor, privacy, shielding). It is purely mathematical/logical.
- **Simulator**: Resides in `simulator/` (network, packets, router, consumer, producer, attacker). It is a centralized, discrete-event simulation (`NetworkTopology`).
- **Current Execution**: Driven by `experiments/runner.py` which executes the simulator as fast as possible in a single asyncio thread.
- **Conflict**: The prompt demands multi-process interactive terminals for nodes, but explicitly forbids destroying the deterministic single-threaded scientific simulator.
- **Resolution**: We will implement the "Controller as State Master" architecture. The `wasp network start` command will launch a central `Controller` process that hosts the `NetworkTopology` simulator, running in *scaled real-time* (e.g., 1 sim second = 1 real second). The Controller will expose a local TCP/Socket API (e.g., JSON over TCP).
- Individual node commands (`wasp node start --id R1`) will launch lightweight Rich-based TUI processes that connect to the Controller, subscribe to their specific node's state, render the interactive dashboard, and send user commands (e.g., "Change Attack Intensity") back to the Controller.

## 2. Shared State Architecture
```
[Controller Process (Port 8001)]
   |-- Runs NetworkTopology (scaled real-time)
   |-- Exposes State Sync Server
   |
   |--- TCP --- [R1 Terminal Process] (Displays R1 state)
   |--- TCP --- [Attacker Terminal Process] (Displays + Sends Attack Commands)
   |--- TCP --- [Consumer Terminal Process] (Displays traffic)
```

## 3. Step-by-Step Execution Plan
1. **Refactor Simulator for Real-Time Execution**: Modify `ExperimentRunner` or create `InteractiveRunner` that yields control to an `asyncio` sleep proportional to simulated time, allowing real-time viewing.
2. **State Sync Server**: Implement `StateServer` in the Controller to broadcast `NodeState` JSON objects.
3. **Node TUIs**: Implement `wasp node start`, `wasp attacker`, `wasp consumer` commands using `rich.live` to consume the state stream.
4. **Interactive Controls**: Allow the TUI processes to send commands back to the Controller (e.g., `SET_KAPPA 12`, `SET_INTENSITY HIGH`).
5. **Two Synchronized Scenarios**: Implement `wasp scenario start --mode baseline` vs `wasp scenario start --mode wasp` to compare identical seeds.
6. **Documentation**: Write `docs/multi-terminal.md`.

*End of Plan.*
