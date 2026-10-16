import os
import sys
import time
import sqlite3
import logging
from datetime import datetime
import win32print

# Adiciona diretório raiz ao sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import storage
import printer_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

PEDIDOS_HOJE_PRODUCAO = [
    {
        "vda_id": "636539",
        "referencia": "4392/2026",
        "cliente": "32502 - HOTEL SAO PAULO ADMINISTRADOR HOTELEIRO LTDA (Fasano Belo Horizonte)",
        "entrega": "20/10/2026",
        "total": "R$ 4.750,00",
        "arquivo": os.path.abspath("downloads/pedido_636539_4392-2026.pdf")
    },
    {
        "vda_id": "636555",
        "referencia": "4394/2026",
        "cliente": "16212 - SEAGRASS SERVICOS DE SPA E BELEZA LTDA. (Aigai Spa)",
        "entrega": "30/10/2026",
        "total": "R$ 1.183,80",
        "arquivo": os.path.abspath("downloads/pedido_636555_4394-2026.pdf")
    },
    {
        "vda_id": "636531",
        "referencia": "4390/2026",
        "cliente": "02637 - L'HOTEL LTDA (L Hotel PortoBay São Paulo)",
        "entrega": "28/10/2026",
        "total": "R$ 11.333,90",
        "arquivo": os.path.abspath("downloads/pedido_636531_4390-2026.pdf")
    },
    {
        "vda_id": "636532",
        "referencia": "4391/2026",
        "cliente": "59525 - IRMANDADE DA SANTA CASA DE MISERICORDIA (Hospital Nora Teixeira)",
        "entrega": "16/11/2026",
        "total": "R$ 18.010,54",
        "arquivo": os.path.abspath("downloads/pedido_636532_4391-2026.pdf")
    },
    {
        "vda_id": "636547",
        "referencia": "4393/2026",
        "cliente": "59525 - IRMANDADE DA SANTA CASA DE MISERICORDIA (Hospital Nora Teixeira)",
        "entrega": "07/12/2026",
        "total": "R$ 33.456,48",
        "arquivo": os.path.abspath("downloads/pedido_636547_4393-2026.pdf")
    }
]

def main():
    printer_name = printer_service.get_target_printer()
    logging.info("==================================================================")
    logging.info("   INICIANDO IMPRESSÃO REAL DOS 5 PEDIDOS DE HOJE EM PRODUÇÃO    ")
    logging.info(f" Impressora Alvo: [{printer_name}]")
    logging.info(f" Total de pedidos a despachar: {len(PEDIDOS_HOJE_PRODUCAO)}")
    logging.info("==================================================================")

    storage.init_db()
    total_sucesso = 0

    for idx, ped in enumerate(PEDIDOS_HOJE_PRODUCAO, 1):
        vda_id = ped["vda_id"]
        ref = ped["referencia"]
        pdf_path = ped["arquivo"]

        logging.info(f"\n[{idx}/{len(PEDIDOS_HOJE_PRODUCAO)}] Processando Pedido: {ref} (ID: {vda_id})")
        logging.info(f"   Cliente: {ped['cliente']}")
        logging.info(f"   Valor: {ped['total']} | Entrega: {ped['entrega']}")
        logging.info(f"   Arquivo PDF: {pdf_path}")

        if not os.path.exists(pdf_path):
            logging.error(f"   ERRO: Arquivo PDF não encontrado: {pdf_path}")
            continue

        # Despacha para a impressora física
        sucesso = printer_service.imprimir_pdf(pdf_path, printer_name=printer_name)

        if sucesso:
            total_sucesso += 1
            storage.registrar_pedido_impresso(
                vda_id=vda_id,
                referencia=ref,
                cliente=ped["cliente"],
                data_entrega=ped["entrega"],
                arquivo_pdf=pdf_path
            )
            logging.info(f"   >> SUCESSO: Pedido {ref} despachado para a impressora [{printer_name}]!")
        else:
            logging.error(f"   >> FALHA ao enviar Pedido {ref} para a impressora.")

        # Pausa de 3 segundos entre trabalhos para evitar sobrecarga no spooler
        time.sleep(3)

    logging.info("\n==================================================================")
    logging.info(f" FIM DO DESPACHO: {total_sucesso} de {len(PEDIDOS_HOJE_PRODUCAO)} pedidos enviados com sucesso! ")
    logging.info("==================================================================")

    # Verifica status final do spooler
    try:
        h = win32print.OpenPrinter(printer_name)
        jobs = win32print.EnumJobs(h, 0, -1, 1)
        win32print.ClosePrinter(h)
        logging.info(f"Trabalhos atualmente em processamento no spooler da impressora: {len(jobs)}")
        for j in jobs:
            logging.info(f" - Spooler Job {j['JobId']}: {j['pDocument']} (Páginas: {j['TotalPages']})")
    except Exception as e:
        logging.warning(f"Aviso ao consultar spooler: {e}")

if __name__ == "__main__":
    main()
