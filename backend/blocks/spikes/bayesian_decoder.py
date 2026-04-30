"""Memoryless Bayesian position decoder."""


from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


class BayesianDecoder(BlockBase):
    """Memoryless Bayesian position decoder.

    For each time bin, computes the posterior probability over position bins
    given observed spike counts and tuning curves using the formula::

        P(x | n) ∝ P(x) × ∏_i [ f_i(x)^n_i × exp(-τ × f_i(x)) ]

    Computed in log space to avoid numerical underflow. Each time-bin column
    of the posterior is normalised to sum to 1.
    """

    block_type_id = "bayesian_decoder"
    display_name = "Bayesian Decoder"
    category = "Spikes"
    description = (
        "Memoryless Bayesian position decoder. Reconstructs position "
        "from binned spike counts and tuning curves."
    )

    inputs = [
        PortDefinition(
            "spike_matrix",
            "NeuroData[spike_matrix]",
            "Binned spike counts, shape (n_units × n_time_bins).",
        ),
        PortDefinition(
            "tuning_curves",
            "NeuroData[tuning_curve]",
            "Firing-rate tuning curves, shape (n_units × n_position_bins) "
            "or (n_position_bins,) for a single unit.",
        ),
    ]
    outputs = [
        PortDefinition(
            "decoded",
            "NeuroData[decoded]",
            "Posterior probability matrix, shape (n_position_bins × n_time_bins).",
        ),
    ]
    parameters = [
        ParameterDefinition(
            "bin_size_sec",
            "float",
            0.02,
            "Time bin duration in seconds. Must match the bin_spikes block.",
        ),
        ParameterDefinition(
            "prior",
            "enum:uniform,empirical",
            "uniform",
            "Spatial prior: uniform (flat) or empirical (proportional to occupancy, v2).",
        ),
    ]

    def run(self, inputs: dict[str, NeuroData], parameters: dict[str, Any]) -> dict:
        spike_nd: NeuroData = inputs["spike_matrix"]
        tc_nd: NeuroData = inputs["tuning_curves"]

        tau = float(parameters.get("bin_size_sec", 0.02))
        prior_type = str(parameters.get("prior", "uniform"))

        # --- Normalise shapes to 2-D ---
        spk = spike_nd.array  # target: (n_units, n_time_bins)
        if spk.ndim == 1:
            spk = spk.reshape(1, -1)

        tc = tc_nd.array      # target: (n_units, n_pos_bins)
        if tc.ndim == 1:
            tc = tc.reshape(1, -1)

        n_units_spk, n_time_bins = spk.shape
        n_units_tc, n_pos_bins = tc.shape

        if n_units_spk != n_units_tc:
            raise ValueError(
                f"Unit count mismatch: spike_matrix has {n_units_spk} unit(s) "
                f"but tuning_curves has {n_units_tc} unit(s)."
            )

        # --- Log prior ---
        if prior_type == "uniform":
            log_prior = np.zeros(n_pos_bins)  # log(1/N) up to constant
        else:
            # empirical prior: v2 feature; fall back to uniform
            log_prior = np.zeros(n_pos_bins)

        # --- Vectorised log-posterior ---
        # log P(x | n_t) = log_prior
        #   + Σ_i [ n_i(t) * log(f_i(x))  -  τ * f_i(x) ]
        #
        # term1 (n_time_bins, n_pos_bins) = spk.T @ log_tc
        # term2 (n_pos_bins,)             = τ * Σ_i f_i(x)
        eps = 1e-10
        log_tc = np.log(np.maximum(tc, eps))  # (n_units, n_pos_bins)

        term1 = spk.T @ log_tc                       # (n_time_bins, n_pos_bins)
        term2 = tau * tc.sum(axis=0)                 # (n_pos_bins,)
        log_post = term1 - term2 + log_prior         # (n_time_bins, n_pos_bins)

        # Numerically stable softmax-style normalisation per time bin
        log_post -= log_post.max(axis=1, keepdims=True)
        posterior_T = np.exp(log_post)               # (n_time_bins, n_pos_bins)

        col_sums = posterior_T.sum(axis=1, keepdims=True)
        col_sums = np.where(col_sums > 0, col_sums, 1.0)
        posterior_T /= col_sums

        posterior = posterior_T.T                    # (n_pos_bins, n_time_bins)

        return {
            "decoded": NeuroData(
                data_type="decoded",
                array=posterior,
                timestamps=spike_nd.timestamps,   # bin-centre times from bin_spikes
                metadata={
                    "n_units": int(n_units_spk),
                    "n_pos_bins": int(n_pos_bins),
                    "n_time_bins": int(n_time_bins),
                    "bin_size_sec": tau,
                    "prior": prior_type,
                },
            )
        }
