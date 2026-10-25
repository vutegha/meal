"""Classeurs Excel produits par l'application."""

from io import BytesIO

from openpyxl import Workbook


def save_as_text(wb: Workbook) -> bytes:
    """Enregistre le classeur sans aucune formule.

    openpyxl prend pour une formule tout texte qui commence par « = ». Une réponse saisie sur le
    terrain (« =HYPERLINK(…) ») s'exécuterait alors chez la personne qui ouvre l'export : toutes
    les cellules restent du texte, l'application n'écrivant jamais de formule.
    """
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if cell.data_type == "f":
                    cell.data_type = "s"
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
