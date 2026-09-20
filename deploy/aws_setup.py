"""One-time AWS setup for the site's media, mirroring the cmim-media arrangement.

    .venv/bin/python deploy/aws_setup.py

Creates (idempotently), using your default AWS profile:
  * bucket  jbw-media-<account>   ACLs disabled, public-read via bucket policy
  * IAM user jbw-vm-s3            inline policy jbw-media-rw, limited to that bucket
  * an access key for that user, written to ./.env (gitignored, mode 600) and never printed
"""
import json
import os
import secrets
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

USER = 'jbw-vm-s3'
POLICY = 'jbw-media-rw'
REGION = 'us-east-1'
ENV_FILE = Path(__file__).resolve().parent.parent / '.env'
HOSTS = 'josephbochettowalsh.com,www.josephbochettowalsh.com,23.94.179.21,localhost,127.0.0.1'


def main():
    account = boto3.client('sts').get_caller_identity()['Account']
    bucket = f'jbw-media-{account}'
    s3 = boto3.client('s3', region_name=REGION)
    iam = boto3.client('iam')

    try:
        s3.head_bucket(Bucket=bucket)
        print('bucket exists:', bucket)
    except ClientError:
        s3.create_bucket(Bucket=bucket)
        print('created bucket:', bucket)
    s3.put_bucket_ownership_controls(
        Bucket=bucket, OwnershipControls={'Rules': [{'ObjectOwnership': 'BucketOwnerEnforced'}]})
    s3.put_public_access_block(Bucket=bucket, PublicAccessBlockConfiguration={
        'BlockPublicAcls': True, 'IgnorePublicAcls': True,
        'BlockPublicPolicy': False, 'RestrictPublicBuckets': False})
    s3.put_bucket_policy(Bucket=bucket, Policy=json.dumps({'Version': '2012-10-17', 'Statement': [{
        'Sid': 'PublicReadMedia', 'Effect': 'Allow', 'Principal': '*',
        'Action': 's3:GetObject', 'Resource': f'arn:aws:s3:::{bucket}/*'}]}))
    print('public-read bucket policy set, ACLs disabled')

    try:
        iam.get_user(UserName=USER)
        print('iam user exists:', USER)
    except ClientError:
        iam.create_user(UserName=USER)
        print('created iam user:', USER)
    iam.put_user_policy(UserName=USER, PolicyName=POLICY, PolicyDocument=json.dumps({
        'Version': '2012-10-17', 'Statement': [{
            'Effect': 'Allow',
            'Action': ['s3:PutObject', 's3:GetObject', 's3:DeleteObject', 's3:ListBucket'],
            'Resource': [f'arn:aws:s3:::{bucket}', f'arn:aws:s3:::{bucket}/*']}]}))
    print(f'inline policy {POLICY} limits {USER} to this bucket')

    if ENV_FILE.exists() and 'AWS_SECRET_ACCESS_KEY' in ENV_FILE.read_text():
        print(f'{ENV_FILE} already holds a key; not creating another')
        return
    key = iam.create_access_key(UserName=USER)['AccessKey']
    ENV_FILE.write_text(
        f'DJANGO_SECRET_KEY={secrets.token_urlsafe(64)}\n'
        'DJANGO_DEBUG=0\n'
        f'DJANGO_ALLOWED_HOSTS={HOSTS}\n'
        f'AWS_STORAGE_BUCKET_NAME={bucket}\n'
        f'AWS_S3_REGION_NAME={REGION}\n'
        f"AWS_ACCESS_KEY_ID={key['AccessKeyId']}\n"
        f"AWS_SECRET_ACCESS_KEY={key['SecretAccessKey']}\n")
    os.chmod(ENV_FILE, 0o600)
    print(f"access key (ending {key['AccessKeyId'][-4:]}) written to {ENV_FILE}")


if __name__ == '__main__':
    main()
