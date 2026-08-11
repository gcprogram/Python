import pandas as pd
import fnmatch
import tkinter as tk
from tkinter import filedialog, messagebox
import os


def select_file(title):
    root = tk.Tk()
    root.withdraw()
    path = filedialog.askopenfilename(title=title, filetypes=[("Tabellen", "*.xlsx *.xls *.csv")])
    root.destroy()
    return path


def process_raw_df(df_raw):
    """Sucht in einem Roh-DataFrame nach der Header-Zeile."""
    keywords = ["begünstigter", "verwendungszweck", "kategorie"]
    header_index = None

    for i, row in df_raw.iterrows():
        row_str = " ".join([str(v).lower() for v in row.values if pd.notna(v)])
        if any(k in row_str for k in keywords):
            header_index = i
            break

    if header_index is None:
        return None

    new_df = df_raw.iloc[header_index + 1:].copy()
    new_df.columns = [str(c).strip() for c in df_raw.iloc[header_index]]
    return new_df.fillna('')


def load_smart(path):
    ext = path.lower().rsplit('.', 1)[-1]
    try:
        if ext == 'csv':
            df_raw = pd.read_csv(path, sep=None, engine='python', header=None, dtype=str, encoding='utf-8-sig')
            res = process_raw_df(df_raw)
            if res is not None: return res
        else:
            with pd.ExcelFile(path) as xls:
                for sheet_name in xls.sheet_names:
                    df_raw = pd.read_excel(xls, sheet_name=sheet_name, header=None, dtype=str)
                    res = process_raw_df(df_raw)
                    if res is not None: return res

        # Fallback: Wenn gar nichts gefunden wurde, nimm die erste Zeile als Header
        if ext == 'csv':
            return pd.read_csv(path, sep=None, engine='python', dtype=str, encoding='utf-8-sig').fillna('')
        else:
            return pd.read_excel(path, dtype=str).fillna('')

    except Exception as e:
        raise Exception(f"Fehler beim Laden von {os.path.basename(path)}: {str(e)}")


def find_col(columns, search_term):
    for col in columns:
        if search_term.lower() in str(col).lower():
            return col
    return None


def apply_rules():
    rules_path = select_file("Regel-Datei auswählen")
    if not rules_path: return
    bank_path = select_file("Kontoauszug auswählen")
    if not bank_path: return

    try:
        df_rules = load_smart(rules_path)
        df_bank = load_smart(bank_path)

        # Spalten-Zuordnung
        c_beg_b = find_col(df_bank.columns, "Begünstigter")
        c_zwe_b = find_col(df_bank.columns, "Verwendungszweck")
        c_bet_b = find_col(df_bank.columns, "Betrag")

        c_beg_r = find_col(df_rules.columns, "Begünstigter")
        c_zwe_r = find_col(df_rules.columns, "Verwendungszweck")
        c_bet_r = find_col(df_rules.columns, "Betrag")  # Hier lag das Problem
        c_kat_r = find_col(df_rules.columns, "Kategorie")
        c_kom_r = find_col(df_rules.columns, "Kommentar")

        # Pflichtfelder Check
        if not c_beg_b or not c_beg_r or not c_kat_r:
            raise ValueError(f"Pflichtspalten fehlen!\nBank: {list(df_bank.columns)}\nRegeln: {list(df_rules.columns)}")

        def match_logic(bank_row):
            for _, rule in df_rules.iterrows():
                # 1. Begünstigter
                val_b = str(bank_row.get(c_beg_b, '')).lower()
                reg_b = str(rule.get(c_beg_r, '')).lower()
                m_beg = fnmatch.fnmatch(val_b, reg_b) if reg_b and reg_b != 'nan' else True

                # 2. Verwendungszweck
                val_z = str(bank_row.get(c_zwe_b, '')).lower()
                reg_z = str(rule.get(c_zwe_r, '')).lower() if c_zwe_r else ""
                m_zwe = fnmatch.fnmatch(val_z, reg_z) if reg_z and reg_z != 'nan' else True

                # 3. Betrag (Sicherheits-Check falls c_bet_r None ist)
                m_bet = True
                if c_bet_r and c_bet_b:
                    rule_betrag = str(rule.get(c_bet_r, '')).strip().replace(',', '.')
                    if rule_betrag and rule_betrag != 'nan':
                        bank_betrag = str(bank_row.get(c_bet_b, '')).strip().replace(',', '.')
                        m_bet = (bank_betrag == rule_betrag)

                if m_beg and m_zwe and m_bet:
                    kat = rule[c_kat_r]
                    kom = rule[c_kom_r] if c_kom_r else ""
                    return pd.Series([kat, kom])

            return pd.Series(["Ohne Kategorie", ""])

        # Verarbeitung
        df_bank[['Kategorie', 'Kommentar']] = df_bank.apply(match_logic, axis=1)

        output_path = os.path.splitext(bank_path)[0] + "_Kategorisiert.xlsx"
        df_bank.to_excel(output_path, index=False)
        messagebox.showinfo("Erfolg", f"Datei gespeichert:\n{output_path}")

    except Exception as e:
        messagebox.showerror("Fehler", f"Ein technischer Fehler ist aufgetreten:\n{str(e)}")


if __name__ == "__main__":
    apply_rules()