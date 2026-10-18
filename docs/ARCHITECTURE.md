# Architecture Overview

## Data Flow (Simulator -> UI)

```mermaid
flowchart TD
    A[Simulator Topology] --> B[Interest Routing]
    B --> C[WASP Engine]
    C -->|Extracts F,T,C,H| D[Privacy Exposure (PES)]
    D -->|Risk Scalar| E[Adaptive Controller (Sigmoid)]
    E --> F[Dynamic Crypto Overhead]
    E --> G[Secure Forwarding Probabilities]
    
    C -->|Stores state| H[Backend FastAPI]
    H -->|REST API| I[React Frontend Dashboard]
    H -->|WebSockets| J[Live Packet Inspector]
```

## Single Source of Truth
The frontend acts purely as a stateless presentation layer. All equations, mathematical bounding, decision mapping, and packet counting occur locally within the `wasp/` and `simulator/` python namespaces. This guarantees strict compliance with the **Zero Mock Data** mandate.

## Implementation of Lifecycle Trace
The `InterestInspector.tsx` frontend module depends entirely on `WASP_DECISION` payloads emitted by the backend via WebSocket or queried via `/api/network/interest/{id}`. The packet metadata includes node origin, feature normalizations, sigmoid logic outputs, and cryptographic assignments, offering a flawless analytical trail for every request without frontend inference.
