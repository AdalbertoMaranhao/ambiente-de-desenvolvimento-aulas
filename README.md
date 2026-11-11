# Laboratórios Portáteis Universais (Kits Híbridos Dual-OS)

Kits modulares e universais para aulas práticas de **Desenvolvimento Web** (PHP 8.5) e **Programação Orientada a Objetos** (Python 3.13 ou Java 25), integrados com **SQLite 3**, Git e VS Code (com extensão **SQLite Viewer** offline).

Projetados para rodar a partir do **mesmo pendrive** tanto em computadores com **Windows 11 x64** quanto com **Linux Mint 21/22 x64**, sem necessidade de reiniciar a máquina e sem transferências manuais de arquivos:
* 🟢 **Zero Configuração & Zero Admin:** Funciona sem privilégios de administrador.
* 🟢 **Zero Conflito de Portas:** O SQLite elimina 100% dos erros de serviços e portas de rede (`3307`).
* 🟢 **Interoperabilidade Total:** Modificações no banco de dados (`banco.db`) e preferências do VS Code feitas no Windows são lidas instantaneamente no Linux e vice-versa.
* 🟢 **100% Offline:** Sem dependência de internet, Docker ou WSL.

---

## 1. Kits Universais Disponíveis

Cada kit é especializado por disciplina e contém os binários de **ambos os sistemas operacionais** compartilhando uma única pasta `projetos/` e o mesmo `banco.db`:

| Kit Universal | Ferramentas Integradas (Win + Linux) | Foco Pedagógico | Tamanho Extraído | Tamanho do Pacote (.zip) |
| :--- | :--- | :--- | :---: | :---: |
| **`kit-web`** | PHP 8.5 (Win) / FrankenPHP (Lin), Composer, SQLite, Git, VS Code + Intelephense + SQLite Viewer + Extensões Pedagógicas | Aulas de Web, páginas dinâmicas e persistência com PDO SQLite | ~3,4 GB | ~1,2 GB |
| **`kit-poo-python`** | CPython 3.13, pip, SQLite nativo, Git, VS Code + Pylance + Debugpy + SQLite Viewer + Extensões Pedagógicas | Aulas de POO em Python e persistência com `sqlite3` | ~3,4 GB | ~1,2 GB |
| **`kit-poo-java`** | Adoptium JDK 25 Hotspot, driver SQLite JDBC, Git, VS Code + Red Hat Java + Debugger + SQLite Viewer + Extensões Pedagógicas | Aulas de POO em Java e conexão JDBC | ~3,8 GB | ~1,5 GB |

> [!NOTE]
> * **Extensões Pedagógicas Incluídas em Todos os Kits:** *Error Lens* (diagnóstico inline imediato), *Indent Rainbow* (identação visual colorida), *Better Comments* (categorização visual de anotações), *Path Intellisense* (autocompletar caminhos de arquivos), *Auto Rename Tag* (fechamento automático de tags HTML/XML) e *Language Pack em Português (Brasil)*.
> * **Ambiente Focado e Sem Distrações:** Todos os assistentes de IA (Copilot, Chat IA e sugestões inline automáticas) vêm **desabilitados por padrão** (`chat.disableAIFeatures: true`), garantindo a integridade pedagógica e a autonomia no aprendizado do código.
> * Cada kit universal extraído deixa mais de **4 GB livres** em qualquer pendrive padrão de 8 GB (formatado em exFAT ou FAT32).

---

## 2. Como Usar o Kit (Aluno)

Consulte o [Guia Completo do Aluno](GUIA-DO-ALUNO.md) para imprimir ou compartilhar no portal de aulas.

1. Extraia o arquivo `.zip` da sua disciplina diretamente no pendrive ou em uma pasta local do computador.
2. Dê duplo clique no lançador correspondente ao sistema da máquina:
   * **No Windows:** Abra `Iniciar <Disciplina>.cmd` (ex: `Iniciar Web.cmd`).
   * **No Linux Mint:** Abra `Iniciar <Disciplina>.desktop` (ou execute `./iniciar-linux.sh`).
3. O VS Code abrirá com seu projeto carregado e as extensões prontas.

### Testando Códigos de Exemplo
* **Web (PHP):** Pressione `Ctrl+Shift+B` (ou `Terminal -> Run Task`) e escolha **"🌐 Iniciar Servidor Web PHP"**. Acesse `http://127.0.0.1:8080/ola-mundo.php`.
* **Java:** Abra `src/OlaMundo.java` e clique no botão `Run` acima de `main` (ou ▶ no IntelliJ).

---

## 3. Gerar os Pacotes Universais (Professor)

O script [`preparar.py`](file:///Users/adalberto/ambiente_de_desenvolvimento_portatil/preparar.py) automatiza a montagem dos kits universais:

```sh
# Montar os kits universais em dist/
python3 preparar.py montar

# Compactar os kits em arquivos .zip universais
python3 preparar.py zip

# Ou fazer tudo em um comando só
python3 preparar.py tudo
```

Os pacotes gerados ficam na pasta `dist/`:
* `dist/kit-web.zip`
* `dist/kit-poo-java.zip`

---

## 4. Gravar o Kit Diretamente no Pendrive

O utilitário [`gravar_pendrive.py`](file:///Users/adalberto/ambiente_de_desenvolvimento_portatil/gravar_pendrive.py) detecta automaticamente pendrives/mídias removíveis conectadas no macOS, Linux ou Windows, confere o hash SHA-256 de integridade e extrai o kit pronto para a aula:

```sh
# Modo interativo (detecta pendrives e exibe opções na tela)
python3 gravar_pendrive.py

# Ou via preparador
python3 preparar.py gravar

# Modo direto por argumentos
python3 gravar_pendrive.py --kit web --destino /Volumes/MEUPENDRIVE
# No Windows: python gravar_pendrive.py --kit web --destino E:\
```

---

## 5. Ambiente do Professor no macOS (`kit-mac`)

Para professores que utilizam macOS (Apple Silicon):
1. Acesse a pasta `kit-mac/` e execute:
   ```sh
   sh configurar.sh
   ```
2. Abra os workspaces dedicados no VS Code:
   * `code web.code-workspace`
   * `code poo-python.code-workspace`
   * `code poo-java.code-workspace`
3. Ou utilize o painel: `python3 lab.py`.

---

## 6. Validação e Testes Automatizados

Para executar todas as validações de uma só vez (testes unitários e inspeção de pacotes):

```sh
# No Linux ou macOS:
./testar.sh

# No Windows:
testar.cmd
```

Ou execute os passos individualmente:

```sh
# Testes unitários (26 testes)
python3 -m unittest discover -s tests -v

# Auditoria estática de binários (PE/ELF) e folga de espaço no pendrive
python3 verificar_pacote.py
```
