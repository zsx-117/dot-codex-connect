#!/bin/sh
set -eu
script_dir=$(CDPATH= cd -P -- "$(dirname -- "$0")" && pwd)
root=${DOT_CODEX_SOURCE:-$(CDPATH= cd -- "$script_dir/../../.." && pwd)}
if [ ! -f "$root/selfhost/server.mjs" ]; then
  printf '%s\n' 'Full source checkout required. Set DOT_CODEX_SOURCE to its absolute path.' >&2
  exit 1
fi
node_bin=${DOT_NODE_BIN:-node}
python_bin=${DOT_PYTHON_BIN:-python3}
case "${1:---check}" in
  --root) printf '%s\n' "$root";;
  --check)
    test -f "$root/selfhost/server.mjs"
    "$node_bin" -e 'if(Number(process.versions.node.split(".")[0])<24)process.exit(1);console.log("Node version supported")'
    "$python_bin" -c 'import sys; assert sys.version_info >= (3,12); print("Python version supported")'
    printf '%s\n' 'Source present. No account, network, daemon or credential changes.'
    ;;
  --test)
    cd "$root/selfhost"
    "$node_bin" --test test.mjs oauth.test.mjs oauth-route.test.mjs
    "$python_bin" ../scripts/test_python.py
    "$python_bin" ../scripts/test_source_build.py
    ;;
  *) printf '%s\n' 'Use --root, --check or --test. See docs/self-hosting.md for explicit source enrollment.' >&2; exit 2;;
esac
