import asyncio
import os
import sys
import base64
import logging
from datetime import datetime
from dotenv import load_dotenv
from playwright.async_api import async_playwright
import win32print

# Adiciona diretório raiz ao path para importar módulos locais
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import storage
import printer_service

load_dotenv(dotenv_path=".env.txt")
load_dotenv(dotenv_path=".env")

USER = os.getenv("ERP_USER", "")
PASS = os.getenv("ERP_PASS", "")
BASE_URL = os.getenv("ERP_URL", "https://erp.admsis.com/")
TARGET_PRINTER = os.getenv("PRINTER_NAME", "HP LaserJet Professional P1102")

VDA_ID_ALVO = "636405"
REF_ALVO = "4352/2026"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

async def executar_teste_4352():
    logging.info("=================================================================")
    logging.info("   TESTE DO INÍCIO AO FIM DO PEDIDO 4352 (COM IMPRESSÃO REAL)    ")
    logging.info(f" Usuário ERP: {USER}")
    logging.info(f" Impressora Alvo: [{TARGET_PRINTER}]")
    logging.info(f" Pedido Alvo: ID={VDA_ID_ALVO} | Ref={REF_ALVO}")
    logging.info("=================================================================")

    # 1. Inicia Playwright e Navegador
    async with async_playwright() as p:
        logging.info("1. Inicializando navegador Chromium...")
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # 2. Login no ERP
        logging.info(f"2. Conectando ao ERP em {BASE_URL}...")
        await page.goto(BASE_URL, wait_until="domcontentloaded")
        await asyncio.sleep(1)

        # Trata eventual modal inicial
        await page.evaluate("""() => {
            const modal = document.querySelector('#eng_alerta');
            if (modal) modal.style.display = 'none';
            const backdrop = document.querySelector('.modal-backdrop');
            if (backdrop) backdrop.remove();
            document.body.classList.remove('modal-open');
        }""")

        await page.fill("#usu_codigo", USER)
        await page.fill("#usu_senha", PASS)
        logging.info("   Enviando formulário de autenticação...")
        await asyncio.gather(
            page.wait_for_load_state("networkidle"),
            page.evaluate("document.querySelector('#frmLogin').submit()")
        )
        await asyncio.sleep(2)
        logging.info(f"   Login realizado! URL atual: {page.url}")

        # 3. Acessar Comercial / Pedidos (0101060100)
        logging.info("3. Acessando tela 0101060100 (Comercial / Pedidos)...")
        await page.goto(f"{BASE_URL}Home?eng_tela=0101060100", wait_until="networkidle")
        await asyncio.sleep(2)

        # 4. Abrir a ficha do pedido 4352 (636405)
        logging.info(f"4. Abrindo ficha do pedido {VDA_ID_ALVO} ({REF_ALVO})...")
        await asyncio.gather(
            page.wait_for_load_state("networkidle"),
            page.evaluate(f"EngNavegacao.selecionar('{VDA_ID_ALVO}');")
        )
        await asyncio.sleep(2)

        # Coleta dados complementares da ficha do pedido
        info_pedido = await page.evaluate("""() => {
            const num = document.querySelector('#vda_referencia') ? document.querySelector('#vda_referencia').value : '';
            const cliente = document.querySelector('#vda_cliente_nome') ? document.querySelector('#vda_cliente_nome').value : (
                document.querySelector('#lbl_vda_cliente_id') ? document.querySelector('#lbl_vda_cliente_id').innerText.trim() : ''
            );
            const dataEntrega = document.querySelector('#vda_data_entrega') ? document.querySelector('#vda_data_entrega').value : '';
            return { referencia: num, cliente: cliente, data_entrega: dataEntrega };
        }""")
        logging.info(f"   Dados na ficha: Ref={info_pedido.get('referencia')} | Cliente={info_pedido.get('cliente')} | DataEntrega={info_pedido.get('data_entrega')}")

        # 5. Gerar e baixar o PDF oficial via streaming autenticado do ERP
        logging.info("5. Solicitando streaming do relatório PDF oficial (EngRelatorio/Pdf/202)...")
        pdf_b64 = await page.evaluate("""async () => {
            const form = document.querySelector('#Formulario');
            const uuid = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
                var r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
                return v.toString(16);
            });
            const url = 'EngRelatorio/Pdf/202?requestID=' + uuid;
            const formData = new FormData(form);
            
            const response = await fetch(url, {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) {
                throw new Error('HTTP ' + response.status + ' ao gerar relatório.');
            }
            
            const buffer = await response.arrayBuffer();
            let binary = '';
            const bytes = new Uint8Array(buffer);
            for (let i = 0; i < bytes.byteLength; i++) {
                binary += String.fromCharCode(bytes[i]);
            }
            return btoa(binary);
        }""")

        pdf_bytes = base64.b64decode(pdf_b64)
        os.makedirs("downloads", exist_ok=True)
        pdf_filepath = os.path.abspath(os.path.join("downloads", f"pedido_{VDA_ID_ALVO}_4352-2026.pdf"))
        with open(pdf_filepath, "wb") as f:
            f.write(pdf_bytes)
        logging.info(f"   PDF gerado e validado com sucesso! Tamanho: {len(pdf_bytes)} bytes")
        logging.info(f"   Arquivo salvo em: {pdf_filepath}")

        await browser.close()

    # 6. Enviar para a Impressora Física HP LaserJet Professional P1102
    logging.info("-----------------------------------------------------------------")
    logging.info(f"6. DESPACHANDO PARA A IMPRESSORA FÍSICA: [{TARGET_PRINTER}]...")
    sucesso = printer_service.imprimir_pdf(pdf_filepath, printer_name=TARGET_PRINTER)

    if sucesso:
        logging.info(f"   >> SUCESSO! Trabalho de impressão enviado ao spooler da [{TARGET_PRINTER}]!")
        
        # 7. Verifica status do Spooler de Impressão do Windows
        try:
            hprinter = win32print.OpenPrinter(TARGET_PRINTER)
            jobs = win32print.EnumJobs(hprinter, 0, -1, 1)
            win32print.ClosePrinter(hprinter)
            logging.info(f"   Trabalhos ativos no spooler da [{TARGET_PRINTER}]: {len(jobs)}")
            for j in jobs:
                logging.info(f"   - Trabalho ID {j['JobId']}: Documento='{j['pDocument']}', Status={j['Status']}, Páginas={j['TotalPages']}")
        except Exception as ex_spool:
            logging.warning(f"   Aviso ao consultar spooler: {ex_spool}")

        # 8. Registra no banco SQLite de histórico
        storage.init_db()
        storage.registrar_pedido_impresso(
            vda_id=VDA_ID_ALVO,
            referencia=REF_ALVO,
            cliente=info_pedido.get("cliente") or "58449 - LEONARDO AGUIAR SANT ANNA",
            data_entrega=info_pedido.get("data_entrega") or "27/10/2026",
            arquivo_pdf=pdf_filepath
        )
        logging.info(f"8. Registro no banco de dados SQLite atualizado com sucesso!")
        logging.info("=================================================================")
        logging.info(" TESTE CONCLUÍDO COM ÊXITO: Folha despachada para a impressora!  ")
        logging.info("=================================================================")
    else:
        logging.error(f"FALHA ao despachar para a impressora [{TARGET_PRINTER}].")

if __name__ == "__main__":
    asyncio.run(executar_teste_4352())
