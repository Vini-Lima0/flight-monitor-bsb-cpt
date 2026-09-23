"""Scraper do Google Flights via Playwright.

Google Flights não tem API pública. Isso aqui abre a página normal
(headless) e lê o texto renderizado procurando por valores monetários.
É frágil por natureza: se o Google mudar o layout, isso pode parar de
funcionar sem aviso — ver limitações no README.
"""

import base64
import logging

from playwright.sync_api import sync_playwright

from scrapers.common import escolher_menor_preco, extract_prices

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


def buscar_menor_preco(origem: str, destino: str, data_ida: str, data_volta: str, moeda: str) -> float:
    """Retorna o menor preço encontrado na página de resultados do Google Flights.

    Levanta RuntimeError se não conseguir extrair nenhum preço plausível.
    """
    url = montar_url(origem, destino, data_ida, data_volta, moeda)

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

            # Espera os resultados carregarem (a busca é feita via JS após o load).
            page.wait_for_timeout(8_000)
            try:
                page.wait_for_load_state("networkidle", timeout=20_000)
            except Exception:
                logger.warning("networkidle não atingido a tempo, seguindo com o texto atual da página")

            conteudo = page.inner_text("body")
        finally:
            browser.close()

    precos = extract_prices(conteudo, moeda)
    if not precos:
        raise RuntimeError("Nenhum preço encontrado na página do Google Flights (layout pode ter mudado)")

    preco, confiavel = escolher_menor_preco(precos)
    if not confiavel:
        logger.warning(
            "Preço %.2f aparece uma única vez na página (baixa confiança — "
            "pode ser ruído de banner/sugestão não relacionado à rota buscada)",
            preco,
        )
    return preco
