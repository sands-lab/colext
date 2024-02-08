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
  targets = ["generic", "jetson"]
}

group "testing" {
  targets = ["generic-test", "jetson-test"]
}

target "generic-base" {
  ssh = ["default"]
  context = "${CONTEXT}"
  args = {
    BASE_IMAGE: "python:3.8.10-slim-buster",
    INSTALL_OPTIONS: ""
  }
  // platforms = ["linux/amd64", "linux/arm64"]
  platforms = ["linux/amd64"]
  tags = ["${REGISTY}/${PROJECT_NAME}/generic:latest"]
}

target "jetson-base" {
  ssh = ["default"]
  context = "${CONTEXT}"
  args = {
    BASE_IMAGE: "dustynv/pytorch:2.0-r35.4.1",
    INSTALL_OPTIONS: "[jetson]"
  }
  platforms = ["linux/arm64"]
  tags = ["${REGISTY}/${PROJECT_NAME}/jetson:latest"]
}

target "generic" {
  inherits = ["generic-base"]
  dockerfile = "${BAKE_FILE_DIR}/fltb_generic.Dockerfile"
}

target "jetson" {
  inherits = ["jetson-base"]
  dockerfile = "${BAKE_FILE_DIR}/fltb_jetson.Dockerfile"
}

target "generic-test" {
  inherits = ["generic-base"]
  dockerfile = "${BAKE_FILE_DIR}/fltb_test.Dockerfile"
}

target "jetson-test" {
  inherits = ["jetson-base"]
  dockerfile = "${BAKE_FILE_DIR}/fltb_test.Dockerfile"
}