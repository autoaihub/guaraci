#!/usr/bin/env python3
"""
Scaffolding tool to generate Guaraci Source blocks from OpenDataSUS DEMAS Swagger catalog.

Usage:
    python scripts/scaffold_opendatasus.py <endpoint_path>

Example:
    python scripts/scaffold_opendatasus.py /cnes/estabelecimentos
"""

import re
import sys
from pathlib import Path
import textwrap

# Add project root to pythonpath
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from guaraci.opendatasus.utils.swagger_catalog import load_local_get_params_catalog

SWAGGER_PATH = project_root / "guaraci" / "opendatasus" / "utils" / "swagger.json"

def get_phase_and_type(param_name: str) -> tuple[str, str, str]:
    """Returns (param_type, phase, allowed_values_code) for a given parameter."""
    name = param_name.lower()
    
    # Auto-generated endpoint parameters are native API filters.
    if name in {"uf", "sg_uf", "sg_uf_not"}:
        return "string", "basico", "allowed_values=uf_values,"
    
    if name.startswith("data_") or name.endswith("_date"):
        return "string", "basico", ""
    
    if name in {"municipio", "co_municipio"}:
        return "string", "basico", ""
        
    return "string", "basico", ""

def generate_source_block(endpoint: str, params: tuple[str, ...]) -> str:
    # Normalize source name (e.g. /cnes/estabelecimentos -> cnes_estabelecimentos)
    source_name = endpoint.strip("/").replace("-", "_").replace("/", "_")
    
    # Exclude core pagination parameters that Guaraci handles implicitly
    excluded = {"limit", "offset"}
    filtered_params = [p for p in params if p.lower() not in excluded]
    path_params = set(re.findall(r"{([^{}]+)}", endpoint))

    lines = []
    lines.append(f"            OpenDataSUSDownloadSource(")
    lines.append(f"                descriptor=SourceDescriptor(")
    lines.append(f"                    source=\"{source_name}\",")
    lines.append(f"                    title=\"{source_name.replace('_', ' ').title()}\",")
    lines.append(f"                    mode=\"opendatasus api\",")
    lines.append(f"                ),")
    lines.append(f"                datasource_cls=OpenDataSUSDataSource,")
    lines.append(f"                params_schema=[")
    
    # 1. Endpoint specific parameters (the most important for the user)
    for param in filtered_params:
        ptype, phase, allowed = get_phase_and_type(param)
        lines.append(f"                    SourceParameterSpec(")
        lines.append(f"                        name=\"{param}\",")
        lines.append(f"                        phase=\"{phase}\",")
        lines.append(f"                        param_type=\"{ptype}\",")
        lines.append(f"                        description=\"Refinamento opcional na chamada da API para {param}.\",")
        lines.append(f"                        required={param in path_params},")
        lines.append(f"                        default=None,")
        if allowed:
            lines.append(f"                        {allowed}")
        lines.append(f"                    ),")

    # 2. All technical and export parameters at the end
    all_tech_params = [
        ("output_dir", "string", "tecnica", "Output directory for downloaded files.", "None"),
        ("output_format", "string", "exportacao", "Optional export format for processed datasets.", "None", "allowed_values=EXPORT_FORMAT_VALUES,"),
        ("keep_raw", "boolean", "tecnica", "Se true, salva snapshot bruto JSONL além da exportação.", "False"),
        ("batch_size", "integer", "tecnica", "Page size for OpenDataSUS API pagination.", "1000", "minimum=1,", "maximum=1000,"),
        ("max_pages", "integer", "tecnica", "Maximum number of pages fetched in OpenDataSUS API.", "OpenDataSUSDataSource.DEFAULT_MAX_PAGES", "minimum=1,", "maximum=200000,"),
        ("api_base_url", "string", "tecnica", "Optional OpenDataSUS API base URL override (DEMAS).", "None"),
    ]
    
    for name, ptype, phase, desc, default, *extras in all_tech_params:
        lines.append(f"                    SourceParameterSpec(")
        lines.append(f"                        name=\"{name}\",")
        lines.append(f"                        phase=\"{phase}\",")
        lines.append(f"                        param_type=\"{ptype}\",")
        lines.append(f"                        description=\"{desc}\",")
        lines.append(f"                        required=False,")
        lines.append(f"                        default={default},")
        for ext in extras:
            if ext: lines.append(f"                        {ext}")
        lines.append(f"                    ),")

    lines.append(f"                ],")
    # For DEMAS, dataset is typically the endpoint path without the leading slash
    dataset_name = endpoint.lstrip("/")
    lines.append(f"                fixed_dataset=\"{dataset_name}\",")
    lines.append(f"                normalize_params=_normalize_opendatasus_params,")
    lines.append(f"            ),")
    
    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("Usage: python scaffold_opendatasus.py <endpoint_path_or_keyword> OR --all")
        sys.exit(1)
        
    query = sys.argv[1].lower()
    
    print(f"Loading swagger catalog from {SWAGGER_PATH}...")
    catalog = load_local_get_params_catalog(SWAGGER_PATH)
    
    if query == "--all":
        out_path = project_root / "guaraci" / "services" / "opendatasus_registry.py"
        print(f"Generating registry file with all {len(catalog)} endpoints to {out_path}...")
        
        lines = []
        lines.append('"""Auto-generated registry of OpenDataSUS API sources."""')
        lines.append("from typing import List, Dict")
        lines.append("from guaraci.core.contracts import SourceParameterSpec")
        lines.append("from guaraci.services.downloads import (")
        lines.append("    OpenDataSUSDownloadSource,")
        lines.append("    SourceDescriptor,")
        lines.append("    EXPORT_FORMAT_VALUES,")
        lines.append("    _normalize_opendatasus_params,")
        lines.append(")")
        lines.append("from guaraci.opendatasus.datasource import OpenDataSUSDataSource")
        lines.append("from guaraci.utils.mapping import UF_DICT")
        lines.append("\nuf_values = sorted(set(UF_DICT.values()))")
        lines.append("\ndef get_opendatasus_sources() -> List[OpenDataSUSDownloadSource]:")
        lines.append("    return [")
        
        # We exclude hardcoded ones and also any endpoint that ends with year patterns
        # to avoid duplication of annual sources (PNI, Gripal, SRAG)
        manual_excludes = {"/arboviroses/zikavirus"}
        
        count = 0
        for endpoint, params in catalog.items():
            # Filter manually excluded
            if endpoint in manual_excludes:
                continue
                
            # Filter yearly endpoints (e.g., -2020 or -2019-2026)
            if re.search(r"-\d{4}$", endpoint) or re.search(r"-\d{4}-\d{4}$", endpoint):
                continue

            block = generate_source_block(endpoint, params)
            lines.append(block)
            count += 1
            
        lines.append("    ]")
        
        out_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"Done! Generated {count} sources in {out_path.name}.")
        return

    matches = {path: params for path, params in catalog.items() if query in path.lower()}
    
    if not matches:
        print(f"No endpoints found matching '{query}'.")
        print("Available examples:")
        for k in list(catalog.keys())[:5]:
            print(f"  {k}")
        sys.exit(1)
        
    if len(matches) > 1 and query not in matches:
        print(f"Found multiple endpoints matching '{query}':")
        for k in matches:
            print(f"  - {k}")
        print("\nPlease provide a more specific endpoint path.")
        sys.exit(1)
        
    # If exact match or only one match
    endpoint = query if query in matches else list(matches.keys())[0]
    params = matches[endpoint]
    
    print(f"\nGenerating source block for endpoint: {endpoint}\n")
    print("-" * 80)
    print(generate_source_block(endpoint, params))
    print("-" * 80)
    print("\n>> Done! Copy the block above into `guaraci/services/downloads.py` under the _default_sources list.")


if __name__ == "__main__":
    main()
