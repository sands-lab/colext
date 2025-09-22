#!/bin/bash

# docker buildx build --platform aarch64 --tag colext:5000/colext/jetson-ox:latest --push \
#                     -f python310_orin_xavier.Dockerfile .

# It runs much faster on the device!
docker buildx build --platform aarch64 --tag colext:5000/colext/jetson-nano:3.10 --push \
                    -f python310_nano.Dockerfile .