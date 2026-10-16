import asyncio
import os
import sys
import base64
import logging
from datetime import datetime
from dotenv import load_dotenv
from playwright.async_api import async_playwright

import storage
import printer_service

# Carrega variáveis de ambiente
load_dotenv(dotenv_path=".env.txt")
load_dotenv(dotenv_path=".env")

USER = os.getenv("ERP_USER", "")
PASS = os.getenv("ERP_PASS", "")
BASE_URL = os.getenv("ERP_URL", "https://erp.admsis.com/")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "120"))
HEADLESS = os.getenv("HEADLESS", "true").lower() in ("true", "1", "yes")

# Configuração de Logging
os.makedirs("logs", exist_ok=True)
os.makedirs("downloads", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join("logs", "job_pedidos.log"), encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)

class ErpBot:
    def __init__(self, headless=HEADLESS, dry_run=False):
        self.headless = headless
        self.dry_run = dry_run
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    async def start(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=self.headless)
        self.context = await self.browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        self.page = await self.context.new_page()

    async def close(self):
        try:
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
        except Exception:
            pass

    async def is_logged_in(self) -> bool:
        if not self.page:
            return False
        user_element = await self.page.query_selector("#eng-notificacoes")
        return user_element is not None

    async def login(self):
        logging.info("Realizando login no ERP...")
        await self.page.goto(BASE_URL, wait_until="domcontentloaded")
        await asyncio.sleep(1)

        # Se houver modal de alerta aberto, remove
        await self.page.evaluate("""() => {
            const modal = document.querySelector('#eng_alerta');
            if (modal) modal.style.display = 'none';
            const backdrop = document.querySelector('.modal-backdrop');
            if (backdrop) backdrop.remove();
            document.body.classList.remove('modal-open');
        }""")

        await self.page.fill("#usu_codigo", USER)
        await self.page.fill("#usu_senha", PASS)
        
        await self.page.evaluate("document.querySelector('#frmLogin').submit()")
        try:
            await self.page.wait_for_selector("#eng-notificacoes", timeout=15000)
        except Exception:
            pass
        await asyncio.sleep(1)

        if not await self.is_logged_in():
            alerta = await self.page.evaluate("""() => {
                const el = document.querySelector('#eng_alerta .modal-body');
                return el ? el.innerText.trim() : null;
            }""")
            raise RuntimeError(f"Falha na autenticação do ERP. Alerta: {alerta}")

        logging.info("Login realizado com sucesso!")

    async def navegar_para_pedidos(self):
        logging.info("Acessando tela 0101060100 (Comercial / Pedidos)...")
        await self.page.goto(f"{BASE_URL}Home?eng_tela=0101060100", wait_until="domcontentloaded")
        await asyncio.sleep(2)

    async def aplicar_filtro_producao(self):
        """Verifica se o filtro de PRODUÇÃO já está ativo ou aplica caso necessário."""
        current_url = self.page.url
        if "eng_tela=0101060100" not in current_url:
            await self.navegar_para_pedidos()

        tem_grade = await self.page.query_selector("table tbody tr[id^='tr_']")
        if not tem_grade:
            await self.navegar_para_pedidos()

        # Verifica se o filtro de PRODUÇÃO já está ativo na tela
        ja_filtrado = await self.page.evaluate("""() => {
            const aviso = document.querySelector('#eng-aviso');
            const desc = document.querySelector('#filtro_descricao');
            const textoAviso = aviso ? aviso.innerText.toUpperCase() : '';
            const textoDesc = desc ? desc.value.toUpperCase() : '';
            return textoAviso.includes('PRODUCAO') || textoDesc.includes('PRODUCAO');
        }""")

        if ja_filtrado and tem_grade:
            logging.info("Filtro de PRODUÇÃO já está ativo. Atualizando grade e ordenação...")
            await self.page.evaluate("""() => {
                $('#order_by').val('vda_data_entrega DESC');
                EngNavegacao.refresh();
            }""")
            await asyncio.sleep(2)
            return

        # Se não está filtrado por PRODUÇÃO:
        logging.info("Filtro de PRODUÇÃO não está ativo. Configurando filtro...")
        situacao_select = await self.page.query_selector("#vda_situacao_id")
        if not situacao_select:
            pesquisar_btn = await self.page.query_selector("#Pesquisar")
            if pesquisar_btn:
                logging.info("Clicando em #Pesquisar para exibir campos de filtro...")
                await self.page.click("#Pesquisar")
                await asyncio.sleep(1)

        await self.page.wait_for_selector("#vda_situacao_id", timeout=15000)
        await self.page.select_option("#vda_situacao_id", "4")
        
        logging.info("Clicando em #ConfirmaFiltroS...")
        await self.page.click("#ConfirmaFiltroS")
        await self.page.wait_for_selector("table tbody tr[id^='tr_']", timeout=15000)
        await asyncio.sleep(1)

        logging.info("Aplicando ordenação vda_data_entrega DESC...")
        await self.page.evaluate("""() => {
            $('#order_by').val('vda_data_entrega DESC');
            EngNavegacao.refresh();
        }""")
        await asyncio.sleep(2)

    async def obter_pedidos_grade(self):
        """Extrai os pedidos da tabela visível."""
        return await self.page.evaluate("""() => {
            const list = [];
            const rows = document.querySelectorAll("table tbody tr[id^='tr_']");
            rows.forEach(tr => {
                const link = tr.querySelector("a[href*='EngNavegacao.selecionar']");
                const ref = tr.querySelector("input[name^='vda_referencia_']");
                const cliente = tr.querySelector("input[name^='vda_cliente_id_']");
                const clienteLabel = tr.querySelector("td[id*='vda_cliente_id'] a");
                const dataEntrega = tr.querySelector("input[name^='vda_data_entrega_']");
                const totalPedido = tr.querySelector("input[name^='vda_total_pedido_']");
                
                if (link) {
                    const match = link.getAttribute('href').match(/selecionar\\('(\\d+)'\\)/);
                    if (match) {
                        list.push({
                            vda_id: match[1],
                            referencia: ref ? ref.value : '',
                            cliente: clienteLabel ? clienteLabel.innerText.trim() : (cliente ? cliente.value : ''),
                            data_entrega: dataEntrega ? dataEntrega.value : '',
                            total: totalPedido ? totalPedido.value : ''
                        });
                    }
                }
            });
            return list;
        }""")

    async def baixar_pdf_pedido(self, vda_id: str) -> bytes:
        """Gera e baixa o PDF do pedido no contexto autenticado."""
        pdf_b64 = await self.page.evaluate("""async () => {
            const form = document.querySelector('#Formulario');
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
                throw new Error('HTTP ' + response.status + ' ao gerar relatório.');
            }
            
            const buffer = await response.arrayBuffer();
            let binary = '';
            const bytes = new Uint8Array(buffer);
            for (let i = 0; i < bytes.byteLength; i++) {
                binary += String.fromCharCode(bytes[i]);
            }
            return btoa(binary);
        }""")
        return base64.b64decode(pdf_b64)

    async def processar_pedido(self, pedido: dict):
        vda_id = pedido["vda_id"]
        ref = pedido["referencia"]
        cliente = pedido["cliente"]
        data_entrega = pedido["data_entrega"]

        logging.info(f"==> Processando NOVO PEDIDO: ID={vda_id} | Ref={ref} | Entrega={data_entrega} | Cliente={cliente}")

        # 1. Abre a ficha do pedido com segurança
        await self.page.evaluate(f"EngNavegacao.selecionar('{vda_id}');")
        
        # Aguarda botão de impressão estar presente e pronto
        await self.page.wait_for_selector("#btImpressao", timeout=15000)
        await asyncio.sleep(1)

        # 2. Baixa o PDF
        pdf_bytes = await self.baixar_pdf_pedido(vda_id)
        if not pdf_bytes or not pdf_bytes.startswith(b"%PDF"):
            logging.error(f"Falha ao obter PDF válido para o pedido {vda_id}.")
            return False

        safe_ref = ref.replace("/", "-").replace("\\", "-")
        pdf_filename = f"pedido_{vda_id}_{safe_ref}.pdf"
        pdf_filepath = os.path.abspath(os.path.join("downloads", pdf_filename))

        with open(pdf_filepath, "wb") as f:
            f.write(pdf_bytes)

        logging.info(f"PDF salvo com sucesso ({len(pdf_bytes)} bytes): {pdf_filepath}")

        # 3. Envia para a impressora padrão do Windows
        if self.dry_run:
            logging.info(f"[DRY-RUN] Simulação ativada: Pedido {vda_id} NÃO enviado para a impressora física.")
            sucesso_impressao = True
        else:
            sucesso_impressao = printer_service.imprimir_pdf(pdf_filepath)

        # 4. Registra no banco de dados SQLite para evitar duplicidade
        if sucesso_impressao:
            storage.registrar_pedido_impresso(
                vda_id=vda_id,
                referencia=ref,
                cliente=cliente,
                data_entrega=data_entrega,
                arquivo_pdf=pdf_filepath
            )
            logging.info(f"Pedido {vda_id} ({ref}) registrado no histórico de impressões!")
            return True
        else:
            logging.error(f"Falha no envio do pedido {vda_id} para a impressora.")
            return False

    async def executar_ciclo(self):
        """Executa um ciclo completo de checagem e impressão."""
        try:
            if not await self.is_logged_in():
                await self.login()
                await self.navegar_para_pedidos()

            # Garante filtro de situação PRODUÇÃO
            await self.aplicar_filtro_producao()

            # Extrai os pedidos da lista
            pedidos = await self.obter_pedidos_grade()
            logging.info(f"Total de pedidos encontrados em PRODUÇÃO na tela: {len(pedidos)}")

            novos_pedidos = []
            for ped in pedidos:
                if not storage.pedido_ja_impresso(ped["vda_id"]):
                    novos_pedidos.append(ped)

            if not novos_pedidos:
                logging.info("Nenhum pedido novo pendente de impressão.")
                return

            logging.info(f"Encontrados {len(novos_pedidos)} pedidos novos para imprimir!")

            for ped in novos_pedidos:
                try:
                    await self.processar_pedido(ped)
                except Exception as ex_ped:
                    logging.exception(f"Erro ao processar pedido {ped.get('vda_id')}: {ex_ped}")
                    try:
                        await self.navegar_para_pedidos()
                    except Exception:
                        pass

            # Ao terminar a fila de novos pedidos, retorna para a tela da grade
            await self.navegar_para_pedidos()

        except Exception as e:
            logging.exception(f"Erro no ciclo de verificação: {e}")
            try:
                await self.login()
                await self.navegar_para_pedidos()
            except Exception:
                pass


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Job de Impressão Automática de Pedidos ERP ADMSIS")
    parser.add_argument("--once", action="store_true", help="Executa apenas um ciclo e encerra")
    parser.add_argument("--dry-run", action="store_true", help="Executa sem enviar para a impressora física (modo simulação)")
    parser.add_argument("--reset-db", action="store_true", help="Limpa o banco de dados de pedidos já impressos")
    parser.add_argument("--interval", type=int, default=POLL_INTERVAL, help="Intervalo em segundos entre checagens")
    args = parser.parse_args()

    if args.reset_db:
        if os.path.exists(storage.DB_PATH):
            os.remove(storage.DB_PATH)
            logging.info("Histórico de pedidos impressos (SQLite) foi resetado com sucesso!")

    # Inicializa o banco de dados SQLite
    storage.init_db()

    impressora_ativa = printer_service.get_target_printer()
    logging.info("======================================================")
    logging.info(" INICIANDO ROBÔ DE IMPRESSÃO AUTOMÁTICA DE PEDIDOS ")
    logging.info(f" Impressora Ativa: [{impressora_ativa}]")
    logging.info(f" Modo Simulação (Dry Run): {args.dry_run}")
    logging.info(f" Intervalo de Checagem: {args.interval}s")
    logging.info("======================================================")

    bot = ErpBot(dry_run=args.dry_run)
    await bot.start()

    try:
        if args.once:
            logging.info("Modo de execução única (--once). Executando 1 ciclo...")
            await bot.executar_ciclo()
        else:
            logging.info("Modo contínuo iniciado. Pressione Ctrl+C para encerrar.")
            while True:
                logging.info(f"--- [Ciclo iniciado às {datetime.now().strftime('%H:%M:%S')}] ---")
                await bot.executar_ciclo()
                logging.info(f"Aguardando {args.interval} segundos até o próximo ciclo...\n")
                await asyncio.sleep(args.interval)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logging.info("Robô interrompido pelo usuário.")
    finally:
        await bot.close()
        logging.info("Robô finalizado.")

if __name__ == "__main__":
    asyncio.run(main())
