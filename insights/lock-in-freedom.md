# Lock-in / Freedom to Operate

Insights about hidden costs, switching barriers, and contractual lock-in. Applicable to any consultancy helping clients reduce vendor dependency.

## What belongs here

- Reframes that reveal hidden switching costs or vendor dependency
- Evidence based on contract analysis, regulatory requirements (e.g., EU Data Act), or migration experience
- Triggers: contract renewals, regulatory deadlines, pricing increases, vendor policy changes

## Stakeholder tailoring

- **Technical leadership:** Frame as architectural debt — vendor-specific abstractions limit future options
- **Finance:** Frame as financial exposure — quantify the cost of switching or being unable to switch
- **Security/compliance:** Frame as supply chain risk — single vendor dependency is a concentration risk
- **Executive:** Frame as strategic autonomy — technology strategy should not depend on a single vendor's decisions

## Example insight structure

```yaml
category: lock-in-freedom
reframe: "Your multi-cloud strategy is not multi-cloud — it is multi-vendor lock-in."
evidence: "Most multi-cloud deployments use vendor-specific services on each cloud, creating parallel lock-in."
stakeholder_lens:
  - role: CTO
    framing: "Each cloud-specific service is a decision your successor will have to live with."
  - role: CFO
    framing: "Switching costs compound annually. Have you calculated yours?"
trigger: "Prospect mentions multi-cloud as a strategy"
next_step: "Lock-in audit to quantify actual switching costs"
```
