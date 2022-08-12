import glob
import hashlib
import io
import json
import os
import time
import zipfile
from datetime import datetime

import boto3

os.environ["AWS_ACCESS_KEY_ID"] = "xxx"
os.environ["AWS_SECRET_ACCESS_KEY"] = "xxx"
os.environ["AWS_DEFAULT_REGION"] = "us-east-2"


iam_client = boto3.client("iam")
s3_client = boto3.client("s3")
lambda_client = boto3.client("lambda")
apigw_client = boto3.client("apigatewayv2")
sts_client = boto3.client("sts")
our_id = sts_client.get_caller_identity().get("Account")
date_time = datetime.utcnow().strftime("%Y-%m-%d_%H.%M.%S")

bucket_name = "plasmacan-code"
lambda_name = "plasmacan_func"
api_name = "plasmacan_api"


def main():

    create_bucket()

    print("processing layer directory")  # noqa: T001
    layer_obj, layer_digest = zipdir("tmp-layer")

    print("processing code directory")  # noqa: T001
    code_obj, code_digest = zipdir("tmp-code")

    layer_arn = publish_lambda_layer(layer_obj, layer_digest)
    function_arn = create_lambda(code_obj, code_digest, layer_arn)
    create_apigw(function_arn)
    print("done!")  # noqa: T001


def create_apigw(function_arn):
    resp = apigw_client.get_apis()
    for item in resp["Items"]:
        if item["Name"] == api_name:
            print("skipping api gateway creation - already exists")  # noqa: T001
            return

    resp = apigw_client.create_api(
        Name=api_name,
        ProtocolType="HTTP",
        Target=function_arn,
    )


def zipdir(src_dir):
    prefix_len = len(src_dir) + 1  # +1 because of / after
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, allowZip64=False, compresslevel=9) as zip_file:
        sha = hashlib.sha256()
        for path in glob.glob(f"{src_dir}/**", recursive=True):
            if os.path.isdir(path) and not os.listdir(path):  # empty directory
                # "/" at the end of file with no contents means directory in zip format
                internal_zip_name = f"{path[prefix_len:]}/"
                zip_file.writestr(internal_zip_name, "")
                sha.update(internal_zip_name.encode())
            if os.path.isfile(path):
                with open(path, "rb") as f:
                    internal_zip_name = path[prefix_len:]
                    sha.update(internal_zip_name.encode())
                    file_bin = f.read()
                    sha.update(file_bin)
                    zip_file.writestr(internal_zip_name, file_bin)
    zip_buffer.seek(0)
    return (zip_buffer, sha.hexdigest())


def create_bucket():

    print("getting account buckets")  # noqa: T001
    bucket_exists = False
    resp = s3_client.list_buckets()
    for bucket in resp["Buckets"]:
        if bucket["Name"] == bucket_name:
            bucket_exists = True

    if bucket_exists:
        print("s3 bucket already exists, skipping")  # noqa: T001
    else:

        print("creating bucket")  # noqa: T001
        s3_client.create_bucket(
            Bucket=bucket_name,
            ACL="private",
            CreateBucketConfiguration={"LocationConstraint": os.environ["AWS_DEFAULT_REGION"]},
        )

        print("encrypting bucket")  # noqa: T001
        s3_client.put_bucket_encryption(
            Bucket=bucket_name,
            ServerSideEncryptionConfiguration={
                "Rules": [
                    {"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}},
                ]
            },
        )

        print("blocking all bucket public access")  # noqa: T001
        s3_client.put_public_access_block(
            Bucket=bucket_name,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": True,
                "IgnorePublicAcls": True,
                "BlockPublicPolicy": True,
                "RestrictPublicBuckets": True,
            },
        )


def create_lambda_role():
    try:
        response = iam_client.create_role(
            RoleName="LambdaBasicExecution",
            AssumeRolePolicyDocument=json.dumps(LambdaBasicExecution_role_policy),
        )
        print(response)  # noqa: T001
    except iam_client.exceptions.EntityAlreadyExistsException:
        pass

    role = iam_client.get_role(RoleName="LambdaBasicExecution")
    role_arn = role["Role"]["Arn"]
    return role_arn


def publish_lambda_layer(layer_obj, layer_digest):

    layer_was_altered = False
    resp = lambda_client.list_layer_versions(LayerName=f"{lambda_name}_layer")
    for version in resp["LayerVersions"]:
        if layer_digest in version["Description"]:
            print("The layer has not changed. Skipping")  # noqa: T001
            layer_arn = version["LayerVersionArn"]
            return layer_arn
        else:
            layer_was_altered = True
            print("The layer has changed")  # noqa: T001

    print("uploading lambda layer")  # noqa: T001
    layer_path = f"{date_time}_layer.zip"
    s3_client.upload_fileobj(layer_obj, bucket_name, layer_path)

    resp = lambda_client.publish_layer_version(
        LayerName=f"{lambda_name}_layer",
        Description=f"sha:{layer_digest}",
        Content={
            "S3Bucket": bucket_name,
            "S3Key": layer_path,
        },
        CompatibleRuntimes=[
            "python3.9",
        ],
        CompatibleArchitectures=[
            "arm64",
        ],
    )
    new_version = resp["Version"]
    layer_arn = resp["LayerVersionArn"]
    print("published new layer")  # noqa: T001

    all_versions = []
    resp = lambda_client.list_layer_versions(LayerName=f"{lambda_name}_layer")
    for version in resp["LayerVersions"]:
        all_versions.append(version["Version"])

    if layer_was_altered:
        try:
            wait_until_function_ready()
            print("updating function configuration with new layer")  # noqa: T001
            lambda_client.update_function_configuration(
                FunctionName=lambda_name,
                Layers=[layer_arn],
            )
        except lambda_client.exceptions.ResourceNotFoundException:
            print("could not update function as it does not exist")  # noqa: T001

    print("deleting old layer version")  # noqa: T001
    for version in all_versions:
        if version != new_version:
            lambda_client.delete_layer_version(LayerName=f"{lambda_name}_layer", VersionNumber=version)
    return layer_arn


def wait_until_function_ready():
    while True:
        resp = lambda_client.get_function(FunctionName=lambda_name)
        if (
            resp["Configuration"]["State"] != "Active"
            or resp["Configuration"]["LastUpdateStatus"] == "InProgress"
        ):
            print("waiting for active lambda")  # noqa: T001
            time.sleep(1)
        else:
            break


def create_lambda(code_obj, code_digest, layer_arn):
    code_path = f"{date_time}_code.zip"

    function_code_changed = True
    function_already_exists = False
    resp = lambda_client.list_functions()
    for function in resp["Functions"]:
        if function["FunctionName"] == lambda_name:
            function_already_exists = True
            print("function already exists")  # noqa: T001

            function_arn = function["FunctionArn"]
            resp = lambda_client.list_tags(Resource=function_arn)
            if code_digest in resp["Tags"]["sha_digest"]:
                print("Function code has not changed. Skipping")  # noqa: T001
                function_code_changed = False
            else:
                print("Function code has changed.")  # noqa: T001

    if function_already_exists:
        if function_code_changed:

            print("uploading new function code")  # noqa: T001
            s3_client.upload_fileobj(code_obj, bucket_name, code_path)

            wait_until_function_ready()
            print("updating function code")  # noqa: T001
            lambda_client.update_function_code(
                FunctionName=lambda_name,
                S3Bucket=bucket_name,
                S3Key=code_path,
                Publish=False,
                Architectures=[
                    "arm64",
                ],
            )

            print("tagging function with digest")  # noqa: T001
            lambda_client.tag_resource(
                Resource=function_arn,
                Tags={"sha_digest": code_digest},
            )

    else:
        print("uploading function code")  # noqa: T001
        s3_client.upload_fileobj(code_obj, bucket_name, code_path)

        print("creating lambda role")  # noqa: T001
        role_arn = create_lambda_role()

        print("creating lambda function")  # noqa: T001
        lambda_client.create_function(
            FunctionName=lambda_name,
            Runtime="python3.9",
            Role=role_arn,
            Code={"S3Key": code_path, "S3Bucket": bucket_name},
            Timeout=900,
            MemorySize=128,
            Architectures=[
                "arm64",
            ],
            Layers=[layer_arn],
            Tags={"sha_digest": code_digest},
            Handler="plasma.lambda_handler",
            Environment={
                "Variables": {
                    "FOO": "bar",
                }
            },
        )

        print("setting lambda permissions")  # noqa: T001
        resp = lambda_client.add_permission(
            FunctionName=lambda_name,
            StatementId="permit_apigateway_invoke",
            Action="lambda:InvokeFunction",
            Principal="apigateway.amazonaws.com",
            SourceAccount=our_id,
        )

    resp = lambda_client.get_function(FunctionName=lambda_name)
    return resp["Configuration"]["FunctionArn"]


LambdaBasicExecution_role_policy = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "",
            "Effect": "Allow",
            "Principal": {"Service": "lambda.amazonaws.com"},
            "Action": "sts:AssumeRole",
        }
    ],
}


if __name__ == "__main__":
    main()
