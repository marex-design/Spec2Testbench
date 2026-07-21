# Trial Cache Audit

Date: 2026-07-21

- Trials audited: 48
- Distinct cache keys: 48
- Cache contamination rows: 0
- Stub determinism: PASS
- Scientific LLM evidence on stub rows: false

Interpretation:

- Trial cache keys remain trial-specific because `trial_id` is part of the cache digest.
- The current provider is stub-backed, so repeated hashes reflect stub determinism and not live-LLM stability.
