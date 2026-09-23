# Monitor de preços de passagens — Brasília (BSB) ↔ Cape Town (CPT)

Bot agendado que busca o menor preço de uma rota no Google Flights (com
fallback pro Skyscanner), compara com um preço-limite e avisa por
**Telegram** quando o preço cai abaixo dele — com o link do trajeto já
montado com as datas.

## Sumário

1. [Como funciona](#como-funciona)
2. [Passo a passo: criar o bot no Telegram](#passo-a-passo-criar-o-bot-no-telegram)
3. [Configurar rota, datas e preço-limite](#configurar-rota-datas-e-preço-limite)
4. [Rodar localmente pra testar](#rodar-localmente-pra-testar)
5. [Subir pro GitHub e configurar os Secrets](#subir-pro-github-e-configurar-os-secrets)
6. [Frequência real de execução e minutos do Actions](#frequência-real-de-execução-e-minutos-do-actions)
7. [Limites e riscos do scraping](#limites-e-riscos-do-scraping)
8. [Reusar pra outra rota/viagem](#reusar-pra-outra-rotaviagem)

## Como funciona

1. `flight_monitor.py` lê `config.yaml` (rota, datas, preço-limite) e o
   token do Telegram (variáveis de ambiente / Secrets).
2. Abre o Google Flights com Playwright (headless) e extrai o menor preço
   da página. Se isso falhar (timeout, layout mudou, bloqueio), tenta o
   Skyscanner como fallback.
3. Registra a leitura em `data/history.csv` (data/hora, preço, fonte).
4. **Só considera alertar se o preço estiver abaixo do `preco_limite`.**
   Nada acima do limite vira alerta, mesmo que seja um novo mínimo
   histórico. Se estiver abaixo, a mensagem informa também se é o menor
   preço já registrado para aquela rota/datas.
5. Se for um preço novo mais baixo que o último já alertado (ver
   `data/alert_state.json`), envia o alerta no Telegram com o link do
   trajeto já preenchido com rota e datas.
6. O GitHub Actions roda esse script periodicamente e commita de volta
   o histórico atualizado, então o estado persiste entre execuções sem
   precisar do seu computador ligado.

## Passo a passo: criar o bot no Telegram

1. No Telegram, procure o usuário **@BotFather** e inicie uma conversa.
2. Envie `/newbot` e siga as instruções: escolha um nome de exibição e um
   username terminado em `bot` (ex: `meu_flight_alert_bot`).
3. O BotFather vai te devolver um **token** parecido com
   `123456789:ABCdefGhIJKlmNoPQRstuVwxyz`. Esse é o `TELEGRAM_BOT_TOKEN`.
4. Agora você precisa do **chat_id** pra onde o bot vai te mandar mensagem:
   - Procure pelo seu bot no Telegram (pelo username que você escolheu) e
     envie qualquer mensagem pra ele (ex: `oi`).
   - No navegador, acesse:
     `https://api.telegram.org/bot<SEU_TOKEN>/getUpdates`
     (troque `<SEU_TOKEN>` pelo token do passo 3).
   - Na resposta JSON, procure por `"chat":{"id": ...}` — esse número
     (pode ser negativo) é o `TELEGRAM_CHAT_ID`.
5. Guarde os dois valores — vão virar Secrets no GitHub.

## Configurar rota, datas e preço-limite

Edite `config.yaml` (não tem segredo nenhum aqui, pode commitar):

```yaml
origem: "BSB"                   # código IATA de origem
destino: "SDU"                   # código IATA de destino
data_ida_alvo: "2027-05-10"      # data de ida DESEJADA da viagem (AAAA-MM-DD)
data_volta_alvo: "2027-05-17"    # data de volta DESEJADA da viagem (AAAA-MM-DD)
horizonte_max_dias: 330           # quantos dias de antecedência dá pra buscar
preco_limite: 600                 # SÓ alerta abaixo deste valor
moeda: "BRL"
```

### Data alvo além do horizonte de busca (ex: viagem em novembro de 2027)

A maioria das companhias aéreas (e por consequência o Google Flights e o
Skyscanner) não deixa buscar/comprar passagens com mais de ~330 dias de
antecedência. Se a `data_ida_alvo` estiver além desse horizonte, o bot **não
falha nem espera** — ele busca automaticamente a data mais distante possível
(hoje + `horizonte_max_dias`), mantendo a mesma duração de viagem entre
`data_ida_alvo` e `data_volta_alvo` (no exemplo acima, 10 dias).

A cada dia que passa, esse horizonte "anda junto" com o calendário e a data
buscada se aproxima sozinha da data alvo — até que, em algum momento, a
viagem alvo entra no horizonte de 330 dias e o bot passa a buscar
exatamente `data_ida_alvo`/`data_volta_alvo` de verdade, e passa a ficar
assim até a viagem acontecer.

Cada leitura registrada em `data/history.csv` guarda as datas usadas
naquela busca, e a comparação de "menor preço histórico" só olha leituras
com o **mesmo par de datas** — assim, preços de datas provisórias diferentes
(enquanto a viagem ainda está fora do horizonte) nunca são comparados entre
si como se fossem a mesma passagem.

## Rodar localmente pra testar

```bash
git clone <url-do-seu-repo>
cd flight-monitor-bsb-cpt

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
playwright install chromium

cp .env.example .env
# edite o .env e preencha TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID

python flight_monitor.py
```

Se tudo estiver certo, você verá logs no terminal com o preço encontrado
e, se estiver abaixo do limite, receberá o alerta no Telegram.

## Subir pro GitHub e configurar os Secrets

1. Crie um repositório no GitHub (veja o aviso sobre visibilidade
   [abaixo](#frequência-real-de-execução-e-minutos-do-actions)) e suba este código.
2. No repositório, vá em **Settings → Secrets and variables → Actions →
   New repository secret** e cadastre os dois:

   | Nome                  | Valor                          |
   |------------------------|---------------------------------|
   | `TELEGRAM_BOT_TOKEN`   | token do BotFather              |
   | `TELEGRAM_CHAT_ID`     | chat_id obtido no `getUpdates`  |

3. Pronto — o workflow em `.github/workflows/monitor.yml` já está
   agendado (`schedule: cron: "*/30 * * * *"`), e você também pode
   disparar uma execução manual pela aba **Actions → Monitor de preços
   de passagens → Run workflow**.

## Frequência real de execução e minutos do Actions

⚠️ **O cron pede 30 minutos, mas o GitHub não cumpre isso.** Agendamentos
do GitHub Actions são "best effort": sob carga, a plataforma atrasa ou
simplesmente descarta execuções agendadas, e isso é mais agressivo em
crons de alta frequência e em repositórios públicos (que rodam em filas
de menor prioridade).

Medição real neste repositório com `cron: "*/30 * * * *"`: os intervalos
entre execuções agendadas foram de **2h37 a 5h49, média de ~4 horas** —
ou seja, cerca de 6 execuções por dia em vez das 48 pedidas. Não há
configuração que conserte isso: é comportamento da plataforma.

Se precisar de frequência real de 30 minutos, as saídas são rodar o
script num serviço que você controla (uma VPS com `cron`, um Raspberry Pi
ligado, ou um agendador tipo Render/Railway/Fly.io) em vez do GitHub
Actions.

**Sobre minutos:** em repositórios **privados**, o plano gratuito tem
limite mensal (2.000 min/mês pra contas pessoais, em 2026) e cada
execução com Playwright leva de 1 a 3 minutos. Em repositórios
**públicos** os minutos são **ilimitados**, e é seguro aqui porque
nenhum segredo fica no código — o token do Telegram fica exclusivamente
em **GitHub Secrets**, que não aparecem no código-fonte nem nos logs. O
único dado exposto no repositório é o histórico de preços da rota.

## Limites e riscos do scraping

- **Não é uma API oficial.** Tanto o Google Flights quanto o Skyscanner
  podem mudar o layout da página a qualquer momento, o que quebra a
  extração de preços sem aviso prévio.
- O script já trata isso com resiliência básica: se o Google Flights
  falhar, tenta o Skyscanner; se os dois falharem, o erro é logado e o
  workflow termina normalmente (sem marcar falha), tentando de novo na
  próxima execução.
- Sites de busca de voos podem eventualmente detectar tráfego automatizado
  e bloquear ou mostrar CAPTCHA. Rodar a cada 30 minutos (e não com mais
  frequência) ajuda a manter um perfil de uso discreto, mas não elimina o
  risco.
- Preços de passagens variam por moeda de cobrança, cookies/histórico de
  busca e até localização do servidor — o preço que o bot vê pode não ser
  idêntico ao que você veria navegando manualmente. Trate o alerta como um
  indicativo pra você conferir manualmente antes de comprar.
- **Falso positivo conhecido:** a extração lê todo o texto da página
  procurando por "R$ nnn", o que às vezes pega valores que não são da rota
  buscada (ex: banners de "voos a partir de R$ 246" de outras promoções).
  Como mitigação, o bot prefere o menor preço que aparece **repetido** na
  página (resultados reais tendem a aparecer mais de uma vez) e loga um
  aviso de "baixa confiança" quando não encontra repetição — mas isso é uma
  heurística, não uma garantia. Sempre confira o preço manualmente antes de
  comprar, principalmente se o alerta vier muito abaixo do esperado.

## Reusar pra outra rota/viagem

Basta editar os campos no topo de `config.yaml` (`origem`, `destino`,
`data_ida_alvo`, `data_volta_alvo`, `preco_limite`) —
todo o resto do código é genérico e não precisa mudar. Se quiser manter o
histórico da rota antiga, copie `data/history.csv` pra outro nome antes
de zerar; o script sempre lê e escreve em `data/history.csv`.
