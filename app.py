#!/usr/bin/env python3
import os

import aws_cdk as cdk

# Stacks will be defined in later commits — imports kept for project scaffolding
from moments_app.moments_app_stack import MomentsAppStack
from networking.networking_stack import NetworkingStack

# Entry point for the Moments CDK application
# Defines the main application stacks for infrastructure and networking


app = cdk.App()
MomentsAppStack(
    app,
    "MomentsAppStack",
)
NetworkingStack(app, "NetworkingStack")


app.synth()
