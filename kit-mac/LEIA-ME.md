# Ambiente do Professor para macOS (kit-mac)

Esta pasta mantém a configuração do professor para computadores Apple Silicon (M1/M2/M3/M4), espelhando com **100% de paridade** as ferramentas, portas e configurações dos kits de alunos.

---

## 1. Configuração Inicial

1. Certifique-se de ter o [Homebrew](https://brew.sh/) instalado.
2. No Terminal, entre nesta pasta e execute:

```sh
./configurar.sh
```

O script:
* Instala/atualiza as ferramentas via `Brewfile` (Python 3.13, PHP 8.5, OpenJDK 25, MariaDB 11.4, VS Code).
* Instala as extensões essenciais do VS Code (incluindo Intelephense e SQLTools).
* Instala a biblioteca `PyMySQL`.
* Garante a presença do driver JDBC `mariadb-java-client.jar`.

---

## 2. Como Usar

### Painel Unificado (Menu Interativo)
Você pode usar a mesma interface dos alunos executando:
```sh
./lab.sh
```
Opções disponíveis:
* **Opção 1:** Abre o VS Code (permite escolher entre Web, POO Python ou POO Java).
* **Opção 2:** Inicia o MariaDB (porta 3307) e abre o VS Code.
* **Opção 3:** Abre terminal com `JAVA_HOME`, `PATH` e variáveis do banco prontas.
* **Opção 4:** Diagnóstico completo das ferramentas instaladas.
* **Opção 5:** Backup SQL do banco `aulas`.
* **Opção 6 / 0:** Parada segura do MariaDB.

---

## 3. Workspaces Modulares no VS Code

Abra o workspace específico da aula que estiver lecionando:
```sh
# Aulas de Web (PHP 8.5 & MariaDB)
code web.code-workspace

# Aulas de POO com Python
code poo-python.code-workspace

# Aulas de POO com Java
code poo-java.code-workspace
```

Todos os workspaces já incluem a conexão com o banco pré-configurada no **SQLTools**:
* **Host:** `127.0.0.1` | **Porta:** `3307` | **Banco:** `aulas`
* **Usuário Aluno:** `aluno` | **Senha:** `aluno`
* **Usuário Admin:** `root` | **Senha:** `root`

---

## 4. Servidor Web PHP (Kit Web)
* **No VS Code:** Pressione `Ctrl+Shift+B` (ou `Terminal -> Run Task`) e selecione **"🌐 Iniciar Servidor Web PHP"**.
* **Pelo Terminal:** Execute dentro de `projetos/web`:
  ```sh
  php -S 127.0.0.1:8080 -t .
  ```
  Acesse no navegador: `http://127.0.0.1:8080/ola-mundo.php`.

---

## 5. Scripts Shell Diretos (Atalhos)
Se preferir não usar o menu `./lab.sh`:
* `./iniciar-mariadb.sh`: sobe o MariaDB na porta `3307` e garante o banco `aulas` e usuário `aluno`.
* `./parar-mariadb.sh`: faz backup automático e encerra o MariaDB.
* `./backup-mariadb.sh [nome_do_banco]`: gera backup SQL na pasta `backups/`.
* `source ./ambiente.sh`: injeta o Java 25, Python 3.13 e variáveis de banco na sessão atual do seu terminal.
