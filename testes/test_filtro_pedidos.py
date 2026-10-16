import asyncio
import os
from playwright.async_api import async_playwright
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env.txt")
USER = os.getenv("ERP_USER")
PASS = os.getenv("ERP_PASS")

async def test_filtra_pedidos():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # 1. Login
        print("Efetuando login...")
        await page.goto("https://erp.admsis.com/", wait_until="networkidle")
        await page.fill("#usu_codigo", USER)
        await page.fill("#usu_senha", PASS)
        await asyncio.gather(
            page.wait_for_load_state("networkidle"),
            page.evaluate("document.querySelector('#frmLogin').submit()")
        )
        await asyncio.sleep(2)
        
        # 2. Tela de Pedidos
        print("Acessando Comercial / Pedidos (0101060100)...")
        await page.goto("https://erp.admsis.com/Home?eng_tela=0101060100", wait_until="networkidle")
        await asyncio.sleep(2)
        
        # 3. Selecionar Situação = 4 (PRODUÇÃO)
        print("Selecionando situação: 4 (PRODUÇÃO)...")
        await page.select_option("#vda_situacao_id", "4")
        
        # 4. Clicar em Filtrar (#ConfirmaFiltroS)
        print("Clicando em Filtrar (#ConfirmaFiltroS)...")
        await asyncio.gather(
            page.wait_for_load_state("networkidle"),
            page.click("#ConfirmaFiltroS")
        )
        await asyncio.sleep(3)
        
        # 5. Ordenar por Data da Entrega decrescente
        print("Aplicando ordenação vda_data_entrega DESC...")
        await page.evaluate("""() => {
            $('#order_by').val('vda_data_entrega DESC');
            EngNavegacao.refresh();
        }""")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)
        
        # 6. Salvar screenshot e HTML resultante
        await page.screenshot(path="screenshot_pedidos_producao.png")
        content = await page.content()
        with open("tela_pedidos_producao.html", "w", encoding="utf-8") as f:
            f.write(content)
            
        # 7. Listar os pedidos encontrados na tabela
        pedidos = await page.evaluate("""() => {
            const linhas = Array.from(document.querySelectorAll("table tbody tr"));
            return linhas.map(tr => {
                const idInput = tr.querySelector("input[name^='vda_id_']");
                const ref = tr.querySelector("span[id^='lbl_vda_referencia_']");
                const cliente = tr.querySelector("span[id^='lbl_vda_cliente_id_']");
                const dataEntrega = tr.querySelector("span[id^='lbl_vda_data_entrega_']");
                const total = tr.querySelector("span[id^='lbl_vda_total_pedido_']");
                return {
                    vda_id: idInput ? idInput.value : null,
                    referencia: ref ? ref.innerText.trim() : null,
                    cliente: cliente ? cliente.innerText.trim() : null,
                    dataEntrega: dataEntrega ? dataEntrega.innerText.trim() : null,
                    total: total ? total.innerText.trim() : null,
                };
            }).filter(p => p.vda_id || p.referencia);
        }""")
        
        print(f"Pedidos encontrados em PRODUÇÃO: {len(pedidos)}")
        for idx, ped in enumerate(pedidos, 1):
            print(f"[{idx}] ID: {ped['vda_id']} | Ref: {ped['referencia']} | Entrega: {ped['dataEntrega']} | Total: {ped['total']} | Cliente: {ped['cliente']}")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_filtra_pedidos())
