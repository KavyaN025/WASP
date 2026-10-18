# The Complete Deep-Dive Guide to WASP & The GAN-AI Extension

This document provides a comprehensive, granular, and technically exhaustive explanation of the entire WASP project—from the underlying networking foundations to every mathematical formula, software module, experimental result, and the future GAN extension.

---

# CHAPTER 1: THE NETWORKING PARADIGM & THE CORE PROBLEM

## 1.1 From Host-Centric IP to Information-Centric Networking (ICN / NDN)
In the traditional Internet Protocol (IP) architecture, communication is **host-centric**:
- A client wants a file, so it must locate a physical server (e.g., `192.168.1.50`), establish a point-to-point connection (TCP/IP handshake), and fetch data through that specific tunnel.
- If 1,000 users in the same university building watch the same video lecture, 1,000 separate data streams traverse the university’s backhaul link from YouTube's remote server. This is bandwidth-inefficient and creates severe network bottlenecks.

**Named Data Networking (NDN / ICN)** completely redesigns the Internet layer around **content names** rather than machine addresses:
- Content has a hierarchical, human-readable name: `/university/cs101/lecture1.mp4` or `/health/patient10/ecg`.
- Communication is driven strictly by the **Consumer** using two packet types:
  1. **Interest Packet:** Sent by a consumer requesting data by name.
  2. **Data Packet:** Returned by a producer or intermediate router, containing the requested content payload and a digital signature from the original producer.

## 1.2 The Engine of ICN: In-Network Caching
Every intermediate NDN router contains three core data structures:
1. **Content Store (CS):** A high-speed local memory cache that stores Data packets traversing the router.
2. **Pending Interest Table (PIT):** A state table that tracks in-flight Interests that have been forwarded upstream but not yet satisfied by incoming Data packets. It records the incoming interface (face) so the Data can be routed back downstream to the consumer.
3. **Forwarding Information Base (FIB):** A routing lookup table (similar to an IP routing table) that maps content name prefixes to outgoing network interfaces toward legitimate producers.

### What happens when an Interest arrives at a router?
```
Interest arrives: /health/patient10/ecg
          │
          ▼
   [ Content Store ] ───(Cache Hit: Data is present)───► [ Serve Data directly to user (Hop 0, ~5ms) ]
          │ (Cache Miss)
          ▼
   [ Pending Interest Table ] ───(Interest already pending from another user)───► [ Aggregate: add face, don't re-forward ]
          │ (Not pending)
          ▼
   [ Forwarding Information Base ] ───► [ Forward Interest upstream toward Producer (~30ms) ]
```

## 1.3 The Fundamental Privacy Dilemma
To enable intermediate routers to match Interests against their Content Store (CS), **content names must be readable in plaintext**.
- If we use traditional end-to-end encryption (like TLS), the content name is scrambled inside an opaque tunnel. Routers cannot inspect the name, so the Content Store cannot match it. In-network caching drops to 0%, destroying the primary performance benefit of ICN.
- However, if content names are left in plaintext, any router operator or eavesdropper along the path can see exactly what files users are requesting.

---

# CHAPTER 2: THE THREAT MODEL — PASSIVE WATCHLIST ATTACK

## 2.1 The Adversary Profile
- **Placement:** The adversary controls or monitors an intermediate router along the forwarding path.
- **Passive Nature:** The attacker does not drop packets, forge checksums, or inject spoofed data. They simply record traffic telemetry.
- **The Target (The Watchlist $L$):** The adversary possesses a predefined list of sensitive content names:
  $$L = \{c_1, c_2, \dots, c_m\}$$
  Examples: `/hospital/oncology/chemo_schedule`, `/political/dissident_manifesto`, `/finance/bankruptcy_filing`.

## 2.2 How the Attacker Infers User Privacy (Bayesian Confidence)
The attacker does not need to compromise the consumer's home laptop. By observing traffic patterns at the router, they measure three side-channels:
1. **Request Frequency ($F_c$):** How often an Interest for $c \in L$ appears over time.
2. **Inter-Arrival Timing ($T_c$):** The precise time intervals between requests. Rapid, periodic requests indicate automated consumption or video streaming.
3. **Cache Hit Observations ($C_c$):** A cache hit returns Data within 5 ms, whereas a cache miss takes 30 ms. By timing round-trip delays, an attacker can determine if someone else nearby recently requested the same content.

Using a Bayesian framework, the attacker starts with a low prior probability ($P_L(c) = 0.10$). Every time an Interest matching $c$ is observed, the posterior confidence updates:
$$P_L(c \mid \text{Observation}) = \frac{P(\text{Observation} \mid c) \cdot P(c)}{P(\text{Observation})}$$
Without defense, the attacker's inference confidence rapidly climbs from $0.10$ to **$0.95+$ (near certainty)**.

The attacker's mathematical optimization objective is:
$$\max \sum_{c \in L} P_L(c)$$

---

# CHAPTER 3: THE WASP PROTOCOL (MATHEMATICAL ARCHITECTURE)

The **Watchlist Attack Shield Protocol (WASP)** (Lal & Malani, IEEE) solves this dilemma by turning NDN routers into an **adaptive immune system**. Instead of encrypting everything, it computes a mathematical risk score for every request and dynamically scales defense only when a threat is detected.

WASP executes in **4 sequential stages** at every router:

```
[Interest Arrives] ──► [Stage 1: Traffic Monitoring] ──► [Stage 2: Privacy Exposure Estimation (PES)]
                                                                           │
[Forward / Shield] ◄── [Stage 4: Dynamic Protection] ◄── [Stage 3: Adaptive Sigmoid Controller]
```

---

## 3.1 Stage 1: Traffic Monitoring (TM)
The router maintains a sliding observation window $W(t)$ containing the last $W$ requests (Eq. 1). From this window, the router extracts four distinct behavioral features for content $c$:

### 1. Request Frequency ($F_c$) (Eq. 2–3):
$$F_c(t) = \sum_{I_i \in W(t)} \delta(I_i, c)$$
Where $\delta(I_i, c) = 1$ if Interest $I_i$ matches content name $c$, else $0$.
*Meaning: Higher frequency implies the user or local population is heavily interested in this specific item.*

### 2. Average Request Interval ($T_c$) (Eq. 4):
$$T_c = \frac{1}{N - 1} \sum_{i=2}^{N} (t_i - t_{i-1})$$
Where $t_i$ are the observation timestamps of consecutive requests for $c$.
*Meaning: Shorter intervals indicate rapid burst requests, which makes traffic correlation easier for the attacker.*

### 3. Cache Observation Ratio ($C_c$) (Eq. 5):
$$C_c = \frac{\text{Hits}_c}{\text{Total Requests}_c}$$
*Meaning: Measures how frequently this content is satisfied directly from the local cache versus forwarded upstream.*

### 4. Average Hop Count ($H_c$) (Eq. 6):
$$H_c = \frac{1}{M} \sum_{i=1}^{M} h_i$$
*Meaning: Measures topological distance traveled by the packet across the network.*

---

## 3.2 Stage 2: Privacy Exposure Estimation (PE)
Raw feature values vary across topologies, so WASP first applies Min-Max Normalization:
$$x'_i = \frac{x_i - x_{\min}}{x_{\max} - x_{\min}} \in [0, 1] \quad (\text{Eq. 17})$$

### The Privacy Exposure Score (PES) (Eq. 18):
$$\text{PES}_i = \alpha F'_c + \beta C'_c + \gamma (1 - T'_c) + \delta H'_c$$
Subject to the weight constraint:
$$\alpha + \beta + \gamma + \delta = 1 \quad (\text{Eq. 19})$$

> **Crucial Engineering Detail ($1 - T'_c$):**  
> In the paper's formulation, shorter inter-arrival times ($T_c$) represent higher request rates and therefore higher privacy risk. Therefore, our code mathematically inverts normalized timing: $(1 - T'_c)$.

### Normalized Privacy Risk ($P_i$) (Eq. 20):
$$P_i = \frac{\text{PES}_i - \text{PES}_{\min}}{\text{PES}_{\max} - \text{PES}_{\min}} \in [0, 1]$$
Risk is mapped into three paper-defined levels:
- **Low:** $P_i < \tau_1$ (benign traffic)
- **Medium:** $\tau_1 \le P_i < \tau_2$ (emerging risk)
- **High:** $P_i \ge \tau_2$ (active watchlist threat)

---

## 3.3 Stage 3: Adaptive Shielding Controller (ASC)
Why not use a simple `if (risk > threshold)` trigger?
Because binary thresholding in networking causes **hysteresis and route flapping**: traffic constantly flips between encrypted and unencrypted states, causing severe latency jitter.

WASP uses a continuous **Sigmoid function** to compute **Shielding Intensity ($S_i \in [0, 1]$)**:
$$S_i = \frac{1}{1 + e^{-\kappa (P_i - \tau)}} \quad (\text{Eq. 22})$$
Where:
- $\tau = 0.50$ is the median risk threshold.
- $\kappa = 8.0$ (or $10.0$) is the adaptation rate (slope steepness).

### Operational Modes ($M_i$) (Eq. 23):
- **Normal Mode:** $S_i < \eta_1$ (e.g., $S_i < 0.40$). Forwarded in plaintext, 0 ms delay.
- **Protected Mode:** $\eta_1 \le S_i < \eta_2$. Moderate protection activated.
- **Shielded Mode:** $S_i \ge \eta_2$ (e.g., $S_i \ge 0.70$). Maximum protection activated.

Binary decision: $D_i = 1$ if $M_i \in \{\text{Protected, Shielded}\}$ else $0$ (Eq. 24).

---

## 3.4 Stage 4: Dynamic Cryptographic & Forwarding Protection (DCP & SF)
When $D_i = 1$, three defensive mechanisms scale linearly with $S_i$:

### 1. Name Obfuscation (A-SHLD-1):
The plaintext name `/c/1` is hashed into an opaque token:
$$\text{Name}_{\text{token}} = \text{SHA256}(c)[:8] \implies \text{OPAQUE\_a8b9f71c}$$
When the packet passes through the compromised router, the attacker checks their watchlist for `/c/1`. The token does not match, generating an attacker watchlist miss!

### 2. Dynamic Key Scaling & Timing Jitter (A-SHLD-2) (Eq. 27 & 36):
- **Key Size:** $K_i = K_{\min} + S_i (K_{\max} - K_{\min})$ bits (e.g., scaling from 128 to 2048 bits).
- **Adaptive Jitter Delay:** $\Delta_i = \Delta_{\min} + (\Delta_{\max} - \Delta_{\min}) S_i$ ms.
This artificial delay breaks inter-arrival timing correlation, preventing the attacker from estimating packet burstiness.

### 3. Routing Diversity (A-SHLD-3) (Eq. 37):
$$R_i = 1 + \rho \cdot S_i$$
Instead of always using the single shortest FIB path (which easily funnels packets through the compromised router), $R_i$ expands the multipath candidate set, probabilistically dispersing consecutive requests across alternative routers.

### Attacker Confidence Suppression (Eq. 48):
Under active shielding, the attacker's Bayesian posterior confidence decays as:
$$P_{\text{profile}} = P_L(c) \cdot (1 - S_i)$$
When $S_i \to 1.0$, $P_{\text{profile}} \to 0.0$.

---

# CHAPTER 4: CODE ARCHITECTURE & SYSTEM IMPLEMENTATION

The project was built in Python 3.13 as a pure-physics, real-time discrete-event testbed.

```
wasp-lab/
├── wasp_lab/
│   ├── engine/
│   │   ├── equations.py     # Pure mathematical implementation of Eq 1-48
│   │   ├── attacker.py      # Bayesian Beta-distribution watchlist attacker
│   │   ├── topology.py      # Network graph builder (Subscribers, Routers, Producers)
│   │   └── runner.py        # Lockstep dual-world simulation runner
│   ├── server/
│   │   └── app.py           # FastAPI backend + 10 Hz WebSocket telemetry stream
│   ├── web/
│   │   ├── index.html       # D3.js topology visualization & Chart.js dashboards
│   │   ├── styles.css       # Clean academic minimalist styling
│   │   └── lib/             # Locally vendored D3.v7 & Chart.js (offline bypass)
│   └── terminal/
│       └── repl.py          # Interactive command-line REPL client
```

## 4.1 The Lockstep Dual-World Engine (`runner.py`)
To prove that WASP's performance improvements are genuine (and not artifacts of lucky random numbers), the engine executes **two parallel worlds simultaneously**:
1. **World 1: WASP-OFF (Unprotected Baseline)**
2. **World 2: WASP-ON (Adaptive Shielding Active)**

### Decoupled RNG Streams:
- `rng_traffic` (Seed 42): Generates Zipf-distributed Interest arrival schedules identically for both worlds.
- `rng_wasp` (Seed 1337): Controls stochastic multipath routing and cryptographic jitter in the WASP-ON world.
This guarantees that **both worlds experience the exact same packet sequence at the exact same millisecond**, providing fair, 1:1 comparative evaluation.

## 4.2 Interactive Web & Terminal Interfaces
- **Web Dashboard (`http://127.0.0.1:8001`):**
  - Uses D3.js to render live nodes and animate Interest packets (blue rectangles) and Data packets (black circles) in real time.
  - Six real-time Chart.js telemetry charts display Attacker Confidence, End-to-End Latency, PDR/CHR, Cryptographic Overheads, Risk Histograms, and Routing Diversity against paper reference baselines.
- **Terminal Client (`wasp terminal`):**
  - An interactive Python `cmd.Cmd` shell. Operators can type `status`, `start`, `stop`, `wasp on`, `wasp off`, inspect specific routers (`router r1` $\to$ `info`), and manually inject requests (`send /c/5 s0`).

---

# CHAPTER 5: EXPERIMENTAL VALIDATION & ABLATION FINDINGS

## 5.1 Benchmark Comparison Table

| Metric | Baseline ICN (No Attack) | Watchlist Attack (WASP OFF) | WASP-ON (Our Lab) | Benchmark Paper Target |
|---|---|---|---|---|
| **Attacker Inference Confidence** | 0.10 (Prior) | **0.85 – 0.98** (High Leakage) | **0.18 – 0.25** (Suppressed) | $\approx 0.20$ |
| **Packet Delivery Ratio (PDR)** | 98.0% | 65.0% (Attack degradation) | **92.4%** | $\approx 92.0\%$ |
| **Cache Hit Ratio (CHR)** | 88.5% | 63.0% | **84.2%** | $\approx 86.0\%$ |
| **Average End-to-End Latency** | 24.5 ms | 26.0 ms | **31.8 ms** (Minimal penalty) | $\approx 32.0$ ms |
| **Average Hop Count** | 1.35 | 1.40 | **1.62** (Multipath dispersion) | $\approx 1.60$ |

## 5.2 Key Scientific Insights
1. **Inference Suppression:** WASP suppresses attacker confidence by **over 75%**, reducing inference from near-certainty ($0.95$) to baseline noise ($0.18$).
2. **Cache-Hit Neutralization:** In-network caching acts as a buffer. Because popular requests are satisfied at Hop 0 or 1 from local router caches, they bypass upstream forwarding entirely—neutralizing cryptographic routing delays!
3. **Ablation Results:**
   - **Disabling Name Obfuscation:** Confidence rebounds to 0.78 (Obfuscation is the primary shield).
   - **Static Encryption ($S=1.0$ Always On):** Latency spikes to 48 ms and CHR drops to 52%, proving that **Adaptive Shielding** is mathematically necessary to preserve network throughput.

---

# CHAPTER 6: THE CRITICAL DRAWBACKS OF WASP (WHY WE NEED THE EXTENSION)

During our 2nd Evaluation, we conducted a rigorous threat analysis of the WASP protocol. While it succeeds at protecting privacy, we identified **four critical architectural vulnerabilities**:

### 1. Strictly One-Sided Threat Model (Privacy $\ne$ Authenticity):
WASP was designed *exclusively* to protect Interest packet privacy against eavesdropping. It has **no mechanism to verify whether the returned Data packet contains authentic or counterfeit data**.

### 2. Blind In-Network Caching:
NDN routers cache Data packets based purely on **name matching** strings. Routers have **zero semantic or visual understanding** of content. If a rogue producer returns a fake image under a valid name, the router caches it blindly.

### 3. WASP Inadvertently Protects Poisoned Content:
Because WASP shields Interest packets with encrypted tunnels and opaque tokens, a poisoned Data packet returned by an adversary travels through the network under that very same encrypted shroud, bypassing inspection and infecting downstream router caches!

### 4. Cryptographic Key Compromise:
Traditional NDN relies on digital signatures. If an adversary compromises a producer's private key, or if lightweight cryptography is used, static cryptographic verification fails completely.

---

# CHAPTER 7: THE FUTURE EXTENSION — GAN CONTENT POISONING & AI DEFENSE

To resolve these drawbacks for Review-III, we are extending the project into a **Two-Tier Security Architecture**:
- **Tier-1 (Completed):** WASP Privacy Shield (protects Interest Privacy).
- **Tier-2 (Extension):** AI-Based Content Authenticity & Mitigation System (protects Content Integrity).

```
                      [User Requests: /animals/horse/image1]
                                         │
                                         ▼
                      [Tier-1: WASP Privacy Shield (PES, Sigmoid)]
                                         │
                                         ▼
                             [NDN Router Network & Caches]
                             /                           \
                    (Genuine Producer)             (Malicious Producer)
                            │                               │
                     [Real Horse Image]             [GAN Synthetic Image]
                            │                               │
                            └───────────────┬───────────────┘
                                            ▼
                                 [Consumer Receives Data]
                                            │
                                            ▼
                      [Tier-2: AI-Based Detection & Mitigation System]
                      1. Cryptographic Hash & Signature Verification
                      2. Deep CNN Classifier (Genuine vs Synthetic)
                      3. Provenance & Source Audit Trail
                                            │
                                      Decision Policy
                                     /              \
                              (Genuine)            (Counterfeit Detected)
                                 │                          │
                           [Accept Data]           [Quarantine & Evict from CS]
                                                   [Isolate Malicious Producer]
                                                   [Update Dashboard Telemetry]
```

---

## 7.1 Component 1: The GAN-Based Attacker (Malicious Producer)
- **Generative Adversarial Network (GAN):**
  - **Generator ($G$):** Takes a random noise vector $z \sim \mathcal{N}(0, I)$ and generates realistic synthetic images of horses.
  - **Discriminator ($D$):** Evaluates training images to help $G$ produce visually convincing output.
- **The Attack Scenario:**
  1. A user sends an Interest for `/animals/horse/image1`.
  2. The adversary acts as a **Malicious Content Producer** and responds with the synthetic GAN image.
  3. Intermediate NDN routers match the content name, cache the synthetic image in their Content Stores, and forward it to the user.
  4. Subsequent requests from other users are satisfied **directly from the poisoned router cache**, spreading counterfeit data network-wide.

## 7.2 Component 2: AI-Based Detection & Mitigation System
- **Deep Convolutional Neural Network (CNN) Detector:**
  - A lightweight vision model (e.g., fine-tuned MobileNetV3 or ResNet) trained to identify synthetic image artifacts (frequency-domain anomalies, pixel grid distortions).
- **Cryptographic Provenance Engine:**
  - For every content object, tracks: Content Name, SHA-256 Hash, Claimed Producer ID, Signature Validation Result, Ingestion Timestamp, Forwarding Route History, and AI Confidence Score.
- **Automated Silent Mitigation:**
  1. Content with high fake probability ($P_{\text{fake}} > \theta$) is quarantined.
  2. Confirmed poisoned entries are **automatically evicted from router Content Stores**.
  3. The rogue producer is isolated from router FIB tables.

---

## 7.3 The 5 Experimental Scenarios for Final Evaluation

| Scenario | Description | Expected Outcome |
|---|---|---|
| **Scenario 1: Normal NDN** | Legitimate producers only; no attack. | High CHR (88%), low latency, 0% privacy leakage, 0% cache pollution. |
| **Scenario 2: Attack Without WASP** | Malicious producer injects GAN images; normal NDN caching. | High cache pollution (~70%), high counterfeit delivery rate, high privacy leakage. |
| **Scenario 3: WASP Without GAN** | Original WASP privacy active against watchlist eavesdropping. | Privacy leakage suppressed to 0.18; proves baseline WASP effectiveness. |
| **Scenario 4: GAN Attack With WASP** | Counterfeit injected while WASP privacy is active. | Privacy is preserved, but cache pollution remains high—proves WASP cannot stop content poisoning! |
| **Scenario 5: GAN Attack With WASP + AI Defense** | Both Tier-1 WASP and Tier-2 AI Detection/Mitigation active. | Privacy preserved + counterfeit content detected, quarantined, and evicted from cache! |

---

## 7.4 Quantitative Metrics for Final Evaluation
1. **Cache Pollution Ratio:** $\frac{\text{Counterfeit Cache Entries}}{\text{Total Cache Capacity}}$
2. **Fake-Content Delivery Rate:** $\frac{\text{Counterfeit Packets Received by Consumers}}{\text{Total Packets Delivered}}$
3. **Propagation Ratio:** $\frac{\text{Infected Intermediate Routers}}{\text{Total Network Routers}}$
4. **AI Detection Precision & Recall:** Precision $= \frac{TP}{TP + FP}$, Recall $= \frac{TP}{TP + FN}$
5. **False-Positive Rate (FPR) & False-Negative Rate (FNR).**
6. **Network Quality Metrics:** Packet Delivery Ratio (PDR), Cache Hit Ratio (CHR), and End-to-End Latency.

---

# CHAPTER 8: ANTICIPATED VIVA / COMMITTEE DEFENSE QUESTIONS

### Q1: Why didn't you just deploy TLS or standard HTTPS encryption?
> **Answer:** *"TLS creates an end-to-end encrypted pipe between two IP hosts. In NDN, intermediate routers must inspect content names to check their Content Store (cache) and Pending Interest Table. Encrypting the payload with TLS blinds routers, reducing Cache Hit Ratio to zero and eliminating the bandwidth savings of ICN. WASP dynamically balances privacy and caching by using adaptive tokenization only when privacy exposure is elevated."*

### Q2: Why did you use a Sigmoid function instead of a simple threshold (e.g., if risk > 0.5)?
> **Answer:** *"A hard threshold causes severe route flapping and latency jitter. If traffic fluctuates around 0.50, the router would continuously toggle between expensive encryption and plaintext forwarding. The Sigmoid function provides a smooth, continuous mapping between 0 and 1, allowing cryptographic key sizes and routing diversity to scale gracefully without network disruption."*

### Q3: Why does your implementation show a 7 ms latency increase under WASP?
> **Answer:** *"The 7 ms increase reflects the cryptographic overhead of token hashing, dynamic key computation, and adaptive jitter ($\Delta_i$). However, because popular content is cached at Hop 0 or 1, cache hits satisfy requests locally, completely avoiding upstream forwarding delays and keeping the net latency penalty remarkably small."*

### Q4: If WASP already protects privacy, why are you adding a GAN?
> **Answer:** *"WASP protects Interest requests from being eavesdropped, but it is completely blind to whether the returned Data is genuine or fake. If a rogue producer responds with synthetic, GAN-generated counterfeit content, the router caches it blindly. This directly pollutes the cache and infects other users. Our GAN extension proves this vulnerability and implements a lightweight CNN to detect and purge poisoned content."*

---

### Master Summary:
This project represents a **complete, closed-loop research trajectory**:
1. **Review-I:** Problem definition, literature survey, and mathematical modeling.
2. **Review-II (Completed):** Pure Python discrete-event engine, mathematical validation of all 40+ WASP equations, dual-world lockstep simulation, interactive Web/CLI dashboards, and quantitative results matching Lal & Malani.
3. **Review-III (Next Phase):** Bridging the fundamental gap of WASP by integrating a GAN-based content poisoning attacker and an AI-based detection, provenance, and automated cache eviction defense.
