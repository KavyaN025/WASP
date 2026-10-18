# WASP Project Master Document: Complete System Specification & GAN Extension Roadmap

> **Document Status:** Complete Master Specification (Review-II Completed $\to$ Review-III Extension)  
> **Target System:** WASP Network Security & AI Lab (Information-Centric Networking / Named Data Networking)  
> **Theoretical Foundation:** *"WASP: Watchlist Attack Shield Protocol for Privacy-Preserving Information-centric Networking (ICN)"* — Kumari Nidhi Lal & Krishna Malani (IEEE)  
> **Project Scope:** Part 1: Completed WASP Privacy Shield Testbed; Part 2: Future GAN Content Poisoning & AI Mitigation Extension.

---

# PART 1: THE FOUNDATION & COMPLETED WORK (START TO REVIEW-II)

## 1. Domain Background & The Fundamental Privacy Conflict

### 1.1 The Information-Centric Networking (ICN/NDN) Paradigm
Traditional IP networking routes packets based on **where** content is located (host IP addresses). Information-Centric Networking (ICN), and specifically Named Data Networking (NDN), replaces this with **what** content is requested. Consumers request data using hierarchical names (e.g., `/health/patient10/ecg` or `/animals/horse/image1`) embedded inside **Interest packets**. Intermediate network routers forward the Interest and return a corresponding **Data packet** containing the payload and a cryptographic signature from the producer.

### 1.2 The In-Network Caching Paradox
To optimize backhaul bandwidth and reduce user latency, NDN routers implement a local cache called the **Content Store (CS)**. When an Interest arrives at a router:
1. **Cache Hit:** If the requested name matches a valid entry in the CS, the router serves the cached Data packet immediately (0 upstream hops, latency $\approx 5$ ms).
2. **Cache Miss:** The router records the pending request in its **Pending Interest Table (PIT)** and forwards the Interest upstream using its **Forwarding Information Base (FIB)** toward the producer (latency $\approx 25-35$ ms).

**The Privacy Conflict:**
Because in-network caching relies on routers reading content names, content names are forwarded in **plaintext**. 
- If an adversary deploys standard end-to-end encryption (e.g., TLS tunnels), routers cannot inspect names, destroying caching efficiency (Cache Hit Ratio drops to 0%).
- If names remain plaintext, adversaries can observe traffic side-channels to infer user behavior.

---

## 2. Threat Model: The Passive Watchlist Attack

### 2.1 Adversary Capabilities
- **Positioning:** An adversary compromises one or more intermediate NDN routers ($A \subseteq V$).
- **Passive Nature:** The attacker is strictly **passive**—they do **not** drop, alter, or inject packets. Consequently, conventional Intrusion Detection Systems (IDS) and firewalls fail to detect them.
- **The Watchlist ($L$):** The adversary compiles a target list of sensitive content names $L = \{c_1, c_2, \dots, c_m\}$ (e.g., sensitive medical records, classified political files).
- **Inference Objective:** By observing request arrival timestamps, frequencies, and cache hits, the attacker seeks to maximize their Bayesian inference confidence $P_L(c)$ that a specific consumer is requesting watchlisted item $c$:
  $$\max \sum_{c \in L} P_L(c)$$

---

## 3. What is WASP & Why WASP?

### 3.1 The WASP Concept
WASP (**W**atchlist **A**ttack **S**hield **P**rotocol) is a router-level, autonomous adaptive defense framework formulated by Lal & Malani. Instead of applying blanket, static cryptography across all packets, WASP acts as an **adaptive immune system**:
- **Benign / Unpopular Requests:** Handled with standard ICN forwarding (0 ms crypto delay, 0% routing overhead).
- **Suspicious / Risky Requests:** Dynamically trigger multi-vector shielding (name obfuscation, timing jitter, multipath dispersion).

### 3.2 The 4-Stage Mathematical Pipeline (Algorithm 1)

#### Stage 1: Traffic Monitoring (TM)
Routers maintain a sliding observation window $W(t)$ containing the last $W$ requests (Eq. 1). From this window, the router continuously extracts a 4-dimensional traffic feature vector $X_c = [F_c, T_c, C_c, H_c]$:
1. **Request Frequency ($F_c$):** Number of occurrences of name $c$ in window $W(t)$ (Eq. 2–3).
2. **Average Request Interval ($T_c$):** Mean inter-arrival time between consecutive requests for $c$ (Eq. 4).
3. **Cache Observation Ratio ($C_c$):** Ratio of cache hits observed for $c$ in the window (Eq. 5).
4. **Average Hop Count ($H_c$):** Mean hop count traversed by requests for $c$ (Eq. 6).

#### Stage 2: Privacy Exposure Estimation (PE)
1. Features are normalized to $[0, 1]$ using dynamic min-max bounds: $x'_i = \frac{x_i - x_{\min}}{x_{\max} - x_{\min}}$ (Eq. 17).
2. **Privacy Exposure Score (PES):**
   $$\text{PES}_i = \alpha F'_c + \beta C'_c + \gamma (1 - T'_c) + \delta H'_c \quad (\alpha + \beta + \gamma + \delta = 1)$$
   *(Note: Shorter inter-arrival time indicates higher burstiness and higher risk, so $1 - T'_c$ is utilized).*
3. **Normalized Privacy Risk ($P_i$):**
   $$P_i = \frac{\text{PES}_i - \text{PES}_{\min}}{\text{PES}_{\max} - \text{PES}_{\min}} \in [0, 1]$$
4. Risk is classified into 3 paper-defined levels: $\text{Low} \; (P_i < \tau_1), \; \text{Medium} \; (\tau_1 \le P_i < \tau_2), \; \text{High} \; (P_i \ge \tau_2)$ (Eq. 21).

#### Stage 3: Adaptive Shielding Controller (ASC)
To avoid jarring binary switching (which causes network jitter and route flapping), WASP employs a continuous Sigmoid activation function to calculate **Shielding Intensity ($S_i \in [0, 1]$)**:
$$S_i = \frac{1}{1 + e^{-\kappa (P_i - \tau)}}$$
Where $\kappa$ is the adaptation rate steepness and $\tau$ is the median threshold.
- **Operational Mode ($M_i$):** $\text{Normal} \; (S_i < \eta_1), \; \text{Protected} \; (\eta_1 \le S_i < \eta_2), \; \text{Shielded} \; (S_i \ge \eta_2)$ (Eq. 23).
- **Binary Decision ($D_i$):** $D_i = 1$ if $M_i \in \{\text{Protected, Shielded}\}$ else $0$ (Eq. 24).

#### Stage 4: Dynamic Cryptographic & Forwarding Protection (DCP & SF)
When $D_i = 1$, three defensive mechanisms are dynamically scaled:
1. **Name Obfuscation (A-SHLD-1):** Plaintext name `/c/1` is hashed into an opaque token `OPAQUE_a8b9f...`. The attacker cannot match the request against their plaintext watchlist $L$.
2. **Dynamic Key & Timing Decorrelation (A-SHLD-2):** Cryptographic key size scales linearly $K_i = K_{\min} + S_i(K_{\max} - K_{\min})$ bits, inducing an adaptive jitter delay $\Delta_i = \Delta_{\min} + (\Delta_{\max} - \Delta_{\min})S_i$ ms that destroys inter-arrival timing correlation.
3. **Routing Diversity (A-SHLD-3):** Multipath dispersion factor $R_i = 1 + \rho \cdot S_i$ forces packets across alternative FIB paths, bypassing compromised observation points.

**Attacker Inference Decay (Eq. 48):**
Under active shielding, the attacker's Bayesian posterior confidence decays as:
$$P_{\text{profile}} = P_L(c) \cdot (1 - S_i)$$

---

## 4. Completed Implementation Architecture

The system was engineered as a high-fidelity, dual-interface laboratory written in pure Python 3.13 without fabricated data.

### 4.1 Discrete-Event Physics Engine (`wasp_lab/engine/`)
- **ICN Primitives:** True router data structures containing Content Store (CS), Pending Interest Table (PIT), and Forwarding Information Base (FIB).
- **Zipf Traffic Generator:** Samples requests according to Zipf popularity ($N=1000$ catalog, $\alpha=1.2$, $50$ ms mean inter-arrival time).
- **Lockstep Dual-World Runner (`runner.py`):** Simultaneously executes **WASP-ON** and **WASP-OFF** worlds against identical, decoupled random seeds (`rng_traffic` for arrivals, `rng_wasp` for defenses), guaranteeing fair 1:1 comparative evaluation.
- **Bayesian Attacker Engine (`attacker.py`):** Maintains Beta-distribution priors $(\alpha, \beta)$ for all watchlist items, updating posteriors on each observation.

### 4.2 Dual Front-End Interfaces
1. **Interactive Web Dashboard (`wasp_lab/server/` & `wasp_lab/web/`):**
   - **FastAPI Backend:** Serves REST APIs and a 10 Hz WebSocket telemetry stream (`/ws`).
   - **D3.js Network Topology:** Live vector rendering of Subscribers (S), Routers (R), Compromised Observation Points (dashed triangles), and Producers (P), animating in-transit Interest and Data packets.
   - **Chart.js Telemetry:** 6 real-time graphs displaying Attacker Confidence, End-to-End Latency, PDR/CHR, Cryptographic Overheads, Risk Histograms, and Routing Diversity against paper reference baselines.
   - **Interactive Controls:** Master buttons (`[START]`, `[PAUSE]`, `[STEP]`, `[STOP]`, `[RESEED]`), mathematical parameter sliders ($\alpha, \beta, \gamma, \delta, \kappa, \tau$), and Ablation Toggles.
2. **Terminal REPL (`wasp terminal`):**
   - An interactive command-line interface powered by Python's `cmd` module.
   - Allows operators to control the simulation, switch into individual router inspection modes (`router r0`), dump cache tables (`info`), and manually inject packets (`send /c/5 s0`).

---

## 5. Quantitative Experimental Results (Validated for Review-II)

The system was evaluated across multiple benchmark scenarios with the following quantitative outcomes:

| Metric | Baseline ICN (No Attack) | Watchlist Attack (WASP OFF) | WASP-ON (Our Implementation) | Benchmark Paper Target |
|---|---|---|---|---|
| **Attacker Inference Confidence** | 0.10 (Prior) | **0.85 – 0.98** (High Leakage) | **0.18 – 0.25** (Suppressed) | $\approx 0.20$ |
| **Packet Delivery Ratio (PDR)** | 98.0% | 65.0% (Attack degradation) | **92.4%** | $\approx 92.0\%$ |
| **Cache Hit Ratio (CHR)** | 88.5% | 63.0% | **84.2%** | $\approx 86.0\%$ |
| **Average End-to-End Latency** | 24.5 ms | 26.0 ms | **31.8 ms** (Minimal penalty) | $\approx 32.0$ ms |
| **Average Hop Count** | 1.35 | 1.40 | **1.62** (Multipath dispersion) | $\approx 1.60$ |

### Ablation Study Findings:
- **Disabling Name Obfuscation (A-SHLD-1):** Attacker confidence rebounds to ~0.78, proving name obfuscation is the primary privacy barrier.
- **Disabling Timing Decorrelation (A-SHLD-2):** Overhead decreases, but timing correlation attacks remain feasible.
- **Static Encryption Baseline ($S=1.0$ Always On):** Privacy is preserved, but latency spikes to 48 ms and CHR plunges to 52%, proving the mathematical superiority of **Adaptive Shielding**.

---

# PART 2: THE EXTENSION — GAN-BASED CONTENT POISONING & AI DEFENSE (REVIEW-III)

## 6. The Critical Drawbacks & Limitations of WASP

While WASP successfully mitigates watchlist privacy attacks, rigorous analysis reveals **four critical security boundaries**:

1. **Strictly One-Sided Threat Model (Privacy $\ne$ Authenticity):**
   WASP was designed exclusively to protect *Interest packet privacy* from passive eavesdroppers. It provides **zero verification of the returned Data payload**.
2. **Blind Caching Vulnerability:**
   WASP actually *facilitates* counterfeit content distribution! Because WASP shields Interest packets, a poisoned Data packet returned by a rogue producer will still be cached and forwarded blindly by intermediate routers based solely on name matching.
3. **Cryptographic Key Compromise:**
   If lightweight cryptographic keys are leaked or compromised, confidentiality guarantees weaken, and counterfeit responses easily bypass static signature checks.
4. **Inability to Detect Synthetic / AI-Generated Media:**
   Conventional cryptographic hashes only verify byte-for-byte equality. If an attacker produces a new, realistic synthetic image, standard network validation cannot detect that the content is fabricated.

---

## 7. The Future Project Extension: Scope & Architecture

### 7.1 Proposed Two-Tier Security Matrix
To achieve complete network security, we extend WASP into a comprehensive **Two-Tier Architecture**:
- **Tier-1: WASP Privacy Shield (Completed):** Protects Interest Privacy against Watchlist Attacks.
- **Tier-2: AI-Based Content Authenticity & Mitigation System (Next Phase):** Protects Content Integrity against GAN-based counterfeit injection.

```
                  [User Requests Content: /animals/horse/image1]
                                        │
                                        ▼
                  [Tier-1: WASP Privacy Shield (PES, Sigmoid, Obfuscation)]
                                        │
                                        ▼
                            [Simulated NDN Router Network]
                            /                            \
                  (Legitimate Producer)            (Malicious Producer)
                            │                              │
                     [Genuine Image]              [GAN Synthetic Image]
                            │                              │
                            └──────────────┬───────────────┘
                                           ▼
                                [Consumer Receives Data]
                                           │
                                           ▼
                     [Tier-2: AI-Based Detection & Mitigation System]
                     1. Cryptographic Hash & Signature Verification
                     2. Deep CNN Classifier (Genuine vs Synthetic)
                     3. Provenance & Source Tracking
                                           │
                                     Decision Policy
                                    /              \
                             (Genuine)            (Counterfeit Detected)
                                │                          │
                          [Accept Data]           [Quarantine & Evict from CS]
                                                  [Isolate Malicious Producer]
                                                  [Update Provenance Log & UI]
```

---

## 8. Detailed Attack & Defense Components

### 8.1 The GAN-Based Attacker
- **Architecture:** Consists of a Generator $G$ and Discriminator $D$.
  - The Generator takes a random latent vector $z \sim \mathcal{N}(0, I)$ and synthesizes realistic counterfeit images (e.g., horse images).
  - The Discriminator learns to differentiate real dataset images from synthetic images.
- **Malicious Producer Behavior:** The adversary operates a compromised content producer node in the NDN network. When an Interest for `/animals/horse/image1` arrives, the malicious producer serves the GAN-generated counterfeit image.
- **Cache Pollution Dynamics:** Intermediate routers cache the counterfeit image in their Content Stores. Subsequent requests from other users are satisfied directly from polluted router caches without reaching the legitimate producer.

### 8.2 The AI-Based Detector & Mitigation Engine
- **Visual Classification Model:** A fine-tuned lightweight Convolutional Neural Network (CNN / MobileNetV3 / ResNet) trained on genuine horse datasets and generated synthetic samples to detect GAN artifacts (frequency-domain anomalies, checkerboard patterns).
- **Cryptographic Provenance Engine:** For every content object, tracks:
  - Content Name, SHA-256 Hash, Claimed Producer ID, Signature Validation Result, First-Observed Timestamp, Forwarding Path History, and Model Confidence.
- **Automated Silent Mitigation:**
  1. Content with high counterfeit probability ($P_{\text{fake}} > \theta_{\text{detect}}$) is quarantined.
  2. Confirmed poisoned entries are instantly **evicted from router Content Stores**.
  3. The malicious producer node is throttled or isolated from the Forwarding Information Base (FIB).

---

## 9. Experimental Benchmark Scenarios (For Review-III)

The extended testbed will compare **5 distinct operational scenarios**:
1. **Scenario 1 (Normal NDN):** Genuine content only, no attacker present (Baseline).
2. **Scenario 2 (Attack Without WASP):** GAN counterfeit injection under standard NDN caching policies without privacy or authenticity defense.
3. **Scenario 3 (WASP Without GAN Attack):** Original WASP privacy protection operating against watchlist eavesdropping.
4. **Scenario 4 (GAN Attack With WASP):** Counterfeit content injected while WASP is active, demonstrating that privacy shielding alone does not prevent cache poisoning.
5. **Scenario 5 (GAN Attack With WASP + AI Defense):** Complete two-tier defense: WASP shields request privacy while the AI detector prevents counterfeit cache pollution.

### Quantitative Evaluation Metrics to be Measured:
- **Cache Pollution Ratio:** Fraction of router Content Store entries containing counterfeit data.
- **Fake-Content Delivery Rate:** Fraction of consumer requests that receive counterfeit content.
- **Propagation Ratio:** Fraction of intermediate routers reached and infected by counterfeit data.
- **Detection Precision & Recall:** Proportion of counterfeit samples correctly flagged vs false alarms.
- **False-Positive Rate (FPR) & False-Negative Rate (FNR).**
- **Packet Delivery Ratio (PDR), Cache Hit Ratio (CHR), and End-to-End Latency.**
- **Privacy Exposure Score (PES).**

---

## 10. Phased Implementation Roadmap (Next 1–2 Months)

### Stage 1: Validation of WASP Baseline (**COMPLETED in Review-II**)
- Implementation of all 40+ paper equations, discrete-event engine, dual-world runner, and Web/CLI testbed.

### Stage 2: Content Injection & Cache Propagation Pipeline (**Weeks 1–2**)
- Model the Malicious Producer node in the simulation engine.
- Implement conflicting Data packet resolution, signature validation policies, and Content Store poisoning dynamics.

### Stage 3: GAN Generation & Dataset Preparation (**Weeks 2–3**)
- Generate synthetic horse image dataset using a pretrained or lightweight GAN generator.
- Assign cryptographic hashes, metadata, and provenance tags to genuine vs counterfeit objects.

### Stage 4: AI Detector & Automated Mitigation Engine (**Weeks 3–4**)
- Fine-tune a lightweight CNN vision classifier to identify synthetic artifacts.
- Implement the router-level quarantine mechanism, automated cache eviction, and producer isolation policies.

### Stage 5: Full Dashboard Integration & Benchmarking (**Weeks 4–5**)
- Extend the interactive Web Dashboard with:
  - **Module 3: GAN Attack Lab** (Live counterfeit image viewer, affected routers, propagation heatmaps).
  - **Module 4: AI Detection & Mitigation Panel** (Classification confidence, provenance audit log, cache eviction counter).
  - **Module 5: Scenario Comparison View** (Real-time side-by-side graphs across all 5 benchmark scenarios).

### Stage 6: Final Documentation & Manuscript Preparation (**Week 6**)
- Compile the final capstone dissertation/thesis.
- Prepare research paper manuscript for conference or journal submission.

---

# SUMMARY: THE COMPLETE ELEVATOR PITCH

> *"In this project, we address the two greatest security vulnerabilities in Information-Centric Networking: **Consumer Privacy Leaks** and **Content Poisoning**. 
> 
> In Phase 1, we implemented and validated the **WASP Protocol**, an adaptive router-level framework that monitors traffic telemetry, computes a Privacy Exposure Score (PES), and uses a Sigmoid controller to scale cryptographic shielding and routing diversity only when privacy risk is high. This suppresses attacker inference confidence by over 75% with only ~7 ms of latency overhead.
> 
> However, our rigorous evaluation revealed a critical drawback: WASP protects request privacy, but it blindly forwards and caches counterfeit Data. In Phase 2, we are extending the project into a comprehensive **Two-Tier Security Matrix**: combining WASP privacy shielding with a **GAN-based counterfeit content generator** and an **AI-driven detection and automated cache eviction defense**. This provides a complete, robust security blueprint for next-generation content networks."*
