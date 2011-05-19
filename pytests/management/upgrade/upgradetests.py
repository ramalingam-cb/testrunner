import unittest
from TestInput import TestInputSingleton
from builds.build_query import BuildQuery
from membase.api.rest_client import RestConnection, RestHelper
from membase.helper.bucket_helper import BucketOperationHelper
from membase.helper.cluster_helper import ClusterOperationHelper
from memcached.helper.data_helper import MemcachedClientHelper
from remote.remote_util import RemoteMachineShellConnection
import logger
import time

class SingleNodeUpgradeTests(unittest.TestCase):
    #test descriptions are available http://techzone.couchbase.com/wiki/display/membase/Test+Plan+1.7.0+Upgrade

    def _install_and_upgrade(self, initial_version='1.6.5.3',
                             initialize_cluster=False,
                             create_buckets=False,
                             insert_data=False):
        inserted_keys = []
        log = logger.Logger.get_logger()
        input = TestInputSingleton.input
        rest_settings = input.membase_settings
        servers = input.servers
        server = servers[0]
        remote = RemoteMachineShellConnection(server)
        rest = RestConnection(server)
        info = remote.extract_remote_info()
        remote.membase_uninstall()
        builds, changes = BuildQuery().get_all_builds()
        build_1_6_5_3_1 = BuildQuery().find_membase_build(builds=builds,
                                                          deliverable_type=info.deliverable_type,
                                                          os_architecture=info.architecture_type,
                                                          build_version=initial_version,
                                                          product='membase-server-enterprise')
        remote.execute_command('/etc/init.d/membase-server stop')
        remote.download_build(build_1_6_5_3_1)
        #now let's install ?
        remote.membase_install(build_1_6_5_3_1)
        RestHelper(rest).is_ns_server_running(120)
        log.info("sleep for 10 seconds to wait for membase-server to start...")
        rest.init_cluster_port(rest_settings.rest_username, rest_settings.rest_password)

        if initialize_cluster:
            rest.init_cluster_memoryQuota()
            if create_buckets:
                #let's create buckets
                #wait for the bucket
                #bucket port should also be configurable , pass it as the
                #parameter to this test ? later
                BucketOperationHelper.create_default_buckets(servers=[server],
                                                             number_of_replicas=1,
                                                             assert_on_test=self)
                BucketOperationHelper.wait_till_memcached_is_ready_or_assert(servers=[server],
                                                                             bucket_port=11211,
                                                                             test=self)
                if insert_data:
                    #let's insert some data
                    distribution = {10: 0.5, 20: 0.5}
                    inserted_keys, rejected_keys =\
                    MemcachedClientHelper.load_bucket_and_return_the_keys(serverInfo=server,
                                                                          name='default',
                                                                          port=11211,
                                                                          ram_load_ratio=0.1,
                                                                          value_size_distribution=distribution)
                    log.info("wait until data is completely persisted on the disk")
                    time.sleep(30)
        filtered_builds = []
        for build in builds:
            if build.deliverable_type == info.deliverable_type and\
               build.architecture_type == info.architecture_type:
                filtered_builds.append(build)
        sorted_builds = BuildQuery().sort_builds_by_version(filtered_builds)
        latest_version = sorted_builds[0].product_version
        #pick the first one in the list
        appropriate_build = BuildQuery().find_membase_build(builds=filtered_builds,
                                                            product='membase-server-enterprise',
                                                            build_version=latest_version,
                                                            deliverable_type=info.deliverable_type,
                                                            os_architecture=info.architecture_type)
        remote.download_build(appropriate_build)
        remote.membase_upgrade(appropriate_build)
        RestHelper(rest).is_ns_server_running(120)

        pools_info = rest.get_pools_info()

        rest.init_cluster_port(rest_settings.rest_username, rest_settings.rest_password)
        time.sleep(10)
        #verify admin_creds still set

        self.assertTrue(pools_info['implementationVersion'], appropriate_build.product_version)
        if initialize_cluster:
            #TODO: how can i verify that the cluster init config is preserved
            if create_buckets:
                self.assertTrue(BucketOperationHelper.wait_for_bucket_creation('default', rest),
                                msg="bucket 'default' does not exist..")
            if insert_data:
                BucketOperationHelper.keys_exist_or_assert(keys=inserted_keys,
                                                           ip=server.ip,
                                                           port=11211,
                                                           name='default',
                                                           password='',
                                                           test=self)


    def single_node_upgrade_s1(self):
        self._install_and_upgrade(initial_version='1.6.5.3',
                                  initialize_cluster=False,
                                  insert_data=False,
                                  create_buckets=False)

    def single_node_upgrade_s2(self):
        self._install_and_upgrade(initial_version='1.6.5.3',
                                  initialize_cluster=True,
                                  insert_data=False,
                                  create_buckets=False)

    def single_node_upgrade_s3(self):
        self._install_and_upgrade(initial_version='1.6.5.3',
                                  initialize_cluster=True,
                                  insert_data=False,
                                  create_buckets=True)

    def single_node_upgrade_s4(self):
        self._install_and_upgrade(initial_version='1.6.5.3',
                                  initialize_cluster=True,
                                  insert_data=True,
                                  create_buckets=True)

    def single_node_upgrade_s5(self):
        #install the latest version and upgrade to itself
        input = TestInputSingleton.input
        servers = input.servers
        server = servers[0]
        builds, changes = BuildQuery().get_all_builds()
        remote = RemoteMachineShellConnection(server)
        info = remote.extract_remote_info()
        filtered_builds = []
        for build in builds:
            if build.deliverable_type == info.deliverable_type and\
               build.architecture_type == info.architecture_type:
                filtered_builds.append(build)
        sorted_builds = BuildQuery().sort_builds_by_version(filtered_builds)
        latest_version = sorted_builds[0].product_version
        self._install_and_upgrade(initial_version=latest_version,
                                  initialize_cluster=False,
                                  insert_data=False,
                                  create_buckets=False)
        #TODO : expect a message like 'package membase-server-1.7~basestar-1.x86_64 is already installed'


class MultipleNodeUpgradeTests(unittest.TestCase):
    #in a 3 node cluster with no buckets shut down all the nodes update all
    # nodes one by one and then restart node(1),node(2) and node(3)
    def multiple_node_upgrade_m1(self):
        input = TestInputSingleton.input
        servers = input.servers
        self._install_and_upgrade('1.6.5.3', False, False, True, len(servers))

    #in a 3 node cluster with default bucket without any keys shut down all the nodes update
    # all nodes one by one and then restart node(1),node(2) and node(3)
    def multiple_node_upgrade_m2(self):
        input = TestInputSingleton.input
        servers = input.servers
        self._install_and_upgrade('1.6.5.3', True, False, True, len(servers))


        #in a 3 node cluster with default bucket with some keys shut down all the
        # nodes update all nodes one by one and then restart node(1),node(2) and node(3)

    def multiple_node_upgrade_m3(self):
        self._install_and_upgrade('1.6.5.3', True, True, True, 1)

    def multiple_node_upgrade_m5(self):
        self._install_and_upgrade('1.6.5.3', True, False, True, 1,False)



        #for


    #let's install 1.6.5.3
    #do some bucket/init related operation
    #now only option x nodes
    #power on upgraded ones first and then the non-upgraded ones
    #start everything and wait for some time

    #return "
    def _install_and_upgrade(self, initial_version='1.6.5.3',
                             create_buckets=False,
                             insert_data=False,
                             join_nodes=False,
                             upgrade_how_many=1, start_upgraded_first=True ):
        node_upgrade_status = {}
        #then start them in whatever order you want
        inserted_keys = []
        log = logger.Logger.get_logger()
        input = TestInputSingleton.input
        rest_settings = input.membase_settings
        servers = input.servers
        builds, changes = BuildQuery().get_all_builds()

        for server in servers:
            remote = RemoteMachineShellConnection(server)
            rest = RestConnection(server)
            info = remote.extract_remote_info()
            build_1_6_5_3_1 = BuildQuery().find_membase_build(builds=builds,
                                                              deliverable_type=info.deliverable_type,
                                                              os_architecture=info.architecture_type,
                                                              build_version=initial_version,
                                                              product='membase-server-enterprise')

            remote.membase_uninstall()
            remote.execute_command('/etc/init.d/membase-server stop')
            remote.download_build(build_1_6_5_3_1)
            #now let's install ?
            remote.membase_install(build_1_6_5_3_1)
            RestHelper(rest).is_ns_server_running(120)
            log.info("sleep for 10 seconds to wait for membase-server to start...")
            rest.init_cluster_port(rest_settings.rest_username, rest_settings.rest_password)
            rest.init_cluster_memoryQuota()
            node_upgrade_status[server] = "installed"

        master = servers[0]
        if create_buckets:
            #let's create buckets
            #wait for the bucket
            #bucket port should also be configurable , pass it as the
            #parameter to this test ? later

            BucketOperationHelper.create_default_buckets(servers=[master],
                                                         number_of_replicas=1,
                                                         assert_on_test=self)
            BucketOperationHelper.wait_till_memcached_is_ready_or_assert(servers=[master],
                                                                         bucket_port=11211,
                                                                         test=self)
            if insert_data:
                #let's insert some data
                distribution = {10: 0.5, 20: 0.5}
                inserted_keys, rejected_keys =\
                MemcachedClientHelper.load_bucket_and_return_the_keys(serverInfo=master,
                                                                      name='default',
                                                                      port=11211,
                                                                      ram_load_ratio=0.1,
                                                                      value_size_distribution=distribution)
                log.info("wait until data is completely persisted on the disk")

        if join_nodes:
            ClusterOperationHelper.add_all_nodes_or_assert(master, servers, rest_settings, self)
            rest = RestConnection(master)
            nodes = rest.node_statuses()
            otpNodeIds = []
            for node in nodes:
                otpNodeIds.append(node.id)
            rebalanceStarted = rest.rebalance(otpNodeIds, [])
            self.assertTrue(rebalanceStarted,
                            "unable to start rebalance on master node {0}".format(master.ip))
            log.info('started rebalance operation on master node {0}'.format(master.ip))
            rebalanceSucceeded = rest.monitorRebalance()
            self.assertTrue(rebalanceSucceeded,
                            "rebalance operation for nodes: {0} was not successful".format(otpNodeIds))

        filtered_builds = []
        for build in builds:
            if build.deliverable_type == info.deliverable_type and\
               build.architecture_type == info.architecture_type:
                filtered_builds.append(build)
        sorted_builds = BuildQuery().sort_builds_by_version(filtered_builds)
        latest_version = sorted_builds[0].product_version
        #pick the first one in the list
        appropriate_build = BuildQuery().find_membase_build(builds=filtered_builds,
                                                            product='membase-server-enterprise',
                                                            build_version=latest_version,
                                                            deliverable_type=info.deliverable_type,
                                                            os_architecture=info.architecture_type)

        for server in servers:
            remote = RemoteMachineShellConnection(server)
            remote.stop_membase()

        time.sleep(30)

        count = 0
        for server in servers:
            remote = RemoteMachineShellConnection(server)
            remote.download_build(appropriate_build)
            remote.membase_upgrade(appropriate_build)
            RestHelper(RestConnection(server)).is_ns_server_running(120)

            pools_info = RestConnection(server).get_pools_info()

            if not join_nodes:
                RestConnection(server).init_cluster_port(rest_settings.rest_username, rest_settings.rest_password)
            node_upgrade_status[server] = "upgraded"
            if upgrade_how_many == count:
                break

            #verify admin_creds still set

            self.assertTrue(pools_info['implementationVersion'], appropriate_build.product_version)

        if start_upgraded_first:
            for server in node_upgrade_status:
                if node_upgrade_status[server] == "upgraded":
                    remote = RemoteMachineShellConnection(server)
                    remote.start_membase()
        else:
            for server in node_upgrade_status:
                if node_upgrade_status[server] == "installed":
                    remote = RemoteMachineShellConnection(server)
                    remote.start_membase()

        for server in servers:
            remote = RemoteMachineShellConnection(server)
            remote.start_membase()



        #TODO: how can i verify that the cluster init config is preserved
        if create_buckets:
            self.assertTrue(BucketOperationHelper.wait_for_bucket_creation('default', RestConnection(master)),
                            msg="bucket 'default' does not exist..")
        if insert_data:
            BucketOperationHelper.keys_exist_or_assert(keys=inserted_keys,
                                                       ip=master.ip,
                                                       port=11211,
                                                       name='default',
                                                       password='',
                                                       test=self)

        return node_upgrade_status



        

