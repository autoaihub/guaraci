"""CNPJ aberto da Receita Federal: empresas, estabelecimentos, sócios, Simples e tabelas.

Origem: WebDAV público da Receita (ver ``webdav.py``), uma pasta ``AAAA-MM/`` por
competência (2023-05 em diante), com zips de um único CSV cada:

- ``Empresas0..9.zip``, ``Estabelecimentos0..9.zip``, ``Socios0..9.zip``: o
  cadastro dividido em até dez partes (a parte 0 de estabelecimentos passa de 2 GB);
- ``Simples.zip``: arquivo único;
- ``Cnaes.zip``, ``Motivos.zip``, ``Municipios.zip``, ``Naturezas.zip``,
  ``Paises.zip`` e ``Qualificacoes.zip``: tabelas de domínio de duas colunas.

Os CSV não têm cabeçalho: separador ``;``, campos entre aspas, Latin-1 (conferido
ao vivo em 2026-10-23, competência 2026-09, lendo o início de ``Empresas1``,
``Estabelecimentos1``, ``Socios1`` e ``Simples`` e as seis tabelas inteiras). As
contagens de colunas abaixo batem com o leiaute oficial, "Metadados do CNPJ"
(``cnpj-metadados.pdf``, Receita Federal, página de dados abertos do CNPJ):
empresas 7, estabelecimentos 30, sócios 11, Simples 7 e tabelas 2. Os nomes das
colunas vêm desse leiaute, em minúsculas, sem acento e com ``_``, e ficam
congelados aqui. Divergência de largura num arquivo é erro, pois nomear colunas
deslocadas daria dado plausível e errado.

Dado pessoal, publicado assim pela Receita: estabelecimentos trazem endereço,
telefone e correio eletrônico (inclusive de MEI); sócios trazem o nome do sócio e
o CPF parcial (seis dígitos centrais, ``***240659**``) e o nome do representante
legal. Nada é removido; o tratamento LGPD fica nas camadas prata e ouro do Sabiá.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import polars as pl

from guaraci.arquivos.http_files import (
    _normalize_format,
    _sink_atomic,
    encoding_warnings,
    transcode_lines,
)
from guaraci.core.datasource import DataSource
from guaraci.core.http import ApiClientError
from guaraci.receita.webdav import (
    DEFAULT_TOKEN,
    ReceitaWebDavClient,
    ReceitaWebDavError,
)

__all__ = [
    "CNPJ_FILES",
    "CNPJ_TABELAS",
    "CnpjDataSource",
    "CnpjFile",
    "EMPRESAS_COLUMNS",
    "ESTABELECIMENTOS_COLUMNS",
    "MIN_COMPETENCIA",
    "PARTES",
    "SIMPLES_COLUMNS",
    "SOCIOS_COLUMNS",
    "datasource_for",
]

MIN_COMPETENCIA = "2023-05"
PARTES = tuple(range(10))
ProgressCallback = Callable[[Dict[str, object]], None]

EMPRESAS_COLUMNS: Tuple[str, ...] = (
    "cnpj_basico",
    "razao_social",
    "natureza_juridica",
    "qualificacao_responsavel",
    "capital_social",
    "porte_empresa",
    "ente_federativo_responsavel",
)
ESTABELECIMENTOS_COLUMNS: Tuple[str, ...] = (
    "cnpj_basico",
    "cnpj_ordem",
    "cnpj_dv",
    "identificador_matriz_filial",
    "nome_fantasia",
    "situacao_cadastral",
    "data_situacao_cadastral",
    "motivo_situacao_cadastral",
    "nome_cidade_exterior",
    "pais",
    "data_inicio_atividade",
    "cnae_fiscal_principal",
    "cnae_fiscal_secundaria",
    "tipo_logradouro",
    "logradouro",
    "numero",
    "complemento",
    "bairro",
    "cep",
    "uf",
    "municipio",
    "ddd_1",
    "telefone_1",
    "ddd_2",
    "telefone_2",
    "ddd_fax",
    "fax",
    "correio_eletronico",
    "situacao_especial",
    "data_situacao_especial",
)
SOCIOS_COLUMNS: Tuple[str, ...] = (
    "cnpj_basico",
    "identificador_socio",
    "nome_socio_razao_social",
    "cnpj_cpf_socio",
    "qualificacao_socio",
    "data_entrada_sociedade",
    "pais",
    "representante_legal",
    "nome_representante",
    "qualificacao_representante_legal",
    "faixa_etaria",
)
SIMPLES_COLUMNS: Tuple[str, ...] = (
    "cnpj_basico",
    "opcao_pelo_simples",
    "data_opcao_pelo_simples",
    "data_exclusao_do_simples",
    "opcao_pelo_mei",
    "data_opcao_pelo_mei",
    "data_exclusao_do_mei",
)
TABELA_COLUMNS: Tuple[str, ...] = ("codigo", "descricao")

# Tabela de domínio -> arquivo no WebDAV.
CNPJ_TABELAS: Dict[str, str] = {
    "cnaes": "Cnaes",
    "motivos": "Motivos",
    "municipios": "Municipios",
    "naturezas": "Naturezas",
    "paises": "Paises",
    "qualificacoes": "Qualificacoes",
}

_PESSOAL_ESTAB = (
    "Traz endereço, telefone e correio eletrônico dos estabelecimentos, inclusive de MEI, "
    "publicados assim pela Receita; o tratamento LGPD fica nas camadas prata e ouro do Sabiá."
)
_PESSOAL_SOCIOS = (
    "Traz identificador pessoal (nome do sócio, CPF parcial com os seis dígitos centrais e "
    "nome do representante legal), publicado assim pela Receita; o tratamento LGPD fica nas "
    "camadas prata e ouro do Sabiá."
)
_FORMATO = (
    "Texto como a Receita publica, sem cabeçalho na origem: as colunas ganham os nomes do "
    "leiaute oficial. Um CSV por parte e competência."
)


@dataclass(frozen=True)
class CnpjFile:
    key: str
    title: str
    description: str
    prefix: str  # prefixo do arquivo no WebDAV
    columns: Tuple[str, ...]
    multipart: bool  # True: <prefixo>0..9.zip; False: arquivo único
    tabelas: bool = False


CNPJ_FILES: Dict[str, CnpjFile] = {
    spec.key: spec
    for spec in (
        CnpjFile(
            "receita_cnpj_estabelecimentos",
            "Receita Federal - CNPJ: Estabelecimentos",
            "Cadastro de estabelecimentos do CNPJ (matriz e filiais): situação cadastral, "
            "CNAE principal e secundários, endereço com UF e município (código da Receita), "
            "CEP, telefones e e-mail. Cruza com o CNES por município e CNAE (por exemplo, "
            "CNAE 86 para saúde). " + _FORMATO + " " + _PESSOAL_ESTAB,
            "Estabelecimentos",
            ESTABELECIMENTOS_COLUMNS,
            True,
        ),
        CnpjFile(
            "receita_cnpj_empresas",
            "Receita Federal - CNPJ: Empresas",
            "Cadastro de empresas (CNPJ básico): razão social, natureza jurídica, "
            "qualificação do responsável, capital social, porte e ente federativo. "
            "Razão social de MEI pode conter o nome do titular. " + _FORMATO,
            "Empresas",
            EMPRESAS_COLUMNS,
            True,
        ),
        CnpjFile(
            "receita_cnpj_socios",
            "Receita Federal - CNPJ: Sócios",
            "Quadro societário: sócio (pessoa física, jurídica ou estrangeiro), qualificação, "
            "data de entrada, representante legal e faixa etária. " + _FORMATO + " "
            + _PESSOAL_SOCIOS,
            "Socios",
            SOCIOS_COLUMNS,
            True,
        ),
        CnpjFile(
            "receita_cnpj_simples",
            "Receita Federal - CNPJ: Simples Nacional e MEI",
            "Opção pelo Simples Nacional e pelo MEI por CNPJ básico, com datas de opção e de "
            "exclusão. Arquivo único (cerca de 300 MB comprimidos). " + _FORMATO,
            "Simples",
            SIMPLES_COLUMNS,
            False,
        ),
        CnpjFile(
            "receita_cnpj_tabelas",
            "Receita Federal - CNPJ: Tabelas de domínio",
            "Tabelas de domínio do CNPJ (CNAE, municípios pelo código da Receita, naturezas "
            "jurídicas, qualificações, países e motivos de situação cadastral), com as "
            "colunas 'codigo' e 'descricao'. Uma saída por tabela. " + _FORMATO,
            "",
            TABELA_COLUMNS,
            False,
            tabelas=True,
        ),
    )
}

_COMPETENCIA_RE = re.compile(r"(\d{4})-?(0[1-9]|1[0-2])")


def parse_competencia(value: object) -> str:
    """``AAAA-MM`` (ou ``AAAAMM``) normalizado para ``AAAA-MM``."""
    match = _COMPETENCIA_RE.fullmatch(str(value).strip())
    if match is None:
        raise ValueError(f"Competência inválida '{value}': use AAAA-MM.")
    text = f"{match.group(1)}-{match.group(2)}"
    if text < MIN_COMPETENCIA:
        raise ValueError(f"O CNPJ no WebDAV começa em {MIN_COMPETENCIA}; pedido: {text}.")
    return text


class CnpjDataSource(DataSource):
    """Baixa os zips de uma competência e exporta um CSV UTF-8 por parte (ou tabela)."""

    DATASET: str = ""
    DEFAULT_TIMEOUT = ReceitaWebDavClient.DEFAULT_TIMEOUT

    def __init__(
        self,
        output_path: Optional[str] = None,
        *,
        dataset: Optional[str] = None,
        client: Optional[ReceitaWebDavClient] = None,
    ) -> None:
        key = dataset or self.DATASET
        if key not in CNPJ_FILES:
            raise ValueError(f"Unknown CNPJ dataset '{key}'. Known: {sorted(CNPJ_FILES)}")
        super().__init__(name=key, output_path=output_path)
        self.spec = CNPJ_FILES[key]
        self._client = client

    def load_dataframe(self, *args, **kwargs) -> pl.DataFrame:  # pragma: no cover
        raise NotImplementedError("Read the exported file with polars.scan_*.")

    def _dav(self, token: Optional[str], timeout: int) -> ReceitaWebDavClient:
        return self._client or ReceitaWebDavClient(
            token=token or DEFAULT_TOKEN, timeout_seconds=timeout
        )

    # -- seleção ----------------------------------------------------------
    def _wanted_files(
        self, partes: Optional[Sequence[object]], tabelas: Optional[Sequence[object]]
    ) -> List[Tuple[str, str]]:
        """``[(código da saída, nome do arquivo no WebDAV)]`` do pedido."""
        spec = self.spec
        if spec.tabelas:
            chosen = [str(t).strip().lower() for t in tabelas or CNPJ_TABELAS]
            unknown = [t for t in chosen if t not in CNPJ_TABELAS]
            if unknown:
                raise ValueError(f"Tabelas desconhecidas {unknown}. Use {sorted(CNPJ_TABELAS)}.")
            return [(t, f"{CNPJ_TABELAS[t]}.zip") for t in dict.fromkeys(chosen)]
        if not spec.multipart:
            return [("unico", f"{spec.prefix}.zip")]
        try:
            numbers = sorted({int(p) for p in partes}) if partes else list(PARTES)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"'partes' deve ter números de 0 a 9: {exc}") from exc
        if any(n not in PARTES for n in numbers):
            raise ValueError("'partes' deve ter valores de 0 a 9.")
        return [(f"parte{n}", f"{spec.prefix}{n}.zip") for n in numbers]

    def _pick_competencia(
        self, dav: ReceitaWebDavClient, competencia: Optional[object], needed: Sequence[str]
    ) -> Tuple[str, Dict[str, Optional[int]], Dict[str, Optional[str]]]:
        """Competência e metadados (tamanho, data) dos arquivos pedidos."""
        if competencia:
            folder = parse_competencia(competencia)
            candidates = [folder]
        else:
            candidates = sorted(
                (
                    e.name
                    for e in dav.list("")
                    if e.is_dir and re.fullmatch(r"\d{4}-\d{2}", e.name)
                ),
                reverse=True,
            )
            if not candidates:
                raise ValueError("Nenhuma pasta de competência no WebDAV da Receita.")
        for folder in candidates:
            entries = {e.name: e for e in dav.list(folder) if not e.is_dir}
            missing = [n for n in needed if n not in entries]
            if not missing:
                return (
                    folder,
                    {n: entries[n].size for n in needed},
                    {n: entries[n].last_modified for n in needed},
                )
            if competencia:
                raise ValueError(
                    f"Competência {folder} sem {', '.join(missing)} no WebDAV da Receita."
                )
        raise ValueError(
            "Nenhuma competência publicada traz todos os arquivos pedidos "
            f"({', '.join(needed)})."
        )

    # -- execução ---------------------------------------------------------
    def download(
        self,
        *,
        output_format: Optional[str] = None,
        keep_raw: bool = False,
        output_dir: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        competencia: Optional[object] = None,
        partes: Optional[Sequence[object]] = None,
        tabelas: Optional[Sequence[object]] = None,
        token: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Dict[str, object]:
        requested = _normalize_format(output_format)
        wanted = self._wanted_files(partes, tabelas)
        dav = self._dav(token, timeout)
        folder, sizes, modified = self._pick_competencia(
            dav, competencia, [name for _, name in wanted]
        )
        stamp = folder.replace("-", "")
        base_dir = Path(output_dir) if output_dir else self.output_path
        base_dir.mkdir(parents=True, exist_ok=True)
        total = len(wanted)
        isolate = total > 1
        warnings: List[str] = []

        def emit(event: Dict[str, object]) -> None:
            if progress_callback is not None:
                progress_callback({"source": self.name, "documents_total": total, **event})

        emit({"event": "download_start"})
        exported: List[str] = []
        downloaded = skipped_count = failed = 0
        first_url: Optional[str] = None
        for index, (code, filename) in enumerate(wanted, start=1):
            remote = f"{folder}/{filename}"
            first_url = first_url or dav.url(remote)
            raw_path = base_dir / f"{self.name}_{stamp}_{filename}"
            size = sizes.get(filename)
            try:
                skipped = (
                    raw_path.exists() and size is not None and raw_path.stat().st_size == size
                )
                if not skipped:

                    def on_bytes(written: int, _p=raw_path, _i=index, _s=size) -> None:
                        emit({
                            "event": "file_progress", "document_index": _i,
                            "file_path": str(_p), "file_bytes_downloaded": written,
                            "file_total_bytes": _s or 0,
                        })

                    dav.download(remote, raw_path, progress_callback=on_bytes)
                emit({
                    "event": "file_skipped" if skipped else "file_completed",
                    "document_index": index, "file_path": str(raw_path),
                })
                skipped_count += 1 if skipped else 0
                downloaded += 0 if skipped else 1
                if requested:
                    dest = self._export(raw_path, base_dir, requested, stamp, code, warnings)
                    exported.append(str(dest))
                    if not keep_raw:
                        raw_path.unlink(missing_ok=True)
            except (ApiClientError, ValueError, zipfile.BadZipFile, OSError) as exc:
                if not isolate or (
                    isinstance(exc, ReceitaWebDavError) and exc.category == "configuration"
                ):
                    raise
                failed += 1
                warnings.append(f"{filename}: {exc}")
        if not requested and not keep_raw:
            warnings.append(
                "Zip mantido como a Receita publica; informe output_format para exportar em "
                "csv, parquet ou sqlite."
            )
        first_name = wanted[0][1]
        return {
            "documents_found": total,
            "downloaded_count": downloaded,
            "skipped_count": skipped_count,
            "failed_count": failed,
            "output_dir": str(base_dir),
            "competencia": folder,
            "source_url": first_url,
            "source_size": sizes.get(first_name),
            "source_last_modified": modified.get(first_name),
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
        stamp: str,
        code: str,
        warnings: List[str],
    ) -> Path:
        name = f"{self.name}_{stamp}" if code == "unico" else f"{self.name}_{stamp}_{code}"
        utf8 = base_dir / f"{name}.utf8.tmp.csv"
        try:
            stats: Dict[str, int] = {}
            with zipfile.ZipFile(raw_path) as archive:
                members = [n for n in archive.namelist() if not n.endswith("/")]
                if len(members) != 1:
                    raise ValueError(f"{raw_path.name} tem {len(members)} membros; esperado 1.")
                with archive.open(members[0]) as source, open(
                    utf8, "w", encoding="utf-8", newline=""
                ) as sink:
                    encoding = transcode_lines(source, sink, stats)
            warnings.extend(encoding_warnings(raw_path.name, stats, encoding))
            frame = pl.scan_csv(
                utf8, separator=";", has_header=False, infer_schema=False, quote_char='"'
            )
            width = len(frame.collect_schema().names())
            if width != len(self.spec.columns):
                raise ValueError(
                    f"{raw_path.name}: {width} colunas, esperadas {len(self.spec.columns)}; "
                    "a Receita pode ter mudado o leiaute (confira os metadados do CNPJ)."
                )
            frame = frame.rename(
                dict(zip(frame.collect_schema().names(), self.spec.columns))
            )
            suffix = {"csv": ".csv", "parquet": ".parquet"}.get(fmt, ".sqlite")
            return _sink_atomic(frame, base_dir / f"{name}{suffix}", fmt, name, raw_path.name)
        finally:
            utf8.unlink(missing_ok=True)


def datasource_for(key: str) -> type:
    """Subclasse com ``DATASET`` fixo, que o ``ApiDownloadSource`` instancia só com ``output_path``."""
    if key not in CNPJ_FILES:
        raise KeyError(key)
    class_name = "".join(part.title() for part in key.split("_")) + "DataSource"
    return type(class_name, (CnpjDataSource,), {"DATASET": key})
