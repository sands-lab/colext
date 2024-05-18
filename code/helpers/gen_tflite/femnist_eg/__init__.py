from .. import *
import tensorflow as tf
from keras import layers, models


@tflite_model_class
class FemnistModel(BaseTFLiteModel):
    X_SHAPE = [28, 28, 3]
    Y_SHAPE = [62]

    def __init__(self):

        self.model = tf.keras.Sequential([
            tf.keras.Input(shape=tuple(self.X_SHAPE)),
            tf.keras.layers.Conv2D(32, (5, 5), padding='same', activation='relu'),
            tf.keras.layers.MaxPooling2D((2, 2)),
            tf.keras.layers.Conv2D(64, (5, 5), padding='same', activation='relu'),
            tf.keras.layers.MaxPooling2D((2, 2), strides=2),
            tf.keras.layers.Flatten(),
            tf.keras.layers.Dense(2048, activation='relu'),
            tf.keras.layers.Dense(62, activation="softmax"),
        ])

        self.model.compile(loss="categorical_crossentropy", optimizer="adam", metrics=["accuracy"])

        self.model.summary()
