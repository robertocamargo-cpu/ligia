# Processo de Verificação e Impressão de Pedidos em Produção (Assistente LigIA)

Este documento descreve detalhadamente o fluxo de funcionamento, as regras de negócio, a arquitetura e as etapas executadas pelo robô autônomo **LigIA** para monitorar e imprimir pedidos em produção no ERP ADMSIS.

---

## 📌 Visão Geral da Arquitetura

O **LigIA** é um assistente autônomo desenvolvido em **Python**, que utiliza o **Playwright** para automação de navegador em modo invisível (*headless*), **pypdfium2** e **Win32 Spooler** para envio direto para a impressora física, e **SQLite** para garantia de não-duplicação de impressões.

```
       +-------------------------------------------------+
       |               Ciclo Contínuo (Polling)          |
       |                   A cada 300s (5 min)           |
       +-------------------------------------------------+
                                |
                                v
               [ 1. Login no ERP ADMSIS (N_LIGIA) ]
                                |
                                v
      [ 2. Acessa Tela Comercial / Pedidos (0101060100) ]
                                |
                                v
    [ 3. Filtro: Data do Pedido (Hoje) + Situação PRODUÇÃO ]
                                |
                                v
     [ 4. Extração e Ordenação (vda_data_entrega DESC) ]
                                |
                                v
       [ 5. Consulta Banco SQLite (pedidos_impressos.db) ]
                     /                      \
            Já impresso?                   Inédito?
                /                              \
        [ Ignora pedido ]           [ 6. Abre Ficha do Pedido ]
                                               |
                                    [ 7. Gera Relatório PDF ]
                                               |
                                    [ 8. Salva em downloads/ ]
                                               |
                                   [ 9. Despacha p/ Impressora ]
                                               |
                                    [ 10. Registra no SQLite ]
```

---

## 🔄 Passo a Passo Detalhado do Processo

### 1. Inicialização e Carregamento de Configurações
- O robô lê as variáveis de ambiente definidas no arquivo [`.env`](file:///c:/Users/Alessandra/Documents/assistente%20LigIA/.env):
  - `ERP_USER`: Usuário de acesso (`N_LIGIA`).
  - `ERP_PASS`: Senha do usuário.
  - `ERP_URL`: Endereço base do sistema (`https://erp.admsis.com/`).
  - `PRINTER_NAME`: Nome da impressora configurada (`HP LaserJet Professional P1102` ou padrão do Windows).
  - `POLL_INTERVAL_SECONDS`: Intervalo entre cada varredura (300 segundos = 5 minutos).
  - `HEADLESS`: Modo de execução do navegador (`true` = em segundo plano).
  - `DRY_RUN`: Modo de teste/simulação (`false` = imprime na impressora física; `true` = apenas baixa o PDF).
- Inicializa a conexão com o banco de dados SQLite local [`pedidos_impressos.db`](file:///c:/Users/Alessandra/Documents/assistente%20LigIA/pedidos_impressos.db) através do módulo [`storage.py`](file:///c:/Users/Alessandra/Documents/assistente%20LigIA/storage.py).
- Inicializa o driver da impressora através do [`printer_service.py`](file:///c:/Users/Alessandra/Documents/assistente%20LigIA/printer_service.py).

---

### 2. Autenticação no ERP ADMSIS
- Inicializa uma instância isolada do navegador Chromium via Playwright.
- Acessa a página de autenticação: `https://erp.admsis.com/`.
- Preenche os campos `#usu_codigo` e `#usu_senha`.
- Aciona o botão de login (`#login`).
- Aguarda a transição e valida se a sessão está ativa checando os menus do sistema e a mensagem de boas-vindas do usuário logado.
- Caso ocorra expiração de sessão em qualquer momento futuro, uma rotina de re-autenticação é disparada automaticamente.

---

### 3. Navegação e Aplicação dos Filtros de Produção
- O robô navega diretamente para o módulo de **Comercial / Pedidos**:
  - URL: `https://erp.admsis.com/tela/101060100` (ou `Home?eng_tela=0101060100`).
- Configura os parâmetros de busca inteligentes:
  - **Intervalo de Datas do Pedido (Data Inicial e Data Final)**:
    - **Regra Inteligente para Dias Úteis (`auto`)**:
      - De **Terça a Sábado**: A Data Inicial é definida como **ontem** e a Data Final como **hoje** (cobre pedidos de ontem que ainda não foram impressos).
      - Na **Segunda-feira**: A Data Inicial recua automaticamente para a **Sexta-feira anterior** (3 dias atrás) até **hoje**, cobrindo todo o fechamento da semana e pedidos de fim de semana.
      - No **Domingo**: A Data Inicial recua para **Sexta-feira** (2 dias atrás).
    - **Configuração Customizável**: Permite alterar para um número fixo de dias no [`.env`](file:///c:/Users/Alessandra/Documents/assistente%20LigIA/.env) via `DIAS_RETROATIVOS=auto` (ou `1`, `2`, `3`, etc.).
  - **Situação do Pedido**: Seleciona a opção **PRODUÇÃO** (código de situação `4`).
  - **Limpeza de filtros residuais**: Garante que campos de filtro de data de entrega estejam limpos, assegurando que nenhum pedido pendente seja omitido.
- Clica no botão **Filtrar** (`button:has-text('Filtrar')` ou `#ConfirmaFiltroS`).

---

### 4. Extração dos Pedidos e Ordenação
- O robô faz a varredura da grade de resultados (compatível com a nova estrutura HTML baseada em `data-eng-linha` e `data-eng-coluna`).
- Para cada registro visível na tabela, extrai:
  - `vda_id`: Código interno único do pedido (ex: `637126`).
  - `referencia`: Número visível do pedido de venda (ex: `4551/2026`).
  - `cliente`: Nome fantasia / Razão social do cliente.
  - `data_entrega`: Data programada de entrega da mercadoria.
  - `total`: Valor financeiro do pedido.
- **Regra de Ordenação**: A lista extraída é ordenada por **Data de Entrega Decrescente (`vda_data_entrega DESC`)**, permitindo o escalonamento correto da fila de produção.

---

### 5. Mecanismo Anti-Duplicidade (Garantia de Impressão Única)
- Antes de iniciar qualquer download ou impressão, o robô consulta o banco SQLite local [`pedidos_impressos.db`](file:///c:/Users/Alessandra/Documents/assistente%20LigIA/pedidos_impressos.db):
  ```sql
  SELECT 1 FROM pedidos_impressos WHERE vda_id = ?
  ```
- **Se o ID já existir**: O pedido já foi impresso em um ciclo anterior. Ele é pulado instantaneamente, evitando desperdício de papel e duplicidade na fábrica.
- **Se o ID não existir**: É classificado como **NOVO PEDIDO** e segue imediatamente para a fila de impressão.

---

### 6. Geração e Captura da Ficha do Pedido em PDF
- Para cada novo pedido identificado:
  1. O robô navega para a ficha do pedido: `https://erp.admsis.com/tela/101060100/{vda_id}`.
  2. Localiza e aciona o botão de impressão de ficha (`button[data-eng-acao="btImpressao"]` ou `Impr.`).
  3. O ERP gera dinamicamente a requisição do Relatório 202 via HTMX e retorna o modal contendo o endpoint do PDF (ex: `/relatorio/202/{uuid}`).
  4. O robô intercepta a URL e faz o download direto do fluxo binário autenticado do documento PDF.
  5. Salva uma cópia física de auditoria na pasta [`downloads/`](file:///c:/Users/Alessandra/Documents/assistente%20LigIA/downloads/) com o formato:
     - `pedido_{vda_id}_{referencia}.pdf` (ex: `pedido_637126_4551-2026.pdf`).

---

### 7. Despacho Silencioso para a Impressora Física
- O arquivo PDF salvo é enviado diretamente para a fila de impressão do Windows através do [`printer_service.py`](file:///c:/Users/Alessandra/Documents/assistente%20LigIA/printer_service.py):
  - **Renderização de Alta Definição**: Cada página do PDF é rasterizada a **300 DPI** utilizando o motor `pypdfium2`.
  - **Envio Direto GDI/Win32**: As páginas são enviadas para a impressora padrão do sistema (ou para a `HP LaserJet Professional P1102`) através das chamadas nativas de spooler do Windows (`StartDoc`, `StartPage`, `StretchDIBits`, `EndPage`, `EndDoc`).
  - **Operação Silenciosa**: Nenhum programa externo (como Adobe Reader ou Edge) é aberto na tela, mantendo a área de trabalho da máquina totalmente desobstruída.

---

### 8. Registro no Histórico de Auditoria
- Assim que o spooler confirma o envio, o pedido é registrado permanentemente no banco SQLite:
  ```sql
  INSERT OR REPLACE INTO pedidos_impressos 
  (vda_id, referencia, cliente, data_entrega, arquivo_pdf, impresso_em) 
  VALUES (?, ?, ?, ?, ?, ?)
  ```
- O robô adiciona um registro detalhado no arquivo de log [`logs/job_pedidos.log`](file:///c:/Users/Alessandra/Documents/assistente%20LigIA/logs/job_pedidos.log).

---

### 9. Repetição Contínua do Ciclo (Polling)
- Finalizada a lista de novos pedidos:
  - O robô retorna para a tela da grade de pedidos.
  - Entra em estado de espera pelo tempo definido em `POLL_INTERVAL_SECONDS` (300 segundos / 5 minutos).
  - Após os 5 minutos, repete todo o ciclo de verificação automaticamente.

---

## 🖥️ Como Iniciar e Controlar a LigIA

### 1. Inicialização Automática com o Windows (Recomendado)
* O atalho **`Assistente LigIA`** foi configurado diretamente na pasta de **Inicialização do Windows** (`Startup`).
* Toda vez que você ligar ou reiniciar o computador e fizer login no Windows, o robô LigIA iniciará **automaticamente em segundo plano (minimizado na barra de tarefas)**, pronto para imprimir os pedidos sem você precisar fazer nada.

### 2. Pelo Ícone na Área de Trabalho
* **`Assistente LigIA`**: Dá início imediato ao robô em uma janela de console dedicada. **Não abre nem exige o Antigravity IDE aberto**, rodando de forma leve e direta.

### 3. Como Parar / Encerrar o Robô
* Se a janela estiver visível, basta **fechar a janela preta do console**.
* Ou clique no script [`PARAR_LIGIA.bat`](file:///c:/Users/Alessandra/Documents/assistente%20LigIA/PARAR_LIGIA.bat) para encerrar o processo com 1 clique.

### 4. Pela Linha de Comando (Terminal)
* **Modo normal contínuo (imprime na impressora física)**:
  ```powershell
  python robot_job.py
  ```
* **Modo simulação (não gasta papel, apenas salva o PDF)**:
  ```powershell
  python robot_job.py --dry-run
  ```
* **Modo teste único (faz apenas 1 varredura e fecha)**:
  ```powershell
  python robot_job.py --once
  ```
* **Resetar histórico do banco (caso precise reimprimir pedidos passados)**:
  ```powershell
  python robot_job.py --reset-db
  ```
- **Resetar histórico do banco (caso precise reimprimir pedidos passados)**:
  ```powershell
  python robot_job.py --reset-db
  ```

