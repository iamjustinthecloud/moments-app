from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_autoscaling as autoscaling,
    aws_elasticloadbalancingv2 as elbv2,
    aws_ssm as ssm,
    CfnOutput
)
from constructs import Construct
from typing import Union

VPC_NAME = "moments-vpc"
VPC_CIDR = "10.0.0.0/16"
SUBNET_NAME = "moments-subnet"
CIDR_MASK = 24


class NetworkingStack(Stack):

    def __init__(
        self, scope: Construct, construct_id: str, vpc: ec2.IVpc | None = None, **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        vpc = vpc or self.create_vpc()
        self.vpc = vpc
        self.create_vpc_id_ssm_parameter()
        nat_instance = self.create_nat_instance(vpc)
        self.add_route_to_nat(vpc, nat_instance)
        web_instance_auto_scaling = self.create_web_instance(vpc)
        alb = self.create_application_load_balancer(vpc, web_instance_auto_scaling)

        CfnOutput(self, "ALB DNS name: ", value=alb.load_balancer_dns_name)
        CfnOutput(self, "URL: ", value="http://" + alb.load_balancer_dns_name)
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
            vpc_subnets=ec2.SubnetSelection(
                availability_zones=["us-east-1a","us-east-1b"],
                subnet_type=ec2.SubnetType.PUBLIC,
            ),
        )
        http_listener = alb.add_listener("HTTPListener", port=80)
        tg = http_listener.add_targets("MomentsAppFleet", port=8080, targets=[web_instance_auto_scaling])
        tg.configure_health_check(healthy_http_codes="200,301")
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
                destination_cidr_block="0.0.0.0/0",
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
            peer=ec2.Peer.ipv4(VPC_CIDR),
            connection=ec2.Port.tcp(80),
            description="HTTP ingress",
        )
        nat_sg.add_ingress_rule(
            peer=ec2.Peer.ipv4(VPC_CIDR),
            connection=ec2.Port.tcp(443),
            description="HTTPS ingress",
        )
        nat_sg.add_egress_rule(
            peer=ec2.Peer.ipv4("0.0.0.0/0"),
            connection=ec2.Port.tcp(80),
            description="HTTP egress",
        )
        nat_sg.add_egress_rule(
            peer=ec2.Peer.ipv4("0.0.0.0/0"),
            connection=ec2.Port.tcp(443),
            description="HTTPS egress",
        )
        return nat_sg

    def vpc_endpoint(self):
        """VPC Endpoint"""
        vpc_endpoint = ec2.Vpc(
            self,
            "vpc-endpoint",
        )
        return vpc_endpoint

    def create_vpc(self) -> ec2.Vpc:

        vpc = ec2.Vpc(
            self,
            "MomentsVPC",
            vpc_name=VPC_NAME,
            ip_addresses=ec2.IpAddresses.cidr(VPC_CIDR),
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public-Subnet",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=CIDR_MASK,
                ),
                ec2.SubnetConfiguration(
                    name="Private-Subnet",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=CIDR_MASK,
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
                availability_zones=["us-east-1a","us-east-1b"],
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
            ),
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T3, ec2.InstanceSize.MICRO
            ),
        )
        return web_instance_auto_scaling
