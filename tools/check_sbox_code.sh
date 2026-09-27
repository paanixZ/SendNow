#!/bin/sh
# Compile sbox/Code against the real s&box engine and run s&box's API whitelist verifier on it.
#   tools/check_sbox_code.sh            (builds the engine reference on first use)
#   SBOX_MANAGED=/path/to/game/bin/managed tools/check_sbox_code.sh
set -e
HERE=$(cd -- "$(dirname -- "$0")" && pwd)
if [ -z "$SBOX_MANAGED" ]; then
  SBOX_MANAGED=$("$HERE/build_sbox_reference.sh" | tail -1)
fi
export SBOX_MANAGED
echo "engine reference: $SBOX_MANAGED"
dotnet build "$HERE/sbox_compile_check/SboxCompileCheck.csproj" -v q -nologo
DLL="$HERE/sbox_compile_check/bin/Debug/net10.0/package.local.sourcebridge_tests.dll"
dotnet run --project "$HERE/sbox_whitelist_check/SboxWhitelistCheck.csproj" -- "$DLL"
