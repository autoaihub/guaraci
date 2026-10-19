"""Arquivos de dados abertos em URL fixa, publicados por HTTP.

Cada fonte aponta para um ou mais arquivos (CSV ou zip) cuja URL não muda; o
conteúdo é que é republicado por cima. O download faz ``HEAD`` antes para não
baixar de novo o que não mudou, grava em fluxo e, com ``output_format``,
converte para CSV UTF-8, Parquet ou SQLite sem carregar o arquivo na memória.
Todas as colunas ficam como texto e os nomes de coluna saem como publicados
(só ``strip``): número em formato pt-BR (``1.874,061``), negativos e brancos
passam intactos, pois interpretar é papel da camada prata, não do bronze.

Fontes:

- ``vigitel``: Vigitel 2006-2024 com peso de pós-estratificação (rake), um zip
  de 87 MB com um CSV de 577 MB. Colunas esparsas por ano são esperadas.
- ``ibama_agrotoxicos_comercializacao``: relatórios de comercialização de
  agrotóxicos do IBAMA (UTF-8 com BOM, ``;``, 33 colunas largas).
- ``farmacia_popular_indicadores``: 14 indicadores do Programa Farmácia
  Popular (bucket S3 do DEMAS), um zip com um CSV por indicador.
- ``mgdi_*``: indicadores agregados do MGDI do Ministério da Saúde (SAMU, UPA,
  RAPS, eMulti, Academia da Saúde, Telessaúde, saúde bucal), mesmo bucket e mesmo
  esquema da Farmácia Popular. Só indicador agregado, sem dado pessoal.
- ``pni_doses_aplicadas_arquivos``: doses aplicadas do PNI (microdado de vacinação),
  um zip de CSV por mês de 2020 a 2026 no bucket ``ckan.saude.gov.br``. Alternativa
  à API DEMAS (``doses_aplicadas_pni``), que devolve 502 acima de ~1 milhão de
  offset por ano. Cada zip tem de 0,4 a 4 GB e o ano inteiro passa de 14 GB
  comprimidos, por isso ``anos`` é obrigatório e ``meses`` recorta dentro do ano.
- ``sisvan_estado_nutricional_arquivos``: acompanhamento do estado nutricional do
  SISVAN, um zip de CSV por ano (2008-2023, de 0,9 a 4,4 GB cada), mesma origem.
"""

from __future__ import annotations

import codecs
import http.client
import os
import re
import socket
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import polars as pl

from guaraci import __version__
from guaraci.core.datasource import DataSource
from guaraci.core.http import (
    ApiClientError,
    classify_http_status,
    is_timeout_reason,
    request_with_retry,
)
from guaraci.datasus.frames import write_sqlite

__all__ = [
    "FARMACIA_INDICADORES",
    "HTTP_FILES",
    "HttpFile",
    "HttpFileClient",
    "HttpFileClientError",
    "HttpFileDataSource",
    "HttpResource",
    "RemoteFile",
    "datasource_for",
]

ProgressCallback = Callable[[Dict[str, object]], None]
_FORMATS = ("csv", "parquet", "sqlite")


class HttpFileClientError(ApiClientError):
    """Falha ao consultar ou baixar um arquivo de URL fixa."""


def transport_error(
    exc: BaseException,
    what: str,
    timeout_seconds: int,
    error_cls: type = HttpFileClientError,
) -> Optional[ApiClientError]:
    """Converte falha de socket em erro retentável; ``None`` se não for de rede.

    Cobre ``TimeoutError``, ``http.client.IncompleteRead`` (e as demais
    ``HTTPException``), ``ConnectionResetError`` e ``OSError`` de socket em
    geral. ``OSError`` com ``filename`` vem do disco local (``open``), não da
    rede, e por isso fica de fora.
    """
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return error_cls(
            f"Timed out reaching '{what}' after {timeout_seconds} seconds.",
            category="timeout",
            retryable=True,
            hint="Arquivos grandes pedem timeout maior.",
        )
    if isinstance(exc, http.client.HTTPException) or (
        isinstance(exc, OSError) and getattr(exc, "filename", None) is None
    ):
        return error_cls(
            f"Connection to '{what}' was interrupted: {exc!r}",
            category="connectivity",
            retryable=True,
            hint="Verifique acesso à internet, DNS e regras de proxy.",
        )
    return None


def _url_is_zip(url: str) -> bool:
    return urlsplit(url).path.lower().endswith(".zip")


@dataclass(frozen=True)
class RemoteFile:
    url: str
    size: Optional[int]
    last_modified: Optional[str]
    etag: Optional[str] = None


class HttpFileClient:
    DEFAULT_TIMEOUT = 600
    USER_AGENT = f"guaraci/{__version__}"

    def __init__(self, *, timeout_seconds: int = DEFAULT_TIMEOUT, max_attempts: int = 3) -> None:
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.max_attempts = max_attempts

    def head(self, url: str) -> RemoteFile:
        def send() -> RemoteFile:
            request = Request(url, method="HEAD", headers={"User-Agent": self.USER_AGENT})
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    length = response.headers.get("Content-Length")
                    return RemoteFile(
                        url=url,
                        size=int(length) if length and length.isdigit() else None,
                        last_modified=response.headers.get("Last-Modified"),
                        etag=response.headers.get("ETag"),
                    )
            except HTTPError as exc:
                raise self._http_error(exc, url) from exc
            except URLError as exc:
                raise self._url_error(exc, url) from exc
            except (OSError, http.client.HTTPException) as exc:
                error = transport_error(exc, url, self.timeout_seconds)
                if error is None:
                    raise
                raise error from exc

        return request_with_retry(send, max_attempts=self.max_attempts)

    def download(
        self,
        url: str,
        destination: Path,
        *,
        progress_callback: Optional[Callable[[int], None]] = None,
        chunk_size: int = 1 << 20,
    ) -> int:
        """Baixa em fluxo para ``destination``, passando por um ``.part``."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_name(destination.name + ".part")

        def send() -> int:
            written = 0
            expected: Optional[int] = None
            request = Request(url, headers={"User-Agent": self.USER_AGENT})
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response, open(
                    partial, "wb"
                ) as sink:
                    length = response.headers.get("Content-Length")
                    expected = int(length) if length and length.isdigit() else None
                    for block in iter(lambda: response.read(chunk_size), b""):
                        sink.write(block)
                        written += len(block)
                        if progress_callback is not None:
                            progress_callback(written)
            except HTTPError as exc:
                raise self._http_error(exc, url) from exc
            except URLError as exc:
                raise self._url_error(exc, url) from exc
            except TimeoutError as exc:
                raise HttpFileClientError(
                    f"Timed out downloading '{url}' after {self.timeout_seconds} seconds.",
                    category="timeout",
                    retryable=True,
                    hint="Arquivos grandes (o zip do Vigitel tem 87 MB); aumente o timeout.",
                ) from exc
            except (OSError, http.client.HTTPException) as exc:
                error = transport_error(exc, url, self.timeout_seconds)
                if error is None:
                    raise
                raise error from exc
            if expected is not None and written < expected:
                raise HttpFileClientError(
                    f"Download of '{url}' was truncated: {written} of {expected} bytes.",
                    category="incomplete",
                    retryable=True,
                    hint="O servidor encerrou a conexão antes do fim; tente de novo.",
                )
            if _url_is_zip(url) and not zipfile.is_zipfile(partial):
                raise HttpFileClientError(
                    f"'{url}' should be a zip but the {written} bytes received are not a valid "
                    "zip archive (truncated or not a zip).",
                    category="incomplete",
                    retryable=True,
                    hint="Baixe de novo; se persistir, confira a URL no portal de origem.",
                )
            return written

        try:
            written = request_with_retry(send, max_attempts=self.max_attempts)
        except BaseException:
            # BaseException: o cancelamento do job também limpa o .part.
            partial.unlink(missing_ok=True)
            raise
        partial.replace(destination)
        return written

    @staticmethod
    def _http_error(exc: HTTPError, url: str) -> HttpFileClientError:
        category, retryable = classify_http_status(exc.code)
        return HttpFileClientError(
            f"Request failed ({exc.code}) for '{url}'.",
            category=category,
            retryable=retryable,
            hint="Confira se a URL do arquivo ainda existe no portal de origem.",
        )

    @staticmethod
    def _url_error(exc: URLError, url: str) -> HttpFileClientError:
        category = "timeout" if is_timeout_reason(exc.reason) else "connectivity"
        return HttpFileClientError(
            f"Could not reach '{url}': {exc.reason}",
            category=category,
            retryable=True,
            hint="Verifique acesso à internet, DNS e regras de proxy.",
        )


@dataclass(frozen=True)
class HttpResource:
    """Um arquivo remoto. ``code`` nomeia a saída quando a fonte tem vários."""

    code: str
    url: str
    title: str = ""


@dataclass(frozen=True)
class HttpFile:
    key: str
    title: str
    description: str
    resources: Tuple[HttpResource, ...]
    separator: str = ","
    # Membro do zip a ler; ``None`` aceita só um zip de membro único.
    member: Optional[str] = None
    # Alternativa a ``member`` quando o nome varia (INEP): regex, sem distinguir caixa,
    # aplicada ao caminho do membro; deve casar exatamente um.
    member_pattern: Optional[str] = None
    # ``auto`` decide pelo conteúdo: BOM ou UTF-8 válido, senão cp1252.
    encoding: str = "auto"
    # Parâmetro que escolhe um subconjunto de ``resources`` pelo ``code``:
    # ``indicadores`` (código exato) ou ``periodo`` (``code`` = ``AAAA`` ou
    # ``AAAA_MM``, filtrado por ``anos`` e ``meses``).
    selector: Optional[str] = None


_FARMACIA_BASE = "https://demas-dados-abertos.s3.amazonaws.com/csv/"
# Títulos do dataset mgdi-programa-farmacia-popular-do-brasil, raspados em 2026-10-13.
_FARMACIA = (
    ("atfpbcop", "Pessoas atendidas pelo PFPB na modalidade copagamento"),
    ("pfpbben", "Pessoas atendidas pelo PFPB"),
    ("pfpbbfam", "Pessoas atendidas pelo PFPB que são beneficiárias do Programa Bolsa Família"),
    (
        "pfpbbfcop",
        "Pessoas atendidas pelo PFPB com medicamentos e insumos de copagamento, "
        "beneficiárias do Bolsa Família",
    ),
    (
        "pfpbbfgrat",
        "Pessoas atendidas pelo PFPB com medicamentos gratuitos que são beneficiárias "
        "do Bolsa Família",
    ),
    ("pfpbdm", "Pessoas atendidas pelo PFPB com a aquisição de absorventes higiênicos"),
    ("pfpbdma", "Pessoas que foram atendidas pelo PFPB com a aquisição de absorventes higiênicos"),
    ("sntpba", "Pessoas atendidas pelo PFPB com medicamentos para asma"),
    ("sntpbcon", "Pessoas atendidas pelo PFPB com medicamentos para contracepção"),
    ("sntpbd", "Pessoas atendidas pelo PFPB com medicamentos para diabetes"),
    ("sntpbh", "Pessoas atendidas pelo PFPB com medicamentos para hipertensão"),
    ("sntpbih", "Pessoas atendidas pelo PFPB na modalidade gratuidade"),
    ("sntpbos", "Pessoas atendidas pelo PFPB com medicamentos para osteoporose"),
    ("sntpdhc", "Pessoas atendidas pelo PFPB com os medicamentos para hipertensão e diabetes"),
)
FARMACIA_INDICADORES: Tuple[str, ...] = tuple(code for code, _ in _FARMACIA)

_MGDI_BASE = _FARMACIA_BASE
# Títulos dos conjuntos mgdi-* de dadosabertos.saude.gov.br, raspados em 2026-10-13.
# Todos os CSV têm o esquema da Farmácia Popular (``co_ano`` ou ``co_anomes``,
# ``co_ibge``, ``vl_indicador_calculado_*``, ``dt_competencia``...).
_SAMU = (
    ('samuaer', 'Número de aeromédicos'),
    ('samuemb', 'Número de embarcações'),
    ('samumoto', 'Número de motolâncias'),
    ('samunaa', 'Número de ambulâncias avançadas'),
    ('samunaab', 'Número de ambulâncias avançadas e básicas'),
    ('samunab', 'Número de ambulâncias básicas'),
    ('samupc', 'População coberta SAMU'),
    ('samuppc', 'Percentual da população coberta SAMU'),
    ('samuqc', 'Número de centrais de regulação'),
    ('samuumst', 'Unidades móveis'),
    ('samuvrf', 'Recursos financeiros transferidos'),
)

_UPA = (
    ('upa', 'Total de UPA em funcionamento'),
    ('upacrem', 'Total de UPA em funcionamento / Construídas com recursos de estados e municípios'),
    ('upacrm', 'Total de UPA em funcionamento / Construídas com recursos do MS'),
    ('upafh', 'Total de UPA em funcionamento habilitada'),
    ('upafnh', 'Total de UPA em funcionamento não habilitada'),
    ('upavcm', 'Valor de custeio mensal da UPA'),
)

_RAPS = (
    ('rapscapadh', 'Centros de Atenção Psicossocial Álcool e Drogas (CAPS AD) habilitados'),
    ('rapscapi', 'Centros de Atenção Psicossocial (CAPS) I habilitados'),
    ('rapscapii', 'Centros de Atenção Psicossocial (CAPS) II habilitados'),
    ('rapscapiii', 'Centros de Atenção Psicossocial (CAPS) III habilitados'),
    ('rapscapijh', 'Centros de Atenção Psicossocial Infanto-juvenil (CAPSi) habilitados'),
    ('rapscapst', 'Quantidade total de Centros de Atenção Psicossocial habilitados'),
    ('rapslphg', 'Leitos de Psiquiatria em Hospital Geral'),
    ('rapslphg2', 'Leitos de psiquiatria em Hospital Psiquiátrico'),
    ('rapsnlee', 'Leitos de saúde mental nas enfermarias especializadas em Hospital Geral'),
    ('rapsnuaai', 'Unidades de Acolhimento (UA) Adulto habilitadas'),
    ('rapsnuaij', 'Unidades de Acolhimento (UA) Infanto-juvenil habilitadas'),
    ('rapsnuch', 'Quantidade de Centros de Atenção Psicossocial Álcool e Drogas (CAPS AD) III habilitados'),
    ('rapssrti', 'Serviço Residencial Terapêutico (SRT) I habilitados'),
    ('rapssrtii', 'Serviço Residencial Terapêutico (SRT) II habilitados'),
)

_EMULTI = (
    ('emultampin', 'Total de eMulti custeadas na APS na modalidade ampliada intermunicipal'),
    ('emultampl', 'Total de eMulti custeadas na APS na modalidade ampliada'),
    ('emultcompl', 'Total de eMulti custeadas na APS na modalidade complementar'),
    ('emultcust', 'Total de eMulti custeadas na APS'),
    ('emultestra', 'Total de eMulti custeadas na APS na modalidade estratégica'),
    ('emulthomol', 'Total de eMulti homologadas na APS'),
    ('emultvlrff', 'Total de incentivo financeiro federal transferido aos municípios com eMulti ativas na APS'),
    ('emultvlrmo', 'Repasse financeiro adicional às eMulti com atendimentos remotos mediados por TICS'),
)

_ACADEMIA = (
    ('pasnpcr', 'Número de polos do Programa Academia da Saúde credenciados'),
    ('pasnpcust', 'Número de polos do Programa Academia da Saúde custeados'),
    ('pasnprofc', 'Número de profissionais que atuam nos polos do Programa Academia da Saúde credenciados'),
    ('pasvlr', 'Valor de repasse financeiro de custeio por polo do Programa Academia da Saúde'),
)

_TELESSAUDE = (
    ('mgdi_ms_2s7', 'Número de teleorientações realizadas na atenção primária'),
    ('mgdi_ms_3pn', 'Número de teleconsultorias realizadas na atenção primária à saúde'),
    ('mgdi_ms_66k', 'Número de telemonitoramentos realizados na atenção primária à saúde no âmbito do SUS'),
    ('mgdi_ms_6vj', 'Número de telediagnósticos emitidos pela Atenção Especializada'),
    ('mgdi_ms_ai6', 'Número de teleconsultorias realizadas na atenção especializada à saúde'),
    ('mgdi_ms_bn9', 'Número de teleinterconsultas realizadas na atenção primária à saúde'),
    ('mgdi_ms_db3', 'Número de teleatendimento realizado na atenção primária'),
    ('mgdi_ms_dv0', 'Número de municípios com procedimento em telessaúde'),
    ('mgdi_ms_exj', 'Número de teletriagens realizadas na atenção especializada à saúde'),
    ('mgdi_ms_fqk', 'Número de teletriagens realizadas na atenção primária à saúde'),
    ('mgdi_ms_g0y', 'Proporção de municípios com procedimentos em telessaúde'),
    ('mgdi_ms_hcm', 'Número de teleconsultas realizadas na atenção primária à saúde'),
    ('mgdi_ms_n15', 'Número de teleorientações realizadas na atenção especializada'),
    ('mgdi_ms_nfr', 'Total de procedimentos de Telessaúde'),
    ('mgdi_ms_vft', 'Número de teleatendimento realizado na atenção especializada'),
    ('mgdi_ms_vmm', 'Número de teleinterconsultas realizadas na Atenção Especializada à Saúde'),
    ('mgdi_ms_w2w', 'Número de teleconsultas realizadas na atenção especializada à saúde'),
    ('mgdi_ms_wd8', 'Número de telemonitoramentos realizados na atenção especializada à saúde no âmbito do SUS'),
    ('mgdi_ms_yf3', 'Número de telediagnósticos emitidos pela atenção primária em saúde'),
)

_SAUDE_BUCAL = (
    ('ceoimp', 'Número de Centros de Especialidades Odontológicas implantado e custeado'),
    ('sbechd', 'Quantidade de equipes de Saúde Bucal com Carga Horária Diferenciada'),
    ('sbesb', 'Número de Equipes de Saúde Bucal (40h + carga horária diferenciada)'),
    ('sbesb40h', 'Número de Equipes de Saúde Bucal 40h'),
    ('sbuomp', 'Número de Unidades Odontológicas Móveis - UOM pagas'),
)

_CKAN_S3 = "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/"
_MESES_PNI = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")
PNI_ANOS: Tuple[int, ...] = tuple(range(2020, 2027))
# O ano corrente entra com os 12 meses: o Ministério publica um mês depois do outro (em
# 2026-10-19 havia jan-set) e um mês ainda não publicado vira aviso (HEAD 404), não erro.
PNI_RECURSOS: Tuple[HttpResource, ...] = tuple(
    HttpResource(
        f"{ano}_{numero:02d}",
        f"{_CKAN_S3}PNI/csv/vacinacao_{mes}_{ano}_csv.zip",
        f"Vacinação - {mes} {ano}",
    )
    for ano in PNI_ANOS
    for numero, mes in enumerate(_MESES_PNI, start=1)
)
SISVAN_ANOS: Tuple[int, ...] = tuple(range(2008, 2024))
SISVAN_RECURSOS: Tuple[HttpResource, ...] = tuple(
    HttpResource(
        str(ano),
        f"{_CKAN_S3}SISVAN/estado_nutricional/sisvan_estado_nutricional_{ano}.zip",
        f"Estado nutricional {ano}",
    )
    for ano in SISVAN_ANOS
)


HTTP_FILES: Dict[str, HttpFile] = {
    item.key: item
    for item in (
        HttpFile(
            "vigitel",
            "Vigitel 2006-2024 (inquérito telefônico, peso rake)",
            "Microdados do Vigitel (SVS/MS) de 2006 a 2024, sem 2022, com o peso de "
            "pós-estratificação. Colunas esparsas por ano.",
            (
                HttpResource(
                    "vigitel",
                    "https://svs.aids.gov.br/daent/cgdnt/vigitel/"
                    "vigitel-2006-2024-peso-rake-csv.zip",
                ),
            ),
            separator=",",
            member="vigitel-2006-2024-peso-rake_slabel.csv",
        ),
        HttpFile(
            "ibama_agrotoxicos_comercializacao",
            "IBAMA Agrotóxicos - Relatórios de comercialização",
            "Vendas semestrais de agrotóxicos por classe de uso e ingrediente ativo, "
            "em toneladas, com uma coluna de vendas por UF.",
            (
                HttpResource(
                    "relatorios_comercializacao_agrotoxicos",
                    "https://stibamadadosabertosprd.blob.core.windows.net/dados-abertos/dados/"
                    "AGROTOXICOS/RelatoriosdeComercializacaodeAgrotoxicos/"
                    "relatorios_comercializacao_agrotoxicos.csv",
                ),
            ),
            separator=";",
        ),
        HttpFile(
            "farmacia_popular_indicadores",
            "Farmácia Popular - Indicadores",
            "Indicadores municipais do Programa Farmácia Popular do Brasil, um CSV por "
            "indicador (competência mensal).",
            tuple(
                HttpResource(code, f"{_FARMACIA_BASE}{code}.csv.zip", title)
                for code, title in _FARMACIA
            ),
            separator=",",
            selector="indicadores",
        ),
        HttpFile(
            "mgdi_samu",
            "MGDI SAMU 192 - Indicadores",
            "Indicadores do Serviço de Atendimento Móvel de Urgência (SAMU 192), um CSV por indicador "
            "(agregado por município, região de saúde, UF e Brasil).",
            tuple(
                HttpResource(code, f"{_MGDI_BASE}{code}.csv.zip", title)
                for code, title in _SAMU
            ),
            separator=",",
            selector="indicadores",
        ),
        HttpFile(
            "mgdi_upa",
            "MGDI UPA 24h - Indicadores",
            "Indicadores das Unidades de Pronto Atendimento (UPA 24h), um CSV por indicador "
            "(agregado por município, região de saúde, UF e Brasil).",
            tuple(
                HttpResource(code, f"{_MGDI_BASE}{code}.csv.zip", title)
                for code, title in _UPA
            ),
            separator=",",
            selector="indicadores",
        ),
        HttpFile(
            "mgdi_raps",
            "MGDI RAPS - Indicadores",
            "Indicadores da Rede de Atenção Psicossocial (CAPS, leitos, residências, serviços), um CSV por indicador "
            "(agregado por município, região de saúde, UF e Brasil).",
            tuple(
                HttpResource(code, f"{_MGDI_BASE}{code}.csv.zip", title)
                for code, title in _RAPS
            ),
            separator=",",
            selector="indicadores",
        ),
        HttpFile(
            "mgdi_emulti",
            "MGDI eMulti - Indicadores",
            "Indicadores das equipes multiprofissionais na atenção primária (eMulti), um CSV por indicador "
            "(agregado por município, região de saúde, UF e Brasil).",
            tuple(
                HttpResource(code, f"{_MGDI_BASE}{code}.csv.zip", title)
                for code, title in _EMULTI
            ),
            separator=",",
            selector="indicadores",
        ),
        HttpFile(
            "mgdi_academia_saude",
            "MGDI Academia da Saúde - Indicadores",
            "Indicadores do Programa Academia da Saúde, um CSV por indicador "
            "(agregado por município, região de saúde, UF e Brasil).",
            tuple(
                HttpResource(code, f"{_MGDI_BASE}{code}.csv.zip", title)
                for code, title in _ACADEMIA
            ),
            separator=",",
            selector="indicadores",
        ),
        HttpFile(
            "mgdi_telessaude",
            "MGDI Telessaúde - Indicadores",
            "Indicadores do Telessaúde, um CSV por indicador "
            "(agregado por município, região de saúde, UF e Brasil).",
            tuple(
                HttpResource(code, f"{_MGDI_BASE}{code}.csv.zip", title)
                for code, title in _TELESSAUDE
            ),
            separator=",",
            selector="indicadores",
        ),
        HttpFile(
            "mgdi_saude_bucal",
            "MGDI Saúde bucal - Indicadores",
            "Indicadores da Rede de Atenção em Saúde Bucal (CEO, equipes, UOM), um CSV por indicador "
            "(agregado por município, região de saúde, UF e Brasil).",
            tuple(
                HttpResource(code, f"{_MGDI_BASE}{code}.csv.zip", title)
                for code, title in _SAUDE_BUCAL
            ),
            separator=",",
            selector="indicadores",
        ),
        # Verificado ao vivo em 2026-10-19 (HEAD e primeiros 3 MB por Range): dataset
        # ``doses-aplicadas-pelo-programa-de-nacional-de-imunizacoes-pni-AAAA``. Os 54
        # campos vêm em snake_case curto (``co_documento``, ``dt_vacina``...), em
        # latin-1 com ``;``. A API devolve nomes longos (``codigo_documento``), então
        # os dois não têm as mesmas colunas.
        HttpFile(
            "pni_doses_aplicadas_arquivos",
            "PNI - Doses aplicadas (arquivos mensais)",
            "Microdados de doses aplicadas do PNI, um CSV por mês de 2020 a 2026, publicados "
            "como arquivo no bucket do portal. Alternativa à API DEMAS, que falha acima de "
            "~1 milhão de offset por ano.",
            PNI_RECURSOS,
            separator=";",
            encoding="auto",
            selector="periodo",
        ),
        # Verificado ao vivo em 2026-10-19: dataset ``sisvan-estado-nutricional``, um zip
        # por ano de 2008 a 2023, 35 colunas, ``;`` e aspas, latin-1.
        HttpFile(
            "sisvan_estado_nutricional_arquivos",
            "SISVAN - Estado nutricional (arquivos anuais)",
            "Acompanhamento do estado nutricional do SISVAN, um CSV por ano de 2008 a 2023, "
            "publicado como arquivo no bucket do portal. Alternativa à API DEMAS, que passa "
            "de 67 milhões de linhas e quebra em offset alto.",
            SISVAN_RECURSOS,
            separator=";",
            encoding="auto",
            selector="periodo",
        ),
    )
}


def _normalize_format(value: Optional[str]) -> Optional[str]:
    if value is None or not str(value).strip():
        return None
    normalized = str(value).strip().lower()
    if normalized not in _FORMATS:
        raise ValueError(f"Unsupported output_format '{value}'. Use one of {_FORMATS}.")
    return normalized


class _ZipMember:
    """Membro de zip que fecha o arquivo junto."""

    def __init__(self, archive: zipfile.ZipFile, name: str) -> None:
        self._archive = archive
        self._stream = archive.open(name)

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)

    def __enter__(self) -> "_ZipMember":
        return self

    def __exit__(self, *exc: object) -> None:
        self._stream.close()
        self._archive.close()


def _open_member(raw: Path, spec: HttpFile):
    """Abre os bytes do dado: o arquivo em si ou o membro do zip.

    Quando o recurso é esperado como zip (nome ``.zip`` ou spec com ``member`` ou
    ``member_pattern``), um arquivo que não é zip válido falha aqui, em vez de
    seguir como CSV cru (um zip truncado viraria lixo).
    """
    if not zipfile.is_zipfile(raw):
        if raw.name.lower().endswith(".zip") or spec.member or spec.member_pattern:
            raise ValueError(
                f"{raw.name} should be a zip archive but is not a valid one "
                "(truncated download?); delete it and download again."
            )
        return open(raw, "rb")
    archive = zipfile.ZipFile(raw)
    names = [n for n in archive.namelist() if not n.endswith("/")]
    if spec.member_pattern is not None:
        found = [n for n in names if re.search(spec.member_pattern, n, re.IGNORECASE)]
        if len(found) != 1:
            archive.close()
            raise ValueError(
                f"Pattern '{spec.member_pattern}' matched {len(found)} members in "
                f"{raw.name}: {found}"
            )
        chosen = found[0]
    elif spec.member is not None:
        if spec.member not in names:
            archive.close()
            raise ValueError(f"Member '{spec.member}' not found in {raw.name}: {names}")
        chosen = spec.member
    elif len(names) == 1:
        chosen = names[0]
    else:
        archive.close()
        raise ValueError(f"{raw.name} has {len(names)} members; expected exactly one.")
    return _ZipMember(archive, chosen)


def transcode_lines(source, sink, stats: Optional[Dict[str, int]] = None) -> str:
    """Copia ``source`` (bytes) para ``sink`` (texto) decidindo a codificação linha a linha.

    Cada linha é lida como UTF-8 e, se não for UTF-8 válido, como cp1252.
    Arquivos do governo misturam as duas: o Vigitel 2006-2024 é cp1252 com
    algumas linhas em UTF-8, e o primeiro trecho ASCII (71 MB) não deixa
    detectar pelo começo do arquivo. Linha a linha nenhuma das duas partes se
    perde.

    Em ``stats``: ``replaced`` conta os bytes que o cp1252 não define (viram
    U+FFFD), ``origin_fffd`` os U+FFFD que já vinham escritos na origem, e
    ``cp1252_lines``/``utf8_lines`` quantas linhas não ASCII caíram em cada
    codificação. Devolve o rótulo da codificação usada.
    """
    replaced = origin = cp_lines = utf_lines = 0
    pending = b""
    first = True

    def emit(line: bytes) -> None:
        nonlocal replaced, origin, cp_lines, utf_lines
        if line.isascii():
            sink.write(line.decode("ascii"))
            return
        try:
            text = line.decode("utf-8")
            utf_lines += 1
            origin += text.count("�")
        except UnicodeDecodeError:
            text = line.decode("cp1252", errors="replace")
            cp_lines += 1
            replaced += text.count("�")
        sink.write(text)

    for block in iter(lambda: source.read(1 << 20), b""):
        if first:
            block = block.removeprefix(codecs.BOM_UTF8)
            first = False
        block = pending + block
        cut = block.rfind(b"\n") + 1
        pending = block[cut:]
        if cut:
            for line in block[:cut].splitlines(keepends=True):
                emit(line)
    if pending:
        emit(pending)
    if stats is not None:
        stats.update(
            replaced=replaced, origin_fffd=origin, cp1252_lines=cp_lines, utf8_lines=utf_lines
        )
    if cp_lines and utf_lines:
        return f"utf-8 e cp1252 por linha ({utf_lines} e {cp_lines} linhas)"
    return "cp1252" if cp_lines else "utf-8"


def _to_utf8(
    raw: Path, spec: HttpFile, target: Path, stats: Optional[Dict[str, int]] = None
) -> str:
    """Grava ``raw`` (ou seu membro do zip) em UTF-8, em blocos, sem BOM.

    Com ``encoding="auto"`` a codificação é decidida linha a linha
    (:func:`transcode_lines`). Com codificação declarada, ``stats["replaced"]``
    recebe quantos U+FFFD a conversão produziu (bytes que ela não define).
    """
    with _open_member(raw, spec) as source, open(target, "w", encoding="utf-8", newline="") as sink:
        if spec.encoding == "auto":
            return transcode_lines(source, sink, stats)
        replaced = 0
        decoder = codecs.getincrementaldecoder(spec.encoding)(errors="replace")
        for block in iter(lambda: source.read(1 << 20), b""):
            text = decoder.decode(block)
            replaced += text.count("�")
            sink.write(text)
        text = decoder.decode(b"", final=True)
        replaced += text.count("�")
        sink.write(text)
    if stats is not None:
        stats["replaced"] = replaced
    return spec.encoding


def _replacement_warning(label: str, replaced: int, encoding: str) -> str:
    return (
        f"{label}: {replaced} caracteres inválidos viraram U+FFFD na conversão para UTF-8 "
        f"(codificação {encoding}); confira a codificação do arquivo de origem."
    )


def encoding_warnings(label: str, stats: Dict[str, int], encoding: str) -> List[str]:
    """Avisos da conversão: bytes perdidos por nós e U+FFFD que já vinham da origem."""
    found = []
    if stats.get("replaced"):
        found.append(_replacement_warning(label, stats["replaced"], encoding))
    if stats.get("origin_fffd"):
        found.append(
            f"{label}: o arquivo de origem já traz {stats['origin_fffd']} caracteres "
            "U+FFFD (acentuação perdida na publicação, não na conversão)."
        )
    return found


def _sink_atomic(frame, dest: Path, fmt: str, table: str, label: str) -> Path:
    """Grava o frame em ``<dest>.part`` e só então troca para ``dest`` (``os.replace``).

    Falha no meio apaga o ``.part``; ``dest`` nunca fica parcial.
    """
    partial = dest.with_name(dest.name + ".part")
    try:
        if fmt == "csv":
            frame.sink_csv(partial)
        elif fmt == "parquet":
            frame.sink_parquet(partial)
        else:
            if write_sqlite(frame, db_path=partial, table=table) is None:
                raise ValueError(f"{label} has no rows to export to sqlite.")
        os.replace(partial, dest)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    return dest


class HttpFileDataSource(DataSource):
    """Fonte de arquivo(s) de URL fixa. Subclasses fixam ``DATASET`` (ver ``datasource_for``)."""

    DATASET: str = ""
    DEFAULT_TIMEOUT = HttpFileClient.DEFAULT_TIMEOUT

    def __init__(
        self,
        output_path: Optional[str] = None,
        *,
        dataset: Optional[str] = None,
        client: Optional[HttpFileClient] = None,
    ) -> None:
        key = dataset or self.DATASET
        if key not in HTTP_FILES:
            raise ValueError(f"Unknown file dataset '{key}'. Known: {sorted(HTTP_FILES)}")
        super().__init__(name=key, output_path=output_path)
        self.spec = HTTP_FILES[key]
        self._client = client

    def load_dataframe(self, *args, **kwargs) -> pl.DataFrame:  # pragma: no cover
        raise NotImplementedError("Read the exported file with polars.scan_*.")

    def _select_periodo(
        self, anos: Optional[Sequence[object]], meses: Optional[Sequence[object]]
    ) -> List[HttpResource]:
        """Recorta por ano (obrigatório) e, quando o código tem mês, por mês."""
        if not anos:
            raise ValueError(
                f"'{self.name}' tem arquivos de vários GB por período; informe 'anos' "
                "(e, se quiser, 'meses') para escolher o que baixar."
            )
        try:
            wanted_years = {str(int(a)) for a in anos}
            wanted_months = {f"{int(m):02d}" for m in meses or ()}
        except (TypeError, ValueError) as exc:
            raise ValueError(f"'anos' e 'meses' devem ser números: {exc}") from exc
        known_years = {r.code.split("_")[0] for r in self.spec.resources}
        unknown = sorted(wanted_years - known_years)
        if unknown:
            raise ValueError(f"Unknown anos {unknown}. Known: {sorted(known_years)}")
        picked = []
        for resource in self.spec.resources:
            year, _, month = resource.code.partition("_")
            if year in wanted_years and (not wanted_months or not month or month in wanted_months):
                picked.append(resource)
        return picked

    def _select(
        self,
        indicadores: Optional[Sequence[str]],
        anos: Optional[Sequence[object]] = None,
        meses: Optional[Sequence[object]] = None,
    ) -> List[HttpResource]:
        if self.spec.selector == "periodo":
            return self._select_periodo(anos, meses)
        if not indicadores or not self.spec.selector:
            return list(self.spec.resources)
        wanted = [str(c).strip().lower() for c in indicadores]
        by_code = {r.code: r for r in self.spec.resources}
        unknown = [c for c in wanted if c not in by_code]
        if unknown:
            raise ValueError(f"Unknown indicadores {unknown}. Known: {sorted(by_code)}")
        return [by_code[c] for c in dict.fromkeys(wanted)]

    def download(
        self,
        *,
        output_format: Optional[str] = None,
        keep_raw: bool = False,
        output_dir: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        indicadores: Optional[Sequence[str]] = None,
        anos: Optional[Sequence[object]] = None,
        meses: Optional[Sequence[object]] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Dict[str, object]:
        requested = _normalize_format(output_format)
        base_dir = Path(output_dir) if output_dir else self.output_path
        base_dir.mkdir(parents=True, exist_ok=True)
        client = self._client or HttpFileClient(timeout_seconds=timeout)
        resources = self._select(indicadores, anos, meses)
        # ``multi`` nomeia os arquivos (a fonte tem vários recursos); ``isolate`` decide se
        # a falha de um recurso vira aviso: com um só recurso pedido, a causa real sobe.
        multi = len(self.spec.resources) > 1
        total = len(resources)
        isolate = total > 1

        def emit(event: Dict[str, object]) -> None:
            if progress_callback is not None:
                progress_callback({"source": self.name, "documents_total": total, **event})

        emit({"event": "download_start"})
        exported: List[str] = []
        warnings: List[str] = []
        downloaded = skipped_count = failed = 0
        remotes: List[RemoteFile] = []

        for index, resource in enumerate(resources, start=1):
            suffix = Path(resource.url).name
            raw_path = base_dir / (f"{self.name}__{suffix}" if multi else suffix)
            try:
                remote = client.head(resource.url)
                remotes.append(remote)
                skipped = (
                    raw_path.exists()
                    and remote.size is not None
                    and raw_path.stat().st_size == remote.size
                )
                if not skipped:

                    def on_bytes(written: int, _p=raw_path, _i=index, _r=remote) -> None:
                        emit({
                            "event": "file_progress", "document_index": _i,
                            "file_path": str(_p), "file_bytes_downloaded": written,
                            "file_total_bytes": _r.size or 0,
                        })

                    client.download(resource.url, raw_path, progress_callback=on_bytes)
                emit({
                    "event": "file_skipped" if skipped else "file_completed",
                    "document_index": index, "file_path": str(raw_path),
                })
                skipped_count += 1 if skipped else 0
                downloaded += 0 if skipped else 1
                if requested:
                    dest = self._export(raw_path, base_dir, requested, resource, multi, warnings)
                    exported.append(str(dest))
                    if not keep_raw:
                        raw_path.unlink(missing_ok=True)
            except (ApiClientError, ValueError, zipfile.BadZipFile) as exc:
                if not isolate:
                    raise
                failed += 1
                warnings.append(f"{resource.code}: {exc}")

        if not requested and not keep_raw:
            warnings.append(
                "Raw file kept as published; set output_format to also export UTF-8 "
                "csv, parquet or sqlite."
            )
        first = remotes[0] if remotes else None
        return {
            "documents_found": total,
            "downloaded_count": downloaded,
            "skipped_count": skipped_count,
            "failed_count": failed,
            "output_dir": str(base_dir),
            "source_url": first.url if first else None,
            "source_size": first.size if first else None,
            "source_last_modified": first.last_modified if first else None,
            "source_etag": first.etag if first else None,
            "output_format": requested,
            "exported_files": exported,
            "keep_raw": keep_raw,
            "export_warning": " ".join(warnings) or None,
        }

    def _export(
        self,
        raw_path: Path,
        base_dir: Path,
        fmt: str,
        resource: HttpResource,
        multi: bool,
        warnings: Optional[List[str]] = None,
    ) -> Path:
        name = f"{self.name}_{resource.code}" if multi else self.name
        utf8 = base_dir / f"{name}.utf8.tmp.csv"
        try:
            stats: Dict[str, int] = {}
            encoding = _to_utf8(raw_path, self.spec, utf8, stats)
            if warnings is not None:
                warnings.extend(encoding_warnings(raw_path.name, stats, encoding))
            frame = pl.scan_csv(
                utf8, separator=self.spec.separator, infer_schema=False, quote_char='"'
            )
            names = frame.collect_schema().names()
            stripped = {n: n.strip() for n in names if n != n.strip()}
            if stripped:
                frame = frame.rename(stripped)
            suffix = {"csv": ".csv", "parquet": ".parquet"}.get(fmt, ".sqlite")
            return _sink_atomic(frame, base_dir / f"{name}{suffix}", fmt, name, raw_path.name)
        finally:
            utf8.unlink(missing_ok=True)


def datasource_for(key: str) -> type:
    """Subclasse com ``DATASET`` fixo, que o ``ApiDownloadSource`` instancia só com ``output_path``."""
    spec = HTTP_FILES[key]
    class_name = "".join(part.title() for part in key.split("_")) + "DataSource"
    return type(class_name, (HttpFileDataSource,), {"DATASET": spec.key})
