"""Confirm the reconstructed baseline classifier actually received the HDF5
weights (by_name=True skips silently on any mismatch, so we check tensor-equality
on a spread of layers)."""
import sys

import h5py
import numpy as np

_W = sys.argv[1] if len(sys.argv) > 1 else "weights/classification.hdf5"
sys.argv = [sys.argv[0], "", "", ""]
from _keras_infer import build_model  # noqa: E402

W = _W
m = build_model()
m.load_weights(W, by_name=True)
rn = m.get_layer("resnet50")
h = h5py.File(W, "r")


def ref(group, layer, wtail):
    g = h[group][layer] if group else h[layer]
    found = []
    g.visititems(lambda n, o: found.append(o) if hasattr(o, "shape") and n.endswith(wtail) else None)
    if not found:
        raise KeyError(f"{group}/{layer}/{wtail}")
    return np.array(found[0])


def cur(layer_obj, wtail):
    for wv in layer_obj.weights:
        if wv.name.split("/")[-1].startswith(wtail):
            return wv.numpy()
    return None


cases = [
    ("resnet50", "conv1", "kernel"),
    ("resnet50", "res3a_branch1", "kernel"),
    ("resnet50", "res5c_branch2c", "kernel"),
    ("resnet50", "bn5c_branch2c", "gamma"),
    (None, "conv2d_1", "kernel"),
    (None, "conv2d_3", "kernel"),
    (None, "dense_1", "kernel"),
    (None, "dense_4", "bias"),
]
allok = True
for grp, lname, wtail in cases:
    r = ref(grp, lname, wtail + ":0")
    lyr = rn.get_layer(lname) if grp else m.get_layer(lname)
    c = cur(lyr, wtail)
    ok = c is not None and c.shape == r.shape and np.allclose(c, r, atol=1e-6)
    allok &= ok
    d = "n/a" if c is None else f"{np.abs(c - r).max():.2e}"
    print(f"  {lname:20s} {str(r.shape):20s} loaded={ok}  maxΔ={d}")
h.close()
print("ALL LAYERS MATCH HDF5" if allok else "!! SOME LAYERS DID NOT LOAD")
sys.exit(0 if allok else 1)
