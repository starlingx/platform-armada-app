#
# SPDX-License-Identifier: Apache-2.0
#

from sysinv.tests.db import base as dbbase
from sysinv.tests.helm.test_helm import HelmOperatorTestSuiteMixin
from sysinv.common import constants


class K8SAppPlatformAppMixin(object):
    app_name = constants.HELM_APP_PLATFORM
    path_name = app_name + '.tgz'

    def setUp(self):
        super(K8SAppPlatformAppMixin, self).setUp()


# Test Configuration:
# - Controller
# - IPv6
# - Ceph Storage
# - platform-integ-apps app
class K8SAppPlatformControllerTestCase(K8SAppPlatformAppMixin,
                                       dbbase.BaseIPv6Mixin,
                                       dbbase.BaseCephStorageBackendMixin,
                                       HelmOperatorTestSuiteMixin,
                                       dbbase.ControllerHostTestCase):
    pass


# Test Configuration:
# - AIO
# - IPv4
# - Ceph Storage
# - platform-integ-apps app
class K8SAppPlatformAIOTestCase(K8SAppPlatformAppMixin,
                                dbbase.BaseCephStorageBackendMixin,
                                HelmOperatorTestSuiteMixin,
                                dbbase.AIOSimplexHostTestCase):
    pass
