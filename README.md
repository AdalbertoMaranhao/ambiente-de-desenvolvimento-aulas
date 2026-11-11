# Laboratórios Portáteis Universais (Provisionamento Local & Isolamento de Alunos)

Kits modulares e universais para aulas práticas de **Desenvolvimento Web** (PHP 8.5) e **Programação Orientada a Objetos** (Java 25 Adoptium), com arquitetura híbrida de alto desempenho: ferramentas provisionadas no SSD local, perfis individuais e isolados para cada aluno no VS Code da máquina e sincronização bidirecional inteligente (3-way sync) com preservação atômica do Git.

Projetados para rodar a partir do **mesmo pendrive** tanto em computadores com **Windows 11 x64** quanto com **Linux Mint 21/22 x64**, sem necessidade de reiniciar a máquina e sem transferências manuais de arquivos:
* 🟢 **Desempenho Nativo de SSD:** As ferramentas e o VS Code executam diretamente do armazenamento local da máquina (`%LOCALAPPDATA%\LaboratorioAulas` no Windows e `~/.local/share/laboratorio-aulas` no Linux Mint), eliminando lentidão de I/O de pendrives.
* 🟢 **Identificação e Isolamento Individual do Aluno:** Cada aluno possui sua pasta e perfil exclusivo de dados no VS Code (`--user-data-dir`), garantindo que diferentes alunos possam usar o mesmo computador sem conflitos ou vazamento de dados.
* 🟢 **Sincronização Inteligente de Projetos (3-Way Sync):** Sincronização automatizada entre o SSD local e o pendrive, com tolerância a falhas, gravação atômica, isolamento seguro de conflitos com timestamp e preservação integral de repositórios Git (`.git` completo: histórico, branches e tags).
* 🟢 **Zero Configuração & Zero Admin:** Funciona sem privilégios de administrador.
* 🟢 **Extensões VSIX Locais e Offline:** Extensões pedagógicas distribuídas pelo kit e instaladas no diretório local compartilhado da disciplina.
* 🟢 **100% Offline:** Sem dependência de internet, Docker ou WSL.

---

## 🧭 Mapa de Branches do Repositório

Este repositório está organizado em branches modulares para atender a diferentes necessidades pedagógicas:

| Branch | Arquitetura / Editor | Banco de Dados | Linguagens | Perfil de Uso |
| :--- | :--- | :---: | :--- | :--- |
| **`feature/vscode-sem-banco`** *(atual)* | Provisionamento Local + Perfis Isolados | *Nenhum* | PHP 8.5, Java 25 | **Nova Arquitetura:** Execução ultra rápida no SSD local, perfil individual de aluno, 3-way sync com Git |
| **`main`** | VS Code da Máquina (Execução Pendrive) | *Nenhum* | PHP 8.5, Java 25 | Execução portátil direta sem banco |
| **`feature/vscode-da-maquina`** | VS Code da Máquina | SQLite 3 | PHP 8.5, Java 25 | Para aulas que exigem persistência SQL sem peso de SGBD servidor |
| **`feature/intellij-java-windows`** | IntelliJ (Win) / VS Code (Lin) | SQLite 3 | PHP 8.5, Java 25 | Para turmas que utilizam a IDE IntelliJ IDEA Community no Windows |
| **`feature/vscode-portatil`** | VS Code Embutido no Pendrive | SQLite 3 | PHP 8.5, Python 3.13, Java 25 | Ambiente 100% independente (não exige VS Code instalado na máquina) |

---

## 1. Kits Universais Disponíveis nesta Branch

Cada kit é especializado por disciplina e contém os binários de **ambos os sistemas operacionais** compartilhando uma única pasta `projetos/`:

| Kit Universal | Ferramentas Integradas (Win + Linux) | Foco Pedagógico | Tamanho Extraído | Tamanho do Pacote (.zip) |
| :--- | :--- | :--- | :---: | :---: |
| **`kit-web`** | PHP 8.5 (Win) / FrankenPHP (Lin), Composer, Git, Extensões Pedagógicas | Aulas de Web, sintaxe PHP, formulários, páginas dinâmicas | **~1,23 GB** | **~496 MB** |
| **`kit-poo-java`** | Adoptium JDK 25 Hotspot, Git, VS Code Java Extension Pack + Extensões Pedagógicas | Aulas de POO em Java, encapsulamento, herança, polimorfismo | **~1,61 GB** | **~719 MB** |

> [!NOTE]
> * **Extensões Pedagógicas Incluídas em Todos os Kits:** *Error Lens* (diagnóstico inline imediato), *Indent Rainbow* (identação visual colorida), *Better Comments* (categorização visual de anotações), *Path Intellisense* (autocompletar caminhos de arquivos), *Auto Rename Tag* (fechamento automático de tags HTML/XML) e *Language Pack em Português (Brasil)*.
> * **Ambiente Focado e Sem Distrações:** Todos os assistentes de IA (Copilot, Chat IA e sugestões inline automáticas) vêm **desabilitados por padrão** (`chat.disableAIFeatures: true`), garantindo a integridade pedagógica e a autonomia no aprendizado do código.
> * Cada kit universal extraído deixa mais de **6 GB livres** em qualquer pendrive padrão de 8 GB.

---

## 2. Nova Arquitetura de Quatro Camadas

1. **Kit de Distribuição (Pendrive):** Transporte seguro e imutável das ferramentas, extensões `.vsix` e inicializadores.
2. **Ferramentas Provisionadas Localmente (SSD):** No primeiro uso, o kit provisiona as ferramentas da disciplina no SSD do computador (`%LOCALAPPDATA%\LaboratorioAulas` ou `~/.local/share/laboratorio-aulas`), compartilhadas entre os alunos da máquina para evitar cópias duplicadas.
3. **Perfil Pessoal do Aluno:** No primeiro uso, o aluno digita seu identificador (ex: `mariasilva` ou matrícula). Seu perfil do VS Code (tema, atalhos, snippets) fica isolado e apenas configurações permitidas (`User/settings.json`, `User/keybindings.json`, `snippets`) são sincronizadas com o pendrive (excluindo caches, logs e lixo de telemetria).
4. **Projetos do Aluno & Sincronização:** Os códigos são executados e compilados no SSD local para máxima velocidade e sincronizados bidirecionalmente com o pendrive através do algoritmo de 3 vias, preservando 100% o versionamento Git (`.git`).

---

## 3. Como Usar o Kit (Aluno)

Consulte o [Guia Completo do Aluno](GUIA-DO-ALUNO.md) para imprimir ou compartilhar no portal de aulas.

1. Conecte o pendrive no computador e abra a pasta do kit desejado:
   * **Web:** Abra a pasta `kit-web\`
   * **Java:** Abra a pasta `kit-poo-java\`
2. Dê duplo clique no inicializador correspondente ao sistema:
   * **No Windows:** Abra `iniciar-windows.cmd`
   * **No Linux Mint:** Abra `laboratorio.desktop` *(ou execute `./iniciar-linux.sh` no terminal)*
3. Na primeira inicialização, informe seu identificador de aluno (ex: `maria-silva`). Nas próximas vezes, seu ambiente será carregado imediatamente.
4. Escolha **1** para abrir o VS Code ou utilize o menu para sincronizar ou abrir o terminal.
5. Ao terminar, escolha a opção **0** no menu para salvar todos os seus arquivos e configurações no pendrive automaticamente!

### Testando Códigos de Exemplo
* **Web (PHP):** Pressione `Ctrl+Shift+B` (ou `Terminal -> Run Task`) e escolha **"🌐 Iniciar Servidor Web PHP"**. Acesse `http://127.0.0.1:8080/ola-mundo.php`.
* **Java:** Abra `src/OlaMundo.java` e clique no botão `Run` que aparece logo acima do método `main`.

---

## 3. Gerar os Pacotes Universais (Professor)

O script [`preparar.py`](file:///Users/adalberto/ambiente_de_desenvolvimento_portatil/preparar.py) automatiza o download de binários oficiais e a montagem dos kits universais:

```sh
# Montar e compactar os kits em dist/
python3 preparar.py tudo

# Ou por etapas:
python3 preparar.py montar
python3 preparar.py zip
```

Os pacotes gerados ficam na pasta `dist/`:
* `dist/kit-web.zip` (496 MB)
* `dist/kit-poo-java.zip` (719 MB)

---

## 4. Gravar o Kit Diretamente no Pendrive

O utilitário [`gravar_pendrive.py`](file:///Users/adalberto/ambiente_de_desenvolvimento_portatil/gravar_pendrive.py) (ou os atalhos [`Gravar-Pendrive.cmd`](file:///Users/adalberto/ambiente_de_desenvolvimento_portatil/Gravar-Pendrive.cmd) e [`gravar-pendrive.sh`](file:///Users/adalberto/ambiente_de_desenvolvimento_portatil/gravar-pendrive.sh)) grava os pacotes em alta velocidade:

```sh
# Modo interativo (detecta pendrives, exibe opções e barra de progresso)
python3 gravar_pendrive.py

# Gravação direta especificando parâmetros
python3 gravar_pendrive.py --kit web --destino /Volumes/MEUPENDRIVE
# No Windows: python gravar_pendrive.py --kit web --destino E:\
```

### Recursos do Gravador:
* **Barra de Progresso Visual:** Acompanhamento em tempo real (UTF-8 com blocos `█░` e fallback ASCII `=-`) para cálculo de SHA-256 e extração.
* **Gravação em Subpasta:** O kit é gravado em pasta dedicada (`E:\kit-web\` ou `E:\kit-poo-java\`), criando automaticamente o arquivo `LEIA-ME.txt` na raiz com orientações para os alunos.
* **Diagnóstico e Formatação Otimizada:** Detecta pendrives em formato subótimo (ex.: FAT32 tradicional) e oferece formatar em **exFAT com cluster de 128 KB** (rótulo `AULAS`), acelerando transferências em até 3x com trava de segurança antierro (`FORMATAR`).

---

## 5. Validação e Testes Automatizados

Para executar todas as validações (testes unitários e inspeção de integridade dos pacotes):

```sh
# No Linux ou macOS:
./testar.sh

# No Windows:
testar.cmd
```

Ou execute individualmente:

```sh
# 42 testes unitários completos
python3 -m unittest discover -s tests -v

# Auditoria estática de binários (PE/ELF) e folga de espaço no pendrive
python3 verificar_pacote.py
```
