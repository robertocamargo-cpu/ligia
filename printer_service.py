import os
import sys
import ctypes
from ctypes import wintypes
import win32print
import win32con
from PIL import Image, ImageWin
import pypdfium2 as pdfium
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env.txt")
load_dotenv(dotenv_path=".env")

class DOCINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.INT),
        ("lpszDocName", wintypes.LPCWSTR),
        ("lpszOutput", wintypes.LPCWSTR),
        ("lpszDatatype", wintypes.LPCWSTR),
        ("fwType", wintypes.DWORD)
    ]

def get_installed_printers():
    """Retorna a lista de nomes de impressoras instaladas no sistema."""
    try:
        printers = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)
        return [p[2] for p in printers]
    except Exception as e:
        print(f"Aviso ao listar impressoras: {e}")
        return []

def get_default_printer():
    """Retorna o nome da impressora padrão do Windows no momento."""
    try:
        return win32print.GetDefaultPrinter()
    except Exception as e:
        print(f"Erro ao obter impressora padrão: {e}")
        return None

def get_target_printer():
    """Retorna a impressora configurada no .env ou a padrão do Windows."""
    env_printer = os.getenv("PRINTER_NAME")
    installed = get_installed_printers()
    
    if env_printer and env_printer.strip():
        chosen = env_printer.strip()
        if chosen in installed:
            return chosen
        else:
            default_p = get_default_printer()
            print(f"Aviso: Impressora configurada '{chosen}' não encontrada neste computador.")
            print(f"Impressoras disponíveis: {installed}")
            print(f"Usando impressora padrão: [{default_p}]")
            return default_p
            
    return get_default_printer()

def _imprimir_via_ctypes_gdi(pdf_path: str, printer_name: str) -> bool:
    """Imprime renderizando em 300 DPI via GDI32 diretamente (sem dependência de MFC/win32ui)."""
    pdf = pdfium.PdfDocument(pdf_path)
    gdi32 = ctypes.windll.gdi32
    
    hdc = gdi32.CreateDCW("WINSPOOL", printer_name, None, None)
    if not hdc:
        raise RuntimeError(f"Não foi possível criar Device Context para a impressora {printer_name}")
        
    try:
        doc_name = os.path.basename(pdf_path)
        di = DOCINFO(cbSize=ctypes.sizeof(DOCINFO), lpszDocName=doc_name)
        if gdi32.StartDocW(hdc, ctypes.byref(di)) <= 0:
            raise RuntimeError("StartDocW falhou.")
            
        printable_width = gdi32.GetDeviceCaps(hdc, win32con.HORZRES)
        printable_height = gdi32.GetDeviceCaps(hdc, win32con.VERTRES)
        
        for i, page in enumerate(pdf):
            gdi32.StartPage(hdc)
            
            pil_image = page.render(scale=300/72).to_pil()
            img_w, img_h = pil_image.size
            ratio = min(printable_width / img_w, printable_height / img_h)
            draw_w = int(img_w * ratio)
            draw_h = int(img_h * ratio)
            
            offset_x = (printable_width - draw_w) // 2
            offset_y = (printable_height - draw_h) // 2
            
            dib = ImageWin.Dib(pil_image)
            dib.draw(hdc, (offset_x, offset_y, offset_x + draw_w, offset_y + draw_h))
            
            gdi32.EndPage(hdc)
            
        gdi32.EndDoc(hdc)
        return True
    finally:
        gdi32.DeleteDC(hdc)

def imprimir_pdf(pdf_path: str, printer_name: str = None) -> bool:
    """
    Imprime um arquivo PDF silenciosamente na impressora configurada (ou informada),
    renderizando em alta resolução (300 DPI) via Windows GDI Spooler,
    sem abrir janelas de leitores de PDF.
    """
    if not os.path.exists(pdf_path):
        print(f"Arquivo não encontrado para impressão: {pdf_path}")
        return False
        
    if not printer_name:
        printer_name = get_target_printer()
        
    if not printer_name:
        print("Nenhuma impressora configurada ou padrão encontrada no Windows.")
        return False
        
    print(f"Despachando para impressão na impressora: [{printer_name}] - Arquivo: {pdf_path}")
    
    # 1. Tentar via GDI nativo direto
    try:
        if _imprimir_via_ctypes_gdi(pdf_path, printer_name):
            print(f"Impressão enviada com sucesso para o spooler da [{printer_name}].")
            return True
    except Exception as e:
        print(f"Falha ao imprimir via GDI nativo na impressora [{printer_name}]: {e}. Tentando fallback...")
        
    # 2. Fallback via ShellExecute printto
    try:
        import win32api
        win32api.ShellExecute(0, "printto", pdf_path, f'"{printer_name}"', ".", 0)
        print(f"Enviado via ShellExecute (printto) para [{printer_name}].")
        return True
    except Exception as ex2:
        print(f"Falha no fallback de impressão: {ex2}")
        return False

if __name__ == "__main__":
    p = get_target_printer()
    print("Impressora configurada para o robô:", p)
    print("Lista de impressoras disponíveis:", get_installed_printers())
