"""
The differentiable problem: ERA5 initial state -> NeuralGCM forecast -> impact on an NC region.

Perturbations live in the *observable* space (ERA5 pressure-level temperature,
winds and humidity at the initial time) and are measured with the moist
total-energy norm (Ehrendorfer et al. 1999), as used for ECMWF singular vectors:
    E = 1/2 sum [u'^2 + v'^2 + (cp/Tr) T'^2 + (L^2/(cp Tr)) q'^2] * mass
"""
import numpy as np, jax, jax.numpy as jnp, neuralgcm
from .safe_load import load_checkpoint
from .era5 import model_inputs
from .cases import WORK
from .storm import gc_dist_km, region_weight

CP, TR, LV, G, A = 1004.0, 270.0, 2.5e6, 9.81, 6.371e6
PERTURB = ["temperature", "u_component_of_wind", "v_component_of_wind", "specific_humidity"]
CHECKPOINT_URL = "gs://neuralgcm/models/v1/{name}.pkl"
# Nudges (and the sensitivity map) are restricted to the troposphere. Above it,
# the energy norm's per-mass weighting piles a steepest-descent direction into
# the near-massless top levels: a first version put 0.5 g/kg of water vapour at
# 1 hPa (130x the local value), which broke the model rather than steering it.
TROPOSPHERE_TOP_HPA = 200


def load_model(name):
    path = WORK / "models" / f"{name}.pkl"
    if not path.exists():
        raise SystemExit(f"missing {path}. Download it with:\n  gsutil cp {CHECKPOINT_URL.format(name=name)} {path}")
    return neuralgcm.PressureLevelModel.from_checkpoint(load_checkpoint(path))


class Problem:
    def __init__(self, case, name="deterministic_2_8_deg"):
        self.case, self.name = case, name
        m = self.model = load_model(name)
        atm, frc = model_inputs(m, case, tag=name)
        self.inputs = m.inputs_from_xarray(atm.isel(time=0))
        self.f0 = m.forcings_from_xarray(frc.isel(time=0))       # encode() adds its own time axis
        self.fall = m.forcings_from_xarray(frc)
        g = m.data_coords.horizontal
        self.lon, self.lat = np.rad2deg(np.asarray(g.longitudes)), np.rad2deg(np.asarray(g.latitudes))
        self.levels = np.asarray(m.data_coords.vertical.centers, dtype=float)
        self.k = {p: int(np.argmin(np.abs(self.levels - p))) for p in (300, 500, 850, 925)}
        self.trop = (self.levels >= TROPOSPHERE_TOP_HPA).astype(np.float32)
        LON, LAT = np.meshgrid(self.lon, self.lat, indexing="ij")
        self.mask = (gc_dist_km(case.storm0[0], case.storm0[1], LAT, LON) > case.keep_out_km).astype(np.float32)
        self.W = jnp.asarray(region_weight(self.lon, self.lat, case.target, case.radius_km))
        dp = np.abs(np.gradient(self.levels)) * 100.0
        area = A ** 2 * np.cos(np.deg2rad(LAT)) * np.deg2rad(self.lon[1] - self.lon[0]) * \
            np.abs(np.gradient(np.deg2rad(self.lat)))[None, :]
        self.dp = jnp.asarray(dp, dtype=jnp.float32)
        self.wmass = (dp[:, None, None] / G) * area[None]
        self.coef = {"u_component_of_wind": 1.0, "v_component_of_wind": 1.0,
                     "temperature": CP / TR, "specific_humidity": LV ** 2 / (CP * TR)}
        self.key = jax.random.key(0)
        self.window_idx = np.array(case.window) // case.every
        self._grad = jax.jit(jax.value_and_grad(self._objective_ckpt))
        self.forecast = jax.jit(self._forecast)

    # ---- impact field: what the objective measures at one time --------------------------
    def impact_field(self, out):
        """out: decoded outputs at one time ([level, lon, lat] arrays) -> [lon, lat] field."""
        u, v = out["u_component_of_wind"], out["v_component_of_wind"]
        if self.case.objective == "wind":
            k9, k8 = self.k[925], self.k[850]
            return 0.5 * (u[k9] ** 2 + v[k9] ** 2 + u[k8] ** 2 + v[k8] ** 2)
        # integrated vapour transport, 1000-300 hPa (kg m^-1 s^-1)
        q = out["specific_humidity"]
        sel = self.levels >= 300
        w = (self.dp * sel)[:, None, None] / G
        ivx, ivy = jnp.sum(q * u * w, 0), jnp.sum(q * v * w, 0)
        return jnp.sqrt(ivx ** 2 + ivy ** 2 + 1e-6)

    def score(self, field):
        return jnp.sum(field * self.W) / jnp.sum(self.W)

    # ---- model ------------------------------------------------------------------------
    def perturbed(self, delta):
        out = dict(self.inputs)
        for k, d in delta.items():
            out[k] = self.inputs[k] + d
        out["specific_humidity"] = jnp.maximum(out["specific_humidity"], 0.0)
        return out

    def _forecast(self, delta):
        """6-hourly decoded outputs (time 0 .. case.hours)."""
        state = self.model.encode(self.perturbed(delta), self.f0, self.key)
        _, preds = self.model.unroll(state, self.fall, steps=self.case.hours // self.case.every + 1,
                                     timedelta=np.timedelta64(self.case.every, "h"), start_with_input=True)
        return preds

    def objective_from(self, preds):
        fields = [self.impact_field({k: v[i] for k, v in preds.items()}) for i in self.window_idx]
        return float(np.mean([self.score(f) for f in fields]))

    def _objective_ckpt(self, delta):
        """Mean impact over the window, stepped hour by hour with gradient checkpointing:
        backprop stores one model state per hour and recomputes the rest (plain
        backprop through 78 h would need ~124 GB)."""
        m = self.model
        state = m.encode(self.perturbed(delta), self.f0, self.key)

        @jax.checkpoint
        def hour(st, _):
            st, out = m.unroll(st, self.fall, steps=1, timedelta=np.timedelta64(1, "h"), start_with_input=False)
            return st, self.score(self.impact_field({k: v[0] for k, v in out.items()}))

        _, s = jax.lax.scan(hour, state, None, length=self.case.hours)    # s[h-1] = impact at hour h
        return jnp.mean(s[np.array(self.case.window) - 1])

    def gradient(self, delta=None):
        """(J, dJ/d initial state) at the initial state + delta (zero by default)."""
        d = {k: jnp.asarray(delta[k]) if delta is not None and k in delta else jnp.zeros_like(self.inputs[k])
             for k in PERTURB}
        J0, g = self._grad(d)
        return float(J0), {k: np.asarray(v) for k, v in g.items()}

    # ---- norms / nudges ---------------------------------------------------------------
    def energy(self, delta):
        return float(sum(0.5 * self.coef[k] * np.sum(self.wmass * np.asarray(d) ** 2) for k, d in delta.items()))

    def descent_direction(self, grad):
        """Steepest-descent direction of the objective in the energy norm, tropospheric only,
        masked away from the storm."""
        m = self.mask[None] * self.trop[:, None, None]
        return {k: -np.asarray(grad[k]) * m / (self.coef[k] * self.wmass) for k in PERTURB}
