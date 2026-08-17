"""Fontes gov.br (SNIS e SINISA) do registro padrao do DownloadService."""

from typing import List

from guaraci.services import downloads as _downloads
from guaraci.services.downloads import (
    DownloadSource,
    GovBrDownloadSource,
    SourceDescriptor,
)


def build_sources() -> List[DownloadSource]:
    """Retorna as fontes gov.br na ordem canonica."""
    return [
        GovBrDownloadSource(
            descriptor=SourceDescriptor(
                source="snis",
                title="SNIS",
                mode="gov.br crawl",
            ),
            datasource_cls=_downloads.SnisDataSource,
        ),
        GovBrDownloadSource(
            descriptor=SourceDescriptor(
                source="sinisa",
                title="SINISA",
                mode="gov.br crawl",
            ),
            datasource_cls=_downloads.SinisaDataSource,
        ),
    ]
