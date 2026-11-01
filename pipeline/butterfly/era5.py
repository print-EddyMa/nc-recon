"""Fetch ERA5 (Google ARCO, 0.25 deg, 37 levels) for NeuralGCM and regrid to the model grid."""
import time
import numpy as np, xarray as xr
from dinosaur import horizontal_interpolation, spherical_harmonic, xarray_utils
from .cases import WORK

ERA5 = "gs://gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3"


def _fetch(times, variables, path):
    if path.exists():
        return xr.open_dataset(path)
    t = time.time()
    ds = xr.open_zarr(ERA5, chunks=None, storage_options=dict(token="anon"))[variables].sel(time=list(times)).compute()
    ds.to_netcdf(path)
    print(f"ERA5: {len(variables)} vars x {len(times)} times in {time.time()-t:.0f}s", flush=True)
    return ds


def _regrid(ds, model):
    src = spherical_harmonic.Grid(
        latitude_nodes=ds.sizes["latitude"], longitude_nodes=ds.sizes["longitude"],
        latitude_spacing=xarray_utils.infer_latitude_spacing(ds.latitude),
        longitude_offset=xarray_utils.infer_longitude_offset(ds.longitude))
    rg = horizontal_interpolation.ConservativeRegridder(src, model.data_coords.horizontal, skipna=True)
    return xarray_utils.fill_nan_with_nearest(xarray_utils.regrid(ds, rg))


def model_inputs(model, case, tag):
    """(atmosphere at init, SST/sea-ice at the forcing times), each on `model`'s grid."""
    d = WORK / "era5"; d.mkdir(parents=True, exist_ok=True)
    key = case.init.replace(":", "").replace("-", "")
    atm = _fetch([np.datetime64(case.init)], model.input_variables, d / f"atm_{key}.nc")
    frc = _fetch([np.datetime64(t) for t in case.forcing_times], model.forcing_variables, d / f"frc_{key}.nc")
    out = []
    for name, ds in [("atm", atm), ("frc", frc)]:
        p = d / f"rg_{tag}_{name}_{key}.nc"
        if not p.exists():
            _regrid(ds, model).to_netcdf(p)
        out.append(xr.open_dataset(p))
    return out
