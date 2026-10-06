import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import os
from datetime import datetime
from fpdf import FPDF
from fpdf.enums import XPos, YPos

CONFIG_FILE = "azienda.json"
CLIENTI_FILE = "clienti.json"

class PreventiviApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Gestione Preventivi Professionale")
        
        self.root.geometry("1000x680")
        self.root.minsize(850, 600)

        self.dati_azienda = {"titolo": "", "bio": "", "piva": "", "cf": "", "iban": "", "logo_path": ""}
        self.carica_dati_azienda()
        
        self.clienti = []
        self.carica_clienti()
        self.articoli = [] 

        self.setup_ui()

    def setup_ui(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.tab_preventivo = ttk.Frame(self.notebook)
        self.tab_azienda = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_preventivo, text=" Compila Preventivo ")
        self.notebook.add(self.tab_azienda, text=" Impostazioni Azienda ")

        self.costruisci_tab_preventivo()
        self.costruisci_tab_azienda()

    def costruisci_tab_preventivo(self):
        toolbar = ttk.Frame(self.tab_preventivo)
        toolbar.pack(fill=tk.X, padx=10, pady=5)
        ttk.Button(toolbar, text="Nuovo", command=self.nuovo_preventivo).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Apri .prev", command=self.apri_preventivo).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Salva .prev", command=self.salva_preventivo).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Esporta PDF", command=self.esporta_pdf).pack(side=tk.RIGHT, padx=2)

        doc_frame = ttk.LabelFrame(self.tab_preventivo, text=" Dati Preventivo e Cliente ")
        doc_frame.pack(fill=tk.X, padx=10, pady=5)
        
        doc_frame.columnconfigure(1, weight=1)
        doc_frame.columnconfigure(3, weight=1)

        ttk.Label(doc_frame, text="Cliente:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.combo_cliente = ttk.Combobox(doc_frame, values=self.clienti)
        self.combo_cliente.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=5)

        ttk.Label(doc_frame, text="Data:").grid(row=0, column=2, sticky=tk.W, padx=5, pady=5)
        self.entry_data = ttk.Entry(doc_frame)
        self.entry_data.insert(0, datetime.now().strftime("%d/%m/%Y"))
        self.entry_data.grid(row=0, column=3, sticky=tk.EW, padx=5, pady=5)

        ttk.Label(doc_frame, text="Data Consegna:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.entry_consegna = ttk.Entry(doc_frame)
        self.entry_consegna.insert(0, "CONSEGNA ENTRO...")
        self.entry_consegna.grid(row=1, column=1, sticky=tk.EW, padx=5, pady=5)

        ttk.Label(doc_frame, text="Pagamento:").grid(row=1, column=2, sticky=tk.W, padx=5, pady=5)
        self.entry_pagamento = ttk.Entry(doc_frame)
        self.entry_pagamento.insert(0, "DA CONCORDARE")
        self.entry_pagamento.grid(row=1, column=3, sticky=tk.EW, padx=5, pady=5)

        input_frame = ttk.LabelFrame(self.tab_preventivo, text=" Aggiungi Riga Oggetto ")
        input_frame.pack(fill=tk.X, padx=10, pady=5)
        input_frame.columnconfigure(3, weight=1)

        ttk.Label(input_frame, text="Q.tà:").grid(row=0, column=0, padx=5, pady=5)
        self.entry_qty = ttk.Entry(input_frame, width=6)
        self.entry_qty.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(input_frame, text="Descrizione:").grid(row=0, column=2, padx=5, pady=5)
        self.entry_desc = ttk.Entry(input_frame)
        self.entry_desc.grid(row=0, column=3, sticky=tk.EW, padx=5, pady=5)

        ttk.Label(input_frame, text="Prezzo Unit (€):").grid(row=0, column=4, padx=5, pady=5)
        self.entry_prezzo = ttk.Entry(input_frame, width=12)
        self.entry_prezzo.grid(row=0, column=5, padx=5, pady=5)

        ttk.Button(input_frame, text="Aggiungi", command=self.aggiungi_articolo).grid(row=0, column=6, padx=10, pady=5)

        table_frame = ttk.Frame(self.tab_preventivo)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        colonne = ("qty", "desc", "prezzo", "totale")
        self.tree = ttk.Treeview(table_frame, columns=colonne, show="headings", height=6)
        self.tree.heading("qty", text="Q.tà")
        self.tree.column("qty", width=60, minwidth=50, anchor=tk.CENTER)
        self.tree.heading("desc", text="Descrizione Oggetto")
        self.tree.column("desc", width=400, minwidth=200, anchor=tk.W)
        self.tree.heading("prezzo", text="Prezzo Unitario")
        self.tree.column("prezzo", width=120, minwidth=80, anchor=tk.E)
        self.tree.heading("totale", text="Prezzo Totale")
        self.tree.column("totale", width=120, minwidth=80, anchor=tk.E)

        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        ttk.Button(self.tab_preventivo, text="Elimina Riga Selezionata", command=self.elimina_articolo).pack(anchor=tk.E, padx=10, pady=2)

        tot_frame = ttk.LabelFrame(self.tab_preventivo, text=" Configurazione Economica ")
        tot_frame.pack(fill=tk.X, padx=10, pady=5)

        inputs_layout = ttk.Frame(tot_frame)
        inputs_layout.pack(fill=tk.X, padx=5, pady=5)

        fields = [("IVA (%)", "entry_iva"), ("Sconto (%)", "entry_sconto"), ("Acconto (%)", "entry_acconto")]
        for idx, (label_text, attr_name) in enumerate(fields):
            ttk.Label(inputs_layout, text=label_text).grid(row=0, column=idx*2, padx=5, pady=2, sticky=tk.W)
            entry = ttk.Entry(inputs_layout, width=8)
            entry.insert(0, "0")
            entry.grid(row=0, column=idx*2+1, padx=5, pady=2, sticky=tk.W)
            entry.bind("<KeyRelease>", lambda e: self.aggiorna_totali())
            setattr(self, attr_name, entry)

        res_layout = ttk.Frame(tot_frame)
        res_layout.pack(fill=tk.X, padx=5, pady=5)

        self.lbl_imp = ttk.Label(res_layout, text="Imponibile: 0.00 €", font=("Arial", 10))
        self.lbl_imp.pack(side=tk.LEFT, padx=10)
        self.lbl_tot = ttk.Label(res_layout, text="Totale (+IVA): 0.00 €", font=("Arial", 10))
        self.lbl_tot.pack(side=tk.LEFT, padx=10)
        self.lbl_tots = ttk.Label(res_layout, text="Totale Scontato: 0.00 €", font=("Arial", 10, "bold"), foreground="blue")
        self.lbl_tots.pack(side=tk.LEFT, padx=10)
        self.lbl_saldo = ttk.Label(res_layout, text="SALDO: 0.00 €", font=("Arial", 12, "bold"), foreground="red")
        self.lbl_saldo.pack(side=tk.RIGHT, padx=10)

    def costruisci_tab_azienda(self):
        container = ttk.Frame(self.tab_azienda, padding=15)
        container.pack(fill=tk.BOTH, expand=True)

        ttk.Label(container, text="Logo Azienda (PNG/JPG):").pack(anchor=tk.W, pady=2)
        logo_f = ttk.Frame(container)
        logo_f.pack(fill=tk.X, pady=2)
        ttk.Button(logo_f, text="Sfoglia...", command=self.seleziona_logo).pack(side=tk.LEFT)
        self.lbl_logo = ttk.Label(logo_f, text=os.path.basename(self.dati_azienda.get("logo_path", "Nessun logo selezionato")))
        self.lbl_logo.pack(side=tk.LEFT, padx=10)

        ttk.Label(container, text="Nome Società / Intestatario:").pack(anchor=tk.W, pady=(10,2))
        self.entry_titolo = ttk.Entry(container)
        self.entry_titolo.insert(0, self.dati_azienda.get("titolo", ""))
        self.entry_titolo.pack(fill=tk.X, pady=2)

        ttk.Label(container, text="Indirizzo / Telefono / Info Contatto:").pack(anchor=tk.W, pady=(10,2))
        self.text_bio = tk.Text(container, height=4)
        self.text_bio.insert(tk.END, self.dati_azienda.get("bio", ""))
        self.text_bio.pack(fill=tk.X, pady=2)

        ttk.Label(container, text="Partita IVA:").pack(anchor=tk.W, pady=(10,2))
        self.entry_piva = ttk.Entry(container)
        self.entry_piva.insert(0, self.dati_azienda.get("piva", ""))
        self.entry_piva.pack(fill=tk.X, pady=2)

        grid_f = ttk.Frame(container)
        grid_f.pack(fill=tk.X, pady=10)
        grid_f.columnconfigure(0, weight=1)
        grid_f.columnconfigure(1, weight=1)

        sub_l = ttk.Frame(grid_f)
        sub_l.grid(row=0, column=0, sticky=tk.EW, padx=(0,5))
        ttk.Label(sub_l, text="Codice Fiscale:").pack(anchor=tk.W)
        self.entry_cf = ttk.Entry(sub_l)
        self.entry_cf.insert(0, self.dati_azienda.get("cf", ""))
        self.entry_cf.pack(fill=tk.X)

        sub_r = ttk.Frame(grid_f)
        sub_r.grid(row=0, column=1, sticky=tk.EW, padx=(5,0))
        ttk.Label(sub_r, text="IBAN per Bonifico:").pack(anchor=tk.W)
        self.entry_iban = ttk.Entry(sub_r)
        self.entry_iban.insert(0, self.dati_azienda.get("iban", ""))
        self.entry_iban.pack(fill=tk.X)

        ttk.Button(container, text="Salva Configurazione Azienda", command=self.salva_dati_azienda).pack(pady=20, fill=tk.X)

    def pulisci_testo(self, testo):
        """Sostituisce i caratteri speciali non supportati dal font Helvetica base"""
        if not testo: return ""
        sostituzioni = {
            '\u2013': '-', '\u2014': '-', # Trattini lunghi di Word
            '\u2018': "'", '\u2019': "'", # Apici curvi
            '\u201c': '"', '\u201d': '"', # Virgollette curve
            '\u2026': '...',              # Puntini di sospensione
            '\u00a0': ' ',                # Spazi unificatori
            '€': 'EUR'                    # Prevenzione extra per l'euro se fallisce
        }
        for originale, pulito in sostituzioni.items():
            testo = testo.replace(originale, pulito)
        return testo

    def seleziona_logo(self):
        path = filedialog.askopenfilename(filetypes=[("Immagini", "*.png *.jpg *.jpeg")])
        if path:
            self.dati_azienda["logo_path"] = path
            self.lbl_logo.config(text=os.path.basename(path))

    def carica_dati_azienda(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    self.dati_azienda = json.load(f)
            except Exception: pass

    def salva_dati_azienda(self):
        self.dati_azienda.update({
            "titolo": self.entry_titolo.get(),
            "bio": self.text_bio.get(1.0, tk.END).strip(),
            "piva": self.entry_piva.get(),
            "cf": self.entry_cf.get(),
            "iban": self.entry_iban.get()
        })
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.dati_azienda, f, indent=4)
        messagebox.showinfo("Successo", "Impostazioni aziendali memorizzate!")

    def carica_clienti(self):
        if os.path.exists(CLIENTI_FILE):
            try:
                with open(CLIENTI_FILE, "r", encoding="utf-8") as f:
                    self.clienti = sorted(json.load(f))
            except Exception: self.clienti = []

    def verifica_salva_cliente(self, nome):
        nome = nome.strip()
        if nome and nome not in self.clienti:
            self.clienti.append(nome)
            self.clienti.sort()
            with open(CLIENTI_FILE, "w", encoding="utf-8") as f:
                json.dump(self.clienti, f, indent=4)
            self.combo_cliente['values'] = self.clienti

    def aggiungi_articolo(self):
        try:
            qty = int(self.entry_qty.get())
            desc = self.entry_desc.get().strip()
            prezzo = float(self.entry_prezzo.get().replace(",", "."))
            if not desc: raise ValueError
        except ValueError:
            messagebox.showerror("Errore", "Dati articolo non validi. Controlla Q.tà e Prezzo.")
            return

        tot = qty * prezzo
        self.articoli.append({"qty": qty, "desc": desc, "prezzo": prezzo, "totale": tot})
        self.tree.insert("", tk.END, values=(qty, desc, f"{prezzo:.2f} €", f"{tot:.2f} €"))
        
        self.entry_qty.delete(0, tk.END)
        self.entry_desc.delete(0, tk.END)
        self.entry_prezzo.delete(0, tk.END)
        self.aggiorna_totali()

    def elimina_articolo(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Seleziona", "Clicca su una riga della tabella per eliminarla.")
            return
        for item in selected:
            idx = self.tree.index(item)
            del self.articoli[idx]
            self.tree.delete(item)
        self.aggiorna_totali()

    def get_float_val(self, entry):
        try: return float(entry.get().replace(",", "."))
        except ValueError: return 0.0

    def aggiorna_totali(self):
        imponibile = sum(item["totale"] for item in self.articoli)
        iva_perc = self.get_float_val(self.entry_iva)
        sconto_perc = self.get_float_val(self.entry_sconto)
        acconto_perc = self.get_float_val(self.entry_acconto)

        valore_iva = imponibile * (iva_perc / 100)
        totale = imponibile + valore_iva
        valore_sconto = totale * (sconto_perc / 100)
        totale_scontato = totale - valore_sconto
        valore_acconto = totale_scontato * (acconto_perc / 100)
        saldo = totale_scontato - valore_acconto

        self.lbl_imp.config(text=f"Imponibile: {imponibile:.2f} €")
        self.lbl_tot.config(text=f"Totale (+IVA): {totale:.2f} €")
        self.lbl_tots.config(text=f"Totale Scontato: {totale_scontato:.2f} €")
        self.lbl_saldo.config(text=f"SALDO: {saldo:.2f} €")

        return imponibile, valore_iva, totale, valore_sconto, totale_scontato, valore_acconto, saldo

    def nuovo_preventivo(self):
        self.articoli.clear()
        for i in self.tree.get_children(): self.tree.delete(i)
        self.combo_cliente.set("")
        self.entry_data.delete(0, tk.END)
        self.entry_data.insert(0, datetime.now().strftime("%d/%m/%Y"))
        self.entry_consegna.delete(0, tk.END)
        self.entry_consegna.insert(0, "CONSEGNA ENTRO...")
        self.entry_pagamento.delete(0, tk.END)
        self.entry_pagamento.insert(0, "DA CONCORDARE")
        for entry in (self.entry_iva, self.entry_sconto, self.entry_acconto):
            entry.delete(0, tk.END)
            entry.insert(0, "0")
        self.aggiorna_totali()

    def salva_preventivo(self):
        if not self.articoli: return messagebox.showwarning("Vuoto", "Nessun prodotto inserito.")
        cliente = self.combo_cliente.get().strip()
        if cliente: self.verifica_salva_cliente(cliente)

        fp = filedialog.asksaveasfilename(defaultextension=".prev", filetypes=[("File Preventivo", "*.prev")])
        if fp:
            dati = {
                "cliente": cliente, "data": self.entry_data.get(),
                "consegna": self.entry_consegna.get(), "pagamento": self.entry_pagamento.get(),
                "iva": self.entry_iva.get(), "sconto": self.entry_sconto.get(),
                "acconto": self.entry_acconto.get(), "articoli": self.articoli
            }
            with open(fp, "w", encoding="utf-8") as f: json.dump(dati, f, indent=4)
            messagebox.showinfo("Successo", "Preventivo salvato in formato editabile (.prev)")

    def apri_preventivo(self):
        fp = filedialog.askopenfilename(filetypes=[("File Preventivo", "*.prev")])
        if fp:
            with open(fp, "r", encoding="utf-8") as f: dati = json.load(f)
            self.nuovo_preventivo()
            self.combo_cliente.set(dati.get("cliente", ""))
            
            self.entry_data.delete(0, tk.END)
            self.entry_data.insert(0, dati.get("data", ""))
            self.entry_consegna.delete(0, tk.END)
            self.entry_consegna.insert(0, dati.get("consegna", ""))
            self.entry_pagamento.delete(0, tk.END)
            self.entry_pagamento.insert(0, dati.get("pagamento", ""))

            for e, val in zip((self.entry_iva, self.entry_sconto, self.entry_acconto), 
                              ("iva", "sconto", "acconto")):
                e.delete(0, tk.END)
                e.insert(0, dati.get(val, "0"))

            for art in dati.get("articoli", []):
                self.articoli.append(art)
                self.tree.insert("", tk.END, values=(art["qty"], art["desc"], f"{art['prezzo']:.2f} €", f"{art['totale']:.2f} €"))
            self.aggiorna_totali()

    def esporta_pdf(self):
        if not self.articoli: return messagebox.showwarning("Avviso", "Preventivo vuoto.")
        cliente = self.combo_cliente.get().strip()
        if cliente: self.verifica_salva_cliente(cliente)

        fp = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")])
        if not fp: return

        imp, val_iva, tot, val_sconto, tot_scont, val_acc, saldo = self.aggiorna_totali()

        pdf = FPDF()
        pdf.add_page()
        
        logo = self.dati_azienda.get("logo_path", "")
        if logo and os.path.exists(logo):
            try: pdf.image(logo, x=10, y=8, w=40)
            except Exception: pass

        # === INTESTAZIONE ===
        pdf.set_font("Helvetica", style="B", size=14)
        titolo_pulito = self.pulisci_testo(self.dati_azienda.get("titolo", "").upper())
        pdf.cell(0, 6, text=titolo_pulito, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R')
        
        pdf.set_font("Helvetica", size=9)
        bio_pulita = self.pulisci_testo(self.dati_azienda.get("bio", ""))
        pdf.multi_cell(0, 5, text=bio_pulita, align='R')
        
        testo_fiscale = self.pulisci_testo(f"P.IVA: {self.dati_azienda.get('piva', '')} | C.F.: {self.dati_azienda.get('cf', '')}")
        pdf.cell(0, 5, text=testo_fiscale, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R')
        pdf.ln(15)

        # === DATI CLIENTE ===
        pdf.set_font("Helvetica", style="B", size=16)
        pdf.cell(100, 8, text="PREVENTIVO", new_x=XPos.RIGHT, new_y=YPos.TOP)
        
        pdf.set_font("Helvetica", style="B", size=10)
        cliente_pulito = self.pulisci_testo(f"SPETT. {cliente.upper()}")
        pdf.cell(90, 8, text=cliente_pulito, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R')
        
        pdf.set_font("Helvetica", size=10)
        pdf.cell(0, 6, text=self.pulisci_testo(f"DATA: {self.entry_data.get()}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.cell(0, 6, text=self.pulisci_testo(f"DATA CONSEGNA: {self.entry_consegna.get()}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.cell(0, 6, text=self.pulisci_testo(f"PAGAMENTO: {self.entry_pagamento.get()}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(8)

        # === TABELLA ARTICOLI ===
        pdf.set_font("Helvetica", style="B", size=9)
        pdf.cell(15, 8, text="Q.TA'", border=1, align='C')
        pdf.cell(115, 8, text="DESCRIZIONE OGGETTO", border=1, align='L')
        pdf.cell(30, 8, text="PREZZO UNIT.", border=1, align='C')
        pdf.cell(30, 8, text="PREZZO TOT.", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')

        pdf.set_font("Helvetica", size=9)
        for art in self.articoli:
            pdf.cell(15, 8, text=str(art["qty"]), border=1, align='C')
            desc = art["desc"] if len(art["desc"]) < 65 else art["desc"][:62]+"..."
            pdf.cell(115, 8, text=self.pulisci_testo(desc), border=1, align='L')
            pdf.cell(30, 8, text=f"EUR {art['prezzo']:.2f}", border=1, align='R')
            pdf.cell(30, 8, text=f"EUR {art['totale']:.2f}", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R')
        pdf.ln(10)

        # === TOTALI ===
        pdf.set_font("Helvetica", size=10)
        pdf.cell(150, 6, text="IMPONIBILE:", align='R')
        pdf.cell(40, 6, text=f"EUR {imp:.2f}", align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
        if val_iva > 0:
            pdf.cell(150, 6, text=f"IVA ({self.entry_iva.get()}%):", align='R')
            pdf.cell(40, 6, text=f"EUR {val_iva:.2f}", align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_font("Helvetica", style="B", size=10)
            pdf.cell(150, 6, text="TOTALE:", align='R')
            pdf.cell(40, 6, text=f"EUR {tot:.2f}", align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_font("Helvetica", size=10)

        if val_sconto > 0:
            pdf.cell(150, 6, text=f"SCONTO ({self.entry_sconto.get()}%):", align='R')
            pdf.cell(40, 6, text=f"- EUR {val_sconto:.2f}", align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
        if val_acc > 0:
            pdf.cell(150, 6, text=f"ACCONTO ({self.entry_acconto.get()}%):", align='R')
            pdf.cell(40, 6, text=f"- EUR {val_acc:.2f}", align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        pdf.set_font("Helvetica", style="B", size=12)
        pdf.cell(150, 8, text="SALDO:", align='R')
        pdf.cell(40, 8, text=f"EUR {saldo:.2f}", align='R', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(15)

        # === FOOTER E FIRME ===
        pdf.set_font("Helvetica", style="B", size=9)
        nota_pulita = self.pulisci_testo("N.B. IL SALDO DEVE ESSERE EFFETTUATO TASSATIVAMENTE PRIMA DELLA CONSEGNA DELLA MERCE")
        pdf.multi_cell(0, 5, text=nota_pulita, align='C')
        pdf.ln(5)
        
        pdf.set_font("Helvetica", size=9)
        iban_pulito = self.pulisci_testo(f"Dati per Bonifico: {self.dati_azienda.get('iban', '')}")
        pdf.cell(0, 5, text=iban_pulito, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        pdf.ln(20)

        pdf.cell(95, 5, text="Il produttore", align='C')
        pdf.cell(95, 5, text="Il committente", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        pdf.cell(95, 10, text="_______________________", align='C')
        pdf.cell(95, 10, text="_______________________", align='C')

        pdf.output(fp)
        messagebox.showinfo("Successo", f"PDF generato correttamente!")

if __name__ == "__main__":
    root = tk.Tk()
    app = PreventiviApp(root)
    root.mainloop()