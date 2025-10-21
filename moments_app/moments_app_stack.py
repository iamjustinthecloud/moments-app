from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
)
from aws_cdk import (
    aws_apigatewayv2 as apigwv2,
)
from aws_cdk import (
    aws_apigatewayv2_integrations as apigwv2_integrations,
)
from aws_cdk import (
    aws_lambda as lambda_,
)
from aws_cdk import (
    aws_lambda_event_sources as lambda_event_sources,
)
from aws_cdk import (
    aws_logs as logs,
)
from aws_cdk import (
    aws_s3 as s3,
)
from aws_cdk import (
    aws_sqs as sqs,
)
from constructs import Construct

GMAIL_INGESTOR = "GmailIngestor"


class MomentsAppStack(Stack):
    aws_account_id: str
    aws_region: str

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.aws_account_id = Stack.of(self).account
        self.aws_region = Stack.of(self).region

        self.create_s3_static_site_bucket()
        # Queues
        gmail_ingestor_dlq = self.create_gmail_ingestor_dlq()
        gmail_ingestor_queue = self.create_gmail_ingestor_queue(gmail_ingestor_dlq)
        # API Gateway
        gmail_ingestor_lambda = self.create_gmail_ingestor_lambda(
            gmail_ingestor_queue=gmail_ingestor_queue,
            gmail_ingestor_dlq=gmail_ingestor_dlq,
        )
        self.create_api_gateway_http_api(gmail_ingestor_lambda=gmail_ingestor_lambda)

    # Resource creation

    def create_s3_static_site_bucket(self):
        """Create the S3 Bucket with web assets."""
        return s3.Bucket(
            self,
            "MomentsStaticSiteBucket",
            removal_policy=RemovalPolicy.DESTROY,
            bucket_name=f"moments-static-site-bucket-{self.aws_account_id}-{self.aws_region}",
            auto_delete_objects=True,
        )

    def create_api_gateway_http_api(self, gmail_ingestor_lambda: lambda_.IFunction):
        """Create HTTP API and integrate it with the Gmail Ingestor Lambda."""
        http_api = apigwv2.HttpApi(
            self,
            "MomentsHttpAPI",
            api_name="MomentsHttpAPI",
            create_default_stage=True,
        )

        # Define Lambda integration
        integration = apigwv2_integrations.HttpLambdaIntegration(
            "GmailIngestorIntegration", handler=gmail_ingestor_lambda
        )

        # Add route
        http_api.add_routes(
            path="/",
            methods=[apigwv2.HttpMethod.GET],
            integration=integration,
        )

        return http_api

    def create_gmail_ingestor_queue(self, gmail_ingestor_dlq: sqs.IQueue) -> sqs.Queue:
        """Create the main queue with a DLQ."""
        return sqs.Queue(
            self,
            f"{GMAIL_INGESTOR}Queue",
            queue_name=f"{GMAIL_INGESTOR}Queue",
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3,
                queue=gmail_ingestor_dlq,
            ),
        )

    def create_gmail_ingestor_dlq(self) -> sqs.Queue:
        """Create the dead-letter queue."""
        return sqs.Queue(
            self,
            f"{GMAIL_INGESTOR}DLQ",
            queue_name=f"{GMAIL_INGESTOR}DLQ",
            retention_period=Duration.days(14),
        )

    def create_gmail_ingestor_lambda(
        self,
        gmail_ingestor_queue: sqs.IQueue,
        gmail_ingestor_dlq: sqs.IQueue,
    ) -> lambda_.Function:

        logs.LogGroup(
            self,
            f"{GMAIL_INGESTOR}LogGroup",
            log_group_name=f"/aws/lambda/{GMAIL_INGESTOR}",
            removal_policy=RemovalPolicy.DESTROY,
            retention=logs.RetentionDays.ONE_YEAR,
        )

        gmail_ingestor_lambda = lambda_.Function(
            self,
            f"{GMAIL_INGESTOR}",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="gmail_ingestor.handler",
            code=lambda_.Code.from_asset("lambdas"),
            timeout=Duration.seconds(10),
            memory_size=128,
            environment={
                "LOG_LEVEL": "INFO",
                "DEAD_LETTER_QUEUE_URL": gmail_ingestor_dlq.queue_url,
            },
            function_name=f"{GMAIL_INGESTOR}",
        )

        gmail_ingestor_lambda.add_event_source(
            lambda_event_sources.SqsEventSource(
                gmail_ingestor_queue,
                batch_size=10,
                max_batching_window=Duration.seconds(30),
                report_batch_item_failures=True,
            )
        )
        return gmail_ingestor_lambda
