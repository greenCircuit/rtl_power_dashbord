#!/bin/bash
podman run -d -it --rm \
  --name rtl \
  --network host \
  -v ./:/app \
  -v ~/.gitconfig:/root/.gitconfig:ro \
  --device /dev/bus/usb:/dev/bus/usb \
  --replace \
  localhost/rtl /bin/bash
