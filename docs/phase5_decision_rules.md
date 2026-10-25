# Sahaay AI — Phase 5 Hardened Decision Engine Rules & Logic Matrix

## 1. Principles of Decision Integrity

The Sahaay AI Decision Engine synthesizes multi-modal, multi-source evidence into an actionable, explainable alert level. It enforces the following core architectural rules:

1. **Separation of Observed Evidence and Environmental Risk**:
   - High rainfall and chronic road vulnerability predict elevated risk; they do **not** prove current road inundation.
   - Street inundation requires authentic ground evidence (verified citizen report, CCTV vantage, or responder inspection).
2. **Non-Silent Missingness**:
   - Missing rainfall is **never** interpreted as zero rainfall.
   - Absence of citizen reports is **never** treated as evidence that a road is safe.
3. **Contradictory Evidence Preservation**:
   - When evidence sources conflict, the system does not average or vote blindly. It surfaces an `INCONCLUSIVE` evidence status with reason `CONTRADICTORY_OBSERVATIONS_DETECTED` and requests human verification.
4. **Emergency Escalation Policy**:
   - `EMERGENCY` alerts are strictly reserved for verified severe inundation ($> 50\text{ cm}$ standing water) corroborated by field inspection or critical rainfall. Autonomous road closures remain prohibited.

---

## 2. Decision Logic Matrix

| Case ID | Vision Evidence | Rainfall Category | Vulnerability Category | Citizen / Ground Reports | Evidence Status | Alert Level | Decision Status | Crew Actionable? |
| :---: | :--- | :--- | :--- | :--- | :--- | :---: | :---: | :---: |
| **D-01** | None | `LOW` | `LOW` | None | `NO_CURRENT_EVIDENCE_AVAILABLE` | `CLEAR` | `EVALUATED` | No |
| **D-02** | None | `HIGH` / `CRITICAL` | `HIGH` / `SEVERE` | None | `ELEVATED_ENVIRONMENTAL_RISK` | `WATCH` | `EVALUATED` | Yes |
| **D-03** | None | `MEDIUM` | `MODERATE` | None | `ELEVATED_ENVIRONMENTAL_RISK` | `ADVISORY` | `EVALUATED` | No |
| **D-04** | None | `LOW` | Any | 1 Unverified Report | `INCONCLUSIVE` | `ADVISORY` | `EVALUATED` | No (Verify) |
| **D-05** | None | `LOW` | Any | 3+ Corroborated Reports | `OBSERVED_FLOOD_EVIDENCE` | `WATCH` | `EVALUATED` | Yes |
| **D-06** | Fresh `flooded` ($\ge 0.70$) | `LOW` / `MEDIUM` | Any | Any | `OBSERVED_FLOOD_EVIDENCE` | `WARNING` | `EVALUATED` | Yes |
| **D-07** | Fresh `flooded` ($\ge 0.70$) | `HIGH` / `CRITICAL` | Any | Verified Responder | `OBSERVED_FLOOD_EVIDENCE` | `EMERGENCY` | `EVALUATED` | Yes |
| **D-08** | Stale / Ambiguous Vision | Any | Any | Any unverified | `INCONCLUSIVE` | `ADVISORY` | `EVALUATED` | No (Verify) |
| **D-09** | Fresh `not_flooded` ($\ge 0.80$) | Any | Any | Fresh Report claiming flood | `INCONCLUSIVE` | `ADVISORY` | `INCONCLUSIVE_CONTRADICTORY` | No (Verify) |
| **D-10** | None | `UNKNOWN` (Missing) | Any | None | `INSUFFICIENT_OR_STALE_DATA` | `ADVISORY` | `INSUFFICIENT_DATA` | No (Verify) |
| **D-11** | None | Any Stale ($> 180\text{m}$) | Any | None | `INSUFFICIENT_OR_STALE_DATA` | `ADVISORY` | `STALE_DATA` | No (Verify) |
| **D-12** | Any | Any | `SEVERE` Hotspot | None | `ELEVATED_ENVIRONMENTAL_RISK` | `ADVISORY` | `EVALUATED` | No |

---

## 3. Dynamic Confidence Calibration

Confidence $\text{Conf} \in [0.10, 1.00]$ is computed dynamically from component weights:

$$\text{Conf} = \text{Base} - \text{Penalty}_{\text{dist}} - \text{Penalty}_{\text{fresh}} - \text{Penalty}_{\text{missing}} - \text{Penalty}_{\text{conflict}}$$

1. **Base Confidence**:
   - Verified field responder report or verified clear CCTV: $\text{Base} = 0.95$.
   - Valid fresh telemetry + fresh unverified community report: $\text{Base} = 0.75$.
   - Telemetry-only environmental prediction: $\text{Base} = 0.65$.
2. **Penalties**:
   - Station distance: $-0.01$ per km beyond $15\text{ km}$ (max $-0.35$).
   - Data staleness: $-0.08$ per hour beyond $1.5\text{ hours}$ (max $-0.40$).
   - Missing rolling windows: $-0.08$ per missing window.
   - Contradictory evidence: $-0.30$.
   - Floor: $\text{Conf} \ge 0.10$.
