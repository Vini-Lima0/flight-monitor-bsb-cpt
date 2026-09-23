#!/bin/bash
# Execução local agendada (launchd, a cada 30 min) — ver README.
#
# O GitHub Actions não cumpre o cron de 30 min (atrasa/descarta execuções),
# então este script dá a cadência real enquanto o Mac estiver ligado. O
# histórico é sincronizado via git para que as execuções locais e as do
# Actions compartilhem o mesmo estado de alerta (sem alertar duas vezes).

set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR" || exit 1

export PATH="/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin:$PATH"

# Traz o estado mais recente (execuções do Actions) antes de comparar preços.
git pull --rebase --quiet origin main || echo "[aviso] git pull falhou, seguindo com o estado local"

.venv/bin/python flight_monitor.py
status=$?

# Sobe o histórico atualizado. Sem isso, execuções locais e do Actions
# divergiriam e o mesmo preço poderia alertar duas vezes.
if ! git diff --quiet data/; then
  git add data/history.csv data/alert_state.json
  git commit --quiet -m "chore: atualiza histórico de preços (local) [skip ci]"
  git push --quiet origin main || echo "[aviso] git push falhou, tenta na próxima execução"
fi

exit $status
