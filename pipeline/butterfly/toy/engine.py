"""
The Butterfly Engine.

Given a storm heading for a city, search for the smallest nudge to the
*environment* (we are not allowed to touch the storm itself) that makes the
storm miss the city several days later.

Two ways to search:
  * EMULATOR  - backprop through the AI weather model (cheap, but it may lie)
  * ORACLE    - backprop through the true physics (exact adjoint; what a
                perfect differentiable model would give you)

Every nudge, however it was found, is judged in the TRUE physics.
"""
import math
from dataclasses import dataclass
import torch
from physics import BetaPlane, storm, environment, track, pdist, L
from data import STEPS_PER_FRAME

HORIZON = 25                    # emulator steps  -> 25 * 0.24 = 6 time units ("~5 days")
NSTEPS = HORIZON * STEPS_PER_FRAME
KEEP_OUT = 1.0                  # radius around the storm where we may NOT intervene
K_MAX = 8                       # actuator can only paint large-scale patterns (k <= 8)
CITY_R = 0.7                    # radius of the city's "damage zone"
DAMAGE_FRAMES = 3               # damage is counted over the final 3 frames


@dataclass
class Scenario:
    seed: int
    z0: torch.Tensor            # initial vorticity [n, n]
    start: tuple                # storm start position
    city: tuple                 # where the unperturbed storm ends up
    base: torch.Tensor          # true baseline frames [HORIZON+1, n, n]
    base_track: list
    E_storm: float
    mask: torch.Tensor          # 1 where intervention allowed
    W: torch.Tensor             # city damage weight
    J0: float                   # baseline damage (normaliser)


def make_scenario(sim, seed):
    g = torch.Generator().manual_seed(10_000 + seed)
    while True:
        x, y = (torch.rand(2, generator=g) * L).tolist()
        s = storm(sim, x, y)
        z0 = s + environment(sim, g)
        base = sim.run(z0, NSTEPS, save_every=STEPS_PER_FRAME)
        tr = track(sim, base, (x, y))
        # require a coherent storm that actually travels
        if base[-1].max() > 6.0 and pdist(tr[0], tr[-1]) > 1.5:
            break
    city = tr[-1]
    W = sim.gaussian(*city, CITY_R)
    mask = 1 - sim.gaussian(x, y, KEEP_OUT)
    J0 = raw_damage(base[-DAMAGE_FRAMES:], W).item()
    return Scenario(seed, z0, (x, y), city, base, tr, sim.energy(s).item(), mask, W, J0)


def raw_damage(frames, W):
    """Squared cyclonic vorticity inside the city zone, summed over the last frames."""
    return (torch.relu(frames) ** 2 * W).sum(dim=(-3, -2, -1))


class Actuator:
    """Maps free parameters theta -> a physically constrained nudge.

    Constraints: large scale only (k <= K_MAX), zero inside the keep-out zone
    around the storm, and an exact energy budget  E(nudge) = eps * E(storm)."""

    def __init__(self, sim, scenarios, kmax=K_MAX):
        self.sim = sim
        self.lp = (sim.K2 <= kmax ** 2).to(sim.dtype) * sim.dealias
        self.mask = torch.stack([s.mask for s in scenarios])
        self.Es = torch.tensor([s.E_storm for s in scenarios])

    def __call__(self, theta, eps):
        p = torch.fft.irfft2(torch.fft.rfft2(theta) * self.lp, s=theta.shape[-2:]) * self.mask
        eps = torch.as_tensor(eps, dtype=theta.dtype)
        return p * (eps * self.Es / self.sim.energy(p)).sqrt()[:, None, None]


# --- forward models ------------------------------------------------------------

def truth_frames(sim, z0, last_only=DAMAGE_FRAMES):
    """True physics, returning the final `last_only` frames (differentiable)."""
    zh = torch.fft.rfft2(z0) * sim.dealias
    out = []
    for i in range(1, NSTEPS + 1):
        zh = sim.step_hat(zh)
        if i % STEPS_PER_FRAME == 0 and i // STEPS_PER_FRAME > HORIZON - last_only:
            out.append(torch.fft.irfft2(zh, s=(sim.n, sim.n)))
    return torch.stack(out, -3)


def emu_frames(model, z0, last_only=DAMAGE_FRAMES):
    out, z = [], z0
    for k in range(1, HORIZON + 1):
        z = model(z)
        if k > HORIZON - last_only:
            out.append(z)
    return torch.stack(out, -3)


def damage_ratio(frames, scen):
    W = torch.stack([s.W for s in scen])[:, None]
    J0 = torch.tensor([s.J0 for s in scen])
    return raw_damage(frames, W) / J0


# --- the search ------------------------------------------------------------------

def optimise(sim, scen, act, eps, through, model=None, iters=40, lr=0.3, seed=0, log=None):
    """Find nudges (one per scenario, batched) that minimise damage at the city."""
    g = torch.Generator().manual_seed(seed)
    z0 = torch.stack([s.z0 for s in scen])
    theta = torch.randn(z0.shape, generator=g).requires_grad_(True)
    opt = torch.optim.Adam([theta], lr=lr)
    best, best_J = None, None
    for it in range(iters):
        p = act(theta, eps)
        fr = truth_frames(sim, z0 + p) if through == "truth" else emu_frames(model, z0 + p)
        J = damage_ratio(fr, scen)
        with torch.no_grad():
            if best is None:
                best, best_J = p.detach().clone(), J.detach().clone()
            imp = J < best_J
            best[imp], best_J[imp] = p.detach()[imp], J.detach()[imp]
        opt.zero_grad(); J.sum().backward(); opt.step()
        if log is not None and (it % 10 == 0 or it == iters - 1):
            log(f"  [{through}] eps={eps:g} it {it:3d}  mean damage {J.mean().item():.3f}")
    return best, best_J          # nudges, and the damage the search model *believes*


def random_nudges(sim, scen, act, eps, n=8, seed=123):
    g = torch.Generator().manual_seed(seed)
    return [act(torch.randn(len(scen), sim.n, sim.n, generator=g), eps) for _ in range(n)]


# --- judging in the true physics -------------------------------------------------

@torch.no_grad()
def judge(sim, scen, nudges):
    """Run the TRUE physics with each nudge. Returns damage ratio, miss distance, frames."""
    z0 = torch.stack([s.z0 for s in scen])
    fr = sim.run(z0 + nudges, NSTEPS, save_every=STEPS_PER_FRAME)       # [B, T+1, n, n]
    dmg = damage_ratio(fr[:, -DAMAGE_FRAMES:], scen)
    tracks = [track(sim, fr[b], s.start) for b, s in enumerate(scen)]
    miss = torch.tensor([pdist(t[-1], s.city) for t, s in zip(tracks, scen)])
    return dict(damage=dmg, miss=miss, frames=fr, tracks=tracks)


@torch.no_grad()
def emulate(model, scen, nudges):
    z0 = torch.stack([s.z0 for s in scen])
    return model.rollout(z0 + nudges, HORIZON, save=True)


def brute_force_energy(sim, scen, miss):
    """Energy you'd need to inject to simply MOVE the storm by `miss` directly
    (energy of storm(x+d) - storm(x)). Ratio to nudge energy = butterfly leverage."""
    out = []
    for s, d in zip(scen, miss.tolist()):
        x, y = s.start
        out.append(sim.energy(storm(sim, x + d, y) - storm(sim, x, y)).item())
    return torch.tensor(out)


def gradient_alignment(sim, model, scen, act):
    """Cosine similarity between the emulator's and the true adjoint sensitivity
    of city damage to the initial state, restricted to the actuator's subspace."""
    z0 = torch.stack([s.z0 for s in scen])
    grads = {}
    for name in ["truth", "emu"]:
        x = z0.clone().requires_grad_(True)
        fr = truth_frames(sim, x) if name == "truth" else emu_frames(model, x)
        damage_ratio(fr, scen).sum().backward()
        gr = torch.fft.irfft2(torch.fft.rfft2(x.grad) * act.lp, s=x.shape[-2:]) * act.mask
        grads[name] = gr
    a, b = grads["truth"].flatten(1), grads["emu"].flatten(1)
    cos = (a * b).sum(1) / (a.norm(dim=1) * b.norm(dim=1))
    return cos, grads
