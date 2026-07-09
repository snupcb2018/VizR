"""
DAVID GO enrichment adapter for VizR.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional
from xml.etree import ElementTree as ET

import pandas as pd
import requests

from backend.utils.logger import setup_module_logger

logger = setup_module_logger(__name__, 'INFO')


class DavidAPIError(Exception):
    """Raised when DAVID GO enrichment fails."""


@dataclass(frozen=True)
class DavidConfig:
    email: str
    timeout: int = 60
    soap_endpoint: str = (
        'https://davidbioinformatics.nih.gov/webservice/services/'
        'DAVIDWebService.DAVIDWebServiceHttpSoap11Endpoint/'
    )


class DavidGOEnrichmentAPI:
    DATABASES = {
        'GO_BP': 'GOTERM_BP_DIRECT',
        'GO_MF': 'GOTERM_MF_DIRECT',
        'GO_CC': 'GOTERM_CC_DIRECT',
    }

    NAMESPACES = {
        'soapenv': 'http://schemas.xmlsoap.org/soap/envelope/',
        'ns': 'http://service.session.sample',
        'ax21': 'http://service.session.sample/xsd',
    }

    def __init__(self, config: DavidConfig):
        email = (config.email or '').strip()
        if not email:
            raise DavidAPIError('DAVID email is required')

        self._config = config
        self._email = email
        self._session = requests.Session()

    def run_enrichment(
        self,
        genes: List[str],
        databases: Optional[List[str]] = None,
        organism: str = 'arabidopsis',
        p_value_cutoff: float = 0.05,
    ) -> Dict[str, pd.DataFrame]:
        if not genes:
            raise DavidAPIError('Gene list is required')

        requested_databases = databases or ['GO_BP', 'GO_MF', 'GO_CC']
        categories = [self.DATABASES[db] for db in requested_databases if db in self.DATABASES]
        if not categories:
            raise DavidAPIError('No valid DAVID GO categories specified')

        self._authenticate()
        self._add_gene_list(genes)
        self._set_categories(categories)
        rows = self._get_chart_report()

        grouped_results: Dict[str, pd.DataFrame] = {}
        for database, category_name in self.DATABASES.items():
            if database not in requested_databases:
                continue

            category_rows = [row for row in rows if row.get('Category') == category_name]
            if not category_rows:
                continue

            df = pd.DataFrame(category_rows)
            df = df[df['Adjusted P-value'].fillna(1.0) <= p_value_cutoff].copy()
            if df.empty:
                continue

            df = df.sort_values('Adjusted P-value', kind='stable').reset_index(drop=True)
            df['Rank'] = range(1, len(df) + 1)
            grouped_results[database] = df[
                [
                    'Rank',
                    'Term',
                    'Term ID',
                    'Term Name',
                    'P-value',
                    'Adjusted P-value',
                    'Genes',
                    'Gene Count',
                    'Term Size',
                    'Query Size',
                    'Intersection Size',
                ]
            ]

        return grouped_results

    def _soap_call(self, action: str, body: str) -> str:
        envelope = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ser="http://service.session.sample">
  <soapenv:Header/>
  <soapenv:Body>
    {body}
  </soapenv:Body>
</soapenv:Envelope>"""

        response = self._session.post(
            self._config.soap_endpoint,
            data=envelope.encode('utf-8'),
            headers={
                'Content-Type': 'text/xml; charset=utf-8',
                'SOAPAction': f'"urn:{action}"',
            },
            timeout=self._config.timeout,
        )
        response.raise_for_status()
        return response.text

    def _authenticate(self) -> None:
        response_xml = self._soap_call(
            'authenticate',
            f'<ser:authenticate><ser:args0>{self._email}</ser:args0></ser:authenticate>',
        )
        root = ET.fromstring(response_xml)
        result = root.find('.//ns:return', self.NAMESPACES)
        if result is None or (result.text or '').strip().lower() != 'true':
            raise DavidAPIError('DAVID authentication failed')

    def _add_gene_list(self, genes: List[str]) -> None:
        joined_genes = ','.join(g.strip() for g in genes if g and g.strip())
        response_xml = self._soap_call(
            'addList',
            (
                '<ser:addList>'
                f'<ser:args0>{joined_genes}</ser:args0>'
                '<ser:args1>TAIR_ID</ser:args1>'
                '<ser:args2>VizR_GO_Analysis</ser:args2>'
                '<ser:args3>0</ser:args3>'
                '</ser:addList>'
            ),
        )
        root = ET.fromstring(response_xml)
        result = root.find('.//ns:return', self.NAMESPACES)
        if result is None:
            raise DavidAPIError('DAVID addList returned no status')

        try:
            mapped_score = float(result.text or '0')
        except ValueError as exc:
            raise DavidAPIError(f'Unexpected DAVID addList response: {result.text}') from exc

        if mapped_score < 0:
            raise DavidAPIError('DAVID could not map the submitted gene list')

    def _set_categories(self, categories: List[str]) -> None:
        joined_categories = ','.join(categories)
        self._soap_call(
            'setCategories',
            f'<ser:setCategories><ser:args0>{joined_categories}</ser:args0></ser:setCategories>',
        )

    def _get_chart_report(self) -> List[Dict[str, object]]:
        response_xml = self._soap_call(
            'getChartReport',
            '<ser:getChartReport><ser:args0>1.0</ser:args0><ser:args1>2</ser:args1></ser:getChartReport>',
        )
        root = ET.fromstring(response_xml)
        results: List[Dict[str, object]] = []

        for row in root.findall('.//ns:return', self.NAMESPACES):
            category_name = self._child_text(row, 'categoryName')
            term_name_raw = self._child_text(row, 'termName')
            if not category_name or not term_name_raw:
                continue

            term_id, term_name = self._split_term_name(term_name_raw)
            gene_ids = (self._child_text(row, 'geneIds') or '').replace(', ', ';').replace(',', ';')
            list_hits = self._child_int(row, 'listHits')
            pop_hits = self._child_int(row, 'popHits')
            list_totals = self._child_int(row, 'listTotals')

            results.append(
                {
                    'Term': f'{term_id}: {term_name}' if term_id else term_name,
                    'Term ID': term_id,
                    'Term Name': term_name,
                    'P-value': self._child_float(row, 'fisher'),
                    'Adjusted P-value': self._child_float(row, 'benjamini'),
                    'Genes': gene_ids,
                    'Gene Count': list_hits,
                    'Term Size': pop_hits,
                    'Query Size': list_totals,
                    'Intersection Size': list_hits,
                    'Category': category_name,
                }
            )

        return results

    def _child_text(self, element: ET.Element, name: str) -> Optional[str]:
        for prefix in ('ax21', 'ns'):
            child = element.find(f'{prefix}:{name}', self.NAMESPACES)
            if child is not None and child.text is not None:
                return child.text

        child = element.find(name)
        if child is not None and child.text is not None:
            return child.text

        return None

    def _child_float(self, element: ET.Element, name: str) -> Optional[float]:
        value = self._child_text(element, name)
        if value in (None, ''):
            return None
        try:
            return float(value)
        except ValueError:
            logger.warning(f'[DAVID] Failed to parse float field {name}: {value}')
            return None

    def _child_int(self, element: ET.Element, name: str) -> int:
        value = self._child_text(element, name)
        if value in (None, ''):
            return 0
        try:
            return int(float(value))
        except ValueError:
            logger.warning(f'[DAVID] Failed to parse int field {name}: {value}')
            return 0

    def _split_term_name(self, raw_term: str) -> tuple[Optional[str], str]:
        if '~' not in raw_term:
            return None, raw_term
        term_id, term_name = raw_term.split('~', 1)
        return term_id, term_name
