📁 Projetos Java (POO)

Nesta pasta você cria suas classes Java (.java).

Como executar:
  Opção 1: No VS Code, abra o arquivo OlaMundo.java e clique em "Run"
           que aparece logo acima de "public static void main".
  Opção 2: No terminal do kit, execute:
    javac OlaMundo.java
    java OlaMundo

Banco de Dados SQLite:
  Arquivo: banco.db (localizado nesta mesma pasta)
  No VS Code: Basta clicar no arquivo banco.db para abrir o SQLite Viewer integrado!
  Driver JDBC: dependencias/java/sqlite-jdbc.jar (já configurado no projeto)
  Conexão em Java:
    import java.sql.Connection;
    import java.sql.DriverManager;
    Connection conn = DriverManager.getConnection("jdbc:sqlite:banco.db");
