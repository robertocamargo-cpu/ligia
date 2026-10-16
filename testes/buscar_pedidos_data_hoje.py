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

async def buscar_pedidos_hoje():
    hoje = datetime.now().strftime("%d/%m/%Y")
    print(f"Filtrando no ERP apenas pela Data do Pedido = {hoje}...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1600, "height": 1000})

        # 1. Login
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
        await page.goto(f"{BASE_URL}Home?eng_tela=0101060100", wait_until="networkidle")
        await asyncio.sleep(2)

        # 3. Preencher filtros de data do pedido
        await page.evaluate(f"""() => {{
            // Limpa filtros prévios para trazer TUDO de hoje
            if (document.querySelector('#vda_situacao_id')) {{
                const sel = document.querySelector('#vda_situacao_id');
                Array.from(sel.options).forEach(opt => opt.selected = false);
            }}
            if (document.querySelector('#vda_data_entrega_i')) document.querySelector('#vda_data_entrega_i').value = '';
            if (document.querySelector('#vda_data_entrega_f')) document.querySelector('#vda_data_entrega_f').value = '';
            
            // Define data do pedido hoje
            if (document.querySelector('#vda_data_i')) document.querySelector('#vda_data_i').value = '{hoje}';
            if (document.querySelector('#vda_data_f')) document.querySelector('#vda_data_f').value = '{hoje}';
        }}""")

        print("Filtros preenchidos. Clicando em Filtrar (#ConfirmaFiltroS)...")
        await asyncio.gather(
            page.wait_for_load_state("networkidle"),
            page.click("#ConfirmaFiltroS")
        )
        await asyncio.sleep(3)

        # 4. Extrai colunas da tabela
        colunas = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll("#eng-tabela-resultado thead th, table thead th"))
                        .map(th => th.innerText.trim())
                        .filter(t => t.length > 0);
        }""")
        print("Colunas detectadas:", colunas)

        # 5. Extrai linhas da tabela de resultados
        pedidos = await page.evaluate("""() => {
            const list = [];
            const trs = document.querySelectorAll("table tbody tr[id^='tr_'], #eng-tabela-resultado tbody tr");
            
            trs.forEach(tr => {
                const link = tr.querySelector("a[href*='EngNavegacao.selecionar']");
                const vdaIdInput = tr.querySelector("input[name^='vda_id_']");
                const ref = tr.querySelector("input[name^='vda_referencia_']") || tr.querySelector("[id*='vda_referencia']");
                const cliente = tr.querySelector("[id*='vda_cliente']") || tr.querySelector("td[id*='cliente']");
                const dataPedido = tr.querySelector("input[name^='vda_data_']") || tr.querySelector("[id*='vda_data_']");
                const dataEntrega = tr.querySelector("input[name^='vda_data_entrega_']") || tr.querySelector("[id*='data_entrega']");
                const situacao = tr.querySelector("[id*='vda_situacao']") || tr.querySelector("td[id*='situacao']");
                const total = tr.querySelector("input[name^='vda_total_pedido_']") || tr.querySelector("[id*='total_pedido']");

                let vda_id = '';
                if (link) {
                    const m = link.getAttribute('href').match(/selecionar\\('(\\d+)'\\)/);
                    if (m) vda_id = m[1];
                } else if (vdaIdInput) {
                    vda_id = vdaIdInput.value;
                }

                // Coleta texto de todas as células para garantir nada perdido
                const cells = Array.from(tr.querySelectorAll("td")).map(td => td.innerText.trim());

                if (vda_id || cells.length > 3) {
                    list.push({
                        vda_id: vda_id,
                        referencia: ref ? (ref.value || ref.innerText.trim()) : '',
                        cliente: cliente ? (cliente.value || cliente.innerText.trim()) : '',
                        data_pedido: dataPedido ? (dataPedido.value || dataPedido.innerText.trim()) : '',
                        data_entrega: dataEntrega ? (dataEntrega.value || dataEntrega.innerText.trim()) : '',
                        situacao: situacao ? (situacao.value || situacao.innerText.trim()) : '',
                        total: total ? (total.value || total.innerText.trim()) : '',
                        celulas: cells
                    });
                }
            });
            return list;
        }""")

        await page.screenshot(path="screenshot_pedidos_hoje.png", full_page=True)
        print(f"\nTotal de pedidos encontrados hoje ({hoje}): {len(pedidos)}")
        
        with open("pedidos_hoje.json", "w", encoding="utf-8") as f:
            json.dump(pedidos, f, ensure_ascii=False, indent=2)

        for i, ped in enumerate(pedidos, 1):
            print(f"[{i}] ID: {ped['vda_id']} | Ref: {ped['referencia']} | Cliente: {ped['cliente']} | Data Pedido: {ped['data_pedido']} | Entrega: {ped['data_entrega']} | Situação: {ped['situacao']} | Total: {ped['total']}")
            if ped['celulas']:
                print(f"    Detalhes brutos da linha: {ped['celulas']}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(buscar_pedidos_hoje())
