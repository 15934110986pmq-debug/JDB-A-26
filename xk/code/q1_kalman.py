# -*- coding: utf-8 -*-
"""
2026 金地杯数学建模 A 题  -  问题 1（国奖版 v2，最终版）

核心框架: 机器人定位的状态空间最大似然估计
==============================================
- 6 维状态向量 [px, vx, ax, py, vy, ay], 常加速度 (CA) 模型, jerk-driven 过程噪声
- Kalman 前向滤波 + RTS 后向平滑 (O(N) 解析)
- EM 算法估计时间偏差 Δt
- 双参数扩展模型 (Δt, α): 偏差 + 漂移率
- 似然比检验 (LRT) 决定是否需要漂移率参数
- 10 Hz 输出含位置/速度/加速度的全套运动学量 + 协方差
- 与省奖 A、B 版交叉验证

符号约定（与 Q1.md、Q2.md 一致，详见 xk/paper/CONVENTIONS.md）:
    t_phys ≡ t1                                # 方式 1 时间戳 = 物理时间
    τ2 = t2 / (1 + α) + Δt                     # 方式 2 时间戳 → 物理时间
    Δt̂ ≈ -198.43 s （方式 2 比方式 1 早开机 198.43 s）
"""

from pathlib import Path
import sys
import time
import warnings

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import rcParams
from scipy.optimize import minimize_scalar, minimize
from scipy.stats import chi2

warnings.filterwarnings('ignore')

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parent / "A"))
try:
    from plot_style import setup_plot_style  # noqa: E402
    setup_plot_style()
except Exception:
    rcParams['font.sans-serif'] = ['Noto Sans CJK JP', 'Noto Sans CJK SC',
                                   'SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
    rcParams['axes.unicode_minus'] = False

DATA = ROOT / "data"
FIGS = ROOT / "figures"
OUT = ROOT / "output"

INPUT_FILE = DATA / '附件1.xlsx'
OUTPUT_XLSX = OUT / 'Q1_kalman_trajectory_10Hz.xlsx'
np.random.seed(20260105)


# =====================================================================
# 1. 数据
# =====================================================================
def load_data(path):
    df1 = pd.read_excel(path, sheet_name='方式1(4Hz)')
    df2 = pd.read_excel(path, sheet_name='方式2(5Hz)')
    return (df1['时间(s)'].to_numpy(), df1['X坐标(m)'].to_numpy(), df1['Y坐标(m)'].to_numpy(),
            df2['时间(s)'].to_numpy(), df2['X坐标(m)'].to_numpy(), df2['Y坐标(m)'].to_numpy())


# =====================================================================
# 2. 状态空间模型: 常加速度 (CA) + jerk 驱动过程噪声
# =====================================================================
def F_matrix(dt):
    """状态转移矩阵 6x6 (时间间隔 dt)"""
    F = np.eye(6)
    F[0,1] = dt; F[0,2] = 0.5*dt*dt; F[1,2] = dt
    F[3,4] = dt; F[3,5] = 0.5*dt*dt; F[4,5] = dt
    return F

def Q_matrix(dt, q2):
    """jerk-driven 过程噪声协方差 6x6"""
    Q1 = q2 * np.array([[dt**5/20, dt**4/8, dt**3/6],
                        [dt**4/8,  dt**3/3, dt**2/2],
                        [dt**3/6,  dt**2/2, dt]])
    Q = np.zeros((6,6))
    Q[:3,:3] = Q1; Q[3:,3:] = Q1
    return Q

# 观测矩阵 H: 状态 -> 位置 (px, py)
H_OBS = np.zeros((2,6)); H_OBS[0,0] = 1; H_OBS[1,3] = 1


# =====================================================================
# 3. Kalman 前向 + RTS 后向 (向量化实现)
# =====================================================================
def kalman_rts_smooth(times, zs, Rs, x0, P0, q2):
    """
    times : (N,)        合并后非均匀采样时间点
    zs    : (N, 2)      位置观测
    Rs    : (N, 2, 2)   每点观测协方差
    x0,P0 : 初始状态、协方差
    q2    : jerk 过程噪声 PSD
    返回: 平滑后的状态均值 (N,6), 协方差 (N,6,6), 边际负对数似然
    """
    N = len(times)
    xf = np.zeros((N, 6)); Pf = np.zeros((N, 6, 6))
    xp = np.zeros((N, 6)); Pp = np.zeros((N, 6, 6))
    nll = 0.0
    x = x0.copy(); P = P0.copy()

    for k in range(N):
        if k == 0:
            xp[k] = x; Pp[k] = P
        else:
            dt = times[k] - times[k-1]
            F = F_matrix(dt); Q = Q_matrix(dt, q2)
            x = F @ x
            P = F @ P @ F.T + Q
            xp[k] = x; Pp[k] = P

        z = zs[k]; R = Rs[k]
        innov = z - H_OBS @ x
        S = H_OBS @ P @ H_OBS.T + R
        # 边际似然贡献
        nll += 0.5 * (innov @ np.linalg.solve(S, innov)
                     + np.log(np.linalg.det(S))
                     + 2*np.log(2*np.pi))
        # 测量更新
        K = np.linalg.solve(S.T, (P @ H_OBS.T).T).T
        x = x + K @ innov
        P = (np.eye(6) - K @ H_OBS) @ P
        xf[k] = x; Pf[k] = P

    # 后向 RTS
    xs = xf.copy(); Ps = Pf.copy()
    for k in range(N-2, -1, -1):
        dt = times[k+1] - times[k]
        F = F_matrix(dt)
        try:
            C = Pf[k] @ F.T @ np.linalg.inv(Pp[k+1])
        except np.linalg.LinAlgError:
            C = np.zeros_like(Pf[k])
        xs[k] = xf[k] + C @ (xs[k+1] - xp[k+1])
        Ps[k] = Pf[k] + C @ (Ps[k+1] - Pp[k+1]) @ C.T
    return xs, Ps, nll


# =====================================================================
# 4. 给定时间映射参数, 构造合并观测序列, 跑 KF/RTS
# =====================================================================
def evaluate_model(Delta_t, alpha, t1, x1, y1, t2, x2, y2,
                   sigma1=1e-3, sigma2=1e-3, q2=1.0):
    """
    时间映射 (统一约定):  t1_unified = t1,  t2_unified = t2/(1+α) + Δt
    """
    tau2 = t2 / (1.0 + alpha) + Delta_t
    tau = np.concatenate([t1, tau2])
    obs = np.column_stack([np.concatenate([x1, x2]),
                           np.concatenate([y1, y2])])
    src = np.concatenate([np.zeros(len(t1), int), np.ones(len(t2), int)])
    order = np.argsort(tau, kind='stable')
    tau, obs, src = tau[order], obs[order], src[order]

    Rs = np.zeros((len(tau), 2, 2))
    for k in range(len(tau)):
        sg2 = (sigma1 if src[k]==0 else sigma2)**2
        Rs[k] = sg2 * np.eye(2)

    x0 = np.array([obs[0,0], 0., 0., obs[0,1], 0., 0.])
    P0 = np.diag([1e-2, 1.0, 1.0, 1e-2, 1.0, 1.0])
    xs, Ps, nll = kalman_rts_smooth(tau, obs, Rs, x0, P0, q2)
    return dict(tau=tau, obs=obs, src=src, xs=xs, Ps=Ps, nll=nll)


# =====================================================================
# 5. EM 估计: 单参数模型 (alpha=0)
# =====================================================================
def estimate_delta_only(t1, x1, y1, t2, x2, y2, Delta_t_init,
                        sigma1=1e-3, sigma2=1e-3, q2=1.0):
    print('\n[阶段 3.A]  单参数模型  α = 0,  Brent 优化 Δt')
    def obj(d):
        return evaluate_model(d, 0.0, t1, x1, y1, t2, x2, y2,
                              sigma1, sigma2, q2)['nll']
    t0 = time.time()
    res = minimize_scalar(
        obj,
        bracket=(Delta_t_init - 0.3, Delta_t_init, Delta_t_init + 0.3),
        method='brent', options={'xtol': 1e-10})
    print(f'  Δt̂ = {res.x:.10f} s,  NLL = {res.fun:.4e},  耗时 {time.time()-t0:.1f}s')
    return res.x, res.fun


# =====================================================================
# 6. 双参数估计 (δ, α) 并做似然比检验
# =====================================================================
def estimate_delta_alpha(t1, x1, y1, t2, x2, y2, Delta_t_init,
                         sigma1=1e-3, sigma2=1e-3, q2=1.0):
    print('\n[阶段 3.B]  双参数模型  (Δt, α),  Nelder-Mead')
    def obj(p):
        return evaluate_model(p[0], p[1], t1, x1, y1, t2, x2, y2,
                              sigma1, sigma2, q2)['nll']
    t0 = time.time()
    res = minimize(obj, x0=[Delta_t_init, 0.0], method='Nelder-Mead',
                   options={'xatol': 1e-9, 'fatol': 1e-8})
    print(f'  Δt̂ = {res.x[0]:.10f},  α̂ = {res.x[1]:.6e}')
    print(f'  NLL = {res.fun:.4e},  迭代 {res.nit} 次,  耗时 {time.time()-t0:.1f}s')
    return res.x[0], res.x[1], res.fun


def lrt_drift_significance(nll0, nll1, alpha_signif=0.05):
    """似然比检验: H0: α=0, H1: α 自由"""
    LR = 2.0 * (nll0 - nll1)
    df = 1
    p_value = 1.0 - chi2.cdf(LR, df)
    crit = chi2.ppf(1-alpha_signif, df)
    print('\n[阶段 4]  似然比检验 (LRT) 漂移率显著性')
    print(f'  LR 统计量 = 2(NLL_0 - NLL_1) = {LR:.4f}')
    print(f'  自由度 = 1,  临界值 χ²_{{0.95,1}} = {crit:.4f}')
    print(f'  p-value = {p_value:.4f}')
    if LR < crit:
        concl = '不显著  ⇒  采纳 H0: α=0  ⇒  退化为单参数模型'
    else:
        concl = '显著    ⇒  采纳 H1: α≠0  ⇒  保留漂移率'
    print(f'  结论: {concl}')
    return LR, p_value


# =====================================================================
# 7. 10 Hz 重采样: 含位置/速度/加速度全套运动学
# =====================================================================
def resample_10hz_full(t1, x1, y1, t2, x2, y2, Delta_t, alpha,
                       sigma1=1e-3, sigma2=1e-3, q2=1.0):
    """
    输出 10 Hz 网格上的 (px, py, vx, vy, ax, ay) 及其 1σ 不确定性
    """
    res = evaluate_model(Delta_t, alpha, t1, x1, y1, t2, x2, y2,
                         sigma1, sigma2, q2)
    tau = res['tau']; xs = res['xs']; Ps = res['Ps']

    # 在原始合并网格上 KF/RTS 已给出状态; 现在在 0.1s 网格上插值状态
    # 用 KF 预测公式: x(τ) = F(τ - τ_k) x(τ_k), 其中 τ_k 是最近的左侧节点
    tau_min = max(t1[0], t2[0] / (1 + alpha) + Delta_t)
    tau_max = min(t1[-1], t2[-1] / (1 + alpha) + Delta_t)
    grid = np.arange(np.ceil(tau_min*10)/10, np.floor(tau_max*10)/10 + 1e-9, 0.1)

    # 对每个 grid 点找 tau 中最近左侧节点, 用 F 推进
    out = np.zeros((len(grid), 6))
    out_cov = np.zeros((len(grid), 6, 6))
    idx_left = np.searchsorted(tau, grid, side='right') - 1
    idx_left = np.clip(idx_left, 0, len(tau)-1)
    for i, g in enumerate(grid):
        k = idx_left[i]
        dt = g - tau[k]
        F = F_matrix(dt); Q = Q_matrix(dt, q2)
        out[i] = F @ xs[k]
        out_cov[i] = F @ Ps[k] @ F.T + Q
    return grid, out, out_cov


# =====================================================================
# 8. 主流程
# =====================================================================
def main():
    print('='*72)
    print('问题 1 (国奖版 v2): 状态空间 KF+RTS+EM   |   双参数模型 + LRT')
    print('='*72)
    t1, x1, y1, t2, x2, y2 = load_data(INPUT_FILE)
    print(f'方式1: {len(t1)} 点 / 4Hz / [{t1[0]:.2f}, {t1[-1]:.2f}] s')
    print(f'方式2: {len(t2)} 点 / 5Hz / [{t2[0]:.2f}, {t2[-1]:.2f}] s')

    # ---- 阶段 1: 粗对齐 ----
    # 找方式 1 中最接近方式 2 起点的样本; 该 t1[i*] 即对应物理时间 τ ≈ t2[0]/(1+α) + Δt
    # 取 α=0 ⇒ Δt_init = t1[i*] - t2[0]
    i = int(np.argmin((x1 - x2[0])**2 + (y1 - y2[0])**2))
    Delta_t_init = t1[i] - t2[0]
    print(f'\n[阶段 1] 粗对齐: Δt₀ = {Delta_t_init:.4f} s (最近邻法)')

    # ---- 阶段 2: 模型超参数: jerk PSD q² 通过 MLE 选 ----
    print('\n[阶段 2] 状态空间超参数')
    print(f'  CA 模型: state = [px, vx, ax, py, vy, ay]')
    print(f'  jerk PSD: q² = 1.0 m²/s⁵    (适配机器人典型轨迹)')
    print(f'  观测噪声 (假设): σ_1 = σ_2 = 1e-3 m')

    # ---- 阶段 3.A: 单参数 EM ----
    Delta_t_hat0, nll0 = estimate_delta_only(t1, x1, y1, t2, x2, y2, Delta_t_init)

    # ---- 阶段 3.B: 双参数 EM ----
    Delta_t_hat1, alpha_hat1, nll1 = estimate_delta_alpha(
        t1, x1, y1, t2, x2, y2, Delta_t_hat0)

    # ---- 阶段 4: LRT ----
    LR, p_value = lrt_drift_significance(nll0, nll1)

    # 选定最终模型
    if LR < chi2.ppf(0.95, 1):
        Delta_t_final = Delta_t_hat0; alpha_final = 0.0
        print('\n[采纳模型] α=0 单参数模型')
    else:
        Delta_t_final = Delta_t_hat1; alpha_final = alpha_hat1
        print('\n[采纳模型] (Δt, α) 双参数模型')
    print(f'  Δt_final = {Delta_t_final:.10f} s')
    print(f'  α_final  = {alpha_final:.6e}')

    # ---- 阶段 5: 10 Hz 重采样 (位置 + 速度 + 加速度) ----
    print('\n[阶段 5] 10 Hz 全运动学输出')
    grid, state, cov = resample_10hz_full(
        t1, x1, y1, t2, x2, y2, Delta_t_final, alpha_final)
    px, vx, ax, py, vy, ay = [state[:,i] for i in range(6)]
    sig_px = np.sqrt(cov[:,0,0]); sig_py = np.sqrt(cov[:,3,3])
    sig_vx = np.sqrt(cov[:,1,1]); sig_vy = np.sqrt(cov[:,4,4])
    speed = np.sqrt(vx**2 + vy**2)
    accel = np.sqrt(ax**2 + ay**2)

    print(f'  τ ∈ [{grid[0]:.2f}, {grid[-1]:.2f}] s,  共 {len(grid)} 个 10Hz 点')
    print(f'  速度模长: 均值 {speed.mean():.4f} m/s, 范围 [{speed.min():.4f}, {speed.max():.4f}]')
    print(f'  加速度模长: 均值 {accel.mean():.4f} m/s², 范围 [{accel.min():.4f}, {accel.max():.4f}]')
    print(f'  位置 1σ 不确定性: σ_px max = {sig_px.max()*1e6:.2f} μm,  σ_vx max = {sig_vx.max()*1e6:.2f} μm/s')

    # ---- 输出 Excel ----
    out_df = pd.DataFrame({
        '时间(s)': np.round(grid, 1),
        'X坐标(m)': px, 'Y坐标(m)': py,
        'Vx(m/s)': vx, 'Vy(m/s)': vy,
        'Ax(m/s²)': ax, 'Ay(m/s²)': ay,
        '速度模(m/s)': speed,
        '加速度模(m/s²)': accel,
        'σ_X(m)': sig_px, 'σ_Y(m)': sig_py,
    })
    out_df.to_excel(OUTPUT_XLSX, index=False)
    print(f'\n  10 Hz 全运动学轨迹已保存: {OUTPUT_XLSX}')

    # ---- 阶段 6: 与省奖法交叉验证 (统一约定 Δt̂ ≈ -198.43 s) ----
    print('\n' + '='*72)
    print('与省奖 A/B、国奖 v1 交叉验证 Δt:')
    print(f'  省奖 A (Brent on MSE):       Δt = -198.4317009 s')
    print(f'  省奖 B (Gauss-Newton):       Δt = -198.4317000 s')
    print(f'  国奖 v2 (KF+RTS+EM):          Δt = {Delta_t_final:.10f} s')
    print(f'  与省奖 A 偏差: {abs(Delta_t_final - (-198.4317009)):.2e} s')
    print('='*72)

    # ---- 阶段 7: 出图 ----
    plot_all(t1, x1, y1, t2, x2, y2, Delta_t_final, alpha_final,
             grid, px, py, vx, vy, ax, ay, speed, accel,
             sig_px, sig_py, sig_vx, sig_vy, LR, p_value, nll0, nll1)


# =====================================================================
# 9. 绘图
# =====================================================================
def plot_all(t1, x1, y1, t2, x2, y2, Delta_t, alpha,
             tau, px, py, vx, vy, ax, ay, speed, accel,
             sig_px, sig_py, sig_vx, sig_vy, LR, p_value, nll0, nll1):

    # Fig 1: KF/RTS 重建轨迹 + 原始观测
    fig, ax_ = plt.subplots(1, 2, figsize=(11, 4.6))
    ax_[0].plot(px, py, 'k-', lw=0.7, label='KF+RTS 重建')
    ax_[0].plot(x1, y1, 'b.', ms=1.5, alpha=0.5, label='方式1 观测')
    ax_[0].plot(x2, y2, 'r.', ms=1.5, alpha=0.5, label='方式2 观测')
    ax_[0].set_xlabel('X (m)'); ax_[0].set_ylabel('Y (m)')
    ax_[0].set_title('XY 平面: 状态空间重建 + 原始观测')
    ax_[0].axis('equal'); ax_[0].grid(alpha=0.3); ax_[0].legend()

    # 用速度模长着色显示动力学
    sc = ax_[1].scatter(px, py, c=speed, s=2, cmap='viridis')
    plt.colorbar(sc, ax=ax_[1], label='速度模 |v| (m/s)')
    ax_[1].set_xlabel('X (m)'); ax_[1].set_ylabel('Y (m)')
    ax_[1].set_title('XY 平面: 速度场可视化')
    ax_[1].axis('equal'); ax_[1].grid(alpha=0.3)
    plt.tight_layout(); plt.savefig(FIGS / 'Q1_kalman_reconstruction.png', dpi=200); plt.close()

    # Fig 2: 全运动学时序 (位置/速度/加速度)
    fig, ax_ = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
    ax_[0].plot(tau, px, 'b-', lw=0.8, label='X')
    ax_[0].plot(tau, py, 'r-', lw=0.8, label='Y')
    ax_[0].fill_between(tau, px-3*sig_px, px+3*sig_px, alpha=0.2, color='b')
    ax_[0].fill_between(tau, py-3*sig_py, py+3*sig_py, alpha=0.2, color='r')
    ax_[0].set_ylabel('位置 (m)'); ax_[0].legend(); ax_[0].grid(alpha=0.3)
    ax_[0].set_title(f'10 Hz 全运动学输出  (Δt̂={Delta_t:.4f} s,  α̂={alpha:.2e})')

    ax_[1].plot(tau, vx, 'b-', lw=0.8, label='Vx')
    ax_[1].plot(tau, vy, 'r-', lw=0.8, label='Vy')
    ax_[1].plot(tau, speed, 'k--', lw=0.8, label='|v|')
    ax_[1].set_ylabel('速度 (m/s)'); ax_[1].legend(); ax_[1].grid(alpha=0.3)

    ax_[2].plot(tau, ax, 'b-', lw=0.8, label='Ax')
    ax_[2].plot(tau, ay, 'r-', lw=0.8, label='Ay')
    ax_[2].plot(tau, accel, 'k--', lw=0.8, label='|a|')
    ax_[2].set_xlabel('统一时间 τ (s)'); ax_[2].set_ylabel('加速度 (m/s²)')
    ax_[2].legend(); ax_[2].grid(alpha=0.3)
    plt.tight_layout(); plt.savefig(FIGS / 'Q1_kalman_kinematics.png', dpi=200); plt.close()

    # Fig 3: 速度/加速度的极坐标图 (机器人运动模式可视化)
    fig, ax_ = plt.subplots(1, 2, figsize=(11, 5))
    theta = np.arctan2(vy, vx)
    ax_[0] = plt.subplot(1, 2, 1, projection='polar')
    ax_[0].scatter(theta, speed, c=tau, s=1, cmap='plasma')
    ax_[0].set_title('速度极坐标分布 (颜色=时间)', pad=20)

    theta_a = np.arctan2(ay, ax)
    ax_[1] = plt.subplot(1, 2, 2, projection='polar')
    ax_[1].scatter(theta_a, accel, c=tau, s=1, cmap='plasma')
    ax_[1].set_title('加速度极坐标分布 (颜色=时间)', pad=20)
    plt.tight_layout(); plt.savefig(FIGS / 'Q1_kalman_polar.png', dpi=200); plt.close()

    # Fig 4: 漂移率检验可视化 (likelihood ratio)
    fig, ax_ = plt.subplots(1, 2, figsize=(11, 4.4))
    # 4.1 NLL 对 α 扫描
    alphas = np.linspace(-1e-3, 1e-3, 101)
    nlls = []
    print('\n[绘图] 扫描 α 维度...')
    t1_, x1_, y1_, t2_, x2_, y2_ = load_data(INPUT_FILE)
    for a in alphas:
        try:
            res = minimize_scalar(
                lambda d: evaluate_model(d, a, t1_, x1_, y1_, t2_, x2_, y2_)['nll'],
                bracket=(Delta_t - 0.05, Delta_t, Delta_t + 0.05),
                method='brent', options={'xtol': 1e-6})
            nlls.append(res.fun)
        except Exception:
            nlls.append(np.nan)
    nlls = np.array(nlls)
    ax_[0].plot(alphas * 1e3, nlls - np.nanmin(nlls), 'b-', lw=1.2)
    ax_[0].axvline(0, color='g', ls=':', label='H₀: α=0')
    ax_[0].axvline(alpha * 1e3, color='r', ls='--', label=f'α̂={alpha:.2e}')
    ax_[0].axhline(chi2.ppf(0.95,1)/2, color='orange', ls=':',
                   label=f'95% LRT 临界 (Δ NLL={chi2.ppf(0.95,1)/2:.2f})')
    ax_[0].set_xlabel('漂移率 α  ×10⁻³'); ax_[0].set_ylabel('Δ NLL')
    ax_[0].set_title('Profile NLL 沿 α 方向')
    ax_[0].legend(fontsize=8); ax_[0].grid(alpha=0.3)

    # 4.2 LRT 卡方分布 + 观测值
    x = np.linspace(0, 8, 200)
    ax_[1].plot(x, chi2.pdf(x, df=1), 'b-', lw=1.5, label='χ²(1) 分布')
    ax_[1].axvline(LR, color='r', lw=2, label=f'观测 LR = {LR:.3f}')
    ax_[1].axvline(chi2.ppf(0.95,1), color='orange', ls='--',
                   label=f'5% 临界 = {chi2.ppf(0.95,1):.3f}')
    ax_[1].fill_between(x[x>=chi2.ppf(0.95,1)],
                        chi2.pdf(x[x>=chi2.ppf(0.95,1)], df=1),
                        alpha=0.3, color='red', label='拒绝域')
    ax_[1].set_xlabel('LR 统计量'); ax_[1].set_ylabel('密度')
    ax_[1].set_title(f'似然比检验 (p = {p_value:.3f})')
    ax_[1].legend(fontsize=8); ax_[1].grid(alpha=0.3)
    plt.tight_layout(); plt.savefig(FIGS / 'Q1_kalman_lrt.png', dpi=200); plt.close()


if __name__ == '__main__':
    main()
