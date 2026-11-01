"""Load NeuralGCM checkpoints with a whitelist unpickler.

Static inspection (pickletools) showed the checkpoints reference only numpy's
array reconstructor, ndarray and dtype. We allow exactly those; any other
global in the file raises instead of executing."""
import pickle

ALLOWED = {
    ("numpy._core.multiarray", "_reconstruct"), ("numpy.core.multiarray", "_reconstruct"),
    ("numpy", "ndarray"), ("numpy", "dtype"),
}


class _Restricted(pickle.Unpickler):
    def find_class(self, module, name):
        if (module, name) in ALLOWED:
            return super().find_class(module, name)
        raise pickle.UnpicklingError(f"blocked global in checkpoint: {module}.{name}")


def load_checkpoint(path):
    with open(path, "rb") as f:
        return _Restricted(f).load()
