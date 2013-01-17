# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import unittest

try:
    from swift.common.swob import Request
except ImportError:
    from webob.exc import Request

from swquota.middleware import Swquota


class FakeCache(object):
    def __init__(self, val):
        self.val = val

    def get(self, *args):
        return self.val

    def set(self, *args, **kwargs):
        pass


class FakeApp(object):
    def __init__(self, headers=[]):
        self.headers = headers

    def __call__(self, env, start_response):
        start_response('200 OK', self.headers)
        return []


class FakeMissingApp(object):
    def __init__(self):
        pass

    def __call__(self, env, start_response):
        start_response('404 Not Found', self.headers)
        return []


def start_response(*args):
    pass


class TestAccountQuota(unittest.TestCase):

    def test_unauthorized(self):
        headers = [('x-account-bytes-used', 1000), ]
        app = Swquota(FakeApp(headers), {})
        cache = FakeCache(None)
        req = Request.blank('/v1/a/c/o',
                            environ={'REQUEST_METHOD': 'PUT',
                                     'swift.cache': cache})
        res = req.get_response(app)
        #Response code of 200 because authentication itself is not done here
        self.assertEquals(res.status_int, 200)

    def test_no_quotas(self):
        headers = [('x-account-bytes-used', 1000), ]
        app = Swquota(FakeApp(headers), {})
        cache = FakeCache(None)
        req = Request.blank('/v1/a/c/o',
                            environ={'REQUEST_METHOD': 'PUT',
                                     'swift.cache': cache,
                                     'REMOTE_USER': 'a'})
        res = req.get_response(app)
        self.assertEquals(res.status_int, 200)

    def test_exceed_bytes_quota(self):
        headers = [('x-account-bytes-used', 1000),
                   ('x-account-meta-bytes-limit', 0)]
        app = Swquota(FakeApp(headers), {})
        cache = FakeCache(None)
        req = Request.blank('/v1/a/c/o',
                            environ={'REQUEST_METHOD': 'PUT',
                                     'swift.cache': cache,
                                     'REMOTE_USER': 'a'})
        res = req.get_response(app)
        self.assertEquals(res.status_int, 413)

    def test_exceed_bytes_quota_reseller(self):
        headers = [('x-account-bytes-used', 1000),
                   ('x-account-meta-bytes-limit', 0)]
        app = Swquota(FakeApp(headers), {})
        cache = FakeCache(None)
        req = Request.blank('/v1/a/c/o',
                            environ={'REQUEST_METHOD': 'PUT',
                                     'swift.cache': cache,
                                     'REMOTE_USER': 'a.,.reseller_admin'})
        res = req.get_response(app)
        self.assertEquals(res.status_int, 200)

    def test_not_exceed_bytes_quota(self):
        headers = [('x-account-bytes-used', 1000),
                   ('x-account-meta-bytes-limit', 2000)]
        app = Swquota(FakeApp(headers), {})
        cache = FakeCache(None)
        req = Request.blank('/v1/a/c/o',
                            environ={'REQUEST_METHOD': 'PUT',
                                     'swift.cache': cache,
                                     'REMOTE_USER': 'a'})
        res = req.get_response(app)
        self.assertEquals(res.status_int, 200)

    def test_invalid_quotas(self):
        headers = [('x-account-bytes-used', 0), ]
        app = Swquota(FakeApp(headers), {})
        req = Request.blank('/v1/a/c',
                            environ={'REQUEST_METHOD': 'POST',
                                     'HTTP_X_ACCOUNT_META_BYTES_LIMIT': 'abc',
                                     'REMOTE_USER': 'a'})
        res = req.get_response(app, {})
        self.assertEquals(res.status_int, 403)

    def test_valid_quotas_admin(self):
        headers = [('x-account-bytes-used', 0), ]
        app = Swquota(FakeApp(headers), {})
        req = Request.blank('/v1/a/c',
                            environ={'REQUEST_METHOD': 'POST',
                                     'HTTP_X_ACCOUNT_META_BYTES_LIMIT': '100',
                                     'REMOTE_USER': 'a'})
        res = req.get_response(app, {})
        self.assertEquals(res.status_int, 403)

    def test_valid_quotas_reseller(self):
        headers = [('x-account-bytes-used', 0), ]
        app = Swquota(FakeApp(headers), {})
        req = Request.blank('/v1/a/c',
                            environ={'REQUEST_METHOD': 'POST',
                                     'HTTP_X_ACCOUNT_META_BYTES_LIMIT': 100,
                                     'REMOTE_USER': 'a.,.reseller_admin'})
        res = req.get_response(app, {})
        self.assertEquals(res.status_int, 200)

    def test_delete_quotas(self):
        headers = [('x-account-bytes-used', 0), ]
        app = Swquota(FakeApp(headers), {})
        req = Request.blank('/v1/a/c',
                            environ={'REQUEST_METHOD': 'POST',
                                     'HTTP_X_ACCOUNT_META_BYTES_LIMIT': None,
                                     'REMOTE_USER': 'a'})
        res = req.get_response(app, {})
        self.assertEquals(res.status_int, 403)

    def test_delete_quotas_reseller(self):
        headers = [('x-account-bytes-used', 0), ]
        app = Swquota(FakeApp(headers), {})
        req = Request.blank('/v1/a/c',
                            environ={'REQUEST_METHOD': 'POST',
                                     'HTTP_X_ACCOUNT_META_BYTES_LIMIT': None,
                                     'REMOTE_USER': 'a.,.reseller_admin'})
        res = req.get_response(app, {})
        self.assertEquals(res.status_int, 200)


if __name__ == '__main__':
    unittest.main()
