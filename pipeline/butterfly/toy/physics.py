"""
The "true atmosphere": 2D barotropic vorticity dynamics on a beta-plane.

    dζ/dt + J(ψ, ζ) + U ∂ζ/∂x + β ∂ψ/∂x = -ν (-∇²)^4 ζ,     ζ = ∇²ψ

This is the textbook toy model for hurricane motion: a cyclone (positive ζ)
is advected by the large-scale environmental flow ("steering") and also
self-propels north-westward because of the beta effect ("beta drift").
Small-scale background eddies make the evolution chaotic.

Pseudo-spectral, doubly periodic on [0, 2π)², 2/3 dealiasing, RK4 time
stepping, hyperviscosity via exact integrating factor. Written in torch so
the whole solver is differentiable -> we get the exact adjoint for free,
which serves as the "oracle" against which the AI emulator is judged.
"""
import math
import torch

L = 2 * math.pi


class BetaPlane:
    def __init__(self, n=64, beta=1.5, U=0.0, nu=None, dt=0.02, device="cpu", dtype=torch.float32):
        self.n, self.beta, self.U, self.dt = n, beta, U, dt
        self.dtype, self.device = dtype, device
        k = torch.fft.fftfreq(n, d=1.0 / n).to(dtype)          # integer wavenumbers (domain 2π)
        kr = torch.fft.rfftfreq(n, d=1.0 / n).to(dtype)
        self.KY, self.KX = torch.meshgrid(k, kr, indexing="ij")
        self.K2 = self.KX ** 2 + self.KY ** 2
        self.K2inv = torch.where(self.K2 > 0, 1.0 / self.K2.clamp(min=1e-12), torch.zeros_like(self.K2))
        kmax = n // 3
        self.dealias = ((self.KX.abs() <= kmax) & (self.KY.abs() <= kmax)).to(dtype)
        if nu is None:
            nu = 2.0 / (kmax ** 8) / dt * 0.5   # damps the dealiasing edge strongly each step
        self.nu = nu
        self.hv = torch.exp(-nu * self.K2 ** 4 * dt)
        x = torch.arange(n, dtype=dtype) * (L / n)
        self.Y, self.X = torch.meshgrid(x, x, indexing="ij")    # ζ[..., iy, ix]
        for name in ["KX", "KY", "K2", "K2inv", "dealias", "hv", "X", "Y"]:
            setattr(self, name, getattr(self, name).to(device))

    # --- spectral helpers -------------------------------------------------
    def rhs_hat(self, zh):
        ikx, iky = 1j * self.KX, 1j * self.KY
        psih = -zh * self.K2inv
        u = torch.fft.irfft2(-iky * psih, s=(self.n, self.n))
        v = torch.fft.irfft2(ikx * psih, s=(self.n, self.n))
        zx = torch.fft.irfft2(ikx * zh, s=(self.n, self.n))
        zy = torch.fft.irfft2(iky * zh, s=(self.n, self.n))
        adv = torch.fft.rfft2((u + self.U) * zx + v * zy) * self.dealias
        return -adv - self.beta * ikx * psih

    def step_hat(self, zh):
        dt = self.dt
        k1 = self.rhs_hat(zh)
        k2 = self.rhs_hat(zh + 0.5 * dt * k1)
        k3 = self.rhs_hat(zh + 0.5 * dt * k2)
        k4 = self.rhs_hat(zh + dt * k3)
        return (zh + dt / 6 * (k1 + 2 * k2 + 2 * k3 + k4)) * self.hv

    def run(self, z0, nsteps, save_every=None):
        """Integrate vorticity field(s) z0 [..., n, n]. Returns final field or list of snapshots."""
        zh = torch.fft.rfft2(z0) * self.dealias
        snaps = [z0] if save_every else None
        for i in range(1, nsteps + 1):
            zh = self.step_hat(zh)
            if save_every and i % save_every == 0:
                snaps.append(torch.fft.irfft2(zh, s=(self.n, self.n)))
        return torch.stack(snaps, dim=-3) if save_every else torch.fft.irfft2(zh, s=(self.n, self.n))

    # --- diagnostics --------------------------------------------------------
    def energy(self, z):
        """Kinetic energy 0.5 <|u|²> = 0.5 Σ |ζ̂|²/k² (normalised)."""
        zh = torch.fft.rfft2(z)
        w = torch.ones_like(self.K2); w[:, 1:-1] = 2.0      # rfft double-counting
        return 0.5 * (w * zh.abs() ** 2 * self.K2inv).sum(dim=(-2, -1)) / self.n ** 4

    def periodic_dist2(self, x0, y0):
        dx = torch.remainder(self.X - x0 + L / 2, L) - L / 2
        dy = torch.remainder(self.Y - y0 + L / 2, L) - L / 2
        return dx ** 2 + dy ** 2

    def gaussian(self, x0, y0, r):
        return torch.exp(-self.periodic_dist2(x0, y0) / r ** 2)


# --- initial conditions -------------------------------------------------------

def storm(sim, x0, y0, amp=12.0, r=0.5):
    """A Gaussian cyclone (monopole). The domain mean is removed (periodic domain)."""
    core = amp * torch.exp(-sim.periodic_dist2(x0, y0) / r ** 2)
    return core - core.mean()


def random_field(sim, gen, k_peak=6.0, k_width=2.0, rms=1.0, batch=()):
    """Random vorticity with a Gaussian-shell spectrum around k_peak."""
    n = sim.n
    shape = tuple(batch) + (n, n // 2 + 1)
    phase = torch.rand(shape, generator=gen, dtype=sim.dtype) * 2 * math.pi
    amp = torch.randn(shape, generator=gen, dtype=sim.dtype).abs()
    k = sim.K2.sqrt()
    spec = torch.exp(-((k - k_peak) / k_width) ** 2) * (k > 0)
    zh = amp * spec * torch.exp(1j * phase) * sim.dealias
    z = torch.fft.irfft2(zh, s=(n, n))
    z = z - z.mean(dim=(-2, -1), keepdim=True)
    return z * rms / z.std(dim=(-2, -1), keepdim=True).clamp(min=1e-8)


def environment(sim, gen, steer_rms=0.5, eddy_rms=0.7, batch=()):
    """Large-scale steering pattern (k~1-2) + small-scale chaotic eddies (k~6-10)."""
    big = random_field(sim, gen, k_peak=1.5, k_width=0.8, rms=steer_rms, batch=batch)
    small = random_field(sim, gen, k_peak=7.0, k_width=2.5, rms=eddy_rms, batch=batch)
    return big + small


# --- storm tracking (non-differentiable, for reporting) -----------------------

def track_center(sim, z, guess=None, search_r=1.2):
    """Locate the storm as the peak of smoothed positive vorticity near the previous position."""
    zh = torch.fft.rfft2(z) * torch.exp(-sim.K2 * 0.15 ** 2)
    zs = torch.fft.irfft2(zh, s=(sim.n, sim.n))
    if guess is not None:
        zs = zs * (sim.periodic_dist2(*guess) < search_r ** 2)
    idx = torch.argmax(zs.reshape(-1)).item()
    iy, ix = divmod(idx, sim.n)
    # sub-grid refinement: weighted centroid in a 5x5 window (periodic)
    w, sx, sy = 0.0, 0.0, 0.0
    h = L / sim.n
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            val = max(zs[(iy + dy) % sim.n, (ix + dx) % sim.n].item(), 0.0)
            w += val; sx += val * (ix + dx) * h; sy += val * (iy + dy) * h
    return (sx / w % L, sy / w % L) if w > 0 else (ix * h, iy * h)


def track(sim, frames, start):
    pos, out = start, []
    for f in frames:
        pos = track_center(sim, f, guess=pos)
        out.append(pos)
    return out


def pdist(a, b):
    dx = (a[0] - b[0] + L / 2) % L - L / 2
    dy = (a[1] - b[1] + L / 2) % L - L / 2
    return math.hypot(dx, dy)
