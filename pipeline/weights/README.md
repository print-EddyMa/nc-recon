# General image model (flood and wind)

Groma's general image channel (E1) is the xView2 CMU baseline damage
classifier (BSD-3, `licenses/xview2-baseline-BSD-3.txt`), run as ONNX on
onnxruntime. It is not in git (474 MB). Get `xview2_cmu_classifier.onnx` here:

1. **Docker (automatic).** `docker compose up -d --build` downloads it from the
   `model-general-v1` release and checks the SHA-256. Nothing to do.
2. **Locally.**
   ```bash
   curl -L -o xview2_cmu_classifier.onnx \
     https://github.com/print-EddyMa/nc-recon/releases/download/model-general-v1/xview2_cmu_classifier.onnx
   shasum -a 256 xview2_cmu_classifier.onnx   # 711fbdd47d99c4e1d5e7d6a84ec5c8d1c8a5eaeb84ea90d1969e10cd02fdb18f
   ```

To rebuild it from the original Keras weights (needs TensorFlow 2.15.1,
tf2onnx 1.16.1 and about 5 GB of memory): download `classification.hdf5` from
the xView2 baseline v1.0 release (SHA-256
a1f0dff601c8f3582b686ac7ce695f116d339e7913d1928d9ff62ab740e703cd) and run
`python ../scripts/export_onnx.py classification.hdf5 xview2_cmu_classifier.onnx`.
The result is byte-identical to the release file.

Or point `NCR_MODEL_PATH` at an existing copy. Without it Groma still runs:
the E1 channel is reported off, and the wildfire model and the other evidence
channels carry the calls.
