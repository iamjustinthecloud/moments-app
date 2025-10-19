from aws_cdk import (
    Stack,
    aws_s3 as s3,
    RemovalPolicy,
    Duration,
    aws_sqs as sqs,
    aws_lambda as lambda_,
    aws_logs as logs,
    aws_lambda_event_sources as lambda_event_sources,
    aws_apigatewayv2 as apigwv2,
)
from constructs import Construct

GMAIL_INGESTOR = "GmailIngestor"


class MomentsAppStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.create_s3_static_site_bucket()
        # --- Queues ---
        gmail_ingestor_dlq = self.create_gmail_ingestor_dlq()
        gmail_ingestor_queue = self.create_gmail_ingestor_queue(gmail_ingestor_dlq)  # type: ignore
        # --- API Gateway ---
        self.create_api_gateway_http_api()
        # --- Create Lambda subscribed to SQS ---
        self.create_gmail_ingestor_lambda(gmail_ingestor_queue=gmail_ingestor_queue, gmail_ingestor_dlq=gmail_ingestor_dlq)  # type: ignore

    # Resource creation

    def create_s3_static_site_bucket(self):
        """Create the S3 Bucket with web assets."""
        return s3.Bucket(
            self,
            "MomentsStaticSiteBucket",
            removal_policy=RemovalPolicy.DESTROY,
            bucket_name="moments-static-site-bucket",
        )

    def create_api_gateway_http_api(self):
        log_group = logs.LogGroup(
            self,
            "MomentsApiAccessLogs",
            log_group_name="/aws/apigateway/moments/dev",
            removal_policy=RemovalPolicy.DESTROY,
            retention=logs.RetentionDays.ONE_YEAR,
        )

        # Using L1 CfnStage for access logs; HttpStage lacks support as of CDK 2.219
        http_api = apigwv2.CfnApi(
            self,
            "MomentsHttpAPI",
            name="MomentsHttpAPI",
            protocol_type="HTTP",
        )

        apigwv2.CfnStage(
            self,
            "DevStage",
            api_id=http_api.ref,
            stage_name="dev",
            access_log_settings=apigwv2.CfnStage.AccessLogSettingsProperty(
                destination_arn=log_group.log_group_arn,
                format="$context.requestId $context.identity.sourceIp $context.requestTime $context.httpMethod $context.path $context.status $context.protocol $context.responseLength",
            ),
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
        self, gmail_ingestor_queue: sqs.IQueue, gmail_ingestor_dlq: sqs.IQueue
    ) -> lambda_.Function:
        gmail_ingestor_lambda_log_group = logs.LogGroup(
            self,
            f"{GMAIL_INGESTOR}LogGroup",
            log_group_name=f"/aws/lambda/{GMAIL_INGESTOR}",
            removal_policy=RemovalPolicy.DESTROY,
        )

        gmail_ingestor_lambda_fn = lambda_.Function(
            self,
            f"{GMAIL_INGESTOR}",
            runtime=lambda_.Runtime.PYTHON_3_12,  # type: ignore
            handler="gmail_ingestor.handler",
            code=lambda_.Code.from_asset("lambdas"),
            timeout=Duration.seconds(10),
            memory_size=128,
            environment={
                "LOG_LEVEL": "INFO",
                "DEAD_LETTER_QUEUE_URL": gmail_ingestor_dlq.queue_url,
            },
            function_name=f"{GMAIL_INGESTOR}",
            log_group=gmail_ingestor_lambda_log_group,
        )

        gmail_ingestor_lambda_fn.node.add_dependency(gmail_ingestor_lambda_log_group)
        gmail_ingestor_lambda_fn.add_event_source(
            lambda_event_sources.SqsEventSource(
                gmail_ingestor_queue,
                batch_size=10,
                max_batching_window=Duration.seconds(30),
                report_batch_item_failures=True,
            )
        )
        return gmail_ingestor_lambda_fn
