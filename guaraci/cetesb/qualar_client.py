"""Cliente autenticado do QUALAR clássico, o caminho da CONCENTRAÇÃO.

O ArcGIS público (:mod:`guaraci.cetesb.client`) entrega índice de qualidade do
ar. Concentração em µg/m³, que é o que um estudo de exposição precisa, só sai
pelo QUALAR clássico, atrás de login. Este módulo faz esse caminho.

O protocolo, reconstruído a partir do HTML do próprio sistema e do pacote R
`qualR` (rOpenSci, MIT), tem dois passos:

1. ``POST https://qualar.cetesb.sp.gov.br/qualar/autenticador`` com os campos
   ``cetesb_login`` e ``cetesb_password``. A sessão fica num cookie, então o
   cliente mantém um ``CookieJar`` próprio entre as chamadas.
2. ``POST https://qualar.cetesb.sp.gov.br/qualar/exportaDados.do?method=pesquisar``
   com ``irede=A`` (rede automática), ``dataInicialStr``/``dataFinalStr`` em
   ``dd/mm/aaaa``, ``iTipoDado=P``, ``estacaoVO.nestcaMonto`` (código da
   estação) e ``parametroVO.nparmt`` (código do parâmetro).

Três características do sistema que moldam este código
------------------------------------------------------
- **A resposta é HTML, não CSV.** Apesar do nome ``exportaDados``, o que volta
  é uma página com os dados numa tabela de 19 colunas, a SEGUNDA da página. O
  parser aqui é o ``html.parser`` da biblioteca padrão, para não acrescentar
  dependência a um projeto que hoje resolve tudo com urllib e polars.
- **Um pedido por estação e por parâmetro.** Não há chamada em lote. Varrer as
  62 estações ativas para 6 poluentes são 372 requisições, e por isso existe
  uma pausa configurável entre elas: este é um sistema público de um órgão
  estadual, não uma API dimensionada para varredura.
- **Nem toda linha é dado válido.** A coluna ``Validado`` (``Sim``/``Não``)
  diz se a leitura passou pela validação da CETESB. O padrão aqui é devolver
  só as validadas, porque é o que serve para análise, mas a escolha fica
  exposta como parâmetro em vez de embutida.

Números vêm no formato brasileiro (``1.234,56``), então a conversão tira o
ponto de milhar antes de trocar a vírgula por ponto. Fazer só a troca da
vírgula transformaria 1.234,56 em 1.23456.
"""

from __future__ import annotations

import time
from datetime import date, datetime
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from typing import Dict, List, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener

from guaraci import __version__
from guaraci.cetesb.client import CetesbClientError
from guaraci.cetesb.codes import Parameter, Station, resolve_parameter, resolve_station

__all__ = [
    "CetesbAuthError",
    "QualarClient",
    "QualarReading",
    "parse_qualar_html",
    "parse_brazilian_number",
    "REGISTRATION_URL",
]

REGISTRATION_URL = "https://seguranca.cetesb.sp.gov.br/Home/CadastrarUsuario"
"""Onde o operador cria a conta exigida por este caminho."""

# Nomes das 19 colunas da tabela, na ordem em que o QUALAR as emite.
_COLUMNS: Tuple[str, ...] = (
    "empresa", "rede", "motivo", "tipo", "dia", "hora", "codigo", "estacao",
    "parametro", "unidade", "valor", "movel", "validado", "dt_amostragem",
    "dt_instalacao", "dt_retirada", "conclusao", "taxa", "empresa2",
)
_EXPECTED_COLUMNS = len(_COLUMNS)


class CetesbAuthError(CetesbClientError):
    """Levantado quando o login no QUALAR não se sustenta."""


class QualarReading(Dict[str, object]):
    """Uma leitura horária. Dict para ir direto ao polars sem conversão."""


def parse_brazilian_number(raw: object) -> Optional[float]:
    """Converte ``"1.234,56"`` em ``1234.56``; devolve ``None`` se não for número.

    A ordem importa: primeiro some com o ponto de milhar, só depois troque a
    vírgula decimal. Inverter transforma ``1.234,56`` em ``1.23456``.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text or text in {"-", "--"}:
        return None
    try:
        return float(text.replace(".", "").replace(",", "."))
    except ValueError:
        return None


class _TableParser(HTMLParser):
    """Extrai o texto de cada célula, tabela a tabela.

    O QUALAR é HTML dos anos 90: tabelas aninhadas usadas como layout, e a
    tabela de dados mora dentro de outras. Por isso tudo aqui é pilha. Uma
    implementação de um nível só perderia a tabela externa ao encontrar a
    interna, e o resultado seria zero linhas sem erro nenhum, que é o pior
    modo de falhar.

    Células não fechadas também são regra nesse HTML, então um ``<td>`` novo
    fecha o anterior em vez de esperar pelo ``</td>`` que talvez nunca venha.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: List[List[List[str]]] = []
        self._tables: List[List[List[str]]] = []
        self._rows: List[List[str]] = []
        self._cell: Optional[List[str]] = None

    # -- pilha ---------------------------------------------------------
    def _close_cell(self) -> None:
        if self._cell is not None and self._rows:
            self._rows[-1].append(" ".join("".join(self._cell).split()))
        self._cell = None

    def _close_row(self) -> None:
        self._close_cell()
        if self._rows and self._tables:
            row = self._rows.pop()
            if row:
                self._tables[-1].append(row)

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "table":
            self._tables.append([])
        elif tag == "tr":
            if self._tables:
                self._close_row()
                self._rows.append([])
        elif tag in ("td", "th"):
            if self._rows:
                self._close_cell()
                self._cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th"):
            self._close_cell()
        elif tag == "tr":
            self._close_row()
        elif tag == "table":
            self._close_row()
            if self._tables:
                self.tables.append(self._tables.pop())

    def close(self) -> None:  # pragma: no cover - fecho defensivo
        super().close()
        self._close_row()
        while self._tables:
            self.tables.append(self._tables.pop())

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)


def parse_qualar_html(html: str) -> List[List[str]]:
    """Devolve as linhas de dados da tabela de 19 colunas.

    Em vez de confiar na posição da tabela na página (o ``qualR`` usa a
    segunda, e uma mudança de layout quebraria isso em silêncio), procura-se a
    tabela cujas linhas têm 19 células. É o mesmo resultado hoje e resiste a
    a CETESB acrescentar um cabeçalho ou um rodapé.
    """
    parser = _TableParser()
    parser.feed(html)
    for table in parser.tables:
        data_rows = [row for row in table if len(row) == _EXPECTED_COLUMNS]
        if data_rows:
            return data_rows
    return []


class QualarClient:
    """Sessão autenticada no QUALAR clássico."""

    DEFAULT_BASE_URL = "https://qualar.cetesb.sp.gov.br/qualar"
    DEFAULT_TIMEOUT = 180
    DEFAULT_PAUSE_SECONDS = 1.0

    def __init__(
        self,
        *,
        login: str,
        password: str,
        base_url: Optional[str] = None,
        timeout_seconds: int = DEFAULT_TIMEOUT,
        pause_seconds: float = DEFAULT_PAUSE_SECONDS,
    ) -> None:
        if not (login or "").strip():
            raise ValueError("QUALAR login cannot be empty.")
        if not (password or "").strip():
            raise ValueError("QUALAR password cannot be empty.")
        selected = (base_url or self.DEFAULT_BASE_URL).strip().rstrip("/")
        if not selected:
            raise ValueError("QUALAR base URL cannot be empty.")
        self.base_url = selected
        self._login = login.strip()
        self._password = password
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.pause_seconds = max(0.0, float(pause_seconds))
        self._opener = build_opener(HTTPCookieProcessor(CookieJar()))
        self._authenticated = False

    # ------------------------------------------------------------------
    # Autenticação
    # ------------------------------------------------------------------
    def authenticate(self) -> None:
        """Faz login e guarda o cookie de sessão.

        O QUALAR responde 200 mesmo para credencial errada, devolvendo a
        própria tela de login. Por isso o sucesso é verificado pelo conteúdo,
        e não pelo código HTTP: sem essa checagem, uma senha errada viraria
        "nenhum dado no período", que é um diagnóstico completamente falso.
        """
        body = urlencode(
            {
                "cetesb_login": self._login,
                "cetesb_password": self._password,
                "enviar": "OK",
            }
        ).encode("latin-1", errors="replace")
        html = self._post(f"{self.base_url}/autenticador", body)
        if "cetesb_password" in html.lower():
            raise CetesbAuthError(
                "QUALAR rejected the credentials (the login form came back).",
                category="configuration",
                retryable=False,
                hint=(
                    "Confirme usuário e senha do QUALAR. Conta gratuita em "
                    f"{REGISTRATION_URL}"
                ),
            )
        self._authenticated = True

    # ------------------------------------------------------------------
    # Consulta
    # ------------------------------------------------------------------
    def fetch_readings(
        self,
        *,
        station: object,
        parameter: object,
        start: date,
        end: date,
        only_validated: bool = True,
    ) -> List[QualarReading]:
        """Leituras horárias de UMA estação e UM parâmetro num intervalo."""
        resolved_station = resolve_station(station)
        resolved_parameter = resolve_parameter(parameter)
        if end < start:
            raise ValueError("Parameter 'end' cannot be before 'start'.")
        if not self._authenticated:
            self.authenticate()

        body = urlencode(
            {
                "irede": "A",
                "dataInicialStr": start.strftime("%d/%m/%Y"),
                "dataFinalStr": end.strftime("%d/%m/%Y"),
                "iTipoDado": "P",
                "estacaoVO.nestcaMonto": str(resolved_station.code),
                "parametroVO.nparmt": str(resolved_parameter.code),
            }
        ).encode("latin-1", errors="replace")

        html = self._post(f"{self.base_url}/exportaDados.do?method=pesquisar", body)
        if "cetesb_password" in html.lower():
            # A sessão caiu no meio da varredura; uma tentativa de reautenticar
            # evita perder uma coleta longa por causa de um timeout de sessão.
            self._authenticated = False
            self.authenticate()
            html = self._post(f"{self.base_url}/exportaDados.do?method=pesquisar", body)

        rows = parse_qualar_html(html)
        readings = self._rows_to_readings(
            rows,
            station=resolved_station,
            parameter=resolved_parameter,
            only_validated=only_validated,
        )
        if self.pause_seconds:
            time.sleep(self.pause_seconds)
        return readings

    @staticmethod
    def _rows_to_readings(
        rows: Sequence[Sequence[str]],
        *,
        station: Station,
        parameter: Parameter,
        only_validated: bool,
    ) -> List[QualarReading]:
        readings: List[QualarReading] = []
        for row in rows:
            record = dict(zip(_COLUMNS, row))
            validated = record.get("validado", "").strip().casefold().startswith("s")
            if only_validated and not validated:
                continue
            moment = QualarClient._parse_moment(record.get("dia"), record.get("hora"))
            if moment is None:
                continue
            readings.append(
                QualarReading(
                    estacao=station.name,
                    codigo_estacao=station.code,
                    latitude=station.latitude,
                    longitude=station.longitude,
                    parametro=parameter.abbreviation,
                    codigo_parametro=parameter.code,
                    unidade=(record.get("unidade") or "").strip() or None,
                    datahora=moment,
                    valor=parse_brazilian_number(record.get("valor")),
                    validado=validated,
                )
            )
        return readings

    @staticmethod
    def _parse_moment(day: Optional[str], hour: Optional[str]) -> Optional[datetime]:
        """Combina ``dd/mm/aaaa`` com ``HH:MM`` em um datetime ingênuo.

        O QUALAR publica hora local de São Paulo sem indicar fuso, então o
        datetime fica ingênuo de propósito, coerente com o que o conector do
        ArcGIS faz com os campos ``TM``.
        """
        day_text = (day or "").strip()
        hour_text = (hour or "").strip()
        if not day_text:
            return None
        if not hour_text:
            hour_text = "00:00"
        # 24:00 é meia-noite do dia seguinte na notação da CETESB; o strptime
        # não aceita, então vira 00:00 do dia seguinte.
        rollover = hour_text.startswith("24")
        if rollover:
            hour_text = "00" + hour_text[2:]
        for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y %H"):
            try:
                moment = datetime.strptime(f"{day_text} {hour_text}", fmt)
            except ValueError:
                continue
            if rollover:
                from datetime import timedelta

                moment += timedelta(days=1)
            return moment
        return None

    # ------------------------------------------------------------------
    # Interno
    # ------------------------------------------------------------------
    def _post(self, url: str, body: bytes) -> str:
        request = Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": f"guaraci/{__version__}",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        try:
            with self._opener.open(request, timeout=self.timeout_seconds) as response:
                raw = response.read()
        except HTTPError as exc:
            if 300 <= exc.code < 400:
                # O autenticador confirma login certo com 302 SEM cabeçalho
                # Location (verificado ao vivo em 2026-09-24). O urllib não tem
                # para onde seguir e levanta HTTPError, mas o cookie de sessão
                # já foi gravado: é resposta de sucesso, não falha.
                return exc.read().decode("latin-1", errors="replace")
            raise CetesbClientError(
                f"QUALAR request failed ({exc.code}).",
                category="http_error",
                retryable=exc.code >= 500,
                hint="Confirme a URL do QUALAR e se o sistema está no ar.",
            ) from exc
        except URLError as exc:
            raise CetesbClientError(
                f"Could not connect to QUALAR at '{self.base_url}': {exc.reason}",
                category="connectivity",
                retryable=True,
                hint="Verifique acesso à internet, DNS e regras de proxy.",
            ) from exc
        except (TimeoutError, OSError) as exc:
            raise CetesbClientError(
                f"QUALAR request timed out after {self.timeout_seconds} seconds.",
                category="timeout",
                retryable=True,
                hint="O QUALAR é lento para intervalos longos; reduza o período.",
            ) from exc
        # O sistema declara iso-8859-1 no próprio HTML.
        return raw.decode("latin-1", errors="replace")
