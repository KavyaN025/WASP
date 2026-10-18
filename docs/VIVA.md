# WASP Viva Preparation Guide

This document contains concise, technically accurate answers for defending the WASP implementation, based strictly on the actual validated code.

**1. What problem does WASP solve?**
WASP mitigates privacy leaks in ICN/NDN caused by in-network caching. Because caching alters request timing and routing paths, adversaries can observe these patterns to infer what sensitive content a consumer is accessing.

**2. What is a watchlist attack?**
An attack where an adversary compiles a list of sensitive content names (the "watchlist") and monitors network traffic (like request frequencies and inter-arrival times) to determine if and when users are requesting items from that list.

**3. Why is the attacker passive?**
A passive attacker eavesdrops on traffic without dropping packets, injecting fake traffic, or altering network state. This makes them extremely difficult to detect using traditional intrusion detection systems, requiring a specialized mathematical privacy algorithm like WASP.

**4. What are F, T, C and H?**
These are the feature vectors extracted by the Sliding Window observer. 
- **F**: Request Frequency.
- **T**: Inter-arrival Timing between requests.
- **C**: Cache Hit Ratio observed.
- **H**: Average Hop Count.

**5. What is PES?**
Privacy Exposure Score (PES). It is the weighted linear combination of the normalized feature vectors ($F', T', C', H'$).

**6. Why are the weights used?**
The weights ($\alpha, \beta, \gamma, \delta$) allow the network operator to tune the sensitivity of the algorithm based on the specific network topology. For instance, in a network with very deep caching, $C'$ might be weighted higher.

**7. How is privacy risk obtained?**
PES is normalized against dynamic historically observed minimum and maximum PES bounds to map it into a generic percentage ($0.0$ to $1.0$).

**8. Why use a sigmoid?**
The Sigmoid function $S = 1 / (1 + \exp(-\kappa(P - \tau)))$ allows for a smooth, bounded transition. Instead of a binary "on/off" switch that causes network jitter, the sigmoid gracefully scales the shielding intensity as risk approaches the threshold $\tau$, avoiding sudden spikes in routing overhead.

**9. What does shielding intensity represent?**
Shielding Intensity ($S \in [0, 1]$) dictates the magnitude of defensive measures. It acts as a universal scalar multiplied against maximum cryptographic encryption delays and forwarding dispersion probabilities.

**10. How does cryptographic protection adapt?**
The protection level (and thus processing delay) is calculated as $K = K_{min} + (K_{max} - K_{min})S$. When $S$ is low, delay is negligible. When $S$ approaches $1.0$, maximum delay is incurred.

**11. How does forwarding adapt?**
Instead of always choosing the shortest path (which an attacker can easily predict), WASP calculates a forwarding probability $P_f = 1-S$. Higher shielding lowers the probability of taking the direct route, forcing the router to disperse traffic across alternative paths.

**12. What is PDR?**
Packet Delivery Ratio: `satisfied_interests / total_interests`.

**13. What is ISR?**
Interest Satisfaction Rate. In our strict 1-to-1 ICN simulator, this maps identically to PDR. 

**14. What is CHR?**
Cache Hit Ratio: `total_hits / (total_hits + total_misses)`.

**15. What is privacy leakage?**
A macro metric defining the fraction of the watchlist that the attacker successfully inferred with high confidence.

**16. What is inference confidence?**
The attacker's localized mathematical probability that a specific observed request pattern maps to a targeted watchlist item.

**17. Why is adaptive protection better than always-on protection?**
Always-on protection (Static Crypto) forces maximum cryptographic and routing overheads on every packet, degrading latency. Adaptive protection mathematically limits this overhead strictly to traffic exhibiting risky patterns.

**18. What are the computational costs?**
The WASP logic incurs an $O(W)$ sliding window slice array operation, $O(1)$ constant time scalar scaling for crypto, and $O(N)$ operations for evaluating alternative route costs, making it highly efficient.

**19. What are the limitations of the simulator?**
The simulator does not execute physical AES-256 byte-shifting (which bottlenecks Python), and it models link bandwidth probabilistically rather than using strict NDN byte-queue bloat equations. Furthermore, the 5-second execution duration compresses the timeframe required to macro-average long-term privacy leakage down to zero.

**20. How does the implementation differ from the paper?**
We map the physical encryption to an exact simulated temporal delay. Additionally, we invert the $T'$ (Timing) normalization internally since shorter intervals equal higher request rates and thus higher risk.

**21. Why is the simulator used instead of a full NDN deployment?**
A lightweight Python simulator allows researchers to instantly isolate, debug, and trace the pure mathematical behavior of the WASP algorithm without being clouded by complex hardware OS networking stack anomalies.

**22. What happens if the risk is low?**
$S$ approaches $0.0$. Traffic remains in `NORMAL` mode. No encryption delay or path dispersion is applied.

**23. What happens if the risk is high?**
$S$ approaches $1.0$. Traffic enters `SHIELDED` mode, applying maximum configured cryptographic delays and drastically reducing the probability of shortest-path forwarding.

**24. What happens when crypto is disabled?**
The adaptive shielding still detects the attack and disperses routes, but encryption time modifiers fall to $0.0$.

**25. What happens when secure forwarding is disabled?**
Traffic is shielded with heavy cryptography, but packets are deterministically forced down the shortest path, potentially allowing attackers to still infer traffic via path timing analysis.
