"""
The AI weather model: a Fourier Neural Operator (the architecture family behind
FourCastNet) trained to advance the vorticity field by one 0.24-time-unit step.
It never sees the equations, only snapshots from the true solver.
"""
import time, math, torch, torch.nn as nn, torch.nn.functional as F

SCALE = 10.0   # vorticity normalisation


class SpectralConv(nn.Module):
    """Learned complex channel-mixing of the lowest Fourier modes (channels-last).

    Implemented as ONE real batched matmul over modes:
        [xr, xi] @ [[wr, wi], [-wi, wr]] = [xr wr - xi wi, xr wi + xi wr]
    (~10x faster on CPU than complex einsum)."""
    def __init__(self, cin, cout, modes):
        super().__init__()
        self.modes, self.cout = modes, cout
        s = 1 / (cin * cout)
        self.wr = nn.Parameter(s * torch.randn(2 * modes * modes, cin, cout))
        self.wi = nn.Parameter(s * torch.randn(2 * modes * modes, cin, cout))

    def forward(self, x):                      # x: [B, H, W, C]
        B, H, W, C = x.shape
        m, O = self.modes, self.cout
        xh = torch.fft.rfft2(x, dim=(1, 2))                                          # [B, H, W/2+1, C]
        blk = torch.cat([xh[:, :m, :m], xh[:, -m:, :m]], dim=1)                      # [B, 2m, m, C]
        blk = blk.permute(1, 2, 0, 3).reshape(2 * m * m, B, C)                       # [M, B, C]
        xin = torch.cat([blk.real, blk.imag], dim=-1).contiguous()                   # [M, B, 2C]
        Wb = torch.cat([torch.cat([self.wr, self.wi], 2), torch.cat([-self.wi, self.wr], 2)], 1)
        y = torch.bmm(xin, Wb)                                                       # [M, B, 2O]
        y = torch.complex(y[..., :O], y[..., O:]).reshape(2 * m, m, B, O).permute(2, 0, 1, 3)  # [B, 2m, m, O]
        out = F.pad(y, (0, 0, 0, W // 2 + 1 - m))
        out = torch.cat([out[:, :m], out.new_zeros(B, H - 2 * m, W // 2 + 1, O), out[:, m:]], dim=1)
        return torch.fft.irfft2(out, s=(H, W), dim=(1, 2))


class FNO(nn.Module):
    def __init__(self, width=40, modes=16, layers=5):
        super().__init__()
        self.lift = nn.Linear(1, width)
        self.spec = nn.ModuleList([SpectralConv(width, width, modes) for _ in range(layers)])
        self.local = nn.ModuleList([nn.Linear(width, width) for _ in range(layers)])
        self.proj = nn.Sequential(nn.Linear(width, 64), nn.GELU(), nn.Linear(64, 1))

    def forward(self, z):
        """z: [B, H, W] vorticity -> vorticity one emulator step (0.24 time units) later."""
        x = self.lift(z[..., None] / SCALE)
        for s, l in zip(self.spec, self.local):
            x = x + F.gelu(s(x) + l(x))
        return z + SCALE * self.proj(x)[..., 0]

    def rollout(self, z, nsteps, save=False):
        frames = [z]
        for _ in range(nsteps):
            z = self(z)
            if save:
                frames.append(z)
        return torch.stack(frames, 1) if save else z


def train(data_path="checkpoints/data.pt", out="checkpoints/emulator.pt", minutes=30, batch=16, seed=0):
    torch.manual_seed(seed); torch.set_num_threads(4)
    data = torch.load(data_path).float()
    ntr = int(0.9 * len(data))
    tr, va = data[:ntr], data[ntr:]
    model = FNO()
    print("params", sum(p.numel() for p in model.parameters()))
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-5)
    T = tr.shape[1]
    t0, it, log = time.time(), 0, []
    budget = minutes * 60
    while time.time() - t0 < budget:
        frac = (time.time() - t0) / budget
        for gp in opt.param_groups:
            gp["lr"] = 1e-3 * 0.5 * (1 + math.cos(math.pi * frac)) + 2e-5
        # curriculum: unroll length 1 -> 6 steps (autoregressive training, like GraphCast fine-tuning)
        K = 1 + int(5 * min(1.0, frac / 0.7))
        i = torch.randint(0, len(tr), (batch,))
        s = torch.randint(0, T - K, (batch,))
        seq = torch.stack([tr[a, b:b + K + 1] for a, b in zip(i.tolist(), s.tolist())])
        z, loss = seq[:, 0], 0.0
        for k in range(1, K + 1):
            z = model(z)
            loss = loss + F.mse_loss(z, seq[:, k]) / SCALE ** 2
        loss = loss / K
        opt.zero_grad(); loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step(); it += 1
        if it % 200 == 0:
            with torch.no_grad():
                z = va[:64, 0]; errs = []
                for k in range(1, 25):
                    z = model(z)
                    if k in (1, 8, 24):
                        errs.append((F.mse_loss(z, va[:64, k]) / va[:64, k].pow(2).mean()).sqrt().item())
            log.append(dict(it=it, t=time.time() - t0, K=K, loss=loss.item(), rel_err_1=errs[0], rel_err_8=errs[1], rel_err_24=errs[2]))
            print(f"it {it} {time.time()-t0:.0f}s K={K} loss {loss.item():.2e} | val rel.err @1:{errs[0]:.3f} @8:{errs[1]:.3f} @24:{errs[2]:.3f}", flush=True)
            torch.save(dict(model=model.state_dict(), log=log), out)
    torch.save(dict(model=model.state_dict(), log=log), out)


def load(path="checkpoints/emulator.pt"):
    m = FNO(); m.load_state_dict(torch.load(path)["model"]); m.eval()
    for p in m.parameters():
        p.requires_grad_(False)
    return m


if __name__ == "__main__":
    train()
