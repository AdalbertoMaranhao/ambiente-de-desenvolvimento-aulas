# Execute com `source ./ambiente.sh` para usar as versões e variáveis do laboratório neste terminal.
if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew não encontrado; execute ./configurar.sh primeiro." >&2
  return 1 2>/dev/null || exit 1
fi

BREW_ROOT=$(brew --prefix)
export JAVA_HOME="$BREW_ROOT/opt/openjdk@25/libexec/openjdk.jdk/Contents/Home"
export PATH="$BREW_ROOT/opt/openjdk@25/bin:$BREW_ROOT/opt/python@3.13/bin:$BREW_ROOT/opt/mariadb@11.4/bin:$BREW_ROOT/bin:$PATH"

# Variáveis do banco de dados idênticas às dos alunos
export DB_HOST="127.0.0.1"
export DB_PORT="3307"
export DB_NAME="aulas"
export DB_USER="aluno"
export DB_PASSWORD="aluno"
