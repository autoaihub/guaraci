"""Arquivos de dados abertos da ANVISA como fontes do Guaraci.

Cada fonte é um arquivo inteiro de ``https://dados.anvisa.gov.br/dados/``,
republicado por cima do anterior. O download guarda o arquivo como veio; a
conversão (``output_format``) gera CSV UTF-8, Parquet ou SQLite em fluxo,
sem carregar o arquivo inteiro na memória, e com TODAS as colunas como texto:
as datas mudam de formato de um arquivo para outro (MM/DD no VigiMed e na
hemovigilância, DD/MM na tecnovigilância) e há ``None`` literal como nulo.
Interpretar isso é papel da camada prata, não do bronze.

Fica de fora, de propósito, ``notivisa2_nsp_da.csv`` (eventos adversos do
Núcleo de Segurança do Paciente, 1,3 GB): o arquivo não tem linha de
cabeçalho, e o dicionário publicado para ele descreve outra tabela (um
cadastro de estabelecimentos, com 11 campos, contra 19 colunas de eventos no
arquivo). Sem nome de coluna vindo da fonte, qualquer nome seria palpite.
Também fora: o SNGPC, com cerca de 1 GB por mês e sem os meses de 2021-11 a
2025-12 (verificado ao vivo em 2026-09-24).
"""

from __future__ import annotations

import codecs
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

import polars as pl

from guaraci.anvisa.client import AnvisaClient
from guaraci.core.datasource import DataSource
from guaraci.datasus.frames import write_sqlite

__all__ = ["AnvisaFile", "ANVISA_FILES", "AnvisaFileDataSource", "datasource_for"]

ProgressCallback = Callable[[Dict[str, object]], None]
_FORMATS = ("csv", "parquet", "sqlite")


@dataclass(frozen=True)
class AnvisaFile:
    key: str
    filename: str
    title: str
    description: str
    # Codificação declarada pela ANVISA: cp1252 na maior parte; o CMED vem em
    # UTF-8 com BOM.
    encoding: str = "cp1252"
    # O CMED abre com um preâmbulo (título, data de publicação, notas legais)
    # de tamanho variável: 59 linhas num arquivo e 72 no outro. O cabeçalho é
    # achado pelo conteúdo, nunca por posição.
    header_prefix: Optional[str] = None
    # Arquivos que citam campos entre aspas (medicamentos registrados, CMED).
    # Os demais não usam aspas, e uma aspa no começo de um campo de texto,
    # como ``"500" Dosage unit...`` no VigiMed, fazia o leitor engolir o resto
    # do arquivo como um campo só (verificado ao vivo em 2026-09-24).
    quoted: bool = False
    # Separador de lista DENTRO de um campo, publicado sem aspas. Na
    # tecnovigilância, OCORRENCIA_NIVEL_1 e _2 trazem "A ; B ; C", e 3 439
    # das 287 mil linhas tinham 2 a 8 campos a mais que o cabeçalho.
    list_separator: Optional[str] = None


ANVISA_FILES: Dict[str, AnvisaFile] = {
    item.key: item
    for item in (
        AnvisaFile(
            "anvisa_vigimed_notificacoes",
            "VigiMed_Notificacoes.csv",
            "ANVISA VigiMed - Notificações",
            "Notificações de eventos adversos a medicamentos e vacinas "
            "(farmacovigilância), com dados do paciente pseudonimizados.",
        ),
        AnvisaFile(
            "anvisa_vigimed_medicamentos",
            "VigiMed_Medicamentos.csv",
            "ANVISA VigiMed - Medicamentos",
            "Medicamentos citados em cada notificação, com princípio ativo "
            "WHODrug e código ATC.",
        ),
        AnvisaFile(
            "anvisa_vigimed_reacoes",
            "VigiMed_Reacoes.csv",
            "ANVISA VigiMed - Reações",
            "Reações de cada notificação codificadas em MedDRA (LLT a SOC), "
            "com gravidade e desfecho.",
        ),
        AnvisaFile(
            "anvisa_tecnovigilancia",
            "DADOS_ABERTOS_TECNOVIGILANCIA.csv",
            "ANVISA Tecnovigilância",
            "Queixas técnicas e eventos adversos com dispositivos médicos, "
            "desde 2012, com UF e município de ocorrência.",
            list_separator=" ; ",
        ),
        AnvisaFile(
            "anvisa_hemovigilancia",
            "DADOS_ABERTOS_HEMOVIGILANCIA.csv",
            "ANVISA Hemovigilância",
            "Reações transfusionais e eventos do ciclo do sangue, desde 2006, "
            "com faixa etária, cidade e UF.",
        ),
        AnvisaFile(
            "anvisa_medicamentos_registrados",
            "DADOS_ABERTOS_MEDICAMENTOS.csv",
            "ANVISA Medicamentos Registrados",
            "Registros de medicamentos: categoria regulatória, classe "
            "terapêutica, detentor, situação e princípio ativo.",
            quoted=True,
        ),
        AnvisaFile(
            "anvisa_cmed_precos",
            "TA_PRECO_MEDICAMENTO.csv",
            "ANVISA CMED - Preços de Medicamentos",
            "Lista CMED de preço fábrica e preço máximo ao consumidor, por "
            "apresentação e alíquota de ICMS.",
            encoding="utf-8-sig",
            header_prefix="SUBST",
            quoted=True,
        ),
        AnvisaFile(
            "anvisa_cmed_precos_governo",
            "TA_PRECO_MEDICAMENTO_GOV.csv",
            "ANVISA CMED - Preços para Compras Públicas",
            "Lista CMED de preço máximo de venda ao governo (PMVG), por "
            "apresentação.",
            encoding="utf-8-sig",
            header_prefix="SUBST",
            quoted=True,
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


def _to_utf8(raw: Path, spec: AnvisaFile, target: Path, rejects: Optional[Path] = None) -> int:
    """Copia ``raw`` para ``target`` em UTF-8, a partir do cabeçalho.

    Em blocos, para não carregar centenas de MB. Byte que o cp1252 não define
    vira o caractere de substituição em vez de abortar a conversão inteira.
    Devolve quantas linhas foram separadas em ``rejects`` (só arquivos sem
    aspas podem ter).
    """
    decoder = codecs.getincrementaldecoder(spec.encoding)(errors="replace")
    with open(raw, "rb") as source, open(target, "w", encoding="utf-8", newline="") as sink:
        pending = ""
        if spec.header_prefix:
            prefix = spec.header_prefix.upper()
            for line in source:
                text = decoder.decode(line)
                if text.lstrip().upper().startswith(prefix):
                    pending = text
                    break
            else:
                raise ValueError(
                    f"Header starting with '{spec.header_prefix}' not found in {raw.name}."
                )
        if spec.quoted:
            sink.write(pending)
            for block in iter(lambda: source.read(1 << 20), b""):
                sink.write(decoder.decode(block))
            sink.write(decoder.decode(b"", final=True))
            return 0
        return _rewrite_unquoted(source, decoder, sink, spec, first_line=pending, rejects=rejects)


_PLACEHOLDER = "\ue000"  # uso privado do Unicode: nunca aparece em dado real


def _split_fields(line: str, expected: int, list_separator: Optional[str]) -> List[str]:
    fields = line.split(";")
    if len(fields) > expected and list_separator:
        # Só um ";" com espaço dos dois lados é separador interno de lista;
        # ele volta para dentro do campo, com o texto exato da origem.
        protected = line.replace(list_separator, _PLACEHOLDER)
        fields = [part.replace(_PLACEHOLDER, list_separator) for part in protected.split(";")]
    return fields


def _rewrite_unquoted(
    source, decoder, sink, spec: AnvisaFile, *, first_line: str, rejects: Optional[Path]
) -> int:
    """Relê um arquivo sem aspas linha a linha e regrava como CSV bem formado.

    Cada linha é dividida só no ``;`` e escrita com aspas onde precisa. Linha
    que continua sem encaixar no cabeçalho (na tecnovigilância, 1 de 287 mil,
    com um ``;`` sem espaços dentro do nome técnico do produto) não é cortada
    por palpite nem descartada: vai inteira, com o número da linha, para
    ``rejects``. Sem ``rejects``, a conversão para com a posição exata.
    """
    writer = csv.writer(sink, delimiter=";", quotechar='"', lineterminator="\n")
    header: List[str] = []
    number = 0
    rejected = 0
    reject_handle = None

    def emit(line: str) -> None:
        nonlocal header, number, rejected, reject_handle
        line = line.rstrip("\r")
        number += 1
        if not header:
            header = line.split(";")
            writer.writerow(header)
            return
        if not line:
            return
        fields = _split_fields(line, len(header), spec.list_separator)
        if len(fields) != len(header):
            if rejects is None:
                raise ValueError(
                    f"{spec.filename}: line {number} has {len(fields)} fields, "
                    f"header has {len(header)}."
                )
            if reject_handle is None:
                reject_handle = open(rejects, "w", encoding="utf-8", newline="")
                reject_handle.write("linha;conteudo_original\n")
            reject_handle.write(f"{number};{line}\n")
            rejected += 1
            return
        writer.writerow(fields)

    buffer = first_line
    try:
        for block in iter(lambda: source.read(1 << 20), b""):
            buffer += decoder.decode(block)
            *complete, buffer = buffer.split("\n")
            for line in complete:
                emit(line)
        buffer += decoder.decode(b"", final=True)
        if buffer.strip():
            emit(buffer)
    finally:
        if reject_handle is not None:
            reject_handle.close()
    return rejected


class AnvisaFileDataSource(DataSource):
    """Um arquivo da ANVISA. Subclasses fixam ``DATASET`` (ver ``datasource_for``)."""

    DATASET: str = ""
    DEFAULT_TIMEOUT = AnvisaClient.DEFAULT_TIMEOUT

    def __init__(
        self,
        output_path: Optional[str] = None,
        *,
        dataset: Optional[str] = None,
        client: Optional[AnvisaClient] = None,
    ) -> None:
        key = dataset or self.DATASET
        if key not in ANVISA_FILES:
            raise ValueError(f"Unknown ANVISA dataset '{key}'. Known: {sorted(ANVISA_FILES)}")
        super().__init__(name=key, output_path=output_path)
        self.spec = ANVISA_FILES[key]
        self._client = client

    def load_dataframe(self, *args, **kwargs) -> pl.DataFrame:  # pragma: no cover
        raise NotImplementedError(
            "ANVISA files can reach GBs; read the exported file with polars.scan_*."
        )

    def download(
        self,
        *,
        output_format: Optional[str] = None,
        keep_raw: bool = False,
        output_dir: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
        api_base_url: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Dict[str, object]:
        requested = _normalize_format(output_format)
        base_dir = Path(output_dir) if output_dir else self.output_path
        base_dir.mkdir(parents=True, exist_ok=True)
        client = self._client or AnvisaClient(base_url=api_base_url, timeout_seconds=timeout)

        remote = client.head(self.spec.filename)
        raw_path = base_dir / self.spec.filename
        skipped = raw_path.exists() and remote.size is not None and raw_path.stat().st_size == remote.size
        if progress_callback is not None:
            progress_callback({"event": "download_start", "source": self.name, "documents_total": 1})
        if not skipped:
            def on_bytes(written: int) -> None:
                # Sem este evento o job via 0 B até o fim, e o cancelamento,
                # que só age num evento, esperava o arquivo inteiro.
                if progress_callback is not None:
                    progress_callback({
                        "event": "file_progress", "source": self.name, "documents_total": 1,
                        "document_index": 1, "file_path": str(raw_path),
                        "file_bytes_downloaded": written, "file_total_bytes": remote.size or 0,
                    })

            client.download(self.spec.filename, raw_path, progress_callback=on_bytes)
        if progress_callback is not None:
            progress_callback({
                "event": "file_skipped" if skipped else "file_completed", "source": self.name,
                "documents_total": 1, "document_index": 1, "file_path": str(raw_path),
            })

        exported: List[str] = []
        warnings: List[str] = []
        rejected = 0
        rejects_path = base_dir / f"{self.name}.rejeitadas.csv"
        if requested:
            dest, rejected = self._export(raw_path, base_dir, requested, rejects_path)
            exported.append(str(dest))
            if rejected:
                warnings.append(
                    f"{rejected} linha(s) com mais campos que o cabeçalho, sem corte "
                    f"seguro, separadas como vieram em {rejects_path.name}."
                )
            if not keep_raw:
                raw_path.unlink(missing_ok=True)
        elif not keep_raw:
            warnings.append(
                "Raw file kept as published (cp1252, ';'); set output_format to "
                "also export UTF-8 csv, parquet or sqlite."
            )

        return {
            "documents_found": 1,
            "downloaded_count": 0 if skipped else 1,
            "skipped_count": 1 if skipped else 0,
            "failed_count": 0,
            "output_dir": str(base_dir),
            "source_url": remote.url,
            "source_size": remote.size,
            "source_last_modified": remote.last_modified,
            "output_format": requested,
            "exported_files": exported,
            "keep_raw": keep_raw,
            "rejected_rows": rejected,
            "rejected_file": str(rejects_path) if rejected else None,
            "export_warning": " ".join(warnings) or None,
        }

    def _export(self, raw_path: Path, base_dir: Path, fmt: str, rejects: Path) -> tuple:
        stem = Path(self.spec.filename).stem
        utf8 = base_dir / f"{stem}.utf8.tmp.csv"
        rejects.unlink(missing_ok=True)
        try:
            rejected = _to_utf8(raw_path, self.spec, utf8, rejects)
            frame = pl.scan_csv(utf8, separator=";", infer_schema=False, quote_char='"')
            # O CMED publica "DESTINAÇÃO COMERCIAL ": com o espaço não
            # separável no nome, frame["DESTINAÇÃO COMERCIAL"] falhava.
            nomes = frame.collect_schema().names()
            limpos = {n: n.strip() for n in nomes if n != n.strip()}
            if limpos:
                frame = frame.rename(limpos)
            if fmt == "csv":
                dest = base_dir / f"{self.name}.csv"
                frame.sink_csv(dest)
            elif fmt == "parquet":
                dest = base_dir / f"{self.name}.parquet"
                frame.sink_parquet(dest)
            else:
                written = write_sqlite(frame, db_path=base_dir / f"{self.name}.sqlite", table=self.name)
                if written is None:
                    raise ValueError(f"{self.spec.filename} has no rows to export to sqlite.")
                dest = written
            return dest, rejected
        finally:
            utf8.unlink(missing_ok=True)


def datasource_for(key: str) -> type:
    """Subclasse com ``DATASET`` fixo, que o ``ApiDownloadSource`` instancia só com ``output_path``."""
    spec = ANVISA_FILES[key]
    class_name = "".join(part.title() for part in key.split("_")) + "DataSource"
    return type(class_name, (AnvisaFileDataSource,), {"DATASET": spec.key})
