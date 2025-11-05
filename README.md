# Sistema de Gestão de NF‑e em Python

Este projeto é uma implementação simples de um sistema de gestão financeira e de estoque construído em Python que utiliza notas fiscais eletrônicas (NF‑e) no formato XML.

## Arquivos (Versão 2)

* **`inventory_system_v2.py`** – Script principal para a versão 2. Integra uma base de dados SQLite, suporte a cadastro e login de usuários com diferentes perfis (administrador, operador, visualizador), importação de notas fiscais, controle de estoque, relatórios financeiros e de movimentações com filtros e exportação para CSV ou Excel. Inclui uma interface de linha de comando e um esboço de IHM com `tkinter`.
* **`inventory_manager.py`** – Versão original (V1) com CLI básica para importação e relatório. Mantido para referência.
* **`inventory_manager_gui.py`** – GUI opcional da versão 1 (necessita `tkinter`).
* **`nfe_000001.xml` ... `nfe_000009.xml`** – Conjunto de notas fiscais de teste.
* **`README.md`** – Este documento.

## Como executar (Versão 2)

1. Certifique‑se de ter Python 3.8 ou superior instalado no seu sistema.
2. Descompacte o arquivo `.zip` onde desejar.
3. No terminal, navegue até a pasta onde se encontram os arquivos do projeto.
4. Para executar a versão de linha de comando da versão 2, use:

   ```bash
   python inventory_system_v2.py
   ```

   Será criado um banco de dados SQLite (`inventory_system_v2.db`) automaticamente. O primeiro acesso cria um usuário administrador padrão (`admin`/`admin`). A partir do menu inicial, é possível cadastrar novos usuários (que necessitam aprovação do administrador), importar notas fiscais, consultar estoque, gerar relatórios, exportar dados e cadastrar produtos conforme o perfil.

5. Para testar a interface gráfica (caso tenha suporte a `tkinter`), execute:

   ```bash
   python -c "from inventory_system_v2 import run_gui; run_gui()"
   ```

   Uma janela será aberta solicitando login ou cadastro. Após logar, você terá acesso às mesmas funcionalidades da CLI por meio de botões e janelas auxiliares.

## Dependências

* Biblioteca padrão do Python (`xml.etree.ElementTree`, `dataclasses`, `glob`, `tkinter`, etc.). Não são necessários pacotes externos.
* Para a versão 2, usa-se apenas a biblioteca padrão (`sqlite3`, `xml.etree.ElementTree`, etc.). A exportação para Excel requer que a biblioteca `pandas` e seus dependentes estejam instalados (já inclusos na maioria dos ambientes científicos). Para a interface gráfica, `tkinter` deve estar disponível.

## Observações

* A versão 2 implementa persistência em banco de dados e autenticação de usuário com perfis e aprovação administrativa, atendendo a requisitos adicionais do projeto【310994896719090†L116-L132】.
* O objetivo desta entrega é fornecer um esqueleto funcional focado na importação de notas, controle de estoque e geração de relatórios conforme descrito nas especificações【310994896719090†L40-L55】.
