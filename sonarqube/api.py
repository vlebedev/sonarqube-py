"""
This module contains the SonarAPIHandler, used for communicating with the
SonarQube server web service API.

Derived from https://github.com/kako-nawao/python-sonarqube-api
"""
import operator

import requests

from .exceptions import ClientError, AuthError, ValidationError, ServerError


class Endpoint:

    def __init__(self, path, pager=None):
        self.path = path
        self.pager = pager


class Pager:

    def __init__(self, response_items, request_page_number='p', request_page_size='ps',
                 response_object='paging', response_page_index='pageIndex',
                 response_page_size='pageSize', response_total='total'):
        self.response_items = response_items
        self.request_page_number = request_page_number
        self.request_page_size = request_page_size
        self.response_object = response_object
        self.response_page_index = response_page_index
        self.response_page_size = response_page_size
        self.response_total = response_total

    def paging(self, response):
        return response[self.response_object] if self.response_object else response

    def page_index(self, response):
        return self.paging(response)[self.response_page_index]

    def page_size(self, response):
        return self.paging(response)[self.response_page_size]

    def total(self, response):
        return self.paging(response)[self.response_total]

    def has_next_page(self, response):
        if response:
            total = self.total(response)
            page_size = self.page_size(response)
            page_num = self.page_index(response)
            return page_num * page_size < total
        else:
            return True

    def next_page(self, response, data):
        page_num = self.page_index(response)
        data[self.request_page_number] = page_num + 1

    def items(self, response):
        return response[self.response_items]

class SonarQube:

    """
    Adapter for SonarQube's web service API.
    """
    # Default host is local
    DEFAULT_HOST = 'http://localhost'
    DEFAULT_PORT = 9000
    DEFAULT_BASE_PATH = ''

    AUTH_VALIDATION_ENDPOINT = Endpoint('/api/authentication/validate')
    PROJECTS_ENDPOINT = Endpoint('/api/projects/search', Pager(response_items='components'))

    def __init__(self, host=None, port=None, user=None, password=None,
                 base_path=None, token=None):
        """
        Set connection info and session, including auth (if user+password
        and/or auth token were provided).
        """
        self._host = host or self.DEFAULT_HOST
        self._port = port or self.DEFAULT_PORT
        self._base_path = base_path or self.DEFAULT_BASE_PATH
        self._session = requests.Session()

        # Prefer revocable authentication token over username/password if
        # both are provided
        if token:
            self._session.auth = token, ''
        elif user and password:
            self._session.auth = user, password

    def _endpoint(self, endpoint):
        """
        Return the complete url including host and port for a given endpoint.

        :param endpoint: service endpoint as str
        :return: complete url (including host and port) as str
        """
        return '{}:{}{}{}'.format(self._host, self._port, self._base_path, endpoint)

    def _get(self, endpoint, **data):

        res = self._session.get(self._endpoint(endpoint.path), params=data or {})

        # Analyse response status and return or raise exception
        # Note: redirects are followed automatically by requests
        if res.status_code < 300:
            # OK, return http response
            return res.json()

        elif res.status_code == 400:
            # Validation error
            msg = ', '.join(e['msg'] for e in res.json()['errors'])
            raise ValidationError(msg)

        elif res.status_code in (401, 403):
            # Auth error
            raise AuthError(res.reason)

        elif res.status_code < 500:
            # Other 4xx, generic client error
            raise ClientError(res.reason)

        else:
            # 5xx is server error
            raise ServerError(res.reason)

    def _paged_get(self, endpoint, **data):

        qs = data.copy()
        pager = endpoint.pager
        res = None

        # Cycle through rules
        while pager.has_next_page(res):
            res = self._get(endpoint, **qs)

            pager.next_page(res, qs)

            # Yield items
            for item in pager.items(res):
                yield item

    def get_authentication_validate(self):
        return self._get(self.AUTH_VALIDATION_ENDPOINT).get('valid', False)

    def get_projects_search(self, **args):
        return self._paged_get(self.PROJECTS_ENDPOINT, **args)