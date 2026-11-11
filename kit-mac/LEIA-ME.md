# Ambiente do Professor para macOS (kit-mac)

Esta pasta mantém a configuração do professor para computadores Apple Silicon (M1/M2/M3/M4), espelhando com **100% de paridade** as ferramentas e configurações dos kits dos alunos.

---

## 1. Configuração Inicial

1. Certifique-se de ter o [Homebrew](https://brew.sh/) instalado.
2. No Terminal, entre nesta pasta e execute:

```sh
./configurar.sh
```

O script:
* Instala/atualiza as ferramentas via `Brewfile` (Python 3.13, PHP 8.5, OpenJDK 25, VS Code).
* Instala as extensões essenciais e pedagógicas do VS Code (Intelephense, Red Hat Java, Error Lens, Indent Rainbow, Better Comments, Path Intellisense, Auto Rename Tag e Português pt-BR).

---

## 2. Como Usar

### Painel Unificado (Menu Interativo)
Você pode usar a interface do laboratório executando:
```sh
./lab.sh
```
Opções disponíveis:
* **Opção 1:** Abre o VS Code (permite escolher entre Web ou POO Java).
* **Opção 2:** Faz backup compactado (`.zip`) de todos os projetos em `backups/`.
* **Opção 3:** Diagnóstico completo das ferramentas (Doctor).
* **Opção 0:** Sair.

---

## 3. Workspaces Modulares no VS Code

Abra o workspace específico da aula que estiver lecionando:
```sh
# Aulas de Desenvolvimento Web (PHP 8.5)
code web.code-workspace

# Aulas de POO com Java (Adoptium JDK 25)
code poo-java.code-workspace
```

---

## 4. Servidor Web PHP (Kit Web)
* **No VS Code:** Pressione `Ctrl+Shift+B` (ou `Terminal -> Run Task`) e selecione **"🌐 Iniciar Servidor Web PHP"**.
* **Pelo Terminal:** Execute dentro de `projetos/web`:
  ```sh
  php -S 127.0.0.1:8080 -t .
  ```
  Acesse no navegador: `http://127.0.0.1:8080/ola-mundo.php`.

---

## 5. Sessão do Terminal do macOS
Para injetar o Java 25 e as variáveis de ambiente na sessão atual do seu terminal:
```sh
source ./ambiente.sh
```
