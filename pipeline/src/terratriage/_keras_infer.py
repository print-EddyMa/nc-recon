"""Standalone: reconstruct the xView2 CMU baseline classifier faithfully, load
its weights-only HDF5, predict 4-class damage on a stack of 128x128x3 POST crops.

    python _keras_infer.py  classification.hdf5  crops.npy  pred.npy

The published `classification.hdf5` (Keras 2.2.5, weights-only) contains a
**ResNet50-v1** (original 2015 block layout: stride on the first 1x1 of each
stage, every conv carries a bias, layer names `res2a_branch2a` / `bn_conv1` ...).
TF2's `keras.applications.ResNet50` is v1.5 with different names and stride
placement, so it will not load these weights. We therefore rebuild ResNet50-v1
here, matching `keras_applications/resnet50.py` (v2.2.x) name-for-name, wrap it as
a submodel named `resnet50`, bolt on the 3-conv side branch + Dense head from
`model/model.py`, and load `by_name=True`.

Preprocessing matches `model/damage_inference.py`: ImageDataGenerator(rescale=1.4)
feeds the *raw* pixels (no caffe preprocess_input) to both branches; the 4-unit
output uses `relu`, argmax at inference.
"""
import sys

import numpy as np

WEIGHTS, INP, OUT = sys.argv[1], sys.argv[2], sys.argv[3]

import tensorflow as tf
from tensorflow.keras import layers
from tensorflow.keras.layers import (
    Activation, Add, BatchNormalization, Concatenate, Conv2D, Dense, Flatten,
    Input, MaxPooling2D,
)
from tensorflow.keras.models import Model

BN_AXIS = 3


def identity_block(x, kernel_size, filters, stage, block):
    f1, f2, f3 = filters
    cb = f"res{stage}{block}_branch"
    bb = f"bn{stage}{block}_branch"
    s = Conv2D(f1, (1, 1), name=cb + "2a")(x)
    s = BatchNormalization(axis=BN_AXIS, name=bb + "2a")(s)
    s = Activation("relu")(s)
    s = Conv2D(f2, kernel_size, padding="same", name=cb + "2b")(s)
    s = BatchNormalization(axis=BN_AXIS, name=bb + "2b")(s)
    s = Activation("relu")(s)
    s = Conv2D(f3, (1, 1), name=cb + "2c")(s)
    s = BatchNormalization(axis=BN_AXIS, name=bb + "2c")(s)
    s = Add()([s, x])
    return Activation("relu")(s)


def conv_block(x, kernel_size, filters, stage, block, strides=(2, 2)):
    f1, f2, f3 = filters
    cb = f"res{stage}{block}_branch"
    bb = f"bn{stage}{block}_branch"
    s = Conv2D(f1, (1, 1), strides=strides, name=cb + "2a")(x)   # v1: stride here
    s = BatchNormalization(axis=BN_AXIS, name=bb + "2a")(s)
    s = Activation("relu")(s)
    s = Conv2D(f2, kernel_size, padding="same", name=cb + "2b")(s)
    s = BatchNormalization(axis=BN_AXIS, name=bb + "2b")(s)
    s = Activation("relu")(s)
    s = Conv2D(f3, (1, 1), name=cb + "2c")(s)
    s = BatchNormalization(axis=BN_AXIS, name=bb + "2c")(s)
    sc = Conv2D(f3, (1, 1), strides=strides, name=cb + "1")(x)
    sc = BatchNormalization(axis=BN_AXIS, name=bb + "1")(sc)
    s = Add()([s, sc])
    return Activation("relu")(s)


def resnet50_v1(input_tensor):
    x = Conv2D(64, (7, 7), strides=(2, 2), padding="same", name="conv1")(input_tensor)
    x = BatchNormalization(axis=BN_AXIS, name="bn_conv1")(x)
    x = Activation("relu")(x)
    x = MaxPooling2D((3, 3), strides=(2, 2))(x)

    x = conv_block(x, 3, [64, 64, 256], 2, "a", strides=(1, 1))
    x = identity_block(x, 3, [64, 64, 256], 2, "b")
    x = identity_block(x, 3, [64, 64, 256], 2, "c")

    x = conv_block(x, 3, [128, 128, 512], 3, "a")
    for b in "bcd":
        x = identity_block(x, 3, [128, 128, 512], 3, b)

    x = conv_block(x, 3, [256, 256, 1024], 4, "a")
    for b in "bcdef":
        x = identity_block(x, 3, [256, 256, 1024], 4, b)

    x = conv_block(x, 3, [512, 512, 2048], 5, "a")
    x = identity_block(x, 3, [512, 512, 2048], 5, "b")
    x = identity_block(x, 3, [512, 512, 2048], 5, "c")
    return x


def build_model():
    inputs = Input(shape=(128, 128, 3), name="input_1")

    rn_in = Input(shape=(128, 128, 3))
    resnet = Model(rn_in, resnet50_v1(rn_in), name="resnet50")
    for lyr in resnet.layers:
        lyr.trainable = False

    x = Conv2D(32, (5, 5), padding="same", activation="relu", name="conv2d_1")(inputs)
    x = MaxPooling2D((2, 2), name="max_pooling2d_2")(x)
    x = Conv2D(64, (3, 3), padding="same", activation="relu", name="conv2d_2")(x)
    x = MaxPooling2D((2, 2), name="max_pooling2d_3")(x)
    x = Conv2D(64, (3, 3), padding="same", activation="relu", name="conv2d_3")(x)
    x = MaxPooling2D((2, 2), name="max_pooling2d_4")(x)
    x = Flatten(name="flatten_1")(x)

    r = Flatten(name="flatten_2")(resnet(inputs))

    c = Concatenate(name="concatenate_1")([x, r])
    c = Dense(2024, activation="relu", name="dense_1")(c)
    c = Dense(524, activation="relu", name="dense_2")(c)
    c = Dense(124, activation="relu", name="dense_3")(c)
    out = Dense(4, activation="relu", name="dense_4")(c)
    return Model(inputs, out)


def main():
    crops = np.load(INP).astype("float32") * 1.4  # ImageDataGenerator(rescale=1.4)
    model = build_model()
    model.load_weights(WEIGHTS, by_name=True)

    # sanity: how many weights actually got populated
    import h5py

    with h5py.File(WEIGHTS, "r") as h:
        want = set(h.keys()) | set(h["resnet50"].keys())
    print(f"h5 groups: {len(want)}", file=sys.stderr)

    pred = model.predict(crops, batch_size=32, verbose=0)
    np.save(OUT, pred.astype("float32"))
    hist = np.bincount(pred.argmax(1), minlength=4).tolist()
    print(f"ok: {pred.shape}  argmax hist (0..3) = {hist}")


if __name__ == "__main__":
    main()
