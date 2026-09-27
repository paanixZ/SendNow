#!/bin/sh
# Build the managed s&box engine from Facepunch/sbox-public for compile-only checks on Linux.
# Pinned to the commit the templates in templates/sbox/reference were taken from.
#
#   tools/build_sbox_reference.sh [workdir]      -> prints the SBOX_MANAGED directory
#
# The official ./Setup.sh downloads prebuilt native artifacts from artifacts.sbox.game.
# Compile checks do not need native code, so this script only generates the interop
# bindings and builds Sandbox.Engine. System.Speech (a Windows-only reference the engine
# ships in ThirdParty) is taken from the official NuGet package, only to satisfy the compiler.
set -e
COMMIT=372c601f8332149851410d88f36c0184bcb988f1
WORK=${1:-${SBOX_REFERENCE_DIR:-$HOME/sbox-reference}}
mkdir -p "$WORK"
if [ ! -d "$WORK/sbox-public/.git" ]; then
  git clone --filter=blob:none --no-checkout https://github.com/Facepunch/sbox-public "$WORK/sbox-public" >&2
fi
cd "$WORK/sbox-public"
git sparse-checkout set engine >&2
git fetch --quiet origin "$COMMIT" >&2 || true
git -c advice.detachedHead=false checkout --quiet "$COMMIT" >&2

mkdir -p "$WORK/interop"
cat > "$WORK/interop/interop.csproj" <<XML
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings></PropertyGroup>
  <ItemGroup><ProjectReference Include="$WORK/sbox-public/engine/Tools/InteropGen/InteropGen.csproj" /></ItemGroup>
</Project>
XML
cat > "$WORK/interop/Program.cs" <<CS
Directory.SetCurrentDirectory("$WORK/sbox-public");
return Facepunch.InteropGen.Program.ProcessManifest("engine", true) ? 0 : 1;
CS
dotnet run --project "$WORK/interop" >&2

if [ ! -s engine/ThirdParty/System.Speech.dll ]; then
  mkdir -p "$WORK/speech"
  curl -sSL -o "$WORK/speech/s.nupkg" https://api.nuget.org/v3-flatcontainer/system.speech/9.0.0/system.speech.9.0.0.nupkg
  (cd "$WORK/speech" && unzip -o -q s.nupkg)
  cp "$WORK/speech/lib/net9.0/System.Speech.dll" engine/ThirdParty/System.Speech.dll
fi
dotnet build engine/Sandbox.Engine/Sandbox.Engine.csproj -c Release -v q -nologo >&2
echo "$WORK/sbox-public/game/bin/managed"
