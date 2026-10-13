"""Leitura do formulário de um ``.def`` TabNet e montagem do POST.

O HTML do TabNet Win32 3.0 é antigo: ``<OPTION>`` sem fechamento, valores em
latin-1 e rótulos com entidades HTML. As opções saem do próprio formulário
(GET do ``.def``) em vez de ficarem fixas no código, para acompanhar anos e
indicadores novos.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlencode

__all__ = ["ALL_CATEGORIES", "TabnetForm", "TabnetOption", "parse_form"]

ALL_CATEGORIES = "TODAS_AS_CATEGORIAS__"

_SELECT_RE = re.compile(r"<SELECT\b([^>]*)>(.*?)</SELECT>", re.I | re.S)
_NAME_RE = re.compile(r"""\bNAME\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", re.I)
_OPTION_RE = re.compile(r"<OPTION\b([^>]*)>([^<]*)", re.I)
_VALUE_RE = re.compile(r"""\bVALUE\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", re.I)
_FORM_RE = re.compile(r"<FORM\b([^>]*)>", re.I)
_ACTION_RE = re.compile(r"""\bACTION\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", re.I)
_RADIO_RE = re.compile(r"<INPUT\b([^>]*\bTYPE\s*=\s*\"?radio\"?[^>]*)>", re.I)


def _attr(pattern: re.Pattern, text: str) -> Optional[str]:
    match = pattern.search(text)
    if not match:
        return None
    return next(group for group in match.groups() if group is not None)


@dataclass(frozen=True)
class TabnetOption:
    value: str
    label: str


@dataclass
class TabnetForm:
    action: Optional[str]
    selects: Dict[str, List[TabnetOption]] = field(default_factory=dict)
    radios: Dict[str, List[str]] = field(default_factory=dict)

    def values(self, name: str) -> List[str]:
        return [option.value for option in self.selects.get(name, [])]

    def filter_fields(self) -> List[str]:
        """Campos de seleção (``S<dimensão>``) que aceitam todas as categorias."""
        return [
            name
            for name, options in self.selects.items()
            if name.startswith("S") and any(o.value == ALL_CATEGORIES for o in options)
        ]

    def years(self, field_name: str = "Arquivos") -> Dict[int, str]:
        """Ano do rótulo para o valor do arquivo (``2024 -> indmun24.dbf``)."""
        found: Dict[int, str] = {}
        for option in self.selects.get(field_name, []):
            label = option.label.strip()
            if label.isdigit() and len(label) == 4:
                found[int(label)] = option.value
        return found

    def build_body(
        self,
        *,
        linha: str,
        coluna: str,
        incrementos: Sequence[str],
        arquivos: Sequence[str],
        filtros: Optional[Dict[str, Sequence[str]]] = None,
        formato: str = "prn",
    ) -> bytes:
        """Corpo ``application/x-www-form-urlencoded`` em latin-1."""
        for name, value in (("Linha", linha), ("Coluna", coluna)):
            if self.selects.get(name) and value not in self.values(name):
                raise ValueError(f"Opção '{value}' não existe no campo {name} do formulário.")
        offered = set(self.values("Incremento"))
        missing = [item for item in incrementos if item not in offered]
        if missing:
            raise ValueError(f"Incremento(s) fora do formulário: {missing}.")
        pairs: List[Tuple[str, str]] = [("Linha", linha), ("Coluna", coluna)]
        pairs += [("Incremento", item) for item in incrementos]
        pairs += [("Arquivos", item) for item in arquivos]
        chosen = dict(filtros or {})
        for name in self.filter_fields():
            for value in chosen.pop(name, None) or [ALL_CATEGORIES]:
                pairs.append((name, value))
        for name, values in chosen.items():
            pairs += [(name, value) for value in values]
        pairs += [("formato", formato), ("mostre", "Mostra")]
        return urlencode(pairs, encoding="latin-1").encode("ascii")


def parse_form(page: str) -> TabnetForm:
    """Lê ação, ``<SELECT>`` e rádios de uma página de formulário TabNet."""
    form_tag = _FORM_RE.search(page)
    action = _attr(_ACTION_RE, form_tag.group(1)) if form_tag else None
    form = TabnetForm(action=html.unescape(action) if action else None)
    for match in _SELECT_RE.finditer(page):
        name = _attr(_NAME_RE, match.group(1))
        if not name:
            continue
        options: List[TabnetOption] = []
        for option in _OPTION_RE.finditer(match.group(2)):
            value = _attr(_VALUE_RE, option.group(1))
            label = html.unescape(option.group(2)).strip()
            options.append(TabnetOption(value=value if value is not None else label, label=label))
        form.selects[name] = options
    for match in _RADIO_RE.finditer(page):
        name = _attr(_NAME_RE, match.group(1))
        value = _attr(_VALUE_RE, match.group(1))
        if name and value is not None:
            form.radios.setdefault(name, []).append(value)
    return form
