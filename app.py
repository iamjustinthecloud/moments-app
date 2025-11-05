#!/usr/bin/env python3
"""AWS CDK entrypoint for provisioning the Moments infrastructure.

This module wires up the core application and networking stacks, ensuring they
share a single deployment environment sourced from the CDK CLI defaults. Update
or override the environment variables to target a different account or region.
"""
import os

import aws_cdk as cdk
from aws_cdk import Environment

# Stacks will be defined in later commits — imports kept for project scaffolding
from moments_app.moments_app_stack import MomentsAppStack
from networking.networking_stack import NetworkingStack

app = cdk.App()

env = Environment(
    account=os.getenv("CDK_DEFAULT_ACCOUNT"),
    region=os.getenv("CDK_DEFAULT_REGION"),
)

MomentsAppStack(
    app,
    "MomentsAppStack",
    env=env,
)
# Provision networking resources (VPC, subnets, gateways, etc.) alongside the app stack.
NetworkingStack(app, "NetworkingStack", env=env)


app.synth()
