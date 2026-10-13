"""Microdados de pesquisas amostrais do IBGE: PNS, PeNSE e POF.

Os arquivos ficam em ``https://ftp.ibge.gov.br/``, um zip por edição (ou por
amostra), sem API. Cada fonte cobre uma pesquisa, e o ano escolhido é a
EDIÇÃO: ano sem edição não gera requisição alguma.

Dois formatos convivem:

- largura fixa (PNS 2013 e 2019, POF 2017-2018, PeNSE 2012), lida pelo
  programa SAS de leitura que o próprio IBGE publica (``fixed_width``);
- CSV (PeNSE 2015, 2019 e 2024), regravado em UTF-8.

A saída é um arquivo por tabela, tudo como texto, com o nome de coluna do
leiaute publicado. Pesos e códigos não são convertidos: interpretar é papel
da camada prata.

Fica de fora a PeNSE 2009: o leiaute dela só existe em planilha XLS, e o
projeto não tem leitor de Excel como dependência.

Verificado ao vivo em 2026-10-13: listagem dos diretórios e dos membros de
cada zip (diretório central lido por Range), programas SAS da PNS 2013 e 2019
(1000 e 1088 variáveis, LRECL 1484 e 1548 igual ao fim da última variável) e
da POF (16 blocos, 550 variáveis), primeiras 5161 linhas da PNS 2019 (1548
bytes cada, só ASCII).
"""

from __future__ import annotations

import codecs
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote
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
from guaraci.ibge.fixed_width import (
    SasBlock,
    parse_sas_input,
    scan_fixed_width,
    transcode_to_utf8,
)

__all__ = [
    "Tabela",
    "Edicao",
    "Pesquisa",
    "PESQUISAS",
    "IbgeFtpClient",
    "IbgeFtpError",
    "IbgeMicrodadosDataSource",
    "datasource_for",
]

ProgressCallback = Callable[[Dict[str, object]], None]
_FORMATS = ("csv", "parquet", "sqlite")


@dataclass(frozen=True)
class RemoteFile:
    url: str
    size: Optional[int]
    last_modified: Optional[str]


class IbgeFtpError(ApiClientError):
    """Falha ao consultar ou baixar um arquivo de ftp.ibge.gov.br."""


class IbgeFtpClient:
    """HEAD e download em fluxo de arquivos do servidor de arquivos do IBGE."""

    DEFAULT_BASE_URL = "https://ftp.ibge.gov.br/"
    DEFAULT_TIMEOUT = 600
    USER_AGENT = f"guaraci/{__version__}"

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        timeout_seconds: int = DEFAULT_TIMEOUT,
        max_attempts: int = 3,
    ) -> None:
        selected = (base_url or self.DEFAULT_BASE_URL).strip()
        self.base_url = selected if selected.endswith("/") else selected + "/"
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.max_attempts = max_attempts

    def url_for(self, path: str) -> str:
        return self.base_url + quote(path, safe="/")

    def head(self, path: str) -> RemoteFile:
        url = self.url_for(path)

        def send() -> RemoteFile:
            request = Request(url, method="HEAD", headers={"User-Agent": self.USER_AGENT})
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    length = response.headers.get("Content-Length")
                    return RemoteFile(
                        url=url,
                        size=int(length) if length and length.isdigit() else None,
                        last_modified=response.headers.get("Last-Modified"),
                    )
            except HTTPError as exc:
                raise self._http_error(exc, url) from exc
            except URLError as exc:
                raise self._url_error(exc, url) from exc

        return request_with_retry(send, max_attempts=self.max_attempts)

    def download(
        self,
        path: str,
        destination: Path,
        *,
        progress_callback: Optional[Callable[[int], None]] = None,
        chunk_size: int = 1 << 20,
    ) -> int:
        """Baixa em fluxo para ``destination``, passando por um ``.part``."""
        url = self.url_for(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_name(destination.name + ".part")

        def send() -> int:
            written = 0
            request = Request(url, headers={"User-Agent": self.USER_AGENT})
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response, open(
                    partial, "wb"
                ) as sink:
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
                raise IbgeFtpError(
                    f"Timed out downloading '{url}' after {self.timeout_seconds} seconds.",
                    category="timeout",
                    retryable=True,
                    hint="Os zips de microdados passam de 100 MB; aumente o timeout.",
                ) from exc
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
    def _http_error(exc: HTTPError, url: str) -> IbgeFtpError:
        category, retryable = classify_http_status(exc.code)
        return IbgeFtpError(
            f"IBGE request failed ({exc.code}) for '{url}'.",
            category=category,
            retryable=retryable,
            hint="Confira se o arquivo ainda existe em https://ftp.ibge.gov.br/.",
        )

    @staticmethod
    def _url_error(exc: URLError, url: str) -> IbgeFtpError:
        category = "timeout" if is_timeout_reason(exc.reason) else "connectivity"
        return IbgeFtpError(
            f"Could not reach '{url}': {exc.reason}",
            category=category,
            retryable=True,
            hint="Verifique acesso à internet, DNS e regras de proxy.",
        )


@dataclass(frozen=True)
class Tabela:
    """Uma tabela de uma edição.

    ``membro`` é o nome do arquivo dentro do zip ``arquivo``, comparado sem a
    pasta e sem caixa: na POF o INFILE diz ``domicilio.txt`` e o zip traz
    ``DOMICILIO.txt``; na PeNSE 2012 a pasta vem com nome em cp437.
    ``layout`` é ``(zip, programa SAS)`` para largura fixa; ``None`` é CSV.
    """

    nome: str
    arquivo: str
    membro: str
    layout: Optional[Tuple[str, str]] = None
    separador: str = ","


@dataclass(frozen=True)
class Edicao:
    ano: int
    rotulo: str
    arquivos: Dict[str, str]  # apelido -> caminho a partir da raiz do FTP
    tabelas: Tuple[Tabela, ...]


@dataclass(frozen=True)
class Pesquisa:
    key: str
    title: str
    description: str
    edicoes: Dict[int, Edicao]


def _pof_tabelas() -> Tuple[Tabela, ...]:
    layout = ("leitura", "Leitura dos Microdados - SAS.txt")
    pares = (
        ("domicilio", "DOMICILIO.txt"),
        ("morador", "MORADOR.txt"),
        ("morador_qualidade_vida", "MORADOR_QUALI_VIDA.txt"),
        ("aluguel_estimado", "ALUGUEL_ESTIMADO.txt"),
        ("despesa_coletiva", "DESPESA_COLETIVA.txt"),
        ("servico_nao_monetario_pof2", "SERVICO_NAO_MONETARIO_POF2.txt"),
        ("inventario_bens_duraveis", "INVENTARIO.txt"),
        ("caderneta_coletiva", "CADERNETA_COLETIVA.txt"),
        ("despesa_individual", "DESPESA_INDIVIDUAL.txt"),
        ("servico_nao_monetario_pof4", "SERVICO_NAO_MONETARIO_POF4.txt"),
        ("restricao_produtos_servicos_saude", "RESTRICAO_PRODUTOS_SERVICOS_SAUDE.txt"),
        ("rendimento_trabalho", "RENDIMENTO_TRABALHO.txt"),
        ("outros_rendimentos", "OUTROS_RENDIMENTOS.txt"),
        ("condicoes_vida", "CONDICOES_VIDA.txt"),
        ("caracteristicas_dieta", "CARACTERISTICAS_DIETA.txt"),
        ("consumo_alimentar", "CONSUMO_ALIMENTAR.txt"),
    )
    return tuple(Tabela(nome, "dados", membro, layout=layout) for nome, membro in pares)


def _pense_2015_tabelas() -> Tuple[Tabela, ...]:
    tabelas = []
    for amostra in ("1", "2"):
        for parte in ("aluno", "alunoescola", "escola"):
            tabelas.append(
                Tabela(
                    f"amostra{amostra}_{parte}",
                    f"amostra{amostra}",
                    f"PENSE_AMOSTRA{amostra}_{parte.upper()}.CSV",
                    separador=";",
                )
            )
    return tuple(tabelas)


_POF = "Orcamentos_Familiares/Pesquisa_de_Orcamentos_Familiares_2017_2018/Microdados/"
_PENSE_2012_LEITURA = "dados"

PESQUISAS: Dict[str, Pesquisa] = {
    item.key: item
    for item in (
        Pesquisa(
            "ibge_pns",
            "IBGE PNS - Pesquisa Nacional de Saúde (microdados)",
            "Microdados da PNS: moradores e morador selecionado, com estado de "
            "saúde, doenças crônicas, estilo de vida e acesso a serviços.",
            {
                2013: Edicao(
                    2013,
                    "2013",
                    {
                        "dados": "PNS/2013/Microdados/Dados/PNS_2013.zip",
                        "doc": "PNS/2013/Microdados/Documentacao/Dicionario_e_input_20200930.zip",
                    },
                    (Tabela("pns", "dados", "PNS_2013.txt", layout=("doc", "input_PNS_2013.sas")),),
                ),
                2019: Edicao(
                    2019,
                    "2019",
                    {
                        "dados": "PNS/2019/Microdados/Dados/PNS_2019_20220525.zip",
                        "doc": "PNS/2019/Microdados/Documentacao/Dicionario_e_input_20220530.zip",
                    },
                    (Tabela("pns", "dados", "PNS_2019.txt", layout=("doc", "input_PNS_2019.sas")),),
                ),
            },
        ),
        Pesquisa(
            "ibge_pof",
            "IBGE POF - Pesquisa de Orçamentos Familiares (microdados)",
            "Microdados da POF 2017-2018 em 16 tabelas: domicílio, moradores, "
            "despesas, rendimentos, consumo alimentar e condições de vida.",
            {
                2017: Edicao(
                    2017,
                    "2017-2018",
                    {
                        "dados": _POF + "Dados_20230713.zip",
                        "leitura": _POF + "Programas_de_Leitura_20230713.zip",
                    },
                    _pof_tabelas(),
                ),
            },
        ),
        Pesquisa(
            "ibge_pense",
            "IBGE PeNSE - Pesquisa Nacional de Saúde do Escolar (microdados)",
            "Microdados da PeNSE: questionário do estudante e da escola, com "
            "alimentação, atividade física, tabagismo, álcool e violência.",
            {
                2012: Edicao(
                    2012,
                    "2012",
                    {"dados": "pense/2012/microdados/PENSE_2012_microdados.zip"},
                    (
                        Tabela(
                            "estudantes",
                            "dados",
                            "pense2012Estudantes.txt",
                            layout=(_PENSE_2012_LEITURA, "Input SAS estudantes.sas"),
                        ),
                        Tabela(
                            "escolas",
                            "dados",
                            "pense2012Escolas.txt",
                            layout=(_PENSE_2012_LEITURA, "Input SAS escolas.sas"),
                        ),
                        Tabela(
                            "estudantes_escolas",
                            "dados",
                            "pense2012EstudantesEscolas.txt",
                            layout=(_PENSE_2012_LEITURA, "Input SAS estudantes e escolas.sas"),
                        ),
                    ),
                ),
                2015: Edicao(
                    2015,
                    "2015",
                    {
                        "amostra1": "pense/2015/microdados/PeNSE_2015_AMOSTRA1.zip",
                        "amostra2": "pense/2015/microdados/PeNSE_2015_AMOSTRA2.zip",
                    },
                    _pense_2015_tabelas(),
                ),
                2019: Edicao(
                    2019,
                    "2019",
                    {"dados": "pense/2019/microdados/Dados.zip"},
                    (Tabela("microdados", "dados", "PENSE2019_MICRODADOS.csv"),),
                ),
                2024: Edicao(
                    2024,
                    "2024",
                    {"dados": "pense/2024/microdados/Dados.zip"},
                    (Tabela("microdados", "dados", "PENSE2024_MICRODADOS.csv"),),
                ),
            },
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


def _normalize_tabelas(value: object) -> Optional[List[str]]:
    if value is None:
        return None
    if isinstance(value, str):
        items = value.split(",")
    elif isinstance(value, Iterable):
        items = [str(v) for v in value]
    else:
        raise ValueError(f"tabelas must be a list of names, got {value!r}.")
    names = [item.strip().lower() for item in items if str(item).strip()]
    return names or None


def _find_member(archive: zipfile.ZipFile, name: str) -> zipfile.ZipInfo:
    wanted = name.casefold()
    for info in archive.infolist():
        if info.is_dir():
            continue
        if info.filename.replace("\\", "/").rsplit("/", 1)[-1].casefold() == wanted:
            return info
    raise ValueError(f"'{name}' not found in {Path(str(archive.filename)).name}.")


def _select_block(blocks: Sequence[SasBlock], tabela: Tabela, programa: str) -> SasBlock:
    membro = tabela.membro.casefold()
    for block in blocks:
        if block.infile and block.infile.casefold() == membro:
            return block
    for block in blocks:
        if block.name.casefold() == tabela.nome.casefold():
            return block
    if len(blocks) == 1:
        return blocks[0]
    raise ValueError(f"{programa}: no INPUT block for {tabela.membro}.")


def _transcode_csv(archive: zipfile.ZipFile, info: zipfile.ZipInfo, target: Path) -> str:
    """Regrava um CSV do zip em UTF-8 e devolve a codificação de origem.

    Tenta UTF-8 estrito primeiro; no primeiro byte inválido recomeça em
    cp1252. Codificação não declarada pelo IBGE: decidir pelo conteúdo é mais
    seguro que fixar uma.
    """
    try:
        with archive.open(info) as source, open(target, "w", encoding="utf-8", newline="") as sink:
            decoder = codecs.getincrementaldecoder("utf-8-sig")(errors="strict")
            for chunk in iter(lambda: source.read(1 << 20), b""):
                sink.write(decoder.decode(chunk))
            sink.write(decoder.decode(b"", final=True))
        return "utf-8"
    except UnicodeDecodeError:
        with archive.open(info) as source:
            transcode_to_utf8(source, target, "cp1252")
        return "cp1252"


class IbgeMicrodadosDataSource(DataSource):
    """Uma pesquisa do IBGE. Subclasses fixam ``DATASET`` (ver ``datasource_for``)."""

    DATASET: str = ""
    DEFAULT_TIMEOUT = IbgeFtpClient.DEFAULT_TIMEOUT

    def __init__(
        self,
        output_path: Optional[str] = None,
        *,
        dataset: Optional[str] = None,
        client: Optional[IbgeFtpClient] = None,
    ) -> None:
        key = dataset or self.DATASET
        if key not in PESQUISAS:
            raise ValueError(f"Unknown IBGE survey '{key}'. Known: {sorted(PESQUISAS)}")
        super().__init__(name=key, output_path=output_path)
        self.spec = PESQUISAS[key]
        self._client = client

    def load_dataframe(self, *args, **kwargs) -> pl.DataFrame:  # pragma: no cover
        raise NotImplementedError(
            "IBGE microdata reach hundreds of MB; read the exported file with polars.scan_*."
        )

    def _plan(
        self, start_year: Optional[int], end_year: Optional[int], tabelas: Optional[List[str]]
    ) -> List[Tuple[Edicao, List[Tabela]]]:
        if start_year is None:
            raise ValueError("start_year is required (survey edition year).")
        first = int(start_year)
        last = int(end_year) if end_year is not None else first
        if last < first:
            raise ValueError(f"end_year ({last}) is before start_year ({first}).")
        edicoes = [e for ano, e in sorted(self.spec.edicoes.items()) if first <= ano <= last]
        if tabelas:
            known = {t.nome for e in edicoes for t in e.tabelas}
            unknown = sorted(set(tabelas) - known)
            if unknown and edicoes:
                raise ValueError(
                    f"Unknown tabelas {unknown} for {self.name} {first}-{last}. "
                    f"Known: {sorted(known)}"
                )
        plan = []
        for edicao in edicoes:
            chosen = [t for t in edicao.tabelas if not tabelas or t.nome in tabelas]
            if chosen:
                plan.append((edicao, chosen))
        return plan

    def download(
        self,
        *,
        start_year: Optional[int] = None,
        end_year: Optional[int] = None,
        tabelas: object = None,
        output_format: Optional[str] = None,
        keep_raw: bool = False,
        output_dir: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        api_base_url: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Dict[str, object]:
        requested = _normalize_format(output_format)
        plan = self._plan(start_year, end_year, _normalize_tabelas(tabelas))
        base_dir = Path(output_dir) if output_dir else self.output_path
        base_dir.mkdir(parents=True, exist_ok=True)
        payload: Dict[str, object] = {
            "documents_found": sum(len(chosen) for _, chosen in plan),
            "downloaded_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "output_dir": str(base_dir),
            "source_url": None,
            "source_urls": [],
            "output_format": requested,
            "exported_files": [],
            "keep_raw": keep_raw,
            "editions": [e.ano for e, _ in plan],
            "encodings": {},
            "export_warning": None,
        }
        if not plan:
            payload["export_warning"] = (
                f"Nenhuma edição de {self.name} entre {start_year} e "
                f"{end_year if end_year is not None else start_year}. Edições: "
                f"{sorted(self.spec.edicoes)}."
            )
            return payload

        client = self._client or IbgeFtpClient(base_url=api_base_url, timeout_seconds=timeout)
        downloads = [
            (edicao, alias)
            for edicao, chosen in plan
            for alias in dict.fromkeys(
                [t.arquivo for t in chosen] + [t.layout[0] for t in chosen if t.layout]
            )
        ]
        total = len(downloads)
        raws: Dict[Tuple[int, str], Path] = {}
        warnings: List[str] = []
        if progress_callback is not None:
            progress_callback({"event": "download_start", "source": self.name, "documents_total": total})
        for index, (edicao, alias) in enumerate(downloads, start=1):
            path = edicao.arquivos[alias]
            remote = client.head(path)
            raw_path = base_dir / f"{self.name}_{edicao.ano}_{Path(path).name}"
            raws[(edicao.ano, alias)] = raw_path
            payload["source_urls"].append(remote.url)
            skipped = (
                raw_path.exists()
                and remote.size is not None
                and raw_path.stat().st_size == remote.size
            )
            if not skipped:
                def on_bytes(written: int, _i=index, _p=raw_path, _s=remote.size) -> None:
                    if progress_callback is not None:
                        progress_callback({
                            "event": "file_progress", "source": self.name,
                            "documents_total": total, "document_index": _i,
                            "file_path": str(_p), "file_bytes_downloaded": written,
                            "file_total_bytes": _s or 0,
                        })

                client.download(path, raw_path, progress_callback=on_bytes)
            payload["skipped_count" if skipped else "downloaded_count"] += 1
            if progress_callback is not None:
                progress_callback({
                    "event": "file_skipped" if skipped else "file_completed",
                    "source": self.name, "documents_total": total,
                    "document_index": index, "file_path": str(raw_path),
                })
        payload["source_url"] = payload["source_urls"][0]

        if requested:
            for edicao, chosen in plan:
                for tabela in chosen:
                    dest, encoding, warning = self._export(edicao, tabela, raws, base_dir, requested)
                    payload["exported_files"].append(str(dest))
                    payload["encodings"][f"{edicao.ano}/{tabela.nome}"] = encoding
                    if warning:
                        warnings.append(warning)
            if not keep_raw:
                for raw_path in raws.values():
                    raw_path.unlink(missing_ok=True)
        else:
            warnings.append(
                "Zips kept as published; set output_format to export one UTF-8 "
                "csv, parquet or sqlite per table."
            )
        payload["export_warning"] = " ".join(warnings) or None
        return payload

    def _export(
        self,
        edicao: Edicao,
        tabela: Tabela,
        raws: Dict[Tuple[int, str], Path],
        base_dir: Path,
        fmt: str,
    ) -> Tuple[Path, str, Optional[str]]:
        stem = f"{self.name}_{edicao.ano}_{tabela.nome}"
        utf8 = base_dir / f"{stem}.utf8.tmp"
        warning = None
        try:
            with zipfile.ZipFile(raws[(edicao.ano, tabela.arquivo)]) as archive:
                info = _find_member(archive, tabela.membro)
                if tabela.layout is None:
                    encoding = _transcode_csv(archive, info, utf8)
                    frame = pl.scan_csv(
                        utf8, separator=tabela.separador, infer_schema=False, quote_char='"'
                    )
                    names = frame.collect_schema().names()
                    cleaned = {n: n.strip() for n in names if n != n.strip()}
                    if cleaned:
                        frame = frame.rename(cleaned)
                else:
                    layout_zip, programa = tabela.layout
                    with zipfile.ZipFile(raws[(edicao.ano, layout_zip)]) as layout_archive:
                        text = layout_archive.read(_find_member(layout_archive, programa))
                    blocks = parse_sas_input(text.decode("cp1252", errors="replace"))
                    block = _select_block(blocks, tabela, programa)
                    warning = block.layout_warning()
                    with archive.open(info) as source:
                        transcode_to_utf8(source, utf8, "cp1252")
                    encoding = "cp1252"
                    frame = scan_fixed_width(utf8, block.columns)
            if fmt == "csv":
                dest = base_dir / f"{stem}.csv"
                frame.sink_csv(dest)
            elif fmt == "parquet":
                dest = base_dir / f"{stem}.parquet"
                frame.sink_parquet(dest)
            else:
                written = write_sqlite(frame, db_path=base_dir / f"{stem}.sqlite", table=tabela.nome)
                if written is None:
                    raise ValueError(f"{stem} has no rows to export to sqlite.")
                dest = written
            return dest, encoding, warning
        finally:
            utf8.unlink(missing_ok=True)


def datasource_for(key: str) -> type:
    """Subclasse com ``DATASET`` fixo, que o ``ApiDownloadSource`` instancia só com ``output_path``."""
    spec = PESQUISAS[key]
    class_name = "".join(part.title() for part in key.split("_")) + "DataSource"
    return type(class_name, (IbgeMicrodadosDataSource,), {"DATASET": spec.key})
