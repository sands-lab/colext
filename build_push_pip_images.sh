#!/bin/bash

set -e # stop at first error

printvar() { 
  echo "$1 = ${!1}"
}

if [ $# -ne 2 ]; then
  echo "Number of arguments should be 2."
  echo "Script should be ran as: $0 <project_name> <absolute_user_code_path>"
  exit 1
fi

# Run commands as if launched on the script folder
cd "$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"/

PROJECT_NAME=$1
USER_CODE_PATH=$2
FLTB_PATH="/home/faustiar/fl-testbed/src/fltb"

REGISTY="kw61463:5000/fltestbed"
BUILD_ARG_USER_CODE_PATH="USER_CODE_PATH=${USER_CODE_PATH}"
BUILD_ARG_FLTB_PATH="FLTB_PATH=${FLTB_PATH}"

echo "Generating pip based docker images" 
echo "Using vars:" 
printvar PROJECT_NAME
printvar BUILD_ARG_USER_CODE_PATH
printvar BUILD_ARG_FLTB_PATH
printvar REGISTY

# MASSIVE HACK! Remove this asap
CONTEXT_PATH="/" 

echo 
echo "Building server image" 
docker build --platform linux/amd64 \
    --build-arg $BUILD_ARG_USER_CODE_PATH --build-arg $BUILD_ARG_FLTB_PATH \
    -f Dockerfiles/pip/fltb_server -t $REGISTY/${PROJECT_NAME}_server:latest --push $CONTEXT_PATH

echo 
echo "Building client image for aarch64" 
docker buildx build --platform linux/aarch64 \
    --build-arg $BUILD_ARG_USER_CODE_PATH --build-arg $BUILD_ARG_FLTB_PATH \
    -f Dockerfiles/pip/fltb_client_jetson -t $REGISTY/${PROJECT_NAME}_client_jetson:latest --push $CONTEXT_PATH

# echo 
# echo "Building client image for amd64" 
# # docker build --platform linux/amd64,linux/aarch64 \
# docker build --platform linux/amd64 \
#    --build-arg $BUILD_ARGS \    
#   -f Dockerfiles/pip/fltb__client -t $REGISTY/${PROJECT_NAME}__client:latest --push .