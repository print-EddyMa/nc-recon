#!/usr/bin/env python
"""One-time conversion of the xView2 CMU baseline classifier to ONNX.

Run in the TensorFlow conda env (the only place Keras 2.2.5-era weights can be
loaded faithfully):

    /opt/miniconda3/envs/terratriage-tf/bin/python scripts/export_onnx.py \
        weights/classification.hdf5 weights/xview2_cmu_classifier.onnx

The ONNX graph takes the *already rescaled* float32 crops (pixels x 1.4, NHWC
128x128x3) and returns the raw Dense(4, relu) activations - exactly what
`_keras_infer.py` returns. Production then runs it with onnxruntime (CPU) in
the main venv, so no TensorFlow is needed at deploy time.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "src", "terratriage")

weights, out = sys.argv[1], sys.argv[2]
# _keras_infer reads its three argv slots at import; give it harmless ones
sys.argv = [sys.argv[0], weights, "-", "-"]
sys.path.insert(0, SRC)
import _keras_infer as ki  # noqa: E402

import tensorflow as tf  # noqa: E402
import tf2onnx  # noqa: E402

model = ki.build_model()
model.load_weights(weights, by_name=True)
spec = (tf.TensorSpec((None, 128, 128, 3), tf.float32, name="crops_x1p4"),)
tf2onnx.convert.from_keras(model, input_signature=spec, opset=13, output_path=out)
print(f"wrote {out}")
