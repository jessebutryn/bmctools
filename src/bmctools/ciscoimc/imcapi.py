"""Low-level Cisco IMC XML API client.

Handles session management (login/refresh/logout) and XML request/response
serialization against the ``/nuova`` endpoint on Cisco IMC (CIMC).
"""

import xml.etree.ElementTree as ET
from typing import Optional
import requests


class ImcApiError(Exception):
    """Raised when the Cisco IMC XML API returns an error response."""

    def __init__(self, error_code: str, error_descr: str, method: str = ''):
        self.error_code = error_code
        self.error_descr = error_descr
        self.method = method
        super().__init__(f"IMC API error (method={method}, code={error_code}): {error_descr}")


class ImcApi:
    """Low-level Cisco IMC XML API client.

    Sends XML documents via HTTP(S) POST to ``/nuova`` and parses responses.

    Args:
        ip: CIMC IP address or hostname.
        username: CIMC username.
        password: CIMC password.
        verify_ssl: Verify SSL certificates (default True).
        port: Override HTTPS port (default None = 443).
    """

    NUOVA_PATH = '/nuova'

    def __init__(self, ip: str, username: str, password: str,
                 verify_ssl: bool = True, port: Optional[int] = None) -> None:
        self.ip = ip
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl

        scheme = 'https'
        port_str = f':{port}' if port else ''
        self.base_url = f'{scheme}://{ip}{port_str}'
        self.url = f'{self.base_url}{self.NUOVA_PATH}'

        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/xml',
        })

        if not self.verify_ssl:
            requests.packages.urllib3.disable_warnings(
                requests.packages.urllib3.exceptions.InsecureRequestWarning
            )

        self._cookie: Optional[str] = None
        self._refresh_period: int = 600
        self._priv: Optional[str] = None
        self._session_id: Optional[str] = None

        self._login()

    # ── Session management ────────────────────────────────────────────

    def _login(self) -> None:
        """Authenticate and obtain a session cookie via aaaLogin."""
        xml = f'<aaaLogin inName="{self.username}" inPassword="{self.password}"></aaaLogin>'
        root = self._post_raw(xml)

        error_code = root.get('errorCode')
        if error_code:
            raise ImcApiError(error_code, root.get('errorDescr', ''), 'aaaLogin')

        self._cookie = root.get('outCookie')
        self._refresh_period = int(root.get('outRefreshPeriod', '600'))
        self._priv = root.get('outPriv')
        self._session_id = root.get('outSessionId')

        if not self._cookie:
            raise ImcApiError('0', 'Login succeeded but no cookie returned', 'aaaLogin')

    def refresh(self) -> None:
        """Refresh the current session via aaaRefresh."""
        xml = (f'<aaaRefresh cookie="{self._cookie}" '
               f'inCookie="{self._cookie}" '
               f'inName="{self.username}" '
               f'inPassword="{self.password}">'
               f'</aaaRefresh>')
        root = self._post_raw(xml)

        error_code = root.get('errorCode')
        if error_code:
            raise ImcApiError(error_code, root.get('errorDescr', ''), 'aaaRefresh')

        new_cookie = root.get('outCookie')
        if new_cookie:
            self._cookie = new_cookie

    def keepalive(self) -> None:
        """Send a keepalive to prevent session timeout."""
        xml = f'<aaaKeepAlive cookie="{self._cookie}"></aaaKeepAlive>'
        root = self._post_raw(xml)
        error_code = root.get('errorCode')
        if error_code:
            raise ImcApiError(error_code, root.get('errorDescr', ''), 'aaaKeepAlive')

    def logout(self) -> None:
        """Terminate the session via aaaLogout."""
        if not self._cookie:
            return
        xml = (f'<aaaLogout cookie="{self._cookie}" '
               f'inCookie="{self._cookie}">'
               f'</aaaLogout>')
        try:
            self._post_raw(xml)
        except Exception:
            pass
        self._cookie = None

    @property
    def cookie(self) -> Optional[str]:
        return self._cookie

    @property
    def privilege(self) -> Optional[str]:
        return self._priv

    @property
    def refresh_period(self) -> int:
        return self._refresh_period

    # ── XML API methods ───────────────────────────────────────────────

    def config_resolve_dn(self, dn: str, hierarchical: bool = False) -> ET.Element:
        """Retrieve a managed object by distinguished name.

        Args:
            dn: Distinguished name (e.g. ``sys/rack-unit-1``).
            hierarchical: If True, return child objects as well.

        Returns:
            The ``outConfig`` Element containing the result.
        """
        hier = 'true' if hierarchical else 'false'
        xml = (f'<configResolveDn cookie="{self._cookie}" '
               f'dn="{dn}" inHierarchical="{hier}"/>')
        root = self._post_xml(xml, 'configResolveDn')
        return root.find('outConfig')

    def config_resolve_class(self, class_id: str, hierarchical: bool = False) -> ET.Element:
        """Retrieve all managed objects of a given class.

        Args:
            class_id: Class identifier (e.g. ``computeRackUnit``, ``firmwareRunning``).
            hierarchical: If True, return child objects as well.

        Returns:
            The ``outConfigs`` Element containing matching objects.
        """
        hier = 'true' if hierarchical else 'false'
        xml = (f'<configResolveClass cookie="{self._cookie}" '
               f'inHierarchical="{hier}" classId="{class_id}"/>')
        root = self._post_xml(xml, 'configResolveClass')
        return root.find('outConfigs') or root.find('outConfig')

    def config_resolve_children(self, dn: str, class_id: str = '',
                                hierarchical: bool = False) -> ET.Element:
        """Retrieve child objects of a managed object.

        Args:
            dn: Parent distinguished name.
            class_id: Optional class filter for children.
            hierarchical: If True, return full subtree.

        Returns:
            The ``outConfigs`` Element containing child objects.
        """
        hier = 'true' if hierarchical else 'false'
        class_attr = f' classId="{class_id}"' if class_id else ''
        xml = (f'<configResolveChildren cookie="{self._cookie}" '
               f'inDn="{dn}"{class_attr} inHierarchical="{hier}"/>')
        root = self._post_xml(xml, 'configResolveChildren')
        return root.find('outConfigs') or root.find('outConfig')

    def config_resolve_parent(self, dn: str, hierarchical: bool = False) -> ET.Element:
        """Retrieve the parent of a managed object.

        Args:
            dn: Child distinguished name.
            hierarchical: If True, return child objects of the parent.

        Returns:
            The ``outConfig`` Element containing the parent object.
        """
        hier = 'true' if hierarchical else 'false'
        xml = (f'<configResolveParent cookie="{self._cookie}" '
               f'dn="{dn}" inHierarchical="{hier}"/>')
        root = self._post_xml(xml, 'configResolveParent')
        return root.find('outConfig')

    def config_conf_mo(self, dn: str, in_config_xml: str,
                       hierarchical: bool = False) -> ET.Element:
        """Configure (modify) a managed object.

        Args:
            dn: Distinguished name of the object to modify.
            in_config_xml: Raw XML string for the ``<inConfig>`` body.
            hierarchical: If True, apply changes hierarchically.

        Returns:
            The ``outConfig`` Element with the resulting object state.
        """
        hier = 'true' if hierarchical else 'false'
        xml = (f'<configConfMo cookie="{self._cookie}" '
               f'inHierarchical="{hier}" dn="{dn}">'
               f'<inConfig>{in_config_xml}</inConfig>'
               f'</configConfMo>')
        root = self._post_xml(xml, 'configConfMo')
        return root.find('outConfig')

    # ── Transport ─────────────────────────────────────────────────────

    def _post_raw(self, xml_body: str) -> ET.Element:
        """POST raw XML to /nuova and return the parsed root Element."""
        response = self.session.post(
            self.url, data=xml_body, verify=self.verify_ssl, timeout=60
        )
        response.raise_for_status()
        return ET.fromstring(response.text)

    def _post_xml(self, xml_body: str, method_name: str) -> ET.Element:
        """POST XML, check for API-level errors, and return root Element."""
        root = self._post_raw(xml_body)
        error_code = root.get('errorCode')
        if error_code:
            raise ImcApiError(
                error_code,
                root.get('errorDescr', 'Unknown error'),
                method_name
            )
        return root

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def element_to_dict(element: ET.Element) -> dict:
        """Convert an XML Element and its attributes to a dict.

        Child elements are included under a ``'children'`` key as a list
        of ``(tag, attrib_dict)`` tuples.
        """
        if element is None:
            return {}
        result = dict(element.attrib)
        children = list(element)
        if children:
            result['children'] = [
                {'tag': child.tag, **dict(child.attrib)}
                for child in children
            ]
        return result

    @staticmethod
    def elements_to_list(container: ET.Element) -> list:
        """Convert all child elements of a container to a list of dicts."""
        if container is None:
            return []
        return [
            {'tag': child.tag, **dict(child.attrib)}
            for child in container
        ]

    def __del__(self):
        try:
            self.logout()
        except Exception:
            pass
