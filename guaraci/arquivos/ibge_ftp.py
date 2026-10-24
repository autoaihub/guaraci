"""IBGE por arquivo (FTP em HTTPS): Censo 2022 agregados, projeções da população e MUNIC 2024.

Conferido ao vivo em 2026-10-23 (listagens HTML, cabeçalhos e primeiras linhas).

- ``ibge_censo2022_setores``: os agregados do Censo 2022 ficam em ``Agregados_por_Setores_
  Censitarios/Agregados_por_<Nivel>_csv/``, uma pasta por nível (setor, município, bairro,
  distrito, subdistrito) com um zip por tema, cada um com um CSV em ``;``. Os nomes trazem a
  data da edição só em alguns temas (``..._basico_BR_20260520.zip``), então a listagem HTML é
  lida na hora e, havendo duas edições do mesmo tema, vale a mais nova. O nível entra no
  parâmetro ``nivel`` (setor por padrão) e os temas em ``indicadores``.
- ``ibge_censo2022_renda_responsavel``: mesma lógica, na pasta ``Agregados_por_Setores_
  Censitarios_Rendimento_do_Responsavel/`` (``..._renda_responsavel_BR_20260508_csv.zip``).
  Com um só tema, a saída leva sempre o nome da fonte, qualquer que seja o nível.
- ``ibge_projecoes_populacao_2024``: cinco xlsx de uma aba cada. O cabeçalho vem depois de
  quatro (tab1, tab2, tab5) ou cinco (tab3, tab4) linhas de título e de grupo, e é isso que
  ``skip_rows`` descarta; a aba NOTAS da tab4 fica de fora.
- ``ibge_munic``: a MUNIC 2024 (xlsx de 25 MB) tem dez abas, uma por bloco temático e uma de
  dicionário, todas exportadas, cada uma como saída irmã.
"""

import re
from typing import Callable, Dict, List, Optional, Sequence, Tuple
from urllib.request import Request, urlopen

from guaraci.arquivos.http_files import (
    HttpFile,
    HttpFileClient,
    HttpFileDataSource,
    HttpResource,
)
from guaraci.core.contracts import SourceParameterSpec
from guaraci.core.datasource import DataSource

_CENSO = "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/"
_SETORES = _CENSO + "Agregados_por_Setores_Censitarios/"
_RENDA = _CENSO + "Agregados_por_Setores_Censitarios_Rendimento_do_Responsavel/"

# nível -> (pasta do índice, plural usado nos nomes dos arquivos)
NIVEIS: Dict[str, Tuple[str, str]] = {
    "setor": ("Agregados_por_Setor_csv/", "setores"),
    "municipio": ("Agregados_por_Municipio_csv/", "municipios"),
    "bairro": ("Agregados_por_Bairro_csv/", "bairros"),
    "distrito": ("Agregados_por_Distrito_csv/", "distritos"),
    "subdistrito": ("Agregados_por_SubDistrito_csv/", "subdistritos"),
}
TEMAS_SETORES: Tuple[str, ...] = (
    "basico",
    "demografia",
    "cor_ou_raca",
    "alfabetizacao",
    "caracteristicas_domicilio1",
    "caracteristicas_domicilio2",
    "caracteristicas_domicilio3",
    "obitos",
    "parentesco",
    "pessoas_indigenas",
    "domicilios_indigenas",
    "pessoas_quilombolas",
    "domicilios_quilombolas",
)
TEMAS_RENDA: Tuple[str, ...] = ("renda_responsavel",)


def fetch_text(url: str, timeout: int = 60) -> str:
    request = Request(url, headers={"User-Agent": HttpFileClient.USER_AGENT})
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - URL fixa do IBGE
        return response.read().decode("utf-8", "replace")


def latest_files(html: str, plural: str, suffix: str = "") -> Dict[str, str]:
    """Tema -> nome do zip mais novo, lendo os ``href`` do índice HTML.

    ``Agregados_por_<plural>_<tema>_BR[_AAAAMMDD]<suffix>.zip``. Sem data, vale como edição
    ``00000000``; com duas edições do mesmo tema, a data maior vence.
    """
    pattern = re.compile(
        rf"^Agregados_por_{plural}_(?P<tema>.+?)_BR(?:_(?P<data>\d{{8}}))?{re.escape(suffix)}\.zip$"
    )
    best: Dict[str, Tuple[str, str]] = {}
    for href in re.findall(r'href="([^"?/][^"]*)"', html):
        match = pattern.match(href)
        if not match:
            continue
        tema, data = match.group("tema"), match.group("data") or "00000000"
        if tema not in best or data > best[tema][0]:
            best[tema] = (data, href)
    return {tema: name for tema, (_data, name) in best.items()}


class IbgeCensoAgregadosDataSource(HttpFileDataSource):
    """Descobre em tempo de execução o zip mais novo de cada tema e baixa os pedidos."""

    # Subclasses fixam a pasta, o sufixo do nome e o conjunto de níveis.
    INDEX_URL = _SETORES
    SUFFIX = ""
    USES_LEVEL_FOLDER = True
    SPEC: HttpFile

    def __init__(
        self,
        output_path: Optional[str] = None,
        *,
        dataset: Optional[str] = None,
        client: Optional[HttpFileClient] = None,
        fetch: Optional[Callable[[str], str]] = None,
    ) -> None:
        DataSource.__init__(self, name=self.SPEC.key, output_path=output_path)
        self.spec = self.SPEC
        self._client = client
        self._fetch = fetch or fetch_text
        self._nivel = "setor"

    def download(self, *, nivel: Optional[str] = None, **kwargs):
        nivel = (nivel or "setor").strip().lower()
        if nivel not in NIVEIS:
            raise ValueError(f"Unknown nivel '{nivel}'. Known: {sorted(NIVEIS)}")
        self._nivel = nivel
        return super().download(**kwargs)

    def _index(self) -> Tuple[str, str]:
        folder, plural = NIVEIS[self._nivel]
        if self.USES_LEVEL_FOLDER:
            return self.INDEX_URL + folder, plural
        return self.INDEX_URL, plural

    def _select(
        self,
        indicadores: Optional[Sequence[str]],
        anos: Optional[Sequence[object]] = None,
        meses: Optional[Sequence[object]] = None,
    ) -> List[HttpResource]:
        known = [r.code for r in self.spec.resources]
        wanted = [str(c).strip().lower() for c in indicadores] if indicadores else known
        unknown = [c for c in wanted if c not in known]
        if unknown:
            raise ValueError(f"Unknown indicadores {unknown}. Known: {sorted(known)}")
        base, plural = self._index()
        files = latest_files(self._fetch(base), plural, self.SUFFIX)
        missing = [c for c in wanted if c not in files]
        if missing:
            raise ValueError(
                f"Tema(s) {missing} não listados em {base} (listados: {sorted(files)})."
            )
        prefix = "" if self._nivel == "setor" else f"{self._nivel}_"
        return [
            HttpResource(f"{prefix}{tema}", base + files[tema], f"Censo 2022 {self._nivel} {tema}")
            for tema in dict.fromkeys(wanted)
        ]


def _censo_spec(key: str, title: str, description: str, temas: Sequence[str]) -> HttpFile:
    return HttpFile(
        key,
        title,
        description,
        tuple(HttpResource(tema, "", tema) for tema in temas),
        separator=";",
        selector="indicadores",
    )


IBGE_CENSO2022_SETORES = _censo_spec(
    "ibge_censo2022_setores",
    "IBGE Censo 2022 - Agregados por setor censitário",
    "Resultados do Universo do Censo Demográfico 2022 agregados por setor censitário (IBGE), "
    "um CSV por tema: básico, demografia, cor ou raça, alfabetização, características dos "
    "domicílios 1 a 3, óbitos, parentesco, pessoas e domicílios indígenas e quilombolas. O "
    "parâmetro nivel troca o setor por município, bairro, distrito ou subdistrito, e a "
    "edição mais nova de cada tema é descoberta na listagem do FTP na hora do download. Os "
    "nomes de coluna são os códigos do IBGE (V00001...), explicados no dicionário de dados "
    "do FTP, e os números ficam como cada tema os publica (o básico usa vírgula decimal). "
    "Dado agregado, sem identificador pessoal.",
    TEMAS_SETORES,
)
IBGE_CENSO2022_RENDA_RESPONSAVEL = _censo_spec(
    "ibge_censo2022_renda_responsavel",
    "IBGE Censo 2022 - Rendimento do responsável por domicílio",
    "Rendimento do responsável pelo domicílio no Censo Demográfico 2022, agregado por setor "
    "censitário (IBGE): código do setor e as variáveis V06001 em diante, 7 colunas (dicionário de dados "
    "no FTP do IBGE). O parâmetro nivel troca o setor por município, bairro, distrito ou subdistrito. "
    "A edição mais nova é descoberta na listagem do FTP na hora do download. Dado agregado, "
    "sem identificador pessoal.",
    TEMAS_RENDA,
)


class IbgeCensoSetoresDataSource(IbgeCensoAgregadosDataSource):
    DATASET = IBGE_CENSO2022_SETORES.key
    SPEC = IBGE_CENSO2022_SETORES
    INDEX_URL = _SETORES


class IbgeCensoRendaDataSource(IbgeCensoAgregadosDataSource):
    DATASET = IBGE_CENSO2022_RENDA_RESPONSAVEL.key
    SPEC = IBGE_CENSO2022_RENDA_RESPONSAVEL
    INDEX_URL = _RENDA
    SUFFIX = "_csv"
    USES_LEVEL_FOLDER = False


_PROJECOES = "https://ftp.ibge.gov.br/Projecao_da_Populacao/Projecao_da_Populacao_2024/"

IBGE_PROJECOES_POPULACAO_2024 = HttpFile(
    "ibge_projecoes_populacao_2024",
    "IBGE Projeções da População (revisão 2024)",
    "Projeções da população do Brasil, grandes regiões e unidades da federação, revisão 2024 "
    "(IBGE), um xlsx por tabela: tab1 por idade simples e sexo, tab2 por grupo quinquenal, "
    "tab3 por grupos etários específicos, tab4 indicadores implícitos (natalidade, "
    "mortalidade, esperança de vida, fecundidade) e tab5 tábuas de mortalidade. Nas tab1 e "
    "tab2 os anos de 2000 a 2070 são colunas; nas demais, linhas. O título e o bloco de "
    "grupos acima do cabeçalho são descartados, e o cabeçalho fica como publicado. Sem "
    "identificador pessoal.",
    (
        HttpResource("tab1", _PROJECOES + "projecoes_2024_tab1_idade_simples.xlsx", skip_rows=4),
        HttpResource("tab2", _PROJECOES + "projecoes_2024_tab2_grupo_quinquenal.xlsx", skip_rows=4),
        HttpResource(
            "tab3", _PROJECOES + "projecoes_2024_tab3_grupos_etarios_especificos.xlsx", skip_rows=5
        ),
        HttpResource(
            "tab4",
            _PROJECOES + "projecoes_2024_tab4_indicadores.xlsx",
            skip_rows=5,
            sheets=("4) INDICADORES",),
        ),
        HttpResource(
            "tab5", _PROJECOES + "projecoes_2024_tab5_tabuas_mortalidade.xlsx", skip_rows=4
        ),
    ),
    file_format="xlsx",
    selector="indicadores",
)

IBGE_MUNIC = HttpFile(
    "ibge_munic",
    "IBGE MUNIC 2024 - Perfil dos municípios",
    "Pesquisa de Informações Básicas Municipais 2024 (IBGE), base completa: uma aba por bloco "
    "temático (recursos humanos, informática e comunicação, governança, habitação, transporte "
    "e mobilidade urbana, agropecuária, gestão migratória, igualdade racial e o evento "
    "climático no Rio Grande do Sul), com uma linha por município e as respostas em texto. A "
    "aba Dicionário descreve as variáveis. Cada aba sai como arquivo próprio. Sem "
    "identificador pessoal.",
    (
        HttpResource(
            "2024",
            "https://ftp.ibge.gov.br/Perfil_Municipios/2024/Base_de_Dados/Base_MUNIC_2024_20251107.xlsx",
        ),
    ),
    file_format="xlsx",
)

SPECS: Tuple[HttpFile, ...] = (
    IBGE_CENSO2022_SETORES,
    IBGE_CENSO2022_RENDA_RESPONSAVEL,
    IBGE_PROJECOES_POPULACAO_2024,
    IBGE_MUNIC,
)
MODES: Dict[str, str] = {spec.key: "ibge files" for spec in SPECS}
DATASOURCES: Dict[str, type] = {
    IBGE_CENSO2022_SETORES.key: IbgeCensoSetoresDataSource,
    IBGE_CENSO2022_RENDA_RESPONSAVEL.key: IbgeCensoRendaDataSource,
}
_NIVEL = SourceParameterSpec(
    name="nivel",
    phase="coleta",
    param_type="string",
    description=(
        "Nível geográfico dos agregados: setor (padrão), municipio, bairro, distrito ou "
        "subdistrito."
    ),
    required=False,
    default="setor",
    allowed_values=sorted(NIVEIS),
)
EXTRA_PARAMS: Dict[str, List[SourceParameterSpec]] = {
    IBGE_CENSO2022_SETORES.key: [_NIVEL],
    IBGE_CENSO2022_RENDA_RESPONSAVEL.key: [_NIVEL],
}
