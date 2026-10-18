# WASP Interactive Network Security Lab

This implementation is a local multi-process network simulator. It does not represent physical NDN routers unless explicitly integrated with a real NDN runtime.

## Architecture

The system uses a **Controller as State Master** architecture:
- **Controller Daemon:** Runs the deterministic `NetworkTopology` event loop in scaled real-time. It exposes a lightweight FastAPI JSON state-sync server on `127.0.0.1:8001`.
- **Node Terminals (TUIs):** Lightweight Rich-based command-line processes (`wasp node`, `wasp attacker`) that poll the Controller for their respective node's telemetry, PES scores, and active WASP decisions.

This preserves the rigorous scientific determinism of the simulator (same seed = same exact mathematical events) while allowing interactive "hacker-style" visual exploration across multiple windows.

## New Commands

1. **Start the Controller**: 
   `wasp network start`
   *(Spins up the daemon in the background)*

2. **Start a Scenario**: 
   `wasp scenario --mode baseline` (Watchlist Attack without protection)
   `wasp scenario --mode wasp` (Full WASP Shield Protocol)

3. **Open Node Terminals (Run these in separate PowerShell windows)**:
   `wasp node --id R0`
   `wasp node --id R1`
   `wasp attacker`

4. **Stop the Controller**:
   `wasp network stop`

## The Causal Chain

When you launch `wasp scenario --mode wasp`, you will see:
1. TRAFFIC enters R0 and R1.
2. ATTACKER begins stealing observations.
3. R1's **PES** (Privacy Exposure Score) rises.
4. Threat Level escalates from **LOW** to **HIGH**.
5. **Adaptive Shielding** triggers, randomly padding requests based on the Sigmoid function.
6. For critical packets, **Crypto** activates and the packet is scrambled in the event log!
