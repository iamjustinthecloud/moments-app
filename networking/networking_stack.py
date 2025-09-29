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

        self.create_vpc()

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
