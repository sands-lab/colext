#!/bin/bash

docker buildx build --platform aarch64 --tag flserver:5000/colext/jetson-ox:latest --push \
                    -f python310_orin_xavier.Dockerfile .