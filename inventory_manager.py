"""
Inventory Management System for NF-e (Nota Fiscal Eletrônica)

This module defines a simple inventory and financial management system that
parses Brazilian electronic invoices (NF‑e) from XML files. It provides
functionalities to import purchase and sales invoices, update product stock
levels, and compute basic financial reports such as total revenue, total
expenses and net balance. While the project specification suggests a GUI,
this implementation focuses on a command‑line interface (CLI) to meet the
core requirements: XML parsing, inventory control and report generation.

Classes and Functions
---------------------

* ``Product`` – Data class representing a product identified by its
  code (``cProd``) and description (``xProd``). It tracks the current
  quantity in stock as well as the last unit price seen in invoices.

* ``InvoiceItem`` – Represents an item within an invoice, capturing the
  product code, name, quantity, unit price and subtotal.

* ``Invoice`` – Represents an invoice (either purchase or sale). It
  stores the basic header information (invoice number, date/time and
  emitter/destination) and a list of items. It also carries a type flag
  (``tpNF``) that indicates whether the invoice is incoming (0) or
  outgoing (1).

* ``Inventory`` – Manages a collection of ``Product`` instances. It
  provides methods to adjust quantities based on invoice items and to
  generate stock reports.

* ``FinancialReport`` – Tracks financial movements derived from
  invoices. It maintains the total revenue (sales) and expenses
  (purchases) and computes the resulting balance.

* ``parse_nfe_xml`` – Reads an NF‑e XML file and returns an ``Invoice``
  instance by extracting header and item data. The parser uses
  ``xml.etree.ElementTree`` and accounts for the NF‑e namespace.

* CLI entry point – Provides a text‑based menu for users to import
  invoices, view the current stock report and financial summary.

Usage
-----

To run the program from the command line:

.. code-block:: bash

   python inventory_manager.py

The script will prompt for a directory containing XML invoices and offer
options to import them, display reports or quit. The provided XML files
(``nfe_000001.xml``–``nfe_000009.xml``) can be used for testing.
"""

from __future__ import annotations

import os
import sys
import glob
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple


###############################################################################
# Data classes
###############################################################################

@dataclass
class Product:
    """Represents a product with stock information."""

    code: str
    name: str
    quantity: float = 0.0
    unit_price: float = 0.0

    def adjust_quantity(self, delta: float, unit_price: float) -> None:
        """Adjust the product's quantity and update unit price.

        Args:
            delta: Positive to increase stock, negative to decrease.
            unit_price: The unit price from the invoice item.
        """
        self.quantity += delta
        # Update unit price only if delta is non-zero
        if delta != 0:
            self.unit_price = unit_price


@dataclass
class InvoiceItem:
    """Represents an item within an invoice."""

    product_code: str
    product_name: str
    quantity: float
    unit_price: float
    subtotal: float


@dataclass
class Invoice:
    """Represents an NF-e invoice (purchase or sale)."""

    number: str
    date: datetime
    tpNF: int  # 0 for purchase (entrada), 1 for sale (saida)
    emitter: str
    destination: str
    items: List[InvoiceItem] = field(default_factory=list)

    @property
    def total_value(self) -> float:
        return sum(item.subtotal for item in self.items)


###############################################################################
# Inventory and Financial Report Management
###############################################################################

class Inventory:
    """Manages product stock levels."""

    def __init__(self) -> None:
        self.products: Dict[str, Product] = {}

    def apply_invoice(self, invoice: Invoice) -> None:
        """Update stock based on an invoice.

        Args:
            invoice: The parsed invoice to apply.
        """
        sign = 1.0 if invoice.tpNF == 0 else -1.0  # purchases increase stock, sales decrease
        for item in invoice.items:
            product = self.products.get(item.product_code)
            if not product:
                # Create new product if it doesn't exist
                product = Product(code=item.product_code, name=item.product_name)
                self.products[item.product_code] = product
            # Adjust quantity according to invoice type
            product.adjust_quantity(delta=sign * item.quantity, unit_price=item.unit_price)

    def get_stock_report(self) -> List[Tuple[str, str, float, float]]:
        """Return a list of current stock entries.

        Each entry is a tuple: (product_code, product_name, quantity, unit_price).
        """
        report = []
        for product in sorted(self.products.values(), key=lambda p: p.code):
            report.append((product.code, product.name, product.quantity, product.unit_price))
        return report


class FinancialReport:
    """Tracks financial totals for purchases and sales."""

    def __init__(self) -> None:
        self.total_expenses: float = 0.0
        self.total_revenue: float = 0.0

    def apply_invoice(self, invoice: Invoice) -> None:
        """Update revenue/expenses based on an invoice."""
        if invoice.tpNF == 0:
            # Purchase: increase expenses
            self.total_expenses += invoice.total_value
        else:
            # Sale: increase revenue
            self.total_revenue += invoice.total_value

    @property
    def balance(self) -> float:
        """Return net balance: revenue minus expenses."""
        return self.total_revenue - self.total_expenses


###############################################################################
# XML Parsing
###############################################################################

def parse_nfe_xml(path: str) -> Optional[Invoice]:
    """Parse an NF-e XML file and return an Invoice object.

    Args:
        path: Path to the XML file.

    Returns:
        Invoice if parsing succeeds, otherwise ``None``.
    """
    try:
        tree = ET.parse(path)
    except ET.ParseError as exc:
        print(f"Error parsing '{path}': {exc}")
        return None
    root = tree.getroot()
    # NF-e elements use a default namespace; we need to account for it
    ns = {"nfe": "http://www.portalfiscal.inf.br/nfe"}

    # Extract header information
    ide = root.find('.//nfe:ide', ns)
    if ide is None:
        print(f"File '{path}' missing <ide> tag")
        return None
    nNF = ide.findtext('nfe:nNF', default='UNKNOWN', namespaces=ns)
    tpNF_text = ide.findtext('nfe:tpNF', default='0', namespaces=ns)
    try:
        tpNF = int(tpNF_text)
    except ValueError:
        tpNF = 0
    dhEmi_text = ide.findtext('nfe:dhEmi', namespaces=ns)
    try:
        date = datetime.fromisoformat(dhEmi_text)
    except Exception:
        # Fallback to current time if parsing fails
        date = datetime.now()

    # Extract emitter and destination names (may be CNPJ/CPF)
    emit = root.find('.//nfe:emit', ns)
    dest = root.find('.//nfe:dest', ns)
    emitter_name = emit.findtext('nfe:xNome', default='', namespaces=ns) if emit is not None else ''
    dest_name = dest.findtext('nfe:xNome', default='', namespaces=ns) if dest is not None else ''

    # Extract invoice items
    items: List[InvoiceItem] = []
    for det in root.findall('.//nfe:det', ns):
        prod = det.find('nfe:prod', ns)
        if prod is None:
            continue
        code = prod.findtext('nfe:cProd', default='', namespaces=ns).strip()
        name = prod.findtext('nfe:xProd', default='', namespaces=ns).strip()
        quantity_text = prod.findtext('nfe:qCom', default='0', namespaces=ns)
        unit_price_text = prod.findtext('nfe:vUnCom', default='0', namespaces=ns)
        subtotal_text = prod.findtext('nfe:vProd', default='0', namespaces=ns)
        try:
            quantity = float(quantity_text.replace(',', '.'))
        except ValueError:
            quantity = 0.0
        try:
            unit_price = float(unit_price_text.replace(',', '.'))
        except ValueError:
            unit_price = 0.0
        try:
            subtotal = float(subtotal_text.replace(',', '.'))
        except ValueError:
            subtotal = quantity * unit_price
        items.append(InvoiceItem(
            product_code=code,
            product_name=name,
            quantity=quantity,
            unit_price=unit_price,
            subtotal=subtotal
        ))

    return Invoice(
        number=nNF,
        date=date,
        tpNF=tpNF,
        emitter=emitter_name,
        destination=dest_name,
        items=items
    )


###############################################################################
# CLI Implementation
###############################################################################

def import_invoices_from_directory(dir_path: str, inventory: Inventory, fin_report: FinancialReport) -> None:
    """Import all NF-e XML files from a directory into the system.

    Files with extension ``.xml`` are parsed and applied to the inventory and
    financial report. Files that fail to parse are skipped.
    """
    xml_files = glob.glob(os.path.join(dir_path, '*.xml'))
    if not xml_files:
        print(f"No XML files found in directory: {dir_path}")
        return
    for file in xml_files:
        invoice = parse_nfe_xml(file)
        if invoice:
            inventory.apply_invoice(invoice)
            fin_report.apply_invoice(invoice)
            print(f"Imported invoice {invoice.number} from {file}")
        else:
            print(f"Skipping invalid XML: {file}")


def display_stock_report(inventory: Inventory) -> None:
    """Print the current stock report to the console."""
    report = inventory.get_stock_report()
    if not report:
        print("No products in stock.")
        return
    print("\nStock Report:\n" + '-' * 50)
    print(f"{'Code':<20} {'Description':<20} {'Qty':>10} {'Unit Price':>12}")
    print('-' * 50)
    for code, name, qty, price in report:
        print(f"{code:<20} {name:<20} {qty:>10.2f} {price:>12.2f}")
    print('-' * 50)


def display_financial_report(fin_report: FinancialReport) -> None:
    """Print the financial summary to the console."""
    print("\nFinancial Report:\n" + '-' * 50)
    print(f"Total expenses (purchases): R$ {fin_report.total_expenses:.2f}")
    print(f"Total revenue  (sales):    R$ {fin_report.total_revenue:.2f}")
    print(f"Net balance:                R$ {fin_report.balance:.2f}")
    print('-' * 50)


def main() -> None:
    """Entry point for the command‑line interface."""
    print("NF-e Inventory and Financial Management System")
    inventory = Inventory()
    fin_report = FinancialReport()
    while True:
        print("\nMenu:")
        print("1. Import invoices from directory")
        print("2. Show stock report")
        print("3. Show financial report")
        print("4. Quit")
        choice = input("Select an option: ").strip()
        if choice == '1':
            dir_path = input("Enter directory path containing XML files: ").strip()
            if not os.path.isdir(dir_path):
                print(f"Invalid directory: {dir_path}")
            else:
                import_invoices_from_directory(dir_path, inventory, fin_report)
        elif choice == '2':
            display_stock_report(inventory)
        elif choice == '3':
            display_financial_report(fin_report)
        elif choice == '4':
            print("Exiting...")
            break
        else:
            print("Invalid option. Please try again.")


if __name__ == '__main__':
    main()