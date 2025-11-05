# Sistema de Gestão de NF‑e em Python

Este projeto é uma implementação simples de um sistema de gestão financeira e de estoque construído em Python que utiliza notas fiscais eletrônicas (NF‑e) no formato XML.

## Arquivos

* **`inventory_manager.py`** – Script principal com uma interface de linha de comando (CLI). Permite importar arquivos XML de NF‑e de um diretório, atualizar o estoque e consultar relatórios de estoque e financeiros.
* **`inventory_manager_gui.py`** – Interface gráfica opcional usando `tkinter`. Pode ser executada se o ambiente possuir suporte a `tkinter`. Permite importar notas através de uma janela de seleção de diretório, exibir o relatório de estoque em uma tabela (`Treeview`) e mostrar o resumo financeiro em janelas pop‑up.
* **`nfe_000001.xml` ... `nfe_000009.xml`** – Conjunto de notas fiscais de teste fornecido para verificar o funcionamento do sistema. Estes arquivos são utilizados durante a importação de notas pelo programa.
* **`README.md`** – Este documento.

## Como executar

1. Certifique‑se de ter Python 3.8 ou superior instalado no seu sistema.
2. Descompacte o arquivo `.zip` onde desejar.
3. No terminal, navegue até a pasta onde se encontram os arquivos do projeto.
4. Para executar a versão de linha de comando, use:

   ```bash
   python inventory_manager.py
   ```

   Você verá um menu onde poderá informar o diretório que contém os arquivos `.xml` para importação e visualizar os relatórios.

5. Para testar a interface gráfica (caso tenha suporte a `tkinter`), execute:

   ```bash
   python inventory_manager_gui.py
   ```

   Uma janela será aberta permitindo selecionar um diretório de notas, exibir o relatório de estoque e o relatório financeiro.

## Dependências

* Biblioteca padrão do Python (`xml.etree.ElementTree`, `dataclasses`, `glob`, `tkinter`, etc.). Não são necessários pacotes externos.
* Para a interface gráfica, é preciso que o módulo `tkinter` esteja disponível no ambiente (nem todos os ambientes Python instalam o `tkinter` por padrão).

## Observações

* O sistema não inclui persistência em banco de dados nem autenticação de usuário; estes itens são considerados aprimoramentos opcionais conforme as especificações do projeto.
* O objetivo desta entrega é fornecer um esqueleto funcional focado na importação de notas, controle de estoque e geração de relatórios conforme descrito nas especificações【310994896719090†L40-L55】.
