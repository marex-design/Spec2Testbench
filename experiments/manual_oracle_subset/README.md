# Independent manual oracle subset

This directory provides a small independent reference subset for the scientific evaluation. It is intentionally restricted to the p10 low-pass and p11 high-pass first-order RC circuits, plus one controlled non-compliant mutation for each circuit.

The `.ckt` decks are manually authored reference decks and are not produced by Spec2Testbench. The expected cutoff is computed independently from `fc = 1/(2*pi*R*C)`. The verdict is then obtained from the frozen requirement `1 Hz <= fc <= 1e9 Hz`.

This subset is an oracle, not a replacement for the ACP-28 campaign. It provides an auditable reference for checking false accepts and false rejects without circularly reusing the framework verdict.
