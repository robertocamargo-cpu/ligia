import asyncio
import os
from playwright.async_api import async_playwright
from dotenv import load_dotenv
import storage

load_dotenv(dotenv_path=".env.txt")
load_dotenv(dotenv_path=".env")

USER = os.getenv("ERP_USER", "")
PASS = os.getenv("ERP_PASS", "")
BASE_URL = os.getenv("ERP_URL", "https://erp.admsis.com/")

async def mapear_todos_existentes():
    storage.init_db()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # Login
        print("Logando...")
        await page.goto(BASE_URL, wait_until="networkidle")
        await page.fill("#usu_codigo", USER)
        await page.fill("#usu_senha", PASS)
        await asyncio.gather(
            page.wait_for_load_state("networkidle"),
            page.evaluate("document.querySelector('#frmLogin').submit()")
        )
        await asyncio.sleep(2)

        # Pedidos
        print("Tela Pedidos...")
        await page.goto(f"{BASE_URL}Home?eng_tela=0101060100", wait_until="networkidle")
        await asyncio.sleep(2)
        await page.select_option("#vda_situacao_id", "4")
        await asyncio.gather(
            page.wait_for_load_state("networkidle"),
            page.click("#ConfirmaFiltroS")
        )
        await asyncio.sleep(2)

        # Ordenar por entrega DESC
        await page.evaluate("""() => {
            $('#order_by').val('vda_data_entrega DESC');
            EngNavegacao.refresh();
        }""")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)

        todos_pedidos = []

        while True:
            # Coleta pedidos da página atual
            pedidos_pagina = await page.evaluate("""() => {
                const list = [];
                const rows = document.querySelectorAll("table tbody tr[id^='tr_']");
                rows.forEach(tr => {
                    const link = tr.querySelector("a[href*='EngNavegacao.selecionar']");
                    const ref = tr.querySelector("input[name^='vda_referencia_']");
                    const clienteLabel = tr.querySelector("td[id*='vda_cliente_id'] a");
                    const dataEntrega = tr.querySelector("input[name^='vda_data_entrega_']");
                    if (link) {
                        const match = link.getAttribute('href').match(/selecionar\\('(\\d+)'\\)/);
                        if (match) {
                            list.push({
                                vda_id: match[1],
                                referencia: ref ? ref.value : '',
                                cliente: clienteLabel ? clienteLabel.innerText.trim() : '',
                                data_entrega: dataEntrega ? dataEntrega.value : ''
                            });
                        }
                    }
                });
                return list;
            }""")
            
            for p_item in pedidos_pagina:
                if not any(x['vda_id'] == p_item['vda_id'] for x in todos_pedidos):
                    todos_pedidos.append(p_item)

            # Checa se existe próxima página
            tem_proximo = await page.evaluate("""() => {
                return typeof Pagina !== 'undefined' && typeof Paginas !== 'undefined' && Pagina < Paginas;
            }""")

            if tem_proximo:
                print("Avançando para próxima página...")
                await asyncio.gather(
                    page.wait_for_load_state("networkidle"),
                    page.evaluate("EngNavegacao.proximo();")
                )
                await asyncio.sleep(2)
            else:
                break

        print(f"Total de pedidos encontrados em PRODUÇÃO: {len(todos_pedidos)}")
        cadastrados_novos = 0
        for ped in todos_pedidos:
            if not storage.pedido_ja_impresso(ped["vda_id"]):
                storage.registrar_pedido_impresso(
                    vda_id=ped["vda_id"],
                    referencia=ped["referencia"],
                    cliente=ped["cliente"],
                    data_entrega=ped["data_entrega"],
                    arquivo_pdf="BASELINE_INICIAL"
                )
                cadastrados_novos += 1
                print(f"Registrado como existente: ID={ped['vda_id']} | Ref={ped['referencia']}")

        print(f"Base de dados atualizada! {cadastrados_novos} novos pedidos registrados como base inicial.")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(mapear_todos_existentes())
