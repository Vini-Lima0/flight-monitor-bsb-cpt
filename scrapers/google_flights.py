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


def buscar_combinacoes(
    origem: str, destino: str, data_ida: str, data_volta: str, moeda: str
) -> list[tuple[float, date, date]]:
    """Abre o calendário de preços em volta das datas dadas e devolve todas
    as combinações (preço, ida, volta) que o Google mostrar na grade.

    Levanta RuntimeError se não conseguir ler nenhuma combinação.
    """
    url = montar_url(origem, destino, data_ida, data_volta, moeda)
    referencia = date.fromisoformat(data_ida)

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
            page.get_by_role("button", name="Calendário").click(timeout=15_000)
            page.wait_for_timeout(6_000)

            combinacoes = _ler_calendario(page, moeda, referencia)
        finally:
            browser.close()

    if not combinacoes:
        raise RuntimeError(
            "Nenhuma combinação lida no calendário do Google Flights "
            "(layout pode ter mudado ou a busca foi bloqueada)"
        )
    return combinacoes
