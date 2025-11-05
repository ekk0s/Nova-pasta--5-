"""
Simple Tkinter GUI for the NF-e Inventory and Financial Management System.

This module provides a graphical interface that wraps around the core
functionalities implemented in ``inventory_manager.py``. Users can import
invoices from a directory, view the current stock report and see
financial totals. The GUI is intentionally minimalistic to focus on
core requirements and can be expanded with additional features like
filters, graphs, login screens and data persistence.
"""

import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from inventory_manager import Inventory, FinancialReport, import_invoices_from_directory


class InventoryApp(tk.Tk):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        self.title("NF-e Inventory Management")
        self.geometry("700x500")
        self.resizable(False, False)

        # Initialize inventory and financial report
        self.inventory = Inventory()
        self.fin_report = FinancialReport()

        # Configure grid
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # Create widgets
        self.create_widgets()

    def create_widgets(self) -> None:
        """Set up the GUI widgets."""
        title_label = tk.Label(self, text="Sistema de Gestão de NF-e", font=("Arial", 18, "bold"))
        title_label.grid(row=0, column=0, pady=10)

        button_frame = tk.Frame(self)
        button_frame.grid(row=1, column=0, pady=5, sticky="nsew")
        button_frame.columnconfigure((0, 1, 2), weight=1)

        import_btn = tk.Button(button_frame, text="Importar Notas", command=self.import_notes)
        import_btn.grid(row=0, column=0, padx=10)

        stock_btn = tk.Button(button_frame, text="Relatório de Estoque", command=self.show_stock_report)
        stock_btn.grid(row=0, column=1, padx=10)

        fin_btn = tk.Button(button_frame, text="Relatório Financeiro", command=self.show_financial_report)
        fin_btn.grid(row=0, column=2, padx=10)

        # Treeview for stock display
        self.tree = ttk.Treeview(self, columns=("code", "desc", "qty", "price"), show="headings")
        self.tree.heading("code", text="Código")
        self.tree.heading("desc", text="Descrição")
        self.tree.heading("qty", text="Quantidade")
        self.tree.heading("price", text="Preço Unitário")
        self.tree.column("code", width=150)
        self.tree.column("desc", width=250)
        self.tree.column("qty", width=100, anchor="e")
        self.tree.column("price", width=100, anchor="e")
        self.tree.grid(row=2, column=0, sticky="nsew", padx=10, pady=10)

        # Scrollbar
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=2, column=1, sticky="ns")

    def import_notes(self) -> None:
        """Open a directory dialog and import XML invoices from the selected folder."""
        dir_path = filedialog.askdirectory(title="Selecione o diretório com arquivos XML")
        if dir_path:
            import_invoices_from_directory(dir_path, self.inventory, self.fin_report)
            messagebox.showinfo("Importação", f"Importação concluída do diretório:\n{dir_path}")

    def show_stock_report(self) -> None:
        """Display the stock report in the treeview."""
        # Clear existing entries
        for row in self.tree.get_children():
            self.tree.delete(row)
        report = self.inventory.get_stock_report()
        if not report:
            messagebox.showinfo("Estoque", "Nenhum produto no estoque.")
            return
        for code, name, qty, price in report:
            self.tree.insert('', 'end', values=(code, name, f"{qty:.2f}", f"R$ {price:.2f}"))

    def show_financial_report(self) -> None:
        """Display a message box with financial totals."""
        total_exp = self.fin_report.total_expenses
        total_rev = self.fin_report.total_revenue
        balance = self.fin_report.balance
        message = (f"Total de despesas (compras): R$ {total_exp:.2f}\n"
                   f"Total de receitas (vendas):   R$ {total_rev:.2f}\n"
                   f"Saldo líquido:              R$ {balance:.2f}")
        messagebox.showinfo("Relatório Financeiro", message)


def run_gui() -> None:
    """Run the Tkinter GUI application."""
    app = InventoryApp()
    app.mainloop()


if __name__ == '__main__':
    run_gui()