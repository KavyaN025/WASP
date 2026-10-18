# WASP Live Demonstration Guide

This guide describes how to seamlessly present the framework to evaluators.

## Preparation
1. Execute `.\start_all.ps1`.
2. Open `http://localhost:5173`.

## Execution
Navigate to the **Presentation Mode** page.
This acts as a guided narrative stepper.

### Step 1: Baseline ICN
- Click **Execute Phase** to run the `NORMAL_ICN` simulation.
- **Narrative:** "We establish baseline performance showing raw ICN routing efficiency."
- Navigate to the **Command Center** to show ~15ms latency and perfect cache usage.

### Step 2: Passive Attack
- Return to Presentation Mode. Click **Execute Phase** for `WATCHLIST_ATTACK`.
- Navigate to the **Attack Center**.
- **Narrative:** "The attacker passively listens without dropping packets, meaning PDR remains unaffected, but Privacy Leakage surges to ~20%."

### Step 3: Full WASP Shielding
- Return to Presentation Mode. Click **Execute Phase** for `FULL_WASP`.
- Navigate to **Interest Inspector**.
- Click an Interest trace.
- **Narrative:** "WASP intercepts the packet, extracts Features (F,T,C,H), calculates PES, and scales it across the Sigmoid threshold. Because this request hit the threshold, WASP triggered SHIELDED mode, injecting cryptographic delay and dispersing the forwarding path."

### Step 4: Quantitative Results
- Navigate to **Scenario Comparison**.
- **Narrative:** "While Static Cryptography severely penalized macro-latency across the entire network, WASP's adaptive architecture successfully mitigated the attack while preserving near-baseline latency by exploiting ICN in-network caching!"
