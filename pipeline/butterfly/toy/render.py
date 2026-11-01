"""Turn outputs/results.json + outputs/hero.pt into figures and an animation."""
import json, math, torch, numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import animation
from physics import L
from engine import CITY_R, KEEP_OUT

R = json.load(open("outputs/results.json"))
H = torch.load("outputs/hero.pt", weights_only=False)

# validated categorical slots (reference palette): 1 blue, 2 orange; baseline in neutral gray
C_EMU, C_ORA, C_RND, C_BASE = "#2a78d6", "#eb6834", "#8a8984", "#0b0b0b"
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
plt.rcParams.update({"font.size": 11, "axes.edgecolor": INK2, "axes.labelcolor": INK, "xtick.color": INK2,
                     "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "lines.linewidth": 2,
                     "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb", "savefig.facecolor": "#fcfcfb"})
VMAX = 8


def unwrap(track):
    """Unwrap a periodic track so lines don't jump across the domain edge."""
    xy = np.array(track); out = [xy[0]]
    for p in xy[1:]:
        d = (p - out[-1] + L / 2) % L - L / 2
        out.append(out[-1] + d)
    return np.array(out)


def draw_track(ax, track, color, upto=None, **kw):
    xy = unwrap(track[: (upto or len(track)) ])
    for sx in (-L, 0, L):
        for sy in (-L, 0, L):
            ax.plot(xy[:, 0] + sx, xy[:, 1] + sy, color=color, **kw)


def field(ax, z, title=None):
    ax.imshow(z, origin="lower", extent=[0, L, 0, L], cmap="RdBu_r", vmin=-VMAX, vmax=VMAX, interpolation="bilinear")
    ax.set_xlim(0, L); ax.set_ylim(0, L); ax.set_xticks([]); ax.set_yticks([]); ax.grid(False)
    for s in ax.spines.values(): s.set_visible(True); s.set_color(INK2)
    if title: ax.set_title(title, fontsize=12, color=INK)


def city(ax, c=None):
    c = c or H["city"]
    for sx in (-L, 0, L):
        for sy in (-L, 0, L):
            ax.add_patch(plt.Circle((c[0] + sx, c[1] + sy), CITY_R, fill=False, ec=INK, lw=2, ls="--"))
            ax.text(c[0] + sx, c[1] + sy + CITY_R + 0.12, "CITY", ha="center", fontsize=9, weight="bold", color=INK,
                    clip_on=True)


def keep_out(ax, start):
    for sx in (-L, 0, L):
        for sy in (-L, 0, L):
            ax.add_patch(plt.Circle((start[0] + sx, start[1] + sy), KEEP_OUT, fill=False, ec="#008300", lw=2))


def sens(ax, g, title, z0):
    g = g.numpy(); m = np.abs(g).max()
    ax.imshow(g, origin="lower", extent=[0, L, 0, L], cmap="PuOr_r", vmin=-m, vmax=m, interpolation="bilinear")
    ax.set_xticks([]); ax.set_yticks([]); ax.grid(False); ax.set_title(title, fontsize=12)
    x = np.linspace(0, L, 64, endpoint=False)
    ax.contour(x, x, z0.numpy(), levels=[4], colors=INK, linewidths=1.5)


# ---------------------------------------------------------------- 1. hero animation
def hero_animation():
    h = H["hero"]["emu"]
    base, steer, dream = H["base"], h["frames"], h["emu_frames"]
    T = base.shape[0]
    dt = R["horizon_time"] / (T - 1)
    fig, axes = plt.subplots(1, 3, figsize=(15, 5.6))
    fig.subplots_adjust(left=0.01, right=0.99, top=0.8, bottom=0.02, wspace=0.04)
    titles = ["① No intervention (true physics)", "② With AI-designed nudge (true physics)",
              "③ What the AI thought would happen"]
    sup = fig.suptitle("", fontsize=15, weight="bold", color=INK, y=0.97)

    def frame(k):
        for ax in axes: ax.clear()
        field(axes[0], base[k], titles[0]); field(axes[1], steer[k], titles[1]); field(axes[2], dream[k], titles[2])
        for ax in axes: city(ax)
        draw_track(axes[0], H["base_track"], C_BASE, upto=k + 1, lw=2)
        draw_track(axes[1], H["base_track"], C_RND, upto=k + 1, lw=1.5, ls=":")
        draw_track(axes[1], h["track"], C_EMU, upto=k + 1, lw=2.5)
        if k <= 2:   # show the nudge for the first frames
            axes[1].contour(np.linspace(0, L, 64, endpoint=False), np.linspace(0, L, 64, endpoint=False),
                            h["nudge"].numpy(), levels=6, colors="#008300", linewidths=1)
            axes[1].text(0.1, 0.15, "green contours = the nudge", color="#006400", fontsize=10, weight="bold")
        sup.set_text(f"The Butterfly Engine   t = {k*dt:4.1f}   "
                     f"(storm #{H['idx']}, nudge energy = {H['eps']*100:.1f}% of the storm's)")
        return []

    anim = animation.FuncAnimation(fig, frame, frames=list(range(T)) + [T - 1] * 6, interval=180)
    anim.save("outputs/butterfly_engine.gif", writer="pillow", dpi=70)
    try:
        anim.save("outputs/butterfly_engine.mp4", writer="ffmpeg", dpi=100, fps=6)
    except Exception as e:
        print("mp4 skipped:", e)
    plt.close(fig)


# ---------------------------------------------------------------- 2. hero static panel
def hero_static():
    h = H["hero"]
    fig, ax = plt.subplots(1, 4, figsize=(20, 5.4))
    x = np.linspace(0, L, 64, endpoint=False)
    field(ax[0], H["z0"], "Initial state: storm, city, no-touch zone")
    keep_out(ax[0], H["start"]); city(ax[0])
    sens(ax[1], H["grads"]["truth"], "TRUE sensitivity (exact adjoint)", H["z0"])
    sens(ax[2], H["grads"]["emu"], "AI's sensitivity (emulator gradient)", H["z0"])
    ax[2].text(0.03, 0.03, f"cosine similarity to truth: {H['cos']:+.2f}", transform=ax[2].transAxes, fontsize=10,
               weight="bold", bbox=dict(fc="white", ec=INK2))

    ax[3].set_title("Storm tracks (true physics)", fontsize=12)
    ax[3].set_aspect("equal")
    draw_track(ax[3], H["base_track"], C_BASE, lw=2.5, label="no intervention")
    draw_track(ax[3], h["emu"]["track"], C_EMU, lw=2.5, label="AI-designed nudge")
    draw_track(ax[3], h["truth"]["track"], C_ORA, lw=2.5, ls="--", label="oracle nudge (exact adjoint)")
    city(ax[3])
    ax[3].plot(*H["start"], "o", color=INK, ms=8)
    x0 = unwrap(H["base_track"])[0]
    for tr, c in [(H["base_track"], C_BASE), (h["emu"]["track"], C_EMU), (h["truth"]["track"], C_ORA)]:
        end = unwrap(tr)[-1] - unwrap(tr)[0] + x0
        ax[3].plot(*end, "X", color=c, ms=13, mec="white", mew=1.5, zorder=5)
    ax[3].text(0.02, 0.02, "● start   ✖ position at t = 6", transform=ax[3].transAxes, fontsize=9, color=INK2)
    xy = unwrap(H["base_track"]); lo, hi = xy.min(0) - 1.6, xy.max(0) + 1.6
    ax[3].set_xlim(lo[0], hi[0]); ax[3].set_ylim(lo[1], hi[1]); ax[3].set_xticks([]); ax[3].set_yticks([])
    handles = [plt.Line2D([], [], color=c, lw=2.5, ls=ls) for c, ls in [(C_BASE, "-"), (C_EMU, "-"), (C_ORA, "--")]]
    ax[3].legend(handles, ["no intervention", "AI-designed nudge", "oracle nudge (exact adjoint)"], loc="best", fontsize=9, frameon=True)
    fig.suptitle(f"Storm #{H['idx']}: nudge energy = {H['eps']*100:.1f}% of the storm's.  "
                 f"AI-designed nudge: {100*(1-h['emu']['damage']):.0f}% of damage avoided (AI promised {100*(1-h['emu']['believed']):.0f}%), "
                 f"oracle: {100*(1-h['truth']['damage']):.0f}%", fontsize=13, weight="bold", color=INK)
    fig.tight_layout()
    fig.savefig("outputs/fig_hero.png", dpi=110)


def liar():
    Lr = H["liar"]
    fig, ax = plt.subplots(1, 3, figsize=(15, 5.4))
    field(ax[0], Lr["z0"], f"Storm #{Lr['idx']}: initial state")
    keep_out(ax[0], Lr["start"]); city(ax[0], Lr["city"])
    sens(ax[1], Lr["grads"]["truth"], "TRUE sensitivity (exact adjoint)", Lr["z0"])
    sens(ax[2], Lr["grads"]["emu"], "AI's sensitivity (emulator gradient)", Lr["z0"])
    ax[2].text(0.03, 0.03, f"cosine similarity to truth: {Lr['cos']:+.2f}", transform=ax[2].transAxes, fontsize=10,
               weight="bold", bbox=dict(fc="white", ec=INK2))
    fig.suptitle("When the AI lies: an accurate forecast, but the wrong map of where to push", fontsize=13, weight="bold", color=INK)
    fig.tight_layout(); fig.savefig("outputs/fig_liar.png", dpi=110); plt.close(fig)
    plt.close(fig)


# ---------------------------------------------------------------- 3. the sweep + lie detector
def sweep():
    eps = R["eps_list"]; pct = [e * 100 for e in eps]
    S = R["sweep"]
    def stat(method, key):
        a = np.array([S[str(e)][method][key] for e in eps])
        return a.mean(1), a.std(1) / math.sqrt(a.shape[1])
    fig, ax = plt.subplots(1, 3, figsize=(18, 5.2))

    for method, c, lab, ls in [("random", C_RND, "random nudge", ":"), ("emu", C_EMU, "AI-designed (judged in true physics)", "-"),
                               ("truth", C_ORA, "oracle (exact adjoint)", "--")]:
        m, s = stat(method, "miss")
        ax[0].errorbar(pct, m, yerr=s, color=c, ls=ls, marker="o", ms=8, capsize=3, label=lab)
        m, s = stat(method, "damage")
        ax[1].errorbar(pct, 100 * (1 - m), yerr=100 * s, color=c, ls=ls, marker="o", ms=8, capsize=3, label=lab)
    ax[0].axhline(CITY_R, color=INK2, lw=1, ls="-.")
    ax[0].text(pct[0], CITY_R + 0.03, "city radius", color=INK2, fontsize=9)
    ax[0].set_xscale("log"); ax[0].set_xlabel("nudge energy (% of storm energy)"); ax[0].set_ylabel("how far the storm misses its original landfall")
    ax[0].set_title("Steering power", fontsize=13, weight="bold", loc="left"); ax[0].legend(fontsize=9)
    ax[1].set_xscale("log"); ax[1].set_xlabel("nudge energy (% of storm energy)"); ax[1].set_ylabel("damage avoided at the city (%)")
    ax[1].set_title("Damage avoided", fontsize=13, weight="bold", loc="left"); ax[1].set_ylim(-10, 105)

    # lie detector: what the emulator believed vs what really happened
    allb, allt = [], []
    for e in eps:
        b = 100 * (1 - np.array(S[str(e)]["emu"]["believed_damage"])); t = 100 * (1 - np.array(S[str(e)]["emu"]["damage"]))
        allb += list(b); allt += list(t)
    ax[2].scatter(allb, allt, s=60, color=C_EMU, ec="white", lw=1.5, zorder=3, label="large-scale actuator (k ≤ 8)")
    if "hacking" in R:
        hb = 100 * (1 - np.array(R["hacking"]["believed_damage"])); ht = 100 * (1 - np.array(R["hacking"]["damage"]))
        ax[2].scatter(hb, ht, s=60, color=C_ORA, marker="D", ec="white", lw=1.5, zorder=3, label="fine-scale actuator (emulator hacking)")
    ax[2].plot([-20, 105], [-20, 105], color=INK2, lw=1, ls="--"); ax[2].text(5, 12, "AI is honest on this line;\nbelow it, the AI over-promised", color=INK2, fontsize=9)
    ax[2].set_xlim(-20, 105); ax[2].set_ylim(-20, 105)
    ax[2].set_xlabel("damage avoided — what the AI PROMISED (%)"); ax[2].set_ylabel("damage avoided — what REALLY happened (%)")
    ax[2].set_title("The lie detector", fontsize=13, weight="bold", loc="left"); ax[2].legend(fontsize=9, loc="upper left")
    fig.tight_layout(); fig.savefig("outputs/fig_sweep.png", dpi=110); plt.close(fig)


# ---------------------------------------------------------------- 4. emulator diagnostics
def diagnostics():
    F = R["forecast"]; t = F["t"]
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.8))
    ax[0].plot(t, F["track_err"], color=C_EMU, marker="o", ms=5)
    ax[0].set_xlabel("forecast lead time"); ax[0].set_ylabel("storm-position error (storm radius ≈ 0.5)")
    ax[0].set_title("The AI is a decent forecaster…", fontsize=13, weight="bold", loc="left")
    shades = {"0.0001": "#9ec5f4", "0.001": "#3987e5", "0.01": "#184f95"}
    for e, r in R["response"].items():
        ax[1].plot(t, r["corr"], color=shades[e], marker="o", ms=5, label=f"nudge = {float(e)*100:g}% of storm energy")
    ax[1].axhline(0, color=INK2, lw=1)
    ax[1].set_ylim(-0.2, 1.05); ax[1].set_xlabel("lead time")
    ax[1].set_ylabel("correlation: AI's vs true response to a nudge")
    ax[1].set_title("…but does it feel the butterfly?", fontsize=13, weight="bold", loc="left"); ax[1].legend(fontsize=9)
    fig.tight_layout(); fig.savefig("outputs/fig_emulator.png", dpi=110); plt.close(fig)


if __name__ == "__main__":
    hero_static(); liar(); sweep(); diagnostics(); hero_animation()
    print("rendered")
