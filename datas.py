"""Datas candidatas da viagem: mês alvo + duração fixa, com datas flexíveis.

A busca não é mais por um par de datas fixo. Você escolhe o MÊS da viagem e
quantos dias quer viajar; o bot procura a combinação mais barata dentro do
mês, deslizando a data de ida.

Cada abertura do calendário do Google Flights devolve uma grade em volta de
uma data "semente", então algumas poucas sementes cobrem o mês inteiro sem
precisar abrir uma página por combinação.

Continua valendo a regra do horizonte: companhias aéreas não vendem passagem
com mais de ~330 dias de antecedência. Se o mês alvo inteiro ainda estiver
além disso, o bot busca a data mais distante possível hoje e vai se
aproximando do mês alvo conforme o calendário avança.
"""

from calendar import monthrange
from datetime import date, timedelta

HORIZONTE_PADRAO_DIAS = 330

# Uma semente a cada 7 dias: a grade do Google cobre ~3 dias para cada lado.
PASSO_SEMENTES = 7


def mes_alvo(cfg: dict) -> tuple[int, int]:
    ano, mes = str(cfg["mes_alvo"]).split("-")
    return int(ano), int(mes)


def limite_busca(cfg: dict, hoje: date | None = None) -> date:
    hoje = hoje or date.today()
    return hoje + timedelta(days=int(cfg.get("horizonte_max_dias", HORIZONTE_PADRAO_DIAS)))


def datas_semente(cfg: dict, hoje: date | None = None) -> tuple[list[tuple[str, str]], bool]:
    """Pares (ida, volta) para abrir o calendário de preços.

    Retorna (sementes, dentro_do_mes_alvo). Quando o mês alvo inteiro está
    além do horizonte de busca, devolve uma única semente na data máxima
    alcançável hoje e `dentro_do_mes_alvo=False`.
    """
    hoje = hoje or date.today()
    ano, mes = mes_alvo(cfg)
    duracao = int(cfg["duracao_dias"])
    ultimo_dia = monthrange(ano, mes)[1]
    limite = limite_busca(cfg, hoje)

    sementes: list[tuple[str, str]] = []
    for inicio in range(1, ultimo_dia + 1, PASSO_SEMENTES):
        ida = date(ano, mes, min(inicio + 3, ultimo_dia))
        if ida > limite or ida <= hoje:
            continue
        par = (ida.isoformat(), (ida + timedelta(days=duracao)).isoformat())
        if par not in sementes:
            sementes.append(par)

    if sementes:
        return sementes, True

    ida = limite
    return [(ida.isoformat(), (ida + timedelta(days=duracao)).isoformat())], False


def combinacao_valida(cfg: dict, ida: date, volta: date, hoje: date | None = None) -> bool:
    """A combinação serve? Ida no mês alvo, duração exata e dentro do horizonte."""
    ano, mes = mes_alvo(cfg)
    return (
        ida.year == ano
        and ida.month == mes
        and (volta - ida).days == int(cfg["duracao_dias"])
        and ida <= limite_busca(cfg, hoje)
        and ida > (hoje or date.today())
    )
