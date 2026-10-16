import asyncio
import os
import sys
import json
import sqlite3
from datetime import datetime
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv(dotenv_path=".env.txt")
load_dotenv(dotenv_path=".env")

USER = os.getenv("ERP_USER", "")
PASS = os.getenv("ERP_PASS", "")
BASE_URL = os.getenv("ERP_URL", "https://erp.admsis.com/")

async def buscar_hoje_producao():
    hoje = datetime.now().strftime("%d/%m/%Y")
    print(f"Consultando ERP com: Data do Pedido = {hoje} E Situação = PRODUÇÃO (4)...")

    # Conecta no DB local para cruzar status de impressão
    db_pedidos = {}
    try:
        conn = sqlite3.connect("pedidos_impressos.db")
        cur = conn.cursor()
        for row in cur.execute("SELECT vda_id, referencia, impresso_em FROM pedidos_impressos"):
            db_pedidos[str(row[0])] = {
                "referencia": row[1],
                "impresso_em": row[2]
            }
        conn.close()
    except Exception as e:
        print(f"Aviso ao consultar DB local: {e}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1600, "height": 1000})

        # Login
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

        # Tela Pedidos
        await page.goto(f"{BASE_URL}Home?eng_tela=0101060100", wait_until="networkidle")
        await asyncio.sleep(2)

        # Preenche filtros combinados: Data do Pedido (Hoje) + Situação (4 - PRODUÇÃO)
        await page.evaluate(f"""() => {{
            // Limpa outros filtros
            if (document.querySelector('#vda_data_entrega_i')) document.querySelector('#vda_data_entrega_i').value = '';
            if (document.querySelector('#vda_data_entrega_f')) document.querySelector('#vda_data_entrega_f').value = '';
            
            // Define data do pedido hoje
            if (document.querySelector('#vda_data_i')) document.querySelector('#vda_data_i').value = '{hoje}';
            if (document.querySelector('#vda_data_f')) document.querySelector('#vda_data_f').value = '{hoje}';
            
            // Seleciona Situação 4 (PRODUÇÃO)
            const sel = document.querySelector('#vda_situacao_id');
            if (sel) {{
                Array.from(sel.options).forEach(opt => {{
                    opt.selected = (opt.value === '4');
                }});
            }}
        }}""")

        print("Aplicando filtros (#ConfirmaFiltroS)...")
        await asyncio.gather(
            page.wait_for_load_state("networkidle"),
            page.click("#ConfirmaFiltroS")
        )
        await asyncio.sleep(3)

        # Extrai os pedidos da grade resultante
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

                const cells = Array.from(tr.querySelectorAll("td")).map(td => td.innerText.trim());

                if (vda_id || cells.length > 3) {
                    list.push({
                        vda_id: vda_id,
                        referencia: ref ? (ref.value || ref.innerText.trim()) : (cells[2] || ''),
                        cliente: cliente ? (cliente.value || cliente.innerText.trim()) : (cells[3] || ''),
                        filial: cells[4] || '',
                        operacao: cells[5] || '',
                        data_pedido: dataPedido ? (dataPedido.value || dataPedido.innerText.trim()) : (cells[6] || ''),
                        data_entrega: dataEntrega ? (dataEntrega.value || dataEntrega.innerText.trim()) : (cells[7] || ''),
                        total_produto: cells[10] || '',
                        total_pedido: total ? (total.value || total.innerText.trim()) : (cells[12] || ''),
                        situacao: situacao ? (situacao.value || situacao.innerText.trim()) : (cells[13] || ''),
                        vendedor: cells[14] || '',
                        celulas: cells
                    });
                }
            });
            return list;
        }""")

        await page.screenshot(path="screenshot_hoje_producao.png", full_page=True)
        print(f"\nTotal de pedidos encontrados hoje ({hoje}) em PRODUÇÃO: {len(pedidos)}")

        # Cruza com o banco de dados de pedidos já impressos
        for p_item in pedidos:
            v_id = p_item["vda_id"]
            if v_id in db_pedidos:
                p_item["status_impressao"] = f"JÁ IMPRESSO ({db_pedidos[v_id]['impresso_em']})"
            else:
                p_item["status_impressao"] = "PENDENTE NO ROBÔ (Ainda não impresso)"

        with open("pedidos_hoje_producao.json", "w", encoding="utf-8") as f:
            json.dump(pedidos, f, ensure_ascii=False, indent=2)

        for i, ped in enumerate(pedidos, 1):
            print(f"[{i}] ID: {ped['vda_id']} | Ref: {ped['referencia']} | Cliente: {ped['cliente']} | Data: {ped['data_pedido']} | Entrega: {ped['data_entrega']} | Total: {ped['total_pedido']} | Status Impressão: {ped['status_impressao']}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(buscar_hoje_producao())
