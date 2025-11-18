from attrs import define, field
from aws_cdk import RemovalPolicy, Stack, aws_logs as logs
from typing import Optional

import common.constants as constants


@define(slots=True, frozen=True)
class StackContext:
    scope: Stack
    env: str = field(
        default=constants.DEFAULT_ENV,
        metadata={"description": "Deployment environment (dev, staging, prod)"},
    )
    service: str = field(default=constants.SERVICE_NAME, init=False)
    domain: str = field(default=constants.DOMAIN)
    component: str = field(default=constants.COMPONENT)

    @property
    def aws_account_id(self) -> str:
        return Stack.of(self.scope).account

    @property
    def aws_region(self) -> str:
        return Stack.of(self.scope).region

    # ---------- layers ----------
    def build_power_tools_layer_arn(self) -> str:
        region = self.aws_region
        runtime = constants.POWER_TOOLS_PYTHON_RUNTIME
        version = constants.POWER_TOOLS_VERSION
        lambda_layer_account = constants.POWER_TOOLS_LAMBDA_LAYER_ACCOUNT
        power_tools_type = constants.POWER_TOOLS_LAMBDA_LAYER_NAME
        architecture = constants.POWER_TOOLS_ARCHITECTURE
        if not region:
            raise ValueError(
                "AWS region is not set, unable to resolve Power Tools Layer ARN"
            )
        return constants.POWER_TOOLS_LAYER.format(
            region=region,
            runtime=runtime,
            version=version,
            lambda_layer_account=lambda_layer_account,
            power_tools_type=power_tools_type,
            architecture=architecture,
        )

    # ---------- naming ----------
    def build_resource_name(
        self, resource_type: str, action: Optional[str] = None
    ) -> str:
        """Build resource name with optional action.

        Examples:
            - Without action: moments-gmail-ingestion-function-dev
            - With action: moments-gmail-ingestion-retriever-function-dev
        """
        if action:
            return f"{self.service}-{self.domain}-{self.component}-{action}-{resource_type}-{self.env}".lower()
        return f"{self.service}-{self.domain}-{self.component}-{resource_type}-{self.env}".lower()

    def build_resource_id(self, resource_type: str, action: Optional[str] = None) -> str:
        """Build resource ID with optional action.

        Examples:
            - Without action: MomentsGmailIngestionFunction
            - With action: MomentsGmailIngestionRetrieverFunction
        """
        if action:
            return (
                f"{self.service.capitalize()}"
                f"{self.domain.capitalize()}"
                f"{self.component.capitalize()}"
                f"{action.capitalize()}"
                f"{resource_type.capitalize()}"
            )
        return (
            f"{self.service.capitalize()}"
            f"{self.domain.capitalize()}"
            f"{self.component.capitalize()}"
            f"{resource_type.capitalize()}"
        )

    # TODO: Move to a log group resource helper module
    def build_log_group(
        self, function_name: str, action: Optional[str] = None
    ) -> logs.LogGroup:
        return logs.LogGroup(
            self.scope,
            self.build_resource_id("LogGroup", action=action),
            log_group_name=f"/aws/lambda/{self.build_resource_name(function_name, action=action)}",
            removal_policy=RemovalPolicy.DESTROY,
            retention=logs.RetentionDays.ONE_YEAR,
        )
