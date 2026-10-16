import asyncio
import os
import sys
import json
from datetime import datetime
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv(dotenv_path=".env.txt")
load_dotenv(dotenv_path=".env")

USER = os.getenv("ERP_USER", "")
PASS = os.getenv("ERP_PASS", "")
BASE_URL = os.getenv("ERP_URL", "https://erp.admsis.com/")

async def consultar_hoje():
    hoje_str = datetime.now().strftime("%d/%m/%Y")
    print(f"Data de hoje: {hoje_str}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1400, "height": 900})
        
        # 1. Login
        print("Realizando login...")
        await page.goto(BASE_URL, wait_until="domcontentloaded")
        await asyncio.sleep(1)
        
        await page.evaluate("""() => {
            const modal = document.querySelector('#eng_alerta');
            if (modal) modal.style.display = 'none';
            const backdrop = document.querySelector('.modal-backdrop');
            if (backdrop) backdrop.remove();
            document.body.classList.remove('modal-open');
        }""")
        
        await page.fill("#usu_codigo", USER)
        await page.fill("#usu_senha", PASS)
        await asyncio.gather(
            page.wait_for_load_state("networkidle"),
            page.evaluate("document.querySelector('#frmLogin').submit()")
        )
        await asyncio.sleep(2)
        
        # 2. Tela Comercial / Pedidos: 0101060100
        print("Acessando Comercial / Pedidos (0101060100)...")
        await page.goto(f"{BASE_URL}Home?eng_tela=0101060100", wait_until="networkidle")
        await asyncio.sleep(2)
        
        # 3. Mapear todos os campos de filtro na tela
        filtros = await page.evaluate("""() => {
            const itens = [];
            // Procura todos os inputs e selects na barra de filtro
            const formFiltro = document.querySelector('#FormularioFiltro') || document.querySelector('#eng-filtro-container') || document;
            formFiltro.querySelectorAll('input, select').forEach(el => {
                const id = el.id || '';
                const name = el.name || '';
                const label = el.closest('div') ? (el.closest('div').querySelector('label') ? el.closest('div').querySelector('label').innerText.trim() : '') : '';
                itens.push({
                    id: id,
                    name: name,
                    type: el.type,
                    value: el.value,
                    label: label
                });
            });
            return itens;
        }""")
        
        print("\n--- Filtros disponíveis na tela ---")
        date_inputs = []
        for f in filtros:
            if any(term in (f['id'] + f['name'] + f['label']).lower() for term in ['data', 'dt_', 'periodo', 'emissao', 'pedido', 'situacao']):
                print(f"ID: {f['id']} | Name: {f['name']} | Label: '{f['label']}' | Value: '{f['value']}' | Type: {f['type']}")
                date_inputs.append(f)
                
        # 4. Inspecionar as colunas da grade atual
        colunas = await page.evaluate("""() => {
            const cols = [];
            document.querySelectorAll('table thead th').forEach(th => {
                cols.push(th.innerText.trim());
            });
            return cols;
        }""")
        print("\n--- Colunas da tabela ---")
        print(colunas)
        
        # 5. Salva screenshot para auditoria visual
        await page.screenshot(path="screenshot_tela_filtro_pedidos.png")
        
        # 6. Salva HTML do filtro para análise exata
        filtro_html = await page.evaluate("""() => {
            const f = document.querySelector('#FormularioFiltro') || document.querySelector('.card-body');
            return f ? f.innerHTML : '';
        }""")
        with open("filtro_pedidos.html", "w", encoding="utf-8") as file:
            file.write(filtro_html)
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(consultar_hoje())
