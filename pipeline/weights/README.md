# General image model (flood and wind)

Groma's general image channel (E1) is the xView2 CMU baseline damage
classifier, run as ONNX on onnxruntime. It is not in git (500 MB, non-commercial
terms). Two ways to get `xview2_cmu_classifier.onnx` here:

1. **Docker (automatic).** `docker compose up -d --build` downloads the weights
   from the public release, checks the SHA-256 and converts them in a throwaway
   build stage. Nothing to do.
2. **Locally.**
   ```bash
   curl -L -o classification.hdf5 \
     https://github.com/DIUx-xView/xView2_baseline/releases/download/v1.0/classification.hdf5
   shasum -a 256 classification.hdf5   # a1f0dff601c8f3582b686ac7ce695f116d339e7913d1928d9ff62ab740e703cd
   # in a Python 3.11 env with tensorflow==2.15.1 tf2onnx==1.16.1 onnx==1.16.2:
   PYTHONPATH=../src python ../scripts/export_onnx.py classification.hdf5 xview2_cmu_classifier.onnx
   ```

Or point `NCR_MODEL_PATH` at an existing copy. Without it Groma still runs:
the E1 channel is reported off, and the wildfire model and the other evidence
channels carry the calls.
