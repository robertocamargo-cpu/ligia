import asyncio
import os
import base64
from playwright.async_api import async_playwright
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env.txt")
USER = os.getenv("ERP_USER")
PASS = os.getenv("ERP_PASS")

async def test_fetch_pdf():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
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
        
        # Baixar o PDF via fetch executado no contexto autenticado da página
        print("Obtendo PDF via fetch autenticado com os dados do formulário...")
        pdf_b64 = await page.evaluate("""async () => {
            const form = document.querySelector('#Formulario');
            // Gera um UUID para o requestID exatamente como o ERP faz
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
                throw new Error('Falha no download do relatório: ' + response.statusText);
            }
            
            const buffer = await response.arrayBuffer();
            let binary = '';
            const bytes = new Uint8Array(buffer);
            for (let i = 0; i < bytes.byteLength; i++) {
                binary += String.fromCharCode(bytes[i]);
            }
            return btoa(binary);
        }""")
        
        if pdf_b64:
            pdf_bytes = base64.b64decode(pdf_b64)
            print(f"Sucesso absoluto! PDF obtido com {len(pdf_bytes)} bytes!")
            os.makedirs("downloads", exist_ok=True)
            output_file = "downloads/pedido_635781.pdf"
            with open(output_file, "wb") as f:
                f.write(pdf_bytes)
            print(f"Arquivo salvo com sucesso em: {output_file}")
            
            # Valida se os primeiros bytes são %PDF
            if pdf_bytes.startswith(b"%PDF"):
                print("Arquivo é um PDF válido (%PDF encontrado no cabeçalho)!")
            else:
                print("Aviso: cabeçalho não começa com %PDF:", pdf_bytes[:50])
        else:
            print("Não retornou dados.")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_fetch_pdf())
