import azure.batch as batch
import azure.batch.batch_auth as batchauth
import azure.batch.models as batchmodels
from azure.common.credentials import ServicePrincipalCredentials
from misc import helpers
import configparser
import datetime


class BatchPool:

    def __init__(self, config = '../configs/azurebatch.cfg', credentials = '../configs/SECRET_paleast_credentials.cfg'):
        """
        BatchPool Object contains a reference to the pool, a credentials object to authorize pool transactions,
        and a config object to
        :param config:
        :param credentials:
        """
        self.config = configparser.ConfigParser()
        self.config.read(config)
        self.credentials = configparser.ConfigParser()
        self.credentials.read(credentials)
        self.client = self._login_to_batch()

    def _login_to_batch(self):
        # credentials2 = batchauth.SharedKeyCredentials(self.credentials.get('BATCH', 'batchaccountname'),
        #                                              self.credentials.get('BATCH', 'batchaccountkey'))

        # Use ServicePrincipal for Custom Image loading
        credentials2 = ServicePrincipalCredentials(
            client_id=self.credentials.get('BATCH', 'clientID'),
            secret=self.credentials.get('BATCH', 'secret'),
            tenant=self.credentials.get('BATCH', 'tenantID'),
            resource="https://batch.core.windows.net/"
        )
        batch_client = batch.BatchServiceClient(credentials2,
                                                batch_url=self.credentials.get('BATCH', 'batchserviceurl'))

        return batch_client

    def expand_pool(self, size):
        print(f"Attempting to resize... {size}")
        try:
            self.client.pool.resize(pool_id=self.config.get('POOL', 'id'), pool_resize_parameter=size)
        except Exception as e:
            print(f"something went wrong in the resize! {e.with_traceback()}")

    def launch_mc_server(self, maxNodes = None):

        if maxNodes is None:
            maxNodes = int(self.config.get('POOL', 'mincount'))

        job = batchmodels.JobAddParameter(
            id="MC_server",
            pool_info=batchmodels.PoolInformation(pool_id=self.config.get('POOL', 'id')),
            on_all_tasks_complete='terminatejob',
            on_task_failure=batchmodels.OnTaskFailure.perform_exit_options_job_action
            )

        self.client.job.add(job)

        constraint = batchmodels.TaskConstraints(
            retention_time=datetime.timedelta(minutes=30),
        )

        user_identity = batch.models.UserIdentity(
            # user_name='azureuser',
            auto_user=batch.models.AutoUserSpecification(
                scope=batch.models.AutoUserScope.pool,
                elevation_level=batch.models.ElevationLevel.admin)
        )

        for count in range(1, maxNodes+1):
            task = batchmodels.TaskAddParameter(
                id=f"Server-{str(count)}",
                command_line=helpers.wrap_commands_in_shell('linux', [
                    '/home/polycraft/scripts/ping_wrapper_no_pp.sh oxygen 25565',
                ]),
                constraints=constraint,
                user_identity=user_identity)

            self.client.task.add(job_id=job.id, task=task)


    def check_or_create_pool(self, id=None):
        if id is None:
            id = self.config.get('POOL', 'id')

        if self.client.pool.exists(id):
            return self.client.pool.get(id)

        api_port = self.config.get('POOL', 'api_port')
        min_count = self.config.get('POOL', 'mincount')

        image_reference = batchmodels.ImageReference(
            virtual_machine_image_id="/subscriptions/889566d5-6e5d-4d31-a82d-b60603b3e50b/resourceGroups/polycraft-game/providers/Microsoft.Compute/galleries/polycraftImgGallery/images/polycraftBestGameServerV1/versions/1.0.0"
        )

        vmc = batchmodels.VirtualMachineConfiguration(
            image_reference=image_reference,
            node_agent_sku_id="batch.node.ubuntu 18.04"
        )

        users = [
            batchmodels.UserAccount(
                name='azureuser',
                password='adminAcct$1',
                elevation_level=batchmodels.ElevationLevel.admin),
            # batchmodels.UserAccount(
            #     name='pool-nonadmin',
            #     password='******',
            #     elevation_level=batchmodels.ElevationLevel.non_admin)
        ]

        start_task = batchmodels.StartTask(
            command_line=helpers.wrap_commands_in_shell('linux', [
                'whoami',
                'printenv',
                'usermod -aG sudo azureuser',
                'cd /home/polycraft',
                'chmod -R 777 *',
                'rm /home/polycraft/oxygen/mods/polycraft-1.5.2-20200909-21.14.01.jar',
            ]),
            wait_for_success=True,
            # user_accounts=users,
            user_identity=batchmodels.UserIdentity(
                # user_name='azureuser',
                auto_user=batchmodels.AutoUserSpecification(
                    scope=batchmodels.AutoUserScope.pool,
                    elevation_level=batchmodels.ElevationLevel.admin)
                # ),

            ),
        )

        net_config = batchmodels.NetworkConfiguration(
            endpoint_configuration=batchmodels.PoolEndpointConfiguration(
                inbound_nat_pools=[batchmodels.InboundNATPool(
                    name='minecraftServer',
                    protocol='tcp',
                    backend_port=25565,
                    frontend_port_range_start=44000,
                    frontend_port_range_end=44099,
                    network_security_group_rules=[
                        batchmodels.NetworkSecurityGroupRule(
                            priority=199,
                            access='allow',
                            source_address_prefix='*'
                        ),
                    ]
                ),
                    batchmodels.InboundNATPool(
                        name='api_port',
                        protocol='tcp',
                        backend_port=int(api_port) if api_port and api_port.isdecimal() else 9010,
                        frontend_port_range_start=44500,
                        frontend_port_range_end=44599,
                        network_security_group_rules=[
                            batchmodels.NetworkSecurityGroupRule(
                                priority=170,
                                access='allow',
                                source_address_prefix='192.168.1.0/24'      # TODO: is this the right subnet?
                            ),
                            batchmodels.NetworkSecurityGroupRule(
                                priority=175,
                                access='deny',
                                source_address_prefix='*'                   # TODO: only allow access to the right ports
                            )
                        ]
                    ),
                ])
        )

        pool = batchmodels.PoolAddParameter(
            id=id,
            vm_size=self.config.get('POOL', 'vm_size'),
            target_dedicated_nodes=int(min_count) if min_count and min_count.isdecimal() else 1,
            virtual_machine_configuration=vmc,
            start_task=start_task,
            user_accounts=users,
            network_configuration=net_config
        )

        helpers.create_pool_if_not_exist(self.client, pool)
