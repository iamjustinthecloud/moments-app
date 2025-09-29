from aws_cdk import (
    Stack,
    aws_ssm as ssm,
    aws_s3 as s3,
    RemovalPolicy,
    Duration,
    aws_sqs as sqs,
    aws_events as events,
    aws_events_targets as targets,

)
from constructs import Construct


class MomentsAppStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.create_stack_name_ssm_parameter()
        self.create_s3_bucket()
        # --- Queues ---
        dlq = self.create_hello_dlq()
        hello_queue = self.create_hello_queue(dlq)  # type: ignore

        # --- Add SQS target to the rule ---
        self.create_hello_rule().add_target(targets.SqsQueue(hello_queue))  # type: ignore

    # Resource creation

    def create_stack_name_ssm_parameter(self) -> ssm.StringParameter:
        """Persist stack name in SSM"""
        return ssm.StringParameter(
            self,
            "MomentsAppStackName",
            description="The name of the Moments App Stack",
            parameter_name="MomentsAppStackName",
            string_value=self.stack_name,
        )

    def create_s3_bucket(self):
        """Create the S3 Bucket."""
        return s3.Bucket(
            self,
            "MomentsBucket",
            removal_policy=RemovalPolicy.DESTROY,
            bucket_name="moments-app-bucket",
        )

    def create_hello_queue(self, dlq: sqs.IQueue) -> sqs.Queue:
        """Create the main queue with a DLQ."""
        return sqs.Queue(
            self,
            "HelloQueue",
            queue_name="HelloQueue",
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3,
                queue=dlq,
            ),
        )
    def create_hello_dlq(self) -> sqs.Queue:
        """Create the dead-letter queue."""
        return sqs.Queue(
            self,
            "HelloDLQ",
            queue_name="HelloDLQ",
            retention_period=Duration.days(7),
        )

    def create_hello_rule(self):
        """Create the CloudWatch Event Rule"""
        return events.Rule(
            self,
            "HelloLambdaRule",
            rule_name="HelloLambdaRule",
            schedule=events.Schedule.cron(minute="*"),
        )

