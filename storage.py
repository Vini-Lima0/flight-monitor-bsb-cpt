"""Leitura e escrita do histórico de preços e do estado de alertas já disparados."""

import csv
import json
import os
from datetime import datetime, timezone

HISTORY_PATH = os.path.join(os.path.dirname(__file__), "data", "history.csv")
ALERT_STATE_PATH = os.path.join(os.path.dirname(__file__), "data", "alert_state.json")

HISTORY_FIELDS = ["timestamp_utc", "data_ida", "data_volta", "preco", "moeda", "fonte"]


def append_history(preco: float, moeda: str, fonte: str, data_ida: str, data_volta: str) -> None:
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    is_new = not os.path.exists(HISTORY_PATH)
    with open(HISTORY_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HISTORY_FIELDS)
        if is_new:
            writer.writeheader()
        writer.writerow(
            {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "data_ida": data_ida,
                "data_volta": data_volta,
                "preco": preco,
                "moeda": moeda,
                "fonte": fonte,
            }
        )


def lowest_historical_price(data_ida: str, data_volta: str) -> float | None:
    """Menor preço já registrado no histórico para o mesmo par de datas.

    Filtra por data_ida/data_volta porque, enquanto a viagem alvo estiver
    fora do horizonte de busca (ver datas.py), a data efetivamente buscada
    muda a cada execução — comparar preços de datas diferentes como se
    fossem a mesma viagem daria falsos "novo menor preço".
    """
    if not os.path.exists(HISTORY_PATH):
        return None
    menor = None
    with open(HISTORY_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("data_ida") != data_ida or row.get("data_volta") != data_volta:
                continue
            try:
                preco = float(row["preco"])
            except (KeyError, ValueError):
                continue
            if menor is None or preco < menor:
                menor = preco
    return menor


def load_alert_state() -> dict:
    if not os.path.exists(ALERT_STATE_PATH):
        return {"lowest_alerted_price": None}
    with open(ALERT_STATE_PATH, encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {"lowest_alerted_price": None}


def save_alert_state(state: dict) -> None:
    os.makedirs(os.path.dirname(ALERT_STATE_PATH), exist_ok=True)
    with open(ALERT_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
