"""Helpers compartilhados pelos scrapers (extração de preço a partir de texto)."""

import re
from collections import Counter

CURRENCY_SYMBOLS = {
    "BRL": r"R\$",
    "USD": r"US\$|\$",
    "EUR": r"€",
    "GBP": r"£",
}


def extract_prices(page_text: str, moeda: str) -> list[float]:
    """Extrai todos os valores monetários plausíveis de um texto de página.

    Aceita formatos "R$ 4.321", "R$4.321,00", "$1,234", etc. Filtra valores
    fora de uma faixa plausível para passagens internacionais (200 a 100000)
    para reduzir falsos positivos (preços de taxas, bagagem, etc. muito baixos
    e números de voo/CEP muito altos).
    """
    simbolo = CURRENCY_SYMBOLS.get(moeda.upper(), re.escape(moeda))
    padrao = rf"(?:{simbolo})\s?([\d]{{1,3}}(?:[.,]\d{{3}})*(?:[.,]\d{{2}})?)"

    valores = []
    for match in re.finditer(padrao, page_text):
        bruto = match.group(1)
        valor = _para_float(bruto)
        if valor is not None and 200 <= valor <= 100_000:
            valores.append(valor)
    return valores


def escolher_menor_preco(precos: list[float]) -> tuple[float, bool]:
    """Escolhe, entre os valores extraídos da página, o mais provável de ser
    o preço real do voo buscado.

    A extração é feita sobre o texto inteiro da página (ver extract_prices),
    então pode capturar valores de banners/sugestões de outras rotas que nada
    têm a ver com a busca. Como mitigação: o preço de um resultado de voo de
    verdade costuma aparecer mais de uma vez na página (no card do resultado,
    no resumo, no gráfico de preços), enquanto um valor "de ruído" tende a
    aparecer uma única vez. Por isso, preferimos o menor valor que se repete;
    só caímos para o menor valor absoluto (com uma flag de baixa confiança)
    se nenhum se repetir.

    Retorna (preco, confiavel).
    """
    contagem = Counter(precos)
    repetidos = [preco for preco, n in contagem.items() if n >= 2]
    if repetidos:
        return min(repetidos), True
    return min(precos), False


def _para_float(bruto: str) -> float | None:
    """Converte '4.321', '4.321,00' ou '4,321.00' para float.

    O separador decimal x separador de milhar é ambíguo entre BRL e USD, então
    a regra é estrutural: o último grupo separado por "." ou "," só é decimal
    se tiver exatamente 2 dígitos — senão, todo mundo é separador de milhar.
    """
    partes = re.split(r"[.,]", bruto.strip())
    if len(partes) == 1:
        try:
            return float(partes[0])
        except ValueError:
            return None

    ultimo = partes[-1]
    if len(ultimo) == 2:
        texto_numero = f"{''.join(partes[:-1])}.{ultimo}"
    else:
        texto_numero = "".join(partes)

    try:
        return float(texto_numero)
    except ValueError:
        return None
