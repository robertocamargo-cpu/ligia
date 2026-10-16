import asyncio
import os
from playwright.async_api import async_playwright
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env.txt")
USER = os.getenv("ERP_USER")
PASS = os.getenv("ERP_PASS")

async def test_filtro():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # 1. Login
        await page.goto("https://erp.admsis.com/", wait_until="networkidle")
        await page.fill("#usu_codigo", USER)
        await page.fill("#usu_senha", PASS)
        await asyncio.gather(
            page.wait_for_load_state("networkidle"),
            page.evaluate("document.querySelector('#frmLogin').submit()")
        )
        await asyncio.sleep(2)
        
        # 2. Tela de Pedidos
        await page.goto("https://erp.admsis.com/Home?eng_tela=0101060100", wait_until="networkidle")
        await asyncio.sleep(2)
        
        # 3. Inspeciona se existe select de situação ou se precisa abrir o filtro
        situacao_exists = await page.query_selector("select[name*='situacao'], select#filtro_vda_situacao_id, select#vda_situacao_id")
        print("Select situação visível direto?", bool(situacao_exists))
        
        # Inspeciona botões de pesquisa / filtro
        pesquisar_btn = await page.query_selector("#Pesquisar")
        confirma_btn = await page.query_selector("#ConfirmaFiltroS")
        print("Botão #Pesquisar existe?", bool(pesquisar_btn))
        print("Botão #ConfirmaFiltroS existe antes de clicar em pesquisar?", bool(confirma_btn))
        
        # Se ConfirmaFiltroS não estiver visível, clica em #Pesquisar para abrir a barra de filtros
        if not confirma_btn and pesquisar_btn:
            print("Clicando em #Pesquisar para abrir filtros...")
            await page.click("#Pesquisar")
            await asyncio.sleep(1)
            confirma_btn = await page.query_selector("#ConfirmaFiltroS")
            print("Botão #ConfirmaFiltroS existe agora?", bool(confirma_btn))
            
        await page.screenshot(path="screenshot_filtro.png")
        
        # Salva o HTML com filtro aberto
        content = await page.content()
        with open("tela_com_filtro.html", "w", encoding="utf-8") as f:
            f.write(content)
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_filtro())
