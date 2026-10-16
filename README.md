# Automação de Impressão de Pedidos ERP ADMSIS (LigIA)

Robô autônomo desenvolvido em Python e Playwright para monitorar a tela `0101060100` (Comercial / Pedidos) do ERP ADMSIS, filtrar pedidos em **PRODUÇÃO** ordenados por **Data da Entrega DESC**, e despachar automaticamente novos pedidos para a impressora padrão do Windows.

---

## 🚀 Como Executar

### 1. Iniciar o Robô (Modo Contínuo)
Basta dar **duplo clique** no arquivo:
* **`INICIAR_ROBO.bat`**

Ou pelo terminal:
```powershell
python robot_job.py
```
O robô executará uma checagem inicial e repetirá a cada **2 minutos** (configurável).

### 2. Testar sem Imprimir Folhas Físicas (Modo Simulação)
Para validar o fluxo sem gastar papel:
* **`TESTAR_SIMULACAO.bat`**

Ou pelo terminal:
```powershell
python robot_job.py --once --dry-run
```

### 3. Testar Pedido Individual Específico
Para testar o fluxo de ponta a ponta com um pedido específico direto na impressora física:
```powershell
python testes/testar_pedido_4352.py
```

### 4. Resetar Histórico de Impressões
Se desejar limpar o histórico e permitir que pedidos antigos sejam impressos novamente:
```powershell
python robot_job.py --reset-db
```

---

## 🛠️ Arquitetura e Funcionamento

1. **Autenticação**:
   * Utiliza as credenciais configuradas no `.env`.
   * Mantém sessão ativa com rotina de reconexão automática caso o login expire.

2. **Navegação & Filtros**:
   * Acessa a tela `0101060100` (Comercial / Pedidos).
   * Aplica o filtro de situação `4` (PRODUCAO) e clica no botão `#ConfirmaFiltroS`.
   * Ordena por Data da Entrega decrescente (`vda_data_entrega DESC`).

3. **Controle Anti-Duplicidade**:
   * Banco de dados local em **SQLite** (`pedidos_impressos.db`).
   * Cada pedido possui identificador único (`vda_id`). Se já foi impresso, é ignorado; se for inédito, é processado e registrado com timestamp.

4. **Captura e Envio para a Impressora**:
   * Abre a ficha do pedido e gera o relatório PDF diretamente via streaming autenticado (`EngRelatorio/Pdf/202`).
   * Salva uma cópia de backup na pasta `downloads/`.
   * Renderiza e envia em alta definição (300 DPI) diretamente para a impressora configurada (`HP LaserJet Professional P1102` ou a padrão do Windows).
   * Não abre popups nem janelas visuais de leitores de PDF.

5. **Logs de Auditoria**:
   * Todos os eventos e erros são registrados em tempo real no console e no arquivo `logs/job_pedidos.log`.
