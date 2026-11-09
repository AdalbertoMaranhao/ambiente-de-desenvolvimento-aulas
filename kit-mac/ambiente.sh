# Execute com `source ./ambiente.sh` para usar as versões e variáveis do laboratório neste terminal.
if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew não encontrado; execute ./configurar.sh primeiro." >&2
  return 1 2>/dev/null || exit 1
fi

BREW_ROOT=$(brew --prefix)
export JAVA_HOME="$BREW_ROOT/opt/openjdk@25/libexec/openjdk.jdk/Contents/Home"
export PATH="$BREW_ROOT/opt/openjdk@25/bin:$BREW_ROOT/opt/python@3.13/bin:$BREW_ROOT/bin:$PATH"
