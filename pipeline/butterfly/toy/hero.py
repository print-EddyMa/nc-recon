"""Re-run the showcase scenario (and the 'AI lies' scenario) in detail for the figures."""
import json, torch
from physics import BetaPlane
from emulator import load
import engine as E

torch.set_num_threads(4)
HERO, LIAR, EPS = 6, 4, 3e-3          # chosen from outputs/results.json (best-aligned / worst-aligned storms)
sim, model = BetaPlane(), load()

scen = [E.make_scenario(sim, HERO)]
act = E.Actuator(sim, scen)
hero = {}
for through, iters in [("emu", 30), ("truth", 40)]:
    p, believed = E.optimise(sim, scen, act, EPS, through, model=model, iters=iters, log=print)
    j = E.judge(sim, scen, p)
    hero[through] = dict(nudge=p[0], frames=j["frames"][0], track=j["tracks"][0], emu_frames=E.emulate(model, scen, p)[0],
                         believed=believed.item(), damage=j["damage"].item(), miss=j["miss"].item())
    print(through, {k: round(v, 3) for k, v in hero[through].items() if isinstance(v, float)})
cos, grads = E.gradient_alignment(sim, model, scen, act)
s = scen[0]
with torch.no_grad():
    emu_base = model.rollout(s.z0[None], E.HORIZON, save=True)[0]

liar = [E.make_scenario(sim, LIAR)]
lcos, lgrads = E.gradient_alignment(sim, model, liar, E.Actuator(sim, liar))
print("cos hero", cos.item(), "cos liar", lcos.item())

torch.save(dict(base=s.base, base_track=s.base_track, city=s.city, start=s.start, z0=s.z0, emu_base=emu_base,
                hero=hero, grads={k: v[0] for k, v in grads.items()}, cos=cos.item(), eps=EPS, idx=HERO,
                liar=dict(idx=LIAR, z0=liar[0].z0, start=liar[0].start, city=liar[0].city, cos=lcos.item(),
                          grads={k: v[0] for k, v in lgrads.items()})),
           "outputs/hero.pt")
