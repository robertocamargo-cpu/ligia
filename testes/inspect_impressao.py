import asyncio
import os
from playwright.async_api import async_playwright
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env.txt")
USER = os.getenv("ERP_USER")
PASS = os.getenv("ERP_PASS")

async def inspect_f_btImpressao():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # Login
        await page.goto("https://erp.admsis.com/", wait_until="networkidle")
        await page.fill("#usu_codigo", USER)
        await page.fill("#usu_senha", PASS)
        await asyncio.gather(
            page.wait_for_load_state("networkidle"),
            page.evaluate("document.querySelector('#frmLogin').submit()")
        )
        await asyncio.sleep(2)
        
        # Pedidos
        await page.goto("https://erp.admsis.com/Home?eng_tela=0101060100", wait_until="networkidle")
        await asyncio.sleep(2)
        await page.select_option("#vda_situacao_id", "4")
        await asyncio.gather(
            page.wait_for_load_state("networkidle"),
            page.click("#ConfirmaFiltroS")
        )
        await asyncio.sleep(2)
        
        # Abre o primeiro pedido (635781)
        await asyncio.gather(
            page.wait_for_load_state("networkidle"),
            page.evaluate("EngNavegacao.selecionar('635781');")
        )
        await asyncio.sleep(2)
        
        # Pega a definição das funções
        fns = await page.evaluate("""() => {
            return {
                f_btImpressao: typeof f_btImpressao !== 'undefined' ? f_btImpressao.toString() : null,
                abrirRelatorioModal: typeof abrirRelatorioModal !== 'undefined' ? abrirRelatorioModal.toString() : null,
                formAction: document.querySelector('#Formulario') ? document.querySelector('#Formulario').action : null,
                formTarget: document.querySelector('#Formulario') ? document.querySelector('#Formulario').target : null,
                modals: Array.from(document.querySelectorAll('.modal')).map(m => ({id: m.id, class: m.className, display: m.style.display})),
                iframes: Array.from(document.querySelectorAll('iframe')).map(i => ({id: i.id, name: i.name, src: i.src}))
            };
        }""")
        
        print("f_btImpressao code:\n", fns['f_btImpressao'])
        print("abrirRelatorioModal code:\n", fns['abrirRelatorioModal'])
        print("Form action/target:", fns['formAction'], fns['formTarget'])
        print("Iframes:", fns['iframes'])
        print("Modals:", fns['modals'])
        
        # Agora vamos escutar requisições de rede
        page.on("request", lambda req: print(f"REQ: {req.method} {req.url}"))
        page.on("response", lambda res: print(f"RES: {res.status} {res.url}"))
        
        print("\n--- Clicando em #btImpressao ---")
        await page.click("#btImpressao")
        await asyncio.sleep(5)
        
        # Inspeciona iframes pós clique
        iframes_pos = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('iframe')).map(i => ({id: i.id, name: i.name, src: i.src}));
        }""")
        print("Iframes pós clique:", iframes_pos)
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(inspect_f_btImpressao())
