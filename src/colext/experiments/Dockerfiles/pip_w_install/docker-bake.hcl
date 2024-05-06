// Variables are set in experiment_dispatcher.py
variable "REGISTY" {
  default = null
}

variable "PROJECT_NAME" {
  default = null
}

variable "BAKE_FILE_DIR" {
  default = null
}

variable "CONTEXT" {
  default = null
}

variable "INHERITANCE_TARGET" {
  default = null
}

group "default" {
  // targets = ["generic-gpu", "jetson-nano"]
  targets = ["generic-cpu", "generic-gpu", "jetson", "jetson-nano"]
}

target "prod-base" {
  ssh = ["default"]
  context = "${CONTEXT}"
  dockerfile = "${BAKE_FILE_DIR}/colext_general.Dockerfile"
}

target "test-base" {
  context = "${CONTEXT}"
  dockerfile = "${BAKE_FILE_DIR}/colext_test.Dockerfile"
}

target "generic-cpu" {
  inherits = ["${INHERITANCE_TARGET}"]
  args = {
    BASE_IMAGE: "python:3.8.10-slim-buster",
    INSTALL_OPTIONS: "",
    BUILD_TYPE: "generic-cpu"
  }

  platforms = ["linux/amd64", "linux/arm64"]
  tags = ["${REGISTY}/${PROJECT_NAME}/generic-cpu:latest"]
}

target "generic-gpu" {
  inherits = ["${INHERITANCE_TARGET}"]
  args = {
    BASE_IMAGE: "pytorch/pytorch:2.0.1-cuda11.7-cudnn8-runtime",
    INSTALL_OPTIONS: "",
    BUILD_TYPE: "generic-gpu"
  }

  platforms = ["linux/amd64"]
  tags = ["${REGISTY}/${PROJECT_NAME}/generic-gpu:latest"]
}

target "jetson" {
  inherits = ["${INHERITANCE_TARGET}"]
  args = {
    // BASE_IMAGE: "dustynv/pytorch:2.0-r35.4.1",
    BASE_IMAGE: "nvcr.io/nvidia/l4t-pytorch:r35.2.1-pth2.0-py3",
    INSTALL_OPTIONS: "[jetson]",
    BUILD_TYPE: "jetson"
  }
  platforms = ["linux/arm64"]
  tags = ["${REGISTY}/${PROJECT_NAME}/jetson:latest"]
}

target "jetson-nano" {
  inherits = ["jetson"]
  args = {
    BASE_IMAGE: "flserver:5000/colext/jetson-nano:torch1.10-r32.7.1-py38",
  }
  tags = ["${REGISTY}/${PROJECT_NAME}/jetson-nano:latest"]
}