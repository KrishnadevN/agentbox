#!/usr/bin/env bash
# uv (official installer) into /usr/local/bin.
curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh
uv --version
