"""
Versão 2 do Sistema de Gestão de NF-e.

Esta versão implementa requisitos adicionais em relação à versão inicial,
incluindo persistência em banco de dados SQLite, cadastro e autenticação
de usuários com perfis distintos, controle mais robusto de estoque e
histórico de movimentações, geração de relatórios com filtros e
exportação de dados. Também há uma estrutura básica para uma interface
gráfica (IHM) via `tkinter` para ser usada em ambientes que possuam a
biblioteca instalada.

Principais funcionalidades:

1. **Importação de XML** – lê arquivos NF-e em um diretório, extrai
   produtos, quantidades, preços, datas, emissores e destinatários, e
   identifica se a nota é de entrada (compra) ou saída (venda) para
   atualizar o estoque e registrar as movimentações.

2. **Controle de estoque** – atualiza automaticamente as quantidades
   com base nas notas importadas e permite cadastro manual de novos
   produtos via interface de usuário (requer permissões).

3. **Relatórios** – gera relatório financeiro (entradas, saídas e
   saldo), relatório de estoque atual e histórico de movimentações
   filtrável por produto, período e tipo de nota. Também oferece
   exportação opcional em CSV ou Excel.

4. **Interface gráfica** – esboço de uma IHM com telas de login,
   cadastro de usuário, importação de notas, consulta de estoque e
   geração de relatórios. A IHM só funcionará em ambientes que
   possuam a biblioteca `tkinter` disponível.

5. **Login e perfis de usuário** – suporte a cadastro de usuários
   pendentes de aprovação, validação de credenciais, perfis (admin,
   operador, visualizador), bloqueio após tentativas incorretas e
   registro de log de acesso.

O código foi organizado de forma modular para facilitar a leitura e a
manutenção. Funções de banco de dados, importação e relatórios são
separadas de funções de interface. Consulte o README para instruções de
execução.
"""

from __future__ import annotations

import os
import sys
import glob
import sqlite3
import hashlib
import csv
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import xml.etree.ElementTree as ET

try:
    import pandas as pd  # opcional para exportar Excel
    _HAS_PANDAS = True
except ImportError:
    pd = None  # type: ignore
    _HAS_PANDAS = False


DB_NAME = 'inventory_system_v2.db'


###############################################################################
# Utilidades de banco de dados
###############################################################################

def get_connection() -> sqlite3.Connection:
    """Obter conexão com o banco SQLite e configurar para retornar tuplas nomeadas."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def setup_database() -> None:
    """Cria as tabelas necessárias se ainda não existirem."""
    conn = get_connection()
    cur = conn.cursor()
    # Tabela de usuários
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            approved INTEGER NOT NULL DEFAULT 0,
            locked INTEGER NOT NULL DEFAULT 0,
            login_attempts INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    # Tabela de produtos
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            quantity REAL NOT NULL DEFAULT 0,
            unit_price REAL NOT NULL DEFAULT 0
        )
        """
    )
    # Tabela de notas fiscais
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            number TEXT NOT NULL,
            type INTEGER NOT NULL,
            date TIMESTAMP NOT NULL,
            emitter TEXT,
            destination TEXT,
            total REAL,
            file_name TEXT
        )
        """
    )
    # Itens da nota
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS invoice_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER NOT NULL,
            product_code TEXT NOT NULL,
            product_name TEXT,
            quantity REAL NOT NULL,
            unit_price REAL NOT NULL,
            subtotal REAL NOT NULL,
            FOREIGN KEY (invoice_id) REFERENCES invoices(id),
            FOREIGN KEY (product_code) REFERENCES products(code)
        )
        """
    )
    # Log de acesso
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS access_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            action TEXT,
            status TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    conn.close()


###############################################################################
# Funções auxiliares para usuários
###############################################################################

def hash_password(password: str) -> str:
    """Retorna o hash SHA-256 da senha fornecida."""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def create_user(username: str, password: str, role: str = 'viewer', approved: bool = False) -> bool:
    """Cadastra um novo usuário. Retorna True se bem-sucedido."""
    if role not in ('admin', 'operator', 'viewer'):
        raise ValueError("Role inválida")
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO users (username, password, role, approved) VALUES (?, ?, ?, ?)",
            (username, hash_password(password), role, 1 if approved else 0)
        )
        conn.commit()
        result = True
    except sqlite3.IntegrityError:
        result = False
    finally:
        conn.close()
    return result


def get_user(username: str) -> Optional[sqlite3.Row]:
    """Recupera um usuário pelo nome."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    return row


def validate_credentials(username: str, password: str) -> Tuple[bool, Optional[str]]:
    """Verifica se as credenciais são válidas.

    Retorna (True, role) se a senha corresponder e o usuário estiver aprovado e não bloqueado.
    Caso contrário, retorna (False, motivo).
    """
    user = get_user(username)
    if not user:
        return False, "Usuário não encontrado"
    if user['locked']:
        return False, "Usuário bloqueado por tentativas excessivas"
    if not user['approved']:
        return False, "Usuário aguardando aprovação"
    if user['password'] != hash_password(password):
        # incrementar tentativas
        increment_login_attempts(username)
        # se exceder 3 tentativas, bloquear
        if user['login_attempts'] + 1 >= 3:
            lock_user(username)
            return False, "Usuário bloqueado por tentativas excessivas"
        return False, "Senha incorreta"
    # resetar tentativas
    reset_login_attempts(username)
    return True, user['role']


def increment_login_attempts(username: str) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET login_attempts = login_attempts + 1 WHERE username = ?",
        (username,)
    )
    conn.commit()
    conn.close()


def reset_login_attempts(username: str) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET login_attempts = 0 WHERE username = ?",
        (username,)
    )
    conn.commit()
    conn.close()


def lock_user(username: str) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET locked = 1 WHERE username = ?",
        (username,)
    )
    conn.commit()
    conn.close()


def approve_user(username: str) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET approved = 1 WHERE username = ?",
        (username,)
    )
    conn.commit()
    result = cur.rowcount > 0
    conn.close()
    return result


def get_pending_users() -> List[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE approved = 0")
    rows = cur.fetchall()
    conn.close()
    return rows


def record_access_log(username: str, action: str, status: str) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO access_log (username, action, status) VALUES (?, ?, ?)",
        (username, action, status)
    )
    conn.commit()
    conn.close()


###############################################################################
# Funções auxiliares para produtos e estoque
###############################################################################

def create_product(code: str, name: str, quantity: float = 0.0, unit_price: float = 0.0) -> bool:
    """Cria um novo produto. Retorna True se criado."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO products (code, name, quantity, unit_price) VALUES (?, ?, ?, ?)",
            (code, name, quantity, unit_price)
        )
        conn.commit()
        result = True
    except sqlite3.IntegrityError:
        result = False
    finally:
        conn.close()
    return result


def update_product_quantity(code: str, delta: float, unit_price: float) -> None:
    """Atualiza a quantidade e preço unitário de um produto existente."""
    conn = get_connection()
    cur = conn.cursor()
    # Atualizar ou criar caso não exista
    cur.execute("SELECT * FROM products WHERE code = ?", (code,))
    row = cur.fetchone()
    if row:
        new_qty = row['quantity'] + delta
        cur.execute(
            "UPDATE products SET quantity = ?, unit_price = ? WHERE code = ?",
            (new_qty, unit_price, code)
        )
    else:
        cur.execute(
            "INSERT INTO products (code, name, quantity, unit_price) VALUES (?, ?, ?, ?)",
            (code, code, delta, unit_price)  # nome igual ao código se desconhecido
        )
    conn.commit()
    conn.close()


def get_stock_balance() -> List[Tuple[str, str, float, float]]:
    """Retorna o estoque atual (código, nome, quantidade, preço)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT code, name, quantity, unit_price FROM products ORDER BY code")
    rows = cur.fetchall()
    conn.close()
    return [(row['code'], row['name'], row['quantity'], row['unit_price']) for row in rows]


###############################################################################
# Importação de NF-e
###############################################################################

def parse_nfe_xml_v2(path: str) -> Optional[Dict[str, Any]]:
    """Analisa um XML de NF-e e retorna um dicionário com cabeçalho e itens.

    Retorna ``None`` se houver erro de análise.
    """
    try:
        tree = ET.parse(path)
    except ET.ParseError as exc:
        print(f"Erro ao analisar '{path}': {exc}")
        return None
    root = tree.getroot()
    ns = {"nfe": "http://www.portalfiscal.inf.br/nfe"}
    ide = root.find('.//nfe:ide', ns)
    if ide is None:
        return None
    number = ide.findtext('nfe:nNF', default='UNKNOWN', namespaces=ns)
    tpNF = ide.findtext('nfe:tpNF', default='0', namespaces=ns)
    try:
        type_ = int(tpNF)
    except ValueError:
        type_ = 0
    dhEmi = ide.findtext('nfe:dhEmi', namespaces=ns)
    try:
        date = datetime.fromisoformat(dhEmi)
    except Exception:
        date = datetime.now()
    # Emissor/destinatário
    emit = root.find('.//nfe:emit', ns)
    dest = root.find('.//nfe:dest', ns)
    emitter = emit.findtext('nfe:CNPJ', namespaces=ns) or emit.findtext('nfe:CPF', namespaces=ns) or '' if emit is not None else ''
    destination = dest.findtext('nfe:CNPJ', namespaces=ns) or dest.findtext('nfe:CPF', namespaces=ns) or '' if dest is not None else ''
    # Valor total
    total_elem = root.find('.//nfe:total/nfe:ICMSTot', ns)
    vNF = 0.0
    if total_elem is not None:
        vNF_text = total_elem.findtext('nfe:vNF', default='0', namespaces=ns)
        try:
            vNF = float(vNF_text.replace(',', '.'))
        except ValueError:
            vNF = 0.0
    # Itens
    items: List[Dict[str, Any]] = []
    for det in root.findall('.//nfe:det', ns):
        prod = det.find('nfe:prod', ns)
        if prod is None:
            continue
        code = prod.findtext('nfe:cProd', default='', namespaces=ns).strip()
        name = prod.findtext('nfe:xProd', default='', namespaces=ns).strip()
        q_text = prod.findtext('nfe:qCom', default='0', namespaces=ns)
        vunit_text = prod.findtext('nfe:vUnCom', default='0', namespaces=ns)
        vprod_text = prod.findtext('nfe:vProd', default='0', namespaces=ns)
        try:
            quantity = float(q_text.replace(',', '.'))
        except ValueError:
            quantity = 0.0
        try:
            unit_price = float(vunit_text.replace(',', '.'))
        except ValueError:
            unit_price = 0.0
        try:
            subtotal = float(vprod_text.replace(',', '.'))
        except ValueError:
            subtotal = quantity * unit_price
        items.append({
            'product_code': code,
            'product_name': name,
            'quantity': quantity,
            'unit_price': unit_price,
            'subtotal': subtotal
        })
    return {
        'number': number,
        'type': type_,
        'date': date,
        'emitter': emitter,
        'destination': destination,
        'total': vNF,
        'items': items
    }


def import_invoices_v2(dir_path: str, current_user: str) -> None:
    """Importa todos os XMLs de um diretório e atualiza o banco de dados.

    O usuário que realizou a ação é registrado no log de acesso.
    """
    files = glob.glob(os.path.join(dir_path, '*.xml'))
    if not files:
        print(f"Nenhum arquivo XML encontrado em {dir_path}")
        return
    conn = get_connection()
    cur = conn.cursor()
    for file in files:
        data = parse_nfe_xml_v2(file)
        if not data:
            print(f"Arquivo inválido: {file}")
            continue
        # Inserir nota fiscal
        cur.execute(
            "INSERT INTO invoices (number, type, date, emitter, destination, total, file_name) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (data['number'], data['type'], data['date'], data['emitter'], data['destination'], data['total'], os.path.basename(file))
        )
        invoice_id = cur.lastrowid
        sign = 1.0 if data['type'] == 0 else -1.0
        for item in data['items']:
            # Inserir item
            cur.execute(
                "INSERT INTO invoice_items (invoice_id, product_code, product_name, quantity, unit_price, subtotal)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (invoice_id, item['product_code'], item['product_name'], item['quantity'], item['unit_price'], item['subtotal'])
            )
            # Atualizar estoque na mesma transação para evitar travamentos
            # Verificar se produto existe
            cur.execute("SELECT quantity FROM products WHERE code = ?", (item['product_code'],))
            row = cur.fetchone()
            delta = sign * item['quantity']
            if row:
                new_qty = row['quantity'] + delta
                cur.execute(
                    "UPDATE products SET quantity = ?, unit_price = ? WHERE code = ?",
                    (new_qty, item['unit_price'], item['product_code'])
                )
            else:
                # Usar nome do item como nome do produto
                cur.execute(
                    "INSERT INTO products (code, name, quantity, unit_price) VALUES (?, ?, ?, ?)",
                    (item['product_code'], item['product_name'] or item['product_code'], delta, item['unit_price'])
                )
        print(f"Importada nota {data['number']} de {file}")
    conn.commit()
    conn.close()
    record_access_log(current_user, f"import_invoices_from_{dir_path}", "success")


###############################################################################
# Funções de relatório
###############################################################################

def get_financial_report(start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> Tuple[float, float, float]:
    """Retorna (despesas, receitas, saldo) no período especificado.

    Entradas são notas de tipo 0, saídas são notas de tipo 1.
    """
    conn = get_connection()
    cur = conn.cursor()
    query = "SELECT type, total FROM invoices"
    params: List[Any] = []
    if start_date and end_date:
        query += " WHERE date BETWEEN ? AND ?"
        params.extend([start_date, end_date])
    elif start_date:
        query += " WHERE date >= ?"
        params.append(start_date)
    elif end_date:
        query += " WHERE date <= ?"
        params.append(end_date)
    cur.execute(query, params)
    total_expenses = 0.0
    total_revenue = 0.0
    for row in cur.fetchall():
        if row['type'] == 0:
            total_expenses += row['total']
        else:
            total_revenue += row['total']
    conn.close()
    balance = total_revenue - total_expenses
    return total_expenses, total_revenue, balance


def get_movement_history(product_code: Optional[str] = None, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None, note_type: Optional[int] = None) -> List[Dict[str, Any]]:
    """Retorna o histórico de movimentações conforme filtros.

    Cada item contém: número da nota, data, tipo, código do produto, nome, quantidade, preço, subtotal.
    """
    conn = get_connection()
    cur = conn.cursor()
    query = (
        "SELECT inv.number, inv.date, inv.type, it.product_code, it.product_name, it.quantity, it.unit_price, it.subtotal, inv.emitter, inv.destination"
        " FROM invoice_items it"
        " JOIN invoices inv ON inv.id = it.invoice_id"
    )
    conditions = []
    params: List[Any] = []
    if product_code:
        conditions.append("it.product_code = ?")
        params.append(product_code)
    if start_date:
        conditions.append("inv.date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("inv.date <= ?")
        params.append(end_date)
    if note_type is not None:
        conditions.append("inv.type = ?")
        params.append(note_type)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY inv.date, inv.number"
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()
    history: List[Dict[str, Any]] = []
    for row in rows:
        history.append({
            'number': row['number'],
            'date': row['date'],
            'type': row['type'],
            'product_code': row['product_code'],
            'product_name': row['product_name'],
            'quantity': row['quantity'],
            'unit_price': row['unit_price'],
            'subtotal': row['subtotal'],
            'emitter': row['emitter'],
            'destination': row['destination'],
        })
    return history


def export_to_csv(data: List[Dict[str, Any]], file_path: str) -> None:
    """Exporta uma lista de dicionários para CSV."""
    if not data:
        print("Sem dados para exportar.")
        return
    with open(file_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(data[0].keys()))
        writer.writeheader()
        for row in data:
            writer.writerow(row)
    print(f"Dados exportados para {file_path}")


def export_to_excel(data: List[Dict[str, Any]], file_path: str) -> None:
    """Exporta os dados para um arquivo Excel se pandas estiver disponível."""
    if not _HAS_PANDAS:
        print("Pandas não está disponível; exportação para Excel indisponível.")
        return
    if not data:
        print("Sem dados para exportar.")
        return
    df = pd.DataFrame(data)
    df.to_excel(file_path, index=False)
    print(f"Dados exportados para {file_path}")


###############################################################################
# CLI (interface de linha de comando)
###############################################################################

def cli_main() -> None:
    """Função principal da interface CLI."""
    setup_database()
    # Garantir que haja ao menos um administrador
    if not get_user('admin'):
        # Criar admin padrão com senha 'admin'
        create_user('admin', 'admin', role='admin', approved=True)
        print("Usuário administrador padrão criado (login: admin / senha: admin)")
    while True:
        print("\nSistema de Gestão NF-e v2")
        print("1. Entrar")
        print("2. Cadastrar usuário")
        print("3. Sair")
        choice = input("Escolha uma opção: ").strip()
        if choice == '1':
            username = input("Usuário: ").strip()
            password = input("Senha: ").strip()
            valid, result = validate_credentials(username, password)
            if not valid:
                print(f"Acesso negado: {result}")
                record_access_log(username, 'login', 'fail')
            else:
                print(f"Bem-vindo, {username} (perfil: {result})")
                record_access_log(username, 'login', 'success')
                # abrir menu principal com base no perfil
                user_menu(username, result)
        elif choice == '2':
            username = input("Escolha um nome de usuário: ").strip()
            password = input("Escolha uma senha: ").strip()
            role = input("Perfil (admin/operator/viewer) [viewer]: ").strip().lower() or 'viewer'
            if role not in ('admin', 'operator', 'viewer'):
                print("Perfil inválido. Tente novamente.")
                continue
            success = create_user(username, password, role=role, approved=False)
            if success:
                print("Usuário cadastrado com sucesso. Aguarde aprovação de um administrador.")
            else:
                print("Nome de usuário já existe.")
        elif choice == '3':
            print("Saindo...")
            break
        else:
            print("Opção inválida.")


def user_menu(username: str, role: str) -> None:
    """Menu principal após login, com opções de acordo com o perfil."""
    while True:
        print("\nMenu Principal")
        print("1. Importar notas fiscais (XML)")
        print("2. Ver estoque atual")
        print("3. Relatório financeiro")
        print("4. Histórico de movimentações")
        print("5. Exportar dados")
        if role in ('admin', 'operator'):
            print("6. Cadastrar novo produto")
        if role == 'admin':
            print("7. Aprovar usuários pendentes")
        print("9. Sair")
        op = input("Selecione uma opção: ").strip()
        if op == '1':
            dir_path = input("Diretório contendo arquivos XML: ").strip()
            if not os.path.isdir(dir_path):
                print("Diretório inválido.")
            else:
                import_invoices_v2(dir_path, username)
        elif op == '2':
            stock = get_stock_balance()
            if not stock:
                print("Nenhum produto cadastrado.")
            else:
                print("\nEstoque:")
                print(f"{'Código':<20}{'Nome':<20}{'Quantidade':>15}{'Preço unitário':>20}")
                for code, name, qty, price in stock:
                    print(f"{code:<20}{name:<20}{qty:>15.2f}{price:>20.2f}")
        elif op == '3':
            print("Relatório financeiro")
            start_str = input("Data inicial (YYYY-MM-DD) ou enter para nenhum filtro: ").strip()
            end_str = input("Data final (YYYY-MM-DD) ou enter para nenhum filtro: ").strip()
            start_date = datetime.fromisoformat(start_str) if start_str else None
            end_date = datetime.fromisoformat(end_str) if end_str else None
            expenses, revenue, balance = get_financial_report(start_date, end_date)
            print(f"Despesas: {expenses:.2f}\nReceitas: {revenue:.2f}\nSaldo: {balance:.2f}")
        elif op == '4':
            print("Histórico de movimentações")
            prod = input("Filtrar por código de produto (ou enter para todos): ").strip() or None
            start_str = input("Data inicial (YYYY-MM-DD) ou enter para nenhum filtro: ").strip()
            end_str = input("Data final (YYYY-MM-DD) ou enter para nenhum filtro: ").strip()
            start_date = datetime.fromisoformat(start_str) if start_str else None
            end_date = datetime.fromisoformat(end_str) if end_str else None
            type_str = input("Tipo de nota (0=entrada, 1=saída, enter=ambos): ").strip()
            note_type = int(type_str) if type_str in ('0', '1') else None
            history = get_movement_history(prod, start_date, end_date, note_type)
            if not history:
                print("Nenhuma movimentação encontrada.")
            else:
                print(f"{'Nota':<10}{'Data':<20}{'Tipo':<6}{'Código':<16}{'Nome':<20}{'Qtd':>8}{'Preço':>12}{'Subtotal':>12}")
                for item in history:
                    tipo = 'Entr' if item['type'] == 0 else 'Saída'
                    print(f"{item['number']:<10}{item['date']:<20}{tipo:<6}{item['product_code']:<16}{item['product_name']:<20}{item['quantity']:>8.2f}{item['unit_price']:>12.2f}{item['subtotal']:>12.2f}")
        elif op == '5':
            print("Exportar dados")
            print("1. Exportar estoque em CSV")
            print("2. Exportar histórico em CSV")
            if _HAS_PANDAS:
                print("3. Exportar histórico em Excel")
            exp_choice = input("Escolha: ").strip()
            if exp_choice == '1':
                file_path = input("Caminho do arquivo CSV: ").strip()
                stock = get_stock_balance()
                data = [
                    {'code': code, 'name': name, 'quantity': qty, 'unit_price': price}
                    for code, name, qty, price in stock
                ]
                export_to_csv(data, file_path)
            elif exp_choice == '2':
                prod = input("Filtro código de produto (ou enter para todos): ").strip() or None
                start_str = input("Data inicial (YYYY-MM-DD) ou enter para nenhum filtro: ").strip()
                end_str = input("Data final (YYYY-MM-DD) ou enter para nenhum filtro: ").strip()
                start_date = datetime.fromisoformat(start_str) if start_str else None
                end_date = datetime.fromisoformat(end_str) if end_str else None
                type_str = input("Tipo de nota (0=entrada, 1=saída, enter=ambos): ").strip()
                note_type = int(type_str) if type_str in ('0', '1') else None
                hist = get_movement_history(prod, start_date, end_date, note_type)
                path_csv = input("Caminho do arquivo CSV: ").strip()
                export_to_csv(hist, path_csv)
            elif exp_choice == '3' and _HAS_PANDAS:
                prod = input("Filtro código de produto (ou enter para todos): ").strip() or None
                start_str = input("Data inicial (YYYY-MM-DD) ou enter para nenhum filtro: ").strip()
                end_str = input("Data final (YYYY-MM-DD) ou enter para nenhum filtro: ").strip()
                start_date = datetime.fromisoformat(start_str) if start_str else None
                end_date = datetime.fromisoformat(end_str) if end_str else None
                type_str = input("Tipo de nota (0=entrada, 1=saída, enter=ambos): ").strip()
                note_type = int(type_str) if type_str in ('0', '1') else None
                hist = get_movement_history(prod, start_date, end_date, note_type)
                path_excel = input("Caminho do arquivo Excel (.xlsx): ").strip()
                export_to_excel(hist, path_excel)
            else:
                print("Opção inválida ou pandas indisponível.")
        elif op == '6' and role in ('admin', 'operator'):
            print("Cadastrar produto")
            code = input("Código do produto: ").strip()
            name = input("Nome do produto: ").strip()
            qty_str = input("Quantidade inicial (0 se desconhecida): ").strip()
            price_str = input("Preço unitário (0 se desconhecido): ").strip()
            quantity = float(qty_str) if qty_str else 0.0
            price = float(price_str) if price_str else 0.0
            success = create_product(code, name, quantity, price)
            if success:
                print("Produto cadastrado com sucesso.")
            else:
                print("Produto já existe.")
        elif op == '7' and role == 'admin':
            pending = get_pending_users()
            if not pending:
                print("Nenhum usuário pendente.")
            else:
                print("Usuários pendentes:")
                for row in pending:
                    print(f"- {row['username']} (perfil: {row['role']})")
                user_to_approve = input("Digite o usuário a aprovar (ou enter para voltar): ").strip()
                if user_to_approve:
                    if approve_user(user_to_approve):
                        print(f"Usuário {user_to_approve} aprovado.")
                    else:
                        print("Usuário não encontrado ou erro ao aprovar.")
        elif op == '9':
            print("Saindo do menu.")
            break
        else:
            print("Opção inválida.")


###############################################################################
# Esboço de interface gráfica (IHM) com tkinter
###############################################################################

try:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
    _HAS_TK = True
except ImportError:
    _HAS_TK = False

if _HAS_TK:
    class AppGUI(tk.Tk):
        """Aplicativo GUI para o sistema versão 2.

        Nota: só funcionará se a biblioteca tkinter estiver instalada no ambiente.
        """
        def __init__(self) -> None:
            super().__init__()
            self.title("Gestão NF-e v2")
            self.geometry("800x600")
            self.resizable(False, False)
            setup_database()
            # Garantir admin
            if not get_user('admin'):
                create_user('admin', 'admin', role='admin', approved=True)
            self.current_user: Optional[str] = None
            self.current_role: Optional[str] = None
            self.build_login_screen()

        def build_login_screen(self) -> None:
            self.clear_screen()
            tk.Label(self, text="Login", font=("Arial", 16)).pack(pady=10)
            frame = tk.Frame(self)
            frame.pack(pady=10)
            tk.Label(frame, text="Usuário").grid(row=0, column=0, pady=5)
            self.user_entry = tk.Entry(frame)
            self.user_entry.grid(row=0, column=1)
            tk.Label(frame, text="Senha").grid(row=1, column=0, pady=5)
            self.pass_entry = tk.Entry(frame, show='*')
            self.pass_entry.grid(row=1, column=1)
            tk.Button(self, text="Entrar", command=self.do_login).pack(pady=5)
            tk.Button(self, text="Cadastrar", command=self.build_register_screen).pack()

        def build_register_screen(self) -> None:
            self.clear_screen()
            tk.Label(self, text="Cadastro de Usuário", font=("Arial", 16)).pack(pady=10)
            frame = tk.Frame(self)
            frame.pack(pady=10)
            tk.Label(frame, text="Usuário").grid(row=0, column=0, pady=5)
            self.reg_user_entry = tk.Entry(frame)
            self.reg_user_entry.grid(row=0, column=1)
            tk.Label(frame, text="Senha").grid(row=1, column=0, pady=5)
            self.reg_pass_entry = tk.Entry(frame, show='*')
            self.reg_pass_entry.grid(row=1, column=1)
            tk.Label(frame, text="Perfil (admin/operator/viewer)").grid(row=2, column=0, pady=5)
            self.reg_role_entry = tk.Entry(frame)
            self.reg_role_entry.grid(row=2, column=1)
            tk.Button(self, text="Cadastrar", command=self.do_register).pack(pady=5)
            tk.Button(self, text="Voltar", command=self.build_login_screen).pack()

        def clear_screen(self) -> None:
            for widget in self.winfo_children():
                widget.destroy()

        def do_login(self) -> None:
            username = self.user_entry.get().strip()
            password = self.pass_entry.get().strip()
            valid, result = validate_credentials(username, password)
            if not valid:
                messagebox.showerror("Acesso negado", result)
                record_access_log(username, 'login', 'fail')
            else:
                messagebox.showinfo("Bem-vindo", f"Usuário {username}, perfil {result}")
                record_access_log(username, 'login', 'success')
                self.current_user = username
                self.current_role = result
                self.build_main_screen()

        def do_register(self) -> None:
            username = self.reg_user_entry.get().strip()
            password = self.reg_pass_entry.get().strip()
            role = self.reg_role_entry.get().strip() or 'viewer'
            if role not in ('admin', 'operator', 'viewer'):
                messagebox.showerror("Erro", "Perfil inválido")
                return
            success = create_user(username, password, role=role, approved=False)
            if success:
                messagebox.showinfo("Cadastro", "Usuário cadastrado. Aguarde aprovação.")
                self.build_login_screen()
            else:
                messagebox.showerror("Erro", "Nome de usuário já existe")

        def build_main_screen(self) -> None:
            self.clear_screen()
            tk.Label(self, text=f"Menu Principal - {self.current_user} ({self.current_role})", font=("Arial", 14)).pack(pady=10)
            btn_frame = tk.Frame(self)
            btn_frame.pack(pady=5)
            tk.Button(btn_frame, text="Importar Notas", command=self.gui_import_invoices).grid(row=0, column=0, padx=5)
            tk.Button(btn_frame, text="Ver Estoque", command=self.gui_show_stock).grid(row=0, column=1, padx=5)
            tk.Button(btn_frame, text="Relatório Financeiro", command=self.gui_financial_report).grid(row=0, column=2, padx=5)
            tk.Button(btn_frame, text="Histórico", command=self.gui_history).grid(row=0, column=3, padx=5)
            tk.Button(btn_frame, text="Exportar", command=self.gui_export).grid(row=0, column=4, padx=5)
            if self.current_role in ('admin', 'operator'):
                tk.Button(btn_frame, text="Cadastrar Produto", command=self.gui_create_product).grid(row=1, column=0, padx=5, pady=5)
            if self.current_role == 'admin':
                tk.Button(btn_frame, text="Aprovar Usuários", command=self.gui_approve_users).grid(row=1, column=1, padx=5, pady=5)
            tk.Button(btn_frame, text="Sair", command=self.build_login_screen).grid(row=1, column=3, padx=5, pady=5)

        # As demais funções são as mesmas definidas anteriormente, sem alterações

        def gui_import_invoices(self) -> None:
            dir_path = filedialog.askdirectory(title="Selecione o diretório de XML")
            if dir_path:
                import_invoices_v2(dir_path, self.current_user or '')
                messagebox.showinfo("Importação", "Importação concluída")

        def gui_show_stock(self) -> None:
            stock = get_stock_balance()
            window = tk.Toplevel(self)
            window.title("Estoque")
            cols = ("Código", "Nome", "Quantidade", "Preço")
            tree = ttk.Treeview(window, columns=cols, show='headings')
            for col in cols:
                tree.heading(col, text=col)
            for code, name, qty, price in stock:
                tree.insert('', 'end', values=(code, name, f"{qty:.2f}", f"{price:.2f}"))
            tree.pack(expand=True, fill='both')

        def gui_financial_report(self) -> None:
            report_win = tk.Toplevel(self)
            report_win.title("Relatório Financeiro")
            tk.Label(report_win, text="Data inicial (YYYY-MM-DD)").grid(row=0, column=0)
            start_entry = tk.Entry(report_win)
            start_entry.grid(row=0, column=1)
            tk.Label(report_win, text="Data final (YYYY-MM-DD)").grid(row=1, column=0)
            end_entry = tk.Entry(report_win)
            end_entry.grid(row=1, column=1)
            def generate():
                start = start_entry.get().strip()
                end = end_entry.get().strip()
                s_date = datetime.fromisoformat(start) if start else None
                e_date = datetime.fromisoformat(end) if end else None
                expenses, revenue, balance = get_financial_report(s_date, e_date)
                messagebox.showinfo("Relatório", f"Despesas: {expenses:.2f}\nReceitas: {revenue:.2f}\nSaldo: {balance:.2f}")
            tk.Button(report_win, text="Gerar", command=generate).grid(row=2, column=0, columnspan=2)

        def gui_history(self) -> None:
            hist_win = tk.Toplevel(self)
            hist_win.title("Histórico de Movimentações")
            tk.Label(hist_win, text="Produto").grid(row=0, column=0)
            prod_entry = tk.Entry(hist_win)
            prod_entry.grid(row=0, column=1)
            tk.Label(hist_win, text="Data inicial (YYYY-MM-DD)").grid(row=1, column=0)
            start_entry = tk.Entry(hist_win)
            start_entry.grid(row=1, column=1)
            tk.Label(hist_win, text="Data final (YYYY-MM-DD)").grid(row=2, column=0)
            end_entry = tk.Entry(hist_win)
            end_entry.grid(row=2, column=1)
            tk.Label(hist_win, text="Tipo (0=entrada,1=saída)").grid(row=3, column=0)
            type_entry = tk.Entry(hist_win)
            type_entry.grid(row=3, column=1)
            cols = ("Nota", "Data", "Tipo", "Código", "Nome", "Qtd", "Preço", "Subtotal")
            tree = ttk.Treeview(hist_win, columns=cols, show='headings')
            for col in cols:
                tree.heading(col, text=col)
            tree.grid(row=5, column=0, columnspan=2, sticky='nsew')
            hist_win.rowconfigure(5, weight=1)
            hist_win.columnconfigure(1, weight=1)
            def load_history():
                prod = prod_entry.get().strip() or None
                start = start_entry.get().strip()
                end = end_entry.get().strip()
                s_date = datetime.fromisoformat(start) if start else None
                e_date = datetime.fromisoformat(end) if end else None
                t = type_entry.get().strip()
                note_t = int(t) if t in ('0', '1') else None
                hist = get_movement_history(prod, s_date, e_date, note_t)
                for item in tree.get_children():
                    tree.delete(item)
                for item in hist:
                    typ = 'Entr' if item['type'] == 0 else 'Saída'
                    tree.insert('', 'end', values=(item['number'], item['date'], typ, item['product_code'], item['product_name'], f"{item['quantity']:.2f}", f"{item['unit_price']:.2f}", f"{item['subtotal']:.2f}"))
            tk.Button(hist_win, text="Carregar", command=load_history).grid(row=4, column=0, columnspan=2)

        def gui_export(self) -> None:
            exp_win = tk.Toplevel(self)
            exp_win.title("Exportar Dados")
            tk.Button(exp_win, text="Exportar Estoque (CSV)", command=self.gui_export_stock_csv).pack(pady=5)
            tk.Button(exp_win, text="Exportar Histórico (CSV)", command=self.gui_export_hist_csv).pack(pady=5)
            if _HAS_PANDAS:
                tk.Button(exp_win, text="Exportar Histórico (Excel)", command=self.gui_export_hist_excel).pack(pady=5)

        def gui_export_stock_csv(self) -> None:
            path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV","*.csv")])
            if path:
                stock = get_stock_balance()
                data = [
                    {'code': code, 'name': name, 'quantity': qty, 'unit_price': price}
                    for code, name, qty, price in stock
                ]
                export_to_csv(data, path)
                messagebox.showinfo("Exportação", f"Estoque exportado para {path}")

        def gui_export_hist_csv(self) -> None:
            filter_win = tk.Toplevel(self)
            filter_win.title("Filtros de Exportação CSV")
            tk.Label(filter_win, text="Produto").grid(row=0, column=0)
            prod_entry = tk.Entry(filter_win)
            prod_entry.grid(row=0, column=1)
            tk.Label(filter_win, text="Data inicial (YYYY-MM-DD)").grid(row=1, column=0)
            start_entry = tk.Entry(filter_win)
            start_entry.grid(row=1, column=1)
            tk.Label(filter_win, text="Data final (YYYY-MM-DD)").grid(row=2, column=0)
            end_entry = tk.Entry(filter_win)
            end_entry.grid(row=2, column=1)
            tk.Label(filter_win, text="Tipo (0=entrada,1=saída)").grid(row=3, column=0)
            type_entry = tk.Entry(filter_win)
            type_entry.grid(row=3, column=1)
            def do_export():
                prod = prod_entry.get().strip() or None
                start = start_entry.get().strip()
                end = end_entry.get().strip()
                s_date = datetime.fromisoformat(start) if start else None
                e_date = datetime.fromisoformat(end) if end else None
                t = type_entry.get().strip()
                note_t = int(t) if t in ('0','1') else None
                hist = get_movement_history(prod, s_date, e_date, note_t)
                path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV","*.csv")])
                if path:
                    export_to_csv(hist, path)
                    messagebox.showinfo("Exportação", f"Histórico exportado para {path}")
                    filter_win.destroy()
            tk.Button(filter_win, text="Exportar", command=do_export).grid(row=4, column=0, columnspan=2)

        def gui_export_hist_excel(self) -> None:
            filter_win = tk.Toplevel(self)
            filter_win.title("Filtros de Exportação Excel")
            tk.Label(filter_win, text="Produto").grid(row=0, column=0)
            prod_entry = tk.Entry(filter_win)
            prod_entry.grid(row=0, column=1)
            tk.Label(filter_win, text="Data inicial (YYYY-MM-DD)").grid(row=1, column=0)
            start_entry = tk.Entry(filter_win)
            start_entry.grid(row=1, column=1)
            tk.Label(filter_win, text="Data final (YYYY-MM-DD)").grid(row=2, column=0)
            end_entry = tk.Entry(filter_win)
            end_entry.grid(row=2, column=1)
            tk.Label(filter_win, text="Tipo (0=entrada,1=saída)").grid(row=3, column=0)
            type_entry = tk.Entry(filter_win)
            type_entry.grid(row=3, column=1)
            def do_export():
                prod = prod_entry.get().strip() or None
                start = start_entry.get().strip()
                end = end_entry.get().strip()
                s_date = datetime.fromisoformat(start) if start else None
                e_date = datetime.fromisoformat(end) if end else None
                t = type_entry.get().strip()
                note_t = int(t) if t in ('0','1') else None
                hist = get_movement_history(prod, s_date, e_date, note_t)
                path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel","*.xlsx")])
                if path:
                    export_to_excel(hist, path)
                    messagebox.showinfo("Exportação", f"Histórico exportado para {path}")
                    filter_win.destroy()
            tk.Button(filter_win, text="Exportar", command=do_export).grid(row=4, column=0, columnspan=2)

        def gui_create_product(self) -> None:
            win = tk.Toplevel(self)
            win.title("Cadastrar Produto")
            tk.Label(win, text="Código").grid(row=0, column=0)
            code_entry = tk.Entry(win)
            code_entry.grid(row=0, column=1)
            tk.Label(win, text="Nome").grid(row=1, column=0)
            name_entry = tk.Entry(win)
            name_entry.grid(row=1, column=1)
            tk.Label(win, text="Quantidade inicial").grid(row=2, column=0)
            qty_entry = tk.Entry(win)
            qty_entry.grid(row=2, column=1)
            tk.Label(win, text="Preço unitário").grid(row=3, column=0)
            price_entry = tk.Entry(win)
            price_entry.grid(row=3, column=1)
            def register():
                code = code_entry.get().strip()
                name = name_entry.get().strip()
                qty = float(qty_entry.get().strip() or '0')
                price = float(price_entry.get().strip() or '0')
                if create_product(code, name, qty, price):
                    messagebox.showinfo("Cadastro", "Produto cadastrado")
                    win.destroy()
                else:
                    messagebox.showerror("Erro", "Produto já existe")
            tk.Button(win, text="Cadastrar", command=register).grid(row=4, column=0, columnspan=2)

        def gui_approve_users(self) -> None:
            pending = get_pending_users()
            win = tk.Toplevel(self)
            win.title("Aprovar Usuários")
            tk.Label(win, text="Usuários Pendentes").pack()
            listbox = tk.Listbox(win)
            for user in pending:
                listbox.insert('end', f"{user['username']} - {user['role']}")
            listbox.pack()
            def approve_selected():
                selection = listbox.curselection()
                if not selection:
                    return
                value = listbox.get(selection[0])
                username = value.split(' - ')[0]
                if approve_user(username):
                    messagebox.showinfo("Aprovação", f"Usuário {username} aprovado")
                    listbox.delete(selection[0])
                else:
                    messagebox.showerror("Erro", "Não foi possível aprovar")
            tk.Button(win, text="Aprovar", command=approve_selected).pack()

    def run_gui() -> None:
        if not _HAS_TK:
            print("tkinter não está disponível. Execute no modo CLI.")
            return
        app = AppGUI()
        app.mainloop()
else:
    # Placeholder when tkinter não disponível
    def run_gui() -> None:
        print("tkinter não está disponível. Execute no modo CLI.")


if __name__ == '__main__':
    # Se chamado diretamente, inicia CLI
    cli_main()