# Controlled State Resynchronization for Kubernetes Edge Nodes

A simulation-based research artifact for studying controlled state resynchronization of Kubernetes edge nodes after network partitions.

## Overview

Kubernetes edge nodes may temporarily lose connectivity with the control plane because of network interruptions. When connectivity is restored, multiple nodes may attempt to synchronize their state at nearly the same time.

This synchronized recovery activity can create a sudden burst of requests toward the Kubernetes API server and increase control-plane load. This behavior is referred to in this work as a **reconnection storm**.

This project studies a controlled state resynchronization approach called the **Resync Governor**. The proposed approach aims to regulate recovery activity and reduce synchronized request bursts when edge nodes reconnect after network partitions.

The work is evaluated using a discrete-event simulation framework.

## Research Objective

The main objectives of this work are:

- Study the impact of simultaneous edge-node reconnections after network partitions.
- Analyze the request bursts generated during state recovery.
- Evaluate a controlled resynchronization mechanism.
- Compare the proposed approach against baseline recovery strategies.
- Measure recovery behavior, request rates, queue peaks, and availability-related metrics.

## Proposed Approach: Resync Governor

The Resync Governor is designed to control how edge nodes resume synchronization after connectivity is restored.

Instead of allowing all reconnecting nodes to resume recovery activities simultaneously, the approach regulates their resynchronization behavior to reduce concentrated request bursts.

The proposed method is evaluated against three baseline approaches:

- **B1:** Baseline recovery strategy 1.
- **B2:** Baseline recovery strategy 2.
- **B3:** Fixed-rate recovery strategy.

The exact implementation and configuration details are provided in the accompanying source code and experiment files.

## Experimental Setup

### Simulation Environment

The evaluation uses a Python-based discrete-event simulator with NumPy to model the Kubernetes control plane and simulated edge agents at the API-request level.

No Kubernetes cluster was available for this study. Therefore, the experiments do not use a real Kubernetes API server, kubelet, or etcd deployment.

The simulated API server is modeled as a single first-in, first-out (FIFO) server with:

- Service capacity: 1,000 requests per second.
- Queue limit: 400 requests.
- HTTP 429 responses when the queue is full.
- Background traffic: 300 requests per second.
- Synthetic availability probes: 20 requests per second.
- Request round-trip time: 40 ms.
- One service unit per API request.

The simulator does not separately model etcd CPU or memory consumption.

### Experimental Scenarios

The paper evaluates the following scenarios:

| Scenario | Description | Configuration |
|---|---|---|
| S1 | Normal operation (control) | Background load only; reference condition, not run separately |
| S3 | Simultaneous reconnection | N = 5, 10, 20, 50, 100, 200; outage duration uniformly distributed between 30 and 600 seconds |
| S4 | Flapping connectivity | N = 50; repeated connection and disconnection phases of 10–30 seconds over 240 seconds |
| S6 | Governor failure | N = 200; Governor terminated 5 seconds after recovery begins |

The single-node scenario (S2) and degraded-network scenario (S5) are not evaluated in the paper.

### Fault Injection

Outage durations are drawn uniformly from 30 to 600 seconds.

All nodes reconnect at the same time, with a random healing offset of up to 1 second.

A watch can be resumed only when the outage is shorter than the 300-second history window. Longer outages receive HTTP 410 Gone.

In each run, 5% of nodes are randomly selected to receive an injected inconsistency after their first synchronization. The injected inconsistencies include:

- A deleted object.
- An extra object.
- A stale generation.
- Status-only drift.

In the flapping scenario, connectivity alternates between connected and disconnected phases lasting 10–30 seconds for 240 seconds. Synchronization in progress is aborted at each disconnection.

In the Governor-failure scenario, the Governor is terminated 5 seconds after connectivity is restored and is not restarted.

### Methods Compared

The proposed Resync Governor (P) is compared against three baseline methods:

- **B1 — Default behavior:** Relist on reconnect with a fixed 1-second retry after HTTP 429.
- **B2 — Exponential backoff with full jitter:** Relist on reconnect, with a 0.5-second base and a 30-second maximum backoff.
- **B3 — Fixed-rate limiter:** Uses the same rate, burst, and concurrency settings as the proposed Governor, but admits nodes in first-come, first-served order without resume preference.

The paper also evaluates four ablations:

- **A1:** No priority or aging.
- **A2:** No watch-resume-first behavior.
- **A3:** No digest verification.
- **A4:** No agent-side fallback.

### Repetitions and Random Seeds

Each configuration is executed 30 times using seeds 1 through 30.

All methods share the same seed for each paired run. This ensures that node attributes, criticality, outage duration, healing offset, injected inconsistencies, and background arrivals are identical across methods within a pair.

The simulator is deterministic for a given seed. Run-to-run variation is introduced through node attributes, background arrivals, and retry jitter.

The tuning and test seeds are kept separate:

- Tuning seeds: 1001–1005.
- Test seeds: 1–30.

### Parameter Tuning

Hyperparameters are selected using a separate tuning set with seeds 1001–1005 and N = 100. The selected settings are then frozen for the test experiments.

Tuning is performed in three stages:

1. Search the admission rate r in {2, 3, 4, 5} full-sync units per second, concurrency m in {8, 16, 32}, and burst b in {5, 15}. Select the lowest weighted recovery cost among configurations whose mean peak request rate remains within capacity.
2. Compare four weight triples with the aging parameter τ in {30, 60} seconds, using weighted cost plus 0.2 times the p99 recovery time of low-priority nodes.
3. Freeze the selected configuration and evaluate it using the separate test seeds.

### Run Duration and Measurement Window

A simulation run ends when all nodes become Ready or when the maximum run duration is reached:

- 300 seconds for regular recovery scenarios.
- 360 seconds for the flapping scenario.

Load metrics are calculated over the first 120 seconds after connectivity is restored.

The simulator starts from an idle server, so no warm-up period is used.

### Evaluation Metrics

The experiments measure:

- API requests per second, including background traffic, using one-second bins.
- Peak API request rate.
- p99 latency of accepted API requests.
- Peak API queue depth.
- Node recovery time, measured from healing until Ready, including digest verification.
- Recovery success rate.
- Consistency violations.
- Synthetic service availability, defined as the fraction of probes answered within 500 ms.
- HTTP 429 response count.
- Network bytes, based on assumed payload sizes.

The assumed payload sizes are:

| Operation | Payload |
|---|---:|
| Full synchronization | 285 KiB |
| Watch resumption | 40 KiB |
| Verification | 50 KiB |
| Retried request | 1 KiB |

API-server and etcd CPU and memory are not reported because they are not modeled separately.

### Consistency Verification

For each node, the simulator compares the desired objects assigned by the control plane with the objects held by the agent after synchronization.

Object tuples contain:

`kind, namespace, name, UID, generation`

The tuples are sorted lexicographically and hashed using SHA-256.

Verification succeeds when the desired and observed digests match.

This detects missing objects, extra objects, replaced objects, and stale generations. It does not inspect status fields or content that does not change generation, and it is not claimed to detect every possible divergence.

The detection rate is measured against the injected inconsistencies.

### Reproducibility

The paper describes the simulator, tuning and analysis scripts, and raw per-run and per-node CSV results as supplementary research artifacts.

The results use the following identifiers and fields:

**Per-node results**

`run_id, method, scenario, N, seed, node_id, criticality, outage_s, recovery_s`

**Per-run results**

`run_id, method, scenario, N, seed, peak_req_s, p99_ms, peak_queue, http_429, availability, success_rate, violations, injected, requests, kib_total, resume_syncs, full_syncs`

The repository URL will be added here once the artifact is published.

**Repository:** [https://github.com/AbhishekKallolimath/kubernetes-edge-resync-governor]

### Scope and Limitations

This evaluation is based on a discrete-event simulation with assumed request costs and a modeled control-plane queue.

The results should not be interpreted as measurements from a production Kubernetes cluster. Real-cluster validation is required to confirm the observed behavior under actual API-server, kubelet, etcd, and network conditions.

The paper also reports that the aging mechanism did not show a measurable benefit under the evaluated conditions. Further experiments with larger fleets, lower admission rates, or continuing arrivals are needed to investigate possible starvation behavior.

