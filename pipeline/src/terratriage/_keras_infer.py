"""Standalone: reconstruct the xView2 CMU baseline classifier, load its
weights-only HDF5, predict on a stack of 128x128x3 POST crops.

Run by `classify._keras_scores` with the `terratriage-tf` conda env's python:
    python _keras_infer.py  classification.hdf5  crops.npy  pred.npy

Mirrors model/model.py + model/damage_inference.py from DIUx-xView/xView2_baseline
(rescale=1.4, ResNet50 imagenet frozen, 4-unit relu output -> argmax).
"""
import sys

import numpy as np

WEIGHTS, INP, OUT = sys.argv[1], sys.argv[2], sys.argv[3]

try:
    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras.layers import (
        Conv2D, MaxPooling2D, Dense, Flatten, Input, Concatenate,
    )
    from tensorflow.keras.models import Model
    from tensorflow.keras.applications.resnet50 import ResNet50
except Exception as ex:  # pragma: no cover
    print("tensorflow import failed:", ex, file=sys.stderr)
    raise


def build_model():
    inputs = Input(shape=(128, 128, 3))
    base_model = ResNet50(include_top=False, weights="imagenet", input_shape=(128, 128, 3))
    for layer in base_model.layers:
        layer.trainable = False

    x = Conv2D(32, (5, 5), strides=(1, 1), padding="same", activation="relu")(inputs)
    x = MaxPooling2D(pool_size=(2, 2), padding="valid")(x)
    x = Conv2D(64, (3, 3), strides=(1, 1), padding="same", activation="relu")(x)
    x = MaxPooling2D(pool_size=(2, 2), padding="valid")(x)
    x = Conv2D(64, (3, 3), strides=(1, 1), padding="same", activation="relu")(x)
    x = MaxPooling2D(pool_size=(2, 2), padding="valid")(x)
    x = Flatten()(x)

    base_resnet = base_model(inputs)
    base_resnet = Flatten()(base_resnet)

    c = Concatenate()([x, base_resnet])
    c = Dense(2024, activation="relu")(c)
    c = Dense(524, activation="relu")(c)
    c = Dense(124, activation="relu")(c)
    out = Dense(4, activation="relu")(c)
    return Model(inputs=inputs, outputs=out)


def main():
    crops = np.load(INP).astype("float32") * 1.4  # reference ImageDataGenerator(rescale=1.4)
    model = build_model()
    try:
        model.load_weights(WEIGHTS)
    except Exception as ex:
        print("strict load_weights failed, retrying by_name=True, skip_mismatch=True:", ex, file=sys.stderr)
        model.load_weights(WEIGHTS, by_name=True, skip_mismatch=True)
    pred = model.predict(crops, batch_size=32, verbose=0)
    np.save(OUT, pred.astype("float32"))
    print(f"ok: {pred.shape} argmax hist = {np.bincount(pred.argmax(1), minlength=4).tolist()}")


if __name__ == "__main__":
    main()
