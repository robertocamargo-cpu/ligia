import asyncio
import os
import re
from playwright.async_api import async_playwright
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env.txt")
USER = os.getenv("ERP_USER")
PASS = os.getenv("ERP_PASS")

async def test_imprime_primeiro():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()
        
        # 1. Login
        print("1. Efetuando login...")
        await page.goto("https://erp.admsis.com/", wait_until="networkidle")
        await page.fill("#usu_codigo", USER)
        await page.fill("#usu_senha", PASS)
        await asyncio.gather(
            page.wait_for_load_state("networkidle"),
            page.evaluate("document.querySelector('#frmLogin').submit()")
        )
        await asyncio.sleep(2)
        
        # 2. Tela de Pedidos
        print("2. Acessando Comercial / Pedidos (0101060100)...")
        await page.goto("https://erp.admsis.com/Home?eng_tela=0101060100", wait_until="networkidle")
        await asyncio.sleep(2)
        
        # 3. Filtrar Situação = 4 (PRODUÇÃO)
        print("3. Filtrando por Situação = PRODUÇÃO (4)...")
        await page.select_option("#vda_situacao_id", "4")
        await asyncio.gather(
            page.wait_for_load_state("networkidle"),
            page.click("#ConfirmaFiltroS")
        )
        await asyncio.sleep(2)
        
        # 4. Ordenar por Data de Entrega DESC
        print("4. Ordenando por Data de Entrega DESC...")
        await page.evaluate("""() => {
            $('#order_by').val('vda_data_entrega DESC');
            EngNavegacao.refresh();
        }""")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)
        
        # 5. Coletar pedidos da lista
        pedidos = await page.evaluate("""() => {
            const list = [];
            const rows = document.querySelectorAll("table tbody tr[id^='tr_']");
            rows.forEach(tr => {
                const link = tr.querySelector("a[href*='EngNavegacao.selecionar']");
                const ref = tr.querySelector("input[name^='vda_referencia_']");
                const dataEntrega = tr.querySelector("input[name^='vda_data_entrega_']");
                if (link) {
                    const match = link.getAttribute('href').match(/selecionar\\('(\\d+)'\\)/);
                    if (match) {
                        list.push({
                            vda_id: match[1],
                            referencia: ref ? ref.value : '',
                            data_entrega: dataEntrega ? dataEntrega.value : ''
                        });
                    }
                }
            });
            return list;
        }""")
        
        print(f"Total de pedidos encontrados: {len(pedidos)}")
        if not pedidos:
            print("Nenhum pedido encontrado!")
            await browser.close()
            return
            
        primeiro = pedidos[0]
        print(f"Primeiro pedido: ID={primeiro['vda_id']} | Ref={primeiro['referencia']} | Entrega={primeiro['data_entrega']}")
        
        # 6. Selecionar o pedido para abrir a ficha
        print(f"Abrindo ficha do pedido {primeiro['vda_id']}...")
        await asyncio.gather(
            page.wait_for_load_state("networkidle"),
            page.evaluate(f"EngNavegacao.selecionar('{primeiro['vda_id']}');")
        )
        await asyncio.sleep(2)
        print("URL da ficha:", page.url)
        
        # Verifica se o botão #btImpressao existe na ficha
        tem_bt_impr = await page.query_selector("#btImpressao")
        print("Botão #btImpressao encontrado na ficha?", bool(tem_bt_impr))
        
        # 7. Monitora respostas HTTP para capturar o PDF
        pdf_bytes = None
        pdf_url = None
        
        async def on_response(response):
            nonlocal pdf_bytes, pdf_url
            if "EngRelatorio/Pdf" in response.url or "application/pdf" in response.headers.get("content-type", ""):
                print("PDF detectado na resposta HTTP:", response.url)
                try:
                    pdf_bytes = await response.body()
                    pdf_url = response.url
                except Exception as e:
                    print("Erro ao ler body da resposta do PDF:", e)
                    
        page.on("response", on_response)
        
        # Clica no botão de impressão
        print("Acionando botão #btImpressao...")
        await page.click("#btImpressao")
        
        # Aguarda 5 segundos para o PDF ser gerado e carregado
        for _ in range(10):
            if pdf_bytes:
                break
            await asyncio.sleep(1)
            
        if pdf_bytes:
            print(f"Sucesso! PDF capturado: {len(pdf_bytes)} bytes.")
            os.makedirs("downloads", exist_ok=True)
            pdf_path = os.path.join("downloads", f"pedido_{primeiro['vda_id']}_{primeiro['referencia'].replace('/', '-')}.pdf")
            with open(pdf_path, "wb") as f:
                f.write(pdf_bytes)
            print(f"PDF salvo com sucesso em: {pdf_path}")
        else:
            print("Não interceptou pela resposta HTTP direta. Verificando o iframe #eng-relatorio-janela-frame...")
            frame_element = await page.query_selector("#eng-relatorio-janela-frame")
            if frame_element:
                frame_src = await frame_element.get_attribute("src")
                print("Iframe src:", frame_src)
                
            await page.screenshot(path="screenshot_pos_impressao.png")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_imprime_primeiro())
