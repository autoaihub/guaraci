"""Tabelas de códigos servidas em JSON pelo IBGE (localidades e CNAE da CONCLA).

Verificado ao vivo em 2026-11-14 (HTTP 200):

- ``/api/v1/localidades/municipios``: 5.571 municípios, cada um com microrregião,
  mesorregião, UF, região, região imediata e região intermediária aninhadas.
- ``/api/v1/localidades/distritos``: 10.751 distritos, com o município aninhado.
- ``/api/v2/cnae/classes`` e ``/api/v2/cnae/subclasses``: 1.332 subclasses com
  classe, grupo, divisão e seção aninhadas.

O JSON aninhado vira colunas achatadas (``microrregiao_mesorregiao_UF_sigla``);
o hífen do nome da chave vira sublinhado. Listas (``observacoes``, ``atividades``)
ficam como texto JSON numa só coluna. O código de município de 6 dígitos não é
publicado pela API e, por isso, não é derivado.
"""

from __future__ import annotations

from typing import Dict, Iterator, Mapping, Optional

from guaraci.gestao_publica.rest import RowSpool, finalize_export, normalize_format
from guaraci.ibge.client import IbgeSidraClient
from guaraci.referencias.base import ProgressCallback, ReferenciaDataSource

DEFAULT_BASE_URL = "https://servicodados.ibge.gov.br"


def achatar(value: Mapping[str, object], prefix: str = "") -> Iterator[tuple]:
    """Percorre os objetos aninhados; listas e valores simples ficam como estão."""
    for key, item in value.items():
        name = f"{prefix}{key}".replace("-", "_")
        if isinstance(item, dict):
            yield from achatar(item, f"{name}_")
        else:
            yield name, item


class JsonListaDataSource(ReferenciaDataSource):
    """Uma requisição GET que devolve uma lista JSON, gravada como um CSV."""

    PATH = ""

    def download(
        self,
        *,
        output_format: Optional[str] = None,
        output_dir: Optional[str] = None,
        timeout: int = ReferenciaDataSource.DEFAULT_TIMEOUT,
        api_base_url: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Dict[str, object]:
        fmt = normalize_format(output_format)
        base_dir = self.base_dir(output_dir)
        # o CDN do IBGE comprime a resposta sem ser pedido; este cliente já trata o gzip
        client = IbgeSidraClient(base_url=api_base_url or DEFAULT_BASE_URL, timeout_seconds=timeout)
        url = f"{client.base_url}/api/{self.PATH}"
        if progress_callback is not None:
            progress_callback({"event": "download_start", "source": self.name, "documents_total": 1})
        body = client._request_json(url)
        if not isinstance(body, list):
            raise ValueError(f"Resposta inesperada de {self.PATH}: esperava uma lista JSON.")
        spool = RowSpool(base_dir, self.name)
        try:
            for item in body:
                spool.add(dict(achatar(item)))
        except BaseException:
            spool.discard()
            raise
        rows = spool.rows
        # um objeto nulo em algumas linhas (``"microrregiao": null``) deixaria uma coluna
        # com o nome do pai ao lado das colunas achatadas dele; ela não carrega dado
        colunas = list(spool.columns)
        colunas = [c for c in colunas if not any(o.startswith(f"{c}_") for o in colunas)]
        csv_path = spool.write_csv(base_dir / f"{self.name}.csv", columns=colunas or None)
        exported = finalize_export(csv_path, fmt, self.name)
        if progress_callback is not None:
            progress_callback({
                "event": "file_progress", "source": self.name,
                "documents_total": 1, "files_completed": 1, "file_path": self.PATH,
            })
        return self.result(
            base_dir=base_dir, source_url=url, fmt=fmt,
            exported=exported, rows=rows, files=1 if rows else 0,
        )


class IbgeMunicipiosDataSource(JsonListaDataSource):
    DATASET = "ibge_localidades_municipios"
    PATH = "v1/localidades/municipios"


class IbgeDistritosDataSource(JsonListaDataSource):
    DATASET = "ibge_localidades_distritos"
    PATH = "v1/localidades/distritos"


class CnaeClassesDataSource(JsonListaDataSource):
    DATASET = "cnae_classes"
    PATH = "v2/cnae/classes"


class CnaeSubclassesDataSource(JsonListaDataSource):
    DATASET = "cnae_subclasses"
    PATH = "v2/cnae/subclasses"
