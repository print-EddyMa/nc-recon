"""Run every Butterfly Engine experiment and save results to outputs/."""
import json, time, math, torch
from physics import BetaPlane, track, pdist
from emulator import load
import engine as E

torch.set_num_threads(4)
T0 = time.time()
def log(msg): print(f"[{time.time()-T0:6.0f}s] {msg}", flush=True)

sim = BetaPlane()
model = load()
N_SCEN = 8
EPS_LIST = [3e-4, 1e-3, 3e-3, 1e-2]
HERO, HERO_EPS = 0, 1e-3

scen = [E.make_scenario(sim, s) for s in range(N_SCEN)]
act = E.Actuator(sim, scen)
log(f"built {N_SCEN} scenarios")
R = dict(eps_list=EPS_LIST, n_scen=N_SCEN, horizon_time=E.NSTEPS * sim.dt)

# ---- A. Is the emulator a good forecaster? -----------------------------------------
z0 = torch.stack([s.z0 for s in scen])
with torch.no_grad():
    emu = model.rollout(z0, E.HORIZON, save=True)
truth = torch.stack([s.base for s in scen])
rel = ((emu - truth).pow(2).mean((-2, -1)) / truth.pow(2).mean((-2, -1))).sqrt().mean(0)
trk_err = []
for b, s in enumerate(scen):
    et = track(sim, emu[b], s.start)
    trk_err.append([pdist(a, c) for a, c in zip(et, s.base_track)])
trk_err = torch.tensor(trk_err).mean(0)
R["forecast"] = dict(rel_field_err=rel.tolist(), track_err=trk_err.tolist(),
                     t=[k * E.STEPS_PER_FRAME * sim.dt for k in range(E.HORIZON + 1)])
log(f"A forecast: track err at T = {trk_err[-1]:.3f}, field rel err at T = {rel[-1]:.3f}")

# ---- B. Does it respond correctly to small nudges? (the butterfly test) -------------
R["response"] = {}
for eps in [1e-4, 1e-3, 1e-2]:
    p = E.random_nudges(sim, scen, act, eps, n=1, seed=7)[0]
    with torch.no_grad():
        dt_ = sim.run(z0 + p, E.NSTEPS, save_every=E.STEPS_PER_FRAME) - truth
        de_ = model.rollout(z0 + p, E.HORIZON, save=True) - emu
    a, b = dt_.flatten(2), de_.flatten(2)
    corr = ((a * b).sum(-1) / (a.norm(dim=-1) * b.norm(dim=-1) + 1e-12)).mean(0)
    amp = (b.norm(dim=-1) / (a.norm(dim=-1) + 1e-12)).mean(0)
    R["response"][str(eps)] = dict(corr=corr.tolist(), amp_ratio=amp.tolist())
    log(f"B response eps={eps:g}: corr at t=1.0 {corr[4]:.2f}, at T {corr[-1]:.2f}; amplitude ratio at T {amp[-1]:.2f}")

# ---- C. Do the gradients agree? -----------------------------------------------------
cos, grads = E.gradient_alignment(sim, model, scen, act)
R["grad_cos"] = cos.tolist()
log(f"C gradient cosine (emulator vs true adjoint): {[round(c,2) for c in cos.tolist()]}")

# ---- D. Steering sweep ---------------------------------------------------------------
R["sweep"] = {}
hero = {}
for eps in EPS_LIST:
    row = {}
    rnd = [E.judge(sim, scen, p) for p in E.random_nudges(sim, scen, act, eps, n=8)]
    rd = torch.stack([r["damage"] for r in rnd]); rm = torch.stack([r["miss"] for r in rnd])
    row["random"] = dict(damage=rd.mean(0).tolist(), miss=rm.mean(0).tolist(),
                         best_damage=rd.min(0).values.tolist(), best_miss=rm.max(0).values.tolist())
    for through, iters in [("emu", 30), ("truth", 40)]:
        p, believed = E.optimise(sim, scen, act, eps, through, model=model, iters=iters, log=log)
        j = E.judge(sim, scen, p)
        bf = E.brute_force_energy(sim, scen, j["miss"])
        leverage = bf / (eps * torch.tensor([s.E_storm for s in scen]))
        row[through] = dict(believed_damage=believed.tolist(), damage=j["damage"].tolist(),
                            miss=j["miss"].tolist(), leverage=leverage.tolist())
        if eps == HERO_EPS:
            hero[through] = dict(nudge=p[HERO], frames=j["frames"][HERO], track=j["tracks"][HERO],
                                 emu_frames=E.emulate(model, scen, p)[HERO])
        log(f"D eps={eps:g} {through:5s}: believed {believed.mean():.3f} | TRUE damage {j['damage'].mean():.3f}, "
            f"miss {j['miss'].mean():.2f}, leverage {leverage.median():.0f}x")
    log(f"D eps={eps:g} random: damage {rd.mean():.3f}, miss {rm.mean():.2f}")
    R["sweep"][str(eps)] = row
    json.dump(R, open("outputs/results.json", "w"), indent=1)

# ---- E. Emulator hacking: let the search use fine scales the emulator never learned ---
act_free = E.Actuator(sim, scen, kmax=21)
p, believed = E.optimise(sim, scen, act_free, HERO_EPS, "emu", model=model, iters=30, log=log)
j = E.judge(sim, scen, p)
R["hacking"] = dict(eps=HERO_EPS, believed_damage=believed.tolist(), damage=j["damage"].tolist(), miss=j["miss"].tolist())
log(f"E free-scale emulator search: believed {believed.mean():.3f} vs TRUE {j['damage'].mean():.3f}")

s = scen[HERO]
torch.save(dict(base=s.base, base_track=s.base_track, city=s.city, start=s.start, z0=s.z0,
                emu_base=emu[HERO], hero=hero, grads={k: v[HERO] for k, v in grads.items()}, eps=HERO_EPS),
           "outputs/hero.pt")
json.dump(R, open("outputs/results.json", "w"), indent=1)
log("done")
