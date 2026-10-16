import asyncio
import os
from playwright.async_api import async_playwright
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env.txt")

USER = os.getenv("ERP_USER")
PASS = os.getenv("ERP_PASS")

async def test_erp_login():
    print(f"Tentando logar no ERP com usuário: {USER}...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        # 1. Página de Login
        await page.goto("https://erp.admsis.com/", wait_until="networkidle")
        await asyncio.sleep(1)
        
        # Se houver alerta de modal aberto, fecha ou remove
        await page.evaluate("""() => {
            const modal = document.querySelector('#eng_alerta');
            if (modal) modal.style.display = 'none';
            const backdrop = document.querySelector('.modal-backdrop');
            if (backdrop) backdrop.remove();
            document.body.classList.remove('modal-open');
        }""")
        
        # Preencher usuário e senha
        await page.fill("#usu_codigo", USER)
        await page.fill("#usu_senha", PASS)
        print("Campos preenchidos. Enviando formulário...")
        
        # Submete o login e aguarda navegação
        await asyncio.gather(
            page.wait_for_load_state("networkidle"),
            page.evaluate("document.querySelector('#frmLogin').submit()")
        )
        await asyncio.sleep(2)
        print("URL após login:", page.url)
        await page.screenshot(path="screenshot_pos_login.png")
        
        # Se ainda estiver na página de login, verifica se exibiu mensagem de erro
        alerta_text = await page.evaluate("""() => {
            const alerta = document.querySelector('#eng_alerta .modal-body');
            return alerta ? alerta.innerText.trim() : null;
        }""")
        if alerta_text:
            print("Mensagem de alerta encontrada na página:", alerta_text)
            
        # 2. Navegar para Comercial / Pedidos: 0101060100
        print("Navegando para Comercial / Pedidos (0101060100)...")
        await page.goto("https://erp.admsis.com/Home?eng_tela=0101060100", wait_until="networkidle")
        await asyncio.sleep(2)
        print("URL da tela de pedidos:", page.url)
        await page.screenshot(path="screenshot_pedidos.png")
        
        # Verifica se estamos na tela de pedidos
        titulo = await page.evaluate("""() => {
            const t = document.querySelector('#eng-tela-titulo h5');
            return t ? t.innerText.trim() : document.title;
        }""")
        print("Título da página atual:", titulo)
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_erp_login())
