# 7 Sustaining the Stack: Measured Emissions

The third ASISAS pillar (*sustainable, independent, and responsible autonomy*) is decorative until you can answer it with a number. For a Kubernetes-deployed agentic system, the relevant numbers are watt-hours, grams of CO₂-equivalent, and litres of water.

We measure them, on the same cluster Mother Tree runs on, with KEIT.

## 7.1 KEIT

**KEIT** (the *Kubernetes Emissions Insights Tool*) is an open-source (Apache-2.0) emissions monitoring stack developed by Aknostic [https://github.com/aknostic/keit]. It composes Kepler (per-process energy via kernel performance counters), Prometheus and Grafana (metrics and visualisation), ElectricityMaps (live regional grid carbon intensity, Paris for our Scaleway deployment), and Boavizta (hardware embodied-emission values), all installed via Helm. KEIT runs in its own namespace; its own CO₂ cost is a small constant we account for explicitly.

## 7.2 Per-namespace attribution

The relevant property for an experience report on Mother Tree is that KEIT performs **per-namespace attribution**. Energy is allocated to workloads via Kepler's per-process accounting; embodied emissions are pro-rated across namespaces by node-share; grid intensity is applied uniformly to the cluster's region. The result is a per-namespace daily figure: grams of CO₂-equivalent and litres of water consumed by the `mother-tree` namespace specifically.

This produces the answer the responsibility claim needs.

## 7.3 The numbers

> *§7.3 to be completed by F. Paganelli and J. Geurtsen with operational figures from the Aknostic cluster. Expected content: daily mean CO₂-equivalent for the `mother-tree` namespace broken down by workload class (ingestion, training, pulse, bot, Anthropic egress); daily water use; the KEIT footprint as a fraction of the measured Mother Tree footprint; and reasoned counterfactual comparisons against (i) the same workload through US-hosted frontier inference and (ii) the same workload re-cast as an autonomous-agent loop with retries and tool-call branching.*

## 7.4 What this measures, and what it does not

KEIT measures the operational and embodied emissions of the Kubernetes cluster running Mother Tree; it does not measure the emissions of inference calls that leave the cluster (Scaleway and Anthropic). What KEIT will let us claim, once §7.3 is filled in, is that the part of the system we host has a measured environmental footprint; whether the architectural decisions in §3 and §4 (scheduled cron, no autonomous retry loops) make a measurable difference is a comparison we have not yet run.
