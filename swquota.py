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

from webob.exc import HTTPForbidden, HTTPUnauthorized, Request
from swift.common.utils import cache_from_env
from swift.common.wsgi import make_pre_authed_request


class Swquota(object):
    """
    swquota is a WSGI middleware for Openstack Swift Proxy. It blocks write
    requests (PUT, POST) if a given quota is exceeded while DELETE requests
    are still allowed.

    swquota uses the x-account-meta-bytes-limit metadata to store the quota.
    Write requests to this metadata setting are only allowed for resellers.
    There is no quota limit if x-account-meta-bytes-limit is not set.

    memcache is used to lower the number of subsequent HTTP requests.

    The following shows an example proxy-server.conf:

    [filter:swquota]
    paste.filter_factory = swquota:filter_factory
    #cache_timeout = 300

    """

    def __init__(self, app, conf):
        self.app = app
        self.conf = conf

    def _get_quota(self, account, env):
        request = make_pre_authed_request(env, 'HEAD', '/v1/' + account)
        response = request.get_response(self.app)
        quota = -1
        for (key, value) in response.headers.items():
            if key == 'x-account-bytes-used':
                bytes_used = int(value)
            if key == 'x-account-meta-bytes-limit':
                quota = int(value)
        return (bytes_used, quota)

    def _header_write_allowed(self, request, env):
        user = env['REMOTE_USER']
        if ".reseller_admin" in user.split(','):
            return True
        for header in request.headers:
            if header.lower() == 'x-account-meta-bytes-limit':
                return False
        return True

    def __call__(self, env, start_response):
        request = Request(env)
        self.app.logger.warn(str(env))
        if request.method in ("POST", "PUT"):
            if not self._header_write_allowed(request, env):
                return HTTPForbidden()(env, start_response)

            if 'PATH_INFO' in env:
                accountname = env['PATH_INFO'].split('/')[2]
                memcache_client = cache_from_env(env)
                if not memcache_client:
                    raise Exception('Memcache required')
                memcache_key = "quota_exceeded_%s" % (accountname, )
                quota_exceeded = memcache_client.get(memcache_key)
                if quota_exceeded is None:
                    quota_exceeded = False

                    (used_bytes, quota) = self._get_quota(accountname, env)

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
