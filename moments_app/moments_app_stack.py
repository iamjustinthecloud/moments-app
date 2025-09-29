from aws_cdk import (
    Stack,
    aws_ssm as ssm,
)
from constructs import Construct


class MomentsAppStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.create_stack_name_ssm_parameter()

    def create_stack_name_ssm_parameter(self) -> ssm.StringParameter:
        # --- Persist stack name in SSM ---
        return ssm.StringParameter(
            self,
            "MomentsAppStackName",
            description="The name of the Moments App Stack",
            parameter_name="MomentsAppStackName",
            string_value=self.stack_name,
        )
