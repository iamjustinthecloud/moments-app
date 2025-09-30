from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
)
from constructs import Construct

VPC_NAME = "moments-vpc"
VPC_CIDR = "10.0.0.0/16"
SUBNET_NAME = "moments-subnet"
CIDR_MASK = 24


class NetworkingStack(Stack):

    def __init__(
        self, scope: Construct, construct_id: str, vpc: ec2.IVpc = None, **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        vpc = vpc or self.create_vpc()
        nat_instance = self.create_nat_instance(vpc)
        self.add_route_to_nat(vpc, nat_instance)

    @staticmethod
    def get_user_data(filename):
        with open("./user_data/" + filename) as file:
            user_data = file.read()
        return user_data

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
                destination_cidr_blrock="0.0.0.0/0",
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
