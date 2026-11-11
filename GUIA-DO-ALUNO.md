# 📘 Guia do Aluno: Laboratório Portátil de Programação

Este guia contém tudo o que você precisa saber para utilizar seu ambiente de desenvolvimento portátil em sala de aula e em casa, funcionando tanto no **Windows 11** quanto no **Linux Mint**, diretamente do seu pendrive.

---

## 1. Preparação do Pendrive

* **Capacidade recomendada:** Pendrive de **8 GB** ou superior (o kit utiliza menos de 2 GB, deixando mais de 6 GB livres para seus arquivos).
* **Formatação recomendada:** **exFAT** (suporta arquivos grandes e funciona nativamente em Windows, Linux e Mac) ou **FAT32**.
* **Rótulo do pendrive (opcional):** `AULAS`.

> [!TIP]
> Os kits ficam organizados em pastas dedicadas no pendrive (ex: `kit-web` ou `kit-poo-java`). Você pode ter ambos no mesmo pendrive sem conflitos!

---

## 2. Como Abrir o Ambiente no Laboratório

Conecte o pendrive no computador, abra a pasta do kit da sua disciplina (ex: `kit-web` ou `kit-poo-java`) e dê duplo clique no inicializador:

| Sistema Operacional | O que fazer |
| :--- | :--- |
| **Windows 11** | Dê duplo clique no atalho: <br> `iniciar-windows.cmd` |
| **Linux Mint** | Dê duplo clique no atalho: <br> `laboratorio.desktop` *(ou abra o terminal na pasta e execute `./iniciar-linux.sh`)* |

### 👤 Identificação do Aluno (Primeiro Uso)
Ao abrir pela primeira vez, o sistema solicitará seu identificador (ex.: seu nome de usuário, como `maria-silva` ou sua matrícula).
* O ambiente cria um perfil exclusivo para você no computador e no pendrive.
* Suas preferências (tema, tamanho de fonte, atalhos, snippets) ficam salvas e acompanham você em qualquer máquina!
* Colegas podem usar a mesma máquina em outro turno sem misturar configurações ou arquivos.

Após isso, o menu principal será exibido:
1. Digite **1** para abrir o **Visual Studio Code** da máquina. Ele abrirá configurado em Português com suas extensões e compiladores no SSD local de alta velocidade!
2. Digite **3** sempre que quiser sincronizar suas alterações com o pendrive no meio da aula.
3. Digite **6** para configurar seu nome e e-mail Git para os commits.

---

## 3. Onde Ficam seus Códigos e Como Funciona a Sincronização?

Para você ter a máxima velocidade sem travar o editor, seus projetos são executados a partir do SSD local da máquina do laboratório e sincronizados com segurança no pendrive:
* No **Pendrive**, seus projetos e histórico ficam guardados em: `alunos/<seu-id>/projetos/`
* Na máquina (SSD local), ficam em: `LaboratorioAulas/alunos/<seu-id>/projetos/`
* O repositório Git (`.git`), seus commits, branches e histórico são **100% preservados**!
* Caso haja alguma diferença entre versões salvas em máquinas diferentes, o sistema detecta e isola em `conflitos/` sem apagar nenhum dado seu!

---

## 4. Como Testar seu Primeiro Programa

Cada kit vem com um arquivo de teste pronto:

### 🌐 Web (PHP)
1. Pressione `Ctrl + Shift + B` (ou menu `Terminal -> Run Task`).
2. Selecione **"🌐 Iniciar Servidor Web PHP"**.
3. Abra seu navegador em: `http://127.0.0.1:8080/ola-mundo.php`.

### ☕ Java (POO)
1. Abra o arquivo `projetos/OlaMundo.java`.
2. Clique no botão **`Run`** que aparece logo acima do método `public static void main`.

---

## 5. Recursos Visuais Pedagógicos no VS Code

Para ajudar você a aprender a programar e encontrar erros com rapidez:

* **Error Lens:** Destaca erros de sintaxe e avisos diretamente ao lado da linha que precisa de ajuste.
* **Indent Rainbow:** Colore as colunas de indentação para você nunca se perder nos blocos de código e chaves `{}`.
* **Better Comments:** Torna seus comentários coloridos:
  * `// ! Alerta importante` (em vermelho)
  * `// ? Pergunta ou dúvida` (em azul)
  * `// TODO: Tarefa pendente` (em laranja)
* **Auto Rename Tag:** Ao renomear uma tag HTML de abertura, a de fechamento é atualizada automaticamente.

> [!IMPORTANT]
> **Integridade e Aprendizado:** Assistentes de inteligência artificial (como Copilot ou preenchimentos mágicos de código) foram **desabilitados propositalmente** neste ambiente. O objetivo das aulas práticas é desenvolver sua autonomia, raciocínio lógico e domínio sobre a sintaxe.

---

## 6. Regra de Ouro ao Final da Aula

1. Salve todos os seus arquivos abertos no VS Code (`Ctrl + S`).
2. Feche a janela do VS Code.
3. No terminal do laboratório, selecione a opção **0 (Sair)**: o sistema sincronizará seus projetos do SSD para o pendrive e atualizará seu perfil pessoal de configurações com segurança.
4. **Ejetar com segurança:** No Windows, clique em *"Remover hardware com segurança"* na bandeja do sistema antes de puxar o pendrive. No Linux, clique na seta de ejetar ao lado do pendrive no gerenciador de arquivos.

---

## 7. Dúvidas Frequentes

* **O Linux Mint diz que o arquivo não tem permissão para executar:**  
  O atalho `iniciar-linux.sh` ajusta as permissões automaticamente. Caso o pendrive tenha sido montado com a opção restritiva `noexec`, copie a pasta do kit para a sua pasta pessoal (`~/aulas`) e execute de lá.

* **Fiz uma alteração errada e quero recuperar meu código:**  
  O kit possui Git integrado. Abra o terminal integrado no VS Code e use `git status` e `git checkout` para verificar ou desfazer alterações locais.

* **Preciso de internet para usar o kit em casa?**  
  Não! Todos os compiladores, interpretadores, extensões e documentações foram baixados para dentro do pendrive e funcionam de forma 100% offline.
