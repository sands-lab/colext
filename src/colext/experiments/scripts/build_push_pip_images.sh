#!/bin/bash

set -e # stop at first error

printvar() { 
  echo "$1 = ${!1}"
}

if [ $# -ne 3 ]; then
  echo "Number of arguments should be 3."
  echo "Script should be ran as: $0 <project_name> <absolute_user_code_path> <True|Default:False>"
  exit 1
fi

PROJECT_NAME=$1
USER_CODE_PATH=$2
TESTING=false

if [ "$3" = "True" ]
then
    TESTING=true
fi 

REGISTY="kw61463:5000/fltestbed"
BUILD_ARG_USER_CODE_PATH="USER_CODE_PATH=${USER_CODE_PATH}"

echo "Generating pip based docker images" 
echo "Using vars:" 
printvar REGISTY 
printvar PROJECT_NAME


# Run commands as if launched on the script folder
cd "$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"/


if [ "$TESTING" = true ] ; then
  echo 
  echo "Building generic image for testing locally (amd64) " 
  docker buildx build --platform linux/amd64 \
      --build-arg $BUILD_ARG_USER_CODE_PATH \
      -f Dockerfiles/pip/fltb_generic -t $REGISTY/${PROJECT_NAME}/generic:latest --push $USER_CODE_PATH

else
  echo 
  echo "Building generic image for LattePanda (amd64) and OrangePi(aarch64)" 
  docker buildx build --platform linux/amd64,linux/aarch64 \
      --build-arg $BUILD_ARG_USER_CODE_PATH \
      -f Dockerfiles/pip_w_install/fltb_generic -t $REGISTY/${PROJECT_NAME}/generic:latest --push $USER_CODE_PATH

  echo 
  echo "Building jetson image (aarch64)" 
  docker buildx build --platform linux/aarch64 \
      --build-arg $BUILD_ARG_USER_CODE_PATH --build-arg $BUILD_ARG_JETSON_BASE_IMAGE \
      -f Dockerfiles/pip_w_install/fltb_jetson -t $REGISTY/${PROJECT_NAME}/jetson:latest --push $USER_CODE_PATH
fi
