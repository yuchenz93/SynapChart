"""Generate three synthetic theta-phase-precession tutorial datasets.

Run from anywhere inside the project::

    python scripts/generate_phase_precession_data.py [--out-dir PATH]

Outputs three dataset sets in ``out-dir`` (default: ``scripts/``):

    phase_precession_1_lfp.npy        shape (N, 1)  – theta LFP, 1250 Hz
    phase_precession_1_spikes.npy     shape (M,)    – spike timestamps (s)
    phase_precession_1_position.npy   shape (T, 3)  – [time_s, x_cm, y_cm]

    … (same for _2_ and _3_)

Phase-precession property
-------------------------
Spikes fired while the animal is inside the place field show a clear
negative linear relationship between their theta phase and the animal's
normalised position within the field:

    phase ≈ 360° at field entry  (normalised position = 0)
    phase ≈   0° at field exit   (normalised position = 1)

The full precession slope spans one complete theta cycle (360° peak-to-peak).
Noise is added via a von Mises distribution (concentration κ): larger κ
gives tighter phase clustering and a cleaner scatter plot.  The three
datasets share the same core mechanism but differ in field width, peak
firing rate, and noise level so they produce visibly distinct scatter
plots while all exhibiting robust precession.

File format notes (compatible with the SynapChart theta-precession template)
-----------------------------------------------------------------------------
*_lfp.npy        float32 (N, 1)   single LFP channel; load_npy → select_reference_channel
*_spikes.npy     float64 (M,)     spike timestamps in seconds; load_spike_times
*_position.npy   float64 (T, 3)   columns [time_s, x_cm, y_cm]; load_position
                                   y_cm = 0 (1-D track); linearize_position will
                                   treat x as the single spatial dimension
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

# ── Shared simulation parameters ──────────────────────────────────────────────

SR_LFP    = 1250      # Hz  – LFP sampling rate
SR_POS    =   30      # Hz  – position sampling rate
DURATION  =  120.0    # s   – recording duration
THETA_HZ  =    8.0    # Hz  – theta oscillation frequency
TRACK_CM  =  100.0    # cm  – linear track length
RUN_SPEED =   20.0    # cm/s – mean running speed (sinusoidal trajectory)

# ── Per-dataset profiles ───────────────────────────────────────────────────────
#
# Tuple fields:
#   label           – used in output filenames
#   field_centre_cm – Gaussian place-field centre (cm)
#   field_sigma_cm  – Gaussian place-field half-width σ (cm)
#   peak_rate_hz    – peak firing rate at field centre (Hz)
#   kappa           – von Mises concentration (phase noise control)
#                     high κ → tight phase coupling → less scatter
#   lfp_noise_std   – additive LFP noise standard deviation
#   seed            – RNG seed for reproducibility
#
DATASET_PROFILES = [
    # label  centre  sigma  peak_hz  kappa  lfp_noise  seed
    ("1",     40,     15,    12.0,    5.0,    0.12,    101),  # clean, tight precession
    ("2",     55,     18,    10.0,    3.0,    0.20,    202),  # wider field, more noise
    ("3",     50,     13,    15.0,    2.0,    0.30,    303),  # narrow field, most noise
]


# ── Helper ────────────────────────────────────────────────────────────────────

def _bessel_i0_approx(x: np.ndarray | float) -> np.ndarray | float:
    """Modified Bessel function I0 via NumPy (exact for real arguments)."""
    return np.i0(x)


# ── Main data-generation routine ──────────────────────────────────────────────

def generate_dataset(
    out_dir: Path,
    label: str,
    field_centre_cm: float,
    field_sigma_cm: float,
    peak_rate_hz: float,
    kappa: float,
    lfp_noise_std: float,
    seed: int,
) -> None:
    """Generate one phase-precession tutorial dataset.

    Parameters
    ----------
    out_dir:
        Directory in which the three .npy files are written.
    label:
        Dataset label (``"1"``, ``"2"``, ``"3"``); becomes part of filename.
    field_centre_cm:
        Centre of the Gaussian place field on the 0–100 cm track.
    field_sigma_cm:
        Standard deviation of the Gaussian place field (cm).
    peak_rate_hz:
        Peak instantaneous firing rate at the field centre (Hz).
    kappa:
        Von Mises concentration controlling phase noise.
        Higher → tighter spike-phase clustering → cleaner precession.
    lfp_noise_std:
        Standard deviation of Gaussian noise added to the LFP.
    seed:
        NumPy RNG seed for reproducibility.
    """
    rng    = np.random.default_rng(seed)
    prefix = out_dir / f"phase_precession_{label}"

    n_lfp = int(DURATION * SR_LFP)
    n_pos = int(DURATION * SR_POS)
    t_lfp = np.arange(n_lfp) / SR_LFP          # (N,)
    t_pos = np.arange(n_pos) / SR_POS           # (T,)

    # ── 1. Position trajectory ────────────────────────────────────────────────
    # Sinusoidal back-and-forth on a 1-D linear track.
    # Period = 2 × track / speed; position ranges smoothly from 0 to 100 cm.
    run_period = 2.0 * TRACK_CM / RUN_SPEED     # seconds per round-trip
    x_pos = TRACK_CM / 2.0 * (1.0 - np.cos(2.0 * np.pi * t_pos / run_period))

    # Small positional jitter (sensor noise / smoothing residuals)
    x_pos = x_pos + rng.normal(0.0, 0.3, n_pos)
    x_pos = np.clip(x_pos, 0.0, TRACK_CM)

    y_pos = np.zeros(n_pos)                     # 1-D track; y is always 0

    position = np.column_stack([t_pos, x_pos, y_pos])   # (T, 3)
    np.save(str(prefix) + "_position.npy", position)

    # ── 2. LFP (single-channel theta oscillation) ─────────────────────────────
    # phi_lfp(t) = 2π·f_θ·t  (unwrapped, monotonically increasing)
    # Wrapped phase in [0, 2π):  phi_lfp % (2π)
    # sin(phi_lfp) = 0 at t=0 (ascending zero-crossing) → rising edge = 0°.
    phi_lfp = 2.0 * np.pi * THETA_HZ * t_lfp   # (N,)  unwrapped
    lfp     = np.sin(phi_lfp)
    lfp     = lfp + rng.normal(0.0, lfp_noise_std, n_lfp)
    lfp     = lfp.reshape(-1, 1).astype(np.float32)   # (N, 1)  channel axis
    np.save(str(prefix) + "_lfp.npy", lfp)

    # ── 3. Spikes ─────────────────────────────────────────────────────────────
    # Interpolate position to LFP timebase for sample-accurate computation.
    x_at_lfp = np.interp(t_lfp, t_pos, x_pos)  # (N,)

    # 3a. Place-field firing-rate envelope (Gaussian, plus small baseline).
    place_rate = peak_rate_hz * np.exp(
        -0.5 * ((x_at_lfp - field_centre_cm) / field_sigma_cm) ** 2
    )
    baseline_rate = 0.03   # Hz – minimal background spiking outside the field
    inst_rate_base = place_rate + baseline_rate

    # 3b. Phase precession via von Mises modulation.
    #
    # The preferred spike phase decreases linearly with the animal's normalised
    # position within the field (u ∈ [0, 1]):
    #
    #   φ_pref(u) = 2π·(1 − u)      [radians]
    #             = 360° · (1 − u)   [degrees]
    #
    # At field entry  (u = 0): φ_pref = 2π  ≡ 360°  (late in theta cycle)
    # At field center (u = 0.5): φ_pref = π ≡ 180°
    # At field exit   (u = 1): φ_pref = 0°           (early in theta cycle)
    #
    # This yields a negative slope of −360° across the field (one full theta
    # cycle), matching the classic phase-precession observation.
    #
    # Normalised position is measured relative to the ±2σ field boundaries.
    field_lo = field_centre_cm - 2.0 * field_sigma_cm
    field_hi = field_centre_cm + 2.0 * field_sigma_cm
    u = np.clip(
        (x_at_lfp - field_lo) / (field_hi - field_lo),
        0.0, 1.0,
    )                                           # (N,)  in [0, 1]

    phi_pref = 2.0 * np.pi * (1.0 - u)        # (N,)  decreases from 2π to 0

    # Von Mises probability density, normalised to have mean = 1 over a cycle.
    #   p(φ | φ_pref, κ) ∝ exp(κ · cos(φ − φ_pref))
    #   Mean over uniform φ = I₀(κ), so divide to get mean = 1.
    phi_wrapped = phi_lfp % (2.0 * np.pi)      # current LFP phase in [0, 2π)
    phase_mod   = (
        np.exp(kappa * np.cos(phi_wrapped - phi_pref))
        / _bessel_i0_approx(kappa)
    )                                           # (N,)  mean ≈ 1 over a cycle

    # Instantaneous rate at each LFP sample (Hz), clipped for numerical safety.
    inst_rate = inst_rate_base * phase_mod      # Hz

    # Sample spikes via Bernoulli process.
    dt         = 1.0 / SR_LFP
    spike_prob = np.clip(inst_rate * dt, 0.0, 1.0)
    spike_mask = rng.uniform(size=n_lfp) < spike_prob
    spike_times = t_lfp[spike_mask].copy()     # (M,)  seconds
    np.save(str(prefix) + "_spikes.npy", spike_times)

    # ── 4. Verification summary ───────────────────────────────────────────────
    # Compute the Pearson correlation between normalised position and theta
    # phase for spikes that fell within the place field boundaries.
    x_at_spike   = np.interp(spike_times, t_pos, x_pos)
    in_field_mask = (x_at_spike >= field_lo) & (x_at_spike <= field_hi)
    n_in_field    = in_field_mask.sum()

    if n_in_field > 10:
        u_spike       = (x_at_spike[in_field_mask] - field_lo) / (field_hi - field_lo)
        phi_at_spike  = (2.0 * np.pi * THETA_HZ * spike_times[in_field_mask]) % (2.0 * np.pi)
        phase_deg     = np.degrees(phi_at_spike)
        pearson_r     = float(np.corrcoef(u_spike, phase_deg)[0, 1])
        corr_str      = f"r = {pearson_r:+.3f}"
    else:
        corr_str      = "r = n/a (too few in-field spikes)"

    n_passes = int(DURATION / (2.0 * TRACK_CM / RUN_SPEED))   # approx round-trips
    print(
        f"  Dataset {label}: "
        f"centre={field_centre_cm} cm  sigma={field_sigma_cm} cm  "
        f"peak={peak_rate_hz} Hz  kappa={kappa}  "
        f"n_spikes={len(spike_times)}  in-field={n_in_field}  "
        f"~{n_passes} passes  {corr_str}"
    )
    print(
        f"    {prefix.name}_lfp.npy      {lfp.shape}  float32\n"
        f"    {prefix.name}_spikes.npy   ({len(spike_times)},)  float64\n"
        f"    {prefix.name}_position.npy {position.shape}  float64"
    )


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate synthetic phase-precession tutorial datasets.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--out-dir",
        default=str(Path(__file__).parent),
        help="Directory in which to write .npy files (default: scripts/).",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(
        f"Generating {len(DATASET_PROFILES)} phase-precession datasets"
        f" -> {out_dir}/\n"
        f"  LFP:      {SR_LFP} Hz, {DURATION:.0f} s, single channel\n"
        f"  Theta:    {THETA_HZ} Hz\n"
        f"  Track:    0 - {TRACK_CM:.0f} cm (1-D), speed ~{RUN_SPEED} cm/s\n"
        f"  Precession slope: -360 deg across each place field\n"
    )

    for profile in DATASET_PROFILES:
        label, centre, sigma, peak_hz, kappa, lfp_noise, seed = profile
        generate_dataset(
            out_dir=out_dir,
            label=label,
            field_centre_cm=centre,
            field_sigma_cm=sigma,
            peak_rate_hz=peak_hz,
            kappa=kappa,
            lfp_noise_std=lfp_noise,
            seed=seed,
        )
        print()

    print(
        "Done.\n\n"
        "Load each dataset in the SynapChart theta-precession template:\n"
        "  load_npy         <- phase_precession_N_lfp.npy\n"
        "  load_spike_times <- phase_precession_N_spikes.npy\n"
        "  load_position    <- phase_precession_N_position.npy\n\n"
        "Expected output:\n"
        "  - Place-field tuning curve  (Gaussian peak)\n"
        "  - Phase-precession scatter  (negative slope, ~-360 deg across field)\n"
        "  - Bayesian decoded posterior (theta-sequence structure)\n"
    )


if __name__ == "__main__":
    main()
