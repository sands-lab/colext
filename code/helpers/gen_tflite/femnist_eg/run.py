from os import path

from .. import *
from . import FemnistModel

DIR = path.dirname(__file__)


TFLITE_FILE = f"cnn_femnist.tflite"


def main():
    model = FemnistModel()
    save_model(model, SAVED_MODEL_DIR)
    tflite_model = convert_saved_model(SAVED_MODEL_DIR)
    save_tflite_model(tflite_model, TFLITE_FILE)


main() if __name__ == "__main__" else None
