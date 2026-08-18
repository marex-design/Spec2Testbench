# FIX4 — Scientific deterministic baseline decisions

Date: 2026-08-18

This reconstruction intentionally does **not** force the historical global verdict counts.
It preserves evidence produced by ngspice-42 under the immutable-DUT protocol.

## MOS OP-bias evidence

The FIX3 probe writes one `wrdata` file per MOS and aggregates
`minimum_device_drain_current_a = min(abs(Id))`.
For p16, p18, p20 and p21 the reconstructed decks produce currents above 10 uA.
Those criteria therefore remain PASS. The historical picoampere FAIL values are treated
as non-reproduced artifacts of the former extraction/deck path, not as ground truth.

## p22 oscillator

The pinned AnalogCoder-Pro checker applies initial conditions of 2.51 V and 2.5 V to
the first two op-amp pins. In p22 those nodes are Vref and Vinn. FIX4 carries the same
startup seed as `.IC` in the generated deterministic deck. This changes the verification
protocol only; DUT topology and component values remain immutable.

## p24 integrator

The upstream checker rewrites Cf to 3 uF. The submitted DUT contains R1=10 kOhm and
Cf=100 nF. Under an immutable-DUT protocol, the expected ramp magnitude is:

    0.5 / (10k * 100n) = 500 V/s

The upstream ±30% tolerance is retained, giving 350..650 V/s.

## p25 differentiator

The upstream checker rewrites C1 to 3 uF. The submitted DUT contains Rf=10 kOhm and
C1=10 nF. The triangular stimulus has |dVin/dt| = 20 V/s, so the expected magnitude is:

    Rf * C1 * |dVin/dt| = 10k * 10n * 20 = 0.002 V

The upstream ±20% tolerance is retained, giving 1.6..2.4 mV.
The square-wave-shape criterion remains NOT_IMPLEMENTED, so p25 cannot become fully
COMPLIANT solely from this amplitude criterion.
