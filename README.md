# Monitor de preços de passagens — Brasília (BSB) ↔ Cape Town (CPT)

Bot que roda a cada 30 minutos, busca o menor preço de uma rota no Google
Flights (com fallback pro Skyscanner), compara com um preço-limite e com o
menor preço já visto, e avisa por **Telegram e e-mail ao mesmo tempo**
quando encontra um preço vantajoso.

## Sumário

1. [Como funciona](#como-funciona)
2. [Passo a passo: criar o bot no Telegram](#passo-a-passo-criar-o-bot-no-telegram)
3. [Passo a passo: senha de app do Gmail](#passo-a-passo-senha-de-app-do-gmail)
4. [Configurar rota, datas e preço-limite](#configurar-rota-datas-e-preço-limite)
5. [Rodar localmente pra testar](#rodar-localmente-pra-testar)
6. [Subir pro GitHub e configurar os Secrets](#subir-pro-github-e-configurar-os-secrets)
7. [Aviso sobre minutos do GitHub Actions](#aviso-sobre-minutos-do-github-actions)
8. [Limites e riscos do scraping](#limites-e-riscos-do-scraping)
9. [Reusar pra outra rota/viagem](#reusar-pra-outra-rotaviagem)

## Como funciona

1. `flight_monitor.py` lê `config.yaml` (rota, datas, preço-limite) e as
   credenciais (variáveis de ambiente / Secrets).
2. Abre o Google Flights com Playwright (headless) e extrai o menor preço
   da página. Se isso falhar (timeout, layout mudou, bloqueio), tenta o
   Skyscanner como fallback.
3. Registra a leitura em `data/history.csv` (data/hora, preço, fonte).
4. Compara o preço atual com o `preco_limite` do config **e** com o menor
   preço já registrado no histórico.
5. Se for vantajoso **e** for um preço novo (menor que o último já
   alertado, ver `data/alert_state.json`), dispara os dois alertas juntos:
   Telegram e e-mail.
6. O GitHub Actions roda esse script a cada 30 minutos e commita de volta
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
5. Guarde os dois valores — vão virar Secrets no GitHub (passo 6).

## Passo a passo: senha de app do Gmail

Uma "senha de app" é uma senha de 16 dígitos gerada pelo Google só pra
aplicativos, sem usar sua senha normal.

1. Ative a **verificação em duas etapas** na sua conta Google, se ainda
   não tiver: https://myaccount.google.com/security
2. Acesse https://myaccount.google.com/apppasswords (pode pedir login de
   novo).
3. Em "Nome do app", digite algo como `flight-monitor` e clique em
   **Criar**.
4. O Google mostra uma senha de 16 caracteres (ex: `abcd efgh ijkl mnop`).
   Copie sem espaços — esse é o `EMAIL_APP_PASSWORD`.
5. `EMAIL_SENDER` é o seu endereço Gmail completo (o mesmo da conta onde
   você gerou a senha de app).

> Quer usar outro provedor de e-mail (Outlook, Yahoo, SMTP próprio)? Só
> trocar `SMTP_SERVER` e `SMTP_PORT` — o código em
> `notify/email_notifier.py` não muda.

## Configurar rota, datas e preço-limite

Edite `config.yaml` (não tem segredo nenhum aqui, pode commitar):

```yaml
origem: "BSB"                   # código IATA de origem
destino: "CPT"                   # código IATA de destino
data_ida_alvo: "2027-11-05"      # data de ida DESEJADA da viagem (AAAA-MM-DD)
data_volta_alvo: "2027-11-15"    # data de volta DESEJADA da viagem (AAAA-MM-DD)
horizonte_max_dias: 330           # quantos dias de antecedência dá pra buscar
preco_limite: 6500                # dispara alerta se o preço cair abaixo disso
moeda: "BRL"
destinatario_email: "seu-email@exemplo.com"
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
# edite o .env e preencha TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
# EMAIL_SENDER e EMAIL_APP_PASSWORD

python flight_monitor.py
```

Se tudo estiver certo, você verá logs no terminal com o preço encontrado
e, se for vantajoso, receberá o alerta no Telegram e no e-mail.

## Subir pro GitHub e configurar os Secrets

1. Crie um repositório no GitHub (veja o aviso sobre visibilidade
   [abaixo](#aviso-sobre-minutos-do-github-actions)) e suba este código.
2. No repositório, vá em **Settings → Secrets and variables → Actions →
   New repository secret** e cadastre, um por um:

   | Nome                  | Valor                                             |
   |------------------------|----------------------------------------------------|
   | `TELEGRAM_BOT_TOKEN`   | token do BotFather                                 |
   | `TELEGRAM_CHAT_ID`     | chat_id obtido no `getUpdates`                     |
   | `EMAIL_SENDER`         | seu e-mail Gmail                                   |
   | `EMAIL_APP_PASSWORD`   | a senha de app de 16 caracteres                    |
   | `SMTP_SERVER`          | opcional, padrão `smtp.gmail.com` se não definido  |
   | `SMTP_PORT`            | opcional, padrão `465` se não definido             |

3. Pronto — o workflow em `.github/workflows/monitor.yml` já está
   configurado pra rodar a cada 30 minutos automaticamente
   (`schedule: cron: "*/30 * * * *"`), e você também pode disparar uma
   execução manual pela aba **Actions → Monitor de preços de
   passagens → Run workflow**.

## Aviso sobre minutos do GitHub Actions

Rodar a cada 30 minutos significa **48 execuções por dia**. Em
repositórios **privados**, o plano gratuito do GitHub Actions tem um
limite mensal de minutos (2.000 min/mês pra contas pessoais no plano
Free, em 2026) — com scraping + Playwright, cada execução pode levar de
1 a 3 minutos, então isso pode estourar o limite ao longo do mês.

**Recomendação:** deixe o repositório **público**. Repositórios públicos
têm minutos **ilimitados** no GitHub Actions. Isso é seguro aqui porque
nenhum segredo fica no código — tokens e senhas ficam exclusivamente em
**GitHub Secrets**, que não aparecem nem no código-fonte nem nos logs do
Actions mesmo em repositório público. O único dado "pessoal" que fica
visível no repositório é o e-mail de destino em `config.yaml` e o
histórico de preços da rota — se isso te incomoda, edite
`destinatario_email` antes de tornar o repo público, ou mantenha o repo
privado e acompanhe seu consumo de minutos em **Settings → Billing**.

## Limites e riscos do scraping

- **Não é uma API oficial.** Tanto o Google Flights quanto o Skyscanner
  podem mudar o layout da página a qualquer momento, o que quebra a
  extração de preços sem aviso prévio.
- O script já trata isso com resiliência básica: se o Google Flights
  falhar, tenta o Skyscanner; se os dois falharem, o erro é logado e o
  workflow termina normalmente (sem marcar falha), tentando de novo na
  próxima execução 30 minutos depois.
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
`data_ida_alvo`, `data_volta_alvo`, `preco_limite`, `destinatario_email`) —
todo o resto do código é genérico e não precisa mudar. Se quiser manter o
histórico da rota antiga, copie `data/history.csv` pra outro nome antes
de zerar; o script sempre lê e escreve em `data/history.csv`.
