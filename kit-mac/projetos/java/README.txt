📁 Projetos Java (POO)

Nesta pasta você desenvolve seus programas Java (.java).
Coloque seus arquivos de código-fonte dentro da pasta "src/".

Exemplos incluídos:
  1. src/OlaMundo.java     - Primeiro programa simples em Java (Olá, mundo!)
  2. src/ExemploBanco.java - Demonstração de conexão e consulta com o banco SQLite

Como executar:
  • No Windows (IntelliJ IDEA):
    Abra pelo menu do kit ("Iniciar Java.cmd").
    O IntelliJ abre com o JDK portátil (JDK-Kit) e a biblioteca sqlite-jdbc.
    No menu de execução superior, escolha "OlaMundo" ou "ExemploBanco" e clique em Run (▶).

  • No Linux (VS Code):
    Abra pelo menu do kit ("iniciar-linux.sh").
    Abra o arquivo src/OlaMundo.java (ou src/ExemploBanco.java) e clique no botão "Run" acima de main.

  • No terminal do kit (Windows ou Linux):
    # Compilar e rodar OlaMundo simples:
    javac -d out src/OlaMundo.java
    java -cp out OlaMundo

    # Compilar e rodar ExemploBanco com SQLite:
    javac -cp "../../dependencias/java/sqlite-jdbc.jar;src" -d out src/ExemploBanco.java   (Windows)
    javac -cp "../../dependencias/java/sqlite-jdbc.jar:src" -d out src/ExemploBanco.java   (Linux)
    java -cp "../../dependencias/java/sqlite-jdbc.jar;out" ExemploBanco                    (Windows)
    java -cp "../../dependencias/java/sqlite-jdbc.jar:out" ExemploBanco                    (Linux)

Banco de Dados SQLite:
  Arquivo: banco.db (localizado nesta mesma pasta)
  No VS Code: Basta clicar no arquivo banco.db para abrir o SQLite Viewer integrado.
  No IntelliJ: Conecte o banco.db na aba Database (versão Ultimate) ou consulte as tabelas pelo menu do kit.
  Driver JDBC: dependencias/java/sqlite-jdbc.jar (já configurado no projeto)
  Conexão em Java:
    import java.sql.Connection;
    import java.sql.DriverManager;
    Connection conn = DriverManager.getConnection("jdbc:sqlite:banco.db");
