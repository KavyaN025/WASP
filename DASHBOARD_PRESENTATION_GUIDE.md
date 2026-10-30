# WASP Dashboard — Complete Session Guide

This document explains everything built into the WASP dashboard during this
working session: the existing privacy engine, and the new Content
Authenticity extension (GAN → poisoning simulation → anti-GAN defense)
layered on top of it. Written to be read start to finish before a
presentation, or used as a reference afterward.

**Live dashboard pages** (run `wasp server` from the `WASP/` folder, then
open these):

| Page | URL |
|---|---|
| Dashboard | `http://127.0.0.1:8001/` |
| Network Controls | `http://127.0.0.1:8001/network` |
| Router Mode | `http://127.0.0.1:8001/router/r0` |
| GAN Comparison | `http://127.0.0.1:8001/gan-comparison` |
| Mesh Poisoning | `http://127.0.0.1:8001/mesh-poisoning` |

**GitHub**: https://github.com/KavyaN025/WASP

---

## 1. The problem, in one sentence

WASP (Watchlist Attack Shield Protocol) guarantees **privacy** — it hides
*who* requested *what* from a passive network eavesdropper. It says
**nothing** about **authenticity** — whether the content sitting in a
router's cache is actually what the real publisher produced. This session's
work closes that second gap: generate fake content (GAN), simulate an
attacker substituting it into the network (Content Poisoning Attack), then
build a defender that catches and corrects it (anti-GAN).

---

## 2. Background: how ICN/NDN works (needed before anything else makes sense)

Information-Centric Networking (ICN, and its concrete instantiation Named
Data Networking, NDN) is a network model where you request content **by
name** (e.g. `/cats/cat_image5.jpg`), not by the IP address of a specific
server. Three kinds of participants:

- **Subscriber** — the requester. Sends an **Interest** packet naming
  content it wants.
- **Router** (Content Router, CR) — forwards Interests toward whoever can
  answer them, and **caches** content it sees pass through, so the *next*
  identical request can be answered immediately without going all the way
  to the original source. Every router keeps three structures:
  - **FIB** (Forwarding Information Base) — "which direction do I send
    Interests for this name?"
  - **PIT** (Pending Interest Table) — "I forwarded this Interest; which
    face do I send the answer back out on?"
  - **CS** (Content Store) — the actual cache.
- **Publisher / Producer** — the original source of the content.

A **Watchlist Attacker** is not a node of its own — it's a passive
eavesdropper that has compromised one specific router and silently logs
every Interest that passes through it, trying to infer who is requesting
sensitive ("watchlisted") content.

---

## 3. Part A — The WASP privacy engine (pre-existing, this session extended it)

### 3.1 Algorithm 1, the five-stage pipeline

Every Interest packet is processed through five stages:

1. **Traffic Monitoring (TM)** — computes behavioral features over a
   sliding window of the last `W` Interests:
   - `F_c` — how many times this exact content name has been requested
     recently (request frequency)
   - `T_c` — average time between repeated requests for this name
   - `C_c` — cache-hit ratio across the network so far
   - `H_c` — hop count (how many routers the request actually traveled
     through, computed from the real FIB-resolved path)

2. **Privacy Exposure Estimation (PE)** — combines those four features
   (after min-max normalization) into a single **Privacy Exposure Score**:
   `PES = α·F' + β·C' + γ·T' + δ·H'` (weights sum to 1), then normalizes
   again to get `P_i`, the final **privacy risk** for this packet, bucketed
   into Low / Medium / High against two thresholds (`τ₁`, `τ₂`).

3. **Adaptive Shielding Control (ASC)** — converts the risk into a
   **shielding intensity** via a sigmoid: `S_i = 1 / (1 + e^{-κ(P_i - τ)})`.
   `S_i` is then bucketed into a protection mode: Normal / Protected /
   Shielded, which sets the binary **shielding decision** `D_i`.

4. **Dynamic Cryptographic Protection (DCP)** — if `D_i = 1`, the content
   name gets encrypted with a key size that *scales with* `S_i`:
   `K_i = K_min + S_i·(K_max − K_min)` — low-risk traffic gets weak/no
   encryption (cheap), high-risk traffic gets strong encryption
   (expensive), rather than encrypting everything uniformly.

5. **Secure Forwarding (SF)** — if shielded, also adds an **adaptive
   delay** (`Δ_i`, scaled by `S_i`) to decorrelate timing patterns, and
   increases **routing diversity** (`R_i`, also scaled by `S_i`) so
   repeated requests don't always take the identical path an attacker
   might be watching.

### 3.2 The attacker's model (Bayesian posterior)

The attacker doesn't know for certain whether a subscriber wants
watchlisted content — it maintains a **belief**, represented as a Beta
distribution `[α, β]` per content name:
- **Prior** — the starting belief, before any observation (`[1, 9]` →
  10% confidence by default).
- **Posterior** — the updated belief after an observation. A full
  plaintext observation adds +1 to `α` (strong evidence "yes"). A shielded
  observation (opaque token instead of the real name) *shrinks* `α`
  instead, proportional to how strong the shielding was — the attacker's
  confidence actively erodes rather than just failing to grow.
- **Confidence** = `α / (α + β)` — the displayed probability.

### 3.3 The four schemes (this session's refactor — previously there was only one crude ON/OFF toggle that didn't actually gate the math)

| Scheme | Decision `D_i` | Key size | Adaptive delay/diversity | Attacker sees |
|---|---|---|---|---|
| **NORMAL** | forced 0 | 0 | none | *nothing* — no adversary modeled at all (the paper's unattacked baseline) |
| **ATTACK** | forced 0 | 0 | none | full plaintext name every time (unprotected baseline) |
| **STATIC_CRYPTO** | forced 1 | fixed 256-bit | none | opaque token, but fixed 0.5 suppression (non-adaptive conventional crypto) |
| **WASP** | adaptive (sigmoid) | interpolated 128–256 bit | adaptive, `S_i`-driven | opaque token, suppression = `1 − S_i` (adapts to risk) |

Each scheme keeps its **own independent attacker-confidence tracker**, so
switching schemes mid-run doesn't contaminate the comparison — you can
watch all four confidence levels evolve in parallel.

### 3.4 The mesh topology rework (ported from a separate NDN-caching project)

The original WASP dashboard had a single hard-coded producer and a simple
linear/mesh chain with synthetic content names (`/c/1`, `/c/2`, ...). This
session replaced it with:

- A **random connected mesh** of routers (via `networkx`), reproducibly
  seeded so the same config always regenerates the same topology.
- **Multiple publishers**, one per content *category* — currently `cats`
  and `dogs`, each with a real image catalog.
- **Per-category FIB**, computed via BFS shortest-path tree from each
  publisher's router — genuine multi-hop routing instead of a hardcoded
  walk.
- **Real content**: 50 real cat photos + 50 real dog photos (the same
  images later used as the "real" class when training the GAN and the
  anti-GAN detector — one consistent dataset across the whole project).

---

## 4. Part B — The GAN work (generating fake content)

### 4.1 Why GANs, and what one actually is

A **GAN (Generative Adversarial Network)** is two neural networks trained
against each other:
- **Generator (G)** — takes random noise, tries to produce a fake image
  realistic enough to fool the Discriminator.
- **Discriminator (D)** — tries to tell real images apart from G's fakes.

They improve together in a minimax game. For this project, only G's
*output* matters at deployment time — it's the thing used to manufacture
fake cat/dog photos that later get planted in the network as poisoned
content.

### 4.2 The four architectures compared

All four share the exact same convolutional backbone (so the comparison
is "same architecture, different loss," not confounded by also changing
network shape):

| Architecture | What's different | Role |
|---|---|---|
| **DCGAN** | Classic baseline — plain binary cross-entropy loss | Mandatory baseline every GAN survey cites |
| **LSGAN** | Least-squares loss instead of BCE, meant to train more smoothly | Stability variant #1 |
| **WGAN-GP** | Wasserstein distance + gradient penalty, theoretically the most resistant to mode collapse | Stability variant #2 — **the one ultimately deployed** |
| **Conditional GAN (cGAN)** | Same as DCGAN, but the class label (cat/dog) is fed in so you can ask for a specific category | The only one that can be steered, but turned out broken (see §4.5) |

### 4.3 Data strategy

Two training runs happened, because the first one wasn't good enough:

**Run 1 (local CPU)** — trained from scratch on only the 50+50 real images
at 64×64 resolution, regularized with **DiffAugment** (randomly perturbs
every batch — color, translation, cutout — so the discriminator can't just
memorize 100 exact photos instead of learning the general pattern).
Produced only abstract blobs of color — not enough data/resolution for
anything recognizable. Useful as a pipeline proof, not as a real result.

**Run 2 (Kaggle GPU, Tesla T4)** — retrained all 4 architectures properly:
- **~7,349 real images** (Oxford-IIIT Pet dataset, auto-downloaded via
  `torchvision`, both splits combined) instead of 100
- **128×128 resolution** instead of 64×64
- Same DiffAugment regularization, now genuinely useful given the GPU
  budget
- `torch.backends.cudnn.benchmark = True` and **mixed precision (AMP)**
  training — a real debugging story: the first GPU attempt was taking
  **~59 seconds per epoch**, which is absurd for a tiny network on a real
  GPU. Diagnosed with a phase-by-phase timing script (not guesswork) down
  to the raw forward passes themselves being slow — missing cuDNN
  autotuning and not using the T4's Tensor Cores (FP16). Fixing both
  dropped one full training step from **249ms → 52ms, a 4.8× speedup**.
  WGAN-GP's gradient penalty (a "double backward," numerically fragile in
  FP16) was deliberately kept in full precision while everything else got
  the speedup, to avoid silently corrupting the one architecture that
  actually mattered most.
- Training also got **checkpoint-every-5-epochs with automatic resume**,
  after a Colab session disconnected mid-run (idle-tab timeout) and lost
  ~14 hours of unsaved progress the first time. Second attempt used
  Kaggle's "Save & Run All" background-commit mode instead, which survives
  closing the browser entirely.

### 4.4 FID — how the 4 architectures were actually scored

**FID (Fréchet Inception Distance)**: run a pretrained image classifier
(Inception-v3) over both the real images and the generated images, but
instead of reading its final prediction, take the internal feature
activations — a compressed numerical "fingerprint" of texture/shape/color
patterns. Fit a Gaussian distribution to the real images' fingerprints and
a separate one to the fakes', then measure the distance between those two
Gaussians. **Lower = more realistic** (0 would mean statistically
identical to real photos).

### 4.5 Results

| Rank | Architecture | FID | Note |
|---|---|---|---|
| 1 | **DCGAN** | 256.08 | Leading candidate |
| 2 | **WGAN-GP** | 256.68 | Leading candidate, effectively tied with DCGAN |
| 3 | LSGAN | 287.49 | **Mode collapse** — produced the same repeated stripe pattern at epoch 5 *and* epoch 100, confirmed by a singular covariance-matrix warning during FID computation (a direct numerical signature of collapse) |
| 4 | Conditional GAN | 300.76 | **Broken from epoch 5 onward** — a persistent checkerboard artifact that never resolved into real content, most likely because the 2-dimensional class-conditioning channel gave the Discriminator too easy a shortcut, starving the Generator of a useful gradient toward real image content |

*(FID values in the 250–300 range are expected given the constraints —
GPU-trained from scratch, no pretrained initialization available for
simple GAN architectures. These are meant as a **relative ranking**
between the 4 candidates, not a claim of photorealism.)*

### 4.6 Why WGAN-GP was selected over DCGAN despite the near-tied FID

The 0.6-point FID gap is noise-level, not a meaningful difference. The
actual deciding factors:
1. **Mode collapse risk** — WGAN-GP's loss function is a structural fix
   for the failure mode that visibly wrecked LSGAN and cGAN in this exact
   experiment. DCGAN *happened* not to collapse this time; that's not the
   same as being structurally resistant to it.
2. **What it's used for** — the deployed generator needs to keep producing
   varied fakes as the simulation runs repeatedly; a generator with a known
   collapse risk is a worse foundation even when today's snapshot looks
   fine.
3. **Defensibility** — "picked for the strongest theoretical guarantee,
   with numbers that happen to support it" is a stronger paper sentence
   than "picked because the number was 0.6 lower."

### 4.7 External reference point

The GAN Comparison page also cites (not retrained, purely cited for
context) `MannShah0312/WGAN-Wasserstein_Generative_Adversarial_Network`, a
DCGAN-vs-WGAN-GP comparison on the standard CIFAR-10 benchmark, as
literature-level context for how these two loss functions typically
compare on a dataset with no resource constraints.

---

## 5. Part C — Mesh Poisoning (the attack simulation)

**Content Poisoning Attack (CPA)**: an attacker substitutes fake content
into a router's cache **under the name of real, legitimate content** (not
a new made-up name) — e.g. the cache entry for `/cats/cat_image5.jpg`
silently becomes a WGAN-GP-generated fake image. Every subsequent
legitimate request for that exact name is served the fake object, through
the network's completely ordinary cache-lookup path — no special-casing
anywhere in WASP's routing or privacy logic, because a name-based lookup
genuinely cannot tell the difference. That's precisely the gap this whole
extension exists to demonstrate: WASP's shielding protects the *privacy*
of that request; it does nothing to stop *this*.

**Default targeting**: when you poison a router, it defaults to
substituting fake content under **watchlisted** names specifically — the
same content WASP's own privacy pipeline is working hardest to protect —
a deliberate narrative tie-in showing both halves of the system are being
exercised against the same target content.

**What it looks like live**: poisoned routers get a dashed purple ring in
the topology view; any packet currently carrying poisoned content renders
as a purple square instead of the normal blue/teal, visible in real time
as it animates across the mesh. A running "Fake Content Served" counter
tracks how many times an unwitting subscriber has been served a fake
object so far.

---

## 6. Part D — The Anti-GAN (the defense)

### 6.1 Why a *separate* model, not just "the GAN's own discriminator"

A GAN's co-trained discriminator is a training-time sparring partner for
one specific generator — it tends to overfit to that generator's exact
quirks. The anti-GAN here is a **separately trained forensic classifier**,
deliberately trained on fakes from **all four** generators (not just the
deployed WGAN-GP), so it generalizes to "this looks GAN-generated" rather
than "this looks like WGAN-GP specifically" — the same design principle
behind real deepfake-detection research (CNNDetection, Wang et al., CVPR
2020, cited in the literature survey).

### 6.2 Architecture and training

- **ResNet-18**, pretrained on ImageNet, fine-tuned as a binary classifier
  (real vs. fake).
- **Training data**: 500 real images + 800 fakes (200 from each of the 4
  architectures) — all already sitting locally from the GPU run's own FID
  evaluation.
- **Augmentation**: random JPEG re-compression + blur during training, so
  the detector can't just key off "this file was never compressed" as a
  shortcut.
- **Result**: 100% validation accuracy by epoch 3, ~5 minutes to train on
  CPU. Verified live afterward: real photos score ~1.0 (confidently real),
  WGAN-GP fakes score ~0.001 (confidently fake) — clean separation.

### 6.3 The scan-and-mitigate policy

Detection is **not** run automatically on every cache insert — inference
takes tens of milliseconds, too slow for the simulation's 10Hz loop, and
a triggered scan better matches how real detection actually works (attack
happens, dwell time passes, detection catches up later). Instead:

- **Run Anti-GAN Scan** (per router, on demand) — scores every object
  currently cached there, labels each `VERIFIED` (score ≥ 0.5) or
  `SUSPECT` (below), and shows the detector's verdict next to the actual
  ground truth so misclassifications are visible, not hidden.
- **Mitigation toggle**:
  - **OFF** — "detect only." Suspect entries are flagged and logged, but
    stay in the cache; subscribers keep getting served the fake content.
  - **ON** — "detect and correct." Any SUSPECT entry is evicted and the
    router re-fetches and re-verifies the genuine content under that same
    name from the real catalog, closing the loop.
- **Live Detection Accuracy stat** — running tally of detector verdicts vs.
  ground truth across every scan performed so far.

**Honest caveat worth keeping**: in testing, the detector produced one
genuine false positive — a real image scored low enough to get flagged
and "corrected." Because mitigation always re-fetches the *actual* real
file rather than inventing a replacement, a false positive just costs one
harmless, wasted re-verification — not lost or corrupted content. That
resilience property is worth stating explicitly rather than glossing over
the imperfection.

---

## 7. Dashboard — page by page

### 7.1 Dashboard (`/`)
The main privacy view. Toolbar: Start/Pause/Step/Stop + live sim-time
clock. Four scheme buttons (NORMAL/ATTACK/STATIC CRYPTO/WASP) — each is a
genuinely different computational path, not a display filter. Comparison
strip shows live attacker confidence, PDR, CHR, latency, and
shielding/crypto overhead for all 4 schemes side by side. Below that: the
animated mesh topology (color-coded packets by shielding mode), a live
packet trace table, a formula-breakdown panel showing the exact Algorithm
1 math for whichever packet you click, a watchlist confidence monitor, and
six live evaluation graphs plotted against the paper's reference values.

### 7.2 Network Controls (`/network`)
Simulation controls plus three configuration groups: topology editor
(router/subscriber/publisher counts, linear vs. mesh pattern), traffic
editor (Zipf popularity skew, watchlist size, which router the attacker
observes from), and the full set of WASP's mathematical parameters
(thresholds, sigmoid steepness, key-size bounds, delay bounds) — all
live-tunable without restarting. Also the three WASP shielding
sub-mechanism toggles (name obfuscation / timing decorrelation / routing
diversity), which only take effect while the active scheme is WASP.

### 7.3 Router Mode (`/router/{id}`)
Per-router inspector: PIT/CS/FIB tables for that one node, a manual
Interest-injection box to fire a specific named request and watch exactly
what happens at that hop, recent traffic through that router, and — if
that router is the compromised observation point — an "Attacker
Interception Feed" showing exactly what the adversary sees passing
through (plaintext, opaque token, or encrypted token, depending on active
scheme).

### 7.4 GAN Comparison (`/gan-comparison`)
Static report page (not live simulation data): the FID ranking table and
bar chart for all 4 trained architectures, their actual generated sample
grids side by side, and the cited external CIFAR-10 reference comparison
for literature context.

### 7.5 Mesh Poisoning (`/mesh-poisoning`)
The attack-and-defense page. "Launch Content Poisoning Attack" panel
(pick a router + category + how many watchlisted names to poison). "Anti-
GAN Content Authenticity Scan" panel (pick a router to scan, toggle
mitigation on/off, see per-item detector verdicts and the running
detection-accuracy stat). Live topology with poisoned-router rings and
purple fake-content packets. Poisoning Event Log and a live "Content
Served — Real vs. Fake" feed with a running fake-content-served counter.

---

## 8. Bugs found and fixed this session (worth mentioning — shows the work was verified, not just built)

- **`/stop` didn't actually reset anything** — it only changed the status
  label; `sim_time`, traces, and caches kept accumulating, so Stop→Start
  silently resumed instead of beginning fresh. Fixed with a proper
  `reset_simulation()`.
- **Stale browser caching** — HTML/CSS/JS routes had no cache-control
  headers, so a plain refresh could silently serve old content during
  active iteration. Fixed with explicit no-cache headers.
- **GPU training was 5–50× slower than it should have been** — root-caused
  with a phase-by-phase timing script to missing `cudnn.benchmark` and no
  mixed precision, not (as first guessed) disk I/O.
- **Caching at *every* router regardless of actual path** — a pre-existing
  bug from before this session's topology rework; fixed naturally as a
  side effect of switching to real FIB-resolved routing.
- **Several dead/mismatched fields** in the terminal REPL (`do_status`,
  `do_topology`, `do_inject`, `do_events` all referenced API fields that
  had since been renamed or never existed) — found during an unrelated
  code review and fixed for real end-to-end correctness, not just the web
  dashboard.
- **Non-reproducible topology generation** — mesh/router-attachment
  randomness was never seeded, so identical configs produced different
  topologies on every call. Fixed by seeding from the existing traffic
  seed.

---

## 9. Glossary

| Term | Meaning |
|---|---|
| **ICN / NDN** | Information-Centric Networking / Named Data Networking — request content by name, not server address |
| **Interest / Data packet** | The request / the response, in NDN terminology |
| **PIT / CS / FIB** | Pending Interest Table / Content Store (cache) / Forwarding Information Base — the three structures every router keeps |
| **Watchlist attack** | A passive eavesdropper at a compromised router inferring sensitive requests by observation alone |
| **PES** | Privacy Exposure Score — weighted combination of frequency/cache/timing/hop-count features |
| **Shielding intensity (`S_i`)** | Sigmoid-mapped privacy risk, 0–1, driving how hard WASP protects a given packet |
| **Posterior / prior** | The attacker's updated belief / its starting belief, before seeing evidence, both expressed as a Beta distribution |
| **GAN** | Generative Adversarial Network — a Generator and Discriminator trained against each other |
| **DCGAN / LSGAN / WGAN-GP / cGAN** | Four GAN loss-function variants compared in this project (see §4.2) |
| **Mode collapse** | A GAN failure mode where the Generator stops producing diverse output and gets stuck on a narrow repeated pattern |
| **FID** | Fréchet Inception Distance — statistical distance between real and generated images' feature distributions; lower = more realistic |
| **DiffAugment** | Differentiable data augmentation applied during GAN training specifically to prevent the discriminator memorizing a small dataset |
| **Content Poisoning Attack (CPA)** | Substituting fake content into a cache under a real content name |
| **Anti-GAN** | This project's term for the separately-trained forensic detector that catches GAN-generated fakes |
| **Mitigation** | The policy of automatically evicting and re-fetching real content when the anti-GAN flags something SUSPECT |

---

*Generated as part of a working session extending the WASP dashboard with
a GAN-based content-authenticity track. Source: https://github.com/KavyaN025/WASP*
