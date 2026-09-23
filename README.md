# Monitor de preços de passagens — Brasília (BSB) ↔ Cape Town (CPT)

Bot agendado que procura a passagem mais barata de uma rota num mês, com
datas flexíveis e duração fixa, compara com um preço-limite e avisa por
**Telegram** quando o preço cai abaixo dele — com as datas vencedoras e o
link do trajeto.

## Sumário

1. [Como funciona](#como-funciona)
2. [Passo a passo: criar o bot no Telegram](#passo-a-passo-criar-o-bot-no-telegram)
3. [Configurar rota, mês, duração e preço-limite](#configurar-rota-mês-duração-e-preço-limite)
4. [Rodar localmente pra testar](#rodar-localmente-pra-testar)
5. [Subir pro GitHub e configurar os Secrets](#subir-pro-github-e-configurar-os-secrets)
6. [Frequência real de execução e minutos do Actions](#frequência-real-de-execução-e-minutos-do-actions)
7. [Limites e riscos do scraping](#limites-e-riscos-do-scraping)
8. [Reusar pra outra rota/viagem](#reusar-pra-outra-rotaviagem)

## Como funciona

1. `flight_monitor.py` lê `config.yaml` (rota, mês alvo, duração,
   preço-limite) e o token do Telegram (variáveis de ambiente / Secrets).
2. Abre o **calendário de preços** do Google Flights com Playwright
   (headless) em 5 datas semente que, juntas, cobrem o mês inteiro, e lê
   todas as combinações de ida/volta com a duração pedida.
3. Fica com a combinação mais barata e registra a leitura em
   `data/history.csv` (data/hora, preço, datas vencedoras, fonte).
4. **Só considera alertar se o preço estiver abaixo do `preco_limite`.**
   Nada acima do limite vira alerta, mesmo que seja um novo mínimo
   histórico. Se estiver abaixo, a mensagem informa também se é o menor
   preço já registrado para aquele mês/duração.
5. Se for um preço novo mais baixo que o último já alertado (ver
   `data/alert_state.json`), envia o alerta no Telegram com as datas
   vencedoras e o link do trajeto.
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

## Configurar rota, mês, duração e preço-limite

Edite `config.yaml` (não tem segredo nenhum aqui, pode commitar):

```yaml
origem: "BSB"            # código IATA de origem
destino: "SDU"            # código IATA de destino
mes_alvo: "2027-05"       # mês da viagem (AAAA-MM) — datas flexíveis dentro dele
duracao_dias: 7            # quantos dias de viagem (ida -> volta)
horizonte_max_dias: 330     # quantos dias de antecedência dá pra buscar
preco_limite: 600           # SÓ alerta abaixo deste valor
moeda: "BRL"
```

### Datas flexíveis dentro do mês

Você não escolhe datas exatas — escolhe o **mês** e a **duração**. O bot
testa todas as datas de ida do mês mantendo a duração pedida e fica com a
combinação mais barata.

Isso é feito pelo **calendário de preços** do Google Flights, que devolve
uma grade 7x7 (49 combinações de ida/volta com seus preços) por página
carregada. Com 5 datas semente — dias 4, 11, 18, 25 e 31, cada uma cobrindo
±3 dias — o mês inteiro é varrido em 5 carregamentos, e não em uma busca por
combinação.

Cada célula da grade vem com um `aria-label` no formato
`"R$ 795, 7 de mai. para 14 de mai."`, ou seja, preço e datas juntos. Por
isso a extração aqui é bem mais confiável do que garimpar valores no texto
solto da página: não há como atribuir um preço às datas erradas.

O alerta informa quais foram as datas vencedoras, e o link aponta para essa
combinação específica.

### Mês alvo além do horizonte de busca

A maioria das companhias aéreas não vende passagem com mais de ~330 dias de
antecedência. Se o mês alvo inteiro ainda estiver além disso (ex: novembro
de 2027 visto de setembro de 2026), o bot **não falha nem espera** — busca a
data mais distante alcançável hoje, mantendo a duração pedida, e vai se
aproximando do mês alvo conforme o calendário avança. Quando o mês entra no
horizonte, a varredura por datas flexíveis começa a valer normalmente.

A comparação de "menor preço histórico" agrupa por **mês + duração** (não
por par de datas), que é o que faz sentido quando as datas são flexíveis: o
que se compara é "a melhor passagem de N dias naquele mês". Trocar destino,
mês ou duração no `config.yaml` zera o controle de alertas repetidos
automaticamente.

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

Não adianta "forçar" isso dentro do Actions mantendo um runner vivo num
loop de `sleep` 24/7: além de gambiarra, isso vai contra o ToS do GitHub
Actions (uso não relacionado a build/teste/deploy do projeto) e pode
fazer a conta ser sinalizada.

### Solução adotada: execução local a cada 30 min (launchd)

Para ter os 30 minutos de verdade, o `run_local.sh` roda no Mac via
`launchd`, e o GitHub Actions continua ligado como rede de segurança
para quando o Mac estiver desligado.

O agente fica em `~/Library/LaunchAgents/com.vinilima.flightmonitor.plist`
com `StartInterval` de 1800 segundos. Comandos úteis:

```bash
# ativar / desativar
launchctl load  ~/Library/LaunchAgents/com.vinilima.flightmonitor.plist
launchctl unload ~/Library/LaunchAgents/com.vinilima.flightmonitor.plist

# ver se está ativo (coluna do meio é o último código de saída)
launchctl list | grep flightmonitor

# acompanhar as execuções
tail -f local-run.log
```

O `run_local.sh` dá `git pull` antes e `git push` depois de cada
execução, então o histórico e o estado de alerta ficam compartilhados
entre as execuções locais e as do Actions — o mesmo preço não alerta
duas vezes.

Requisitos locais: `.venv` criada com `pip install -r requirements.txt` +
`playwright install chromium`, e um arquivo `.env` (não versionado) com
`TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`.

**Limitação:** com o Mac desligado ou dormindo, o `launchd` não roda —
ele dispara uma vez ao acordar e retoma o ciclo de 30 min. Nesses
períodos, quem cobre é o GitHub Actions (a cada ~4h). Para 30 minutos
reais 24/7 sem depender do Mac, seria preciso uma VPS/Raspberry Pi
ligado ou um agendador pago (Render/Railway/Fly.io).

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
- **O fallback do Skyscanner está bloqueado hoje.** Verificado em
  2026-09-23: a página responde com a tela de detecção de bot ("Are you a
  person or a robot?") e nenhum preço é extraído. Na prática, o Google
  Flights é a única fonte funcionando; o fallback só falha de forma
  silenciosa e o bot tenta de novo na execução seguinte.
- **A URL da busca precisa ser o deep link `tfs=`.** Uma URL de texto
  livre (`?q=voos de X para Y`) não preenche a rota: o Google carrega uma
  página genérica, e os preços lidos ali são promoções sem relação com a
  busca. Isso gerou leituras falsas (R$246, R$952) antes de ser corrigido.
  O `montar_url()` em `scrapers/google_flights.py` monta o protobuf do
  `tfs` na mão — se o Google mudar esse formato, é o primeiro lugar a
  investigar.
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
`mes_alvo`, `duracao_dias`, `preco_limite`) —
todo o resto do código é genérico e não precisa mudar. Se quiser manter o
histórico da rota antiga, copie `data/history.csv` pra outro nome antes
de zerar; o script sempre lê e escreve em `data/history.csv`.
