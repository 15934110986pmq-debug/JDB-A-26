"""Kalman filter + RTS smoother fusion for Q2.

State: s = (x, y, vx, vy)^T  with constant-velocity model.

Discrete-time model with variable Δt between observations:

    s_{k+1} = F(Δt) s_k + w_k,  w_k ~ N(0, Q(Δt))
    z_k     = H s_k + v_k,      v_k ~ N(0, R_k)

    F(Δt) = [[1, 0, Δt, 0],
             [0, 1, 0, Δt],
             [0, 0, 1, 0],
             [0, 0, 0, 1]]
    H     = [[1, 0, 0, 0],
             [0, 1, 0, 0]]

    Process noise from continuous white-acceleration σ_a (Bar-Shalom 2001 §6.3.2):
    Q(Δt) = σ_a^2 * [[Δt^4/4,   0,        Δt^3/2,  0],
                     [0,        Δt^4/4,   0,       Δt^3/2],
                     [Δt^3/2,   0,        Δt^2,    0],
                     [0,        Δt^3/2,   0,       Δt^2]]

Observations come from both methods after time/space alignment:
    method 1 sample at t1_i  ->  z = (x1_i, y1_i),                       R = σ1^2 I
    method 2 sample at t2_j  ->  z = (x2_j + Δx, y2_j + Δy),            R = σ2^2 I,
                                  with physical timestamp = t2_j + Δt
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def F_matrix(dt: float) -> np.ndarray:
    F = np.eye(4)
    F[0, 2] = dt
    F[1, 3] = dt
    return F


def Q_matrix(dt: float, sigma_a: float) -> np.ndarray:
    s2 = sigma_a ** 2
    dt2 = dt ** 2
    dt3 = dt ** 3
    dt4 = dt ** 4
    return s2 * np.array([
        [dt4 / 4, 0,       dt3 / 2, 0      ],
        [0,       dt4 / 4, 0,       dt3 / 2],
        [dt3 / 2, 0,       dt2,     0      ],
        [0,       dt3 / 2, 0,       dt2    ],
    ])


H = np.array([[1.0, 0.0, 0.0, 0.0],
              [0.0, 1.0, 0.0, 0.0]])


def collect_observations(s1: pd.DataFrame, s2: pd.DataFrame,
                         dt_hat: float, dx_hat: float, dy_hat: float,
                         sigma_1: float, sigma_2: float):
    """Return list of (t_phys, z, R, source) sorted by t_phys."""
    obs = []
    for _, r in s1.iterrows():
        obs.append((float(r["t"]), np.array([r["x"], r["y"]]), sigma_1 ** 2, 1))
    for _, r in s2.iterrows():
        obs.append((float(r["t"]) + dt_hat,
                    np.array([r["x"] + dx_hat, r["y"] + dy_hat]),
                    sigma_2 ** 2, 2))
    obs.sort(key=lambda x: x[0])
    return obs


def kf_forward(obs, sigma_a: float):
    """Standard discrete-time KF forward pass with variable Δt."""
    n = len(obs)
    states = np.zeros((n, 4))
    covs = np.zeros((n, 4, 4))
    pred_states = np.zeros((n, 4))
    pred_covs = np.zeros((n, 4, 4))
    nis = np.zeros(n)

    # Initial state: position from first obs, velocity = 0
    t0, z0, R0, _ = obs[0]
    s = np.array([z0[0], z0[1], 0.0, 0.0])
    P = np.diag([R0, R0, 1.0, 1.0])  # large vel uncertainty
    states[0] = s; covs[0] = P
    pred_states[0] = s; pred_covs[0] = P

    for i in range(1, n):
        ti, zi, Ri, _ = obs[i]
        dt = ti - obs[i - 1][0]
        if dt <= 0:
            dt = 1e-9
        # Predict
        F = F_matrix(dt)
        Q = Q_matrix(dt, sigma_a)
        s_pred = F @ s
        P_pred = F @ P @ F.T + Q
        pred_states[i] = s_pred; pred_covs[i] = P_pred
        # Update
        S = H @ P_pred @ H.T + Ri * np.eye(2)
        K = P_pred @ H.T @ np.linalg.inv(S)
        innov = zi - H @ s_pred
        s = s_pred + K @ innov
        P = (np.eye(4) - K @ H) @ P_pred
        # Symmetrize numerically
        P = 0.5 * (P + P.T)
        nis[i] = float(innov @ np.linalg.solve(S, innov))
        states[i] = s; covs[i] = P

    return states, covs, pred_states, pred_covs, nis


def rts_backward(states, covs, pred_states, pred_covs, obs, sigma_a: float):
    """Rauch-Tung-Striebel smoother backward pass."""
    n = len(states)
    sm_states = np.zeros_like(states)
    sm_covs = np.zeros_like(covs)
    sm_states[-1] = states[-1]
    sm_covs[-1] = covs[-1]
    for i in range(n - 2, -1, -1):
        dt = obs[i + 1][0] - obs[i][0]
        if dt <= 0:
            dt = 1e-9
        F = F_matrix(dt)
        # Smoother gain (uses predicted cov of step i+1 = P_{i+1|i} stored as pred_covs[i+1])
        try:
            G = covs[i] @ F.T @ np.linalg.inv(pred_covs[i + 1])
        except np.linalg.LinAlgError:
            G = covs[i] @ F.T @ np.linalg.pinv(pred_covs[i + 1])
        sm_states[i] = states[i] + G @ (sm_states[i + 1] - pred_states[i + 1])
        sm_covs[i] = covs[i] + G @ (sm_covs[i + 1] - pred_covs[i + 1]) @ G.T
        sm_covs[i] = 0.5 * (sm_covs[i] + sm_covs[i].T)
    return sm_states, sm_covs


def fuse_kf_rts(s1: pd.DataFrame, s2: pd.DataFrame,
                dt_hat: float, dx_hat: float, dy_hat: float,
                sigma_1: float, sigma_2: float,
                sigma_a: float = 0.5):
    """Returns observation timestamps + smoothed (x, y, vx, vy) + cov."""
    obs = collect_observations(s1, s2, dt_hat, dx_hat, dy_hat, sigma_1, sigma_2)
    states, covs, pred_states, pred_covs, nis = kf_forward(obs, sigma_a)
    sm_states, sm_covs = rts_backward(states, covs, pred_states, pred_covs, obs, sigma_a)
    times = np.array([o[0] for o in obs])
    return times, sm_states, sm_covs, states, covs, nis


def resample_to_10hz(times, states, covs):
    """Linear interpolation to 0.1 s grid."""
    t_lo = float(np.ceil(times.min() * 10) / 10)
    t_hi = float(np.floor(times.max() * 10) / 10)
    grid = np.arange(t_lo, t_hi + 1e-9, 0.1)
    x = np.interp(grid, times, states[:, 0])
    y = np.interp(grid, times, states[:, 1])
    vx = np.interp(grid, times, states[:, 2])
    vy = np.interp(grid, times, states[:, 3])
    # Cov: interpolate diagonal only, conservative
    var_x = np.interp(grid, times, covs[:, 0, 0])
    var_y = np.interp(grid, times, covs[:, 1, 1])
    return grid, x, y, vx, vy, var_x, var_y
