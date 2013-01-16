# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import httplib
import urlparse

from webob.exc import HTTPForbidden, HTTPUnauthorized
from swift.common.utils import cache_from_env
from swift.common.wsgi import make_pre_authed_request


class Swquota(object):
    """
    swquota is a WSGI middleware for Openstack Swift Proxy. It blocks write
    requests (PUT, POST) if a given quota is exceeded while DELETE requests
    are still allowed.

    swquota request an URL with the name of the account appended and uses the
    returned body data as quota size in bytes. The easiest way is to put
    objects with the name of the account as key and size in bytes as the
    content into a public readable container.

    memcache is used to lower the number of subsequent HTTP requests.

    The following shows an example proxy-server.conf:

    [filter:swquota]
    paste.filter_factory = swquota:filter_factory
    quota_account = auth_swquota
    quota_container = quotas
    #cache_timeout = 300
    #request_timeout = 15

    """

    def __init__(self, app, conf):
        self.app = app
        self.conf = conf

    def _get_quota(self, accountname):
        quota_url = self.conf.get('quota_url', None)
        if not quota_url:
            raise Exception('swquota: missing quota_url setting')

        request_timeout = self.conf.get('request_timeout', 5)
        #pylint:disable=E1101
        parsed_url = urlparse.urlparse(quota_url)
        if parsed_url.scheme == "http":
            conn = httplib.HTTPConnection(parsed_url.netloc,
                                          timeout=request_timeout)
        else:
            conn = httplib.HTTPSConnection(parsed_url.netloc,
                                           timeout=request_timeout)
        conn.request("GET", parsed_url.path + "/" + accountname)
        #pylint:enable=E1101
        response = conn.getresponse()
        if response.status == 200:
            limit = int(response.read())
        else:
            limit = -1
            self.app.logger.warn("Quota request for %s failed (%s)",
                                 accountname, response.status)
        conn.close()
        return limit

    def _get_usage(self, account, env):
        request = make_pre_authed_request(env, 'HEAD', '/v1/' + account)
        response = request.get_response(self.app)
        for (key, value) in response.headers.items():
            if key == 'x-account-bytes-used':
                bytes_used = value
        return bytes_used

    def __call__(self, env, start_response):
        if env['REQUEST_METHOD'] in ('POST', 'PUT'):
            if 'PATH_INFO' in env:
                accountname = env['PATH_INFO'].split('/')[2]
                memcache_client = cache_from_env(env)
                if not memcache_client:
                    raise Exception('Memcache required')
                memcache_key = "quota_exceeded_%s" % (accountname, )
                quota_exceeded = memcache_client.get(memcache_key)
                if quota_exceeded is None:
                    quota_exceeded = False

                    used_bytes = self._get_usage(accountname, env)
                    quota = self._get_quota(accountname)

                    if quota >= 0 and quota < used_bytes:
                        quota_exceeded = True
                        self.app.logger.warn("Quota exceeded: %s %s > %s",
                                             accountname, used_bytes, quota)

                    memcache_client.set(
                        memcache_key,
                        quota_exceeded,
                        timeout=float(self.conf.get('cache_timeout', 60)))

                if quota_exceeded:
                    #A different return code is needed for Swift S3
                    if 'HTTP_AUTHORIZATION' in env:
                        if env['HTTP_AUTHORIZATION'][0:3] == "AWS":
                            return HTTPUnauthorized()(env, start_response)
                    return HTTPForbidden()(env, start_response)
        return self.app(env, start_response)


def filter_factory(global_conf, **local_conf):
    """Returns a WSGI filter app for use with paste.deploy."""
    conf = global_conf.copy()
    conf.update(local_conf)

    def auth_filter(app):
        return Swquota(app, conf)
    return auth_filter
