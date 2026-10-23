"""Fiscalização do IBAMA (autos de infração e termos de embargo), arquivos de URL fixa.

Os dois conjuntos saem do Azure Blob do portal de dados abertos do IBAMA, cujas URLs vêm
do CKAN (``package_show?id=fiscalizacao-auto-de-infracao`` e
``fiscalizacao-termo-de-embargo``) e foram conferidas ao vivo em 2026-10-23. Os arquivos
são regerados todo dia (``ULTIMA_ATUALIZACAO_RELATORIO``), então cada download é um
instantâneo completo.

O RAPP (emissões e efluentes) continua em ``HTTP_FILES``, ao lado das demais fontes do
IBAMA, porque já era dali.
"""

from typing import Dict, Tuple

from guaraci.arquivos.http_files import HttpFile, HttpResource

_BLOB = "https://stibamadadosabertosprd.blob.core.windows.net/dados-abertos/dados/"

_PESSOAL = (
    "Traz identificador pessoal ({colunas}), publicado assim pelo órgão; o tratamento LGPD "
    "fica nas camadas prata e ouro do Sabiá."
)

IBAMA_AUTOS_INFRACAO = HttpFile(
    "ibama_autos_infracao",
    "IBAMA Fiscalização - Autos de infração",
    "Autos de infração ambiental lavrados pelo IBAMA (SIFISC), de 1977 em diante, com tipo "
    "e valor da multa, infração, município e UF, área, coordenada e situação do auto. "
    "O recurso auto_infracao é um zip com um CSV por ano do auto (84 colunas no primeiro "
    "membro; o leiaute pode variar entre anos), que sai como uma saída irmã por ano; "
    "enquadramento (artigos infringidos, também um CSV por ano) e os CSV únicos especime "
    "(espécimes apreendidos), coordenada (vértices, em WKT) e bioma ligam-se ao auto por "
    "SEQ_AUTO_INFRACAO. Os anexos e os arquivos do sistema AIe Mob ficam de fora. "
    + _PESSOAL.format(colunas="NOME_INFRATOR e CPF_CNPJ_INFRATOR, com CPF de pessoa física")
    + " Instantâneo regerado diariamente.",
    (
        HttpResource(
            "auto_infracao",
            _BLOB + "SIFISC/auto_infracao/auto_infracao/auto_infracao_csv.zip",
            "Autos de infração",
        ),
        HttpResource(
            "enquadramento",
            _BLOB + "SIFISC/auto_infracao/enquadramento/enquadramento_csv.zip",
            "Autos de infração - enquadramento legal",
        ),
        HttpResource(
            "especime",
            _BLOB + "SIFISC/auto_infracao/especime/especime.csv",
            "Autos de infração - espécimes",
        ),
        HttpResource(
            "coordenada",
            _BLOB + "SIFISC/auto_infracao/coordenada/coordenada.csv",
            "Autos de infração - coordenadas geográficas",
        ),
        HttpResource(
            "bioma",
            _BLOB + "SIFISC/auto_infracao/bioma/bioma.csv",
            "Autos de infração - biomas",
        ),
    ),
    separator=";",
    members_pattern=r"\.csv$",
    selector="indicadores",
)

IBAMA_TERMOS_EMBARGO = HttpFile(
    "ibama_termos_embargo",
    "IBAMA Fiscalização - Termos de embargo",
    "Termos de embargo e de desembargo de áreas lavrados pelo IBAMA (SIFISC): data, "
    "município e UF, área embargada (polígono em WKT), vínculo com o auto de infração e a "
    "ação fiscalizatória, desembargo e alterações. Os CSV itens, coordenadas, enquadramento "
    "e decisao ligam-se ao termo por SEQ_TAD. O histórico de alterações (730 MB) e os anexos "
    "ficam de fora. "
    + _PESSOAL.format(
        colunas="NOME_EMBARGADO e CPF_CNPJ_EMBARGADO, com CPF de pessoa física sem máscara"
    )
    + " Instantâneo regerado diariamente.",
    (
        HttpResource(
            "termo_embargo",
            _BLOB + "TERMOS_DE_EMBARGO/TERMO_EMBARGO/termo_de_embargo.csv",
            "Termos de embargo",
        ),
        HttpResource(
            "itens",
            _BLOB + "TERMOS_DE_EMBARGO/TERMO_EMBARGO_ITENS/termo_embargo_itens.csv",
            "Termos de embargo - itens",
        ),
        HttpResource(
            "coordenadas",
            _BLOB
            + "TERMOS_DE_EMBARGO/TERMO_EMBARGO_COORDENADAS/termo_de_embargo_coordenadas.csv",
            "Termos de embargo - coordenadas geográficas",
        ),
        HttpResource(
            "enquadramento",
            _BLOB
            + "TERMOS_DE_EMBARGO/TERMO_EMBARGO_ENQUADRAMENTO/"
            "termo_de_embargo_enquadramento.csv",
            "Termos de embargo - enquadramento",
        ),
        HttpResource(
            "decisao",
            _BLOB + "TERMOS_DE_EMBARGO/TERMO_EMBARGO_DECISAO/termo_embargo_decisao.csv",
            "Termos de embargo - decisões judiciais",
        ),
    ),
    separator=";",
    selector="indicadores",
)

SPECS: Tuple[HttpFile, ...] = (IBAMA_AUTOS_INFRACAO, IBAMA_TERMOS_EMBARGO)
MODES: Dict[str, str] = {spec.key: "ibama files" for spec in SPECS}
