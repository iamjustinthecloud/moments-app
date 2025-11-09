from typing import Union

from aws_cdk import (
    CfnOutput,
    Duration,
    Stack,
    aws_autoscaling as autoscaling,
    aws_ec2 as ec2,
    aws_elasticloadbalancingv2 as elbv2,
    aws_ssm as ssm,
)
from constructs import Construct

from common import constants


class NetworkingStack(Stack):

    def __init__(
        self, scope: Construct, construct_id: str, vpc: ec2.IVpc | None = None, **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        vpc = vpc or self.create_vpc()
        self.vpc = vpc
        self.vpc_endpoint()
        self.create_vpc_id_ssm_parameter()
        nat_instance = self.create_nat_instance(vpc)
        self.add_route_to_nat(vpc, nat_instance)
        web_instance_auto_scaling = self.create_web_instance(vpc)
        alb = self.create_application_load_balancer(vpc, web_instance_auto_scaling)

        CfnOutput(self, "AlbDnsName", value=alb.load_balancer_dns_name)
        CfnOutput(self, "AlbUrl", value="http://" + alb.load_balancer_dns_name)
        CfnOutput(self, "VpcId", value=vpc.vpc_id)

    def create_vpc_id_ssm_parameter(self) -> ssm.StringParameter:
        """Persist vpc id in SSM"""
        return ssm.StringParameter(
            self,
            "MomentsVPCID",
            description="Contains the Moments VPC ID",
            parameter_name="MomentsVPCID",
            string_value=self.vpc.vpc_id,
        )

    @staticmethod
    def get_user_data(filename):
        with open("./user_data/" + filename) as file:
            user_data = file.read()
        return user_data

    def create_application_load_balancer(
        self, vpc: ec2.IVpc, web_instance_auto_scaling
    ) -> elbv2.ApplicationLoadBalancer:
        alb = elbv2.ApplicationLoadBalancer(
            self,
            id="ApplicationLoadBalancer",
            vpc=vpc,
            internet_facing=True,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
        )
        http_listener = alb.add_listener("HTTPListener", port=80)
        tg = http_listener.add_targets(
            "MomentsAppFleet", port=8080, targets=[web_instance_auto_scaling]
        )
        tg.configure_health_check(path="/health", healthy_http_codes="200,301")
        web_instance_auto_scaling.connections.allow_from(
            alb, ec2.Port.tcp(8080), "ALB access on target instance"
        )
        return alb

    def create_nat_instance(self, vpc: ec2.IVpc) -> ec2.Instance:
        user_data = self.get_user_data("nat_instance")
        amazon_linux = ec2.MachineImage.latest_amazon_linux2()
        nat_instance = ec2.Instance(
            self,
            id="NatInstance",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            source_dest_check=False,
            user_data=ec2.UserData.custom(user_data),
            security_group=self.create_nat_sg(vpc),
            machine_image=amazon_linux,
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T3, ec2.InstanceSize.MICRO
            ),
        )
        return nat_instance

    def add_route_to_nat(self, vpc: ec2.IVpc, nat_instance) -> None:
        for subnet in vpc.private_subnets:
            ec2.CfnRoute(
                self,
                id=f"PrivateRouteToNat{subnet.node.id}",
                route_table_id=subnet.route_table.route_table_id,
                destination_cidr_block=constants.ANY_IPV4_CIDR,
                instance_id=nat_instance.instance_id,
            )

    def create_nat_sg(self, vpc: ec2.IVpc) -> ec2.SecurityGroup:
        nat_sg = ec2.SecurityGroup(
            self,
            id="NatSG",
            vpc=vpc,
            allow_all_outbound=False,
            description="Security group for the Nat Instance",
        )
        nat_sg.add_ingress_rule(
            peer=ec2.Peer.ipv4(constants.VPC_CIDR),
            connection=ec2.Port.tcp(80),
            description="Allow inbound HTTP (TCP/80) from VPC CIDR for NAT forwarding",
        )
        nat_sg.add_ingress_rule(
            peer=ec2.Peer.ipv4(constants.VPC_CIDR),
            connection=ec2.Port.tcp(443),
            description="Allow inbound HTTPS (TCP/443) from VPC CIDR for NAT forwarding",
        )
        nat_sg.add_egress_rule(
            peer=ec2.Peer.ipv4(constants.ANY_IPV4_CIDR),
            connection=ec2.Port.tcp(80),
            description=f"Allow outbound HTTP (TCP/80) to internet ({constants.ANY_IPV4_CIDR}) for NAT egress",
        )
        nat_sg.add_egress_rule(
            peer=ec2.Peer.ipv4(constants.ANY_IPV4_CIDR),
            connection=ec2.Port.tcp(443),
            description=f"Allow outbound HTTPS (TCP/443) to internet ({constants.ANY_IPV4_CIDR}) for NAT egress",
        )
        return nat_sg

    def vpc_endpoint(self) -> None:
        """Add common VPC endpoints to the existing VPC."""
        # Gateway VPC endpoint for S3 (uses route tables in selected subnets)
        self.vpc.add_gateway_endpoint(
            "S3Endpoint",
            service=ec2.GatewayVpcEndpointAwsService.S3,
            subnets=[
                ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            ],
        )

        # Interface VPC endpoint for CloudWatch Logs (ENIs in selected subnets)
        self.vpc.add_interface_endpoint(
            "CloudWatchLogsEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS,
            subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
            ),
        )

    def create_vpc(self) -> ec2.Vpc:

        vpc = ec2.Vpc(
            self,
            "MomentsVPC",
            nat_gateways=0,
            vpc_name=constants.VPC_NAME,
            ip_addresses=ec2.IpAddresses.cidr(constants.VPC_CIDR),
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public-Subnet",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=constants.CIDR_MASK,
                ),
                ec2.SubnetConfiguration(
                    name="Private-Subnet",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=constants.CIDR_MASK,
                ),
            ],
        )
        return vpc

    def create_web_instance(
        self, vpc: Union[ec2.Vpc, ec2.IVpc]
    ) -> autoscaling.AutoScalingGroup:
        amazon_linux = ec2.MachineImage.latest_amazon_linux2()
        user_data = self.get_user_data("web_server")

        web_instance_auto_scaling = autoscaling.AutoScalingGroup(
            self,
            id="MomentsWebServerAutoScalingGroup",
            vpc=vpc,
            machine_image=amazon_linux,
            user_data=ec2.UserData.custom(user_data),
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
            ),
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T3, ec2.InstanceSize.MICRO
            ),
            min_capacity=1,
            max_capacity=2,
            desired_capacity=1,
            health_check=autoscaling.HealthCheck.elb(grace=Duration.seconds(120)),
        )

        return web_instance_auto_scaling
