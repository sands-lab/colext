import tensorflow as tf

from .. import *


def custom_fedprox_loss(y_true, y_pred, model, reg_constant):
    usual_loss = tf.keras.losses.categorical_crossentropy(y_true, y_pred)
    l2_regularization = 0.5 * reg_constant * tf.reduce_sum([tf.reduce_sum(tf.square(w)) for w in model.trainable_weights])
    total_loss = usual_loss + l2_regularization
    return total_loss
@tflite_model_class
class CIFAR10Model(BaseTFLiteModel):

    X_SHAPE = [32, 32, 3]
    Y_SHAPE = [10]

    def __init__(self, reg_constant=0.01):
        self.model = tf.keras.Sequential(
            [
                tf.keras.Input(shape=tuple(self.X_SHAPE)),
                tf.keras.layers.Conv2D(6, 5, activation="relu"),
                tf.keras.layers.MaxPooling2D(pool_size=(2, 2)),
                tf.keras.layers.Conv2D(16, 5, activation="relu"),
                tf.keras.layers.Flatten(),
                tf.keras.layers.Dense(units=120, activation="relu"),
                tf.keras.layers.Dense(units=84, activation="relu"),
                tf.keras.layers.Dense(units=10, activation="softmax"),
            ]
        )

        self.model.compile(loss=lambda y_true, y_pred: custom_fedprox_loss(y_true, y_pred, self.model, reg_constant),
                           optimizer="sgd")
