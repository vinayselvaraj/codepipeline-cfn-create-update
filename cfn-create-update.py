#!/usr/bin/env python

import boto3
from botocore.client import Config

import json
import os
import sys
import tempfile
import zipfile

# Get environment variables
CODEPIPELINE_ARTIFACT_CREDENTIALS = json.loads(os.environ['CODEPIPELINE_ARTIFACT_CREDENTIALS'])
CODEPIPELINE_USER_PARAMS          = json.loads(os.environ['CODEPIPELINE_USER_PARAMS'])
CODEPIPELINE_INPUT_ARTIFACTS      = json.loads(os.environ['CODEPIPELINE_INPUT_ARTIFACTS'])
CODEPIPELINE_OUTPUT_ARTIFACTS     = json.loads(os.environ['CODEPIPELINE_OUTPUT_ARTIFACTS'])

# Parse user parameters
user_params = dict()
pairs = CODEPIPELINE_USER_PARAMS.split(',')
for pair in pairs:
    kv = pair.split('=')
    user_params[ kv[0].strip() ] = kv[1].strip()

# Setup S3 client using CodePipeline provided credentials
cp_s3_client = boto3.client('s3',
                             config=Config(signature_version='s3v4'),
                             region_name=user_params['awsRegion'],
                             aws_access_key_id=CODEPIPELINE_ARTIFACT_CREDENTIALS['accessKeyId'],
                             aws_secret_access_key=CODEPIPELINE_ARTIFACT_CREDENTIALS['secretAccessKey'],
                             aws_session_token=CODEPIPELINE_ARTIFACT_CREDENTIALS['sessionToken'])

# Get input artifacts
sourceBundleArtifact = None
imageNameTagArtifact = None

for artifact in CODEPIPELINE_INPUT_ARTIFACTS:
    if artifact['name'] == 'SourceBundle':
        sourceBundleArtifact = artifact
    elif artifact['name'] == 'ImageNameTag':
        imageNameTagArtifact = artifact

if sourceBundleArtifact == None or imageNameTagArtifact == None:
    print "SourceBundle and ImageNameTag must be provided"
    sys.exit(1)


_, srcBundleFile = tempfile.mkstemp()
cp_s3_client.download_file(
                            sourceBundleArtifact['location']['s3Location']['bucketName'],
                            sourceBundleArtifact['location']['s3Location']['objectKey'],
                            srcBundleFile)

_, imageNameTagFile = tempfile.mkstemp()
cp_s3_client.download_file(
                            imageNameTagArtifact['location']['s3Location']['bucketName'],
                            imageNameTagArtifact['location']['s3Location']['objectKey'],
                            imageNameTagFile)

# Extract source bundle
src_bundle_dir = tempfile.mkdtemp()
zf = zipfile.ZipFile(srcBundleFile, 'r')
zf.extractAll(src_bundle_dir)
zf.close()

cfn_template = src_bundle_dir + "/" + user_params['cfnStackTemplate']
print "cfn_template = %s" % cfn_template

# Create CFN stack if it does not exist

# Update CFN stack if it does exist

# Wait for stack create/update to complete

print "-- CloudFormation Create/Update Task Complete --"