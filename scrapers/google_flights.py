"""Scraper do Google Flights via Playwright.

Google Flights não tem API pública. Isso aqui abre a página normal
(headless) e lê o texto renderizado procurando por valores monetários.
É frágil por natureza: se o Google mudar o layout, isso pode parar de
funcionar sem aviso — ver limitações no README.
"""

import base64
import logging
import re
from datetime import date

from playwright.sync_api import sync_playwright

from scrapers.common import CURRENCY_SYMBOLS, parse_preco

logger = logging.getLogger(__name__)

BASE_URL = "https://www.google.com/travel/flights"

# O Google Flights identifica a busca pelo parâmetro `tfs`: um protobuf
# serializado e codificado em base64. Uma URL de texto livre (?q=voos de X
# para Y) NÃO preenche a rota — cai numa página genérica cujos preços são
# promoções não relacionadas à busca. Por isso montamos o protobuf na mão
# (são poucos campos, não vale uma dependência de protobuf só pra isso).


def _varint(n: int) -> bytes:
    saida = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            saida.append(b | 0x80)
        else:
            saida.append(b)
            return bytes(saida)


def _chave(campo: int, tipo: int) -> bytes:
    return _varint((campo << 3) | tipo)


def _submensagem(campo: int, payload: bytes) -> bytes:
    return _chave(campo, 2) + _varint(len(payload)) + payload


def _texto(campo: int, valor: str) -> bytes:
    return _submensagem(campo, valor.encode())


def _inteiro(campo: int, valor: int) -> bytes:
    return _chave(campo, 0) + _varint(valor)


def _trecho(data: str, origem: str, destino: str) -> bytes:
    """Um trecho da viagem: data + aeroporto de origem (13) + destino (14)."""
    return _texto(2, data) + _submensagem(13, _texto(2, origem)) + _submensagem(14, _texto(2, destino))


def montar_url(origem: str, destino: str, data_ida: str, data_volta: str, moeda: str) -> str:
    """URL do Google Flights com rota e datas já selecionadas.

    É a mesma URL que o scraper abre — vai junto no alerta para você abrir
    direto o trajeto (não é link de pagamento/reserva).
    """
    busca = (
        _submensagem(3, _trecho(data_ida, origem, destino))
        + _submensagem(3, _trecho(data_volta, destino, origem))
        + _inteiro(8, 1)  # 1 passageiro adulto
        + _inteiro(9, 1)  # classe econômica
        + _inteiro(19, 1)  # ida e volta
    )
    tfs = base64.b64encode(busca).decode()
    return f"{BASE_URL}?tfs={tfs}&hl=pt-BR&curr={moeda}"


# Cada célula do calendário de preços vem com um aria-label no formato
# "R$ 795, 7 de mai. para 14 de mai." — preço e datas juntos, o que é bem
# mais confiável do que garimpar valores no texto solto da página.
MESES_PT = {
    "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12,
}

_CELULA = re.compile(
    r"([\d.,]+),\s*(\d{1,2}) de ([a-zç]{3,4})\.?\s+para\s+(\d{1,2}) de ([a-zç]{3,4})\.?",
    re.IGNORECASE,
)


def _com_ano(dia: int, mes: int, referencia: date) -> date | None:
    """O calendário não informa o ano; deduz pelo ano mais próximo da semente."""
    for ano in (referencia.year, referencia.year + 1, referencia.year - 1):
        try:
            candidata = date(ano, mes, dia)
        except ValueError:
            continue
        if abs((candidata - referencia).days) <= 200:
            return candidata
    return None


def _ler_calendario(page, moeda: str, referencia: date) -> list[tuple[float, date, date]]:
    simbolo = CURRENCY_SYMBOLS.get(moeda.upper(), re.escape(moeda))
    combinacoes = []
    for elemento in page.locator("[aria-label]").all():
        try:
            rotulo = elemento.get_attribute("aria-label") or ""
        except Exception:
            continue
        if not re.search(simbolo, rotulo):
            continue
        achado = _CELULA.search(re.sub(simbolo, "", rotulo))
        if not achado:
            continue
        preco = parse_preco(achado.group(1))
        mes_ida = MESES_PT.get(achado.group(3)[:3].lower())
        mes_volta = MESES_PT.get(achado.group(5)[:3].lower())
        if preco is None or not mes_ida or not mes_volta:
            continue
        ida = _com_ano(int(achado.group(2)), mes_ida, referencia)
        volta = _com_ano(int(achado.group(4)), mes_volta, referencia)
        if ida and volta and volta > ida:
            combinacoes.append((preco, ida, volta))
    return combinacoes


def _achar_aba_menores_precos(page):
    """Devolve (elemento, rótulo) da aba 'Menores preços', ou (None, None)."""
    for elemento in page.get_by_role("tab").all():
        try:
            rotulo = (elemento.get_attribute("aria-label") or elemento.inner_text() or "")
        except Exception:
            continue
        rotulo = rotulo.replace("\n", " ").strip()
        if "menores pre" in rotulo.lower():
            return elemento, rotulo
    return None, None


def _ativar_aba_menores_precos(page, moeda: str) -> float | None:
    """Ativa a aba 'Menores preços' e espera ela terminar de carregar.

    A aba recalcula os preços de forma assíncrona: logo após o clique ela
    ainda mostra os valores da aba "Melhor opção", que são mais altos. Só
    consideramos pronta quando ela aparece selecionada E o rótulo já traz o
    preço ("Menores preços a partir de R$ 795") — esse valor é o menor preço
    para as datas buscadas, e é devolvido como resultado.
    """
    elemento, _ = _achar_aba_menores_precos(page)
    if elemento is None:
        logger.warning("Aba 'Menores preços' não encontrada — seguindo com a aba padrão")
        return None

    try:
        elemento.click(timeout=10_000)
    except Exception:
        try:
            elemento.dispatch_event("click")  # o clique normal às vezes é interceptado
        except Exception:
            logger.warning("Não consegui clicar na aba 'Menores preços'")
            return None

    simbolo = CURRENCY_SYMBOLS.get(moeda.upper(), re.escape(moeda))
    for _ in range(16):
        page.wait_for_timeout(2_500)
        elemento, rotulo = _achar_aba_menores_precos(page)
        if elemento is None:
            continue
        try:
            selecionada = elemento.get_attribute("aria-selected") == "true"
        except Exception:
            selecionada = False
        # "Buscando resultados" no rótulo significa que o preço exibido ainda é
        # parcial: ele aparece junto com um valor que pode mudar em seguida.
        carregando = re.search(r"buscando|searching", rotulo or "", re.IGNORECASE)
        achado = re.search(rf"{simbolo}\s*([\d.,]+)", rotulo or "")
        if selecionada and achado and not carregando:
            preco = parse_preco(achado.group(1))
            logger.info("Aba 'Menores preços' carregada: %s", rotulo)
            return preco

    logger.warning("Aba 'Menores preços' não terminou de carregar a tempo")
    return None


def _abrir_calendario(page) -> bool:
    """Abre o calendário de preços. O botão nem sempre está pronto de cara."""
    for tentativa in range(3):
        try:
            botao = page.get_by_role("button", name="Calendário")
            botao.click(timeout=10_000)
            page.wait_for_timeout(6_000)
            return True
        except Exception:
            if tentativa == 0:
                try:
                    page.keyboard.press("Escape")  # fecha overlay que possa cobrir o botão
                except Exception:
                    pass
            page.wait_for_timeout(4_000)
    logger.warning("Não consegui abrir o calendário de preços")
    return False


def buscar_combinacoes(
    origem: str, destino: str, data_ida: str, data_volta: str, moeda: str
) -> list[tuple[float, date, date]]:
    """Combinações (preço, ida, volta) para as datas em volta das informadas.

    Sempre ativa a aba "Menores preços" e espera ela carregar antes de ler
    qualquer preço — a aba padrão ("Melhor opção") mostra valores mais altos,
    por priorizar custo-benefício em vez do menor preço.

    Levanta RuntimeError se não conseguir ler nenhuma combinação.
    """
    url = montar_url(origem, destino, data_ida, data_volta, moeda)
    referencia = date.fromisoformat(data_ida)
    ida_pedida = date.fromisoformat(data_ida)
    volta_pedida = date.fromisoformat(data_volta)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        contexto = browser.new_context(locale="pt-BR")
        page = contexto.new_page()
        try:
            page.goto(url, timeout=45_000, wait_until="domcontentloaded")

            # Fecha diálogo de consentimento de cookies do Google, se aparecer.
            for texto_botao in ["Aceitar tudo", "Accept all", "Concordo", "I agree"]:
                try:
                    botao = page.get_by_role("button", name=texto_botao)
                    if botao.is_visible(timeout=2_000):
                        botao.click()
                        break
                except Exception:
                    pass

            page.wait_for_timeout(7_000)

            # Ordem importa: o calendário precisa ser lido ANTES de trocar de
            # aba — ativar "Menores preços" primeiro faz o botão do calendário
            # sumir, e aí se perde a varredura de datas flexíveis.
            combinacoes = []
            if _abrir_calendario(page):
                combinacoes = _ler_calendario(page, moeda, referencia)
                try:
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(2_000)
                except Exception:
                    pass

            preco_da_aba = _ativar_aba_menores_precos(page, moeda)
        finally:
            browser.close()

    # O preço da aba vale para as datas exatas que foram buscadas e costuma
    # ser mais confiável que a grade, então entra como candidato próprio.
    if preco_da_aba is not None:
        combinacoes.append((preco_da_aba, ida_pedida, volta_pedida))

    if not combinacoes:
        raise RuntimeError(
            "Nenhum preço lido no Google Flights "
            "(layout pode ter mudado ou a busca foi bloqueada)"
        )
    return combinacoes
