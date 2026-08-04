import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from collections import defaultdict
import pdfplumber

# ================= CONFIGURAÇÃO =================
DEFAULT_LIMITE_BATCH = 4500

AREA_NUMERO = {
    "x0": 494,
    "x1": 500,
    "top": 230,
    "bottom": 240
}

FONT = ("Consolas", 10)
FONT_UI = ("Segoe UI", 10)
FONT_RESUMO = ("Segoe UI", 10, "bold")  # Mesma fonte do AutoScan


# ===============================================


def resource_path(relative_path):
    """ Obtém o caminho absoluto para o recurso, funciona para dev e para PyInstaller """
    try:
        # O PyInstaller cria uma pasta temporária e armazena o caminho em _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)



# ================= DOMÍNIO =================

def chave_grupo(nome_arquivo: str) -> int:
    try:
        return int(nome_arquivo.split("_", 1)[0])
    except Exception:
        raise ValueError(f"Nome de ficheiro inválido: {nome_arquivo}")


def extrair_numero(pdf_path: str) -> int:
    with pdfplumber.open(pdf_path) as pdf:
        if not pdf.pages:
            raise ValueError("PDF sem páginas")
        page = pdf.pages[0]
        palavras = page.extract_words()
        TOLERANCIA = 5
        for p in palavras:
            if (
                    AREA_NUMERO["x0"] - TOLERANCIA <= p["x0"] <= AREA_NUMERO["x1"] + TOLERANCIA
                    and AREA_NUMERO["top"] - TOLERANCIA <= p["top"] <= AREA_NUMERO["bottom"] + TOLERANCIA
                    and p["text"].isdigit()
            ):
                return int(p["text"])
        raise ValueError("Número não encontrado")


def criar_batches(grupos: dict[int, list[tuple[str, int]]], limite: int):
    batches = []
    batch_atual = []
    soma_atual = 0
    for grupo in sorted(grupos):
        itens = grupos[grupo]
        total_grupo = sum(v for _, v in itens)
        if total_grupo > limite:
            raise ValueError(
                f"O grupo {grupo} excede o limite ({total_grupo} > {limite})"
            )
        if soma_atual + total_grupo > limite and batch_atual:
            batches.append(batch_atual)
            batch_atual = []
            soma_atual = 0
        batch_atual.extend(itens)
        soma_atual += total_grupo
    if batch_atual:
        batches.append(batch_atual)
    return batches


# ================= UI =================
class PDFBatchApp:

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Processamento · AutoBatch")
        self.root.geometry("1000x750")

        # Correção do Ícone para funcionar no EXE
        try:
            icon_path = resource_path("icone.ico")  # Usa o nome exato do teu ficheiro
            self.root.iconbitmap(icon_path)
        except:
            pass

        ttk.Style(self.root).theme_use("vista")

        self._build_config()
        self._build_actions()
        self._build_progress()
        self._build_summary()
        self._build_batches_area()

    def ui(self, func, *args, **kwargs):
        self.root.after(0, lambda: func(*args, **kwargs))

    def _build_config(self):
        self.frame_config = ttk.LabelFrame(self.root, text="Configuração")
        self.frame_config.pack(fill="x", padx=10, pady=5)

        ttk.Label(self.frame_config, text="Pasta dos PDFs:").grid(row=0, column=0, padx=5, pady=10, sticky="w")
        self.entry_pasta = ttk.Entry(self.frame_config, width=60)
        self.entry_pasta.grid(row=0, column=1, padx=5)
        ttk.Button(self.frame_config, text="Procurar", command=self.browse).grid(row=0, column=2, padx=5)

        ttk.Label(self.frame_config, text="Limite por batch:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.entry_limite = ttk.Entry(self.frame_config, width=15)
        self.entry_limite.insert(0, str(DEFAULT_LIMITE_BATCH))
        self.entry_limite.grid(row=1, column=1, sticky="w", padx=5)

    def _build_actions(self):
        self.frame_acoes = ttk.LabelFrame(self.root, text="Ações")
        self.frame_acoes.pack(fill="x", padx=10, pady=5)

        container = ttk.Frame(self.frame_acoes)
        container.pack(fill="x", padx=10, pady=10)

        # Botões com tamanho aumentado (ipady e ipadx)
        estilo_botao = {'side': 'left', 'ipady': 5, 'ipadx': 10}

        ttk.Button(container, text="Processar", command=self.start).pack(**estilo_botao)
        ttk.Button(container, text="Limpar", command=self.clear).pack(**estilo_botao, padx=10)

    def _build_progress(self):
        self.frame_progresso = ttk.LabelFrame(self.root, text="Progresso")
        self.frame_progresso.pack(fill="x", padx=10, pady=5)

        self.progress = ttk.Progressbar(self.frame_progresso, mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True, padx=(10, 5), pady=15)

        self.lbl_percent = ttk.Label(self.frame_progresso, text="0%")
        self.lbl_percent.pack(side="left", padx=(0, 10))

    def _build_summary(self):
        self.frame_resumo = ttk.LabelFrame(self.root, text="Resumo")
        self.frame_resumo.pack(fill="x", padx=10, pady=5)

        self.lbl_summary = ttk.Label(
            self.frame_resumo,
            text="Nenhum processamento executado",
            font=FONT_RESUMO,
            foreground="#7f8c8d"  # Cinza inativo
        )
        self.lbl_summary.pack(anchor="w", padx=10, pady=10)

    def _build_batches_area(self):
        frame = ttk.LabelFrame(self.root, text="Resultados")
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.canvas = tk.Canvas(frame, bg="#f8f9fa", highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.canvas.yview)
        self.container = ttk.Frame(self.canvas)

        self.canvas_window = self.canvas.create_window((0, 0), window=self.container, anchor="nw")

        self.container.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width))

        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def browse(self):
        pasta = filedialog.askdirectory()
        if pasta:
            self.entry_pasta.delete(0, tk.END)
            self.entry_pasta.insert(0, pasta)

    def clear(self):
        for w in self.container.winfo_children():
            w.destroy()
        self.progress["value"] = 0
        self.lbl_percent.config(text="0%")
        self.lbl_summary.config(text="Nenhum processamento executado", foreground="#7f8c8d")

    def start(self):
        threading.Thread(target=self.processar, daemon=True).start()

    def processar(self):
        try:
            pasta = self.entry_pasta.get()
            limite = int(self.entry_limite.get())
            if not os.path.isdir(pasta):
                raise ValueError("Pasta inválida")

            self.ui(self.clear)
            self.ui(self.lbl_summary.config, text="A processar...", foreground="#2c3e50")

            arquivos = sorted(f for f in os.listdir(pasta) if f.lower().endswith(".pdf"))
            if not arquivos:
                raise ValueError("Nenhum PDF encontrado")

            grupos = defaultdict(list)

            for idx, nome in enumerate(arquivos, start=1):
                caminho = os.path.join(pasta, nome)
                grupo = chave_grupo(nome)
                valor = extrair_numero(caminho)
                grupos[grupo].append((nome, valor))

                p = int((idx / len(arquivos)) * 100)
                self.ui(self.progress.configure, value=p)
                self.ui(self.lbl_percent.config, text=f"{p}%")

            batches = criar_batches(grupos, limite)

            self.ui(self.mostrar_batches, batches)
            self.ui(self.lbl_summary.config,
                    text=f"PDFs processados: {len(arquivos)} | Batches criados: {len(batches)}",
                    foreground="#2c3e50")

        except Exception as e:
            self.ui(messagebox.showerror, "Erro", str(e))
            self.ui(self.lbl_summary.config, text="Erro no processamento")

    def mostrar_batches(self, batches):
        for idx, batch in enumerate(batches, start=1):
            total = sum(v for _, v in batch)
            lf = ttk.LabelFrame(self.container, text=f"Batch {idx} | PDFs: {len(batch)} | Total: {total}", padding=5)
            lf.pack(fill="x", padx=5, pady=5)

            resumo_frame = ttk.Frame(lf)
            resumo_frame.pack(fill="x", padx=10, pady=5)

            ttk.Label(resumo_frame, text=f"Início: {batch[0][0]}", font=FONT).pack(anchor="w")
            if len(batch) > 1:
                ttk.Label(resumo_frame, text=f"Fim: {batch[-1][0]}", font=FONT).pack(anchor="w")

            detalhes_frame = ttk.Frame(lf)
            for nome, valor in batch:
                ttk.Label(detalhes_frame, text=f"{nome} ({valor})", font=FONT).pack(anchor="w", padx=10)

            def toggle(f=detalhes_frame):
                if f.winfo_ismapped():
                    f.pack_forget()
                else:
                    f.pack(fill="x", padx=10, pady=5)

            ttk.Button(lf, text="Ver detalhes", command=toggle).pack(anchor="w", padx=10, pady=5)


if __name__ == "__main__":
    root = tk.Tk()
    app = PDFBatchApp(root)
    root.mainloop()