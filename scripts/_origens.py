"""Sonda de alcance das origens, para as baterias de ``scripts/verificar_*.py``.

O runner do GitHub fica nos EUA e algumas origens brasileiras não respondem
de lá (o ``servicodados.ibge.gov.br`` dá timeout, e do Brasil responde em
0,3 s). Falha por isso não é defeito do Guaraci, e deixá-la como falha
esconde as reais. No início da bateria, ``ALCANCE.sondar()`` testa cada host
da lista; se um deles não responde, a falha cujo texto cita esse host vira
AVISO ("origem inalcançável a partir do runner"). Se o host responde, nada
muda: falha continua falha.

Só usa a biblioteca padrão, para valer também no venv do Playwright.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, Iterable, List, Optional
from urllib.error import HTTPError
from urllib.request import Request, urlopen

# Hosts sondados. Para incluir outra origem instável do runner, basta o nome aqui.
HOSTS = ("servicodados.ibge.gov.br",)
MOTIVO = "origem inalcançável a partir do runner"


def host_responde(host: str, tentativas: int = 2, timeout: float = 10.0,
                  abrir: Callable[..., Any] = urlopen, pausa: float = 2.0) -> bool:
    """True se o host devolve qualquer resposta HTTP (até 404). Sem resposta
    (timeout, conexão recusada, DNS) em todas as tentativas, False."""
    for i in range(tentativas):
        try:
            req = Request(f"https://{host}/", headers={"User-Agent": "guaraci-verificacao"})
            with abrir(req, timeout=timeout):
                return True
        except HTTPError:
            return True
        except Exception:  # noqa: BLE001  (URLError, timeout, ssl, reset)
            if i + 1 < tentativas:
                time.sleep(pausa)
    return False


class Alcance:
    def __init__(self) -> None:
        self.resultados: Dict[str, bool] = {}

    def sondar(self, hosts: Iterable[str] = HOSTS, **kw: Any) -> Dict[str, bool]:
        for host in hosts:
            self.resultados[host] = host_responde(host, **kw)
            if not self.resultados[host]:
                print(f"AVISO  sonda: {host} {MOTIVO}; falhas que citam esse host viram aviso", flush=True)
        return self.resultados

    @property
    def inalcancaveis(self) -> List[str]:
        return [h for h, ok in self.resultados.items() if not ok]

    def afetado(self, texto: Any) -> Optional[str]:
        """Host inalcançável citado no texto da falha, se houver."""
        texto = str(texto)
        return next((h for h in self.inalcancaveis if h in texto), None)

    def relatorio(self) -> Dict[str, Any]:
        return {h: ("alcançável" if ok else MOTIVO) for h, ok in self.resultados.items()}


ALCANCE = Alcance()
