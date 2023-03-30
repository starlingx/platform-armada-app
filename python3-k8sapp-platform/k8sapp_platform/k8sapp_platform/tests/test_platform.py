#
# Copyright (c) 2023 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

from k8sapp_platform.tests import test_plugins

from sysinv.db import api as dbapi
from sysinv.tests.helm import base
from sysinv.tests.db import base as dbbase
from sysinv.tests.db import utils as dbutils


class PlatformTestCase(test_plugins.K8SAppPlatformAppMixin,
                       base.HelmTestCaseMixin):

    def setUp(self):
        super(PlatformTestCase, self).setUp()
        self.app = dbutils.create_test_app(name='platform')
        self.dbapi = dbapi.get_instance()


class PlatformTestCaseDummy(PlatformTestCase,
                            dbbase.ProvisionedControllerHostTestCase):
    # without a test zuul will fail
    def test_dummy(self):
        pass
