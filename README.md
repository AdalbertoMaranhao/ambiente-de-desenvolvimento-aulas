# Laboratórios Portáteis Offline (Kits Modulares)

Kits modulares e portáteis para aulas práticas de **Desenvolvimento Web** (PHP 8.5) e **Programação Orientada a Objetos** (Python 3.13 ou Java 25), integrados com **MariaDB 11.4**, Git e VS Code (com **SQLTools** offline).

Projetados para rodar em computadores de laboratório com **Windows 11 x64** e **Linux Mint 21/22 x64**, direto de um pendrive ou pasta do usuário:
* 🟢 **Sem instalação administrativa** (zero-admin).
* 🟢 **Sem conexão com a internet** (100% offline).
* 🟢 **Sem dependência de Docker, WSL ou serviços de sistema**.

---

## 1. Perfis Disponíveis

Os kits são gerados de forma especializada e independente:

| Perfil | Linguagem & Ferramentas | Foco Pedagógico | Tamanho Extraído | Tamanho Compactado |
| :--- | :--- | :--- | :---: | :---: |
| **`web`** | PHP 8.5 CLI/FrankenPHP, Composer 2.10, MariaDB 11.4, Git, VS Code + Intelephense + SQLTools | Aulas de Web, páginas dinâmicas e conexão com banco de dados | ~1,6 GB (Win) / ~3,7 GB (Lin) | ~550 MB (.zip) / ~600 MB (.tar.gz) |
| **`poo-python`** | CPython 3.13, pip, PyMySQL, MariaDB 11.4, Git, VS Code + Pylance + Debugpy + SQLTools | Aulas de POO em Python e persistência relacional | ~1,7 GB (Win) / ~3,7 GB (Lin) | ~500 MB (.zip) / ~550 MB (.tar.gz) |
| **`poo-java`** | Adoptium JDK 25 Hotspot, driver JDBC, MariaDB 11.4, Git, VS Code + Red Hat Java + Debugger + SQLTools | Aulas de POO em Java e conexão JDBC | ~1,9 GB (Win) / ~3,9 GB (Lin) | ~850 MB (.zip) / ~900 MB (.tar.gz) |

> [!NOTE]
> Cada kit deixa entre **4 GB e 6 GB livres** em qualquer pendrive padrão de 8 GB.

---

## 2. Como Usar o Pacote (Aluno)

1. Extraia o pacote (`.zip` no Windows ou `.tar.gz` no Linux) para uma pasta local do computador.
2. Inicie o laboratório:
   * **Windows:** dê duplo clique em `iniciar-windows.cmd`.
   * **Linux Mint:** dê duplo clique em `laboratorio.desktop` ou execute no terminal: `sh iniciar-linux.sh`.
3. Escolha uma opção no menu interativo:
   * **Opção 1:** Abre apenas o VS Code (aulas sem banco).
   * **Opção 2:** Abre o VS Code e inicia o MariaDB automaticamente (aulas com banco).
   * **Opção 3:** Abre terminal isolado com todas as ferramentas no `PATH`.
   * **Opção 4:** Diagnóstico e teste de funcionamento das ferramentas.
   * **Opção 5:** Salvar cópia de segurança (backup SQL do banco).
   * **Opção 6 / 0:** Parada segura do MariaDB (com backup automático preventivo).

### Credenciais Padrão do Banco de Dados
* **Host:** `127.0.0.1` | **Porta:** `3307` | **Banco padrão:** `aulas`
* **Usuário Comum:** `aluno` | **Senha:** `aluno`
* **Usuário Administrador:** `root` | **Senha:** `root`
* **Visualizador SQLTools no VS Code:** A conexão `Laboratório (MariaDB)` já vem pré-configurada na barra lateral do editor. Basta clicar para conectar e visualizar tabelas ou rodar queries.

### Servidor Web PHP (Kit Web)
* **No VS Code:** No menu superior, clique em `Terminal -> Run Task` (ou `Ctrl+Shift+B`) e selecione **"🌐 Iniciar Servidor Web PHP"**.
* **Pelo Terminal:** Execute `php -S 127.0.0.1:8080 -t .` dentro de `projetos/web`.
* Acesse no navegador: `http://127.0.0.1:8080/ola-mundo.php`.

---

## 3. Gerar e Montar os Kits (Professor)

O script mestre [`preparar.py`](file:///Users/adalberto/ambiente_de_desenvolvimento_portatil/preparar.py) orquestra a resolução, extração e compactação dos pacotes.

### Modo Interativo (com Menu)
Execute sem argumentos para abrir o assistente interativo:
```sh
python3 preparar.py
```

### Linha de Comando (Automação)
Você pode especificar diretamente a ação, perfil e sistema:
```sh
# Montar um kit específico
python3 preparar.py montar --perfil web --so windows
python3 preparar.py montar --perfil poo-python --so linux

# Montar todos os 6 kits
python3 preparar.py montar --perfil todos --so ambos

# Compactar os kits (gera .zip para Windows e .tar.gz para Linux)
python3 preparar.py zip --perfil web --so windows
python3 preparar.py zip --perfil todos --so ambos
```

Os arquivos finais são gerados no diretório `dist/`:
* `dist/kit-web-windows.zip`
* `dist/kit-web-linux.tar.gz`
* `dist/kit-poo-python-windows.zip`
* `dist/kit-poo-python-linux.tar.gz`
* `dist/kit-poo-java-windows.zip`
* `dist/kit-poo-java-linux.tar.gz`

---

## 4. Validação e Testes

Para auditar os pacotes montados e conferir dependências binárias (ELF / PE) e limites de tamanho:
```sh
# Inspecionar todos os pacotes em dist/
python3 verificar_pacote.py

# Inspecionar um pacote específico
python3 verificar_pacote.py dist/kit-web-windows
```

Para rodar a suíte de testes unitários do runtime:
```sh
PYTHONPYCACHEPREFIX=/tmp/kit-aulas-pycache python3 -m unittest discover -s tests -v
```
