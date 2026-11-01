"""Generate training trajectories from the true solver for the AI emulator."""
import math, time, torch
from physics import BetaPlane, storm, environment, random_field

STEPS_PER_FRAME = 12      # emulator time step = 12 * 0.02 = 0.24 time units
FRAMES = 33               # 8 time units per trajectory


def random_ic(sim, g, batch):
    zs = []
    for _ in range(batch):
        z = environment(sim, g)
        nstorm = int(torch.randint(0, 3, (1,), generator=g).item() > 0) + int(torch.rand(1, generator=g).item() < 0.15)
        for _ in range(nstorm):   # 0, 1 or 2 storms
            x, y = (torch.rand(2, generator=g) * 2 * math.pi).tolist()
            amp = 8 + 8 * torch.rand(1, generator=g).item()
            r = 0.4 + 0.2 * torch.rand(1, generator=g).item()
            z = z + storm(sim, x, y, amp, r)
        # sometimes add a smooth "intervention-like" perturbation so the emulator sees them
        if torch.rand(1, generator=g).item() < 0.5:
            z = z + random_field(sim, g, k_peak=3, k_width=2, rms=0.3 * torch.rand(1, generator=g).item())
        zs.append(z)
    return torch.stack(zs)


def generate(n_traj=1920, batch=64, seed=1, path="checkpoints/data.pt"):
    torch.set_num_threads(4)
    sim = BetaPlane(); g = torch.Generator().manual_seed(seed)
    out, t0 = [], time.time()
    for b in range(n_traj // batch):
        z0 = random_ic(sim, g, batch)
        out.append(sim.run(z0, STEPS_PER_FRAME * (FRAMES - 1), save_every=STEPS_PER_FRAME).half())
        print(f"batch {b+1}/{n_traj//batch}  {time.time()-t0:.0f}s", flush=True)
    data = torch.cat(out)
    torch.save(data, path)
    print("saved", tuple(data.shape))


if __name__ == "__main__":
    generate()
