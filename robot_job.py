import asyncio
import os
import sys
import base64
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
from playwright.async_api import async_playwright

import storage
import printer_service

# Carrega variáveis de ambiente
load_dotenv(dotenv_path=".env.txt")
load_dotenv(dotenv_path=".env", override=True)

USER = os.getenv("ERP_USER", "")
PASS = os.getenv("ERP_PASS", "")
BASE_URL = os.getenv("ERP_URL", "https://erp.admsis.com/")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "300"))
HEADLESS = os.getenv("HEADLESS", "true").lower() in ("true", "1", "yes")
DRY_RUN_DEFAULT = os.getenv("DRY_RUN", "false").lower() in ("true", "1", "yes")

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

def calcular_intervalo_datas():
    """
    Calcula a Data Inicial e Data Final para busca dos pedidos.
    Regra de negócio:
    - Sempre busca pedidos de ontem até hoje.
    - Se hoje for Segunda-feira (weekday == 0), a data inicial recua para Sexta-feira (3 dias atrás).
    - Se hoje for Domingo (weekday == 6), recua para Sexta-feira (2 dias atrás).
    - Permite override via variável de ambiente DIAS_RETROATIVOS no .env.
    """
    hoje = datetime.now()
    env_dias = os.getenv("DIAS_RETROATIVOS", os.getenv("LOOKBACK_DAYS", "auto")).strip().lower()

    if env_dias.isdigit():
        dias = int(env_dias)
        data_inicial = hoje - timedelta(days=dias)
    elif hoje.weekday() == 0:  # Segunda-feira -> Sexta-feira
        data_inicial = hoje - timedelta(days=3)
    elif hoje.weekday() == 6:  # Domingo -> Sexta-feira
        data_inicial = hoje - timedelta(days=2)
    else:  # Terça a Sábado -> Ontem
        data_inicial = hoje - timedelta(days=1)

    return data_inicial.strftime("%d/%m/%Y"), hoje.strftime("%d/%m/%Y")


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
        return await self.page.evaluate("""() => {
            const hasLoginInput = !!document.querySelector('#usu_codigo');
            const hasUserOrMenu = !!document.querySelector('#eng-notificacoes') || 
                                  document.body.innerText.includes('Olá,') || 
                                  (document.title && document.title.includes('ADMSIS'));
            return !hasLoginInput && hasUserOrMenu;
        }""")

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
        
        login_btn = await self.page.query_selector("#login, button[type='submit']")
        if login_btn:
            await login_btn.click()
        else:
            await self.page.evaluate("document.querySelector('#frmLogin').submit()")
        try:
            await self.page.wait_for_selector("#usu_codigo", state="detached", timeout=15000)
        except Exception:
            pass
        await asyncio.sleep(2)

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
        dt_inicio, dt_fim = calcular_intervalo_datas()
        logging.info(f"Configurando filtro: Data do Pedido = {dt_inicio} até {dt_fim} e Situação = PRODUÇÃO (4)...")

        # Preenche filtros compatíveis com UI moderna e legado
        await self.page.evaluate(f"""() => {{
            // Campos de Data Inicial / Final
            const dt_i = document.querySelector('[name="vda_data"], #vda_data_i, #t101060100-filtro-vda_data');
            if (dt_i) dt_i.value = '{dt_inicio}';

            const dt_f = document.querySelector('[name="vda_data-f"], #vda_data_f, #t101060100-filtro-vda_data-f');
            if (dt_f) dt_f.value = '{dt_fim}';

            // Limpa data de entrega se houver
            const dte_i = document.querySelector('#vda_data_entrega_i, #t101060100-filtro-vda_data_entrega');
            if (dte_i) dte_i.value = '';
            const dte_f = document.querySelector('#vda_data_entrega_f, #t101060100-filtro-vda_data_entrega-f');
            if (dte_f) dte_f.value = '';

            // Situação = 4 (PRODUÇÃO)
            const sel = document.querySelector('[name="vda_situacao_id"], #vda_situacao_id, #t101060100-filtro-vda_situacao_id');
            if (sel) {{
                sel.value = '4';
                Array.from(sel.options).forEach(opt => {{
                    opt.selected = (opt.value === '4');
                }});
            }}
        }}""")

        # Clica no botão de Filtrar
        filtrar_btn = await self.page.query_selector("button:has-text('Filtrar'), input[value='Filtrar'], #ConfirmaFiltroS")
        if filtrar_btn:
            logging.info("Clicando no botão Filtrar...")
            await filtrar_btn.click()
            await asyncio.sleep(3)

    async def obter_pedidos_grade(self):
        """Extrai os pedidos da tabela visível (compatível com UI moderna e legado)."""
        pedidos = await self.page.evaluate("""() => {
            const list = [];
            // UI moderna (data-eng-linha) ou legado (tr[id^='tr_'])
            const rows = document.querySelectorAll("table tbody tr[data-eng-linha], table tbody tr[id^='tr_']");
            rows.forEach(tr => {
                const vdaIdAttr = tr.getAttribute('data-eng-linha');
                const link = tr.querySelector("a[href*='selecionar'], a[href*='/tela/101060100/']");
                let vda_id = vdaIdAttr || '';
                if (!vda_id && link) {
                    const matchHref = link.getAttribute('href').match(/(\\d+)/);
                    if (matchHref) vda_id = matchHref[1];
                }

                if (!vda_id) return;

                // Referência
                const refTd = tr.querySelector("[data-eng-coluna='vda_referencia']");
                const refInput = tr.querySelector("input[name^='vda_referencia_']");
                const ref = refTd ? (refTd.getAttribute('data-eng-valor') || refTd.innerText.trim()) : (refInput ? refInput.value : '');

                // Cliente
                const cliTd = tr.querySelector("[data-eng-coluna='vda_cliente_id']");
                const cliInput = tr.querySelector("input[name^='vda_cliente_id_']");
                const cliente = cliTd ? (cliTd.getAttribute('data-eng-valor') || cliTd.innerText.trim()) : (cliInput ? cliInput.value : '');

                // Data de Entrega
                const dtEntTd = tr.querySelector("[data-eng-coluna='vda_data_entrega']");
                const dtEntInput = tr.querySelector("input[name^='vda_data_entrega_']");
                const dataEntrega = dtEntTd ? (dtEntTd.getAttribute('data-eng-valor') || dtEntTd.innerText.trim()) : (dtEntInput ? dtEntInput.value : '');

                // Total Pedido
                const totTd = tr.querySelector("[data-eng-coluna='vda_total_pedido']");
                const totInput = tr.querySelector("input[name^='vda_total_pedido_']");
                const total = totTd ? (totTd.getAttribute('data-eng-valor') || totTd.innerText.trim()) : (totInput ? totInput.value : '');

                list.push({
                    vda_id: String(vda_id),
                    referencia: ref,
                    cliente: cliente,
                    data_entrega: dataEntrega,
                    total: total
                });
            });
            return list;
        }""")

        # Ordena pedidos por Data da Entrega DESC
        def parse_data(p):
            dt_str = p.get("data_entrega", "")
            if dt_str and "/" in dt_str:
                try:
                    return datetime.strptime(dt_str.strip(), "%d/%m/%Y")
                except Exception:
                    pass
            return datetime.min

        pedidos.sort(key=parse_data, reverse=True)
        return pedidos

    async def baixar_pdf_pedido(self, vda_id: str) -> bytes:
        """Gera e baixa o PDF do pedido no contexto autenticado (UI moderna e legado)."""
        # 1. Verifica se foi aberto modal com link/iframe de PDF (UI moderna)
        try:
            await self.page.wait_for_selector("[data-eng-pdf], a[href*='/relatorio/202/'], iframe[src*='/relatorio/202/']", state="attached", timeout=6000)
            pdf_rel_path = await self.page.evaluate("""() => {
                const el = document.querySelector('[data-eng-pdf]');
                if (el) return el.getAttribute('data-eng-pdf');
                const a = document.querySelector('a[href*="/relatorio/202/"]');
                if (a) return a.getAttribute('href');
                const iframe = document.querySelector('iframe[src*="/relatorio/202/"]');
                return iframe ? iframe.getAttribute('src') : null;
            }""")
            if pdf_rel_path:
                pdf_url = pdf_rel_path if pdf_rel_path.startswith("http") else f"{BASE_URL.rstrip('/')}{pdf_rel_path}"
                logging.info(f"Baixando PDF via endpoint do relatório: {pdf_url}")
                res = await self.page.request.get(pdf_url)
                return await res.body()
        except Exception:
            pass

        # 2. Fallback para formulário legado (EngRelatorio/Pdf/202)
        pdf_b64 = await self.page.evaluate("""async () => {
            const form = document.querySelector('#Formulario');
            if (!form) return null;
            const uuid = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
                var r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
                return v.toString(16);
            });
            const url = 'EngRelatorio/Pdf/202?requestID=' + uuid;
            const formData = new FormData(form);
            const response = await fetch(url, { method: 'POST', body: formData });
            if (!response.ok) return null;
            const buffer = await response.arrayBuffer();
            let binary = '';
            const bytes = new Uint8Array(buffer);
            for (let i = 0; i < bytes.byteLength; i++) {
                binary += String.fromCharCode(bytes[i]);
            }
            return btoa(binary);
        }""")
        if pdf_b64:
            return base64.b64decode(pdf_b64)
        return None

    async def processar_pedido(self, pedido: dict):
        vda_id = pedido["vda_id"]
        ref = pedido["referencia"]
        cliente = pedido["cliente"]
        data_entrega = pedido["data_entrega"]

        logging.info(f"==> Processando NOVO PEDIDO: ID={vda_id} | Ref={ref} | Entrega={data_entrega} | Cliente={cliente}")

        # 1. Abre a ficha do pedido (compatível com URL direta e EngNavegacao)
        await self.page.goto(f"{BASE_URL}tela/101060100/{vda_id}", wait_until="domcontentloaded")
        await asyncio.sleep(2)

        # 2. Localiza e clica no botão de Impressão (Impr. ou #btImpressao)
        impr_btn = await self.page.query_selector("button[data-eng-acao='btImpressao'], button:has-text('Impr.'), #btImpressao")
        if not impr_btn:
            logging.error(f"Botão de impressão não encontrado para o pedido {vda_id}.")
            return False

        await impr_btn.click()
        await asyncio.sleep(1)

        # 3. Baixa o PDF
        pdf_bytes = await self.baixar_pdf_pedido(vda_id)
        if not pdf_bytes or not pdf_bytes.startswith(b"%PDF"):
            logging.error(f"Falha ao obter PDF válido para o pedido {vda_id}.")
            return False

        safe_ref = ref.replace("/", "-").replace("\\", "-").strip()
        pdf_filename = f"pedido_{vda_id}_{safe_ref}.pdf" if safe_ref else f"pedido_{vda_id}.pdf"
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
            if not self.dry_run:
                storage.registrar_pedido_impresso(
                    vda_id=vda_id,
                    referencia=ref,
                    cliente=cliente,
                    data_entrega=data_entrega,
                    arquivo_pdf=pdf_filepath
                )
                logging.info(f"Pedido {vda_id} ({ref}) registrado no histórico de impressões!")
            else:
                logging.info(f"[DRY-RUN] Pedido {vda_id} ({ref}) simulado com sucesso (não gravado no histórico para permitir impressão real futura).")
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
    parser.add_argument("--dry-run", dest="dry_run", action="store_true", help="Executa sem enviar para a impressora física (modo simulação)")
    parser.add_argument("--no-dry-run", dest="dry_run", action="store_false", help="Desativa modo simulação")
    parser.set_defaults(dry_run=DRY_RUN_DEFAULT)
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
