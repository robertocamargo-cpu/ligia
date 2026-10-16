# Regra de Filtro de Pedidos - Assistente LigIA

## Regra Oficial Definida pelo Usuário:
Ao consultar e processar pedidos na tela `0101060100` (Comercial / Pedidos) do ERP ADMSIS, o robô deve **SEMPRE** aplicar os seguintes critérios combinados:

1. **Data do Pedido (Hoje):**
   * Campo Inicial: `#vda_data_i` = Data atual (`DD/MM/AAAA`)
   * Campo Final: `#vda_data_f` = Data atual (`DD/MM/AAAA`)
2. **Situação do Pedido:**
   * Campo Situação: `#vda_situacao_id` = `4` (**PRODUÇÃO**)
3. **Ordenação:**
   * `#order_by` = `vda_data_entrega DESC`

Todos os ciclos de verificação e scripts de monitoramento devem respeitar estritamente esta combinação.
