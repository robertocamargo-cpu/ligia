import asyncio
import os
from playwright.async_api import async_playwright
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env.txt")
USER = os.getenv("ERP_USER")
PASS = os.getenv("ERP_PASS")

async def test_pdf_capture():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Garante que pdfViewerEnabled seja true
        context = await browser.new_context(
            accept_downloads=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        # Escuta novas abas (popups)
        popup_page = None
        def on_popup(p):
            nonlocal popup_page
            print("NOVA ABA / POPUP DETECTADA:", p.url)
            popup_page = p
        context.on("page", on_popup)
        
        # Escuta todas as respostas no contexto
        pdf_bytes = None
        async def on_response(res):
            nonlocal pdf_bytes
            ct = res.headers.get("content-type", "")
            if "pdf" in ct.lower() or "EngRelatorio" in res.url:
                print(f"[RES-PDF] Status {res.status} | Content-Type: {ct} | URL: {res.url}")
                try:
                    pdf_bytes = await res.body()
                    print(f"[RES-PDF] Baixados {len(pdf_bytes)} bytes de PDF!")
                except Exception as e:
                    print("[RES-PDF] Erro ao obter corpo:", e)
                    
        context.on("response", on_response)
        context.on("request", lambda r: print(f"[REQ] {r.method} {r.url}") if "EngRelatorio" in r.url else None)
        
        # Login
        print("Login...")
        await page.goto("https://erp.admsis.com/", wait_until="networkidle")
        await page.fill("#usu_codigo", USER)
        await page.fill("#usu_senha", PASS)
        await asyncio.gather(
            page.wait_for_load_state("networkidle"),
            page.evaluate("document.querySelector('#frmLogin').submit()")
        )
        await asyncio.sleep(2)
        
        # Pedidos
        print("Tela Pedidos...")
        await page.goto("https://erp.admsis.com/Home?eng_tela=0101060100", wait_until="networkidle")
        await asyncio.sleep(2)
        await page.select_option("#vda_situacao_id", "4")
        await asyncio.gather(
            page.wait_for_load_state("networkidle"),
            page.click("#ConfirmaFiltroS")
        )
        await asyncio.sleep(2)
        
        # Abre primeiro pedido
        print("Abrindo pedido 635781...")
        await asyncio.gather(
            page.wait_for_load_state("networkidle"),
            page.evaluate("EngNavegacao.selecionar('635781');")
        )
        await asyncio.sleep(2)
        
        # Executa f_btImpressao diretamente
        print("Chamando f_btImpressao()...")
        await page.evaluate("f_btImpressao();")
        
        # Aguarda a resposta
        for _ in range(15):
            if pdf_bytes:
                break
            await asyncio.sleep(1)
            
        if pdf_bytes:
            os.makedirs("downloads", exist_ok=True)
            with open("downloads/pedido_teste_635781.pdf", "wb") as f:
                f.write(pdf_bytes)
            print("PDF salvo com sucesso em downloads/pedido_teste_635781.pdf!")
        else:
            print("Não capturou pdf_bytes diretamente.")
            if popup_page:
                print("Popup URL:", popup_page.url)
                
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_pdf_capture())
