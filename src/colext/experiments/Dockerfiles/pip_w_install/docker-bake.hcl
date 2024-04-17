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

group "default" {
  targets = ["generic-gpu", "jetson-nano"]
  // targets = ["generic-cpu", "generic-gpu", "jetson", "jetson-nano"]
}

group "testing" {
  // targets = ["generic-gpu-test", "jetson-nano-test"]
  targets = ["generic-cpu-test", "generic-gpu-test", "jetson-test", "jetson-nano-test"]
}

target "base" {
  ssh = ["default"]
  context = "${CONTEXT}"
  dockerfile = "${BAKE_FILE_DIR}/colext_general.Dockerfile"
}

target "test-override" {
  dockerfile = "${BAKE_FILE_DIR}/colext_test.Dockerfile"
}

target "generic-cpu" {
  inherits = ["base"]
  args = {
    BASE_IMAGE: "python:3.8.10-slim-buster",
    INSTALL_OPTIONS: "",
    BUILD_TYPE: "generic-cpu"
  }

  platforms = ["linux/amd64", "linux/arm64"]
  tags = ["${REGISTY}/${PROJECT_NAME}/generic-cpu:latest"]
}

target "generic-gpu" {
  inherits = ["base"]
  args = {
    BASE_IMAGE: "pytorch/pytorch:2.0.1-cuda11.7-cudnn8-runtime",
    INSTALL_OPTIONS: "",
    BUILD_TYPE: "generic-gpu"
  }

  platforms = ["linux/amd64"]
  tags = ["${REGISTY}/${PROJECT_NAME}/generic-gpu:latest"]
}

target "jetson" {
  inherits = ["base"]
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

target "generic-cpu-test" {
  inherits = ["generic-cpu", "test-override"]
  # Override platforms to ignore arm64
  // platforms = ["linux/amd64"]
}

target "generic-gpu-test" {
  inherits = ["generic-gpu", "test-override"]
}

target "jetson-test" {
  inherits = ["jetson", "test-override"]
}

target "jetson-nano-test" {
  inherits = ["jetson-nano", "test-override"]
}