#!/bin/sh
set -eu

export PATH="/opt/homebrew/opt/openjdk@25/bin:/opt/homebrew/opt/python@3.13/bin:/opt/homebrew/bin:$PATH"
export JAVA_HOME="/opt/homebrew/opt/openjdk@25/libexec/openjdk.jdk/Contents/Home"

echo "Computador: $(scutil --get ComputerName 2>/dev/null || hostname)"
echo "Arquitetura: $(uname -m)"
echo "macOS: $(sw_vers -productVersion) ($(sw_vers -buildVersion))"
echo
for tool in brew git python3.13 php composer java sqlite3 code; do
  if command -v "$tool" >/dev/null 2>&1; then
    case "$tool" in
      java) version=$(java -version 2>&1 | head -n 1) ;;
      php) version=$(php -v | head -n 1) ;;
      brew) version=$(brew --version | head -n 1) ;;
      *) version=$("$tool" --version 2>&1 | head -n 1 || true) ;;
    esac
    printf '%-12s %s\n' "$tool" "$version"
  else
    printf '%-12s %s\n' "$tool" "nao encontrado"
  fi
done
echo
if command -v brew >/dev/null 2>&1; then
  echo "Formulae relevantes:"
  brew list --versions git python@3.13 php composer openjdk@25 sqlite 2>/dev/null || true
fi
if command -v code >/dev/null 2>&1; then
  echo
  echo "Extensoes do VS Code:"
  code --list-extensions --show-versions 2>/dev/null || true
fi
