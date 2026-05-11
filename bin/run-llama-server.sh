#!/usr/bin/env bash
#
# Thin wrapper around `llama-server` (llama.cpp). Spawned by
# `bin/llm_up.py` with per-model flags built from the active
# profile entry. Edit here to add MACHINE-WIDE flags that apply to
# every llama-server we start (e.g. GPU layers, thread count,
# flash-attn). Per-model flags (port, model refs, ctx-size,
# embedding) come through as `"$@"`.
#
# Direct invocation for debugging:
#   bin/run-llama-server.sh --port 8080 --hf-repo X --hf-file Y
#
# Cache: weights are pulled by llama-server to its global cache
# (`~/.cache/llama.cpp/` or `$LLAMA_CACHE`). See specs/llm-profiles.md.

set -euo pipefail

# Machine-wide defaults. Uncomment / tune for your hardware:
#   --n-gpu-layers 999      # offload all layers to GPU (CUDA / Metal)
#   --threads "$(nproc)"    # CPU thread count
#   --flash-attn            # enable flash attention
#   --no-warmup             # skip the warmup decode

DEFAULTS=(
    --host 127.0.0.1
)

exec llama-server "${DEFAULTS[@]}" "$@"
